import unittest

from app.api import parse_posts_filters
from app.db import build_posts_where


class QueueSkipTests(unittest.TestCase):
    def test_active_queue_excludes_terminal_posts(self):
        filters = parse_posts_filters({"status": "queued"})
        where, args = build_posts_where(filters)
        self.assertIn("p.status = ANY(%s)", where)
        self.assertEqual(set(args[0]), {"candidate", "pending", "processing", "failed", "ambiguous"})
        for status in ("skipped", "published", "expired"):
            self.assertNotIn(status, args[0])

    def test_explicit_skipped_filter_preserves_history(self):
        where, args = build_posts_where(parse_posts_filters({"status": "skipped"}))
        self.assertIn("p.status = %s", where)
        self.assertEqual(args, ["skipped"])

    def test_all_filter_does_not_filter_status(self):
        where, args = build_posts_where(parse_posts_filters({"status": "all"}))
        self.assertEqual(where, "TRUE")
        self.assertEqual(args, [])
