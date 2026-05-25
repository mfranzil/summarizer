from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from .config import AppConfig, Policy, Target
from .formatter import coalesce_digest_items, format_digest, format_direct
from .miniflux import MinifluxClient
from .models import Entry, FeedRef
from .policy import resolve_policy_by_feed_title
from .state import RouterState, load_state, save_state
from .telegram import TelegramAPIError, TelegramClient


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _policy_key(policy: Policy) -> str:
    return policy.feed_title


def _topic_key(chat_id: str, feed_title: str) -> str:
    return f"{chat_id}:{feed_title}"


def _topic_name(feed_title: str) -> str:
    normalized = " ".join(feed_title.split())
    if not normalized:
        normalized = "Feed"
    return normalized[:128]


def _entry_to_state(entry: Entry) -> dict:
    return {
        "id": entry.id,
        "title": entry.title,
        "url": entry.url,
        "published_at": entry.published_at.isoformat(),
        "created_at": entry.created_at.isoformat(),
        "content": entry.content,
        "feed": {
            "id": entry.feed.id,
            "title": entry.feed.title,
            "site_url": entry.feed.site_url,
            "feed_url": entry.feed.feed_url,
            "category_title": entry.feed.category_title,
        },
    }


def _entry_from_state(raw: dict) -> Entry:
    feed = raw["feed"]
    return Entry(
        id=int(raw["id"]),
        title=raw["title"],
        url=raw["url"],
        published_at=datetime.fromisoformat(raw["published_at"]),
        created_at=datetime.fromisoformat(raw["created_at"]),
        content=raw.get("content"),
        feed=FeedRef(
            id=int(feed["id"]),
            title=feed["title"],
            site_url=feed["site_url"],
            feed_url=feed["feed_url"],
            category_title=feed.get("category_title"),
        ),
    )


