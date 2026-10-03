import json
import unittest

from aiohttp.test_utils import TestClient, TestServer

from app.api import ApiContext, build_app
from app.settings import RuntimeSettings
from tests.fakes import FakeDB, FakeWorker, make_cfg


class AIProfileSettingsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = FakeDB()
        self.settings = RuntimeSettings(self.db, make_cfg(), ttl=0)

    async def test_profiles_are_isolated_and_view_selects_profile(self):
        await self.settings.update("ai", {
            "ai_secondary_base_url": "https://backup.example/v1",
            "ai_secondary_model": "backup-model",
            "ai_secondary_api_key": "backup-secret",
        })
        primary = await self.settings.view(profile=1)
        secondary = await self.settings.view(profile=2)
        self.assertEqual((primary.ai_base_url, primary.ai_model, primary.ai_api_key),
                         ("https://ai.example/v1", "test-model", "sk-abcdef123456"))
        self.assertEqual((secondary.ai_base_url, secondary.ai_model, secondary.ai_api_key),
                         ("https://backup.example/v1", "backup-model", "backup-secret"))
        await self.settings.update("ai", {"ai_active_profile": 2})
        self.assertEqual((await self.settings.view()).ai_model, "backup-model")
        public = await self.settings.api_view()
        self.assertNotIn("ai_api_key", public)
        self.assertNotIn("ai_secondary_api_key", public)


class AIProfileApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = FakeDB()
        self.worker = FakeWorker(self.db, make_cfg())
        self.client = TestClient(TestServer(build_app(ApiContext(self.worker), "tok")))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    def headers(self):
        return {"Authorization": "Bearer tok"}

    async def test_secondary_mask_preserve_clear_and_no_secret_leak(self):
        secret = "backup-secret-9876"
        r = await self.client.put("/api/ai", json={
            "ai_secondary_base_url": "https://backup.example/v1",
            "ai_secondary_model": "backup-model",
            "secondary_api_key": secret,
        }, headers=self.headers())
        self.assertEqual(r.status, 200)
        text = await r.text()
        self.assertNotIn(secret, text)
        data = json.loads(text)
        self.assertTrue(data["secondary_api_key_configured"])
        self.assertTrue(data["secondary_api_key"]["mask"].endswith("9876"))

        r = await self.client.put("/api/ai", json={
            "secondary_api_key": "   ", "ai_secondary_model": "backup-model-2",
        }, headers=self.headers())
        self.assertEqual(r.status, 200)
        self.assertEqual((await self.worker.rt.view(profile=2)).ai_api_key, secret)

        r = await self.client.put("/api/ai", json={"clear_secondary_api_key": True},
                                  headers=self.headers())
        self.assertEqual(r.status, 200)
        self.assertFalse((await r.json())["secondary_api_key_configured"])

    async def test_secondary_origin_guard_and_active_validation(self):
        await self.client.put("/api/ai", json={
            "ai_secondary_base_url": "https://backup.example/v1",
            "ai_secondary_model": "backup-model",
            "secondary_api_key": "backup-secret",
        }, headers=self.headers())
        r = await self.client.put("/api/ai", json={
            "ai_secondary_base_url": "https://attacker.example/v1",
        }, headers=self.headers())
        self.assertEqual(r.status, 400)
        self.assertEqual((await self.worker.rt.view(profile=2)).ai_base_url,
                         "https://backup.example/v1")

        other = FakeWorker(FakeDB(), make_cfg())
        c = TestClient(TestServer(build_app(ApiContext(other), "tok")))
        await c.start_server()
        try:
            r = await c.put("/api/ai", json={"ai_active_profile": 2}, headers=self.headers())
            self.assertEqual(r.status, 400)
        finally:
            await c.close()

    async def test_test_action_snapshots_profile_and_validates_payload(self):
        await self.client.put("/api/ai", json={
            "ai_secondary_base_url": "https://backup.example/v1",
            "ai_secondary_model": "backup-model",
            "secondary_api_key": "backup-secret",
        }, headers=self.headers())
        r = await self.client.post("/api/ai/test", json={
            "profile": 2, "text": " hello ", "post_id": 7,
        }, headers=self.headers())
        self.assertEqual(r.status, 202)
        action = self.db.actions[-1]
        self.assertEqual(action["payload"], {"profile": 2, "text": "hello", "post_id": 7})
        self.assertNotIn("secret", json.dumps(action))

        for payload in ({"profile": 3}, {"profile": True}, {"text": 7},
                        {"post_id": 0}, {"post_id": "7"}):
            with self.subTest(payload=payload):
                r = await self.client.post("/api/ai/test", json=payload, headers=self.headers())
                self.assertEqual(r.status, 400)

    async def test_legacy_empty_test_uses_active_profile_snapshot(self):
        r = await self.client.post("/api/ai/test", json={}, headers=self.headers())
        self.assertEqual(r.status, 202)
        self.assertEqual(self.db.actions[-1]["payload"], {"profile": 1, "text": ""})


if __name__ == "__main__":
    unittest.main()
