"""Copy weekly top posts from our private destination to the public comics channel."""
from __future__ import annotations

import asyncio
import hashlib
import tempfile
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from time import monotonic
from zoneinfo import ZoneInfo

from telethon import errors
from telethon.tl.types import MessageEntityBold, MessageEntityCustomEmoji, MessageEntityTextUrl, MessageMediaDocument, MessageMediaPhoto

from . import events
from .content import filter_source_content
from .logic import build_caption, group_messages
from .media import album_kind, media_batches, prepare_media
from .tg import resolve

TARGET = '@comics_komixy'
TZ = ZoneInfo('Europe/Moscow')
TIMES = (time(12), time(16), time(20))
EMOJI_ID = 5462931610028510371
FOOTER = [{'emoji': '☝️', 'emoji_id': EMOJI_ID, 'text': 'Весь наш контент ☝️',
           'url': 'https://t.me/comics_komixy/29'}]


def daily_times(now):
    """Stable daily 1..3 quota: identical across processes and restarts."""
    day = now.astimezone(TZ).date().isoformat()
    count = 1 + int.from_bytes(hashlib.sha256(day.encode()).digest()[:4], 'big') % 3
    return (TIMES[0],) if count == 1 else (TIMES[0], TIMES[2]) if count == 2 else TIMES


def weekly_slot(now):
    """Latest due slot, retained until the Moscow day ends."""
    slots = due_slots(now)
    return slots[-1] if slots else None


def due_slots(now):
    local = now.astimezone(TZ)
    return [local.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M')
            for t in daily_times(now) if t <= local.time()]


def ranked_groups(messages, now, settle_seconds=60):
    by_id = {m.id: m for m in messages}
    cutoff, settled = now - timedelta(days=7), now - timedelta(seconds=settle_seconds)
    result = []
    for key, ids in group_messages([(m.id, m.grouped_id) for m in messages]):
        group = [by_id[i] for i in ids]
        if not all(cutoff <= m.date <= settled and not m.action and
                   not getattr(m, 'noforwards', False) and
                   (m.message or isinstance(m.media, (MessageMediaPhoto, MessageMediaDocument))) for m in group):
            continue
        reactions = sum(sum(r.count for r in getattr(getattr(m, 'reactions', None), 'results', []) or []) for m in group)
        views = max((getattr(m, 'views', None) or 0) for m in group)
        forwards = max((getattr(m, 'forwards', None) or 0) for m in group)
        result.append(((reactions, views, forwards, max(ids)), key, group))
    return sorted(result, key=lambda row: row[0], reverse=True)


