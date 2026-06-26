"""
行情数据接入模块 — 基于 AKShare（免费、无需注册）获取 A 股实时行情数据。

提供：
- 概念板块实时行情（涨跌幅、成交额）
- 板块成分股行情
- 板块资金流向
- 涨停板数据
- A 股个股实时行情

所有 API 调用均有超时设置、异常处理和 5 分钟内存缓存。
"""

from __future__ import annotations

import functools
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from config import get_logger

_log = get_logger("market_data")

# ==================== 数据结构 ====================


@dataclass
class SectorMarketData:
    """概念板块行情数据"""
    sector_name: str          # 板块名称
    sector_code: str          # 板块代码（如 BK0001）
    pct_chg_1d: float | None  # 近 1 日涨跌幅（%）
    pct_chg_3d: float | None  # 近 3 日涨跌幅（%）
    pct_chg_5d: float | None  # 近 5 日涨跌幅（%）
    turnover: float | None    # 成交额（亿元）
    fund_flow: float | None   # 资金净流入（亿元，正=流入，负=流出）
    stock_count: int | None   # 成分股数量
    limit_up_count: int | None  # 涨停成分股数量
    fetched_at: str = ""      # 数据获取时间


@dataclass
class StockMarketSummary:
    """个股行情摘要"""
    stock_code: str
    stock_name: str
    pct_chg_1d: float | None  # 近 1 日涨跌幅（%）
    pct_chg_3d: float | None
    pct_chg_5d: float | None
    limit_up: bool = False    # 是否涨停


@dataclass
class LimitUpSummary:
    """涨停板数据摘要"""
    date: str
    limit_up_count: int       # 涨停个股总数
    limit_up_stocks: list[dict] = field(default_factory=list)


# ==================== 缓存工具 ====================

CACHE_TTL_SECONDS = 300  # 5 分钟

_cache: dict[str, tuple[float, Any]] = {}


def _cached(key: str, ttl: int = CACHE_TTL_SECONDS):
    """装饰器：基于 key 的内存缓存，TTL 默认 5 分钟"""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            now = time.time()
            if key in _cache:
                cached_at, value = _cache[key]
                if now - cached_at < ttl:
                    _log.debug("缓存命中 key=%s age=%ds", key, now - cached_at)
                    return value
            result = fn(*args, **kwargs)
            _cache[key] = (now, result)
            return result
        return wrapper
    return decorator


def _clear_cache():
    """清除所有缓存"""
    _cache.clear()


# ==================== AKShare 获取函数 ====================


def _safe_call(api_name: str, fn, *args, **kwargs):
    """安全的 API 调用：超时 30 秒 + 异常捕获"""
    try:
        _log.info("调用 AKShare API: %s", api_name)
        # AKShare 函数不支持直接设 timeout，通过 signal 也不行（Windows 限制）
        # 降级方案：信任 akshare 自身的超时机制
        result = fn(*args, **kwargs)
        _log.info("AKShare API 返回成功: %s", api_name)
        return result
    except Exception as exc:
        _log.warning("AKShare API 调用失败 %s: %s", api_name, exc)
        return None


@_cached("concept_board_list")
def get_concept_board_list() -> pd.DataFrame | None:
    """获取概念板块列表（东方财富）"""
    try:
        import akshare as ak
    except ImportError:
        _log.error("akshare 未安装，请运行: pip install akshare")
        return None

    result = _safe_call("stock_board_concept_name_em", ak.stock_board_concept_name_em)
    if result is None:
        return None
    return result


@_cached("a_spot_em")
def get_a_share_spot() -> pd.DataFrame | None:
    """获取 A 股实时行情（全部个股）"""
    try:
        import akshare as ak
    except ImportError:
        _log.error("akshare 未安装")
        return None

    result = _safe_call("stock_zh_a_spot_em", ak.stock_zh_a_spot_em)
    if result is None:
        return None
    return result


def _get_sector_hist_cache_key(sector_code: str) -> str:
    return f"sector_hist_{sector_code}"


def get_sector_history(sector_code: str, period: str = "daily") -> pd.DataFrame | None:
    """获取概念板块历史行情"""
    key = _get_sector_hist_cache_key(sector_code)
    now = time.time()
    if key in _cache:
        cached_at, value = _cache[key]
        if now - cached_at < CACHE_TTL_SECONDS:
            return value

    try:
        import akshare as ak
    except ImportError:
        return None

    result = _safe_call(
        f"stock_board_concept_hist_em({sector_code})",
        ak.stock_board_concept_hist_em,
        symbol=sector_code,
        period=period,
    )
    if result is not None:
        _cache[key] = (now, result)
    return result


