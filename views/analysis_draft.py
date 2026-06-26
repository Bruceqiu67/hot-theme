"""
分析草稿页 — 三栏工作台：产业链树、节点详情、个股映射。
"""
from __future__ import annotations

import time

import streamlit as st

import core.database as db
import tasks.task_manager as tm
from core.ai_client import generate_analysis_draft, load_api_config
from ui_components import badge, esc, level_tone, metric_strip, page_header
from core.stock_verifier  import (    VerificationStatus,
    verify_stocks_batch,
    verification_result_to_db_json,
    get_verification_stats as verifier_stats,
)


def render():
    page_header(
        "分析草稿",
        "预览、编辑、删除并确认入库两阶段题材分析结果。",
        eyebrow="Analysis Draft",
        meta="确认前不会写入正式题材库",
    )

    drafts = db.get_latest_analysis_drafts(limit=50)
    if not drafts:
        st.info("暂无分析草稿。请先在「热点题材」或「发酵观察」页生成草稿。")
        return

    row = _select_draft(drafts)
    if not row:
        st.warning("草稿不存在")
        return

    _check_regen_tasks()
    _check_verify_tasks()

    draft = row["draft"]
    _render_summary(row, draft)
    _render_toolbar(row, draft)
    _render_editor(row, draft)


def _select_draft(drafts: list[dict]) -> dict | None:
    active_id = st.session_state.get("active_draft_id")
    draft_ids = [item["draft_id"] for item in drafts]
    if active_id not in draft_ids:
        active_id = draft_ids[0]

    options = {
        item["draft_id"]: f"#{item['draft_id']} {item['topic_name']} · {item['status']} · {item['updated_at']}"
        for item in drafts
    }
    selected_id = st.selectbox(
        "选择草稿",
        draft_ids,
        index=draft_ids.index(active_id),
        format_func=lambda x: options[x],
    )
    st.session_state["active_draft_id"] = selected_id
    return db.get_analysis_draft(selected_id)


def _render_summary(row: dict, draft: dict):
    nodes = draft.get("chain_nodes", [])
    stocks = draft.get("stocks", [])
    metric_strip([
        ("产业链节点", len(nodes), row["topic_name"]),
        ("映射个股", len(stocks), "全部待人工核验"),
        ("草稿状态", row["status"], row["updated_at"]),
    ])


def _render_toolbar(row: dict, draft: dict):
    with st.container(border=True):
        title, actions = st.columns([3, 3])
        with title:
            st.markdown(f"### {esc(row['topic_name'])}")
            st.markdown(
                badge(row["status"], level_tone(row["status"]))
                + badge(f"创建 {row['created_at']}", "slate")
                + badge(f"更新 {row['updated_at']}", "slate"),
                unsafe_allow_html=True,
            )
        with actions:
            c1, c2, c3, c4 = st.columns(4)
            if c1.button("保存", width="stretch"):
                db.update_analysis_draft(row["draft_id"], draft, "draft")
                st.success("草稿已保存")
                st.rerun()
            if c2.button("确认入库", type="primary", width="stretch"):
                try:
                    count = db.confirm_analysis_draft(row["draft_id"])
                    st.success(f"已写入正式题材库，共 {count} 条个股记录")
                    # 触发后台自动验证
                    _trigger_verification(row["topic_name"])
                    st.rerun()
                except Exception as exc:
                    st.error(f"确认入库失败：{exc}")
            if c3.button("重新生成", width="stretch"):
                _regenerate(row)
            if c4.button("废弃", width="stretch"):
                db.set_analysis_draft_status(row["draft_id"], "discarded")
                st.warning("草稿已废弃")
                st.rerun()


