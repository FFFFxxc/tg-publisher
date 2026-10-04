"""Дополнительные user-аккаунты для реакций на посты собственного канала."""
from __future__ import annotations

import asyncio
import logging
import re
import secrets
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from telethon import TelegramClient, errors, functions, types, utils

from .logic import parse_ref
from .networks import REACTION_SECONDS, load_settings, reaction_target

log = logging.getLogger("activity")
PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")
CODE_RE = re.compile(r"^\d{4,8}$")
PENDING_TTL = 600
MAX_PENDING = 5


def normalize_phone(value: str) -> str:
    phone = re.sub(r"[\s()\-]", "", str(value or ""))
    if not PHONE_RE.fullmatch(phone):
        raise ValueError("Введите номер в международном формате, например +79991234567")
    return phone


def mask_phone(phone: str) -> str:
    return phone[:3] + "•" * max(4, len(phone) - 6) + phone[-3:]


@dataclass
class PendingLogin:
    account_id: str
    phone: str
    phone_code_hash: str
    client: object
    created_at: float


class ActivityAccounts:
    def __init__(self, cfg, db, client_factory=TelegramClient, approver=None):
        self.cfg, self.db = cfg, db
        self.client_factory = client_factory
        self.approver = approver
        self.base_dir = Path(cfg.session_path).parent / "activity-accounts"
        self.pending: dict[str, PendingLogin] = {}
        self.clients: dict[str, object] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._settings_changed = asyncio.Event()
        self.network_settings_lock = asyncio.Lock()
        self._last_reactions: dict[str, str] = {}

    def _new_client(self, session_path: str):
        return self.client_factory(
            session_path, self.cfg.api_id, self.cfg.api_hash,
            proxy=self.cfg.proxy, flood_sleep_threshold=120, auto_reconnect=False,
            connection_retries=3, request_retries=3, timeout=30,
        )

    async def start_login(self, phone_value: str) -> dict:
        await self._sweep_pending()
        phone = normalize_phone(phone_value)
        for token, pending in list(self.pending.items()):
            if pending.phone == phone:
                await self._discard_pending(token, pending)
        if len(self.pending) >= MAX_PENDING:
            raise ValueError("Слишком много незавершённых входов — завершите один из них")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        account_id = uuid.uuid4().hex
        client = self._new_client(str(self.base_dir / account_id))
        await client.connect()
        try:
            sent = await client.send_code_request(phone)
        except Exception:
            await client.disconnect()
            self._remove_session_files(str(self.base_dir / account_id))
            raise
        token = uuid.uuid4().hex
        self.pending[token] = PendingLogin(account_id, phone, sent.phone_code_hash, client, time.time())
        return {"login_token": token, "phone_mask": mask_phone(phone), "expires_in": PENDING_TTL}

    async def complete_login(self, token: str, code_value: str = "", password: str = "") -> dict:
        await self._sweep_pending()
        pending = self.pending.get(str(token or ""))
        if pending is None:
            raise ValueError("Код входа истёк — запросите новый")
        code = re.sub(r"\s", "", str(code_value or ""))
        try:
            if password:
                await pending.client.sign_in(password=password)
            else:
                if not CODE_RE.fullmatch(code):
                    raise ValueError("Введите код из Telegram")
                await pending.client.sign_in(
                    phone=pending.phone, code=code, phone_code_hash=pending.phone_code_hash,
                )
        except errors.SessionPasswordNeededError:
            return {"authorized": False, "password_required": True,
                    "login_token": token, "phone_mask": mask_phone(pending.phone)}
        except (errors.PhoneCodeInvalidError, errors.PhoneCodeExpiredError) as exc:
            raise ValueError("Неверный или просроченный код Telegram") from exc
        except errors.PasswordHashInvalidError as exc:
            raise ValueError("Неверный пароль двухэтапной аутентификации") from exc

        me = await pending.client.get_me()
        display_name = " ".join(x for x in (getattr(me, "first_name", ""),
                                              getattr(me, "last_name", "")) if x).strip()
        display_name = display_name or ("@" + me.username if getattr(me, "username", None) else str(me.id))
        session_path = str(self.base_dir / pending.account_id)
        previous = await self.db.activity_account_by_telegram_id(me.id)
        previous_path = previous.get("session_path") if previous else None
        saved_id = await self.db.save_activity_account(
            pending.account_id, me.id, mask_phone(pending.phone), display_name, session_path,
        )
        self.pending.pop(token, None)
        if saved_id != pending.account_id:
            old = self.clients.pop(saved_id, None)
            if old and old is not pending.client:
                await old.disconnect()
            if previous_path and previous_path != session_path:
                self._remove_session_files(previous_path)
        self.clients[saved_id] = pending.client
        try:
            await self._resolve_activity_target(pending.client, me.id)
            await self.db.set_activity_account_status(saved_id, "ready")
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"[:500]
            await self.db.set_activity_account_status(saved_id, "error", detail)
            log.warning("activity account=%s initial join failed: %s", saved_id, detail)
        return {"authorized": True, "password_required": False, "account_id": saved_id,
                "display_name": display_name}

    async def list(self) -> list[dict]:
        return [{key: value for key, value in row.items() if key != "session_path"}
                for row in await self.db.activity_accounts()]

    async def settings(self) -> dict:
        seconds = int(await self.db.kv_get("activity_interval_sec", str(self.cfg.activity_interval)))
        return {"interval_minutes": max(1, seconds // 60), "max_reactions_per_account": 1}

    async def update_settings(self, interval_minutes) -> dict:
        if isinstance(interval_minutes, bool):
            raise ValueError("Интервал должен быть целым числом минут")
        try:
            minutes = int(interval_minutes)
        except (TypeError, ValueError) as exc:
            raise ValueError("Интервал должен быть целым числом минут") from exc
        if minutes < 1 or minutes > 1440:
            raise ValueError("Интервал должен быть от 1 до 1440 минут")
        await self.db.kv_set("activity_interval_sec", minutes * 60)
        self._settings_changed.set()
        return {"interval_minutes": minutes, "max_reactions_per_account": 1}

    async def set_enabled(self, account_id: str, enabled: bool) -> None:
        lock = self._locks.setdefault(account_id, asyncio.Lock())
        async with lock:
            if not await self.db.set_activity_account_enabled(account_id, enabled):
                raise LookupError("Аккаунт не найден")
            if not enabled:
                await self._disconnect(account_id)

    async def delete(self, account_id: str) -> None:
        lock = self._locks.setdefault(account_id, asyncio.Lock())
        async with lock:
            await self._disconnect(account_id)
            row = await self.db.delete_activity_account(account_id)
            if row is None:
                raise LookupError("Аккаунт не найден")
            self._remove_session_files(row["session_path"])
        self._locks.pop(account_id, None)

    async def react_now(self, account_id: str | None = None) -> dict:
        rows = await self.db.activity_accounts()
        if account_id:
            rows = [row for row in rows if row["id"] == account_id]
            if not rows:
                raise LookupError("Аккаунт не найден")
        semaphore = asyncio.Semaphore(4)

        async def one(row):
            if not row["enabled"]:
                return None
            try:
                async with semaphore:
                    count = await self._react_account(row, limit=1)
                return {"account_id": row["id"], "reacted": count, "status": "ready"}
            except Exception as exc:
                detail = f"{type(exc).__name__}: {exc}"[:500]
                await self.db.set_activity_account_status(row["id"], "error", detail)
                log.warning("activity account=%s failed: %s", row["id"], detail)
                return {"account_id": row["id"], "reacted": 0, "status": "error", "error": detail}

        results = [result for result in await asyncio.gather(*(one(row) for row in rows)) if result]
        return {"items": results, "reacted": sum(item["reacted"] for item in results)}

    async def _react_account(self, row: dict, limit: int = 1) -> int:
        lock = self._locks.setdefault(row["id"], asyncio.Lock())
        async with lock:
            current = await self.db.activity_account(row["id"])
            if current is None or not current["enabled"]:
                return 0
            row = current
            client = await self._client(row)
            entity = await self._resolve_activity_target(client, row["telegram_user_id"])
            target_ref = str(getattr(entity, "id", self.cfg.destination))
            messages = await client.get_messages(entity, limit=self.cfg.activity_recent_limit)
            reacted = 0
            for message in reversed(messages):
                if not message or getattr(message, "action", None) is not None:
                    continue
                if await self.db.activity_reacted(row["id"], target_ref, message.id):
                    continue
                reaction = self._next_reaction(row["id"])
                await client(functions.messages.SendReactionRequest(
                    peer=entity, msg_id=message.id,
                    reaction=[types.ReactionEmoji(emoticon=reaction)],
                    big=False, add_to_recent=False,
                ))
                await self.db.mark_activity_reacted(row["id"], target_ref, message.id)
                reacted += 1
                if reacted >= limit:
                    break
            await self.db.set_activity_account_status(row["id"], "ready")
            return reacted

    def _next_reaction(self, account_id: str, available=None) -> str:
        configured = list(dict.fromkeys(available if available is not None else
                          (getattr(self.cfg, "activity_reactions", None) or [self.cfg.activity_reaction])))
        if not configured:
            raise ValueError('В канале не разрешены настроенные реакции')
        previous = self._last_reactions.get(account_id)
        choices = [reaction for reaction in configured if reaction != previous] or configured
        selected = secrets.choice(choices)
        self._last_reactions[account_id] = selected
        return selected

    async def _client(self, row: dict):
        client = self.clients.get(row["id"])
        if client is None:
            client = self._new_client(row["session_path"])
            self.clients[row["id"]] = client
        if not client.is_connected():
            await client.connect()
        if not await client.is_user_authorized():
            raise RuntimeError("сессия Telegram отозвана — добавьте аккаунт заново")
        return client

    async def _resolve(self, client, ref: str):
        kind, value = parse_ref(ref)
        if kind == "invite":
            info = await client(functions.messages.CheckChatInviteRequest(value))
            if isinstance(info, (types.ChatInviteAlready, types.ChatInvitePeek)):
                return info.chat
            update = await client(functions.messages.ImportChatInviteRequest(value))
            return update.chats[0]
        try:
            return await client.get_entity(value)
        except ValueError:
            await client.get_dialogs()
            return await client.get_entity(value)

    async def _resolve_activity_target(self, client, telegram_user_id: int):
        try:
            return await self._resolve(client, self.cfg.destination)
        except ValueError:
            invite = str(getattr(self.cfg, "activity_target_invite", "") or "").strip()
            kind, invite_hash = parse_ref(invite) if invite else (None, None)
            if kind != "invite":
                raise ValueError("Аккаунт не состоит в закрытой группе, а ACTIVITY_TARGET_INVITE не задан")

        request_sent = False
        try:
            await client(functions.messages.ImportChatInviteRequest(invite_hash))
        except errors.InviteRequestSentError:
            request_sent = True
        except errors.UserAlreadyParticipantError:
            pass
        if request_sent:
            await self._approve_join_request(telegram_user_id)

        last_error = None
        for _ in range(10):
            try:
                await client.get_dialogs()
                return await self._resolve(client, self.cfg.destination)
            except ValueError as exc:
                last_error = exc
                await asyncio.sleep(0.5)
        raise ValueError("Заявка одобрена, но группа ещё не появилась в диалогах аккаунта") from last_error

    async def _approve_join_request(self, telegram_user_id: int, target_ref=None):
        if self.approver is None:
            raise RuntimeError("Основной аккаунт для одобрения заявки не подключён")
        if not self.approver.is_connected():
            await self.approver.connect()
        peer = await self._resolve(self.approver, target_ref or self.cfg.destination)
        for _ in range(10):
            pending = await self.approver(functions.messages.GetChatInviteImportersRequest(
                peer=peer, offset_date=None, offset_user=types.InputUserEmpty(), limit=100,
                requested=True,
            ))
            user = next((user for user in pending.users if user.id == telegram_user_id), None)
            if user is not None:
                await self.approver(functions.messages.HideChatJoinRequestRequest(
                    peer=peer, user_id=utils.get_input_user(user), approved=True,
                ))
                return
            await asyncio.sleep(0.5)
        raise RuntimeError("Заявка аккаунта на вступление не найдена для одобрения")

    async def _resolve_network_target(self, client, ref, telegram_user_id):
        kind, value = parse_ref(ref)
        if kind == 'id' and parse_ref(self.cfg.destination) == (kind, value):
            return await self._resolve_activity_target(client, telegram_user_id)
        try:
            entity = await self._resolve(client, ref)
            if isinstance(entity, types.Channel):
                try:
                    await client(functions.channels.JoinChannelRequest(entity))
                except errors.UserAlreadyParticipantError:
                    pass
            return entity
        except errors.InviteRequestSentError:
            await self._approve_join_request(telegram_user_id, ref)
            for _ in range(10):
                try:
                    await client.get_dialogs()
                    return await self._resolve(client, ref)
                except (ValueError, errors.InviteRequestSentError):
                    await asyncio.sleep(0.5)
            raise RuntimeError('Заявка одобрена, но канал ещё не появился')

    async def network_tick(self):
        # Independent persisted per-account/per-channel schedule. Never inherit
        # the primary group's interval or reset it when the worker restarts.
        await self.db.network_recover()
        for due in await self.db.network_due():
            network_id, aid = due['network_id'], due['id']
            lock = self._locks.setdefault(aid, asyncio.Lock())
            async with lock:
                settings = await load_settings(self.db, self.cfg, network_id)
                if not settings['enabled']:
                    continue
                token = uuid.uuid4().hex
                if not await self.db.network_claim(network_id, aid, token):
                    continue
                try:
                    count = await asyncio.wait_for(self._network_react(aid, network_id, settings, token), 240)
                    await self.db.network_finish(network_id, aid, token, 'ready' if count else 'no_new_posts')
                except errors.FloodWaitError as exc:
                    await self.db.network_finish(network_id, aid, token, 'error', f'FloodWait {exc.seconds}s',
                                                 max(REACTION_SECONDS, exc.seconds))
                except Exception as exc:
                    detail = f'{type(exc).__name__}: {exc}'[:500]
                    await self.db.network_finish(network_id, aid, token, 'error', detail)
                    log.warning('network=%s account=%s reactions failed: %s', network_id, aid, detail)

    async def _network_react(self, aid, network_id, settings, token):
        row = await self.db.activity_account(aid)
        if not row or not row['enabled']:
            return 0
        client = await self._client(row)
        ref = reaction_target(network_id, settings)
        async def active():
            binding = await self.db.network_binding(network_id, aid)
            current = await load_settings(self.db, self.cfg, network_id)
            account = await self.db.activity_account(aid)
            return (binding and binding['enabled'] and binding['claim_token'] == token
                    and account and account['enabled'] and current['enabled']
                    and reaction_target(network_id, current) == ref)

        # Settings updates share this lock: once a save completes no obsolete
        # join/reaction may start. An already-started RPC finishes before saving.
        async with self.network_settings_lock:
            if not await active():
                return 0
            entity = await self._resolve_network_target(client, ref, row['telegram_user_id'])
        if isinstance(entity, types.User):
            raise ValueError('Укажите канал или группу, а не личный аккаунт')
        configured = getattr(self.cfg, 'activity_reactions', None) or [self.cfg.activity_reaction]
        if isinstance(entity, types.Channel):
            full = await client(functions.channels.GetFullChannelRequest(entity))
            allowed = getattr(full.full_chat, 'available_reactions', None)
            if isinstance(allowed, types.ChatReactionsNone):
                raise ValueError('В канале отключены реакции')
            if isinstance(allowed, types.ChatReactionsSome):
                emojis = {r.emoticon for r in allowed.reactions if isinstance(r, types.ReactionEmoji)}
                configured = [r for r in configured if r in emojis]
        target_ref = str(getattr(entity, 'id', ref))
        messages = await client.get_messages(entity, limit=self.cfg.activity_recent_limit)
        for message in reversed(messages):
            if not message or getattr(message, 'action', None) is not None:
                continue
            if await self.db.activity_reacted(aid, target_ref, message.id):
                continue
            # Recover a Telegram-confirmed reaction whose local receipt was lost.
            results = getattr(getattr(message, 'reactions', None), 'results', []) or []
            if any(getattr(r, 'chosen_order', None) is not None for r in results):
                await self.db.mark_activity_reacted(aid, target_ref, message.id)
                continue
            async with self.network_settings_lock:
                if not await active():
                    return 0
                reaction = self._next_reaction(aid + ':' + network_id, configured)
                # Physical identity, not workflow/name: aliases or two workflows
                # pointing at one peer must not double the six-hour cadence.
                if not await self.db.network_claim_target(aid, target_ref):
                    return 0
                await client(functions.messages.SendReactionRequest(peer=entity, msg_id=message.id,
                    reaction=[types.ReactionEmoji(emoticon=reaction)], big=False, add_to_recent=False))
                await self.db.mark_activity_reacted(aid, target_ref, message.id)
            return 1
        return 0

    async def network_run(self):
        log.info('network reactions loop started, per-account interval=6h')
        while True:
            try:
                await self.network_tick()
            except Exception:
                log.exception('network reactions loop failed')
            await asyncio.sleep(30)

    async def run(self):
        while True:
            try:
                await self._sweep_pending()
                await self.react_now()
            except Exception:
                log.exception("activity loop failed")
            seconds = int(await self.db.kv_get("activity_interval_sec", str(self.cfg.activity_interval)))
            self._settings_changed.clear()
            try:
                await asyncio.wait_for(self._settings_changed.wait(), timeout=max(60, seconds))
            except asyncio.TimeoutError:
                pass

    async def close(self):
        for token, pending in list(self.pending.items()):
            await pending.client.disconnect()
            self.pending.pop(token, None)
        for account_id in list(self.clients):
            await self._disconnect(account_id)

    async def _disconnect(self, account_id: str):
        client = self.clients.pop(account_id, None)
        if client and client.is_connected():
            await client.disconnect()

    async def _sweep_pending(self):
        now = time.time()
        for token, pending in list(self.pending.items()):
            if now - pending.created_at > PENDING_TTL:
                await self._discard_pending(token, pending)

    async def _discard_pending(self, token: str, pending: PendingLogin):
        self.pending.pop(token, None)
        if pending.client.is_connected():
            await pending.client.disconnect()
        self._remove_session_files(str(self.base_dir / pending.account_id))

    @staticmethod
    def _remove_session_files(session_path: str):
        path = Path(session_path)
        for candidate in (path, Path(str(path) + ".session"), Path(str(path) + ".session-journal")):
            try:
                candidate.unlink(missing_ok=True)
            except OSError:
                log.warning("cannot remove session file %s", candidate)
