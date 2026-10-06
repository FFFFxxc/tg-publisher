import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

from telethon.tl.types import MessageEntityTextUrl

from app.content import is_advertisement
from app.actions import h_backfill_source
from app.worker import Worker
from app.weekly import ranked_groups
from tests.fakes import make_cfg, make_post, to_post
from tests import test_content_publish
from tests.test_media_publish import PublishClient, PublishDB, photo
from tests.test_weekly import NOW, msg


class AdDetectionTests(unittest.TestCase):
    def test_legal_markers_without_hashtag(self):
        for text in ('Реклама. ООО Магазин', 'О рекламодателе', 'erid: 2Vtzq123',
                     'https://shop.ru/item?erid=2Vtzq123', '#ре\u200bклама',
                     'Партнерский материал: новый сервис'):
            with self.subTest(text=text):
                self.assertTrue(is_advertisement(text))

    def test_commercial_offer_without_label(self):
        self.assertTrue(is_advertisement(
            'STYLAR: брендовая одежда, обувь и аксессуары. Без лишних наценок '
            'напрямую от поставщиков. Заказать: https://shop.example/catalog'))

    def test_hidden_channel_promotion(self):
        text = 'Подписывайся на наш канал'
        entity = MessageEntityTextUrl(0, len(text), 'https://t.me/advertiser')
        self.assertTrue(is_advertisement(text, [entity]))

    def test_non_advertising_text_not_blocked(self):
        for text in ('Ненавижу рекламу', 'Убрали рекламу', '#adventure',
                     'Купил кроссовки и упал', 'Мем про рекламу',
                     'Документация https://python.org', 'Подписывайся на наш канал'):
            with self.subTest(text=text):
                self.assertFalse(is_advertisement(text))

    def test_weekly_ranking_drops_ad_even_with_high_score(self):
        advert, normal = msg(1, reactions=999), msg(2, reactions=1)
        advert.message = 'Реклама. erid: ABC123'
        self.assertEqual([row[1] for row in ranked_groups([advert, normal], NOW)], ['m2'])

    def test_weekly_album_hidden_ad_in_second_caption(self):
        first, second = msg(1, group=7), msg(2, group=7)
        second.message = 'Подписывайся на наш канал'
        second.entities = [MessageEntityTextUrl(0, len(second.message), 'https://t.me/advertiser')]
        self.assertEqual(ranked_groups([first, second], NOW), [])


class AdPublishTests(unittest.IsolatedAsyncioTestCase):
    async def test_own_archive_is_not_exempt_from_ad_filter(self):
        helper = test_content_publish.ContentPublishTests()
        row, client = await helper.publish('Реклама. erid: ABC123', source_id=1140244688)
        self.assertEqual(row['status'], 'skipped')
        self.assertEqual(client.sent, [])
        self.assertEqual(client.uploaded, [])

    async def test_second_album_caption_checked_before_media_download(self):
        first, second = photo(1), photo(2)
        first.message, second.message = 'Мем', 'Реклама. erid: ABC123'
        db = PublishDB()
        db.posts = [make_post(7, 'processing', text='Мем')]
        client = PublishClient([first, second])
        client.download_media = AsyncMock()
        worker = Worker(make_cfg(ai_enabled=False), db, client)
        worker.dest = 'dest'
        with tempfile.TemporaryDirectory() as tmp, patch('app.worker.resolve', AsyncMock(return_value=NS(id=123))):
            await worker._publish(to_post(db.posts[0]), tmp, await worker.rt.view())
        self.assertEqual(db.posts[0]['status'], 'skipped')
        client.download_media.assert_not_awaited()
        self.assertEqual(client.sent, [])

    async def test_collector_drops_ad_and_advances_cursor(self):
        advert = msg(1)
        advert.message = 'Реклама. erid: ABC123'
        advert.entities = []
        advert.replies = None
        async def messages(*args, **kwargs):
            yield advert
        db = NS(upsert_candidate=AsyncMock(), set_source_cursor=AsyncMock(),
                log_event=AsyncMock(), kv_prefix=AsyncMock(return_value={}))
        worker = Worker(make_cfg(ai_enabled=False), db, NS(iter_messages=messages))
        with patch('app.worker.resolve', AsyncMock(return_value=NS(id=123))), patch('app.worker.events.log_event', AsyncMock()):
            await worker._collect_source({'id': 1, 'ref': '@fixture', 'last_message_id': 0},
                                         NOW, await worker.rt.view())
        db.upsert_candidate.assert_not_awaited()
        db.set_source_cursor.assert_awaited_once_with(1, 1)

    async def test_backfill_drops_ad_before_queue_insert(self):
        advert = msg(1)
        advert.replies = None
        advert.message = 'Реклама. erid: ABC123'
        db = NS(get_source=AsyncMock(return_value={'ref': '@fixture'}),
                backfill_candidates=AsyncMock(return_value=0), set_source_title=AsyncMock())
        worker = NS(db=db, client=NS(get_messages=AsyncMock(return_value=[advert])),
                    rt=NS(view=AsyncMock(return_value=NS(ai_enabled=False))))
        with patch('app.actions.resolve', AsyncMock(return_value=NS(id=123))), patch('app.actions.events.log_event', AsyncMock()):
            await h_backfill_source(worker, {'source_id': 1, 'n': 10})
        db.backfill_candidates.assert_awaited_once_with(1, [], False)
