import asyncio
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from aiohttp.test_utils import TestClient, TestServer
from telethon import functions

from app.activity import ActivityAccounts
from app.api import ApiContext, build_app
from app.networks import NetworkService, defaults, load_settings, validate_settings


ACCOUNT_ID = "a" * 32


def cfg(tmp="."):
    return SimpleNamespace(
        destination="-1001140244688", session_path=str(Path(tmp) / "main"),
        api_id=1, api_hash="hash", proxy=None, activity_recent_limit=20,
        activity_reaction="👍", activity_reactions=["👍", "🔥"],
        activity_target_invite="", activity_interval=3600,
    )


class FakeNetworkDB:
    def __init__(self):
        self.kv = {}
        self.accounts = [{
            "id": ACCOUNT_ID, "telegram_user_id": 42, "display_name": "Аккаунт",
            "phone_mask": "+79••••••567", "session_path": "secret/session/path",
            "enabled": True, "status": "ready",
        }]
        self.bindings = {}
        self.reacted = set()
        self.saves = []
        self.finishes = []
        self.physical_claims = set()
        self.cancel_on_claim = None

    async def kv_get(self, key, default=None):
        return self.kv.get(key, default)

    async def kv_set(self, key, value):
        self.kv[key] = str(value)

    async def activity_accounts(self):
        return [dict(row) for row in self.accounts]

    async def activity_account(self, aid):
        row = next((row for row in self.accounts if row["id"] == aid), None)
        return dict(row) if row else None

    async def network_bindings(self, network_id):
        return [self._public_binding(value) for (nid, _), value in self.bindings.items()
                if nid == network_id]

    async def network_recent(self, network_id):
        return [{"slot": "2026-10-04 12:00", "status": "sent", "dest_msg_ids": [1],
                 "error": None}]

    async def save_network_settings(self, network_id, settings, accounts, target_changed=False):
        self.kv["network:" + network_id] = json.dumps(settings)
        self.saves.append((network_id, dict(settings), accounts, target_changed))
        if target_changed:
            for (nid, _), binding in self.bindings.items():
                if nid == network_id:
                    binding.update(due=False, claim_token=None, status="waiting", last_error=None)
        if accounts is not None:
            selected = set(accounts)
            for (nid, aid), binding in self.bindings.items():
                if nid == network_id and aid not in selected:
                    binding.update(enabled=False, claim_token=None)
            for aid in selected:
                binding = self.bindings.setdefault((network_id, aid), self._new_binding(network_id, aid))
                binding["enabled"] = True

    def bind(self, network_id, aid=ACCOUNT_ID, *, due=True, enabled=True):
        binding = self._new_binding(network_id, aid)
        binding.update(due=due, enabled=enabled)
        self.bindings[(network_id, aid)] = binding
        return binding

    @staticmethod
    def _new_binding(network_id, aid):
        return {"network_id": network_id, "account_id": aid, "enabled": True, "due": True,
                "claim_token": None, "status": "waiting", "last_error": None,
                "last_run_at": None, "next_run_at": "now"}

    @staticmethod
    def _public_binding(binding):
        return {key: value for key, value in binding.items()
                if key not in {"network_id", "claim_token", "due"}}

    async def network_due(self):
        return [{"network_id": nid, "id": aid} for (nid, aid), binding in self.bindings.items()
                if binding["enabled"] and binding["due"]]

    async def network_recover(self):
        return None

    async def network_claim(self, network_id, aid, token):
        binding = self.bindings.get((network_id, aid))
        if not binding or not binding["enabled"] or not binding["due"]:
            return False
        binding.update(due=False, claim_token=token, status="processing", last_error=None)
        if self.cancel_on_claim == (network_id, aid):
            binding["enabled"] = False
        return True

    async def network_claim_target(self, aid, resolved_target):
        key = (aid, str(resolved_target))
        if key in self.physical_claims:
            return False
        self.physical_claims.add(key)
        return True

    async def network_finish(self, network_id, aid, token, status, error=None, cooldown=0):
        binding = self.bindings[(network_id, aid)]
        if binding["claim_token"] != token:
            return
        binding.update(claim_token=None, status=status, last_error=error,
                       last_run_at="now", due=False)
        self.finishes.append((network_id, aid, status, error, cooldown))

    async def network_binding(self, network_id, aid):
        binding = self.bindings.get((network_id, aid))
        return dict(binding) if binding else None

    async def activity_reacted(self, aid, target, mid):
        return (aid, target, mid) in self.reacted

    async def mark_activity_reacted(self, aid, target, mid):
        self.reacted.add((aid, target, mid))


