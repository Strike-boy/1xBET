import asyncpg
from datetime import datetime, timezone
import config

pool = None

async def init_db():
    global pool
    pool = await asyncpg.create_pool(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        min_size=2,
        max_size=10,
    )
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                language VARCHAR(2) DEFAULT 'ru',
                active_order_id INTEGER,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                type VARCHAR(20) NOT NULL,
                amount INTEGER NOT NULL,
                unique_sum INTEGER,
                player_id VARCHAR(50) NOT NULL,
                card_number VARCHAR(50),
                status VARCHAR(20) DEFAULT 'checking',
                screenshot_file_id TEXT,
                comment TEXT,
                admin_username VARCHAR(100),
                created_at TIMESTAMP DEFAULT NOW(),
                processed_at TIMESTAMP,
                admin_message_id INTEGER
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key VARCHAR(50) PRIMARY KEY,
                value TEXT
            )
        """)
        # Добавляем настройки по умолчанию, если их нет
        await conn.execute("""
            INSERT INTO settings (key, value) VALUES ('card_number', $1)
            ON CONFLICT (key) DO NOTHING
        """, config.DEFAULT_CARD_NUMBER)
        # Видео для вывода
        await conn.execute("""
            INSERT INTO settings (key, value) VALUES ('withdraw_video', $1)
            ON CONFLICT (key) DO NOTHING
        """, config.WITHDRAW_VIDEO)
        # Контакты админов
        await conn.execute("""
            INSERT INTO settings (key, value) VALUES ('admin_contacts', $1)
            ON CONFLICT (key) DO NOTHING
        """, config.ADMIN_CONTACTS)

async def get_user_language(user_id: int) -> str:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT language FROM users WHERE user_id = $1", user_id)
        if row:
            return row['language']
        return 'ru'  # по умолчанию русский

async def set_user_language(user_id: int, lang: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, language) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET language = $2, updated_at = NOW()
        """, user_id, lang)

async def has_active_order(user_id: int) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM orders WHERE user_id = $1 AND status = 'checking' LIMIT 1",
            user_id
        )
        return row is not None

async def create_order(user_id: int, type: str, amount: int, player_id: str,
                       card_number: str = None, unique_sum: int = None,
                       screenshot_file_id: str = None) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO orders (user_id, type, amount, unique_sum, player_id, card_number, screenshot_file_id, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'checking')
            RETURNING id
        """, user_id, type, amount, unique_sum, player_id, card_number, screenshot_file_id)
        return row['id']

async def update_order_status(order_id: int, status: str, comment: str = None, admin_username: str = None):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE orders SET status = $1, comment = $2, admin_username = $3, processed_at = NOW()
            WHERE id = $4
        """, status, comment, admin_username, order_id)

async def get_order(order_id: int) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM orders WHERE id = $1", order_id)
        return dict(row) if row else None

async def get_checking_orders() -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM orders WHERE status = 'checking' ORDER BY created_at ASC")
        return [dict(r) for r in rows]

async def get_stats() -> dict:
    async with pool.acquire() as conn:
        today = datetime.now(timezone.utc).date().isoformat()
        total = await conn.fetchval("SELECT COUNT(*) FROM orders")
        done = await conn.fetchval("SELECT COUNT(*) FROM orders WHERE status = 'done'")
        cancelled = await conn.fetchval("SELECT COUNT(*) FROM orders WHERE status = 'cancelled'")
        checking = await conn.fetchval("SELECT COUNT(*) FROM orders WHERE status = 'checking'")
        today_count = await conn.fetchval("SELECT COUNT(*) FROM orders WHERE DATE(created_at) = $1", today)
        return {
            'total': total,
            'done': done,
            'cancelled': cancelled,
            'checking': checking,
            'today': today_count
        }

async def set_admin_message_id(order_id: int, message_id: int):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE orders SET admin_message_id = $1 WHERE id = $2", message_id, order_id)

async def get_setting(key: str) -> str:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM settings WHERE key = $1", key)
        return row['value'] if row else ""

async def set_setting(key: str, value: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO settings (key, value) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = $2
        """, key, value)
