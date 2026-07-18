# Miniflux Telegram Router

Miniflux is good at collecting feeds. Telegram is good for viewing them.
Unfortunately, Miniflux does not make a good job in delivering feeds to a
Telegram group. This project connects the two: it polls Miniflux, applies a
small set of per-feed rules, and delivers entries to forum
topics inside that chat.

The service does not modify Miniflux, does not expose an HTTP endpoint, nor
wants to be yet another feed reader. Using a simple JSON file, it reads the
Miniflux API token and the Telegram bot token, and uses them to fetch new
entries and send them to the configured chat, automatically creating topics for
feeds that do not have one.

## But why I need it?

Miniflux by default has a Telegram integration that sends each new entry to a
single chat.  As of July 2026, there is a "topic ID" option, but it simply sends
all entries to the same topic. This is not ideal for feeds that have many
entries per day, or for feeds that are not related to each other.

This project addresses that by allowing per-feed policies.
Each feed is matched by its exact Miniflux title. A feed can be sent one entry
at a time (`direct`), collected into periodic summaries (`digest`), or ignored
(`mute`). When automatic topics are enabled, a topic is created for each feed
and its ID is saved in the state file so restarts do not create duplicates.

Direct messages use Telegram HTML formatting, link previews, and buttons for the
entry and, when available, its comments (e.g., Hacker News). Digest messages
group similar titles together and send a single message with a list of links.
The digest title can be customized, and the similarity threshold can be adjusted
to control how many entries are grouped together.  When the number of entries
exceeds the configured maximum, the oldest entries are dropped from the digest.

## Requirements

- Python 3.10 or newer, or Docker
- A Miniflux instance and an API token
- A Telegram bot
- A Telegram forum-enabled supergroup where the bot can create and manage topics

The bot cannot create the group itself. Add it to an existing supergroup and
give it the permissions needed to manage topics and send messages.

## Setup with Python

Create a virtual environment and install the project:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

Create a private configuration file and fill in the credentials:

```bash
cp config.example.json config.local.json
```

The example starts with `defaults.mode` set to `mute`, which is a safe choice
for a new installation. Add a policy for each feed that should be delivered.
Feed titles must match Miniflux exactly. Then make a first one-shot run:

```bash
feed-router --config config.local.json run-once
```

Once that works, use the polling loop:

```bash
feed-router --config config.local.json run-loop
```

The module form is also available when running directly from the repository:

```bash
python -m src.feed_router.cli --config config.local.json run-once
```

## Configuration

A sample configuration is shown in `config.example.json`. Some notes:

- `telegram.chat_id` is the default destination. A policy can override it with
  a `target` containing `chat_id` and, optionally, `message_thread_id`.
- `telegram.auto_create_topics` controls whether feeds without an explicit
  thread are assigned their own forum topic.
- `defaults.mode` is used for feeds without a policy. It can be set to `mute` (= ignore),
  `direct` (= send each entry immediately), or `digest` (= collect entries into a summary).
- A digest policy requires `window_hours` and `max_items`. Its optional title
  and similarity threshold control the resulting summary.
- `state.path` should point to persistent storage. Losing the state file can:
  - Make old entries be delivered again, and
  - Recreate topics that already exist (the topic name is not an ID, and the service does not check for duplicates)


### Topic icons

Topic icons are optional Telegram custom emojis. Map an exact Miniflux category
title to its Telegram custom-emoji ID in the top-level `category_icons` object:

```json
{
  "category_icons": {
    "News": "5434144690511290129"
  }
}
```

To obtain the ID of a custom emoji, send it to the bot and read the
`message.entities` field in the JSON update. The ID is a 19-digit number.
Categories without a map are left without a custom icon. Existing topics can be
updated after changing the mapping with:

```bash
feed-router --config config.local.json sync-topic-icons
```

## Commands and dry runs

`run-once` polls Miniflux once, `run-loop` repeats it at the configured
interval, `cleanup-topics` deletes recent bot-created topics in the default
chat, and `sync-topic-icons` updates cached topics using the category map.

Use `--log-level DEBUG` when diagnosing feed matching or topic reuse:

```bash
feed-router --config config.local.json --log-level DEBUG run-once
```

Dry-run mode still reads Miniflux, but prints planned deliveries and topic
operations instead of calling Telegram. It does not write router state:

```bash
feed-router --config config.local.json --dry-run run-once
```

## Docker

Build the image locally:

```bash
docker build -t miniflux-telegram-router .
```

The `config.local.json` and the `/state` directory can be mounted into the container
to persist the state:

```bash
mkdir -p state
docker run --rm \
  -v "$PWD/config.local.json:/data/config.local.json:ro" \
  -v "$PWD/state:/data/state" \
  miniflux-telegram-router \
  --config /data/config.local.json run-once
```

For continuous operation, use `--restart unless-stopped` and replace
`run-once` with `run-loop`. The image published by GitHub Actions is available
at `ghcr.io/mfranzil/summarizer`. No tags are published yet, so use `:master` to get the latest build.

## Development

The runtime has no third-party Python dependencies. Run the test suite with
the standard library:

```bash
python -m unittest discover -s tests -v
```

The project is available under the MIT license. Contributions should keep the
footprint small (ideally, I would like to submit this to the main Miniflux
repository) and include a regression test for changes to routing or message
formatting.