from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Target:
    chat_id: str
    message_thread_id: int | None = None


@dataclass(frozen=True)
class DigestConfig:
    window_hours: int
    max_items: int
    title: str | None = None
    similarity_threshold: float = 0.7


@dataclass(frozen=True)
class Policy:
    feed_title: str
    mode: str
    target: Target | None = None
    digest: DigestConfig | None = None


@dataclass(frozen=True)
class AppConfig:
    miniflux_base_url: str
    miniflux_api_token: str
    telegram_bot_token: str
    telegram_default_chat_id: str | None
    telegram_auto_create_topics: bool
    state_path: Path
    interval_seconds: int
    lookback_hours: int
    page_limit: int
    default_mode: str
    policies: tuple[Policy, ...]
    category_icons: dict[str, str] = field(default_factory=dict)


def _load_target(data: dict[str, Any] | None) -> Target | None:
    if not data:
        return None
    return Target(
        chat_id=str(data["chat_id"]),
        message_thread_id=data.get("message_thread_id"),
    )


def _load_digest(data: dict[str, Any] | None) -> DigestConfig | None:
    if not data:
        return None
    return DigestConfig(
        window_hours=int(data["window_hours"]),
        max_items=int(data["max_items"]),
        title=data.get("title"),
        similarity_threshold=float(data.get("similarity_threshold", 0.7)),
    )


def load_config(path: str | Path) -> AppConfig:
    raw = json.loads(Path(path).read_text())
    telegram = raw["telegram"]
    default_chat_id = telegram.get("chat_id")
    policies = tuple(
        Policy(
            feed_title=item["feed_title"],
            mode=item["mode"],
            target=_load_target(item.get("target")),
            digest=_load_digest(item.get("digest")),
        )
        for item in raw.get("policies", [])
    )
    return AppConfig(
        miniflux_base_url=raw["miniflux"]["base_url"].rstrip("/"),
        miniflux_api_token=raw["miniflux"]["api_token"],
        telegram_bot_token=telegram["bot_token"],
        telegram_default_chat_id=str(default_chat_id) if default_chat_id is not None else None,
        telegram_auto_create_topics=bool(telegram.get("auto_create_topics", True)),
        state_path=Path(raw["state"]["path"]),
        interval_seconds=int(raw["polling"].get("interval_seconds", 300)),
        lookback_hours=int(raw["polling"].get("lookback_hours", 24)),
        page_limit=int(raw["polling"].get("page_limit", 500)),
        default_mode=raw.get("defaults", {}).get("mode", "mute"),
        policies=policies,
        category_icons={
            str(category): str(icon_id)
            for category, icon_id in raw.get("category_icons", {}).items()
        },
    )
