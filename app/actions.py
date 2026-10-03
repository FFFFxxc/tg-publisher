"""Persistent dashboard actions: панель только создаёт записи, исполняет их воркер
в собственном цикле (FOR UPDATE SKIP LOCKED). Никаких Telegram-операций внутри HTTP."""
from __future__ import annotations

import logging
import tempfile

from . import events
from .ai import generate_caption
from .logic import AI_UNCHECKED, PARSED, canonical_ref, group_messages
from .tg import resolve

log = logging.getLogger("actions")

BACKFILL_SIZES = (10, 25, 50, 100)
STALE_ACTION_SEC = 15 * 60


def _pid(payload: dict) -> int:
    pid = int(payload.get("post_id") or 0)
    if pid <= 0:
        raise ValueError("post_id required")
    return pid


def _sid(payload: dict) -> int:
    sid = int(payload.get("source_id") or 0)
    if sid <= 0:
        raise ValueError("source_id required")
    return sid


async def h_add_source(w, payload):
    ref = str(payload.get("ref") or "").strip()
    if not ref or len(ref) > 200:
        raise ValueError("ref обязателен (1..200 символов)")
    canon = canonical_ref(ref)
    if canon == canonical_ref(str(w.cfg.destination)):
        raise ValueError("нельзя добавлять канал назначения как источник")
    ent = await resolve(w.client, canon)
    title = getattr(ent, "title", None) or getattr(ent, "username", None) or canon
    sid, created = await w.db.add_source_checked(canon, title)
    if not created:
        return {"status": "exists", "source_id": sid, "ref": canon, "title": title}
    await events.log_event(w.db, events.SOURCE_ADDED, source_id=sid, message=canon, metadata={"title": title})
    return {"status": "created", "source_id": sid, "ref": canon, "title": title}


async def h_verify_source(w, payload):
    sid = _sid(payload)
    src = await w.db.get_source(sid)
    if not src:
        raise ValueError(f"source {sid} not found")
    ent = await resolve(w.client, src["ref"])
    msgs = await w.client.get_messages(ent, limit=1)
    last = msgs[0].id if msgs else 0
    title = getattr(ent, "title", None)
    await w.db.set_source_cursor(sid, last, None)
    await w.db.set_source_title(sid, title)
    await events.log_event(w.db, events.SOURCE_VERIFIED, source_id=sid, message="ok",
                           metadata={"last_message_id": last})
    return {"ok": True, "last_message_id": last, "title": title}


async def h_backfill_source(w, payload):
    sid = _sid(payload)
    n = int(payload.get("n") or 25)
    if n not in BACKFILL_SIZES:
        raise ValueError(f"n должен быть одним из {list(BACKFILL_SIZES)}")
    src = await w.db.get_source(sid)
    if not src:
        raise ValueError(f"source {sid} not found")
    from .worker import msg_stats, usable  # lazy: worker импортирует dispatch из этого модуля
    ent = await resolve(w.client, src["ref"])
    msgs = [m for m in await w.client.get_messages(ent, limit=n) if m]
    rt = await w.rt.view()
    by_id = {m.id: m for m in msgs}
    items = []
    for key, ids in group_messages([(m.id, m.grouped_id) for m in msgs]):
        group = [by_id[i] for i in ids]
        if not any(usable(m) for m in group):
            continue
        text = next((m.message for m in group if m.message), "")
        items.append((key, ids, group[0].date, text, msg_stats(group)))
    added = await w.db.backfill_candidates(sid, items, rt.ai_enabled)
    await w.db.set_source_title(sid, getattr(ent, "title", None))
    await events.log_event(w.db, events.SOURCE_BACKFILLED, source_id=sid, message=f"backfill {n}",
                           metadata={"added": added, "scanned": len(items)})
    return {"added": added, "scanned": len(items)}


