"""
SQLite 数据库操作模块
P2-14: 版本化数据库迁移机制
"""
import sqlite3
import json
from contextlib import contextmanager
import pandas as pd
from datetime import datetime
from config import DB_PATH, get_logger

_log = get_logger("database")

# P2-14: 数据库 Schema 版本号
SCHEMA_VERSION = 3


@contextmanager
def get_connection():
    """获取数据库连接（上下文管理器，自动关闭）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """初始化数据库表与索引"""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS theme_stocks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                theme_name  TEXT    NOT NULL,
                level1      TEXT    NOT NULL DEFAULT '',
                level2      TEXT    DEFAULT '',
                level3      TEXT    DEFAULT '',
                stock_code  TEXT    NOT NULL,
                stock_name  TEXT    NOT NULL,
                market_type TEXT    NOT NULL,
                role        TEXT    DEFAULT '',
                logic_summary TEXT  DEFAULT '',
                market_position TEXT DEFAULT '',
                market_share TEXT   DEFAULT '',
                customers   TEXT    DEFAULT '',
                importance  TEXT    DEFAULT '中',
                source      TEXT    DEFAULT '',
                notes       TEXT    DEFAULT '',
                tier        TEXT    DEFAULT '',
                biz_relevance INTEGER,
                biz_growth  INTEGER,
                quality_score INTEGER,
                flow_score  INTEGER,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        _ensure_columns(conn, "theme_stocks", {
            "tier": "TEXT DEFAULT ''",
            "biz_relevance": "INTEGER",
            "biz_growth": "INTEGER",
            "quality_score": "INTEGER",
            "flow_score": "INTEGER",
            "verification_status": "TEXT DEFAULT '待核验'",
            "verification_details": "TEXT DEFAULT ''",
            "verified_at": "TIMESTAMP",
        })
        conn.execute("""
            CREATE TABLE IF NOT EXISTS theme_quality (
                theme_name    TEXT PRIMARY KEY,
                breadth       INTEGER,
                event_density INTEGER,
                capital_flow  INTEGER,
                sustainability INTEGER,
                overall_score INTEGER,
                summary       TEXT DEFAULT '',
                updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS raw_news (
                news_id      TEXT PRIMARY KEY,
                title        TEXT DEFAULT '',
                summary      TEXT DEFAULT '',
                content      TEXT DEFAULT '',
                source       TEXT DEFAULT '',
                url          TEXT DEFAULT '',
                published_at TEXT DEFAULT '',
                fetched_at   TEXT DEFAULT '',
                search_query TEXT DEFAULT '',
                category     TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hot_topics (
                topic_id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_name                  TEXT NOT NULL,
                heat_score                  INTEGER,
                heat_level                  TEXT DEFAULT '',
                trigger_event               TEXT DEFAULT '',
                core_logic                  TEXT DEFAULT '',
                evidence_summary            TEXT DEFAULT '',
                suggested_chains            TEXT DEFAULT '',
                related_keywords            TEXT DEFAULT '',
                preliminary_related_stocks  TEXT DEFAULT '',
                confidence                  TEXT DEFAULT '',
                should_import               INTEGER DEFAULT 0,
                reason_to_import            TEXT DEFAULT '',
                risk_note                   TEXT DEFAULT '',
                created_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        _ensure_columns(conn, "hot_topics", {
            "topic_type": "TEXT DEFAULT ''",
            "parent_theme": "TEXT DEFAULT ''",
            "specificity_score": "INTEGER",
            "novelty_score": "INTEGER",
            "key_entities": "TEXT DEFAULT ''",
            "second_round_queries": "TEXT DEFAULT ''",
        })
        conn.execute("""
            CREATE TABLE IF NOT EXISTS topic_evidence (
                topic_id        INTEGER NOT NULL,
                news_id         TEXT NOT NULL,
                relevance_score INTEGER,
                reason          TEXT DEFAULT '',
                PRIMARY KEY (topic_id, news_id),
                FOREIGN KEY(topic_id) REFERENCES hot_topics(topic_id) ON DELETE CASCADE,
                FOREIGN KEY(news_id) REFERENCES raw_news(news_id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS analysis_drafts (
                draft_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id    INTEGER,
                topic_name  TEXT NOT NULL,
                draft_json  TEXT NOT NULL,
                status      TEXT DEFAULT 'draft',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_theme    ON theme_stocks(theme_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_code     ON theme_stocks(stock_code)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_name     ON theme_stocks(stock_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_market   ON theme_stocks(market_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_importance ON theme_stocks(importance)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_level1   ON theme_stocks(level1)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tier     ON theme_stocks(tier)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_news_category ON raw_news(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_news_fetched  ON raw_news(fetched_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hot_created   ON hot_topics(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_draft_status  ON analysis_drafts(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_draft_topic   ON analysis_drafts(topic_id)")
        conn.commit()

    # P2-14: 执行版本化迁移
    _run_migrations()


# 合法的表名（白名单，防止 SQL 注入）
_VALID_TABLES = frozenset({"theme_stocks", "theme_quality", "raw_news", "hot_topics", "topic_evidence", "analysis_drafts", "db_info", "watchlist"})


def _ensure_columns(conn: sqlite3.Connection, table_name: str, columns: dict[str, str]) -> None:
    """为旧数据库补齐新增列（白名单校验表名，安全拼接）"""
    if table_name not in _VALID_TABLES:
        return
    existing = {
        row["name"]
        for row in conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    }
    for col, definition in columns.items():
        if col not in existing:
            conn.execute(f'ALTER TABLE "{table_name}" ADD COLUMN "{col}" {definition}')


# ---- P2-14: 版本化迁移机制 ----

def _ensure_db_info(conn: sqlite3.Connection) -> None:
    """创建 db_info 表（如果不存在）"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS db_info (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)


def _get_schema_version(conn: sqlite3.Connection) -> int:
    """读取当前数据库的 schema 版本号"""
    _ensure_db_info(conn)
    row = conn.execute("SELECT value FROM db_info WHERE key = 'schema_version'").fetchone()
    if row:
        try:
            return int(row["value"])
        except (ValueError, TypeError):
            return 0
    # 旧数据库：无 db_info 记录，默认版本 0
    # 但通过 _ensure_columns 补齐的视为版本 1
    conn.execute(
        "INSERT INTO db_info (key, value) VALUES ('schema_version', '0')"
    )
    return 0


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """更新 schema 版本号"""
    conn.execute(
        "INSERT OR REPLACE INTO db_info (key, value) VALUES ('schema_version', ?)",
        [str(version)],
    )


def _run_migrations() -> None:
    """
    按版本号顺序执行数据库迁移。
    向下兼容：自动检测旧数据库并补齐所有缺失的变更。
    """
    with get_connection() as conn:
        current = _get_schema_version(conn)
        _log.info("当前数据库 schema_version=%d, 目标=%d", current, SCHEMA_VERSION)

        if current >= SCHEMA_VERSION:
            return

        # ---- 迁移 v0 → v1 (初始版本补齐) ----
        if current < 1:
            _log.info("执行迁移: v0 → v1 (补齐基础列)")
            # 补齐 theme_stocks 追加列
            _ensure_columns(conn, "theme_stocks", {
                "tier": "TEXT DEFAULT ''",
                "biz_relevance": "INTEGER",
                "biz_growth": "INTEGER",
                "quality_score": "INTEGER",
                "flow_score": "INTEGER",
            })
            # 补齐 hot_topics 追加列
            _ensure_columns(conn, "hot_topics", {
                "topic_type": "TEXT DEFAULT ''",
                "parent_theme": "TEXT DEFAULT ''",
                "specificity_score": "INTEGER",
                "novelty_score": "INTEGER",
                "key_entities": "TEXT DEFAULT ''",
                "second_round_queries": "TEXT DEFAULT ''",
            })
            # 补齐 v1 索引
            for idx_sql in [
                "CREATE INDEX IF NOT EXISTS idx_tier ON theme_stocks(tier)",
            ]:
                try:
                    conn.execute(idx_sql)
                except Exception:
                    pass
            _set_schema_version(conn, 1)

        # ---- 迁移 v1 → v2 (个股验证 + 新鲜度) ----
        if current < 2:
            _log.info("执行迁移: v1 → v2 (个股验证字段)")
            _ensure_columns(conn, "theme_stocks", {
                "verification_status": "TEXT DEFAULT '待核验'",
                "verification_details": "TEXT DEFAULT ''",
                "verified_at": "TIMESTAMP",
            })
            _set_schema_version(conn, 2)

        # ---- 迁移 v2 → v3 (watchlist + token_usage) ----
        if current < 3:
            _log.info("执行迁移: v2 → v3 (关注列表)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_type   TEXT    NOT NULL CHECK(item_type IN ('theme', 'stock')),
                    item_id     TEXT    NOT NULL,
                    added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    notes       TEXT    DEFAULT '',
                    has_update  INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_type ON watchlist(item_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_item ON watchlist(item_id)")
            _set_schema_version(conn, 3)

        conn.commit()
        _log.info("数据库迁移完成，当前 schema_version=%d", SCHEMA_VERSION)


def clear_all() -> None:
    """清空所有数据（事务保护）"""
    with get_connection() as conn:
        try:
            conn.execute("DELETE FROM theme_stocks")
            conn.execute("DELETE FROM theme_quality")
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def delete_theme(theme_name: str) -> int:
    """删除指定题材的所有数据，返回删除行数"""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM theme_stocks WHERE theme_name = ?", [theme_name]
        )
        conn.execute("DELETE FROM theme_quality WHERE theme_name = ?", [theme_name])
        deleted = cursor.rowcount
        conn.commit()
        return deleted


def _to_nullable_int(value) -> int | None:
    """将评分字段转为整数，空值或非法值返回 None"""
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def import_dataframe(df: pd.DataFrame) -> int:
    """将 DataFrame 导入数据库，返回导入行数"""
    # 标准化列名（去除首尾空格）
    df.columns = df.columns.str.strip()

    required_cols = [
        "theme_name", "level1", "level2", "level3",
        "stock_code", "stock_name", "market_type",
    ]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"CSV 缺少必须列: {col}")

    # 填充可选字段的空值
    optional_str_cols = [
        "role", "logic_summary", "market_position", "market_share",
        "customers", "importance", "source", "notes", "tier",
    ]
    for col in optional_str_cols:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)
        else:
            df[col] = ""

    if "importance" in df.columns:
        df["importance"] = df["importance"].apply(
            lambda x: x if x in ("高", "中", "低") else "中"
        )

    # 统一 stock_code 为 6 位字符串
    df["stock_code"] = df["stock_code"].astype(str).str.zfill(6)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        cursor = conn.cursor()

        # 构建批量插入的行参数列表
        row_params = [
            (
                str(row["theme_name"]),
                str(row["level1"]),
                str(row.get("level2", "")),
                str(row.get("level3", "")),
                str(row["stock_code"]),
                str(row["stock_name"]),
                str(row["market_type"]),
                str(row.get("role", "")),
                str(row.get("logic_summary", "")),
                str(row.get("market_position", "")),
                str(row.get("market_share", "")),
                str(row.get("customers", "")),
                str(row.get("importance", "中")),
                str(row.get("source", "")),
                str(row.get("notes", "")),
                str(row.get("tier", "")),
                _to_nullable_int(row.get("biz_relevance")),
                _to_nullable_int(row.get("biz_growth")),
                _to_nullable_int(row.get("quality_score")),
                _to_nullable_int(row.get("flow_score")),
                now, now,
            )
            for _, row in df.iterrows()
        ]

        cursor.executemany("""
            INSERT INTO theme_stocks
                (theme_name, level1, level2, level3,
                 stock_code, stock_name, market_type,
                 role, logic_summary, market_position, market_share,
                 customers, importance, source, notes,
                 tier, biz_relevance, biz_growth, quality_score, flow_score,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, row_params)

        conn.commit()
        return len(row_params)


def replace_theme(theme_name: str, df: pd.DataFrame, quality: dict | None = None) -> int:
    """覆盖式导入单个题材（单事务，失败时回滚）"""
    with get_connection() as conn:
        try:
            conn.execute("DELETE FROM theme_stocks WHERE theme_name = ?", [theme_name])
            conn.execute("DELETE FROM theme_quality WHERE theme_name = ?", [theme_name])
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    normalized = df.copy()
    normalized["theme_name"] = theme_name
    n = import_dataframe(normalized)
    upsert_theme_quality(theme_name, quality)
    return n


def upsert_theme_quality(theme_name: str, quality: dict | None) -> None:
    """保存 AI 生成的题材质量评分"""
    if not theme_name or not quality:
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO theme_quality
                (theme_name, breadth, event_density, capital_flow,
                 sustainability, overall_score, summary, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(theme_name) DO UPDATE SET
                breadth = excluded.breadth,
                event_density = excluded.event_density,
                capital_flow = excluded.capital_flow,
                sustainability = excluded.sustainability,
                overall_score = excluded.overall_score,
                summary = excluded.summary,
                updated_at = excluded.updated_at
        """, (
            theme_name,
            quality.get("breadth"),
            quality.get("event_density"),
            quality.get("capital_flow"),
            quality.get("sustainability"),
            quality.get("overall_score"),
            quality.get("summary", ""),
            now,
        ))
        conn.commit()


# ==================== 热点候选题材与证据 ====================

def save_raw_news(news_items: list[dict]) -> int:
    """保存抓取到的原始资讯，按 news_id 去重更新"""
    if not news_items:
        return 0
    with get_connection() as conn:
        rows = [
            (
                item.get("news_id", ""),
                item.get("title", ""),
                item.get("summary", ""),
                item.get("content", ""),
                item.get("source", ""),
                item.get("url", ""),
                item.get("published_at", ""),
                item.get("fetched_at", ""),
                item.get("search_query", ""),
                item.get("category", ""),
            )
            for item in news_items
            if item.get("news_id")
        ]
        conn.executemany("""
            INSERT INTO raw_news
                (news_id, title, summary, content, source, url, published_at,
                 fetched_at, search_query, category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(news_id) DO UPDATE SET
                title = excluded.title,
                summary = excluded.summary,
                content = excluded.content,
                source = excluded.source,
                url = excluded.url,
                published_at = excluded.published_at,
                fetched_at = excluded.fetched_at,
                search_query = excluded.search_query,
                category = excluded.category
        """, rows)
        conn.commit()
        return len(rows)


def get_raw_news_by_ids(news_ids: list[str]) -> list[dict]:
    """按 news_id 批量读取原始资讯，保持入参顺序。"""
    clean_ids = [str(news_id).strip() for news_id in news_ids if str(news_id).strip()]
    if not clean_ids:
        return []
    placeholders = ",".join("?" for _ in clean_ids)
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM raw_news WHERE news_id IN ({placeholders})",
            clean_ids,
        ).fetchall()
    by_id = {row["news_id"]: dict(row) for row in rows}
    return [by_id[news_id] for news_id in clean_ids if news_id in by_id]


def clear_hot_topic_candidates() -> None:
    """清空候选题材和证据关系，不删除 raw_news"""
    with get_connection() as conn:
        conn.execute("DELETE FROM topic_evidence")
        conn.execute("DELETE FROM hot_topics")
        conn.commit()


def save_hot_topic_candidates(topics: list[dict], news_by_id: dict[str, dict]) -> int:
    """保存候选热点题材及其证据关系"""
    clear_hot_topic_candidates()
    if not topics:
        return 0
    save_raw_news(list(news_by_id.values()))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        saved = 0
        for topic in topics:
            cursor = conn.execute("""
                INSERT INTO hot_topics
                    (topic_name, heat_score, heat_level, trigger_event, core_logic,
                     evidence_summary, suggested_chains, related_keywords,
                     preliminary_related_stocks, confidence, should_import,
                     reason_to_import, risk_note,
                     topic_type, parent_theme, specificity_score, novelty_score,
                     key_entities, second_round_queries,
                     created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                topic.get("topic_name", ""),
                topic.get("heat_score"),
                topic.get("heat_level", ""),
                topic.get("trigger_event", ""),
                topic.get("core_logic", ""),
                topic.get("evidence_summary", ""),
                _join_list(topic.get("suggested_chains", [])),
                _join_list(topic.get("related_keywords", [])),
                _join_list(topic.get("preliminary_related_stocks", [])),
                topic.get("confidence", ""),
                1 if topic.get("should_import") else 0,
                topic.get("reason_to_import", ""),
                topic.get("risk_note", ""),
                topic.get("topic_type", ""),
                topic.get("parent_theme", ""),
                topic.get("specificity_score"),
                topic.get("novelty_score"),
                _join_list(topic.get("key_entities", [])),
                _join_list(topic.get("second_round_queries", [])),
                now,
            ))
            topic_id = cursor.lastrowid
            for evidence in topic.get("source_items", []):
                news_id = evidence.get("news_id")
                if not news_id:
                    continue
                conn.execute("""
                    INSERT OR REPLACE INTO topic_evidence
                        (topic_id, news_id, relevance_score, reason)
                    VALUES (?, ?, ?, ?)
                """, (
                    topic_id,
                    news_id,
                    evidence.get("relevance_score"),
                    evidence.get("reason", ""),
                ))
            saved += 1
        conn.commit()
        return saved


def _join_list(value) -> str:
    if isinstance(value, list):
        return "、".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "")


def get_hot_topic_candidates() -> list[dict]:
    """获取候选热点题材，按热度排序"""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                h.*,
                COUNT(e.news_id) AS evidence_count
            FROM hot_topics h
            LEFT JOIN topic_evidence e ON h.topic_id = e.topic_id
            GROUP BY h.topic_id
            ORDER BY h.heat_score DESC, h.created_at DESC
        """).fetchall()
    return [dict(row) for row in rows]


def get_topic_evidence(topic_id: int) -> list[dict]:
    """获取某个候选题材关联的证据新闻"""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                n.*,
                e.relevance_score,
                e.reason
            FROM topic_evidence e
            JOIN raw_news n ON e.news_id = n.news_id
            WHERE e.topic_id = ?
            ORDER BY e.relevance_score DESC, n.fetched_at DESC
        """, [topic_id]).fetchall()
    return [dict(row) for row in rows]


def get_hot_topic_candidate(topic_id: int) -> dict | None:
    """获取单个候选题材"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM hot_topics WHERE topic_id = ?",
            [topic_id],
        ).fetchone()
    return dict(row) if row else None


# ==================== 分析草稿 ====================

def create_analysis_draft(topic_id: int | None, topic_name: str, draft: dict) -> int:
    """保存 AI 生成的分析草稿，返回 draft_id"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO analysis_drafts
                (topic_id, topic_name, draft_json, status, created_at, updated_at)
            VALUES (?, ?, ?, 'draft', ?, ?)
        """, (
            topic_id,
            topic_name,
            json.dumps(draft, ensure_ascii=False),
            now,
            now,
        ))
        draft_id = cursor.lastrowid
        conn.commit()
        return draft_id


