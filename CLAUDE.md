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
5. **State / scheduling** — done. `state.py` reads/writes seen article URLs to Firestore; `.github/workflows/digest.yml` runs `emailer.py` on a cron every 3 days.

`fetcher.py` owns the `NewsItem` dataclass and all fetch logic. `ranker.py` owns `RankedItem` and scoring; it imports `fetch_all()` directly and can be run standalone. `config.py` holds the shared configuration (`RSS_FEEDS`, `TOPICS`, `TOPIC_ALIASES`) imported by all steps.

## Key constraints

**RSS fetch pattern:** Always use `requests.get()` to download feed content, then pass `resp.content` (bytes) to `feedparser.parse()`. Do **not** pass URLs directly to `feedparser.parse()` — feedparser's built-in urllib fetch fails SSL verification on macOS because Python's bundled SSL doesn't use the system keychain. `requests` ships with `certifi` and avoids this.

**Per-feed fault isolation:** Each RSS feed is wrapped in its own `try/except`. A broken feed must log a `WARNING` and continue — never raise or abort the run.

**Lookback window:** `LOOKBACK_DAYS = 5` in `fetcher.py`. Items with a known `published` date older than this are filtered out. Items with no date are kept.

**Deduplication:** Done by exact URL match in `fetch_all()`. Keep this as the single dedup point when adding new sources.

**Topic matching:** `ranker.py` checks each topic's main phrase plus all entries in `TOPIC_ALIASES` (from `config.py`). Add synonyms/abbreviations there explicitly — don't add magic normalization to the scorer. Title hit = 2 pts, snippet hit = 1 pt; a topic scores at most 3 pts regardless of how many alias phrases match.

**Adding or updating recipients:** Recipients are stored in the Firestore `recipients` collection — not in code or secrets. Each document needs `email`, `name`, `topics` (list of topic strings from `TOPICS`), and `active` (boolean). Add/edit them directly in the Firebase console, or use `state.save_recipient(dict)` from a Python shell. To migrate from `recipients.json` to Firestore for the first time, run `python migrate_recipients.py`. `state.py` falls back to `recipients.json` if Firestore is unavailable or empty (local dev only).

**Person-specific extra topics:** A recipient can be granted topics that aren't offered on the Google Form, via the `extra_topics` field on their Firestore doc. Set them with `state.set_extra_topics(email, ["topic", ...])` (validates against `TOPICS`; pass `[]` to clear). This must NOT be done by editing `topics` directly — `sync_recipients.py` rewrites `topics` wholesale from the form before every digest, so a hand-added entry there is wiped on the next run. The sync never writes `extra_topics`, so it survives. `emailer._all_topics()` unions the two.

**Preferred display names:** The Google Form asks for a legal first name. To greet someone differently, set `name_override` on their Firestore doc via `state.set_name_override(email, "Preferred Name")` (pass `None` to clear). Same reasoning as `extra_topics` — `sync_recipients.py` rewrites `name` from the form on every run, and the sync never writes `name_override`, so it survives. `sync_recipients.load_name_overrides()` reads them all in one query. This must **not** go back to a hardcoded dict in source: a name↔address mapping is personal data and this repo is public.

**Firebase deduplication:** `state.py` resolves credentials in this order: (1) `FIREBASE_CREDENTIALS` env var (JSON string — used in CI), (2) `firebase-credentials.json` file in the project root (gitignored, used locally). If neither is present, dedup is silently disabled and all matched items are sent. The Firestore collection is `seen_articles`; document IDs are SHA-1 hashes of the article URL.

**GitHub Actions secrets required:** `ANTHROPIC_API_KEY`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `FIREBASE_CREDENTIALS` (the full service-account JSON as a single-line string), and `GOOGLE_SHEET_ID`. Set at Settings → Secrets and variables → Actions. `RECIPIENTS_JSON` is no longer used — recipients now live in Firestore.

`GOOGLE_SHEET_ID` has no hardcoded fallback — `sync_recipients.py` exits 1 if it is unset. The value is the long ID in the sheet's URL (`docs.google.com/spreadsheets/d/<THIS_PART>/edit`). It is read from the environment because this repository is **public**: a sheet ID is a durable pointer to a file containing every respondent's name, address, and topic choices. The sheet is access-controlled, so the ID alone grants nothing — keeping it out of source means a future loosening of the sheet's sharing settings isn't instantly exploitable.

**Never log a recipient's email address.** This repo is public, and GitHub makes workflow logs world-readable on public repos — so anything printed to stdout during a digest run is published. Use `state.mask_email()` for every log line, `print`, and exception message that touches an address (`someone@example.com` → `s***@example.com`); it keeps the first character and domain for traceability while hiding the local part and its length. Recipient *names* are not logged at all. This applies to logging only — the digest emails themselves are unaffected.

**Summarization retry chain:** Each article gets up to three attempts (`summarizer._ATTEMPTS`): Haiku, Haiku again, then `claude-sonnet-5`. The first retry catches transient API errors and one-off refusals; the Sonnet attempt catches thin or odd articles Haiku won't summarize. Only failures pay for the extra calls. The Sonnet attempt passes `thinking={"type": "disabled"}` and a larger `max_tokens` — Sonnet 5 thinks by default and `max_tokens` caps thinking + response text together, so the Haiku-sized 150-token budget would truncate the summary. The SDK already retries 429s/5xx inside each attempt.

**Summarization failure handling (soft failure):** An article that fails all three attempts is left with `summary = ""` and `summary_failed = True`. `emailer.py` keeps its card — title, source, and "Read more" link — and renders `SUMMARY_UNAVAILABLE` in place of the summary, so one bad article never costs recipients the rest of the digest. Failed URLs are excluded from `mark_seen()`, so the next run retries them and a transient failure self-heals (until the article ages out of `LOOKBACK_DAYS`).

The digest is held only when failures exceed `emailer.HOLD_FAILURE_RATIO` (50%) of attempted summaries — a majority means something systemic (bad API key, wrong model name, account issue) and a digest of mostly notices is worse than none. In that case `emailer.py` exits 1; re-run with `FORCE_SEND=true` once resolved.

Either way an alert email goes to `ALERT_EMAIL` if set, otherwise `GMAIL_USER`; the subject is tagged `(digest HELD)` or `(digest SENT)`. No extra secret is needed unless you want alerts routed elsewhere. `summarize()` returns `(ranked, failures, attempted)` — `attempted` is what the hold ratio is measured against.

**Opening brief:** Each digest starts with a per-recipient "Today's Brief" (a one-line hook + 3-4 bullets), generated by `summarizer.overview()` from that recipient's own article set and priority topics — one Claude Haiku call per recipient. It is deliberately per-recipient because everyone receives a different article subset. A brief failure is non-fatal: it logs a warning and the digest sends without the block (unlike article-summary failures, which hold the whole digest).

**Testing the emailer safely:** Two env-var safeguards on `emailer.py`, both off by default:
- `DRY_RUN=true` — builds every recipient's digest and prints it to the terminal; opens no SMTP connection and sends nothing. Needs `ANTHROPIC_API_KEY` (for summaries + brief) but no Gmail creds. Pair with `FORCE_SEND=true` to preview already-sent items too.
- `ONLY_EMAIL=<address>` — restricts a real send to a single recipient, so a test send cannot fan out to the whole list. Typical first-send check: `ONLY_EMAIL=you@example.com FORCE_SEND=true python emailer.py`.
