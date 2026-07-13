"""
Обработчик для проверки подписки на каналы.
"""
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery

from middlewares import handle_check_subscription as _handle_check_subscription

router = Router()

@router.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: CallbackQuery, bot: Bot):
    """Обрабатывает нажатие кнопки проверки подписки"""
    await _handle_check_subscription(callback, bot)