async def h_publish_now(w, payload):
    pid = _pid(payload)
    post = await w.db.claim_post_for_publish(pid)
    if post is None:
        cur = await w.db.get_post(pid)
        if cur and cur["status"] == "published" and cur["dest_msg_ids"]:
            return {"status": "already_published", "post_id": pid, "dest_msg_ids": list(cur["dest_msg_ids"])}
        status = cur["status"] if cur else "missing"
        raise ValueError(f"нельзя опубликовать: пост в статусе {status!r} или уже подтверждён отправкой")
    await w._run(post)
    cur = await w.db.get_post(pid)
    return {"status": cur["status"], "post_id": pid}


async def h_requeue_post(w, payload):
    pid = _pid(payload)
    if not await w.db.requeue(pid):
        raise ValueError("requeue отклонён: статус не failed/ambiguous или dest_msg_ids уже подтверждены")
    await events.log_event(w.db, events.PUBLISH_RETRY, post_id=pid, message="requeued from panel")
    return {"requeued": True, "post_id": pid}


async def h_skip_post(w, payload):
    pid = _pid(payload)
    if not await w.db.skip_post(pid):
        raise ValueError("skip отклонён: пост published/processing/ambiguous или не существует")
    return {"skipped": True, "post_id": pid}


async def h_generate_ai(w, payload):
    pid = _pid(payload)
    row = await w.db.get_post(pid)
    if not row:
        raise ValueError(f"post {pid} not found")
    if row["kind"] != PARSED:
        raise ValueError("AI доступен только для parsed-постов")
    rt = await w.rt.view()
    if not rt.ai_enabled:
        raise ValueError("AI выключен")
    await w.db.set_ai(pid, AI_UNCHECKED, None, None)
    post = await w.db.load_post(pid)
    ent = await resolve(w.client, post.source_ref)
    msgs = [m for m in await w.client.get_messages(ent, ids=post.source_msg_ids) if m]
    with tempfile.TemporaryDirectory() as tmp:
        image = await w._preview_image(msgs, [], tmp)
        await w._ai(post, image, rt)
    cur = await w.db.get_post(pid)
    return {"ai_status": cur["ai_status"], "ai_caption": cur["ai_caption"], "post_id": pid}


async def h_scan_own(w, payload):
    await w.scan_own(force=True)
    n = await w.db.own_count()
    await events.log_event(w.db, events.OWN_SCANNED, message=f"{n} posts")
    return {"posts": n}


async def h_test_ai_provider(w, payload):
    rt = await w.rt.view()
    if not rt.ai_enabled:
        raise ValueError("AI выключен: включи его в разделе AI (ключ задаётся через ENV AI_API_KEY)")
    text = str(payload.get("text") or "Тест AI из панели управления").strip()[:500]
    cap = await generate_caption(rt, text, None)
    return {"ok": True, "model": rt.ai_model, "reply": cap[:300]}


async def h_repost_own(w, payload):
    key = str(payload.get("group_key") or "").strip()
    if not key:
        raise ValueError("group_key required")
    row = await w.db.get_own(key)
    if not row:
        raise ValueError("own post not found")
    own_sid = await w._own_sid()
    pid = await w.db.create_repost_from_own(own_sid, key, row["msg_ids"], row["post_date"],
                                            row["text"], row["reactions"])
    if not pid:
        raise ValueError("этот пост уже публиковался — защита от дублей")
    await w.db.mark_own_reposted(key)
    post = await w.db.claim_post_for_publish(pid)
    if post is None:
        raise ValueError("не удалось взять пост в работу")
    await w._run(post)
    cur = await w.db.get_post(pid)
    return {"status": cur["status"], "post_id": pid}


HANDLERS = {
    "add_source": h_add_source,
    "verify_source": h_verify_source,
    "backfill_source": h_backfill_source,
    "publish_now": h_publish_now,
    "requeue_post": h_requeue_post,
    "skip_post": h_skip_post,
    "generate_ai": h_generate_ai,
    "scan_own": h_scan_own,
    "test_ai_provider": h_test_ai_provider,
    "repost_own": h_repost_own,
}


async def dispatch(w, kind: str, payload):
    """Единая точка исполнения: неизвестный/кривой payload -> исключение -> action failed."""
    handler = HANDLERS.get(kind)
    if handler is None:
        raise ValueError(f"unknown action kind {kind!r}")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    return await handler(w, payload)
