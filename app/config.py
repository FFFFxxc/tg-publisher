"""Конфигурация из окружения. Не печатает секреты."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from .logic import parse_footer, parse_pattern, parse_times


class ConfigError(RuntimeError):
    pass


def _env(name: str, default: str | None = None, required: bool = False) -> str:
    val = os.environ.get(name, default)
    if required and not val:
        raise ConfigError(f"{name} is required")
    return val or ""


def _bool(name: str, default: bool = False) -> bool:
    return _env(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = _env(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError as e:
        raise ConfigError(f"{name} must be an integer") from e


def validate_session_string(s: str) -> str:
    s = s.strip()
    if not s:
        return ""   # пусто = файл-сессия в volume (создаётся командой login)
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        raise ConfigError(
            "TG_SESSION_STRING is wrapped in literal quotes. "
            "docker --env-file does not strip quotes: remove them."
        )
    return s


def normalize_dsn(url: str) -> str:
    """Для psycopg 3 нужен libpq-DSN (postgresql://)."""
    url = url.strip()
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


def sqlalchemy_url(url: str) -> str:
    """Если когда-нибудь понадобится SQLAlchemy: всегда драйвер psycopg 3."""
    return "postgresql+psycopg://" + normalize_dsn(url)[len("postgresql://"):]


def build_proxy(host: str, port: int) -> dict | None:
    if not host:
        return None
    return {"proxy_type": "socks5", "addr": host, "port": port, "rdns": True}


@dataclass
class Config:
    api_id: int
    api_hash: str
    session: str
    destination: str
    sources: list
    proxy: dict | None
    database_url: str
    collect_interval: int = 300
    publish_interval: int = 1800
    publish_window: str = ""
    tz_name: str = "UTC"
    initial_backfill: int = 0
    album_settle: int = 60
    max_post_age_hours: int = 48
    max_attempts: int = 5
    max_media_mb: int = 200
    footer: list = field(default_factory=list)
    premium: bool = True
    schedule_pattern: list = field(default_factory=lambda: ["parsed"])
    publish_times: list = field(default_factory=list)
    candidate_min_age_min: int = 120
    best_min_score: float = 1.0
    baseline_days: int = 7
    own_min_age_days: int = 14
    repost_cooldown_days: int = 60
    own_scan_limit: int = 3000
    own_scan_hours: int = 6
    ai_enabled: bool = False
    ai_required: bool = False
    ai_base_url: str = ""
    ai_api_key: str = field(default="", repr=False)
    ai_api_key_file: str = "/home/app/.data/ai_api_key"
    ai_model: str = ""
    ai_timeout: int = 40
    ai_prompt: str = ""
    health_port: int = 8080
    control_api_port: int = 8081
    control_api_token: str = field(default="", repr=False)
    db_schema: str = "tg_publisher"
    session_path: str = "/home/app/.data/userbot"
    activity_reaction: str = "👍"
    activity_reactions: list = field(default_factory=lambda: ["❤", "👍", "🔥", "😍", "😁"])
    activity_target_invite: str = field(default="", repr=False)
    activity_interval: int = 30
    activity_recent_limit: int = 20

    def __repr__(self) -> str:  # никаких секретов в логах
        return (f"Config(dest={self.destination!r}, sources={self.sources!r}, "
                f"proxy={'socks5 ' + self.proxy['addr'] + ':' + str(self.proxy['port']) if self.proxy else 'direct'}, "
                f"ai={'on' if self.ai_enabled else 'off'}, pattern={','.join(self.schedule_pattern)}, "
                f"times={[t.strftime('%H:%M') for t in self.publish_times] or 'interval'})")

    @classmethod
    def from_env(cls) -> "Config":
        cfg = cls(
            api_id=_int("TG_API_ID", 0),
            api_hash=_env("TG_API_HASH", required=True),
            session=validate_session_string(_env("TG_SESSION_STRING")),
            destination=_env("TG_DESTINATION", required=True),
            sources=[x.strip() for x in (_env("TG_SOURCES") or _env("TG_INITIAL_SOURCE")).split(",") if x.strip()],
            proxy=build_proxy(_env("TG_PROXY_HOST").strip(), _int("TG_PROXY_PORT", 1080)),
            database_url=normalize_dsn(_env("DATABASE_URL", required=True)),
            session_path=_env("TG_SESSION_PATH", "/home/app/.data/userbot"),
            activity_reaction=_env("ACTIVITY_REACTION", "👍").strip() or "👍",
            activity_reactions=[x.strip() for x in _env(
                "ACTIVITY_REACTIONS", "❤,👍,🔥,😍,😁").split(",") if x.strip()],
            activity_target_invite=_env("ACTIVITY_TARGET_INVITE").strip(),
            activity_interval=_int("ACTIVITY_INTERVAL_SEC", 30),
            activity_recent_limit=_int("ACTIVITY_RECENT_LIMIT", 20),
            collect_interval=_int("COLLECT_INTERVAL_SEC", 300),
            publish_interval=_int("PUBLISH_INTERVAL_SEC", 1800),
            publish_window=_env("PUBLISH_WINDOW"),
            tz_name=_env("TZ_NAME", "Europe/Moscow"),
            initial_backfill=_int("INITIAL_BACKFILL", 0),
            album_settle=_int("ALBUM_SETTLE_SEC", 60),
            max_post_age_hours=_int("MAX_POST_AGE_HOURS", 48),
            max_attempts=_int("MAX_ATTEMPTS", 5),
            max_media_mb=_int("MAX_MEDIA_MB", 200),
            footer=parse_footer(_env("FOOTER_JSON")),
            premium=_bool("TG_ACCOUNT_PREMIUM", True),
            schedule_pattern=parse_pattern(_env("SCHEDULE_PATTERN", "parsed,old")),
            publish_times=parse_times(_env("PUBLISH_TIMES")),
            candidate_min_age_min=_int("CANDIDATE_MIN_AGE_MIN", 120),
            best_min_score=float(_env("BEST_MIN_SCORE", "1.0")),
            baseline_days=_int("BASELINE_DAYS", 7),
            own_min_age_days=_int("OWN_MIN_AGE_DAYS", 14),
            repost_cooldown_days=_int("REPOST_COOLDOWN_DAYS", 60),
            own_scan_limit=_int("OWN_SCAN_LIMIT", 3000),
            own_scan_hours=_int("OWN_SCAN_HOURS", 6),
            ai_enabled=bool(_env("AI_API_KEY").strip()),   # ключ есть = AI включён
            ai_required=_bool("AI_REQUIRED"),
            ai_base_url=_env("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            ai_api_key=_env("AI_API_KEY"),
            ai_api_key_file=_env("AI_API_KEY_FILE", "/home/app/.data/ai_api_key"),
            ai_model=_env("AI_MODEL", "gpt-4o-mini"),
            ai_timeout=_int("AI_TIMEOUT_SEC", 40),
            ai_prompt=_env("AI_PROMPT", "Перепиши подпись к посту для Telegram-канала: коротко и живо. "
                           "Убери ссылки, упоминания и призывы подписаться на источник. Верни только текст."),
            health_port=_int("HEALTH_PORT", 8080),
            control_api_port=_int("CONTROL_API_PORT", 8081),
            control_api_token=_env("CONTROL_API_TOKEN"),
            db_schema=_env("DB_SCHEMA", "tg_publisher").strip() or "tg_publisher",
        )
        if not cfg.api_id:
            raise ConfigError("TG_API_ID is required")
        return cfg
