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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Flask-приложение для Render
app = Flask(__name__)

@app.route("/")
def home():
    return "UC Shop Bot is running!"

def run_web():
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )


async def main():
    await db.init_db()
    logger.info("База данных инициализирована (%s)", config.DB_PATH)

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(client.router)
    dp.include_router(admin.router)

    @dp.errors()
    async def errors_handler(event: ErrorEvent):
        logger.exception(
            "Ошибка при обработке апдейта %s: %s",
            event.update.update_id if event.update else "unknown",
            event.exception,
        )
        return True

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен и готов принимать заказы")

    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        # Запускаем веб-сервер для Render
        Thread(target=run_web, daemon=True).start()

        # Запускаем Telegram-бота
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")
