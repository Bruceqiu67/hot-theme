"""
Serenity 四维分析框架 — 白毛股神方法论 A 股化实现。

核心模块，提供独立可测试的四维分析能力：
  1. 卡脖子指数 (Bottleneck Index) — 评估题材在产业链中的"不可替代性"
  2. 机构行为信号 (Institutional Behavior) — 北向资金/融资融券/龙虎榜
  3. 长线价值评分 (Long-term Value) — ROE/毛利率/现金流/护城河
  4. 估值重置判断 (Valuation Reset) — 范式转移 vs 周期性波动 vs 价值陷阱

设计原则：
  - 独立模块，零外部依赖（除 Python 标准库）
  - 所有评分返回 0-100 标准化分数
  - A 股语境全程映射
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ============================================================================
# 枚举定义
# ============================================================================


class IndustryPosition(str, Enum):
    """产业链位置"""
    UPSTREAM = "upstream"         # 上游：原材料、设备、EDA/IP
    MIDSTREAM = "midstream"       # 中游：制造、封装、模组
    DOWNSTREAM = "downstream"     # 下游：终端、应用、品牌


class BottleneckLevel(str, Enum):
    """卡脖子等级"""
    CRITICAL = "critical"             # 极高：国产替代率 <10%，短期无法替代
    HIGH = "high"                     # 高：国产替代率 10-30%，替代周期 3-5 年
    MODERATE = "moderate"             # 中：国产替代率 30-60%，有国产方案但性能差距
    LOW = "low"                       # 低：国产替代率 60%+，国产方案成熟
    NONE = "none"                     # 无：完全自主可控或非核心技术


class ValuationRegime(str, Enum):
    """估值状态"""
    PARADIGM_SHIFT = "paradigm_shift"     # 范式转移：新产业逻辑，旧估值框架失效
    CYCLICAL_PEAK = "cyclical_peak"       # 周期高位：景气高点，估值需回调
    CYCLICAL_TROUGH = "cyclical_trough"   # 周期底部：景气低点，估值修复空间大
    VALUE_TRAP = "value_trap"             # 价值陷阱：低估值但无成长性
    FAIR_VALUE = "fair_value"             # 合理估值：估值与基本面匹配


class SignalStrength(str, Enum):
    """信号强度"""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


# ============================================================================
# 数据类
# ============================================================================


@dataclass
class BottleneckResult:
    """卡脖子分析结果"""
    score: int                              # 0-100，越高越"卡脖子"（越有国产替代溢价）
    level: BottleneckLevel
    position: IndustryPosition
    domestic_substitution_rate: float       # 国产替代率 0.0-1.0
    import_dependency: float                # 进口依赖度 0.0-1.0
    tech_autonomy_score: int                # 技术自主可控评分 0-100
    moat_description: str = ""
    key_bottleneck_items: list[str] = field(default_factory=list)
    substitution_timeline: str = ""         # 替代时间线预估


@dataclass
class InstitutionalResult:
    """机构行为分析结果"""
    score: int                              # 0-100，越高机构越看好
    signal: SignalStrength
    northbound_flow_score: int              # 北向资金信号分
    margin_trading_score: int               # 融资融券信号分
    dragon_tiger_score: int                 # 龙虎榜信号分
    institution_research_score: int         # 机构调研信号分
    signals_summary: str = ""


@dataclass
class ValueResult:
    """长线价值分析结果"""
    score: int                              # 0-100，越高价值越优
    roe_score: int                          # ROE 评分
    gross_margin_score: int                 # 毛利率评分
    cashflow_score: int                     # 现金流评分
    moat_score: int                         # 护城河评分
    moat_type: str = ""                     # 护城河类型
    value_summary: str = ""


@dataclass
class ValuationResetResult:
    """估值重置分析结果"""
    score: int                              # 0-100，越高越接近"逢低布局"窗口
    regime: ValuationRegime
    is_paradigm_shift: bool
    is_value_trap: bool
    policy_driver_score: int                # 政策驱动力（A 股特色）
    industry_cycle_phase: str = ""          # 行业周期阶段
    reset_trigger: str = ""                 # 估值重置触发因素
    risk_warning: str = ""


@dataclass
class SerenityReport:
    """Serenity 完整分析报告"""
    target_name: str
    target_type: str                        # "theme" | "stock"
    bottleneck: BottleneckResult
    institutional: InstitutionalResult
    value: ValueResult
    valuation_reset: ValuationResetResult
    composite_score: int                    # 0-100 综合置信度
    composite_grade: str                    # A/B/C/D/F
    investment_thesis: str = ""             # 一句话投资主题
    timestamp: str = ""


# ============================================================================
# 评分辅助函数
# ============================================================================


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> int:
    """夹紧到 [low, high] 并返回整数"""
    return max(low, min(high, round(value)))


def _safe_float(value: Any, default: float = 0.0) -> float:
    """安全转换为 float"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _weighted_average(items: list[tuple[float, float]]) -> float:
    """加权平均，[(value, weight), ...]"""
    if not items:
        return 50.0
    total_weight = sum(w for _, w in items)
    if total_weight == 0:
        return 50.0
    return sum(v * w for v, w in items) / total_weight


