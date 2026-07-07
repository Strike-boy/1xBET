"""
Обработчики для клиентов: оформление заказа на пополнение UC.

Сценарий (FSM):
amount -> player_id -> confirm_payment -> screenshot -> заказ создан и уходит в админ-чат
"""

import logging

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

import config
import database as db

logger = logging.getLogger(__name__)
router = Router()


class OrderStates(StatesGroup):
    amount = State()
    player_id = State()
    confirm_payment = State()
    screenshot = State()


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Пополнить UC")]],
        resize_keyboard=True,
    )


def payment_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Я оплатил", callback_data="paid")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_order")],
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Добро пожаловать в магазин UC!\n"
        "Нажмите кнопку «Пополнить UC», чтобы оформить заказ.",
        reply_markup=main_menu_kb(),
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Дополнительная удобная команда — прервать оформление заказа на любом шаге."""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нечего отменять 🙂", reply_markup=main_menu_kb())
        return
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=main_menu_kb())


@router.message(F.text == "Пополнить UC")
async def start_order(message: Message, state: FSMContext):
    await state.set_state(OrderStates.amount)
    await message.answer(
        "💰 Введите количество UC, которое хотите получить:",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(OrderStates.amount)
async def process_amount(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("⚠️ Пожалуйста, введите корректное число, например 660.")
        return

    await state.update_data(amount=int(text))
    await state.set_state(OrderStates.player_id)
    await message.answer("🎮 Введите ваш ID игрока в PUBG Mobile:")


@router.message(OrderStates.player_id)
async def process_player_id(message: Message, state: FSMContext):
    player_id = (message.text or "").strip()
    if not (2 <= len(player_id) <= 50):
        await message.answer("⚠️ Введите корректный ID игрока (2–50 символов):")
        return

    await state.update_data(player_id=player_id)
    data = await state.get_data()
    card_number = await db.get_card_number()

    await message.answer(
        f"📋 Ваш заказ:\n"
        f"Сумма: {data['amount']} UC\n"
        f"ID игрока: {player_id}\n\n"
        f"💳 Реквизиты для оплаты:\n{card_number}\n\n"
        f"После оплаты нажмите «Я оплатил».",
        reply_markup=payment_kb(),
    )
    await state.set_state(OrderStates.confirm_payment)


@router.callback_query(OrderStates.confirm_payment, F.data == "cancel_order")
async def cancel_payment(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Заказ отменён.", reply_markup=None)
    await callback.message.answer(
        "Чтобы оформить новый заказ, нажмите кнопку ниже.",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


@router.callback_query(OrderStates.confirm_payment, F.data == "paid")
async def confirm_paid(callback: CallbackQuery, state: FSMContext):
    await state.set_state(OrderStates.screenshot)
    await callback.message.edit_text(
        "📸 Пожалуйста, прикрепите скриншот оплаты.", reply_markup=None
    )
    await callback.answer()


@router.message(OrderStates.screenshot, F.photo | F.document)
async def process_screenshot(message: Message, state: FSMContext, bot: Bot):
    is_document = False

    if message.photo:
        screenshot_file_id = message.photo[-1].file_id
    elif (
        message.document
        and message.document.mime_type
        and message.document.mime_type.startswith("image/")
    ):
        screenshot_file_id = message.document.file_id
        is_document = True
    else:
        await message.answer("⚠️ Пожалуйста, отправьте скриншот оплаты (фото).")
        return

    data = await state.get_data()
    amount = data.get("amount")
    player_id = data.get("player_id")

    username_display = (
        f"@{message.from_user.username}"
        if message.from_user.username
        else message.from_user.full_name
    )

    order_id = await db.create_order(
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        username=username_display,
        amount=amount,
        player_id=player_id,
        screenshot_file_id=screenshot_file_id,
    )

    caption = (
        f"🆕 Заказ #{order_id}\n"
        f"Сумма: {amount} UC\n"
        f"ID игрока: {player_id}\n"
        f"От: {username_display} (id: {message.from_user.id})\n"
        f"Статус: проверка"
    )
    admin_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Готово", callback_data=f"done:{order_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"cancel:{order_id}"),
            ]
        ]
    )

    try:
        if is_document:
            admin_msg = await bot.send_document(
                chat_id=config.ADMIN_CHAT_ID,
                document=screenshot_file_id,
                caption=caption,
                reply_markup=admin_kb,
            )
        else:
            admin_msg = await bot.send_photo(
                chat_id=config.ADMIN_CHAT_ID,
                photo=screenshot_file_id,
                caption=caption,
                reply_markup=admin_kb,
            )
        await db.set_admin_message_id(order_id, admin_msg.message_id)
    except Exception:
        logger.exception("Не удалось отправить заказ #%s в админ-чат", order_id)

    await message.answer(
        "✅ Спасибо! Ваш заказ принят на проверку.\n"
        "Ожидайте, UC будут зачислены вручную после проверки оплаты.",
        reply_markup=main_menu_kb(),
    )
    await state.clear()


@router.message(OrderStates.screenshot)
async def screenshot_invalid(message: Message):
    await message.answer("⚠️ Пожалуйста, отправьте именно скриншот оплаты (фото).")
