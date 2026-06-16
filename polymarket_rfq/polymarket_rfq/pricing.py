"""Pricing engine for the RFQ maker.

This is the heart of the bot --- given an incoming quote request, decide
whether to quote and at what price/size. The default implementation is a
deliberately conservative *config-driven stub*: it quotes a fixed spread
around a static reference price you supply per combo, and skips anything it
doesn't recognise.

Replace ``PricingEngine.reference_price`` with a live fair-value source
(e.g. summing underlying leg mids from the CLOB) before trading real size.
Everything else --- spread application, clamping, sizing, BUY/SELL handling
--- can stay as is.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from polymarket_rfq.config import Config

log = logging.getLogger(__name__)

# Direction of the *taker's* request.
BUY = "BUY"
SELL = "SELL"


@dataclass(frozen=True)
class QuoteRequest:
    """A quote request normalised out of the SDK's event object.

    The maker layer (maker.py) is responsible for mapping whatever the
    installed SDK emits into this shape, so pricing stays SDK-agnostic.
    """

    rfq_id: str
    condition_id: str
    direction: str  # BUY or SELL (taker's side on YES)
    requested_size: Decimal


@dataclass(frozen=True)
class QuoteDecision:
    """The maker's answer: a price+size, or a skip with a reason."""

    price: Decimal | None
    size: Decimal | None
    skip_reason: str | None = None

    @property
    def should_quote(self) -> bool:
        return self.price is not None and self.size is not None

    @classmethod
    def skip(cls, reason: str) -> "QuoteDecision":
        return cls(price=None, size=None, skip_reason=reason)


class PricingEngine:
    def __init__(self, config: Config) -> None:
        self.config = config

    def reference_price(self, condition_id: str) -> Decimal | None:
        """Fair value for the YES side of this combo, or None if unknown.

        STUB: returns the static `reference` from config. Swap this out for a
        live source (leg-sum, external model, ...) when you're ready.
        """
        combo = self.config.combos.get(condition_id.lower())
        if combo is None or not combo.enabled:
            return None
        return combo.reference

    def _clamp(self, price: Decimal) -> Decimal:
        return max(self.config.min_price, min(self.config.max_price, price))

    def decide(self, req: QuoteRequest) -> QuoteDecision:
        combo = self.config.combos.get(req.condition_id.lower())
        if combo is None:
            return QuoteDecision.skip(f"combo {req.condition_id} not configured")
        if not combo.enabled:
            return QuoteDecision.skip(f"combo {req.condition_id} disabled")

        reference = self.reference_price(req.condition_id)
        if reference is None:
            return QuoteDecision.skip(f"no reference price for {req.condition_id}")

        spread = combo.spread if combo.spread is not None else self.config.default_spread
        half = spread / 2

        # Quote on the side that's favourable to us:
        #   taker BUYs YES  -> we SELL YES -> quote the ask (reference + half)
        #   taker SELLs YES -> we BUY YES  -> quote the bid (reference - half)
        if req.direction == BUY:
            price = reference + half
        elif req.direction == SELL:
            price = reference - half
        else:
            return QuoteDecision.skip(f"unknown direction {req.direction!r}")

        price = self._clamp(price)

        max_size = combo.max_size if combo.max_size is not None else self.config.max_quote_size
        # Partial fill: never quote more than our configured cap.
        size = min(req.requested_size, max_size)
        if size <= 0:
            return QuoteDecision.skip("max size is zero")

        log.info(
            "Quoting %s %s @ %s x %s (ref=%s, spread=%s)",
            req.direction,
            req.condition_id,
            price,
            size,
            reference,
            spread,
        )
        return QuoteDecision(price=price, size=size)

    def should_confirm_last_look(self, req: QuoteRequest, decision: QuoteDecision) -> bool:
        """Last Look hook: re-check before a selected quote executes.

        STUB: always confirms. Add a staleness/inventory check here --- e.g.
        re-fetch the reference and decline if it moved beyond your spread.
        """
        return True