# ============================================================================
# 维度一：卡脖子指数
# ============================================================================


# 产业链位置权重矩阵 — A 股市场规律：上游享有最高估值溢价
POSITION_WEIGHTS = {
    IndustryPosition.UPSTREAM: 1.0,      # 上游溢价系数
    IndustryPosition.MIDSTREAM: 0.75,
    IndustryPosition.DOWNSTREAM: 0.55,
}

# 国产替代率 → 评分映射
SUBSTITUTION_RATE_TABLE = [
    (0.05, 95),   # <5% 几乎完全依赖进口
    (0.10, 90),   # <10%
    (0.20, 80),
    (0.30, 70),
    (0.50, 55),
    (0.70, 35),
    (0.85, 20),
    (1.00, 5),    # 100% 国产化，无卡脖子溢价
]


def _substitution_to_score(rate: float) -> int:
    """国产替代率 → 卡脖子评分（越低替代率 → 越高卡脖子分）"""
    rate = max(0.0, min(1.0, rate))
    for threshold, score in SUBSTITUTION_RATE_TABLE:
        if rate <= threshold:
            return score
    return 5


def _score_to_bottleneck_level(score: int) -> BottleneckLevel:
    if score >= 85:
        return BottleneckLevel.CRITICAL
    elif score >= 65:
        return BottleneckLevel.HIGH
    elif score >= 40:
        return BottleneckLevel.MODERATE
    elif score >= 15:
        return BottleneckLevel.LOW
    else:
        return BottleneckLevel.NONE


def analyze_bottleneck(
    industry_position: str = "midstream",
    domestic_substitution_rate: float = 0.3,
    import_dependency: float = 0.5,
    tech_autonomy_score: int = 50,
    moat_description: str = "",
    key_bottleneck_items: list[str] | None = None,
    substitution_timeline: str = "",
) -> BottleneckResult:
    """
    卡脖子指数分析。

    Args:
        industry_position: 产业链位置 "upstream" / "midstream" / "downstream"
        domestic_substitution_rate: 国产替代率 0.0-1.0
        import_dependency: 进口依赖度 0.0-1.0
        tech_autonomy_score: 技术自主可控评分 0-100
        moat_description: 护城河/壁垒描述
        key_bottleneck_items: 关键卡脖子环节列表
        substitution_timeline: 替代时间线预估
    """
    try:
        position = IndustryPosition(industry_position)
    except ValueError:
        position = IndustryPosition.MIDSTREAM

    # 基础分 = 国产替代率得分
    base_score = _substitution_to_score(domestic_substitution_rate)

    # 进口依赖度修正
    import_modifier = import_dependency * 10  # 依赖度越高分越高

    # 技术自主可控修正
    tech_modifier = (100 - tech_autonomy_score) * 0.15

    # 产业链位置加权
    position_weight = POSITION_WEIGHTS.get(position, 0.75)

    raw_score = (base_score + import_modifier + tech_modifier) * position_weight
    score = _clamp(raw_score)
    level = _score_to_bottleneck_level(score)

    return BottleneckResult(
        score=score,
        level=level,
        position=position,
        domestic_substitution_rate=domestic_substitution_rate,
        import_dependency=import_dependency,
        tech_autonomy_score=tech_autonomy_score,
        moat_description=moat_description,
        key_bottleneck_items=key_bottleneck_items or [],
        substitution_timeline=substitution_timeline,
    )


# ============================================================================
# 维度二：机构行为信号
# ============================================================================


def _signal_from_score(score: int) -> SignalStrength:
    if score >= 80:
        return SignalStrength.STRONG_BUY
    elif score >= 60:
        return SignalStrength.BUY
    elif score >= 40:
        return SignalStrength.NEUTRAL
    elif score >= 20:
        return SignalStrength.SELL
    else:
        return SignalStrength.STRONG_SELL


