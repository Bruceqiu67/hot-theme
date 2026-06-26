"""
AI 客户端 — 调用 OpenAI 兼容 API（DeepSeek / OpenAI 等）
P1-8: API Key 加密存储（Fernet 对称加密）
"""
import json
import os
import base64
from functools import lru_cache
from openai import OpenAI

try:
    from cryptography.fernet import Fernet, InvalidToken
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False
from config import get_logger
from core.ai_prompts  import (    SYSTEM_PROMPT,
    HOT_TOPICS_PROMPT,
    FERMENTATION_OBSERVATION_PROMPT,
    PREDICTIONS_PROMPT,
    CANDIDATE_TOPICS_PROMPT,
    ENTITY_EXTRACTION_PROMPT,
    CHAIN_DECOMPOSITION_PROMPT,
    STOCK_MAPPING_PROMPT,
)
from core.ai_validators  import (    _current_year,
    _extract_json,
    _repair_truncated_json,
    _search_web,
    validate_theme_analysis,
    validate_hot_topics,
    validate_predictions,
    validate_fermentation_observations,
    validate_candidate_topics,
    validate_chain_decomposition,
    validate_stock_mapping,
    flatten_chains,
)
from core.fetch_news  import (    calculate_fermentation_score,
    calculate_heat_score,
    calculate_heat_score_v2,
    calculate_composite_heat,
    extract_entities_from_news,
    second_round_search,
)
from core.constants  import BROAD_TOPIC_BLACKLIST, FINANCE_STOP_WORDS
_log = get_logger("ai_client")


# ---- OpenAI 客户端缓存 ----

@lru_cache(maxsize=8)
def _get_client(api_key: str, base_url: str) -> OpenAI:
    """缓存 OpenAI 客户端实例，避免重复创建连接池"""
    return OpenAI(api_key=api_key, base_url=base_url)


# ---- P1-8: API Key 加密存储 ----

def _get_key_path() -> str:
    """获取加密密钥文件路径（Windows: 用户目录下 .marvis_key）"""
    home = os.path.expanduser("~")
    return os.path.join(home, ".marvis_key")


def _get_config_path() -> str:
    """获取 API 配置文件路径（统一使用 config.DATA_DIR）"""
    from config import DATA_DIR
    return os.path.join(DATA_DIR, "api_config.json")


def _load_or_create_key() -> bytes | None:
    """加载或创建 Fernet 密钥"""
    if not _CRYPTO_AVAILABLE:
        return None
    key_path = _get_key_path()
    try:
        if os.path.exists(key_path):
            with open(key_path, "rb") as f:
                return f.read()
        # 创建新密钥，仅当前用户可读写（Windows 下通过文件 ACL 控制）
        key = Fernet.generate_key()
        with open(key_path, "wb") as f:
            f.write(key)
        # 尝试限制权限（Windows 不直接支持 chmod，忽略）
        try:
            os.chmod(key_path, 0o600)
        except Exception:
            pass
        _log.info("已创建加密密钥: %s", key_path)
        return key
    except Exception as exc:
        _log.warning("密钥操作失败: %s", exc)
        return None


def _get_fernet():
    """获取 Fernet 实例。返回 Fernet 或 None。"""
    if not _CRYPTO_AVAILABLE:
        return None
    key = _load_or_create_key()
    if key:
        return Fernet(key)
    return None


def _is_encrypted(data: bytes) -> bool:
    """判断数据是否为 Fernet 加密格式（前缀 gAAAAA）"""
    return data.startswith(b"gAAAAA")


def _migrate_plaintext_to_encrypted(config_path: str) -> bool:
    """
    检测旧版明文 api_config.json 并自动加密迁移。
    返回 True 表示已迁移。
    """
    if not _CRYPTO_AVAILABLE or not os.path.exists(config_path):
        return False
    try:
        with open(config_path, "rb") as f:
            raw = f.read()
        if _is_encrypted(raw):
            return False  # 已是密文，无需迁移

        # 明文 JSON → 加密
        config = json.loads(raw.decode("utf-8"))
        fernet = _get_fernet()
        if not fernet:
            return False
        encrypted = fernet.encrypt(json.dumps(config, ensure_ascii=False).encode("utf-8"))
        with open(config_path, "wb") as f:
            f.write(encrypted)
        _log.info("已自动加密迁移 api_config.json")
        return True
    except Exception as exc:
        _log.debug("迁移加密失败: %s", exc)
        return False