class FakeClient:
    def __init__(self, db=None, cancel_binding=None, fail=None, chosen=False, change_setting=None):
        self.db = db
        self.cancel_binding = cancel_binding
        self.fail = fail
        self.chosen = chosen
        self.change_setting = change_setting
        self.requests = []
        self.resolved = []
        self.connected = True

    def is_connected(self):
        return self.connected

    async def connect(self):
        self.connected = True

    async def is_user_authorized(self):
        return True

    async def get_entity(self, value):
        self.resolved.append(value)
        return SimpleNamespace(id=777)

    async def get_dialogs(self):
        return []

    async def get_messages(self, entity, limit, min_id=0):
        if self.fail:
            raise self.fail
        if self.cancel_binding:
            self.db.bindings[self.cancel_binding]["enabled"] = False
        if self.change_setting:
            network_id, partial = self.change_setting
            self.db.kv["network:" + network_id] = json.dumps(partial)
        chosen_order = 0 if self.chosen else None
        reactions = SimpleNamespace(results=[SimpleNamespace(chosen_order=chosen_order)]) if self.chosen else None
        messages = [SimpleNamespace(id=3, action=None, reactions=None),
                SimpleNamespace(id=2, action=None, reactions=None),
                SimpleNamespace(id=1, action=None, reactions=reactions)]
        return [message for message in messages if message.id > min_id]

    async def __call__(self, request):
        self.requests.append(request)
        return SimpleNamespace()


class NetworkValidationTests(unittest.IsolatedAsyncioTestCase):
    def test_weekly_defaults_preserve_custom_emoji_id_as_string(self):
        settings = defaults(cfg(), "weekly")
        self.assertEqual(settings["emoji_id"], "5462931610028510371")
        self.assertIsInstance(settings["emoji_id"], str)

    async def test_load_settings_merges_saved_partial_config_with_defaults(self):
        db = FakeNetworkDB()
        db.kv["network:weekly"] = json.dumps({"max_posts": 2})
        settings = await load_settings(db, cfg(), "weekly")
        self.assertEqual(settings["max_posts"], 2)
        self.assertEqual(settings["target_ref"], "@comics_komixy")

    def test_validate_settings_rejects_numeric_custom_emoji_id(self):
        current = defaults(cfg(), "weekly")
        with self.assertRaisesRegex(ValueError, "строка"):
            validate_settings(cfg(), "weekly", current, {"emoji_id": 5462931610028510371})

    def test_validate_settings_rejects_malformed_account_ids(self):
        current = defaults(cfg(), "promo")
        with self.assertRaisesRegex(ValueError, "уникальных ID"):
            validate_settings(cfg(), "promo", current, {"account_ids": ["not-an-account"]})

    def test_validate_settings_canonicalizes_username_references(self):
        current = defaults(cfg(), "promo")
        settings, _ = validate_settings(cfg(), "promo", current, {
            "source_ref": "https://t.me/anime_edit_videoo/",
        })
        self.assertEqual(settings["source_ref"], "@anime_edit_videoo")

    def test_validate_settings_rejects_equal_source_and_target(self):
        current = defaults(cfg(), "promo")
        with self.assertRaisesRegex(ValueError, "должны различаться"):
            validate_settings(cfg(), "promo", current, {
                "source_ref": "https://t.me/same_channel",
                "target_ref": "@same_channel",
            })


class NetworkServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_does_not_expose_account_session_path(self):
        db = FakeNetworkDB()
        result = await NetworkService(cfg(), db).list()
        self.assertNotIn("session_path", result["accounts"][0])
        self.assertNotIn("secret/session/path", json.dumps(result, ensure_ascii=False))

    async def test_update_rejects_account_id_missing_from_activity_accounts(self):
        db = FakeNetworkDB()
        with self.assertRaisesRegex(ValueError, "аккаунтов уже удалён"):
            await NetworkService(cfg(), db).update("promo", {"account_ids": ["b" * 32]})
        self.assertEqual(db.saves, [])

    async def test_update_merges_partial_config_and_persists_account_binding(self):
        db = FakeNetworkDB()
        result = await NetworkService(cfg(), db).update("weekly", {
            "max_posts": 2, "account_ids": [ACCOUNT_ID],
        })
        self.assertEqual(result["item"]["max_posts"], 2)
        self.assertEqual(result["item"]["emoji_id"], "5462931610028510371")
        self.assertTrue(db.bindings[("weekly", ACCOUNT_ID)]["enabled"])

    async def test_update_waits_for_shared_network_settings_lock(self):
        db = FakeNetworkDB()
        lock = asyncio.Lock()
        await lock.acquire()
        task = asyncio.create_task(NetworkService(cfg(), db, lock).update("promo", {"enabled": False}))
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        lock.release()
        result = await task
        self.assertFalse(result["item"]["enabled"])


class NetworkApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = FakeNetworkDB()
        worker = SimpleNamespace(db=self.db, cfg=cfg(), rt=SimpleNamespace(), activity=None)
        self.client = TestClient(TestServer(build_app(ApiContext(worker), "tok")))
        await self.client.start_server()
        self.headers = {"Authorization": "Bearer tok"}

    async def asyncTearDown(self):
        await self.client.close()

    async def test_network_routes_require_bearer_authentication(self):
        get_response = await self.client.get("/api/networks")
        put_response = await self.client.put("/api/networks/weekly", json={"max_posts": 2})
        self.assertEqual((get_response.status, put_response.status), (401, 401))

    async def test_get_networks_returns_both_workflows(self):
        response = await self.client.get("/api/networks", headers=self.headers)
        self.assertEqual(response.status, 200)
        self.assertEqual([item["id"] for item in (await response.json())["items"]], ["weekly", "promo"])

    async def test_put_weekly_saves_partial_configuration(self):
        response = await self.client.put("/api/networks/weekly", json={"max_posts": 2},
                                         headers=self.headers)
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["item"]["max_posts"], 2)

    async def test_put_promo_saves_account_binding(self):
        response = await self.client.put("/api/networks/promo", json={"account_ids": [ACCOUNT_ID]},
                                         headers=self.headers)
        self.assertEqual(response.status, 200)
        self.assertTrue(self.db.bindings[("promo", ACCOUNT_ID)]["enabled"])


