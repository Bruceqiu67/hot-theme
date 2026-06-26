"""
AI 数据校验工具函数单元测试
"""
import os
import sys
import json

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ai_validators  import (    _repair_truncated_json,
    _extract_json,
    _current_year,
    _to_score,
    _to_probability,
    _valid_stock_code,
    _normalize_choice,
    _safe_verification_text,
    _ensure_list,
    flatten_chains,
)


class TestRepairTruncatedJson:
    """测试被截断JSON的修复函数"""

    def test_complete_json_unchanged(self):
        """完整JSON应该原样返回"""
        text = '{"key": "value"}'
        result = _repair_truncated_json(text)
        assert json.loads(result) == {"key": "value"}

    def test_unclosed_braces(self):
        """未闭合的大括号应该被修复"""
        text = '{"key": "value"'
        result = _repair_truncated_json(text)
        assert result.count("{") == result.count("}")

    def test_unclosed_brackets(self):
        """未闭合的方括号应该被修复"""
        text = '{"items": [1, 2'
        result = _repair_truncated_json(text)
        assert result.count("[") == result.count("]")

    def test_nested_unclosed(self):
        """嵌套的未闭合结构应该被修复"""
        text = '{"outer": {"inner": [1, 2'
        result = _repair_truncated_json(text)
        assert result.count("{") == result.count("}")
        assert result.count("[") == result.count("]")

    def test_empty_string(self):
        """空字符串应该返回空字符串"""
        result = _repair_truncated_json("")
        assert result == ""


class TestExtractJson:
    """测试JSON提取函数"""

    def test_direct_json(self):
        """直接的JSON应该被提取"""
        text = '{"theme_name": "test"}'
        result = _extract_json(text)
        assert result == text

    def test_markdown_json_block(self):
        """markdown代码块中的JSON应该被提取"""
        text = '''一些文本
```json
{"theme_name": "test"}
```
更多文本'''
        result = _extract_json(text)
        assert result == '{"theme_name": "test"}'

    def test_json_with_prefix_text(self):
        """带有前缀文本的JSON应该被提取"""
        text = '这是分析结果：{"theme_name": "test"}'
        result = _extract_json(text)
        assert result == '{"theme_name": "test"}'

    def test_json_with_known_keys(self):
        """包含已知键的JSON应该被优先提取"""
        text = '''一些文本
{"theme_name": "test", "chains": []}
更多文本'''
        result = _extract_json(text)
        assert '"theme_name": "test"' in result

    def test_empty_text(self):
        """空文本应该返回空字符串"""
        result = _extract_json("")
        assert result == ""

    def test_no_json(self):
        """没有JSON的文本应该返回原文本"""
        text = "这里没有JSON"
        result = _extract_json(text)
        assert result == text


class TestCurrentYear:
    """测试获取当前年份函数"""

    def test_returns_integer(self):
        """应该返回整数"""
        result = _current_year()
        assert isinstance(result, int)

    def test_reasonable_year(self):
        """年份应该在合理范围内"""
        result = _current_year()
        assert 2020 <= result <= 2100


class TestToScore:
    """测试分数转换函数"""

    def test_valid_score(self):
        """有效分数应该被转换"""
        assert _to_score(5) == 5
        assert _to_score("7") == 7
        assert _to_score(8.5) == 8

    def test_boundary_scores(self):
        """边界分数应该被接受"""
        assert _to_score(1) == 1
        assert _to_score(10) == 10

    def test_out_of_range_score(self):
        """超出范围的分数应该返回默认值"""
        assert _to_score(0) is None
        assert _to_score(11) is None
        assert _to_score(-1) is None

    def test_invalid_score(self):
        """无效分数应该返回默认值"""
        assert _to_score("abc") is None
        assert _to_score(None) is None
        assert _to_score("") is None

    def test_custom_default(self):
        """应该支持自定义默认值"""
        assert _to_score("abc", default=0) == 0
        assert _to_score(0, default=5) == 5


class TestToProbability:
    """测试概率转换函数"""

    def test_valid_probability(self):
        """有效概率应该被转换"""
        assert _to_probability(50) == 50
        assert _to_probability("75") == 75
        assert _to_probability(80.5) == 80

    def test_boundary_probabilities(self):
        """边界概率应该被接受"""
        assert _to_probability(0) == 0
        assert _to_probability(100) == 100

    def test_out_of_range_probability(self):
        """超出范围的概率应该返回默认值"""
        assert _to_probability(-1) is None
        assert _to_probability(101) is None

    def test_invalid_probability(self):
        """无效概率应该返回默认值"""
        assert _to_probability("abc") is None
        assert _to_probability(None) is None

    def test_custom_default(self):
        """应该支持自定义默认值"""
        assert _to_probability("abc", default=0) == 0


