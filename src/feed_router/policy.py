from __future__ import annotations

from .config import AppConfig, Policy
from .models import Entry


def resolve_policy_by_feed_title(config: AppConfig, feed_title: str) -> Policy | None:
    for policy in config.policies:
        if policy.feed_title == feed_title:
            return policy
    return None


def resolve_policy(config: AppConfig, entry: Entry) -> Policy | None:
    return resolve_policy_by_feed_title(config, entry.feed.title)
