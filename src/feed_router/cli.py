from __future__ import annotations

import argparse

from .config import load_config
from .service import RouterService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--dry-run", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run-once")
    sub.add_parser("run-loop")
    sub.add_parser("cleanup-topics")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
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
    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
