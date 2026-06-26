"""
新闻/资讯搜索抓取模块

第一版仅通过公开搜索结果获取标题、摘要、来源和 URL，不抓取行情数据，
也不把页面做成新闻列表。该模块作为新闻源适配层，便于后续替换成 RSS、
财经网站 API 或自建爬虫。
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from urllib.parse import urlparse

from config import get_logger
from core.constants  import BROAD_TOPIC_BLACKLIST, FINANCE_STOP_WORDS

# 抑制 ddgs/duckduckgo_search 引擎超时的 INFO 日志噪音
logging.getLogger("ddgs").setLevel(logging.WARNING)
logging.getLogger("duckduckgo_search").setLevel(logging.WARNING)

_log = get_logger("fetch_news")


TIME_RANGE_OPTIONS = [
    "最近 6 小时",
    "最近 12 小时",
    "最近 24 小时",
    "最近 3 天",
    "最近 7 天",
    "自定义",
]

SEARCH_CATEGORIES = [
    "全市场热点",
    "科技成长",
    "半导体",
    "AI硬件",
    "机器人",
    "电力设备",
    "新能源",
    "消费电子",
    "低空经济",
    "商业航天",
    "自定义关键词",
]


QUERY_TEMPLATES: dict[str, list[str]] = {
    "全市场热点": [
        "A股 热点题材 产业链 近一周",
        "A股 概念题材 催化 产业链",
        "A股 资讯快讯 题材 发酵",
        "A股 券商研报 产业趋势 题材",
        "A股 政策催化 产业链 题材",
    ],
    "科技成长": [
        "科技成长 A股 产业链 题材",
        "新质生产力 A股 产业链",
        "硬科技 A股 投资机会 产业链",
        "科技创新 A股 概念题材",
    ],
    "半导体": [
        "半导体 产业链 A股",
        "先进封装 A股",
        "HBM A股",
        "光刻胶 A股",
        "半导体设备 A股",
        "晶圆代工 A股",
        "封测 A股",
    ],
    "AI硬件": [
        "AI服务器 产业链 A股",
        "PCB CCL 铜箔 A股",
        "液冷 服务器 A股",
        "光模块 A股",
        "算力 电力 A股",
    ],
    "机器人": [
        "人形机器人 A股",
        "减速器 丝杠 传感器 A股",
        "特斯拉机器人 产业链 A股",
        "机器人执行器 A股",
    ],
    "电力设备": [
        "电力设备 A股 产业链",
        "特高压 A股",
        "智能电网 A股",
        "电力设备 出海 A股",
        "变压器 开关设备 A股",
    ],
    "新能源": [
        "固态电池 A股 产业链",
        "钠离子电池 A股",
        "光伏新技术 A股",
        "储能温控 A股",
        "锂电材料 A股",
    ],
    "消费电子": [
        "消费电子 A股 产业链",
        "AI手机 A股",
        "折叠屏 A股",
        "MR AR 眼镜 A股",
        "端侧AI A股",
    ],
    "低空经济": [
        "低空经济 A股 产业链",
        "eVTOL A股",
        "无人机 A股 产业链",
        "空管系统 A股",
        "航空材料 A股",
    ],
    "商业航天": [
        "商业航天 A股 产业链",
        "卫星互联网 A股",
        "火箭制造 A股",
        "卫星通信 A股",
        "航天电子 A股",
    ],
    "小切口题材发现": [
        "A股 今日新题材",
        "A股 题材发酵",
        "A股 产业链映射",
        "A股 供应链映射",
        "A股 概念股梳理",
        "A股 受益股梳理",
        "A股 涨停原因 题材",
        "A股 异动拉升 原因",
        "A股 多股涨停 概念",
        "A股 新主线",
        "A股 补涨 概念",
        "华为 产业链 A股 受益股",
        "长鑫存储 A股 产业链",
        "长鑫存储 上市 受益股",
        "英伟达 Rubin A股 产业链",
        "HVLP铜箔 A股",
        "载体铜箔 A股",
        "高频高速CCL A股",
        "AI服务器 PCB 材料 A股",
        "混合键合设备 A股",
        "存储封测 A股",
        "DRAM设备 A股",
        "NAND产业链 A股",
        "先进封装材料 A股",
    ],
}

# 宽泛词黑名单 — 使用共享常量（从 constants.py 导入）


SOURCE_WEIGHTS = {
    "cls.cn": 0.95,
    "eastmoney.com": 0.9,
    "10jqka.com.cn": 0.88,
    "stcn.com": 0.86,
    "cnstock.com": 0.84,
    "cs.com.cn": 0.84,
    "sina.com.cn": 0.78,
    "qq.com": 0.72,
    "163.com": 0.68,
}


def resolve_time_range(
    time_range: str,
    custom_start: datetime | None = None,
    custom_end: datetime | None = None,
) -> tuple[datetime, datetime]:
    """将页面选择的时间范围转成起止时间"""
    now = datetime.now()
    mapping = {
        "最近 6 小时": timedelta(hours=6),
        "最近 12 小时": timedelta(hours=12),
        "最近 24 小时": timedelta(hours=24),
        "最近 3 天": timedelta(days=3),
        "最近 7 天": timedelta(days=7),
    }
    if time_range == "自定义":
        start = custom_start or (now - timedelta(days=1))
        end = custom_end or now
    else:
        start = now - mapping.get(time_range, timedelta(days=1))
        end = now
    if start > end:
        start, end = end, start
    return start, end


def build_search_queries(
    selected_categories: list[str],
    custom_keywords: str = "",
) -> list[dict]:
    """根据搜索范围生成 query 列表，保留 category 便于追踪来源"""
    queries = []
    for category in selected_categories:
        if category == "自定义关键词":
            continue
        for query in QUERY_TEMPLATES.get(category, []):
            queries.append({"category": category, "query": query})

    keywords = [
        item.strip()
        for item in re.split(r"[,，;\n]+", custom_keywords or "")
        if item.strip()
    ]
    for keyword in keywords:
        queries.append({"category": "自定义关键词", "query": f"{keyword} A股 产业链 题材"})
        queries.append({"category": "自定义关键词", "query": f"{keyword} 概念股 催化 研报"})

    seen = set()
    deduped = []
    for item in queries:
        key = item["query"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _source_from_url(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _news_id(url: str, title: str) -> str:
    raw = (url or title).strip().lower()
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _parse_published_at(_result: dict) -> str:
    """DDGS 文本搜索通常不给稳定发布时间，第一版保留为空"""
    return ""


def _search_ddgs(query: str, max_results: int) -> list[dict]:
    """
    多引擎文本搜索，国内环境优先使用 Bing，DDGS 作为降级回退。

    P2-7: 国内网络环境下 Google/Yahoo/Brave 等 DDGS 后端均被墙，
    改用 Bing (cn.bing.com) 作为主力搜索引擎，DDGS 仅作 fallback。
    单次请求超时 12s，快速失败不阻塞。
    """
    from core.search_providers import search

    results = search(query, max_results=max_results)
    if results:
        return results

    # 全部 provider 失败时才报 warning
    _log.warning("搜索失败 (所有引擎均超时): query=%s", query[:60])
    return []


def fetch_news(
    time_range: str,
    selected_categories: list[str],
    custom_keywords: str = "",
    custom_start: datetime | None = None,
    custom_end: datetime | None = None,
    max_results_per_query: int = 5,
) -> list[dict]:
    """
    搜索财经新闻/资讯/研报摘要。

    输出字段：
    title, summary, content, source, url, published_at, fetched_at,
    search_query, category
    """
    start, end = resolve_time_range(time_range, custom_start, custom_end)
    queries = build_search_queries(selected_categories, custom_keywords)
    fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    raw_news = []

    for item in queries:
        query = f"{item['query']} {start:%Y-%m-%d}..{end:%Y-%m-%d}"
        for result in _search_ddgs(query, max_results=max_results_per_query):
            title = (result.get("title") or "").strip()
            summary = (result.get("body") or "").strip()
            url = (result.get("href") or "").strip()
            if not title and not summary:
                continue
            raw_news.append({
                "news_id": _news_id(url, title),
                "title": title,
                "summary": summary,
                "content": "",
                "source": _source_from_url(url),
                "url": url,
                "published_at": _parse_published_at(result),
                "fetched_at": fetched_at,
                "search_query": item["query"],
                "category": item["category"],
            })

    return dedupe_news(raw_news)


def dedupe_news(news_items: list[dict], title_threshold: float = 0.88) -> list[dict]:
    """按 URL 和标题相似度去重"""
    deduped = []
    seen_urls = set()
    seen_titles_exact = set()
    seen_titles_raw = []
    for item in news_items:
        url = (item.get("url") or "").strip().lower()
        title = re.sub(r"\s+", "", item.get("title") or "")
        if url and url in seen_urls:
            continue
        if title and title in seen_titles_exact:
            continue
        duplicate_title = False
        for old_title in seen_titles_raw:
            if title and SequenceMatcher(None, title, old_title).ratio() >= title_threshold:
                duplicate_title = True
                break
        if duplicate_title:
            continue
        if url:
            seen_urls.add(url)
        if title:
            seen_titles_exact.add(title)
            seen_titles_raw.append(title)
        deduped.append(item)
    return deduped


def source_quality(url_or_source: str) -> float:
    source = _source_from_url(url_or_source) or (url_or_source or "").lower()
    for host, weight in SOURCE_WEIGHTS.items():
        if host in source:
            return weight
    return 0.55


def calculate_heat_score(topic: dict, evidence_items: list[dict]) -> tuple[int, str]:
    """
    规则热度评分。

    heat_score =
    0.30 * news_count_score +
    0.25 * source_quality_score +
    0.20 * recency_score +
    0.15 * keyword_density_score +
    0.10 * chain_clarity_score
    """
    news_count = len(evidence_items)
    news_count_score = min(100, news_count * 18)

    source_quality_score = 55
    if evidence_items:
        source_quality_score = int(
            sum(source_quality(item.get("url") or item.get("source", "")) for item in evidence_items)
            / len(evidence_items)
            * 100
        )

    now = datetime.now()
    recency_score = 65
    fetched_times = []
    for item in evidence_items:
        raw_time = item.get("published_at") or item.get("fetched_at")
        try:
            fetched_times.append(datetime.fromisoformat(str(raw_time).replace(" ", "T")))
        except ValueError:
            continue
    if fetched_times:
        hours = max(0.0, (now - max(fetched_times)).total_seconds() / 3600)
        recency_score = int(max(35, 100 - hours * 2.5))

    keywords = topic.get("related_keywords", [])
    if isinstance(keywords, str):
        keywords = re.split(r"[,，、\s]+", keywords)
    keywords = [str(k).strip() for k in keywords if str(k).strip()]
    keyword_density_score = min(100, len(set(keywords)) * 12)

    chains = topic.get("suggested_chains", [])
    if isinstance(chains, str):
        chains = re.split(r"[,，、\n]+", chains)
    chains = [str(c).strip() for c in chains if str(c).strip()]
    chain_clarity_score = min(100, len(set(chains)) * 20)

    score = round(
        0.30 * news_count_score
        + 0.25 * source_quality_score
        + 0.20 * recency_score
        + 0.15 * keyword_density_score
        + 0.10 * chain_clarity_score
    )
    if score >= 80:
        level = "高"
    elif score >= 60:
        level = "中"
    else:
        level = "低"
    return int(score), level


# ---- 综合热度评分（行情数据集成） ----

def calculate_composite_heat(
    topic: dict,
    evidence_items: list[dict],
    market_data: dict | None = None,
) -> tuple[int, str, dict]:
    """
    综合热度分 = 新闻热度分 × 0.6 + 行情热度分 × 0.4

    行情分数获取失败时自动回退为纯新闻热度分（向后兼容）。

    Args:
        topic: 题材数据字典
        evidence_items: 证据新闻列表
        market_data: 行情数据字典，包含以下可选字段：
            - market_heat_score (float): 行情热度分 0-100
            - pct_chg_1d (float): 板块近 1 日涨跌幅
            - pct_chg_3d (float): 板块近 3 日涨跌幅
            - fund_flow (float): 板块资金净流入（亿元）
            - limit_up_count (int): 关联涨停数
            - sector_stock_count (int): 板块成分股总数
            - market_source (str): 行情数据来源标识

    Returns:
        (composite_score: int, level: str, detail: dict)
        detail 包含 news_score、market_score、各子项明细
    """
    # 1. 新闻热度分
    news_score, _ = calculate_heat_score_v2(topic, evidence_items)

    detail = {
        "news_score": news_score,
        "market_score": None,
        "market_source": None,
        "pct_chg_1d": None,
        "pct_chg_3d": None,
        "fund_flow": None,
        "limit_up_count": None,
        "sector_stock_count": None,
    }

    # 2. 行情热度分（如果可用）
    if market_data and isinstance(market_data, dict) and market_data.get("market_heat_score") is not None:
        market_score = float(market_data["market_heat_score"])
        composite = round(news_score * 0.6 + market_score * 0.4)

        detail.update({
            "market_score": round(market_score, 1),
            "market_source": market_data.get("market_source", "akshare"),
            "pct_chg_1d": market_data.get("pct_chg_1d"),
            "pct_chg_3d": market_data.get("pct_chg_3d"),
            "fund_flow": market_data.get("fund_flow"),
            "limit_up_count": market_data.get("limit_up_count"),
            "sector_stock_count": market_data.get("sector_stock_count"),
        })
    else:
        # 回退：纯新闻热度分
        composite = news_score

    # 3. 等级评定
    if composite >= 80:
        level = "高"
    elif composite >= 60:
        level = "中"
    else:
        level = "低"

    return composite, level, detail
def calculate_fermentation_score(topic: dict, evidence_items: list[dict]) -> tuple[int, str]:
    """
    发酵观察评分。

    fermentation_score =
    0.30 * mention_growth_score +
    0.25 * catalyst_strength_score +
    0.20 * chain_spread_score +
    0.15 * source_quality_score +
    0.10 * astock_mapping_score
    """
    evidence_count = len(evidence_items)
    categories = {item.get("category", "") for item in evidence_items if item.get("category")}
    queries = {item.get("search_query", "") for item in evidence_items if item.get("search_query")}
    mention_growth_score = min(100, evidence_count * 14 + len(categories) * 8 + len(queries) * 4)

    trigger_clues = topic.get("trigger_clues", [])
    if isinstance(trigger_clues, str):
        trigger_clues = re.split(r"[,，、;\n]+", trigger_clues)
    catalyst_words = ("政策", "公告", "订单", "突破", "量产", "发布", "扩产", "研报", "合作", "招标")
    catalyst_hits = sum(
        1 for clue in trigger_clues
        if any(word in str(clue) for word in catalyst_words)
    )
    catalyst_strength_score = min(100, len([x for x in trigger_clues if str(x).strip()]) * 18 + catalyst_hits * 14)

    chains = topic.get("suggested_chains", [])
    if isinstance(chains, str):
        chains = re.split(r"[,，、;\n]+", chains)
    chain_spread_score = min(100, len({str(x).strip() for x in chains if str(x).strip()}) * 22)

    source_quality_score = 55
    if evidence_items:
        source_quality_score = int(
            sum(source_quality(item.get("url") or item.get("source", "")) for item in evidence_items)
            / len(evidence_items)
            * 100
        )

    stocks = topic.get("preliminary_related_stocks", [])
    if isinstance(stocks, str):
        stocks = re.split(r"[,，、;\n]+", stocks)
    astock_mapping_score = min(100, len({str(x).strip() for x in stocks if str(x).strip()}) * 16)

    score = round(
        0.30 * mention_growth_score
        + 0.25 * catalyst_strength_score
        + 0.20 * chain_spread_score
        + 0.15 * source_quality_score
        + 0.10 * astock_mapping_score
    )
    if score >= 75:
        status = "正在升温"
    elif score >= 55:
        status = "预热中"
    else:
        status = "等待确认"
    return int(score), status


# ---- 实体提取（轻量规则） ----

# 中文停用词 / 财经泛词（使用共享常量）
_FINANCE_STOP_WORDS = FINANCE_STOP_WORDS


def extract_entities_from_news(news_items: list[dict], max_entities: int = 25) -> list[str]:
    """
    从新闻标题和摘要中提取高频关键实体。
    返回 entity 列表（按出现频率降序）。
    """
    import re as _re
    from collections import Counter

    counter = Counter()
    for item in news_items:
        title = str(item.get("title") or "")
        summary = str(item.get("summary") or "")
        text = title + " " + summary

        # 中文词：2-8 字的连续中文字符串
        chinese_words = _re.findall(r"[\u4e00-\u9fff]{2,8}", text)
        for word in chinese_words:
            if word in _FINANCE_STOP_WORDS:
                continue
            # 过滤纯数字/日期
            if _re.match(r"^[\d零一二三四五六七八九十百千万亿]+$", word):
                continue
            counter[word] += 1

        # 英文/混合词：大写字母开头或含数字的术语
        mixed_words = _re.findall(r"[A-Z][A-Za-z0-9\-]{1,15}|[A-Za-z]+[\u4e00-\u9fff]+|[0-9]+[A-Za-z]+", text)
        for word in mixed_words:
            word = word.strip()
            if len(word) >= 2:
                counter[word] += 1

    return [word for word, _ in counter.most_common(max_entities)]


def build_entity_search_queries(entities: list[str], max_queries: int = 20) -> list[dict]:
    """基于关键实体生成第二轮搜索 query，保留 category 追踪"""
    queries = []
    for entity in entities[:15]:
        base = f"{entity} A股"
        queries.append({"category": "实体深挖", "query": base})
        queries.append({"category": "实体深挖", "query": f"{entity} 产业链"})
        queries.append({"category": "实体深挖", "query": f"{entity} 受益股"})
        queries.append({"category": "实体深挖", "query": f"{entity} 概念股"})
        queries.append({"category": "实体深挖", "query": f"{entity} 供应商"})
    return queries[:max_queries]


def second_round_search(
    entities: list[str],
    start: "datetime",
    end: "datetime",
    max_results_per_query: int = 3,
) -> list[dict]:
    """基于实体执行第二轮深挖搜索，返回去重后的新闻列表"""
    queries = build_entity_search_queries(entities)
    raw_news = []
    for item in queries:
        query = f"{item['query']} {start:%Y-%m-%d}..{end:%Y-%m-%d}"
        for result in _search_ddgs(query, max_results=max_results_per_query):
            title = (result.get("title") or "").strip()
            summary = (result.get("body") or "").strip()
            url = (result.get("href") or "").strip()
            if not title and not summary:
                continue
            raw_news.append({
                "news_id": _news_id(url, title),
                "title": title,
                "summary": summary,
                "content": "",
                "source": _source_from_url(url),
                "url": url,
                "published_at": _parse_published_at(result),
                "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "search_query": item["query"],
                "category": item["category"],
            })
    return dedupe_news(raw_news)


# ---- 新热度评分 v2 ----

def _news_count_score(news_count: int) -> float:
    return min(100.0, news_count * 18.0)


def _recency_score(evidence_items: list[dict]) -> float:
    now = datetime.now()
    fetched_times = []
    for item in evidence_items:
        raw_time = item.get("published_at") or item.get("fetched_at")
        try:
            fetched_times.append(datetime.fromisoformat(str(raw_time).replace(" ", "T")))
        except ValueError:
            continue
    if not fetched_times:
        return 65.0
    hours = max(0.0, (now - max(fetched_times)).total_seconds() / 3600)
    return max(35.0, 100.0 - hours * 2.5)


def _catalyst_score(topic: dict) -> float:
    """触发事件强度。政策>涨价>技术突破>订单>事件驱动"""
    trigger = str(topic.get("trigger_event") or "")
    core = str(topic.get("core_logic") or "")
    text = trigger + core

    weights = {
        "政策": 18, "文件": 16, "国务院": 20, "工信部": 18,
        "涨价": 18, "提价": 18, "供不应求": 16,
        "突破": 16, "量产": 16, "首发": 15,
        "订单": 15, "中标": 14, "供货": 14,
        "上市": 15, "IPO": 15, "发布会": 13,
        "涨停": 12, "异动": 10, "资金流入": 10,
    }
    score = 40.0
    for keyword, weight in weights.items():
        if keyword in text:
            score = min(100.0, score + weight)
    return score


def _specificity_score(topic: dict) -> float:
    """题材细分度。名称越具体、越不宽泛，分数越高"""
    topic_name = str(topic.get("topic_name") or "").strip()

    # 命中黑名单 → 大幅降权
    for broad in BROAD_TOPIC_BLACKLIST:
        if broad in topic_name:
            return 10.0

    # 长度惩罚：太短（≤3字）通常太宽泛
    if len(topic_name) <= 3:
        return 40.0 + min(len(topic_name) * 3, 15)

    # 包含具体特征词加分
    specificity_words = [
        "铜箔", "设备", "材料", "封测", "封装", "光刻", "硅", "芯片",
        "传感器", "减速器", "丝杠", "电机", "电池", "激光", "连接器",
        "PCB", "CCL", "HBM", "DRAM", "NAND", "eVTOL", "CoWoS",
        "映射", "供应商", "受益", "订单", "涨价", "IPO", "上市",
    ]
    bonus = sum(8 for word in specificity_words if word in topic_name)
    # AI 给的初步分
    ai_score = float(topic.get("specificity_score") or 60)
    base = (ai_score + 50) / 2
    return min(100.0, base + bonus)


def _novelty_score(topic: dict) -> float:
    """题材新鲜度"""
    ai_score = float(topic.get("novelty_score") or 50)
    # trigger 中新事件词加分
    trigger = str(topic.get("trigger_event") or "")
    novelty_words = ["首次", "新发布", "突破", "量产", "IPO", "上市", "首发", "刚", "近日"]
    bonus = sum(5 for word in novelty_words if word in trigger)
    return min(100.0, ai_score * 0.7 + 30 + bonus)


def _stock_mapping_score(topic: dict) -> float:
    """A股映射清晰度"""
    stocks = topic.get("preliminary_related_stocks", [])
    if isinstance(stocks, str):
        stocks = re.split(r"[,，、;\n]+", stocks)
    stocks = [s.strip() for s in stocks if s.strip()]
    chains = topic.get("suggested_chains", [])
    if isinstance(chains, str):
        chains = re.split(r"[,，、;\n]+", chains)
    chains = [c.strip() for c in chains if c.strip()]
    score = min(100.0, len(stocks) * 15 + len(chains) * 10)
    return max(30.0, score)


def calculate_heat_score_v2(topic: dict, evidence_items: list[dict]) -> tuple[int, str]:
    """
    新热度评分公式：
    heat_score =
      0.25 * news_count_score
      + 0.20 * recency_score
      + 0.20 * catalyst_score
      + 0.15 * specificity_score
      + 0.10 * stock_mapping_score
      + 0.10 * novelty_score
    """
    news_count = len(evidence_items)
    score = round(
        0.25 * _news_count_score(news_count)
        + 0.20 * _recency_score(evidence_items)
        + 0.20 * _catalyst_score(topic)
        + 0.15 * _specificity_score(topic)
        + 0.10 * _stock_mapping_score(topic)
        + 0.10 * _novelty_score(topic)
    )
    if score >= 80:
        level = "高"
    elif score >= 60:
        level = "中"
    else:
        level = "低"
    return int(score), level