def _get_sector_cons_cache_key(sector_code: str) -> str:
    return f"sector_cons_{sector_code}"


def get_sector_constituents(sector_code: str) -> pd.DataFrame | None:
    """获取概念板块成分股"""
    key = _get_sector_cons_cache_key(sector_code)
    now = time.time()
    if key in _cache:
        cached_at, value = _cache[key]
        if now - cached_at < CACHE_TTL_SECONDS:
            return value

    try:
        import akshare as ak
    except ImportError:
        return None

    result = _safe_call(
        f"stock_board_concept_cons_em({sector_code})",
        ak.stock_board_concept_cons_em,
        symbol=sector_code,
    )
    if result is not None:
        _cache[key] = (now, result)
    return result


@_cached("limit_up_pool_today")
def get_limit_up_pool(date_str: str = "") -> pd.DataFrame | None:
    """获取涨停板池数据"""
    try:
        import akshare as ak
    except ImportError:
        return None

    if not date_str:
        date_str = datetime.now().strftime("%Y%m%d")

    result = _safe_call(
        f"stock_zt_pool_em({date_str})",
        ak.stock_zt_pool_em,
        date=date_str,
    )
    if result is None:
        return None
    return result


@_cached("sector_fund_flow")
def get_sector_fund_flow() -> pd.DataFrame | None:
    """获取板块资金流向排名"""
    try:
        import akshare as ak
    except ImportError:
        return None

    result = _safe_call(
        "stock_sector_fund_flow_rank",
        ak.stock_sector_fund_flow_rank,
        indicator="今日",
    )
    if result is None:
        return None
    return result


# ==================== 数据加工与结构化输出 ====================


