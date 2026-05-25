"""AI Daily Pipeline — Source Configuration"""

import os
from dataclasses import dataclass, field
from datetime import timedelta, timezone
from typing import Optional

# Beijing timezone (UTC+8)
BEIJING_TZ = timezone(timedelta(hours=8))

@dataclass
class Source:
    name: str           # Display name (中文 or English)
    url: str            # RSS feed URL
    lang: str = "en"    # "en" | "zh"
    ai_specific: bool = True  # False = needs AI keyword filter

# ============================================================
# 15 sources verified working as of 2026-05-14
# ============================================================

SOURCES: list[Source] = [
    # ---- AI-specific English ----
    Source("TechCrunch",      "https://techcrunch.com/category/artificial-intelligence/feed/",   "en", True),
    Source("VentureBeat",     "https://venturebeat.com/category/ai/feed/",                       "en", True),
    Source("MarkTechPost",    "https://www.marktechpost.com/feed/",                              "en", True),
    Source("AI News",         "https://www.artificialintelligence-news.com/feed/",               "en", True),
    Source("The Verge AI",    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml","en", True),
    Source("Synced Review",   "https://syncedreview.com/feed/",                                  "en", True),
    Source("OpenAI Blog",     "https://openai.com/blog/rss.xml",                                 "en", True),
    Source("Google AI Blog",  "https://blog.google/technology/ai/rss/",                          "en", True),
    Source("DeepMind Blog",   "https://deepmind.google/blog/feed/",                              "en", True),

    # ---- General tech (AI keyword filtered) ----
    Source("MIT Tech Review", "https://www.technologyreview.com/feed/",                          "en", False),
    Source("Ars Technica",    "https://feeds.arstechnica.com/arstechnica/index.xml",             "en", False),
    Source("The Verge",       "https://www.theverge.com/rss/index.xml",                          "en", False),
    Source("Hacker News",     "https://hnrss.org/frontpage?count=15",                            "en", False),

    # ---- Chinese ----
    Source("36氪",            "https://36kr.com/feed",                                           "zh", False),
    Source("少数派",          "https://sspai.com/feed",                                          "zh", False),
]

# ============================================================
# AI keyword filters (for general sources)
# ============================================================

AI_KEYWORDS_EN = [
    "AI", "LLM", "GPT", "Claude", "OpenAI", "Anthropic", "Gemini",
    "agent", "neural", "transformer", "deep learning", "machine learning",
    "language model", "diffusion", "chatbot", "copilot", "foundation model",
    "artificial intelligence", "RAG", "fine-tun", "alignment", "RLHF",
    "NVIDIA GPU", "AI chip", "token", "benchmark", "SOTA", "open source model",
]

AI_KEYWORDS_ZH = [
    "AI", "人工智能", "大模型", "GPT", "Claude", "OpenAI", "模型",
    "智能", "深度学习", "机器学习", "Agent", "智能体", "推理",
    "训练", "开源模型", "多模态", "对齐", "微调", "算力",
    "AIGC", "生成式", "LLM", "ChatGPT", "提示词",
]

# ============================================================
# Pipeline settings
# ============================================================

# AI provider: "deepseek" | "claude"
AI_PROVIDER = "deepseek"

# API keys (set via environment variables, never hardcode here)
#   AI_DAILY_DS_KEY        — DeepSeek API key
#   AI_DAILY_ANTHROPIC_KEY  — Anthropic API key
#   AI_DAILY_SERVERCHAN_KEY — Server酱 SendKey for WeChat push
DEEPSEEK_API_KEY = os.environ.get("AI_DAILY_DS_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("AI_DAILY_ANTHROPIC_KEY", "")

# DeepSeek (OpenAI-compatible)
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"

# Claude (Anthropic)
CLAUDE_MODEL = "claude-sonnet-4-6"

# Time window: articles published within last N hours
TIME_WINDOW_HOURS = 24

# Max articles per source
MAX_PER_SOURCE = 10

# Target article count after dedup
TARGET_ARTICLE_COUNT = 12

# Dedup similarity threshold (0-1)
DEDUP_THRESHOLD = 0.6

# Fetch timeout per source (seconds)
FETCH_TIMEOUT = 15

# WeChat push (Server酱)
SERVERCHAN_KEY = os.environ.get("AI_DAILY_SERVERCHAN_KEY", "")
PUSH_ENABLED = bool(SERVERCHAN_KEY)

# Output directory
OUTPUT_DIR = "data/daily"
