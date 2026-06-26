"""
AI 生成页 — 输入题材名，AI 自动分析产业链结构并生成个股数据
"""
import os
import time

import streamlit as st
import pandas as pd

import core.database as db
import tasks.task_manager as tm
from core.ai_client import generate_theme_analysis, flatten_chains, load_api_config, save_api_config
from config import DATA_DIR, get_logger

_log = get_logger("ai_generate")

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"

# 持久化配置文件路径（仅用于检查文件是否存在）
_CONFIG_FILE = os.path.join(DATA_DIR, "api_config.json")


_AI_GEN_PREFIX = "ai_gen_"


def render():
    # P2-13: 移除 Emoji 标题，统一使用研究工作台风格
    st.subheader("AI 生成产业链分析")

    _check_ai_gen_tasks()

    # 如果已有生成结果 → 显示编辑器
    if "ai_rows" in st.session_state and "ai_theme" in st.session_state:
        _render_editor()
    else:
        _render_input()


def _render_input():
    """第一步：输入题材 + API 配置 → 调用 LLM 生成"""
    saved_key, saved_url, saved_model = load_api_config(st.session_state.get)

    # 检查本地是否有已保存的配置
    has_saved_file = os.path.exists(_CONFIG_FILE)

    with st.expander(
        f"API 配置 {'— 已保存' if has_saved_file else ''}",
        expanded=(not saved_key),
    ):
        api_key = st.text_input(
            "API Key", value=saved_key, type="password", placeholder="sk-...",
            help="DeepSeek 在 platform.deepseek.com 获取；OpenAI 在 platform.openai.com 获取",
        )
        base_url = st.text_input(
            "API Base URL", value=saved_url, placeholder=DEFAULT_BASE_URL,
        )
        model = st.text_input(
            "模型名称", value=saved_model, placeholder=DEFAULT_MODEL,
        )

        col_save, col_status = st.columns([1, 3])
        if col_save.button("保存配置", width="stretch"):
            save_api_config(api_key.strip(), base_url.strip(), model.strip(), st.session_state)
            st.success("配置已保存，下次打开无需重新输入")
            st.rerun()

        if has_saved_file:
            col_status.caption("已从本地加载保存的配置")
        else:
            col_status.caption("保存后，关闭浏览器再打开也无需重新输入")

    st.divider()

    # 检查是否从题材列表的"更新"按钮跳转过来
    prefill = st.session_state.pop("ai_prefill_theme", "")

    col1, col2 = st.columns([3, 1])
    theme_name = col1.text_input(
        "📝 题材名称",
        value=prefill,
        placeholder="例如：固态电池、人形机器人、低空经济…",
    )
    extra_hint = st.text_area(
        "额外提示（可选）",
        placeholder="例如：重点关注上游材料环节 / 聚焦科创板标的 / 创业板为主…",
        height=68,
    )

    # P2-13: Serenity 四维分析维度选择器
    use_serenity = False
    bottleneck_hint = institutional_hint = value_hint = valuation_hint = "自动推断"

    with st.expander("Serenity 四维深度分析（可选）", expanded=False):
        st.caption("基于白毛股神分析框架，为生成结果附加产业链深度评估")
        use_serenity = st.checkbox("启用四维分析", value=False,
                                   help="在生成提示词中加入卡脖子/机构行为/长线价值/估值重置维度")
        if use_serenity:
            serenity_cols = st.columns(4)
            with serenity_cols[0]:
                bottleneck_hint = st.selectbox(
                    "产业链位置", ["自动推断", "上游（材料/设备/EDA）", "中游（制造/封装）", "下游（应用/终端）"],
                    help="上游卡脖子程度最高，得分最高"
                )
            with serenity_cols[1]:
                institutional_hint = st.selectbox(
                    "资金面关注", ["自动评估", "高关注（北向+融资双增）", "中等关注", "低关注"],
                )
            with serenity_cols[2]:
                value_hint = st.selectbox(
                    "基本面深度", ["自动评估", "深度分析ROE/毛利率/护城河", "基础财务概览"],
                )
            with serenity_cols[3]:
                valuation_hint = st.selectbox(
                    "估值框架", ["自动判断", "范式转移（高增速不适用PE）", "周期分析", "价值陷阱筛查"],
                )

    if not col2.button("生成分析", type="primary", width="stretch"):
        st.info("输入题材名称，点击「生成分析」")
        return

    # 校验
    if not theme_name.strip():
        st.error("请输入题材名称")
        return
    if not api_key.strip():
        st.error("请输入 API Key")
        return

    # 保存 API 配置，下次不用重新输入
    save_api_config(api_key.strip(), base_url.strip(), model.strip(), st.session_state)

    # 提交后台任务 - 融入 Serenity 四维提示
    task_id = f"{_AI_GEN_PREFIX}{theme_name.strip()}"

    # 构造增强的 extra_hint
    enhanced_hint = extra_hint.strip()
    if use_serenity:
        serenity_parts = []
        if bottleneck_hint != "自动推断":
            serenity_parts.append(f"卡脖子位置: {bottleneck_hint}")
        if institutional_hint != "自动评估":
            serenity_parts.append(f"资金面: {institutional_hint}")
        if value_hint != "自动评估":
            serenity_parts.append(f"基本面: {value_hint}")
        if valuation_hint != "自动判断":
            serenity_parts.append(f"估值框架: {valuation_hint}")
        if serenity_parts:
            serenity_prompt = "【Serenity四维分析】" + "；".join(serenity_parts) + "。请从产业链不可替代性、机构资金行为、长线价值、估值重置四个维度深度评估每个标的。"
            enhanced_hint = f"{enhanced_hint}\n\n{serenity_prompt}" if enhanced_hint else serenity_prompt

    ok = tm.submit(
        task_id,
        _run_ai_gen,
        theme_name.strip(), enhanced_hint,
        api_key.strip(), base_url.strip() or DEFAULT_BASE_URL, model.strip() or DEFAULT_MODEL,
    )
    if ok:
        st.rerun()
    else:
        st.warning("该题材正在生成中，请等待完成")


