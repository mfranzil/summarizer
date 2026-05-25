from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib.error import HTTPError
import urllib.parse
import urllib.request

from .config import Target
from .models import Entry


@dataclass(frozen=True)
class ForumTopic:
    message_thread_id: int
    name: str


class TelegramAPIError(RuntimeError):
    def __init__(self, method: str, error_code: int | None, description: str, parameters: dict | None = None) -> None:
        super().__init__(f"Telegram {method} failed: {description}")
        self.method = method
        self.error_code = error_code
        self.description = description
        self.parameters = parameters or {}


class TelegramClient:
    def __init__(self, bot_token: str) -> None:
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        prefix = bot_token.split(":", 1)[0]
        self.bot_id = int(prefix) if prefix.isdigit() else None
        self._last_request_at = 0.0

    def send_message(self, target: Target, text: str) -> None:
        payload = {
            "chat_id": target.chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
        if target.message_thread_id is not None:
            payload["message_thread_id"] = target.message_thread_id
        self._request("sendMessage", payload)

    def send_entry(self, target: Target, text: str, entry: Entry) -> None:
        payload = {
            "chat_id": target.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": json.dumps({"is_disabled": False, "url": entry.url}),
            "reply_markup": json.dumps(_entry_reply_markup(entry)),
        }
        if target.message_thread_id is not None:
            payload["message_thread_id"] = target.message_thread_id
        self._request("sendMessage", payload)

    def create_forum_topic(self, chat_id: str, name: str) -> ForumTopic:
        result = self._request(
            "createForumTopic",
            {
                "chat_id": chat_id,
                "name": name,
            },
        )
        return ForumTopic(
            message_thread_id=int(result["message_thread_id"]),
            name=result["name"],
        )

    def delete_forum_topic(self, chat_id: str, message_thread_id: int) -> None:
        try:
            self._request(
                "deleteForumTopic",
                {
                    "chat_id": chat_id,
                    "message_thread_id": message_thread_id,
                },
            )
        except TelegramAPIError as exc:
            if exc.error_code == 400 and "topic_id_invalid" in exc.description.lower():
                return
            raise

    def get_recent_forum_topics(self, chat_id: str) -> list[ForumTopic]:
        updates = self._request(
            "getUpdates",
            {
                "limit": 100,
                "allowed_updates": json.dumps(["message"]),
            },
        )
        topics = []
        for update in updates:
            message = update.get("message") or {}
            created = message.get("forum_topic_created")
            sender = message.get("from") or {}
            message_chat_id = message.get("chat", {}).get("id")
            thread_id = message.get("message_thread_id")
            if created is None or thread_id is None:
                continue
            if str(message_chat_id) != str(chat_id):
                continue
            if self.bot_id is not None and int(sender.get("id", 0)) != self.bot_id:
                continue
            topics.append(ForumTopic(message_thread_id=int(thread_id), name=created.get("name", "")))
        return topics

    def _request(self, method: str, payload: dict) -> dict:
        retry_delay = 1.0
        for _ in range(5):
            self._wait_for_slot()
            body = urllib.parse.urlencode(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/{method}",
                data=body,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    self._last_request_at = time.monotonic()
                    data = json.loads(resp.read().decode("utf-8"))
            except HTTPError as exc:
                self._last_request_at = time.monotonic()
                response = exc.read().decode("utf-8", errors="replace")
                retry_after = _retry_after_seconds(response)
                if exc.code == 429 and retry_after is not None:
                    time.sleep(retry_after)
                    continue
                raise _telegram_api_error(method, response, fallback_error_code=exc.code) from exc

            if data.get("ok"):
                return data["result"]

            retry_after = _retry_after_seconds(data)
            if data.get("error_code") == 429 and retry_after is not None:
                time.sleep(retry_after)
                continue
            raise _telegram_api_error(method, data)

        raise TelegramAPIError(method, 429, "retry limit exceeded")

    def _wait_for_slot(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        minimum_interval = 1.0
        if elapsed < minimum_interval:
            time.sleep(minimum_interval - elapsed)


def _retry_after_seconds(payload: str | dict) -> int | None:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return None
    parameters = payload.get("parameters") or {}
    retry_after = parameters.get("retry_after")
    if retry_after is None:
        return None
    return max(1, int(retry_after))


def _telegram_api_error(method: str, payload: str | dict, fallback_error_code: int | None = None) -> TelegramAPIError:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return TelegramAPIError(method, fallback_error_code, payload)
    return TelegramAPIError(
        method,
        payload.get("error_code", fallback_error_code),
        payload.get("description", str(payload)),
        payload.get("parameters"),
    )


def _entry_reply_markup(entry: Entry) -> dict:
    buttons = [[{"text": "Open", "url": entry.url}]]
    if entry.comments_url:
        buttons[0].append({"text": "Comments", "url": entry.comments_url})
    return {"inline_keyboard": buttons}
