"""
数据新鲜度评估模块

提供题材级新鲜度评估、全局汇总、重新分析建议。
所有计算基于 SQLite 中已有数据，无需外部 API。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

_log = logging.getLogger("data_freshness")


# ---------------------------------------------------------------------------
# 新鲜度评分核心逻辑
# ---------------------------------------------------------------------------

def _days_score(days: int | float) -> int:
    """
    将「距离今天的间隔天数」映射为 0-100 的新鲜度分。
    1 天内 = 100，3 天内 = 80，7 天内 = 60，14 天内 = 30，>30 天 = 0。
    中间值线性插值。
    """
    if days < 0:
        days = 0
    if days <= 1:
        return 100
    if days <= 3:
        return 80
    if days <= 7:
        return 60
    if days <= 14:
        return 30
    if days > 30:
        return 0
    # 14-30 天线性衰减
    return max(0, int(30 - (days - 14) * 30 / 16))


def _freshness_level(score: int) -> str:
    """根据 0-100 分数返回新鲜度等级标签"""
    if score >= 70:
        return "新鲜"
    if score >= 40:
        return "一般"
    return "过期"


def _freshness_color(score: int) -> str:
    if score >= 70:
        return "green"
    if score >= 40:
        return "amber"
    return "red"


def _now_utc() -> datetime:
    return datetime.now()


def _parse_dt(val: Any) -> datetime | None:
    """解析数据库时间值，返回 datetime 或 None"""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, pd.Timestamp):
        return val.to_pydatetime()
    s = str(val).strip()
    if not s:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# 题材级新鲜度
# ---------------------------------------------------------------------------

class ThemeFreshness:
    """单个题材的新鲜度评估结果"""

    __slots__ = (
        "theme_name", "last_update_days", "update_score",
        "last_news_days", "news_score",
        "overall_score", "level", "level_color",
        "needs_refresh", "refresh_reason",
        "last_update_str", "last_news_str",
    )

    def __init__(
        self,
        theme_name: str,
        last_update: datetime | None,
        last_news: datetime | None,
        sector_alert: str = "",
    ):
        now = _now_utc()
        self.theme_name = theme_name

        # --- 更新分 ---
        if last_update:
            self.last_update_days = (now - last_update).total_seconds() / 86400
            self.last_update_str = last_update.strftime("%Y-%m-%d %H:%M")
        else:
            self.last_update_days = 999
            self.last_update_str = "无记录"
        self.update_score = _days_score(self.last_update_days)

        # --- 新闻分 ---
        if last_news:
            self.last_news_days = (now - last_news).total_seconds() / 86400
            self.last_news_str = last_news.strftime("%Y-%m-%d %H:%M")
        else:
            self.last_news_days = 999
            self.last_news_str = "无数据"
        self.news_score = _days_score(self.last_news_days)

        # --- 综合分 ---
        self.overall_score = int(self.update_score * 0.5 + self.news_score * 0.5)
        self.level = _freshness_level(self.overall_score)
        self.level_color = _freshness_color(self.overall_score)

        # --- 重新分析建议 ---
        self.needs_refresh = False
        self.refresh_reason = ""
        if self.last_update_days > 7:
            self.needs_refresh = True
            self.refresh_reason = f"超过 {int(self.last_update_days)} 天未更新"
        if sector_alert:
            if not self.needs_refresh:
                self.needs_refresh = True
                self.refresh_reason = sector_alert
            else:
                self.refresh_reason += f"；{sector_alert}"


# ---------------------------------------------------------------------------
# 全局新鲜度汇总
# ---------------------------------------------------------------------------

class GlobalFreshness:
    """全局新鲜度汇总快照"""

    __slots__ = (
        "total_themes", "fresh_count", "stale_count", "normal_count",
        "health_pct", "latest_update_str", "oldest_update_str",
        "stale_list", "needs_refresh_list",
    )

    def __init__(self, theme_list: list[ThemeFreshness]):
        self.total_themes = len(theme_list)
        self.fresh_count = sum(1 for t in theme_list if t.level == "新鲜")
        self.stale_count = sum(1 for t in theme_list if t.level == "过期")
        self.normal_count = self.total_themes - self.fresh_count - self.stale_count

        if self.total_themes > 0:
            self.health_pct = int(
                (self.fresh_count * 100 + self.normal_count * 50) / self.total_themes
            )
        else:
            self.health_pct = 0

        # 最新/最旧
        update_dates = [t.last_update_str for t in theme_list if t.last_update_days < 999]
        self.latest_update_str = max(update_dates) if update_dates else "无数据"
        self.oldest_update_str = min(update_dates) if update_dates else "无数据"

        self.stale_list = [
            t for t in theme_list if t.level == "过期"
        ]
        self.needs_refresh_list = [
            t for t in theme_list if t.needs_refresh
        ]


# ---------------------------------------------------------------------------
# 对外 API
# ---------------------------------------------------------------------------

def compute_theme_freshness(
    theme_name: str,
    last_update: datetime | None,
    last_news: datetime | None,
    sector_alert: str = "",
) -> ThemeFreshness:
    """计算单个题材新鲜度"""
    return ThemeFreshness(theme_name, last_update, last_news, sector_alert)


def compute_global_freshness(
    themes: list[dict[str, Any]],
) -> GlobalFreshness:
    """
    计算全局新鲜度汇总。

    Args:
        themes: [{"theme_name": str, "last_update": datetime|None, "last_news": datetime|None}, ...]
    """
    freshness_list = [
        ThemeFreshness(
            t.get("theme_name", "?"),
            t.get("last_update"),
            t.get("last_news"),
            t.get("sector_alert", ""),
        )
        for t in themes
    ]
    return GlobalFreshness(freshness_list)


def get_freshness_label(score: int) -> str:
    """新鲜度文字标签"""
    return _freshness_level(score)


def get_freshness_color(score: int) -> str:
    """新鲜度颜色：green / amber / red"""
    return _freshness_color(score)
