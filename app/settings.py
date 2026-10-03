"""Runtime-настройки: ENV (Config) = дефолт, переопределения в kv под префиксом rt:.
Кэш с коротким TTL, чтобы не долбить PostgreSQL из каждого тика."""
from __future__ import annotations

import json
import logging
import time as _time
from datetime import time as dtime
from types import SimpleNamespace
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .logic import parse_footer, parse_pattern

log = logging.getLogger("settings")

PREFIX = "rt:"
CACHE_TTL_SEC = 10
JS_SAFE_INTEGER = 2 ** 53 - 1
INT64_MAX = 2 ** 63 - 1


def _v_int(lo: int, hi: int):
    def v(raw):
        n = int(raw)
        if not (lo <= n <= hi):
            raise ValueError(f"ожидается целое {lo}..{hi}")
        return n
    return v


def _v_float(lo: float, hi: float):
    def v(raw):
        f = float(raw)
        if not (lo <= f <= hi):
            raise ValueError(f"ожидается число {lo}..{hi}")
        return f
    return v


def _v_bool(raw):
    if isinstance(raw, bool):
        return raw
    s = str(raw).strip().lower()
    if s in {"1", "true", "yes", "on"}:
        return True
    if s in {"0", "false", "no", "off"}:
        return False
    raise ValueError("ожидается true/false")


def _v_str(maxlen: int):
    def v(raw):
        s = str(raw).strip()
        if not s or len(s) > maxlen:
            raise ValueError(f"ожидается непустая строка до {maxlen} символов")
        return s
    return v


def _v_api_key(raw):
    """API credential override. Empty is meaningful: it disables the ENV fallback."""
    if not isinstance(raw, str):
        raise ValueError("ожидается строка до 4096 символов")
    value = raw.strip()
    if len(value) > 4096:
        raise ValueError("ожидается строка до 4096 символов")
    return value


def _v_url(raw):
    s = _v_str(200)(raw)
    if not s.startswith(("http://", "https://")):
        raise ValueError("ожидается http(s) URL")
    return s.rstrip("/")


def _v_optional_str(maxlen: int):
    def v(raw):
        if not isinstance(raw, str):
            raise ValueError(f"ожидается строка до {maxlen} символов")
        s = raw.strip()
        if len(s) > maxlen:
            raise ValueError(f"ожидается строка до {maxlen} символов")
        return s
    return v


def _v_optional_url(raw):
    s = _v_optional_str(200)(raw)
    if s and not s.startswith(("http://", "https://")):
        raise ValueError("ожидается http(s) URL")
    return s.rstrip("/")


def _v_tz(raw):
    s = _v_str(64)(raw)
    try:
        ZoneInfo(s)
    except (ZoneInfoNotFoundError, ValueError, KeyError) as e:
        raise ValueError(f"неизвестная таймзона {s!r}") from e
    return s


def _v_times(raw):
    items = raw if isinstance(raw, list) else [x for x in str(raw).split(",")]
    if not items:
        raise ValueError("ожидается непустой список HH:MM")
    out = sorted(dtime.fromisoformat(str(x).strip()) for x in items if str(x).strip())
    if not out:
        raise ValueError("ожидается непустой список HH:MM")
    return [t.strftime("%H:%M") for t in out]


def _v_pattern(raw):
    items = raw if isinstance(raw, list) else [x for x in str(raw).split(",")]
    return parse_pattern(",".join(str(x) for x in items if str(x).strip()))


def _v_footer(raw):
    if not isinstance(raw, list) or not raw:
        raise ValueError("footer должен быть непустым списком строк")
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("footer: каждый элемент должен быть объектом")
        emoji_id = item.get("emoji_id")
        if emoji_id is None or emoji_id == "":
            continue
        if isinstance(emoji_id, bool) or isinstance(emoji_id, float):
            raise ValueError("footer: emoji_id должен быть целым числом в строке")
        if isinstance(emoji_id, int):
            if emoji_id < 1 or emoji_id > JS_SAFE_INTEGER:
                raise ValueError("footer: большой emoji_id передавайте строкой")
            continue
        if not isinstance(emoji_id, str) or not emoji_id.isascii() or not emoji_id.isdigit():
            raise ValueError("footer: emoji_id должен быть целым числом в строке")
        parsed_id = int(emoji_id)
        if parsed_id < 1 or parsed_id > INT64_MAX:
            raise ValueError("footer: emoji_id вне допустимого диапазона")
    items = parse_footer(json.dumps(raw, ensure_ascii=False))
    for it in items:
        if len(str(it.get("text", ""))) > 128 or len(str(it.get("url", ""))) > 256:
            raise ValueError("footer: text <= 128, url <= 256 символов")
        if len(str(it.get("emoji", ""))) > 16:
            raise ValueError("footer: emoji слишком длинный")
    return items


def footer_for_api(items: list[dict]) -> list[dict]:
    """Copy footer values for JSON without exposing 64-bit Telegram IDs as JS numbers."""
    out = []
    for item in items:
        public_item = dict(item)
        emoji_id = public_item.get("emoji_id")
        if emoji_id is not None:
            public_item["emoji_id"] = str(emoji_id)
        out.append(public_item)
    return out