def _render_editor():
    """第二步：审核编辑 + 导入数据库"""
    rows = st.session_state.get("ai_rows", [])
    theme_name = st.session_state.get("ai_theme", "")

    st.subheader(f"{theme_name} — 共 {len(rows)} 条记录，请审核后导入")

    # 题材质量评分
    quality = st.session_state.get("ai_theme_quality", {})
    if quality:
        q_cols = st.columns(5)
        q_cols[0].metric("综合", quality.get("overall_score", "?"))
        q_cols[1].metric("广度", quality.get("breadth", "?"))
        q_cols[2].metric("事件密度", quality.get("event_density", "?"))
        q_cols[3].metric("资金确认", quality.get("capital_flow", "?"))
        q_cols[4].metric("持续性", quality.get("sustainability", "?"))
        if quality.get("summary"):
            st.caption(quality["summary"])

    df = pd.DataFrame(rows)

    edited = st.data_editor(
        df,
        column_config={
            "theme_name": "题材",
            "level1": "一级环节",
            "level2": "二级方向",
            "level3": "三级方向",
            "stock_code": "股票代码",
            "stock_name": "股票名称",
            "market_type": st.column_config.SelectboxColumn(
                "市场类型", options=["主板", "创业板", "科创板", "北交所"]
            ),
            "role": "公司角色",
            "logic_summary": st.column_config.TextColumn("核心逻辑", width="large"),
            "market_position": "市场地位",
            "market_share": "市占率",
            "customers": "客户",
            "importance": st.column_config.SelectboxColumn(
                "重要性", options=["高", "中", "低"]
            ),
            "source": "信息来源",
            "notes": "备注",
        },
        width="stretch",
        num_rows="dynamic",
        hide_index=True,
    )

    st.divider()

    col_a, col_b = st.columns(2)

    if col_a.button("审核通过，导入数据库", type="primary", width="stretch"):
        try:
            n = db.replace_theme(theme_name, edited, st.session_state.get("ai_theme_quality", {}))
            _clear_cache()
            st.success(f"导入成功，共 {n} 条记录")
            # 触发后台自动验证
            from views.analysis_draft import _trigger_verification
            _trigger_verification(theme_name)
            st.rerun()
        except Exception as e:
            st.error(f"导入失败: {e}")

    if col_b.button("放弃本次生成", width="stretch"):
        _clear_cache()
        st.rerun()

    # 快速统计
    st.caption(
        f"一级环节: {edited['level1'].nunique()}  |  "
        f"二级方向: {edited['level2'].nunique()}  |  "
        f"三级方向: {edited['level3'].nunique()}  |  "
        f"个股: {edited['stock_code'].nunique()}  |  "
        f"核心: {(edited['tier'] == '核心').sum() if 'tier' in edited.columns else '?'}  |  "
        f"次级: {(edited['tier'] == '次级').sum() if 'tier' in edited.columns else '?'}  |  "
        f"观察: {(edited['tier'] == '观察').sum() if 'tier' in edited.columns else '?'}"
    )


def _clear_cache():
    st.session_state.pop("ai_rows", None)
    st.session_state.pop("ai_theme", None)
    st.session_state.pop("ai_theme_quality", None)


# ---- 后台任务 ----


def _run_ai_gen(theme_name: str, extra_hint: str, api_key: str, base_url: str, model: str) -> dict:
    """后台线程：AI 生成产业链分析"""
    task_id = f"{_AI_GEN_PREFIX}{theme_name}"
    tm.update_progress(task_id, 0.2, "搜索产业链信息…")
    raw = generate_theme_analysis(theme_name, api_key, base_url, model, extra_hint)
    tm.update_progress(task_id, 0.7, "解析结果…")
    rows, theme_quality = flatten_chains(raw)
    return {"rows": rows, "theme_quality": theme_quality, "theme_name": theme_name}


def _check_ai_gen_tasks() -> None:
    """检查 AI 生成后台任务，完成时切换到编辑器"""
    all_tasks = tm.get_all()
    for tid, task in all_tasks.items():
        if not tid.startswith(_AI_GEN_PREFIX):
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
                status_area.spinner(f"正在分析产业链… {msg}")
                progress_area.progress(p, text=f"{msg} ({int(p * 100)}%)")
                time.sleep(1.5)
            status_area.empty()
            progress_area.empty()
            st.rerun()
        if task["status"] == "completed":
            result = task["result"] or {}
            rows = result.get("rows", [])
            if not rows:
                st.warning("未返回有效数据，请重试")
            else:
                st.session_state["ai_rows"] = rows
                st.session_state["ai_theme_quality"] = result.get("theme_quality", {})
                st.session_state["ai_theme"] = result["theme_name"]
            tm.clear(tid)
            st.rerun()
        if task["status"] == "failed":
            st.error(f"AI 生成失败：{task['error']}")
            if st.button("重试", key=f"retry_{tid}"):
                tm.clear(tid)
                st.rerun()
