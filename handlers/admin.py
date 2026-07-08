"""
Обработчики для администратора:
- подтверждение/отклонение заказов с комментариями
- команды /setcard, /orders, /stats
"""
import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
import config
import database as db

logger = logging.getLogger(__name__)
router = Router()

# Временное хранилище для комментариев (в реальном проекте лучше использовать FSM, но для простоты – словарь)
pending_comments = {}  # {admin_id: order_id}

def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS

@router.callback_query(F.data.startswith("done:"))
async def order_done(callback: CallbackQuery, bot: Bot):
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

    # Обновляем статус
    await db.update_status(order_id, "done")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Уведомление клиенту
    try:
        await bot.send_message(
            chat_id=order["chat_id"],
            text=(
                f"✅ Ваш заказ #{order_id} одобрен!\n"
                f"Средства зачислены на ID {order['player_id']}.\n"
                f"Дата обработки: {now}"
            )
        )
    except Exception:
        logger.exception("Не удалось уведомить клиента #%s", order_id)

    # Обновляем сообщение в админ-чате
    admin_name = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.full_name
    old_caption = callback.message.caption or ""
    # Добавляем время обработки
    new_caption = (
        f"{old_caption}\n\n"
        f"✅ Одобрено (админ {admin_name}) в {now}"
    )
    try:
        await callback.message.edit_caption(caption=new_caption, reply_markup=None)
    except Exception:
        logger.exception("Не удалось обновить сообщение в админ-чате #%s", order_id)

    await callback.answer("Заказ одобрен ✅")

@router.callback_query(F.data.startswith("cancel:"))
async def order_cancel_start(callback: CallbackQuery):
    """Начало процесса отклонения: запрашиваем комментарий."""
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
    # Сохраняем order_id для этого админа
    pending_comments[callback.from_user.id] = order_id
    await callback.message.answer(
        "Введите причину отклонения (текст). После отправки заказ будет отклонён.\n"
        "Или отправьте /skip, чтобы отклонить без комментария."
    )
    await callback.answer()

@router.message(Command("skip"))
async def skip_comment(message: Message):
    """Пропуск комментария при отклонении."""
    if not is_admin(message.from_user.id):
        return
    admin_id = message.from_user.id
    if admin_id not in pending_comments:
        await message.answer("Нет активного отклонения.")
        return
    order_id = pending_comments.pop(admin_id)
    await finalize_cancel(order_id, admin_id, comment=None, bot=message.bot, source_msg=message)

@router.message(F.text)
async def receive_comment(message: Message):
    """Принимаем комментарий от админа."""
    if not is_admin(message.from_user.id):
        return
    admin_id = message.from_user.id
    if admin_id not in pending_comments:
        return
    order_id = pending_comments.pop(admin_id)
    comment = message.text.strip()
    if not comment:
        await message.answer("Комментарий не может быть пустым. Введите текст или /skip.")
        pending_comments[admin_id] = order_id  # возвращаем обратно
        return
    await finalize_cancel(order_id, admin_id, comment=comment, bot=message.bot, source_msg=message)

async def finalize_cancel(order_id: int, admin_id: int, comment: str | None, bot: Bot, source_msg: Message):
    """Финальная обработка отклонения."""
    order = await db.get_order(order_id)
    if not order:
        await source_msg.answer("Заказ не найден.")
        return
    # Обновляем статус и комментарий
    await db.update_status(order_id, "cancelled", admin_comment=comment)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    admin_name = f"@{source_msg.from_user.username}" if source_msg.from_user.username else source_msg.from_user.full_name

    # Уведомление клиенту
    try:
        text = (
            f"❌ Ваш заказ #{order_id} отклонён.\n"
            f"Дата: {now}\n"
        )
        if comment:
            text += f"Причина: {comment}\n"
        text += f"Свяжитесь с администратором: {config.ADMIN_CONTACTS}"
        await bot.send_message(chat_id=order["chat_id"], text=text)
    except Exception:
        logger.exception("Не удалось уведомить клиента об отклонении #%s", order_id)

    # Обновляем сообщение в админ-чате
    old_caption = source_msg.chat.type != "private" and source_msg.caption or ""  # но мы будем использовать callback.message
    # Лучше обновить через callback.message, но у нас его нет, поэтому получим сообщение админа
    # Мы можем сохранить message_id заказа из БД
    admin_msg_id = order.get("admin_message_id")
    if admin_msg_id:
        try:
            # Получаем сообщение
            msg = await bot.get_messages(chat_id=config.ADMIN_CHAT_ID, message_ids=admin_msg_id)
            if msg:
                old_caption = msg.caption or ""
                new_caption = (
                    f"{old_caption}\n\n"
                    f"❌ Отклонено (админ {admin_name}) в {now}\n"
                    f"Комментарий: {comment or 'не указан'}"
                )
                await bot.edit_message_caption(
                    chat_id=config.ADMIN_CHAT_ID,
                    message_id=admin_msg_id,
                    caption=new_caption,
                    reply_markup=None
                )
        except Exception:
            logger.exception("Не удалось обновить сообщение админа #%s", order_id)

    await source_msg.answer("Заказ отклонён ❌")
    # Удаляем из pending_comments, если осталось
    pending_comments.pop(admin_id, None)

# ------------------- Команды админа -------------------
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
        await message.answer("Активных заказов нет. 🎉")
        return
    lines = ["📋 Активные заказы (в проверке):\n"]
    for o in orders:
        lines.append(f"#{o['id']} — {o['amount']} {o['currency']}, ID: {o['player_id']}, от {o['username']} ({o['order_type']})")
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
        f"⏳ В проверке: {stats['checking']}\n"
        f"💰 Выводов выполнено: {stats.get('withdraw_done', 0)}\n"
        f"⏳ Выводов в проверке: {stats.get('withdraw_checking', 0)}"
    )
