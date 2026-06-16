"""The RFQ maker loop.

Connects to Polymarket's Combos RFQ gateway, receives quote-request events,
asks the PricingEngine what to quote, and submits signed quotes within the
~400ms window. Optionally handles Last Look confirmations and logs execution
updates.

NOTE ON THE SDK: Polymarket's docs give the Python entry points
(`AsyncSecureClient.create`, `client.open_rfq_session()`, `event.quote(...)`)
but most examples are TypeScript, so some symbol names below are best-effort.
The event-field access is therefore written defensively (`_field`) and the
SDK imports are isolated in `_build_client` so you have one place to adjust
names against the version you install. Run against the testnet/staging
gateway first.
"""

from __future__ import annotations

import asyncio
import logging
import os
from decimal import Decimal

from polymarket_rfq.config import Config
from polymarket_rfq.pricing import BUY, SELL, PricingEngine, QuoteRequest

log = logging.getLogger(__name__)


def _field(obj, *names, default=None):
    """Read the first present attribute (or mapping key) from `obj`.

    Tolerates the SDK exposing fields under camelCase or snake_case.
    """
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


def _normalize_request(event) -> QuoteRequest:
    """Map an SDK quote-request event onto our SDK-agnostic QuoteRequest."""
    direction = str(_field(event, "direction", default="")).upper()
    if direction not in (BUY, SELL):
        # Some SDKs use side=0/1 or BID/ASK; map the common cases.
        side = str(_field(event, "side", default="")).upper()
        direction = {"BID": SELL, "ASK": BUY, "0": BUY, "1": SELL}.get(side, direction)

    raw_size = _field(event, "requestedSize", "requested_size", "size", default="0")
    return QuoteRequest(
        rfq_id=str(_field(event, "rfqId", "rfq_id", "id", default="")),
        condition_id=str(_field(event, "conditionId", "condition_id", default="")),
        direction=direction,
        requested_size=Decimal(str(raw_size)),
    )


class RfqMaker:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.pricing = PricingEngine(config)
        # Keep quote references so we can cancel / correlate if needed.
        self._quotes: dict[str, object] = {}

    async def _build_client(self):
        """Construct and authenticate the Polymarket async client.

        Isolated so the exact SDK constructor lives in one place. Adjust the
        imports/kwargs to match your installed `polymarket-client` version.
        """
        from polymarket_client import AsyncSecureClient, RelayerApiKey  # type: ignore

        creds = self.config.credentials
        client = await AsyncSecureClient.create(
            private_key=creds.private_key,
            wallet=creds.wallet_address,
            api_key=RelayerApiKey(
                key=creds.api_key,
                secret=creds.api_secret,
                passphrase=creds.api_passphrase,
            ),
        )
        # One-time on-chain approvals so the maker can settle fills.
        await client.setup_trading_approvals()
        return client

    async def _quote_source_kwarg(self):
        """Return the kwargs to pass to event.quote() for inventory vs collateral."""
        if self.config.quote_source != "inventory":
            return {}
        from polymarket_client import RfqQuoteSource  # type: ignore

        return {"source": RfqQuoteSource.INVENTORY}

    async def _handle_quote_request(self, session, event) -> None:
        req = _normalize_request(event)
        decision = self.pricing.decide(req)
        if not decision.should_quote:
            log.info("Skipping RFQ %s: %s", req.rfq_id, decision.skip_reason)
            return

        kwargs = await self._quote_source_kwarg()
        try:
            reference = await event.quote(
                price=str(decision.price),
                size=str(decision.size),
                **kwargs,
            )
            if req.rfq_id:
                self._quotes[req.rfq_id] = reference
            log.info(
                "Submitted quote for RFQ %s: %s x %s",
                req.rfq_id,
                decision.price,
                decision.size,
            )
        except Exception:  # noqa: BLE001 - log and keep the session alive
            log.exception("Failed to submit quote for RFQ %s", req.rfq_id)

    async def _handle_confirmation(self, event) -> None:
        """Last Look: confirm or decline a selected quote."""
        req = _normalize_request(event)
        decision = self.pricing.decide(req)
        try:
            if decision.should_quote and self.pricing.should_confirm_last_look(req, decision):
                await event.confirm()
                log.info("Confirmed last-look for RFQ %s", req.rfq_id)
            else:
                await event.decline()
                log.info("Declined last-look for RFQ %s", req.rfq_id)
        except Exception:  # noqa: BLE001
            log.exception("Last-look handling failed for RFQ %s", req.rfq_id)

    def _handle_execution(self, event) -> None:
        log.info(
            "Execution update rfq=%s status=%s tx=%s",
            _field(event, "rfqId", "rfq_id", default="?"),
            _field(event, "status", default="?"),
            _field(event, "txHash", "tx_hash", default=""),
        )

    async def run(self) -> None:
        client = await self._build_client()
        log.info("Authenticated as maker; opening RFQ session...")

        async with client.open_rfq_session() as session:
            log.info("RFQ session open. Waiting for quote requests (Ctrl-C to stop).")
            async for event in session:
                etype = str(_field(event, "type", default="")).lower()
                cls = type(event).__name__.lower()

                if "quote_request" in etype or "quoterequest" in cls:
                    await self._handle_quote_request(session, event)
                elif "confirmation" in etype or "confirmation" in cls:
                    if self.config.last_look:
                        await self._handle_confirmation(event)
                elif "execution" in etype or "execution" in cls:
                    self._handle_execution(event)
                else:
                    log.debug("Unhandled event type=%r cls=%r", etype, cls)


def run(config: Config) -> None:
    """Synchronous entry point used by the CLI."""
    logging.basicConfig(
        level=os.environ.get("RFQ_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    maker = RfqMaker(config)
    try:
        asyncio.run(maker.run())
    except KeyboardInterrupt:
        log.info("Shutting down.")
