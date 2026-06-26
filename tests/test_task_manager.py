"""
任务管理器单元测试
"""
import os
import sys
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock streamlit session_state
mock_st = MagicMock()
mock_st.session_state = {}
sys.modules['streamlit'] = mock_st

import tasks.task_manager as tm


@pytest.fixture(autouse=True)
def reset_tasks():
    """每个测试前重置任务状态"""
    mock_st.session_state.clear()
    yield
    mock_st.session_state.clear()


def test_submit_and_get():
    """提交任务后应能读取状态"""
    lock = threading.Event()

    def slow_task():
        lock.wait(timeout=5)
        return 42

    result = tm.submit("task_1", slow_task)
    assert result is True
    state = tm.get("task_1")
    assert state is not None
    assert state["status"] == "running"
    assert state["progress"] == 0.0
    lock.set()  # 释放阻塞，让任务完成


def test_submit_duplicate_running():
    """同 ID 任务运行中时应拒绝重复提交"""
    lock = threading.Event()

    def slow_task():
        lock.wait(timeout=2)
        return 1

    assert tm.submit("dup_task", slow_task) is True
    assert tm.submit("dup_task", slow_task) is False
    lock.set()  # 释放阻塞


def test_get_nonexistent():
    """读取不存在的任务应返回 None"""
    assert tm.get("nonexistent") is None


def test_clear():
    """清除任务后应读取不到"""
    def dummy():
        return 1

    tm.submit("to_clear", dummy)
    tm.clear("to_clear")
    assert tm.get("to_clear") is None


def test_is_running():
    """is_running 应正确反映任务状态"""
    lock = threading.Event()

    def slow_task():
        lock.wait(timeout=2)
        return 1

    tm.submit("running_task", slow_task)
    assert tm.is_running("running_task") is True
    assert tm.is_running("nonexistent") is False
    lock.set()


def test_running_count():
    """running_count 应正确统计"""
    lock = threading.Event()

    def slow_task():
        lock.wait(timeout=2)
        return 1

    tm.submit("task_a", slow_task)
    tm.submit("task_b", slow_task)
    assert tm.running_count() == 2
    lock.set()


def test_update_progress():
    """update_progress 应更新进度"""
    lock = threading.Event()

    def slow_task():
        lock.wait(timeout=2)
        return 1

    tm.submit("progress_task", slow_task)
    tm.update_progress("progress_task", 0.5, "处理中")
    state = tm.get("progress_task")
    assert state["progress"] == 0.5
    assert state["progress_msg"] == "处理中"
    lock.set()


def test_update_progress_ignored_when_not_running():
    """任务完成后 update_progress 应被忽略"""
    def dummy():
        return 1

    tm.submit("done_task", dummy)
    time.sleep(0.1)  # 等待任务完成
    tm.update_progress("done_task", 0.5, "应该被忽略")
    state = tm.get("done_task")
    assert state["progress"] == 1.0  # 任务完成后进度为1.0


def test_task_completion():
    """任务完成后状态应为 completed"""
    def dummy():
        return 42

    tm.submit("complete_task", dummy)
    time.sleep(0.1)  # 等待任务完成
    state = tm.get("complete_task")
    assert state["status"] == "completed"
    assert state["result"] == 42
    assert state["progress"] == 1.0


def test_task_failure():
    """任务失败后状态应为 failed"""
    def failing():
        raise ValueError("测试错误")

    tm.submit("fail_task", failing)
    time.sleep(0.1)  # 等待任务完成
    state = tm.get("fail_task")
    assert state["status"] == "failed"
    assert "测试错误" in state["error"]


def test_cleanup_same_family():
    """同族任务清理应正常工作"""
    def dummy():
        return 1

    # 提交并完成任务
    tm.submit("hot_search_1", dummy)
    time.sleep(0.1)

    # 提交同族新任务
    tm.submit("hot_search_2", dummy)

    # 旧任务应该被清理
    assert tm.get("hot_search_1") is None
    assert tm.get("hot_search_2") is not None


def test_get_all():
    """get_all 应返回所有任务"""
    def dummy():
        return 1

    tm.submit("all_task_1", dummy)
    tm.submit("all_task_2", dummy)
    all_tasks = tm.get_all()
    assert "all_task_1" in all_tasks
    assert "all_task_2" in all_tasks


if __name__ == "__main__":
    pytest.main([__file__])