"""
ranker.py — Step 2 of the AI News Digest Agent.

Scores NewsItem objects against the TOPICS list in config.py and returns
them sorted by relevance. Run directly to see a ranked console report.
"""

from dataclasses import dataclass, field
from datetime import datetime

from config import TOPIC_ALIASES, TOPICS
from fetcher import NewsItem, fetch_all


@dataclass
class RankedItem:
    item: NewsItem
    score: float
    matched_topics: list[str] = field(default_factory=list)
    summary: str = ""  # populated by summarizer.py


def _phrases_for(topic: str) -> list[str]:
    """Return all search phrases for a topic: the topic itself plus any aliases."""
    return [topic] + TOPIC_ALIASES.get(topic, [])


def _score_item(item: NewsItem) -> tuple[float, list[str]]:
    """
    Check each topic (and its aliases) against the item's title and snippet.

    Title matches are worth 2 pts — titles are concise and high-signal.
    Snippet matches are worth 1 pt.
    A topic is counted at most once regardless of how many alias phrases hit.
    """
    title_lower = item.title.lower()
    snippet_lower = item.snippet.lower()

    total = 0.0
    matched: list[str] = []

    for topic in TOPICS:
        phrases = _phrases_for(topic)
        title_hit   = any(p.lower() in title_lower   for p in phrases)
        snippet_hit = any(p.lower() in snippet_lower for p in phrases)
        pts = (2.0 if title_hit else 0.0) + (1.0 if snippet_hit else 0.0)
        if pts > 0:
            total += pts
            matched.append(topic)

    return total, matched


def rank(items: list[NewsItem]) -> list[RankedItem]:
    """
    Score every item and return them sorted by score descending.
    Items with score 0 are kept at the bottom so nothing is silently dropped.
    Ties are broken by published date (newest first).
    """
    ranked = [RankedItem(item=i, score=s, matched_topics=m) for i, (s, m) in
              ((i, _score_item(i)) for i in items)]

    ranked.sort(
        key=lambda r: (
            r.score,
            r.item.published or datetime.min.replace(tzinfo=__import__("datetime").timezone.utc),
        ),
        reverse=True,
    )
    return ranked


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s  %(message)s")

    raw = fetch_all()
    results = rank(raw)

    scored = [r for r in results if r.score > 0]
    unscored = [r for r in results if r.score == 0]

    print(f"\n{'='*60}")
    print(f"  AI News Digest — ranked  |  {len(results)} items  ({len(scored)} matched topics)")
    print(f"{'='*60}")

    print(f"\n── Matched ({len(scored)}) ──────────────────────────────────────")
    for r in scored:
        date_str = r.item.published.strftime("%Y-%m-%d") if r.item.published else "no date"
        topics_str = ", ".join(r.matched_topics)
        print(f"[{r.score:.0f}pt] [{r.item.source}] {r.item.title}")
        print(f"       {date_str}  |  topics: {topics_str}")
        print(f"       {r.item.url}")
        print()

    print(f"\n── Unmatched ({len(unscored)}) ─────────────────────────────────")
    for r in unscored:
        date_str = r.item.published.strftime("%Y-%m-%d") if r.item.published else "no date"
        print(f"[{r.item.source}] {r.item.title}  ({date_str})")
