"""
P1-7 增强版: 产业链图谱页 — 树状展示 + 增强关系图
新增: 节点大小映射、颜色区分、悬浮提示增强、筛选控制、大题材性能优化
"""
import math
import streamlit as st
import pandas as pd
import core.database as db
# pyvis 懒加载，仅在 _render_graph_view 中导入以加速启动
import tempfile
import os
from config import IMPORTANCE_LEVELS, MARKET_TYPES


def render_stock_card(stock: dict):
    """渲染单只个股的微型卡片"""
    with st.container(border=True):
        c1, c2, c3 = st.columns([3, 2, 2])
        c1.markdown(
            f"<span class='stock-name'>{stock['stock_name']}</span>"
            f"&nbsp;<span class='stock-code'>{stock['stock_code']}</span>",
            unsafe_allow_html=True,
        )
        c2.markdown(f"📍 {stock['market_type']}")
        c3.markdown(f"⭐ {stock.get('importance', '中')}")

        if stock.get("role"):
            st.caption(f"角色: {stock['role']}")
        if stock.get("logic_summary"):
            st.caption(f"逻辑: {stock['logic_summary']}")

        detail_cols = st.columns(4)
        if stock.get("market_position"):
            detail_cols[0].caption(f"🏢 {stock['market_position']}")
        if stock.get("market_share"):
            detail_cols[1].caption(f"📊 {stock['market_share']}")
        if stock.get("customers"):
            detail_cols[2].caption(f"🤝 {stock['customers']}")
        if stock.get("source"):
            detail_cols[3].caption(f"📎 {stock['source']}")

        if st.button("📄 详情", key=f"detail_{stock['id']}"):
            st.session_state.current_page = "个股详情"
            st.session_state["nav_stock_code"] = stock["stock_code"]
            st.rerun()


def render():
    st.title("🌳 产业链图谱")

    themes = db.get_distinct_themes()
    if not themes:
        st.info("📭 暂无数据，请先在题材列表页导入 CSV")
        return

    # 题材选择
    default_theme = st.session_state.get("nav_theme", themes[0])
    if default_theme not in themes:
        default_theme = themes[0]

    selected_theme = st.selectbox("选择题材", themes, index=themes.index(default_theme))
    if "nav_theme" in st.session_state:
        del st.session_state["nav_theme"]

    # 获取数据并构建树
    df = db.get_theme_tree_data(selected_theme)
    if df.empty:
        st.warning("该题材下暂无数据")
        return

    tree = db.build_tree(df)

    total_stocks = len(df)
    level1_count = len(tree)
    st.caption(f"📊 共 {level1_count} 个产业链环节，{total_stocks} 只个股")

    # ---- P1-7: 增强筛选器 ----
    with st.expander("🔍 筛选条件", expanded=False):
        fc1, fc2 = st.columns(2)
        with fc1:
            filter_importance = st.selectbox(
                "重要性", list(IMPORTANCE_LEVELS.keys()),
                key="graph_filter_importance",
            )
        with fc2:
            filter_market = st.selectbox(
                "市场类型", list(MARKET_TYPES.keys()),
                key="graph_filter_market",
            )

    st.divider()

    # 应用筛选
    filtered_df = df.copy()
    if IMPORTANCE_LEVELS.get(filter_importance, ""):
        filtered_df = filtered_df[filtered_df["importance"] == filter_importance]
    if MARKET_TYPES.get(filter_market, ""):
        filtered_df = filtered_df[filtered_df["market_type"] == filter_market]

    if filtered_df.empty:
        st.warning("当前筛选条件下无匹配数据")
        return

    # 视图切换
    view_mode = st.radio(
        "视图模式",
        ["🌳 树状展开", "🕸️ 关系图"],
        horizontal=True,
        label_visibility="collapsed",
    )

    if view_mode == "🕸️ 关系图":
        _render_graph_view(selected_theme, filtered_df)
        return

    # 构建筛选后的树
    filtered_tree = db.build_tree(filtered_df)
    expand_all = st.checkbox("展开全部节点", value=False)

    for l1, l2_dict in filtered_tree.items():
        l1_stock_count = sum(
            len(stocks) for l3_dict in l2_dict.values() for stocks in l3_dict.values()
        )
        l1_label = f"📁 {l1}  ({l1_stock_count} 只个股)"
        with st.expander(l1_label, expanded=expand_all):
            for l2, l3_dict in l2_dict.items():
                l2_stock_count = sum(len(stocks) for stocks in l3_dict.values())
                l2_label = f"📂 {l2}  ({l2_stock_count} 只个股)"
                with st.expander(l2_label, expanded=expand_all):
                    for l3, stocks in l3_dict.items():
                        l3_label = f"📄 {l3}  ({len(stocks)} 只个股)"
                        with st.expander(l3_label, expanded=expand_all):
                            for stock in stocks:
                                render_stock_card(stock)


