"""Опциональные AI-подписи. Ходят напрямую (не через Telegram SOCKS), с жёстким таймаутом."""
from __future__ import annotations

import base64
import mimetypes

import httpx

from .config import Config


class AIError(RuntimeError):
    pass


def _user_content(text: str, image_path: str | None):
    if not image_path:
        return text
    mime = mimetypes.guess_type(image_path)[0] or "image/jpeg"
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return [{"type": "text", "text": text or "(у поста нет текста, подпиши по картинке)"},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]


async def generate_caption(cfg: Config, text: str, image_path: str | None = None) -> str:
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
    if r.status_code != 200:
        raise AIError(f"ai http {r.status_code}: {r.text[:200]}")
    try:
        out = r.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, ValueError) as e:
        raise AIError("ai bad response shape") from e
    if not out:
        raise AIError("ai empty response")
    return out
