RECIPIENTS = [
    {
        "email": "cjpentz777@gmail.com",
        "name": "Cameron",
        "topics": ["large language models", "AI agents", "AI tooling", "AI policy", "AI in hospitality and wine"],
    },
    {
        "email": "djpentz@gmail.com",
        "name": "Paps",
        "topics": ["large language models", "AI agents", "AI tooling", "AI policy", "AI in hospitality and wine"],
    },
    {
        "email": "mjpentz21@gmail.com",
        "name": "MJ",
        "topics": ["large language models", "AI agents", "AI tooling", "AI policy", "AI in hospitality and wine"],
    },
]

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
