import unittest

from src.feed_router.telegram import _retry_after_seconds


class TelegramTests(unittest.TestCase):
    def test_retry_after_seconds_from_dict(self) -> None:
        self.assertEqual(_retry_after_seconds({"parameters": {"retry_after": 7}}), 7)

    def test_retry_after_seconds_from_json_string(self) -> None:
        payload = '{"ok": false, "parameters": {"retry_after": 3}}'
        self.assertEqual(_retry_after_seconds(payload), 3)

    def test_retry_after_seconds_missing(self) -> None:
        self.assertIsNone(_retry_after_seconds({"ok": False}))


if __name__ == "__main__":
    unittest.main()