def update_analysis_draft(draft_id: int, draft: dict, status: str = "draft") -> None:
    """更新分析草稿 JSON 和状态"""
    if status not in {"draft", "confirmed", "discarded"}:
        status = "draft"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute("""
            UPDATE analysis_drafts
            SET draft_json = ?, status = ?, updated_at = ?
            WHERE draft_id = ?
        """, (
            json.dumps(draft, ensure_ascii=False),
            status,
            now,
            draft_id,
        ))
        conn.commit()


def set_analysis_draft_status(draft_id: int, status: str) -> None:
    """更新草稿状态"""
    if status not in {"draft", "confirmed", "discarded"}:
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute(
            "UPDATE analysis_drafts SET status = ?, updated_at = ? WHERE draft_id = ?",
            [status, now, draft_id],
        )
        conn.commit()


def get_analysis_draft(draft_id: int) -> dict | None:
    """读取单个分析草稿，draft_json 会解析为 draft 字段"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM analysis_drafts WHERE draft_id = ?",
            [draft_id],
        ).fetchone()
    if not row:
        return None
    data = dict(row)
    try:
        data["draft"] = json.loads(data.get("draft_json") or "{}")
    except json.JSONDecodeError:
        data["draft"] = {}
    return data


def get_latest_analysis_drafts(limit: int = 20, status: str = "") -> list[dict]:
    """获取最近的分析草稿"""
    with get_connection() as conn:
        if status:
            rows = conn.execute("""
                SELECT draft_id, topic_id, topic_name, status, created_at, updated_at
                FROM analysis_drafts
                WHERE status = ?
                ORDER BY updated_at DESC
                LIMIT ?
            """, [status, limit]).fetchall()
        else:
            rows = conn.execute("""
                SELECT draft_id, topic_id, topic_name, status, created_at, updated_at
                FROM analysis_drafts
                ORDER BY updated_at DESC
                LIMIT ?
            """, [limit]).fetchall()
    return [dict(row) for row in rows]


def confirm_analysis_draft(draft_id: int) -> int:
    """将草稿写入正式题材库，并标记 confirmed"""
    row = get_analysis_draft(draft_id)
    if not row:
        raise ValueError(f"草稿不存在: {draft_id}")
    draft = row.get("draft") or {}
    rows, quality = draft_to_theme_rows(draft)
    if not rows:
        raise ValueError("草稿中没有可入库个股")
    n = replace_theme(row["topic_name"], pd.DataFrame(rows), quality)
    update_analysis_draft(draft_id, draft, "confirmed")
    return n


def draft_to_theme_rows(draft: dict) -> tuple[list[dict], dict]:
    """把分析草稿转换为现有 theme_stocks 行结构"""
    topic_name = draft.get("topic_name") or draft.get("theme_name") or ""
    rows = []
    for stock in draft.get("stocks", []):
        rows.append({
            "theme_name": topic_name,
            "level1": stock.get("level1", ""),
            "level2": stock.get("level2", ""),
            "level3": stock.get("level3", ""),
            "stock_code": stock.get("stock_code", ""),
            "stock_name": stock.get("stock_name", ""),
            "market_type": stock.get("market_type", ""),
            "role": stock.get("role", ""),
            "logic_summary": stock.get("logic_summary", ""),
            "market_position": stock.get("market_position", "待核验"),
            "market_share": stock.get("market_share", "待核验"),
            "customers": stock.get("customers", "待核验"),
            "importance": _draft_importance_to_legacy(stock.get("importance", "观察")),
            "source": stock.get("evidence", ""),
            "notes": _compose_draft_notes(stock),
            "tier": stock.get("importance", "观察"),
            "biz_relevance": stock.get("relevance_score"),
            "biz_growth": "",
            "quality_score": "",
            "flow_score": "",
        })

    quality = {
        "breadth": None,
        "event_density": None,
        "capital_flow": None,
        "sustainability": None,
        "overall_score": None,
        "summary": draft.get("core_logic", ""),
    }
    return rows, quality


def _draft_importance_to_legacy(value: str) -> str:
    value = str(value or "")
    if value in {"核心", "高"}:
        return "高"
    if value in {"重要", "中"}:
        return "中"
    return "低"


def _compose_draft_notes(stock: dict) -> str:
    parts = []
    if stock.get("products"):
        parts.append(f"产品：{stock['products']}")
    if stock.get("risk_note"):
        parts.append(f"风险：{stock['risk_note']}")
    if stock.get("verification_status"):
        parts.append(f"核验状态：{stock['verification_status']}")
    return "；".join(parts)


# ==================== 查询函数 ====================

def get_theme_summary() -> pd.DataFrame:
    """获取题材汇总（用于列表页）"""
    with get_connection() as conn:
        df = pd.read_sql_query("""
            SELECT
                s.theme_name AS theme_name,
                COUNT(DISTINCT level1 || '|' || COALESCE(level2,'') || '|' || COALESCE(level3,'')) AS node_count,
                COUNT(*)                                         AS stock_count,
                SUM(CASE WHEN importance = '高' THEN 1 ELSE 0 END) AS high_importance_count,
                MAX(s.updated_at)                                 AS last_updated,
                q.overall_score                                   AS overall_score,
                q.summary                                         AS quality_summary
            FROM theme_stocks s
            LEFT JOIN theme_quality q USING(theme_name)
            GROUP BY s.theme_name, q.overall_score, q.summary
            ORDER BY stock_count DESC
        """, conn)
    return df


def get_theme_summary_with_dimensions() -> pd.DataFrame:
    """P2-9: 获取题材汇总（含四维评分均值，用于多维度筛选排序）"""
    with get_connection() as conn:
        df = pd.read_sql_query("""
            SELECT
                s.theme_name AS theme_name,
                COUNT(DISTINCT level1 || '|' || COALESCE(level2,'') || '|' || COALESCE(level3,'')) AS node_count,
                COUNT(*)                                         AS stock_count,
                SUM(CASE WHEN importance = '高' THEN 1 ELSE 0 END) AS high_importance_count,
                MAX(s.updated_at)                                 AS last_updated,
                q.overall_score                                   AS overall_score,
                q.summary                                         AS quality_summary,
                ROUND(AVG(CAST(s.biz_relevance AS FLOAT)), 1)      AS avg_biz_relevance,
                ROUND(AVG(CAST(s.biz_growth AS FLOAT)), 1)         AS avg_biz_growth,
                ROUND(AVG(CAST(s.quality_score AS FLOAT)), 1)      AS avg_quality_score,
                ROUND(AVG(CAST(s.flow_score AS FLOAT)), 1)         AS avg_flow_score
            FROM theme_stocks s
            LEFT JOIN theme_quality q USING(theme_name)
            GROUP BY s.theme_name, q.overall_score, q.summary
            ORDER BY stock_count DESC
        """, conn)
    return df


def get_theme_tree_data(theme_name: str) -> pd.DataFrame:
    """获取某个题材下的全部数据（用于构建树）"""
    with get_connection() as conn:
        df = pd.read_sql_query("""
            SELECT *
            FROM theme_stocks
            WHERE theme_name = ?
            ORDER BY level1, level2, level3, stock_code
        """, conn, params=[theme_name])
    return df


def build_tree(df: pd.DataFrame) -> dict[str, dict]:
    """
    将平铺的 DataFrame 构建为嵌套字典树：
    { level1: { level2: { level3: [stock_dict, ...] } } }
    """
    tree = {}
    for _, row in df.iterrows():
        l1 = row["level1"]
        l2 = row.get("level2") or "(未分类)"
        l3 = row.get("level3") or "(未分类)"

        tree.setdefault(l1, {})
        tree[l1].setdefault(l2, {})
        tree[l1][l2].setdefault(l3, [])
        tree[l1][l2][l3].append(dict(row))
    return tree


def search_stocks(
    keyword: str = "",
    market_type: str = "",
    importance: str = "",
    theme_name: str = "",
) -> pd.DataFrame:
    """多条件搜索个股"""
    conditions = []
    params = []

    if keyword:
        kw = f"%{keyword}%"
        conditions.append("""(
            theme_name  LIKE ? OR
            level1      LIKE ? OR
            level2      LIKE ? OR
            level3      LIKE ? OR
            stock_name  LIKE ? OR
            stock_code  LIKE ? OR
            role        LIKE ? OR
            logic_summary LIKE ? OR
            market_position LIKE ? OR
            customers   LIKE ? OR
            tier        LIKE ?
        )""")
        params.extend([kw] * 11)

    if market_type:
        conditions.append("market_type = ?")
        params.append(market_type)

    if importance:
        conditions.append("importance = ?")
        params.append(importance)

    if theme_name:
        conditions.append("theme_name = ?")
        params.append(theme_name)

    where = " AND ".join(conditions) if conditions else "1=1"
    sql = f"SELECT * FROM theme_stocks WHERE {where} ORDER BY theme_name, level1, level2, level3"

    with get_connection() as conn:
        df = pd.read_sql_query(sql, conn, params=params)
    return df


def get_stock_by_code(stock_code: str) -> dict | None:
    """按股票代码获取单条记录"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM theme_stocks WHERE stock_code = ?", [stock_code]
        ).fetchone()
    if row:
        return dict(row)
    return None


