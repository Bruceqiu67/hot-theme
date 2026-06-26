"""
P2-12: Token 消耗监控模块

在每次 AI 调用后记录 token 用量和费用估算。
通过包装器模式无侵入埋点到 ai_client 的 OpenAI 调用。

费用定价（DeepSeek）：
- 输入：¥1 / 百万 tokens
- 输出：¥2 / 百万 tokens
"""
import os
import time
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from config import DATA_DIR, get_logger

_log = get_logger("token_monitor")

# ---- 数据库 ----

_TOKEN_DB = os.path.join(DATA_DIR, "token_usage.db")


def _ensure_table() -> None:
    """创建 token_usage 表"""
    conn = sqlite3.connect(_TOKEN_DB)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS token_usage (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                call_time       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                model           TEXT    NOT NULL,
                function_name   TEXT    DEFAULT '',
                prompt_tokens   INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens    INTEGER NOT NULL DEFAULT 0,
                cost_input      REAL    DEFAULT 0.0,
                cost_output     REAL    DEFAULT 0.0,
                cost_total      REAL    DEFAULT 0.0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_token_time ON token_usage(call_time)")
        conn.commit()
    finally:
        conn.close()


# 费用定价（元/百万 tokens）
PRICE_INPUT_PER_M = 1.0     # 输入 ¥1
PRICE_OUTPUT_PER_M = 2.0    # 输出 ¥2


def _cost(prompt_tokens: int, completion_tokens: int) -> tuple[float, float, float]:
    """计算费用"""
    cost_in = prompt_tokens * PRICE_INPUT_PER_M / 1_000_000
    cost_out = completion_tokens * PRICE_OUTPUT_PER_M / 1_000_000
    return cost_in, cost_out, cost_in + cost_out


def record_usage(
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    function_name: str = "",
) -> None:
    """记录一次 AI 调用的 token 用量"""
    if total_tokens == 0:
        total_tokens = prompt_tokens + completion_tokens
    cost_in, cost_out, cost_total = _cost(prompt_tokens, completion_tokens)

    _ensure_table()
    conn = sqlite3.connect(_TOKEN_DB)
    try:
        conn.execute("""
            INSERT INTO token_usage
                (model, function_name, prompt_tokens, completion_tokens,
                 total_tokens, cost_input, cost_output, cost_total)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (model, function_name, prompt_tokens, completion_tokens,
              total_tokens, cost_in, cost_out, cost_total))
        conn.commit()
    except Exception as exc:
        _log.debug("记录 token 用量失败: %s", exc)
    finally:
        conn.close()


def _row_to_dict(row) -> dict:
    """将 SQLite 查询行转换为字典（兼容 tuple 和 sqlite3.Row）"""
    if row is None:
        return {}
    cols = ["prompt_tokens", "completion_tokens", "total_tokens", "cost_total", "call_count"]
    return {cols[i]: row[i] for i in range(len(cols))}


def get_today_usage() -> dict:
    """获取今日用量统计"""
    today = datetime.now().strftime("%Y-%m-%d")
    _ensure_table()
    conn = sqlite3.connect(_TOKEN_DB)
    try:
        row = conn.execute("""
            SELECT
                COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COALESCE(SUM(cost_total), 0) AS cost_total,
                COUNT(*) AS call_count
            FROM token_usage
            WHERE DATE(call_time) = ?
        """, [today]).fetchone()
    finally:
        conn.close()
    return _row_to_dict(row)


def get_month_usage() -> dict:
    """获取本月用量统计"""
    month_start = datetime.now().replace(day=1).strftime("%Y-%m-%d")
    _ensure_table()
    conn = sqlite3.connect(_TOKEN_DB)
    try:
        row = conn.execute("""
            SELECT
                COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COALESCE(SUM(cost_total), 0) AS cost_total,
                COUNT(*) AS call_count
            FROM token_usage
            WHERE DATE(call_time) >= ?
        """, [month_start]).fetchone()
    finally:
        conn.close()
    return _row_to_dict(row)


def get_total_usage() -> dict:
    """获取累计用量统计"""
    _ensure_table()
    conn = sqlite3.connect(_TOKEN_DB)
    try:
        row = conn.execute("""
            SELECT
                COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COALESCE(SUM(cost_total), 0) AS cost_total,
                COUNT(*) AS call_count
            FROM token_usage
        """).fetchone()
    finally:
        conn.close()
    return _row_to_dict(row)


def track_ai_call(func_name: str, model: str):
    """
    装饰器：追踪 ai_client 中的 AI 调用，自动记录 token 用量。

    用法：
        @track_ai_call("generate_theme_analysis", model="deepseek-v4-flash")
        def generate_theme_analysis(...):
            ...
    """
    def decorator(original_func):
        def wrapper(*args, **kwargs):
            try:
                result = original_func(*args, **kwargs)
                try:
                    _extract_and_record(result, model, func_name)
                except Exception as exc:
                    _log.debug("token 记录失败: %s", exc)
                return result
            except Exception:
                raise
        return wrapper
    return decorator


def _extract_and_record(result: object, model: str, func_name: str) -> None:
    """从 OpenAI Response 对象中提取 usage 并记录"""
    try:
        # 尝试从结果中提取 usage
        if hasattr(result, 'usage') and result.usage:
            usage = result.usage
            record_usage(
                model=model,
                prompt_tokens=getattr(usage, 'prompt_tokens', 0) or 0,
                completion_tokens=getattr(usage, 'completion_tokens', 0) or 0,
                total_tokens=getattr(usage, 'total_tokens', 0) or 0,
                function_name=func_name,
            )
    except Exception:
        pass


def track_openai_response(response, model: str, func_name: str = "") -> None:
    """
    直接在 OpenAI 调用处手动埋点。
    在每次 client.chat.completions.create() 调用后立即调用本函数。

    Args:
        response: OpenAI chat completion response 对象
        model: 模型名称
        func_name: 调用函数名
    """
    try:
        usage = getattr(response, 'usage', None)
        if usage:
            record_usage(
                model=model,
                prompt_tokens=getattr(usage, 'prompt_tokens', 0) or 0,
                completion_tokens=getattr(usage, 'completion_tokens', 0) or 0,
                total_tokens=getattr(usage, 'total_tokens', 0) or 0,
                function_name=func_name,
            )
    except Exception as exc:
        _log.debug("token_usage 记录失败: %s", exc)


def format_usage_summary(usage: dict) -> str:
    """格式化用量摘要为可读字符串"""
    if not usage or usage.get("call_count", 0) == 0:
        return "暂无调用记录"
    total_tokens = usage.get("total_tokens", 0)
    cost = usage.get("cost_total", 0)
    calls = usage.get("call_count", 0)

    if total_tokens >= 1_000_000:
        token_str = f"{total_tokens / 1_000_000:.1f}M tokens"
    elif total_tokens >= 1_000:
        token_str = f"{total_tokens / 1_000:.1f}K tokens"
    else:
        token_str = f"{total_tokens} tokens"

    return f"{calls} 次调用 / {token_str} / ¥{cost:.4f}"
