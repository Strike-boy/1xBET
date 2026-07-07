"""
Работа с базой данных SQLite (через aiosqlite).

Таблицы:
- orders   — заказы клиентов на пополнение UC
- settings — изменяемые настройки (например, текущий номер карты для /setcard)
"""

from datetime import datetime, timezone

import aiosqlite

import config

DB_PATH = config.DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                username TEXT,
                amount INTEGER NOT NULL,
                player_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'checking',
                screenshot_file_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                admin_message_id INTEGER
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        await conn.commit()


async def create_order(
    user_id: int,
    chat_id: int,
    username: str,
    amount: int,
    player_id: str,
    screenshot_file_id: str,
) -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """
            INSERT INTO orders (user_id, chat_id, username, amount, player_id, status, screenshot_file_id)
            VALUES (?, ?, ?, ?, ?, 'checking', ?)
            """,
            (user_id, chat_id, username, amount, player_id, screenshot_file_id),
        )
        await conn.commit()
        return cursor.lastrowid


async def set_admin_message_id(order_id: int, message_id: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE orders SET admin_message_id = ? WHERE id = ?",
            (message_id, order_id),
        )
        await conn.commit()


async def get_order(order_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_status(order_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (status, order_id),
        )
        await conn.commit()


async def get_checking_orders() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM orders WHERE status = 'checking' ORDER BY created_at DESC"
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
            """
            INSERT INTO settings (key, value) VALUES ('card_number', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (new_number,),
        )
        await conn.commit()
