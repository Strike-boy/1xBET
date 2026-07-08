import logging
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
import database as db
from utils.i18n import get_text
from utils.helpers import generate_unique_sum
from middlewares.throttling import ThrottlingMiddleware
import config

router = Router()
router.callback_query.middleware(ThrottlingMiddleware(rate_limit=1.0))

class DepositStates(StatesGroup):
    amount = State()
    player_id = State()
    confirm_payment = State()
    screenshot = State()

@router.message(F.text.in_(["📥 Пополнить", "📥 To'ldirish"]))
async def start_deposit(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = await db.get_user_language(user_id)
    # Проверка на активный заказ
    if await db.has_active_order(user_id):
        await message.answer("У вас уже есть активный заказ. Дождитесь его завершения.")
        return
    await state.set_state(DepositStates.amount)
    # Кнопки быстрых сумм (inline)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="50 000", callback_data="amount_50000"),
         InlineKeyboardButton(text="100 000", callback_data="amount_100000")],
        [InlineKeyboardButton(text="150 000", callback_data="amount_150000"),
         InlineKeyboardButton(text="300 000", callback_data="amount_300000")],
        [InlineKeyboardButton(text="500 000", callback_data="amount_500000")]
    ])
    await message.answer(
        get_text('enter_amount', lang) + "\n" + get_text('quick_amounts', lang),
        reply_markup=kb
    )

@router.callback_query(DepositStates.amount, F.data.startswith("amount_"))
async def process_quick_amount(callback: CallbackQuery, state: FSMContext):
    amount = int(callback.data.split("_")[1])
    await state.update_data(amount=amount)
    await callback.message.delete()
    await callback.message.answer(f"Вы выбрали {amount} UZS.")
    await ask_player_id(callback.message, state)

@router.message(DepositStates.amount)
async def process_manual_amount(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("Введите число.")
        return
    amount = int(text)
    if amount < 50000 or amount > 100000000:
        await message.answer("Сумма должна быть от 50 000 до 100 000 000.")
        return
    await state.update_data(amount=amount)
    await ask_player_id(message, state)

async def ask_player_id(message: Message, state: FSMContext):
    lang = await db.get_user_language(message.from_user.id)
    await state.set_state(DepositStates.player_id)
    await message.answer(get_text('enter_player_id', lang), reply_markup=ReplyKeyboardRemove())

@router.message(DepositStates.player_id)
async def process_player_id(message: Message, state: FSMContext):
    player_id = message.text.strip()
    if len(player_id) < 2:
        await message.answer("ID слишком короткий.")
        return
    await state.update_data(player_id=player_id)
    data = await state.get_data()
    amount = data['amount']
    unique_sum = generate_unique_sum(amount)
    await state.update_data(unique_sum=unique_sum)
    card = await db.get_setting('card_number')
    lang = await db.get_user_language(message.from_user.id)
    # Показываем реквизиты
    text = get_text('payment_details', lang, card=card, amount=unique_sum, unique=unique_sum-amount)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Оплатил", callback_data="paid_deposit"),
         InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_deposit")]
    ])
    await message.answer(text, reply_markup=kb)
    await state.set_state(DepositStates.confirm_payment)

@router.callback_query(DepositStates.confirm_payment, F.data == "cancel_deposit")
async def cancel_deposit(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    lang = await db.get_user_language(callback.from_user.id)
    await callback.message.edit_text(get_text('payment_cancelled', lang))
    await callback.message.answer(get_text('main_menu', lang))
    await callback.answer()

@router.callback_query(DepositStates.confirm_payment, F.data == "paid_deposit")
async def confirm_paid(callback: CallbackQuery, state: FSMContext):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(DepositStates.screenshot)
    await callback.message.edit_text(get_text('send_screenshot', lang))
    await callback.answer()

@router.message(DepositStates.screenshot, F.photo | F.document)
async def process_screenshot(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    amount = data['amount']
    unique_sum = data['unique_sum']
    player_id = data['player_id']
    user_id = message.from_user.id
    lang = await db.get_user_language(user_id)

    # Получаем file_id
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and message.document.mime_type.startswith('image/'):
        file_id = message.document.file_id
    else:
        await message.answer(get_text('send_screenshot', lang))
        return

    # Создаём заказ
    order_id = await db.create_order(
        user_id=user_id,
        type='deposit',
        amount=amount,
        unique_sum=unique_sum,
        player_id=player_id,
        screenshot_file_id=file_id
    )

    # Отправляем в админ-чат
    admin_text = get_text('admin_new_order', 'ru', 
                          order_id=order_id, type='Пополнение', amount=unique_sum, 
                          player_id=player_id, from_user=f"@{message.from_user.username or message.from_user.full_name}")
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve:{order_id}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{order_id}")]
    ])
    if message.photo:
        msg = await bot.send_photo(config.ADMIN_CHAT_ID, file_id, caption=admin_text, reply_markup=admin_kb)
    else:
        msg = await bot.send_document(config.ADMIN_CHAT_ID, file_id, caption=admin_text, reply_markup=admin_kb)
    await db.set_admin_message_id(order_id, msg.message_id)

    await message.answer(get_text('order_created', lang), reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=get_text('main_menu', lang))]],
        resize_keyboard=True
    ))
    await state.clear()

@router.message(DepositStates.screenshot)
async def invalid_screenshot(message: Message):
    lang = await db.get_user_language(message.from_user.id)
    await message.answer(get_text('send_screenshot', lang))
