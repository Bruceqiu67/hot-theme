"""
后台任务管理器 — 让 AI 长任务在后台线程中运行，不阻塞页面切换。

原理：长任务由 daemon 线程执行，状态存储在 st.session_state 的共享字典中。
Streamlit rerun 不会终止后台线程，只中断主线程的轮询循环。
用户切换页面后返回，页面重新检测任务状态即可拿到结果。
"""
from __future__ import annotations

import threading
import traceback
from datetime import datetime
from typing import Any, Callable

import streamlit as st

_TASKS_KEY = "_bg_tasks"


def _get_tasks() -> dict:
    """获取或初始化任务状态字典（存储在 st.session_state 中，同一 session 内持久）"""
    if _TASKS_KEY not in st.session_state:
        st.session_state[_TASKS_KEY] = {}
    return st.session_state[_TASKS_KEY]


def submit(task_id: str, fn: Callable, *args: Any, **kwargs: Any) -> bool:
    """
    提交一个后台任务。若同 ID 任务已在运行中则忽略。

    Args:
        task_id: 唯一任务标识（如 "hot_search"、"update_固态电池"）
        fn: 后台线程执行的函数
        *args, **kwargs: 传给 fn

    Returns:
        True 已提交，False 已有同名任务运行中
    """
    tasks = _get_tasks()

    if task_id in tasks and tasks[task_id].get("status") == "running":
        return False

    _cleanup_same_family(task_id)

    tasks[task_id] = {
        "status": "running",
        "started_at": datetime.now().strftime("%H:%M:%S"),
        "result": None,
        "error": None,
        "progress": 0.0,
        "progress_msg": "",
    }

    def _wrapper() -> None:
        task_state = tasks[task_id]
        try:
            result = fn(*args, **kwargs)
            task_state["status"] = "completed"
            task_state["result"] = result
            task_state["progress"] = 1.0
        except Exception as exc:
            task_state["status"] = "failed"
            task_state["error"] = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"

    thread = threading.Thread(target=_wrapper, daemon=True)
    thread.start()
    return True


# ---- 任务族前缀，用于自动清理 ----
_FAMILY_PREFIXES = [
    "hot_search",
    "ferm_search",
    "draft_",
    "update_",
    "ai_gen_",
]


def _cleanup_same_family(task_id: str) -> None:
    """清理与 task_id 同族的已完成/失败任务（保留 running 中的）"""
    tasks = _get_tasks()
    for prefix in _FAMILY_PREFIXES:
        if task_id.startswith(prefix) or task_id == prefix:
            stale = [
                tid for tid, t in tasks.items()
                if tid.startswith(prefix) and t.get("status") != "running"
            ]
            for tid in stale:
                del tasks[tid]
            break


def get(task_id: str) -> dict | None:
    """读取任务状态，不存在返回 None"""
    return _get_tasks().get(task_id)


def clear(task_id: str) -> None:
    """移除任务记录"""
    _get_tasks().pop(task_id, None)


def get_all() -> dict:
    """返回所有任务 {task_id: state_dict}"""
    return dict(_get_tasks())


def is_running(task_id: str) -> bool:
    """任务是否仍在执行中"""
    t = get(task_id)
    return t is not None and t.get("status") == "running"


def running_count() -> int:
    """当前运行中的任务数"""
    return sum(1 for t in _get_tasks().values() if t.get("status") == "running")


def update_progress(task_id: str, progress: float, msg: str = "") -> None:
    """
    供后台线程更新任务进度（0.0 ~ 1.0）。
    仅当任务存在且 running 时生效。
    """
    tasks = _get_tasks()
    t = tasks.get(task_id)
    if t and t.get("status") == "running":
        t["progress"] = min(max(float(progress), 0.0), 1.0)
        if msg:
            t["progress_msg"] = str(msg)
