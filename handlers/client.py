import logging
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
import database as db
from utils.i18n import get_text
from middlewares.throttling import ThrottlingMiddleware

router = Router()
router.message.middleware(ThrottlingMiddleware(rate_limit=1.0))

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    lang = await db.get_user_language(user_id)
    if not lang:
        # Предлагаем выбрать язык
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🇷🇺 Русский"), KeyboardButton(text="🇺🇿 O'zbekcha")]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.answer("Выберите язык / Tilni tanlang:", reply_markup=kb)
        return
    # Уже есть язык, показываем меню
    await show_main_menu(message, lang)

@router.message(F.text.in_(["🇷🇺 Русский", "🇺🇿 O'zbekcha"]))
async def set_language(message: Message, state: FSMContext):
    lang = 'ru' if message.text == "🇷🇺 Русский" else 'uz'
    await db.set_user_language(message.from_user.id, lang)
    await message.answer(get_text('language_changed', lang), reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=get_text('main_menu', lang))]],
        resize_keyboard=True
    ))
    await show_main_menu(message, lang)

async def show_main_menu(message: Message, lang: str):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text('deposit_button', lang)), KeyboardButton(text=get_text('withdraw_button', lang))],
            [KeyboardButton(text=get_text('support_button', lang))]
        ],
        resize_keyboard=True
    )
    await message.answer(get_text('main_menu', lang), reply_markup=kb)

# Обработчик кнопки "Связь с админом"
@router.message(F.text.in_(["📞 Связь с админом", "📞 Admin bilan bog'lanish"]))
async def support(message: Message):
    user_id = message.from_user.id
    lang = await db.get_user_language(user_id)
    contacts = await db.get_setting('admin_contacts')
    await message.answer(get_text('support_contact', lang, contacts=contacts))

# Остальные кнопки будут обработаны в deposit.py и withdraw.py
