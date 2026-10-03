import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiohttp.test_utils import TestClient, TestServer
from telethon import errors, functions, types

from app.activity import ActivityAccounts, mask_phone, normalize_phone
from app.api import ApiContext, build_app


class FakeDB:
    def __init__(self):
        self.rows = []
        self.reacted = set()
        self.kv = {}

    async def kv_get(self, key, default=None): return self.kv.get(key, default)
    async def kv_set(self, key, value): self.kv[key] = str(value)

    async def save_activity_account(self, aid, uid, phone, name, path):
        existing = next((row for row in self.rows if row["telegram_user_id"] == uid), None)
        if existing:
            existing.update(phone_mask=phone, display_name=name, session_path=path,
                            enabled=True, status="ready", last_error=None)
            return existing["id"]
        self.rows = [{"id": aid, "telegram_user_id": uid, "phone_mask": phone,
                      "display_name": name, "session_path": path, "enabled": True,
                      "status": "ready", "last_error": None, "last_active_at": None,
                      "created_at": "now", "updated_at": "now"}]
        return aid

    async def activity_accounts(self):
        return self.rows

    async def activity_account(self, aid):
        return next((r for r in self.rows if r["id"] == aid), None)

    async def activity_account_by_telegram_id(self, uid):
        return next((r for r in self.rows if r["telegram_user_id"] == uid), None)

    async def activity_reacted(self, aid, target, mid):
        return (aid, target, mid) in self.reacted

    async def mark_activity_reacted(self, aid, target, mid):
        self.reacted.add((aid, target, mid))

    async def set_activity_account_status(self, aid, status, error=None):
        row = next(r for r in self.rows if r["id"] == aid)
        row.update(status=status, last_error=error)

    async def set_activity_account_enabled(self, aid, enabled):
        row = next((r for r in self.rows if r["id"] == aid), None)
        if row: row["enabled"] = enabled
        return bool(row)

    async def delete_activity_account(self, aid):
        row = next((r for r in self.rows if r["id"] == aid), None)
        if row: self.rows.remove(row)
        return {"session_path": row["session_path"]} if row else None


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.connected = False
        self.authorized = False
        self.requests = []

    async def connect(self): self.connected = True
    async def disconnect(self): self.connected = False
    def is_connected(self): return self.connected
    async def is_user_authorized(self): return self.authorized
    async def send_code_request(self, phone): return SimpleNamespace(phone_code_hash="hash")
    async def sign_in(self, **kwargs): self.authorized = True
    async def get_me(self): return SimpleNamespace(id=42, first_name="Иван", last_name="", username="ivan")
    async def get_entity(self, value): return "destination"
    async def get_dialogs(self): return []
    async def get_messages(self, entity, limit):
        return [SimpleNamespace(id=2, action=None), SimpleNamespace(id=1, action=None)]
    async def __call__(self, request): self.requests.append(request); return SimpleNamespace()


def cfg(path):
    return SimpleNamespace(session_path=str(Path(path) / "main"), api_id=1, api_hash="hash", proxy=None,
                           destination="@private", activity_recent_limit=20,
                           activity_reaction="👍", activity_reactions=["❤", "👍", "🔥", "😍", "😁"],
                           activity_target_invite="", activity_interval=30)


