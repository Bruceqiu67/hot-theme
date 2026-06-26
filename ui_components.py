"""
Shared UI helpers for the research workbench — Bloomberg Terminal style.
"""
from __future__ import annotations

import html
from typing import Iterable

import streamlit as st


TONE_COLORS = {
    "default": ("#1E2635", "#F0F2F5", "#384050"),
    "blue": ("#0D1B3E", "#60A5FA", "#1E3A5F"),
    "green": ("#0D2E1F", "#00D4AA", "#1E5F3F"),
    "amber": ("#2E200D", "#F59E0B", "#5F3F1E"),
    "red": ("#2E0D0D", "#FF4757", "#5F1E1E"),
    "slate": ("#1E2635", "#9BA3B0", "#384050"),
}


_THEME_VARS = {
    "dark": {
        "--bg-root": "#12171F",
        "--bg-main": "#161C24",
        "--surface": "#1E2635",
        "--surface-raised": "#242D3D",
        "--surface-hover": "#2A3343",
        "--text-main": "#F0F2F5",
        "--text-secondary": "#9BA3B0",
        "--text-disabled": "#555D6B",
        "--border": "#384050",
        "--border-light": "#2A3343",
        "--accent": "#FF6A00",
        "--accent-hover": "#FF8533",
        "--up": "#00D4AA",
        "--down": "#FF4757",
    },
    "light": {
        "--bg-root": "#F5F6F8",
        "--bg-main": "#F0F1F3",
        "--surface": "#FFFFFF",
        "--surface-raised": "#F9FAFB",
        "--surface-hover": "#EEF0F3",
        "--text-main": "#1A1D23",
        "--text-secondary": "#5A6070",
        "--text-disabled": "#8F95A3",
        "--border": "#D1D5DB",
        "--border-light": "#E0E3E8",
        "--accent": "#FF6A00",
        "--accent-hover": "#E55D00",
        "--up": "#009E73",
        "--down": "#DC2626",
    },
}


