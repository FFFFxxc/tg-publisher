"""Telethon-клиент. Прокси задаётся в конструкторе, чтобы его наследовали
exported senders и скачивания после FileMigrateError в другой DC."""
from __future__ import annotations

import asyncio
import logging

from telethon import TelegramClient
from telethon.sessions import StringSession

from .config import Config

log = logging.getLogger("tg")

# Один Telethon client используется несколькими worker-loop. Без lock несколько
# coroutine могут одновременно вызвать client.connect() после старта/обрыва и
# зависнуть внутри Telethon. Сериализуем reconnect и повторно проверяем состояние.
_connect_lock = asyncio.Lock()


class SessionError(RuntimeError):
    pass


def build_client(cfg: Config) -> TelegramClient:
    session = StringSession(cfg.session) if cfg.session else cfg.session_path
    client = TelegramClient(
        session, cfg.api_id, cfg.api_hash,
        proxy=cfg.proxy,
        flood_sleep_threshold=120,
        auto_reconnect=False,          # переподключением управляем сами (ensure_connected)
        connection_retries=3, request_retries=3, timeout=30,
    )
    verify_client_proxy(client, cfg.proxy)
    return client


def verify_client_proxy(client, expected: dict | None):
    actual = getattr(client, "_proxy", None)
    if expected and actual != expected:
        raise RuntimeError("TG_PROXY_HOST is set, but TelegramClient has no matching proxy config")
    log.info("telegram transport: %s", f"socks5 {expected['addr']}:{expected['port']} rdns" if expected else "direct")


async def ensure_connected(client: TelegramClient):
    if client.is_connected():
        return
    async with _connect_lock:
        # Пока ждали lock, другой loop мог уже восстановить соединение.
        if client.is_connected():
            return
        log.info("telegram connecting")
        try:
            await asyncio.wait_for(client.connect(), timeout=45)
            if not await asyncio.wait_for(client.is_user_authorized(), timeout=30):
                await client.disconnect()
                raise SessionError("userbot is not logged in (or session revoked). "
                                   "Run once: docker compose run --rm app login")
            me = await asyncio.wait_for(client.get_me(), timeout=30)
            log.info("telegram authorized as id=%s", me.id)
        except asyncio.TimeoutError:
            try:
                await client.disconnect()
            except Exception:
                pass
            raise ConnectionError("telegram connect timed out")


_cache: dict[str, object] = {}


async def resolve(client, ref: str):
    """Открытые и закрытые каналы: @username, -100ID, инвайт t.me/+hash.
    По инвайту вступает сам, если ещё не участник."""
    if ref in _cache:
        return _cache[ref]
    from telethon import functions, types
    from .logic import parse_ref
    kind, val = parse_ref(ref)
    if kind == "invite":
        info = await client(functions.messages.CheckChatInviteRequest(val))
        if isinstance(info, (types.ChatInviteAlready, types.ChatInvitePeek)):
            ent = info.chat
        else:
            log.info("joining private chat by invite %s…", val[:4])
            upd = await client(functions.messages.ImportChatInviteRequest(val))
            ent = upd.chats[0]
    elif kind == "id":
        try:
            ent = await client.get_entity(val)
        except ValueError:
            # свежая сессия ещё не знает access_hash закрытого канала: прогреваем кэш диалогами
            log.info("entity %s not cached, loading dialogs", val)
            await client.get_dialogs()
            ent = await client.get_entity(val)
    else:
        ent = await client.get_entity(val)
    _cache[ref] = ent
    return ent
