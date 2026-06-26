"""
发酵观察页：识别尚未成为主流热点、但出现升温迹象的题材线索。
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from datetime import time as dt_time

import streamlit as st

import core.database as db
import tasks.task_manager as tm
from core.ai_client import generate_analysis_draft, generate_fermentation_observations, load_api_config
from config import DATA_DIR, FERMENTATION_DEFAULTS, get_logger
from core.fetch_news import SEARCH_CATEGORIES, TIME_RANGE_OPTIONS, fetch_news
from ui_components import badge, chips, esc, field_html, level_tone, metric_strip, page_header, score_tone

_log = get_logger("fermentation")

_OBSERVATION_FILE = os.path.join(DATA_DIR, "fermentation_observations.json")
_CACHE_TTL_HOURS = 6


def _load_cached() -> tuple[list[dict], str]:
    try:
        with open(_OBSERVATION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("observations", []), data.get("fetched_at", "")
    except (FileNotFoundError, json.JSONDecodeError):
        _log.debug("发酵观察缓存文件 %s 不存在或损坏，跳过加载", _OBSERVATION_FILE)
        return [], ""


def _save_cache(observations: list[dict]) -> None:
    try:
        with open(_OBSERVATION_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "observations": observations,
                    "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
    except OSError as exc:
        _log.warning("保存发酵观察缓存失败: %s", exc)


def _cache_age_text(timestamp: str) -> tuple[str, bool]:
    if not timestamp:
        return "", False
    try:
        fetched_at = datetime.strptime(timestamp, "%Y-%m-%d %H:%M")
    except ValueError:
        return timestamp, True
    age = datetime.now() - fetched_at
    hours = max(0, int(age.total_seconds() // 3600))
    return f"{timestamp}，约 {hours} 小时前", age > timedelta(hours=_CACHE_TTL_HOURS)


def _as_text(value, fallback: str = "-") -> str:
    if isinstance(value, list):
        text = "、".join(str(item).strip() for item in value if str(item).strip())
        return text or fallback
    text = str(value or "").strip()
    return text or fallback


def render():
    cached_observations, cached_time = _load_cached()
    meta = None
    if cached_time:
        age_text, expired = _cache_age_text(cached_time)
        meta = f"{'缓存过期' if expired else '最近更新'}：{age_text}"

    page_header(
        "发酵观察",
        "从近期财经新闻、公告、研报摘要和公开资讯中识别尚未大面积扩散的潜在题材线索。",
        eyebrow="Potential Theme Pool",
        meta=meta,
    )

    api_key, base_url, model = load_api_config(st.session_state.get)
    if not api_key:
        st.warning("未配置 API Key，请先到「AI 生成」页保存配置")
        return

    if "fermentation_observations" not in st.session_state and cached_observations:
        st.session_state["fermentation_observations"] = cached_observations

    _check_ferm_task()
    _check_ferm_draft_task()

    _render_search_config(api_key, base_url, model, has_cache=bool(cached_observations))
    _render_observations(api_key, base_url, model)


def _render_search_config(api_key: str, base_url: str, model: str, has_cache: bool):
    """一键发现模式 + 高级配置（折叠）"""

    # ---- 缓存状态指示 ----
    if has_cache:
        cached_observations, cached_time = _load_cached()
        if cached_time:
            age_text, expired = _cache_age_text(cached_time)
            if expired:
                st.warning(f"缓存已过期（{age_text}），建议重新扫描")
            else:
                st.info(f"已缓存观察线索（{age_text}）")

    # ---- 一键发现模式 ----
    col_btn, col_adv = st.columns([2.6, 1])
    with col_btn:
        submitted = st.button(
            "一键发现发酵题材",
            type="primary",
            width="stretch",
            disabled=tm.get("ferm_search") is not None,
        )
    with col_adv:
        show_adv = st.checkbox("⚙️ 高级配置", key="ferm_show_advanced",
                                value=st.session_state.get("ferm_show_advanced", False))

    if not show_adv:
        st.caption(
            f"自动扫描全市场热点与科技成长方向（{FERMENTATION_DEFAULTS['time_range']}），"
            "识别尚未大面积扩散、但出现升温迹象的潜在题材线索。预计耗时约 30-60 秒。"
        )

    if submitted:
        _submit_one_click_ferm(api_key, base_url, model)
        return

    # ---- 高级配置（展开） ----
    if show_adv:
        st.divider()
        st.markdown('<div class="field-label" style="margin-bottom:8px;">高级观察参数</div>',
                    unsafe_allow_html=True)
        c1, c2 = st.columns([1, 2])
        with c1:
            time_range = st.selectbox("时间范围", TIME_RANGE_OPTIONS,
                                       index=TIME_RANGE_OPTIONS.index(FERMENTATION_DEFAULTS["time_range"]))
        with c2:
            selected_categories = st.multiselect(
                "搜索范围", SEARCH_CATEGORIES,
                default=FERMENTATION_DEFAULTS["search_scopes"],
                help="复用热点题材资讯抓取模板。",
            )

        custom_keywords = ""
        if "自定义关键词" in selected_categories:
            custom_keywords = st.text_area(
                "自定义关键词",
                placeholder="每行或用逗号分隔，例如：新型储能、端侧AI、先进封装",
                height=72,
            )

        custom_start = custom_end = None
        if time_range == "自定义":
            d1, t1, d2, t2 = st.columns(4)
            start_date = d1.date_input("开始日期", value=datetime.now().date())
            start_time = t1.time_input("开始时间", value=dt_time(9, 30))
            end_date = d2.date_input("结束日期", value=datetime.now().date())
            end_time = t2.time_input("结束时间", value=datetime.now().time().replace(second=0, microsecond=0))
            custom_start = datetime.combine(start_date, start_time)
            custom_end = datetime.combine(end_date, end_time)

        c3, c4 = st.columns([1, 2])
        max_results = c3.slider("每个 query 结果数", min_value=3, max_value=10,
                                 value=FERMENTATION_DEFAULTS["results_per_query"])
        adv_submitted = c4.button("搜索并生成观察线索", type="primary", width="stretch",
                                   disabled=tm.get("ferm_search") is not None)

        if not adv_submitted:
            return
        if not selected_categories:
            st.warning("请至少选择一个搜索范围")
            return
        if selected_categories == ["自定义关键词"] and not custom_keywords.strip():
            st.warning("选择自定义关键词时，请输入至少一个关键词")
            return

        ok = tm.submit(
            "ferm_search",
            _run_ferm_search,
            api_key, base_url, model,
            time_range, selected_categories, custom_keywords,
            custom_start, custom_end, max_results,
        )
        if ok:
            st.rerun()
        else:
            st.warning("发酵观察任务已在运行中，请等待完成")


def _submit_one_click_ferm(api_key: str, base_url: str, model: str):
    """一键发现：使用智能默认值直接提交后台任务"""
    time_range = FERMENTATION_DEFAULTS["time_range"]
    selected_categories = FERMENTATION_DEFAULTS["search_scopes"]
    max_results = FERMENTATION_DEFAULTS["results_per_query"]

    ok = tm.submit(
        "ferm_search",
        _run_ferm_search,
        api_key, base_url, model,
        time_range, selected_categories, "",
        None, None, max_results,
    )
    if ok:
        st.rerun()
    else:
        st.warning("发酵观察任务已在运行中，请等待完成")


def _render_observations(api_key: str, base_url: str, model: str):
    observations = st.session_state.get("fermentation_observations", [])
    observations = [item for item in observations if item.get("watch_status") != "ignored"]
    if not observations:
        st.info("请先展开观察配置并生成观察线索。")
        return

    watching_count = len([item for item in observations if item.get("watch_status") == "watching"])
    avg_score = round(sum(item.get("fermentation_score", 0) for item in observations) / len(observations))
    metric_strip([
        ("观察线索", len(observations), "未忽略线索"),
        ("观察池", watching_count, "已标记跟踪"),
        ("平均发酵分", avg_score, "规则辅助评分"),
    ])
    st.caption("本页只提供观察线索，不提供买卖、目标价或仓位建议。")

    for rank, observation in enumerate(observations, start=1):
        _render_observation_card(rank, observation, api_key, base_url, model)


def _render_observation_card(rank: int, observation: dict, api_key: str, base_url: str, model: str):
    name = observation.get("topic_name", "")
    score = observation.get("fermentation_score", 0)
    status = observation.get("status", "等待确认")
    evidence_count = observation.get("evidence_count", 0)
    source_items = observation.get("source_items", [])

    with st.container(border=True):
        left, middle, right = st.columns([0.8, 4.4, 1.45])
        with left:
            st.markdown(f'<div class="field-label">排名</div><div class="metric-value">{rank}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="score-pill">{score}</div>', unsafe_allow_html=True)
            st.markdown(badge(status, level_tone(status)), unsafe_allow_html=True)

        with middle:
            st.markdown(f'<div class="card-title">{esc(name)}</div>', unsafe_allow_html=True)
            st.markdown(
                badge("观察线索", score_tone(score))
                + badge(f"证据 {evidence_count}", "blue")
                + (badge("已加入观察池", "green") if observation.get("watch_status") == "watching" else ""),
                unsafe_allow_html=True,
            )
            st.markdown(field_html("触发线索", observation.get("trigger_clues")), unsafe_allow_html=True)
            st.markdown(field_html("关注理由", observation.get("why_watch")), unsafe_allow_html=True)
            st.markdown(field_html("来源摘要", observation.get("source_summary")), unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            c1.markdown('<div class="field-label">相关关键词</div>' + chips(observation.get("related_keywords")), unsafe_allow_html=True)
            c2.markdown('<div class="field-label">建议拆解方向</div>' + chips(observation.get("suggested_chains")), unsafe_allow_html=True)
            st.markdown(field_html("后续观察信号", observation.get("next_signals_to_watch")), unsafe_allow_html=True)
            st.markdown(field_html("风险提示", observation.get("risk_note")), unsafe_allow_html=True)

        with right:
            if st.button("加入观察池", key=f"watch_{rank}_{name}", width="stretch"):
                observation["watch_status"] = "watching"
                _persist_current_observations()
                st.success("已加入观察池")
                st.rerun()
            if st.button("生成产业链草稿", key=f"draft_obs_{rank}_{name}", type="primary", width="stretch"):
                _generate_draft_from_observation(observation, api_key, base_url, model)
            if st.button("忽略", key=f"ignore_{rank}_{name}", width="stretch"):
                observation["watch_status"] = "ignored"
                _persist_current_observations()
                st.rerun()

        if source_items:
            with st.expander(f"查看证据 ({len(source_items)})"):
                _render_evidence(source_items)


def _persist_current_observations() -> None:
    observations = st.session_state.get("fermentation_observations", [])
    st.session_state["fermentation_observations"] = observations
    _save_cache(observations)


def _render_evidence(source_items: list[dict]) -> None:
    evidence = db.get_raw_news_by_ids([item.get("news_id", "") for item in source_items])
    reasons = {item.get("news_id"): item for item in source_items}
    if not evidence:
        st.info("本地未找到对应证据，请重新生成观察线索")
        return
    for item in evidence:
        reason = reasons.get(item.get("news_id"), {})
        st.markdown(f"**{item.get('title') or '无标题'}**")
        st.caption(
            f"{item.get('source') or '未知来源'} · "
            f"相关度 {reason.get('relevance_score') or '-'} · "
            f"{reason.get('reason') or ''}"
        )
        if item.get("summary"):
            st.write(item["summary"])
        if item.get("url"):
            st.markdown(f"[打开来源]({item['url']})")
        st.divider()


def _generate_draft_from_observation(observation: dict, api_key: str, base_url: str, model: str) -> None:
    """提交后台草稿生成任务"""
    topic_name = observation.get("topic_name", "")
    # 用 topic_name 的 hash 做 id，避免特殊字符
    task_id = f"ferm_draft_{abs(hash(topic_name)) % 100000}"
    ok = tm.submit(task_id, _run_ferm_draft_gen, observation, api_key, base_url, model)
    if ok:
        st.rerun()
    else:
        st.warning("该题材草稿正在生成中")


# ---- 后台任务 ----

_FERM_TASK = "ferm_search"
_FERM_DRAFT_PREFIX = "ferm_draft_"


def _run_ferm_search(
    api_key: str, base_url: str, model: str,
    time_range: str, selected_categories: list[str], custom_keywords: str,
    custom_start, custom_end, max_results: int,
) -> dict:
    """后台线程：搜索 + 发酵观察生成 + 缓存"""
    tm.update_progress(_FERM_TASK, 0.15, "搜索近期资讯…")
    raw_news = fetch_news(
        time_range=time_range,
        selected_categories=selected_categories,
        custom_keywords=custom_keywords,
        custom_start=custom_start,
        custom_end=custom_end,
        max_results_per_query=max_results,
    )
    db.save_raw_news(raw_news)

    if not raw_news:
        return {"raw_count": 0, "obs_count": 0, "msg": "没有搜索到可用结果"}

    tm.update_progress(_FERM_TASK, 0.45, "生成发酵观察…")
    observations = generate_fermentation_observations(
        raw_news=raw_news,
        api_key=api_key,
        base_url=base_url,
        model=model,
        existing_themes=db.get_distinct_themes(),
    )

    tm.update_progress(_FERM_TASK, 0.85, "保存缓存…")
    _save_cache(observations)
    return {"raw_count": len(raw_news), "obs_count": len(observations), "observations": observations, "msg": ""}


def _check_ferm_task() -> None:
    """检查发酵观察后台任务，完成时展示结果。展示步骤进度条。"""
    task = tm.get(_FERM_TASK)
    if task is None:
        return

    if task["status"] == "running":
        progress_area = st.empty()
        status_area = st.empty()
        p = task.get("progress", 0)
        msg = task.get("progress_msg", "")

        step_labels = [
            (0.20, "🔍 搜索财经资讯…", "正在抓取近期热点新闻"),
            (0.50, "🤖 AI 生成发酵观察…", "大模型识别潜在升温题材"),
            (0.85, "📊 分析证据链…", "关联新闻证据并评分"),
            (0.95, "✅ 完成！", "正在整理结果"),
        ]

        current_label = msg
        for threshold, label, _detail in step_labels:
            if p >= threshold:
                current_label = label

        status_area.markdown(
            f'<div style="text-align:center;padding:16px 0;">'
            f'<div style="font-size:1.1rem;font-weight:600;margin-bottom:4px;">{current_label}</div>'
            f'<div style="color:#9BA3B0;font-size:0.85rem;">{msg}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        progress_area.progress(p)

        while True:
            task = tm.get(_FERM_TASK)
            if task is None or task["status"] != "running":
                break
            p = task.get("progress", 0)
            msg = task.get("progress_msg", "")
            for threshold, label, _detail in step_labels:
                if p >= threshold:
                    current_label = label
            status_area.markdown(
                f'<div style="text-align:center;padding:16px 0;">'
                f'<div style="font-size:1.1rem;font-weight:600;margin-bottom:4px;">{current_label}</div>'
                f'<div style="color:#9BA3B0;font-size:0.85rem;">{msg}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            progress_area.progress(p)
            time.sleep(1.5)
        status_area.empty()
        progress_area.empty()
        st.rerun()

    if task["status"] == "completed":
        result = task["result"] or {}
        msg = result.get("msg", "")
        if msg:
            st.warning(msg)
        else:
            observations = result.get("observations", [])
            st.session_state["fermentation_observations"] = observations
            st.success(f"已抓取 {result['raw_count']} 条资讯，生成 {result['obs_count']} 条观察线索")
        tm.clear(_FERM_TASK)

    elif task["status"] == "failed":
        st.error(f"发酵观察生成失败：{task['error']}")
        if st.button("重试", key="retry_ferm_search"):
            tm.clear(_FERM_TASK)
            st.rerun()


def _run_ferm_draft_gen(observation: dict, api_key: str, base_url: str, model: str) -> dict:
    """后台线程：从发酵观察生成草稿"""
    topic_name = observation.get("topic_name", "")
    task_id = f"{_FERM_DRAFT_PREFIX}{abs(hash(topic_name)) % 100000}"

    tm.update_progress(task_id, 0.15, "读取证据…")
    evidence = db.get_raw_news_by_ids([
        item.get("news_id", "")
        for item in observation.get("source_items", [])
    ])

    topic = {
        "topic_id": None,
        "topic_name": topic_name,
        "trigger_event": _as_text(observation.get("trigger_clues"), ""),
        "core_logic": observation.get("why_watch", ""),
        "evidence_summary": observation.get("source_summary", ""),
        "related_keywords": observation.get("related_keywords", []),
        "preliminary_related_stocks": observation.get("preliminary_related_stocks", []),
        "suggested_chains": observation.get("suggested_chains", []),
    }

    tm.update_progress(task_id, 0.35, "生成产业链拆解…")
    draft = generate_analysis_draft(topic, evidence, api_key, base_url, model)

    tm.update_progress(task_id, 0.8, "保存草稿…")
    draft_id = db.create_analysis_draft(None, topic_name, draft)
    return {"draft_id": draft_id, "topic_name": topic_name}


def _check_ferm_draft_task() -> None:
    """检查发酵草稿后台任务"""
    all_tasks = tm.get_all()
    for tid, task in all_tasks.items():
        if not tid.startswith(_FERM_DRAFT_PREFIX):
            continue
        if task["status"] == "running":
            status_area = st.empty()
            progress_area = st.empty()
            while True:
                task = tm.get(tid)
                if task is None or task["status"] != "running":
                    break
                p = task.get("progress", 0)
                msg = task.get("progress_msg", "")
                status_area.spinner(f"正在生成草稿… {msg}")
                progress_area.progress(p, text=f"{msg} ({int(p * 100)}%)")
                time.sleep(1.5)
            status_area.empty()
            progress_area.empty()
            st.rerun()
        if task["status"] == "completed":
            result = task["result"] or {}
            tm.clear(tid)
            st.session_state.current_page = "分析草稿"
            st.session_state["active_draft_id"] = result["draft_id"]
            st.success(f"已生成「{result['topic_name']}」分析草稿")
            st.rerun()
        if task["status"] == "failed":
            st.error(f"草稿生成失败：{task['error']}")
            if st.button("重试", key=f"retry_{tid}"):
                tm.clear(tid)
                st.rerun()
