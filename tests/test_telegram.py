import unittest
import json
from types import SimpleNamespace
from unittest.mock import patch

from src.feed_router.config import Target
from src.feed_router.telegram import TelegramAPIError, TelegramClient, _retry_after_seconds


class TelegramTests(unittest.TestCase):
    def test_invalid_preview_retries_without_preview(self) -> None:
        client = TelegramClient("test")
        entry = SimpleNamespace(id=42, url="https://example.com/article", comments_url=None)
        payloads = []

        def request(method, payload):
            payloads.append(dict(payload))
            if len(payloads) == 1:
                raise TelegramAPIError(method, 400, "Bad Request: WEBPAGE_URL_INVALID")
            return {}

        with patch.object(client, "_request", side_effect=request):
            client.send_entry(Target("123", 7), "Article", entry)
        self.assertEqual(len(payloads), 2)
        self.assertEqual(json.loads(payloads[1]["link_preview_options"]), {"is_disabled": True})
        for key in ("text", "chat_id", "message_thread_id", "reply_markup"):
            self.assertEqual(payloads[0][key], payloads[1][key])

    def test_unrelated_error_is_not_retried(self) -> None:
        client = TelegramClient("test")
        entry = SimpleNamespace(id=42, url="https://example.com", comments_url=None)
        error = TelegramAPIError("sendMessage", 403, "Forbidden")
        with patch.object(client, "_request", side_effect=error) as request:
            with self.assertRaises(TelegramAPIError):
                client.send_entry(Target("123"), "Article", entry)
        request.assert_called_once()

    def test_retry_after_seconds_from_dict(self) -> None:
        self.assertEqual(_retry_after_seconds({"parameters": {"retry_after": 7}}), 7)

    def test_retry_after_seconds_from_json_string(self) -> None:
        payload = '{"ok": false, "parameters": {"retry_after": 3}}'
        self.assertEqual(_retry_after_seconds(payload), 3)

    def test_retry_after_seconds_missing(self) -> None:
        self.assertIsNone(_retry_after_seconds({"ok": False}))


if __name__ == "__main__":
    unittest.main()
