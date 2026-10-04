"""Control API для веб-панели: JSON поверх aiohttp на отдельном порту.
Каждый /api/* запрос требует Authorization: Bearer CONTROL_API_TOKEN.
Секреты наружу не отдаются, SQL только параметризованный, произвольного SQL нет,
тяжёлые Telegram-операции выполняются воркером через persistent actions."""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit

from aiohttp import web
from psycopg import errors as pg_errors

from . import __version__, events
from .actions import BACKFILL_SIZES
from .db import POST_STATUSES
from .logic import next_slot, render_footer
from .networks import NetworkService
from .settings import footer_for_api, validate

log = logging.getLogger("api")

KINDS = {"parsed", "repost"}
AI_STATUSES = {"unchecked", "processing", "generated", "not_needed", "no_preview", "failed", "manual"}
EVENT_LEVELS = {"info", "warning", "error"}
MAX_BODY = 256 * 1024


def jr(data, status: int = 200) -> web.Response:
    return web.json_response(data, status=status,
                             dumps=lambda x: json.dumps(x, default=str, ensure_ascii=False))


def mask_key(key: str) -> dict:
    """Секрет не возвращаем никогда: только статус и необратимая маска с хвостом."""
    if not key:
        return {"configured": False, "mask": ""}
    tail = key[-4:] if len(key) >= 12 else ""
    return {"configured": True, "mask": "•" * 8 + tail}


def parse_paging(qs, default_limit: int = 25) -> tuple[int, int]:
    def _int(name, default, lo, hi):
        raw = qs.get(name)
        if raw is None or raw == "":
            return default
        try:
            n = int(raw)
        except ValueError as e:
            raise ValueError(f"{name} must be an integer") from e
        return max(lo, min(hi, n))
    return _int("limit", default_limit, 1, 100), _int("offset", 0, 0, 10 ** 9)


def _one_of(qs, name, allowed, f: dict):
    v = (qs.get(name) or "").strip()
    if not v:
        return
    if v not in allowed:
        raise ValueError(f"{name}: недопустимое значение {v!r}")
    f[name] = v


def _day(qs, name) -> date | None:
    v = (qs.get(name) or "").strip()
    if not v:
        return None
    try:
        return date.fromisoformat(v)
    except ValueError as e:
        raise ValueError(f"{name}: ожидается дата YYYY-MM-DD") from e


def parse_posts_filters(qs) -> dict:
    f: dict = {}
    _one_of(qs, "status", POST_STATUSES, f)
    _one_of(qs, "kind", KINDS, f)
    _one_of(qs, "media_type", {"photo", "video", "mixed", "text", "document", "unknown"}, f)
    _one_of(qs, "ai_status", AI_STATUSES, f)
    if qs.get("source_id"):
        try:
            f["source_id"] = int(qs["source_id"])
        except ValueError as e:
            raise ValueError("source_id must be an integer") from e
    d = _day(qs, "date")
    if d:
        f["date_from"] = d.isoformat()
        f["date_to"] = (d + timedelta(days=1)).isoformat()
    d = _day(qs, "date_from")
    if d:
        f["date_from"] = d.isoformat()
    d = _day(qs, "date_to")
    if d:
        f["date_to"] = (d + timedelta(days=1)).isoformat()
    q = (qs.get("q") or "").strip()
    if q:
        f["q"] = q[:200]
    return f


def parse_events_filters(qs) -> dict:
    f: dict = {}
    t = (qs.get("type") or "").strip()
    if t:
        f["type"] = t[:64]
    _one_of(qs, "level", EVENT_LEVELS, f)
    for name in ("post_id", "source_id"):
        if qs.get(name):
            try:
                f[name] = int(qs[name])
            except ValueError as e:
                raise ValueError(f"{name} must be an integer") from e
    return f


async def body_json(request: web.Request) -> dict:
    if request.content_type != "application/json":
        raise ValueError("content-type must be application/json")
    try:
        data = json.loads(await request.read())
    except ValueError as e:
        raise ValueError("bad json body") from e
    if not isinstance(data, dict):
        raise ValueError("json object expected")
    return data


