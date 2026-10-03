import unittest

from app.api import mask_key, parse_paging, parse_posts_filters
from app.db import SchemaIsolationError, assert_current_schema, build_events_where, build_posts_where
from app.events import scrub
from app.logic import canonical_ref, next_slot
from datetime import datetime, time


class SchemaAssertionTests(unittest.TestCase):
    def test_ok(self):
        assert_current_schema("tg_publisher", "tg_publisher")

    def test_fail_fast_on_wrong_schema(self):
        for actual in ("public", None, ""):
            with self.assertRaises(SchemaIsolationError, msg=str(actual)):
                assert_current_schema(actual, "tg_publisher")


class MaskAndScrubTests(unittest.TestCase):
    def test_mask_key(self):
        self.assertEqual(mask_key(""), {"configured": False, "mask": ""})
        m = mask_key("sk-abcdef123456")
        self.assertTrue(m["configured"])
        self.assertNotIn("sk-abcdef", m["mask"])
        self.assertTrue(m["mask"].endswith("3456"))
        self.assertEqual(mask_key("short")["mask"], "•" * 8)   # короткий ключ не раскрываем хвостом

    def test_scrub_metadata(self):
        md = scrub({"api_key": "X", "nested": {"password": "Y", "ok": 1}, "model": "m",
                    "l": ["a" * 600]})
        self.assertNotIn("api_key", md)
        self.assertNotIn("password", md["nested"])
        self.assertEqual(md["nested"]["ok"], 1)
        self.assertEqual(md["model"], "m")
        self.assertEqual(len(md["l"][0]), 500)


class NextSlotTests(unittest.TestCase):
    def test_next_slot(self):
        times = [time(9), time(12), time(21)]
        self.assertEqual(next_slot(datetime(2026, 10, 3, 8, 0), times), datetime(2026, 10, 3, 9, 0))
        self.assertEqual(next_slot(datetime(2026, 10, 3, 12, 5), times), datetime(2026, 10, 3, 21, 0))
        self.assertEqual(next_slot(datetime(2026, 10, 3, 22, 0), times), datetime(2026, 10, 4, 9, 0))
        self.assertIsNone(next_slot(datetime(2026, 10, 3, 8, 0), []))


class CanonicalRefTests(unittest.TestCase):
    def test_canonical_ref(self):
        self.assertEqual(canonical_ref("@chan"), "@chan")
        self.assertEqual(canonical_ref("https://t.me/chan"), "@chan")
        self.assertEqual(canonical_ref("t.me/chan_name"), "@chan_name")
        self.assertEqual(canonical_ref("-1001234567890"), "-1001234567890")
        self.assertEqual(canonical_ref("https://t.me/+AbC-12_x"), "https://t.me/+AbC-12_x")


class QueryBuilderTests(unittest.TestCase):
    def test_posts_where(self):
        where, args = build_posts_where({"status": "failed", "kind": "parsed", "q": "42"})
        self.assertIn("p.status = %s", where)
        self.assertIn("p.kind = %s", where)
        self.assertIn("p.id::text = %s", where)
        self.assertEqual(args, ["failed", "parsed", "%42%", "42"])

    def test_posts_where_text_search(self):
        where, args = build_posts_where({"q": "кот"})
        self.assertNotIn("p.id::text", where)
        self.assertEqual(args, ["%кот%"])

    def test_posts_where_date_range(self):
        where, args = build_posts_where({"date_from": "2026-10-01", "date_to": "2026-10-02"})
        self.assertIn("p.source_date >= %s", where)
        self.assertIn("p.source_date < %s", where)
        self.assertEqual(args, ["2026-10-01", "2026-10-02"])

    def test_posts_where_empty(self):
        where, args = build_posts_where({})
        self.assertEqual(where, "TRUE")
        self.assertEqual(args, [])

    def test_events_where(self):
        where, args = build_events_where({"level": "error", "post_id": 5})
        self.assertIn("level = %s", where)
        self.assertIn("post_id = %s", where)
        self.assertEqual(args, ["error", 5])


class ApiParsingTests(unittest.TestCase):
    def test_parse_paging(self):
        self.assertEqual(parse_paging({}), (25, 0))
        self.assertEqual(parse_paging({"limit": "500"}), (100, 0))   # clamp
        self.assertEqual(parse_paging({"limit": "10", "offset": "30"}), (10, 30))
        with self.assertRaises(ValueError):
            parse_paging({"limit": "abc"})

    def test_parse_posts_filters(self):
        f = parse_posts_filters({"status": "failed", "date": "2026-10-03", "q": "привет"})
        self.assertEqual(f["status"], "failed")
        self.assertEqual(f["date_from"], "2026-10-03")
        self.assertEqual(f["date_to"], "2026-10-04")
        self.assertEqual(f["q"], "привет")
        with self.assertRaises(ValueError):
            parse_posts_filters({"status": "wat"})
        with self.assertRaises(ValueError):
            parse_posts_filters({"date": "03-10-2026"})
        with self.assertRaises(ValueError):
            parse_posts_filters({"source_id": "x"})


if __name__ == "__main__":
    unittest.main()
