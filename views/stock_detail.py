"""
个股详情页 — 搜索并展示单只股票的完整信息卡片
"""
import streamlit as st
import pandas as pd
import core.database as db
from core.serenity_analyzer import quick_score_stock, report_to_dict
from ui_components import (
    verify_status_badge,
    verify_status_icon,
    field_verify_badge,
    render_verification_expander,
    serenity_composite_badge,
    serenity_dimension_bar,
    SERENITY_DIMENSIONS,
    SERENITY_GRADE_COLORS,
)


# ---- P2-9: 四维评分柱状对比 ----

def _render_dimension_scores(score_items: list[tuple[str, int | float]]) -> None:
    """使用 Streamlit 原生 metric + 横向柱状条展示四维评分对比"""
    labels = [item[0] for item in score_items]
    values = [item[1] for item in score_items]

    # 指标卡片行
    cols = st.columns(len(score_items))
    for col, label, value in zip(cols, labels, values):
        col.metric(label, value)

    # 横向柱状对比条
    chart_data = pd.DataFrame({"维度": labels, "评分": values})
    st.bar_chart(
        chart_data.set_index("维度"),
        width="stretch",
    )


def render_full_card(stock: dict):
    """渲染完整的个股详情卡片"""
    st.markdown("---")

    # 标题行
    title_cols = st.columns([4, 2, 2])
    title_cols[0].markdown(
        f"<span class='stock-name' style='font-size:2rem !important;'>{stock['stock_name']}</span>",
        unsafe_allow_html=True,
    )
    title_cols[1].markdown(
        f"<span class='stock-code' style='font-size:1.4rem !important;'>{stock['stock_code']}</span>",
        unsafe_allow_html=True,
    )
    importance = stock.get("importance", "中")
    tier = stock.get("tier", "")
    imp_emoji = {"高": "🔴", "中": "🟡", "低": "🟢"}.get(importance, "🟡")
    tier_badge = {"核心": "⭐", "次级": "👍", "观察": "👀"}.get(tier, "")
    verify_status = stock.get("verification_status", "待核验")
    title_cols[2].markdown(
        f"### {imp_emoji} {importance}  {tier_badge} {tier}"
        f'&nbsp;{verify_status_icon(verify_status)}',
        unsafe_allow_html=True,
    )

    st.divider()

    # P2-10: 关注/取消关注按钮
    import tasks.watchlist as wl
    stock_code = stock.get("stock_code", "")
    theme_name = stock.get("theme_name", "")
    is_watched = wl.is_watched("stock", stock_code)

    btn_cols = st.columns([0.8, 3])
    watch_label = "取消关注" if is_watched else "关注此股票"
    if btn_cols[0].button(watch_label, key=f"ws_{stock_code}", width="stretch"):
        if is_watched:
            wl.remove_from_watchlist("stock", stock_code)
        else:
            wl.add_to_watchlist("stock", stock_code, notes=theme_name)
        st.rerun()

    # 基本信息
    st.markdown("### 基本信息")
    info_cols = st.columns(4)

    # 跨题材关联
    all_themes = db.get_stock_themes(stock["stock_code"])
    if len(all_themes) > 1:
        tags = " ".join(
            f"<span style='background:rgba(255,106,0,0.15);color:#FF6A00;padding:2px 8px;border-radius:3px;"
            f"font-size:0.85rem;'>{t}</span>"
            for t in all_themes
        )
        info_cols[0].markdown(
            f"**题材**\n\n{stock['theme_name']}\n\n🔗 同时属于：\n\n{tags}",
            unsafe_allow_html=True,
        )
    else:
        info_cols[0].markdown(f"**题材**\n\n{stock['theme_name']}")

    info_cols[1].markdown(f"**市场类型**\n\n{stock['market_type']}")
    info_cols[2].markdown(
        f"**产业链环节**\n\n{stock['level1']}"
        + (f" > {stock['level2']}" if stock.get("level2") else "")
        + (f" > {stock['level3']}" if stock.get("level3") else "")
    )
    info_cols[3].markdown(f"**公司角色**\n\n{stock.get('role') or '—'}")

    st.divider()

    # 核心分析
    st.markdown("### 💡 核心逻辑")
    st.markdown(stock.get("logic_summary") or "*(暂无)*")

    st.divider()

    # AI 多维评分
    score_items = [
        ("业务关联", stock.get("biz_relevance")),
        ("业务增速", stock.get("biz_growth")),
        ("质量分", stock.get("quality_score")),
        ("资金关注", stock.get("flow_score")),
    ]
    score_items = [(label, value) for label, value in score_items if value not in (None, "")]
    if score_items:
        st.markdown("### AI 多维评分")
        # P2-9: 使用原生 metric + bar 组件展示四维评分对比
        _render_dimension_scores(score_items)
        st.divider()

    # P2-13: Serenity 四维深度分析仪表盘
    _render_serenity_dashboard_section(theme_name, stock)

    # 市场 & 竞争
    st.markdown("### 🏢 市场与竞争")
    comp_cols = st.columns(3)

    # 解析验证详情获取字段状态
    details_str = stock.get("verification_details", "")
    field_statuses = {}
    if details_str:
        try:
            import json
            details = json.loads(details_str)
            for fname, fd in details.get("field_details", {}).items():
                field_statuses[fname] = fd.get("status", "")
        except (json.JSONDecodeError, TypeError):
            pass

    mp_badge = field_verify_badge(field_statuses.get("market_position", ""))
    ms_badge = field_verify_badge(field_statuses.get("market_share", ""))
    cu_badge = field_verify_badge(field_statuses.get("customers", ""))

    comp_cols[0].markdown(
        f"**市场地位** {mp_badge}\n\n{stock.get('market_position') or '—'}",
        unsafe_allow_html=True,
    )
    comp_cols[1].markdown(
        f"**市场占有率** {ms_badge}\n\n{stock.get('market_share') or '—'}",
        unsafe_allow_html=True,
    )
    comp_cols[2].markdown(
        f"**客户关系** {cu_badge}\n\n{stock.get('customers') or '—'}",
        unsafe_allow_html=True,
    )

    st.divider()

    # 验证详情
    verify_status = stock.get("verification_status", "待核验")
    st.markdown(
        f"### 🔍 验证状态 {verify_status_badge(verify_status)}",
        unsafe_allow_html=True,
    )
    render_verification_expander(stock)

    st.divider()

    # 来源 & 备注
    st.markdown("### 📎 参考信息")
    ref_cols = st.columns(2)
    ref_cols[0].markdown(f"**信息来源**\n\n{stock.get('source') or '—'}")
    ref_cols[1].markdown(f"**备注**\n\n{stock.get('notes') or '—'}")

    st.divider()
    st.caption(f"更新时间: {stock.get('updated_at', '—')}")


