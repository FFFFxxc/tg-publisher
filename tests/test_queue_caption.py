import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from aiohttp.test_utils import TestClient, TestServer
from app.worker import Worker
from app.api import ApiContext, build_app
from app.db import DB
from tests.fakes import FakeDB, make_cfg, make_post, to_post

class QueueCaptionTests(unittest.IsolatedAsyncioTestCase):
    async def test_manual_caption_used_even_if_ai_disabled(self):
        db=FakeDB(); w=Worker(make_cfg(ai_enabled=False),db,None)
        post=to_post(make_post(5,ai_status='manual',ai_caption='Моя подпись'))
        self.assertEqual(await w._ai(post,None,await w.rt.view()),'Моя подпись')

    async def test_background_prepares_next_queue_post(self):
        db=FakeDB(); db.next_caption_post=AsyncMock(return_value=5)
        w=Worker(make_cfg(ai_enabled=True),db,None)
        w.prepare_caption=AsyncMock()
        await w.caption_tick()
        w.prepare_caption.assert_awaited_once_with(5)

    async def test_background_preserves_manual_caption(self):
        db=FakeDB();db.posts=[make_post(5,ai_status='manual',ai_caption='Авторский текст')]
        w=Worker(make_cfg(ai_enabled=True),db,None)
        w._ai=AsyncMock()
        await w.prepare_caption(5)
        w._ai.assert_not_awaited()
        self.assertEqual(db.posts[0]['ai_caption'],'Авторский текст')

    async def test_background_does_not_generate_when_disabled(self):
        db=FakeDB();db.next_caption_post=AsyncMock()
        w=Worker(make_cfg(ai_enabled=False),db,None)
        await w.caption_tick()
        db.next_caption_post.assert_not_awaited()

    async def test_manual_update_guard(self):
        db=object.__new__(DB); db._q=AsyncMock(return_value=[{'id':5}])
        self.assertTrue(await db.set_manual_caption(5,'Моя подпись'))
        sql,args=db._q.call_args.args
        self.assertIn("ai_status='manual'",sql)
        self.assertIn('send_started_at IS NULL',sql)
        self.assertIn('cardinality(dest_msg_ids)=0',sql)
        self.assertEqual(args,('Моя подпись',5))

    async def test_caption_api_and_validation(self):
        db=FakeDB();db.posts=[make_post(5)];db.set_manual_caption=AsyncMock(return_value=True)
        w=Worker(make_cfg(),db,None)
        c=TestClient(TestServer(build_app(ApiContext(w),'tok')));await c.start_server()
        try:
            headers={'Authorization':'Bearer tok'}
            r=await c.put('/api/posts/5/caption',json={'caption':'Моя подпись'},headers=headers)
            self.assertEqual(r.status,200)
            for value in ('',True,'x'*4097):
                r=await c.put('/api/posts/5/caption',json={'caption':value},headers=headers)
                self.assertEqual(r.status,400)
            db.set_manual_caption.return_value=False
            r=await c.put('/api/posts/5/caption',json={'caption':'abc'},headers=headers)
            self.assertEqual(r.status,409)
        finally: await c.close()
