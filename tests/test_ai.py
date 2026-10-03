import unittest
from types import SimpleNamespace
from unittest.mock import patch

import app.ai as ai


def make_cfg():
    return SimpleNamespace(
        ai_timeout=40,
        ai_base_url="https://ai.example/v1",
        ai_api_key="secret",
        ai_model="free-model",
        ai_prompt="rewrite",
    )


class FakeResponse:
    def __init__(self, status_code, text="", headers=None, payload=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self._payload = payload

    def json(self):
        return self._payload


class FakeAsyncClient:
    calls = []
    responses = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        self.__class__.calls.append((url, kwargs))
        return self.__class__.responses.pop(0)


class AITests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        FakeAsyncClient.calls = []
        FakeAsyncClient.responses = []
        ai._cooldowns.clear()

    async def test_429_raises_typed_error_with_retry_after(self):
        FakeAsyncClient.responses = [FakeResponse(429, "quota", {"Retry-After": "120"})]
        with patch.object(ai.httpx, "AsyncClient", FakeAsyncClient), patch.object(ai.time, "monotonic", return_value=10):
            with self.assertRaises(ai.AIRateLimitError) as caught:
                await ai.generate_caption(make_cfg(), "original")

        self.assertEqual(caught.exception.retry_after, 120)
        self.assertIn("ai http 429", str(caught.exception))
        self.assertEqual(len(FakeAsyncClient.calls), 1)
        self.assertEqual(FakeAsyncClient.calls[0][1]["json"]["model"], "free-model")

    async def test_cooldown_blocks_repeat_http_call_then_expires(self):
        FakeAsyncClient.responses = [
            FakeResponse(429, "quota", {"Retry-After": "60"}),
            FakeResponse(200, payload={"choices": [{"message": {"content": "rewritten"}}]}),
        ]
        clock = iter((100, 100, 110, 161))
        with patch.object(ai.httpx, "AsyncClient", FakeAsyncClient), patch.object(
            ai.time, "monotonic", side_effect=lambda: next(clock)
        ):
            with self.assertRaises(ai.AIRateLimitError):
                await ai.generate_caption(make_cfg(), "original")
            with self.assertRaises(ai.AIRateLimitError) as caught:
                await ai.generate_caption(make_cfg(), "original")
            self.assertEqual(caught.exception.retry_after, 50)
            self.assertEqual(len(FakeAsyncClient.calls), 1)

            result = await ai.generate_caption(make_cfg(), "original")

        self.assertEqual(result, "rewritten")
        self.assertEqual(len(FakeAsyncClient.calls), 2)

    async def test_non_429_remains_generic_ai_error(self):
        FakeAsyncClient.responses = [FakeResponse(500, "broken")]
        with patch.object(ai.httpx, "AsyncClient", FakeAsyncClient):
            with self.assertRaises(ai.AIError) as caught:
                await ai.generate_caption(make_cfg(), "original")
        self.assertNotIsInstance(caught.exception, ai.AIRateLimitError)

    async def test_refusal_never_returns_as_caption(self):
        for text in (
            'Я не могу генерировать контент сексуального или откровенного характера (18+), так как это противоречит правилам.',
            'Извините, но я не могу комментировать это изображение.',
            "I'm sorry, but I can't help with this request.",
            'I cannot generate a caption for this image.',
        ):
            with self.subTest(text=text):
                FakeAsyncClient.responses = [FakeResponse(200, payload={'choices': [{'message': {'content': text}}]})]
                with patch.object(ai.httpx, 'AsyncClient', FakeAsyncClient):
                    with self.assertRaises(ai.AIError):
                        await ai.generate_caption(make_cfg(), 'original')

    async def test_provider_structured_refusal_and_content_filter(self):
        for choice in (
            {'message': {'content': 'placeholder', 'refusal': 'declined'}},
            {'message': {'content': 'placeholder'}, 'finish_reason': 'content_filter'},
        ):
            FakeAsyncClient.responses = [FakeResponse(200, payload={'choices': [choice]})]
            with patch.object(ai.httpx, 'AsyncClient', FakeAsyncClient):
                with self.assertRaises(ai.AIError):
                    await ai.generate_caption(make_cfg(), 'original')

    async def test_normal_caption_with_first_person_is_preserved(self):
        text = 'Когда я не могу перестать смеяться над этим мемом 😂'
        FakeAsyncClient.responses = [FakeResponse(200, payload={'choices': [{'message': {'content': text}}]})]
        with patch.object(ai.httpx, 'AsyncClient', FakeAsyncClient):
            self.assertEqual(await ai.generate_caption(make_cfg(), 'original'), text)

    def test_missing_image_service_reply_is_not_caption(self):
        self.assertTrue(ai.is_refusal('Я не вижу саму картинку, так как в сообщении указан только текст.'))
        self.assertTrue(ai.is_refusal("I can't see the image you mentioned."))

    async def test_429_without_retry_after_uses_bounded_defaults(self):
        cases = [
            ("temporary rate limit", 60),
            ("You've reached today's free-model token quota; wait for the daily reset", 3600),
        ]
        for body, expected in cases:
            with self.subTest(body=body):
                ai._cooldowns.clear()
                FakeAsyncClient.responses = [FakeResponse(429, body)]
                with patch.object(ai.httpx, "AsyncClient", FakeAsyncClient), patch.object(
                    ai.time, "monotonic", return_value=10
                ):
                    with self.assertRaises(ai.AIRateLimitError) as caught:
                        await ai.generate_caption(make_cfg(), "original")
                self.assertEqual(caught.exception.retry_after, expected)


if __name__ == "__main__":
    unittest.main()
