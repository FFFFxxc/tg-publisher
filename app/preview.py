"""Shared, persistent image previews for AI caption generation.

The cache deliberately uses the caller's existing Telethon client.  In
particular it never creates a second connection, so the configured SOCKS5
transport and Telethon's normal cross-DC download handling remain in force.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageOps, UnidentifiedImageError
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto, VideoSize

from .tg import ensure_connected, resolve

log = logging.getLogger("preview")
UNCERTAIN = (ConnectionError, asyncio.TimeoutError, TimeoutError, OSError)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


class PreviewCache:
    """Build one bounded JPEG preview per post, with concurrent de-duplication."""

    def __init__(self, client, cache_dir="/home/app/.data/previews", *,
                 max_concurrency: int = 2, timeout: float = 90):
        self.client = client
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._locks: dict[str, asyncio.Lock] = {}

    async def get(self, post_id, msgs=None, source_ref=None, source_msg_ids=None,
                  downloaded_files=None) -> str | None:
        """Return a local cached preview path, or ``None`` when no image exists."""
        key = str(post_id)
        target = self.cache_dir / f"post_{key}.jpg"
        if self._valid_image(target):
            return str(target)

        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            if self._valid_image(target):
                return str(target)
            async with self._semaphore:
                return await asyncio.wait_for(
                    self._build(target, msgs, source_ref, source_msg_ids, downloaded_files),
                    timeout=self.timeout,
                )

    async def _build(self, target: Path, msgs, source_ref, source_msg_ids,
                     downloaded_files) -> str | None:
        if msgs is None:
            if not source_ref or not source_msg_ids:
                return None
            await ensure_connected(self.client)
            entity = await resolve(self.client, source_ref)
            received = await self.client.get_messages(entity, ids=list(source_msg_ids))
            by_id = {m.id: m for m in received if m is not None}
            msgs = [by_id[mid] for mid in source_msg_ids if mid in by_id]

        work = Path(tempfile.mkdtemp(prefix="preview_", dir=self.cache_dir))
        try:
            files = list(downloaded_files or [])
            for msg in msgs or []:
                source = self._matching_download(msg, files)
                if source is not None and self._write_preview(source, target):
                    return str(target)

                media = getattr(msg, "media", None)
                kwargs = {}
                if isinstance(media, MessageMediaPhoto):
                    pass
                elif isinstance(media, MessageMediaDocument):
                    thumb = self._largest_static_thumb(getattr(msg, "document", None)
                                                      or getattr(media, "document", None))
                    if thumb is None:
                        continue
                    kwargs["thumb"] = thumb
                else:
                    continue

                candidate = work / f"{msg.id}.jpg"
                try:
                    downloaded = await self.client.download_media(msg, file=str(candidate), **kwargs)
                    if downloaded and self._write_preview(Path(downloaded), target):
                        return str(target)
                    log.warning("invalid AI preview msg=%s", msg.id)
                except UNCERTAIN:
                    raise
                except Exception as exc:
                    log.warning("AI preview download failed msg=%s: %s: %s",
                                msg.id, type(exc).__name__, exc)
            return None
        finally:
            shutil.rmtree(work, ignore_errors=True)

    @staticmethod
    def _largest_static_thumb(document):
        thumbs = getattr(document, "thumbs", None) or []
        static = [t for t in thumbs
                  if not isinstance(t, VideoSize)
                  and type(t).__name__.startswith("Photo")
                  and getattr(t, "w", 0) and getattr(t, "h", 0)]
        return max(static, key=lambda t: (t.w * t.h, getattr(t, "size", 0)), default=None)

    @staticmethod
    def _matching_download(msg, files: Iterable[str]) -> Path | None:
        if not isinstance(getattr(msg, "media", None), MessageMediaPhoto):
            return None
        marker = re.compile(rf"(?:^|\D){re.escape(str(msg.id))}(?:\D|$)")
        for raw in files:
            path = Path(raw)
            if path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            # Publisher stores media under <tmp>/<message-id>/<filename>.
            if path.parent.name == str(msg.id) or marker.search(path.stem):
                return path
        return None

    @staticmethod
    def _valid_image(path: Path) -> bool:
        if not path.is_file() or path.stat().st_size == 0:
            return False
        try:
            with Image.open(path) as image:
                image.verify()
            return True
        except (OSError, ValueError, UnidentifiedImageError):
            return False

    @staticmethod
    def _write_preview(source: Path, target: Path) -> bool:
        part = target.with_suffix(f".{os.getpid()}.part")
        try:
            with Image.open(source) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
                image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
                image.save(part, format="JPEG", quality=88, optimize=True)
            os.replace(part, target)
            return True
        except (OSError, ValueError, UnidentifiedImageError):
            part.unlink(missing_ok=True)
            return False
