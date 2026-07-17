from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from html import unescape

from .config import DigestConfig
from .models import Entry


_TELEGRAM_MESSAGE_LIMIT = 4096


@dataclass(frozen=True)
class DigestGroup:
    representative: Entry
    entries: tuple[Entry, ...]


_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def _normalize_title(title: str) -> str:
    return " ".join(_TOKEN_RE.findall(title.lower()))


def _token_set(title: str) -> set[str]:
    return set(_TOKEN_RE.findall(title.lower()))


def _title_similarity(left: str, right: str) -> float:
    left_norm = _normalize_title(left)
    right_norm = _normalize_title(right)
    if not left_norm or not right_norm:
        return 0.0
    ratio = SequenceMatcher(a=left_norm, b=right_norm).ratio()
    left_tokens = _token_set(left)
    right_tokens = _token_set(right)
    if not left_tokens or not right_tokens:
        return ratio
    jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    return max(ratio, jaccard)


def format_direct(entry: Entry) -> str:
    return f"<b>{_escape_html(entry.feed.title)}</b>\n<a href=\"{_escape_html(entry.url)}\">{_escape_html(entry.title)}</a>{_format_content_preview(entry.content)}"


def group_digest_items(entries: list[Entry], digest: DigestConfig) -> list[DigestGroup]:
    groups: list[list[Entry]] = []
    for entry in entries:
        placed = False
        for group in groups:
            representative = group[0]
            if _title_similarity(entry.title, representative.title) >= digest.similarity_threshold:
                group.append(entry)
                placed = True
                break
        if not placed:
            groups.append([entry])

    result = []
    for group in groups:
        result.append(DigestGroup(representative=group[0], entries=tuple(group)))
    return result


def format_digest(entries: list[Entry], digest: DigestConfig, feed_title: str) -> str:
    title = _escape_html(digest.title) if digest.title else f"{_escape_html(feed_title)} Digest"
    lines = [title]
    groups = group_digest_items(entries, digest)
    for group in groups[: digest.max_items]:
        representative = group.representative
        if len(group.entries) == 1:
            lines.append(f"- {_escape_html(representative.title)}")
            lines.append(f"  {_escape_html(representative.url)}")
            continue
        sources = ", ".join(sorted({_escape_html(entry.feed.title) for entry in group.entries}))
        lines.append(f"- {_escape_html(representative.title)} ({len(group.entries)} items)")
        lines.append(f"  Sources: {sources}")
        lines.append(f"  {_escape_html(representative.url)}")

    message = "\n".join(lines)
    if len(message) <= _TELEGRAM_MESSAGE_LIMIT:
        return message

    truncated_lines = [title]
    remaining = len(groups[: digest.max_items])
    for group in groups[: digest.max_items]:
        group_lines = _format_digest_group(group)
        overflow_line = _overflow_line(remaining - 1)
        candidate_lines = truncated_lines + group_lines
        if overflow_line is not None:
            candidate_lines.append(overflow_line)
        candidate = "\n".join(candidate_lines)
        if len(candidate) > _TELEGRAM_MESSAGE_LIMIT:
            break
        truncated_lines.extend(group_lines)
        remaining -= 1

    overflow_line = _overflow_line(remaining)
    if overflow_line is not None:
        candidate = "\n".join(truncated_lines + [overflow_line])
        if len(candidate) <= _TELEGRAM_MESSAGE_LIMIT:
            truncated_lines.append(overflow_line)
    return "\n".join(truncated_lines)


def _format_digest_group(group: DigestGroup) -> list[str]:
    representative = group.representative
    if len(group.entries) == 1:
        return [f"- {_escape_html(representative.title)}", f"  {_escape_html(representative.url)}"]
    sources = ", ".join(sorted({_escape_html(entry.feed.title) for entry in group.entries}))
    return [
        f"- {_escape_html(representative.title)} ({len(group.entries)} items)",
        f"  Sources: {sources}",
        f"  {_escape_html(representative.url)}",
    ]


def _overflow_line(remaining_groups: int) -> str | None:
    if remaining_groups <= 0:
        return None
    noun = "item" if remaining_groups == 1 else "items"
    return f"... and {remaining_groups} more digest {noun}"


def coalesce_digest_items(entries: list[Entry]) -> list[Entry]:
    seen = set()
    result = []
    for entry in entries:
        key = (entry.title.strip().lower(), entry.url.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(entry)
    return result


def _format_content_preview(content: str | None) -> str:
    preview = _content_preview(content)
    if not preview:
        return ""
    return f"\n{_escape_html(preview)}"


def _content_preview(content: str | None, limit: int = 280) -> str:
    if not content:
        return ""
    text = re.sub(r"<[^>]+>", " ", unescape(content))
    text = " ".join(text.split())
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
