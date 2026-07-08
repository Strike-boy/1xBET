import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
ADMIN_IDS = [int(uid.strip()) for uid in os.getenv("ADMIN_IDS", "").split(",") if uid.strip()]
DEFAULT_CARD_NUMBER = os.getenv("CARD_NUMBER", "Номер карты не задан")

# PostgreSQL
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "ucshop")

# Redis
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

# Контакты админов для отображения пользователям (можно сгенерировать из ADMIN_IDS)
ADMIN_CONTACTS = os.getenv("ADMIN_CONTACTS", "https://t.me/admin1, https://t.me/admin2")

# Видео-инструкция для вывода (file_id или ссылка)
WITHDRAW_VIDEO = os.getenv("WITHDRAW_VIDEO", "")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан")
if not ADMIN_IDS:
    raise RuntimeError("ADMIN_IDS не задан")