def _render_editor(row: dict, draft: dict):
    nodes = draft.get("chain_nodes", [])
    if not nodes:
        st.warning("草稿中没有产业链节点")
        return

    selected_key = st.session_state.get(f"draft_node_{row['draft_id']}")
    node_keys = [_node_key(node) for node in nodes]
    if selected_key not in node_keys:
        selected_key = node_keys[0]

    current_node = _find_node(nodes, selected_key)
    if not current_node:
        st.warning("当前节点不存在")
        return

    left, middle, right = st.columns([1.1, 1.6, 2.25])
    with left:
        _render_node_tree(row, draft, nodes, selected_key)
    with middle:
        _render_node_detail(row, draft, current_node)
    with right:
        _render_stocks(row, draft, current_node)


def _render_node_tree(row: dict, draft: dict, nodes: list[dict], selected_key: str):
    with st.container(border=True):
        st.markdown("### 产业链树")
        for idx, node in enumerate(nodes, start=1):
            key = _node_key(node)
            label = _node_label(node, idx)
            if st.button(
                label,
                key=f"select_{row['draft_id']}_{key}",
                width="stretch",
                type="primary" if key == selected_key else "secondary",
            ):
                st.session_state[f"draft_node_{row['draft_id']}"] = key
                st.rerun()
        st.divider()
        if st.button("删除当前节点", key=f"delete_node_{row['draft_id']}", width="stretch"):
            _delete_node(row, draft, selected_key)


def _render_node_detail(row: dict, draft: dict, node: dict):
    with st.container(border=True):
        st.markdown("### 节点详情")
        st.caption("编辑后点击顶部保存草稿。")
        st.text_input("一级环节", value=node.get("level1", ""), key=f"node_l1_{row['draft_id']}_{_node_key(node)}", disabled=True)
        st.text_input("二级方向", value=node.get("level2", ""), key=f"node_l2_{row['draft_id']}_{_node_key(node)}", disabled=True)
        st.text_input("三级细分", value=node.get("level3", ""), key=f"node_l3_{row['draft_id']}_{_node_key(node)}", disabled=True)
        node["node_description"] = st.text_area(
            "节点解释",
            value=node.get("node_description", ""),
            height=120,
            key=f"node_desc_{row['draft_id']}_{_node_key(node)}",
        )
        node["why_it_matters"] = st.text_area(
            "重要性说明",
            value=node.get("why_it_matters", ""),
            height=120,
            key=f"node_why_{row['draft_id']}_{_node_key(node)}",
        )
        node["importance"] = st.selectbox(
            "节点重要性",
            ["核心", "重要", "观察"],
            index=["核心", "重要", "观察"].index(
                node.get("importance", "观察") if node.get("importance") in ["核心", "重要", "观察"] else "观察"
            ),
            key=f"node_imp_{row['draft_id']}_{_node_key(node)}",
        )


def _render_stocks(row: dict, draft: dict, node: dict):
    with st.container(border=True):
        st.markdown("### 个股映射")
        stocks = [
            stock for stock in draft.get("stocks", [])
            if _stock_node_key(stock) == _node_key(node)
        ]
        st.caption(f"当前节点 {len(stocks)} 只个股，字段默认待人工核验。")
        if not stocks:
            st.info("当前节点暂无个股映射。")
            return

        for stock in stocks:
            global_idx = draft["stocks"].index(stock)
            _render_stock_editor(row, draft, stock, global_idx)


