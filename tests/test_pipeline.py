"""Unit tests for AI Daily pipeline core functions."""

import sys
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Add pipeline dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

from run import strip_html, title_similarity, deduplicate, relative_time, merge_results, _parse_ai_json


# ---- strip_html ----

def test_strip_html():
    assert strip_html("<p>Hello</p>") == "Hello"
    assert strip_html("<a href='x'>link</a> text") == "link text"
    assert strip_html("plain text") == "plain text"
    assert strip_html("<div><span>nested</span></div>") == "nested"
    assert strip_html("") == ""


# ---- title_similarity ----

def test_title_similarity_identical():
    assert title_similarity("GPT-5 released", "GPT-5 released") == 1.0

def test_title_similarity_different():
    assert title_similarity("GPT-5", "Claude 4.7") < 0.3

def test_title_similarity_case_insensitive():
    assert title_similarity("gpt-5 RELEASED", "GPT-5 released") > 0.9


# ---- deduplicate ----

def test_deduplicate_identical_titles():
    now = datetime.now(timezone.utc)
    articles = [
        {"title": "GPT-5 released", "source": "TechCrunch", "published": now},
        {"title": "GPT-5 released", "source": "The Verge", "published": now - timedelta(hours=1)},
    ]
    result = deduplicate(articles, threshold=0.6)
    assert len(result) == 1
    assert "multi_source" in result[0]
    assert result[0]["multi_source"] == {"TechCrunch", "The Verge"}

def test_deduplicate_keeps_most_recent():
    now = datetime.now(timezone.utc)
    articles = [
        {"title": "GPT-5 released", "source": "Old Source", "published": now - timedelta(hours=5)},
        {"title": "GPT-5 released", "source": "New Source", "published": now},
    ]
    result = deduplicate(articles, threshold=0.6)
    assert len(result) == 1
    assert result[0]["source"] == "New Source"

def test_deduplicate_different_titles():
    now = datetime.now(timezone.utc)
    articles = [
        {"title": "GPT-5 released", "source": "A", "published": now},
        {"title": "Claude 4.7 announced", "source": "B", "published": now - timedelta(hours=1)},
    ]
    result = deduplicate(articles, threshold=0.6)
    assert len(result) == 2


# ---- relative_time ----

def test_relative_time_minutes():
    now = datetime.now(timezone.utc)
    dt = now - timedelta(minutes=5)
    result = relative_time(dt)
    assert "分钟前" in result

def test_relative_time_hours():
    now = datetime.now(timezone.utc)
    dt = now - timedelta(hours=3)
    result = relative_time(dt)
    assert "小时前" in result

def test_relative_time_days():
    now = datetime.now(timezone.utc)
    dt = now - timedelta(hours=48)
    result = relative_time(dt)
    assert "天前" in result


# ---- merge_results ----

def test_merge_results_injects_ai_content():
    now = datetime.now(timezone.utc)
    articles = [
        {"title": "Original Title", "source": "TestSrc", "published": now, "summary": "Raw summary", "url": "http://x.com"},
    ]
    ai_result = {
        "articles": [
            {"index": 0, "cat": "model", "title_cn": "中文标题", "summary_cn": "AI摘要", "snark": "吐槽"},
        ]
    }
    result = merge_results(articles, ai_result)
    assert len(result) == 1
    assert result[0]["title"] == "中文标题"
    assert result[0]["summary"] == "AI摘要"
    assert result[0]["snark"] == "吐槽"
    assert result[0]["cat"] == "model"

def test_merge_results_missing_ai_entry():
    now = datetime.now(timezone.utc)
    articles = [
        {"title": "T1", "source": "S", "published": now, "summary": "Raw", "url": "http://x.com"},
        {"title": "T2", "source": "S", "published": now, "summary": "Raw", "url": "http://x.com"},
    ]
    ai_result = {"articles": [{"index": 0, "cat": "tool", "title_cn": "T1 CN", "summary_cn": "sum1", "snark": "s"}]}
    result = merge_results(articles, ai_result)
    assert len(result) == 2
    assert result[0]["cat"] == "tool"
    assert result[1]["cat"] == "strategy"  # default when AI entry missing


# ---- _parse_ai_json ----

def test_parse_plain_json():
    result = _parse_ai_json('{"highlight": "test", "articles": []}')
    assert result["highlight"] == "test"

def test_parse_json_with_markdown_fence():
    text = '```json\n{"highlight": "h", "articles": []}\n```'
    result = _parse_ai_json(text)
    assert result["highlight"] == "h"

def test_parse_json_with_text_wrapping():
    text = 'Sure, here is the JSON:\n{"highlight": "h", "articles": []}\nHope this helps!'
    result = _parse_ai_json(text)
    assert result["highlight"] == "h"

def test_parse_invalid_json_raises():
    with pytest.raises(json.JSONDecodeError):
        _parse_ai_json("not json at all")


# ---- filter_time (integration-style) ----
from run import filter_time

def test_filter_time_excludes_old_articles():
    now = datetime.now(timezone.utc)
    fresh = {"title": "Fresh", "published": now - timedelta(hours=2)}
    stale = {"title": "Stale", "published": now - timedelta(hours=30)}
    result = filter_time([fresh, stale], hours=24)
    assert len(result) == 1
    assert result[0]["title"] == "Fresh"

def test_filter_time_handles_timezone_aware():
    now = datetime.now(timezone.utc)
    article = {"title": "T", "published": now - timedelta(hours=5, minutes=1)}
    result = filter_time([article], hours=5)
    # 5h1m ago > 5h window, should be excluded
    assert len(result) == 0


# ---- filter_ai_keywords ----
from run import filter_ai_keywords

def test_filter_keeps_ai_specific():
    articles = [
        {"title": "Something AI", "summary": "", "ai_specific": True, "lang": "en"},
    ]
    result = filter_ai_keywords(articles)
    assert len(result) == 1

def test_filter_requires_two_keywords_for_general():
    articles = [
        {"title": "AI is great", "summary": "no second keyword", "ai_specific": False, "lang": "en"},
        {"title": "LLM and GPT models", "summary": "multiple keywords here", "ai_specific": False, "lang": "en"},
    ]
    result = filter_ai_keywords(articles)
    # First article: only "AI" matches once, need 2+
    # Second article: "LLM" + "GPT" = 2 matches → passes
    assert len(result) == 1
    assert result[0]["title"] == "LLM and GPT models"
