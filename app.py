"""
A 股热点题材产业链梳理工具 — 主入口
"""
import streamlit as st

from ui_components import apply_global_style
import tasks.task_manager as tm


st.set_page_config(
    page_title="A股热点题材产业链梳理",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


NAV_GROUPS = [
    ("研究流程", [
        ("热点题材", "🔥"),
        ("发酵观察", "🌱"),
        ("分析草稿", "🧩"),
    ]),
    ("题材库", [
        ("题材列表", "📋"),
        ("产业链图谱", "🌳"),
        ("题材对比", "📊"),
    ]),
    ("查询工具", [
        ("细分详情", "🔍"),
        ("个股详情", "📈"),
    ]),
    ("系统", [
        ("AI 生成", "🤖"),
        ("回测验证", "🧪"),
    ]),
]
PAGE_OPTIONS = [item for _, items in NAV_GROUPS for item in items]
PAGE_NAMES = {name for name, _ in PAGE_OPTIONS}


def _render_sidebar(current_page: str, is_onboarding: bool = False) -> None:
    with st.sidebar:
        st.markdown(
            """
<div class="sidebar-brand">
  <div class="sidebar-logo">A</div>
  <div>
    <div class="sidebar-title">题材研究台</div>
    <div class="sidebar-subtitle">A股产业链分析工具</div>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )

        if is_onboarding:
            # 引导期间：导航保持可用，顶部提示 + 跳过入口
            st.markdown(
                '<div style="text-align:center;padding:4px 0;color:#FF6A00;font-size:0.82rem;font-weight:600;">'
                '正在新手引导中</div>',
                unsafe_allow_html=True,
            )
            if st.button("跳过引导 →", key="nav_skip_onboarding", width="stretch"):
                st.session_state.onboarding_complete = True
                st.session_state.onboarding_trigger = ""
                st.rerun()
            st.divider()

        # ---- 导航按钮（引导/非引导均渲染） ----
        for group_name, pages in NAV_GROUPS:
            st.markdown(f'<div class="nav-group-title">{group_name}</div>', unsafe_allow_html=True)
            for page_name, icon in pages:
                is_active = page_name == current_page
                label = f"{icon}  {page_name}"
                if st.button(
                    label,
                    key=f"nav_{page_name}",
                    width="stretch",
                    type="primary" if is_active else "secondary",
                ):
                    if is_onboarding:
                        # 引导期间点击导航 → 退出引导，跳转到目标页
                        st.session_state.onboarding_complete = True
                        st.session_state.onboarding_trigger = ""
                    st.session_state.current_page = page_name
                    st.rerun()

        # ---- 新手指引入口（仅非引导期间显示） ----
        if not is_onboarding:
            st.divider()
            if st.button("❓ 新手指引", key="nav_onboarding", width="stretch"):
                st.session_state.onboarding_step = 1
                st.session_state.onboarding_complete = False
                st.session_state.onboarding_trigger = "manual"
                st.rerun()

        # ---- 后台任务指示器 ----
        running = tm.running_count()
        all_tasks = tm.get_all()
        if running:
            st.divider()
            st.markdown(
                f'<div style="font-size:0.78rem;color:#9BA3B0;margin-bottom:6px;">⏳ {running} 个任务运行中</div>',
                unsafe_allow_html=True,
            )
            for tid, t in all_tasks.items():
                if t.get("status") != "running":
                    continue
                pct = int(t.get("progress", 0) * 100)
                msg = t.get("progress_msg") or tid
                st.progress(t.get("progress", 0), text=f"{msg} ({pct}%)")

        # ---- P0-3: 数据新鲜度仪表盘 ----
        # 引导期间跳过侧边栏重查询，大幅减少卡顿
        if not is_onboarding:
            _render_freshness_panel()

        # ---- P2-10: 我的关注列表 ----
        if not is_onboarding:
            _render_watchlist_panel()

        # ---- 主题切换 ----
        st.divider()
        theme_labels = {"dark": "🌙 暗色", "light": "☀️ 亮色"}
        current_theme = st.session_state.get("theme", "dark")
        chosen = st.selectbox(
            "主题",
            options=list(theme_labels.keys()),
            format_func=lambda k: theme_labels[k],
            index=0 if current_theme == "dark" else 1,
            key="theme_selector",
            label_visibility="collapsed",
        )
        if chosen != current_theme:
            st.session_state.theme = chosen
            st.rerun()


def _render_watchlist_panel() -> None:
    """P2-10: 侧边栏渲染「我的关注」列表"""
    import tasks.watchlist as wl

    items = wl.get_watchlist()
    if not items:
        return

    st.divider()
    st.markdown(
        '<div class="nav-group-title">我的关注</div>',
        unsafe_allow_html=True,
    )

    for item in items:
        item_type = item.get("item_type", "")
        item_id = item.get("item_id", "")
        notes = item.get("notes", "") or ""
        has_update = item.get("has_update", 0)

        prefix = "T:" if item_type == "theme" else "S:"
        label = f"{prefix}{item_id}"
        if notes:
            label += f" ({notes})"
        if has_update:
            label += " [UPD]"

        if st.button(
            label,
            key=f"wl_{item_type}_{item_id}",
            width="stretch",
        ):
            # 点击跳转
            if item_type == "theme":
                st.session_state.selected_theme = item_id
                st.session_state.current_page = "细分详情"
            else:
                st.session_state["nav_stock_code"] = item_id
                st.session_state.current_page = "个股详情"
            st.rerun()


def _render_freshness_panel() -> None:
    """在侧边栏渲染数据新鲜度仪表盘（轻量查询，实时计算）"""
    import core.database as db
    from core.data_freshness import compute_global_freshness, compute_theme_freshness
    from datetime import datetime

    # 只在非任务页面渲染完整面板；后台任务运行时已由 _render_sidebar 展示了
    raw = db.get_freshness_raw_data()
    if not raw:
        return

    theme_count = len(raw)
    parsed: list[dict] = []
    for r in raw:
        last_update = None
        if r.get("last_update"):
            try:
                last_update = datetime.strptime(r["last_update"][:19], "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                pass
        last_news = None
        if r.get("last_news"):
            try:
                last_news = datetime.strptime(r["last_news"][:19], "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                pass
        parsed.append({
            "theme_name": r["theme_name"],
            "last_update": last_update,
            "last_news": last_news,
        })

    gf = compute_global_freshness(parsed)
    from ui_components import render_freshness_dashboard
    render_freshness_dashboard(gf)


def _main() -> None:
    """主流程：判断是否进入引导，否则正常渲染页面"""

    # ---- 初始化 session_state ----
    if "current_page" not in st.session_state:
        st.session_state.current_page = "题材列表"
    if "onboarding_step" not in st.session_state:
        st.session_state.onboarding_step = 1
    if "theme" not in st.session_state:
        st.session_state.theme = "dark"

    # ---- 应用主题 CSS（Python 端控制，不依赖 JS） ----
    apply_global_style(st.session_state.theme)

    # ---- 判断是否需要启动引导 ----
    from tasks.onboarding import check_should_onboard
    trigger_manual = st.session_state.get("onboarding_trigger") == "manual"

    if trigger_manual or not st.session_state.get("onboarding_complete", False):
        should_onboard = trigger_manual or check_should_onboard()
        if should_onboard:
            _render_onboarding_flow()
            return

    # ---- 正常页面流程 ----
    page = st.session_state.current_page
    if page == "\u9884\u6d4b\u53d1\u9175":
        page = "发酵观察"
    if page not in PAGE_NAMES:
        page = "题材列表"
    st.session_state.current_page = page

    _render_sidebar(page, is_onboarding=False)

    if page == "题材列表":
        from views.theme_list import render
        render()
    elif page == "热点题材":
        from views.hot_topics import render
        render()
    elif page == "分析草稿":
        from views.analysis_draft import render
        render()
    elif page == "发酵观察":
        from views.predict import render
        render()
    elif page == "产业链图谱":
        from views.theme_tree import render
        render()
    elif page == "题材对比":
        from views.theme_compare import render
        render()
    elif page == "细分详情":
        from views.segment_detail import render
        render()
    elif page == "个股详情":
        from views.stock_detail import render
        render()
    elif page == "AI 生成":
        from views.ai_generate import render
        render()
    elif page == "回测验证":
        from views.backtest_view import render
        render()


def _render_onboarding_flow() -> None:
    """渲染引导流程：隐藏正常导航，显示 3 步引导"""
    from tasks.onboarding import render_onboarding
    step = st.session_state.get("onboarding_step", 1)

    # 引导期间侧边栏简化
    _render_sidebar("", is_onboarding=True)

    # 渲染引导步骤
    prefix = f"ob_{step}_"
    next_step = render_onboarding(step, reset_key_prefix=prefix)

    if next_step == 0:
        # 引导完成，恢复正常页面
        st.session_state.onboarding_complete = True
        st.session_state.onboarding_trigger = ""
        st.rerun()
    elif next_step is not None:
        st.session_state.onboarding_step = next_step
        st.rerun()


if __name__ == "__main__":
    _main()
else:
    _main()
