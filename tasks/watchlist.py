"""
P2-10: 自选/关注列表模块

管理用户关注的题材和个股，支持添加/移除/标记更新。
数据存储在 SQLite watchlist 表中。
"""
import core.database as db
from config import get_logger

_log = get_logger("watchlist")

# ---- 数据库表初始化 ----

def ensure_watchlist_table() -> None:
    """创建 watchlist 表（如不存在）"""
    with db.get_connection() as conn:
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
        conn.commit()


# ---- CRUD 操作 ----

def add_to_watchlist(item_type: str, item_id: str, notes: str = "") -> bool:
    """
    添加关注项。已存在则跳过。

    Args:
        item_type: 'theme' 或 'stock'
        item_id: 题材名称（theme_name）或股票代码（stock_code）
        notes: 备注

    Returns:
        True 表示新增成功，False 表示已存在
    """
    if item_type not in ("theme", "stock"):
        _log.warning("无效的 item_type: %s", item_type)
        return False
    if not item_id or not item_id.strip():
        return False

    ensure_watchlist_table()
    with db.get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM watchlist WHERE item_type = ? AND item_id = ?",
            [item_type, item_id],
        ).fetchone()
        if existing:
            return False

        conn.execute(
            "INSERT INTO watchlist (item_type, item_id, notes) VALUES (?, ?, ?)",
            [item_type, item_id, notes],
        )
        conn.commit()
        _log.info("已添加关注: %s/%s", item_type, item_id)
        return True


def remove_from_watchlist(item_type: str, item_id: str) -> bool:
    """
    取消关注。

    Returns:
        True 表示移除成功，False 表示不存在
    """
    if item_type not in ("theme", "stock"):
        return False
    ensure_watchlist_table()
    with db.get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM watchlist WHERE item_type = ? AND item_id = ?",
            [item_type, item_id],
        )
        conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            _log.info("已取消关注: %s/%s", item_type, item_id)
        return deleted


def is_watched(item_type: str, item_id: str) -> bool:
    """检查是否已关注"""
    ensure_watchlist_table()
    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM watchlist WHERE item_type = ? AND item_id = ?",
            [item_type, item_id],
        ).fetchone()
        return row is not None


def get_watchlist() -> list[dict]:
    """获取完整关注列表"""
    ensure_watchlist_table()
    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM watchlist ORDER BY added_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def get_watchlist_by_type(item_type: str) -> list[dict]:
    """按类型获取关注列表"""
    ensure_watchlist_table()
    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM watchlist WHERE item_type = ? ORDER BY added_at DESC",
            [item_type],
        ).fetchall()
    return [dict(row) for row in rows]


def mark_update(item_type: str, item_id: str, updated: bool = True) -> None:
    """标记关注项有更新"""
    ensure_watchlist_table()
    with db.get_connection() as conn:
        conn.execute(
            "UPDATE watchlist SET has_update = ? WHERE item_type = ? AND item_id = ?",
            [1 if updated else 0, item_type, item_id],
        )
        conn.commit()


def clear_all_updates() -> None:
    """清除所有更新标记"""
    ensure_watchlist_table()
    with db.get_connection() as conn:
        conn.execute("UPDATE watchlist SET has_update = 0")
        conn.commit()


def get_watchlist_stats() -> dict:
    """获取关注列表统计"""
    ensure_watchlist_table()
    with db.get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
        themes = conn.execute(
            "SELECT COUNT(*) FROM watchlist WHERE item_type = 'theme'"
        ).fetchone()[0]
        stocks = total - themes
        updated = conn.execute(
            "SELECT COUNT(*) FROM watchlist WHERE has_update = 1"
        ).fetchone()[0]
    return {
        "total": total,
        "themes": themes,
        "stocks": stocks,
        "has_update": updated,
    }