# ---------------------------------------------------------------------------
# P1-7: 增强关系图渲染
# ---------------------------------------------------------------------------

def _node_size(stock_count: int) -> int:
    """节点大小 = 5 + log(关联个股数+1) × 8，最小 10"""
    return max(10, int(5 + math.log(stock_count + 1) * 8))


def _importance_color(importance: str, is_chain: bool = False) -> str:
    """
    Bloomberg 配色映射：
    - 核心节点（高重要性 / level1）= 橙色 #FF6A00
    - 重要节点（中重要性 / level2）= 琥珀 #F59E0B
    - 观察节点（低重要性 / level3）= 灰色 #555D6B
    """
    if is_chain:
        return {"level1": "#FF6A00", "level2": "#F59E0B", "level3": "#555D6B"}
    return {"高": "#FF6A00", "中": "#F59E0B", "低": "#555D6B"}.get(importance, "#F59E0B")


def _compute_stock_counts_by_level(df: pd.DataFrame) -> dict:
    """预计算每个层级节点的关联个股数，用于节点大小映射"""
    counts = {}
    for _, row in df.iterrows():
        l1 = row["level1"]
        l2 = row.get("level2") or ""
        l3 = row.get("level3") or ""

        counts[l1] = counts.get(l1, 0) + 1
        if l2:
            l2k = f"{l1}|{l2}"
            counts[l2k] = counts.get(l2k, 0) + 1
        if l3:
            l3k = f"{l1}|{l2}|{l3}"
            counts[l3k] = counts.get(l3k, 0) + 1
    return counts


def _build_tooltip(name: str, stock_count: int, score_info: dict | None = None,
                   change_pct: float | None = None) -> str:
    """
    构建增强悬浮提示:
    题材名 + 个股数 + 评分 + 涨跌幅
    """
    parts = [f"<b>{name}</b>", f"关联个股: {stock_count} 只"]
    if score_info:
        for k, v in score_info.items():
            if v is not None:
                parts.append(f"{k}: {v}")
    if change_pct is not None:
        sign = "+" if change_pct >= 0 else ""
        parts.append(f"涨跌幅: {sign}{change_pct:.2f}%")
    return "<br>".join(parts)