def get_theme_stocks(theme_name: str) -> list[dict]:
    """获取指定题材的所有个股记录"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM theme_stocks WHERE theme_name = ? ORDER BY level1, level2, level3",
            [theme_name],
        ).fetchall()
    return [dict(row) for row in rows]


def get_distinct_themes() -> list[str]:
    """获取所有题材名称"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT theme_name FROM theme_stocks ORDER BY theme_name"
        ).fetchall()
    return [r["theme_name"] for r in rows]


# 合法的层级列名（白名单，防止 SQL 注入）
_VALID_LEVEL_COLS = frozenset({"level1", "level2", "level3"})


def get_distinct_levels(theme_name: str, level_col: str) -> list[str]:
    """获取某个分层的去重值（白名单校验列名，安全拼接）"""
    if level_col not in _VALID_LEVEL_COLS:
        return []
    with get_connection() as conn:
        # level_col 已通过白名单校验，安全拼接
        rows = conn.execute(
            f'SELECT DISTINCT "{level_col}" FROM theme_stocks '
            f'WHERE theme_name = ? AND "{level_col}" != \'\' '
            f'ORDER BY "{level_col}"',
            [theme_name],
        ).fetchall()
    return [r[level_col] for r in rows]


def get_db_stats() -> dict[str, int]:
    """获取数据库统计信息"""
    with get_connection() as conn:
        theme_count = conn.execute(
            "SELECT COUNT(DISTINCT theme_name) FROM theme_stocks"
        ).fetchone()[0]
        stock_count = conn.execute(
            "SELECT COUNT(DISTINCT stock_code) FROM theme_stocks"
        ).fetchone()[0]
        total_rows = conn.execute("SELECT COUNT(*) FROM theme_stocks").fetchone()[0]
    return {
        "theme_count": theme_count,
        "stock_count": stock_count,
        "total_rows": total_rows,
    }


