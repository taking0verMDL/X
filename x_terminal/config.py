from __future__ import annotations

from pathlib import Path

import yaml

from .models import Category, Config


class ConfigError(Exception):
    pass


def load_config(path: str | Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise ConfigError(
            f"Config file not found: {path}\n"
            "Copy config.example.yaml to config.yaml and edit it."
        )

    with path.open() as f:
        raw = yaml.safe_load(f) or {}

    raw_categories = raw.get("categories") or []
    if not raw_categories:
        raise ConfigError("Config must define at least one category.")

    categories: list[Category] = []
    seen: set[str] = set()
    for entry in raw_categories:
        name = str(entry.get("name", "")).strip()
        if not name:
            raise ConfigError("Every category needs a non-empty 'name'.")
        if name.lower() in seen:
            raise ConfigError(f"Duplicate category name: {name}")
        seen.add(name.lower())

        accounts = [str(a).lstrip("@").strip() for a in (entry.get("accounts") or [])]
        accounts = [a for a in accounts if a]
        if not accounts:
            raise ConfigError(f"Category '{name}' has no accounts.")

        categories.append(
            Category(name=name, accounts=accounts, color=str(entry.get("color", "cyan")))
        )

    return Config(
        categories=categories,
        bearer_token_env=str(raw.get("bearer_token_env", "X_BEARER_TOKEN")),
        poll_interval=float(raw.get("poll_interval", 60)),
        exclude_retweets=bool(raw.get("exclude_retweets", True)),
        exclude_replies=bool(raw.get("exclude_replies", False)),
        max_tweets_per_category=int(raw.get("max_tweets_per_category", 200)),
    )
