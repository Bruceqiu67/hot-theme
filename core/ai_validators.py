"""
AI 数据校验 & 工具函数
— JSON 提取/修复、字段校验、产业链展平、网页搜索
"""
import json
import re
from datetime import datetime
from typing import Any
from config import get_logger
from core.constants  import BROAD_TOPIC_BLACKLIST
_log = get_logger("ai_validators")


# ======================== JSON 处理 ========================

def _repair_truncated_json(text: str) -> str:
    """尝试修复被截断的 JSON：补全未闭合的引号、括号、大括号"""
    # 如果在字符串中间截断，先闭合引号
    in_string = False
    escape = False
    repaired = list(text)
    for ch in text:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string

    # 如果在字符串内被截断，加闭合引号
    if in_string:
        repaired.append('"')

    text = "".join(repaired)

    # 统计未闭合的 {} 和 []
    depth_braces = 0
    depth_brackets = 0
    in_string = False
    escape = False
    for ch in text:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth_braces += 1
        elif ch == "}":
            depth_braces -= 1
        elif ch == "[":
            depth_brackets += 1
        elif ch == "]":
            depth_brackets -= 1

    # 补全未闭合的括号
    if depth_brackets > 0:
        text += "]" * depth_brackets
    if depth_braces > 0:
        text += "}" * depth_braces

    return text


def _extract_json(text: str) -> str:
    """
    从混合文本中提取 JSON 对象。
    处理推理型模型（如 deepseek-v4-pro）在 JSON 前输出思考过程的情况。

    策略：
    1. 先尝试直接解析
    2. 查找 ```json ... ``` 代码块
    3. 从每一个 '{' 处尝试解析完整 JSON，避免截到最后一个内部对象
    """
    text = text.strip()

    # 策略 1: 直接就是 JSON
    if text.startswith("{"):
        return text

    # 策略 2: markdown 代码块
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        return m.group(1).strip()

    # 策略 3: 从每一个 '{' 处尝试解析完整 JSON，避免截到最后一个内部对象
    decoder = json.JSONDecoder()
    candidates = []
    for match in re.finditer(r"\{", text):
        start = match.start()
        try:
            obj, end = decoder.raw_decode(text[start:])
            candidate = text[start : start + end]
            if isinstance(obj, dict) and any(k in obj for k in ("theme_name", "theme_quality", "chains", "topics", "predictions")):
                return candidate
            candidates.append(candidate)
        except json.JSONDecodeError:
            continue

    if candidates:
        return candidates[0]

    return text


# ======================== 字段转换 ========================

def _current_year() -> int:
    return datetime.now().year


def _to_score(value, default: Any = None) -> int | Any:
    """转成 1-10 分；非法值返回 default"""
    try:
        score = int(float(value))
    except (TypeError, ValueError):
        return default
    if 1 <= score <= 10:
        return score
    return default


def _to_probability(value, default: Any = None) -> int | Any:
    """转成 0-100 概率；非法值返回 default"""
    try:
        prob = int(float(value))
    except (TypeError, ValueError):
        return default
    if 0 <= prob <= 100:
        return prob
    return default


def _valid_stock_code(value: str) -> str:
    code = str(value or "").strip()
    if code.endswith(".0"):
        code = code[:-2]
    code = code.zfill(6)
    return code if re.fullmatch(r"\d{6}", code) else ""


def _normalize_choice(value: str, choices: tuple[str, ...], default: str) -> str:
    value = str(value or "").strip()
    return value if value in choices else default


# ======================== 网页搜索 ========================

def _search_web(query: str, max_results: int = 8, max_retries: int = 1) -> str:
    """
    搜索网页并返回拼接的摘要文本。

    P2-7: 使用 China-friendly 多引擎搜索层 (Bing 优先)，
    替代原来的 DDGS-only 方案，解决国内网络环境下搜索超时问题。
    单引擎超时 12s，快速失败，不阻塞。
    """
    from core.search_providers import search_as_text

    for attempt in range(max_retries + 1):
        try:
            result = search_as_text(query, max_results=max_results)
            if result:
                return result
            # search_as_text 返回空字符串表示所有 provider 均失败
            if attempt < max_retries:
                _log.debug("网页搜索无结果 (query=%s)，重试 %d/%d", query[:50], attempt + 1, max_retries)
                import time
                time.sleep(0.5)
            else:
                _log.warning("网页搜索无结果 (query=%s)，所有搜索引擎均失败", query[:50])
                return ""
        except Exception as exc:
            if attempt < max_retries:
                _log.warning("网页搜索异常 (query=%s)，重试 %d/%d: %s", query[:50], attempt + 1, max_retries, exc)
                import time
                time.sleep(0.5)
            else:
                _log.warning("网页搜索异常 (query=%s): %s", query[:50], exc)
                return ""
    return ""


