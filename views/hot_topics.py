"""
热点题材页 — 自动搜索资讯并提取候选题材。
"""
from __future__ import annotations

import time
from datetime import datetime
from datetime import time as dt_time

import streamlit as st

import core.database as db
import tasks.task_manager as tm
from core.ai_client import generate_analysis_draft, generate_candidate_topics, load_api_config
from config import DISCOVERY_DEFAULTS, get_logger
from core.fetch_news import SEARCH_CATEGORIES, TIME_RANGE_OPTIONS, fetch_news
from ui_components import (
    badge, chips, esc, field_html, level_tone, metric_strip, page_header,
    score_tone, market_pct_badge, market_flow_badge, limit_up_badge,
    market_indicators_html, serenity_dimension_badge,
)

_log = get_logger("hot_topics")


def render():
    page_header(
        "热点题材",
        "从近期财经资讯中提取已经明显升温、适合继续做产业链拆解的候选题材。",
        eyebrow="Signal Discovery",
        meta="含行情验证",
    )

    api_key, base_url, model = load_api_config(st.session_state.get)
    if not api_key:
        st.warning("未配置 API Key，请先到「AI 生成」页保存配置")
        return

    # 检查后台任务是否完成
    _check_hot_search_task()
    _check_draft_task()

    _render_search_config(api_key, base_url, model)
    _render_candidate_topics(api_key, base_url, model)


def _render_search_config(api_key: str, base_url: str, model: str):
    """一键发现模式 + 高级配置（折叠）"""
    has_existing = bool(db.get_hot_topic_candidates())

    # ---- 一键发现模式 ----
    col_btn, col_adv = st.columns([2.6, 1])
    with col_btn:
        submitted = st.button(
            "一键发现热点题材",
            type="primary",
            width="stretch",
            disabled=tm.get("hot_search") is not None,
        )
    with col_adv:
        show_adv = st.checkbox("⚙️ 高级配置", key="hot_show_advanced",
                                value=st.session_state.get("hot_show_advanced", False))

    if not show_adv:
        st.caption(
            f"自动扫描近期全市场热点（{DISCOVERY_DEFAULTS['time_range']}），"
            "结合行情数据验证，发现最具投资价值的题材方向。预计耗时约 30-60 秒。"
        )
    if submitted:
        _submit_one_click(api_key, base_url, model)
        return

    # ---- 高级配置（展开） ----
    if show_adv:
        st.divider()
        st.markdown('<div class="field-label" style="margin-bottom:8px;">高级搜索参数</div>',
                    unsafe_allow_html=True)
        c1, c2 = st.columns([1, 2])
        with c1:
            time_range = st.selectbox("时间范围", TIME_RANGE_OPTIONS,
                                       index=TIME_RANGE_OPTIONS.index(DISCOVERY_DEFAULTS["time_range"]))
        with c2:
            selected_categories = st.multiselect(
                "搜索范围", SEARCH_CATEGORIES,
                default=DISCOVERY_DEFAULTS["search_scopes"],
                help="可多选。每个范围对应一组 query 模板。",
            )

        custom_keywords = ""
        if "自定义关键词" in selected_categories:
            custom_keywords = st.text_area(
                "自定义关键词",
                placeholder="每行或用逗号分隔，例如：HBM、液冷服务器、低空经济",
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
                                 value=DISCOVERY_DEFAULTS["results_per_query"])
        adv_submitted = c4.button("搜索并提取候选题材", type="primary", width="stretch",
                                   disabled=tm.get("hot_search") is not None)

        if not adv_submitted:
            return
        if not selected_categories:
            st.warning("请至少选择一个搜索范围")
            return
        if selected_categories == ["自定义关键词"] and not custom_keywords.strip():
            st.warning("选择自定义关键词时，请输入至少一个关键词")
            return

        ok = tm.submit(
            "hot_search",
            _run_hot_search,
            api_key, base_url, model,
            time_range, selected_categories, custom_keywords,
            custom_start, custom_end, max_results,
        )
        if ok:
            st.rerun()
        else:
            st.warning("搜索任务已在运行中，请等待完成")