def apply_global_style(theme: str = "dark") -> None:
    """Apply Bloomberg Terminal professional theme (dark / light)."""
    vars_dict = _THEME_VARS.get(theme, _THEME_VARS["dark"])
    root_lines = "\n".join(
        f"        {key}: {value};" for key, value in vars_dict.items()
    )

    css = """<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

    :root {
""" + root_lines + """
        --radius-sm: 4px;
        --radius: 6px;
        --font-body: 'IBM Plex Sans', 'Microsoft YaHei', -apple-system, sans-serif;
        --font-mono: 'JetBrains Mono', 'Cascadia Code', 'Fira Code', monospace;
    }

    html, body, [class*="css"] {
        font-family: var(--font-body);
        font-size: 13px;
        color: var(--text-main);
        letter-spacing: 0 !important;
        background: var(--bg-root) !important;
    }

    .stApp {
        background: var(--bg-root) !important;
    }

    .main .block-container {
        max-width: 1380px !important;
        padding-top: 1rem !important;
        padding-bottom: 2rem !important;
    }

    /* ---- Typography ---- */
    h1, h2, h3, h4, h5, h6 {
        font-family: var(--font-body);
        color: var(--text-main) !important;
        letter-spacing: 0 !important;
    }
    h1 { font-size: 1.3rem !important; font-weight: 700 !important; margin: 0 !important; }
    h2 { font-size: 1.1rem !important; font-weight: 700 !important; }
    h3 { font-size: 0.95rem !important; font-weight: 650 !important; }
    p, li, span, div { color: var(--text-main); }
    small, .caption, caption { color: var(--text-secondary) !important; }
    hr {
        border-color: var(--border) !important;
        margin: 1rem 0 !important;
        opacity: 0.5;
    }

    /* ---- Sidebar ---- */
    [data-testid="stSidebar"] {
        background: var(--bg-main) !important;
        border-right: 1px solid var(--border) !important;
        box-shadow: none !important;
        min-width: 220px !important;
        max-width: 240px !important;
    }
    [data-testid="stSidebar"] > div {
        padding: 0.8rem 0.6rem !important;
    }

    .sidebar-brand {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 0 4px 12px;
        border-bottom: 1px solid var(--border);
        margin-bottom: 10px;
    }
    .sidebar-logo {
        width: 30px;
        height: 30px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: 4px;
        background: var(--accent);
        color: #FFFFFF;
        font-weight: 700;
        font-size: 0.85rem;
    }
    .sidebar-title { font-weight: 700; font-size: 0.92rem; color: var(--text-main); }
    .sidebar-subtitle { color: var(--text-secondary); font-size: 0.7rem; margin-top: 2px; }
    .nav-group-title {
        margin: 14px 0 4px;
        padding-left: 2px;
        color: var(--text-disabled);
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.6px;
    }

    [data-testid="stSidebar"] .stButton > button {
        width: 100%;
        justify-content: flex-start;
        border: none !important;
        border-radius: 4px !important;
        background: transparent !important;
        color: var(--text-secondary) !important;
        box-shadow: none !important;
        padding: 6px 8px !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        min-height: 32px;
        font-family: var(--font-body);
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        background: var(--surface-hover) !important;
        color: var(--text-main) !important;
    }
    [data-testid="stSidebar"] .stButton > button[kind="primary"] {
        background: rgba(255, 106, 0, 0.15) !important;
        color: var(--accent) !important;
        font-weight: 650 !important;
        border-left: 2px solid var(--accent) !important;
    }

    /* ---- Buttons ---- */
    .stButton > button {
        border-radius: 4px !important;
        border: 1px solid var(--border) !important;
        background: var(--surface) !important;
        color: var(--text-main) !important;
        box-shadow: none !important;
        font-weight: 550 !important;
        min-height: 32px;
        padding: 5px 12px !important;
        font-family: var(--font-body);
        font-size: 0.82rem !important;
        transition: background 0.12s ease, border-color 0.12s ease;
    }
    .stButton > button:hover {
        background: var(--surface-hover) !important;
        border-color: var(--text-secondary) !important;
    }
    .stButton > button[kind="primary"] {
        background: var(--accent) !important;
        color: #FFFFFF !important;
        border-color: var(--accent) !important;
        font-weight: 650 !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: var(--accent-hover) !important;
        border-color: var(--accent-hover) !important;
    }

    /* ---- Expanders & Containers ---- */
    div[data-testid="stVerticalBlockBorderWrapper"],
    [data-testid="stExpander"] details {
        border: 1px solid var(--border-light) !important;
        border-radius: 4px !important;
        background: var(--surface) !important;
        box-shadow: none !important;
    }
    [data-testid="stExpander"] summary {
        padding: 10px 14px !important;
        font-weight: 600 !important;
        color: var(--text-main) !important;
        font-family: var(--font-body);
    }
    [data-testid="stExpander"] summary:hover {
        color: var(--accent) !important;
    }

    /* ---- Inputs & Selects ---- */
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    .stSelectbox > div > div,
    .stMultiSelect > div > div {
        background: var(--surface) !important;
        border: 1px solid var(--border) !important;
        border-radius: 4px !important;
        color: var(--text-main) !important;
        font-family: var(--font-body);
    }
    [data-testid="stTextInput"] input:focus,
    [data-testid="stNumberInput"] input:focus,
    .stSelectbox [data-baseweb="select"]:focus {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 1px rgba(255, 106, 0, 0.25) !important;
    }

    /* ---- Tables ---- */
    [data-testid="stTable"] table {
        background: var(--surface) !important;
        border-collapse: collapse;
        width: 100%;
        font-size: 0.8rem;
    }
    [data-testid="stTable"] thead th {
        background: var(--bg-main) !important;
        color: var(--text-secondary) !important;
        font-weight: 650 !important;
        text-transform: uppercase;
        font-size: 0.7rem;
        letter-spacing: 0.4px;
        padding: 8px 10px !important;
        border-bottom: 1px solid var(--border) !important;
    }
    [data-testid="stTable"] tbody td {
        padding: 7px 10px !important;
        border-bottom: 1px solid var(--border-light) !important;
        color: var(--text-main) !important;
        font-family: var(--font-body);
    }
    [data-testid="stTable"] tbody tr:hover td {
        background: var(--surface-hover) !important;
    }
    /* Numeric cells: right-aligned, monospace */
    [data-testid="stTable"] td:nth-child(n+2) {
        text-align: right;
        font-family: var(--font-mono);
        font-variant-numeric: tabular-nums;
    }

    /* ---- DataFrame ---- */
    .stDataFrame {
        background: var(--surface) !important;
        border: 1px solid var(--border-light) !important;
        border-radius: 4px;
    }

    /* ---- Metrics ---- */
    [data-testid="stMetricValue"] {
        font-family: var(--font-mono) !important;
        font-size: 1.4rem !important;
        font-weight: 700 !important;
        color: var(--text-main) !important;
    }
    [data-testid="stMetricLabel"] {
        color: var(--text-disabled) !important;
        font-size: 0.7rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.5px;
    }
    [data-testid="stMetricDelta"] {
        font-family: var(--font-mono) !important;
    }

    /* ---- Progress bar ---- */
    .stProgress > div > div {
        background-color: var(--border) !important;
    }
    .stProgress > div > div > div {
        background: linear-gradient(90deg, var(--accent), #FF8533) !important;
    }

    /* ---- Checks / Toggle ---- */
    [data-testid="stCheckbox"] label span {
        color: var(--text-main) !important;
        font-family: var(--font-body);
    }

    /* ---- Tabs ---- */
    [data-testid="stTabs"] [role="tab"] {
        color: var(--text-secondary) !important;
        border-bottom-color: transparent !important;
    }
    [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
        color: var(--accent) !important;
        border-bottom-color: var(--accent) !important;
    }

    /* ---- Workbench Header ---- */
    .workbench-header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 18px;
        padding: 16px 20px;
        background: var(--surface);
        border: 1px solid var(--border-light);
        border-radius: 4px;
        margin-bottom: 14px;
    }
    .workbench-eyebrow {
        color: var(--text-disabled);
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        margin-bottom: 4px;
    }
    .workbench-desc {
        margin-top: 6px;
        color: var(--text-secondary);
        max-width: 780px;
        line-height: 1.55;
        font-size: 0.85rem;
    }
    .workbench-meta {
        color: var(--text-disabled);
        font-size: 0.78rem;
        white-space: nowrap;
        padding-top: 2px;
    }

    /* ---- Metric Strip ---- */
    .metric-strip {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 8px;
        margin-bottom: 14px;
    }
    .metric-card {
        padding: 12px 14px;
        background: var(--surface);
        border: 1px solid var(--border-light);
        border-radius: 4px;
    }
    .metric-label {
        color: var(--text-disabled);
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 4px;
    }
    .metric-value {
        color: var(--text-main);
        font-size: 1.3rem;
        font-weight: 750;
        line-height: 1.15;
        font-family: var(--font-mono);
        font-variant-numeric: tabular-nums;
    }
    .metric-help {
        margin-top: 4px;
        color: var(--text-secondary);
        font-size: 0.74rem;
    }

    /* ---- Research Card ---- */
    .research-card {
        padding: 14px 16px;
        background: var(--surface);
        border: 1px solid var(--border-light);
        border-radius: 4px;
        margin-bottom: 10px;
    }
    .card-title {
        font-size: 0.98rem;
        font-weight: 700;
        margin-bottom: 6px;
        color: var(--text-main);
    }
    .card-meta {
        color: var(--text-secondary);
        font-size: 0.78rem;
        line-height: 1.45;
    }
    .field-label {
        color: var(--text-disabled);
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 3px;
    }
    .field-value {
        color: var(--text-main);
        line-height: 1.55;
        font-size: 0.88rem;
    }
    .chip {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 3px 8px;
        border-radius: 3px;
        border: 1px solid var(--border);
        background: var(--surface-raised);
        color: var(--text-secondary);
        font-size: 0.74rem;
        font-weight: 550;
        margin: 0 5px 5px 0;
    }
    .score-pill {
        display: inline-flex;
        min-width: 44px;
        height: 26px;
        align-items: center;
        justify-content: center;
        border-radius: 4px;
        background: var(--accent);
        color: #FFFFFF;
        font-weight: 750;
        font-family: var(--font-mono);
        font-size: 0.85rem;
    }
    .danger-text { color: var(--down) !important; }
    .up-text { color: var(--up) !important; }

    /* ---- Stock mini-card ---- */
    .stock-name { font-weight: 650; color: var(--text-main); }
    .stock-code { color: var(--text-disabled); font-family: var(--font-mono); font-size: 0.82rem; }

    /* ---- Alerts / Info / Warning ---- */
    [data-testid="stAlert"] {
        background: var(--surface) !important;
        border: 1px solid var(--border) !important;
        border-radius: 4px !important;
        color: var(--text-main) !important;
    }
    [data-testid="stAlert"][data-baseweb="notification"] {
        background: var(--surface) !important;
    }

    /* ---- scrollbar ---- */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: var(--bg-root); }
    ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--text-disabled); }

    @media (max-width: 860px) {
        .workbench-header { display: block; }
        .workbench-meta { margin-top: 10px; white-space: normal; }
        .metric-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
</style>"""
    st.markdown(css, unsafe_allow_html=True)