# ======================== 数据校验 ========================

def validate_theme_analysis(data: dict) -> dict:
    """规范化题材分析 JSON，过滤明显无效的个股记录"""
    if not isinstance(data, dict):
        raise RuntimeError("模型返回 JSON 顶层不是对象")

    theme_name = str(data.get("theme_name", "")).strip()
    chains = data.get("chains", [])
    if not theme_name:
        raise RuntimeError("模型返回缺少 theme_name")
    if not isinstance(chains, list) or not chains:
        raise RuntimeError("模型返回缺少 chains")

    quality = data.get("theme_quality", {}) if isinstance(data.get("theme_quality", {}), dict) else {}
    data["theme_quality"] = {
        "breadth": _to_score(quality.get("breadth")),
        "event_density": _to_score(quality.get("event_density")),
        "capital_flow": _to_score(quality.get("capital_flow")),
        "sustainability": _to_score(quality.get("sustainability")),
        "overall_score": _to_score(quality.get("overall_score")),
        "summary": str(quality.get("summary", "")).strip(),
    }

    cleaned_chains = []
    for chain in chains:
        if not isinstance(chain, dict):
            continue
        stocks = chain.get("stocks", [])
        if not isinstance(stocks, list):
            continue
        cleaned_stocks = []
        for stock in stocks:
            if not isinstance(stock, dict):
                continue
            code = _valid_stock_code(stock.get("stock_code", ""))
            name = str(stock.get("stock_name", "")).strip()
            if not code or not name:
                continue
            cleaned_stocks.append({
                **stock,
                "stock_code": code,
                "stock_name": name,
                "market_type": _normalize_choice(stock.get("market_type"), ("主板", "创业板", "科创板", "北交所"), "主板"),
                "importance": _normalize_choice(stock.get("importance"), ("高", "中", "低"), "中"),
                "tier": _normalize_choice(stock.get("tier"), ("核心", "次级", "观察"), "观察"),
                "biz_relevance": _to_score(stock.get("biz_relevance"), ""),
                "biz_growth": _to_score(stock.get("biz_growth"), ""),
                "quality_score": _to_score(stock.get("quality_score"), ""),
                "flow_score": _to_score(stock.get("flow_score"), ""),
            })
        if cleaned_stocks:
            cleaned_chains.append({
                "level1": str(chain.get("level1", "")).strip() or "未分类",
                "level2": str(chain.get("level2", "")).strip(),
                "level3": str(chain.get("level3", "")).strip(),
                "stocks": cleaned_stocks,
            })

    if not cleaned_chains:
        raise RuntimeError("模型返回中没有可用的 A 股个股记录")

    return {
        "theme_name": theme_name,
        "theme_quality": data["theme_quality"],
        "chains": cleaned_chains,
    }


def validate_hot_topics(topics: list[dict]) -> list[dict]:
    """规范化热点题材列表，过滤无名称项并补齐展示字段"""
    if not isinstance(topics, list):
        raise RuntimeError("热点题材返回格式错误：topics 不是数组")
    cleaned = []
    seen = set()
    for item in topics:
        if not isinstance(item, dict):
            continue
        name = str(item.get("theme_name", "")).strip()
        if not name:
            continue
        # 过滤太宽泛的题材名称
        if any(keyword in name for keyword in BROAD_TOPIC_BLACKLIST):
            _log.info("过滤宽泛题材: %s", name)
            continue
        key = re.sub(r"\s+", "", name)
        if key in seen:
            continue
        seen.add(key)
        evidence = item.get("evidence", [])
        if isinstance(evidence, str):
            evidence = [evidence]
        if not isinstance(evidence, list):
            evidence = []
        # 验证 hot_score 范围
        hot_score = _to_probability(item.get("hot_score"), 50)
        if hot_score is None:
            hot_score = 50
        # 验证 source_count 范围
        source_count = max(0, int(_to_probability(item.get("source_count"), len(evidence)) or 0))
        cleaned.append({
            "theme_name": name,
            "summary": str(item.get("summary", "")).strip(),
            "hot_score": hot_score,
            "catalyst": str(item.get("catalyst", "")).strip() or "综合催化",
            "evidence": [str(x).strip() for x in evidence if str(x).strip()][:4],
            "source_count": source_count,
        })
    if not cleaned:
        raise RuntimeError("未生成有效热点题材")
    # 按 hot_score 降序排序
    cleaned.sort(key=lambda x: x["hot_score"], reverse=True)
    return cleaned


