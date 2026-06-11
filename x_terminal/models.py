from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Tweet:
    id: str
    author_handle: str
    author_name: str
    text: str
    created_at: datetime
    category: str
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    quotes: int = 0

    @property
    def url(self) -> str:
        return f"https://x.com/{self.author_handle}/status/{self.id}"

    @property
    def age(self) -> str:
        """Compact relative age like 5s / 3m / 2h / 4d."""
        delta = datetime.now(timezone.utc) - self.created_at
        seconds = max(0, int(delta.total_seconds()))
        if seconds < 60:
            return f"{seconds}s"
        if seconds < 3600:
            return f"{seconds // 60}m"
        if seconds < 86400:
            return f"{seconds // 3600}h"
        return f"{seconds // 86400}d"


@dataclass
class Category:
    name: str
    accounts: list[str]
    color: str = "cyan"


@dataclass
class Config:
    categories: list[Category]
    bearer_token_env: str = "X_BEARER_TOKEN"
    poll_interval: float = 60.0
    exclude_retweets: bool = True
    exclude_replies: bool = False
    max_tweets_per_category: int = 200
    extra: dict = field(default_factory=dict)
