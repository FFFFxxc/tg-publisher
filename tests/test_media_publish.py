"""Publish pipeline regressions; Telegram/DB are offline boundary doubles."""
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

from telethon import errors
from telethon.tl import types as t

from app.worker import Worker
from tests.fakes import FakeDB, make_cfg, make_post, to_post


def photo(mid):
    return NS(id=mid, media=t.MessageMediaPhoto(t.PhotoEmpty(mid)),
              photo=t.PhotoEmpty(mid), document=None, file=NS(size=10),
              message="original" if mid == 1 else "", entities=[])


def document(mid, attrs=None, mime="video/mp4"):
    doc = NS(dc_id=2, mime_type=mime, attributes=attrs or [
        t.DocumentAttributeFilename("clip.mp4"),
        t.DocumentAttributeVideo(12, 640, 480, supports_streaming=True)])
    return NS(id=mid, media=t.MessageMediaDocument(doc), photo=None,
              document=doc, file=NS(size=10), message="original" if mid == 1 else "", entities=[])


class PublishDB(FakeDB):
    async def mark_send_started(self, pid):
        (await self.get_post(pid))["send_started_at"] = "started"

    async def record_sent(self, pid, ids):
        p = await self.get_post(pid)
        p.update(status="ambiguous", dest_msg_ids=list(ids))

    async def mark_published(self, pid, ids):
        p = await self.get_post(pid)
        p.update(status="published", dest_msg_ids=list(ids))

    async def mark(self, pid, status, error=None):
        (await self.get_post(pid)).update(status=status, last_error=error)

    async def retry_later(self, pid, delay, error):
        (await self.get_post(pid)).update(status="pending", send_started_at=None,
                                         next_attempt_at=delay, last_error=error)


class PublishClient:
    def __init__(self, msgs, fail_at=None, failure=None, invalid_emoji=None):
        self.msgs, self.sent, self.uploaded = msgs, [], []
        self.calls = 0
        self.fail_at, self.failure = fail_at, failure
        self.invalid_emoji = invalid_emoji or set()

    async def __call__(self, request):
        return [t.DocumentEmpty(i) if i in self.invalid_emoji else
                t.Document(i, 0, b"", datetime.now(timezone.utc), "application/x-tgsticker", 1, 2, [])
                for i in request.document_id]

    async def get_messages(self, entity, ids):
        return self.msgs

    async def download_media(self, msg, file):
        path = Path(file)
        if not path.suffix:
            path = path / f"{msg.id}.{'jpg' if msg.photo else 'mp4'}"
        if msg.photo:
            from PIL import Image
            Image.new('RGB', (16, 16), 'red').save(path, format='JPEG')
        else:
            path.write_bytes(b"offline-media-fixture")
        return str(path)

    async def upload_file(self, path):
        self.uploaded.append(path)
        return t.InputFile(len(self.uploaded), 1, Path(path).name, "hash")

    async def send_file(self, dest, media, **kwargs):
        self.calls += 1
        if self.calls == self.fail_at:
            raise self.failure
        items = media if isinstance(media, list) else [media]
        # Reproduce a Telegram rejection of uploads with lost document metadata.
        if any(isinstance(m, str) for m in items):
            raise errors.DocumentInvalidError(request=None)
        if any(isinstance(e, t.MessageEntityCustomEmoji) and e.document_id in self.invalid_emoji
               for e in kwargs.get("formatting_entities", [])):
            raise errors.DocumentInvalidError(request=None)
        self.sent.append((items, kwargs))
        out = [NS(id=100 + sum(len(x[0]) for x in self.sent[:-1]) + i) for i in range(len(items))]
        return out if isinstance(media, list) else out[0]

    async def send_message(self, dest, text, **kwargs):
        self.sent.append(([text], kwargs))
        return NS(id=100)


