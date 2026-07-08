import logging
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
import database as db
from utils.i18n import get_text
from middlewares.throttling import ThrottlingMiddleware
import config

router = Router()
router.callback_query.middleware(ThrottlingMiddleware(rate_limit=1.0))

class WithdrawStates(StatesGroup):
    video_watched = State()
    player_id = State()
    card_number = State()
    confirm_kassa = State()
    screenshot = State()

@router.message(F.text.in_(["💸 Вывести", "💸 Yechib olish"]))
async def start_withdraw(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = await db.get_user_language(user_id)
    if await db.has_active_order(user_id):
        await message.answer("У вас уже есть активный заказ. Дождитесь его завершения.")
        return
    # Показываем видео
    video_file_id = await db.get_setting('withdraw_video')
    if video_file_id:
        await message.answer_video(video_file_id, caption=get_text('withdraw_video', lang))
    else:
        await message.answer(get_text('withdraw_video', lang) + "\n(видео не настроено)")
    await state.set_state(WithdrawStates.video_watched)
    # Кнопка "Понятно, далее"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Понятно, далее", callback_data="video_seen")]])
    await message.answer("После просмотра нажмите кнопку.", reply_markup=kb)

@router.callback_query(WithdrawStates.video_watched, F.data == "video_seen")
async def video_seen(callback: CallbackQuery, state: FSMContext):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(WithdrawStates.player_id)
    await callback.message.edit_text(get_text('withdraw_enter_player', lang))
    await callback.answer()

@router.message(WithdrawStates.player_id)
async def process_withdraw_player(message: Message, state: FSMContext):
    player_id = message.text.strip()
    if len(player_id) < 2:
        await message.answer("Введите корректный ID.")
        return
    await state.update_data(player_id=player_id)
    lang = await db.get_user_language(message.from_user.id)
    await state.set_state(WithdrawStates.card_number)
    await message.answer(get_text('withdraw_enter_card', lang))

@router.message(WithdrawStates.card_number)
async def process_withdraw_card(message: Message, state: FSMContext):
    card = message.text.strip().replace(" ", "")
    if len(card) < 10:
        await message.answer("Введите корректный номер карты.")
        return
    await state.update_data(card_number=card)
    lang = await db.get_user_language(message.from_user.id)
    # Показываем адрес кассы
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправил", callback_data="withdraw_sent"),
         InlineKeyboardButton(text="❌ Отменить", callback_data="withdraw_cancel")]
    ])
    await state.set_state(WithdrawStates.confirm_kassa)
    await message.answer(
        get_text('withdraw_kassa', lang) + "\n" + get_text('withdraw_confirm', lang),
        reply_markup=kb
    )

@router.callback_query(WithdrawStates.confirm_kassa, F.data == "withdraw_cancel")
async def cancel_withdraw(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    lang = await db.get_user_language(callback.from_user.id)
    await callback.message.edit_text("Вывод отменён.")
    await callback.message.answer(get_text('main_menu', lang))
    await callback.answer()

@router.callback_query(WithdrawStates.confirm_kassa, F.data == "withdraw_sent")
async def withdraw_sent(callback: CallbackQuery, state: FSMContext):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(WithdrawStates.screenshot)
    await callback.message.edit_text(get_text('send_screenshot', lang))
    await callback.answer()

@router.message(WithdrawStates.screenshot, F.photo | F.document)
async def process_withdraw_screenshot(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    player_id = data['player_id']
    card_number = data['card_number']
    user_id = message.from_user.id
    lang = await db.get_user_language(user_id)

    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and message.document.mime_type.startswith('image/'):
        file_id = message.document.file_id
    else:
        await message.answer(get_text('send_screenshot', lang))
        return

    # Создаём заказ (сумма может быть не указана, но для вывода можно задать 0 или запросить отдельно)
    # Предположим, что сумма не требуется для вывода, но можно добавить запрос суммы.
    # Для простоты зададим 0.
    order_id = await db.create_order(
        user_id=user_id,
        type='withdraw',
        amount=0,
        unique_sum=None,
        player_id=player_id,
        card_number=card_number,
        screenshot_file_id=file_id
    )

    # Отправляем в админ-чат
    admin_text = f"🆕 Новый заказ #{order_id}\nТип: Вывод\nID: {player_id}\nКарта: {card_number}\nОт: @{message.from_user.username or message.from_user.full_name}"
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

@router.message(WithdrawStates.screenshot)
async def invalid_withdraw_screenshot(message: Message):
    lang = await db.get_user_language(message.from_user.id)
    await message.answer(get_text('send_screenshot', lang))
