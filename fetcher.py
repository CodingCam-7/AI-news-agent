"""
fetcher.py — Step 1 of the AI News Digest Agent.

Pulls recent AI stories from RSS feeds and Hacker News, dedupes them,
and prints a console report. Run directly with the green ▶ in PyCharm.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import feedparser
import requests

from config import RSS_FEEDS

# ── logging setup ────────────────────────────────────────────────────────────
# WARNING-level messages (e.g. broken feeds) go to stderr so they're visible
# without cluttering the main output.
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s  %(message)s",
)
logger = logging.getLogger(__name__)

# Items older than this are ignored.
LOOKBACK_DAYS = 7


# ── data model ───────────────────────────────────────────────────────────────

@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    published: Optional[datetime]   # None when the feed omits a date
    snippet: str                    # first ~200 chars of the summary


# ── helpers ──────────────────────────────────────────────────────────────────

def _cutoff() -> datetime:
    """Returns a timezone-aware datetime representing the start of our lookback window."""
    return datetime.now(tz=timezone.utc) - timedelta(days=LOOKBACK_DAYS)


def _parse_date(entry) -> Optional[datetime]:
    """
    feedparser stores parsed dates in entry.published_parsed (a time.struct_time).
    We convert it to a timezone-aware datetime so we can compare against _cutoff().
    Returns None if the field is missing or unparseable.
    """
    if not hasattr(entry, "published_parsed") or entry.published_parsed is None:
        return None
    try:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    except Exception:
        return None


def _snippet(entry) -> str:
    """Extract a short text preview from the feed entry's summary field."""
    raw = getattr(entry, "summary", "") or ""
    # Strip any embedded HTML tags with a simple approach — good enough for a snippet.
    import re
    text = re.sub(r"<[^>]+>", "", raw).strip()
    return text[:200]


# ── fetchers ─────────────────────────────────────────────────────────────────

def fetch_rss() -> list[NewsItem]:
    """
    Loops over RSS_FEEDS from config.py and parses each one with feedparser.
    Each feed is wrapped in its own try/except so a single bad feed can't
    crash the whole run — it just logs a warning and moves on.
    """
    cutoff = _cutoff()
    items: list[NewsItem] = []

    for source_name, url in RSS_FEEDS:
        try:
            # Fetch via requests so we get certifi's SSL bundle (avoids the
            # macOS Python SSL certificate issue where feedparser's built-in
            # urllib call can't verify certs against the system keychain).
            resp = requests.get(url, timeout=15, headers={"User-Agent": "AI-news-agent/1.0"})
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)

            # feedparser sets bozo=True when the XML is malformed.
            # We still attempt to read entries in case some came through.
            if feed.bozo and not feed.entries:
                logger.warning("Feed may be malformed (%s): %s", source_name, feed.bozo_exception)

            for entry in feed.entries:
                pub = _parse_date(entry)

                # Skip items outside our lookback window (None dates are kept).
                if pub is not None and pub < cutoff:
                    continue

                items.append(NewsItem(
                    title=getattr(entry, "title", "(no title)").strip(),
                    url=getattr(entry, "link", ""),
                    source=source_name,
                    published=pub,
                    snippet=_snippet(entry),
                ))

        except Exception as exc:
            logger.warning("Skipping feed '%s' — %s: %s", source_name, type(exc).__name__, exc)

    return items


def fetch_hackernews() -> list[NewsItem]:
    """
    Queries the Hacker News Algolia API for AI stories from the last 5 days
    with more than 50 points. No API key needed.

    API docs: https://hn.algolia.com/api
    """
    cutoff = _cutoff()
    # Convert cutoff to a Unix timestamp — that's what the API's numericFilters expects.
    cutoff_ts = int(cutoff.timestamp())

    url = (
        "https://hn.algolia.com/api/v1/search_by_date"
        f"?query=AI&tags=story"
        f"&numericFilters=points>50,created_at_i>{cutoff_ts}"
    )

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("Hacker News fetch failed — %s: %s", type(exc).__name__, exc)
        return []

    items: list[NewsItem] = []
    for hit in data.get("hits", []):
        # The story URL is in 'url'; for Ask HN / self-posts it may be None,
        # so we fall back to the HN thread link.
        story_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"

        # created_at_i is a Unix timestamp integer.
        ts = hit.get("created_at_i")
        pub = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None

        items.append(NewsItem(
            title=hit.get("title", "(no title)"),
            url=story_url,
            source="Hacker News",
            published=pub,
            snippet=hit.get("story_text") or "",   # self-posts only; empty for links
        ))

    return items


# ── orchestrator ─────────────────────────────────────────────────────────────

def fetch_all() -> list[NewsItem]:
    """Combine RSS + HN results, dedupe by URL, and sort newest first."""
    all_items = fetch_rss() + fetch_hackernews()

    # Dedupe: keep the first occurrence of each URL we encounter.
    seen: set[str] = set()
    unique: list[NewsItem] = []
    for item in all_items:
        if item.url and item.url not in seen:
            seen.add(item.url)
            unique.append(item)

    # Sort: items with a known date come first (newest first), then undated items.
    unique.sort(key=lambda i: i.published or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return unique


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    items = fetch_all()

    # --- summary header ---
    print(f"\n{'='*60}")
    print(f"  AI News Digest — {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  {len(items)} items")
    print(f"{'='*60}")

    # Count items per source for a quick sanity-check.
    from collections import Counter
    counts = Counter(i.source for i in items)
    print("\nItems per source:")
    for source, count in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {source:<20} {count}")

    # --- item list ---
    print(f"\n{'-'*60}")
    for item in items:
        date_str = item.published.strftime("%Y-%m-%d") if item.published else "no date"
        print(f"[{item.source}] {item.title}")
        print(f"  {date_str}  —  {item.url}")
        print()