def validate_predictions(predictions: list[dict]) -> list[dict]:
    """严格校验预测输出，避免页面静默兜底造成误判"""
    if not isinstance(predictions, list):
        raise RuntimeError("预测返回格式错误：predictions 不是数组")

    cleaned = []
    required_scores = ("AI", "FF", "SM", "CH", "PV")
    for item in predictions:
        if not isinstance(item, dict):
            continue
        name = str(item.get("theme_name", "")).strip()
        prob = _to_probability(item.get("ferment_prob"))
        scores = item.get("scores", {})
        if not name or prob is None or not isinstance(scores, dict):
            continue
        # 验证发酵概率范围
        if prob < 0 or prob > 100:
            _log.warning("发酵概率超出范围: %d, 题材: %s", prob, name)
            continue
        norm_scores = {}
        for key in required_scores:
            score = _to_score(scores.get(key))
            if score is None:
                break
            norm_scores[key] = score
        if len(norm_scores) != len(required_scores):
            continue
        evidence = item.get("evidence", [])
        if isinstance(evidence, str):
            evidence = [evidence]
        if not isinstance(evidence, list):
            evidence = []
        # 验证证据数量
        if len(evidence) < 2:
            _log.warning("预测证据不足 (<2)，题材: %s", name)
            continue

        cleaned.append({
            "theme_name": name,
            "ferment_prob": prob,
            "confidence": _normalize_choice(item.get("confidence"), ("高", "中", "低"), "中"),
            "gate_pass": bool(item.get("gate_pass", False)),
            "signal_type": _normalize_choice(
                item.get("signal_type"),
                ("政策催化", "技术突破", "资金异动", "产业链传导", "事件驱动"),
                "事件驱动",
            ),
            "reason": str(item.get("reason", "")).strip(),
            "related_existing": str(item.get("related_existing", "")).strip() or "新方向",
            "key_trigger": str(item.get("key_trigger", "")).strip(),
            "scores": norm_scores,
            "evidence": [str(x).strip() for x in evidence if str(x).strip()][:4],
            "suggested_stocks": str(item.get("suggested_stocks", "")).strip(),
        })

    if not cleaned:
        raise RuntimeError("预测结果缺少必要字段，请重新生成")
    return sorted(cleaned, key=lambda x: x["ferment_prob"], reverse=True)


def validate_fermentation_observations(observations: list[dict], valid_news_ids: set[str]) -> list[dict]:
    """校验发酵观察线索，确保只保留可追溯的观察项"""
    if not isinstance(observations, list):
        raise RuntimeError("发酵观察返回格式错误：observations 不是数组")

    cleaned = []
    seen = set()
    for item in observations:
        if not isinstance(item, dict):
            continue
        name = str(item.get("topic_name", "")).strip()
        if not name:
            continue
        key = re.sub(r"\s+", "", name)
        if key in seen:
            continue
        seen.add(key)

        source_items = []
        for source in item.get("source_items", []):
            if not isinstance(source, dict):
                continue
            news_id = str(source.get("news_id", "")).strip()
            if news_id not in valid_news_ids:
                continue
            source_items.append({
                "news_id": news_id,
                "relevance_score": _to_probability(source.get("relevance_score"), 60),
                "reason": str(source.get("reason", "")).strip(),
            })
        if not source_items:
            continue

        cleaned.append({
            "topic_name": name,
            "fermentation_score": _to_probability(item.get("fermentation_score"), 50),
            "status": _normalize_choice(item.get("status"), ("预热中", "正在升温", "等待确认"), "等待确认"),
            "trigger_clues": _ensure_list(item.get("trigger_clues", []))[:8],
            "why_watch": str(item.get("why_watch", "")).strip(),
            "related_keywords": _ensure_list(item.get("related_keywords", []))[:12],
            "suggested_chains": _ensure_list(item.get("suggested_chains", []))[:8],
            "preliminary_related_stocks": _ensure_list(item.get("preliminary_related_stocks", []))[:12],
            "evidence_count": max(1, int(_to_probability(item.get("evidence_count"), len(source_items)) or len(source_items))),
            "source_summary": str(item.get("source_summary", "")).strip(),
            "source_items": source_items[:6],
            "next_signals_to_watch": _ensure_list(item.get("next_signals_to_watch", []))[:8],
            "risk_note": str(item.get("risk_note", "")).strip(),
            "action_options": ["加入观察池", "生成产业链草稿", "忽略"],
        })

    if not cleaned:
        raise RuntimeError("未生成有效发酵观察线索")
    return cleaned


