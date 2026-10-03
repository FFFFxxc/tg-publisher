"""Чистая логика без сети: легко тестируется."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, time, timedelta

MEDIA_CAPTION_LIMIT = 1024
TEXT_LIMIT = 4096

# Состояния очереди
CANDIDATE, PENDING, PROCESSING, PUBLISHED = "candidate", "pending", "processing", "published"
FAILED, AMBIGUOUS, SKIPPED, EXPIRED = "failed", "ambiguous", "skipped", "expired"
# AI-статусы
AI_UNCHECKED, AI_PROCESSING, AI_GENERATED = "unchecked", "processing", "generated"
AI_NOT_NEEDED, AI_NO_PREVIEW, AI_FAILED, AI_MANUAL = "not_needed", "no_preview", "failed", "manual"
# Типы слотов расписания
PARSED, OLD = "parsed", "old"

DEFAULT_FOOTER = [
    {"emoji": "👀", "emoji_id": 5256105385420412669, "text": "ХОТ КОНТЕНТ", "url": "https://t.me/fulli4k_bot"},
    {"emoji": "😡", "emoji_id": 5195160091547942599, "text": "МЫ В МАКСЕ", "url": "https://max.ru/channel_anime2d"},
]


def u16(s: str) -> int:
    """Telegram считает offset/length сущностей в UTF-16 code units."""
    return len(s.encode("utf-16-le")) // 2


def cut_u16(s: str, limit: int) -> str:
    out, n = [], 0
    for ch in s:
        w = u16(ch)
        if n + w > limit:
            break
        out.append(ch)
        n += w
    return "".join(out)


def parse_footer(raw: str) -> list[dict]:
    items = json.loads(raw) if raw.strip() else DEFAULT_FOOTER
    for it in items:
        it["emoji_id"] = int(it["emoji_id"]) if it.get("emoji_id") else None
        if not it.get("text"):
            raise ValueError("footer item needs text")
    return items


def render_footer(items: list[dict]) -> tuple[str, list[tuple]]:
    """-> (текст, [("emoji", off, len, id) | ("url", off, len, url)]) с offset от начала футера."""
    text, ents = "", []
    for i, it in enumerate(items):
        if i:
            text += "\n"
        if it.get("emoji"):
            if it.get("emoji_id"):
                ents.append(("emoji", u16(text), u16(it["emoji"]), it["emoji_id"]))
            text += it["emoji"] + " "
        if it.get("url"):
            ents.append(("url", u16(text), u16(it["text"]), it["url"]))
        text += it["text"]
    return text, ents


def footer_present(text: str, items: list[dict]) -> bool:
    return bool(items) and all(it["text"] in text for it in items)


def build_caption(body: str, body_entities: list | None, footer: list[dict], has_media: bool,
                  premium: bool = False):
    """-> (text, kept_body_entities, footer_entity_specs_with_absolute_offsets).
    Футер добавляется всегда (если его ещё нет в тексте). Тело режется так, чтобы футер влез."""
    limit = TEXT_LIMIT if (not has_media or premium) else MEDIA_CAPTION_LIMIT
    body = (body or "").rstrip()
    ftext, fents = ("", [])
    if footer and not footer_present(body, footer):
        ftext, fents = render_footer(footer)
    sep = "\n\n" if body and ftext else ""
    room = limit - u16(sep) - u16(ftext)
    if u16(body) > room:
        body = cut_u16(body, room - 1).rstrip() + "…"
        sep = "\n\n" if body and ftext else ""
    blen = u16(body)
    kept = [e for e in (body_entities or []) if e.offset + e.length <= blen]
    base = blen + u16(sep)
    abs_f = [(k, off + base, ln, v) for k, off, ln, v in fents]
    return body + sep + ftext, kept, abs_f


def recovery_action(status: str, send_started: bool, dest_ids: list[int] | None) -> str | None:
    if status != PROCESSING:
        return None
    if dest_ids:
        return PUBLISHED
    if send_started:
        return AMBIGUOUS
    return PENDING


def group_messages(msgs: list[tuple[int, int | None]]) -> list[tuple[str, list[int]]]:
    out: dict[str, list[int]] = {}
    for mid, gid in msgs:
        key = f"g{gid}" if gid else f"m{mid}"
        out.setdefault(key, []).append(mid)
    return [(k, sorted(v)) for k, v in out.items()]


def parse_pattern(spec: str) -> list[str]:
    alias = {"parsed": PARSED, "new": PARSED, "p": PARSED, "спаршенный": PARSED,
             "old": OLD, "o": OLD, "старый": OLD}
    out = [alias.get(x.strip().lower()) for x in spec.split(",") if x.strip()]
    if not out or None in out:
        raise ValueError("SCHEDULE_PATTERN: use comma-separated parsed/old")
    return out


def parse_times(spec: str) -> list[time]:
    return sorted(time.fromisoformat(x.strip()) for x in spec.split(",") if x.strip())


def due_slot(now: datetime, times: list[time], grace_min: int = 15) -> str | None:
    """Ключ самого свежего наступившего слота (если он не старше grace_min), иначе None."""
    past = [t for t in times if t <= now.time()]
    if not past:
        return None
    t = past[-1]
    slot = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    if (now - slot).total_seconds() > grace_min * 60:
        return None
    return slot.strftime("%Y-%m-%d %H:%M")


def next_slot(now: datetime, times: list[time]) -> datetime | None:
    """Ближайший будущий слот публикации (сегодня или завтра)."""
    if not times:
        return None
    today = [now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0) for t in times]
    future = [d for d in today if d > now]
    if future:
        return min(future)
    t = min(times)
    return (now + timedelta(days=1)).replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)


def parse_window(spec: str):
    if not spec.strip():
        return None
    a, b = spec.split("-")
    return time.fromisoformat(a.strip()), time.fromisoformat(b.strip())


def in_window(now: datetime, spec: str) -> bool:
    w = parse_window(spec)
    if not w:
        return True
    start, end = w
    t = now.time()
    return start <= t < end if start <= end else (t >= start or t < end)


def backoff_seconds(attempt: int) -> int:
    return min(60 * 2 ** max(attempt - 1, 0), 3600)


@dataclass
class Post:
    id: int
    kind: str
    source_id: int
    source_ref: str
    source_msg_ids: list[int]
    text: str
    ai_status: str
    ai_caption: str | None
    attempts: int


def parse_ref(ref: str) -> tuple[str, object]:
    """@name / t.me/name -> ("username", name); -100123 / 123 -> ("id", int);
    t.me/+HASH, t.me/joinchat/HASH -> ("invite", HASH)."""
    import re
    r = ref.strip()
    m = re.match(r"^(?:https?://)?t(?:elegram)?\.me/(?:\+|joinchat/)([\w-]+)/?$", r)
    if m:
        return "invite", m.group(1)
    if re.fullmatch(r"-?\d+", r):
        return "id", int(r)
    m = re.match(r"^(?:https?://)?t(?:elegram)?\.me/([A-Za-z0-9_]{4,})/?$", r)
    if m:
        return "username", m.group(1)
    return "username", r.lstrip("@")


def canonical_ref(ref: str) -> str:
    """Каноническая форма ссылки канала: разные написания одного канала схлопываются в одну."""
    kind, val = parse_ref(ref)
    if kind == "username":
        return f"@{val}"
    if kind == "id":
        return str(val)
    return f"https://t.me/+{val}"
