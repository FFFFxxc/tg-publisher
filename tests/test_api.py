import json
import unittest

from aiohttp.test_utils import TestClient, TestServer

from app.api import ApiContext, build_app
from tests.fakes import PROXY, FakeDB, FakeWorker, make_cfg, make_post


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = FakeDB()
        self.db.sources = [
            {"id": 1, "ref": "@src1", "role": "source", "enabled": True, "title": "Src1",
             "last_message_id": 10, "last_error": None},
            {"id": 2, "ref": "@src2", "role": "source", "enabled": False, "title": None,
             "last_message_id": None, "last_error": "boom"},
        ]
        self.db.posts = [make_post(1, "candidate"), make_post(2, "failed"),
                         make_post(3, "published", dest=[9])]
        self.cfg = make_cfg(proxy=PROXY)
        self.w = FakeWorker(self.db, self.cfg)
        self.client = TestClient(TestServer(build_app(ApiContext(self.w), "tok")))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    def _h(self, **kw):
        return {"Authorization": "Bearer tok", **kw}

    # ---------- auth ----------
    async def test_auth_required(self):
        r = await self.client.get("/api/overview")
        self.assertEqual(r.status, 401)
        r = await self.client.get("/api/overview", headers={"Authorization": "Bearer wrong"})
        self.assertEqual(r.status, 401)

    async def test_overview_ok(self):
        r = await self.client.get("/api/overview", headers=self._h())
        self.assertEqual(r.status, 200)
        data = await r.json()
        self.assertTrue(data["worker"]["online"])
        self.assertEqual(data["worker"]["transport"], "socks5")
        self.assertTrue(data["db"]["ok"])
        self.assertEqual(data["queue"].get("candidate"), 1)
        self.assertEqual(data["schedule"]["pattern"], ["parsed", "old"])
        self.assertIn("next_slot", data["schedule"])

    # ---------- posts ----------
    async def test_posts_filters_and_paging(self):
        r = await self.client.get("/api/posts", params={"status": "failed", "limit": "500"},
                                  headers=self._h())
        self.assertEqual(r.status, 200)
        data = await r.json()
        self.assertEqual(data["limit"], 100)   # clamp
        self.assertEqual(self.db.last_posts_filters["status"], "failed")
        r = await self.client.get("/api/posts", params={"status": "wat"}, headers=self._h())
        self.assertEqual(r.status, 400)

    async def test_post_detail_404(self):
        r = await self.client.get("/api/posts/999", headers=self._h())
        self.assertEqual(r.status, 404)

    # ---------- sources ----------
    async def test_source_add_creates_action(self):
        r = await self.client.post("/api/sources", json={"ref": "@newsrc"}, headers=self._h())
        self.assertEqual(r.status, 202)
        data = await r.json()
        a = await self.db.get_action(data["action_id"])
        self.assertEqual(a["kind"], "add_source")
        r = await self.client.post("/api/sources", json={}, headers=self._h())
        self.assertEqual(r.status, 400)

    async def test_source_patch_toggle(self):
        r = await self.client.patch("/api/sources/2", json={"enabled": True}, headers=self._h())
        self.assertEqual(r.status, 200)
        self.assertTrue((await self.db.get_source(2))["enabled"])
        r = await self.client.patch("/api/sources/999", json={"enabled": True}, headers=self._h())
        self.assertEqual(r.status, 404)
        r = await self.client.patch("/api/sources/2", json={"enabled": "yes"}, headers=self._h())
        self.assertEqual(r.status, 400)

    async def test_source_delete_fallback_disable(self):
        self.db.sources[0]["has_posts"] = True   # FK-конфликт
        r = await self.client.delete("/api/sources/1", headers=self._h())
        self.assertEqual(r.status, 200)
        data = await r.json()
        self.assertFalse(data["deleted"])
        self.assertTrue(data["disabled"])
        self.assertFalse((await self.db.get_source(1))["enabled"])

    # ---------- AI ----------
    async def test_ai_secret_never_leaks(self):
        r = await self.client.get("/api/ai", headers=self._h())
        self.assertEqual(r.status, 200)
        body = await r.text()
        self.assertNotIn("sk-abcdef123456", body)
        data = json.loads(body)
        self.assertTrue(data["api_key_configured"])
        self.assertTrue(data["api_key"]["configured"])
        self.assertTrue(data["api_key"]["mask"].endswith("3456"))
        self.assertFalse(data["api_key_env_only"])

    async def test_ai_key_model_and_endpoint_are_settable_without_leaking_secret(self):
        secret = "sk-new-secret-4321"
        r = await self.client.put("/api/ai", json={
            "api_key": secret,
            "ai_enabled": True,
            "ai_base_url": "https://new-ai.example/v1",
            "ai_model": "new-model",
        }, headers=self._h())
        self.assertEqual(r.status, 200)
        body = await r.text()
        self.assertNotIn(secret, body)
        self.assertEqual(await self.w.rt.get("ai_model"), "new-model")
        runtime = await self.w.rt.view()
        self.assertEqual(runtime.ai_api_key, secret)
        self.assertTrue(runtime.ai_enabled)
        self.assertEqual(runtime.ai_base_url, "https://new-ai.example/v1")
        self.assertNotIn(secret, json.dumps(self.db.events))

    async def test_provider_change_cannot_reuse_hidden_key(self):
        r = await self.client.put("/api/ai", json={"ai_base_url": "https://other.example/v1"},
                                  headers=self._h())
        self.assertEqual(r.status, 400)
        runtime = await self.w.rt.view()
        self.assertEqual(runtime.ai_base_url, "https://ai.example/v1")
        self.assertEqual(runtime.ai_api_key, self.cfg.ai_api_key)

    async def test_ai_blank_key_keeps_current_and_explicit_clear_removes_it(self):
        await self.client.put("/api/ai", json={"api_key": "sk-runtime-1234", "ai_model": "m1"},
                              headers=self._h())
        r = await self.client.put("/api/ai", json={"api_key": "  ", "ai_model": "m2"},
                                  headers=self._h())
        self.assertEqual(r.status, 200)
        self.assertEqual((await self.w.rt.view()).ai_api_key, "sk-runtime-1234")

        r = await self.client.put("/api/ai", json={"clear_api_key": True}, headers=self._h())
        self.assertEqual(r.status, 200)
        data = await r.json()
        self.assertFalse(data["api_key_configured"])
        self.assertEqual((await self.w.rt.view()).ai_api_key, "")

    async def test_ai_rejects_setting_and_clearing_key_together_without_echo(self):
        secret = "sk-do-not-echo-1234"
        r = await self.client.put("/api/ai", json={"api_key": secret, "clear_api_key": True},
                                  headers=self._h())
        self.assertEqual(r.status, 400)
        self.assertNotIn(secret, await r.text())

        oversized = "s" * 4097
        r = await self.client.put("/api/ai", json={"api_key": oversized}, headers=self._h())
        self.assertEqual(r.status, 400)
        self.assertNotIn(oversized, await r.text())

    async def test_settings_endpoint_never_contains_ai_secret(self):
        secret = "sk-settings-secret-1234"
        await self.client.put("/api/ai", json={"api_key": secret, "ai_model": "m"}, headers=self._h())
        r = await self.client.get("/api/settings", headers=self._h())
        self.assertEqual(r.status, 200)
        self.assertNotIn(secret, await r.text())

    async def test_footer_emoji_ids_are_strings_in_settings_and_schedule(self):
        expected = ["5256105385420412669", "5195160091547942599"]
        r = await self.client.get("/api/settings", headers=self._h())
        self.assertEqual(r.status, 200)
        self.assertEqual([x["emoji_id"] for x in (await r.json())["footer"]], expected)

        r = await self.client.get("/api/schedule", headers=self._h())
        self.assertEqual(r.status, 200)
        self.assertEqual([x["emoji_id"] for x in (await r.json())["settings"]["footer"]], expected)

    async def test_footer_put_roundtrip_preserves_full_emoji_id(self):
        exact = "5256105385420412669"
        footer = [{"emoji": "👀", "emoji_id": exact, "text": "Тест", "url": "https://t.me/test"}]
        r = await self.client.put("/api/settings", json={"footer": footer}, headers=self._h())
        self.assertEqual(r.status, 200)
        self.assertEqual((await r.json())["footer"][0]["emoji_id"], exact)
        self.assertEqual((await self.w.rt.get("footer"))[0]["emoji_id"], int(exact))

    async def test_footer_put_rejects_js_unsafe_numeric_emoji_id(self):
        rounded = 5256105385420413000
        footer = [{"emoji": "👀", "emoji_id": rounded, "text": "Тест", "url": ""}]
        r = await self.client.put("/api/settings", json={"footer": footer}, headers=self._h())
        self.assertEqual(r.status, 400)
        self.assertNotIn(str(rounded), await r.text())

    # ---------- schedule ----------
    async def test_schedule_roundtrip(self):
        r = await self.client.put("/api/schedule", json={"tz_name": "UTC", "publishing_paused": True},
                                  headers=self._h())
        self.assertEqual(r.status, 200)
        self.assertEqual(await self.w.rt.get("tz_name"), "UTC")
        r = await self.client.get("/api/schedule", headers=self._h())
        data = await r.json()
        self.assertTrue(data["settings"]["publishing_paused"])
        self.assertIn("next_slot", data)

    async def test_schedule_bad_tz(self):
        r = await self.client.put("/api/schedule", json={"tz_name": "Mars/Olympus"}, headers=self._h())
        self.assertEqual(r.status, 400)
        self.assertIn("tz_name", (await r.json())["error"])

    # ---------- actions / events ----------
    async def test_action_visibility(self):
        aid = await self.db.create_action("skip_post", {"post_id": 1}, post_id=1)
        r = await self.client.get(f"/api/actions/{aid}", headers=self._h())
        self.assertEqual(r.status, 200)
        r = await self.client.get("/api/actions/unknown-id", headers=self._h())
        self.assertEqual(r.status, 404)

    async def test_events_endpoint(self):
        await self.db.add_event("publish_failed", level="error", post_id=2, message="boom")
        r = await self.client.get("/api/events", params={"level": "error"}, headers=self._h())
        self.assertEqual(r.status, 200)
        data = await r.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["type"], "publish_failed")


if __name__ == "__main__":
    unittest.main()
