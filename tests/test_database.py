"""
数据库模块单元测试
"""
import os
import sys
import tempfile
import pytest
import pandas as pd

# 确保能导入项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.database as db
from config import DB_PATH as _ORIGINAL_DB_PATH


@pytest.fixture(autouse=True)
def use_temp_db(monkeypatch):
    """每个测试使用独立临时数据库"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr("core.database.DB_PATH", path)
    db.init_db()
    yield
    # 清理
    try:
        os.unlink(path)
    except OSError:
        pass


# ---- 样本数据 ----

def _sample_df() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "theme_name": "固态电池",
            "level1": "上游材料",
            "level2": "电解质",
            "level3": "氧化物电解质",
            "stock_code": "000001",
            "stock_name": "测试A",
            "market_type": "主板",
            "role": "龙头",
            "logic_summary": "核心电解液供应商",
            "market_position": "国内第一",
            "market_share": "30%",
            "customers": "宁德时代",
            "importance": "高",
            "source": "研究报告",
            "notes": "",
            "tier": "核心",
            "biz_relevance": 9,
            "biz_growth": 8,
            "quality_score": 7,
            "flow_score": 8,
        },
        {
            "theme_name": "固态电池",
            "level1": "上游材料",
            "level2": "电解质",
            "level3": "硫化物电解质",
            "stock_code": "000002",
            "stock_name": "测试B",
            "market_type": "创业板",
            "role": "供应商",
            "logic_summary": "硫化物路线领先",
            "market_position": "国内前三",
            "market_share": "15%",
            "customers": "比亚迪",
            "importance": "中",
            "source": "行业推断",
            "notes": "",
            "tier": "次级",
            "biz_relevance": 7,
            "biz_growth": 9,
            "quality_score": 6,
            "flow_score": 5,
        },
        {
            "theme_name": "人形机器人",
            "level1": "核心部件",
            "level2": "减速器",
            "level3": "谐波减速器",
            "stock_code": "000001",  # 跨题材
            "stock_name": "测试A",
            "market_type": "主板",
            "role": "核心供应商",
            "logic_summary": "谐波减速器国内龙头",
            "market_position": "国内第一",
            "market_share": "40%",
            "customers": "特斯拉",
            "importance": "高",
            "source": "公告",
            "notes": "",
            "tier": "核心",
            "biz_relevance": 9,
            "biz_growth": 8,
            "quality_score": 8,
            "flow_score": 9,
        },
    ])


# ---- 建表 ----

def test_init_db_creates_tables():
    """建表后应能插入查询"""
    df = pd.DataFrame([{
        "theme_name": "测试题材",
        "level1": "环节1",
        "level2": "方向1",
        "level3": "细分1",
        "stock_code": "600000",
        "stock_name": "测试公司",
        "market_type": "主板",
    }])
    n = db.import_dataframe(df)
    assert n == 1
    assert db.get_db_stats()["total_rows"] == 1


def test_ensure_columns_adds_missing():
    """补齐缺失列不应报错"""
    with db.get_connection() as conn:
        # 传入已存在的列，应静默跳过
        db._ensure_columns(conn, "theme_stocks", {"tier": "TEXT DEFAULT ''"})


def test_ensure_columns_rejects_unknown_table():
    """白名单外的表名应被忽略"""
    with db.get_connection() as conn:
        db._ensure_columns(conn, "nonexistent_table", {"col": "TEXT"})


# ---- 导入 ----

def test_import_dataframe():
    """批量导入 DataFrame"""
    n = db.import_dataframe(_sample_df())
    assert n == 3


def test_import_missing_required_cols():
    """缺少必填列应抛出 ValueError"""
    df = pd.DataFrame([{"stock_code": "000001"}])
    with pytest.raises(ValueError, match="缺少必须列"):
        db.import_dataframe(df)


def test_import_fills_optional_cols():
    """可选列为空时应填充默认值"""
    df = pd.DataFrame([{
        "theme_name": "测试",
        "level1": "L1",
        "level2": "L2",
        "level3": "L3",
        "stock_code": "600001",
        "stock_name": "公司",
        "market_type": "主板",
    }])
    db.import_dataframe(df)
    result = db.get_stock_by_code("600001")
    assert result is not None
    assert result["importance"] == "中"
    assert result["tier"] == ""


def test_import_normalizes_stock_code():
    """股票代码自动补零到 6 位"""
    df = pd.DataFrame([{
        "theme_name": "测试",
        "level1": "L1",
        "level2": "L2",
        "level3": "L3",
        "stock_code": "1",
        "stock_name": "公司",
        "market_type": "主板",
    }])
    db.import_dataframe(df)
    result = db.get_stock_by_code("000001")
    assert result is not None
    assert result["stock_code"] == "000001"


def test_import_normalizes_importance():
    """非法 importance 值应归为中"""
    df = pd.DataFrame([{
        "theme_name": "测试",
        "level1": "L1",
        "level2": "L2",
        "level3": "L3",
        "stock_code": "600002",
        "stock_name": "公司",
        "market_type": "主板",
        "importance": "超高",
    }])
    db.import_dataframe(df)
    result = db.get_stock_by_code("600002")
    assert result["importance"] == "中"


# ---- 查询 ----

def test_get_theme_summary():
    """题材汇总应正确统计"""
    db.import_dataframe(_sample_df())
    summary = db.get_theme_summary()
    assert len(summary) == 2
    solid = summary[summary["theme_name"] == "固态电池"].iloc[0]
    assert solid["stock_count"] == 2
    assert solid["high_importance_count"] == 1


def test_get_distinct_themes():
    """获取去重题材名"""
    db.import_dataframe(_sample_df())
    themes = db.get_distinct_themes()
    assert set(themes) == {"固态电池", "人形机器人"}


def test_get_stock_by_code():
    """按代码查询个股"""
    db.import_dataframe(_sample_df())
    stock = db.get_stock_by_code("000001")
    assert stock is not None
    assert stock["stock_name"] == "测试A"
    assert stock["theme_name"] == "固态电池"  # 第一条匹配


def test_get_stock_by_code_not_found():
    """查询不存在的代码返回 None"""
    assert db.get_stock_by_code("999999") is None


def test_search_stocks_keyword():
    """关键字搜索"""
    db.import_dataframe(_sample_df())
    results = db.search_stocks(keyword="电解质")
    assert len(results) == 2


def test_search_stocks_market_type():
    """市场类型过滤"""
    db.import_dataframe(_sample_df())
    results = db.search_stocks(market_type="创业板")
    assert len(results) == 1
    assert results.iloc[0]["stock_name"] == "测试B"


def test_search_stocks_importance():
    """重要性过滤"""
    db.import_dataframe(_sample_df())
    results = db.search_stocks(importance="高")
    assert len(results) == 2


def test_search_stocks_theme():
    """题材过滤"""
    db.import_dataframe(_sample_df())
    results = db.search_stocks(theme_name="人形机器人")
    assert len(results) == 1


def test_get_distinct_levels():
    """获取层级去重值"""
    db.import_dataframe(_sample_df())
    levels = db.get_distinct_levels("固态电池", "level1")
    assert "上游材料" in levels


def test_get_distinct_levels_invalid():
    """非法列名返回空列表"""
    assert db.get_distinct_levels("固态电池", "level99") == []


def test_get_theme_tree_data():
    """获取题材树数据"""
    db.import_dataframe(_sample_df())
    df = db.get_theme_tree_data("固态电池")
    assert len(df) == 2


def test_get_db_stats():
    """统计信息"""
    db.import_dataframe(_sample_df())
    stats = db.get_db_stats()
    assert stats["theme_count"] == 2
    assert stats["stock_count"] == 2  # 000001 和 000002
    assert stats["total_rows"] == 3


def test_export_dataframe():
    """导出为 DataFrame"""
    db.import_dataframe(_sample_df())
    df = db.export_dataframe()
    assert len(df) == 3
    # 按题材导出
    df2 = db.export_dataframe("固态电池")
    assert len(df2) == 2


# ---- 跨题材 ----

def test_get_cross_theme_stocks():
    """跨题材个股检测"""
    db.import_dataframe(_sample_df())
    cross = db.get_cross_theme_stocks()
    assert len(cross) == 1
    assert cross.iloc[0]["stock_code"] == "000001"


def test_get_stock_themes():
    """获取股票所属题材"""
    db.import_dataframe(_sample_df())
    themes = db.get_stock_themes("000001")
    assert set(themes) == {"固态电池", "人形机器人"}


# ---- 题材对比 ----

def test_get_theme_compare_data():
    """题材对比数据"""
    db.import_dataframe(_sample_df())
    data = db.get_theme_compare_data(["固态电池", "人形机器人"])
    assert len(data["per_theme"]) == 2
    # 共有个股（000001 同时出现在两个题材中）
    assert len(data["common_stocks"]) == 1


def test_get_theme_compare_empty():
    """空列表返回空字典"""
    assert db.get_theme_compare_data([]) == {}


# ---- 删除 ----

def test_delete_theme():
    """删除题材"""
    db.import_dataframe(_sample_df())
    n = db.delete_theme("固态电池")
    assert n == 2
    assert "固态电池" not in db.get_distinct_themes()
    assert "人形机器人" in db.get_distinct_themes()


# ---- 覆盖导入 ----

def test_replace_theme():
    """覆盖式导入"""
    db.import_dataframe(_sample_df())
    new_data = pd.DataFrame([{
        "theme_name": "固态电池",
        "level1": "新材料",
        "level2": "正极",
        "level3": "高镍",
        "stock_code": "600100",
        "stock_name": "新公司",
        "market_type": "科创板",
    }])
    n = db.replace_theme("固态电池", new_data)
    assert n == 1
    # 固态电池的旧数据被清除（000002 只在固态电池中）
    assert db.get_stock_by_code("000002") is None
    # 跨题材股票不受影响（000001 也在人形机器人中）
    assert db.get_stock_by_code("000001") is not None
    # 新数据存在
    assert db.get_stock_by_code("600100") is not None
    # 其他题材不受影响
    assert "人形机器人" in db.get_distinct_themes()


# ---- 题材质量 ----

def test_upsert_theme_quality():
    """保存题材质量评分"""
    db.upsert_theme_quality("固态电池", {
        "breadth": 8,
        "event_density": 7,
        "capital_flow": 6,
        "sustainability": 7,
        "overall_score": 7,
        "summary": "测试摘要",
    })
    with db.get_connection() as conn:
        row = conn.execute("SELECT * FROM theme_quality WHERE theme_name = ?", ["固态电池"]).fetchone()
    assert row is not None
    assert row["overall_score"] == 7
    assert row["summary"] == "测试摘要"


def test_upsert_theme_quality_none():
    """空数据不应报错"""
    db.upsert_theme_quality("", None)
    db.upsert_theme_quality("空题材", None)
    db.upsert_theme_quality("", {"breadth": 5})


# ---- 树构建 ----

def test_build_tree():
    """嵌套字典树"""
    df = pd.DataFrame([
        {"level1": "上游", "level2": "材料", "level3": "A", "stock_name": "X", "stock_code": "000001", "id": 1, "theme_name": "T"},
        {"level1": "上游", "level2": "材料", "level3": "B", "stock_name": "Y", "stock_code": "000002", "id": 2, "theme_name": "T"},
        {"level1": "下游", "level2": "应用", "level3": "C", "stock_name": "Z", "stock_code": "000003", "id": 3, "theme_name": "T"},
    ])
    tree = db.build_tree(df)
    assert "上游" in tree
    assert "下游" in tree
    assert len(tree["上游"]["材料"]["A"]) == 1
    assert tree["上游"]["材料"]["A"][0]["stock_name"] == "X"


def test_build_tree_empty_levels():
    """空层级替换为 (未分类)"""
    df = pd.DataFrame([{
        "level1": "上游", "level2": "", "level3": "",
        "stock_name": "X", "stock_code": "000001", "id": 1, "theme_name": "T",
    }])
    tree = db.build_tree(df)
    assert "(未分类)" in tree["上游"]
    assert "(未分类)" in tree["上游"]["(未分类)"]


# ---- 清空 ----

def test_clear_all():
    """清空所有数据"""
    db.import_dataframe(_sample_df())
    db.upsert_theme_quality("固态电池", {"overall_score": 5, "summary": "test"})
    db.clear_all()
    assert db.get_db_stats()["total_rows"] == 0
    assert db.get_distinct_themes() == []


# ---- 热点候选题材 ----

def _sample_news():
    return [
        {
            "news_id": "n1",
            "title": "HBM产业链景气上行",
            "summary": "AI服务器需求带动HBM需求",
            "content": "",
            "source": "eastmoney.com",
            "url": "https://example.com/n1",
            "published_at": "",
            "fetched_at": "2026-05-26 10:00:00",
            "search_query": "HBM A股",
            "category": "半导体",
        },
        {
            "news_id": "n2",
            "title": "先进封装需求增长",
            "summary": "先进封装受益AI芯片",
            "content": "",
            "source": "cls.cn",
            "url": "https://example.com/n2",
            "published_at": "",
            "fetched_at": "2026-05-26 10:01:00",
            "search_query": "先进封装 A股",
            "category": "半导体",
        },
    ]


def _sample_candidate_topics():
    return [
        {
            "topic_name": "HBM高带宽内存",
            "heat_score": 82,
            "heat_level": "高",
            "trigger_event": "AI服务器需求提升",
            "core_logic": "HBM需求增长带动产业链",
            "evidence_summary": "两条资讯共同指向HBM和先进封装",
            "source_items": [
                {"news_id": "n1", "relevance_score": 90, "reason": "直接提及HBM"},
                {"news_id": "n2", "relevance_score": 72, "reason": "先进封装相关"},
            ],
            "suggested_chains": ["存储芯片", "先进封装"],
            "related_keywords": ["HBM", "AI服务器"],
            "preliminary_related_stocks": ["香农芯创"],
            "confidence": "高",
            "should_import": True,
            "reason_to_import": "题材可拆解",
            "risk_note": "需核验业务占比",
        }
    ]


def test_save_raw_news_upsert():
    news = _sample_news()
    assert db.save_raw_news(news) == 2
    assert db.save_raw_news(news) == 2
    with db.get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM raw_news").fetchone()[0]
    assert count == 2


def test_get_raw_news_by_ids_keeps_order():
    db.save_raw_news(_sample_news())
    rows = db.get_raw_news_by_ids(["n2", "n1", "missing"])
    assert [row["news_id"] for row in rows] == ["n2", "n1"]


def test_save_hot_topic_candidates_and_evidence():
    news = _sample_news()
    news_by_id = {item["news_id"]: item for item in news}
    saved = db.save_hot_topic_candidates(_sample_candidate_topics(), news_by_id)
    assert saved == 1
    candidates = db.get_hot_topic_candidates()
    assert len(candidates) == 1
    assert candidates[0]["topic_name"] == "HBM高带宽内存"
    assert candidates[0]["evidence_count"] == 2
    evidence = db.get_topic_evidence(candidates[0]["topic_id"])
    assert len(evidence) == 2
    assert evidence[0]["news_id"] in {"n1", "n2"}


# ---- 分析草稿 ----

def _sample_draft():
    return {
        "topic_name": "HBM高带宽内存",
        "theme_definition": "HBM产业链",
        "trigger_event": "AI服务器需求提升",
        "core_logic": "高带宽内存需求增长",
        "industry_scope": "存储、封装、设备",
        "excluded_scope": "泛AI应用",
        "chain_nodes": [
            {
                "level1": "上游",
                "level2": "材料",
                "level3": "封装基板",
                "node_description": "先进封装材料",
                "why_it_matters": "影响良率",
                "importance": "核心",
            }
        ],
        "stocks": [
            {
                "stock_code": "002156",
                "stock_name": "通富微电",
                "market_type": "主板",
                "level1": "上游",
                "level2": "材料",
                "level3": "封装基板",
                "role": "封测厂商",
                "logic_summary": "先进封装相关",
                "market_position": "待核验",
                "market_share": "待核验",
                "customers": "待核验",
                "products": "封测",
                "evidence": "新闻证据",
                "relevance_score": 8,
                "importance": "重要",
                "verification_status": "待人工核验",
                "risk_note": "需核验HBM占比",
            }
        ],
    }


def test_create_and_update_analysis_draft():
    draft_id = db.create_analysis_draft(1, "HBM高带宽内存", _sample_draft())
    row = db.get_analysis_draft(draft_id)
    assert row is not None
    assert row["status"] == "draft"
    assert row["draft"]["topic_name"] == "HBM高带宽内存"
    draft = row["draft"]
    draft["core_logic"] = "更新逻辑"
    db.update_analysis_draft(draft_id, draft)
    updated = db.get_analysis_draft(draft_id)
    assert updated["draft"]["core_logic"] == "更新逻辑"


def test_confirm_analysis_draft():
    draft_id = db.create_analysis_draft(1, "HBM高带宽内存", _sample_draft())
    n = db.confirm_analysis_draft(draft_id)
    assert n == 1
    row = db.get_analysis_draft(draft_id)
    assert row["status"] == "confirmed"
    stock = db.get_stock_by_code("002156")
    assert stock is not None
    assert stock["theme_name"] == "HBM高带宽内存"
    assert stock["market_share"] == "待核验"


# ---- 空库查询 ----

def test_empty_summary():
    """空库摘要返回空 DataFrame"""
    df = db.get_theme_summary()
    assert df.empty


def test_empty_tree_data():
    """空库树数据返回空 DataFrame"""
    df = db.get_theme_tree_data("不存在")
    assert df.empty
