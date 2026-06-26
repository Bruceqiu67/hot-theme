"""
UI 组件单元测试
"""
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock streamlit before importing ui_components
sys.modules['streamlit'] = MagicMock()

from ui_components import (
    esc,
    score_tone,
    level_tone,
    field_html,
    chips,
    badge,
    TONE_COLORS,
    SERENITY_DIMENSIONS,
    SERENITY_GRADE_COLORS,
    serenity_dimension_badge,
    serenity_composite_badge,
    serenity_dimension_bar,
)


class TestEsc:
    """测试HTML转义函数"""

    def test_escapes_html(self):
        """应该转义HTML特殊字符"""
        assert esc("<script>") == "&lt;script&gt;"
        assert esc("a&b") == "a&amp;b"
        assert esc('"quotes"') == "&quot;quotes&quot;"

    def test_none_returns_empty(self):
        """None应该返回空字符串"""
        assert esc(None) == ""

    def test_empty_string(self):
        """空字符串应该返回空字符串"""
        assert esc("") == ""

    def test_normal_text(self):
        """普通文本应该原样返回"""
        assert esc("hello") == "hello"
        assert esc("测试") == "测试"


class TestScoreTone:
    """测试分数颜色函数"""

    def test_high_score(self):
        """高分应该返回绿色"""
        assert score_tone(80) == "green"
        assert score_tone(90) == "green"
        assert score_tone(100) == "green"

    def test_mid_score(self):
        """中分应该返回琥珀色"""
        assert score_tone(60) == "amber"
        assert score_tone(70) == "amber"

    def test_low_score(self):
        """低分应该返回石板色"""
        assert score_tone(50) == "slate"
        assert score_tone(0) == "slate"

    def test_invalid_score(self):
        """无效分数应该返回默认色"""
        assert score_tone(None) == "default"
        assert score_tone("abc") == "default"


class TestLevelTone:
    """测试级别颜色函数"""

    def test_heat_levels(self):
        """测试热度级别"""
        assert level_tone("高") == "green"
        assert level_tone("中") == "amber"
        assert level_tone("低") == "slate"

    def test_fermentation_status(self):
        """测试发酵状态"""
        assert level_tone("正在升温") == "green"
        assert level_tone("预热中") == "amber"
        assert level_tone("等待确认") == "slate"

    def test_draft_status(self):
        """测试草稿状态"""
        assert level_tone("draft") == "amber"
        assert level_tone("confirmed") == "green"
        assert level_tone("discarded") == "red"

    def test_stock_importance(self):
        """测试股票重要性"""
        assert level_tone("核心") == "green"
        assert level_tone("重要") == "blue"
        assert level_tone("观察") == "amber"
        assert level_tone("泛相关") == "slate"

    def test_unknown(self):
        """未知值应该返回默认色"""
        assert level_tone("未知") == "default"
        assert level_tone("") == "default"


class TestFieldHtml:
    """测试字段HTML函数"""

    def test_basic_field(self):
        """测试基本字段"""
        result = field_html("标签", "值")
        assert "标签" in result
        assert "值" in result

    def test_list_value(self):
        """测试列表值"""
        result = field_html("标签", ["a", "b", "c"])
        assert "a、b、c" in result

    def test_fallback(self):
        """测试空值回退"""
        result = field_html("标签", "")
        assert "-" in result

    def test_none_value(self):
        """测试None值"""
        result = field_html("标签", None)
        assert "-" in result

    def test_custom_fallback(self):
        """测试自定义回退"""
        result = field_html("标签", "", fallback="N/A")
        assert "N/A" in result


class TestChips:
    """测试标签函数"""

    def test_string_input(self):
        """测试字符串输入"""
        result = chips("a、b、c")
        assert "a" in result
        assert "b" in result
        assert "c" in result

    def test_list_input(self):
        """测试列表输入"""
        result = chips(["a", "b", "c"])
        assert "a" in result
        assert "b" in result
        assert "c" in result

    def test_empty(self):
        """测试空输入"""
        result = chips("")
        assert "-" in result

    def test_truncates(self):
        """测试截断"""
        values = [f"item{i}" for i in range(20)]
        result = chips(values)
        assert "item0" in result
        assert "item11" in result
        assert "item12" not in result


