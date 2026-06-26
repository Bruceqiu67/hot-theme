"""
题材对比页 — 选 2-3 个题材并排对比
"""
import streamlit as st
import pandas as pd
import core.database as db


def render():
    st.title("📊 题材对比")

    themes = db.get_distinct_themes()
    if len(themes) < 2:
        st.info("📭 至少需要 2 个题材才能对比，请先导入数据")
        return

    selected = st.multiselect(
        "选择要对比的题材（2–3 个）",
        themes,
        max_selections=3,
        placeholder="选择题材...",
    )

    if len(selected) < 2:
        st.info("👆 请至少选择 2 个题材")
        return

    st.divider()

    data = db.get_theme_compare_data(selected)

    # ---- 概览卡片 ----
    st.subheader("📋 概览对比")
    cols = st.columns(len(selected))
    for i, t in enumerate(selected):
        df_t = data["per_theme"].get(t, pd.DataFrame())
        cols[i].metric(
            f"📁 {t}",
            f"{len(df_t)} 条",
            delta=f"{df_t['stock_code'].nunique()} 只个股",
        )

    # ---- 环节对比 ----
    st.divider()
    st.subheader("🔗 产业链环节对比")

    level_data = {}
    for t in selected:
        df_t = data["per_theme"].get(t, pd.DataFrame())
        if df_t.empty:
            continue
        for level in ["level1", "level2", "level3"]:
            vals = df_t[level].dropna().replace("", pd.NA).dropna().unique()
            level_data.setdefault(level, {})[t] = set(vals)

    for level_name, theme_sets in level_data.items():
        label = {"level1": "一级环节", "level2": "二级方向", "level3": "三级方向"}.get(level_name, level_name)

        with st.expander(f"{label} 对比", expanded=(level_name == "level1")):
            rows = []
            all_vals = set()
            for s in theme_sets.values():
                all_vals |= s

            for val in sorted(all_vals):
                row = {"环节": val}
                for t in selected:
                    row[t] = "✅" if val in theme_sets.get(t, set()) else "—"
                rows.append(row)

            if rows:
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
            else:
                st.caption("无数据")

    # ---- 共有个股 ----
    st.divider()
    st.subheader("🤝 共有个股（同时出现在所有选中题材中）")
    common = data.get("common_stocks", pd.DataFrame())
    if not common.empty:
        for _, row in common.iterrows():
            st.markdown(
                f"<span class='stock-name'>{row['stock_name']}</span>"
                f"&nbsp;<span class='stock-code'>{row['stock_code']}</span>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("无共有个股")

    # ---- 详情表 ----
    st.divider()
    st.subheader("📋 个股详情对比")
    for t in selected:
        df_t = data["per_theme"].get(t, pd.DataFrame())
        if df_t.empty:
            continue
        with st.expander(f"📁 {t} — {len(df_t)} 条"):
            st.dataframe(
                df_t[["stock_code", "stock_name", "level1", "level2", "level3", "importance"]],
                width="stretch",
                hide_index=True,
            )
