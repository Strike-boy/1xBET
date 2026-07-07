"""
Конфигурация бота.

Все чувствительные данные (токен, ID админов, ID админ-чата) берутся
из файла .env и НЕ должны попадать в git-репозиторий (см. .gitignore).
"""

import os

from dotenv import load_dotenv

load_dotenv()

# Токен бота, полученный от @BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# ID чата/группы для админов, куда приходят заказы на проверку
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))

# Telegram ID администраторов через запятую, например: "111111111,222222222"
ADMIN_IDS = [
    int(uid.strip())
    for uid in os.getenv("ADMIN_IDS", "").split(",")
    if uid.strip()
]

# Путь к файлу базы данных SQLite
DB_PATH = os.getenv("DB_PATH", "orders.db")

# Номер карты по умолчанию (используется, пока админ не задаст свой через /setcard)
DEFAULT_CARD_NUMBER = os.getenv(
    "CARD_NUMBER", "Номер карты ещё не задан. Обратитесь к администратору."
)

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не задан. Скопируйте .env.example в .env и укажите токен бота."
    )

if not ADMIN_IDS:
    raise RuntimeError(
        "ADMIN_IDS не задан. Укажите хотя бы один Telegram ID администратора в .env."
    )
