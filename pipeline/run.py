#!/usr/bin/env python3
"""AI Daily Pipeline — fetch → filter → dedup → AI process → output JSON.

Usage:
    python3 pipeline/run.py                    # Full pipeline
    python3 pipeline/run.py --fetch-only       # Only fetch, skip AI
    python3 pipeline/run.py --output json      # Output to stdout instead of file
"""

import sys
import os
import ssl
import json
import time
import hashlib
import argparse
import logging
import subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from typing import Optional

import feedparser
import httpx
from openai import OpenAI
from anthropic import Anthropic

from config import (
    SOURCES, AI_KEYWORDS_EN, AI_KEYWORDS_ZH,
    AI_PROVIDER, DEEPSEEK_MODEL, DEEPSEEK_BASE_URL, CLAUDE_MODEL,
    DEEPSEEK_API_KEY, ANTHROPIC_API_KEY,
    TIME_WINDOW_HOURS, MAX_PER_SOURCE, TARGET_ARTICLE_COUNT,
    DEDUP_THRESHOLD, FETCH_TIMEOUT, OUTPUT_DIR,
    SERVERCHAN_KEY, PUSH_ENABLED, BEIJING_TZ,
)

# ---- Logging ----
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("pipeline")

# ---- SSL workaround for macOS ----
# Use unverified context for RSS fetch to handle misconfigured/missing certs
_SSL_VERIFY = True
if hasattr(ssl, "_create_unverified_context"):
    _SSL_VERIFY = ssl._create_unverified_context()

# ---- Paths ----
ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / OUTPUT_DIR


# ============================================================
# Phase 1: Fetch
# ============================================================

def fetch_source(source) -> list[dict]:
    """Fetch and parse a single RSS source. Returns normalized articles."""
    articles = []
    try:
        resp = httpx.get(source.url, timeout=FETCH_TIMEOUT, follow_redirects=True, verify=_SSL_VERIFY)
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)

        for entry in feed.entries[:MAX_PER_SOURCE]:
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if not title or not link:
                continue

            # Parse publication date — prefer published over updated
            # Articles without a parsable date are skipped (no datetime.now() fallback
            # which would let stale articles bypass the time filter)
            published = None
            tp = entry.get("published_parsed")
            if tp:
                published = datetime(*tp[:6], tzinfo=timezone.utc)
            if not published:
                tp = entry.get("updated_parsed")
                if tp:
                    published = datetime(*tp[:6], tzinfo=timezone.utc)
            if not published:
                continue  # skip articles without a publication date

            # Extract text content
            summary = ""
            if entry.get("summary"):
                summary = strip_html(entry.summary)[:500]
            elif entry.get("content"):
                for c in entry.content:
                    if c.get("value"):
                        summary = strip_html(c.value)[:500]
                        break
            if not summary:
                summary = entry.get("description", "")[:500]
            summary = strip_html(summary)[:500]

            articles.append({
                "title": title,
                "url": link,
                "source": source.name,
                "lang": source.lang,
                "ai_specific": source.ai_specific,
                "published": published,
                "summary": summary,
                "source_url": link,
            })

        log.info(f"  {source.name}: {len(articles)} articles")
    except Exception as e:
        log.warning(f"  {source.name}: fetch failed — {e}")

    return articles


def fetch_all(sources: list) -> list[dict]:
    """Fetch all sources in parallel."""
    log.info(f"Fetching {len(sources)} sources...")
    all_articles = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fetch_source, s): s for s in sources}
        for f in as_completed(futures):
            all_articles.extend(f.result())
    log.info(f"Fetched {len(all_articles)} raw articles from {len(sources)} sources")
    return all_articles


# ============================================================
# Phase 2: Filter
# ============================================================

