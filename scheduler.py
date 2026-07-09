"""
Фоновые задачи (напоминания админам).
"""
import asyncio
import logging
from aiogram import Bot
import database as db
import config

logger = logging.getLogger(__name__)

async def remind_admins(bot: Bot):
    """Каждые 5 минут проверяет заказы в статусе checking старше 5 минут и напоминает."""
    while True:
        await asyncio.sleep(100)  # 1.5 минут
        try:
            orders = await db.get_checking_orders_older_than(minutes=5)
            if orders:
                ids = [str(o['id']) for o in orders]
                text = f"⏳Eslatma: bajarilmagan zakazlar bor: #{', #'.join(ids)}"
                await bot.send_message(config.ADMIN_CHAT_ID, text)
        except Exception as e:
            logger.exception("Adminlar eslatmasida xatolik: %s", e)
