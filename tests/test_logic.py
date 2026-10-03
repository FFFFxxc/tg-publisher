import os
import unittest
from datetime import datetime, time
from types import SimpleNamespace as E

from app.config import ConfigError, build_proxy, normalize_dsn, sqlalchemy_url, validate_session_string
from app.logic import (AMBIGUOUS, DEFAULT_FOOTER, MEDIA_CAPTION_LIMIT, OLD, PARSED, PENDING, PROCESSING,
                       PUBLISHED, backoff_seconds, build_caption, due_slot, group_messages, in_window,
                       parse_footer, parse_pattern, recovery_action, render_footer, u16)


class ConfigTests(unittest.TestCase):
    def test_quoted_session_rejected(self):
        for s in ['"abc"', "'abc'"]:
            with self.assertRaises(ConfigError):
                validate_session_string(s)
        self.assertEqual(validate_session_string(" abc \n"), "abc")

    def test_proxy(self):
        self.assertIsNone(build_proxy("", 1080))
        self.assertEqual(build_proxy("127.0.0.1", 1080),
                         {"proxy_type": "socks5", "addr": "127.0.0.1", "port": 1080, "rdns": True})

    def test_dsn(self):
        self.assertEqual(normalize_dsn("postgres://u:p@h/db"), "postgresql://u:p@h/db")
        self.assertEqual(sqlalchemy_url("postgres://u@h/db"), "postgresql+psycopg://u@h/db")

    def test_repr_hides_secrets(self):
        os.environ.update(TG_API_ID="1", TG_API_HASH="SECRETHASH", TG_SESSION_STRING="SECRETSESS",
                          TG_DESTINATION="@d", DATABASE_URL="postgresql://u:PW@h/db", TG_PROXY_HOST="")
        from app.config import Config
        r = repr(Config.from_env())
        for secret in ("SECRETHASH", "SECRETSESS", "PW"):
            self.assertNotIn(secret, r)


class FooterTests(unittest.TestCase):
    def test_default_footer_ids(self):
        f = parse_footer("")
        self.assertEqual([x["emoji_id"] for x in f], [5256105385420412669, 5195160091547942599])

    def test_render_offsets_utf16(self):
        text, ents = render_footer(DEFAULT_FOOTER)
        self.assertEqual(text, "👀 ХОТ КОНТЕНТ\n😡 МЫ В МАКСЕ")
        self.assertEqual(ents[0], ("emoji", 0, 2, 5256105385420412669))   # 👀 = 2 UTF-16 units
        self.assertEqual(ents[1], ("url", 3, 11, "https://t.me/fulli4k_bot"))
        line2 = u16("👀 ХОТ КОНТЕНТ\n")
        self.assertEqual(ents[2], ("emoji", line2, 2, 5195160091547942599))
        self.assertEqual(ents[3], ("url", line2 + 3, 10, "https://max.ru/channel_anime2d"))

    def test_caption_always_has_footer_with_shifted_offsets(self):
        text, kept, specs = build_caption("Привет 🔥", [E(offset=0, length=6)], DEFAULT_FOOTER, True)
        self.assertTrue(text.startswith("Привет 🔥\n\n👀 ХОТ КОНТЕНТ"))
        self.assertEqual(len(kept), 1)
        base = u16("Привет 🔥\n\n")
        self.assertEqual(specs[0][1], base)
        enc = text.encode("utf-16-le")
        k, off, ln, url = specs[1]
        self.assertEqual(enc[off * 2:(off + ln) * 2].decode("utf-16-le"), "ХОТ КОНТЕНТ")

    def test_footer_not_duplicated_on_repost(self):
        old = "старый пост\n\n👀 ХОТ КОНТЕНТ\n😡 МЫ В МАКСЕ"
        text, _, specs = build_caption(old, [], DEFAULT_FOOTER, True)
        self.assertEqual(text, old)
        self.assertEqual(specs, [])

    def test_long_caption_truncated_footer_kept(self):
        text, kept, _ = build_caption("x" * 3000, [E(offset=2990, length=5)], DEFAULT_FOOTER, True, premium=False)
        self.assertLessEqual(u16(text), MEDIA_CAPTION_LIMIT)
        self.assertTrue(text.endswith("МЫ В МАКСЕ"))
        self.assertEqual(kept, [])


class ScheduleTests(unittest.TestCase):
    def test_pattern(self):
        self.assertEqual(parse_pattern("parsed,old,parsed,old"), [PARSED, OLD, PARSED, OLD])
        self.assertEqual(parse_pattern("спаршенный, старый"), [PARSED, OLD])
        with self.assertRaises(ValueError):
            parse_pattern("parsed,wat")

    def test_due_slot(self):
        times = [time(9), time(12)]
        self.assertEqual(due_slot(datetime(2026, 10, 3, 12, 5), times), "2026-10-03 12:00")
        self.assertIsNone(due_slot(datetime(2026, 10, 3, 12, 30), times))
        self.assertIsNone(due_slot(datetime(2026, 10, 3, 8, 0), times))

    def test_window(self):
        d = lambda h: datetime(2026, 1, 1, h, 0)
        self.assertTrue(in_window(d(12), "09:00-23:00"))
        self.assertFalse(in_window(d(3), "09:00-23:00"))
        self.assertTrue(in_window(d(1), "22:00-02:00"))


class RecoveryTests(unittest.TestCase):
    def test_matrix(self):
        self.assertEqual(recovery_action(PROCESSING, True, [10]), PUBLISHED)
        self.assertEqual(recovery_action(PROCESSING, True, []), AMBIGUOUS)
        self.assertEqual(recovery_action(PROCESSING, False, []), PENDING)
        self.assertIsNone(recovery_action("published", True, [1]))

    def test_albums_and_backoff(self):
        self.assertEqual(group_messages([(5, None), (6, 77), (7, 77)]), [("m5", [5]), ("g77", [6, 7])])
        self.assertEqual(backoff_seconds(20), 3600)


if __name__ == "__main__":
    unittest.main()


class RefTests(unittest.TestCase):
    def test_parse_ref(self):
        from app.logic import parse_ref
        self.assertEqual(parse_ref("@chan"), ("username", "chan"))
        self.assertEqual(parse_ref("https://t.me/chan_name"), ("username", "chan_name"))
        self.assertEqual(parse_ref("-1001234567890"), ("id", -1001234567890))
        self.assertEqual(parse_ref("https://t.me/+AbC-12_x"), ("invite", "AbC-12_x"))
        self.assertEqual(parse_ref("t.me/joinchat/XYZ123"), ("invite", "XYZ123"))
