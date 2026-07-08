import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import database as db
import config
from utils.i18n import get_text

logger = logging.getLogger(__name__)
router = Router()

# Состояние для ввода причины отклонения
class AdminRejectState(StatesGroup):
    reason = State()

def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS

# При обработке кнопки "Отклонить" переходим в состояние запроса причины
@router.callback_query(F.data.startswith("reject:"))
async def reject_order(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет прав")
        return
    order_id = int(callback.data.split(":")[1])
    order = await db.get_order(order_id)
    if not order or order['status'] != 'checking':
        await callback.answer("Заказ уже обработан")
        return
    # Сохраняем order_id в состоянии
    await state.update_data(order_id=order_id, admin_message_id=callback.message.message_id)
    await state.set_state(AdminRejectState.reason)
    await callback.message.answer("Введите причину отклонения (или отправьте 'пропустить' чтобы не указывать):")
    await callback.answer()

@router.message(AdminRejectState.reason)
async def process_reject_reason(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    order_id = data.get('order_id')
    if not order_id:
        await state.clear()
        return
    reason = message.text.strip()
    if reason.lower() == 'пропустить':
        reason = None
    # Обновляем статус
    await db.update_order_status(order_id, 'cancelled', comment=reason, admin_username=message.from_user.username or str(message.from_user.id))
    order = await db.get_order(order_id)
    # Уведомляем клиента
    lang = await db.get_user_language(order['user_id'])
    contacts = await db.get_setting('admin_contacts')
    text = get_text('order_rejected', lang, order_id=order_id, reason=reason or "не указана", contacts=contacts)
    try:
        await bot.send_message(order['user_id'], text)
    except Exception:
        pass
    # Обновляем сообщение в админ-чате
    try:
        admin_msg_id = order['admin_message_id']
        await bot.edit_message_caption(
            chat_id=config.ADMIN_CHAT_ID,
            message_id=admin_msg_id,
            caption=order['caption'] + f"\n\n❌ Отклонено (причина: {reason})"
        )
    except Exception:
        pass
    await message.answer(f"Заказ #{order_id} отклонён.")
    await state.clear()

# Кнопка "Одобрить" - без комментария
@router.callback_query(F.data.startswith("approve:"))
async def approve_order(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет прав")
        return
    order_id = int(callback.data.split(":")[1])
    order = await db.get_order(order_id)
    if not order or order['status'] != 'checking':
        await callback.answer("Заказ уже обработан")
        return
    await db.update_order_status(order_id, 'done', admin_username=callback.from_user.username or str(callback.from_user.id))
    # Уведомляем клиента
    lang = await db.get_user_language(order['user_id'])
    text = get_text('order_approved', lang, order_id=order_id)
    try:
        await bot.send_message(order['user_id'], text)
    except Exception:
        pass
    # Обновляем сообщение в админ-чате
    try:
        admin_msg_id = order['admin_message_id']
        await bot.edit_message_caption(
            chat_id=config.ADMIN_CHAT_ID,
            message_id=admin_msg_id,
            caption=order['caption'] + "\n\n✅ Одобрено"
        )
    except Exception:
        pass
    await callback.answer("Одобрено")

# Команды админа /setcard, /orders, /stats (без изменений, но с учётом новых функций)
@router.message(Command("setcard"))
async def cmd_setcard(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /setcard 1234 5678 9012 3456")
        return
    card = parts[1].strip()
    await db.set_setting('card_number', card)
    await message.answer(f"✅ Карта обновлена: {card}")

@router.message(Command("orders"))
async def cmd_orders(message: Message):
    if not is_admin(message.from_user.id):
        return
    orders = await db.get_checking_orders()
    if not orders:
        await message.answer("Нет активных заказов.")
        return
    lines = ["📋 Активные заказы:"]
    for o in orders:
        lines.append(f"#{o['id']} — {o['type']} — {o['amount']} — ID: {o['player_id']}")
    await message.answer("\n".join(lines))

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    stats = await db.get_stats()
    await message.answer(
        f"📊 Статистика:\n"
        f"Всего: {stats['total']}\n"
        f"✅ Выполнено: {stats['done']}\n"
        f"❌ Отклонено: {stats['cancelled']}\n"
        f"🔍 На проверке: {stats['checking']}\n"
        f"📅 За сегодня: {stats['today']}"
    )

# Напоминание админам (будет запускаться в main)
async def reminder_task(bot: Bot):
    while True:
        await asyncio.sleep(300)  # 5 минут
        checking = await db.get_checking_orders()
        if checking:
            count = len(checking)
            await bot.send_message(config.ADMIN_CHAT_ID, f"⏳ Напоминание: у вас {count} заказов на проверке.")
