import json
import unittest
from datetime import time

from app.settings import RuntimeSettings, SettingsError
from tests.fakes import FakeDB, make_cfg


class SettingsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = FakeDB()
        self.s = RuntimeSettings(self.db, make_cfg(), ttl=0)

    async def test_env_defaults(self):
        v = await self.s.view()
        self.assertEqual(v.publish_times, [time(9), time(12)])
        self.assertEqual(v.tz_name, "Europe/Moscow")
        self.assertEqual(v.schedule_pattern, ["parsed", "old"])
        self.assertFalse(v.publishing_paused)
        self.assertEqual(v.ai_api_key, "sk-abcdef123456")

    async def test_db_override_wins_over_env(self):
        await self.db.kv_set("rt:tz_name", json.dumps("UTC"))
        self.assertEqual(await self.s.get("tz_name"), "UTC")
        self.assertEqual((await self.s.view()).tz_name, "UTC")

    async def test_ttl_cache(self):
        s = RuntimeSettings(self.db, make_cfg(), ttl=60)
        self.assertEqual(await s.get("tz_name"), "Europe/Moscow")   # первое чтение формирует кэш
        await self.db.kv_set("rt:tz_name", json.dumps("UTC"))
        self.assertEqual(await s.get("tz_name"), "Europe/Moscow")   # ещё живёт кэш
        s.invalidate()
        self.assertEqual(await s.get("tz_name"), "UTC")

    async def test_update_validates_and_stores(self):
        cleaned = await self.s.update("schedule", {"tz_name": "UTC", "publishing_paused": True})
        self.assertEqual(cleaned["tz_name"], "UTC")
        self.assertTrue(cleaned["publishing_paused"])
        self.assertEqual(json.loads(self.db.kv["rt:tz_name"]), "UTC")
        self.assertTrue(await self.s.get("publishing_paused"))

    async def test_update_times_and_pattern(self):
        cleaned = await self.s.update("schedule", {"publish_times": ["10:30", "22:00"],
                                                   "schedule_pattern": "old,parsed"})
        self.assertEqual(cleaned["publish_times"], ["10:30", "22:00"])
        self.assertEqual(cleaned["schedule_pattern"], ["old", "parsed"])
        self.assertEqual((await self.s.view()).publish_times, [time(10, 30), time(22, 0)])

    async def test_validation_errors(self):
        cases = [
            ("schedule", {"tz_name": "Nope/Nope"}),
            ("schedule", {"best_min_score": "abc"}),
            ("schedule", {"collect_interval": 1}),
            ("schedule", {"max_post_age_hours": 0}),
            ("schedule", {"unknown_key": 1}),
            ("ai", {"ai_timeout": 0}),
            ("ai", {"ai_base_url": "ftp://x"}),
            ("footer", {"footer": []}),
            ("footer", {"footer": [{"text": ""}]}),
            ("wat", {"x": 1}),
            ("schedule", {}),
        ]
        for section, values in cases:
            with self.assertRaises(SettingsError, msg=f"{section} {values}"):
                await self.s.update(section, values)

    async def test_api_key_override_wins_over_env_and_can_be_cleared(self):
        await self.s.update("ai", {"ai_api_key": "sk-runtime-987654"})
        self.assertEqual((await self.s.view()).ai_api_key, "sk-runtime-987654")

        await self.s.update("ai", {"ai_api_key": ""})
        self.assertEqual((await self.s.view()).ai_api_key, "")

    async def test_api_key_validation_never_echoes_secret(self):
        secret = "s" * 4097
        with self.assertRaises(SettingsError) as caught:
            await self.s.update("ai", {"ai_api_key": secret})
        self.assertNotIn(secret, str(caught.exception))

    async def test_api_view_json_safe_without_key(self):
        await self.s.update("schedule", {"publish_times": ["08:15"]})
        v = await self.s.api_view()
        self.assertEqual(v["publish_times"], ["08:15"])
        self.assertNotIn("ai_api_key", v)
        self.assertEqual(
            [item["emoji_id"] for item in v["footer"]],
            ["5256105385420412669", "5195160091547942599"],
        )

    async def test_footer_string_id_roundtrip_keeps_exact_internal_integer(self):
        exact = "5256105385420412669"
        cleaned = await self.s.update("footer", {"footer": [
            {"emoji": "👀", "emoji_id": exact, "text": "Тест", "url": "https://t.me/test"},
        ]})
        self.assertEqual(cleaned["footer"][0]["emoji_id"], int(exact))
        self.assertEqual((await self.s.get("footer"))[0]["emoji_id"], int(exact))
        self.assertEqual((await self.s.api_view())["footer"][0]["emoji_id"], exact)

    async def test_footer_rejects_lossy_or_out_of_range_emoji_ids(self):
        invalid_ids = [1.5, 5256105385420413000, str(2 ** 63), True]
        for emoji_id in invalid_ids:
            with self.subTest(emoji_id=emoji_id), self.assertRaises(SettingsError):
                await self.s.update("footer", {"footer": [
                    {"emoji": "👀", "emoji_id": emoji_id, "text": "Тест", "url": ""},
                ]})

    async def test_pause_toggle(self):
        await self.s.update("schedule", {"publishing_paused": True})
        self.assertTrue((await self.s.view()).publishing_paused)
        await self.s.update("schedule", {"publishing_paused": False})
        self.assertFalse((await self.s.view()).publishing_paused)


if __name__ == "__main__":
    unittest.main()
