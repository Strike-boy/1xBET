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
        await callback.answer("Zakas topilmadi.", show_alert=True)
        return
    if order["status"] != "checking":
        await callback.answer("Bu zakas qilib bo'lindi.", show_alert=True)
        return

    await db.update_status(order_id, "done")

    try:
        await bot.send_message(
            chat_id=order["chat_id"],
            text=(
                f"✅ Sizning zakasingiz #{order_id} bajarildi!\n"
                f"Pullaringiz akkauntga tushdi {order['player_id']}.\n"
                f"Omad!"
            ),
        )
    except Exception:
        logger.exception("Klientdi zakas bo'yicha ogohlantirib bo'lmadi #%s", order_id)

    admin_name = (
        f"@{callback.from_user.username}"
        if callback.from_user.username
        else callback.from_user.full_name
    )
    old_caption = callback.message.caption or ""
    try:
        await callback.message.edit_caption(
            caption=f"{old_caption}\n\n✅ Tayyor (админ {admin_name})",
            reply_markup=None,
        )
    except Exception:
        logger.exception("Habarni admin-chatda o'zgartirib bo'lmadi (zakas #%s)", order_id)

    await callback.answer("Zakas bajarilgan ✅")


@router.callback_query(F.data.startswith("cancel:"))
async def order_cancel(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    order_id = int(callback.data.split(":")[1])
    order = await db.get_order(order_id)

    if not order:
        await callback.answer("Zakas topilmadi.", show_alert=True)
        return
    if order["status"] != "checking":
        await callback.answer("Zakas bajarilgan.", show_alert=True)
        return

    await db.update_status(order_id, "cancelled")

    try:
        await bot.send_message(
            chat_id=order["chat_id"],
            text=(
                f"❌ Afsuski, buyurtmangiz #{order_id} bekor qilindi.\n"
                f"Adminga yozing‼️"
            ),
        )
    except Exception:
        logger.exception("Klientdi zakas bo'yicha ogohlantirib bo'lmadi #%s", order_id)

    admin_name = (
        f"@{callback.from_user.username}"
        if callback.from_user.username
        else callback.from_user.full_name
    )
    old_caption = callback.message.caption or ""
    try:
        await callback.message.edit_caption(
            caption=f"{old_caption}\n\n❌ Rad etildi (админ {admin_name})",
            reply_markup=None,
        )
    except Exception:
        logger.exception("Habardi admin-chatda o'zgartirib bo'lmadi (zakas #%s)", order_id)

    await callback.answer("Rad etildi")


@router.message(Command("setcard"))
async def cmd_setcard(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Ishlatish:\n/setcard 1234 5678 9012 3456")
        return

    new_card = parts[1].strip()
    await db.set_card_number(new_card)
    await message.answer(f"✅ Karta raqam yangilandi:\n{new_card}")


@router.message(Command("orders"))
async def cmd_orders(message: Message):
    if not is_admin(message.from_user.id):
        return

    orders = await db.get_checking_orders()
    if not orders:
        await message.answer("Aktiv zakaslar yo'q. 🎉")
        return

    lines = ["📋 Aktiv zakaslar (tekshiruvda):\n"]
    for o in orders:
        lines.append(f"#{o['id']} — {o['amount']} UC, ID: {o['player_id']}, от {o['username']}")
    await message.answer("\n".join(lines))


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return

    stats = await db.get_stats()
    await message.answer(
        "📊 Zakaslar statistikasi:\n"
        f"Bugun: {stats['today']}\n"
        f"Umumiy: {stats['total']}\n"
        f"✅ Bajarildi: {stats['done']}\n"
        f"❌ Rad etildi: {stats['cancelled']}\n"
        f"🔍 Tekshiruvda: {stats['checking']}"
    )