class TestBadge:
    """测试徽章函数"""

    def test_default_badge(self):
        """测试默认徽章"""
        result = badge("测试")
        assert "测试" in result
        assert "chip" in result

    def test_tone_badge(self):
        """测试带颜色的徽章"""
        result = badge("测试", tone="green")
        assert "测试" in result


class TestToneColors:
    """测试颜色配置"""

    def test_all_tones_defined(self):
        """所有颜色应该被定义"""
        assert "default" in TONE_COLORS
        assert "blue" in TONE_COLORS
        assert "green" in TONE_COLORS
        assert "amber" in TONE_COLORS
        assert "red" in TONE_COLORS
        assert "slate" in TONE_COLORS

    def test_each_tone_has_three_values(self):
        """每个颜色应该有三个值"""
        for tone, colors in TONE_COLORS.items():
            assert len(colors) == 3, f"{tone} should have 3 values"


# ============================================================================
# Serenity UI 组件测试
# ============================================================================


class TestSerenityDimensions:
    """四维配置完整性"""

    def test_all_four_dimensions_defined(self):
        assert "bottleneck" in SERENITY_DIMENSIONS
        assert "institutional" in SERENITY_DIMENSIONS
        assert "value" in SERENITY_DIMENSIONS
        assert "valuation" in SERENITY_DIMENSIONS

    def test_each_dimension_has_required_keys(self):
        for key, dim in SERENITY_DIMENSIONS.items():
            assert "label" in dim
            assert "icon" in dim
            assert "color" in dim
            assert "bg" in dim
            assert "description" in dim

    def test_colors_are_hex(self):
        for dim in SERENITY_DIMENSIONS.values():
            assert dim["color"].startswith("#")
            assert dim["bg"].startswith("#")


class TestSerenityGradeColors:
    """综合评级配色"""

    def test_all_grades_defined(self):
        for grade in ("A", "B", "C", "D", "F"):
            assert grade in SERENITY_GRADE_COLORS

    def test_each_grade_has_two_colors(self):
        for grade, colors in SERENITY_GRADE_COLORS.items():
            assert len(colors) == 2, f"Grade {grade} should have (fg, bg)"
            assert colors[0].startswith("#")
            assert colors[1].startswith("#")


class TestSerenityDimensionBadge:
    """四维单项徽章"""

    def test_valid_dimension(self):
        result = serenity_dimension_badge("bottleneck", 85)
        assert "85" in result
        assert "卡脖子" in result

    def test_invalid_dimension_returns_empty(self):
        assert serenity_dimension_badge("nonexistent", 50) == ""

    def test_institutional_badge(self):
        result = serenity_dimension_badge("institutional", 42)
        assert "机构信号" in result
        assert "42" in result


class TestSerenityCompositeBadge:
    """综合置信度徽章"""

    def test_grade_a(self):
        result = serenity_composite_badge(90, "A")
        assert "90" in result
        assert "A" in result
        assert "Serenity" in result

    def test_grade_f(self):
        result = serenity_composite_badge(15, "F")
        assert "15" in result
        assert "F" in result


class TestSerenityDimensionBar:
    """维度进度条"""

    def test_basic_bar(self):
        result = serenity_dimension_bar("卡脖子指数", 75, "#FF6A00", "#2E1A00")
        assert "75" in result
        assert "卡脖子指数" in result
        assert "75%" in result

    def test_zero_score(self):
        result = serenity_dimension_bar("测试", 0, "#000", "#111")
        assert "0%" in result

    def test_full_score(self):
        result = serenity_dimension_bar("测试", 100, "#000", "#111")
        assert "100%" in result


if __name__ == "__main__":
    pytest.main([__file__])