def _decrypt_config_file(config_path: str) -> dict | None:
    """解密配置文件，返回 dict；失败返回 None"""
    if not _CRYPTO_AVAILABLE:
        return None
    try:
        with open(config_path, "rb") as f:
            raw = f.read()
        if not _is_encrypted(raw):
            return json.loads(raw.decode("utf-8"))
        fernet = _get_fernet()
        if not fernet:
            return None
        decrypted = fernet.decrypt(raw)
        return json.loads(decrypted.decode("utf-8"))
    except InvalidToken:
        _log.warning("配置文件解密失败：密钥不匹配或数据损坏")
        return None
    except Exception as exc:
        _log.debug("读取配置文件失败: %s", exc)
        return None


def _encrypt_and_save_config(config_path: str, config: dict) -> bool:
    """加密并保存配置到文件"""
    if not _CRYPTO_AVAILABLE:
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return True
        except OSError:
            return False
    try:
        fernet = _get_fernet()
        if not fernet:
            return False
        encrypted = fernet.encrypt(json.dumps(config, ensure_ascii=False).encode("utf-8"))
        with open(config_path, "wb") as f:
            f.write(encrypted)
        return True
    except Exception as exc:
        _log.warning("加密保存配置失败: %s", exc)
        return False


# ---- 共享的 API 配置 ----

def load_api_config(
    session_state_get=None,
    default_base: str = "https://api.deepseek.com",
    default_model: str = "deepseek-v4-flash",
) -> tuple[str, str, str]:
    """
    跨模块加载 API 配置，优先级：
    1. session_state
    2. 本地文件 data/api_config.json
    3. streamlit secrets.toml
    4. 默认值
    """
    key = ""
    url = ""
    model = ""

    # session_state
    if session_state_get:
        key = session_state_get("ai_api_key", "")
        url = session_state_get("ai_base_url", "")
        model = session_state_get("ai_model", "")

    # 本地文件（P1-8: 支持加密存储 + 自动明文迁移）
    if not key or not url or not model:
        try:
            config_path = _get_config_path()
            if os.path.exists(config_path):
                # 先尝试解密读取
                saved = _decrypt_config_file(config_path)
                # 如果解密失败但文件存在，尝试明文回退
                if saved is None:
                    try:
                        with open(config_path, "r", encoding="utf-8") as f:
                            saved = json.load(f)
                        # 明文回退成功 → 自动迁移加密
                        _migrate_plaintext_to_encrypted(config_path)
                    except Exception:
                        saved = {}
                if saved:
                    key = key or saved.get("api_key", "")
                    url = url or saved.get("base_url", "")
                    model = model or saved.get("model", "")
        except Exception as exc:
            _log.debug("读取 api_config.json 失败: %s", exc)

    # secrets (需要在 streamlit 上下文中)
    if not key and session_state_get:
        try:
            import streamlit as st
            key = st.secrets.get("api_key", "") or key
            url = st.secrets.get("base_url", "") or url
            model = st.secrets.get("model", "") or model
        except Exception as exc:
            _log.debug("读取 streamlit secrets 失败: %s", exc)

    return (key, url or default_base, model or default_model)


def save_api_config(api_key: str, base_url: str, model: str, session_state=None) -> None:
    """
    持久化 API 配置到 session_state 和本地文件。
    跨会话恢复：下次 load_api_config 可自动读取。

    Args:
        api_key: API 密钥
        base_url: API 地址
        model: 模型名称
        session_state: Streamlit session_state 对象（可选），传入则同步更新内存
    """
    if session_state is not None:
        session_state["ai_api_key"] = api_key
        session_state["ai_base_url"] = base_url
        session_state["ai_model"] = model

    config_path = _get_config_path()
    config = {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
    }
    if not _encrypt_and_save_config(config_path, config):
        _log.warning("保存 api_config.json 失败")


