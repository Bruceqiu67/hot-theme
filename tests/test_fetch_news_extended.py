"""
新闻抓取模块扩展测试
"""
import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.fetch_news  import (    build_search_queries,
    calculate_fermentation_score,
    calculate_heat_score,
    calculate_heat_score_v2,
    dedupe_news,
    resolve_time_range,
    source_quality,
    _source_from_url,
    _news_id,
    extract_entities_from_news,
    build_entity_search_queries,
    BROAD_TOPIC_BLACKLIST,
    SOURCE_WEIGHTS,
    TIME_RANGE_OPTIONS,
    SEARCH_CATEGORIES,
    QUERY_TEMPLATES,
)


class TestResolveTimeRange:
    """测试时间范围解析函数"""

    def test_recent_6_hours(self):
        """测试最近6小时"""
        start, end = resolve_time_range("最近 6 小时")
        assert end >= start
        assert timedelta(hours=5, minutes=50) <= (end - start) <= timedelta(hours=6, minutes=10)

    def test_recent_12_hours(self):
        """测试最近12小时"""
        start, end = resolve_time_range("最近 12 小时")
        assert end >= start
        assert timedelta(hours=11, minutes=50) <= (end - start) <= timedelta(hours=12, minutes=10)

    def test_recent_24_hours(self):
        """测试最近24小时"""
        start, end = resolve_time_range("最近 24 小时")
        assert end >= start
        assert timedelta(hours=23, minutes=50) <= (end - start) <= timedelta(hours=24, minutes=10)

    def test_recent_3_days(self):
        """测试最近3天"""
        start, end = resolve_time_range("最近 3 天")
        assert end >= start
        assert timedelta(days=2, hours=23) <= (end - start) <= timedelta(days=3, hours=1)

    def test_recent_7_days(self):
        """测试最近7天"""
        start, end = resolve_time_range("最近 7 天")
        assert end >= start
        assert timedelta(days=6, hours=23) <= (end - start) <= timedelta(days=7, hours=1)

    def test_custom_time_range(self):
        """测试自定义时间范围"""
        custom_start = datetime(2026, 1, 1)
        custom_end = datetime(2026, 1, 10)
        start, end = resolve_time_range("自定义", custom_start, custom_end)
        assert start == custom_start
        assert end == custom_end

    def test_custom_time_range_swap(self):
        """测试自定义时间范围自动交换"""
        custom_start = datetime(2026, 1, 10)
        custom_end = datetime(2026, 1, 1)
        start, end = resolve_time_range("自定义", custom_start, custom_end)
        assert start == custom_end
        assert end == custom_start

    def test_unknown_time_range(self):
        """测试未知时间范围"""
        start, end = resolve_time_range("未知范围")
        assert end >= start


class TestBuildSearchQueries:
    """测试搜索查询构建函数"""

    def test_single_category(self):
        """测试单个类别"""
        queries = build_search_queries(["半导体"])
        query_texts = [item["query"] for item in queries]
        assert "先进封装 A股" in query_texts
        assert "HBM A股" in query_texts
        assert all(item["category"] == "半导体" for item in queries)

    def test_multiple_categories(self):
        """测试多个类别"""
        queries = build_search_queries(["半导体", "AI硬件"])
        categories = {item["category"] for item in queries}
        assert "半导体" in categories
        assert "AI硬件" in categories

    def test_custom_keywords(self):
        """测试自定义关键词"""
        queries = build_search_queries(["自定义关键词"], "液冷服务器，HBM")
        query_texts = [item["query"] for item in queries]
        assert "液冷服务器 A股 产业链 题材" in query_texts
        assert "HBM 概念股 催化 研报" in query_texts

    def test_custom_keywords_with_category(self):
        """测试自定义关键词和类别组合"""
        queries = build_search_queries(["半导体"], "液冷服务器")
        query_texts = [item["query"] for item in queries]
        assert "先进封装 A股" in query_texts
        assert "液冷服务器 A股 产业链 题材" in query_texts

    def test_deduplication(self):
        """测试去重功能"""
        queries = build_search_queries(["半导体", "半导体"])
        query_texts = [item["query"] for item in queries]
        assert len(query_texts) == len(set(query_texts))

    def test_empty_keywords(self):
        """测试空关键词"""
        queries = build_search_queries(["半导体"], "")
        assert len(queries) > 0
        assert all(item["category"] == "半导体" for item in queries)


