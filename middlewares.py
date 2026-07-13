import time
from typing import Any, Callable, Dict, Awaitable, Optional, List

from aiogram import BaseMiddleware
from aiogram.types import Update, Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

import config


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate_limit: float = 1.0):
        self.rate_limit = rate_limit
        self.last_usage: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        user_id = self._get_user_id(event)
        
        if user_id is None:
            return await handler(event, data)

        now = time.time()
        last = self.last_usage.get(user_id, 0)
        if now - last < self.rate_limit:
            return  # игнорируем
        self.last_usage[user_id] = now
        return await handler(event, data)
    
    def _get_user_id(self, event: Update) -> Optional[int]:
        if event.message and event.message.from_user:
            return event.message.from_user.id
        elif event.callback_query and event.callback_query.from_user:
            return event.callback_query.from_user.id
        return None


class ForceSubscribeMiddleware(BaseMiddleware):
    """
    Middleware для проверки подписки пользователя на обязательные каналы.
    Перехватывает все обновления и проверяет подписку перед выполнением обработчиков.
    """
    
    # Хранилище для отслеживания отправленных сообщений о подписке
    _subscription_messages: Dict[int, int] = {}  # {user_id: message_id}
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        # Получаем пользователя из события
        user_id = self._get_user_id(event)
        
        # Если пользователь не найден (например, системное сообщение), пропускаем
        if user_id is None:
            return await handler(event, data)
        
        # Админов пропускаем (опционально, но рекомендуется)
        if user_id in config.ADMIN_IDS:
            return await handler(event, data)
        
        # Проверяем подписку
        bot = data.get("bot")
        if bot is None:
            return await handler(event, data)
        
        # Получаем объект для ответа (message или callback)
        target = self._get_target(event)
        if target is None:
            return await handler(event, data)
        
        # Проверяем подписку на все каналы
        is_subscribed, unsubscribed_channels = await self._check_all_channels(bot, user_id)
        
        if is_subscribed:
            # Если пользователь подписан - удаляем сообщение о подписке (если есть)
            await self._remove_subscription_message(target, user_id)
            return await handler(event, data)
        
        # Пользователь не подписан - отправляем требование подписки
        await self._send_subscription_required(target, user_id, unsubscribed_channels)
        
        # Останавливаем дальнейшую обработку
        return
    
    def _get_user_id(self, event: Update) -> Optional[int]:
        """Извлекает ID пользователя из события"""
        if event.message and event.message.from_user:
            return event.message.from_user.id
        elif event.callback_query and event.callback_query.from_user:
            return event.callback_query.from_user.id
        return None
    
    def _get_target(self, event: Update):
        """Получает объект для отправки ответа"""
        if event.message:
            return event.message
        elif event.callback_query and event.callback_query.message:
            return event.callback_query.message
        return None
    
    async def _check_all_channels(self, bot, user_id: int) -> tuple[bool, List[dict]]:
        """
        Проверяет подписку на все обязательные каналы.
        Возвращает (все_подписан, список_неподписанных_каналов)
        """
        unsubscribed = []
        
        for channel in config.REQUIRED_CHANNELS:
            channel_id = channel.get("id")
            if channel_id == 0:
                continue
                
            try:
                member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
                if member.status not in ["member", "administrator", "creator"]:
                    unsubscribed.append(channel)
            except TelegramBadRequest:
                # Если не удалось получить информацию (бот не админ в канале и т.д.)
                # Считаем, что пользователь не подписан
                unsubscribed.append(channel)
        
        return len(unsubscribed) == 0, unsubscribed
    
    async def _send_subscription_required(self, target, user_id: int, unsubscribed_channels: List[dict]):
        """
        Отправляет сообщение с требованием подписки и клавиатуру
        """
        # Формируем текст сообщения
        text = "📛 Iltimos quyidagi kanallarga obuna bo'ling:\n\n"
        for channel in unsubscribed_channels:
            text += f"• {channel.get('url', '')}\n"
        text += "\nObuna bo'lgandan so'ng «Tekshirish» tugmasini bosing."
        
        # Создаем клавиатуру
        keyboard = self._build_subscription_keyboard(unsubscribed_channels)
        
        # Отправляем или обновляем сообщение
        await self._send_or_update_message(target, user_id, text, keyboard)
    
    def _build_subscription_keyboard(self, channels: List[dict]) -> InlineKeyboardMarkup:
        """Создает клавиатуру с кнопками для подписки"""
        keyboard = []
        
        # Кнопки для каждого канала
        for channel in channels:
            if channel.get("url"):
                keyboard.append([
                    InlineKeyboardButton(
                        text="📢 Kanalga o'tish",
                        url=channel["url"]
                    )
                ])
        
        # Кнопка проверки
        keyboard.append([
            InlineKeyboardButton(
                text="✅ Tekshirish",
                callback_data="check_subscription"
            )
        ])
        
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    async def _send_or_update_message(self, target, user_id: int, text: str, keyboard: InlineKeyboardMarkup):
        """
        Отправляет новое сообщение или обновляет существующее
        """
        # Проверяем, есть ли уже сообщение для этого пользователя
        if user_id in self._subscription_messages:
            try:
                # Если это callback_query, используем его для редактирования
                if hasattr(target, 'edit_text'):
                    await target.edit_text(text, reply_markup=keyboard)
                    return
                # Иначе удаляем старое сообщение и отправляем новое
                await target.bot.delete_message(
                    chat_id=target.chat.id,
                    message_id=self._subscription_messages[user_id]
                )
            except Exception:
                pass  # Игнорируем ошибки удаления
            del self._subscription_messages[user_id]
        
        # Отправляем новое сообщение
        msg = await target.answer(text, reply_markup=keyboard)
        self._subscription_messages[user_id] = msg.message_id
    
    async def _remove_subscription_message(self, target, user_id: int):
        """
        Удаляет сообщение о подписке, если оно есть
        """
        if user_id in self._subscription_messages:
            try:
                await target.bot.delete_message(
                    chat_id=target.chat.id,
                    message_id=self._subscription_messages[user_id]
                )
            except Exception:
                pass
            del self._subscription_messages[user_id]


