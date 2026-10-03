import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

from app.worker import Worker
from tests.fakes import make_cfg, make_post, to_post
from tests.test_media_publish import PublishClient, PublishDB, photo


class ContentPublishTests(unittest.IsolatedAsyncioTestCase):
    async def publish(self, text, source_id=2122808509, ai_caption=None, media=True):
        msg = photo(1) if media else NS(id=1, media=None, message=text, entities=[])
        msg.message = text
        db = PublishDB()
        db.posts = [make_post(7, 'processing', source_ref=str(-1000000000000 - source_id),
                             text=text, ai_status='generated' if ai_caption else 'not_needed',
                             ai_caption=ai_caption)]
        client = PublishClient([msg])
        w = Worker(make_cfg(ai_enabled=bool(ai_caption), footer=[]), db, client)
        w.dest = 'dest'
        with tempfile.TemporaryDirectory() as tmp, patch('app.worker.resolve', AsyncMock(return_value=NS(id=source_id))):
            await w._publish(to_post(db.posts[0]), tmp, await w.rt.view())
        return db.posts[0], client

    async def test_foreign_links_removed_but_own_footer_preserved(self):
        msg = photo(1)
        msg.message = 'Мем https://t.me/foreign @advertiser example.com'
        db = PublishDB()
        db.posts = [make_post(7, 'processing', text=msg.message)]
        client = PublishClient([msg])
        w = Worker(make_cfg(ai_enabled=False), db, client)
        w.dest = 'dest'
        with tempfile.TemporaryDirectory() as tmp, patch('app.worker.resolve', AsyncMock(return_value=NS(id=123))):
            await w._publish(to_post(db.posts[0]), tmp, await w.rt.view())
        caption = client.sent[0][1]['caption']
        self.assertNotIn('foreign', caption)
        self.assertNotIn('advertiser', caption)
        self.assertNotIn('example.com', caption)
        self.assertIn('ХОТ КОНТЕНТ', caption)
        self.assertTrue(any(getattr(e, 'url', '') == 'https://t.me/fulli4k_bot'
                            for e in client.sent[0][1]['formatting_entities']))

    async def test_2d_webm_links_kept(self):
        _, client = await self.publish('Мем https://t.me/own_link', source_id=1140244688)
        self.assertIn('https://t.me/own_link', client.sent[0][1]['caption'])

    async def test_cached_ai_links_removed(self):
        _, client = await self.publish('Мем', ai_caption='Весело https://evil.example/promo')
        self.assertEqual(client.sent[0][1]['caption'], 'Весело')

    async def test_refusal_uses_original_not_service_text(self):
        row, client = await self.publish('Мем', ai_caption='Я не могу генерировать такой контент.')
        self.assertEqual(client.sent[0][1]['caption'], 'Мем')
        self.assertEqual(row['ai_status'], 'failed')
        self.assertIsNone(row['ai_caption'])

    async def test_link_only_text_skipped_without_footer_only_post(self):
        row, client = await self.publish('https://t.me/advertiser', media=False)
        self.assertEqual(row['status'], 'skipped')
        self.assertEqual(client.sent, [])

    async def test_explicit_foreign_ad_skipped_before_upload(self):
        row, client = await self.publish('#реклама Подпишись https://t.me/advertiser')
        self.assertEqual(row['status'], 'skipped')
        self.assertEqual(client.sent, [])
        self.assertEqual(client.uploaded, [])