def _path_id(request: web.Request) -> int:
    try:
        return int(request.match_info["id"])
    except (KeyError, ValueError) as e:
        raise ValueError("invalid id in path") from e


def _event_brief(e) -> dict | None:
    if not e:
        return None
    return {"id": e["id"], "type": e["type"], "level": e["level"], "message": e["message"],
            "post_id": e["post_id"], "source_id": e["source_id"], "created_at": e["created_at"]}


def handler(fn):
    async def wrapped(request: web.Request) -> web.Response:
        try:
            return await fn(request)
        except ValueError as e:
            return jr({"error": str(e)}, status=400)
        except LookupError as e:
            return jr({"error": str(e) or "not found"}, status=404)
        except pg_errors.ForeignKeyViolation:
            return jr({"error": "связанные записи существуют"}, status=409)
        except web.HTTPException:
            raise
        except Exception:
            log.exception("api error on %s %s", request.method, request.path)
            return jr({"error": "internal error"}, status=500)
    return wrapped


@web.middleware
async def auth_mw(request: web.Request, handler):
    token = request.app["token"]
    header = request.headers.get("Authorization", "")
    if not token or not hmac.compare_digest(header, f"Bearer {token}"):
        return jr({"error": "unauthorized"}, status=401)
    return await handler(request)


class ApiContext:
    """Тонкая обвязка над работающим воркером: тот же asyncio-процесс, та же DB."""

    def __init__(self, worker):
        self.worker = worker
        self.db = worker.db
        self.cfg = worker.cfg
        self.settings = worker.rt
        self.activity = getattr(worker, "activity", None)


# ============================ handlers ============================

@handler
async def h_overview(request: web.Request) -> web.Response:
    ctx: ApiContext = request.app["ctx"]
    w, db = ctx.worker, ctx.db
    rt = await ctx.settings.view()
    ages = {k: round(max(time.time() - v, 0)) for k, v in w.heartbeat.items()}
    online = bool(ages) and max(ages.values()) < 1800
    tz = ZoneInfo(rt.tz_name)
    now_local = datetime.now(tz)
    today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    idx = int(await db.kv_get("pattern_idx", "0"))
    pattern = rt.schedule_pattern or []
    nxt = next_slot(now_local, rt.publish_times)
    last_pub = await db.last_published_at()
    last_collect = float(await db.kv_get("last_collect_at", "0"))
    return jr({
        "worker": {"online": online, "heartbeat_age_s": ages, "version": __version__,
                   "telegram_connected": bool(w.client.is_connected()),
                   "transport": "socks5" if w.cfg.proxy else "direct"},
        "db": {"ok": await db.ping(), "schema": db.schema},
        "destination": w.cfg.destination,
        "sources_enabled": await db.enabled_sources_count(),
        "queue": await db.counts_by_status(),
        "published": await db.published_stats(today_start),
        "last_collect_age_s": round(time.time() - last_collect) if last_collect else None,
        "last_published_at": last_pub.isoformat() if last_pub else None,
        "last_error": _event_brief(await db.last_error_event()),
        "schedule": {"paused": rt.publishing_paused, "pattern": pattern, "pattern_index": idx,
                     "next_kind": pattern[idx % len(pattern)] if pattern else None,
                     "next_slot": nxt.isoformat() if nxt else None,
                     "publish_times": [t.strftime("%H:%M") for t in rt.publish_times], "tz": rt.tz_name},
    })


@handler
async def h_sources(request: web.Request) -> web.Response:
    ctx: ApiContext = request.app["ctx"]
    return jr({"items": await ctx.db.sources(only_enabled=False)})


@handler
async def h_source_add(request: web.Request) -> web.Response:
    ctx: ApiContext = request.app["ctx"]
    body = await body_json(request)
    ref = str(body.get("ref") or "").strip()
    if not ref or len(ref) > 200:
        raise ValueError("ref обязателен (1..200 символов)")
    aid = await ctx.db.create_action("add_source", {"ref": ref})
    return jr({"action_id": aid, "status": "pending"}, status=202)