class NetworkReactionTests(unittest.IsolatedAsyncioTestCase):
    def make_service(self, db, client):
        service = ActivityAccounts(cfg(), db, lambda *args, **kwargs: client)
        service.clients[ACCOUNT_ID] = client
        return service

    async def test_disabled_workflow_is_skipped_without_claiming_binding(self):
        db = FakeNetworkDB()
        binding = db.bind("promo")
        db.kv["network:promo"] = json.dumps({"enabled": False})
        client = FakeClient(db)
        await self.make_service(db, client).network_tick()
        self.assertIsNone(binding["claim_token"])
        self.assertTrue(binding["due"])

    async def test_persisted_claim_cooldown_prevents_immediate_send_after_restart(self):
        db = FakeNetworkDB()
        db.bind("promo")
        first_client = FakeClient(db)
        await self.make_service(db, first_client).network_tick()
        second_client = FakeClient(db)
        await self.make_service(db, second_client).network_tick()
        sent = [request for request in first_client.requests + second_client.requests
                if isinstance(request, functions.messages.SendReactionRequest)]
        self.assertEqual([request.msg_id for request in sent], [1, 2, 3])

    async def test_network_tick_reacts_to_every_unprocessed_post(self):
        db = FakeNetworkDB()
        db.bind("weekly")
        client = FakeClient(db)
        await self.make_service(db, client).network_tick()
        sent = [request for request in client.requests
                if isinstance(request, functions.messages.SendReactionRequest)]
        self.assertEqual([request.msg_id for request in sent], [1, 2, 3])

    async def test_network_tick_saves_receipt_for_resolved_target(self):
        db = FakeNetworkDB()
        db.bind("weekly")
        client = FakeClient(db)
        await self.make_service(db, client).network_tick()
        self.assertEqual(db.reacted, {(ACCOUNT_ID, "777", mid) for mid in (1, 2, 3)})

    async def test_weekly_binding_resolves_configured_target_channel(self):
        db = FakeNetworkDB()
        db.bind("weekly")
        client = FakeClient(db)
        await self.make_service(db, client).network_tick()
        self.assertEqual(client.resolved, ["comics_komixy"])

    async def test_promo_binding_resolves_configured_source_channel(self):
        db = FakeNetworkDB()
        db.bind("promo")
        client = FakeClient(db)
        await self.make_service(db, client).network_tick()
        self.assertEqual(client.resolved, ["anime_edit_videoo"])

    async def test_cancelled_binding_mid_operation_sends_no_reaction(self):
        db = FakeNetworkDB()
        key = ("weekly", ACCOUNT_ID)
        db.bind(*key)
        client = FakeClient(db, cancel_binding=key)
        await self.make_service(db, client).network_tick()
        sent = [request for request in client.requests
                if isinstance(request, functions.messages.SendReactionRequest)]
        self.assertEqual(sent, [])

    async def test_cancelled_binding_after_claim_is_checked_before_telegram_resolution(self):
        db = FakeNetworkDB()
        key = ("weekly", ACCOUNT_ID)
        db.bind(*key)
        db.cancel_on_claim = key
        client = FakeClient(db)
        await self.make_service(db, client).network_tick()
        self.assertEqual(client.resolved, [])

    async def test_two_workflows_resolving_same_peer_do_not_duplicate_batch(self):
        db = FakeNetworkDB()
        db.bind("weekly")
        db.bind("promo")
        client = FakeClient(db)
        await self.make_service(db, client).network_tick()
        sent = [request for request in client.requests
                if isinstance(request, functions.messages.SendReactionRequest)]
        self.assertEqual([request.msg_id for request in sent], [1, 2, 3])

    async def test_target_change_during_message_preparation_prevents_obsolete_send(self):
        db = FakeNetworkDB()
        db.bind("weekly")
        client = FakeClient(db, change_setting=("weekly", {"target_ref": "@changed_channel"}))
        await self.make_service(db, client).network_tick()
        sent = [request for request in client.requests
                if isinstance(request, functions.messages.SendReactionRequest)]
        self.assertEqual(sent, [])

    async def test_telegram_failure_is_persisted_as_binding_error(self):
        db = FakeNetworkDB()
        db.bind("promo")
        client = FakeClient(db, fail=RuntimeError("telegram down"))
        await self.make_service(db, client).network_tick()
        self.assertEqual(db.finishes[0][2], "error")
        self.assertIn("telegram down", db.finishes[0][3])

    async def test_existing_telegram_reaction_is_recorded_without_resending_it(self):
        db = FakeNetworkDB()
        db.bind("promo")
        client = FakeClient(db, chosen=True)
        await self.make_service(db, client).network_tick()
        sent = [request for request in client.requests
                if isinstance(request, functions.messages.SendReactionRequest)]
        self.assertEqual([request.msg_id for request in sent], [2, 3])
        self.assertIn((ACCOUNT_ID, "777", 1), db.reacted)

    async def test_cursor_fetches_all_new_posts_without_recent_limit(self):
        db = FakeNetworkDB()
        db.bind("weekly")
        db.kv["network_cursor:" + ACCOUNT_ID + ":777"] = "1"
        client = FakeClient(db)
        from unittest.mock import AsyncMock
        original = client.get_messages
        client.get_messages = AsyncMock(side_effect=original)
        await self.make_service(db, client).network_tick()
        client.get_messages.assert_awaited_once_with(unittest.mock.ANY, limit=None, min_id=1)
        self.assertEqual(db.kv["network_cursor:" + ACCOUNT_ID + ":777"], "3")

    async def test_failed_send_does_not_advance_cursor_past_confirmed_posts(self):
        db = FakeNetworkDB()
        db.bind("weekly")
        class FailSecond(FakeClient):
            async def __call__(self, request):
                if isinstance(request, functions.messages.SendReactionRequest) and request.msg_id == 2:
                    raise RuntimeError("send failed")
                return await super().__call__(request)
        client = FailSecond(db)
        await self.make_service(db, client).network_tick()
        self.assertEqual(db.kv.get("network_cursor:" + ACCOUNT_ID + ":777"), "1")
        self.assertEqual(db.reacted, {(ACCOUNT_ID, "777", 1)})


if __name__ == "__main__":
    unittest.main()