VALIDATORS = {
    "tz_name": _v_tz,
    "publish_times": _v_times,
    "schedule_pattern": _v_pattern,
    "candidate_min_age_min": _v_int(0, 7 * 24 * 60),
    "max_post_age_hours": _v_int(1, 336),
    "best_min_score": _v_float(0, 100),
    "baseline_days": _v_int(1, 90),
    "own_min_age_days": _v_int(0, 3650),
    "repost_cooldown_days": _v_int(0, 3650),
    "collect_interval": _v_int(60, 86400),
    "publishing_paused": _v_bool,
    "ai_enabled": _v_bool,
    "ai_required": _v_bool,
    "ai_api_key": _v_api_key,
    "ai_base_url": _v_url,
    "ai_model": _v_str(200),
    "ai_secondary_api_key": _v_api_key,
    "ai_secondary_base_url": _v_optional_url,
    "ai_secondary_model": _v_optional_str(200),
    "ai_active_profile": _v_int(1, 2),
    "ai_prompt": _v_str(4000),
    "ai_timeout": _v_int(5, 300),
    "footer": _v_footer,
}

SECTIONS = {
    "schedule": ["tz_name", "publish_times", "schedule_pattern", "candidate_min_age_min",
                 "max_post_age_hours", "best_min_score", "baseline_days", "own_min_age_days",
                 "repost_cooldown_days", "collect_interval", "publishing_paused"],
    "ai": ["ai_enabled", "ai_required", "ai_api_key", "ai_base_url", "ai_model",
           "ai_secondary_api_key", "ai_secondary_base_url", "ai_secondary_model",
           "ai_active_profile", "ai_prompt", "ai_timeout"],
    "footer": ["footer"],
}


class SettingsError(ValueError):
    pass


def validate(section: str, values: dict) -> dict:
    """Чистая валидация обновления настроек: -> очищенные значения либо SettingsError."""
    if section not in SECTIONS:
        raise SettingsError(f"неизвестная секция {section!r}")
    if not isinstance(values, dict) or not values:
        raise SettingsError("пустое обновление")
    out = {}
    for k, raw in values.items():
        if k not in SECTIONS[section]:
            raise SettingsError(f"{section}: неизвестный ключ {k!r}")
        try:
            out[k] = VALIDATORS[k](raw)
        except ValueError as e:
            raise SettingsError(f"{k}: {e}") from e
    return out


class RuntimeSettings:
    """Читается воркером каждый тик (view), пишется панелью (update). ENV -> DB fallback."""

    def __init__(self, db, cfg, ttl: float = CACHE_TTL_SEC):
        self.db, self.cfg, self.ttl = db, cfg, ttl
        self._cache: dict | None = None
        self._at = 0.0

    def default(self, key: str):
        if key == "publishing_paused":
            return False
        if key in {"ai_secondary_api_key", "ai_secondary_base_url", "ai_secondary_model"}:
            return ""
        if key == "ai_active_profile":
            return 1
        return getattr(self.cfg, key)

    async def _overrides(self) -> dict:
        now = _time.monotonic()
        if self._cache is None or now - self._at > self.ttl:
            raw = await self.db.kv_prefix(PREFIX)
            out = {}
            for k, v in raw.items():
                try:
                    out[k] = json.loads(v)
                except ValueError:
                    log.warning("bad settings json for %s ignored", k)
            self._cache, self._at = out, now
        return self._cache

    def invalidate(self):
        self._cache = None

    def _resolved(self, key: str, ov: dict):
        v = ov.get(key, self.default(key))
        if key == "publish_times" and v and isinstance(v[0], str):
            v = [dtime.fromisoformat(x) for x in v]
        return v

    async def view(self, profile: int | None = None) -> SimpleNamespace:
        """Снимок воркера; стандартные AI-поля указывают на выбранный профиль."""
        ov = await self._overrides()
        d = {k: self._resolved(k, ov) for k in VALIDATORS}
        selected = d["ai_active_profile"] if profile is None else profile
        if isinstance(selected, bool) or selected not in (1, 2):
            raise SettingsError("profile: ожидается 1 или 2")
        if selected == 2:
            d["ai_base_url"] = d["ai_secondary_base_url"]
            d["ai_model"] = d["ai_secondary_model"]
            d["ai_api_key"] = d["ai_secondary_api_key"]
        return SimpleNamespace(**d)

    async def get(self, key: str):
        ov = await self._overrides()
        return self._resolved(key, ov)

    async def api_view(self) -> dict:
        """JSON-безопасный снимок для панели (времена как 'HH:MM')."""
        ov = await self._overrides()
        out = {}
        for k in VALIDATORS:
            if k in {"ai_api_key", "ai_secondary_api_key"}:
                continue
            v = self._resolved(k, ov)
            if k == "publish_times":
                v = [t.strftime("%H:%M") for t in v]
            elif k == "footer":
                v = footer_for_api(v)
            out[k] = v
        return out

    async def update(self, section: str, values: dict) -> dict:
        cleaned = validate(section, values)
        for k, v in cleaned.items():
            await self.db.kv_set(PREFIX + k, json.dumps(v, ensure_ascii=False))
        self.invalidate()
        return cleaned