def analyze_institutional_behavior(
    northbound_flow_score: int = 50,
    margin_trading_score: int = 50,
    dragon_tiger_score: int = 50,
    institution_research_score: int = 50,
    signals_summary: str = "",
) -> InstitutionalResult:
    """
    机构行为信号分析。

    Args:
        northbound_flow_score: 北向资金信号分 0-100（>60 净流入，<40 净流出）
        margin_trading_score: 融资融券信号分 0-100（>60 融资增加）
        dragon_tiger_score: 龙虎榜信号分 0-100（>60 游资/机构买入）
        institution_research_score: 机构调研信号分 0-100（>60 调研频繁）
        signals_summary: 信号摘要
    """
    # A 股权重：北向资金是 A 股最核心的机构信号
    score = _clamp(_weighted_average([
        (_safe_float(northbound_flow_score), 0.35),    # 北向权重最高
        (_safe_float(margin_trading_score), 0.25),     # 融资融券
        (_safe_float(dragon_tiger_score), 0.20),       # 龙虎榜
        (_safe_float(institution_research_score), 0.20),  # 机构调研
    ]))

    return InstitutionalResult(
        score=score,
        signal=_signal_from_score(score),
        northbound_flow_score=_clamp(northbound_flow_score),
        margin_trading_score=_clamp(margin_trading_score),
        dragon_tiger_score=_clamp(dragon_tiger_score),
        institution_research_score=_clamp(institution_research_score),
        signals_summary=signals_summary,
    )


# ============================================================================
# 维度三：长线价值评分
# ============================================================================


# ROE 评分映射（A 股标准）
def _roe_to_score(roe: float) -> int:
    """ROE → 0-100 评分"""
    if roe >= 25:
        return 95
    elif roe >= 20:
        return 85
    elif roe >= 15:
        return 70
    elif roe >= 10:
        return 55
    elif roe >= 5:
        return 35
    elif roe >= 0:
        return 15
    else:
        return 5


# 毛利率评分映射
def _gross_margin_to_score(margin: float) -> int:
    """毛利率(%) → 0-100 评分"""
    if margin >= 60:
        return 90
    elif margin >= 40:
        return 75
    elif margin >= 25:
        return 60
    elif margin >= 15:
        return 40
    elif margin >= 5:
        return 20
    else:
        return 5


def analyze_long_term_value(
    roe: float = 10.0,
    gross_margin: float = 25.0,
    cashflow_quality_score: int = 50,
    moat_score: int = 50,
    moat_type: str = "",
    value_summary: str = "",
) -> ValueResult:
    """
    长线价值分析。

    Args:
        roe: ROE (%)
        gross_margin: 毛利率 (%)
        cashflow_quality_score: 现金流质量分 0-100
        moat_score: 护城河评分 0-100
        moat_type: 护城河类型（品牌/专利/网络效应/规模优势/转换成本）
        value_summary: 价值分析摘要
    """
    roe_s = _roe_to_score(_safe_float(roe))
    margin_s = _gross_margin_to_score(_safe_float(gross_margin))

    score = _clamp(_weighted_average([
        (roe_s, 0.30),
        (margin_s, 0.25),
        (_safe_float(cashflow_quality_score), 0.25),
        (_safe_float(moat_score), 0.20),
    ]))

    return ValueResult(
        score=score,
        roe_score=roe_s,
        gross_margin_score=margin_s,
        cashflow_score=_clamp(cashflow_quality_score),
        moat_score=_clamp(moat_score),
        moat_type=moat_type,
        value_summary=value_summary,
    )


# ============================================================================
# 维度四：估值重置判断
# ============================================================================


# 行业周期阶段 → 基础分
CYCLE_PHASE_BASE = {
    "衰退末期": 85,    # 最佳布局窗口
    "复苏初期": 80,
    "复苏中期": 65,
    "复苏后期": 50,
    "繁荣初期": 40,
    "繁荣中期": 25,
    "繁荣后期": 15,
    "衰退初期": 30,
    "衰退中期": 45,
    "衰退末期": 85,
}


def _determine_regime(
    is_paradigm_shift: bool,
    is_value_trap: bool,
    cycle_phase: str,
) -> ValuationRegime:
    """判断估值状态"""
    if is_value_trap:
        return ValuationRegime.VALUE_TRAP
    if is_paradigm_shift:
        return ValuationRegime.PARADIGM_SHIFT
    if cycle_phase in ("衰退末期", "衰退中期", "复苏初期"):
        return ValuationRegime.CYCLICAL_TROUGH
    if cycle_phase in ("繁荣中期", "繁荣后期", "衰退初期"):
        return ValuationRegime.CYCLICAL_PEAK
    return ValuationRegime.FAIR_VALUE


