"""
Обработчики клиентов: пополнение, вывод, связь с админом.
"""
import logging
from datetime import datetime, timedelta, timezone
UZ_TZ = timezone(timedelta(hours=5))
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile
)
import config
import database as db
from utils import generate_extra_amount

logger = logging.getLogger(__name__)
router = Router()

# ------------------- FSM состояния -------------------
class DepositStates(StatesGroup):
    currency = State()        # выбор валюты
    player_id = State()       # ID игрока
    amount = State()          # ввод суммы или выбор кнопки
    confirm = State()         # подтверждение оплаты
    screenshot = State()      # скриншот

class WithdrawStates(StatesGroup):
    currency = State()        # выбор валюты
    player_id = State()       # ID игрока
    card_number = State()     # карта для вывода
    confirm = State()         # подтверждение отправки
    screenshot = State()      # чек

# ------------------- Клавиатуры -------------------
def main_menu_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📥 Hisobni to'ldirish")],
            [KeyboardButton(text="📤 Pul yechish")],
            [KeyboardButton(text="👨🏻‍💻 Admin Aloqa")]
        ],
        resize_keyboard=True
    )

def currency_kb():
    """Кнопки выбора валюты (инлайн)"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🇺🇿 UZS", callback_data="currency_uzs"),
             InlineKeyboardButton(text="🇺🇸 USD", callback_data="currency_usd")],
            [InlineKeyboardButton(text="🚫 Bekor qilish", callback_data="cancel_action")]
        ]
    )

def amount_kb():
    """Быстрые суммы для пополнения (reply)"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="50 000"), KeyboardButton(text="100 000"), KeyboardButton(text="150 000")],
            [KeyboardButton(text="300 000"), KeyboardButton(text="500 000"), KeyboardButton(text="Boshqa summa")]
        ],
        resize_keyboard=True
    )

def confirm_payment_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ To'lov qildim", callback_data="paid")],
            [InlineKeyboardButton(text="🚫 Bekor qilish", callback_data="cancel_order")]
        ]
    )

def withdraw_confirm_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ To'lov qildim", callback_data="withdraw_sent")],
            [InlineKeyboardButton(text="🚫 Bekor qilish", callback_data="cancel_order")]
        ]
    )

# ------------------- Команда /start -------------------
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Assalomu alaykum! 🖐️\n"
        "Onlayn kassamizga xush kelibsiz!\n"
        "\n"
        "💳 Toʻldirishlar — 0% komissiya\n"
        "⚡️ Jarayon juda sodda va tez\n"
        "📱 Bir necha soniya ichida hisobingiz toʻldiriladi\n",
        reply_markup=main_menu_kb()
    )

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Bekor qilindi.", reply_markup=main_menu_kb())

# ------------------- Главное меню -------------------
@router.message(F.text == "📥 Hisobni to'ldirish")
async def deposit_start(message: Message, state: FSMContext):
    active = await db.get_active_order(message.from_user.id)
    if active:
        await message.answer(f"⏳ Sizda aktiv zakaz bor (№{active['id']}). Kutib to'ring.")
        return
    await state.set_state(DepositStates.currency)
    await message.answer("🇺🇿So`mli yoki 🇺🇸Dollarli hisobni tanlang:", reply_markup=currency_kb())

@router.message(F.text == "📤 Pul yechish")
async def withdraw_start(message: Message, state: FSMContext):
    active = await db.get_active_order(message.from_user.id)
    if active:
        await message.answer(f"⏳ Sizda aktiv zakaz bor (№{active['id']}). Kutib to'ring.")
        return
    await state.set_state(WithdrawStates.currency)
    await message.answer("🇺🇿So`mli yoki 🇺🇸Dollarli hisobni tanlang:", reply_markup=currency_kb())

@router.message(F.text == "👨🏻‍💻 Admin Aloqa")
async def contact_admin(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👨🏻‍💻 Operator", url=f"https://t.me/{config.ADMIN_CONTACTS.lstrip('@')}")]
        ]
    )
    await message.answer(
        "Pul tushmadimi operatorga chekni junating:\n\n"
        "Muammo yoki savol bo'lsa yozing!"
        f"{config.ADMIN_CONTACTS}",
        reply_markup=kb
    )