def validate_candidate_topics(topics: list[dict], valid_news_ids: set[str]) -> list[dict]:
    """校验候选热点题材输出，保留可追溯证据"""
    if not isinstance(topics, list):
        raise RuntimeError("候选题材返回格式错误：topics 不是数组")

    cleaned = []
    seen = set()
    for item in topics:
        if not isinstance(item, dict):
            continue
        name = str(item.get("topic_name", "") or item.get("theme_name", "")).strip()
        if not name:
            continue
        # 宽泛题材不再过滤，只标记降权
        is_broad = any(b in name for b in BROAD_TOPIC_BLACKLIST)
        key = re.sub(r"\s+", "", name)
        if key in seen:
            continue
        seen.add(key)

        source_items = []
        for source in item.get("source_items", []):
            if not isinstance(source, dict):
                continue
            news_id = str(source.get("news_id", "")).strip()
            if news_id not in valid_news_ids:
                continue
            source_items.append({
                "news_id": news_id,
                "relevance_score": _to_probability(source.get("relevance_score"), 60),
                "reason": str(source.get("reason", "")).strip(),
            })
        if not source_items:
            continue

        suggested_chains = _ensure_list(item.get("suggested_chains", []))
        related_keywords = _ensure_list(item.get("related_keywords", []))
        preliminary_stocks = _ensure_list(item.get("preliminary_related_stocks", []))
        # v2 新字段
        topic_type = _normalize_choice(
            item.get("topic_type"),
            ("细分题材", "事件映射题材", "IPO上市映射题材", "政策催化题材", "产业链涨价题材", "产品发布映射题材"),
            "细分题材",
        )
        specificity = _to_probability(item.get("specificity_score"), 60)
        if is_broad:
            specificity = min(specificity or 60, 25)
        novelty = _to_probability(item.get("novelty_score"), 50)

        cleaned.append({
            "topic_name": name,
            "topic_type": topic_type,
            "parent_theme": str(item.get("parent_theme") or "").strip(),
            "heat_score": _to_probability(item.get("heat_score"), 50),
            "heat_level": _normalize_choice(item.get("heat_level"), ("高", "中", "低"), "中"),
            "trigger_event": str(item.get("trigger_event", "")).strip(),
            "core_logic": str(item.get("core_logic", "")).strip(),
            "evidence_summary": str(item.get("evidence_summary", "")).strip(),
            "source_items": source_items[:6],
            "suggested_chains": suggested_chains[:8],
            "related_keywords": related_keywords[:12],
            "preliminary_related_stocks": preliminary_stocks[:12],
            "key_entities": _ensure_list(item.get("key_entities", []))[:15],
            "specificity_score": specificity,
            "novelty_score": novelty,
            "confidence": _normalize_choice(item.get("confidence"), ("高", "中", "低"), "中"),
            "should_import": bool(item.get("should_import", False)),
            "reason_to_import": str(item.get("reason_to_import", "")).strip(),
            "risk_note": str(item.get("risk_note", "")).strip(),
        })

    if not cleaned:
        raise RuntimeError("未生成有效候选题材")
    return cleaned


def validate_chain_decomposition(data: dict) -> dict:
    """校验阶段一产业链拆解结果"""
    if not isinstance(data, dict):
        raise RuntimeError("产业链拆解返回 JSON 顶层不是对象")
    nodes = data.get("chain_nodes", [])
    if not isinstance(nodes, list) or not nodes:
        raise RuntimeError("产业链拆解缺少 chain_nodes")
    cleaned_nodes = []
    seen = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        level1 = str(node.get("level1", "")).strip()
        level2 = str(node.get("level2", "")).strip()
        level3 = str(node.get("level3", "")).strip()
        if not level1:
            continue
        key = (level1, level2, level3)
        if key in seen:
            continue
        seen.add(key)
        cleaned_nodes.append({
            "level1": level1,
            "level2": level2,
            "level3": level3,
            "node_description": str(node.get("node_description", "")).strip(),
            "why_it_matters": str(node.get("why_it_matters", "")).strip(),
            "importance": _normalize_choice(node.get("importance"), ("核心", "重要", "观察"), "观察"),
        })
    if not cleaned_nodes:
        raise RuntimeError("产业链拆解没有有效节点")
    return {
        "theme_definition": str(data.get("theme_definition", "")).strip(),
        "trigger_event": str(data.get("trigger_event", "")).strip(),
        "core_logic": str(data.get("core_logic", "")).strip(),
        "industry_scope": str(data.get("industry_scope", "")).strip(),
        "excluded_scope": str(data.get("excluded_scope", "")).strip(),
        "chain_nodes": cleaned_nodes,
    }


