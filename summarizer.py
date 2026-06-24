"""
summarizer.py — Step 3 of the AI News Digest Agent.

Calls the Claude API to write a 2-3 sentence digest summary for each item
that matched at least one topic. Run directly to see the full pipeline:
fetch → rank → summarize.

Requires ANTHROPIC_API_KEY set in your environment (or PyCharm run config).
"""

import logging
import os
import sys
from datetime import datetime

import anthropic

from fetcher import fetch_all
from ranker import RankedItem, rank

logger = logging.getLogger(__name__)

# Haiku is fast and cheap — well-suited for short, high-volume summarization.
SUMMARY_MODEL = "claude-haiku-4-5"

# Stable system prompt, cached across all items in a single run.
SYSTEM_PROMPT = (
    "You are a concise AI news digest writer. "
    "Given an article's title, source, and excerpt, write a 2-3 sentence summary that:\n"
    "- Captures the key development or insight\n"
    "- Explains why it matters for someone tracking AI trends\n"
    "- Uses plain, direct prose (no bullet points, no hype)\n\n"
    "Respond with only the summary text — no preamble, no labels."
)


def _make_client() -> anthropic.Anthropic:
    """Build the Anthropic client, exiting early with a helpful message if no key is set."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "Error: ANTHROPIC_API_KEY is not set.\n"
            "Add it to your shell profile or to PyCharm's run configuration "
            "(Run > Edit Configurations > Environment variables).",
            file=sys.stderr,
        )
        sys.exit(1)
    return anthropic.Anthropic(api_key=api_key)


def _summarize_one(client: anthropic.Anthropic, r: RankedItem) -> str:
    """
    Call the Claude API for a single item.
    The system prompt has cache_control so it's reused across all calls in the run.
    """
    user_content = (
        f"Title: {r.item.title}\n"
        f"Source: {r.item.source}\n"
        f"Excerpt: {r.item.snippet or '(no excerpt available)'}"
    )

    response = client.messages.create(
        model=SUMMARY_MODEL,
        max_tokens=150,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                # Cache the system prompt — same bytes every call, so the first call
                # pays the write cost and all subsequent calls get a cache hit.
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_content}],
    )
    return response.content[0].text.strip()


def summarize(ranked: list[RankedItem], min_score: float = 1.0) -> list[RankedItem]:
    """
    Populate the `summary` field on every item whose score >= min_score.
    Items below the threshold are left with summary = "".
    Returns the same list (mutated in place) for chaining.
    """
    to_summarize = [r for r in ranked if r.score >= min_score]

    if not to_summarize:
        logger.warning("No items met the score threshold — nothing to summarize.")
        return ranked

    client = _make_client()
    print(f"Summarizing {len(to_summarize)} matched item(s) via Claude {SUMMARY_MODEL}...\n")

    for r in to_summarize:
        try:
            r.summary = _summarize_one(client, r)
        except Exception as exc:
            logger.warning("Summary failed for '%s': %s", r.item.title, exc)
            r.summary = r.item.snippet  # fall back to the raw snippet


    return ranked


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s  %(message)s")

    raw = fetch_all()
    ranked = rank(raw)
    summarize(ranked)

    scored = [r for r in ranked if r.score > 0]

    print(f"\n{'='*60}")
    print(f"  AI News Digest — {datetime.now().strftime('%Y-%m-%d')}  |  {len(scored)} matched items")
    print(f"{'='*60}")

    for r in scored:
        date_str = r.item.published.strftime("%Y-%m-%d") if r.item.published else "no date"
        topics_str = ", ".join(r.matched_topics)
        print(f"\n[{r.score:.0f}pt] [{r.item.source}]  {r.item.title}")
        print(f"  {date_str}  |  {topics_str}")
        print(f"  {r.item.url}")
        if r.summary:
            print(f"\n  {r.summary}")
