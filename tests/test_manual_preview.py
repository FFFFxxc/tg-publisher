import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

from PIL import Image
from telethon.tl import types as t

from app.actions import h_generate_ai, h_test_ai_provider
from app.worker import Worker
from tests.fakes import FakeDB, make_cfg, make_post


class PreviewClient:
    def __init__(self, msgs):
        self.msgs = msgs
        self.downloads = []

    async def get_messages(self, entity, ids):
        return self.msgs

    async def download_media(self, msg, file, thumb=None):
        self.downloads.append((msg.id, thumb))
        path = Path(file)
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (24, 18), color='red').save(path, format='JPEG')
        return str(path)

    def is_connected(self):
        return True


def photo():
    p = t.PhotoEmpty(20)
    return NS(id=10, media=t.MessageMediaPhoto(p), photo=p, document=None, message='Мем', entities=[])


def video():
    doc = NS(thumbs=[t.PhotoSize('m', 320, 180, 1000)], size=300_000_000, mime_type='video/mp4')
    return NS(id=10, media=t.MessageMediaDocument(doc), photo=None, document=doc, message='Видео', entities=[])


class ManualPreviewTests(unittest.IsolatedAsyncioTestCase):
    async def run_manual(self, msg):
        with tempfile.TemporaryDirectory() as tmp:
            db = FakeDB()
            db.posts = [make_post(5, text=msg.message, ai_status='unchecked')]
            client = PreviewClient([msg])
            w = Worker(make_cfg(ai_enabled=True, session_path=str(Path(tmp)/'userbot')), db, client)
            seen = []

            async def caption(post, image, rt):
                seen.append((image, Path(image).read_bytes() if image else None))
                await db.set_ai(post.id, 'generated', 'Готовая подпись')

            w._ai = caption
            with patch('app.actions.resolve', AsyncMock(return_value='source')):
                result = await h_generate_ai(w, {'post_id': 5})
            return seen, client.downloads, result

    async def test_photo_passes_existing_image_path_to_ai(self):
        seen, downloads, result = await self.run_manual(photo())
        self.assertTrue(seen[0][0])
        self.assertTrue(seen[0][1].startswith(b'\xff\xd8'))
        self.assertEqual(downloads[0][0], 10)
        self.assertEqual(result['ai_status'], 'generated')

    async def test_video_uses_thumb_not_large_original(self):
        seen, downloads, _ = await self.run_manual(video())
        self.assertTrue(seen[0][0])
        self.assertEqual(len(downloads), 1)
        self.assertIsNotNone(downloads[0][1])

    async def test_text_only_passes_none(self):
        msg = NS(id=10, media=None, document=None, photo=None, message='Только текст', entities=[])
        seen, downloads, _ = await self.run_manual(msg)
        self.assertIsNone(seen[0][0])
        self.assertEqual(downloads, [])


class QuickModelTestTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_secondary_test_does_not_switch_bot(self):
        db = FakeDB()
        w = Worker(make_cfg(ai_enabled=False), db, None)
        await w.rt.update('ai', {'ai_secondary_base_url': 'https://second.example/v1',
                                 'ai_secondary_model': 'vision-2', 'ai_secondary_api_key': 'second-secret'})
        with patch('app.actions.generate_caption', AsyncMock(return_value='Тест работает')) as generate:
            result = await h_test_ai_provider(w, {'profile': 2, 'text': 'Проверка'})
        cfg = generate.call_args.args[0]
        self.assertEqual(cfg.ai_model, 'vision-2')
        self.assertEqual(cfg.ai_api_key, 'second-secret')
        self.assertEqual(result['profile'], 2)
        self.assertFalse(result['image_attached'])
        self.assertEqual((await w.rt.view()).ai_model, 'test-model')

    async def test_vision_test_attaches_post_preview_without_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = FakeDB()
            db.posts = [make_post(5)]
            client = PreviewClient([photo()])
            w = Worker(make_cfg(ai_enabled=True, session_path=str(Path(tmp)/'userbot')), db, client)
            captured = []

            async def generate(cfg, text, image):
                captured.append(image)
                self.assertTrue(image and Path(image).exists())
                return 'На изображении красный квадрат'

            with patch('app.preview.resolve', AsyncMock(return_value='src')), patch('app.actions.generate_caption', generate):
                result = await h_test_ai_provider(w, {'profile': 1, 'post_id': 5})
            self.assertTrue(result['image_attached'])
            self.assertEqual(result['model'], 'test-model')
            self.assertEqual(db.posts[0]['status'], 'candidate')
            self.assertIsNone(db.posts[0]['ai_caption'])
