"""
新闻抓取与规则评分测试
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.fetch_news  import (    build_search_queries,
    calculate_fermentation_score,
    calculate_heat_score,
    dedupe_news,
    resolve_time_range,
)


def test_build_search_queries_semiconductor():
    queries = build_search_queries(["半导体"], "")
    query_texts = [item["query"] for item in queries]
    assert "先进封装 A股" in query_texts
    assert "HBM A股" in query_texts
    assert all(item["category"] == "半导体" for item in queries)


def test_build_search_queries_custom_keywords():
    queries = build_search_queries(["自定义关键词"], "液冷服务器，HBM")
    query_texts = [item["query"] for item in queries]
    assert "液冷服务器 A股 产业链 题材" in query_texts
    assert "HBM 概念股 催化 研报" in query_texts


def test_resolve_time_range_recent_6_hours():
    start, end = resolve_time_range("最近 6 小时")
    assert end >= start
    assert timedelta(hours=5, minutes=50) <= (end - start) <= timedelta(hours=6, minutes=10)


def test_dedupe_news_by_url_and_similar_title():
    news = [
        {"title": "HBM产业链景气上行", "url": "https://example.com/a"},
        {"title": "HBM产业链景气上行", "url": "https://example.com/a"},
        {"title": "HBM 产业链景气上行", "url": "https://example.com/b"},
        {"title": "液冷服务器需求提升", "url": "https://example.com/c"},
    ]
    result = dedupe_news(news)
    assert len(result) == 2


def test_calculate_heat_score():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    topic = {
        "related_keywords": ["HBM", "先进封装", "AI服务器"],
        "suggested_chains": ["存储芯片", "封装", "设备"],
    }
    evidence = [
        {"source": "eastmoney.com", "fetched_at": now},
        {"source": "cls.cn", "fetched_at": now},
    ]
    score, level = calculate_heat_score(topic, evidence)
    assert 0 <= score <= 100
    assert level in {"高", "中", "低"}


def test_calculate_fermentation_score():
    topic = {
        "trigger_clues": ["政策发布带来新催化", "订单增长"],
        "suggested_chains": ["材料", "设备", "应用"],
        "preliminary_related_stocks": ["测试A", "测试B"],
    }
    evidence = [
        {"source": "eastmoney.com", "search_query": "新材料 A股", "category": "科技成长"},
        {"source": "cls.cn", "search_query": "新材料 研报", "category": "全市场热点"},
    ]
    score, status = calculate_fermentation_score(topic, evidence)
    assert 0 <= score <= 100
    assert status in {"预热中", "正在升温", "等待确认"}
