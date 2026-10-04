import time
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiohttp.test_utils import TestClient, TestServer

from app.api import ApiContext, build_app
from app.db import DB
from app.logic import Post
from app.worker import Worker
from tests.fakes import FakeDB, FakeWorker, make_cfg


class OverviewDB(FakeDB):
    def __init__(self):
        super().__init__()
        self.replaced = None

    async def overview_queue_funnel(self):
        return {"found": 9, "ready": 4, "published": 5}

    async def overview_chart_7d(self, tz_name):
        return [{"date": "2026-10-04", "published": 2, "reactions": 7}]

    async def overview_last_problem(self):
        return {"id": 9, "type": "action_failed", "level": "error", "message": "generate_ai",
                "post_id": 42, "source_id": 1, "created_at": "2026-10-04T10:00:00+00:00",
                "post_status": "candidate", "ai_status": "failed", "dest_msg_ids": [],
                "send_started_at": None, "source_ref": "@src", "action_kind": "generate_ai",
                "action_error": None, "metadata": {"error": "AIError: лимит модели"}}

    async def overview_next_post(self, planned, rt, next_slot):
        return {"id": 42, "kind": "parsed", "group_key": "g42", "text": "текст",
                "score": 1.73, "media_type": "photo", "source_ref": "@src",
                "source_title": "Источник", "scheduled_at": None, "selection": "ranking"}

    async def post_scores(self, ids, baseline_days):
        return {pid: {"score": 1.4, "er": .1, "avg_er": .08,
                      "views": 100, "avg_views": 80} for pid in ids}

    async def replace_overview_next_post(self, kind, current, rt):
        self.replaced = (kind, current)
        return {"id": 43, "kind": kind, "group_key": "g43", "text": "другой",
                "score": 1.5, "media_type": "video", "source_ref": "@src",
                "source_title": "Источник", "scheduled_at": None, "selection": "override"}


class OverviewUxApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = OverviewDB()
        self.w = FakeWorker(self.db, make_cfg())
        self.w.heartbeat["collect"] = time.time() - 1000
        self.w.dest = SimpleNamespace(title="Закрытая группа", photo=object())
        self.w.client.download_profile_photo = AsyncMock(return_value=b"jpeg")
        self.client = TestClient(TestServer(build_app(ApiContext(self.w), "token")))
        await self.client.start_server()
        self.h = {"Authorization": "Bearer token"}

    async def asyncTearDown(self):
        await self.client.close()

    async def test_overview_exposes_truthful_homepage_contract(self):
        r = await self.client.get("/api/overview", headers=self.h)
        self.assertEqual(r.status, 200)
        d = await r.json()
        self.assertEqual(d["destination"]["title"], "Закрытая группа")
        self.assertEqual(d["queue_funnel"], {"found": 9, "ready": 4, "published": 5})
        self.assertEqual(d["next_post"]["id"], 42)
        self.assertEqual(d["next_post"]["score"], 1.73)
        self.assertEqual(d["last_error"]["post_url"], "/queue/42")
        self.assertTrue(d["last_error"]["retryable"])
        self.assertEqual(d["last_error"]["message"], "AIError: лимит модели")
        self.assertEqual(d["last_error"]["retry_path"], "posts/42/ai")
        self.assertEqual(d["last_error"]["retry_body"], {"force": True})
        collect = next(p for p in d["worker"]["processes"] if p["id"] == "collect")
        self.assertEqual(collect["label"], "Сбор постов")
        self.assertEqual(collect["state"], "red")
        self.assertEqual(d["chart_7d"][0]["reactions"], 7)

    async def test_replace_persists_validated_choice(self):
        r = await self.client.post("/api/overview/next-post/replace",
                                   json={"kind": "parsed", "current": 42}, headers=self.h)
        self.assertEqual(r.status, 200)
        self.assertEqual((await r.json())["next_post"]["id"], 43)
        self.assertEqual(self.db.replaced, ("parsed", 42))
        bad = await self.client.post("/api/overview/next-post/replace",
                                     json={"kind": "parsed", "current": "42"}, headers=self.h)
        self.assertEqual(bad.status, 400)

    async def test_ambiguous_send_never_offers_one_click_repeat(self):
        original = self.db.overview_last_problem
        async def problem():
            row = await original()
            row.update(post_status="ambiguous", action_kind="publish", message="send failed",
                       metadata={}, send_started_at="2026-10-04T10:00:00+00:00")
            return row
        self.db.overview_last_problem = problem
        r = await self.client.get("/api/overview", headers=self.h)
        self.assertEqual(r.status, 200)
        last = (await r.json())["last_error"]
        self.assertFalse(last["retryable"])
        self.assertIsNone(last["retry_path"])

    async def test_replace_rejects_retry_that_precedes_ranked_candidate(self):
        original = self.db.overview_next_post
        async def retry_first(*args):
            return {"id": 99, "kind": "parsed", "selection": "retry"}
        self.db.overview_next_post = retry_first
        r = await self.client.post("/api/overview/next-post/replace",
                                   json={"kind": "parsed", "current": 42}, headers=self.h)
        self.assertEqual(r.status, 400)
        self.db.overview_next_post = original

    async def test_destination_avatar_is_authenticated_and_cached(self):
        self.assertEqual((await self.client.get("/api/overview/destination-avatar")).status, 401)
        r = await self.client.get("/api/overview/destination-avatar", headers=self.h)
        self.assertEqual(r.status, 200)
        self.assertEqual(await r.read(), b"jpeg")
        await self.client.get("/api/overview/destination-avatar", headers=self.h)
        self.w.client.download_profile_photo.assert_awaited_once()

    async def test_queue_candidates_receive_current_computed_score(self):
        from tests.fakes import make_post
        self.db.posts = [make_post(5, "candidate")]
        r = await self.client.get("/api/posts", headers=self.h)
        self.assertEqual(r.status, 200)
        post = (await r.json())["items"][0]
        self.assertEqual(post["score"], 1.4)
        self.assertEqual(post["avg_views"], 80)


