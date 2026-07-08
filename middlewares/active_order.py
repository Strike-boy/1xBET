from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
import database as db

class ActiveOrderMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        # Проверяем, если это начало нового заказа (команда или кнопка)
        # Но будем проверять непосредственно в хендлерах, чтобы не блокировать все сообщения.
        # Можно реализовать выборочную проверку.
        return await handler(event, data)
