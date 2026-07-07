"""
Обработчики для администратора:
- подтверждение/отклонение заказов (инлайн-кнопки под скриншотом в админ-чате)
- команды /setcard, /orders, /stats (доступны только ID из ADMIN_IDS)
"""

import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import config
import database as db

logger = logging.getLogger(__name__)
router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


@router.callback_query(F.data.startswith("done:"))
async def order_done(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        # Тихо игнорируем нажатие от не-админа, просто гасим "часики" на кнопке.
        await callback.answer()
        return

    order_id = int(callback.data.split(":")[1])
    order = await db.get_order(order_id)

    if not order:
        await callback.answer("Заказ не найден.", show_alert=True)
        return
    if order["status"] != "checking":
        await callback.answer("Этот заказ уже обработан.", show_alert=True)
        return

    await db.update_status(order_id, "done")

    try:
        await bot.send_message(
            chat_id=order["chat_id"],
            text=(
                f"✅ Ваш заказ #{order_id} выполнен!\n"
                f"UC зачислены на аккаунт {order['player_id']}.\n"
                f"Приятной игры!"
            ),
        )
    except Exception:
        logger.exception("Не удалось уведомить клиента по заказу #%s", order_id)

    admin_name = (
        f"@{callback.from_user.username}"
        if callback.from_user.username
        else callback.from_user.full_name
    )
    old_caption = callback.message.caption or ""
    try:
        await callback.message.edit_caption(
            caption=f"{old_caption}\n\n✅ Готово (админ {admin_name})",
            reply_markup=None,
        )
    except Exception:
        logger.exception("Не удалось отредактировать сообщение в админ-чате (заказ #%s)", order_id)

    await callback.answer("Заказ отмечен как выполненный ✅")


@router.callback_query(F.data.startswith("cancel:"))
async def order_cancel(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    order_id = int(callback.data.split(":")[1])
    order = await db.get_order(order_id)

    if not order:
        await callback.answer("Заказ не найден.", show_alert=True)
        return
    if order["status"] != "checking":
        await callback.answer("Этот заказ уже обработан.", show_alert=True)
        return

    await db.update_status(order_id, "cancelled")

    try:
        await bot.send_message(
            chat_id=order["chat_id"],
            text=(
                f"❌ К сожалению, ваш заказ #{order_id} отклонён.\n"
                f"Если нужна причина, обратитесь в поддержку."
            ),
        )
    except Exception:
        logger.exception("Не удалось уведомить клиента по заказу #%s", order_id)

    admin_name = (
        f"@{callback.from_user.username}"
        if callback.from_user.username
        else callback.from_user.full_name
    )
    old_caption = callback.message.caption or ""
    try:
        await callback.message.edit_caption(
            caption=f"{old_caption}\n\n❌ Отклонено (админ {admin_name})",
            reply_markup=None,
        )
    except Exception:
        logger.exception("Не удалось отредактировать сообщение в админ-чате (заказ #%s)", order_id)

    await callback.answer("Заказ отклонён")


@router.message(Command("setcard"))
async def cmd_setcard(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Использование:\n/setcard 1234 5678 9012 3456")
        return

    new_card = parts[1].strip()
    await db.set_card_number(new_card)
    await message.answer(f"✅ Номер карты обновлён:\n{new_card}")


@router.message(Command("orders"))
async def cmd_orders(message: Message):
    if not is_admin(message.from_user.id):
        return

    orders = await db.get_checking_orders()
    if not orders:
        await message.answer("Нет активных заказов на проверке. 🎉")
        return

    lines = ["📋 Активные заказы (на проверке):\n"]
    for o in orders:
        lines.append(f"#{o['id']} — {o['amount']} UC, ID: {o['player_id']}, от {o['username']}")
    await message.answer("\n".join(lines))


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return

    stats = await db.get_stats()
    await message.answer(
        "📊 Статистика заказов:\n"
        f"Сегодня: {stats['today']}\n"
        f"Всего: {stats['total']}\n"
        f"✅ Выполнено: {stats['done']}\n"
        f"❌ Отклонено: {stats['cancelled']}\n"
        f"🔍 На проверке: {stats['checking']}"
    )
