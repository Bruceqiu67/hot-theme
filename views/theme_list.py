"""
题材列表页 — 显示所有题材概览，支持 CSV 导入、导出和 AI 更新
"""
import time

import pandas as pd
import streamlit as st

import core.database as db
import tasks.task_manager as tm
from config import get_logger
from ui_components import badge, esc, metric_strip, page_header, freshness_badge

_log = get_logger("theme_list")


def render():
    page_header(
        "题材列表",
        "管理已入库题材，快速查看产业链覆盖、个股数量、评分和更新时间。",
        eyebrow="Theme Library",
        meta="核心题材库",
    )

    _render_import_panel()
    _render_summary()

    # P2-9: 使用含维度数据的查询
    df = db.get_theme_summary_with_dimensions()
    if df.empty:
        st.info("暂无数据，请先导入 theme_knowledge.csv")
        return

    _handle_updates()
    _render_toolbar()
    # P2-9: 多维度排序和筛选
    df = _apply_dimension_filters(df)
    _render_theme_rows(df)
    _check_update_tasks()
    _render_delete_confirm()


def _render_import_panel():
    with st.expander("导入 CSV 数据", expanded=False):
        st.caption("上传 theme_knowledge.csv 会清空现有数据并重新导入。")
        uploaded = st.file_uploader(
            "选择 CSV 文件",
            type=["csv"],
            label_visibility="collapsed",
        )
        if uploaded is None:
            return
        try:
            df = pd.read_csv(uploaded, dtype=str)
            st.info(f"已读取 {len(df)} 行，{len(df.columns)} 列")
            st.dataframe(df.head(5), width="stretch")
            if st.button("确认导入并覆盖现有数据", type="primary"):
                db.clear_all()
                count = db.import_dataframe(df)
                st.success(f"导入成功，共 {count} 条记录")
                st.rerun()
        except Exception as exc:
            st.error(f"导入失败: {exc}")


def _render_summary():
    stats = db.get_db_stats()
    metric_strip([
        ("题材数量", stats["theme_count"], "已入库主题"),
        ("个股数量", stats["stock_count"], "去重股票"),
        ("总关联数", stats["total_rows"], "题材-个股关系"),
    ])


def _handle_updates():
    updating = st.session_state.pop("updating_theme", None)
    if updating:
        _submit_update_one(updating)

    if st.session_state.pop("updating_all", False):
        _submit_update_all()


def _submit_update_one(theme_name: str):
    """提交单个题材 AI 更新后台任务"""
    from core.ai_client import load_api_config
    api_key, base_url, model = load_api_config(st.session_state.get)
    if not api_key:
        st.error("未配置 API Key，请先到「AI 生成」页保存配置")
        return
    task_id = f"update_{theme_name}"
    ok = tm.submit(task_id, _run_update_one, theme_name, api_key, base_url, model)
    if ok:
        st.rerun()


def _submit_update_all():
    """提交全部题材批量更新后台任务"""
    from core.ai_client import load_api_config
    api_key, base_url, model = load_api_config(st.session_state.get)
    if not api_key:
        st.error("未配置 API Key，请先到「AI 生成」页保存配置")
        return
    themes = db.get_distinct_themes()
    if not themes:
        st.warning("暂无题材可更新")
        return
    ok = tm.submit("update_all", _run_update_all, themes, api_key, base_url, model)
    if ok:
        st.rerun()


# ---- 后台任务 ----

_UPDATE_PREFIX = "update_"


def _run_update_one(theme_name: str, api_key: str, base_url: str, model: str) -> dict:
    """后台线程：更新单个题材"""
    from core.ai_client import generate_theme_analysis, flatten_chains
    task_id = f"update_{theme_name}"
    tm.update_progress(task_id, 0.3, f"正在分析「{theme_name}」…")
    raw = generate_theme_analysis(theme_name, api_key, base_url, model)
    rows, theme_quality = flatten_chains(raw)
    count = db.replace_theme(theme_name, pd.DataFrame(rows), theme_quality)
    return {"theme_name": theme_name, "count": count}


def _run_update_all(themes: list[str], api_key: str, base_url: str, model: str) -> dict:
    """后台线程：批量更新全部题材"""
    from core.ai_client import generate_theme_analysis, flatten_chains
    total = len(themes)
    ok = 0
    fail = 0
    for idx, theme in enumerate(themes):
        pct = (idx + 1) / total
        tm.update_progress("update_all", pct, f"({idx + 1}/{total}) 正在分析「{theme}」…")
        try:
            raw = generate_theme_analysis(theme, api_key, base_url, model)
            rows, theme_quality = flatten_chains(raw)
            db.replace_theme(theme, pd.DataFrame(rows), theme_quality)
            ok += 1
        except Exception:
            _log.exception("批量更新题材「%s」失败", theme)
            fail += 1
    return {"ok": ok, "fail": fail, "total": total}


