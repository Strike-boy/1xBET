"""
Обработчики для администратора:
- подтверждение/отклонение заказов с комментариями
- команды /setcard, /orders, /stats, /history
"""
import logging
from datetime import datetime, timedelta, timezone
UZ_TZ = timezone(timedelta(hours=5))
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
import config
import database as db
from utils import format_number

logger = logging.getLogger(__name__)
router = Router()

# Временное хранилище для комментариев
pending_comments = {}  # {admin_id: order_id}

def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS

# ------------------- Обработка заказов -------------------
@router.callback_query(F.data.startswith("done:"))
async def order_done(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    
    order_id = int(callback.data.split(":")[1])
    order = await db.get_order(order_id)
    
    if not order:
        await callback.answer("Zakaz topilmadi.", show_alert=True)
        return
    if order["status"] != "checking":
        await callback.answer("Bu zakaz bajarib bo'lingan.", show_alert=True)
        return

    await db.update_status(order_id, "done")
    now = datetime.now(UZ_TZ).strftime("%Y-%m-%d %H:%M")

    # Уведомление клиенту
    try:
        text = f"✅ Sizning zakazingiz #{order_id} qabul qilindi!\n"
        if order['order_type'] == 'deposit':
            text += f"Pullaringiz tushdi, ID: {order['player_id']}.\n"
        else:
            text += f"Pul o'tkazildi, karta: {order.get('withdraw_card', 'указанную')}.\n"
        text += f"Vaqt: {now}"
        await bot.send_message(chat_id=order["chat_id"], text=text)
    except Exception:
        logger.exception("Klientdi habar qilib bo'lmadi #%s", order_id)

    # Обновляем сообщение в админ-чате
    admin_name = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.full_name
    old_caption = callback.message.caption or ""
    new_caption = f"{old_caption}\n\n✅ Tasdiqlandi (админ {admin_name}) в {now}"
    
    try:
        await callback.message.edit_caption(caption=new_caption, reply_markup=None)
    except Exception:
        logger.exception("Admin-chatda habarni yangilab bo'lmadi #%s", order_id)

    await callback.answer("Zakaz tasdiqlandi ✅")

@router.callback_query(F.data.startswith("cancel:"))
async def order_cancel_start(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    
    order_id = int(callback.data.split(":")[1])
    order = await db.get_order(order_id)
    
    if not order:
        await callback.answer("Zakaz topilmadi.", show_alert=True)
        return
    if order["status"] != "checking":
        await callback.answer("Bu zakaz bajarib bo'lingan.", show_alert=True)
        return
    
    pending_comments[callback.from_user.id] = order_id
    await callback.message.answer(
        "Rad etish sababini yozing!\n"
        "Yoki bo'sh qoldirish uchun /skip ni bsoing."
    )
    await callback.answer()

@router.message(Command("skip"))
async def skip_comment(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    admin_id = message.from_user.id
    if admin_id not in pending_comments:
        await message.answer("Aktiv rad etishla yo'q.")
        return
    
    order_id = pending_comments.pop(admin_id)
    await finalize_cancel(order_id, admin_id, comment=None, bot=message.bot, source_msg=message)

@router.message(
    F.text,
    ~F.text.startswith("/"),
    lambda message: message.from_user.id in pending_comments
)
async def receive_comment(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    admin_id = message.from_user.id
    if admin_id not in pending_comments:
        return
    
    order_id = pending_comments.pop(admin_id)
    comment = message.text.strip()
    
    if not comment:
        await message.answer("Kommentariya bo'sh bo'lishi mumkun emas. Tekst yozing yoki /skip ni bosing.")
        pending_comments[admin_id] = order_id
        return
    
    await finalize_cancel(order_id, admin_id, comment=comment, bot=message.bot, source_msg=message)

async def finalize_cancel(order_id: int, admin_id: int, comment: str | None, bot: Bot, source_msg: Message):
    order = await db.get_order(order_id)
    if not order:
        await source_msg.answer("Zakas topilmadi.")
        return
    
    await db.update_status(order_id, "cancelled", admin_comment=comment)
    now = datetime.now(UZ_TZ).strftime("%Y-%m-%d %H:%M")
    admin_name = f"@{source_msg.from_user.username}" if source_msg.from_user.username else source_msg.from_user.full_name

    # Уведомление клиенту
    try:
        text = f"❌ Sizning zakasingiz #{order_id} rad qilindi.\nДата: {now}\n"
        if comment:
            text += f"Sababi: {comment}\n"
        text += f"Admin bilan bog'laning: {config.ADMIN_CONTACTS}"
        await bot.send_message(chat_id=order["chat_id"], text=text)
    except Exception:
        logger.exception("Klientdi zakazdi rad bo'lganligi haqida habar qilib bo'lmadi. #%s", order_id)

    # Обновляем сообщение в админ-чате
    admin_msg_id = order.get("admin_message_id")
    if admin_msg_id:
        try:
            old_caption = source_msg.caption or ""
            new_caption = (
                f"{old_caption}\n\n"
                f"❌ Rad qilindi (админ {admin_name}) в {now}\n"
                f"Sababi: {comment or 'не указан'}"
            )
            await bot.edit_message_caption(
                chat_id=config.ADMIN_CHAT_ID,
                message_id=admin_msg_id,
                caption=new_caption,
                reply_markup=None
            )
        except Exception:
            logger.exception("Admin habarini yangilab bo'lmadi #%s", order_id)

    await source_msg.answer("Zakaz rad qilindi ❌")
    pending_comments.pop(admin_id, None)

# ------------------- Команды админа -------------------
@router.message(Command("setcard"))
async def cmd_setcard(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Ishlatilishi:\n/setcard 1234 5678 9012 3456")
        return
    
    new_card = parts[1].strip()
    await db.set_card_number(new_card)
    await message.answer(f"✅ Karta raqami yangilandi:\n{new_card}")

@router.message(Command("orders"))
async def cmd_orders(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    orders = await db.get_checking_orders()
    if not orders:
        await message.answer("Aktiv zakazlar yo'q. 🎉")
        return
    
    lines = ["📋 Aktiv zakazlar (tekshiruvda):\n"]
    for o in orders:
        lines.append(f"#{o['id']} — {o['amount']:,} {o['currency']}, ID: {o['player_id']}, от {o['username']} ({o['order_type']})")
    await message.answer("\n".join(lines))

@router.message(Command("history"))
async def cmd_history(message: Message):
    """Показывает статистику за сегодня: принято, отклонено, в ожидании."""
    if not is_admin(message.from_user.id):
        return
    
    stats = await db.get_stats()
    today = datetime.now(UZ_TZ).strftime("%Y-%m-%d")
    
    await message.answer(
        f"📊 Bugungi zakazlar {today}:\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✅ Qabul qilindi: {stats['done']}\n"
        f"❌ Rad etildi: {stats['cancelled']}\n"
        f"⏳ Tekshirilmoqda: {stats['checking']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📦 Bugunga: {stats['today']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 Chiqim (bajarildi): {stats.get('withdraw_done', 0)}\n"
        f"⏳ Chiqim (kutilmoqda): {stats.get('withdraw_checking', 0)}"
    )

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    stats = await db.get_stats()
    
    # Существующая статистика
    result_text = (
        "📊 Zakazlar statistikasi:\n"
        f"Bugun: {stats['today']}\n"
        f"Jami: {stats['total']}\n"
        f"✅ Bajarildi: {stats['done']}\n"
        f"❌ Rad etildi: {stats['cancelled']}\n"
        f"⏳ Tekshiruvda: {stats['checking']}\n"
        f"💰 Bajarilgan chiqimlar: {stats.get('withdraw_done', 0)}\n"
        f"⏳ Tekshiruvdagi chiqimlar: {stats.get('withdraw_checking', 0)}\n\n"
    )
    
    # Новый блок: только пополнения
    result_text += (
        "📅 Bugun\n"
        f"💰 To'ldirishlar: {format_number(stats.get('today_deposit_sum', 0))} so'm\n\n"
    )
    
    # Новый блок: общие суммы (только пополнения)
    result_text += (
        "📆 Umumiy\n"
        f"💰 To'ldirishlar: {format_number(stats.get('total_deposit_sum', 0))} so'm\n\n"
    )
    
    # Новый блок: пользователи
    result_text += (
        "👥 Foydalanuvchilar\n"
        f"🆕 Bugun: {stats.get('new_users_today', 0)}\n"
        f"👤 Jami: {stats.get('total_users', 0)}"
    )
    
    await message.answer(result_text)