@handler
async def h_source_patch(request: web.Request) -> web.Response:
    ctx: ApiContext = request.app["ctx"]
    sid = _path_id(request)
    body = await body_json(request)
    if not isinstance(body.get("enabled"), bool):
        raise ValueError("enabled (boolean) обязателен")
    if not await ctx.db.set_source_enabled(sid, body["enabled"]):
        raise LookupError(f"source {sid} not found")
    await events.log_event(ctx.db, events.SOURCE_ENABLED if body["enabled"] else events.SOURCE_DISABLED,
                           source_id=sid, message=f"enabled={body['enabled']}")
    return jr({"ok": True, "enabled": body["enabled"]})


@handler
async def h_source_delete(request: web.Request) -> web.Response:
    ctx: ApiContext = request.app["ctx"]
    sid = _path_id(request)
    res = await ctx.db.delete_source(sid)
    if res == "missing":
        raise LookupError(f"source {sid} not found")
    if res == "has_posts":
        await ctx.db.set_source_enabled(sid, False)
        await events.log_event(ctx.db, events.SOURCE_DISABLED, source_id=sid,
                               message="delete rejected: есть связанные посты — источник выключен")
        return jr({"deleted": False, "disabled": True,
                   "message": "У источника есть связанные посты (FK): вместо удаления он выключен."})
    await events.log_event(ctx.db, events.SOURCE_DELETED, source_id=sid, message="deleted")
    return jr({"deleted": True, "disabled": False})


@handler
async def h_source_check(request: web.Request) -> web.Response:
    ctx: ApiContext = request.app["ctx"]
    sid = _path_id(request)
    if not await ctx.db.get_source(sid):
        raise LookupError(f"source {sid} not found")
    aid = await ctx.db.create_action("verify_source", {"source_id": sid})
    return jr({"action_id": aid, "status": "pending"}, status=202)


@handler
async def h_source_backfill(request: web.Request) -> web.Response:
    ctx: ApiContext = request.app["ctx"]
    sid = _path_id(request)
    body = await body_json(request)
    try:
        n = int(body.get("n") or 25)
    except (TypeError, ValueError) as e:
        raise ValueError("n must be an integer") from e
    if n not in BACKFILL_SIZES:
        raise ValueError(f"n должен быть одним из {list(BACKFILL_SIZES)}")
    if not await ctx.db.get_source(sid):
        raise LookupError(f"source {sid} not found")
    aid = await ctx.db.create_action("backfill_source", {"source_id": sid, "n": n})
    return jr({"action_id": aid, "status": "pending"}, status=202)


@handler
async def h_post_preview(request: web.Request) -> web.Response:
    ctx = request.app['ctx']
    pid = _path_id(request)
    if pid <= 0:
        raise ValueError('invalid post id')
    row = await ctx.db.get_post(pid)
    if row is None:
        raise LookupError('post not found')
    try:
        image = await ctx.worker.previews.get(pid, source_ref=row['source_ref'], source_msg_ids=row['source_msg_ids'])
    except Exception as exc:
        log.warning('preview unavailable post=%s: %s', pid, type(exc).__name__)
        return jr({'error': 'Превью временно недоступно'}, status=503)
    if image is None:
        return web.Response(status=204, headers={'Cache-Control': 'no-store'})
    return web.FileResponse(image, headers={'Content-Type': 'image/jpeg', 'Cache-Control': 'private, max-age=300'})


@handler
async def h_posts(request: web.Request) -> web.Response:
    ctx: ApiContext = request.app["ctx"]
    limit, offset = parse_paging(request.query)
    filters = parse_posts_filters(request.query)
    items, total = await ctx.db.posts_page(filters, limit, offset)
    for it in items:
        it["text"] = (it.get("text") or "")[:400]
    return jr({"items": items, "total": total, "limit": limit, "offset": offset})