def validate_stock_mapping(data: dict, chain_nodes: list[dict]) -> list[dict]:
    """校验阶段二个股映射结果"""
    if not isinstance(data, dict):
        raise RuntimeError("个股映射返回 JSON 顶层不是对象")
    stocks = data.get("stocks", [])
    if not isinstance(stocks, list) or not stocks:
        raise RuntimeError("个股映射缺少 stocks")
    node_keys = {
        (node.get("level1", ""), node.get("level2", ""), node.get("level3", ""))
        for node in chain_nodes
    }
    cleaned = []
    seen_codes = set()
    for stock in stocks:
        if not isinstance(stock, dict):
            continue
        code = _valid_stock_code(stock.get("stock_code", ""))
        name = str(stock.get("stock_name", "")).strip()
        if not code or not name:
            continue
        if code in seen_codes:
            continue
        level1 = str(stock.get("level1", "")).strip()
        level2 = str(stock.get("level2", "")).strip()
        level3 = str(stock.get("level3", "")).strip()
        if (level1, level2, level3) not in node_keys:
            # 允许模型漏填二三级时保留 level1 匹配的节点，避免过度丢弃
            matches = [key for key in node_keys if key[0] == level1]
            if matches:
                level1, level2, level3 = matches[0]
            else:
                continue
        seen_codes.add(code)
        cleaned.append({
            "stock_code": code,
            "stock_name": name,
            "market_type": _normalize_choice(stock.get("market_type"), ("主板", "创业板", "科创板", "北交所"), "主板"),
            "level1": level1,
            "level2": level2,
            "level3": level3,
            "role": str(stock.get("role", "")).strip(),
            "logic_summary": str(stock.get("logic_summary", "")).strip(),
            "market_position": _safe_verification_text(stock.get("market_position")),
            "market_share": _safe_verification_text(stock.get("market_share")),
            "customers": _safe_verification_text(stock.get("customers")),
            "products": str(stock.get("products", "")).strip(),
            "evidence": str(stock.get("evidence", "")).strip(),
            "relevance_score": _to_score(stock.get("relevance_score"), 5),
            "importance": _normalize_choice(stock.get("importance"), ("核心", "重要", "观察", "泛相关"), "观察"),
            "verification_status": "待人工核验",
            "risk_note": str(stock.get("risk_note", "")).strip(),
        })
    if not cleaned:
        raise RuntimeError("个股映射没有有效 A 股公司")
    return cleaned


def _safe_verification_text(value) -> str:
    value = str(value or "").strip()
    if not value or value in {"未知", "不详", "暂无"}:
        return "待核验"
    return value


def _ensure_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,，、;\n]+", value) if item.strip()]
    return []


# ======================== 数据展平 ========================

def flatten_chains(data: dict) -> tuple[list[dict], dict]:
    """
    将嵌套的 chains 结构展平为 CSV 行格式

    Returns:
        tuple: (rows, theme_quality_dict)
    """
    rows = []
    theme_name = data.get("theme_name", "")
    theme_quality = data.get("theme_quality", {})

    for chain in data.get("chains", []):
        l1 = chain.get("level1", "")
        l2 = chain.get("level2", "")
        l3 = chain.get("level3", "")

        for stock in chain.get("stocks", []):
            rows.append({
                "theme_name": theme_name,
                "level1": l1,
                "level2": l2,
                "level3": l3,
                "stock_code": str(stock.get("stock_code", "")).strip(),
                "stock_name": stock.get("stock_name", ""),
                "market_type": stock.get("market_type", ""),
                "role": stock.get("role", ""),
                "logic_summary": stock.get("logic_summary", ""),
                "market_position": stock.get("market_position", ""),
                "market_share": stock.get("market_share", ""),
                "customers": stock.get("customers", ""),
                "importance": stock.get("importance", "中"),
                "source": stock.get("source", ""),
                "notes": stock.get("notes", ""),
                "tier": stock.get("tier", "观察"),
                "biz_relevance": stock.get("biz_relevance", ""),
                "biz_growth": stock.get("biz_growth", ""),
                "quality_score": stock.get("quality_score", ""),
                "flow_score": stock.get("flow_score", ""),
            })

    return rows, theme_quality