def analyze_valuation_reset(
    is_paradigm_shift: bool = False,
    is_value_trap: bool = False,
    industry_cycle_phase: str = "复苏中期",
    policy_driver_score: int = 50,
    reset_trigger: str = "",
    risk_warning: str = "",
) -> ValuationResetResult:
    """
    估值重置判断。

    Args:
        is_paradigm_shift: 是否为范式转移（新产业逻辑）
        is_value_trap: 是否为价值陷阱（低估值无成长）
        industry_cycle_phase: 行业周期阶段
        policy_driver_score: 政策驱动力 0-100（A 股特色）
        reset_trigger: 估值重置触发因素
        risk_warning: 风险提示
    """
    regime = _determine_regime(is_paradigm_shift, is_value_trap, industry_cycle_phase)

    cycle_base = CYCLE_PHASE_BASE.get(industry_cycle_phase, 50)

    if is_paradigm_shift:
        # 范式转移：传统估值失效，给予高潜力分但加风险警示
        score = _clamp(cycle_base + _safe_float(policy_driver_score) * 0.25 + 15)
    elif is_value_trap:
        # 价值陷阱：低分
        score = _clamp(max(cycle_base - 25, 10))
    else:
        score = _clamp(_weighted_average([
            (cycle_base, 0.50),
            (_safe_float(policy_driver_score), 0.35),
            (70 if industry_cycle_phase in ("衰退末期", "复苏初期") else 40, 0.15),
        ]))

    return ValuationResetResult(
        score=score,
        regime=regime,
        is_paradigm_shift=is_paradigm_shift,
        is_value_trap=is_value_trap,
        policy_driver_score=_clamp(policy_driver_score),
        industry_cycle_phase=industry_cycle_phase,
        reset_trigger=reset_trigger,
        risk_warning=risk_warning,
    )


# ============================================================================
# 综合分析
# ============================================================================


# 综合置信度加权
COMPOSITE_WEIGHTS = {
    "bottleneck": 0.30,
    "institutional": 0.30,
    "value": 0.25,
    "valuation_reset": 0.15,
}


def _composite_grade(score: int) -> str:
    if score >= 85:
        return "A"
    elif score >= 70:
        return "B"
    elif score >= 55:
        return "C"
    elif score >= 40:
        return "D"
    else:
        return "F"


def generate_serenity_report(
    target_name: str,
    target_type: str = "stock",
    bottleneck: BottleneckResult | None = None,
    institutional: InstitutionalResult | None = None,
    value: ValueResult | None = None,
    valuation_reset: ValuationResetResult | None = None,
    investment_thesis: str = "",
) -> SerenityReport:
    """
    生成完整的 Serenity 四维分析报告。

    可单独传入各维度结果；未传入的维度使用默认值。
    """
    bn = bottleneck or analyze_bottleneck()
    inst = institutional or analyze_institutional_behavior()
    val = value or analyze_long_term_value()
    vr = valuation_reset or analyze_valuation_reset()

    composite = _clamp(_weighted_average([
        (bn.score, COMPOSITE_WEIGHTS["bottleneck"]),
        (inst.score, COMPOSITE_WEIGHTS["institutional"]),
        (val.score, COMPOSITE_WEIGHTS["value"]),
        (vr.score, COMPOSITE_WEIGHTS["valuation_reset"]),
    ]))

    from datetime import datetime
    return SerenityReport(
        target_name=target_name,
        target_type=target_type,
        bottleneck=bn,
        institutional=inst,
        value=val,
        valuation_reset=vr,
        composite_score=composite,
        composite_grade=_composite_grade(composite),
        investment_thesis=investment_thesis,
        timestamp=datetime.now().isoformat(),
    )


# ============================================================================
# 快速评分函数（便捷接口）
# ============================================================================