class TestSourceFromUrl:
    """测试URL来源提取函数"""

    def test_normal_url(self):
        """测试正常URL"""
        assert _source_from_url("https://www.eastmoney.com/news/123") == "eastmoney.com"

    def test_url_without_www(self):
        """测试没有www的URL"""
        assert _source_from_url("https://eastmoney.com/news/123") == "eastmoney.com"

    def test_empty_url(self):
        """测试空URL"""
        assert _source_from_url("") == ""

    def test_none_url(self):
        """测试None URL"""
        assert _source_from_url(None) == ""


class TestNewsId:
    """测试新闻ID生成函数"""

    def test_same_url_same_id(self):
        """相同URL应该生成相同ID"""
        id1 = _news_id("https://example.com/news/1", "标题1")
        id2 = _news_id("https://example.com/news/1", "标题2")
        assert id1 == id2

    def test_different_url_different_id(self):
        """不同URL应该生成不同ID"""
        id1 = _news_id("https://example.com/news/1", "标题")
        id2 = _news_id("https://example.com/news/2", "标题")
        assert id1 != id2

    def test_empty_url_uses_title(self):
        """空URL应该使用标题生成ID"""
        id1 = _news_id("", "标题1")
        id2 = _news_id("", "标题1")
        assert id1 == id2

    def test_id_length(self):
        """ID长度应该为16"""
        news_id = _news_id("https://example.com", "标题")
        assert len(news_id) == 16


class TestSourceQuality:
    """测试来源质量评分函数"""

    def test_known_sources(self):
        """测试已知来源"""
        assert source_quality("cls.cn") == 0.95
        assert source_quality("eastmoney.com") == 0.9
        assert source_quality("10jqka.com.cn") == 0.88

    def test_unknown_source(self):
        """测试未知来源"""
        assert source_quality("unknown.com") == 0.55

    def test_url_with_known_host(self):
        """测试包含已知主机的URL"""
        assert source_quality("https://www.cls.cn/news/123") == 0.95


class TestDedupeNews:
    """测试新闻去重函数"""

    def test_exact_duplicate_urls(self):
        """测试完全重复的URL"""
        news = [
            {"title": "标题1", "url": "https://example.com/a"},
            {"title": "标题2", "url": "https://example.com/a"},
        ]
        result = dedupe_news(news)
        assert len(result) == 1

    def test_similar_titles(self):
        """测试相似标题"""
        news = [
            {"title": "HBM产业链景气上行", "url": "https://example.com/a"},
            {"title": "HBM 产业链景气上行", "url": "https://example.com/b"},
        ]
        result = dedupe_news(news)
        assert len(result) == 1

    def test_different_news(self):
        """测试不同新闻"""
        news = [
            {"title": "HBM产业链景气上行", "url": "https://example.com/a"},
            {"title": "液冷服务器需求提升", "url": "https://example.com/c"},
        ]
        result = dedupe_news(news)
        assert len(result) == 2

    def test_empty_list(self):
        """测试空列表"""
        result = dedupe_news([])
        assert len(result) == 0

    def test_no_url(self):
        """测试没有URL的新闻"""
        news = [
            {"title": "标题1", "url": ""},
            {"title": "标题2", "url": ""},
        ]
        result = dedupe_news(news)
        assert len(result) == 2


class TestExtractEntitiesFromNews:
    """测试实体提取函数"""

    def test_chinese_entities(self):
        """测试中文实体提取"""
        news = [
            {"title": "HBM产业链景气上行", "summary": "AI服务器需求带动HBM需求"},
        ]
        entities = extract_entities_from_news(news)
        assert "HBM" in entities
        assert any("产业链" in e for e in entities)

    def test_english_entities(self):
        """测试英文实体提取"""
        news = [
            {"title": "AI服务器需求提升", "summary": "HBM需求增长"},
        ]
        entities = extract_entities_from_news(news)
        assert "AI" in entities

    def test_max_entities(self):
        """测试最大实体数量限制"""
        news = [
            {"title": f"实体{i}", "summary": f"描述{i}"}
            for i in range(30)
        ]
        entities = extract_entities_from_news(news, max_entities=10)
        assert len(entities) <= 10

    def test_empty_news(self):
        """测试空新闻列表"""
        entities = extract_entities_from_news([])
        assert entities == []


