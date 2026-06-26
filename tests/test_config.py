"""
配置模块单元测试
"""
import os
import sys
import logging

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    BASE_DIR,
    DATA_DIR,
    DB_PATH,
    LOG_FILE,
    MARKET_TYPES,
    IMPORTANCE_LEVELS,
    get_logger,
)


class TestPaths:
    """测试路径配置"""

    def test_base_dir_exists(self):
        """BASE_DIR 应该存在"""
        assert os.path.isdir(BASE_DIR)

    def test_data_dir_is_under_base(self):
        """DATA_DIR 应该在 BASE_DIR 下"""
        assert DATA_DIR.startswith(BASE_DIR)

    def test_db_path_is_under_data(self):
        """DB_PATH 应该在 DATA_DIR 下"""
        assert DB_PATH.startswith(DATA_DIR)
        assert DB_PATH.endswith(".db")

    def test_log_file_is_under_data(self):
        """LOG_FILE 应该在 DATA_DIR 下"""
        assert LOG_FILE.startswith(DATA_DIR)
        assert LOG_FILE.endswith(".log")


class TestGetLogger:
    """测试日志获取函数"""

    def test_returns_logger_instance(self):
        """应该返回 Logger 实例"""
        logger = get_logger("test_module")
        assert isinstance(logger, logging.Logger)

    def test_logger_name(self):
        """Logger 名称应该正确"""
        logger = get_logger("my_module")
        assert logger.name == "my_module"

    def test_same_name_returns_same_logger(self):
        """相同名称应该返回相同的 Logger"""
        logger1 = get_logger("same_name")
        logger2 = get_logger("same_name")
        assert logger1 is logger2


class TestMarketTypes:
    """测试市场类型映射"""

    def test_contains_all_types(self):
        """应该包含所有市场类型"""
        assert "全部" in MARKET_TYPES
        assert "主板" in MARKET_TYPES
        assert "创业板" in MARKET_TYPES
        assert "科创板" in MARKET_TYPES
        assert "北交所" in MARKET_TYPES

    def test_all_maps_to_empty(self):
        """全部应该映射为空字符串"""
        assert MARKET_TYPES["全部"] == ""

    def test_others_map_to_self(self):
        """其他类型应该映射为自身"""
        assert MARKET_TYPES["主板"] == "主板"
        assert MARKET_TYPES["创业板"] == "创业板"
        assert MARKET_TYPES["科创板"] == "科创板"
        assert MARKET_TYPES["北交所"] == "北交所"


class TestImportanceLevels:
    """测试重要性级别映射"""

    def test_contains_all_levels(self):
        """应该包含所有重要性级别"""
        assert "全部" in IMPORTANCE_LEVELS
        assert "高" in IMPORTANCE_LEVELS
        assert "中" in IMPORTANCE_LEVELS
        assert "低" in IMPORTANCE_LEVELS

    def test_all_maps_to_empty(self):
        """全部应该映射为空字符串"""
        assert IMPORTANCE_LEVELS["全部"] == ""

    def test_others_map_to_self(self):
        """其他级别应该映射为自身"""
        assert IMPORTANCE_LEVELS["高"] == "高"
        assert IMPORTANCE_LEVELS["中"] == "中"
        assert IMPORTANCE_LEVELS["低"] == "低"


if __name__ == "__main__":
    pytest.main([__file__])