from __future__ import annotations

import asyncio
from datetime import datetime

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Static, TabbedContent, TabPane

from .models import Config, Tweet

ALL_TAB = "all"


def _tab_id(name: str) -> str:
    return "cat-" + "".join(c if c.isalnum() else "-" for c in name.lower())


class TweetCard(Static):
    """One tweet rendered as a compact card."""

    def __init__(self, tweet: Tweet, color: str) -> None:
        content = Text()
        content.append(f"@{tweet.author_handle}", style=f"bold {color}")
        content.append(
            f" ({tweet.author_name}) · {tweet.age} ago · "
            f"♥ {tweet.likes}  ↻ {tweet.retweets}\n",
            style="dim",
        )
        content.append(tweet.text)
        content.append("\n")
        content.append(tweet.url, style=f"dim link {tweet.url}")
        super().__init__(content)
        self.add_class("tweet-card")


class XTerminalApp(App):
    """Live, categorized X feed dashboard."""

    TITLE = "X Terminal"
    CSS_PATH = "app.tcss"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh now"),
    ]

    def __init__(self, config: Config, client, mock: bool = False) -> None:
        super().__init__()
        self._config = config
        self._client = client
        self._mock = mock
        self._poll_interval = 3.0 if mock else config.poll_interval
        self._colors = {c.name: c.color for c in config.categories}
        self._unread: dict[str, int] = {c.name: 0 for c in config.categories}
        self._seen_all: set[str] = set()
        self._refresh_now = asyncio.Event()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial=ALL_TAB):
            with TabPane("All", id=ALL_TAB):
                yield VerticalScroll(id=f"feed-{ALL_TAB}")
            for category in self._config.categories:
                with TabPane(category.name, id=_tab_id(category.name)):
                    yield VerticalScroll(id=f"feed-{_tab_id(category.name)}")
        yield Footer()
        yield Static(id="status-bar")

    def on_mount(self) -> None:
        if self._mock:
            self.sub_title = "MOCK MODE - set your bearer token for live data"
        self._set_status("Connecting…")
        for i, category in enumerate(self._config.categories):
            # Stagger category polls to spread API rate-limit usage.
            delay = i * (self._poll_interval / max(1, len(self._config.categories)))
            self.run_worker(
                self._poll_loop(category, delay), exclusive=False, exit_on_error=False
            )

    async def _poll_loop(self, category, initial_delay: float) -> None:
        await asyncio.sleep(initial_delay)
        while True:
            try:
                tweets = await self._client.fetch_category(category)
            except Exception as exc:  # noqa: BLE001 - surface, keep polling
                self._set_status(Text(f"{category.name}: {exc}", style="red"))
            else:
                if tweets:
                    self._add_tweets(category.name, tweets)
                blocked = self._client.rate_limited_for
                if blocked > 0:
                    self._set_status(
                        Text(
                            f"Rate limited - resuming in {int(blocked)}s",
                            style="yellow",
                        )
                    )
                else:
                    self._set_status(
                        Text(
                            f"Last update {datetime.now():%H:%M:%S} · "
                            f"polling every {int(self._poll_interval)}s"
                        )
                    )
            # Wait for the next tick, but wake immediately on manual refresh.
            try:
                await asyncio.wait_for(
                    self._refresh_now.wait(), timeout=self._poll_interval
                )
            except asyncio.TimeoutError:
                pass

    def _add_tweets(self, category_name: str, tweets: list[Tweet]) -> None:
        color = self._colors.get(category_name, "cyan")
        feed = self.query_one(f"#feed-{_tab_id(category_name)}", VerticalScroll)
        all_feed = self.query_one(f"#feed-{ALL_TAB}", VerticalScroll)
        active = self.query_one(TabbedContent).active

        # Newest first: mount each batch at the top, oldest of the batch last.
        for tweet in tweets:
            feed.mount(TweetCard(tweet, color), before=0)
            if tweet.id not in self._seen_all:
                self._seen_all.add(tweet.id)
                all_feed.mount(TweetCard(tweet, color), before=0)

        self._trim(feed)
        self._trim(all_feed)

        if active != _tab_id(category_name):
            self._unread[category_name] += len(tweets)
            self._update_tab_label(category_name)
        self.bell()

    def _trim(self, feed: VerticalScroll) -> None:
        cards = feed.query(TweetCard)
        excess = len(cards) - self._config.max_tweets_per_category
        for card in list(cards)[-excess:] if excess > 0 else []:
            card.remove()

    def _update_tab_label(self, category_name: str) -> None:
        tabs = self.query_one(TabbedContent)
        unread = self._unread[category_name]
        label = f"{category_name} ({unread})" if unread else category_name
        tabs.get_tab(_tab_id(category_name)).label = label

    def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        tab_id = event.pane.id or ""
        for name in self._unread:
            if _tab_id(name) == tab_id and self._unread[name]:
                self._unread[name] = 0
                self._update_tab_label(name)

    def _set_status(self, text: str | Text) -> None:
        self.query_one("#status-bar", Static).update(text)

    def action_refresh(self) -> None:
        self._refresh_now.set()
        self._refresh_now = asyncio.Event()
        self._set_status("Refreshing…")

    async def on_unmount(self) -> None:
        await self._client.close()