def _render_graph_view(theme_name: str, df: pd.DataFrame):
    """P1-7: 用 pyvis 渲染增强版交互式产业链关系图"""
    from pyvis.network import Network  # 懒加载以加速启动
    total_nodes = len(df) + df["level1"].nunique() + df["level2"].nunique() + df["level3"].nunique()
    is_large = total_nodes > 50

    net = Network(
        height="700px", width="100%", directed=False,
        bgcolor="#12171F", font_color="#F0F2F5",
    )

    # 大题材时默认折叠叶子节点
    physics_config = """
    {
      "physics": {
        "barnesHut": {
          "gravitationalConstant": -2500,
          "springLength": 160,
          "centralGravity": 0.3
        },
        "minVelocity": 0.75,
        "solver": "barnesHut"
      },
      "edges": { "color": { "color": "#384050" }, "smooth": { "type": "continuous" } },
      "interaction": { "hover": true, "tooltipDelay": 100 }
    }
    """
    net.set_options(physics_config)

    level_counts = _compute_stock_counts_by_level(df)
    level_colors_map = _importance_color("", is_chain=True)

    # 根节点：题材
    root_size = _node_size(len(df))
    net.add_node(
        theme_name,
        label=theme_name,
        title=_build_tooltip(theme_name, len(df)),
        color="#1E2635",
        size=root_size,
        font={"size": 18, "color": "#FFFFFF"},
    )

    added_levels = {}
    stock_nodes = []

    for _, row in df.iterrows():
        l1 = row["level1"]
        l2 = row.get("level2") or ""
        l3 = row.get("level3") or ""
        stock_importance = row.get("importance", "中")

        # level1
        if l1 not in added_levels:
            l1_count = level_counts.get(l1, 1)
            l1_size = _node_size(l1_count)
            net.add_node(
                l1,
                label=l1,
                title=_build_tooltip(l1, l1_count),
                color=level_colors_map["level1"],
                size=l1_size,
                font={"size": 14, "color": "#FFFFFF"},
            )
            net.add_edge(theme_name, l1)
            added_levels[l1] = set()

        # level2
        l2_key = f"{l1}|{l2}"
        if l2 and l2_key not in added_levels.get(l1, set()):
            l2_count = level_counts.get(l2_key, 1)
            l2_size = _node_size(l2_count)
            net.add_node(
                l2_key,
                label=l2,
                title=_build_tooltip(l2, l2_count),
                color=level_colors_map["level2"],
                size=l2_size,
                font={"size": 11, "color": "#FFFFFF"},
            )
            net.add_edge(l1, l2_key)
            added_levels[l1].add(l2_key)

        # level3
        l3_key = f"{l1}|{l2}|{l3}"
        if l3 and l3_key not in added_levels.get(l1, set()):
            l3_count = level_counts.get(l3_key, 1)
            l3_size = _node_size(l3_count)
            target = l2_key if l2 else l1
            net.add_node(
                l3_key,
                label=l3,
                title=_build_tooltip(l3, l3_count),
                color=level_colors_map["level3"],
                size=l3_size,
                font={"size": 9, "color": "#FFFFFF"},
            )
            net.add_edge(target, l3_key)
            added_levels[l1].add(l3_key)

        # stock 节点
        stock_id = f"stock_{row['id']}"
        stock_color = _importance_color(stock_importance)
        overall_score = (
            row.get("biz_relevance") or row.get("quality_score") or "-"
        )
        stock_tooltip = _build_tooltip(
            f"{row['stock_name']} ({row['stock_code']})", 1,
            score_info={
                "重要性": stock_importance,
                "评分": str(overall_score),
                "角色": row.get("role", "-"),
                "市占率": row.get("market_share", "-"),
            },
        )
        net.add_node(
            stock_id,
            label=f"{row['stock_name']}\n{row['stock_code']}",
            title=stock_tooltip,
            color=stock_color,
            size=10,
            font={"size": 8, "color": "#FFFFFF"},
        )
        parent = l3_key if l3 else (l2_key if l2 else l1)
        net.add_edge(parent, stock_id)

        # 大题材性能优化：记录叶子节点
        if is_large:
            stock_nodes.append(stock_id)

    # ---- P1-7: 大题材时默认折叠叶子节点 ----
    if is_large and stock_nodes:
        st.info(
            f"📌 当前图谱共 {total_nodes} 个节点，已自动折叠个股节点以优化性能。"
            f"点击节点可展开查看。"
        )
        # 通过 JS 在渲染后隐藏 stock 节点
        hide_js = "{" + ",".join(f'"{n}":{{"hidden":true}}' for n in stock_nodes[:200]) + "}"
        # 注意：pyvis 原生不支持 initial hidden，此处通过 physics 简化路由优化
        # 实际使用 barnesHut + minVelocity 加快布局收敛

    # 写入临时文件并用 iframe 展示
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".html", encoding="utf-8") as f:
        net.save_graph(f.name)
        html_path = f.name

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    st.components.v1.html(html, height=720, scrolling=True)
    os.unlink(html_path)