class TestValidStockCode:
    """测试股票代码验证函数"""

    def test_valid_code(self):
        """有效股票代码应该被接受"""
        assert _valid_stock_code("000001") == "000001"
        assert _valid_stock_code("600000") == "600000"

    def test_short_code_padded(self):
        """短代码应该被补零"""
        assert _valid_stock_code("1") == "000001"
        assert _valid_stock_code("123") == "000123"

    def test_float_string_code(self):
        """浮点数字符串应该被处理"""
        assert _valid_stock_code("1.0") == "000001"
        assert _valid_stock_code("123.0") == "000123"

    def test_invalid_code(self):
        """无效代码应该返回空字符串"""
        assert _valid_stock_code("abc") == ""
        assert _valid_stock_code("1234567") == ""  # 7位数字

    def test_empty_code(self):
        """空代码应该返回补零后的代码"""
        assert _valid_stock_code("") == "000000"
        assert _valid_stock_code(None) == "000000"

    def test_whitespace_code(self):
        """带空格的代码应该被处理"""
        assert _valid_stock_code("  000001  ") == "000001"


class TestNormalizeChoice:
    """测试选择规范化函数"""

    def test_valid_choice(self):
        """有效选择应该被返回"""
        assert _normalize_choice("主板", ("主板", "创业板"), "主板") == "主板"
        assert _normalize_choice("创业板", ("主板", "创业板"), "主板") == "创业板"

    def test_invalid_choice(self):
        """无效选择应该返回默认值"""
        assert _normalize_choice("无效", ("主板", "创业板"), "主板") == "主板"

    def test_empty_choice(self):
        """空选择应该返回默认值"""
        assert _normalize_choice("", ("主板", "创业板"), "主板") == "主板"
        assert _normalize_choice(None, ("主板", "创业板"), "主板") == "主板"

    def test_whitespace_choice(self):
        """带空格的选择应该被处理"""
        assert _normalize_choice("  主板  ", ("主板", "创业板"), "主板") == "主板"


class TestSafeVerificationText:
    """测试安全验证文本函数"""

    def test_valid_text(self):
        """有效文本应该被返回"""
        assert _safe_verification_text("龙头") == "龙头"
        assert _safe_verification_text(" 龙头 ") == "龙头"

    def test_empty_fallback(self):
        """空值应该返回待核验"""
        assert _safe_verification_text("") == "待核验"
        assert _safe_verification_text(None) == "待核验"

    def test_unknown_values(self):
        """未知值应该返回待核验"""
        assert _safe_verification_text("未知") == "待核验"
        assert _safe_verification_text("不详") == "待核验"
        assert _safe_verification_text("暂无") == "待核验"


class TestEnsureList:
    """测试列表确保函数"""

    def test_list_input(self):
        """列表输入应该被处理"""
        assert _ensure_list(["a", "b", ""]) == ["a", "b"]

    def test_string_input(self):
        """字符串输入应该被分割"""
        result = _ensure_list("a,b,c")
        assert result == ["a", "b", "c"]

    def test_empty_string(self):
        """空字符串应该返回空列表"""
        assert _ensure_list("") == []

    def test_invalid_input(self):
        """无效输入应该返回空列表"""
        assert _ensure_list(123) == []
        assert _ensure_list(None) == []


class TestFlattenChains:
    """测试产业链展平函数"""

    def test_basic_flatten(self):
        """基本展平功能"""
        data = {
            "theme_name": "固态电池",
            "theme_quality": {"breadth": 8},
            "chains": [
                {
                    "level1": "上游",
                    "level2": "材料",
                    "level3": "电解质",
                    "stocks": [
                        {
                            "stock_code": "000001",
                            "stock_name": "测试A",
                            "market_type": "主板",
                        }
                    ]
                }
            ]
        }
        rows, quality = flatten_chains(data)
        assert len(rows) == 1
        assert rows[0]["theme_name"] == "固态电池"
        assert rows[0]["stock_code"] == "000001"
        assert quality == {"breadth": 8}

    def test_multiple_stocks(self):
        """多个股票应该展平为多行"""
        data = {
            "theme_name": "测试",
            "theme_quality": {},
            "chains": [
                {
                    "level1": "上游",
                    "level2": "材料",
                    "level3": "电解质",
                    "stocks": [
                        {"stock_code": "000001", "stock_name": "A"},
                        {"stock_code": "000002", "stock_name": "B"},
                    ]
                }
            ]
        }
        rows, _ = flatten_chains(data)
        assert len(rows) == 2

    def test_empty_chains(self):
        """空产业链应该返回空列表"""
        data = {
            "theme_name": "测试",
            "theme_quality": {},
            "chains": []
        }
        rows, _ = flatten_chains(data)
        assert len(rows) == 0


if __name__ == "__main__":
    pytest.main([__file__])