def esc(value) -> str:
    return html.escape(str(value or ""))


def page_header(title: str, description: str, eyebrow: str = "Research Workbench", meta: str | None = None) -> None:
    meta_html = f'<div class="workbench-meta">{esc(meta)}</div>' if meta else ""
    st.markdown(
        f"""
<div class="workbench-header">
  <div>
    <div class="workbench-eyebrow">{esc(eyebrow)}</div>
    <h1>{esc(title)}</h1>
    <div class="workbench-desc">{esc(description)}</div>
  </div>
  {meta_html}
</div>
        """,
        unsafe_allow_html=True,
    )


def metric_strip(metrics: Iterable[tuple[str, object, str | None]]) -> None:
    cards = []
    for label, value, help_text in metrics:
        help_html = f'<div class="metric-help">{esc(help_text)}</div>' if help_text else ""
        cards.append(
            f"""
<div class="metric-card">
  <div class="metric-label">{esc(label)}</div>
  <div class="metric-value">{esc(value)}</div>
  {help_html}
</div>
            """
        )
    st.markdown(f'<div class="metric-strip">{"".join(cards)}</div>', unsafe_allow_html=True)


def badge(label: str, tone: str = "default") -> str:
    bg, fg, bd = TONE_COLORS.get(tone, TONE_COLORS["default"])
    return (
        f'<span class="chip" style="background:{bg};color:{fg};border-color:{bd};">'
        f"{esc(label)}</span>"
    )


