import json
import tempfile
import unittest
from pathlib import Path

from src.feed_router.config import load_config


class ConfigTests(unittest.TestCase):
    def test_load_config_supports_default_chat_id(self) -> None:
        raw = {
            "miniflux": {
                "base_url": "https://reader.example.com",
                "api_token": "token",
            },
            "telegram": {
                "bot_token": "bot-token",
                "chat_id": "12345",
            },
            "category_icons": {
                "News": 5434144690511290129,
            },
            "state": {
                "path": "state/router-state.json",
            },
            "polling": {
                "interval_seconds": 300,
                "lookback_hours": 24,
                "page_limit": 100,
            },
            "defaults": {
                "mode": "direct",
            },
            "policies": [
                {
                    "feed_title": "Feed A",
                    "mode": "digest",
                    "digest": {
                        "window_hours": 12,
                        "max_items": 10,
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.json"
            path.write_text(json.dumps(raw))
            config = load_config(path)
        self.assertEqual(config.telegram_default_chat_id, "12345")
        self.assertTrue(config.telegram_auto_create_topics)
        self.assertEqual(config.category_icons, {"News": "5434144690511290129"})
        self.assertEqual(config.default_mode, "direct")
        self.assertEqual(config.policies[0].feed_title, "Feed A")
        self.assertIsNone(config.policies[0].target)


if __name__ == "__main__":
    unittest.main()
