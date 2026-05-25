from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RouterState:
    last_processed_entry_id: int = 0
    delivered_entry_ids: dict[str, list[int]] = field(default_factory=dict)
    digest_entries: dict[str, list[dict]] = field(default_factory=dict)
    digest_last_sent_at: dict[str, str] = field(default_factory=dict)
    forum_topic_ids: dict[str, int] = field(default_factory=dict)
    deleted_forum_topic_ids: dict[str, list[int]] = field(default_factory=dict)


def load_state(path: Path) -> RouterState:
    if not path.exists():
        return RouterState()
    raw = json.loads(path.read_text())
    return RouterState(
        last_processed_entry_id=int(raw.get("last_processed_entry_id", 0)),
        delivered_entry_ids={k: list(v) for k, v in raw.get("delivered_entry_ids", {}).items()},
        digest_entries={k: list(v) for k, v in raw.get("digest_entries", {}).items()},
        digest_last_sent_at=dict(raw.get("digest_last_sent_at", {})),
        forum_topic_ids={k: int(v) for k, v in raw.get("forum_topic_ids", {}).items()},
        deleted_forum_topic_ids={k: [int(item) for item in v] for k, v in raw.get("deleted_forum_topic_ids", {}).items()},
    )


def save_state(path: Path, state: RouterState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "last_processed_entry_id": state.last_processed_entry_id,
                "delivered_entry_ids": state.delivered_entry_ids,
                "digest_entries": state.digest_entries,
                "digest_last_sent_at": state.digest_last_sent_at,
                "forum_topic_ids": state.forum_topic_ids,
                "deleted_forum_topic_ids": state.deleted_forum_topic_ids,
                "saved_at": _utc_now().isoformat(),
            },
            indent=2,
            sort_keys=True,
        )
    )
