"""
引导式入门流程 — P1-4 优化

3 步引导：
  1. 欢迎页
  2. API Key 配置
  3. 加载示例数据

使用 session_state.onboarding_step 控制流程。
"""
import os
import json
import streamlit as st
from datetime import datetime

from config import DATA_DIR
from tasks.example_data  import EXAMPLE_THEMES
ONBOARDING_STEPS = {
    1: "欢迎",
    2: "API Key 配置",
    3: "加载示例数据",
}


def _step_indicator(current: int) -> None:
    """渲染步骤指示器"""
    cols = st.columns(3)
    for i, (num, label) in enumerate(ONBOARDING_STEPS.items()):
        with cols[i]:
            dot = "●" if num <= current else "○"
            color = "#FF6A00" if num <= current else "#555D6B"
            active_class = "active" if num == current else ""
            st.markdown(
                f"""
<div style="text-align:center;padding:8px 0;">
  <div style="font-size:1.4rem;color:{color};margin-bottom:4px;">{dot}</div>
  <div style="font-size:0.82rem;color:{color};" class="{active_class}">
    {label}
  </div>
</div>
                """,
                unsafe_allow_html=True,
            )
    st.markdown('<hr style="margin-top:0;">', unsafe_allow_html=True)


def _validate_api_key(api_key: str, base_url: str, model: str) -> tuple[bool, str]:
    """验证 API Key 有效性：发送简单请求，返回 (是否有效, 消息)"""
    if not api_key.strip():
        return False, "请填写 API Key"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key.strip(), base_url=base_url.strip())
        response = client.chat.completions.create(
            model=model.strip(),
            messages=[{"role": "user", "content": "回复: OK"}],
            max_tokens=5,
            timeout=8,  # 快速失败，避免新手引导长时间卡住
        )
        return True, "API Key 验证通过"
    except Exception as e:
        err = str(e)
        if "401" in err or "Unauthorized" in err or "invalid" in err.lower():
            return False, "API Key 无效，请检查后重试"
        elif "404" in err or "model" in err.lower():
            return False, f"模型 '{model}' 不存在，请检查模型名称"
        elif "timed out" in err.lower() or "timeout" in err.lower():
            return False, "请求超时，请检查网络连接"
        else:
            return False, f"连接失败：{err[:80]}"


def _save_api_key_to_config(api_key: str, base_url: str, model: str) -> None:
    """保存 API Key 到本地文件和 session_state"""
    config_path = os.path.join(DATA_DIR, "api_config.json")
    config = {
        "api_key": api_key.strip(),
        "base_url": base_url.strip(),
        "model": model.strip(),
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # 同步到 session_state
    st.session_state.ai_api_key = api_key.strip()
    st.session_state.ai_base_url = base_url.strip()
    st.session_state.ai_model = model.strip()


def _load_example_data_into_db():
    """将示例数据写入数据库。先检查是否已有同名主题，避免重复插入。"""
    import core.database as db

    existing_themes = set(db.get_distinct_themes())
    inserted_count = 0

    for theme in EXAMPLE_THEMES:
        tname = theme["theme_name"]
        if tname in existing_themes:
            continue

        try:
            with db.get_connection() as conn:
                # 插入 theme_quality
                conn.execute("""
                    INSERT INTO theme_quality
                        (theme_name, breadth, event_density, capital_flow, sustainability, overall_score, summary)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    tname,
                    theme["breadth"],
                    theme["event_density"],
                    theme["capital_flow"],
                    theme["sustainability"],
                    theme["overall_score"],
                    theme.get("quality_summary", ""),
                ))

                # 插入 theme_stocks（产业链个股）
                for chain in theme["chains"]:
                    level1 = chain["level1"]
                    for seg in chain["segments"]:
                        level2 = seg["level2"]
                        level3 = seg.get("level3", "")
                        for stock in seg["stocks"]:
                            conn.execute("""
                                INSERT INTO theme_stocks
                                    (theme_name, level1, level2, level3, stock_code, stock_name,
                                     market_type, role, importance, source, tier)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                tname, level1, level2, level3,
                                stock["code"], stock["name"], stock["market"],
                                stock["role"], stock.get("importance", "中"),
                                stock.get("source", "示例"), stock.get("tier", ""),
                            ))

                conn.commit()
                inserted_count += 1
        except Exception:
            pass

    return inserted_count


def render_onboarding(step: int, reset_key_prefix: str = "") -> int | None:
    """
    渲染引导流程页面，返回下一步的 step 编号。
    返回 None 表示引导仍在进行中；返回 0 表示引导完成。

    Args:
        step: 当前步骤编号 (1/2/3)
        reset_key_prefix: 在侧边栏重新触发时传入唯一前缀，避免 key 冲突
    """
    # 进度条
    st.progress(step / 3)

    # 步骤指示器
    _step_indicator(step)

    if step == 1:
        return _render_step1(reset_key_prefix)
    elif step == 2:
        return _render_step2(reset_key_prefix)
    elif step == 3:
        return _render_step3(reset_key_prefix)
    return None


