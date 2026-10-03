import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiohttp.test_utils import TestClient, TestServer

from app.api import ApiContext, build_app
from tests.fakes import FakeDB, FakeWorker, make_cfg, make_post


class PreviewApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.image = Path(self.tmp.name)/'post-5.jpg'
        self.image.write_bytes(b'\xff\xd8preview-test\xff\xd9')
        self.db = FakeDB()
        self.db.posts = [make_post(5)]
        self.worker = FakeWorker(self.db, make_cfg())
        self.worker.previews = SimpleNamespace(get=AsyncMock(return_value=str(self.image)))
        self.client = TestClient(TestServer(build_app(ApiContext(self.worker), 'tok')))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.tmp.cleanup()

    async def fetch(self, pid='5', authorized=True):
        return await self.client.get('/api/posts/'+pid+'/preview',
                                     headers={'Authorization': 'Bearer tok'} if authorized else {})

    async def test_auth_required(self):
        self.assertEqual((await self.fetch(authorized=False)).status, 401)
        self.worker.previews.get.assert_not_awaited()

    async def test_jpeg_bytes_from_shared_cache(self):
        r = await self.fetch()
        self.assertEqual(r.status, 200)
        self.assertEqual(r.content_type, 'image/jpeg')
        self.assertEqual(await r.read(), self.image.read_bytes())
        self.assertIn('private', r.headers['Cache-Control'])
        self.worker.previews.get.assert_awaited_once_with(5, source_ref='@src', source_msg_ids=[10])

    async def test_no_media_is_empty_response(self):
        self.worker.previews.get.return_value = None
        self.assertEqual((await self.fetch()).status, 204)

    async def test_missing_post(self):
        self.assertEqual((await self.fetch('999')).status, 404)
        self.worker.previews.get.assert_not_awaited()

    async def test_invalid_id(self):
        for pid in ('bad', '-1', '0'):
            self.assertEqual((await self.fetch(pid)).status, 400)

    async def test_network_error_is_retryable_without_crashing_api(self):
        self.worker.previews.get.side_effect = ConnectionError('offline')
        self.assertEqual((await self.fetch()).status, 503)
        self.worker.previews.get.side_effect = None
        self.assertEqual((await self.fetch()).status, 200)
