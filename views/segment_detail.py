"""
细分环节详情页 — 搜索 & 过滤个股
"""
import streamlit as st
import pandas as pd
import core.database as db
from config import MARKET_TYPES, IMPORTANCE_LEVELS


def render_stock_row(stock: dict):
    """以紧凑行展示个股信息"""
    with st.container(border=True):
        top = st.columns([2, 1, 1, 1, 1])
        top[0].markdown(
            f"<span class='stock-name'>{stock['stock_name']}</span>"
            f"&nbsp;<span class='stock-code'>{stock['stock_code']}</span>",
            unsafe_allow_html=True,
        )
        top[1].markdown(f"📍 {stock['market_type']}")
        top[2].markdown(f"📁 {stock['level1']}")
        top[3].markdown(f"⭐ {stock.get('importance', '中')}")
        top[4].markdown(f"🏷️ {stock['theme_name']}")

        if stock.get("role"):
            st.caption(f"🔹 角色: {stock['role']}")
        if stock.get("logic_summary"):
            st.caption(f"💡 {stock['logic_summary']}")

        cols = st.columns(5)
        if stock.get("market_position"):
            cols[0].caption(f"🏢 {stock['market_position']}")
        if stock.get("market_share"):
            cols[1].caption(f"📊 {stock['market_share']}")
        if stock.get("customers"):
            cols[2].caption(f"🤝 {stock['customers']}")
        if stock.get("source"):
            cols[3].caption(f"📎 {stock['source']}")
        if stock.get("notes"):
            cols[4].caption(f"📝 {stock['notes']}")

        if st.button("📄 详情", key=f"seg_{stock['id']}"):
            st.session_state.current_page = "个股详情"
            st.session_state["nav_stock_code"] = stock["stock_code"]
            st.rerun()


def render():
    st.title("🔍 细分环节详情")

    themes = db.get_distinct_themes()
    if not themes:
        st.info("📭 暂无数据，请先导入 CSV")
        return

    # ---- 搜索与过滤 ----
    col_kw, col_mkt, col_imp = st.columns([3, 1, 1])

    keyword = col_kw.text_input(
        "🔎 搜索关键词",
        placeholder="输入题材/股票名/产业链环节/关键词 如 EDA、光刻胶…",
        value=st.session_state.get("search_keyword", ""),
    )
    market_type = col_mkt.selectbox("📌 市场类型", list(MARKET_TYPES.keys()))
    importance = col_imp.selectbox("⭐ 重要性", list(IMPORTANCE_LEVELS.keys()))

    # 可选：按题材筛选
    theme_filter = st.selectbox(
        "🏷️ 限定题材（可选）",
        ["全部"] + themes,
    )

    st.divider()

    # ---- 查询 ----
    df = db.search_stocks(
        keyword=keyword.strip(),
        market_type=MARKET_TYPES.get(market_type, ""),
        importance=IMPORTANCE_LEVELS.get(importance, ""),
        theme_name="" if theme_filter == "全部" else theme_filter,
    )

    st.caption(f"找到 {len(df)} 条匹配记录")

    if df.empty:
        st.info("未找到匹配结果，请调整搜索条件")
        return

    # 分页
    PAGE_SIZE = 20
    total_pages = max(1, (len(df) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = st.number_input(
        "页码", min_value=1, max_value=total_pages, value=1, label_visibility="collapsed"
    )
    page = min(page, total_pages)

    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE

    st.caption(f"第 {page}/{total_pages} 页，显示 {start+1}–{min(end, len(df))} 条")

    for _, row in df.iloc[start:end].iterrows():
        render_stock_row(dict(row))