@handler
async def h_post(request: web.Request) -> web.Response:
    ctx: ApiContext = request.app["ctx"]
    pid = _path_id(request)
    post = await ctx.db.get_post(pid)
    if not post:
        raise LookupError(f"post {pid} not found")
    evs, _ = await ctx.db.events_page({"post_id": pid}, 50, 0)
    return jr({"post": post, "events": evs, "actions": await ctx.db.actions_for_post(pid)})


async def _post_action(request: web.Request, kind: str, payload: dict) -> web.Response:
    ctx: ApiContext = request.app["ctx"]
    pid = _path_id(request)
    aid = await ctx.db.create_action(kind, {"post_id": pid, **payload}, post_id=pid)
    return jr({"action_id": aid, "status": "pending"}, status=202)


@handler
async def h_post_publish(request: web.Request) -> web.Response:
    return await _post_action(request, "publish_now", {})


@handler
async def h_post_requeue(request: web.Request) -> web.Response:
    return await _post_action(request, "requeue_post", {})


@handler
async def h_post_skip(request: web.Request) -> web.Response:
    return await _post_action(request, "skip_post", {})


@handler
async def h_post_schedule(request: web.Request) -> web.Response:
    ctx = request.app['ctx']
    pid = _path_id(request)
    if pid <= 0:
        raise ValueError('invalid post id')
    body = await body_json(request)
    if set(body) != {'scheduled_at'}:
        raise ValueError('Укажите scheduled_at или null для отмены')
    at = body['scheduled_at']
    if at is not None:
        if not isinstance(at, str):
            raise ValueError('Ожидается дата и время с часовым поясом')
        try:
            at = datetime.fromisoformat(at.replace('Z', '+00:00'))
        except ValueError as exc:
            raise ValueError('Неверная дата публикации') from exc
        if at.tzinfo is None or at <= datetime.now(timezone.utc):
            raise ValueError('Выберите будущее время с часовым поясом')
    if not await ctx.db.get_post(pid):
        raise LookupError('Публикация не найдена')
    if not await ctx.db.set_post_schedule(pid, at):
        return jr({'error': 'Пост уже отправлен, обрабатывается или требует проверки'}, status=409)
    await events.log_event(ctx.db, events.SETTINGS_UPDATED, post_id=pid,
                           message='Время публикации изменено' if at else 'Личное время отменено',
                           metadata={'scheduled_at': at.isoformat() if at else None})
    return jr({'ok': True, 'scheduled_at': at})


@handler
async def h_post_ai(request: web.Request) -> web.Response:
    body = await body_json(request)
    return await _post_action(request, "generate_ai", {"force": bool(body.get("force"))})


@handler
async def h_post_caption(request: web.Request) -> web.Response:
    ctx = request.app['ctx']
    pid = _path_id(request)
    body = await body_json(request)
    caption = body.get('caption')
    if set(body) != {'caption'} or not isinstance(caption, str) or not caption.strip() or len(caption.encode('utf-16-le')) // 2 > 4096:
        raise ValueError('Введите подпись от 1 до 4096 символов')
    if not await ctx.db.get_post(pid):
        raise LookupError('Пост не найден')
    async with ctx.worker.caption_locks.setdefault(pid, asyncio.Lock()):
        if not await ctx.db.set_manual_caption(pid, caption.strip()):
            return jr({'error': 'Пост уже отправлен или обрабатывается'}, status=409)
    return jr({'ok': True, 'ai_status': 'manual', 'ai_caption': caption.strip()})


@handler
async def h_schedule_get(request: web.Request) -> web.Response:
    ctx: ApiContext = request.app["ctx"]
    v = await ctx.settings.api_view()
    idx = int(await ctx.db.kv_get("pattern_idx", "0"))
    pattern = v["schedule_pattern"] or []
    tz = ZoneInfo(v["tz_name"])
    times = [datetime.strptime(t, "%H:%M").time() for t in v["publish_times"]]
    nxt = next_slot(datetime.now(tz), times)
    return jr({"settings": v, "pattern_index": idx,
               "next_kind": pattern[idx % len(pattern)] if pattern else None,
               "next_slot": nxt.isoformat() if nxt else None})


