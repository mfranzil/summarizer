from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from .models import Entry, FeedRef


_USER_AGENT = "MinifluxTelegramRouter/0.1"


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


class MinifluxClient:
    def __init__(self, base_url: str, api_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token

    def _get(self, path: str, query: dict[str, str | int]) -> dict:
        qs = urllib.parse.urlencode(query, doseq=True)
        url = f"{self.base_url}{path}?{qs}"
        req = urllib.request.Request(url)
        req.add_header("X-Auth-Token", self.api_token)
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", _USER_AGENT)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_entries(self, after_unix: int, limit: int) -> list[Entry]:
        payload = self._get(
            "/v1/entries",
            {
                "direction": "asc",
                "order": "id",
                "after": after_unix,
                "limit": limit,
            },
        )
        entries = []
        for item in payload.get("entries", []):
            feed = item["feed"]
            category = feed.get("category") or {}
            entries.append(
                Entry(
                    id=int(item["id"]),
                    title=item["title"],
                    url=item["url"],
                    comments_url=item.get("comments_url") or None,
                    published_at=_parse_dt(item["published_at"]),
                    created_at=_parse_dt(item["created_at"]),
                    content=item.get("content"),
                    feed=FeedRef(
                        id=int(feed["id"]),
                        title=feed["title"],
                        site_url=feed["site_url"],
                        feed_url=feed["feed_url"],
                        category_title=category.get("title"),
                    ),
                )
            )
        return entries

    def get_feeds(self) -> list[FeedRef]:
        payload = self._get("/v1/feeds", {})
        feeds = []
        for item in payload:
            category = item.get("category") or {}
            feeds.append(
                FeedRef(
                    id=int(item["id"]),
                    title=item["title"],
                    site_url=item["site_url"],
                    feed_url=item["feed_url"],
                    category_title=category.get("title"),
                )
            )
        return feeds

    def get_feed_by_title(self, title: str) -> FeedRef | None:
        for feed in self.get_feeds():
            if feed.title == title:
                return feed
        return None
