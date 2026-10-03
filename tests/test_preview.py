from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from PIL import Image
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto, PhotoSize, VideoSize

from app.preview import PreviewCache


def _image(path: str | Path, color=(20, 80, 160), size=(32, 24)):
    Image.new("RGB", size, color).save(path, format="JPEG")


def _photo(mid: int):
    return SimpleNamespace(id=mid, media=MessageMediaPhoto(), document=None)


def _video(mid: int):
    document = SimpleNamespace(thumbs=[
        VideoSize("v", 1920, 1080, 9999),
        PhotoSize("s", 90, 90, 100),
        PhotoSize("x", 800, 450, 2000),
    ])
    return SimpleNamespace(id=mid, media=MessageMediaDocument(document=document), document=document)


def _text(mid: int):
    return SimpleNamespace(id=mid, media=None, document=None)


class Client:
    def __init__(self, broken_ids=()):
        self.calls = []
        self.fetches = 0
        self.broken_ids = set(broken_ids)

    def is_connected(self):
        return True

    async def download_media(self, msg, file, **kwargs):
        self.calls.append((msg.id, dict(kwargs)))
        if msg.id in self.broken_ids:
            Path(file).write_bytes(b"not an image")
        else:
            _image(file, color=(msg.id % 255, 40, 80))
        return str(file)

    async def get_messages(self, entity, ids):
        self.fetches += 1
        return [_photo(mid) for mid in ids]


class PreviewCacheTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        import tempfile
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    async def test_photo_post_returns_local_image(self):
        client = Client()
        result = await PreviewCache(client, self.path).get(1, msgs=[_photo(10)])
        self.assertTrue(result and Path(result).is_file())
        self.assertEqual(client.calls, [(10, {})])

    async def test_video_uses_largest_static_thumbnail_never_original(self):
        client = Client()
        result = await PreviewCache(client, self.path).get(2, msgs=[_video(20)])
        self.assertTrue(result)
        thumb = client.calls[0][1]["thumb"]
        self.assertIsInstance(thumb, PhotoSize)
        self.assertEqual(thumb.type, "x")

    async def test_text_only_returns_none(self):
        client = Client()
        self.assertIsNone(await PreviewCache(client, self.path).get(3, msgs=[_text(30)]))
        self.assertEqual(client.calls, [])

    async def test_album_uses_first_suitable_image_in_source_order(self):
        client = Client()
        result = await PreviewCache(client, self.path).get(4, msgs=[_text(1), _photo(2), _photo(3)])
        self.assertTrue(result)
        self.assertEqual([call[0] for call in client.calls], [2])

    async def test_cache_hit_avoids_fetch_and_download(self):
        client = Client()
        preview = PreviewCache(client, self.path)
        first = await preview.get(5, msgs=[_photo(50)])
        client.calls.clear()
        second = await preview.get(5, source_ref="@source", source_msg_ids=[50])
        self.assertEqual(second, first)
        self.assertEqual((client.fetches, client.calls), (0, []))

    async def test_cache_miss_fetches_with_supplied_client_in_source_order(self):
        client = Client()
        preview = PreviewCache(client, self.path)
        with patch("app.preview.resolve", AsyncMock(return_value="entity")):
            result = await preview.get(51, source_ref="@source", source_msg_ids=[512, 511])
        self.assertTrue(result)
        self.assertEqual(client.fetches, 1)
        self.assertEqual([call[0] for call in client.calls], [512])

    async def test_bad_first_media_falls_through_to_next(self):
        client = Client(broken_ids={61})
        result = await PreviewCache(client, self.path).get(6, msgs=[_photo(61), _photo(62)])
        self.assertTrue(result)
        self.assertEqual([call[0] for call in client.calls], [61, 62])

    async def test_concurrent_requests_deduplicate_download(self):
        client = Client()
        preview = PreviewCache(client, self.path)
        results = await asyncio.gather(*[preview.get(7, msgs=[_photo(70)]) for _ in range(5)])
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(len(client.calls), 1)

    async def test_reuses_matching_downloaded_photo(self):
        downloaded = self.path / "downloads" / "81" / "photo.jpg"
        downloaded.parent.mkdir(parents=True)
        _image(downloaded)
        client = Client()
        result = await PreviewCache(client, self.path / "cache").get(
            8, msgs=[_photo(81)], downloaded_files=[str(downloaded)]
        )
        self.assertTrue(result)
        self.assertEqual(client.calls, [])
