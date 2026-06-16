"""Tests for the pricing engine. Pure logic --- no SDK or network."""

from decimal import Decimal

from polymarket_rfq.config import ComboConfig, Config, Credentials
from polymarket_rfq.pricing import BUY, SELL, PricingEngine, QuoteRequest


def make_config(**combo_overrides) -> Config:
    combo_overrides.setdefault("reference", Decimal("0.45"))
    combo = ComboConfig(
        condition_id="0xabc",
        **combo_overrides,
    )
    return Config(
        quote_source="collateral",
        default_spread=Decimal("0.04"),
        max_quote_size=Decimal("50"),
        min_price=Decimal("0.02"),
        max_price=Decimal("0.98"),
        last_look=True,
        ws_url="wss://example/ws/rfq",
        combos={combo.condition_id.lower(): combo},
        credentials=Credentials("k", "w", "a", "s", "p"),
    )


def req(direction, size="10", cid="0xabc") -> QuoteRequest:
    return QuoteRequest(
        rfq_id="r1",
        condition_id=cid,
        direction=direction,
        requested_size=Decimal(size),
    )


def test_buy_quotes_ask_above_reference():
    eng = PricingEngine(make_config())
    d = eng.decide(req(BUY))
    # taker buys YES -> we sell at ref + half_spread = 0.45 + 0.02
    assert d.should_quote
    assert d.price == Decimal("0.47")
    assert d.size == Decimal("10")


def test_sell_quotes_bid_below_reference():
    eng = PricingEngine(make_config())
    d = eng.decide(req(SELL))
    assert d.price == Decimal("0.43")


def test_per_combo_spread_override():
    eng = PricingEngine(make_config(spread=Decimal("0.10")))
    d = eng.decide(req(BUY))
    assert d.price == Decimal("0.50")  # 0.45 + 0.05


def test_size_capped_to_max():
    eng = PricingEngine(make_config(max_size=Decimal("5")))
    d = eng.decide(req(BUY, size="100"))
    assert d.size == Decimal("5")


def test_price_clamped_into_band():
    # reference near 1 with a wide spread would exceed max_price without clamping
    eng = PricingEngine(make_config(reference=Decimal("0.99"), spread=Decimal("0.10")))
    d = eng.decide(req(BUY))
    assert d.price == Decimal("0.98")


def test_unconfigured_combo_is_skipped():
    eng = PricingEngine(make_config())
    d = eng.decide(req(BUY, cid="0xnope"))
    assert not d.should_quote
    assert "not configured" in d.skip_reason


def test_disabled_combo_is_skipped():
    eng = PricingEngine(make_config(enabled=False))
    d = eng.decide(req(BUY))
    assert not d.should_quote
    assert "disabled" in d.skip_reason


def test_unknown_direction_is_skipped():
    eng = PricingEngine(make_config())
    d = eng.decide(req("SIDEWAYS"))
    assert not d.should_quote
