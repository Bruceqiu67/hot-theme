"""
Serenity 四维分析框架测试
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.serenity_analyzer import (
    # 枚举
    IndustryPosition, BottleneckLevel, ValuationRegime, SignalStrength,
    # 数据类
    BottleneckResult, InstitutionalResult, ValueResult, ValuationResetResult,
    SerenityReport,
    # 核心分析函数
    analyze_bottleneck,
    analyze_institutional_behavior,
    analyze_long_term_value,
    analyze_valuation_reset,
    generate_serenity_report,
    quick_score_stock,
    quick_score_theme,
    # 序列化
    report_to_dict,
    report_to_json,
    # 启发式
    DecisionHeuristic,
    # 辅助
    _clamp, _safe_float, _weighted_average,
    _substitution_to_score, _score_to_bottleneck_level,
    _roe_to_score, _gross_margin_to_score,
    _signal_from_score, _determine_regime,
    _composite_grade,
)


# ============================================================================
# 辅助函数测试
# ============================================================================


class TestClamp:
    def test_within_range(self):
        assert _clamp(50) == 50

    def test_below_range(self):
        assert _clamp(-10) == 0

    def test_above_range(self):
        assert _clamp(200) == 100

    def test_custom_range(self):
        assert _clamp(150, high=200) == 150
        assert _clamp(300, high=200) == 200


class TestSafeFloat:
    def test_normal(self):
        assert _safe_float(3.14) == 3.14

    def test_int(self):
        assert _safe_float(42) == 42.0

    def test_none(self):
        assert _safe_float(None) == 0.0

    def test_string(self):
        assert _safe_float("3.14") == 3.14

    def test_invalid(self):
        assert _safe_float("abc") == 0.0

    def test_custom_default(self):
        assert _safe_float("abc", default=99.0) == 99.0


class TestWeightedAverage:
    def test_simple(self):
        assert _weighted_average([(100, 1.0)]) == 100.0

    def test_balanced(self):
        assert _weighted_average([(80, 0.5), (60, 0.5)]) == 70.0

    def test_unequal_weights(self):
        avg = _weighted_average([(100, 0.8), (0, 0.2)])
        assert avg == 80.0

    def test_empty(self):
        assert _weighted_average([]) == 50.0

    def test_zero_weights(self):
        assert _weighted_average([(100, 0), (50, 0)]) == 50.0


# ============================================================================
# 卡脖子指数测试
# ============================================================================


class TestBottleneckScoring:
    def test_substitution_to_score_critical(self):
        """国产替代率极低 → 最高卡脖子分"""
        assert _substitution_to_score(0.01) >= 90

    def test_substitution_to_score_low(self):
        """国产替代率高 → 低卡脖子分"""
        assert _substitution_to_score(0.95) <= 20

    def test_substitution_to_score_mid(self):
        score = _substitution_to_score(0.25)
        assert 55 <= score <= 85

    def test_score_to_level_critical(self):
        assert _score_to_bottleneck_level(90) == BottleneckLevel.CRITICAL

    def test_score_to_level_high(self):
        assert _score_to_bottleneck_level(70) == BottleneckLevel.HIGH

    def test_score_to_level_moderate(self):
        assert _score_to_bottleneck_level(50) == BottleneckLevel.MODERATE

    def test_score_to_level_none(self):
        assert _score_to_bottleneck_level(5) == BottleneckLevel.NONE


class TestAnalyzeBottleneck:
    def test_critical_upstream(self):
        """上游 + 极低国产替代率 → 超高卡脖子分"""
        result = analyze_bottleneck(
            industry_position="upstream",
            domestic_substitution_rate=0.05,
            import_dependency=0.95,
            tech_autonomy_score=10,
        )
        assert result.score >= 80
        assert result.level == BottleneckLevel.CRITICAL
        assert result.position == IndustryPosition.UPSTREAM

    def test_moderate_midstream(self):
        result = analyze_bottleneck(
            industry_position="midstream",
            domestic_substitution_rate=0.4,
            import_dependency=0.5,
            tech_autonomy_score=50,
        )
        assert 30 <= result.score <= 75
        assert result.position == IndustryPosition.MIDSTREAM

    def test_none_downstream(self):
        """下游 + 高国产替代率 → 低卡脖子分"""
        result = analyze_bottleneck(
            industry_position="downstream",
            domestic_substitution_rate=0.95,
            import_dependency=0.05,
            tech_autonomy_score=90,
        )
        assert result.score <= 35
        assert result.position == IndustryPosition.DOWNSTREAM

    def test_upstream_gets_higher_score(self):
        """上游比下游在同等条件下得分更高"""
        upstream = analyze_bottleneck("upstream", 0.3)
        downstream = analyze_bottleneck("downstream", 0.3)
        assert upstream.score > downstream.score

    def test_invalid_position_defaults(self):
        result = analyze_bottleneck(industry_position="invalid")
        assert result.position == IndustryPosition.MIDSTREAM

    def test_extra_fields_preserved(self):
        result = analyze_bottleneck(
            moat_description="技术壁垒极高",
            key_bottleneck_items=["光刻机", "光刻胶"],
            substitution_timeline="预计 5-8 年",
        )
        assert "光刻机" in result.key_bottleneck_items
        assert "技术壁垒" in result.moat_description

    def test_output_is_dataclass(self):
        result = analyze_bottleneck()
        assert isinstance(result, BottleneckResult)
        assert 0 <= result.score <= 100


# ============================================================================
# 机构行为信号测试
# ============================================================================


class TestInstitutionalBehavior:
    def test_strong_buy(self):
        result = analyze_institutional_behavior(90, 85, 80, 88)
        assert result.signal == SignalStrength.STRONG_BUY
        assert result.score >= 80

    def test_neutral(self):
        result = analyze_institutional_behavior(50, 50, 50, 50)
        assert result.signal == SignalStrength.NEUTRAL

    def test_strong_sell(self):
        result = analyze_institutional_behavior(5, 10, 5, 8)
        assert result.signal == SignalStrength.STRONG_SELL

    def test_northbound_has_highest_weight(self):
        """北向资金权重最高 — 同等变化下北向对总分影响最大"""
        # 北向从 50→80（+30）vs 融资从 50→80（+30）
        base = analyze_institutional_behavior(50, 50, 50, 50)
        nb_up = analyze_institutional_behavior(80, 50, 50, 50)
        mt_up = analyze_institutional_behavior(50, 80, 50, 50)
        # 北向提升带来的总分增量应大于融资提升带来的增量
        nb_delta = nb_up.score - base.score
        mt_delta = mt_up.score - base.score
        assert nb_delta > mt_delta

    def test_output_fields(self):
        result = analyze_institutional_behavior(70, 60, 55, 65)
        assert isinstance(result, InstitutionalResult)
        assert result.northbound_flow_score == 70
        assert result.margin_trading_score == 60
        assert 0 <= result.score <= 100


class TestSignalFromScore:
    def test_buy_signal(self):
        assert _signal_from_score(65) == SignalStrength.BUY

    def test_sell_signal(self):
        assert _signal_from_score(25) == SignalStrength.SELL

    def test_neutral_signal(self):
        assert _signal_from_score(50) == SignalStrength.NEUTRAL


# ============================================================================
# 长线价值评分测试
# ============================================================================


class TestValueScoring:
    def test_roe_to_score_high(self):
        assert _roe_to_score(30) >= 90

    def test_roe_to_score_negative(self):
        assert _roe_to_score(-5) < 10

    def test_gross_margin_to_score_high(self):
        assert _gross_margin_to_score(70) >= 85

    def test_gross_margin_to_score_low(self):
        assert _gross_margin_to_score(3) <= 20


class TestAnalyzeLongTermValue:
    def test_high_quality(self):
        result = analyze_long_term_value(roe=30, gross_margin=65, cashflow_quality_score=85, moat_score=90)
        assert result.score >= 80

    def test_low_quality(self):
        result = analyze_long_term_value(roe=2, gross_margin=5, cashflow_quality_score=10, moat_score=5)
        assert result.score <= 35

    def test_moat_info_preserved(self):
        result = analyze_long_term_value(moat_type="技术专利 + 网络效应")
        assert "技术专利" in result.moat_type

    def test_output_dataclass(self):
        result = analyze_long_term_value()
        assert isinstance(result, ValueResult)
        assert 0 <= result.roe_score <= 100
        assert 0 <= result.gross_margin_score <= 100


# ============================================================================
# 估值重置判断测试
# ============================================================================


class TestValuationReset:
    def test_paradigm_shift(self):
        result = analyze_valuation_reset(is_paradigm_shift=True, policy_driver_score=80)
        assert result.regime == ValuationRegime.PARADIGM_SHIFT
        assert result.is_paradigm_shift is True
        assert result.score >= 70

    def test_value_trap(self):
        result = analyze_valuation_reset(is_value_trap=True, industry_cycle_phase="繁荣后期")
        assert result.regime == ValuationRegime.VALUE_TRAP
        assert result.score <= 35

    def test_cyclical_trough(self):
        result = analyze_valuation_reset(industry_cycle_phase="衰退末期")
        assert result.regime == ValuationRegime.CYCLICAL_TROUGH
        assert result.score >= 70

    def test_cyclical_peak(self):
        result = analyze_valuation_reset(industry_cycle_phase="繁荣后期")
        assert result.regime == ValuationRegime.CYCLICAL_PEAK

    def test_policy_driver_boosts_score(self):
        """A 股特色：政策驱动力大幅提升得分"""
        low_policy = analyze_valuation_reset(policy_driver_score=10)
        high_policy = analyze_valuation_reset(policy_driver_score=90)
        assert high_policy.score > low_policy.score

    def test_regime_determination(self):
        assert _determine_regime(False, True, "复苏中期") == ValuationRegime.VALUE_TRAP
        assert _determine_regime(True, False, "复苏中期") == ValuationRegime.PARADIGM_SHIFT
        assert _determine_regime(False, False, "衰退末期") == ValuationRegime.CYCLICAL_TROUGH
        assert _determine_regime(False, False, "繁荣后期") == ValuationRegime.CYCLICAL_PEAK
        assert _determine_regime(False, False, "复苏中期") == ValuationRegime.FAIR_VALUE


# ============================================================================
# 综合分析测试
# ============================================================================


class TestCompositeGrade:
    def test_a_grade(self):
        assert _composite_grade(90) == "A"

    def test_b_grade(self):
        assert _composite_grade(75) == "B"

    def test_c_grade(self):
        assert _composite_grade(60) == "C"

    def test_d_grade(self):
        assert _composite_grade(45) == "D"

    def test_f_grade(self):
        assert _composite_grade(20) == "F"


class TestGenerateSerenityReport:
    def test_full_report_with_custom(self):
        bn = analyze_bottleneck("upstream", 0.1)
        inst = analyze_institutional_behavior(80, 70, 60, 75)
        val = analyze_long_term_value(25, 50, 80, 70)
        vr = analyze_valuation_reset(is_paradigm_shift=True, policy_driver_score=85)

        report = generate_serenity_report(
            target_name="中芯国际",
            target_type="stock",
            bottleneck=bn,
            institutional=inst,
            value=val,
            valuation_reset=vr,
            investment_thesis="国产晶圆代工龙头，先进制程突破驱动范式转移",
        )
        assert isinstance(report, SerenityReport)
        assert report.target_name == "中芯国际"
        assert report.target_type == "stock"
        assert 0 <= report.composite_score <= 100
        assert report.composite_grade in ("A", "B", "C", "D", "F")
        assert len(report.investment_thesis) > 0
        assert len(report.timestamp) > 0

    def test_default_dimensions(self):
        report = generate_serenity_report("测试标的")
        assert isinstance(report.bottleneck, BottleneckResult)
        assert isinstance(report.institutional, InstitutionalResult)
        assert isinstance(report.value, ValueResult)
        assert isinstance(report.valuation_reset, ValuationResetResult)

    def test_theme_type(self):
        report = generate_serenity_report("固态电池", target_type="theme")
        assert report.target_type == "theme"


class TestQuickScoreFunctions:
    def test_quick_score_stock(self):
        report = quick_score_stock(
            "宁德时代",
            industry_position="upstream",
            domestic_substitution_rate=0.15,
            northbound_flow_score=75,
            roe=20,
            gross_margin=35,
            is_paradigm_shift=True,
            policy_driver_score=80,
        )
        assert report.target_name == "宁德时代"
        assert report.target_type == "stock"
        assert report.bottleneck.position == IndustryPosition.UPSTREAM

    def test_quick_score_theme(self):
        report = quick_score_theme(
            "低空经济",
            industry_position="midstream",
            domestic_substitution_rate=0.4,
            policy_driver_score=75,
            is_paradigm_shift=True,
        )
        assert report.target_type == "theme"
        assert report.valuation_reset.is_paradigm_shift is True


# ============================================================================
# 序列化测试
# ============================================================================


class TestSerialization:
    def setup_method(self):
        self.report = quick_score_stock("测试股")

    def test_report_to_dict(self):
        d = report_to_dict(self.report)
        assert d["target_name"] == "测试股"
        assert "bottleneck" in d
        assert "institutional" in d
        assert "value" in d
        assert "valuation_reset" in d
        assert "composite_score" in d

    def test_report_to_json(self):
        j = report_to_json(self.report)
        parsed = json.loads(j)
        assert parsed["target_name"] == "测试股"
        assert parsed["composite_grade"] in ("A", "B", "C", "D", "F")

    def test_json_roundtrip(self):
        j = report_to_json(self.report)
        parsed = json.loads(j)
        assert isinstance(parsed["bottleneck"]["score"], int)
        assert isinstance(parsed["institutional"]["score"], int)
        assert isinstance(parsed["value"]["score"], int)
        assert isinstance(parsed["valuation_reset"]["score"], int)


# ============================================================================
# 决策启发式测试
# ============================================================================


class TestDecisionHeuristics:
    def test_all_count(self):
        all_h = DecisionHeuristic.all_heuristics()
        assert len(all_h) == 12

    def test_by_category(self):
        stock_h = DecisionHeuristic.by_category("选股")
        assert len(stock_h) == 3
        assert all(h["category"] == "选股" for h in stock_h)

        val_h = DecisionHeuristic.by_category("估值")
        assert len(val_h) == 3

    def test_each_has_required_fields(self):
        for h in DecisionHeuristic.all_heuristics():
            assert "id" in h
            assert "category" in h
            assert "rule" in h
            assert "description" in h
            assert "a_share_context" in h
            assert h["id"].startswith("H")

    def test_get_heuristic(self):
        h = DecisionHeuristic.get_heuristic("H1")
        assert h is not None
        assert h["rule"] == "卡脖子位置优先"

    def test_get_nonexistent(self):
        h = DecisionHeuristic.get_heuristic("H99")
        assert h is None

    def test_categories(self):
        """验证四个类别各有 3 条"""
        for cat in ("选股", "估值", "风险", "时机"):
            assert len(DecisionHeuristic.by_category(cat)) == 3


# ============================================================================
# 枚举测试
# ============================================================================


class TestEnums:
    def test_industry_position_values(self):
        assert IndustryPosition.UPSTREAM.value == "upstream"
        assert IndustryPosition.MIDSTREAM.value == "midstream"
        assert IndustryPosition.DOWNSTREAM.value == "downstream"

    def test_bottleneck_level_values(self):
        assert BottleneckLevel.CRITICAL.value == "critical"
        assert BottleneckLevel.NONE.value == "none"

    def test_valuation_regime_values(self):
        assert ValuationRegime.VALUE_TRAP.value == "value_trap"
        assert ValuationRegime.PARADIGM_SHIFT.value == "paradigm_shift"

    def test_signal_strength_values(self):
        assert SignalStrength.STRONG_BUY.value == "strong_buy"
        assert SignalStrength.NEUTRAL.value == "neutral"