# ---- AI 生成函数 ----

def generate_theme_analysis(
    theme_name: str,
    api_key: str,
    base_url: str = "https://api.deepseek.com",
    model: str = "deepseek-v4-flash",
    extra_hint: str = "",
) -> dict:
    """
    调用 LLM 生成题材产业链分析

    Args:
        theme_name: 题材名称，如 "固态电池"
        api_key: API 密钥
        base_url: API 地址
        model: 模型名称
        extra_hint: 额外提示（可选）

    Returns:
        dict: 解析后的产业链数据，包含 theme_name 和 chains 列表
    """
    # 第一步：联网搜索该题材的产业链信息 - 多维度搜索
    year = _current_year()
    search_queries = [
        # 产业链结构维度
        f"{theme_name} 产业链 A股 概念股 {year}",
        f"{theme_name} 龙头股 上市公司 {year}",
        f"{theme_name} 产业链 上游 下游 A股 最新",
        # 公司维度
        f"{theme_name} 机构调研 订单 公告 A股 近30天",
        f"{theme_name} 上市公司 业务 市占率 A股",
        # 市场维度
        f"{theme_name} 概念股 涨停 资金流入 近期",
        f"{theme_name} 行业分析 研报 券商 观点 {year}",
    ]
    
    all_snippets = []
    successful_queries = 0
    for q in search_queries:
        text = _search_web(q, max_results=5)
        if text:
            all_snippets.append(text)
            successful_queries += 1
    
    # 检查搜索结果质量
    if successful_queries == 0:
        _log.warning("题材分析搜索全部失败 (theme=%s)，将基于LLM知识生成", theme_name)
        search_context = "（暂无搜索结果，请基于知识回答）"
    elif successful_queries < 3:
        _log.warning("题材分析搜索结果较少 (theme=%s, %d/%d)，可能影响生成质量", 
                    theme_name, successful_queries, len(search_queries))
        search_context = "\n\n".join(all_snippets)
    else:
        search_context = "\n\n".join(all_snippets)

    # 第二步：LLM 分析
    client = _get_client(api_key, base_url)

    user_prompt = (
        f'【最新搜索结果】\n{search_context}\n\n'
        f'请分析"{theme_name}"题材的产业链结构。'
    )
    if extra_hint:
        user_prompt += f"\n\n额外提示：{extra_hint}"

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=16384,
        timeout=120,
    )

    choice = response.choices[0]

    # 检查是否被截断或拒绝
    if choice.finish_reason == "length":
        raise RuntimeError("模型输出被截断，请换更大 max_tokens 的模型或缩小题材范围后重试")
    if choice.finish_reason and choice.finish_reason != "stop":
        raise RuntimeError(f"模型返回异常，finish_reason={choice.finish_reason}")

    # 优先取 content，部分模型（如 reasoner 类）可能返回 reasoning_content
    msg = choice.message
    content = getattr(msg, "content", None)
    if not content:
        content = getattr(msg, "reasoning_content", None)
    if not content:
        raise RuntimeError("模型返回为空，可能是模型名称不支持或 API 限制")

    content = content.strip()

    # 从混合文本（推理过程+JSON）中提取纯 JSON
    json_text = _extract_json(content)

    try:
        return validate_theme_analysis(json.loads(json_text))
    except json.JSONDecodeError:
        # 尝试修复截断的 JSON
        repaired = _repair_truncated_json(json_text)
        try:
            return validate_theme_analysis(json.loads(repaired))
        except json.JSONDecodeError:
            raise RuntimeError(
                f"模型返回不是合法 JSON（修复也失败）。\n"
                f"提取片段（前 500 字符）：\n{json_text[:500]}\n\n"
                f"原始返回（前 300 字符）：\n{content[:300]}"
            )