# ------------------- Обработчики выбора валюты (инлайн) -------------------
@router.callback_query(F.data.startswith("currency_"))
async def currency_selected(callback: CallbackQuery, state: FSMContext):
    currency = callback.data.split("_")[1].upper()
    await state.update_data(currency=currency)
    current_state = await state.get_state()
    
    if current_state == DepositStates.currency.state:
        await state.set_state(DepositStates.player_id)
        await callback.message.delete()
        await callback.message.answer(
            "🎮 Iltimos, o'yinchi ID'ingizni kiriting:"
        )
    elif current_state == WithdrawStates.currency.state:
        await state.set_state(WithdrawStates.player_id)
        await callback.message.delete()
        if config.WITHDRAW_VIDEO_FILE_ID:
            try:
                await callback.message.answer_video(
                    config.WITHDRAW_VIDEO_FILE_ID,
                    caption="📹 Instruksiya:\n ID kiriting:"
                )
            except Exception:
                await callback.message.answer(
                    "🎮 Iltimos, o'yinchi ID'ingizni kiriting:"
                )
        else:
            await callback.message.answer(
                "🎮 Iltimos, o'yinchi ID'ingizni kiriting:"
            )
    await callback.answer()

@router.callback_query(F.data == "cancel_action")
async def cancel_action(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("Bekor qilindi.", reply_markup=main_menu_kb())
    await callback.answer()

# ------------------- Пополнение: ID игрока -------------------
@router.message(DepositStates.player_id)
async def deposit_player_id(message: Message, state: FSMContext):
    player_id = message.text.strip()
    if not (2 <= len(player_id) <= 50):
        await message.answer("ID 2 dan 50 tagacha belgidan iborat bo'lishi kerak. Qayta urinib ko'ring:")
        return
    
    await state.update_data(player_id=player_id)
    await state.set_state(DepositStates.amount)
    
    await message.answer(
        f"💰 Minimal: 50.000 UZS\n"
        f"💰 Maksimal: 100.000.000 UZS\n\n"
        f"Summani yozing‼️:",
        reply_markup=amount_kb()
    )

# ------------------- Обработчики пополнения: сумма -------------------
@router.message(DepositStates.amount, F.text.regexp(r'^[\d\s]+$'))
async def deposit_amount(message: Message, state: FSMContext):
    text = message.text.strip().replace(" ", "")
    
    if text == "Boshqa summa" or text == "Boshqa":
        await message.answer("Summa kiriting:")
        return
    
    if not text.isdigit():
        await message.answer("To'g'ri summa kiriting.")
        return
    
    amount = int(text)
    if amount < 50000:
        await message.answer("Minimal summa 50 000 UZS.")
        return
    if amount > 100000000:
        await message.answer("Maksimal summa 100 000 000 UZS.")
        return
    
    extra = generate_extra_amount()
    total = amount + extra
    await state.update_data(amount=amount, extra=extra, total=total)
    
    data = await state.get_data()
    card = await db.get_card_number()
    
    # Формируем красивое сообщение как в примере
    await message.answer(
        f"#{message.message_id}\n"
        f"🆔ID {data.get('currency', 'UZS')} 🇺🇿: {data['player_id']}\n"
        f"💰Komissiya: 0%\n"
        f"💵{data.get('currency', 'UZS')} 🇺🇿 tushadi: {total:,}\n\n"
        f"{total:,} {data.get('currency', 'UZS')} pulni {card} karta raqamga o'tkazing va\n\n"
        f"Diqqat noto'g'ri o'tqazmang, tushmaydi aks holda ‼️\n"
        f"Arizada ko'rsatilgan summani o'tqazing ‼️\n\n"
        f"(To'lov qildim) tugmasiga bosing‼ ✅",
        reply_markup=confirm_payment_kb()
    )
    await state.set_state(DepositStates.confirm)

@router.message(DepositStates.amount)
async def deposit_amount_manual(message: Message, state: FSMContext):
    text = message.text.strip().replace(" ", "")
    if not text.isdigit():
        await message.answer("To'g'ri son kiriting.")
        return
    
    amount = int(text)
    if amount < 50000:
        await message.answer("Minimal summa 50 000 UZS.")
        return
    if amount > 100000000:
        await message.answer("Maksimal summa 100 000 000 UZS.")
        return
    
    extra = generate_extra_amount()
    total = amount + extra
    await state.update_data(amount=amount, extra=extra, total=total)
    
    data = await state.get_data()
    card = await db.get_card_number()
    
    await message.answer(
        f"#{message.message_id}\n"
        f"🆔ID {data.get('currency', 'UZS')} 🇺🇿: {data['player_id']}\n"
        f"💰Komissiya: 0%\n"
        f"💵{data.get('currency', 'UZS')} 🇺🇿 tushadi: {total:,}\n\n"
        f"{total:,} {data.get('currency', 'UZS')} pulni {card} karta raqamga o'tkazing va\n\n"
        f"Diqqat noto'g'ri o'tqazmang, tushmaydi aks holda ‼️\n"
        f"Arizada ko'rsatilgan summani o'tqazing ‼️\n\n"
        f"(To'lov qildim) tugmasiga bosing‼ ✅",
        reply_markup=confirm_payment_kb()
    )
    await state.set_state(DepositStates.confirm)

# ------------------- Подтверждение оплаты (пополнение) -------------------
@router.callback_query(DepositStates.confirm, F.data == "paid")
async def deposit_paid(callback: CallbackQuery, state: FSMContext):
    await state.set_state(DepositStates.screenshot)
    await callback.message.edit_text("📸 Skrinshotni (chekni) yuboring.", reply_markup=None)
    await callback.answer()

@router.callback_query(DepositStates.confirm, F.data == "cancel_order")
async def deposit_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Buyurtma bekor qilindi.", reply_markup=None)
    await callback.message.answer("Amalni tanlang:", reply_markup=main_menu_kb())
    await callback.answer()

# ------------------- Получение скриншота (пополнение) -------------------
@router.message(DepositStates.screenshot, F.photo | F.document)
async def deposit_screenshot(message: Message, state: FSMContext, bot: Bot):
    if message.photo:
        file_id = message.photo[-1].file_id
        is_doc = False
    elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
        file_id = message.document.file_id
        is_doc = True
    else:
        await message.answer("Iltimos, rasm yuboring.")
        return

    data = await state.get_data()
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
    
    order_id = await db.create_order(
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        username=username,
        amount=data['amount'],
        extra_amount=data.get('extra', 0),
        player_id=data['player_id'],
        screenshot_file_id=file_id,
        currency=data.get('currency', 'UZS'),
        order_type='deposit'
    )

    caption = (
        f"🆕 Zakaz #{order_id} (to'ldirish)\n"
        f"Summa: {data.get('total', data['amount']):,} {data.get('currency', 'UZS')}\n"
        f"ID: {data['player_id']}\n"
        f"Kimdan: {username} (id: {message.from_user.id})\n"
        f"Valyuta: {data.get('currency', 'UZS')}\n"
        f"🕒 Yaratilgan: {datetime.now(UZ_TZ).strftime('%Y-%m-%d %H:%M')}\n"
        f"Holati: ⏳ tekshiruv"
    )
    
    admin_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"done:{order_id}"),
             InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancel:{order_id}")]
        ]
    )
    
    try:
        if is_doc:
            msg = await bot.send_document(config.ADMIN_CHAT_ID, file_id, caption=caption, reply_markup=admin_kb)
        else:
            msg = await bot.send_photo(config.ADMIN_CHAT_ID, file_id, caption=caption, reply_markup=admin_kb)
        await db.set_admin_message_id(order_id, msg.message_id)
    except Exception:
        logger.exception("Zakaz #%s adminlarga yuborilmadi", order_id)

    await message.answer("✅ Buyurtma qabul qilindi! Tasdiqlashni kuting.", reply_markup=main_menu_kb())
    await state.clear()