def _render_step1(prefix: str) -> int:
    """Step 1 — 欢迎页"""
    st.markdown("""
<div style="text-align:center;padding:20px 0 10px;">
  <div style="font-size:2.8rem;color:var(--accent-blue);margin-bottom:8px;">📊</div>
  <h2 style="margin-bottom:6px;">欢迎使用 A股热点题材产业链分析工具</h2>
  <p style="color:var(--text-secondary);font-size:0.95rem;max-width:520px;margin:0 auto;">
    从海量财经资讯中自动发现热点题材、拆解产业链、映射 A 股标的，
    <strong>3 分钟配置，即刻上手</strong>，替代大量人工搜索与整理工作。
  </p>
</div>
    """, unsafe_allow_html=True)

    # 快速上手要点
    cols = st.columns(3)
    with cols[0]:
        st.markdown("""
<div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px;height:130px;">
  <div style="font-size:1.2rem;font-weight:600;color:var(--accent-blue);margin-bottom:6px;">1. 配置 API Key</div>
  <p style="font-size:0.82rem;color:var(--text-secondary);margin:0;">接入 DeepSeek 大模型，驱动题材分析与产业链拆解</p>
</div>
        """, unsafe_allow_html=True)
    with cols[1]:
        st.markdown("""
<div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px;height:130px;">
  <div style="font-size:1.2rem;font-weight:600;color:var(--accent-blue);margin-bottom:6px;">2. 浏览示例数据</div>
  <p style="font-size:0.82rem;color:var(--text-secondary);margin:0;">预置 AI 算力、低空经济、人形机器人等真实热点题材</p>
</div>
        """, unsafe_allow_html=True)
    with cols[2]:
        st.markdown("""
<div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px;height:130px;">
  <div style="font-size:1.2rem;font-weight:600;color:var(--accent-blue);margin-bottom:6px;">3. 发现新题材</div>
  <p style="font-size:0.82rem;color:var(--text-secondary);margin:0;">使用「热点题材」功能，AI 自动搜索并分析最新财经资讯</p>
</div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1.2, 1, 1])
    with col1:
        if st.button("开始配置", key=f"{prefix}start_setup", type="primary", use_container_width=True):
            return 2
    return 1


def _render_step2(prefix: str) -> int:
    """Step 2 — API Key 配置"""
    st.markdown("""
<h3 style="margin-bottom:4px;">配置 DeepSeek API Key</h3>
<p style="color:var(--text-secondary);font-size:0.88rem;margin-bottom:16px;">
  本工具依赖 DeepSeek 大模型进行产业链分析与个股映射。
  <a href="https://platform.deepseek.com/api_keys" target="_blank">前往 DeepSeek 官网获取 API Key →</a>
</p>
    """, unsafe_allow_html=True)

    # 从 session_state 或本地文件加载已有配置
    default_key = st.session_state.get(f"{prefix}api_key", "")
    default_url = st.session_state.get(f"{prefix}base_url", "https://api.deepseek.com")
    default_model = st.session_state.get(f"{prefix}model", "deepseek-v4-flash")

    if not default_key:
        # 尝试从本地文件加载
        try:
            config_path = os.path.join(DATA_DIR, "api_config.json")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                default_key = saved.get("api_key", "")
                default_url = saved.get("base_url", "https://api.deepseek.com")
                default_model = saved.get("model", "deepseek-v4-flash")
        except Exception:
            pass

    api_key = st.text_input(
        "API Key",
        value=default_key,
        type="password",
        placeholder="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        key=f"{prefix}api_key_input",
        help="您的密钥加密存储在本地，不会上传到任何地方",
    )

    col1, col2 = st.columns(2)
    with col1:
        base_url = st.text_input(
            "API 地址",
            value=default_url,
            key=f"{prefix}base_url_input",
            help="默认使用 DeepSeek 官方 API",
        )
    with col2:
        model = st.text_input(
            "模型名称",
            value=default_model,
            key=f"{prefix}model_input",
            help="推荐 deepseek-v4-flash（性价比高）或 deepseek-v4（更强）",
        )

    st.markdown("<br>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1, 1.3])
    with col1:
        if st.button("验证并保存", key=f"{prefix}verify", type="primary", use_container_width=True):
            with st.spinner("正在验证 API Key（最长 8 秒）..."):
                valid, msg = _validate_api_key(api_key, base_url, model)
            if valid:
                _save_api_key_to_config(api_key, base_url, model)
                st.success(msg)
                st.info("验证通过！点击下方按钮进入下一步 →")
                return 3
            else:
                st.error(msg)
                return 2

    with col2:
        if st.button("跳过，先看示例", key=f"{prefix}skip", use_container_width=True):
            return 3

    with col3:
        st.markdown(
            '<span style="font-size:0.78rem;color:var(--text-tertiary);">'
            '跳过后使用预置示例数据，无需 AI 调用即可浏览全部功能</span>',
            unsafe_allow_html=True,
        )

    return 2


def _render_step3(prefix: str) -> int:
    """Step 3 — 加载示例数据"""

    # 先检查是否有示例数据
    try:
        import core.database as db
        existing = set(db.get_distinct_themes())
    except Exception:
        existing = set()

    example_names = [t["theme_name"] for t in EXAMPLE_THEMES]
    already_loaded = [n for n in example_names if n in existing]
    to_load = [n for n in example_names if n not in existing]

    if already_loaded and not to_load:
        # 所有示例数据已存在
        st.markdown("""
<h3 style="margin-bottom:4px;">示例数据已就绪</h3>
<p style="color:var(--text-secondary);font-size:0.88rem;margin-bottom:16px;">
  以下示例题材已在您的数据库中，可直接开始使用。
</p>
        """, unsafe_allow_html=True)
        _render_theme_preview_cards(EXAMPLE_THEMES)

        if st.button("进入应用", key=f"{prefix}enter_already", type="primary", use_container_width=True):
            st.session_state.onboarding_complete = True
            st.rerun()
        return 3

    if already_loaded:
        st.info(f"已存在 {len(already_loaded)} 个示例题材：{'、'.join(already_loaded)}，将加载剩余 {len(to_load)} 个")

    st.markdown("""
<h3 style="margin-bottom:4px;">加载示例数据</h3>
<p style="color:var(--text-secondary);font-size:0.88rem;margin-bottom:16px;">
  预置 3 个近期热点题材的产业链数据，标注"示例"来源，方便您快速了解工具功能。
</p>
    """, unsafe_allow_html=True)

    _render_theme_preview_cards(EXAMPLE_THEMES)

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("加载示例并进入应用", key=f"{prefix}load_and_enter", type="primary", use_container_width=True):
            count = _load_example_data_into_db()
            st.session_state.onboarding_complete = True
            st.success(f"已加载 {count} 个示例题材")
            st.rerun()
    with col2:
        if st.button("跳过，直接进入", key=f"{prefix}skip_all", use_container_width=True):
            st.session_state.onboarding_complete = True
            st.rerun()

    return 3


def _render_theme_preview_cards(themes: list[dict]) -> None:
    """渲染示例题材预览卡片"""
    for theme in themes:
        tname = theme["theme_name"]
        summary = theme["summary"]
        score = theme["overall_score"]

        # 统计个股数量
        stock_count = 0
        chain_counts: list[int] = []
        for chain in theme["chains"]:
            seg_count = 0
            for seg in chain["segments"]:
                seg_count += len(seg["stocks"])
            stock_count += seg_count
            chain_counts.append(seg_count)

        # 提取产业链环节
        level1_names = [c["level1"] for c in theme["chains"]]

        with st.expander(f"{tname}  —  {stock_count} 只个股 ｜ 综合评分 {score}", expanded=False):
            st.markdown(
                f'<p style="font-size:0.88rem;color:var(--text-secondary);margin-bottom:10px;">{summary}</p>',
                unsafe_allow_html=True,
            )
            for i, chain in enumerate(theme["chains"]):
                st.markdown(
                    f'<span style="font-size:0.82rem;font-weight:600;color:var(--text-primary);">{chain["level1"]}</span>',
                    unsafe_allow_html=True,
                )
                for seg in chain["segments"]:
                    stocks_str = "、".join(
                        f"{s['name']}" for s in seg["stocks"]
                    )
                    st.markdown(
                        f'<p style="font-size:0.78rem;color:var(--text-tertiary);margin:2px 0 2px 16px;">'
                        f'  {seg["level2"]}：{stocks_str}</p>',
                        unsafe_allow_html=True,
                    )


def check_should_onboard() -> bool:
    """
    判断是否应启动引导流程：
    - 数据库中题材数为 0（首次使用）
    - 或用户主动点击侧边栏"新手指引"重新触发
    返回 True 表示需要显示引导。

    结果缓存到 session_state，避免每次 rerun 都打开数据库。
    """
    # 如果已标记完成，且不是用户主动触发，则跳过
    if st.session_state.get("onboarding_complete", False):
        return False

    # 手动触发始终进入引导
    if st.session_state.get("onboarding_trigger") == "manual":
        return True

    # 缓存检查结果，避免每次 rerun 查询数据库
    cache_key = "_onboarding_check_done"
    if st.session_state.get(cache_key):
        return False  # 已检查过且未通过（否则 onboarding_complete 已为 True）

    try:
        import core.database as db
        count = db.get_theme_count()
        needs_onboarding = count == 0
        if not needs_onboarding:
            # 数据库有数据，不需要引导，缓存结果
            st.session_state[cache_key] = True
        return needs_onboarding
    except Exception:
        return True  # 数据库异常时也显示引导
