"""
集成测试 - 测试模块间的交互
"""
import os
import sys
import tempfile

import pytest
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.database as db
import core.ai_validators as ai_validators
import core.fetch_news as fetch_news


@pytest.fixture(autouse=True)
def use_temp_db(monkeypatch):
    """每个测试使用独立临时数据库"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr("core.database.DB_PATH", path)
    db.init_db()
    yield
    try:
        os.unlink(path)
    except OSError:
        pass


class TestDatabaseAndValidatorsIntegration:
    """测试数据库和验证器的集成"""

    def test_import_validated_theme_analysis(self):
        """测试导入经过验证的题材分析数据"""
        ai_data = {
            "theme_name": "固态电池",
            "theme_quality": {
                "breadth": 8,
                "event_density": 7,
                "capital_flow": 6,
                "sustainability": 9,
                "overall_score": 8,
                "summary": "优质题材",
            },
            "chains": [
                {
                    "level1": "上游材料",
                    "level2": "电解质",
                    "level3": "氧化物电解质",
                    "stocks": [
                        {
                            "stock_code": "000001",
                            "stock_name": "测试A",
                            "market_type": "主板",
                            "importance": "高",
                            "tier": "核心",
                            "biz_relevance": 8,
                            "biz_growth": 7,
                            "quality_score": 6,
                            "flow_score": 7,
                        }
                    ]
                }
            ]
        }

        validated = ai_validators.validate_theme_analysis(ai_data)
        assert validated["theme_name"] == "固态电池"

        rows = []
        for chain in validated["chains"]:
            for stock in chain["stocks"]:
                rows.append({
                    "theme_name": validated["theme_name"],
                    "level1": chain["level1"],
                    "level2": chain["level2"],
                    "level3": chain["level3"],
                    **stock,
                })
        df = pd.DataFrame(rows)
        n = db.import_dataframe(df)
        assert n == 1

        stock = db.get_stock_by_code("000001")
        assert stock is not None
        assert stock["theme_name"] == "固态电池"
        assert stock["tier"] == "核心"

    def test_hot_topic_workflow(self):
        """测试热点题材工作流程"""
        news = [
            {
                "news_id": "n1",
                "title": "HBM产业链景气上行",
                "summary": "AI服务器需求带动HBM需求",
                "content": "",
                "source": "eastmoney.com",
                "url": "https://example.com/n1",
                "published_at": "",
                "fetched_at": "2026-05-26 10:00:00",
                "search_query": "HBM A股",
                "category": "半导体",
            },
        ]

        saved = db.save_raw_news(news)
        assert saved == 1

        candidate_topics = [
            {
                "topic_name": "HBM高带宽内存",
                "heat_score": 82,
                "heat_level": "高",
                "trigger_event": "AI服务器需求提升",
                "core_logic": "HBM需求增长带动产业链",
                "evidence_summary": "两条资讯共同指向HBM和先进封装",
                "source_items": [
                    {"news_id": "n1", "relevance_score": 90, "reason": "直接提及HBM"},
                ],
                "suggested_chains": ["存储芯片", "先进封装"],
                "related_keywords": ["HBM", "AI服务器"],
                "preliminary_related_stocks": ["香农芯创"],
                "confidence": "高",
                "should_import": True,
                "reason_to_import": "题材可拆解",
                "risk_note": "需核验业务占比",
            }
        ]

        news_by_id = {item["news_id"]: item for item in news}
        saved = db.save_hot_topic_candidates(candidate_topics, news_by_id)
        assert saved == 1

        candidates = db.get_hot_topic_candidates()
        assert len(candidates) == 1
        assert candidates[0]["topic_name"] == "HBM高带宽内存"

        evidence = db.get_topic_evidence(candidates[0]["topic_id"])
        assert len(evidence) == 1

    def test_analysis_draft_workflow(self):
        """测试分析草稿工作流程"""
        draft_data = {
            "topic_name": "HBM高带宽内存",
            "theme_definition": "HBM产业链",
            "trigger_event": "AI服务器需求提升",
            "core_logic": "高带宽内存需求增长",
            "industry_scope": "存储、封装、设备",
            "excluded_scope": "泛AI应用",
            "chain_nodes": [
                {
                    "level1": "上游",
                    "level2": "材料",
                    "level3": "封装基板",
                    "node_description": "先进封装材料",
                    "why_it_matters": "影响良率",
                    "importance": "核心",
                }
            ],
            "stocks": [
                {
                    "stock_code": "002156",
                    "stock_name": "通富微电",
                    "market_type": "主板",
                    "level1": "上游",
                    "level2": "材料",
                    "level3": "封装基板",
                    "role": "封测厂商",
                    "logic_summary": "先进封装相关",
                    "market_position": "待核验",
                    "market_share": "待核验",
                    "customers": "待核验",
                    "products": "封测",
                    "evidence": "新闻证据",
                    "relevance_score": 8,
                    "importance": "重要",
                    "verification_status": "待人工核验",
                    "risk_note": "需核验HBM占比",
                }
            ],
        }

        draft_id = db.create_analysis_draft(1, "HBM高带宽内存", draft_data)
        assert draft_id > 0

        row = db.get_analysis_draft(draft_id)
        assert row is not None
        assert row["status"] == "draft"

        draft = row["draft"]
        draft["core_logic"] = "更新后的逻辑"
        db.update_analysis_draft(draft_id, draft)

        n = db.confirm_analysis_draft(draft_id)
        assert n == 1

        stock = db.get_stock_by_code("002156")
        assert stock is not None
        assert stock["theme_name"] == "HBM高带宽内存"


class TestFetchNewsAndDatabaseIntegration:
    """测试新闻抓取和数据库的集成"""

    def test_news_deduplication_and_storage(self):
        """测试新闻去重和存储"""
        news = [
            {"title": "HBM产业链景气上行", "url": "https://example.com/a"},
            {"title": "HBM产业链景气上行", "url": "https://example.com/a"},
            {"title": "液冷服务器需求提升", "url": "https://example.com/c"},
        ]

        deduped = fetch_news.dedupe_news(news)
        assert len(deduped) == 2

        for item in deduped:
            item["news_id"] = fetch_news._news_id(item["url"], item["title"])
            item["summary"] = ""
            item["content"] = ""
            item["source"] = fetch_news._source_from_url(item["url"])
            item["published_at"] = ""
            item["fetched_at"] = "2026-05-26 10:00:00"
            item["search_query"] = "测试"
            item["category"] = "测试"

        saved = db.save_raw_news(deduped)
        assert saved == 2

    def test_heat_score_with_database_evidence(self):
        """测试使用数据库证据计算热度分数"""
        news = [
            {
                "news_id": "n1",
                "title": "HBM产业链景气上行",
                "summary": "AI服务器需求带动HBM需求",
                "content": "",
                "source": "eastmoney.com",
                "url": "https://example.com/n1",
                "published_at": "",
                "fetched_at": "2026-05-26 10:00:00",
                "search_query": "HBM A股",
                "category": "半导体",
            },
            {
                "news_id": "n2",
                "title": "先进封装需求增长",
                "summary": "先进封装受益AI芯片",
                "content": "",
                "source": "cls.cn",
                "url": "https://example.com/n2",
                "published_at": "",
                "fetched_at": "2026-05-26 10:01:00",
                "search_query": "先进封装 A股",
                "category": "半导体",
            },
        ]
        db.save_raw_news(news)

        news_ids = ["n1", "n2"]
        evidence = db.get_raw_news_by_ids(news_ids)
        assert len(evidence) == 2

        topic = {
            "related_keywords": ["HBM", "先进封装", "AI服务器"],
            "suggested_chains": ["存储芯片", "封装", "设备"],
        }
        score, level = fetch_news.calculate_heat_score(topic, evidence)
        assert 0 <= score <= 100
        assert level in {"高", "中", "低"}


class TestValidatorsAndFetchNewsIntegration:
    """测试验证器和新闻抓取的集成"""

    def test_validate_candidate_topics_with_evidence(self):
        """测试验证候选题材及其证据"""
        valid_news_ids = {"n1", "n2", "n3"}

        candidate_topics = [
            {
                "topic_name": "HBM高带宽内存",
                "heat_score": 70,
                "heat_level": "高",
                "trigger_event": "AI服务器需求提升",
                "core_logic": "HBM需求增长带动产业链",
                "evidence_summary": "多条资讯指向需求上行",
                "source_items": [
                    {"news_id": "n1", "relevance_score": 90, "reason": "直接相关"},
                    {"news_id": "n2", "relevance_score": 75, "reason": "间接相关"},
                ],
                "suggested_chains": ["存储芯片", "先进封装"],
                "related_keywords": ["HBM", "AI服务器"],
                "preliminary_related_stocks": ["香农芯创"],
                "confidence": "高",
                "should_import": True,
                "reason_to_import": "产业链可拆解",
                "risk_note": "需核验公司业务占比",
            }
        ]

        validated = ai_validators.validate_candidate_topics(candidate_topics, valid_news_ids)
        assert len(validated) == 1
        assert validated[0]["topic_name"] == "HBM高带宽内存"

    def test_validate_fermentation_observations(self):
        """测试验证发酵观察数据"""
        valid_news_ids = {"n1", "n2"}

        observations = [
            {
                "topic_name": "端侧AI芯片",
                "fermentation_score": 66,
                "status": "预热中",
                "trigger_clues": ["新品发布", "研报提及"],
                "why_watch": "端侧模型带动芯片和存储需求",
                "related_keywords": ["端侧AI", "AI芯片"],
                "suggested_chains": ["芯片", "存储", "模组"],
                "preliminary_related_stocks": ["测试A"],
                "evidence_count": 2,
                "source_summary": "多条资讯提到端侧AI产品催化",
                "source_items": [
                    {"news_id": "n1", "relevance_score": 80, "reason": "直接提及"},
                    {"news_id": "n2", "relevance_score": 70, "reason": "产业链相关"},
                ],
                "next_signals_to_watch": ["更多厂商发布新品"],
                "risk_note": "需核验产业链公司匹配度",
            }
        ]

        validated = ai_validators.validate_fermentation_observations(observations, valid_news_ids)
        assert len(validated) == 1
        assert validated[0]["topic_name"] == "端侧AI芯片"


class TestFlattenAndImport:
    """测试展平和导入的集成"""

    def test_flatten_and_import(self):
        """测试展平后导入数据库"""
        data = {
            "theme_name": "固态电池",
            "theme_quality": {"breadth": 8, "overall_score": 7},
            "chains": [
                {
                    "level1": "上游材料",
                    "level2": "电解质",
                    "level3": "氧化物电解质",
                    "stocks": [
                        {
                            "stock_code": "000001",
                            "stock_name": "测试A",
                            "market_type": "主板",
                            "importance": "高",
                            "tier": "核心",
                        },
                        {
                            "stock_code": "000002",
                            "stock_name": "测试B",
                            "market_type": "创业板",
                            "importance": "中",
                            "tier": "次级",
                        }
                    ]
                }
            ]
        }

        rows, quality = ai_validators.flatten_chains(data)
        assert len(rows) == 2
        assert quality == {"breadth": 8, "overall_score": 7}

        df = pd.DataFrame(rows)
        n = db.import_dataframe(df)
        assert n == 2

        stats = db.get_db_stats()
        assert stats["theme_count"] == 1
        assert stats["stock_count"] == 2
        assert stats["total_rows"] == 2


if __name__ == "__main__":
    pytest.main([__file__])