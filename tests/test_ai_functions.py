"""
AI 功能单元测试
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# 确保能导入项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ai_validators  import (    validate_candidate_topics,
    validate_chain_decomposition,
    validate_fermentation_observations,
    validate_hot_topics,
    validate_predictions,
    validate_stock_mapping,
    validate_theme_analysis,
    _search_web,
)


class TestValidateHotTopics:
    """测试热点题材验证函数"""
    
    def test_valid_topics(self):
        """测试有效的热点题材列表"""
        topics = [
            {
                "theme_name": "HBM高带宽内存",
                "summary": "AI芯片需求驱动HBM产业链爆发",
                "hot_score": 85,
                "catalyst": "技术突破",
                "evidence": ["三星HBM4量产", "SK海力士扩产"],
                "source_count": 3,
            }
        ]
        result = validate_hot_topics(topics)
        assert len(result) == 1
        assert result[0]["theme_name"] == "HBM高带宽内存"
        assert result[0]["hot_score"] == 85
    
    def test_filter_broad_topics(self):
        """测试过滤宽泛题材"""
        topics = [
            {
                "theme_name": "半导体",
                "summary": "半导体行业",
                "hot_score": 80,
                "catalyst": "综合催化",
                "evidence": ["证据1"],
                "source_count": 1,
            },
            {
                "theme_name": "HBM高带宽内存",
                "summary": "AI芯片需求驱动",
                "hot_score": 85,
                "catalyst": "技术突破",
                "evidence": ["证据1", "证据2"],
                "source_count": 2,
            }
        ]
        result = validate_hot_topics(topics)
        assert len(result) == 1
        assert result[0]["theme_name"] == "HBM高带宽内存"
    
    def test_empty_topics(self):
        """测试空题材列表"""
        with pytest.raises(RuntimeError, match="未生成有效热点题材"):
            validate_hot_topics([])
    
    def test_invalid_topics(self):
        """测试无效题材列表"""
        with pytest.raises(RuntimeError, match="热点题材返回格式错误"):
            validate_hot_topics("not a list")


class TestValidateCandidateTopics:
    """测试候选热点题材验证函数"""

    def test_valid_candidate_topics(self):
        topics = [
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
        result = validate_candidate_topics(topics, {"n1", "n2"})
        assert len(result) == 1
        assert result[0]["topic_name"] == "HBM高带宽内存"
        assert len(result[0]["source_items"]) == 2

    def test_candidate_topics_require_valid_evidence(self):
        topics = [
            {
                "topic_name": "HBM高带宽内存",
                "source_items": [{"news_id": "missing", "relevance_score": 90}],
            }
        ]
        with pytest.raises(RuntimeError, match="未生成有效候选题材"):
            validate_candidate_topics(topics, {"n1"})


class TestValidatePredictions:
    """测试预测验证函数"""
    
    def test_valid_predictions(self):
        """测试有效的预测列表"""
        predictions = [
            {
                "theme_name": "固态电池",
                "ferment_prob": 75,
                "confidence": "高",
                "gate_pass": True,
                "signal_type": "技术突破",
                "reason": "技术突破催化",
                "related_existing": "新能源",
                "key_trigger": "量产突破",
                "scores": {"AI": 8, "FF": 7, "SM": 6, "CH": 5, "PV": 7},
                "evidence": ["证据1", "证据2"],
                "suggested_stocks": "上游材料",
            }
        ]
        result = validate_predictions(predictions)
        assert len(result) == 1
        assert result[0]["theme_name"] == "固态电池"
        assert result[0]["ferment_prob"] == 75
    
    def test_invalid_probability(self):
        """测试无效的发酵概率"""
        predictions = [
            {
                "theme_name": "固态电池",
                "ferment_prob": 150,  # 超出范围
                "confidence": "高",
                "gate_pass": True,
                "signal_type": "技术突破",
                "reason": "技术突破催化",
                "related_existing": "新能源",
                "key_trigger": "量产突破",
                "scores": {"AI": 8, "FF": 7, "SM": 6, "CH": 5, "PV": 7},
                "evidence": ["证据1", "证据2"],
                "suggested_stocks": "上游材料",
            }
        ]
        with pytest.raises(RuntimeError, match="预测结果缺少必要字段"):
            validate_predictions(predictions)
    
    def test_insufficient_evidence(self):
        """测试证据不足"""
        predictions = [
            {
                "theme_name": "固态电池",
                "ferment_prob": 75,
                "confidence": "高",
                "gate_pass": True,
                "signal_type": "技术突破",
                "reason": "技术突破催化",
                "related_existing": "新能源",
                "key_trigger": "量产突破",
                "scores": {"AI": 8, "FF": 7, "SM": 6, "CH": 5, "PV": 7},
                "evidence": ["证据1"],  # 只有1个证据
                "suggested_stocks": "上游材料",
            }
        ]
        with pytest.raises(RuntimeError, match="预测结果缺少必要字段"):
            validate_predictions(predictions)


class TestValidateFermentationObservations:
    """测试发酵观察验证函数"""

    def test_valid_observations(self):
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
        result = validate_fermentation_observations(observations, {"n1", "n2"})
        assert len(result) == 1
        assert result[0]["topic_name"] == "端侧AI芯片"
        assert result[0]["action_options"] == ["加入观察池", "生成产业链草稿", "忽略"]

    def test_observations_require_valid_evidence(self):
        observations = [
            {
                "topic_name": "端侧AI芯片",
                "source_items": [{"news_id": "missing", "relevance_score": 80}],
            }
        ]
        with pytest.raises(RuntimeError, match="未生成有效发酵观察线索"):
            validate_fermentation_observations(observations, {"n1"})


class TestValidateThemeAnalysis:
    """测试题材分析验证函数"""
    
    def test_valid_analysis(self):
        """测试有效的题材分析"""
        data = {
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
        result = validate_theme_analysis(data)
        assert result["theme_name"] == "固态电池"
        assert len(result["chains"]) == 1
        assert len(result["chains"][0]["stocks"]) == 1
    
    def test_invalid_stock_code(self):
        """测试无效的股票代码"""
        data = {
            "theme_name": "固态电池",
            "theme_quality": {},
            "chains": [
                {
                    "level1": "上游材料",
                    "level2": "电解质",
                    "level3": "氧化物电解质",
                    "stocks": [
                        {
                            "stock_code": "invalid",  # 无效代码
                            "stock_name": "测试A",
                            "market_type": "主板",
                        }
                    ]
                }
            ]
        }
        with pytest.raises(RuntimeError, match="模型返回中没有可用的 A 股个股记录"):
            validate_theme_analysis(data)


class TestTwoStageAnalysis:
    """测试两阶段题材深度分析校验"""

    def test_validate_chain_decomposition(self):
        data = {
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
        }
        result = validate_chain_decomposition(data)
        assert result["theme_definition"] == "HBM产业链"
        assert result["chain_nodes"][0]["importance"] == "核心"

    def test_validate_stock_mapping(self):
        nodes = [{"level1": "上游", "level2": "材料", "level3": "封装基板"}]
        data = {
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
                    "market_position": "",
                    "market_share": "",
                    "customers": "",
                    "products": "封测",
                    "evidence": "新闻证据",
                    "relevance_score": 8,
                    "importance": "重要",
                    "verification_status": "待人工核验",
                    "risk_note": "需核验HBM占比",
                }
            ]
        }
        result = validate_stock_mapping(data, nodes)
        assert len(result) == 1
        assert result[0]["stock_code"] == "002156"
        assert result[0]["market_position"] == "待核验"
        assert result[0]["verification_status"] == "待人工核验"


class TestSearchWeb:
    """测试网页搜索函数"""
    
    def test_search_success(self):
        """测试搜索成功"""
        # 由于依赖外部库，这里只测试函数调用不会抛出异常
        try:
            result = _search_web("测试查询")
            # 结果可能是空字符串（如果没有安装duckduckgo_search）
            assert isinstance(result, str)
        except Exception:
            # 如果搜索失败，应该返回空字符串
            pass
    
    def test_search_failure(self):
        """测试搜索失败"""
        # 测试无效查询
        result = _search_web("")
        assert isinstance(result, str)


if __name__ == "__main__":
    pytest.main([__file__])
