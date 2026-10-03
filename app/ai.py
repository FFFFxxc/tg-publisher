"""Опциональные AI-подписи. Ходят напрямую (не через Telegram SOCKS), с жёстким таймаутом."""
from __future__ import annotations

import base64
import math
import mimetypes
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from .config import Config


class AIError(RuntimeError):
    pass


class AIRefusalError(AIError):
    """Provider declined the task; its service response is not a caption."""


_REFUSAL = re.compile(
    r"^(?:(?:извините|извини|простите|к сожалению)[\s,.!:—-]*(?:но\s+)?)*"
    r"(?:я\s+(?:не могу|не буду|не готов)\s+(?:генерировать|создавать|создать|"
    r"комментировать|описать|описывать|помочь|помогать|выполнить|обрабатывать|"
    r"предоставить|предоставлять|подписать|сделать)|"
    r"(?:(?:i(?:['’]m| am) sorry|sorry|i apologize)[\s,.!:—-]*(?:but\s+)?)*"
    r"i\s+(?:can(?:not|['’]t)|will not|won['’]t|am unable to)\s+(?:help|assist|"
    r"generate|create|describe|comment|provide|comply|fulfill|process)|"
    r"(?:этот|данный)\s+(?:запрос|контент)\s+(?:нарушает|противоречит)|"
    r"(?:this|that)\s+(?:request|content)\s+(?:violates|goes against))",
    re.IGNORECASE,
)


def is_refusal(text: str | None) -> bool:
    value = (text or '').lstrip(' \n\r\t\"\'«*')
    return bool(_REFUSAL.match(value) or re.match(
        r'^(?:я\s+не\s+(?:вижу|получил)|(?:i\s+)?(?:cannot|can[\'’]t)\s+(?:see|view))\b',
        value, re.IGNORECASE))


def validate_caption(text: str | None) -> str:
    if not isinstance(text, str) or not text.strip():
        raise AIError('ai empty response')
    if is_refusal(text):
        raise AIRefusalError('Нейросеть отказалась создать подпись')
    return text.strip()


class AIRateLimitError(AIError):
    """AI provider rate limit with the delay before another request is allowed."""

    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after


_cooldowns: dict[tuple[str, str, str], float] = {}


def _cooldown_key(cfg: Config) -> tuple[str, str, str]:
    return (cfg.ai_base_url, cfg.ai_api_key, cfg.ai_model)


def _retry_after(response: httpx.Response) -> int:
    value = response.headers.get("Retry-After", "").strip()
    if value:
        try:
            return max(1, math.ceil(float(value)))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                return max(1, math.ceil((retry_at - datetime.now(timezone.utc)).total_seconds()))
            except (TypeError, ValueError, OverflowError):
                pass
    body = response.text.lower()
    if "daily" in body or "today's" in body or "today’s" in body:
        return 3600
    return 60


def _user_content(text: str, image_path: str | None):
    if not image_path:
        return text
    mime = mimetypes.guess_type(image_path)[0] or "image/jpeg"
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return [{"type": "text", "text": text or "(у поста нет текста, подпиши по картинке)"},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]


async def generate_caption(cfg: Config, text: str, image_path: str | None = None) -> str:
    key = _cooldown_key(cfg)
    now = time.monotonic()
    blocked_until = _cooldowns.get(key, 0)
    if blocked_until > now:
        retry_after = max(1, math.ceil(blocked_until - now))
        raise AIRateLimitError(f"ai rate limit cooldown: retry after {retry_after}s", retry_after)
    _cooldowns.pop(key, None)
    timeout = httpx.Timeout(cfg.ai_timeout, connect=10)
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as http:
            r = await http.post(
                f"{cfg.ai_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {cfg.ai_api_key}"},
                json={"model": cfg.ai_model, "temperature": 0.7, "messages": [
                    {"role": "system", "content": cfg.ai_prompt},
                    {"role": "user", "content": _user_content(text, image_path)}]},
            )
    except httpx.HTTPError as e:
        raise AIError(f"ai network error: {type(e).__name__}") from e
    if r.status_code == 429:
        retry_after = _retry_after(r)
        _cooldowns[key] = time.monotonic() + retry_after
        raise AIRateLimitError(f"ai http 429: retry after {retry_after}s: {r.text[:200]}", retry_after)
    if r.status_code != 200:
        raise AIError(f"ai http {r.status_code}: {r.text[:200]}")
    try:
        choice = r.json()["choices"][0]
        message = choice['message']
        if message.get('refusal') or choice.get('finish_reason') == 'content_filter':
            raise AIRefusalError('Нейросеть отказалась создать подпись')
        out = message['content']
    except (KeyError, IndexError, ValueError, TypeError) as e:
        raise AIError("ai bad response shape") from e
    return validate_caption(out)