@handler
async def h_schedule_put(request: web.Request) -> web.Response:
    ctx: ApiContext = request.app["ctx"]
    body = await body_json(request)
    cleaned = await ctx.settings.update("schedule", body)
    await events.log_event(ctx.db, events.SETTINGS_UPDATED, message="schedule",
                           metadata={"keys": sorted(cleaned)})
    return jr({"ok": True, "updated": sorted(cleaned)})


@handler
async def h_settings_get(request: web.Request) -> web.Response:
    ctx: ApiContext = request.app["ctx"]
    footer = await ctx.settings.get("footer")
    return jr({"footer": footer_for_api(footer), "preview": render_footer(footer)[0], "premium": ctx.cfg.premium})


@handler
async def h_settings_put(request: web.Request) -> web.Response:
    ctx: ApiContext = request.app["ctx"]
    body = await body_json(request)
    if "footer" not in body:
        raise ValueError("footer обязателен")
    cleaned = await ctx.settings.update("footer", {"footer": body["footer"]})
    await events.log_event(ctx.db, events.SETTINGS_UPDATED, message="footer", metadata={"keys": ["footer"]})
    return jr({"ok": True, "footer": footer_for_api(cleaned["footer"]),
               "preview": render_footer(cleaned["footer"])[0]})


@handler
async def h_ai_get(request: web.Request) -> web.Response:
    ctx: ApiContext = request.app["ctx"]
    v = await ctx.settings.api_view()
    primary = await ctx.settings.view(profile=1)
    secondary = await ctx.settings.view(profile=2)
    data = {k: v[k] for k in ("ai_enabled", "ai_required", "ai_base_url", "ai_model", "ai_prompt", "ai_timeout")}
    data["ai_secondary_base_url"] = v["ai_secondary_base_url"]
    data["ai_secondary_model"] = v["ai_secondary_model"]
    data["ai_active_profile"] = v["ai_active_profile"]
    data["api_key"] = mask_key(primary.ai_api_key)
    data["api_key_configured"] = bool(primary.ai_api_key)
    data["api_key_env_only"] = False
    data["secondary_api_key"] = mask_key(secondary.ai_api_key)
    data["secondary_api_key_configured"] = bool(secondary.ai_api_key)
    data["secondary_api_key_env_only"] = False
    return jr(data)


@handler
async def h_ai_put(request: web.Request) -> web.Response:
    ctx: ApiContext = request.app["ctx"]
    body = await body_json(request)
    def take_key(public_name: str, clear_name: str, settings_name: str) -> tuple[str, bool]:
        clear = body.pop(clear_name, False)
        if not isinstance(clear, bool):
            raise ValueError(f"{clear_name}: ожидается true/false")
        supplied = body.pop(public_name, None)
        if supplied is not None and not isinstance(supplied, str):
            raise ValueError(f"{public_name}: ожидается строка до 4096 символов")
        supplied = supplied.strip() if isinstance(supplied, str) else ""
        if clear and supplied:
            raise ValueError("нельзя одновременно задать и удалить API-ключ")
        if clear:
            body[settings_name] = ""
        elif supplied:
            body[settings_name] = supplied
        return supplied, clear

    api_key, clear_api_key = take_key("api_key", "clear_api_key", "ai_api_key")
    secondary_key, clear_secondary_key = take_key(
        "secondary_api_key", "clear_secondary_api_key", "ai_secondary_api_key")
    cleaned = validate("ai", body) if body else {}

    def origin(url):
        parsed = urlsplit(url)
        return (parsed.scheme.lower(), parsed.hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80))

    primary = await ctx.settings.view(profile=1)
    secondary = await ctx.settings.view(profile=2)
    if "ai_base_url" in cleaned and not api_key and not clear_api_key:
        if primary.ai_api_key and origin(cleaned["ai_base_url"]) != origin(primary.ai_base_url):
            raise ValueError("Для смены сервиса нейросети введите новый API-ключ или удалите текущий")
    if "ai_secondary_base_url" in cleaned and not secondary_key and not clear_secondary_key:
        if (secondary.ai_api_key and
                origin(cleaned["ai_secondary_base_url"]) != origin(secondary.ai_base_url)):
            raise ValueError("Для смены резервного сервиса введите новый API-ключ или удалите текущий")

    resulting_active = cleaned.get("ai_active_profile", primary.ai_active_profile)
    if resulting_active == 2:
        second_url = cleaned.get("ai_secondary_base_url", secondary.ai_base_url)
        second_model = cleaned.get("ai_secondary_model", secondary.ai_model)
        second_key = cleaned.get("ai_secondary_api_key", secondary.ai_api_key)
        if not (second_url and second_model and second_key):
            raise ValueError("Профиль 2 нужно полностью настроить: Base URL, модель и API-ключ")

    if cleaned:
        cleaned = await ctx.settings.update("ai", cleaned)
        public_keys = []
        for key in sorted(cleaned):
            public_keys.append({"ai_api_key": "api_key",
                                "ai_secondary_api_key": "secondary_api_key"}.get(key, key))
        await events.log_event(ctx.db, events.SETTINGS_UPDATED, message="ai",
                               metadata={"keys": public_keys})
    return await h_ai_get(request)