def _render_stock_editor(row: dict, draft: dict, stock: dict, global_idx: int):
    with st.container(border=True):
        title_cols = st.columns([2.2, 1, 0.8])
        title_cols[0].markdown(f"**{esc(stock.get('stock_name', ''))}** `{esc(stock.get('stock_code', ''))}`")
        title_cols[1].markdown(badge(stock.get("importance", "观察"), level_tone(stock.get("importance", "观察"))), unsafe_allow_html=True)
        if title_cols[2].button("删除", key=f"delete_stock_{row['draft_id']}_{global_idx}", width="stretch"):
            draft["stocks"].pop(global_idx)
            db.update_analysis_draft(row["draft_id"], draft, "draft")
            st.rerun()

        c1, c2 = st.columns(2)
        stock["role"] = c1.text_input("角色", value=stock.get("role", ""), key=f"role_{row['draft_id']}_{global_idx}")
        stock["products"] = c2.text_input("产品", value=stock.get("products", ""), key=f"prod_{row['draft_id']}_{global_idx}")
        stock["logic_summary"] = st.text_area("个股逻辑", value=stock.get("logic_summary", ""), height=80, key=f"logic_{row['draft_id']}_{global_idx}")
        c3, c4, c5 = st.columns(3)
        stock["market_position"] = c3.text_input("市场地位", value=stock.get("market_position", "待核验"), key=f"pos_{row['draft_id']}_{global_idx}")
        stock["market_share"] = c4.text_input("市占率", value=stock.get("market_share", "待核验"), key=f"share_{row['draft_id']}_{global_idx}")
        stock["customers"] = c5.text_input("客户", value=stock.get("customers", "待核验"), key=f"cust_{row['draft_id']}_{global_idx}")
        stock["risk_note"] = st.text_area("风险/备注", value=stock.get("risk_note", ""), height=68, key=f"risk_{row['draft_id']}_{global_idx}")
        stock["importance"] = st.selectbox(
            "重要性",
            ["核心", "重要", "观察", "泛相关"],
            index=["核心", "重要", "观察", "泛相关"].index(
                stock.get("importance", "观察") if stock.get("importance") in ["核心", "重要", "观察", "泛相关"] else "观察"
            ),
            key=f"stock_imp_{row['draft_id']}_{global_idx}",
        )
        stock["verification_status"] = "待人工核验"


def _delete_node(row: dict, draft: dict, selected_key: str):
    draft["chain_nodes"] = [node for node in draft.get("chain_nodes", []) if _node_key(node) != selected_key]
    draft["stocks"] = [stock for stock in draft.get("stocks", []) if _stock_node_key(stock) != selected_key]
    db.update_analysis_draft(row["draft_id"], draft, "draft")
    st.success("节点及其个股已删除")
    st.rerun()


_REGEN_PREFIX = "draft_regen_"
_VERIFY_PREFIX = "stock_verify_"


def _trigger_verification(theme_name: str):
    """提交后台个股验证任务"""
    task_id = f"{_VERIFY_PREFIX}{theme_name}"
    ok = tm.submit(task_id, _run_verification, theme_name)
    if not ok:
        _log_verify("验证任务已在运行中: %s", theme_name)


def _run_verification(theme_name: str) -> dict:
    """后台线程：对指定题材的所有个股执行自动验证"""
    import json
    task_id = f"{_VERIFY_PREFIX}{theme_name}"
    task = tm.get(task_id)
    task_state = task if task else None

    # 获取题材下所有个股
    stocks = db.get_theme_stocks(theme_name)
    if not stocks:
        return {"theme_name": theme_name, "verified": 0, "stats": {}}

    # 批量验证
    results = verify_stocks_batch(
        [dict(s) for s in stocks],
        theme_name=theme_name,
        task_state=task_state,
    )

    # 写入数据库
    updates = []
    verification_map = verification_result_to_db_json(results)
    for stock_code, v_data in verification_map.items():
        updates.append({
            "stock_code": stock_code,
            "theme_name": theme_name,
            "verification_status": v_data["overall_status"],
            "verification_details": json.dumps(v_data, ensure_ascii=False),
        })

    count = db.batch_update_stock_verification(updates)
    stats = verifier_stats(results)

    return {
        "theme_name": theme_name,
        "verified": count,
        "stats": stats,
    }


def _log_verify(msg, *args):
    """验证日志"""
    try:
        from config import get_logger
        get_logger("stock_verifier.ui").info(msg, *args)
    except Exception:
        pass