def score_tone(score: int | float | None) -> str:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "default"
    if value >= 80:
        return "green"
    if value >= 60:
        return "amber"
    return "slate"


def level_tone(value: str) -> str:
    return {
        "高": "green",
        "中": "amber",
        "低": "slate",
        "正在升温": "green",
        "预热中": "amber",
        "等待确认": "slate",
        "draft": "amber",
        "confirmed": "green",
        "discarded": "red",
        "核心": "green",
        "重要": "blue",
        "观察": "amber",
        "泛相关": "slate",
    }.get(str(value), "default")


def field_html(label: str, value, fallback: str = "-") -> str:
    text = value
    if isinstance(value, list):
        text = "、".join(str(item).strip() for item in value if str(item).strip())
    text = str(text or "").strip() or fallback
    return (
        f'<div class="field-label">{esc(label)}</div>'
        f'<div class="field-value">{esc(text)}</div>'
    )


def chips(values) -> str:
    if isinstance(values, str):
        parts = [item.strip() for item in values.replace("，", "、").split("、") if item.strip()]
    elif isinstance(values, list):
        parts = [str(item).strip() for item in values if str(item).strip()]
    else:
        parts = []
    if not parts:
        return '<span class="card-meta">-</span>'
    return "".join(badge(item, "slate") for item in parts[:12])


# ---- 行情数据展示 ----


def market_pct_badge(pct: float | None) -> str:
    """涨跌幅彩色标记 — 中国市场：红涨绿跌"""
    if pct is None:
        return '<span style="color:var(--text-disabled);">-</span>'
    try:
        value = float(pct)
    except (TypeError, ValueError):
        return '<span style="color:var(--text-disabled);">-</span>'
    color = "var(--down)" if value > 0 else ("var(--up)" if value < 0 else "var(--text-secondary)")
    sign = "+" if value > 0 else ""
    return f'<span style="color:{color};font-weight:700;white-space:nowrap;font-family:var(--font-mono);font-variant-numeric:tabular-nums;">{sign}{value:.2f}%</span>'


def market_flow_badge(flow: float | None) -> str:
    """资金流向标记"""
    if flow is None:
        return '<span class="card-meta">-</span>'
    try:
        value = float(flow)
    except (TypeError, ValueError):
        return '<span class="card-meta">-</span>'
    direction = "流入" if value > 0 else ("流出" if value < 0 else "持平")
    color = "var(--down)" if value > 0 else ("var(--up)" if value < 0 else "var(--text-secondary)")
    abs_val = abs(value)
    if abs_val >= 1:
        text = f"{direction} {abs_val:.1f}亿"
    else:
        text = f"{direction} {abs_val*10000:.0f}万"
    return f'<span style="color:{color};font-weight:650;white-space:nowrap;font-family:var(--font-mono);">{text}</span>'


def limit_up_badge(limit_up: int | None, total: int | None) -> str:
    """涨停关联标记"""
    if limit_up is None and total is None:
        return '<span class="card-meta">-</span>'
    lu = limit_up or 0
    tot = total or 0
    if tot == 0:
        return '<span class="card-meta">-</span>'
    color = "var(--down)" if lu > 0 else "var(--text-secondary)"
    return f'<span style="color:{color};font-weight:650;white-space:nowrap;font-family:var(--font-mono);">{lu}/{tot} 涨停</span>'


