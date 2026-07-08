"""
Middleware для антифлуда (не более 1 сообщения в секунду от одного пользователя).
"""
import time
from typing import Any, Callable, Dict, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, Update

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
        user_id = None
        if event.message and event.message.from_user:
            user_id = event.message.from_user.id
        elif event.callback_query and event.callback_query.from_user:
            user_id = event.callback_query.from_user.id
        # Если нет user_id, пропускаем
        if user_id is None:
            return await handler(event, data)

        now = time.time()
        last = self.last_usage.get(user_id, 0)
        if now - last < self.rate_limit:
            # Слишком часто – игнорируем
            return
        self.last_usage[user_id] = now
        return await handler(event, data)