_MAX_RERUN_COUNT = 90  # 90 * 2s = 3 分钟最大自动刷新


def _check_update_tasks() -> None:
    """检查 AI 更新后台任务，完成时展示结果。

    非阻塞设计：正在运行的任务展示进度条后，通过短 sleep + st.rerun()
    实现自动刷新（每次仅阻塞 2 秒，页面其余内容正常渲染）。
    超过 _MAX_RERUN_COUNT 次后停止自动刷新，提示用户手动操作。
    """
    all_tasks = tm.get_all()
    for tid, task in all_tasks.items():
        if not tid.startswith(_UPDATE_PREFIX):
            continue

        if task["status"] == "running":
            p = task.get("progress", 0)
            msg = task.get("progress_msg", "")
            label = f"批量更新中… {msg}" if tid == "update_all" else f"更新中… {msg}"

            with st.container(border=True):
                left, right = st.columns([4, 1])
                with left:
                    st.spinner(label)
                    st.progress(p, text=f"{msg} ({int(p * 100)}%)")
                with right:
                    if st.button("取消", key=f"cancel_{tid}", type="secondary"):
                        tm.clear(tid)
                        st.rerun()

            # 自动刷新进度（最多 3 分钟）
            counter_key = f"__rerun_cnt_{tid}"
            cnt = st.session_state.get(counter_key, 0)
            if cnt >= _MAX_RERUN_COUNT:
                st.warning(
                    f"「{tid.replace('update_', '')}」更新耗时较长，"
                    f"请稍后刷新页面或点击上方取消按钮。"
                )
                st.session_state[counter_key] = 0  # 重置，下次重新计数
            else:
                st.session_state[counter_key] = cnt + 1
                time.sleep(2)
                st.rerun()

        elif task["status"] == "completed":
            result = task["result"] or {}
            if tid == "update_all":
                st.success(f"全部更新完成：成功 {result['ok']} 个，失败 {result['fail']} 个")
            else:
                st.success(f"「{result['theme_name']}」更新完成，共 {result['count']} 条记录")
            tm.clear(tid)

        elif task["status"] == "failed":
            st.error(f"更新失败（{tid}）：{task['error']}")
            if st.button("关闭", key=f"dismiss_{tid}"):
                tm.clear(tid)
                st.rerun()


def _render_toolbar():
    left, right = st.columns([1, 1.4])
    with left:
        if st.button("一键更新全部题材", width="stretch"):
            st.session_state["updating_all"] = True
            st.rerun()

    with right:
        themes = db.get_distinct_themes()
        c1, c2 = st.columns([1, 1])
        export_theme = c1.selectbox("导出范围", ["全部"] + themes, label_visibility="collapsed")
        export_df = db.export_dataframe("" if export_theme == "全部" else export_theme)
        if not export_df.empty:
            label = "全部题材" if export_theme == "全部" else export_theme
            c2.download_button(
                f"导出 {label} ({len(export_df)} 条)",
                data=export_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                file_name=f"theme_knowledge_{label}.csv",
                mime="text/csv",
                width="stretch",
            )


# ---- P2-9: 多维度筛选与排序 ----

_DIMENSION_LABELS = {
    "overall_score": "综合评分",
    "avg_biz_relevance": "业务相关性",
    "avg_biz_growth": "成长性",
    "avg_quality_score": "质量分",
    "avg_flow_score": "资金热度",
}


def _apply_dimension_filters(df: pd.DataFrame) -> pd.DataFrame:
    """应用多维度排序和阈值筛选"""
    with st.expander("多维度筛选与排序", expanded=False):
        c1, c2, c3 = st.columns(3)

        # 排序维度
        sort_options = ["综合评分", "业务相关性", "成长性", "质量分", "资金热度", "个股数量"]
        sort_choice = c1.selectbox("排序方式", sort_options, index=0)

        # 排序方向
        sort_order = c2.selectbox("排序方向", ["降序", "升序"], index=0)

        # 阈值筛选模式
        filter_enabled = c3.checkbox("启用维度阈值筛选", value=False)

        if filter_enabled:
            fc1, fc2, fc3, fc4 = st.columns(4)
            min_biz_rel = fc1.number_input("业务相关性 >=", 0, 100, 0, step=5, key="f_biz_rel")
            min_biz_growth = fc2.number_input("成长性 >=", 0, 100, 0, step=5, key="f_biz_growth")
            min_quality = fc3.number_input("质量分 >=", 0, 100, 0, step=5, key="f_quality")
            min_flow = fc4.number_input("资金热度 >=", 0, 100, 0, step=5, key="f_flow")

            # 应用阈值
            df = df[
                (df["avg_biz_relevance"].fillna(0) >= min_biz_rel) &
                (df["avg_biz_growth"].fillna(0) >= min_biz_growth) &
                (df["avg_quality_score"].fillna(0) >= min_quality) &
                (df["avg_flow_score"].fillna(0) >= min_flow)
            ]

        # 应用排序
        col_map = {
            "综合评分": "overall_score",
            "业务相关性": "avg_biz_relevance",
            "成长性": "avg_biz_growth",
            "质量分": "avg_quality_score",
            "资金热度": "avg_flow_score",
            "个股数量": "stock_count",
        }
        sort_col = col_map.get(sort_choice, "overall_score")
        ascending = sort_order == "升序"
        if sort_col in df.columns:
            df = df.sort_values(by=sort_col, ascending=ascending, na_position="last")

    return df