def market_indicators_html(market_detail: dict | None) -> str:
    """渲染行情指标条（用于题材卡片内嵌）"""
    if not market_detail or not isinstance(market_detail, dict):
        return ""

    parts = []
    if market_detail.get("pct_chg_1d") is not None:
        parts.append(f'近1日 {market_pct_badge(market_detail.get("pct_chg_1d"))}')
    if market_detail.get("fund_flow") is not None:
        parts.append(market_flow_badge(market_detail.get("fund_flow")))
    if market_detail.get("limit_up_count") is not None and market_detail.get("sector_stock_count"):
        parts.append(limit_up_badge(
            market_detail.get("limit_up_count"),
            market_detail.get("sector_stock_count"),
        ))

    if not parts:
        return ""

    return (
        '<div style="display:flex;flex-wrap:wrap;gap:12px;margin-top:6px;'
        'font-size:0.8rem;color:#8B92A0;">'
        + "".join(f"<span>{p}</span>" for p in parts)
        + "</div>"
    )


# ==================== 验证状态 UI 组件 ====================

VERIFY_STATUS_CONFIG = {
    "verified_auto": {
        "label": "自动验证通过",
        "icon": "&#9989;",
        "color": "#00D4AA",
        "bg": "#0D2E1F",
        "border": "#1E5F3F",
        "tone": "green",
    },
    "verified_inferred": {
        "label": "推断验证",
        "icon": "&#9888;",
        "color": "#F59E0B",
        "bg": "#2E200D",
        "border": "#5F3F1E",
        "tone": "amber",
    },
    "still_unverified": {
        "label": "仍待核验",
        "icon": "&#10067;",
        "color": "#FF4757",
        "bg": "#2E0D0D",
        "border": "#5F1E1E",
        "tone": "red",
    },
    "manually_confirmed": {
        "label": "人工确认",
        "icon": "&#10004;",
        "color": "#E6E8EC",
        "bg": "#1E2430",
        "border": "#2A3040",
        "tone": "slate",
    },
    "待核验": {
        "label": "待核验",
        "icon": "&#10067;",
        "color": "#FF4757",
        "bg": "#2E0D0D",
        "border": "#5F1E1E",
        "tone": "red",
    },
    "验证中": {
        "label": "验证中",
        "icon": "&#9203;",
        "color": "#60A5FA",
        "bg": "#0D1B3E",
        "border": "#1E3A5F",
        "tone": "blue",
    },
    "unverified": {
        "label": "待核验",
        "icon": "&#10067;",
        "color": "#FF4757",
        "bg": "#2E0D0D",
        "border": "#5F1E1E",
        "tone": "red",
    },
    "verifying": {
        "label": "验证中",
        "icon": "&#9203;",
        "color": "#60A5FA",
        "bg": "#0D1B3E",
        "border": "#1E3A5F",
        "tone": "blue",
    },
}


def verify_status_badge(status: str, show_label: bool = True) -> str:
    """验证状态彩色徽章（HTML）"""
    cfg = VERIFY_STATUS_CONFIG.get(status, VERIFY_STATUS_CONFIG["待核验"])
    label = cfg["label"] if show_label else ""
    return (
        f'<span style="display:inline-flex;align-items:center;gap:4px;'
        f'padding:2px 10px;border-radius:3px;font-size:0.78rem;'
        f'font-weight:550;background:{cfg["bg"]};color:{cfg["color"]};'
        f'border:1px solid {cfg["border"]};white-space:nowrap;">'
        f'{cfg["icon"]} {label}</span>'
    )


def verify_status_icon(status: str) -> str:
    """仅返回验证状态图标（HTML）"""
    cfg = VERIFY_STATUS_CONFIG.get(status, VERIFY_STATUS_CONFIG["待核验"])
    return (
        f'<span style="display:inline-flex;align-items:center;'
        f'color:{cfg["color"]};font-size:1rem;margin-right:2px;">'
        f'{cfg["icon"]}</span>'
    )


def field_verify_badge(field_status: str) -> str:
    """字段级验证状态小标记"""
    icons = {
        "verified_auto": '<span style="color:#00D4AA;" title="自动验证">&#9989;</span>',
        "verified_inferred": '<span style="color:#F59E0B;" title="推断验证">&#9888;</span>',
        "still_unverified": '<span style="color:#FF4757;" title="仍待核验">&#10067;</span>',
    }
    return icons.get(field_status, '<span style="color:#555D6B;" title="未验证">?</span>')


def parse_verification_details(details_str: str) -> dict | None:
    """解析 verification_details JSON 字符串"""
    if not details_str:
        return None
    try:
        import json
        return json.loads(details_str)
    except (json.JSONDecodeError, TypeError):
        return None