def quick_score_stock(
    stock_name: str,
    industry_position: str = "midstream",
    domestic_substitution_rate: float = 0.3,
    northbound_flow_score: int = 50,
    margin_trading_score: int = 50,
    roe: float = 10.0,
    gross_margin: float = 25.0,
    is_paradigm_shift: bool = False,
    is_value_trap: bool = False,
    policy_driver_score: int = 50,
) -> SerenityReport:
    """快速个股评分 — 一次调用完成四维分析"""
    return generate_serenity_report(
        target_name=stock_name,
        target_type="stock",
        bottleneck=analyze_bottleneck(
            industry_position=industry_position,
            domestic_substitution_rate=domestic_substitution_rate,
        ),
        institutional=analyze_institutional_behavior(
            northbound_flow_score=northbound_flow_score,
            margin_trading_score=margin_trading_score,
        ),
        value=analyze_long_term_value(roe=roe, gross_margin=gross_margin),
        valuation_reset=analyze_valuation_reset(
            is_paradigm_shift=is_paradigm_shift,
            is_value_trap=is_value_trap,
            policy_driver_score=policy_driver_score,
        ),
    )


def quick_score_theme(
    theme_name: str,
    industry_position: str = "midstream",
    domestic_substitution_rate: float = 0.3,
    policy_driver_score: int = 50,
    is_paradigm_shift: bool = False,
) -> SerenityReport:
    """快速题材评分"""
    return generate_serenity_report(
        target_name=theme_name,
        target_type="theme",
        bottleneck=analyze_bottleneck(
            industry_position=industry_position,
            domestic_substitution_rate=domestic_substitution_rate,
        ),
        institutional=analyze_institutional_behavior(),
        value=analyze_long_term_value(),
        valuation_reset=analyze_valuation_reset(
            is_paradigm_shift=is_paradigm_shift,
            policy_driver_score=policy_driver_score,
        ),
    )


# ============================================================================
# 序列化与导出
# ============================================================================


def report_to_dict(report: SerenityReport) -> dict:
    """将 SerenityReport 转为可 JSON 序列化的字典"""
    return {
        "target_name": report.target_name,
        "target_type": report.target_type,
        "bottleneck": {
            "score": report.bottleneck.score,
            "level": report.bottleneck.level.value,
            "position": report.bottleneck.position.value,
            "domestic_substitution_rate": report.bottleneck.domestic_substitution_rate,
            "import_dependency": report.bottleneck.import_dependency,
            "tech_autonomy_score": report.bottleneck.tech_autonomy_score,
            "moat_description": report.bottleneck.moat_description,
            "key_bottleneck_items": report.bottleneck.key_bottleneck_items,
            "substitution_timeline": report.bottleneck.substitution_timeline,
        },
        "institutional": {
            "score": report.institutional.score,
            "signal": report.institutional.signal.value,
            "northbound_flow_score": report.institutional.northbound_flow_score,
            "margin_trading_score": report.institutional.margin_trading_score,
            "dragon_tiger_score": report.institutional.dragon_tiger_score,
            "institution_research_score": report.institutional.institution_research_score,
            "signals_summary": report.institutional.signals_summary,
        },
        "value": {
            "score": report.value.score,
            "roe_score": report.value.roe_score,
            "gross_margin_score": report.value.gross_margin_score,
            "cashflow_score": report.value.cashflow_score,
            "moat_score": report.value.moat_score,
            "moat_type": report.value.moat_type,
            "value_summary": report.value.value_summary,
        },
        "valuation_reset": {
            "score": report.valuation_reset.score,
            "regime": report.valuation_reset.regime.value,
            "is_paradigm_shift": report.valuation_reset.is_paradigm_shift,
            "is_value_trap": report.valuation_reset.is_value_trap,
            "policy_driver_score": report.valuation_reset.policy_driver_score,
            "industry_cycle_phase": report.valuation_reset.industry_cycle_phase,
            "reset_trigger": report.valuation_reset.reset_trigger,
            "risk_warning": report.valuation_reset.risk_warning,
        },
        "composite_score": report.composite_score,
        "composite_grade": report.composite_grade,
        "investment_thesis": report.investment_thesis,
        "timestamp": report.timestamp,
    }


def report_to_json(report: SerenityReport) -> str:
    """将 SerenityReport 转为 JSON 字符串"""
    return json.dumps(report_to_dict(report), ensure_ascii=False, indent=2)


# ============================================================================
# 十二决策启发式（12 Decision Heuristics）
# ============================================================================