def filter_time(articles: list[dict], hours: int = TIME_WINDOW_HOURS,
                 target_date: Optional[str] = None) -> list[dict]:
    """Keep only articles published within the time window (Beijing time).
    When target_date is set, uses a wide window back to that date and keeps only
    articles from that specific date."""
    if target_date:
        target_dt = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=BEIJING_TZ)
        # Wide window: from now back to start of target date
        hours = max(72, int((datetime.now(BEIJING_TZ) - target_dt).total_seconds() / 3600) + 4)
        cutoff = datetime.now(BEIJING_TZ) - timedelta(hours=hours)
        filtered = [a for a in articles
                    if a["published"] >= cutoff
                    and a["published"].astimezone(BEIJING_TZ).date() == target_dt.date()]
        log.info(f"Time filter (backfill {target_date}, {hours}h window): {len(articles)} → {len(filtered)}")
    else:
        cutoff = datetime.now(BEIJING_TZ) - timedelta(hours=hours)
        filtered = [a for a in articles if a["published"] >= cutoff]
        log.info(f"Time filter ({hours}h): {len(articles)} → {len(filtered)}")
    return filtered


def filter_ai_keywords(articles: list[dict]) -> list[dict]:
    """For non-AI-specific sources, keep only AI-related articles.
    Requires 2+ keyword matches to filter out incidental mentions."""
    result = []
    for a in articles:
        if a["ai_specific"]:
            result.append(a)
        else:
            text = (a["title"] + " " + a["summary"]).lower()
            keywords = AI_KEYWORDS_ZH if a["lang"] == "zh" else AI_KEYWORDS_EN
            matches = sum(1 for kw in keywords if kw.lower() in text)
            if matches >= 2:
                result.append(a)
    log.info(f"AI keyword filter: {len(articles)} → {len(result)}")
    return result


def title_similarity(a: str, b: str) -> float:
    """Calculate title similarity ratio."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def deduplicate(articles: list[dict], threshold: float = DEDUP_THRESHOLD) -> list[dict]:
    """Remove near-duplicate articles by title similarity."""
    articles.sort(key=lambda a: a["published"], reverse=True)
    kept = []
    for a in articles:
        is_dup = False
        for k in kept:
            if title_similarity(a["title"], k["title"]) >= threshold:
                is_dup = True
                # Preserve multi-source info
                if a["source"] != k["source"]:
                    k.setdefault("multi_source", {k["source"]})
                    k["multi_source"].add(a["source"])
                break
        if not is_dup:
            kept.append(a)
    log.info(f"Dedup: {len(articles)} → {len(kept)}")
    return kept


# ============================================================
# Phase 3: AI Process
# ============================================================

def build_ai_prompt(articles: list[dict]) -> str:
    """Build the prompt for Claude to classify and summarize articles."""
    article_list = []
    for i, a in enumerate(articles):
        article_list.append(
            f"[{i}] 标题: {a['title']}\n"
            f"    来源: {a['source']}\n"
            f"    原文摘要: {a['summary'][:300]}\n"
            f"    链接: {a['url']}"
        )
    article_block = "\n\n".join(article_list)

    return f"""你是 AI Daily 的 AI 编辑。请处理以下 {len(articles)} 条 AI 行业资讯。

## 任务

1. **分类打标**: 给每条资讯分配一个分类标签
   - `model` = 新模型发布、模型评测、开源模型、模型技术突破
   - `strategy` = 大厂战略、融资、行业趋势
   - `tool` = 开发者工具、产品发布、应用落地
   - `policy` = 政策监管、法规合规、学术伦理、隐私安全

2. **中文摘要**: 每条写 150-250 字中文概要，把技术细节讲清楚

3. **毒舌评论**: 每条写一句带幽默感的短评（15-30 字中文，像 AI 同行吐槽）

4. **今日要点**: 写一句 50 字内的中文总结，概括今天最值得关注的事

5. **每日运势**: 从今天的资讯中挑一个模型或公司作为"幸运模型"，写一句"宜...忌..."的运势建议（像星座运势风格，跟 AI 行业相关）

6. **冷笑话**: 写一个 AI 行业的冷笑话，30 字内，带点程序员幽默

## 输出格式

只输出 JSON，不要 markdown 代码块标记：