class JoinClient(FakeClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.connected = True
        self.authorized = True
        self.member = False

    async def get_entity(self, value):
        if not self.member:
            raise ValueError("unknown private peer")
        return SimpleNamespace(id=1140244688)

    async def get_dialogs(self): return []

    async def __call__(self, request):
        self.requests.append(request)
        if isinstance(request, functions.messages.ImportChatInviteRequest):
            raise errors.InviteRequestSentError(request=request)
        return SimpleNamespace()


class DirectJoinClient(JoinClient):
    async def __call__(self, request):
        self.requests.append(request)
        if isinstance(request, functions.messages.ImportChatInviteRequest):
            self.member = True
            return SimpleNamespace(chats=[SimpleNamespace(id=1140244688)])
        return SimpleNamespace()


class ApproverClient(FakeClient):
    def __init__(self, member_client):
        super().__init__()
        self.connected = True
        self.authorized = True
        self.member_client = member_client

    async def get_entity(self, value): return SimpleNamespace(id=1140244688)

    async def __call__(self, request):
        self.requests.append(request)
        if isinstance(request, functions.messages.GetChatInviteImportersRequest):
            return SimpleNamespace(users=[types.User(id=42, access_hash=777, first_name="Иван")])
        if isinstance(request, functions.messages.HideChatJoinRequestRequest):
            self.member_client.member = True
        return SimpleNamespace()


class ActivityAccountTests(unittest.IsolatedAsyncioTestCase):
    async def test_completed_login_immediately_joins_private_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = cfg(tmp); c.destination = "-1001140244688"
            c.activity_target_invite = "https://t.me/+testInviteHash"
            member = JoinClient(); approver = ApproverClient(member); db = FakeDB()
            service = ActivityAccounts(c, db, lambda *a, **k: member, approver=approver)
            started = await service.start_login("+79991234567")
            result = await service.complete_login(started["login_token"], "12345")
            self.assertTrue(result["authorized"])
            self.assertTrue(member.member)
            self.assertEqual(db.rows[0]["status"], "ready")

    async def test_unknown_private_group_joins_by_invite_and_admin_approves(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = cfg(tmp); c.destination = "-1001140244688"
            c.activity_target_invite = "https://t.me/+testInviteHash"
            member = JoinClient()
            approver = ApproverClient(member)
            service = ActivityAccounts(c, FakeDB(), lambda *a, **k: member, approver=approver)
            entity = await service._resolve_activity_target(member, 42)
            self.assertEqual(entity.id, 1140244688)
            self.assertTrue(any(isinstance(r, functions.messages.ImportChatInviteRequest)
                                for r in member.requests))
            approvals = [r for r in approver.requests
                         if isinstance(r, functions.messages.HideChatJoinRequestRequest)]
            self.assertEqual(len(approvals), 1)
            self.assertTrue(approvals[0].approved)

    async def test_direct_invite_join_needs_no_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = cfg(tmp); c.destination = "-1001140244688"
            c.activity_target_invite = "https://t.me/+testInviteHash"
            member = DirectJoinClient()
            service = ActivityAccounts(c, FakeDB(), lambda *a, **k: member)
            entity = await service._resolve_activity_target(member, 42)
            self.assertEqual(entity.id, 1140244688)

    async def test_reactions_are_selected_from_positive_rotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = FakeDB(); service = ActivityAccounts(cfg(tmp), db, FakeClient)
            started = await service.start_login("+79991234567")
            account = await service.complete_login(started["login_token"], "12345")
            await service.react_now(account["account_id"])
            await service.react_now(account["account_id"])
            reactions = [r.reaction[0].emoticon for r in service.clients[account["account_id"]].requests
                         if isinstance(r, functions.messages.SendReactionRequest)]
            self.assertEqual(len(reactions), 2)
            self.assertNotEqual(reactions[0], reactions[1])
            self.assertTrue(set(reactions).issubset({"❤", "👍", "🔥", "😍", "😁"}))
    def test_phone_normalization_and_mask(self):
        self.assertEqual(normalize_phone("+7 (999) 123-45-67"), "+79991234567")
        self.assertEqual(mask_phone("+79991234567"), "+79••••••567")
        with self.assertRaises(ValueError): normalize_phone("8999")

    async def test_login_then_react_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = FakeDB(); service = ActivityAccounts(cfg(tmp), db, FakeClient)
            started = await service.start_login("+79991234567")
            result = await service.complete_login(started["login_token"], "12345")
            self.assertTrue(result["authorized"])
            self.assertNotIn("session_path", (await service.list())[0])
            first = await service.react_now(result["account_id"])
            second = await service.react_now(result["account_id"])
            third = await service.react_now(result["account_id"])
            self.assertEqual((first["reacted"], second["reacted"], third["reacted"]), (1, 1, 0))
            self.assertEqual(db.reacted, {(result["account_id"], "@private", 1),
                                          (result["account_id"], "@private", 2)})
            await service.close()

    async def test_activity_period_persists_and_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = FakeDB(); service = ActivityAccounts(cfg(tmp), db, FakeClient)
            saved = await service.update_settings(15)
            self.assertEqual(saved, {"interval_minutes": 15, "max_reactions_per_account": 1})
            self.assertEqual(await service.settings(), saved)
            self.assertTrue(service._settings_changed.is_set())
            for value in (0, 1441, "bad", True):
                with self.assertRaises(ValueError):
                    await service.update_settings(value)

    async def test_disable_and_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = FakeDB(); service = ActivityAccounts(cfg(tmp), db, FakeClient)
            started = await service.start_login("+79991234567")
            result = await service.complete_login(started["login_token"], "12345")
            await service.set_enabled(result["account_id"], False)
            self.assertFalse(db.rows[0]["enabled"])
            await service.delete(result["account_id"])
            self.assertEqual(db.rows, [])

    async def test_pending_login_expires_and_disconnects(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = ActivityAccounts(cfg(tmp), FakeDB(), FakeClient)
            started = await service.start_login("+79991234567")
            pending = service.pending[started["login_token"]]
            pending.created_at = 0
            await service._sweep_pending()
            self.assertEqual(service.pending, {})
            self.assertFalse(pending.client.is_connected())

    async def test_duplicate_login_removes_previous_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = FakeDB(); service = ActivityAccounts(cfg(tmp), db, FakeClient)
            first = await service.start_login("+79991234567")
            account = await service.complete_login(first["login_token"], "12345")
            old_session = Path(db.rows[0]["session_path"] + ".session")
            old_session.touch()
            second = await service.start_login("+79991234567")
            again = await service.complete_login(second["login_token"], "12345")
            self.assertEqual(again["account_id"], account["account_id"])
            self.assertFalse(old_session.exists())
            await service.close()

    async def test_disable_waits_for_account_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = FakeDB(); service = ActivityAccounts(cfg(tmp), db, FakeClient)
            started = await service.start_login("+79991234567")
            account = await service.complete_login(started["login_token"], "12345")
            lock = service._locks.setdefault(account["account_id"], asyncio.Lock())
            await lock.acquire()
            task = asyncio.create_task(service.set_enabled(account["account_id"], False))
            await asyncio.sleep(0)
            self.assertFalse(task.done())
            lock.release()
            await task
            self.assertFalse(db.rows[0]["enabled"])


class ActivityApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = SimpleNamespace(
            list=AsyncMock(return_value=[]), start_login=AsyncMock(return_value={"login_token": "t"}),
            complete_login=AsyncMock(return_value={"authorized": True}), set_enabled=AsyncMock(),
            delete=AsyncMock(), react_now=AsyncMock(return_value={"reacted": 1, "items": []}),
            settings=AsyncMock(return_value={"interval_minutes": 10, "max_reactions_per_account": 1}),
            update_settings=AsyncMock(return_value={"interval_minutes": 20, "max_reactions_per_account": 1}),
        )
        worker = SimpleNamespace(db=SimpleNamespace(), cfg=SimpleNamespace(), rt=SimpleNamespace(),
                                 activity=self.service)
        self.client = TestClient(TestServer(build_app(ApiContext(worker), "tok")))
        await self.client.start_server()

    async def asyncTearDown(self): await self.client.close()
    def headers(self): return {"Authorization": "Bearer tok", "Content-Type": "application/json"}

    async def test_login_and_account_routes(self):
        response = await self.client.post("/api/activity-accounts/login/start",
                                          json={"phone": "+79991234567"}, headers=self.headers())
        self.assertEqual(response.status, 202)
        response = await self.client.post("/api/activity-accounts/login/complete",
                                          json={"login_token": "t", "code": "12345"}, headers=self.headers())
        self.assertEqual(response.status, 200)
        response = await self.client.patch("/api/activity-accounts/a1", json={"enabled": False},
                                           headers=self.headers())
        self.assertEqual(response.status, 200)
        response = await self.client.post("/api/activity-accounts/a1/react", json={}, headers=self.headers())
        self.assertEqual((response.status, (await response.json())["reacted"]), (200, 1))

    async def test_patch_rejects_non_boolean(self):
        response = await self.client.patch("/api/activity-accounts/a1", json={"enabled": "yes"},
                                           headers=self.headers())
        self.assertEqual(response.status, 400)

    async def test_activity_settings_routes(self):
        response = await self.client.get("/api/activity-settings", headers=self.headers())
        self.assertEqual((response.status, (await response.json())["interval_minutes"]), (200, 10))
        response = await self.client.put("/api/activity-settings", json={"interval_minutes": 20},
                                         headers=self.headers())
        self.assertEqual((response.status, (await response.json())["interval_minutes"]), (200, 20))
        self.service.update_settings.assert_awaited_once_with(20)

    async def test_react_failure_is_not_reported_as_success(self):
        self.service.react_now.return_value = {
            "reacted": 0, "items": [{"account_id": "a1", "reacted": 0,
                                        "status": "error", "error": "FloodWaitError"}],
        }
        response = await self.client.post("/api/activity-accounts/a1/react", json={},
                                          headers=self.headers())
        self.assertEqual(response.status, 409)
        self.assertEqual((await response.json())["error"], "FloodWaitError")


if __name__ == "__main__": unittest.main()