@handler
async def h_ai_test(request: web.Request) -> web.Response:
    ctx: ApiContext = request.app["ctx"]
    body = await body_json(request)
    unknown = set(body) - {"profile", "text", "post_id"}
    if unknown:
        raise ValueError(f"неизвестный ключ {sorted(unknown)[0]!r}")
    profile = body.get("profile")
    if profile is None:
        profile = (await ctx.settings.view()).ai_active_profile
    if isinstance(profile, bool) or not isinstance(profile, int) or profile not in (1, 2):
        raise ValueError("profile: ожидается 1 или 2")
    text = body.get("text", "")
    if not isinstance(text, str):
        raise ValueError("text: ожидается строка")
    text = text.strip()[:500]
    post_id = body.get("post_id")
    if post_id is not None and (isinstance(post_id, bool) or not isinstance(post_id, int) or post_id < 1):
        raise ValueError("post_id: ожидается положительное целое")
    runtime = await ctx.settings.view(profile=profile)
    if not (runtime.ai_base_url and runtime.ai_model and runtime.ai_api_key):
        raise ValueError(f"Профиль {profile} не настроен")
    payload = {"profile": profile, "text": text}
    if post_id is not None:
        payload["post_id"] = post_id
    aid = await ctx.db.create_action("test_ai_provider", payload, post_id=post_id)
    return jr({"action_id": aid, "status": "pending"}, status=202)


@handler
async def h_own_scan(request: web.Request) -> web.Response:
    ctx: ApiContext = request.app["ctx"]
    aid = await ctx.db.create_action("scan_own", {})
    return jr({"action_id": aid, "status": "pending"}, status=202)


@handler
async def h_own(request: web.Request) -> web.Response:
    ctx: ApiContext = request.app["ctx"]
    limit, offset = parse_paging(request.query, default_limit=50)
    order = request.query.get("order", "reactions")
    if order not in ("reactions", "date"):
        raise ValueError("order: reactions | date")
    media = request.query.get('media_type', '')
    if media and media not in {"photo", "video", "mixed", "text", "document", "unknown"}:
        raise ValueError('Неверный формат материала')
    items, total = await ctx.db.own_page(order, limit, offset, media_type=media) if media else await ctx.db.own_page(order, limit, offset)
    for it in items:
        it["text"] = (it.get("text") or "")[:200]
    return jr({"items": items, "total": total, "limit": limit, "offset": offset})


