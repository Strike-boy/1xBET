"""
Работа с базой данных SQLite (aiosqlite).
"""
import aiosqlite
from datetime import datetime, timedelta, timezone
UZ_TZ = timezone(timedelta(hours=5))
import config

DB_PATH = config.DB_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                username TEXT,
                amount INTEGER NOT NULL,
                extra_amount INTEGER DEFAULT 0,
                player_id TEXT NOT NULL,
                currency TEXT DEFAULT 'UZS',
                order_type TEXT DEFAULT 'deposit',
                withdraw_card TEXT,
                status TEXT DEFAULT 'checking',
                screenshot_file_id TEXT,
                admin_comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP,
                admin_message_id INTEGER,
                card_used TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await conn.commit()

async def migrate_if_needed():
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute("PRAGMA table_info(orders)")
        columns = [row[1] for row in await cursor.fetchall()]
        if "order_type" not in columns:
            await conn.execute("ALTER TABLE orders ADD COLUMN order_type TEXT DEFAULT 'deposit'")
        if "extra_amount" not in columns:
            await conn.execute("ALTER TABLE orders ADD COLUMN extra_amount INTEGER DEFAULT 0")
        if "currency" not in columns:
            await conn.execute("ALTER TABLE orders ADD COLUMN currency TEXT DEFAULT 'UZS'")
        if "withdraw_card" not in columns:
            await conn.execute("ALTER TABLE orders ADD COLUMN withdraw_card TEXT")
        if "admin_comment" not in columns:
            await conn.execute("ALTER TABLE orders ADD COLUMN admin_comment TEXT")
        if "processed_at" not in columns:
            await conn.execute("ALTER TABLE orders ADD COLUMN processed_at TIMESTAMP")
        if "card_used" not in columns:
            await conn.execute("ALTER TABLE orders ADD COLUMN card_used TEXT")
        await conn.commit()

async def create_order(user_id: int, chat_id: int, username: str, amount: int,
                       player_id: str, screenshot_file_id: str, currency: str = 'UZS',
                       order_type: str = 'deposit', extra_amount: int = 0,
                       withdraw_card: str = None, card_used: str = None) -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """
            INSERT INTO orders (user_id, chat_id, username, amount, extra_amount, player_id,
                                currency, order_type, withdraw_card, screenshot_file_id, status, card_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'checking', ?)
            """,
            (user_id, chat_id, username, amount, extra_amount, player_id,
             currency, order_type, withdraw_card, screenshot_file_id, card_used)
        )
        await conn.commit()
        return cursor.lastrowid

async def set_admin_message_id(order_id: int, message_id: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE orders SET admin_message_id = ? WHERE id = ?", (message_id, order_id))
        await conn.commit()

async def get_order(order_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def update_status(order_id: int, status: str, admin_comment: str = None):
    async with aiosqlite.connect(DB_PATH) as conn:
        now = datetime.now(UZ_TZ).isoformat()
        if admin_comment is not None:
            await conn.execute(
                "UPDATE orders SET status = ?, processed_at = ?, admin_comment = ? WHERE id = ?",
                (status, now, admin_comment, order_id)
            )
        else:
            await conn.execute(
                "UPDATE orders SET status = ?, processed_at = ? WHERE id = ?",
                (status, now, order_id)
            )
        await conn.commit()

async def get_active_order(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM orders WHERE user_id = ? AND status = 'checking' ORDER BY created_at DESC LIMIT 1",
            (user_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

async def get_checking_orders() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM orders WHERE status = 'checking' ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def get_checking_orders_older_than(minutes: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM orders WHERE status = 'checking' AND (julianday('now') - julianday(created_at)) * 24 * 60 > ?",
            (minutes,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def get_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async def count(where: str = "", params: tuple = ()) -> int:
            query = "SELECT COUNT(*) as c FROM orders"
            if where:
                query += f" WHERE {where}"
            cursor = await conn.execute(query, params)
            row = await cursor.fetchone()
            return row["c"]
        today = datetime.now(UZ_TZ).date().isoformat()
        return {
            "total": await count(),
            "done": await count("status = ?", ("done",)),
            "cancelled": await count("status = ?", ("cancelled",)),
            "checking": await count("status = ?", ("checking",)),
            "today": await count("DATE(created_at) = ?", (today,)),
            "withdraw_done": await count("status = ? AND order_type = ?", ("done", "withdraw")),
            "withdraw_checking": await count("status = ? AND order_type = ?", ("checking", "withdraw")),
        }

async def get_card_number() -> str:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute("SELECT value FROM settings WHERE key = 'card_number'")
        row = await cursor.fetchone()
        if row and row[0]:
            return row[0]
        return config.DEFAULT_CARD_NUMBER

async def set_card_number(new_number: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO settings (key, value) VALUES ('card_number', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (new_number,)
        )
        await conn.commit()

# ========== МЕТОДЫ ДЛЯ ИСТОРИИ ТРАНЗАКЦИЙ ==========

async def get_user_orders_count(user_id: int) -> int:
    """Получить общее количество транзакций пользователя"""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM orders WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

async def get_user_orders_paginated(user_id: int, page: int = 1, limit: int = 5) -> list[dict]:
    """Получить транзакции пользователя с пагинацией"""
    offset = (page - 1) * limit
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """
            SELECT * FROM orders 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT ? OFFSET ?
            """,
            (user_id, limit, offset)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

# ========== ОСТАЛЬНЫЕ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

async def get_user_orders(user_id: int, limit: int = 10) -> list[dict]:
    """Получить последние заказы пользователя"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def get_today_stats() -> dict:
    """Статистика за сегодня"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        today = datetime.now(UZ_TZ).date().isoformat()
        cursor = await conn.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as done, "
            "SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled, "
            "SUM(CASE WHEN status = 'checking' THEN 1 ELSE 0 END) as checking "
            "FROM orders WHERE DATE(created_at) = ?",
            (today,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else {"total": 0, "done": 0, "cancelled": 0, "checking": 0}

async def get_orders_by_status(status: str) -> list[dict]:
    """Получить заказы по статусу"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM orders WHERE status = ? ORDER BY created_at DESC",
            (status,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def update_order_comment(order_id: int, comment: str):
    """Обновить комментарий к заказу"""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE orders SET admin_comment = ? WHERE id = ?",
            (comment, order_id)
        )
        await conn.commit()

async def delete_old_orders(days: int = 30):
    """Удалить старые заказы (старше days дней)"""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "DELETE FROM orders WHERE DATE(created_at) < DATE('now', ?)",
            (f'-{days} days',)
        )
        await conn.commit()

async def get_total_amount_by_status(status: str) -> int:
    """Получить общую сумму заказов по статусу"""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT SUM(amount) as total FROM orders WHERE status = ?",
            (status,)
        )
        row = await cursor.fetchone()
        return row[0] if row and row[0] else 0

async def get_orders_count_by_currency() -> dict:
    """Количество заказов по валютам"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT currency, COUNT(*) as count FROM orders GROUP BY currency"
        )
        rows = await cursor.fetchall()
        return {row["currency"]: row["count"] for row in rows}

async def get_last_order(user_id: int) -> dict | None:
    """Получить последний заказ пользователя"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
            (user_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
