import unittest
from datetime import datetime, timezone

from src.feed_router.config import DigestConfig
from src.feed_router.formatter import coalesce_digest_items, format_digest, format_direct, group_digest_items
from src.feed_router.models import Entry, FeedRef


def make_entry(entry_id: int, title: str, url: str) -> Entry:
    now = datetime.now(timezone.utc)
    return Entry(
        id=entry_id,
        title=title,
        url=url,
        comments_url=None,
        published_at=now,
        created_at=now,
        content=None,
        feed=FeedRef(id=1, title="Feed", site_url="https://example.com", feed_url="https://example.com/feed"),
    )


class FormatterTests(unittest.TestCase):
    def test_coalesce_digest_items_removes_exact_duplicates(self) -> None:
        first = make_entry(1, "Hello", "https://example.com/a")
        duplicate = make_entry(2, "Hello", "https://example.com/a")
        result = coalesce_digest_items([first, duplicate])
        self.assertEqual(result, [first])

    def test_format_digest_uses_title_and_links(self) -> None:
        digest = DigestConfig(window_hours=12, max_items=10, title="Digest")
        text = format_digest([make_entry(1, "Hello", "https://example.com/a")], digest, "Feed")
        self.assertIn("Digest", text)
        self.assertIn("Hello", text)
        self.assertIn("https://example.com/a", text)

    def test_group_digest_items_merges_similar_titles(self) -> None:
        digest = DigestConfig(window_hours=12, max_items=10, title="Digest", similarity_threshold=0.7)
        first = make_entry(1, "Apple unveils M4 chip for laptops", "https://example.com/a")
        second = make_entry(2, "Apple unveils M4 chips for laptops", "https://example.com/b")
        groups = group_digest_items([first, second], digest)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0].entries), 2)

    def test_format_digest_truncates_to_telegram_limit(self) -> None:
        digest = DigestConfig(window_hours=12, max_items=200, title="Digest")
        entries = [
            make_entry(index, (chr(64 + index) * 220), f"https://example.com/{index}")
            for index in range(1, 40)
        ]
        text = format_digest(entries, digest, "Feed")
        self.assertLessEqual(len(text), 4096)
        self.assertIn("... and ", text)

    def test_format_direct_uses_html_link_and_preview(self) -> None:
        entry = make_entry(1, "Hello", "https://example.com/a")
        entry = Entry(
            id=entry.id,
            title=entry.title,
            url=entry.url,
            comments_url=entry.comments_url,
            published_at=entry.published_at,
            created_at=entry.created_at,
            content="<p>Summary with <b>markup</b>.</p>",
            feed=entry.feed,
        )
        text = format_direct(entry)
        self.assertIn("<b>Feed</b>", text)
        self.assertIn('<a href="https://example.com/a">Hello</a>', text)
        self.assertIn("Summary with markup.", text)


if __name__ == "__main__":
    unittest.main()
