import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.feed_router.config import AppConfig, Policy, Target
from src.feed_router.models import Entry, FeedRef
from src.feed_router.policy import resolve_policy


class PolicyTests(unittest.TestCase):
    def test_resolve_policy_by_feed_title(self) -> None:
        policy = Policy(feed_title="Feed A", mode="direct", target=Target(chat_id="1"))
        config = AppConfig(
            miniflux_base_url="https://reader.example.com",
            miniflux_api_token="x",
            telegram_bot_token="y",
            telegram_default_chat_id=None,
            telegram_auto_create_topics=True,
            state_path=Path("state.json"),
            interval_seconds=300,
            lookback_hours=24,
            page_limit=100,
            default_mode="mute",
            policies=(policy,),
        )
        now = datetime.now(timezone.utc)
        entry = Entry(
            id=1,
            title="Hello",
            url="https://example.com",
            comments_url=None,
            published_at=now,
            created_at=now,
            content=None,
            feed=FeedRef(id=1, title="Feed A", site_url="https://site", feed_url="https://feed"),
        )
        self.assertEqual(resolve_policy(config, entry), policy)


if __name__ == "__main__":
    unittest.main()
