"""Структурированные события в БД. Никогда не ломают основной поток и не содержат секретов."""
from __future__ import annotations

import logging

log = logging.getLogger("events")

# ключи metadata с такими подстроками вырезаются
SECRET_HINTS = ("token", "secret", "key", "password", "session", "api_hash", "dsn", "authorization")

# типы событий
WORKER_STARTED = "worker_started"
SOURCE_COLLECTED = "source_collected"
SOURCE_ERROR = "source_error"
SOURCE_ADDED = "source_added"
SOURCE_ENABLED = "source_enabled"
SOURCE_DISABLED = "source_disabled"
SOURCE_DELETED = "source_deleted"
SOURCE_VERIFIED = "source_verified"
SOURCE_BACKFILLED = "source_backfilled"
PUBLISH_STARTED = "publish_started"
PUBLISH_COMPLETED = "publish_completed"
PUBLISH_FAILED = "publish_failed"
PUBLISH_AMBIGUOUS = "publish_ambiguous"
PUBLISH_RETRY = "publish_retry"
AI_GENERATED = "ai_generated"
AI_FAILED = "ai_failed"
ACTION_COMPLETED = "action_completed"
ACTION_FAILED = "action_failed"
OWN_SCANNED = "own_scanned"
SETTINGS_UPDATED = "settings_updated"


def scrub(value):
    """Рекурсивно убираем из metadata всё, что похоже на секрет, и режем длинные строки."""
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()
                if not any(h in str(k).lower() for h in SECRET_HINTS)}
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    if isinstance(value, str):
        return value[:500]
    return value


async def log_event(db, type_: str, level: str = "info", *, post_id=None, source_id=None,
                    action_id=None, message: str = "", metadata: dict | None = None):
    try:
        await db.add_event(type_, level, post_id=post_id, source_id=source_id, action_id=action_id,
                           message=str(message)[:500], metadata=scrub(metadata if metadata is not None else {}))
    except Exception:
        log.exception("event %s not persisted", type_)