class RouterService:
    def __init__(self, config: AppConfig, dry_run: bool = False) -> None:
        self.config = config
        self.dry_run = dry_run
        self.state = load_state(config.state_path)
        self.miniflux = MinifluxClient(config.miniflux_base_url, config.miniflux_api_token)
        self.telegram = TelegramClient(config.telegram_bot_token)
        self._planned_topics: set[str] = set()
        self._recent_topics_by_chat: dict[str, list] = {}

    def run_once(self) -> None:
        after_unix = int((_utc_now() - timedelta(hours=self.config.lookback_hours)).timestamp())
        entries = self.miniflux.get_entries(after_unix=after_unix, limit=self.config.page_limit)
        entries = [entry for entry in entries if entry.id > self.state.last_processed_entry_id]

        for entry in entries:
            self._handle_entry(entry)
            self.state.last_processed_entry_id = max(self.state.last_processed_entry_id, entry.id)

        self._flush_due_digests()
        if self.dry_run:
            return
        save_state(self.config.state_path, self.state)

    def run_loop(self) -> None:
        while True:
            self.run_once()
            time.sleep(self.config.interval_seconds)

    def cleanup_topics(self) -> None:
        chat_id = self.config.telegram_default_chat_id
        if chat_id is None:
            raise ValueError("cleanup-topics requires telegram.chat_id in config")
        topics = self.telegram.get_recent_forum_topics(chat_id)
        seen = set()
        unique_topics = []
        for topic in sorted(topics, key=lambda item: item.message_thread_id, reverse=True):
            if topic.message_thread_id in seen:
                continue
            seen.add(topic.message_thread_id)
            unique_topics.append(topic)

        if self.dry_run:
            for topic in unique_topics:
                print("=== DRY RUN DELETE TOPIC ===")
                print(f"chat_id={chat_id} thread_id={topic.message_thread_id} name={topic.name}")
                print("=== END DELETE TOPIC ===")
            return

        for topic in unique_topics:
            try:
                self.telegram.delete_forum_topic(chat_id, topic.message_thread_id)
            except TelegramAPIError as exc:
                if not self._is_invalid_topic_error(exc):
                    raise
            deleted = self.state.deleted_forum_topic_ids.setdefault(chat_id, [])
            if topic.message_thread_id not in deleted:
                deleted.append(topic.message_thread_id)

        prefix = f"{chat_id}:"
        self.state.forum_topic_ids = {
            key: value for key, value in self.state.forum_topic_ids.items() if not key.startswith(prefix)
        }
        save_state(self.config.state_path, self.state)

    def _handle_entry(self, entry: Entry) -> None:
        policy = self._resolve_policy(entry.feed.title)
        if policy is None:
            return

        if policy.mode == "mute":
            return
        if policy.mode == "direct":
            self._send_direct(policy, entry)
            return
        if policy.mode == "digest":
            self._queue_digest(policy, entry)
            return
        raise ValueError(f"Unsupported policy mode: {policy.mode}")

    def _send_direct(self, policy: Policy, entry: Entry) -> None:
        sent = self.state.delivered_entry_ids.setdefault(_policy_key(policy), [])
        if entry.id in sent:
            return
        self._deliver_entry_for_policy(policy, entry)
        sent.append(entry.id)

    def _queue_digest(self, policy: Policy, entry: Entry) -> None:
        key = _policy_key(policy)
        items = self.state.digest_entries.setdefault(key, [])
        if any(existing["id"] == entry.id for existing in items):
            return
        items.append(_entry_to_state(entry))

    def _flush_due_digests(self) -> None:
        now = _utc_now()
        for policy in self.config.policies:
            if policy.mode != "digest":
                continue
            assert policy.digest is not None
            key = _policy_key(policy)
            last_sent = self.state.digest_last_sent_at.get(key)
            if last_sent is None:
                should_send = True
            else:
                should_send = now >= datetime.fromisoformat(last_sent) + timedelta(hours=policy.digest.window_hours)
            items = self.state.digest_entries.get(key, [])
            if not items:
                continue
            if not should_send:
                continue
            entries = [_entry_from_state(item) for item in items]
            entries.sort(key=lambda item: item.created_at)
            entries = coalesce_digest_items(entries)
            message = format_digest(entries, policy.digest, policy.feed_title)
            self._deliver_for_policy(policy, message)
            self.state.delivered_entry_ids.setdefault(key, []).extend(entry.id for entry in entries)
            self.state.digest_entries[key] = []
            self.state.digest_last_sent_at[key] = now.isoformat()

    def _resolve_policy(self, feed_title: str) -> Policy | None:
        policy = resolve_policy_by_feed_title(self.config, feed_title)
        if policy is not None:
            return policy
        if self.config.default_mode == "mute":
            return None
        if self.config.default_mode == "direct":
            return Policy(feed_title=feed_title, mode="direct")
        raise ValueError(f"Unsupported default mode for unmatched feed {feed_title!r}: {self.config.default_mode}")

    def _resolve_base_target(self, policy: Policy) -> Target:
        if policy.target is not None:
            return policy.target
        if self.config.telegram_default_chat_id is None:
            raise ValueError(
                f"Feed {policy.feed_title!r} needs a target but no telegram.chat_id is configured"
            )
        return Target(chat_id=self.config.telegram_default_chat_id)

    def _resolve_target(self, policy: Policy) -> Target:
        target = self._resolve_base_target(policy)
        if target.message_thread_id is not None:
            return target
        if not self.config.telegram_auto_create_topics:
            return target
        return self._ensure_forum_topic(target.chat_id, policy.feed_title)

    def _deliver_for_policy(self, policy: Policy, message: str) -> None:
        target = self._resolve_target(policy)
        try:
            self._deliver(target, message)
            return
        except TelegramAPIError as exc:
            if not self._is_missing_thread_error(exc):
                raise

        base_target = self._resolve_base_target(policy)
        key = _topic_key(base_target.chat_id, policy.feed_title)
        stale_thread_id = self.state.forum_topic_ids.pop(key, None)
        if stale_thread_id is not None:
            deleted = self.state.deleted_forum_topic_ids.setdefault(base_target.chat_id, [])
            if stale_thread_id not in deleted:
                deleted.append(stale_thread_id)
            if not self.dry_run:
                save_state(self.config.state_path, self.state)

        retry_target = self._ensure_forum_topic(base_target.chat_id, policy.feed_title, allow_existing=False)
        self._deliver(retry_target, message)

    def _deliver_entry_for_policy(self, policy: Policy, entry: Entry) -> None:
        target = self._resolve_target(policy)
        try:
            self._deliver_entry(target, entry)
            return
        except TelegramAPIError as exc:
            if not self._is_missing_thread_error(exc):
                raise

        base_target = self._resolve_base_target(policy)
        key = _topic_key(base_target.chat_id, policy.feed_title)
        stale_thread_id = self.state.forum_topic_ids.pop(key, None)
        if stale_thread_id is not None:
            deleted = self.state.deleted_forum_topic_ids.setdefault(base_target.chat_id, [])
            if stale_thread_id not in deleted:
                deleted.append(stale_thread_id)
            if not self.dry_run:
                save_state(self.config.state_path, self.state)

        retry_target = self._ensure_forum_topic(base_target.chat_id, policy.feed_title, allow_existing=False)
        self._deliver_entry(retry_target, entry)

    def _ensure_forum_topic(self, chat_id: str, feed_title: str, allow_existing: bool = True) -> Target:
        key = _topic_key(chat_id, feed_title)
        thread_id = self.state.forum_topic_ids.get(key)
        if thread_id is not None:
            return Target(chat_id=chat_id, message_thread_id=thread_id)

        if allow_existing:
            existing_topic = self._find_existing_forum_topic(chat_id, feed_title)
            if existing_topic is not None:
                self.state.forum_topic_ids[key] = existing_topic.message_thread_id
                if not self.dry_run:
                    save_state(self.config.state_path, self.state)
                return Target(chat_id=chat_id, message_thread_id=existing_topic.message_thread_id)

        name = _topic_name(feed_title)
        if self.dry_run:
            if key not in self._planned_topics:
                print("=== DRY RUN TOPIC ===")
                print(f"chat_id={chat_id} name={name}")
                print("=== END TOPIC ===")
                self._planned_topics.add(key)
            return Target(chat_id=chat_id)

        topic = self.telegram.create_forum_topic(chat_id, name)
        self.state.forum_topic_ids[key] = topic.message_thread_id
        self._recent_topics_by_chat.setdefault(chat_id, []).append(topic)
        save_state(self.config.state_path, self.state)
        return Target(chat_id=chat_id, message_thread_id=topic.message_thread_id)

    def _find_existing_forum_topic(self, chat_id: str, feed_title: str):
        if self.dry_run:
            return None
        name = _topic_name(feed_title)
        topics = self._recent_topics_by_chat.get(chat_id)
        if topics is None:
            topics = self.telegram.get_recent_forum_topics(chat_id)
            self._recent_topics_by_chat[chat_id] = topics
        deleted_ids = set(self.state.deleted_forum_topic_ids.get(chat_id, []))
        matching = [topic for topic in topics if topic.name == name and topic.message_thread_id not in deleted_ids]
        if not matching:
            return None
        return min(matching, key=lambda topic: topic.message_thread_id)

    def _is_missing_thread_error(self, exc: TelegramAPIError) -> bool:
        description = exc.description.lower()
        return exc.error_code == 400 and "message thread not found" in description

    def _is_invalid_topic_error(self, exc: TelegramAPIError) -> bool:
        description = exc.description.lower()
        return exc.error_code == 400 and "topic_id_invalid" in description

    def _deliver(self, target, message: str) -> None:
        if self.dry_run:
            print("=== DRY RUN MESSAGE ===")
            print(f"chat_id={target.chat_id} thread_id={target.message_thread_id}")
            print(message)
            print("=== END MESSAGE ===")
            return
        self.telegram.send_message(target, message)

    def _deliver_entry(self, target, entry: Entry) -> None:
        message = format_direct(entry)
        if self.dry_run:
            print("=== DRY RUN MESSAGE ===")
            print(f"chat_id={target.chat_id} thread_id={target.message_thread_id}")
            print(message)
            if entry.comments_url:
                print(f"buttons=Open,Comments comments_url={entry.comments_url}")
            else:
                print("buttons=Open")
            print("=== END MESSAGE ===")
            return
        self.telegram.send_entry(target, message, entry)