@handler
async def h_own_preview(request: web.Request) -> web.Response:
    ctx = request.app['ctx']
    key = request.query.get('group_key', '').strip()
    if not key or len(key) > 200:
        raise ValueError('group_key обязателен')
    row = await ctx.db.get_own(key)
    if row is None:
        raise LookupError('Материал архива не найден')
    import hashlib
    cache_key = 'own_' + hashlib.sha256(key.encode()).hexdigest()
    try:
        image = await ctx.worker.previews.get(cache_key, source_ref=ctx.cfg.destination,
                                              source_msg_ids=row['msg_ids'])
    except Exception as exc:
        log.warning('own preview unavailable: %s', type(exc).__name__)
        return jr({'error': 'Превью временно недоступно'}, status=503)
    if image is None:
        return web.Response(status=204, headers={'Cache-Control': 'no-store'})
    return web.FileResponse(image, headers={'Content-Type': 'image/jpeg', 'Cache-Control': 'private, max-age=300'})


@handler
async def h_own_repost(request: web.Request) -> web.Response:
    ctx: ApiContext = request.app["ctx"]
    body = await body_json(request)
    key = str(body.get("group_key") or "").strip()
    if not key or len(key) > 200:
        raise ValueError("group_key обязателен")
    payload = {"group_key": key}
    at = body.get('scheduled_at')
    if at is not None:
        if not isinstance(at, str):
            raise ValueError('Ожидается дата и время с часовым поясом')
        try:
            date = datetime.fromisoformat(at.replace('Z', '+00:00'))
        except ValueError as exc:
            raise ValueError('Неверная дата публикации') from exc
        if date.tzinfo is None or date <= datetime.now(timezone.utc):
            raise ValueError('Выберите будущее время с часовым поясом')
        payload['scheduled_at'] = date.isoformat()
    aid = await ctx.db.create_action("repost_own", payload)
    return jr({"action_id": aid, "status": "pending"}, status=202)


@handler
async def h_actions(request: web.Request) -> web.Response:
    ctx: ApiContext = request.app["ctx"]
    limit, offset = parse_paging(request.query, default_limit=50)
    return jr({"items": await ctx.db.actions_page(limit, offset)})


@handler
async def h_action(request: web.Request) -> web.Response:
    ctx: ApiContext = request.app["ctx"]
    aid = request.match_info["id"]
    a = await ctx.db.get_action(aid)
    if not a:
        raise LookupError(f"action {aid} not found")
    return jr(a)


@handler
async def h_events(request: web.Request) -> web.Response:
    ctx: ApiContext = request.app["ctx"]
    limit, offset = parse_paging(request.query)
    filters = parse_events_filters(request.query)
    items, total = await ctx.db.events_page(filters, limit, offset)
    return jr({"items": items, "total": total, "limit": limit, "offset": offset})


def _activity(request: web.Request):
    service = request.app["ctx"].activity
    if service is None:
        raise RuntimeError("Сервис аккаунтов не запущен")
    return service


@handler
async def h_activity_accounts(request: web.Request) -> web.Response:
    return jr({"items": await _activity(request).list()})


@handler
async def h_activity_settings_get(request: web.Request) -> web.Response:
    return jr(await _activity(request).settings())


@handler
async def h_activity_settings_put(request: web.Request) -> web.Response:
    body = await body_json(request)
    return jr(await _activity(request).update_settings(body.get("interval_minutes")))


@handler
async def h_activity_login_start(request: web.Request) -> web.Response:
    body = await body_json(request)
    result = await _activity(request).start_login(str(body.get("phone") or ""))
    return jr(result, status=202)


@handler
async def h_activity_login_complete(request: web.Request) -> web.Response:
    body = await body_json(request)
    result = await _activity(request).complete_login(
        str(body.get("login_token") or ""), str(body.get("code") or ""),
        str(body.get("password") or ""),
    )
    return jr(result, status=200 if result.get("authorized") else 202)


@handler
async def h_activity_account_patch(request: web.Request) -> web.Response:
    body = await body_json(request)
    if not isinstance(body.get("enabled"), bool):
        raise ValueError("enabled должен быть boolean")
    await _activity(request).set_enabled(request.match_info["id"], body["enabled"])
    return jr({"ok": True})