class TestBuildEntitySearchQueries:
    """测试实体搜索查询构建函数"""

    def test_basic_entities(self):
        """测试基本实体查询构建"""
        entities = ["HBM", "先进封装"]
        queries = build_entity_search_queries(entities)
        assert len(queries) > 0
        assert len(queries) >= 4

    def test_max_queries(self):
        """测试最大查询数量限制"""
        entities = [f"实体{i}" for i in range(10)]
        queries = build_entity_search_queries(entities, max_queries=5)
        assert len(queries) <= 5

    def test_empty_entities(self):
        """测试空实体列表"""
        queries = build_entity_search_queries([])
        assert queries == []


class TestHeatScore:
    """测试热度评分函数"""

    def test_heat_score_basic(self):
        """测试基本热度评分"""
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

    def test_heat_score_empty_evidence(self):
        """测试空证据的热度评分"""
        topic = {
            "related_keywords": ["HBM"],
            "suggested_chains": ["存储芯片"],
        }
        score, level = calculate_heat_score(topic, [])
        assert 0 <= score <= 100
        assert level in {"高", "中", "低"}


class TestFermentationScore:
    """测试发酵评分函数"""

    def test_fermentation_score_basic(self):
        """测试基本发酵评分"""
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

    def test_fermentation_score_empty_evidence(self):
        """测试空证据的发酵评分"""
        topic = {
            "trigger_clues": ["政策发布"],
            "suggested_chains": ["材料"],
            "preliminary_related_stocks": ["测试A"],
        }
        score, status = calculate_fermentation_score(topic, [])
        assert 0 <= score <= 100
        assert status in {"预热中", "正在升温", "等待确认"}


class TestHeatScoreV2:
    """测试热度评分v2函数"""

    def test_heat_score_v2_basic(self):
        """测试热度评分v2计算"""
        topic = {
            "related_keywords": ["HBM", "先进封装", "AI服务器"],
            "suggested_chains": ["存储芯片", "封装", "设备"],
            "trigger_event": "政策发布",
            "core_logic": "技术突破",
            "topic_name": "HBM高带宽内存",
            "preliminary_related_stocks": ["公司A"],
        }
        evidence = [
            {"source": "eastmoney.com", "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
            {"source": "cls.cn", "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        ]
        score, level = calculate_heat_score_v2(topic, evidence)
        assert 0 <= score <= 100
        assert level in {"高", "中", "低"}


class TestConstants:
    """测试常量定义"""

    def test_time_range_options(self):
        """测试时间范围选项"""
        assert "最近 6 小时" in TIME_RANGE_OPTIONS
        assert "最近 24 小时" in TIME_RANGE_OPTIONS
        assert "自定义" in TIME_RANGE_OPTIONS

    def test_search_categories(self):
        """测试搜索类别"""
        assert "全市场热点" in SEARCH_CATEGORIES
        assert "半导体" in SEARCH_CATEGORIES
        assert "机器人" in SEARCH_CATEGORIES
        assert "自定义关键词" in SEARCH_CATEGORIES

    def test_query_templates_has_all_categories(self):
        """测试查询模板包含所有类别"""
        for cat in SEARCH_CATEGORIES:
            if cat == "自定义关键词":
                continue
            assert cat in QUERY_TEMPLATES, f"Missing template for {cat}"
            assert len(QUERY_TEMPLATES[cat]) > 0

    def test_source_weights_reasonable(self):
        """测试来源权重合理"""
        for source, weight in SOURCE_WEIGHTS.items():
            assert 0.5 <= weight <= 1.0, f"{source} weight out of range"

    def test_broad_topic_blacklist(self):
        """测试宽泛题材黑名单"""
        assert "半导体" in BROAD_TOPIC_BLACKLIST
        assert "AI" in BROAD_TOPIC_BLACKLIST


if __name__ == "__main__":
    pytest.main([__file__])