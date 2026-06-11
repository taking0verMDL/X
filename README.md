# X Terminal

A live terminal dashboard for your X (Twitter) feed. You define categories
(AI, Markets, Tech News, ...) and the accounts that belong to each one; the
app polls the X API and streams new tweets into per-category tabs as they
arrive, with unread counters and a combined **All** firehose tab — so you
catch news the moment it drops.

## Quick start (no API key needed)

```bash
pip install -e .
x-terminal --mock
```

Mock mode runs the full UI with simulated tweets so you can try the layout
and keybindings immediately.

## Going live

1. Get an X API v2 bearer token (the recent-search endpoint used here
   requires the **Basic** plan or higher).
2. Copy the example config and fill in your categories and accounts:

   ```bash
   cp config.example.yaml config.yaml
   ```

3. Export your token and run:

   ```bash
   export X_BEARER_TOKEN="your-token-here"
   x-terminal
   ```

## Configuration

Everything lives in `config.yaml` — see `config.example.yaml` for a
commented template. The essentials:

```yaml
poll_interval: 60        # seconds between polls per category
categories:
  - name: AI
    color: cyan
    accounts: [AnthropicAI, OpenAI, GoogleDeepMind]
  - name: Markets
    color: green
    accounts: [DeItaone, unusual_whales]
```

Each category becomes one search query (`from:a OR from:b ...`), so an
account listed in two categories shows up in both. Long account lists are
automatically split across multiple queries.

**Rate limits:** the Basic plan allows 60 recent-search requests per
15 minutes. Keep `categories × (900 / poll_interval) ≤ 60` — e.g. 4
categories at a 60-second interval. The app staggers category polls and
backs off automatically when it hits a 429.

## Keys

| Key | Action |
| --- | --- |
| `q` | Quit |
| `r` | Refresh all categories now |
| `Tab` / arrows | Move between category tabs |

Tweets show a clickable `x.com` link (in terminals that support hyperlinks).
Tab labels show an unread count for categories you're not currently viewing,
and the terminal bell rings when new tweets land.