class MediaPublishTests(unittest.IsolatedAsyncioTestCase):
    async def run_post(self, msgs, client=None, **cfg):
        db = PublishDB()
        db.posts = [make_post(3, "processing", source_msg_ids=[m.id for m in msgs], attempts=1)]
        client = client or PublishClient(msgs)
        w = Worker(make_cfg(ai_enabled=False, **cfg), db, client)
        w.dest = "dest"
        with tempfile.TemporaryDirectory() as tmp, patch("app.worker.resolve", AsyncMock(return_value="src")):
            await w._publish(to_post(db.posts[0]), tmp, await w.rt.view())
        return db, client

    async def test_four_item_album_keeps_source_video_metadata(self):
        msgs = [photo(1), document(2), document(3), photo(4)]
        db, client = await self.run_post(msgs)
        self.assertEqual(db.posts[0]["status"], "published")
        self.assertEqual(db.posts[0]["dest_msg_ids"], [100, 101, 102, 103])
        self.assertEqual(len(client.sent), 1)
        media, kwargs = client.sent[0]
        self.assertIsInstance(media[0], t.InputMediaUploadedPhoto)
        self.assertIsInstance(media[1], t.InputMediaUploadedDocument)
        self.assertEqual(media[1].mime_type, "video/mp4")
        video = next(a for a in media[1].attributes if isinstance(a, t.DocumentAttributeVideo))
        self.assertEqual((video.duration, video.w, video.h, video.supports_streaming), (12, 640, 480, True))
        self.assertTrue(media[1].nosound_video)
        self.assertIn("original", kwargs["caption"])

    async def test_invalid_customemoji_does_not_poison_photo_album(self):
        msgs = [photo(i) for i in range(1, 5)]
        client = PublishClient(msgs, invalid_emoji={5256105385420412669, 5195160091547942599})
        db, _ = await self.run_post(msgs, client)
        self.assertEqual(db.posts[0]["status"], "published")
        media, kwargs = client.sent[0]
        self.assertEqual(len(media), 4)
        self.assertFalse(any(isinstance(e, t.MessageEntityCustomEmoji) for e in kwargs["formatting_entities"]))
        self.assertIn("👀", kwargs["caption"])
        self.assertTrue(any(isinstance(e, t.MessageEntityTextUrl) for e in kwargs["formatting_entities"]))

    async def test_animation_sent_separately_in_original_order_caption_once(self):
        gif = document(2, [t.DocumentAttributeAnimated(), t.DocumentAttributeFilename("anim.mp4")])
        db, client = await self.run_post([photo(1), gif, photo(3), document(4)])
        self.assertEqual(db.posts[0]["status"], "published")
        self.assertEqual([len(items) for items, _ in client.sent], [1, 1, 2])
        self.assertEqual([kw["caption"] != "" for _, kw in client.sent], [True, False, False])

    async def test_audio_documents_and_visuals_are_not_mixed(self):
        msgs = [photo(1), document(2, [t.DocumentAttributeAudio(5)], "audio/mpeg"),
                document(3, [t.DocumentAttributeAudio(6)], "audio/mpeg"),
                document(4, [t.DocumentAttributeFilename("file.pdf")], "application/pdf")]
        db, client = await self.run_post(msgs)
        self.assertEqual(db.posts[0]["status"], "published")
        self.assertEqual([len(items) for items, _ in client.sent], [1, 2, 1])

    async def test_large_album_is_chunked_and_every_id_is_persisted(self):
        db, client = await self.run_post([photo(i) for i in range(1, 13)])
        self.assertEqual(db.posts[0]["status"], "published")
        self.assertEqual([len(items) for items, _ in client.sent], [10, 2])
        self.assertEqual(db.posts[0]["dest_msg_ids"], list(range(100, 112)))

    async def test_partial_rpc_failure_keeps_ids_and_is_not_retried(self):
        msgs = [photo(1), document(2, [t.DocumentAttributeAnimated()])]
        client = PublishClient(msgs, 2, errors.DocumentInvalidError(request=None))
        db, _ = await self.run_post(msgs, client)
        self.assertEqual(db.posts[0]["status"], "ambiguous")
        self.assertEqual(db.posts[0]["dest_msg_ids"], [100])
        self.assertIsNone(db.posts[0]["next_attempt_at"])

    async def test_network_failure_is_ambiguous(self):
        msgs = [photo(1)]
        client = PublishClient(msgs, 1, ConnectionError("offline"))
        with self.assertRaises(ConnectionError):
            await self.run_post(msgs, client)

    async def test_first_rpc_failure_can_be_retried(self):
        msgs = [photo(1)]
        db, _ = await self.run_post(msgs, PublishClient(msgs, 1, errors.DocumentInvalidError(request=None)))
        self.assertEqual(db.posts[0]["status"], "pending")
        self.assertEqual(db.posts[0]["dest_msg_ids"], [])

    async def test_text_only_still_publishes(self):
        msg = NS(id=1, media=None, photo=None, document=None, message="original", entities=[])
        db, client = await self.run_post([msg])
        self.assertEqual(db.posts[0]["status"], "published")
        self.assertIn("original", client.sent[0][0][0])


if __name__ == "__main__":
    unittest.main()
