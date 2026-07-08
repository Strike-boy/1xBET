"""
Работа с базой данных SQLite (aiosqlite).
"""
import aiosqlite
from datetime import datetime, timezone
import config

DB_PATH = config.DB_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as conn:
        # Проверяем, есть ли уже таблица orders, если нет – создаём с новыми полями
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
                admin_message_id INTEGER
            )
        """)
        # Таблица настроек
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await conn.commit()

# --- Вспомогательные функции для миграции (если таблица уже существует, но без новых полей) ---
async def migrate_if_needed():
    async with aiosqlite.connect(DB_PATH) as conn:
        # Проверим наличие колонки order_type
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
        await conn.commit()

# --- Основные функции ---

async def create_order(user_id: int, chat_id: int, username: str, amount: int,
                       player_id: str, screenshot_file_id: str, currency: str = 'UZS',
                       order_type: str = 'deposit', extra_amount: int = 0,
                       withdraw_card: str = None) -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """
            INSERT INTO orders (user_id, chat_id, username, amount, extra_amount, player_id,
                                currency, order_type, withdraw_card, screenshot_file_id, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'checking')
            """,
            (user_id, chat_id, username, amount, extra_amount, player_id,
             currency, order_type, withdraw_card, screenshot_file_id)
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
        now = datetime.now(timezone.utc).isoformat()
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
    """Проверяет, есть ли у пользователя активный заказ (status = 'checking')"""
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
    """Заказы в статусе checking, созданные более minutes минут назад"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM orders WHERE status = 'checking' AND julianday('now') - julianday(created_at) * 24*60 > ?",
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
        today = datetime.now(timezone.utc).date().isoformat()
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
