import json
import os as _os

def _load_recipients() -> list[dict]:
    """Load recipients from RECIPIENTS_JSON env var (CI) or recipients.json file (local dev)."""
    env_json = _os.environ.get("RECIPIENTS_JSON")
    if env_json:
        return json.loads(env_json)
    local_path = _os.path.join(_os.path.dirname(__file__), "recipients.json")
    if _os.path.exists(local_path):
        with open(local_path) as f:
            return json.load(f)
    raise RuntimeError(
        "No recipients configured. Set the RECIPIENTS_JSON env var or create a recipients.json file."
    )

RECIPIENTS: list[dict] = _load_recipients()

RSS_FEEDS = [
    ("TechCrunch AI",      "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("The Verge AI",       "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("Hugging Face",       "https://huggingface.co/blog/feed.xml"),
    ("OpenAI",             "https://openai.com/news/rss.xml"),
    ("VentureBeat AI",     "https://venturebeat.com/category/ai/feed/"),
    ("MIT Tech Review",    "https://www.technologyreview.com/feed/"),
    ("Ars Technica",       "https://feeds.arstechnica.com/arstechnica/technology-lab"),
    ("Google AI Blog",     "https://blog.google/innovation-and-ai/technology/ai/rss/"),
    ("DeepMind",           "https://deepmind.google/blog/rss.xml"),
    ("IEEE Spectrum",      "https://spectrum.ieee.org/feeds/feed.rss"),
    ("Wired",              "https://www.wired.com/feed/rss"),
]

# Primary topic labels — used as display names in the digest.
TOPICS = [
    "large language models",
    "AI agents",
    "AI tooling",
    "AI policy",
    "AI in hospitality and wine",
]

# Additional search phrases checked alongside each topic.
# Add synonyms, abbreviations, or singular/plural variants here
# rather than relying on magic normalization.
TOPIC_ALIASES: dict[str, list[str]] = {
    "large language models": ["large language model", "LLM", "LLMs", "foundation model", "foundation models"],
    "AI agents":             ["AI agent", "agentic", "autonomous agent", "autonomous agents", "multi-agent"],
    "AI tooling":            ["AI tool", "AI tools", "AI SDK", "developer tool", "AI framework", "AI infrastructure"],
    "AI policy":             ["AI regulation", "AI governance", "AI law", "AI safety", "AI ban", "AI policy"],
    "AI in hospitality and wine": ["restaurant AI", "hospitality AI", "wine AI", "sommelier AI", "hotel AI"],
}
