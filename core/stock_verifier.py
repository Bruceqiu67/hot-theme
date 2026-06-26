"""
个股自动验证模块 — 二阶段自动验证机制

阶段一（搜索反查）：对 AI 生成的待核验字段，通过搜索引擎反查验证。
阶段二（财报验证）：通过 AKShare 获取财报数据，交叉验证 AI 生成的业务增速。

验证状态机：
    UNVERIFIED → VERIFYING → VERIFIED_AUTO / VERIFIED_INFERRED / STILL_UNVERIFIED
    VERIFIED_AUTO / VERIFIED_INFERRED / STILL_UNVERIFIED → MANUALLY_CONFIRMED (人工覆盖)
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from config import get_logger

_log = get_logger("stock_verifier")

# ==================== 验证状态枚举 ====================

class VerificationStatus:
    UNVERIFIED = "待核验"
    VERIFYING = "验证中"
    VERIFIED_AUTO = "verified_auto"        # 高置信：官方来源直接证实
    VERIFIED_INFERRED = "verified_inferred"  # 中等置信：财经媒体间接证实
    STILL_UNVERIFIED = "still_unverified"    # 仍待核验：搜索无有效结果
    MANUALLY_CONFIRMED = "manually_confirmed"  # 人工确认覆盖

    @classmethod
    def display_label(cls, status: str) -> str:
        return {
            cls.UNVERIFIED: "待核验",
            cls.VERIFYING: "验证中",
            cls.VERIFIED_AUTO: "自动验证通过",
            cls.VERIFIED_INFERRED: "推断验证",
            cls.STILL_UNVERIFIED: "仍待核验",
            cls.MANUALLY_CONFIRMED: "人工确认",
        }.get(status, status)

    @classmethod
    def display_icon(cls, status: str) -> str:
        return {
            cls.VERIFIED_AUTO: "verified_auto",
            cls.VERIFIED_INFERRED: "verified_inferred",
            cls.STILL_UNVERIFIED: "still_unverified",
            cls.MANUALLY_CONFIRMED: "manually_confirmed",
            cls.UNVERIFIED: "unverified",
            cls.VERIFYING: "verifying",
        }.get(status, "unverified")


# ==================== 数据结构 ====================

@dataclass
class FieldVerification:
    """单字段验证详情"""
    field_name: str               # 字段名：market_position / market_share / customers / biz_growth
    original_value: str            # AI 生成的原始值
    verified_value: str | None = None  # 验证后的值（如果有改进）
    status: str = VerificationStatus.UNVERIFIED
    evidence_urls: list[str] = field(default_factory=list)  # 证据来源 URL 列表
    evidence_summary: str = ""     # 证据摘要
    confidence: str = ""           # 置信度：high / medium / low


@dataclass
class StockVerificationResult:
    """单只个股的验证结果"""
    stock_code: str
    stock_name: str
    theme_name: str
    overall_status: str = VerificationStatus.UNVERIFIED
    field_details: dict[str, FieldVerification] = field(default_factory=dict)
    verified_at: str = ""
    summary: str = ""


# ==================== 搜索辅助函数 ====================

def _search_web(query: str, max_results: int = 8, max_retries: int = 2) -> str:
    """搜索网页并返回拼接的摘要文本，支持重试（与 ai_validators._search_web 同逻辑）"""
    # 优先复用已有的 _search_web
    try:
        from core.ai_validators import _search_web as ai_search
        return ai_search(query, max_results=max_results, max_retries=max_retries)
    except (ImportError, AttributeError):
        pass

    for attempt in range(max_retries + 1):
        try:
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    title = r.get("title", "")
                    body = r.get("body", "")
                    href = r.get("href", "")
                    results.append(f"- {title}: {body}" + (f" | {href}" if href else ""))
            return "\n".join(results) if results else ""
        except Exception as exc:
            if attempt < max_retries:
                _log.warning("搜索失败 query=%s 重试 %d/%d: %s", query[:50], attempt + 1, max_retries, exc)
                time.sleep(1)
            else:
                _log.warning("搜索失败 query=%s: %s", query[:50], exc)
                return ""
    return ""


def _search_with_urls(query: str, max_results: int = 6) -> list[dict]:
    """搜索并返回包含 URL 的结果列表"""
    results = []
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "body": r.get("body", ""),
                    "href": r.get("href", ""),
                })
    except Exception as exc:
        _log.warning("带URL搜索失败 query=%s: %s", query[:50], exc)
    return results


# ==================== 阶段一：搜索反查验证 ====================

# 官方来源域名特征
_OFFICIAL_SOURCE_PATTERNS = [
    r'cninfo\.com\.cn',       # 巨潮资讯（官方公告）
    r'sse\.com\.cn',          # 上交所
    r'szse\.cn',              # 深交所
    r'csrc\.gov\.cn',         # 证监会
    r'\.szse\.cn',            # 深交所
    r'\.sse\.com\.cn',        # 上交所
    r'eastmoney\.com',        # 东方财富（转载公告）
    r'10jqka\.com\.cn',       # 同花顺
    r'stock\.star\.com\.cn',  # 证券之星
]


def _is_official_source(url: str) -> bool:
    """判断 URL 是否来自官方/权威来源"""
    if not url:
        return False
    for pattern in _OFFICIAL_SOURCE_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return True
    return False


def _extract_urls_from_search(search_text: str) -> list[str]:
    """从搜索结果文本中提取 URL"""
    urls = re.findall(r'https?://[^\s|)]+', search_text)
    return urls[:5]


def _check_claim_in_results(claim_keywords: list[str], search_results: list[dict]) -> dict:
    """
    在搜索结果中检查声明是否被证实。

    Returns:
        {
            "confirmed": bool,
            "confidence": "high" / "medium" / "low",
            "evidence_urls": [...],
            "evidence_summary": "...",
            "verified_value": "..." 或 None
        }
    """
    if not search_results:
        return {"confirmed": False, "confidence": "low", "evidence_urls": [], "evidence_summary": "搜索无结果"}

    official_evidence = []
    media_evidence = []
    all_text = ""

    for result in search_results:
        text = (result.get("title", "") + " " + result.get("body", "")).lower()
        all_text += text + " "
        url = result.get("href", "")

        # 检查是否包含关键声明
        matched_keywords = [kw for kw in claim_keywords if kw.lower() in text]
        if not matched_keywords:
            continue

        if _is_official_source(url):
            official_evidence.append({
                "url": url,
                "title": result.get("title", ""),
                "matched": matched_keywords,
            })
        else:
            media_evidence.append({
                "url": url,
                "title": result.get("title", ""),
                "matched": matched_keywords,
            })

    # 判定置信度
    if official_evidence:
        evidence_urls = [e["url"] for e in official_evidence[:3]]
        evidence_summary = f"官方来源证实：{official_evidence[0]['title']}"
        return {
            "confirmed": True,
            "confidence": "high",
            "evidence_urls": evidence_urls,
            "evidence_summary": evidence_summary,
        }
    elif len(media_evidence) >= 1:
        evidence_urls = [e["url"] for e in media_evidence[:3]]
        evidence_summary = f"媒体报道：{media_evidence[0]['title']}"
        return {
            "confirmed": True,
            "confidence": "medium",
            "evidence_urls": evidence_urls,
            "evidence_summary": evidence_summary,
        }
    else:
        # 关键词没在结果里找到
        return {
            "confirmed": False,
            "confidence": "low",
            "evidence_urls": [],
            "evidence_summary": "搜索结果未包含相关声明",
        }


def _verify_market_position(stock_name: str, theme_keywords: str, current_value: str) -> FieldVerification:
    """验证市场地位/行业排名"""
    field = FieldVerification(
        field_name="market_position",
        original_value=current_value,
    )

    if current_value and current_value not in ("待核验", "未知", "不详", "暂无", ""):
        # 已有具体值，尝试验证
        query = f"{stock_name} {theme_keywords} 市场地位 行业排名 龙头"
        search_results = _search_with_urls(query, max_results=6)
        keywords = [stock_name, "龙头", "排名", "市场地位", "份额"]
        result = _check_claim_in_results(keywords, search_results)
    else:
        # 待核验状态，搜索确认
        query = f"{stock_name} {theme_keywords} 市场地位 行业排名 龙头 市占率"
        search_results = _search_with_urls(query, max_results=6)
        keywords = [stock_name, "龙头", "排名", "第一", "前列", "领先"]
        result = _check_claim_in_results(keywords, search_results)

    field.evidence_urls = result["evidence_urls"]
    field.evidence_summary = result["evidence_summary"]

    if result["confirmed"]:
        if result["confidence"] == "high":
            field.status = VerificationStatus.VERIFIED_AUTO
        else:
            field.status = VerificationStatus.VERIFIED_INFERRED
    else:
        field.status = VerificationStatus.STILL_UNVERIFIED

    return field


def _verify_market_share(stock_name: str, theme_keywords: str, current_value: str) -> FieldVerification:
    """验证市占率数据"""
    field = FieldVerification(
        field_name="market_share",
        original_value=current_value,
    )

    queries = [
        f"{stock_name} 年报 市占率 {theme_keywords}",
        f"{stock_name} 市场占有率 {theme_keywords} 公告",
        f"{stock_name} {theme_keywords} 份额 券商 研报",
    ]

    all_results = []
    for q in queries:
        results = _search_with_urls(q, max_results=4)
        all_results.extend(results)
        if len(all_results) >= 8:
            break

    keywords = [stock_name, "市占率", "占有率", "份额", "%"]
    result = _check_claim_in_results(keywords, all_results)

    field.evidence_urls = result["evidence_urls"]
    field.evidence_summary = result["evidence_summary"]

    if result["confirmed"]:
        if result["confidence"] == "high":
            field.status = VerificationStatus.VERIFIED_AUTO
        else:
            field.status = VerificationStatus.VERIFIED_INFERRED
    else:
        field.status = VerificationStatus.STILL_UNVERIFIED

    return field


def _verify_customers(stock_name: str, theme_keywords: str, current_value: str) -> FieldVerification:
    """验证客户关系/供应关系"""
    field = FieldVerification(
        field_name="customers",
        original_value=current_value,
    )

    queries = [
        f"{stock_name} 客户 供应商 {theme_keywords}",
        f"{stock_name} 供应 {theme_keywords} 产业链",
        f"{stock_name} 公告 客户 {theme_keywords}",
    ]

    all_results = []
    for q in queries:
        results = _search_with_urls(q, max_results=4)
        all_results.extend(results)
        if len(all_results) >= 8:
            break

    keywords = [stock_name, "客户", "供应", "合作", "订单"]
    result = _check_claim_in_results(keywords, all_results)

    field.evidence_urls = result["evidence_urls"]
    field.evidence_summary = result["evidence_summary"]

    if result["confirmed"]:
        if result["confidence"] == "high":
            field.status = VerificationStatus.VERIFIED_AUTO
        else:
            field.status = VerificationStatus.VERIFIED_INFERRED
    else:
        field.status = VerificationStatus.STILL_UNVERIFIED

    return field


# ==================== 阶段二：财报数据验证 ====================

def _verify_biz_growth_via_akshare(stock_code: str) -> FieldVerification | None:
    """
    通过 AKShare 获取最新财报数据，验证业务增速。

    返回 None 表示 AKShare 不可用或获取失败。
    """
    field = FieldVerification(
        field_name="biz_growth",
        original_value="",
    )

    try:
        import akshare as ak
    except ImportError:
        _log.warning("AKShare 不可用，跳过财报验证")
        return None

    try:
        # 获取利润表数据
        df = ak.stock_profit_sheet_by_report_em(symbol=stock_code)
        if df is None or df.empty:
            _log.debug("无法获取 %s 的财报数据", stock_code)
            return None

        # 取最近两个报告期的营收数据
        latest_col = df.columns[1]  # 最新报告期
        prev_col = df.columns[2] if len(df.columns) > 2 else None

        # 提取营业收入行
        revenue_rows = df[df["项目"].str.contains("营业总收入|营业收入", na=False)]
        if revenue_rows.empty:
            return None

        latest_revenue = revenue_rows[latest_col].values[0]
        if prev_col:
            prev_revenue = revenue_rows[prev_col].values[0]
            if prev_revenue and float(prev_revenue) > 0:
                growth = (float(latest_revenue) - float(prev_revenue)) / float(prev_revenue) * 100
                field.evidence_summary = f"财报营收增速: {growth:.1f}% (基于 {latest_col} vs {prev_col})"
                field.verified_value = f"营收增速 {growth:.1f}%"
            else:
                field.evidence_summary = f"最新报告期 {latest_col} 营收: {latest_revenue}"
        else:
            field.evidence_summary = f"最新报告期 {latest_col} 营收: {latest_revenue}"

        field.status = VerificationStatus.VERIFIED_AUTO
        field.evidence_urls = []
        return field

    except Exception as exc:
        _log.debug("AKShare 财报获取失败 stock=%s: %s", stock_code, exc)
        return None


# ==================== 主验证流程 ====================

def _extract_theme_keywords(theme_name: str) -> str:
    """从题材名称中提取搜索关键词"""
    # 简化：直接用题材名称作为关键词
    return theme_name


def verify_single_stock(
    stock: dict,
    theme_name: str = "",
    skip_search: bool = False,
    skip_financial: bool = False,
) -> StockVerificationResult:
    """
    对单只个股执行二阶段自动验证。

    Args:
        stock: 个股数据字典，需包含 stock_code, stock_name, market_position, market_share, customers
        theme_name: 题材名称，用于构造搜索 query
        skip_search: 跳过阶段一（搜索反查）
        skip_financial: 跳过阶段二（财报验证）

    Returns:
        StockVerificationResult
    """
    stock_name = str(stock.get("stock_name", "")).strip()
    stock_code = str(stock.get("stock_code", "")).strip()
    theme = theme_name or str(stock.get("theme_name", "")).strip()

    if not stock_name or not stock_code:
        return StockVerificationResult(
            stock_code=stock_code,
            stock_name=stock_name,
            theme_name=theme,
            overall_status=VerificationStatus.STILL_UNVERIFIED,
            summary="缺少个股基本信息",
        )

    theme_keywords = _extract_theme_keywords(theme)
    result = StockVerificationResult(
        stock_code=stock_code,
        stock_name=stock_name,
        theme_name=theme,
        verified_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    field_details: dict[str, FieldVerification] = {}

    # --- 阶段一：搜索反查验证 ---
    if not skip_search:
        mp = str(stock.get("market_position", "")).strip()
        ms = str(stock.get("market_share", "")).strip()
        cu = str(stock.get("customers", "")).strip()

        # 只验证"待核验"或空值字段
        if not mp or mp in ("待核验", "未知", "不详", "暂无"):
            field_details["market_position"] = _verify_market_position(stock_name, theme_keywords, mp)
            _log.info("验证 market_position: %s -> %s", stock_name, field_details["market_position"].status)

        if not ms or ms in ("待核验", "未知", "不详", "暂无", "*估算", "*行业推断"):
            field_details["market_share"] = _verify_market_share(stock_name, theme_keywords, ms)
            _log.info("验证 market_share: %s -> %s", stock_name, field_details["market_share"].status)

        if not cu or cu in ("待核验", "未知", "不详", "暂无"):
            field_details["customers"] = _verify_customers(stock_name, theme_keywords, cu)
            _log.info("验证 customers: %s -> %s", stock_name, field_details["customers"].status)

    # --- 阶段二：财报数据验证 ---
    if not skip_financial:
        biz_growth_value = str(stock.get("biz_growth", "")).strip()
        if biz_growth_value in ("", "待核验", "未知", "不详", "暂无"):
            fin_result = _verify_biz_growth_via_akshare(stock_code)
            if fin_result:
                field_details["biz_growth"] = fin_result
                _log.info("验证 biz_growth: %s -> %s", stock_name, fin_result.status)

    result.field_details = field_details

    # --- 计算整体验证状态 ---
    if not field_details:
        result.overall_status = VerificationStatus.UNVERIFIED
        result.summary = "未执行验证"
        return result

    statuses = [fd.status for fd in field_details.values()]
    has_auto = any(s == VerificationStatus.VERIFIED_AUTO for s in statuses)
    has_inferred = any(s == VerificationStatus.VERIFIED_INFERRED for s in statuses)
    all_still = all(s == VerificationStatus.STILL_UNVERIFIED for s in statuses)

    if all_still:
        result.overall_status = VerificationStatus.STILL_UNVERIFIED
        result.summary = f"验证 {len(field_details)} 个字段，均未找到有效证据"
    elif has_auto and not has_inferred:
        result.overall_status = VerificationStatus.VERIFIED_AUTO
        result.summary = f"验证 {len(field_details)} 个字段，全部通过官方来源确认"
    elif has_auto:
        result.overall_status = VerificationStatus.VERIFIED_AUTO
        auto_count = sum(1 for s in statuses if s == VerificationStatus.VERIFIED_AUTO)
        inferred_count = sum(1 for s in statuses if s == VerificationStatus.VERIFIED_INFERRED)
        result.summary = f"验证 {len(field_details)} 个字段：{auto_count} 个官方确认，{inferred_count} 个媒体推断"
    elif has_inferred:
        result.overall_status = VerificationStatus.VERIFIED_INFERRED
        inferred_count = sum(1 for s in statuses if s == VerificationStatus.VERIFIED_INFERRED)
        result.summary = f"验证 {len(field_details)} 个字段：{inferred_count} 个通过媒体推断"
    else:
        result.overall_status = VerificationStatus.STILL_UNVERIFIED

    return result


def verify_stocks_batch(
    stocks: list[dict],
    theme_name: str = "",
    task_state: dict | None = None,
) -> list[StockVerificationResult]:
    """
    批量验证个股列表。

    Args:
        stocks: 个股列表
        theme_name: 题材名称
        task_state: 可选的 task_manager 任务状态 dict，用于进度汇报

    Returns:
        list[StockVerificationResult]
    """
    results: list[StockVerificationResult] = []
    total = len(stocks)

    for i, stock in enumerate(stocks):
        if task_state:
            task_state["progress"] = (i + 1) / max(total, 1)
            task_state["progress_msg"] = f"验证个股 {i+1}/{total}: {stock.get('stock_name', '')}"

        try:
            result = verify_single_stock(stock, theme_name)
            results.append(result)
        except Exception as exc:
            _log.error("验证个股失败 %s: %s", stock.get("stock_name", ""), exc)
            results.append(StockVerificationResult(
                stock_code=str(stock.get("stock_code", "")),
                stock_name=str(stock.get("stock_name", "")),
                theme_name=theme_name,
                overall_status=VerificationStatus.STILL_UNVERIFIED,
                summary=f"验证异常: {exc}",
            ))

        # 搜索频率控制
        if i < total - 1:
            time.sleep(0.8)

    return results


# ==================== 数据库集成 ====================

def verification_result_to_db_json(results: list[StockVerificationResult]) -> dict[str, dict]:
    """
    将验证结果列表转换为 {stock_code: verification_json} 格式，
    用于存储到数据库。
    """
    output = {}
    for result in results:
        field_json = {}
        for field_name, fd in result.field_details.items():
            field_json[field_name] = {
                "original_value": fd.original_value,
                "verified_value": fd.verified_value,
                "status": fd.status,
                "evidence_urls": fd.evidence_urls,
                "evidence_summary": fd.evidence_summary,
                "confidence": fd.confidence,
            }

        output[result.stock_code] = {
            "stock_name": result.stock_name,
            "overall_status": result.overall_status,
            "verified_at": result.verified_at,
            "summary": result.summary,
            "field_details": field_json,
        }

    return output


def get_verification_stats(results: list[StockVerificationResult]) -> dict:
    """统计验证结果"""
    total = len(results)
    if total == 0:
        return {"total": 0, "verified_auto": 0, "verified_inferred": 0, "still_unverified": 0, "verified_rate": 0}

    auto_count = sum(1 for r in results if r.overall_status == VerificationStatus.VERIFIED_AUTO)
    inferred_count = sum(1 for r in results if r.overall_status == VerificationStatus.VERIFIED_INFERRED)
    still_count = sum(1 for r in results if r.overall_status == VerificationStatus.STILL_UNVERIFIED)

    # 总验证字段数
    total_fields = 0
    verified_fields = 0
    for r in results:
        total_fields += len(r.field_details)
        verified_fields += sum(
            1 for fd in r.field_details.values()
            if fd.status in (VerificationStatus.VERIFIED_AUTO, VerificationStatus.VERIFIED_INFERRED)
        )

    verified_rate = round(verified_fields / max(total_fields, 1) * 100, 1)

    return {
        "total_stocks": total,
        "verified_auto": auto_count,
        "verified_inferred": inferred_count,
        "still_unverified": still_count,
        "total_fields": total_fields,
        "verified_fields": verified_fields,
        "verified_rate": verified_rate,
    }
