from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

import httpx

from .models import Category, Config, Tweet

API_BASE = "https://api.x.com/2"
# Basic tier query length limit for /tweets/search/recent.
MAX_QUERY_LEN = 512

TWEET_FIELDS = "created_at,public_metrics,author_id"
EXPANSIONS = "author_id"
USER_FIELDS = "username,name"


class XClientError(Exception):
    pass


def build_queries(category: Category, config: Config) -> list[str]:
    """Build recent-search queries for a category, chunking the account list
    so each query stays under the API's length limit."""
    suffix = ""
    if config.exclude_retweets:
        suffix += " -is:retweet"
    if config.exclude_replies:
        suffix += " -is:reply"

    queries: list[str] = []
    chunk: list[str] = []

    def flush() -> None:
        if chunk:
            queries.append("(" + " OR ".join(f"from:{a}" for a in chunk) + ")" + suffix)

    for account in category.accounts:
        candidate = chunk + [account]
        query = "(" + " OR ".join(f"from:{a}" for a in candidate) + ")" + suffix
        if len(query) > MAX_QUERY_LEN and chunk:
            flush()
            chunk = [account]
        else:
            chunk = candidate
    flush()
    return queries


class XFeedClient:
    """Polls the X API v2 recent-search endpoint, one query per category,
    tracking since_id so each poll only returns new tweets."""

    def __init__(self, bearer_token: str, config: Config) -> None:
        self._config = config
        self._http = httpx.AsyncClient(
            base_url=API_BASE,
            headers={"Authorization": f"Bearer {bearer_token}"},
            timeout=httpx.Timeout(15.0),
        )
        # since_id per (category, query index)
        self._since: dict[tuple[str, int], str] = {}
        # When rate-limited, do not call the API again until this time.
        self._blocked_until: float = 0.0

    async def close(self) -> None:
        await self._http.aclose()

    @property
    def rate_limited_for(self) -> float:
        """Seconds remaining on a rate-limit block (0 if not blocked)."""
        return max(0.0, self._blocked_until - time.monotonic())

    async def fetch_category(self, category: Category) -> list[Tweet]:
        """Fetch tweets newer than the last poll for one category."""
        if self.rate_limited_for > 0:
            return []

        tweets: list[Tweet] = []
        queries = build_queries(category, self._config)
        for i, query in enumerate(queries):
            key = (category.name, i)
            params: dict[str, str] = {
                "query": query,
                "max_results": "50",
                "tweet.fields": TWEET_FIELDS,
                "expansions": EXPANSIONS,
                "user.fields": USER_FIELDS,
            }
            if key in self._since:
                params["since_id"] = self._since[key]

            resp = await self._http.get("/tweets/search/recent", params=params)

            if resp.status_code == 429:
                reset = resp.headers.get("x-rate-limit-reset")
                wait = 60.0
                if reset and reset.isdigit():
                    wait = max(5.0, int(reset) - time.time())
                self._blocked_until = time.monotonic() + wait
                return tweets
            if resp.status_code == 401:
                raise XClientError(
                    "X API returned 401 Unauthorized - check your bearer token."
                )
            if resp.status_code == 403:
                raise XClientError(
                    "X API returned 403 Forbidden - your API plan may not include "
                    "the recent-search endpoint."
                )
            resp.raise_for_status()

            payload = resp.json()
            data = payload.get("data") or []
            users = {
                u["id"]: u for u in (payload.get("includes", {}).get("users") or [])
            }
            if data:
                self._since[key] = max(data, key=lambda t: int(t["id"]))["id"]

            for item in data:
                user = users.get(item.get("author_id"), {})
                metrics = item.get("public_metrics") or {}
                tweets.append(
                    Tweet(
                        id=item["id"],
                        author_handle=user.get("username", "unknown"),
                        author_name=user.get("name", "Unknown"),
                        text=item.get("text", ""),
                        created_at=_parse_time(item.get("created_at")),
                        category=category.name,
                        likes=metrics.get("like_count", 0),
                        retweets=metrics.get("retweet_count", 0),
                        replies=metrics.get("reply_count", 0),
                        quotes=metrics.get("quote_count", 0),
                    )
                )
            # Be gentle between chunked requests for the same category.
            if i < len(queries) - 1:
                await asyncio.sleep(1.0)

        tweets.sort(key=lambda t: t.created_at)
        return tweets


def _parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