def _render_theme_rows(df: pd.DataFrame):
    st.caption(f"共 {len(df)} 个题材。每行展示当前库内结构覆盖，不包含实时行情。")

    # 预计算所有题材新鲜度
    from datetime import datetime
    from core.data_freshness import compute_theme_freshness
    import core.database as db

    # 从 freshness_raw_data 获取 last_news（get_theme_summary_with_dimensions 不含此字段）
    freshness_raw = db.get_freshness_raw_data()
    news_map: dict[str, datetime | None] = {}
    for r in freshness_raw:
        ln = None
        if r.get("last_news"):
            try:
                ln = datetime.strptime(str(r["last_news"])[:19], "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                pass
        news_map[r["theme_name"]] = ln

    freshness_map: dict[str, dict] = {}
    for _, row in df.iterrows():
        theme_name = row["theme_name"]
        last_update_str = row.get("last_updated")
        last_update = None
        if last_update_str and str(last_update_str) != "-":
            try:
                last_update = datetime.strptime(str(last_update_str)[:19], "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                pass
        last_news = news_map.get(theme_name)
        f = compute_theme_freshness(theme_name, last_update, last_news)
        freshness_map[theme_name] = {"score": f.overall_score, "level": f.level}

    for _, row in df.iterrows():
        theme_name = row["theme_name"]
        f_info = freshness_map.get(theme_name, {"score": 0, "level": "过期"})
        _render_theme_row(row, f_info)


def _render_theme_row(row: pd.Series, freshness_info: dict):
    theme_name = row["theme_name"]
    score = row.get("overall_score")
    score_text = "-" if pd.isna(score) else str(int(score))
    updated_at = str(row.get("last_updated") or "-")[:10]
    quality_summary = row.get("quality_summary")
    f_score = freshness_info.get("score", 0)

    with st.container(border=True):
        cols = st.columns([2.2, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7, 1.4])
        cols[0].markdown(f"**{esc(theme_name)}**")
        if quality_summary and not pd.isna(quality_summary):
            cols[0].caption(str(quality_summary))
        cols[1].metric("节点", row["node_count"])
        cols[2].metric("个股", row["stock_count"])
        cols[3].metric("高重要", row["high_importance_count"])
        cols[4].metric("评分", score_text)
        cols[5].markdown(f"{badge(updated_at, 'slate')}", unsafe_allow_html=True)
        cols[6].markdown(freshness_badge(f_score), unsafe_allow_html=True)

        action_cols = cols[7].columns(4)
        # P2-10: 关注按钮
        import tasks.watchlist as wl
        is_watched = wl.is_watched("theme", theme_name)
        watch_icon = "取消关注" if is_watched else "关注"
        if action_cols[0].button(watch_icon, key=f"wt_{theme_name}", width="stretch"):
            if is_watched:
                wl.remove_from_watchlist("theme", theme_name)
            else:
                wl.add_to_watchlist("theme", theme_name)
            st.rerun()
        if action_cols[1].button("图谱", key=f"goto_{theme_name}", help="查看产业链图谱"):
            st.session_state.current_page = "产业链图谱"
            st.session_state["nav_theme"] = theme_name
            st.rerun()
        if action_cols[2].button("更新", key=f"update_{theme_name}", help="AI 更新此题材"):
            st.session_state["updating_theme"] = theme_name
            st.rerun()
        if action_cols[3].button("删除", key=f"delete_{theme_name}", help="删除此题材"):
            st.session_state["confirm_delete"] = theme_name
            st.rerun()


def _render_delete_confirm():
    if "confirm_delete" not in st.session_state:
        return

    theme_name = st.session_state["confirm_delete"]
    st.warning(f"确认删除题材「{theme_name}」吗？此操作不可撤销。")
    yes, no, _ = st.columns([1, 1, 8])
    if yes.button("确认删除", type="primary"):
        count = db.delete_theme(theme_name)
        del st.session_state["confirm_delete"]
        st.success(f"已删除「{theme_name}」，共 {count} 条记录")
        st.rerun()
    if no.button("取消"):
        del st.session_state["confirm_delete"]
        st.rerun()
