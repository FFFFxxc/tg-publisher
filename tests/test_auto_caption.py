import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

from app.worker import Worker
from tests.fakes import make_cfg, make_post, to_post
from tests.test_media_publish import PublishClient, PublishDB, photo


class AutomaticCaptionTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_generates_unchecked_caption_without_manual_action(self):
        message = photo(1)
        message.message = 'Исходный текст'
        db = PublishDB()
        db.posts = [make_post(7, 'processing', text=message.message, ai_status='unchecked')]
        client = PublishClient([message])
        worker = Worker(make_cfg(ai_enabled=True, ai_required=True, footer=[]), db, client)
        worker.dest = 'dest'
        generator = AsyncMock(return_value='Автоматическая подпись')
        with tempfile.TemporaryDirectory() as tmp, \
             patch('app.worker.resolve', AsyncMock(return_value=NS(id=123))), \
             patch.object(worker, '_preview_image', AsyncMock(return_value=None)), \
             patch('app.worker.generate_caption', generator):
            await worker._publish(to_post(db.posts[0]), tmp, await worker.rt.view())
        generator.assert_awaited_once()
        self.assertEqual(client.sent[0][1]['caption'], 'Автоматическая подпись')
        self.assertEqual(db.posts[0]['ai_status'], 'generated')