def _check_verify_tasks() -> None:
    """检查个股验证后台任务（在 render 中调用）"""
    all_tasks = tm.get_all()
    for tid, task in all_tasks.items():
        if not tid.startswith(_VERIFY_PREFIX):
            continue
        if task["status"] == "running":
            progress_area = st.empty()
            while True:
                t = tm.get(tid)
                if t is None or t["status"] != "running":
                    break
                p = t.get("progress", 0)
                msg = t.get("progress_msg", "")
                progress_area.progress(p, text=f"自动验证中… {msg} ({int(p * 100)}%)")
                time.sleep(1)
            progress_area.empty()
            st.rerun()
        if task["status"] == "completed":
            result = task.get("result") or {}
            stats = result.get("stats", {})
            tm.clear(tid)
            st.success(
                f"「{result.get('theme_name', '')}」自动验证完成："
                f"{stats.get('verified_fields', 0)}/{stats.get('total_fields', 0)} 字段验证，"
                f"验证率 {stats.get('verified_rate', 0)}%"
            )
            st.rerun()
        if task["status"] == "failed":
            st.error(f"验证失败：{task.get('error')}")
            if st.button("关闭", key=f"dismiss_verify_{tid}"):
                tm.clear(tid)
                st.rerun()


def _regenerate(row: dict):
    """提交后台重新生成草稿任务"""
    api_key, base_url, model = load_api_config(st.session_state.get)
    if not api_key:
        st.error("未配置 API Key")
        return
    draft_id = row["draft_id"]
    task_id = f"{_REGEN_PREFIX}{draft_id}"
    ok = tm.submit(task_id, _run_regen, row, api_key, base_url, model)
    if ok:
        st.rerun()
    else:
        st.warning("该草稿正在重新生成中")


def _run_regen(row: dict, api_key: str, base_url: str, model: str) -> dict:
    """后台线程：重新生成草稿"""
    draft_id = row["draft_id"]
    task_id = f"{_REGEN_PREFIX}{draft_id}"

    topic = db.get_hot_topic_candidate(row.get("topic_id")) if row.get("topic_id") else None
    if not topic:
        raise RuntimeError("找不到原始候选题材")

    evidence = db.get_topic_evidence(row["topic_id"])
    draft = generate_analysis_draft(topic, evidence, api_key, base_url, model)
    db.update_analysis_draft(draft_id, draft, "draft")
    return {"draft_id": draft_id, "topic_name": row["topic_name"]}


def _check_regen_tasks() -> None:
    """检查草稿重新生成后台任务"""
    all_tasks = tm.get_all()
    for tid, task in all_tasks.items():
        if not tid.startswith(_REGEN_PREFIX):
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
                status_area.spinner(f"正在重新生成草稿… {msg}")
                progress_area.progress(p, text=f"{msg} ({int(p * 100)}%)")
                time.sleep(1.5)
            status_area.empty()
            progress_area.empty()
            st.rerun()
        if task["status"] == "completed":
            result = task["result"] or {}
            tm.clear(tid)
            st.success(f"「{result['topic_name']}」草稿已重新生成")
            st.rerun()
        if task["status"] == "failed":
            st.error(f"重新生成失败：{task['error']}")
            if st.button("关闭", key=f"dismiss_{tid}"):
                tm.clear(tid)
                st.rerun()


def _node_label(node: dict, idx: int) -> str:
    parts = [node.get("level1", ""), node.get("level2", ""), node.get("level3", "")]
    parts = [part for part in parts if part]
    return f"{idx}. " + " / ".join(parts)


def _node_key(node: dict) -> str:
    return "|".join([node.get("level1", ""), node.get("level2", ""), node.get("level3", "")])


def _stock_node_key(stock: dict) -> str:
    return "|".join([stock.get("level1", ""), stock.get("level2", ""), stock.get("level3", "")])


def _find_node(nodes: list[dict], key: str) -> dict | None:
    for node in nodes:
        if _node_key(node) == key:
            return node
    return None
