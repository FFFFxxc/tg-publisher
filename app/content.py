"""Очистка подписей, импортированных из чужих Telegram-каналов."""
from __future__ import annotations

import copy
import re
from bisect import bisect_left

from telethon.tl import types


_PATTERNS = (
    re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s<>()\[\]{}]+"),
    re.compile(r"(?i)(?<![\w@])(?:www\.|t\.me/|telegram\.me/)[^\s<>()\[\]{}]+"),
    re.compile(r"(?i)(?<![\w@])[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,24}(?!\w)"),
    re.compile(r"(?i)(?<![\w@])@[a-z0-9_]{4,}(?!\w)"),
    re.compile(
        r"(?i)(?<![@\w])"
        r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
        r"[a-z]{2,24}(?:/[^\s<>()\[\]{}]*)?"
    ),
)

_TRAILING_URL_PUNCTUATION = ".,;:!?…'\"»”)]}"
_LINK_ENTITY_TYPES = tuple(
    cls
    for name in (
        "MessageEntityUrl",
        "MessageEntityTextUrl",
        "MessageEntityMention",
        "MessageEntityMentionName",
        "InputMessageEntityMentionName",
        "MessageEntityEmail",
    )
    if (cls := getattr(types, name, None)) is not None
)
_EXPLICIT_ADVERTISEMENT = re.compile(
    r"(?iu)(?<!\w)#(?:реклама|advertisement|ad)(?!\w)"
    r"|\b(?:рекламный пост|рекламная интеграция|на правах рекламы)\b"
)


def _u16(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def is_advertisement(text: str | None) -> bool:
    """Распознаёт только явную маркировку рекламы, без догадок по содержанию."""
    return bool(_EXPLICIT_ADVERTISEMENT.search(text or ""))


def filter_source_content(text: str | None, entities: list | None = None) -> tuple[str, list]:
    """Удаляет рекламные ссылки и корректно пересчитывает остальные entities.

    Telegram хранит offsets в UTF-16, поэтому remap делается по исходным символам,
    а не по индексам Python. Входные entity не изменяются.
    """
    source = text or ""
    source_entities = list(entities or [])
    if not source:
        return "", []

    boundaries = [0]
    for char in source:
        boundaries.append(boundaries[-1] + _u16(char))
    keep = [True] * len(source)

    def delete_codepoints(start: int, end: int) -> None:
        for index in range(max(start, 0), min(end, len(keep))):
            keep[index] = False

    def delete_u16(start: int, end: int) -> None:
        cp_start = max(0, bisect_left(boundaries, start))
        cp_end = min(len(source), bisect_left(boundaries, end))
        delete_codepoints(cp_start, cp_end)

    for entity in source_entities:
        if isinstance(entity, _LINK_ENTITY_TYPES):
            delete_u16(entity.offset, entity.offset + entity.length)

    for pattern in _PATTERNS:
        for match in pattern.finditer(source):
            end = match.end()
            while end > match.start() and source[end - 1] in _TRAILING_URL_PUNCTUATION:
                end -= 1
            delete_codepoints(match.start(), end)

    # Убираем пробельный мусор, оставшийся на месте удалённой ссылки.
    visible = [i for i, present in enumerate(keep) if present]
    while visible and source[visible[0]].isspace():
        keep[visible.pop(0)] = False
    while visible and source[visible[-1]].isspace():
        keep[visible.pop()] = False

    previous_kept: int | None = None
    newline_run = 0
    for index, char in enumerate(source):
        if not keep[index]:
            continue
        if char in " \t" and previous_kept is not None and source[previous_kept] in " \t":
            keep[index] = False
            continue
        if char == "\n":
            if previous_kept is not None and source[previous_kept] in " \t":
                keep[previous_kept] = False
            newline_run += 1
            if newline_run > 2:
                keep[index] = False
                continue
        elif char != "\r":
            newline_run = 0
        previous_kept = index

    clean = "".join(char for index, char in enumerate(source) if keep[index])
    remapped = []
    for entity in source_entities:
        if isinstance(entity, _LINK_ENTITY_TYPES):
            continue
        start = bisect_left(boundaries, entity.offset)
        end = bisect_left(boundaries, entity.offset + entity.length)
        if (
            start >= end
            or start >= len(boundaries)
            or end >= len(boundaries)
            or boundaries[start] != entity.offset
            or boundaries[end] != entity.offset + entity.length
        ):
            continue
        if not all(keep[start:end]):
            continue
        cloned = copy.copy(entity)
        cloned.offset = sum(_u16(source[i]) for i in range(start) if keep[i])
        cloned.length = sum(_u16(source[i]) for i in range(start, end) if keep[i])
        remapped.append(cloned)

    return clean, remapped
