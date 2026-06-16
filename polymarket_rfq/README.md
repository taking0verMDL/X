# Polymarket Combos RFQ Maker

A market-maker bot that answers [Polymarket Combos](https://docs.polymarket.com/market-makers/combos)
**request-for-quote (RFQ)** auctions. It connects to the RFQ gateway over
WebSocket, receives quote requests, prices them, and submits signed quotes
inside the ~400ms window.

## How RFQ works (the loop you're joining)

1. A user creates an unsigned request for a combo price.
2. The gateway broadcasts it to connected makers (you).
3. Makers submit **signed quotes within ~400ms**.
4. The best quote is returned to the user, who has ~10s to accept.
5. Optional **Last Look**: you get ~1s to confirm before execution.
6. The system executes the accepted combo on-chain.

## What this bot does (and doesn't) do

- **Does**: authenticate as a maker, normalise incoming quote requests, apply a
  configurable spread around a reference price, clamp/size the quote, submit it,
  and (optionally) handle Last Look + log execution updates.
- **Doesn't**: compute a real fair value. Pricing is a **config-driven stub** —
  you provide a static `reference` per combo. `PricingEngine.reference_price`
  in `pricing.py` is the single place to plug in live pricing (e.g. summing
  underlying leg mids) before you trade real size.

The bot only quotes combos explicitly listed in your config; everything else is
skipped. That's a safety default, not a limitation.

## Setup

```bash
cd polymarket_rfq
pip install -e .
cp config.example.yaml config.yaml   # then edit your combos
```

Export your secrets (never put them in the YAML):

```bash
export PRIVATE_KEY="0x..."
export POLYMARKET_WALLET_ADDRESS="0x..."
export POLYMARKET_API_KEY="..."
export POLYMARKET_API_SECRET="..."
export POLYMARKET_API_PASSPHRASE="..."
```

Validate everything before connecting:

```bash
polymarket-rfq --check
```

Run the maker:

```bash
polymarket-rfq            # uses ./config.yaml
polymarket-rfq -c my.yaml
```

## Configuration

See `config.example.yaml` for the commented template. Key knobs:

| Field | Meaning |
| --- | --- |
| `quote_source` | `collateral` (pUSD) or `inventory` (existing combo positions) |
| `default_spread` | full spread around reference; `0.04` = ±0.02 |
| `max_quote_size` | hard cap on size you'll quote (larger requests → partial fill) |
| `min_price`/`max_price` | clamp band so a bad reference can't quote <0 or >1 |
| `last_look` | re-confirm a selected quote before it executes |
| `combos[]` | per-combo `reference`, optional `spread`/`max_size`, `enabled` |

## ⚠️ Before trading real size

- The Python SDK surface (event classes, the relayer-key constructor, Last
  Look / execution event shapes) is written best-effort against the docs, which
  are mostly TypeScript. **Verify the symbol names** in `maker.py._build_client`
  against the `polymarket-client` version you install, and test against
  staging/testnet first.
- Replace the static `reference` stub with a live fair-value source.
- Add a real staleness/inventory check in
  `PricingEngine.should_confirm_last_look`.

## Tests

```bash
python -m pytest        # pricing logic, no SDK/network required
```
