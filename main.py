import asyncio
import logging
import os
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent
import config
import database as db
from handlers import client, admin
from middlewares import ThrottlingMiddleware
from scheduler import remind_admins

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Flask для Render
app = Flask(__name__)

@app.route("/")
def home():
    return "UC Shop Bot is running!"

def run_web():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

async def main():
    # Инициализация БД и миграция
    await db.init_db()
    await db.migrate_if_needed()
    logger.info("База данных готова (%s)", config.DB_PATH)

    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    # Подключаем middleware антифлуда
    dp.update.middleware(ThrottlingMiddleware(rate_limit=1.0))

    dp.include_router(admin.router)
    dp.include_router(client.router)

    @dp.errors()
    async def errors_handler(event: ErrorEvent):
        logger.exception("Ошибка: %s", event.exception)
        return True

    # Запускаем напоминания админам
    asyncio.create_task(remind_admins(bot))

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен")

    await dp.start_polling(bot)

if __name__ == "__main__":
    Thread(target=run_web, daemon=True).start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