# ========== Вспомогательные функции для обработчика кнопки проверки подписки ==========

async def _check_channels_for_user(bot, user_id: int) -> tuple[bool, List[dict]]:
    """Проверяет подписку пользователя на все каналы"""
    unsubscribed = []
    
    for channel in config.REQUIRED_CHANNELS:
        channel_id = channel.get("id")
        if channel_id == 0:
            continue
            
        try:
            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                unsubscribed.append(channel)
        except TelegramBadRequest:
            unsubscribed.append(channel)
    
    return len(unsubscribed) == 0, unsubscribed


def _build_subscription_keyboard(channels: List[dict]) -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопками для подписки"""
    keyboard = []
    
    for channel in channels:
        if channel.get("url"):
            keyboard.append([
                InlineKeyboardButton(
                    text="📢 Kanalga o'tish",
                    url=channel["url"]
                )
            ])
    
    keyboard.append([
        InlineKeyboardButton(
            text="✅ Tekshirish",
            callback_data="check_subscription"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def handle_check_subscription(callback: CallbackQuery, bot):
    """Обрабатывает нажатие кнопки проверки подписки"""
    from handlers.client import main_menu_kb
    
    user_id = callback.from_user.id
    
    # Проверяем подписку
    is_subscribed, unsubscribed_channels = await _check_channels_for_user(bot, user_id)
    
    if is_subscribed:
        # Подписка подтверждена
        await callback.message.delete()
        await callback.answer("✅ Siz kanallarga obuna bo'ldingiz! Endi botdan foydalanishingiz mumkin.")
        
        # Удаляем из хранилища
        ForceSubscribeMiddleware._subscription_messages.pop(user_id, None)
        
        # Отправляем приветственное сообщение или главное меню
        await callback.message.answer(
            "Assalomu alaykum! 🖐️\n"
            "Onlayn kassamizga xush kelibsiz!\n"
            "\n"
            "💳 Toʻldirishlar — 0% komissiya\n"
            "⚡️ Jarayon juda sodda va tez\n"
            "📱 Bir necha soniya ichida hisobingiz toʻldiriladi\n",
            reply_markup=main_menu_kb()
        )
    else:
        # Все еще не подписан
        text = "❌ Siz hali kanalga obuna bo'lmagansiz.\n\n"
        for channel in unsubscribed_channels:
            text += f"• {channel.get('url', '')}\n"
        text += "\nIltimos, avval obuna bo'ling!"
        
        await callback.answer("❌ Siz hali kanalga obuna bo'lmagansiz.", show_alert=True)
        
        # Обновляем сообщение
        keyboard = _build_subscription_keyboard(unsubscribed_channels)
        await callback.message.edit_text(text, reply_markup=keyboard)
