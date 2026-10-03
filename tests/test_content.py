import unittest

from telethon.tl import types

from app.content import filter_source_content, is_advertisement


def _u16(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


class FilterSourceContentTests(unittest.TestCase):
    def test_detects_only_explicit_advertisement_markers(self):
        for text in (
            "#реклама",
            "Партнёрский материал #Advertisement",
            "#AD новый выпуск",
            "Это рекламный пост",
            "Рекламная интеграция: партнёр",
            "Материал на правах рекламы",
        ):
            with self.subTest(text=text):
                self.assertTrue(is_advertisement(text))

        for text in ("Ненавижу рекламу", "Убрали рекламу", "#adventure", "Обычный пост"):
            with self.subTest(text=text):
                self.assertFalse(is_advertisement(text))

    def test_removes_visible_links_mentions_and_email_without_touching_decimal_numbers(self):
        text = (
            "Цена 12.50 — реклама https://spam.example/x, www.ads.ru/a; "
            "t.me/bad @bad_channel mail@ads.example. Конец"
        )
        clean, entities = filter_source_content(text)
        self.assertEqual(clean, "Цена 12.50 — реклама , ; . Конец")
        self.assertEqual(entities, [])

    def test_removes_hidden_link_anchor_entirely(self):
        text = "До Нажми сюда после"
        start = text.index("Нажми")
        entity = types.MessageEntityTextUrl(
            offset=_u16(text[:start]), length=_u16("Нажми сюда"), url="https://ads.example"
        )
        clean, entities = filter_source_content(text, [entity])
        self.assertEqual(clean, "До после")
        self.assertEqual(entities, [])

    def test_preserves_and_remaps_unrelated_entities_with_utf16_emoji_offsets(self):
        text = "😀 https://ads.example\n\n\nФинал Жирный"
        start = text.index("Жирный")
        bold = types.MessageEntityBold(offset=_u16(text[:start]), length=_u16("Жирный"))
        custom = types.MessageEntityCustomEmoji(offset=0, length=_u16("😀"), document_id=123456789)
        original = [(bold.offset, bold.length), (custom.offset, custom.length)]
        clean, entities = filter_source_content(text, [bold, custom])
        self.assertEqual(clean, "😀\n\nФинал Жирный")
        self.assertEqual(
            [(type(e), e.offset, e.length) for e in entities],
            [
                (types.MessageEntityBold, _u16("😀\n\nФинал "), _u16("Жирный")),
                (types.MessageEntityCustomEmoji, 0, _u16("😀")),
            ],
        )
        self.assertEqual([(bold.offset, bold.length), (custom.offset, custom.length)], original)
        self.assertIsNot(entities[0], bold)
        self.assertIsNot(entities[1], custom)

    def test_entity_marked_url_is_removed_even_when_text_does_not_look_like_url(self):
        text = "Текст РЕКЛАМА конец"
        start = text.index("РЕКЛАМА")
        entity = types.MessageEntityUrl(offset=_u16(text[:start]), length=_u16("РЕКЛАМА"))
        clean, entities = filter_source_content(text, [entity])
        self.assertEqual(clean, "Текст конец")
        self.assertEqual(entities, [])

    def test_only_links_becomes_empty_and_none_entities_stays_empty_list(self):
        clean, entities = filter_source_content("  https://ads.example\n@bad_channel  ", None)
        self.assertEqual(clean, "")
        self.assertEqual(entities, [])


if __name__ == "__main__":
    unittest.main()