def render_verification_expander(stock: dict, theme_name: str = "") -> None:
    """在个股卡片中渲染可展开的验证详情区域"""
    details_str = stock.get("verification_details", "")
    details = parse_verification_details(details_str)
    if not details:
        return

    field_details = details.get("field_details", {})
    if not field_details:
        return

    with st.expander("查看验证详情", expanded=False):
        st.caption(f"验证时间: {details.get('verified_at', '—')}")
        if details.get("summary"):
            st.info(details["summary"])

        for field_name, fd in field_details.items():
            field_labels = {
                "market_position": "市场地位",
                "market_share": "市占率",
                "customers": "客户关系",
                "biz_growth": "业务增速",
            }
            label = field_labels.get(field_name, field_name)

            col1, col2 = st.columns([2, 5])
            with col1:
                st.markdown(f"**{label}**")
                st.markdown(field_verify_badge(fd.get("status", "")), unsafe_allow_html=True)
            with col2:
                st.caption(f"原值: {fd.get('original_value', '—')}")
                if fd.get("evidence_summary"):
                    st.caption(f"证据: {fd['evidence_summary']}")
                if fd.get("evidence_urls"):
                    for url in fd["evidence_urls"][:2]:
                        st.caption(f"来源: [{url}]({url})")
        st.divider()


# ---------------------------------------------------------------------------
# P0-3: 数据新鲜度 UI 组件
# ---------------------------------------------------------------------------

FRESHNESS_CONFIG = {
    "新鲜": {"color": "#00D4AA", "bg": "#0D2E1F", "icon": "●", "label": "新鲜"},
    "一般": {"color": "#F59E0B", "bg": "#2E200D", "icon": "●", "label": "一般"},
    "过期": {"color": "#FF4757", "bg": "#2E0D0D", "icon": "●", "label": "过期"},
}


def freshness_badge(score: int, label: str | None = None) -> str:
    """
    新鲜度徽章 HTML。
    score: 0-100 新鲜度分
    """
    from core.data_freshness import get_freshness_label, get_freshness_color
    level = label or get_freshness_label(score)
    config = FRESHNESS_CONFIG.get(level, FRESHNESS_CONFIG["一般"])
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:3px;'
        f'font-size:0.73rem;font-weight:600;'
        f'color:{config["color"]};background:{config["bg"]};">'
        f'{config["icon"]} {score}分 {config["label"]}</span>'
    )


def freshness_indicator(level: str) -> str:
    """返回简洁新鲜度图标HTML"""
    config = FRESHNESS_CONFIG.get(level, FRESHNESS_CONFIG["一般"])
    return (
        f'<span style="color:{config["color"]};font-size:0.9rem;">'
        f'{config["icon"]}</span>'
    )


def freshness_gauge(pct: int, width: str = "100%") -> str:
    """
    健康度进度条 HTML。
    pct: 0-100 整体健康度百分比
    """
    if pct >= 70:
        bar_color = "#00D4AA"
    elif pct >= 40:
        bar_color = "#F59E0B"
    else:
        bar_color = "#FF4757"
    return (
        f'<div style="width:{width};background:#2A3040;border-radius:3px;height:6px;margin:6px 0;">'
        f'<div style="width:{pct}%;background:{bar_color};border-radius:3px;height:100%;"></div>'
        f'</div>'
    )


