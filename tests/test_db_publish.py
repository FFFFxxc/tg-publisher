import unittest

from app.db import DB


class CaptureDB(DB):
    def __init__(self):
        self.query = None

    async def _q(self, sql, args=()):
        self.query = (sql, args)
        return [{"id": 7}]


class PublishPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirmed_partial_send_is_durable_and_not_published(self):
        db = CaptureDB()
        await db.record_sent(3, [100, 101])
        sql, args = db.query
        self.assertIn("status='ambiguous'", sql)
        self.assertIn("dest_msg_ids=%s", sql)
        self.assertEqual(args, ([100, 101], 3))

    async def test_repost_array_parameters_explicitly_match_bigint_columns(self):
        db = CaptureDB()
        await db.create_repost_from_own(1, "k", [12, 13], "2026-01-01", "text", 1)
        sql, args = db.query
        self.assertIn("r.dest_msg_ids && %s::bigint[]", sql)
        self.assertIn("r.source_msg_ids = %s::bigint[]", sql)