def generate_hot_topics(
    api_key: str,
    base_url: str = "https://api.deepseek.com",
    model: str = "deepseek-v4-flash",
) -> list[dict]:
    """
    搜索 + LLM 汇总获取近期热点题材列表

    流程：
    1. 搜索多家财经网站的最新热点
    2. 将搜索结果作为上下文传给 LLM
    3. LLM 汇总输出题材列表

    Returns:
        list[dict]: [{"theme_name": "...", "summary": "..."}, ...]
    """
    # 第一步：联网搜索 - 多维度搜索策略
    year = _current_year()
    search_queries = [
        # 来源维度：主要财经网站
        f"site:eastmoney.com A股 概念板块 领涨 热点 {year}",
        f"site:10jqka.com.cn 题材 概念股 涨停 近一周 {year}",
        f"site:cls.cn 热点题材 概念 异动 A股 近一周 {year}",
        # 时间维度：近期热点
        "近期A股 涨停 概念板块 资金流入 龙头 近一周",
        f"A股 新概念 题材 爆发 {year} 近30天",
        # 类型维度：不同催化类型
        f"A股 政策催化 概念 题材 {year} 近期",
        f"A股 技术突破 概念 题材 {year} 近期",
        f"A股 涨价题材 概念 题材 {year} 近期",
        # 资金维度：资金流入
        "A股 资金流入 概念板块 龙头 近一周",
        # 事件维度：事件驱动
        f"A股 事件驱动 概念 题材 {year} 近期",
    ]
    
    all_snippets = []
    successful_queries = 0
    for q in search_queries:
        text = _search_web(q, max_results=6)
        if text:
            all_snippets.append(text)
            successful_queries += 1
    
    # 检查搜索结果质量
    if successful_queries == 0:
        _log.warning("所有搜索查询均失败，将基于LLM知识生成")
        search_context = "（暂无搜索结果，请基于知识回答）"
    elif successful_queries < 3:
        _log.warning("搜索结果较少 (%d/%d)，可能影响生成质量", successful_queries, len(search_queries))
        search_context = "\n\n".join(all_snippets)
    else:
        search_context = "\n\n".join(all_snippets)
    
    # 第二步：LLM 汇总
    client = _get_client(api_key, base_url)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": HOT_TOPICS_PROMPT},
            {"role": "user", "content": f"【最新搜索结果】\n{search_context}\n\n请基于以上搜索结果，列出当前最热门的10个A股题材。"},
        ],
        temperature=0.8,
        max_tokens=4096,
        timeout=120,
    )

    choice = response.choices[0]
    if choice.finish_reason == "length":
        raise RuntimeError("模型输出被截断，请重试")
    if choice.finish_reason and choice.finish_reason != "stop":
        raise RuntimeError(f"模型返回异常，finish_reason={choice.finish_reason}")

    msg = choice.message
    content = getattr(msg, "content", None)
    if not content:
        content = getattr(msg, "reasoning_content", None)
    if not content:
        raise RuntimeError("模型返回为空")

    json_text = _extract_json(content.strip())

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"模型返回不是合法 JSON。提取片段：\n{json_text[:500]}"
        )

    return validate_hot_topics(data.get("topics", []))