@router.message(DepositStates.screenshot)
async def deposit_screenshot_invalid(message: Message):
    await message.answer("Iltimos, chek rasmini yuboring.")

# ------------------- Сценарий вывода -------------------
@router.message(WithdrawStates.player_id)
async def withdraw_player_id(message: Message, state: FSMContext):
    player_id = message.text.strip()
    if not (2 <= len(player_id) <= 50):
        await message.answer("ID 2 dan 50 tagacha belgidan iborat bo'lishi kerak. Qayta urinib ko'ring:")
        return
    await state.update_data(player_id=player_id)
    await state.set_state(WithdrawStates.card_number)
    await message.answer("💳 Pul chiqarish uchun karta raqamingizni kiriting:")

@router.message(WithdrawStates.card_number)
async def withdraw_card_number(message: Message, state: FSMContext):
    card = message.text.strip()
    card_clean = card.replace(" ", "")
    if not card_clean.isdigit() or len(card_clean) < 10:
        await message.answer("To'g'ri karta raqamini kiriting (faqat raqamlar).")
        return
    
    await state.update_data(withdraw_card=card)
    data = await state.get_data()
    
    await message.answer(
        f"📋 Pul chiqarish ma'lumotlari:\n"
        f"ID: {data['player_id']}\n"
        f"Karta: {card}\n"
        f"Valyuta: {data.get('currency', 'UZS')}\n\n"
        f"🏦 Kassa manzili: Karshi shahri, G'ang'a orientiri (24/7)\n\n"
        f"Pulni olganingizdan so'ng «✅ To'lov qildim» tugmasini bosing.",
        reply_markup=withdraw_confirm_kb()
    )
    await state.set_state(WithdrawStates.confirm)

