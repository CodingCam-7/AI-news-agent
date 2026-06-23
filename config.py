RSS_FEEDS = [
    ("TechCrunch AI",  "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("The Verge AI",   "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("Hugging Face",   "https://huggingface.co/blog/feed.xml"),
    ("OpenAI",         "https://openai.com/news/rss.xml"),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
]

# Used in the next step (ranking) to score articles by topic relevance.
# Niche topics like "AI in hospitality and wine" are intentionally included
# so the ranker can surface rare-but-relevant stories.
TOPICS = [
    "large language models",
    "AI agents",
    "AI tooling",
    "AI policy",
    "AI in hospitality and wine",
]