def generate_candidate_topics(
    raw_news: list[dict],
    api_key: str,
    base_url: str = "https://api.deepseek.com",
    model: str = "deepseek-v4-flash",
    time_start: str = "",
    time_end: str = "",
) -> list[dict]:
    """
    三阶段候选题材提取：
    1. 从首轮新闻中提取关键实体
    2. 基于实体执行第二轮深挖搜索
    3. 合并新闻后调用 LLM 生成候选热点题材（v2 细分题材导向）
    """
    if not raw_news:
        raise RuntimeError("没有可用于提取题材的新闻/资讯")

    # ---- 阶段 1：实体提取（规则 + AI 双路径） ----
    _log.info("阶段1: 从 %d 条新闻中提取关键实体", len(raw_news))
    entities = extract_entities_from_news(raw_news, max_entities=20)

    # 尝试 AI 辅助实体提取（轻量调用，失败不阻塞）
    try:
        news_payload = [
            {"news_id": item.get("news_id"), "title": item.get("title", ""), "summary": item.get("summary", "")}
            for item in raw_news[:30]
        ]
        client = _get_client(api_key, base_url)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": ENTITY_EXTRACTION_PROMPT},
                {"role": "user", "content": json.dumps(news_payload, ensure_ascii=False)},
            ],
            temperature=0.35,
            max_tokens=2048,
            timeout=120,
        )
        content = getattr(resp.choices[0].message, "content", None) or getattr(resp.choices[0].message, "reasoning_content", None)
        if content:
            ai_data = json.loads(_extract_json(content.strip()))
            ai_entities = ai_data.get("entities", [])
            # 合并 AI 实体到前面
            seen = set(entities)
            for e in ai_entities:
                if e not in seen and e not in _FINANCE_STOP:
                    entities.insert(0, e)
                    seen.add(e)
    except Exception as exc:
        _log.debug("AI 实体提取失败（使用规则结果）: %s", exc)

    entities = entities[:25]
    _log.info("提取到 %d 个关键实体: %s", len(entities), entities[:10])

    # ---- 阶段 2：第二轮深挖搜索 ----
    second_news = []
    if entities and time_start and time_end:
        try:
            from datetime import datetime as _dt
            start = _dt.fromisoformat(time_start.replace(" ", "T"))
            end = _dt.fromisoformat(time_end.replace(" ", "T"))
            second_news = second_round_search(entities, start, end, max_results_per_query=3)
            _log.info("阶段2: 第二轮搜索获得 %d 条新闻", len(second_news))
        except Exception as exc:
            _log.warning("第二轮搜索失败（继续使用首轮结果）: %s", exc)

    # ---- 合并新闻并构建 payload ----
    all_news = list(raw_news)
    existing_ids = {item.get("news_id") for item in all_news if item.get("news_id")}
    for item in second_news:
        if item.get("news_id") not in existing_ids:
            all_news.append(item)
            existing_ids.add(item.get("news_id"))

    news_payload = [
        {
            "news_id": item.get("news_id"),
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "source": item.get("source", ""),
            "published_at": item.get("published_at", ""),
            "fetched_at": item.get("fetched_at", ""),
            "search_query": item.get("search_query", ""),
            "category": item.get("category", ""),
        }
        for item in all_news
    ]
    valid_news_ids = {item["news_id"] for item in news_payload if item.get("news_id")}
    news_by_id = {item.get("news_id"): item for item in all_news if item.get("news_id")}

    # ---- 阶段 3：LLM 生成候选题材（v2 细分题材 Prompt） ----
    _log.info("阶段3: 用 %d 条新闻生成候选题材", len(news_payload))
    second_queries = [q.get("query", "") for q in build_entity_search_queries_stub(entities[:10])]

    client = _get_client(api_key, base_url)
    user_msg = (
        "【raw_news】\n" + json.dumps(news_payload, ensure_ascii=False)
        + "\n\n【key_entities】\n" + json.dumps(entities, ensure_ascii=False)
        + "\n\n请提取候选热点题材。优先从实体中挖掘细分题材/事件映射题材。"
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": CANDIDATE_TOPICS_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.55,
        max_tokens=8192,
        timeout=120,
    )

    choice = response.choices[0]
    if choice.finish_reason == "length":
        raise RuntimeError("模型输出被截断，请减少搜索范围或重试")
    if choice.finish_reason and choice.finish_reason != "stop":
        raise RuntimeError(f"模型返回异常，finish_reason={choice.finish_reason}")

    content = getattr(choice.message, "content", None) or getattr(choice.message, "reasoning_content", None)
    if not content:
        raise RuntimeError("模型返回为空")
    json_text = _extract_json(content.strip())
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"模型返回不是合法 JSON：{exc}") from exc

    topics = validate_candidate_topics(data.get("topics", []), valid_news_ids)

    # ---- 综合热度评分（新闻 + 行情数据） ----
    _log.info("获取行情数据以计算综合热度分...")
    try:
        from core.market_data import get_market_data_for_topic
    except ImportError:
        get_market_data_for_topic = None
        _log.warning("market_data 模块不可用，将使用纯新闻热度分")

    for topic in topics:
        evidence_news = [
            news_by_id[evidence["news_id"]]
            for evidence in topic.get("source_items", [])
            if evidence.get("news_id") in news_by_id
        ]
        topic_name = topic.get("topic_name", "")

        # 获取行情数据
        market_detail = None
        try:
            if get_market_data_for_topic:
                preliminary_stocks = topic.get("preliminary_related_stocks", [])
                if isinstance(preliminary_stocks, str):
                    import re
                    preliminary_stocks = [s.strip() for s in re.split(r"[,，、;\n]+", preliminary_stocks) if s.strip()]
                _, market_detail = get_market_data_for_topic(
                    topic_name,
                    preliminary_stocks if preliminary_stocks else None,
                )
        except Exception as exc:
            _log.debug("行情数据获取失败 topic=%s: %s", topic_name, exc)

        # 计算综合热度分（新闻 60% + 行情 40%）
        score, level, composite_detail = calculate_composite_heat(
            topic, evidence_news, market_detail,
        )
        topic["heat_score"] = score
        topic["heat_level"] = level
        # 保存行情明细供 UI 使用
        topic["market_detail"] = composite_detail
        # 记录第二轮查询
        topic["second_round_queries"] = second_queries
        # 自动补全 key_entities
        if not topic.get("key_entities"):
            topic["key_entities"] = entities[:8]

    return sorted(topics, key=lambda item: item["heat_score"], reverse=True)


