import unittest

from app.actions import dispatch
from app.worker import Worker
from tests.fakes import FakeDB, FakeWorker, make_cfg, make_post


class ActionDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = FakeDB()
        self.db.posts = [make_post(1, "failed"), make_post(2, "published", dest=[55]),
                         make_post(3, "candidate")]
        self.w = FakeWorker(self.db, make_cfg())

    async def test_unknown_kind_rejected(self):
        with self.assertRaises(ValueError):
            await dispatch(self.w, "wat", {})

    async def test_payload_must_be_object(self):
        with self.assertRaises(ValueError):
            await dispatch(self.w, "scan_own", [1, 2])

    async def test_requeue_ok(self):
        r = await dispatch(self.w, "requeue_post", {"post_id": 1})
        self.assertTrue(r["requeued"])
        self.assertEqual((await self.db.get_post(1))["status"], "pending")

    async def test_requeue_never_when_dest_confirmed(self):
        # главное правило: подтверждённая отправка (dest_msg_ids) не ретраится
        self.db.posts = [make_post(4, "failed", dest=[77]), make_post(5, "ambiguous", dest=[78])]
        for pid in (4, 5):
            with self.assertRaises(ValueError, msg=f"post {pid}"):
                await dispatch(self.w, "requeue_post", {"post_id": pid})
        self.assertEqual((await self.db.get_post(4))["status"], "failed")

    async def test_skip(self):
        r = await dispatch(self.w, "skip_post", {"post_id": 3})
        self.assertTrue(r["skipped"])
        self.assertEqual((await self.db.get_post(3))["status"], "skipped")

    async def test_skip_rejected_for_published(self):
        with self.assertRaises(ValueError):
            await dispatch(self.w, "skip_post", {"post_id": 2})

    async def test_publish_now_idempotent_for_already_published(self):
        r = await dispatch(self.w, "publish_now", {"post_id": 2})
        self.assertEqual(r["status"], "already_published")
        self.assertEqual(self.w.ran, [])

    async def test_publish_now_runs_same_pipeline(self):
        r = await dispatch(self.w, "publish_now", {"post_id": 3})
        self.assertEqual(self.w.ran, [3])   # прошёл через worker._run, а не прямой send

    async def test_publish_now_rejects_processing(self):
        self.db.posts = [make_post(5, "processing")]
        with self.assertRaises(ValueError):
            await dispatch(self.w, "publish_now", {"post_id": 5})

    async def test_generate_ai_only_for_parsed(self):
        self.db.posts = [make_post(6, "candidate", kind="repost")]
        with self.assertRaises(ValueError):
            await dispatch(self.w, "generate_ai", {"post_id": 6})

    async def test_generate_ai_disabled(self):
        await self.db.kv_set("rt:ai_enabled", "false")
        with self.assertRaises(ValueError):
            await dispatch(self.w, "generate_ai", {"post_id": 1})

    async def test_repost_own_dupe_guard(self):
        self.db.own = [{"group_key": "k1", "msg_ids": [10], "post_date": "now", "text": "t", "reactions": 3}]
        self.db.posts = [make_post(7, "published", dest=[10], kind="repost")]
        with self.assertRaises(ValueError):
            await dispatch(self.w, "repost_own", {"group_key": "k1"})

    async def test_repost_own_goes_through_pipeline(self):
        self.db.own = [{"group_key": "k2", "msg_ids": [11], "post_date": "now", "text": "t", "reactions": 3}]
        r = await dispatch(self.w, "repost_own", {"group_key": "k2"})
        self.assertEqual(self.w.ran, [r["post_id"]])

    async def test_scan_own(self):
        await dispatch(self.w, "scan_own", {})
        self.assertEqual(self.w.scan_calls, 1)

    async def test_add_source_requires_ref(self):
        with self.assertRaises(ValueError):
            await dispatch(self.w, "add_source", {})


class ActionLoopTests(unittest.IsolatedAsyncioTestCase):
    """Цикл воркера забирает actions атомарно и не оставляет их висеть."""

    async def asyncSetUp(self):
        self.db = FakeDB()
        self.w = Worker(make_cfg(), self.db, None)   # реальный Worker, сеть не нужна

    async def test_pending_action_completes(self):
        self.db.posts = [make_post(1, "failed")]
        aid = await self.db.create_action("requeue_post", {"post_id": 1}, post_id=1)
        await self.w.actions_tick()
        a = await self.db.get_action(aid)
        self.assertEqual(a["status"], "completed")
        self.assertTrue(a["result"]["requeued"])
        self.assertIn("action_completed", [e["type"] for e in self.db.events])

    async def test_unknown_action_marked_failed(self):
        aid = await self.db.create_action("wat", {})
        await self.w.actions_tick()
        a = await self.db.get_action(aid)
        self.assertEqual(a["status"], "failed")
        self.assertIn("action_failed", [e["type"] for e in self.db.events])

    async def test_stale_processing_recovered(self):
        aid = await self.db.create_action("scan_own", {})
        a = await self.db.get_action(aid)
        a["status"], a["claimed_at"] = "processing", 0.0   # заявлено «древним» процессом
        await self.w.actions_tick()
        a = await self.db.get_action(aid)
        self.assertEqual(a["status"], "failed")
        self.assertIn("stale", a["error"])


if __name__ == "__main__":
    unittest.main()
