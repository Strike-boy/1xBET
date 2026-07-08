import asyncio
import logging
import os
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent
import config
import database as db
from redis_storage import get_redis_storage
from handlers import client, deposit, withdraw, admin
from middlewares.throttling import ThrottlingMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/')
def home():
    return "UC Shop Bot is running!"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

async def main():
    await db.init_db()
    logger.info("База данных PostgreSQL инициализирована")

    storage = get_redis_storage()
    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=storage)

    # Подключаем middleware антифлуда глобально (для сообщений и колбэков)
    dp.message.middleware(ThrottlingMiddleware(rate_limit=1.0))
    dp.callback_query.middleware(ThrottlingMiddleware(rate_limit=1.0))

    dp.include_router(client.router)
    dp.include_router(deposit.router)
    dp.include_router(withdraw.router)
    dp.include_router(admin.router)

    @dp.errors()
    async def errors_handler(event: ErrorEvent):
        logger.exception("Ошибка: %s", event.exception)
        return True

    # Запускаем фоновую задачу напоминания админам
    asyncio.create_task(admin.reminder_task(bot))

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    Thread(target=run_web, daemon=True).start()
    asyncio.run(main())