class NextPostOrderDB:
    overview_next_post = DB.overview_next_post

    def __init__(self, scheduled_at, retry_at):
        self.scheduled_at, self.retry_at = scheduled_at, retry_at

    async def _q(self, sql, args=()):
        if "p.status='pending'" in sql:
            return [{"id": 2, "kind": "parsed", "due_at": self.retry_at}]
        if "p.scheduled_at IS NOT NULL" in sql:
            return ([{"id": 1, "kind": "parsed", "scheduled_at": self.scheduled_at}]
                    if args[0] is None or self.scheduled_at <= args[0] else [])
        raise AssertionError(sql)


class NextPostOrderingTests(unittest.IsolatedAsyncioTestCase):
    async def test_manual_schedule_before_retry_wins(self):
        slot = datetime(2026, 10, 4, 14, tzinfo=timezone.utc)
        db = NextPostOrderDB(datetime(2026, 10, 4, 11, tzinfo=timezone.utc),
                             datetime(2026, 10, 4, 12, tzinfo=timezone.utc))
        row = await db.overview_next_post("parsed", SimpleNamespace(), slot)
        self.assertEqual(row["id"], 1)
        self.assertEqual(row["selection"], "scheduled")

    async def test_retry_due_earlier_still_waits_for_regular_slot(self):
        slot = datetime(2026, 10, 4, 14, tzinfo=timezone.utc)
        db = NextPostOrderDB(datetime(2026, 10, 4, 13, tzinfo=timezone.utc),
                             datetime(2026, 10, 4, 12, tzinfo=timezone.utc))
        row = await db.overview_next_post("parsed", SimpleNamespace(), slot)
        self.assertEqual(row["id"], 1)
        self.assertEqual(row["selection"], "scheduled")

    async def test_retry_wins_when_manual_schedule_is_after_regular_slot(self):
        slot = datetime(2026, 10, 4, 14, tzinfo=timezone.utc)
        db = NextPostOrderDB(datetime(2026, 10, 4, 15, tzinfo=timezone.utc),
                             datetime(2026, 10, 4, 12, tzinfo=timezone.utc))
        row = await db.overview_next_post("parsed", SimpleNamespace(), slot)
        self.assertEqual(row["id"], 2)
        self.assertEqual(row["selection"], "retry")


class OverrideWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_pick_prefers_persistent_override(self):
        selected = Post(id=7, kind="parsed", source_id=1, source_ref="@s",
                        source_msg_ids=[1], text="x", ai_status="unchecked",
                        ai_caption=None, attempts=0)
        db = SimpleNamespace(claim_overview_override=AsyncMock(return_value=selected),
                             claim_best_candidate=AsyncMock())
        w = object.__new__(Worker)
        w.db = db
        w.refresh_stats = AsyncMock()
        w._own_sid = AsyncMock(return_value=99)
        rt = SimpleNamespace(candidate_min_age_min=1, max_post_age_hours=48,
                             baseline_days=7, best_min_score=0.1)
        got = await w._pick("parsed", rt)
        self.assertIs(got, selected)
        db.claim_best_candidate.assert_not_awaited()
        db.claim_overview_override.assert_awaited_once_with("parsed", rt, None)


if __name__ == "__main__":
    unittest.main()
