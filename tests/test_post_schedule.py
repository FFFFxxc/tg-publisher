import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import AsyncMock
from types import SimpleNamespace
from aiohttp.test_utils import TestClient,TestServer
from app.api import ApiContext,build_app
from app.worker import Worker
from app.db import DB
from tests.fakes import FakeDB,make_cfg,make_post
class ScheduleTests(unittest.IsolatedAsyncioTestCase):
 async def test_due_schedule_independent_of_slots(self):
  post=SimpleNamespace(id=5);db=FakeDB(); db.claim_scheduled=AsyncMock(return_value=post); w=Worker(make_cfg(),db,None); w._run=AsyncMock()
  await w.scheduled_tick(); w._run.assert_awaited_once_with(post)
 async def test_pause_preserved(self):
  db=FakeDB();await db.kv_set('rt:publishing_paused','true');db.claim_scheduled=AsyncMock();w=Worker(make_cfg(),db,None)
  await w.scheduled_tick();db.claim_scheduled.assert_not_awaited()
 async def test_atomic_claim_and_normal_pick_exclusion(self):
  db=object.__new__(DB);db._q=AsyncMock(return_value=[])
  await db.claim_scheduled();sql=db._q.call_args.args[0]
  for term in ('scheduled_at <= now()', 'SKIP LOCKED', 'cardinality(dest_msg_ids)=0', 'next_attempt_at'):
   self.assertIn(term,sql)
  await db.claim_retry();self.assertIn('scheduled_at IS NULL',db._q.call_args.args[0])
  await db.claim_best_candidate(1,100,7,0);self.assertIn('scheduled_at IS NULL',db._q.call_args.args[0])
  await db.expire_old(48);self.assertIn('scheduled_at IS NULL',db._q.call_args.args[0])
 async def test_schedule_update_guard(self):
  db=object.__new__(DB);db._q=AsyncMock(return_value=[{'id':5}]);at=datetime.now(timezone.utc)+timedelta(hours=2)
  self.assertTrue(await db.set_post_schedule(5,at));sql,args=db._q.call_args.args
  self.assertIn('cardinality(dest_msg_ids)=0',sql);self.assertIn("'candidate','pending','failed','expired'",sql)
  self.assertEqual(args,(at,5))
class ScheduleApiTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.db=FakeDB();self.db.posts=[make_post(5)];self.db.set_post_schedule=AsyncMock(return_value=True)
  self.w=Worker(make_cfg(),self.db,None);self.c=TestClient(TestServer(build_app(ApiContext(self.w),'tok')));await self.c.start_server()
 async def asyncTearDown(self):await self.c.close()
 async def send(self,data,auth=True):return await self.c.put('/api/posts/5/schedule',json=data,headers={'Authorization':'Bearer tok'} if auth else {})
 async def test_valid_moscow_time_and_cancel(self):
  at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
  r=await self.send({'scheduled_at':at});self.assertEqual(r.status,200);self.assertEqual(self.db.set_post_schedule.call_args.args[1],datetime.fromisoformat(at))
  r=await self.send({'scheduled_at':None});self.assertEqual(r.status,200);self.assertIsNone(self.db.set_post_schedule.call_args.args[1])
 async def test_past_naive_invalid_rejected(self):
  for value in ('yesterday','2020-01-01T10:00:00+03:00','2030-01-01T10:00',True):
   self.assertEqual((await self.send({'scheduled_at':value})).status,400)
 async def test_auth_and_missing_and_conflict(self):
  self.assertEqual((await self.send({'scheduled_at':None},False)).status,401)
  self.db.set_post_schedule.return_value=False;self.assertEqual((await self.send({'scheduled_at':None})).status,409)
  self.db.posts=[];self.assertEqual((await self.send({'scheduled_at':None})).status,404)
