# Telegram Feed Router

Local Miniflux-to-Telegram delivery service.

This MVP:

- polls Miniflux via API token
- discovers feeds from Miniflux
- routes by feed title
- supports `direct`, `digest`, and `mute` policies
- auto-creates Telegram forum topics per feed
- supports dry-run mode
- persists local state
- sends to Telegram chats or topics
- formats direct messages with previews and inline buttons

## Files

- `config.example.json`: example configuration
- `src/feed_router/`: implementation
- `tests/`: unit tests

## Run

```bash
python3 -m src.feed_router.cli --config config.local.json run-once
```

Set the log level explicitly when needed:

```bash
python3 -m src.feed_router.cli --config config.local.json --log-level DEBUG run-once
```

Use a forum-enabled Telegram supergroup and make the bot an admin with topic management rights.
Bots can't create new chats or channels, but they can create forum topics inside an existing chat.

For a simple loop:

```bash
python3 -m src.feed_router.cli --config config.local.json run-loop
```

To delete recent bot-created forum topics in the configured chat:

```bash
python3 -m src.feed_router.cli --config config.local.json cleanup-topics
```

To update existing topic icons in place based on the current category mapping:

```bash
python3 -m src.feed_router.cli --config config.local.json sync-topic-icons
```

To see what would be sent without calling Telegram:

```bash
python3 -m src.feed_router.cli --config config.local.json --dry-run run-once
```

## Docker

Build locally:

```bash
docker build -t miniflux-telegram-router .
```

Example `docker-compose.yml` service using GHCR:

```yaml
services:
  miniflux-telegram-router:
    image: ghcr.io/<owner>/summarizer:latest
    restart: unless-stopped
    command: ["--config", "/data/config.local.json", "--log-level", "INFO", "run-loop"]
    volumes:
      - ./config.local.json:/data/config.local.json:ro
      - ./state:/data/state
```

Your config should use a state path under the mounted volume, for example `/data/state/router-state.json`.

Dry-run still calls Miniflux so it needs valid Miniflux credentials.
It skips Telegram delivery and does not write router state.

## Notes

- Feed matching is by exact Miniflux feed title.
- `telegram.chat_id` is the default destination; per-feed topics are created automatically and cached in state.
- New topics get a category-based Telegram topic icon when the Miniflux category maps to one of Telegram's allowed forum-topic emoji stickers.
- Topic IDs are saved immediately after creation, and recent bot-created topics are reused when possible if local state is missing.
- Policies are meant to be overrides for `mute`, `digest`, or rare custom targets.
- Telegram requests are paced and honor Bot API `retry_after` backoff on `429` responses.
- Direct delivery uses HTML formatting, Telegram link previews, an `Open` button, and a `Comments` button when Miniflux provides `comments_url`.
- Logging is enabled by default at `INFO` level and can be raised to `DEBUG` with `--log-level DEBUG`.
- Digest messages are grouped per configured policy and collapse similar titles into one digest item.
- State is stored locally as JSON.
- No server-side changes are required.
