"""
全局配置
"""
import os
import logging

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "theme_tracker.db")

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)

# ---- 日志 ----
LOG_FILE = os.path.join(DATA_DIR, "app.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

def get_logger(name: str) -> logging.Logger:
    """获取模块级 logger"""
    return logging.getLogger(name)

# 市场类型映射（显示名 → 数据库值）
MARKET_TYPES = {
    "全部": "",
    "主板": "主板",
    "创业板": "创业板",
    "科创板": "科创板",
    "北交所": "北交所",
}

# 重要性映射
IMPORTANCE_LEVELS = {
    "全部": "",
    "高": "高",
    "中": "中",
    "低": "低",
}

# ---- P1-5: 一键发现智能默认值 ----
DISCOVERY_DEFAULTS = {
    "search_scopes": ["全市场热点", "科技成长"],
    "time_range": "最近 24 小时",
    "results_per_query": 6,
    "max_queries": 8,
    "enable_market_validation": True,
}

FERMENTATION_DEFAULTS = {
    "search_scopes": ["全市场热点", "科技成长", "新能源"],
    "time_range": "最近 24 小时",
    "results_per_query": 6,
}

# ---- P2-7: 搜索层配置 ----
# 国内网络环境下，Google/Yahoo/Brave 等 DDGS 后端均被墙。
# 优先使用 Bing (cn.bing.com 国内可直接访问)，DDGS 作为降级回退。
SEARCH_CONFIG = {
    # 搜索引擎优先级：按顺序尝试，首个返回结果即停止
    # "bing" — cn.bing.com (国内可用，推荐首选)
    # "ddgs_api" — DuckDuckGo API via DDGS (可能可用)
    # "ddgs_yandex" — Yandex via DDGS (俄罗斯引擎，国内偶尔可用)
    "provider_order": ["bing", "ddgs_api"],
    # 单次搜索超时（秒）
    "timeout": 12,
    # 同引擎连续请求最小间隔（秒），避免被限流
    "rate_limit_delay": 0.3,
}
