import contextlib
import io
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.feed_router.config import AppConfig
from src.feed_router.models import Entry, FeedRef
from src.feed_router.service import RouterService


class StubMinifluxClient:
    def __init__(self, entry: Entry) -> None:
        self.entry = entry

    def get_entries(self, after_unix: int, limit: int):
        return [self.entry]


class StubTelegramClient:
    def send_message(self, target, text: str) -> None:
        raise AssertionError("dry-run must not send Telegram messages")

    def send_entry(self, target, text: str, entry) -> None:
        raise AssertionError("dry-run must not send Telegram messages")


def make_entry() -> Entry:
    now = datetime.now(timezone.utc)
    return Entry(
        id=1,
        title="Hello",
        url="https://example.com/hello",
        comments_url="https://example.com/comments",
        published_at=now,
        created_at=now,
        content=None,
        feed=FeedRef(id=1, title="Feed A", site_url="https://example.com", feed_url="https://example.com/feed"),
    )


class DryRunTests(unittest.TestCase):
    def test_run_once_dry_run_does_not_write_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            config = AppConfig(
                miniflux_base_url="https://reader.example.com",
                miniflux_api_token="token",
                telegram_bot_token="bot-token",
                telegram_default_chat_id="12345",
                telegram_auto_create_topics=False,
                state_path=state_path,
                interval_seconds=300,
                lookback_hours=24,
                page_limit=100,
                default_mode="direct",
                policies=(),
            )
            service = RouterService(config, dry_run=True)
            service.miniflux = StubMinifluxClient(make_entry())
            service.telegram = StubTelegramClient()

            with contextlib.redirect_stdout(io.StringIO()):
                service.run_once()

            self.assertFalse(state_path.exists())


if __name__ == "__main__":
    unittest.main()