def render_freshness_dashboard(global_freshness) -> None:
    """在侧边栏渲染数据新鲜度仪表盘卡片"""
    import streamlit as st

    gf = global_freshness
    if gf.total_themes == 0:
        return

    st.divider()
    st.markdown(
        '<div style="font-size:0.7rem;color:#555D6B;margin-bottom:4px;letter-spacing:0.5px;text-transform:uppercase;">'
        '数据新鲜度</div>',
        unsafe_allow_html=True,
    )

    # 整体健康度
    st.markdown(
        f'<div style="font-size:1.5rem;font-weight:700;color:#E6E8EC;font-family:var(--font-mono);">'
        f'{gf.health_pct}%</div>',
        unsafe_allow_html=True,
    )
    st.markdown(freshness_gauge(gf.health_pct), unsafe_allow_html=True)

    # 统计行
    st.markdown(
        f'<div style="font-size:0.72rem;color:#8B92A0;line-height:1.6;">'
        f'新鲜 <b style="color:#00D4AA;">{gf.fresh_count}</b> 个 &nbsp;|&nbsp; '
        f'一般 <b style="color:#F59E0B;">{gf.normal_count}</b> 个 &nbsp;|&nbsp; '
        f'过期 <b style="color:#FF4757;">{gf.stale_count}</b> 个</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        f'<div style="font-size:0.68rem;color:#555D6B;margin-top:4px;">'
        f'最新: {gf.latest_update_str}</div>',
        unsafe_allow_html=True,
    )

    # 待关注列表
    if gf.needs_refresh_list:
        st.markdown(
            '<div style="font-size:0.72rem;color:#8B92A0;margin-top:8px;">'
            '待关注</div>',
            unsafe_allow_html=True,
        )
        for t in gf.needs_refresh_list[:5]:
            st.markdown(
                f'<div style="font-size:0.7rem;color:#555D6B;padding:2px 0;">'
                f'<span style="color:{FRESHNESS_CONFIG[t.level]["color"]};">'
                f'{FRESHNESS_CONFIG[t.level]["icon"]}</span> '
                f'<span style="color:#E6E8EC;">{esc(t.theme_name)}</span>'
                f'<br><span style="font-size:0.66rem;">{t.refresh_reason}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ============================================================================
# Serenity 四维分析 UI 组件
# ============================================================================

SERENITY_DIMENSIONS = {
    "bottleneck": {
        "label": "卡脖子",
        "icon": "&#9889;",
        "color": "#FF6A00",
        "bg": "#2E1A00",
        "description": "评估产业链不可替代性：上游 > 中游 > 下游",
    },
    "institutional": {
        "label": "机构信号",
        "icon": "&#127970;",
        "color": "#60A5FA",
        "bg": "#0D1B3E",
        "description": "北向资金/融资融券/龙虎榜/机构调研",
    },
    "value": {
        "label": "长线价值",
        "icon": "&#128176;",
        "color": "#00D4AA",
        "bg": "#0D2E1F",
        "description": "ROE/毛利率/现金流/护城河",
    },
    "valuation": {
        "label": "估值重置",
        "icon": "&#128200;",
        "color": "#F59E0B",
        "bg": "#2E200D",
        "description": "范式转移 vs 周期波动 vs 价值陷阱",
    },
}

SERENITY_GRADE_COLORS = {
    "A": ("#00D4AA", "#0D2E1F"),
    "B": ("#60A5FA", "#0D1B3E"),
    "C": ("#F59E0B", "#2E200D"),
    "D": ("#FF8533", "#2E1800"),
    "F": ("#FF4757", "#2E0D0D"),
}


def serenity_dimension_badge(dimension_key: str, score: int) -> str:
    """四维单项徽章 HTML"""
    dim = SERENITY_DIMENSIONS.get(dimension_key)
    if not dim:
        return ""
    return (
        f'<span style="display:inline-flex;align-items:center;gap:6px;'
        f'padding:4px 12px;border-radius:4px;font-size:0.82rem;font-weight:600;'
        f'background:{dim["bg"]};color:{dim["color"]};'
        f'border:1px solid {dim["color"]}33;white-space:nowrap;">'
        f'{dim["icon"]} {dim["label"]} '
        f'<span style="font-family:var(--font-mono);font-weight:750;">{score}</span>'
        f'</span>'
    )


def serenity_composite_badge(score: int, grade: str) -> str:
    """综合置信度徽章"""
    color, bg = SERENITY_GRADE_COLORS.get(grade, ("#9BA3B0", "#1E2635"))
    return (
        f'<span style="display:inline-flex;align-items:center;gap:6px;'
        f'padding:5px 14px;border-radius:4px;font-size:0.88rem;font-weight:700;'
        f'background:{bg};color:{color};border:2px solid {color}55;">'
        f'&#127942; Serenity '
        f'<span style="font-family:var(--font-mono);font-size:1.1rem;">{score}</span>'
        f'<span style="font-size:0.78rem;opacity:0.8;">({grade})</span>'
        f'</span>'
    )


def serenity_dimension_bar(label: str, score: int, color: str, bg: str) -> str:
    """单个维度横向进度条"""
    return (
        f'<div style="margin-bottom:6px;">'
        f'<div style="display:flex;justify-content:space-between;'
        f'font-size:0.72rem;color:#8B92A0;margin-bottom:3px;">'
        f'<span>{label}</span>'
        f'<span style="font-family:var(--font-mono);color:{color};font-weight:650;">'
        f'{score}</span></div>'
        f'<div style="height:6px;background:#2A3040;border-radius:3px;">'
        f'<div style="width:{score}%;height:100%;background:{color};'
        f'border-radius:3px;transition:width 0.4s ease;"></div></div></div>'
    )


def render_serenity_dashboard(report: dict) -> None:
    """
    渲染 Serenity 四维分析仪表盘。

    Args:
        report: report_to_dict() 的输出字典
    """
    import streamlit as st

    composite = report.get("composite_score", 50)
    grade = report.get("composite_grade", "C")

    # 综合置信度徽章
    color, bg = SERENITY_GRADE_COLORS.get(grade, ("#9BA3B0", "#1E2635"))
    st.markdown(
        f'<div style="text-align:center;margin:8px 0;">'
        f'{serenity_composite_badge(composite, grade)}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # 四维进度条
    dimensions = [
        ("bottleneck", "卡脖子指数", report["bottleneck"]["score"]),
        ("institutional", "机构行为信号", report["institutional"]["score"]),
        ("value", "长线价值评分", report["value"]["score"]),
        ("valuation", "估值重置判断", report["valuation_reset"]["score"]),
    ]

    for key, label, score in dimensions:
        dim = SERENITY_DIMENSIONS[key]
        st.markdown(
            serenity_dimension_bar(label, score, dim["color"], dim["bg"]),
            unsafe_allow_html=True,
        )

    # 四维指标卡片行
    cols = st.columns(4)
    for col, (key, label, score) in zip(cols, dimensions):
        dim = SERENITY_DIMENSIONS[key]
        col.markdown(
            f'<div style="padding:10px 8px;background:{dim["bg"]}55;'
            f'border-radius:4px;text-align:center;border:1px solid {dim["color"]}22;">'
            f'<div style="color:{dim["color"]};font-size:0.75rem;font-weight:600;">'
            f'{dim["icon"]} {dim["label"]}</div>'
            f'<div style="font-size:1.5rem;font-weight:750;font-family:var(--font-mono);'
            f'color:{dim["color"]};">{score}</div>'
            f'<div style="font-size:0.65rem;color:#555D6B;margin-top:2px;">'
            f'{dim["description"][:20]}...</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # 投资主题
    thesis = report.get("investment_thesis", "")
    if thesis:
        st.markdown(
            f'<div style="margin-top:12px;padding:10px 14px;'
            f'background:#1E2635;border-left:3px solid {color};border-radius:4px;">'
            f'<span style="color:#9BA3B0;font-size:0.7rem;">投资主题</span><br>'
            f'<span style="font-size:0.88rem;font-weight:600;">{esc(thesis)}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )


def render_serenity_expander(report: dict) -> None:
    """
    渲染 Serenity 四维分析的展开详情（用于信息提示区域）。

    Args:
        report: report_to_dict() 的输出字典
    """
    import streamlit as st

    with st.expander("Serenity 四维分析详情", expanded=False):
        # 卡脖子
        bn = report["bottleneck"]
        st.markdown(f"**卡脖子指数: {bn['score']}** — {bn['level']}")
        st.caption(
            f"产业链位置: {bn['position']}  |  "
            f"国产替代率: {bn['domestic_substitution_rate']:.0%}  |  "
            f"进口依赖度: {bn['import_dependency']:.0%}"
        )
        if bn.get("key_bottleneck_items"):
            st.caption(f"关键卡脖子环节: {'、'.join(bn['key_bottleneck_items'])}")

        st.divider()

        # 机构行为
        inst = report["institutional"]
        st.markdown(f"**机构行为信号: {inst['score']}** — {inst['signal']}")
        st.caption(
            f"北向: {inst['northbound_flow_score']}  |  "
            f"融资: {inst['margin_trading_score']}  |  "
            f"龙虎榜: {inst['dragon_tiger_score']}  |  "
            f"调研: {inst['institution_research_score']}"
        )

        st.divider()

        # 长线价值
        val = report["value"]
        st.markdown(f"**长线价值评分: {val['score']}**")
        st.caption(
            f"ROE: {val['roe_score']}  |  "
            f"毛利率: {val['gross_margin_score']}  |  "
            f"现金流: {val['cashflow_score']}  |  "
            f"护城河: {val['moat_score']}"
        )
        if val.get("moat_type"):
            st.caption(f"护城河类型: {val['moat_type']}")

        st.divider()

        # 估值重置
        vr = report["valuation_reset"]
        st.markdown(f"**估值重置判断: {vr['score']}** — {vr['regime']}")
        st.caption(
            f"行业周期: {vr.get('industry_cycle_phase', '-')}  |  "
            f"政策驱动: {vr['policy_driver_score']}"
        )
        if vr.get("risk_warning"):
            st.warning(vr["risk_warning"])