# 财经停用词（使用共享常量）
_FINANCE_STOP = FINANCE_STOP_WORDS


def build_entity_search_queries_stub(entities: list[str]) -> list[dict]:
    """轻量 stub，供 generate_candidate_topics 内部使用"""
    from core.fetch_news import build_entity_search_queries
    return build_entity_search_queries(entities, max_queries=20)


def generate_chain_decomposition(
    topic: dict,
    evidence_items: list[dict],
    api_key: str,
    base_url: str = "https://api.deepseek.com",
    model: str = "deepseek-v4-flash",
) -> dict:
    """阶段一：只做产业链拆解，不输出股票"""
    payload = {
        "topic": topic,
        "evidence_items": _compact_evidence(evidence_items),
    }
    client = _get_client(api_key, base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": CHAIN_DECOMPOSITION_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.45,
        max_tokens=4096,
        timeout=120,
    )
    data = _load_json_response(response, "产业链拆解")
    return validate_chain_decomposition(data)


def generate_stock_mapping(
    topic: dict,
    chain_data: dict,
    evidence_items: list[dict],
    api_key: str,
    base_url: str = "https://api.deepseek.com",
    model: str = "deepseek-v4-flash",
) -> list[dict]:
    """阶段二：基于产业链节点分批映射 A 股公司，避免大 JSON 被截断。"""
    chain_nodes = chain_data.get("chain_nodes", [])
    if not chain_nodes:
        raise RuntimeError("个股映射缺少产业链节点")

    all_stocks: list[dict] = []
    errors: list[str] = []
    for batch in _chunk_list(chain_nodes, 3):
        batch_chain = {**chain_data, "chain_nodes": batch}
        try:
            all_stocks.extend(
                _generate_stock_mapping_batch(topic, batch_chain, evidence_items, api_key, base_url, model)
            )
        except RuntimeError as exc:
            # 单批仍被截断时降级为单节点，尽量保住草稿可用性。
            if "截断" not in str(exc) and "不是合法 JSON" not in str(exc):
                errors.append(str(exc))
                continue
            for node in batch:
                single_chain = {**chain_data, "chain_nodes": [node]}
                try:
                    all_stocks.extend(
                        _generate_stock_mapping_batch(topic, single_chain, evidence_items, api_key, base_url, model)
                    )
                except RuntimeError as node_exc:
                    errors.append(str(node_exc))

    all_stocks = _dedupe_stock_rows(all_stocks)
    if not all_stocks:
        detail = "；".join(errors[:3]) if errors else "未生成有效 A 股公司"
        raise RuntimeError(f"个股映射失败：{detail}")
    return all_stocks