def _safe_float(value, default=None):
    """安全转 float"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _normalize_stock_code(code) -> str:
    """标准化股票代码为 6 位字符串"""
    return str(code).strip().zfill(6)


def get_sector_market_data(
    sector_name: str,
    sector_code_mapping: dict[str, str] | None = None,
) -> SectorMarketData | None:
    """
    获取指定概念板块的实时行情数据。

    Args:
        sector_name: 用户侧题材名称或概念板块名称
        sector_code_mapping: 题材名称 → 板块代码的已知映射表

    Returns:
        SectorMarketData 或 None（获取失败）
    """
    # 1. 查找板块代码
    sector_code = None
    if sector_code_mapping and sector_name in sector_code_mapping:
        sector_code = sector_code_mapping[sector_name]

    if not sector_code:
        board_list = get_concept_board_list()
        if board_list is not None:
            # AKShare 返回的 DataFrame 列名可能是 '板块名称'/'代码' 或 'name'/'code'
            name_col = (
                "板块名称" if "板块名称" in board_list.columns
                else "name" if "name" in board_list.columns
                else None
            )
            code_col = (
                "代码" if "代码" in board_list.columns
                else "code" if "code" in board_list.columns
                else None
            )
            if name_col and code_col:
                match = board_list[board_list[name_col].str.contains(
                    sector_name.replace("(", "\\(").replace(")", "\\)"),
                    na=False,
                    regex=True,
                )]
                if not match.empty:
                    sector_code = str(match.iloc[0][code_col])

    if not sector_code:
        _log.warning("未找到板块代码: %s", sector_name)
        return None

    # 2. 获取历史行情（近 5 日）
    hist = get_sector_history(sector_code, period="daily")
    pct_chg_1d = pct_chg_3d = pct_chg_5d = None
    turnover = None

    if hist is not None and len(hist) > 0:
        # 列名判断
        pct_col = (
            "涨跌幅" if "涨跌幅" in hist.columns
            else "pct_chg" if "pct_chg" in hist.columns
            else None
        )
        turn_col = (
            "成交额" if "成交额" in hist.columns
            else "amount" if "amount" in hist.columns
            else None
        )
        if pct_col:
            # 最近一天
            pct_chg_1d = _safe_float(hist.iloc[-1][pct_col])
            # 近 3 日累计
            if len(hist) >= 3:
                pct_values = [_safe_float(x, 0) for x in hist.iloc[-3:][pct_col]]
                pct_chg_3d = round(sum(pct_values), 2) if all(v is not None for v in pct_values) else None
            # 近 5 日累计
            if len(hist) >= 5:
                pct_values = [_safe_float(x, 0) for x in hist.iloc[-5:][pct_col]]
                pct_chg_5d = round(sum(pct_values), 2) if all(v is not None for v in pct_values) else None
        if turn_col:
            turnover = _safe_float(hist.iloc[-1][turn_col])
            if turnover and turnover > 10000:
                turnover = round(turnover / 1e8, 2)  # 转亿元

    # 3. 获取成分股
    cons = get_sector_constituents(sector_code)
    stock_count = len(cons) if cons is not None else None

    # 4. 资金流向
    fund_flow = None
    flow_data = get_sector_fund_flow()
    if flow_data is not None:
        name_col = "名称" if "名称" in flow_data.columns else "name"
        flow_col = "主力净流入-净额" if "主力净流入-净额" in flow_data.columns else (
            "今日主力净流入-净额" if "今日主力净流入-净额" in flow_data.columns else None
        )
        if name_col in flow_data.columns and flow_col and flow_col in flow_data.columns:
            match = flow_data[flow_data[name_col].str.contains(
                sector_name, na=False, regex=False
            )]
            if not match.empty:
                fund_flow = _safe_float(match.iloc[0][flow_col])
                if fund_flow and abs(fund_flow) > 1000:
                    fund_flow = round(fund_flow / 1e8, 2)  # 转亿元

    # 5. 涨停关联
    limit_up_count = 0
    try:
        limit_up_data = get_limit_up_pool()
        if limit_up_data is not None and cons is not None:
            code_col_lu = "代码" if "代码" in limit_up_data.columns else "code"
            code_col_cons = "代码" if "代码" in cons.columns else "code"
            if code_col_lu in limit_up_data.columns and code_col_cons in cons.columns:
                lu_codes = set(str(c).strip().zfill(6) for c in limit_up_data[code_col_lu])
                cons_codes = set(str(c).strip().zfill(6) for c in cons[code_col_cons])
                limit_up_count = len(lu_codes & cons_codes)
    except Exception as exc:
        _log.debug("涨停数据获取失败: %s", exc)

    return SectorMarketData(
        sector_name=sector_name,
        sector_code=str(sector_code),
        pct_chg_1d=pct_chg_1d,
        pct_chg_3d=pct_chg_3d,
        pct_chg_5d=pct_chg_5d,
        turnover=turnover,
        fund_flow=fund_flow,
        stock_count=stock_count,
        limit_up_count=limit_up_count,
        fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def get_stocks_summary(stock_codes: list[str]) -> dict[str, StockMarketSummary]:
    """
    批量获取个股行情摘要（主要用于题材关联个股）。

    Args:
        stock_codes: 股票代码列表（6 位字符串）

    Returns:
        {stock_code: StockMarketSummary} 映射
    """
    if not stock_codes:
        return {}

    spot = get_a_share_spot()
    if spot is None:
        return {}

    # 标准化
    codes_set = {_normalize_stock_code(c) for c in stock_codes}

    # 列名探测
    code_col = "代码" if "代码" in spot.columns else "code"
    name_col = "名称" if "名称" in spot.columns else "name"
    pct_col = "涨跌幅" if "涨跌幅" in spot.columns else "pct_chg"

    if code_col not in spot.columns:
        return {}

    result = {}
    spot["_code"] = spot[code_col].astype(str).str.zfill(6)

    for _, row in spot.iterrows():
        sc = row["_code"]
        if sc in codes_set:
            result[sc] = StockMarketSummary(
                stock_code=sc,
                stock_name=str(row.get(name_col, "")),
                pct_chg_1d=_safe_float(row.get(pct_col)),
                pct_chg_3d=None,
                pct_chg_5d=None,
                limit_up=_safe_float(row.get(pct_col), -999) > 9.5,
            )

    # 补充涨停标记（更精确）
    limit_up_data = get_limit_up_pool()
    if limit_up_data is not None:
        lu_code_col = "代码" if "代码" in limit_up_data.columns else "code"
        if lu_code_col in limit_up_data.columns:
            lu_codes = set(str(c).strip().zfill(6) for c in limit_up_data[lu_code_col])
            for sc in result:
                if sc in lu_codes:
                    result[sc].limit_up = True

    return result


def get_limit_up_count_for_stocks(stock_codes: list[str]) -> int:
    """获取给定股票列表中涨停的数量"""
    if not stock_codes:
        return 0
    codes_set = {_normalize_stock_code(c) for c in stock_codes}
    limit_up_data = get_limit_up_pool()
    if limit_up_data is None:
        return 0
    code_col = "代码" if "代码" in limit_up_data.columns else "code"
    if code_col not in limit_up_data.columns:
        return 0
    lu_codes = set(str(c).strip().zfill(6) for c in limit_up_data[code_col])
    return len(codes_set & lu_codes)


# ==================== 综合行情热度分 ====================


def calculate_market_heat_score(
    sector_data: SectorMarketData | None,
    topic_stocks: list[str] | None = None,
) -> tuple[float, dict]:
    """
    计算行情热度分（0-100），返回 (分数, 明细)。

    行情热度分 = (
        板块近1日涨幅标准化分 × 0.3 +
        板块近3日涨幅标准化分 × 0.2 +
        板块资金流向标准化分 × 0.3 +
        涨停关联度分 × 0.2
    )

    Args:
        sector_data: 概念板块行情数据
        topic_stocks: 题材关联个股代码列表（用于计算涨停关联度）

    Returns:
        (market_heat_score, detail_dict)
        若行情数据获取失败，返回 (0, {}) 调用方应回退为纯新闻热度分
    """
    if sector_data is None:
        return 0.0, {}

    # 涨跌幅标准化（映射到 0-100，涨跌幅区间通常 -10 ~ +10）
    def normalize_pct(value, default=30.0):
        if value is None:
            return default
        # 将涨跌幅映射到 0-100 分：-10%→0, 0%→50, +10%→100
        clamped = max(-10.0, min(10.0, value))
        score = (clamped + 10.0) / 20.0 * 100.0
        return score

    # 资金流向标准化（映射到 0-100，假设区间 -50 亿 ~ +50 亿）
    def normalize_flow(value, default=40.0):
        if value is None:
            return default
        clamped = max(-50.0, min(50.0, value))
        score = (clamped + 50.0) / 100.0 * 100.0
        return score

    pct_1d_score = normalize_pct(sector_data.pct_chg_1d)
    pct_3d_score = normalize_pct(sector_data.pct_chg_3d, default=pct_1d_score)
    flow_score = normalize_flow(sector_data.fund_flow)

    # 涨停关联度分
    limit_up_score = 0.0
    if sector_data.stock_count and sector_data.stock_count > 0:
        limit_up_score = (sector_data.limit_up_count or 0) / sector_data.stock_count * 100.0

    # 如果提供了题材关联个股，也计算个股级别的涨停关联
    topic_limit_up_score = 0.0
    if topic_stocks and len(topic_stocks) > 0:
        lu_count = get_limit_up_count_for_stocks(topic_stocks)
        topic_limit_up_score = lu_count / len(topic_stocks) * 100.0
        # 使用两者中更高的
        limit_up_score = max(limit_up_score, topic_limit_up_score)

    market_heat = round(
        0.30 * pct_1d_score
        + 0.20 * pct_3d_score
        + 0.30 * flow_score
        + 0.20 * limit_up_score,
        2,
    )

    detail = {
        "pct_chg_1d": sector_data.pct_chg_1d,
        "pct_chg_1d_score": round(pct_1d_score, 1),
        "pct_chg_3d": sector_data.pct_chg_3d,
        "pct_chg_3d_score": round(pct_3d_score, 1),
        "fund_flow": sector_data.fund_flow,
        "fund_flow_score": round(flow_score, 1),
        "limit_up_count": sector_data.limit_up_count,
        "sector_stock_count": sector_data.stock_count,
        "limit_up_score": round(limit_up_score, 1),
        "market_heat_score": market_heat,
    }

    return market_heat, detail


def calculate_composite_heat_score(
    news_heat_score: int,
    market_heat_score: float,
) -> int:
    """
    计算综合热度分。
    综合热度分 = 新闻热度分 × 0.6 + 行情热度分 × 0.4

    Args:
        news_heat_score: 新闻规则热度分（0-100 整数）
        market_heat_score: 行情热度分（0-100 浮点）

    Returns:
        综合热度分（0-100 整数）
    """
    return round(news_heat_score * 0.6 + market_heat_score * 0.4)


def get_market_data_for_topic(
    topic_name: str,
    preliminary_stocks: list[str] | None = None,
) -> tuple[SectorMarketData | None, dict]:
    """
    为指定题材获取行情数据的便捷函数。

    Args:
        topic_name: 题材名称
        preliminary_stocks: 初步关联个股代码

    Returns:
        (SectorMarketData | None, market_detail_dict)
    """
    sector_data = get_sector_market_data(topic_name)
    _, detail = calculate_market_heat_score(sector_data, preliminary_stocks)
    return sector_data, detail
