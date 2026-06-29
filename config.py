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
    # Models & Research
    "large language models",
    "multimodal AI",
    "AI safety & alignment",
    "open source AI",
    # Hardware & Infrastructure
    "AI hardware & chips",
    "AI cloud & infrastructure",
    "AI energy & costs",
    # Applications
    "AI agents",
    "AI tooling",
    "AI in finance",
    "AI in healthcare",
    "AI in creative industries",
    "robotics & physical AI",
    "AI in hospitality and wine",
    # Business & Society
    "AI startups & funding",
    "enterprise AI",
    "AI policy",
]

# Additional search phrases checked alongside each topic.
# Add synonyms, abbreviations, or singular/plural variants here
# rather than relying on magic normalization.
TOPIC_ALIASES: dict[str, list[str]] = {
    "large language models":      ["large language model", "LLM", "LLMs", "foundation model", "foundation models",
                                   "GPT", "Claude", "Gemini", "ChatGPT", "language model"],
    "multimodal AI":              ["multimodal", "vision model", "image model", "audio model", "video model",
                                   "DALL-E", "Stable Diffusion", "Midjourney", "Sora",
                                   "text-to-image", "text-to-video", "image generation", "video generation"],
    "AI safety & alignment":      ["AI safety", "AI alignment", "alignment research", "interpretability",
                                   "AI risk", "AI ethics", "responsible AI", "AI harm", "AI bias"],
    "open source AI":             ["open source", "open weights", "open weight", "open-source AI",
                                   "Llama", "Mistral", "Falcon", "Phi", "Gemma", "open model"],
    "AI hardware & chips":        ["NVIDIA", "GPU", "TPU", "semiconductor", "data center", "data centre",
                                   "H100", "A100", "Blackwell", "AMD", "Intel", "custom silicon",
                                   "AI accelerator", "AI chip"],
    "AI cloud & infrastructure":  ["cloud AI", "MLOps", "model deployment", "inference", "AWS Bedrock",
                                   "Azure AI", "Google Cloud AI", "AI infrastructure", "model serving"],
    "AI energy & costs":          ["AI energy", "electricity", "power consumption", "carbon footprint",
                                   "AI cost", "compute cost", "training cost", "AI sustainability"],
    "AI agents":                  ["AI agent", "agentic", "autonomous agent", "autonomous agents",
                                   "multi-agent", "workflow automation", "AI workflow", "copilot"],
    "AI tooling":                 ["AI tool", "AI tools", "AI SDK", "developer tool", "AI framework",
                                   "AI API", "LangChain", "LlamaIndex", "Cursor", "GitHub Copilot"],
    "AI in finance":              ["fintech", "algorithmic trading", "AI trading", "financial AI",
                                   "stock market AI", "AI investing", "AI banking", "quantitative"],
    "AI in healthcare":           ["medical AI", "healthcare AI", "drug discovery", "AI diagnosis",
                                   "clinical AI", "biotech AI", "genomics", "radiology AI", "medical imaging"],
    "AI in creative industries":  ["AI art", "AI music", "creative AI", "AI video", "AI design",
                                   "Adobe AI", "generative art", "AI animation"],
    "robotics & physical AI":     ["robot", "robotics", "humanoid", "self-driving", "autonomous vehicle",
                                   "Boston Dynamics", "physical AI", "embodied AI", "drone AI"],
    "AI in hospitality and wine": ["restaurant AI", "hospitality AI", "wine AI", "sommelier AI", "hotel AI"],
    "AI startups & funding":      ["AI startup", "venture capital", "AI funding", "AI investment",
                                   "AI acquisition", "AI IPO", "AI unicorn", "Y Combinator"],
    "enterprise AI":              ["enterprise AI", "business AI", "corporate AI", "AI adoption",
                                   "AI productivity", "workforce AI", "Microsoft Copilot", "Salesforce AI"],
    "AI policy":                  ["AI regulation", "AI governance", "AI law", "AI ban", "AI policy",
                                   "EU AI Act", "executive order", "AI legislation", "AI oversight"],
}
