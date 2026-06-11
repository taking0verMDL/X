"""Mock feed source so the terminal can run without X API credentials."""

from __future__ import annotations

import itertools
import random
from datetime import datetime, timezone

from .models import Category, Tweet

_SAMPLES = [
    "BREAKING: {topic} announcement expected within the hour, sources say.",
    "Just published a deep dive on {topic} - the implications are bigger than people think.",
    "Hot take: everyone is sleeping on {topic} right now.",
    "Live updates on {topic} as the situation develops. Thread below.",
    "New numbers out on {topic} this morning - well above expectations.",
    "Why {topic} matters more than the headlines suggest. 1/7",
    "Confirmed: the {topic} report is real. More details shortly.",
    "{topic} update: things are moving fast, refresh for the latest.",
]

_ids = itertools.count(1_800_000_000_000_000_000)


class MockFeedClient:
    """Mimics XFeedClient.fetch_category, emitting a few fake tweets per poll."""

    rate_limited_for = 0.0

    def __init__(self) -> None:
        self._first_poll: set[str] = set()

    async def close(self) -> None:
        pass

    async def fetch_category(self, category: Category) -> list[Tweet]:
        # First poll returns a small backlog; later polls trickle 0-2 tweets.
        if category.name not in self._first_poll:
            self._first_poll.add(category.name)
            count = random.randint(3, 6)
        else:
            count = random.choice([0, 0, 1, 1, 2])

        tweets = []
        for _ in range(count):
            handle = random.choice(category.accounts)
            tweets.append(
                Tweet(
                    id=str(next(_ids)),
                    author_handle=handle,
                    author_name=handle,
                    text=random.choice(_SAMPLES).format(topic=category.name),
                    created_at=datetime.now(timezone.utc),
                    category=category.name,
                    likes=random.randint(0, 5000),
                    retweets=random.randint(0, 800),
                    replies=random.randint(0, 300),
                )
            )
        return tweets
