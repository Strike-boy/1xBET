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
        keyboard=[[KeyboardButton(text="📥Hisobni to'ldirish")]],
        resize_keyboard=True,
    )


def payment_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ To'lov qildim", callback_data="paid")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_order")],
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Assalomu alaykum! 🖐️\n"
        "Onlayn kassamizga xush kelibsiz!\n"
        "\n"
        "💳 Toʻldirishlar — 0% komissiya\n"
        "⚡️ Jarayon juda sodda va tez\n"
        "📱 Bir necha soniya ichida hisobingiz toʻldiriladi\n"
        "\n"
        "🔘 «Toʻldirish» tugmasini bosing va buyurtmangizni rasmiylashtiring.",
        reply_markup=main_menu_kb(),
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Дополнительная удобная команда — прервать оформление заказа на любом шаге."""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Bekor qilindi❌", reply_markup=main_menu_kb())
        return
    await state.clear()
    await message.answer("Bekor qilindi❌", reply_markup=main_menu_kb())


@router.message(F.text == "📥Hisobni to'ldirish")
async def start_order(message: Message, state: FSMContext):
    await state.set_state(OrderStates.amount)
    await message.answer(
        "💰 Minimal: 50.000 UZS\n"
        "💎 Maksimal: 100.000.000 UZS\n"
        "\n"
        "Summani kiriting‼️:",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(OrderStates.amount)
async def process_amount(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("⚠️Iltimos, to'gri summani kiriting, masalan 50500.")
        return

    await state.update_data(amount=int(text))
    await state.set_state(OrderStates.player_id)
    await message.answer("UZS🇺🇿 ID raqamini kiriting:")


@router.message(OrderStates.player_id)
async def process_player_id(message: Message, state: FSMContext):
    player_id = (message.text or "").strip()
    if not (2 <= len(player_id) <= 50):
        await message.answer("⚠️To'gri ID raqamini kiriting:")
        return

    await state.update_data(player_id=player_id)
    data = await state.get_data()
    card_number = await db.get_card_number()

    await message.answer(
        f"📋Sizning zakasingiz:\n"
        f"💵Summa: {data['amount']} UZS\n"
        f"🆔ID UZS 🇺🇿: {player_id}\n\n"
        f"💳To'lov uchun karta:\n{card_number}\n\n"
        f"{data['amount']} UZS pulni {card_number} karta raqamiga o'tkazing‼️\n\n"
        f"Diqqat notug'ri o'tqazmang, aks holda tushmaydi‼️\n\n"
        f"(✅ To'lov qildim) tugmasini bosing‼️",
        reply_markup=payment_kb(),
    )
    await state.set_state(OrderStates.confirm_payment)


@router.callback_query(OrderStates.confirm_payment, F.data == "cancel_order")
async def cancel_payment(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ To'lov bekor qilindi.", reply_markup=None)
    await callback.message.answer(
        "Yanfi zakas berish uchun, pastdagi tugmani bosing.",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


@router.callback_query(OrderStates.confirm_payment, F.data == "paid")
async def confirm_paid(callback: CallbackQuery, state: FSMContext):
    await state.set_state(OrderStates.screenshot)
    await callback.message.edit_text(
        "📸Iltimos, to'lov chekini junating.", reply_markup=None
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
        await message.answer("⚠️Iltimos, to'lov chekini junating (rasm).")
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
        f"🆕 Zakas #{order_id}\n"
        f"Summa: {amount} UC\n"
        f"ID: {player_id}\n"
        f"От: {username_display} (id: {message.from_user.id})\n"
        f"Holati: tekshirilmoqda⏳"
    )
    admin_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tayyor", callback_data=f"done:{order_id}"),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancel:{order_id}"),
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
        logger.exception("Sizning zakasingiz #%s tekshirishga yuborib bo'lmadi!", order_id)

    await message.answer(
        "✅ Raxmat! Zakasingiz qabul qilindi.\n"
        "Tekshiruvdan so'ng pulingiz tushadi‼️",
        reply_markup=main_menu_kb(),
    )
    await state.clear()


@router.message(OrderStates.screenshot)
async def screenshot_invalid(message: Message):
    await message.answer("⚠️Iltimos, to'lov chekini junating (rasm).")
