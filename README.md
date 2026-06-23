# AI News Digest Agent

An automated AI news digest that fetches recent articles from curated RSS feeds and Hacker News, filters them by topic relevance, and (in future steps) ranks, summarizes, and emails a digest every two days. The current implementation covers the **fetch step only**: run `fetcher.py` to pull stories from the last five days and print a clean console report showing every item by source.

## Run instructions

```bash
# 1. Create and activate a virtual environment (one-time setup)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the fetcher
python fetcher.py
```

In PyCharm, open `fetcher.py` and press the green ▶ button — no additional configuration needed.