@router.callback_query(WithdrawStates.confirm, F.data == "withdraw_sent")
async def withdraw_sent(callback: CallbackQuery, state: FSMContext):
    await state.set_state(WithdrawStates.screenshot)
    await callback.message.edit_text("📸 Chek skrinshotini yuboring.", reply_markup=None)
    await callback.answer()

@router.callback_query(WithdrawStates.confirm, F.data == "cancel_order")
async def withdraw_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Pul chiqarish bekor qilindi.", reply_markup=None)
    await callback.message.answer("Amalni tanlang:", reply_markup=main_menu_kb())
    await callback.answer()

@router.message(WithdrawStates.screenshot, F.photo | F.document)
async def withdraw_screenshot(message: Message, state: FSMContext, bot: Bot):
    if message.photo:
        file_id = message.photo[-1].file_id
        is_doc = False
    elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
        file_id = message.document.file_id
        is_doc = True
    else:
        await message.answer("Iltimos, chek rasmini yuboring.")
        return

    data = await state.get_data()
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
    
    order_id = await db.create_order(
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        username=username,
        amount=0,
        extra_amount=0,
        player_id=data['player_id'],
        screenshot_file_id=file_id,
        currency=data.get('currency', 'UZS'),
        order_type='withdraw',
        withdraw_card=data['withdraw_card']
    )

    caption = (
        f"🆕 Zakaz #{order_id} (pul chiqarish)\n"
        f"ID: {data['player_id']}\n"
        f"Karta: {data['withdraw_card']}\n"
        f"Kimdan: {username} (id: {message.from_user.id})\n"
        f"Valyuta: {data.get('currency', 'UZS')}\n"
        f"🕒 Yaratilgan: {datetime.now(UZ_TZ).strftime('%Y-%m-%d %H:%M')}\n"
        f"Holati: ⏳ tekshiruv"
    )
    
    admin_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"done:{order_id}"),
             InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancel:{order_id}")]
        ]
    )
    
    try:
        if is_doc:
            msg = await bot.send_document(config.ADMIN_CHAT_ID, file_id, caption=caption, reply_markup=admin_kb)
        else:
            msg = await bot.send_photo(config.ADMIN_CHAT_ID, file_id, caption=caption, reply_markup=admin_kb)
        await db.set_admin_message_id(order_id, msg.message_id)
    except Exception:
        logger.exception("Pul chiqarish #%s adminlarga yuborilmadi", order_id)

    await message.answer("✅ Ariza qabul qilindi! Tekshiruvdan so'ng xabar beramiz.", reply_markup=main_menu_kb())
    await state.clear()

@router.message(WithdrawStates.screenshot)
async def withdraw_screenshot_invalid(message: Message):
    await message.answer("Iltimos, chek rasmini yuboring.")