def _submit_one_click(api_key: str, base_url: str, model: str):
    """一键发现：使用智能默认值直接提交后台任务"""
    time_range = DISCOVERY_DEFAULTS["time_range"]
    selected_categories = DISCOVERY_DEFAULTS["search_scopes"]
    max_results = DISCOVERY_DEFAULTS["results_per_query"]

    ok = tm.submit(
        "hot_search",
        _run_hot_search,
        api_key, base_url, model,
        time_range, selected_categories, "",
        None, None, max_results,
    )
    if ok:
        st.rerun()
    else:
        st.warning("搜索任务已在运行中，请等待完成")


def _render_candidate_topics(api_key: str, base_url: str, model: str):
    candidates = db.get_hot_topic_candidates()
    if not candidates:
        st.info("请先展开搜索配置并提取候选题材。")
        return

    metric_strip([
        ("候选题材", len(candidates), "按热度分排序"),
        ("高热度", len([x for x in candidates if (x.get("heat_score") or 0) >= 80]), "规则评分 >= 80"),
        ("待拆解", len([x for x in candidates if x.get("should_import")]), "AI 建议继续分析"),
    ])
    st.caption("综合热度分 = 新闻热度分(60%) + 行情热度分(40%)，含板块涨跌幅、资金流向、涨停关联度验证。")

    existing = set(db.get_distinct_themes())
    for rank, topic in enumerate(candidates, start=1):
        _render_topic_card(rank, topic, topic["topic_name"] in existing, api_key, base_url, model)


