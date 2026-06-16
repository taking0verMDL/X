"""Configuration loading for the RFQ maker.

Pricing/behaviour lives in a YAML file; secrets live only in environment
variables. ``load_config`` resolves both and fails fast (with a clear message)
if anything required is missing, so the bot never starts half-configured.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

DEFAULT_WS_URL = "wss://combos-rfq-gateway-quoter.polymarket.com/ws/rfq"

# Default env var names; overridable via the config's `env:` block.
DEFAULT_ENV = {
    "private_key": "PRIVATE_KEY",
    "wallet_address": "POLYMARKET_WALLET_ADDRESS",
    "api_key": "POLYMARKET_API_KEY",
    "api_secret": "POLYMARKET_API_SECRET",
    "api_passphrase": "POLYMARKET_API_PASSPHRASE",
}


class ConfigError(Exception):
    """Raised when the config or environment is missing/invalid."""


@dataclass(frozen=True)
class Credentials:
    """Secrets pulled from the environment. Never logged."""

    private_key: str
    wallet_address: str
    api_key: str
    api_secret: str
    api_passphrase: str


@dataclass(frozen=True)
class ComboConfig:
    """Pricing parameters for a single combo we're willing to quote."""

    condition_id: str
    reference: Decimal
    spread: Decimal | None = None
    max_size: Decimal | None = None
    enabled: bool = True


@dataclass(frozen=True)
class Config:
    quote_source: str
    default_spread: Decimal
    max_quote_size: Decimal
    min_price: Decimal
    max_price: Decimal
    last_look: bool
    ws_url: str
    combos: dict[str, ComboConfig]  # keyed by lower-cased condition_id
    credentials: Credentials = field(repr=False)


def _to_decimal(value, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ConfigError(f"{field_name!r} is not a valid number: {value!r}") from exc


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise ConfigError(
            f"Required environment variable {name!r} is not set. "
            "Export your Polymarket secrets before starting the bot."
        )
    return val


def load_config(path: str | Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise ConfigError(
            f"Config file not found: {path}. "
            "Copy config.example.yaml to config.yaml and edit it."
        )

    raw = yaml.safe_load(path.read_text()) or {}

    env_names = {**DEFAULT_ENV, **(raw.get("env") or {})}
    credentials = Credentials(
        private_key=_require_env(env_names["private_key"]),
        wallet_address=_require_env(env_names["wallet_address"]),
        api_key=_require_env(env_names["api_key"]),
        api_secret=_require_env(env_names["api_secret"]),
        api_passphrase=_require_env(env_names["api_passphrase"]),
    )

    quote_source = str(raw.get("quote_source", "collateral")).lower()
    if quote_source not in ("collateral", "inventory"):
        raise ConfigError(
            f"quote_source must be 'collateral' or 'inventory', got {quote_source!r}"
        )

    combos: dict[str, ComboConfig] = {}
    for entry in raw.get("combos") or []:
        cid = entry.get("condition_id")
        if not cid:
            raise ConfigError("Every combo entry needs a 'condition_id'.")
        combo = ComboConfig(
            condition_id=cid,
            reference=_to_decimal(entry["reference"], f"combos[{cid}].reference"),
            spread=(
                _to_decimal(entry["spread"], f"combos[{cid}].spread")
                if entry.get("spread") is not None
                else None
            ),
            max_size=(
                _to_decimal(entry["max_size"], f"combos[{cid}].max_size")
                if entry.get("max_size") is not None
                else None
            ),
            enabled=bool(entry.get("enabled", True)),
        )
        combos[cid.lower()] = combo

    if not combos:
        raise ConfigError(
            "No combos configured. The bot only quotes combos listed under "
            "'combos:' --- add at least one before starting."
        )

    return Config(
        quote_source=quote_source,
        default_spread=_to_decimal(raw.get("default_spread", "0.04"), "default_spread"),
        max_quote_size=_to_decimal(raw.get("max_quote_size", "50"), "max_quote_size"),
        min_price=_to_decimal(raw.get("min_price", "0.02"), "min_price"),
        max_price=_to_decimal(raw.get("max_price", "0.98"), "max_price"),
        last_look=bool(raw.get("last_look", True)),
        ws_url=str(raw.get("ws_url", DEFAULT_WS_URL)),
        combos=combos,
        credentials=credentials,
    )
