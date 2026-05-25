from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FeedRef:
    id: int
    title: str
    site_url: str
    feed_url: str
    category_title: str | None = None


@dataclass(frozen=True)
class Entry:
    id: int
    title: str
    url: str
    comments_url: str | None
    published_at: datetime
    created_at: datetime
    content: str | None
    feed: FeedRef