def _render_topic_card(rank: int, topic: dict, is_imported: bool, api_key: str, base_url: str, model: str):
    heat_score = topic.get("heat_score") or 0
    heat_level = topic.get("heat_level") or "低"
    topic_id = topic["topic_id"]
    evidence_count = topic.get("evidence_count", 0)

    with st.container(border=True):
        left, middle, right = st.columns([0.8, 4.4, 1.35])
        with left:
            st.markdown(f'<div class="field-label">排名</div><div class="metric-value">{rank}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="score-pill">{heat_score}</div>', unsafe_allow_html=True)
            st.markdown(badge(f"热度{heat_level}", level_tone(heat_level)), unsafe_allow_html=True)

        with middle:
            # 标题 + parent_theme
            parent = topic.get("parent_theme") or ""
            title_html = f'<div class="card-title">{esc(topic["topic_name"])}</div>'
            if parent:
                title_html += f'<div style="font-size:0.78rem;color:#9BA3B0;margin-top:2px;">📂 {esc(parent)}</div>'
            st.markdown(title_html, unsafe_allow_html=True)

            # 行情指标条（新增）
            market_html = market_indicators_html(topic.get("market_detail"))
            if market_html:
                st.markdown(market_html, unsafe_allow_html=True)

            # 标签行
            tags = [
                badge(topic.get("topic_type") or "细分题材", "blue"),
                badge(f"细分 {topic.get('specificity_score') or '-'}", score_tone(topic.get("specificity_score") or 50)),
                badge(f"新鲜 {topic.get('novelty_score') or '-'}", score_tone(topic.get("novelty_score") or 50)),
                badge(f"证据 {evidence_count}", "slate"),
            ]
            # Serenity 产业链位置徽章（由 AI 分析自动填充）
            chain_pos = topic.get("chain_position") or topic.get("bottleneck_position")
            if chain_pos:
                tags.append(badge(f"产业链 {chain_pos}", "orange"))
            if is_imported:
                tags.append(badge("已入库", "green"))
            st.markdown("".join(tags), unsafe_allow_html=True)

            # 关键实体
            entities = topic.get("key_entities") or []
            if isinstance(entities, str):
                entities = [e.strip() for e in entities.replace("、", ",").split(",") if e.strip()]
            if entities:
                st.markdown('<div class="field-label">关键实体</div>' + chips(entities[:10]), unsafe_allow_html=True)

            st.markdown(field_html("触发事件", topic.get("trigger_event")), unsafe_allow_html=True)
            st.markdown(field_html("核心逻辑", topic.get("core_logic")), unsafe_allow_html=True)
            st.markdown(field_html("依据摘要", topic.get("evidence_summary")), unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            c1.markdown('<div class="field-label">建议拆解方向</div>' + chips(topic.get("suggested_chains")), unsafe_allow_html=True)
            c2.markdown('<div class="field-label">初步相关个股</div>' + chips(topic.get("preliminary_related_stocks")), unsafe_allow_html=True)

            # Serenity 四维分析快速提示
            serenity_hints = _build_serenity_hints(topic)
            if serenity_hints:
                st.markdown(serenity_hints, unsafe_allow_html=True)

            st.markdown(field_html("风险提示", topic.get("risk_note")), unsafe_allow_html=True)

        with right:
            if st.button(f"查看证据 ({evidence_count})", key=f"evidence_{topic_id}", width="stretch"):
                st.session_state["show_topic_evidence"] = topic_id
                st.rerun()
            if is_imported:
                st.success("已入库")
            elif st.button("生成草稿", key=f"draft_{topic_id}", type="primary", width="stretch"):
                _generate_draft(topic, api_key, base_url, model)

        if st.session_state.get("show_topic_evidence") == topic_id:
            _render_evidence(topic_id)


def _render_evidence(topic_id: int):
    evidence = db.get_topic_evidence(topic_id)
    if not evidence:
        st.info("暂无证据")
        return
    with st.expander("关联证据", expanded=True):
        for item in evidence:
            st.markdown(f"**{item.get('title') or '无标题'}**")
            st.caption(
                f"{item.get('source') or '未知来源'} · "
                f"相关度 {item.get('relevance_score') or '-'} · "
                f"{item.get('reason') or ''}"
            )
            if item.get("summary"):
                st.write(item["summary"])
            if item.get("url"):
                st.markdown(f"[打开来源]({item['url']})")
            st.divider()


# ---- 后台任务 ----

_HOT_SEARCH_TASK = "hot_search"
_DRAFT_TASK_PREFIX = "draft_gen_"


def _run_hot_search(
    api_key: str, base_url: str, model: str,
    time_range: str, selected_categories: list[str], custom_keywords: str,
    custom_start, custom_end, max_results: int,
) -> dict:
    """后台线程：搜索 + AI 提取 + 保存 DB"""
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
        return {"raw_count": 0, "topic_count": 0, "msg": "没有搜索到可用结果"}

    tm.update_progress(_HOT_SEARCH_TASK, 0.4, "正在提取候选题材…")
    # 传递时间范围用于第二轮搜索
    time_start = custom_start.strftime("%Y-%m-%d %H:%M:%S") if custom_start else ""
    time_end = custom_end.strftime("%Y-%m-%d %H:%M:%S") if custom_end else ""
    if not time_start:
        from datetime import datetime as _dt
        time_start = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
    topics = generate_candidate_topics(raw_news, api_key, base_url, model, time_start, time_end)

    news_by_id = {item["news_id"]: item for item in raw_news if item.get("news_id")}
    db.save_hot_topic_candidates(topics, news_by_id)
    return {"raw_count": len(raw_news), "topic_count": len(topics), "msg": ""}


def _check_hot_search_task() -> None:
    """检查热点搜索后台任务，完成时展示结果。一键模式展示步骤进度条。"""
    task = tm.get(_HOT_SEARCH_TASK)
    if task is None:
        return

    if task["status"] == "running":
        progress_area = st.empty()
        status_area = st.empty()
        p = task.get("progress", 0)
        msg = task.get("progress_msg", "")

        # 步骤映射
        step_labels = [
            (0.15, "🔍 搜索财经资讯…", "正在从多个渠道抓取近期热点新闻"),
            (0.40, "🤖 AI 分析提取题材…", "大模型识别题材并拆解产业链"),
            (0.70, "📊 接入行情数据验证…", "验证题材的市场热度和资金流向"),
            (0.95, "✅ 完成！", "正在整理结果"),
        ]

        # 确定当前步骤
        current_label = msg
        for threshold, label, detail in step_labels:
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

        # 轮询等待
        while True:
            task = tm.get(_HOT_SEARCH_TASK)
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
            st.success(f"已抓取 {result['raw_count']} 条去重资讯，提取 {result['topic_count']} 个候选题材")
        tm.clear(_HOT_SEARCH_TASK)

    elif task["status"] == "failed":
        st.error(f"搜索失败：{task['error']}")
        if st.button("重试", key="retry_hot_search"):
            tm.clear(_HOT_SEARCH_TASK)
            st.rerun()


def _generate_draft(topic: dict, api_key: str, base_url: str, model: str):
    """提交后台生成草稿任务"""
    topic_id = topic["topic_id"]
    task_id = f"{_DRAFT_TASK_PREFIX}{topic_id}"
    ok = tm.submit(task_id, _run_draft_gen, topic, api_key, base_url, model)
    if ok:
        st.rerun()


def _run_draft_gen(topic: dict, api_key: str, base_url: str, model: str) -> dict:
    """后台线程：生成两阶段分析草稿并保存 DB"""
    topic_id = topic["topic_id"]
    topic_name = topic["topic_name"]
    task_id = f"{_DRAFT_TASK_PREFIX}{topic_id}"

    tm.update_progress(task_id, 0.2, "读取证据…")
    evidence = db.get_topic_evidence(topic_id)

    tm.update_progress(task_id, 0.4, "生成产业链拆解…")
    draft = generate_analysis_draft(topic, evidence, api_key, base_url, model)

    tm.update_progress(task_id, 0.8, "保存草稿…")
    draft_id = db.create_analysis_draft(topic_id, topic_name, draft)
    return {"draft_id": draft_id, "topic_name": topic_name}


_MAX_DRAFT_RERUN = 120  # 120 * 2s = 4 分钟最大自动刷新


def _check_draft_task() -> None:
    """检查草稿生成后台任务，完成时跳转到分析草稿页。

    非阻塞设计：正在运行的任务展示进度条后，通过短 sleep + st.rerun()
    实现自动刷新（每次仅阻塞 2 秒，页面其余内容正常渲染）。
    """
    all_tasks = tm.get_all()
    for tid, task in all_tasks.items():
        if not tid.startswith(_DRAFT_TASK_PREFIX):
            continue
        if task["status"] == "running":
            p = task.get("progress", 0)
            msg = task.get("progress_msg", "")

            with st.container(border=True):
                left, right = st.columns([4, 1])
                with left:
                    st.spinner(f"正在生成草稿… {msg}")
                    st.progress(p, text=f"{msg} ({int(p * 100)}%)")
                with right:
                    if st.button("取消", key=f"cancel_{tid}", type="secondary"):
                        tm.clear(tid)
                        st.rerun()

            counter_key = f"__draft_rerun_{tid}"
            cnt = st.session_state.get(counter_key, 0)
            if cnt >= _MAX_DRAFT_RERUN:
                st.warning("草稿生成耗时较长，请稍后刷新页面或点击取消按钮。")
                st.session_state[counter_key] = 0
            else:
                st.session_state[counter_key] = cnt + 1
                time.sleep(2)
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


def _build_serenity_hints(topic: dict) -> str:
    """
    基于题材数据构建 Serenity 四维分析快速提示。
    从 topic 的字段中提取产业链位置、热度信号、风险等信息，
    组装为简约的 HTML 提示条。
    """
    parts = []

    # 卡脖子位置
    chain_pos = topic.get("chain_position") or topic.get("bottleneck_position")
    if chain_pos:
        pos_color = {"上游": "#FF6A00", "中游": "#F59E0B", "下游": "#60A5FA"}.get(chain_pos, "#9BA3B0")
        parts.append(
            f'<span style="color:{pos_color};font-weight:600;">卡脖子</span> {chain_pos}'
        )

    # 热度信号 → 机构关注度参考
    heat = topic.get("heat_score") or 0
    if heat >= 80:
        parts.append('<span style="color:#60A5FA;">机构信号</span> 高关注')
    elif heat >= 50:
        parts.append('<span style="color:#F59E0B;">机构信号</span> 中等关注')

    # 新鲜度 → 估值暂不判断（新题材不适合传统估值）
    novelty = topic.get("novelty_score") or 0
    if novelty >= 70:
        parts.append('<span style="color:#00D4AA;">估值框架</span> 范式转移')

    # 风险提示 → 价值陷阱
    risk = topic.get("risk_note") or ""
    if risk and any(kw in risk for kw in ["产能过剩", "高股息低增长", "周期性", "退潮"]):
        parts.append('<span style="color:#FF4757;">风险</span> 价值陷阱警示')

    if not parts:
        return ""

    return (
        '<div style="margin-top:6px;padding:6px 10px;'
        'background:#1E2635;border-left:2px solid #FF6A00;border-radius:2px;'
        f'font-size:0.72rem;color:#9BA3B0;">Serenity: ' + " · ".join(parts) + '</div>'
    )