def render():
    st.title("📊 个股详情")

    # 从其他页面跳转过来的预填代码（强制预填模式）
    prefill_code = st.session_state.pop("nav_stock_code", "")

    if prefill_code:
        # 强制预填模式：直接用 value，绕过 session_state widget 状态
        # 避免与旧 widget 状态冲突（保证跳转时一定能正确填充）
        stock_input = st.text_input(
            "输入股票代码或名称",
            value=prefill_code,
            key=f"stock_input_forced_{prefill_code}",  # 动态 key 避免状态冲突
            placeholder="例如：688981 或 中芯国际",
        )
    else:
        # 正常搜索模式：用 key 绑定 session_state（避免 widget 状态冲突死循环）
        if "stock_search_input" not in st.session_state:
            st.session_state.stock_search_input = ""
        stock_input = st.text_input(
            "输入股票代码或名称",
            key="stock_search_input",
            placeholder="例如：688981 或 中芯国际",
        )

    # 模糊匹配
    keyword = stock_input.strip()
    if keyword:
        results = db.search_stocks(keyword=keyword)
        if results.empty:
            st.warning("未找到匹配的股票")
            return

        if len(results) > 1 and not prefill_code:
            # 多条匹配，让用户选择
            st.info(f"找到 {len(results)} 条匹配，请选择：")
            for _, row in results.iterrows():
                r = dict(row)
                label = f"{r['stock_name']} ({r['stock_code']}) — {r['theme_name']}"
                if st.button(label, key=f"pick_{r['id']}"):
                    render_full_card(r)
        else:
            # 精确或单条，直接展示
            for _, row in results.iterrows():
                render_full_card(dict(row))
    else:
        st.info("请输入股票代码或名称进行搜索")


# ============================================================================
# P2-13: Serenity 四维深度分析仪表盘
# ============================================================================

_show_serenity_help = False