class DecisionHeuristic:
    """12 条决策启发式 — 选股/估值/风险/时机各 3 条"""

    STOCK_SELECTION = [
        {
            "id": "H1",
            "category": "选股",
            "rule": "卡脖子位置优先",
            "description": "上游设备/材料/EDA > 中游制造 > 下游应用。只有不可替代的环节才有定价权。",
            "a_share_context": "优先筛选国产替代率 <30% 的环节，如半导体设备、高端光刻胶、EDA 工具。",
        },
        {
            "id": "H2",
            "category": "选股",
            "rule": "机构用脚投票",
            "description": "北向资金持续净流入 + 融资余额上升的组合，比单一信号更可靠。",
            "a_share_context": "北向资金连续 5 日净流入 + 融资余额周环比增长 >5% 是强确认信号。",
        },
        {
            "id": "H3",
            "category": "选股",
            "rule": "毛利率是最诚实的护城河",
            "description": "持续高于 35% 的毛利率意味着真实壁垒，低毛利率的「龙头」往往是周期幻象。",
            "a_share_context": "A 股制造业毛利率 >35% 且稳定，通常对应技术壁垒或品牌溢价。",
        },
    ]

    VALUATION = [
        {
            "id": "H4",
            "category": "估值",
            "rule": "范式转移不用 PE",
            "description": "产业逻辑重构时，传统估值框架失效。应关注 TAM 扩张速度和渗透率曲线。",
            "a_share_context": "双碳/数字经济/新质生产力相关题材，优先看渗透率而非 PE。",
        },
        {
            "id": "H5",
            "category": "估值",
            "rule": "周期股买在 PE 最高时",
            "description": "周期底部利润最低、PE 最高，恰是买入时机；周期顶部利润最高、PE 最低，恰是卖出时机。",
            "a_share_context": "化工/钢铁/养殖等周期行业，PE 倒数是更可靠的反向指标。",
        },
        {
            "id": "H6",
            "category": "估值",
            "rule": "高股息 + 低增长 = 价值陷阱",
            "description": "高股息但如果盈利持续下滑，股息迟早被砍。真正的价值需要成长性支撑。",
            "a_share_context": "银行/公用事业/传统能源中需区分真价值和价值陷阱。",
        },
    ]

    RISK = [
        {
            "id": "H7",
            "category": "风险",
            "rule": "永远问'如果错了呢'",
            "description": "在买入任何标的之前，先写出三条可能导致亏损的情景。如果写不出来，说明研究不够。",
            "a_share_context": "A 股特有的风险：政策转向、监管问询、ST 风险、退市新规。",
        },
        {
            "id": "H8",
            "category": "风险",
            "rule": "警惕叙事驱动型上涨",
            "description": "如果上涨的理由全是'故事'而缺乏可验证的数据，退出窗口可能极短。",
            "a_share_context": "A 股概念炒作周期通常 2-4 周，超过此窗口需看到业绩验证。",
        },
        {
            "id": "H9",
            "category": "风险",
            "rule": "集中但不 ALL IN",
            "description": "深度研究 5-10 只标的比泛泛覆盖 50 只更有价值，但单票不超过 20%。",
            "a_share_context": "A 股波动率较高，更应严格执行仓位纪律。",
        },
    ]

    TIMING = [
        {
            "id": "H10",
            "category": "时机",
            "rule": "等待'无需思考'的时刻",
            "description": "最好的投资机会不需要复杂的估值模型 — 当价值明显被低估时，直觉会告诉你。",
            "a_share_context": "A 股极度恐慌时（跌停潮、千股跌停）往往是中期底部。",
        },
        {
            "id": "H11",
            "category": "时机",
            "rule": "催化剂在前，价值在后",
            "description": "价值是必要条件，催化剂（政策/事件/财报）是充分条件。有催化剂的低估才是机会。",
            "a_share_context": "政策文件发布、行业大会、龙头财报是 A 股最有效的催化剂。",
        },
        {
            "id": "H12",
            "category": "时机",
            "rule": "北向资金是先行指标",
            "description": "北向资金通常领先市场 1-2 周，持续流入的板块值得重点关注。",
            "a_share_context": "深股通/沪股通每日额度使用率和十大成交股是核心观测指标。",
        },
    ]

    @classmethod
    def all_heuristics(cls) -> list[dict]:
        return cls.STOCK_SELECTION + cls.VALUATION + cls.RISK + cls.TIMING

    @classmethod
    def by_category(cls, category: str) -> list[dict]:
        mapping = {
            "选股": cls.STOCK_SELECTION,
            "估值": cls.VALUATION,
            "风险": cls.RISK,
            "时机": cls.TIMING,
        }
        return mapping.get(category, [])

    @classmethod
    def get_heuristic(cls, hid: str) -> dict | None:
        for h in cls.all_heuristics():
            if h["id"] == hid:
                return h
        return None
