# AI News Digest Agent

An automated AI news digest that fetches recent articles from curated RSS feeds and Hacker News, scores them against 17 configurable AI topics, summarizes each one with Claude, and emails a personalized digest to each recipient. The full pipeline runs automatically every three days via GitHub Actions.

## Pipeline

```
fetcher.py → ranker.py → summarizer.py → emailer.py
```

| Step | File | What it does |
|------|------|--------------|
| Fetch | `fetcher.py` | Pulls articles from RSS feeds and Hacker News for the last 7 days |
| Rank | `ranker.py` | Scores each article against 17 AI topics; filters to matched items only |
| Summarize | `summarizer.py` | Calls Claude Haiku to write a 2-3 sentence digest summary per article |
| Email | `emailer.py` | Sends a personalized HTML digest to each active recipient via Gmail SMTP |
| State | `state.py` | Tracks sent article URLs in Firestore to avoid re-sending across runs |
| Sync | `sync_recipients.py` | Reads Google Form responses and upserts recipient preferences to Firestore |

## Run instructions

```bash
# 1. Create and activate a virtual environment (one-time setup)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run individual steps
python fetcher.py       # fetch only — prints a console report
python ranker.py        # fetch + rank — shows scored articles
python summarizer.py    # fetch + rank + summarize — requires ANTHROPIC_API_KEY
python emailer.py       # full pipeline — requires all env vars below
```

### Required environment variables

| Variable | Used by | Where to get it |
|----------|---------|-----------------|
| `ANTHROPIC_API_KEY` | `summarizer.py`, `emailer.py` | console.anthropic.com |
| `GMAIL_USER` | `emailer.py` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | `emailer.py` | myaccount.google.com/apppasswords |
| `FIREBASE_CREDENTIALS` | `emailer.py`, `sync_recipients.py` | Firebase service account JSON (single-line string) |

In PyCharm, set these under Run > Edit Configurations > Environment variables.

## Recipients

Recipients and their topic preferences are stored in Firestore (`recipients` collection). Each document holds the recipient's name, email, selected topics, and optional priority ranking.

New recipients fill out a Google Form — `sync_recipients.py` reads the linked Google Sheet and upserts their preferences to Firestore automatically before each digest run. To add a recipient manually, use `state.save_recipient(dict)` from a Python shell or the Firebase console.

## Automatic scheduling

`.github/workflows/digest.yml` runs the full pipeline every three days at 8:30 AM SAST. The workflow syncs recipients from the Google Form, then runs `emailer.py`. Articles already sent are tracked in Firestore and skipped on subsequent runs.

To trigger a run manually, go to Actions → AI News Digest → Run workflow. Enable "Bypass dedup" to resend all matched articles (useful for testing).