class WeeklyPublisher:
    def __init__(self, worker):
        self.w = worker

    async def candidates(self, now):
        source = await self.w._dest()
        if getattr(source, 'noforwards', False):
            raise ValueError('Закрытая группа запрещает копирование контента')
        messages, boundary = [], None
        cutoff = now - timedelta(days=7)
        async for m in self.w.client.iter_messages(source, limit=None):
            if m.date < cutoff:
                if boundary is None:
                    boundary = m.grouped_id
                elif m.grouped_id != boundary:
                    break
                messages.append(m)
                if boundary is None:
                    break
            else:
                messages.append(m)
        used = await self.w.db.weekly_used(self.w.cfg.destination)
        return [(key, group) for _, key, group in ranked_groups(messages, now, self.w.cfg.album_settle) if key not in used]

    async def prepare(self, group, tmp):
        items = []
        for m in group:
            if not isinstance(m.media, (MessageMediaPhoto, MessageMediaDocument)):
                continue
            if (getattr(getattr(m, 'file', None), 'size', 0) or 0) > self.w.cfg.max_media_mb * 1024 * 1024:
                raise ValueError(f'Слишком большой файл {m.id}: пост не обрезается')
            folder = Path(tmp) / str(m.id)
            folder.mkdir()
            path = await self.w.client.download_media(m, file=str(folder) + '/')
            if not path:
                raise RuntimeError(f'Не скачан файл {m.id}')
            items.append((await prepare_media(self.w.client, m, path), album_kind(m)))
        body = '' if items else next((m.message for m in group if m.message), '')
        if not items:
            body = filter_source_content(body, None)[0]
        # Dedicated public signature only; never leak the private-group footer.
        caption, kept, specs = build_caption(body, None, FOOTER, bool(items), self.w.cfg.premium)
        # Arrow is budgeted inside the footer, but only words form the link.
        specs = [(kind, off, length - 3 if kind == 'url' else length, value)
                 for kind, off, length, value in specs]
        entities = [MessageEntityCustomEmoji(off, length, document_id=value) if kind == 'emoji'
                    else MessageEntityTextUrl(off, length, url=value) for kind, off, length, value in specs]
        entities += [MessageEntityBold(off, length) for kind, off, length, _ in specs if kind == 'url']
        entities = await self.w._valid_custom_emojis((kept or []) + entities)
        return list(media_batches(items)), caption, entities

    async def tick(self, now=None):
        now = now or datetime.now(timezone.utc)
        slots = due_slots(now)
        if not slots or (await self.w.rt.view()).publishing_paused:
            return
        db = self.w.db
        await db.weekly_recover()
        if now.timestamp() < float(await db.kv_get('weekly_retry_after', 0)):
            return
        slot = None
        for candidate_slot in slots:
            if not await db.weekly_has_slot(candidate_slot):
                slot = candidate_slot
                break
        if slot is None:
            return
        try:
            target = await resolve(self.w.client, TARGET)
            if getattr(target, 'broadcast', False) and not (
                    getattr(target, 'creator', False) or
                    getattr(getattr(target, 'admin_rights', None), 'post_messages', False)):
                raise ValueError(f'У издателя нет права публикации в {TARGET}')
            choices = await self.candidates(now)
        except errors.FloodWaitError as exc:
            await db.kv_set('weekly_retry_after', datetime.now(timezone.utc).timestamp() + max(1, exc.seconds))
            return
        if not choices:
            if await db.weekly_claim(slot, self.w.cfg.destination, None, []):
                await db.weekly_finish(slot, 'skipped', error='Нет новых подходящих постов за 7 дней')
                await events.log_event(db, 'weekly_skipped', message=f'{slot}: {TARGET}')
            return
        key, group = choices[0]
        ids = [m.id for m in group]
        # Preparation is not a publication. Serialize by slot before downloading;
        # failed pre-send runs can retry, uncertain sends retain their reservation.
        if not await db.weekly_claim(slot, self.w.cfg.destination, key, ids):
            return
        sent_ids, started = [], monotonic()
        send_started = False
        try:
            with tempfile.TemporaryDirectory(prefix='weekly-') as tmp:
                batches, caption, entities = await asyncio.wait_for(self.prepare(group, tmp), 600)
                if (await self.w.rt.view()).publishing_paused:
                    await db.weekly_defer(slot, now.timestamp())
                    return
                current = now + timedelta(seconds=monotonic() - started)
                if current.astimezone(TZ).date() != now.astimezone(TZ).date():
                    await db.weekly_defer(slot, current.timestamp())
                    return
                await events.log_event(db, 'weekly_started', message=f'{slot}: {TARGET}', metadata={'source_ids': ids})
                if not await db.weekly_start_send(slot):
                    return
                if batches:
                    for batch in batches:
                        send_started = True
                        sent = await asyncio.wait_for(self.w.client.send_file(
                            target, batch if len(batch) > 1 else batch[0], caption=caption if not sent_ids else '',
                            formatting_entities=entities if not sent_ids else [], parse_mode=None), 300)
                        sent = sent if isinstance(sent, list) else [sent]
                        confirmed = [m.id for m in sent if m is not None]
                        sent_ids.extend(confirmed)
                        await db.weekly_finish(slot, 'sending', sent_ids)
                        if len(confirmed) != len(batch):
                            raise RuntimeError('Telegram подтвердил не весь альбом')
                else:
                    send_started = True
                    sent = await asyncio.wait_for(self.w.client.send_message(
                        target, caption, formatting_entities=entities, parse_mode=None, link_preview=False), 120)
                    sent_ids = [sent.id]
        except errors.FloodWaitError as exc:
            if not sent_ids:
                await db.weekly_defer(slot, now.timestamp() + monotonic() - started + max(1, exc.seconds))
                return
            await db.weekly_finish(slot, 'ambiguous', sent_ids, f'Partial FloodWait {exc.seconds}')
            return
        except errors.RPCError as exc:
            if sent_ids:
                await db.weekly_finish(slot, 'ambiguous', sent_ids, f'{type(exc).__name__}: {exc}')
            else:
                await db.weekly_reject(slot, f'{type(exc).__name__}: {exc}')
            await events.log_event(db, 'weekly_failed', level='error', message=f'{slot}: {type(exc).__name__}')
            return
        except Exception as exc:
            if not send_started:
                await db.weekly_defer(slot, now.timestamp() + monotonic() - started + 300)
                await events.log_event(db, 'weekly_prepare_failed', level='error', message=f'{slot}: {type(exc).__name__}: {exc}')
            else:
                await db.weekly_finish(slot, 'ambiguous', sent_ids, f'{type(exc).__name__}: {exc}')
                await events.log_event(db, 'weekly_ambiguous', level='error', message=f'{slot}: {type(exc).__name__}')
            return
        await db.weekly_finish(slot, 'published', sent_ids)
        # Catch up today's missed slots one at a time, never in a restart burst.
        await db.kv_set('weekly_retry_after', now.timestamp() + monotonic() - started + 1800)
        await events.log_event(db, 'weekly_published', message=f'{slot}: {TARGET}', metadata={'source_ids': ids, 'dest_ids': sent_ids})
