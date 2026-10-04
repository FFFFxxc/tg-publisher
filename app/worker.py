from __future__ import annotations

import asyncio
import inspect
import logging
import shutil
import tempfile
import time
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from dataclasses import replace
from zoneinfo import ZoneInfo

from telethon import errors, functions
from telethon.tl.types import (Document, MessageEntityCustomEmoji, MessageEntityTextUrl,
                               MessageMediaDocument, MessageMediaPhoto)

from . import __version__, events
from .actions import STALE_ACTION_SEC, dispatch
from .ai import AIError, generate_caption, validate_caption
from .config import Config
from .content import filter_source_content, is_advertisement
from .db import DB
from .logic import (AI_FAILED, AI_GENERATED, AI_NO_PREVIEW, AI_PROCESSING, AI_UNCHECKED, AMBIGUOUS, FAILED,
                    OLD, PARSED, SKIPPED, backoff_seconds, build_caption, due_slot, group_messages, in_window)
from .logic import parse_ref
from .settings import RuntimeSettings
from .media import album_kind, media_batches, prepare_media, media_type
from .preview import PreviewCache
from .promo import PromoPublisher
from .weekly import WeeklyPublisher
from .tg import ensure_connected, resolve

log = logging.getLogger("worker")

UNCERTAIN = (ConnectionError, asyncio.TimeoutError, TimeoutError, OSError)
# Verified Telegram peer of «2D WEBM | аниме мемы». Titles are not proof of identity.
LINK_ALLOWED_CHANNEL_ID = 1140244688


def msg_stats(msgs) -> dict:
    """Метрики поста (альбом = сумма реакций, максимум просмотров)."""
    st = {"views": 0, "reactions": 0, "forwards": 0, "replies": 0, "media_type": media_type(msgs)}
    for m in msgs:
        st["views"] = max(st["views"], m.views or 0)
        st["forwards"] = max(st["forwards"], m.forwards or 0)
        st["replies"] = max(st["replies"], getattr(m.replies, "replies", 0) or 0)
        if m.reactions and m.reactions.results:
            st["reactions"] += sum(r.count for r in m.reactions.results)
    return st


def usable(m) -> bool:
    if m.action is not None:
        return False
    return bool(m.message) or isinstance(m.media, (MessageMediaPhoto, MessageMediaDocument))


def to_entities(specs):
    out = []
    for kind, off, ln, val in specs:
        out.append(MessageEntityCustomEmoji(off, ln, document_id=val) if kind == "emoji"
                   else MessageEntityTextUrl(off, ln, url=val))
    return out


