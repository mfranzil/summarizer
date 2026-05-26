from __future__ import annotations

import argparse
import logging

from .config import load_config
from .service import RouterService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run-once")
    sub.add_parser("run-loop")
    sub.add_parser("cleanup-topics")
    sub.add_parser("sync-topic-icons")
    return parser


def configure_logging(level_name: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level_name.upper()),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.log_level)
    config = load_config(args.config)
    service = RouterService(config, dry_run=args.dry_run)
    if args.command == "run-once":
        service.run_once()
        return
    if args.command == "run-loop":
        service.run_loop()
        return
    if args.command == "cleanup-topics":
        service.cleanup_topics()
        return
    if args.command == "sync-topic-icons":
        service.sync_topic_icons()
        return
    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
