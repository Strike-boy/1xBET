"""
Конфигурация бота.
"""
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
ADMIN_IDS = [int(uid.strip()) for uid in os.getenv("ADMIN_IDS", "").split(",") if uid.strip()]
DB_PATH = os.getenv("DB_PATH", "orders.db")
DEFAULT_CARD_NUMBER = os.getenv("CARD_NUMBER", "Номер карты не задан.")
ADMIN_CONTACTS = os.getenv("ADMIN_CONTACTS", "@admin")
WITHDRAW_VIDEO_FILE_ID = os.getenv("WITHDRAW_VIDEO_FILE_ID", "")

# Force Subscribe конфигурация
REQUIRED_CHANNELS = [
    {
        "id": int(os.getenv("REQUIRED_CHANNEL_ID", "0")),
        "url": os.getenv("REQUIRED_CHANNEL_URL", "https://t.me/your_channel")
    }
]

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан.")
if not ADMIN_IDS:
    raise RuntimeError("ADMIN_IDS не задан.")
