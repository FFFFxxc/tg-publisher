import unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from datetime import datetime,timedelta,timezone
from aiohttp.test_utils import TestClient,TestServer
from app.api import ApiContext,build_app
from app.actions import h_repost_own
from app.db import DB
from tests.fakes import FakeDB,FakeWorker,make_cfg,PROXY

class ArchiveTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.db=FakeDB();self.cfg=make_cfg(proxy=PROXY);self.w=FakeWorker(self.db,self.cfg)
  self.db.get_own=AsyncMock(return_value={'msg_ids':[10,11]})
  self.w.previews=SimpleNamespace(get=AsyncMock(return_value=None))
  self.client=TestClient(TestServer(build_app(ApiContext(self.w),'tok')));await self.client.start_server()
 async def asyncTearDown(self):await self.client.close()
 def headers(self):return {'Authorization':'Bearer tok'}
 async def test_preview_existing_client_namespace(self):
  r=await self.client.get('/api/own/preview?group_key=album:10',headers=self.headers());self.assertEqual(r.status,204)
  args=self.w.previews.get.call_args
  self.assertTrue(args.args[0].startswith('own_'));self.assertNotIn(':',args.args[0]);self.assertEqual(args.kwargs,{'source_ref':self.cfg.destination,'source_msg_ids':[10,11]})
 async def test_preview_image_and_missing(self):
  with tempfile.TemporaryDirectory() as tmp:
   f=Path(tmp)/'p.jpg';f.write_bytes(b'jpeg-fixture');self.w.previews.get.return_value=str(f)
   r=await self.client.get('/api/own/preview?group_key=10',headers=self.headers());self.assertEqual(r.status,200);self.assertEqual(await r.read(),b'jpeg-fixture')
  self.db.get_own.return_value=None
  r=await self.client.get('/api/own/preview?group_key=unknown',headers=self.headers());self.assertEqual(r.status,404)
 async def test_schedule_api_future(self):
  at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
  r=await self.client.post('/api/own/repost',headers=self.headers(),json={'group_key':'10','scheduled_at':at});self.assertEqual(r.status,202)
  a=await self.db.get_action((await r.json())['action_id']);self.assertEqual(a['payload']['scheduled_at'],at)
 async def test_schedule_api_invalid(self):
  for at in ['2000-01-01T12:00:00+03:00','2099-01-01T12:00:00',42,'bad']:
   r=await self.client.post('/api/own/repost',headers=self.headers(),json={'group_key':'10','scheduled_at':at});self.assertEqual(r.status,400)
 async def test_schedule_action_never_sends_now(self):
  at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
  db=SimpleNamespace(get_own=AsyncMock(return_value={'msg_ids':[10],'post_date':datetime.now(timezone.utc),'text':'x','reactions':1}),create_repost_from_own=AsyncMock(return_value=123),mark_own_reposted=AsyncMock(),claim_post_for_publish=AsyncMock())
  w=SimpleNamespace(db=db,_own_sid=AsyncMock(return_value=1),_run=AsyncMock())
  result=await h_repost_own(w,{'group_key':'10','scheduled_at':at});self.assertEqual(result['scheduled_at'],at)
  self.assertEqual(db.create_repost_from_own.call_args.kwargs['scheduled_at'],datetime.fromisoformat(at));db.claim_post_for_publish.assert_not_awaited();w._run.assert_not_awaited()
 async def test_schedule_insert_atomic_and_duplicate_guard(self):
  db=object.__new__(DB);db._q=AsyncMock(return_value=[{'id':1}]);at=datetime.now(timezone.utc)+timedelta(days=1)
  await db.create_repost_from_own(1,'10',[10],at,'x',1,scheduled_at=at)
  sql,args=db._q.call_args.args;self.assertIn('reactions, scheduled_at',sql);self.assertIn("'candidate','processing'",sql);self.assertEqual(args[6],at)

if __name__=='__main__':unittest.main()
