"""Command-line entry point for the Polymarket RFQ maker."""

from __future__ import annotations

import argparse
import sys

from polymarket_rfq import __version__
from polymarket_rfq.config import ConfigError, load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="polymarket-rfq",
        description="Market-maker bot for Polymarket Combos RFQ.",
    )
    parser.add_argument(
        "-c",
        "--config",
        default="config.yaml",
        help="Path to the YAML config file (default: config.yaml).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate config + environment and print a summary, then exit "
        "without connecting.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    if args.check:
        enabled = [c for c in config.combos.values() if c.enabled]
        print("Config OK.")
        print(f"  ws_url       : {config.ws_url}")
        print(f"  quote_source : {config.quote_source}")
        print(f"  last_look    : {config.last_look}")
        print(f"  default_spread: {config.default_spread}")
        print(f"  price band   : [{config.min_price}, {config.max_price}]")
        print(f"  combos       : {len(config.combos)} ({len(enabled)} enabled)")
        for combo in config.combos.values():
            flag = "" if combo.enabled else " (disabled)"
            print(f"    - {combo.condition_id} ref={combo.reference}{flag}")
        return 0

    # Imported lazily so `--check` and `--help` work without the SDK installed.
    from polymarket_rfq.maker import run

    run(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
