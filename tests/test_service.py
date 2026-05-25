import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.feed_router.config import AppConfig, Policy
from src.feed_router.models import Entry, FeedRef
from src.feed_router.service import RouterService
from src.feed_router.telegram import ForumTopic, TelegramAPIError


class RecordingTelegramClient:
    def __init__(self) -> None:
        self.created_topics = []
        self.deleted_topics = []
        self.invalid_deleted_topics = set()
        self.recent_topics = []
        self.sent_messages = []
        self.sent_entries = []
        self.fail_missing_thread_ids = set()

    def create_forum_topic(self, chat_id: str, name: str) -> ForumTopic:
        self.created_topics.append((chat_id, name))
        return ForumTopic(message_thread_id=1000 + len(self.created_topics), name=name)

    def send_message(self, target, text: str) -> None:
        if target.message_thread_id in self.fail_missing_thread_ids:
            raise TelegramAPIError("sendMessage", 400, "Bad Request: message thread not found")
        self.sent_messages.append((target, text))

    def send_entry(self, target, text: str, entry) -> None:
        if target.message_thread_id in self.fail_missing_thread_ids:
            raise TelegramAPIError("sendMessage", 400, "Bad Request: message thread not found")
        self.sent_entries.append((target, text, entry))

    def delete_forum_topic(self, chat_id: str, message_thread_id: int) -> None:
        if message_thread_id in self.invalid_deleted_topics:
            raise TelegramAPIError("deleteForumTopic", 400, "Bad Request: TOPIC_ID_INVALID")
        self.deleted_topics.append((chat_id, message_thread_id))

    def get_recent_forum_topics(self, chat_id: str):
        return list(self.recent_topics)


class StubMinifluxClient:
    def __init__(self, entries=None):
        self.entries = list(entries or [])

    def get_feeds(self):
        return []

    def get_entries(self, after_unix: int, limit: int):
        return list(self.entries)


def make_entry(feed_title: str) -> Entry:
    now = datetime.now(timezone.utc)
    return Entry(
        id=1,
        title="Hello",
        url="https://example.com/hello",
        comments_url="https://example.com/comments",
        published_at=now,
        created_at=now,
        content=None,
        feed=FeedRef(id=1, title=feed_title, site_url="https://example.com", feed_url="https://example.com/feed"),
    )


class ServiceTests(unittest.TestCase):
    def test_unmatched_feed_routes_to_auto_created_topic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            config = AppConfig(
                miniflux_base_url="https://reader.example.com",
                miniflux_api_token="token",
                telegram_bot_token="bot-token",
                telegram_default_chat_id="12345",
                telegram_auto_create_topics=True,
                state_path=state_path,
                interval_seconds=300,
                lookback_hours=24,
                page_limit=100,
                default_mode="direct",
                policies=(Policy(feed_title="Muted", mode="mute"),),
            )
            service = RouterService(config)
            service.telegram = RecordingTelegramClient()
            service.miniflux = StubMinifluxClient([make_entry("Feed A")])

            service.run_once()

        self.assertEqual(service.telegram.created_topics, [("12345", "Feed A")])
        self.assertEqual(len(service.telegram.sent_entries), 1)
        target, text, entry = service.telegram.sent_entries[0]
        self.assertEqual(target.chat_id, "12345")
        self.assertEqual(target.message_thread_id, 1001)
        self.assertIn("Feed A", text)
        self.assertEqual(entry.comments_url, "https://example.com/comments")
        self.assertEqual(service.state.forum_topic_ids, {"12345:Feed A": 1001})

    def test_existing_recent_topic_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AppConfig(
                miniflux_base_url="https://reader.example.com",
                miniflux_api_token="token",
                telegram_bot_token="bot-token",
                telegram_default_chat_id="12345",
                telegram_auto_create_topics=True,
                state_path=Path(tmpdir) / "state.json",
                interval_seconds=300,
                lookback_hours=24,
                page_limit=100,
                default_mode="direct",
                policies=(),
            )
            service = RouterService(config)
            service.telegram = RecordingTelegramClient()
            service.telegram.recent_topics = [ForumTopic(message_thread_id=42, name="Feed A")]
            service.miniflux = StubMinifluxClient()

            service._handle_entry(make_entry("Feed A"))

        self.assertEqual(service.telegram.created_topics, [])
        self.assertEqual(service.telegram.sent_entries[0][0].message_thread_id, 42)

    def test_cleanup_topics_deletes_recent_bot_topics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AppConfig(
                miniflux_base_url="https://reader.example.com",
                miniflux_api_token="token",
                telegram_bot_token="bot-token",
                telegram_default_chat_id="12345",
                telegram_auto_create_topics=True,
                state_path=Path(tmpdir) / "state.json",
                interval_seconds=300,
                lookback_hours=24,
                page_limit=100,
                default_mode="direct",
                policies=(),
            )
            service = RouterService(config)
            service.telegram = RecordingTelegramClient()
            service.telegram.recent_topics = [
                ForumTopic(message_thread_id=8, name="Feed A"),
                ForumTopic(message_thread_id=10, name="Feed B"),
            ]
            service.state.forum_topic_ids = {"12345:Feed A": 8, "12345:Feed B": 10}

            service.cleanup_topics()

        self.assertEqual(service.telegram.deleted_topics, [("12345", 10), ("12345", 8)])
        self.assertEqual(service.state.deleted_forum_topic_ids, {"12345": [10, 8]})

    def test_cleanup_topics_ignores_invalid_topic_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AppConfig(
                miniflux_base_url="https://reader.example.com",
                miniflux_api_token="token",
                telegram_bot_token="bot-token",
                telegram_default_chat_id="12345",
                telegram_auto_create_topics=True,
                state_path=Path(tmpdir) / "state.json",
                interval_seconds=300,
                lookback_hours=24,
                page_limit=100,
                default_mode="direct",
                policies=(),
            )
            service = RouterService(config)
            service.telegram = RecordingTelegramClient()
            service.telegram.invalid_deleted_topics = {8}
            service.telegram.recent_topics = [ForumTopic(message_thread_id=8, name="Feed A")]

            service.cleanup_topics()

        self.assertEqual(service.state.deleted_forum_topic_ids, {"12345": [8]})

    def test_missing_thread_recreates_topic_and_retries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AppConfig(
                miniflux_base_url="https://reader.example.com",
                miniflux_api_token="token",
                telegram_bot_token="bot-token",
                telegram_default_chat_id="12345",
                telegram_auto_create_topics=True,
                state_path=Path(tmpdir) / "state.json",
                interval_seconds=300,
                lookback_hours=24,
                page_limit=100,
                default_mode="direct",
                policies=(),
            )
            service = RouterService(config)
            service.telegram = RecordingTelegramClient()
            service.telegram.fail_missing_thread_ids = {22}
            service.telegram.recent_topics = [ForumTopic(message_thread_id=22, name="Feed A")]
            service.state.forum_topic_ids = {"12345:Feed A": 22}

            service._handle_entry(make_entry("Feed A"))

        self.assertEqual(service.telegram.created_topics, [("12345", "Feed A")])
        self.assertEqual(service.state.forum_topic_ids["12345:Feed A"], 1001)
        self.assertIn(22, service.state.deleted_forum_topic_ids["12345"])
        self.assertEqual(service.telegram.sent_entries[-1][0].message_thread_id, 1001)


if __name__ == "__main__":
    unittest.main()
