# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the project

```bash
# Activate the venv (already exists at .venv/)
source .venv/bin/activate

# Install / sync dependencies
pip install -r requirements.txt

# Run fetch-only report
python fetcher.py

# Run ranked report (fetch + score)
python ranker.py

# Run full pipeline (fetch + rank + summarize via Claude API)
# Requires ANTHROPIC_API_KEY set in environment or PyCharm run config
python summarizer.py

# Run full pipeline + send email digest
# Requires ANTHROPIC_API_KEY, GMAIL_USER, GMAIL_APP_PASSWORD
python emailer.py
```

In PyCharm, open any file and press ▶. For `summarizer.py` and `emailer.py`, add env vars under Run > Edit Configurations > Environment variables:
- `ANTHROPIC_API_KEY` — Claude API key
- `GMAIL_USER` — Gmail address used as sender
- `GMAIL_APP_PASSWORD` — 16-char App Password from myaccount.google.com/apppasswords (not your Google account password)

## Architecture

This is a pipeline project being built incrementally. Each step is planned as its own module:

1. **Fetch** (`fetcher.py`) — done. Pulls `NewsItem` objects from RSS feeds and Hacker News.
2. **Rank** (`ranker.py`) — done. Scores items against `TOPICS`; wraps each in `RankedItem(item, score, matched_topics)`.
3. **Summarize** (`summarizer.py`) — done. Calls Claude Haiku for 2-3 sentence summaries; populates `RankedItem.summary`.
4. **Email** (`emailer.py`) — done. Formats digest as HTML+plain-text and sends via Gmail SMTP.
5. **State / scheduling** — done. `state.py` reads/writes seen article URLs to Firestore; `.github/workflows/digest.yml` runs `emailer.py` on a cron every 2 days.

`fetcher.py` owns the `NewsItem` dataclass and all fetch logic. `ranker.py` owns `RankedItem` and scoring; it imports `fetch_all()` directly and can be run standalone. `config.py` holds the shared configuration (`RSS_FEEDS`, `TOPICS`, `TOPIC_ALIASES`) imported by all steps.

## Key constraints

**RSS fetch pattern:** Always use `requests.get()` to download feed content, then pass `resp.content` (bytes) to `feedparser.parse()`. Do **not** pass URLs directly to `feedparser.parse()` — feedparser's built-in urllib fetch fails SSL verification on macOS because Python's bundled SSL doesn't use the system keychain. `requests` ships with `certifi` and avoids this.

**Per-feed fault isolation:** Each RSS feed is wrapped in its own `try/except`. A broken feed must log a `WARNING` and continue — never raise or abort the run.

**Lookback window:** `LOOKBACK_DAYS = 5` in `fetcher.py`. Items with a known `published` date older than this are filtered out. Items with no date are kept.

**Deduplication:** Done by exact URL match in `fetch_all()`. Keep this as the single dedup point when adding new sources.

**Topic matching:** `ranker.py` checks each topic's main phrase plus all entries in `TOPIC_ALIASES` (from `config.py`). Add synonyms/abbreviations there explicitly — don't add magic normalization to the scorer. Title hit = 2 pts, snippet hit = 1 pt; a topic scores at most 3 pts regardless of how many alias phrases match.

**Adding or updating recipients:** Edit `RECIPIENTS` in `config.py`. Each entry needs `email`, `name`, and `topics` (a subset of the `TOPICS` list). The emailer sends one personalised email per recipient containing only articles matching their chosen topics. Articles are grouped by topic in the email.

**Firebase deduplication:** `state.py` resolves credentials in this order: (1) `FIREBASE_CREDENTIALS` env var (JSON string — used in CI), (2) `firebase-credentials.json` file in the project root (gitignored, used locally). If neither is present, dedup is silently disabled and all matched items are sent. The Firestore collection is `seen_articles`; document IDs are SHA-1 hashes of the article URL.

**GitHub Actions secrets required:** `ANTHROPIC_API_KEY`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `FIREBASE_CREDENTIALS` (the full service-account JSON as a single-line string). Set at Settings → Secrets and variables → Actions.