{{
  "highlight": "今日要点一句话",
  "fun": {{
    "lucky": "幸运模型名称",
    "advice": "宜：...\\n忌：...",
    "joke": "冷笑话内容"
  }},
  "articles": [
    {{
      "index": 0,
      "cat": "model",
      "title_cn": "中文标题",
      "summary_cn": "150-250字中文概要",
      "snark": "毒舌短评"
    }}
  ]
}}

## 资讯列表

{article_block}"""


def call_claude(articles: list[dict], api_key: str) -> dict:
    """Send articles to Claude for classification and summarization."""
    if not articles:
        return {"highlight": "", "articles": []}

    log.info(f"Calling Claude ({CLAUDE_MODEL}) to process {len(articles)} articles...")
    client = Anthropic(api_key=api_key)

    prompt = build_ai_prompt(articles)
    log.info(f"Prompt length: {len(prompt)} chars")

    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    text = resp.content[0].text.strip()
    return _parse_ai_json(text, "Claude")


def call_deepseek(articles: list[dict], api_key: str) -> dict:
    """Send articles to DeepSeek for classification and summarization."""
    if not articles:
        return {"highlight": "", "articles": []}

    log.info(f"Calling DeepSeek ({DEEPSEEK_MODEL}) to process {len(articles)} articles...")
    client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)

    prompt = build_ai_prompt(articles)
    log.info(f"Prompt length: {len(prompt)} chars")

    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        max_tokens=4096,
        temperature=0.7,
        messages=[{"role": "user", "content": prompt}],
    )

    text = resp.choices[0].message.content.strip()
    return _parse_ai_json(text, "DeepSeek")


def _parse_ai_json(text: str, provider: str = "") -> dict:
    """Parse AI API response JSON, handling markdown code blocks and common edge cases."""
    import re

    raw = text.strip()

    # Strip markdown code fence (```json ... ``` or ``` ... ```)
    m = re.match(r"```(?:json)?\s*\n(.*?)\n```", raw, re.DOTALL)
    if m:
        raw = m.group(1).strip()
    elif raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:]) if len(lines) > 1 else raw
        if raw.endswith("```"):
            raw = raw[:-3]

    # Try to extract JSON object if text has surrounding content
    brace_start = raw.find("{")
    brace_end = raw.rfind("}")
    if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
        raw = raw[brace_start:brace_end + 1]

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        log.error(f"{provider} returned invalid JSON: {e}")
        log.debug(f"Raw response (first 500 chars): {raw[:500]}")
        raise

    count = len(result.get("articles", []))
    log.info(f"{provider} processed {count} articles")
    return result


# ============================================================
# Phase 4: Output
# ============================================================

def merge_results(articles: list[dict], ai_result: dict) -> list[dict]:
    """Merge AI-generated content back into the original articles."""
    ai_articles = {a["index"]: a for a in ai_result.get("articles", [])}
    output = []
    for i, a in enumerate(articles):
        ai = ai_articles.get(i, {})
        entry = {
            "id": i + 1,
            "cat": ai.get("cat") or "strategy",
            "title": ai.get("title_cn", a["title"]),
            "title_en": a["title"],
            "source": a["source"],
            "url": a["url"],
            "time": relative_time(a["published"]),
            "published": a["published"].isoformat(),
            "summary": ai.get("summary_cn", a["summary"][:200]),
            "snark": ai.get("snark", ""),
        }
        if a.get("multi_source") and len(a["multi_source"]) > 1:
            entry["multiSource"] = sorted(a["multi_source"])
        output.append(entry)
    return output


def relative_time(dt: datetime) -> str:
    """Convert datetime to Chinese relative time string (Beijing time anchor)."""
    diff = datetime.now(BEIJING_TZ) - dt
    hours = int(diff.total_seconds() / 3600)
    if hours < 1:
        return f"{max(1, int(diff.total_seconds() / 60))}分钟前"
    elif hours < 24:
        return f"{hours}小时前"
    else:
        return f"{hours // 24}天前"


def build_output(articles: list[dict], ai_result: dict,
                  target_date: Optional[str] = None) -> dict:
    """Build the final output JSON."""
    items = merge_results(articles, ai_result)
    date_str = target_date or datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")
    return {
        "date": date_str,
        "generated_at": datetime.now(BEIJING_TZ).isoformat(),
        "highlight": ai_result.get("highlight", ""),
        "fun": ai_result.get("fun", {}),
        "articles": items,
        "stats": {
            "total": len(items),
            "model_count": sum(1 for i in items if i["cat"] == "model"),
            "strategy_count": sum(1 for i in items if i["cat"] == "strategy"),
            "tool_count": sum(1 for i in items if i["cat"] == "tool"),
        },
    }


# ============================================================
# Index
# ============================================================

def update_index(output: dict):
    """Maintain data/daily/index.json with all available dates."""
    index_path = OUTPUT_PATH / "index.json"
    index = {}
    try:
        if index_path.exists():
            index = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        index = {}

    date_str = output["date"]
    index[date_str] = {
        "date": date_str,
        "highlight": output.get("highlight", ""),
        "count": len(output.get("articles", [])),
        "stats": output.get("stats", {}),
    }

    # Keep last 60 days
    sorted_dates = sorted(index.keys(), reverse=True)[:60]
    index = {d: index[d] for d in sorted_dates}

    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info(f"Index updated ({len(index)} dates) → {index_path}")


# ============================================================
# WeChat Push (Server酱)
# ============================================================

def push_wechat(output: dict):
    """Push daily summary to WeChat via Server酱."""
    if not PUSH_ENABLED or not SERVERCHAN_KEY or SERVERCHAN_KEY.startswith("SCT_YOUR"):
        log.info("WeChat push disabled (no ServerChan key)")
        return

    date_str = output["date"]
    highlight = output.get("highlight", "")
    articles = output.get("articles", [])
    stats = output.get("stats", {})
    fun = output.get("fun", {})

    # Build markdown content
    lines = [
        f"## 智脉 AI 日报 | {date_str}",
        "",
        f"> {highlight}" if highlight else "",
        "",
        "### 今日资讯",
        "",
    ]
    for i, a in enumerate(articles[:8]):
        emoji = {"model": "🧠", "strategy": "🏢", "tool": "🔧"}.get(a.get("cat", ""), "📌")
        title = a.get("title", "")[:50]
        source = a.get("source", "")
        lines.append(f"{i+1}. {emoji} **{title}** — {source}")

    if fun:
        joke = fun.get("joke", "")
        advice = fun.get("advice", "").replace("\\n", " ")
        lines.extend([
            "",
            "### 今日冷笑话",
            f"> {joke}" if joke else "",
        ])

    lines.extend([
        "",
        f"📊 共{stats.get('total','?')}条 | 模型{stats.get('model_count','?')} 战略{stats.get('strategy_count','?')} 工具{stats.get('tool_count','?')}",
        "",
        "[📖 查看完整日报](https://rexchen595223656.github.io/ai-daily-pulse/)",
    ])

    title = f"智脉 AI 日报 | {date_str}"
    desp = "\n".join(lines)

    try:
        import urllib.request
        import urllib.parse
        url = f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send"
        data = urllib.parse.urlencode({"title": title, "desp": desp}).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10, context=_SSL_VERIFY) as resp:
            result = json.loads(resp.read())
            if result.get("code") == 0:
                log.info(f"WeChat push OK")
            else:
                log.warning(f"WeChat push failed: {result}")
    except Exception as e:
        log.warning(f"WeChat push error: {e}")


def auto_deploy():
    """Run deploy.sh to sync to GitHub Pages (non-blocking, best-effort)."""
    deploy_script = ROOT / "deploy.sh"
    if not deploy_script.exists():
        log.info("Deploy script not found, skipping auto-deploy")
        return
    try:
        result = subprocess.run(
            ["bash", str(deploy_script)],
            cwd=str(ROOT),
            capture_output=True,
            timeout=60,
        )
        if result.returncode == 0:
            log.info("Auto-deploy OK")
        else:
            log.warning(f"Auto-deploy failed (exit {result.returncode}): {result.stderr.decode()[:200]}")
    except Exception as e:
        log.warning(f"Auto-deploy error: {e}")


# ============================================================
# Helpers
# ============================================================

def strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    import re
    text = re.sub(r"<[^>]*>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="AI Daily Pipeline")
    parser.add_argument("--fetch-only", action="store_true", help="Only fetch, skip AI processing")
    parser.add_argument("--output", choices=["file", "stdout"], default="file")
    parser.add_argument("--api-key", help="AI API key override")
    parser.add_argument("--provider", choices=["deepseek", "claude"], help="AI provider: deepseek | claude")
    parser.add_argument("--claude", action="store_true", help="Shortcut for --provider claude")
    parser.add_argument("--date", help="Target date for backfill (YYYY-MM-DD), overrides time window")
    args = parser.parse_args()

    provider = "claude" if args.claude else (args.provider or AI_PROVIDER)

    # Resolve API key: CLI arg > env var > config
    if provider == "deepseek":
        api_key = args.api_key or os.environ.get("AI_DAILY_DS_KEY") or DEEPSEEK_API_KEY or ""
    else:
        api_key = args.api_key or os.environ.get("AI_DAILY_ANTHROPIC_KEY") or os.environ.get("ANTHROPIC_API_KEY") or ANTHROPIC_API_KEY or ""

    if not args.fetch_only and not api_key:
        log.error(f"No API key found for {provider}. Set in config, env, or use --api-key.")
        log.info("Running with --fetch-only instead.")
        args.fetch_only = True

    # Phase 1: Fetch
    raw = fetch_all(SOURCES)
    if not raw:
        log.error("No articles fetched. Check network / sources.")
        return 1

    # Phase 2: Filter
    articles = filter_time(raw, target_date=args.date)
    articles = filter_ai_keywords(articles)
    articles = deduplicate(articles)

    # Limit to target count
    articles = articles[:TARGET_ARTICLE_COUNT]
    log.info(f"Final selection: {len(articles)} articles")

    # Phase 3: AI Process
    if args.fetch_only:
        log.info("Skipping AI processing (--fetch-only)")
        ai_result = {"highlight": "", "articles": []}
        for i, a in enumerate(articles):
            ai_result["articles"].append({
                "index": i,
                "cat": "strategy",
                "title_cn": a["title"],
                "summary_cn": a["summary"][:200],
                "snark": "",
            })
    else:
        try:
            if provider == "deepseek":
                ai_result = call_deepseek(articles, api_key)
            else:
                ai_result = call_claude(articles, api_key)
        except Exception as e:
            log.error(f"AI API failed ({provider}): {e}")
            log.info("Falling back to raw output.")
            ai_result = {"highlight": "", "articles": []}
            for i, a in enumerate(articles):
                ai_result["articles"].append({
                    "index": i,
                    "cat": "strategy",
                    "title_cn": a["title"],
                    "summary_cn": a["summary"][:200],
                    "snark": "",
                })

    # Phase 4: Output
    output = build_output(articles, ai_result, target_date=args.date)

    if args.output == "stdout":
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
        date_str = args.date or datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")
        filepath = OUTPUT_PATH / f"{date_str}.json"
        filepath.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info(f"Output → {filepath}")

        # Also write latest.json
        latest_path = OUTPUT_PATH / "latest.json"
        latest_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info(f"Output → {latest_path}")

        # Update index.json for history archive
        update_index(output)

        # Push to WeChat
        push_wechat(output)

        # Auto deploy to GitHub Pages
        auto_deploy()

    # Print summary
    log.info("=" * 50)
    log.info(f"Date: {output['date']}")
    log.info(f"Articles: {output['stats']['total']} (模型:{output['stats']['model_count']} 战略:{output['stats']['strategy_count']} 工具:{output['stats']['tool_count']})")
    if output["highlight"]:
        log.info(f"Highlight: {output['highlight']}")
    for a in output["articles"]:
        log.info(f"  [{a['cat']}] {a['title'][:50]} — {a['source']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