def _render_serenity_dashboard_section(theme_name: str, stock: dict) -> None:
    """渲染 Serenity 四维分析仪表盘"""
    global _show_serenity_help

    # 从个股数据推断产业链位置和参数
    level1 = stock.get("level1", "")
    chain_hierarchy = f"{level1} > {stock.get('level2', '')} > {stock.get('level3', '')}"

    # 产业链位置推断：上游关键词
    upstream_keywords = ["材料", "设备", "原料", "芯片", "组件", "模组", "EDA", "IP", "光刻", "硅", "基板"]
    downstream_keywords = ["终端", "应用", "品牌", "消费", "销售", "服务", "运营", "集成"]

    if any(kw in chain_hierarchy for kw in upstream_keywords):
        position = "upstream"
    elif any(kw in chain_hierarchy for kw in downstream_keywords):
        position = "downstream"
    else:
        position = "midstream"

    # 基于现有数据构建 Serenity 报告
    biz_relevance = stock.get("biz_relevance") or 50
    biz_growth = stock.get("biz_growth") or 50
    quality_score = stock.get("quality_score") or 50
    flow_score = stock.get("flow_score") or 50

    try:
        biz_relevance = int(float(biz_relevance))
        biz_growth = int(float(biz_growth))
        quality_score = int(float(quality_score))
        flow_score = int(float(flow_score))
    except (ValueError, TypeError):
        biz_relevance = biz_growth = quality_score = flow_score = 50

    # 业务关联 → 卡脖子 (相关性越强，位置越核心)
    bottleneck_score = min(95, int(biz_relevance * 0.85 + 5 * (1 if position == "upstream" else 0)))

    # 资金关注 → 机构信号
    inst_score = min(95, flow_score)

    # 质量分 → 长线价值
    value_score = min(95, quality_score)

    # 业务增速 + 题材属性 → 估值重置 (高增速题材 = 范式转移)
    vr_score = min(95, int(biz_growth * 0.7 + 20 * (1 if biz_growth > 60 else 0)))

    # 综合置信度
    composite = int(
        bottleneck_score * 0.25
        + inst_score * 0.25
        + value_score * 0.25
        + vr_score * 0.25
    )

    # 评分等级
    if composite >= 85:
        grade = "A"
    elif composite >= 70:
        grade = "B"
    elif composite >= 55:
        grade = "C"
    elif composite >= 40:
        grade = "D"
    else:
        grade = "F"

    # ---- 渲染 ----
    st.divider()
    st.markdown("### Serenity 四维深度分析")

    # 帮助提示
    if not _show_serenity_help:
        st.caption("基于白毛股神四维框架：卡脖子位置 · 机构资金 · 长线价值 · 估值重置")
        if st.button("了解四维框架", key=f"serenity_help_{stock.get('stock_code', '')}"):
            _show_serenity_help = True
            st.rerun()

    if _show_serenity_help:
        with st.expander("四维框架说明", expanded=True):
            st.markdown(
                """
| 维度 | 核心问题 | A股映射 |
|------|----------|---------|
| **卡脖子指数** | 在产业链中多难被替代？ | 国产替代率、进口依赖度、技术自主可控 |
| **机构行为信号** | 聪明钱在做什么？ | 北向资金、融资融券、龙虎榜游资 |
| **长线价值评分** | 基本面是否支撑长期持有？ | ROE、毛利率、现金流、护城河 |
| **估值重置判断** | 当前估值是否合理？ | 范式转移 vs 周期波动 vs 价值陷阱 |
"""
            )

    # 综合置信度徽章
    st.markdown(
        serenity_composite_badge(composite, grade),
        unsafe_allow_html=True,
    )

    # 四维进度条
    dims = [
        ("卡脖子指数", bottleneck_score, SERENITY_DIMENSIONS["bottleneck"]["color"], SERENITY_DIMENSIONS["bottleneck"]["bg"]),
        ("机构行为信号", inst_score, SERENITY_DIMENSIONS["institutional"]["color"], SERENITY_DIMENSIONS["institutional"]["bg"]),
        ("长线价值评分", value_score, SERENITY_DIMENSIONS["value"]["color"], SERENITY_DIMENSIONS["value"]["bg"]),
        ("估值重置判断", vr_score, SERENITY_DIMENSIONS["valuation"]["color"], SERENITY_DIMENSIONS["valuation"]["bg"]),
    ]
    for label, score, color, bg in dims:
        st.markdown(serenity_dimension_bar(label, score, color, bg), unsafe_allow_html=True)

    # 四维指标卡片
    cols = st.columns(4)
    for col, (key, label, score) in zip(
        cols,
        [
            ("bottleneck", "卡脖子", bottleneck_score),
            ("institutional", "机构信号", inst_score),
            ("value", "长线价值", value_score),
            ("valuation", "估值重置", vr_score),
        ],
    ):
        dim = SERENITY_DIMENSIONS[key]
        col.markdown(
            f'<div style="padding:10px 8px;background:{dim["bg"]}55;'
            f'border-radius:4px;text-align:center;border:1px solid {dim["color"]}22;">'
            f'<div style="font-size:1.5rem;font-weight:750;font-family:monospace;'
            f'color:{dim["color"]};">{score}</div>'
            f'<div style="color:{dim["color"]};font-size:0.72rem;font-weight:600;">'
            f'{dim["icon"]} {dim["label"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.divider()


def _bottleneck_level_label(score: int) -> str:
    if score >= 80:
        return "极高"
    elif score >= 60:
        return "高"
    elif score >= 35:
        return "中等"
    elif score >= 15:
        return "低"
    return "无"


def _signal_label(score: int) -> str:
    if score >= 70:
        return "强买入信号"
    elif score >= 55:
        return "买入"
    elif score >= 45:
        return "中性"
    elif score >= 30:
        return "卖出"
    return "强卖出信号"


def _regime_label(score: int, growth: int) -> str:
    if score >= 75 and growth >= 60:
        return "范式转移"
    elif score >= 60:
        return "合理估值"
    elif score >= 35:
        return "周期波动"
    return "价值陷阱"