@handler
async def h_activity_account_delete(request: web.Request) -> web.Response:
    await _activity(request).delete(request.match_info["id"])
    return jr({"ok": True})


@handler
async def h_activity_react(request: web.Request) -> web.Response:
    result = await _activity(request).react_now(request.match_info["id"])
    failed = next((item for item in result["items"] if item["status"] == "error"), None)
    if failed:
        return jr({**result, "error": failed["error"]}, status=409)
    return jr(result)


@handler
async def h_networks_get(request):
    ctx = request.app['ctx']
    return jr(await NetworkService(ctx.cfg, ctx.db).list())


@handler
async def h_networks_put(request):
    ctx = request.app['ctx']
    lock = getattr(getattr(ctx, 'activity', None), 'network_settings_lock', None)
    return jr(await NetworkService(ctx.cfg, ctx.db, lock).update(request.match_info['id'], await body_json(request)))


def build_app(ctx: ApiContext, token: str) -> web.Application:
    app = web.Application(middlewares=[auth_mw], client_max_size=MAX_BODY)
    app["ctx"], app["token"] = ctx, token
    r = app.router
    r.add_get("/api/overview", h_overview)
    r.add_get("/api/sources", h_sources)
    r.add_post("/api/sources", h_source_add)
    r.add_patch("/api/sources/{id}", h_source_patch)
    r.add_delete("/api/sources/{id}", h_source_delete)
    r.add_post("/api/sources/{id}/check", h_source_check)
    r.add_post("/api/sources/{id}/backfill", h_source_backfill)
    r.add_get("/api/posts", h_posts)
    r.add_get("/api/posts/{id}", h_post)
    r.add_get("/api/posts/{id}/preview", h_post_preview)
    r.add_post("/api/posts/{id}/publish", h_post_publish)
    r.add_post("/api/posts/{id}/requeue", h_post_requeue)
    r.add_post("/api/posts/{id}/skip", h_post_skip)
    r.add_post("/api/posts/{id}/ai", h_post_ai)
    r.add_put("/api/posts/{id}/schedule", h_post_schedule)
    r.add_put("/api/posts/{id}/caption", h_post_caption)
    r.add_get("/api/schedule", h_schedule_get)
    r.add_put("/api/schedule", h_schedule_put)
    r.add_get("/api/settings", h_settings_get)
    r.add_put("/api/settings", h_settings_put)
    r.add_get("/api/ai", h_ai_get)
    r.add_put("/api/ai", h_ai_put)
    r.add_post("/api/ai/test", h_ai_test)
    r.add_post("/api/own/scan", h_own_scan)
    r.add_get("/api/own", h_own)
    r.add_get("/api/own/preview", h_own_preview)
    r.add_post("/api/own/repost", h_own_repost)
    r.add_get("/api/actions", h_actions)
    r.add_get("/api/actions/{id}", h_action)
    r.add_get("/api/events", h_events)
    r.add_get("/api/networks", h_networks_get)
    r.add_put("/api/networks/{id}", h_networks_put)
    r.add_get("/api/activity-accounts", h_activity_accounts)
    r.add_get("/api/activity-settings", h_activity_settings_get)
    r.add_put("/api/activity-settings", h_activity_settings_put)
    r.add_post("/api/activity-accounts/login/start", h_activity_login_start)
    r.add_post("/api/activity-accounts/login/complete", h_activity_login_complete)
    r.add_patch("/api/activity-accounts/{id}", h_activity_account_patch)
    r.add_delete("/api/activity-accounts/{id}", h_activity_account_delete)
    r.add_post("/api/activity-accounts/{id}/react", h_activity_react)
    return app


async def serve(port: int, ctx: ApiContext, token: str):
    app = build_app(ctx, token)
    runner = web.AppRunner(app, access_log=None)  # access log off: не логируем заголовки/пути с данными
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info("control api listening on :%d", port)
    await asyncio.Event().wait()