def export_dataframe(theme_name: str = "") -> pd.DataFrame:
    """导出全部或指定题材为 DataFrame"""
    with get_connection() as conn:
        if theme_name:
            df = pd.read_sql_query(
                "SELECT * FROM theme_stocks WHERE theme_name = ? ORDER BY level1, level2, level3",
                conn, params=[theme_name],
            )
        else:
            df = pd.read_sql_query(
                "SELECT * FROM theme_stocks ORDER BY theme_name, level1, level2, level3",
                conn,
            )
    return df


def get_cross_theme_stocks() -> pd.DataFrame:
    """获取跨题材个股（同一股票出现在多个题材中）"""
    with get_connection() as conn:
        df = pd.read_sql_query("""
            SELECT
                stock_code,
                stock_name,
                GROUP_CONCAT(DISTINCT theme_name) AS themes,
                COUNT(DISTINCT theme_name) AS theme_count
            FROM theme_stocks
            GROUP BY stock_code
            HAVING theme_count > 1
            ORDER BY theme_count DESC
        """, conn)
    return df


def get_stock_themes(stock_code: str) -> list[str]:
    """获取某只股票所属的所有题材"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT theme_name FROM theme_stocks WHERE stock_code = ?",
            [stock_code],
        ).fetchall()
    return [r["theme_name"] for r in rows]


def get_theme_compare_data(theme_names: list[str]) -> dict:
    """
    获取多个题材的对比数据（单连接）
    返回: {
        "per_theme": {theme_name: DataFrame},
        "common_stocks": DataFrame (共有个股),
    }
    """
    if not theme_names:
        return {}

    placeholders = ",".join(["?" for _ in theme_names])
    with get_connection() as conn:
        # 每个题材的个股
        per_theme = {}
        for t in theme_names:
            per_theme[t] = pd.read_sql_query(
                "SELECT * FROM theme_stocks WHERE theme_name = ?",
                conn, params=[t],
            )

        # 共有个股
        common = pd.read_sql_query(f"""
            SELECT stock_code, stock_name, COUNT(DISTINCT theme_name) AS cnt
            FROM theme_stocks
            WHERE theme_name IN ({placeholders})
            GROUP BY stock_code
            HAVING cnt = ?
        """, conn, params=[*theme_names, len(theme_names)])

    return {
        "per_theme": per_theme,
        "common_stocks": common,
    }


def update_stock_verification(
    stock_code: str,
    theme_name: str,
    verification_status: str,
    verification_details: str,
) -> bool:
    """更新个股验证状态"""
    with get_connection() as conn:
        conn.execute(
            """UPDATE theme_stocks
               SET verification_status = ?,
                   verification_details = ?,
                   verified_at = ?
               WHERE stock_code = ? AND theme_name = ?""",
            (verification_status, verification_details, datetime.now().isoformat(), stock_code, theme_name),
        )
        conn.commit()
        return conn.total_changes > 0


def batch_update_stock_verification(
    updates: list[dict],
) -> int:
    """
    批量更新个股验证状态。

    Args:
        updates: [{"stock_code": ..., "theme_name": ..., "verification_status": ..., "verification_details": ...}, ...]

    Returns:
        成功更新的行数
    """
    count = 0
    with get_connection() as conn:
        for item in updates:
            cursor = conn.execute(
                """UPDATE theme_stocks
                   SET verification_status = ?,
                       verification_details = ?,
                       verified_at = ?
                   WHERE stock_code = ? AND theme_name = ?""",
                (
                    item.get("verification_status", "待核验"),
                    item.get("verification_details", ""),
                    datetime.now().isoformat(),
                    item.get("stock_code", ""),
                    item.get("theme_name", ""),
                ),
            )
            count += cursor.rowcount
        conn.commit()
    return count


def get_verification_stats_by_theme(theme_name: str) -> dict:
    """获取某题材的验证统计"""
    with get_connection() as conn:
        row = conn.execute(
            """SELECT
                 COUNT(*) AS total,
                 SUM(CASE WHEN verification_status = 'verified_auto' THEN 1 ELSE 0 END) AS auto_count,
                 SUM(CASE WHEN verification_status = 'verified_inferred' THEN 1 ELSE 0 END) AS inferred_count,
                 SUM(CASE WHEN verification_status IN ('still_unverified', '待核验') THEN 1 ELSE 0 END) AS unverified_count
               FROM theme_stocks
               WHERE theme_name = ?""",
            (theme_name,),
        ).fetchone()
        if row:
            total = row["total"] or 0
            auto = row["auto_count"] or 0
            inferred = row["inferred_count"] or 0
            unverified = row["unverified_count"] or 0
            return {
                "total": total,
                "verified_auto": auto,
                "verified_inferred": inferred,
                "still_unverified": unverified,
                "verified_rate": round((auto + inferred) / max(total, 1) * 100, 1) if total > 0 else 0,
            }
        return {"total": 0, "verified_auto": 0, "verified_inferred": 0, "still_unverified": 0, "verified_rate": 0}


# ---------------------------------------------------------------------------
# P0-3: 数据新鲜度查询
# ---------------------------------------------------------------------------

def get_freshness_raw_data() -> list[dict]:
    """
    查询每个题材的最新更新时间 + 最近新闻时间。
    返回 [{"theme_name": str, "last_update": str|None, "last_news": str|None}, ...]
    """
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                s.theme_name,
                MAX(s.updated_at) AS last_update,
                MAX(rn.fetched_at) AS last_news
            FROM theme_stocks s
            LEFT JOIN (
                SELECT
                    ht.topic_name AS theme_name,
                    MAX(rn2.fetched_at) AS fetched_at
                FROM hot_topics ht
                JOIN topic_evidence te ON ht.topic_id = te.topic_id
                JOIN raw_news rn2 ON te.news_id = rn2.news_id
                GROUP BY ht.topic_name
            ) rn ON s.theme_name = rn.theme_name
            GROUP BY s.theme_name
            ORDER BY s.theme_name
        """).fetchall()
    return [dict(r) for r in rows]


def get_theme_count() -> int:
    """获取题材总数"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(DISTINCT theme_name) FROM theme_stocks"
        ).fetchone()
    return row[0] if row else 0


# 模块导入时自动初始化
init_db()