class Worker:
    def __init__(self, cfg: Config, db: DB, client, settings: RuntimeSettings | None = None):
        self.cfg, self.db, self.client = cfg, db, client
        self.rt = settings or RuntimeSettings(db, cfg)
        self.heartbeat: dict[str, float] = {}
        self.dest = None
        self.own_sid = None
        self.caption_locks: dict[int, asyncio.Lock] = {}
        self.previews = PreviewCache(client, Path(cfg.session_path).parent / 'previews')

    async def _dest(self):
        if self.dest is None:
            self.dest = await resolve(self.client, self.cfg.destination)
        return self.dest

    async def _own_sid(self):
        if self.own_sid is None:
            self.own_sid = await self.db.ensure_source(self.cfg.destination, role="own")
        return self.own_sid

    # ================= сбор кандидатов =================
    async def collect_once(self):
        rt = await self.rt.view()
        for ref in self.cfg.sources:
            await self.db.ensure_source(ref)
        settle = datetime.now(timezone.utc) - timedelta(seconds=self.cfg.album_settle)
        for src in await self.db.sources():
            try:
                await self._collect_source(src, settle, rt)
            except UNCERTAIN:
                raise
            except Exception as e:
                log.error("source=%s read failed: %s: %s", src["ref"], type(e).__name__, e)
                await self.db.set_source_cursor(src["id"], None, f"{type(e).__name__}: {e}")
                await events.log_event(self.db, events.SOURCE_ERROR, level="warning", source_id=src["id"],
                                       message=f"{src['ref']}: {type(e).__name__}: {e}")
        await self.refresh_stats(rt.max_post_age_hours)
        await self.refresh_media_types()
        if await self.db.kv_get('media_index_version') != '1':
            await self.scan_own(force=True, rt=rt)
            await self.db.kv_set('media_index_version', '1')
        await self.db.kv_set("last_collect_at", time.time())

    async def _collect_source(self, src, settle, rt):
        entity = await resolve(self.client, src["ref"])
        last = src["last_message_id"]
        if last is None:
            latest = await self.client.get_messages(entity, limit=max(self.cfg.initial_backfill, 1))
            if not latest:
                return await self.db.set_source_cursor(src["id"], 0)
            last = (min(m.id for m in latest) - 1) if self.cfg.initial_backfill else latest[0].id
            await self.db.set_source_cursor(src["id"], last)
            log.info("source=%s initialized cursor=%s", src["ref"], last)
        batch = []
        async for m in self.client.iter_messages(entity, min_id=last, reverse=True, limit=200):
            if m.date > settle:
                break
            batch.append(m)
        if not batch:
            return
        by_id = {m.id: m for m in batch}
        added = 0
        for key, ids in group_messages([(m.id, m.grouped_id) for m in batch]):
            msgs = [by_id[i] for i in ids]
            if not any(usable(m) for m in msgs):
                continue
            text = next((m.message for m in msgs if m.message), "")
            await self.db.upsert_candidate(src["id"], key, ids, msgs[0].date, text, msg_stats(msgs),
                                           rt.ai_enabled)
            added += 1
        await self.db.set_source_cursor(src["id"], max(by_id))
        log.info("source=%s +%d candidates, cursor=%s", src["ref"], added, max(by_id))
        await events.log_event(self.db, events.SOURCE_COLLECTED, source_id=src["id"],
                               message=f"{src['ref']}: +{added}", metadata={"added": added})

    async def refresh_stats(self, max_age_h: int):
        """Обновляем просмотры/реакции кандидатов: «лучшесть» видна только спустя время."""
        rows = await self.db.candidates_for_refresh(max_age_h)
        by_src = defaultdict(list)
        for r in rows:
            by_src[r["ref"]].append(r)
        for ref, posts in by_src.items():
            try:
                entity = await resolve(self.client, ref)
                ids = [i for p in posts for i in p["source_msg_ids"]]
                got = {}
                for i in range(0, len(ids), 100):
                    for m in await self.client.get_messages(entity, ids=ids[i:i + 100]):
                        if m:
                            got[m.id] = m
                for p in posts:
                    msgs = [got[i] for i in p["source_msg_ids"] if i in got]
                    if msgs:
                        await self.db.set_stats(p["id"], msg_stats(msgs))
            except UNCERTAIN:
                raise
            except Exception as e:
                log.warning("stats refresh source=%s failed: %s", ref, e)
        if rows:
            log.info("stats refreshed for %d candidates", len(rows))

    async def refresh_media_types(self):
        rows = await self.db.unclassified_posts()
        by_src = defaultdict(list)
        for row in rows:
            by_src[row['ref']].append(row)
        for ref, posts in by_src.items():
            try:
                entity = await resolve(self.client, ref)
                ids = list(dict.fromkeys(mid for p in posts for mid in p['source_msg_ids']))
                got = {}
                for i in range(0, len(ids), 100):
                    for msg in await self.client.get_messages(entity, ids=ids[i:i+100]):
                        if msg:
                            got[msg.id] = msg
                for post in posts:
                    msgs = [got[mid] for mid in post['source_msg_ids'] if mid in got]
                    if msgs:
                        await self.db.set_media_type(post['id'], media_type(msgs))
            except UNCERTAIN:
                raise
            except Exception as exc:
                log.warning('media classification source=%s failed: %s', ref, exc)

    # ================= снимок своего канала =================
    async def scan_own(self, force=False, rt=None):
        rt = rt or await self.rt.view()
        last = float(await self.db.kv_get("own_scan_at", "0"))
        if not force and time.time() - last < self.cfg.own_scan_hours * 3600:
            return
        log.info("own channel scan start (limit %d)", self.cfg.own_scan_limit)
        dest = await self._dest()
        msgs = [m async for m in self.client.iter_messages(dest, limit=self.cfg.own_scan_limit)]
        by_id = {m.id: m for m in msgs}
        n = 0
        for key, ids in group_messages([(m.id, m.grouped_id) for m in msgs]):
            group = [by_id[i] for i in ids]
            if not any(usable(m) for m in group):
                continue
            st = msg_stats(group)
            text = next((m.message for m in group if m.message), "")
            await self.db.upsert_own(key, ids, group[0].date, text, st["reactions"], st["views"], st["forwards"], st['media_type'])
            n += 1
        await self.db.kv_set("own_scan_at", time.time())
        log.info("own channel scan done: %d posts", n)

    # ================= расписание =================
    async def scheduled_tick(self):
        rt = await self.rt.view()
        if rt.publishing_paused:
            return
        post = await self.db.claim_scheduled()
        if post:
            log.info('personal schedule due post=%s', post.id)
            await self._run(post)

    async def publish_tick(self):
        rt = await self.rt.view()
        if rt.publishing_paused:
            return log.info("publishing paused via panel, tick skipped")
        now = datetime.now(ZoneInfo(rt.tz_name))
        if rt.publish_times:
            slot = due_slot(now, rt.publish_times)
            if not slot or slot == await self.db.kv_get("last_slot"):
                return
            await self.db.kv_set("last_slot", slot)
            log.info("slot %s due", slot)
        elif not in_window(now, self.cfg.publish_window):
            return
        n = await self.db.expire_old(rt.max_post_age_hours)
        if n:
            log.info("expired %d stale candidates", n)

        post = await self.db.claim_retry()
        if post:
            log.info("retry slot: post=%s kind=%s", post.id, post.kind)
            return await self._run(post)

        pattern = rt.schedule_pattern
        idx = int(await self.db.kv_get("pattern_idx", "0"))
        planned = pattern[idx % len(pattern)] if pattern else PARSED
        for kind in (planned, OLD if planned == PARSED else PARSED):
            post = await self._pick(kind, rt)
            if post:
                if kind != planned:
                    log.info("planned %s unavailable, fallback to %s", planned, kind)
                break
        if not post:
            return log.info("slot: nothing worth publishing (planned=%s)", planned)
        await self.db.kv_set("pattern_idx", idx + 1)
        log.info("slot #%d planned=%s -> post=%s kind=%s", idx, planned, post.id, post.kind)
        await self._run(post)

    async def _pick(self, kind, rt):
        if kind == PARSED:
            await self.refresh_stats(rt.max_post_age_hours)
            return await self.db.claim_best_candidate(rt.candidate_min_age_min, rt.max_post_age_hours,
                                                      rt.baseline_days, rt.best_min_score)
        own_sid = await self._own_sid()
        await self.scan_own(rt=rt)
        return await self.db.claim_best_own(own_sid, rt.own_min_age_days, rt.repost_cooldown_days)

    async def _run(self, post):
        async with self.caption_locks.setdefault(post.id, asyncio.Lock()):
            current = await self.db.load_post(post.id)
            await self._run_locked(current or post)

    async def _run_locked(self, post):
        rt = await self.rt.view()
        tmp = tempfile.mkdtemp(prefix=f"post{post.id}_")
        try:
            await self._publish(post, tmp, rt)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ================= AI (только для спаршенных) =================
    @staticmethod
    def _source_links_allowed(post, source_entity=None):
        if source_entity is not None:
            return getattr(source_entity, 'id', None) == LINK_ALLOWED_CHANNEL_ID
        kind, value = parse_ref(post.source_ref)
        return kind == 'id' and value in (LINK_ALLOWED_CHANNEL_ID, -1000000000000 - LINK_ALLOWED_CHANNEL_ID)

    async def _ai(self, post, image: str | None, rt, source_entity=None, source_entities=None):
        if post.ai_status == 'manual':
            return post.ai_caption
        if post.kind != PARSED or not rt.ai_enabled:
            return None
        allow_links = self._source_links_allowed(post, source_entity)

        def caption_text(text):
            text = validate_caption(text)
            if not allow_links:
                text = filter_source_content(text)[0]
            return validate_caption(text)

        if post.ai_status == AI_GENERATED:
            try:
                return caption_text(post.ai_caption)
            except AIError as e:
                await self.db.set_ai(post.id, AI_FAILED, None, str(e))
                if rt.ai_required:
                    raise
                return None
        if post.ai_status != AI_UNCHECKED:
            if rt.ai_required:
                raise AIError(f"required AI caption is unavailable (status={post.ai_status})")
            return None
        if not allow_links:
            post = replace(post, text=filter_source_content(post.text, source_entities)[0])
        if not post.text.strip() and not image:
            await self.db.set_ai(post.id, AI_NO_PREVIEW)
            if rt.ai_required:
                raise AIError("required AI caption has no text or preview")
            return None
        await self.db.set_ai(post.id, AI_PROCESSING)
        log.info("ai start post=%s", post.id)
        try:
            cap = caption_text(await asyncio.wait_for(generate_caption(rt, post.text, image), rt.ai_timeout + 15))
            await self.db.set_ai(post.id, AI_GENERATED, cap)
            log.info("ai done post=%s", post.id)
            await events.log_event(self.db, events.AI_GENERATED, post_id=post.id, message=(cap or "")[:200],
                                   metadata={"model": rt.ai_model})
            return cap
        except (AIError, asyncio.TimeoutError) as e:
            await self.db.set_ai(post.id, AI_FAILED, error=str(e) or "timeout")
            log.warning("ai failed post=%s: %s", post.id, e or "timeout")
            await events.log_event(self.db, events.AI_FAILED, level="warning", post_id=post.id,
                                   message=str(e) or "timeout")
            if rt.ai_required:
                raise
            return None

    async def _preview_image(self, msgs, files, tmp, post_id=None):
        cache = self.previews if post_id is not None else PreviewCache(self.client, tmp)
        return await cache.get(post_id if post_id is not None else 'temporary', msgs=msgs, downloaded_files=files)

    async def _valid_custom_emojis(self, entities):
        ids = list({e.document_id for e in entities if isinstance(e, MessageEntityCustomEmoji)})
        if not ids:
            return entities
        docs = await self.client(functions.messages.GetCustomEmojiDocumentsRequest(ids))
        valid = {d.id for d in docs if isinstance(d, Document)}
        if len(valid) != len(ids):
            log.warning("invalid custom emoji IDs %s: using ordinary emoji", sorted(set(ids) - valid))
        # Keep Unicode text and links; invalid IDs must not reject the whole album.
        return [e for e in entities if not isinstance(e, MessageEntityCustomEmoji) or e.document_id in valid]

    # ================= публикация =================
    async def _publish(self, post, tmp, rt):
        try:
            entity = await resolve(self.client, post.source_ref)
            msgs = [m for m in await self.client.get_messages(entity, ids=post.source_msg_ids) if m]
            if not msgs:
                await self.db.mark(post.id, SKIPPED, "source messages deleted")
                return log.info("skip post=%s: source deleted", post.id)
            src_msg = next((m for m in msgs if m.message), None)
            source_body = src_msg.message if src_msg else ''
            source_entities = src_msg.entities if src_msg else None
            allow_links = self._source_links_allowed(post, entity)
            if not allow_links:
                if is_advertisement(source_body) or is_advertisement(post.text):
                    await self.db.mark(post.id, SKIPPED, 'Явная реклама из чужого канала')
                    return log.info('skip post=%s: foreign advertisement', post.id)
                source_body, source_entities = filter_source_content(source_body, source_entities)
            files, file_msgs = [], []
            for m in msgs:
                if not isinstance(m.media, (MessageMediaPhoto, MessageMediaDocument)):
                    continue
                size = getattr(getattr(m, "file", None), "size", 0) or 0
                if size > self.cfg.max_media_mb * 1024 * 1024:
                    log.warning("post=%s msg=%s media too big (%d B), dropped", post.id, m.id, size)
                    continue
                log.info("download start post=%s msg=%s dc=%s", post.id, m.id, _dc(m))
                t = time.monotonic()
                media_dir = Path(tmp) / str(m.id)
                media_dir.mkdir(exist_ok=True)
                path = await self.client.download_media(m, file=str(media_dir) + "/")
                if not path:
                    raise RuntimeError(f"download returned nothing for msg {m.id}")
                files.append(path)
                file_msgs.append(m)
                log.info("download done post=%s msg=%s %.1fs", post.id, m.id, time.monotonic() - t)
            if not files and not source_body.strip():
                await self.db.mark(post.id, SKIPPED, "nothing to publish")
                return
            image = await self._preview_image(msgs, files, tmp, post.id) if post.kind == PARSED and rt.ai_enabled else None
            try:
                ai_text = await self._ai(replace(post, text=source_body), image, rt, entity, source_entities)
            except (AIError, asyncio.TimeoutError) as e:
                await self.db.mark(post.id, FAILED, f"AI_REQUIRED: {e}")
                await events.log_event(self.db, events.PUBLISH_FAILED, level="error", post_id=post.id,
                                       message=f"AI_REQUIRED: {e}")
                return
            body = ai_text or source_body
            body_ents = None if ai_text else source_entities
            if not allow_links:
                if is_advertisement(body):
                    await self.db.mark(post.id, SKIPPED, 'Явная реклама из чужого канала')
                    return
                body, body_ents = filter_source_content(body, body_ents)
            caption, kept, fspecs = build_caption(body, body_ents, rt.footer, bool(files), self.cfg.premium)
            entities = await self._valid_custom_emojis((kept or []) + to_entities(fspecs))
            dest = await self._dest()
            # Upload before marking send_started; these RPCs do not publish a post.
            prepared = [(await prepare_media(self.client, m, path), album_kind(m))
                        for m, path in zip(file_msgs, files)]
        except errors.FloodWaitError as e:
            await self.db.retry_later(post.id, e.seconds + 5, f"FloodWait {e.seconds}s before send")
            return log.warning("post=%s flood wait %ss (pre-send), requeued", post.id, e.seconds)
        except Exception as e:
            return await self._pre_send_failure(post, e, rt)

        await self.db.mark_send_started(post.id)
        log.info("publish start post=%s kind=%s files=%d", post.id, post.kind, len(files))
        await events.log_event(self.db, events.PUBLISH_STARTED, post_id=post.id,
                               message=f"kind={post.kind} files={len(files)}")
        ids = []
        try:
            if files:
                for batch in media_batches(prepared):
                    sent = await self.client.send_file(
                        dest, batch if len(batch) > 1 else batch[0],
                        caption=caption if not ids else "",
                        formatting_entities=entities if not ids else [], parse_mode=None)
                    ids.extend(s.id for s in (sent if isinstance(sent, list) else [sent]))
                    # A crash/next-batch failure must never retry already published media.
                    await self.db.record_sent(post.id, ids)
            else:
                sent = await self.client.send_message(dest, caption, formatting_entities=entities,
                                                      parse_mode=None, link_preview=False)
                ids = [sent.id]
        except errors.FloodWaitError as e:
            if ids:
                return await self._partial_send_failure(post, ids, e)
            await self.db.retry_later(post.id, e.seconds + 5, f"FloodWait {e.seconds}s on send")
            return log.warning("post=%s flood wait on send, requeued", post.id)
        except errors.RPCError as e:
            if ids:
                return await self._partial_send_failure(post, ids, e)
            return await self._pre_send_failure(post, e, rt)
        except UNCERTAIN as e:
            await self.db.mark(post.id, AMBIGUOUS, f"network error during send: {type(e).__name__}")
            log.error("post=%s AMBIGUOUS: %s during send, check channel then requeue", post.id, type(e).__name__)
            await events.log_event(self.db, events.PUBLISH_AMBIGUOUS, level="error", post_id=post.id,
                                   message=f"{type(e).__name__} during send, check channel then requeue")
            raise
        except Exception as e:
            # Includes persistence failures after a confirmed send. Do not send the next batch.
            await self._partial_send_failure(post, ids, e)
            raise
        log.info("publish done post=%s dest_ids=%s", post.id, ids)
        for i in range(5):
            try:
                await self.db.mark_published(post.id, ids)
                await events.log_event(self.db, events.PUBLISH_COMPLETED, post_id=post.id,
                                       message=f"dest_ids={ids}", metadata={"dest_msg_ids": ids})
                return
            except Exception as e:
                log.error("post=%s persist dest_ids failed (try %d): %s", post.id, i + 1, e)
                await asyncio.sleep(2 ** i)

    async def _partial_send_failure(self, post, ids, e):
        err = f"partial send dest_ids={ids}: {type(e).__name__}: {e}"
        await self.db.mark(post.id, AMBIGUOUS, err)
        log.error("post=%s AMBIGUOUS: %s", post.id, err)
        await events.log_event(self.db, events.PUBLISH_AMBIGUOUS, level="error", post_id=post.id,
                               message=err, metadata={"dest_msg_ids": ids})

    async def _pre_send_failure(self, post, e, rt):
        err = f"{type(e).__name__}: {e}"
        if post.attempts >= self.cfg.max_attempts:
            await self.db.mark(post.id, FAILED, err)
            log.error("post=%s failed permanently: %s", post.id, err)
            await events.log_event(self.db, events.PUBLISH_FAILED, level="error", post_id=post.id, message=err)
        else:
            delay = backoff_seconds(post.attempts)
            await self.db.retry_later(post.id, delay, err)
            log.warning("post=%s retry in %ss: %s", post.id, delay, err)
            await events.log_event(self.db, events.PUBLISH_RETRY, level="warning", post_id=post.id,
                                   message=f"retry in {delay}s: {err}")
        if isinstance(e, UNCERTAIN):
            raise e

    # ================= persistent dashboard actions =================
    async def actions_tick(self):
        stale = await self.db.fail_stale_actions(STALE_ACTION_SEC,
                                                 f"stale: no progress for {STALE_ACTION_SEC}s")
        for a in stale:
            log.error("action %s %s marked stale", a["id"], a["kind"])
            await events.log_event(self.db, events.ACTION_FAILED, level="error", action_id=a["id"],
                                   message=f"{a['kind']}: stale action")
        a = await self.db.claim_action()
        if not a:
            return
        log.info("action %s %s start", a["id"], a["kind"])
        try:
            result = await dispatch(self, a["kind"], a.get("payload"))
            await self.db.finish_action(a["id"], result or {})
            await events.log_event(self.db, events.ACTION_COMPLETED, action_id=a["id"],
                                   post_id=a.get("post_id"), message=a["kind"], metadata={"result": result})
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            await self.db.fail_action(a["id"], err)
            await events.log_event(self.db, events.ACTION_FAILED, level="error", action_id=a["id"],
                                   post_id=a.get("post_id"), message=a["kind"], metadata={"error": err})
            log.exception("action %s failed", a["id"])

    # ================= циклы =================
    async def _collect_interval(self) -> int:
        rt = await self.rt.view()
        return rt.collect_interval

    async def prepare_caption(self, pid: int, force=False):
        async with self.caption_locks.setdefault(pid, asyncio.Lock()):
            row = await self.db.get_post(pid)
            if not row or row['kind'] != PARSED or row['status'] not in ('candidate','pending','failed','expired'):
                return
            if row.get('send_started_at') or row.get('dest_msg_ids'):
                return
            if not force and row['ai_status'] != AI_UNCHECKED:
                return
            rt = await self.rt.view()
            if not rt.ai_enabled:
                return
            if force:
                await self.db.set_ai(pid, AI_UNCHECKED)
            post = await self.db.load_post(pid)
            try:
                entity = await resolve(self.client, post.source_ref)
                msgs = [m for m in await self.client.get_messages(entity, ids=post.source_msg_ids) if m]
                with tempfile.TemporaryDirectory() as tmp:
                    image = await self._preview_image(msgs, [], tmp, pid)
                    await self._ai(post, image, rt, entity)
            except (AIError, asyncio.TimeoutError):
                log.warning('queue caption failed post=%s', pid)
            except Exception as exc:
                await self.db.set_ai(pid, AI_FAILED, error=f'{type(exc).__name__}: {exc}')
                log.warning('queue caption preparation failed post=%s: %s', pid, type(exc).__name__)

    async def caption_tick(self):
        if not (await self.rt.view()).ai_enabled:
            return
        pid = await self.db.next_caption_post()
        if pid is not None:
            await self.prepare_caption(pid)

    async def loop(self, name, interval, fn):
        log.info("loop %s started", name)
        while True:
            self.heartbeat[name] = time.time()
            try:
                await ensure_connected(self.client)
                await fn()
            except UNCERTAIN as e:
                log.error("%s: telegram transport error %s, reconnecting", name, type(e).__name__)
                try:
                    await self.client.disconnect()
                except Exception:
                    pass
            except Exception:
                log.exception("%s: unexpected error", name)
            iv = interval
            if callable(iv):
                iv = iv()
            if inspect.isawaitable(iv):
                iv = await iv
            await asyncio.sleep(iv)

    async def watchdog(self, limits):
        while True:
            await asyncio.sleep(60)
            for name, last in self.heartbeat.items():
                if time.time() - last > limits[name] * 3 + 300:
                    log.error("heartbeat: loop %s stalled for %.0fs", name, time.time() - last)

    async def run(self):
        log.info("worker v%s starting %r", __version__, self.cfg)
        await self.db.recover()
        await self.db._q("UPDATE posts SET ai_status='unchecked',ai_error=NULL WHERE ai_status='processing' "
                         "AND status IN ('candidate','pending') AND send_started_at IS NULL AND cardinality(dest_msg_ids)=0")
        # зависшие actions от прошлого процесса: processing -> failed, дублей публикации нет
        await self.db.fail_stale_actions(0, "interrupted by worker restart")
        await events.log_event(self.db, events.WORKER_STARTED, message=f"v{__version__}")
        pub_every = 30 if self.cfg.publish_times else self.cfg.publish_interval
        limits = {"collect": self.cfg.collect_interval, "publish": pub_every, "actions": 5, "scheduled": 5, "promo": 30, "captions": 120, "weekly": 30}
        await asyncio.gather(self.loop("collect", self._collect_interval, self.collect_once),
                             self.loop("publish", pub_every, self.publish_tick),
                             self.loop("actions", 5, self.actions_tick),
                             self.loop("scheduled", 5, self.scheduled_tick),
                             self.loop("promo", 30, PromoPublisher(self).tick),
                             self.loop("weekly", 30, WeeklyPublisher(self).tick),
                             self.loop("captions", 5, self.caption_tick),
                             self.watchdog(limits))


def _dc(m):
    return getattr(m.photo or m.document, "dc_id", "?")
