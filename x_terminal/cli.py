from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .config import ConfigError, load_config


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="x-terminal",
        description="Live, categorized X (Twitter) feed in your terminal.",
    )
    parser.add_argument(
        "-c",
        "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run with simulated tweets (no API credentials needed)",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists() and args.mock:
        # Mock mode should work out of the box - fall back to the example config.
        example = Path(__file__).resolve().parent.parent / "config.example.yaml"
        if example.exists():
            config_path = example

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        sys.exit(f"Config error: {exc}")

    mock = args.mock
    token = os.environ.get(config.bearer_token_env, "")
    if not mock and not token:
        print(
            f"No bearer token found in ${config.bearer_token_env} - "
            "starting in MOCK mode.\n"
            f"Set the token to go live:  export {config.bearer_token_env}=...\n",
            file=sys.stderr,
        )
        mock = True

    if mock:
        from .mock import MockFeedClient

        client = MockFeedClient()
    else:
        from .client import XFeedClient

        client = XFeedClient(token, config)

    from .app import XTerminalApp

    XTerminalApp(config, client, mock=mock).run()


if __name__ == "__main__":
    main()