def _generate_stock_mapping_batch(
    topic: dict,
    chain_data: dict,
    evidence_items: list[dict],
    api_key: str,
    base_url: str,
    model: str,
) -> list[dict]:
    """映射一小批产业链节点。"""
    payload = {
        "topic": topic,
        "chain_decomposition": chain_data,
        "evidence_items": _compact_evidence(evidence_items),
        "output_limits": {
            "max_stocks_per_node": 3,
            "max_total_stocks": 8,
            "keep_text_brief": True,
        },
    }
    client = _get_client(api_key, base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": STOCK_MAPPING_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.35,
        max_tokens=6144,
        timeout=120,
    )
    data = _load_json_response(response, "个股映射")
    return validate_stock_mapping(data, chain_data.get("chain_nodes", []))


def _chunk_list(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _dedupe_stock_rows(stocks: list[dict]) -> list[dict]:
    """按 股票+节点 去重，允许同一公司出现在不同产业链节点。"""
    deduped = []
    seen = set()
    for stock in stocks:
        key = (
            stock.get("stock_code", ""),
            stock.get("level1", ""),
            stock.get("level2", ""),
            stock.get("level3", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(stock)
    return deduped


def generate_analysis_draft(
    topic: dict,
    evidence_items: list[dict],
    api_key: str,
    base_url: str = "https://api.deepseek.com",
    model: str = "deepseek-v4-flash",
) -> dict:
    """生成两阶段题材深度分析草稿"""
    chain_data = generate_chain_decomposition(topic, evidence_items, api_key, base_url, model)
    stocks = generate_stock_mapping(topic, chain_data, evidence_items, api_key, base_url, model)
    topic_name = topic.get("topic_name") or topic.get("topic_name", "") or topic.get("theme_name", "")
    return {
        "topic_name": topic_name,
        "topic_id": topic.get("topic_id"),
        "theme_definition": chain_data.get("theme_definition", ""),
        "trigger_event": chain_data.get("trigger_event") or topic.get("trigger_event", ""),
        "core_logic": chain_data.get("core_logic") or topic.get("core_logic", ""),
        "industry_scope": chain_data.get("industry_scope", ""),
        "excluded_scope": chain_data.get("excluded_scope", ""),
        "chain_nodes": chain_data.get("chain_nodes", []),
        "stocks": stocks,
    }


def _compact_evidence(evidence_items: list[dict]) -> list[dict]:
    return [
        {
            "news_id": item.get("news_id", ""),
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "source": item.get("source", ""),
            "url": item.get("url", ""),
            "reason": item.get("reason", ""),
        }
        for item in evidence_items[:10]
    ]


def _load_json_response(response, task_name: str) -> dict:
    choice = response.choices[0]
    if choice.finish_reason == "length":
        raise RuntimeError(f"{task_name}输出被截断，请重试")
    if choice.finish_reason and choice.finish_reason != "stop":
        raise RuntimeError(f"{task_name}模型返回异常，finish_reason={choice.finish_reason}")
    content = getattr(choice.message, "content", None) or getattr(choice.message, "reasoning_content", None)
    if not content:
        raise RuntimeError(f"{task_name}模型返回为空")
    json_text = _extract_json(content.strip())
    try:
        return json.loads(json_text)
    except json.JSONDecodeError as exc:
        repaired = _repair_truncated_json(json_text)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            raise RuntimeError(f"{task_name}模型返回不是合法 JSON：{exc}") from exc


def generate_fermentation_observations(
    raw_news: list[dict],
    api_key: str,
    base_url: str = "https://api.deepseek.com",
    model: str = "deepseek-v4-flash",
    existing_themes: list[str] | None = None,
) -> list[dict]:
    """基于近期资讯生成发酵观察线索，并用规则分重新校准。"""
    if not raw_news:
        raise RuntimeError("没有可用于发酵观察的资讯")

    news_payload = [
        {
            "news_id": item.get("news_id", ""),
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "source": item.get("source", ""),
            "url": item.get("url", ""),
            "published_at": item.get("published_at", ""),
            "fetched_at": item.get("fetched_at", ""),
            "search_query": item.get("search_query", ""),
            "category": item.get("category", ""),
        }
        for item in raw_news[:40]
    ]
    valid_news_ids = {str(item.get("news_id", "")).strip() for item in raw_news if item.get("news_id")}
    news_by_id = {str(item.get("news_id", "")).strip(): item for item in raw_news if item.get("news_id")}
    payload = {
        "existing_themes": existing_themes or [],
        "raw_news": news_payload,
    }

    client = _get_client(api_key, base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": FERMENTATION_OBSERVATION_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.5,
        max_tokens=8192,
        timeout=120,
    )
    data = _load_json_response(response, "发酵观察")
    observations = validate_fermentation_observations(data.get("observations", []), valid_news_ids)

    for observation in observations:
        evidence_items = [
            news_by_id[item["news_id"]]
            for item in observation.get("source_items", [])
            if item.get("news_id") in news_by_id
        ]
        score, status = calculate_fermentation_score(observation, evidence_items)
        observation["fermentation_score"] = score
        observation["status"] = status
        observation["evidence_count"] = len(evidence_items)

    return sorted(observations, key=lambda item: item["fermentation_score"], reverse=True)


def generate_predictions(
    api_key: str,
    base_url: str = "https://api.deepseek.com",
    model: str = "deepseek-v4-flash",
    existing_themes: list[str] | None = None,
) -> list[dict]:
    """搜索早期信号并生成题材发酵预测"""
    year = _current_year()
    queries = [
        # 政策维度
        f"A股 新概念 政策 新兴 题材 {year} 近30天",
        f"site:cls.cn 政策催化 新题材 A股 {year}",
        # 资金维度
        "A股 异动 资金流入 新方向 概念 近一周",
        "A股 资金流入 概念板块 龙头 近一周",
        # 技术维度
        f"A股 技术突破 新材料 新赛道 {year} 近30天",
        f"A股 技术突破 概念 题材 {year} 近期",
        # 市场维度
        "A股 涨停 扩散 产业链 题材 发酵 近一周",
        "A股 涨停潮 概念板块 异动 近一周",
        # 事件维度
        f"A股 事件驱动 概念 题材 {year} 近期",
        "A股 概念板块 异动 资金流入 近一周",
    ]
    
    all_snippets = []
    successful_queries = 0
    for q in queries:
        text = _search_web(q, max_results=5)
        if text:
            all_snippets.append(text)
            successful_queries += 1
    
    # 检查搜索结果质量
    if successful_queries == 0:
        _log.warning("预测搜索全部失败，将基于LLM知识生成")
        search_context = "（暂无搜索结果）"
    elif successful_queries < 3:
        _log.warning("预测搜索结果较少 (%d/%d)，可能影响生成质量", successful_queries, len(queries))
        search_context = "\n\n".join(all_snippets)
    else:
        search_context = "\n\n".join(all_snippets)

    existing_str = "、".join(existing_themes or []) if existing_themes else "暂无"
    client = _get_client(api_key, base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": PREDICTIONS_PROMPT},
            {"role": "user", "content": f"【已有题材库】{existing_str}\n\n【最新搜索信号】\n{search_context}\n\n请基于以上信息，预测可能发酵的题材方向。"},
        ],
        temperature=0.65,
        max_tokens=4096,
        timeout=120,
    )

    choice = response.choices[0]
    if choice.finish_reason == "length":
        raise RuntimeError("模型输出被截断，请重试")
    if choice.finish_reason and choice.finish_reason != "stop":
        raise RuntimeError(f"模型返回异常，finish_reason={choice.finish_reason}")

    content = getattr(choice.message, "content", None) or getattr(choice.message, "reasoning_content", None)
    if not content:
        raise RuntimeError("模型返回为空")
    json_text = _extract_json(content.strip())
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"模型返回不是合法 JSON：{exc}") from exc
    return validate_predictions(data.get("predictions", []))
