import asyncio
import hashlib
import logging
import random
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    LabeledPrice, Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, PreCheckoutQuery, SuccessfulPayment,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# ===================== КОНФИГУРАЦИЯ =====================
BOT_TOKEN = "8251949164:AAE1fYvR_cMK7PnykcqpCxaXS9vIWxo1VjQ"
ADMIN_USERNAMES = ["hjklgf1"]

REFERRAL_BONUS_PERCENT = 10
REFERRAL_SIGNUP_BONUS = 5
REFERRAL_INVITE_BONUS = 10

# Хранилища данных
users_balance: Dict[int, int] = {}
users_referrer: Dict[int, int] = {}
users_referrals: Dict[int, List[int]] = {}
users_stats: Dict[int, dict] = {}
users_daily_bonus: Dict[int, str] = {}
users_weekly_bonus: Dict[int, str] = {}
users_monthly_bonus: Dict[int, str] = {}
users_last_active: Dict[int, str] = {}
users_warning: Dict[int, int] = {}
users_ban: Dict[int, bool] = {}
users_mute: Dict[int, bool] = {}
pending_payments: Dict[str, dict] = {}
transactions: Dict[int, list] = {}
users_username: Dict[int, str] = {}
users_join_date: Dict[int, str] = {}
blacklist: List[int] = []
promo_codes: Dict[str, dict] = {}
daily_players: Dict[str, int] = {}  # date -> count

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# ===================== FSM =====================
class GameStates(StatesGroup):
    custom_deposit = State()
    admin_find_user = State()
    admin_change_balance = State()
    admin_send_message = State()
    admin_broadcast_photo = State()
    admin_set_warning = State()
    admin_set_promo = State()
    admin_edit_user = State()
    admin_send_global = State()
    dice_game = State()
    mines_game = State()
    pyramid_game = State()
    penalty_game = State()
    three_point_game = State()
    bowl_game = State()


# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
def is_admin(username: str) -> bool:
    return username.lower() in [adm.lower() for adm in ADMIN_USERNAMES]

def is_banned(user_id: int) -> bool:
    return user_id in blacklist

async def get_user_id_by_username(username: str) -> Optional[int]:
    for uid, uname in users_username.items():
        if uname and uname.lower() == username.lower():
            return uid
    return None

def generate_referral_link(user_id: int) -> str:
    code = hashlib.md5(f"starplay_{user_id}_{datetime.now().date()}".encode()).hexdigest()[:8]
    return f"https://t.me/{bot.username}?start=ref_{code}"

def get_user_stats(user_id: int) -> dict:
    if user_id not in users_stats:
        users_stats[user_id] = {
            "games_played": 0, "games_won": 0, "total_won": 0, "total_lost": 0,
            "roulette_wins": 0, "darts_wins": 0, "football_wins": 0,
            "bowling_wins": 0, "basketball_wins": 0, "mines_wins": 0,
            "pyramid_wins": 0, "slots_wins": 0, "penalty_wins": 0,
            "three_point_wins": 0, "bowl_wins": 0
        }
    return users_stats[user_id]

def update_balance(user_id: int, delta: int) -> int:
    if is_banned(user_id):
        return users_balance.get(user_id, 0)
    current = users_balance.get(user_id, 0)
    new_balance = current + delta
    if new_balance < 0:
        new_balance = 0
    users_balance[user_id] = new_balance
    return new_balance

def get_user_balance(user_id: int) -> int:
    return users_balance.get(user_id, 0)

def save_transaction(user_id: int, amount: int, tx_type: str, details: str = ""):
    if user_id not in transactions:
        transactions[user_id] = []
    transactions[user_id].append({
        "amount": amount, "type": tx_type, "details": details,
        "timestamp": datetime.now().isoformat()
    })

def format_stars(amount: int) -> str:
    return f"⭐️ {amount} Stars"

def get_random_emoji() -> str:
    return random.choice(["🎲","🎯","⚡️","💫","🌟","⭐️","✨","🎮","🎰","🔥"])

def generate_promo_code() -> str:
    return hashlib.md5(str(random.randint(1, 999999)).encode()).hexdigest()[:8].upper()


# ===================== ПРАВИЛА ИГР ЧЕРЕЗ DICE =====================
# Все игры используют sendDice с разными эмодзи
# Значения dice: от 1 до 6

DICE_RULES = {
    "🎲": {  # Обычный кубик
        "name": "Кубик",
        "emoji": "🎲",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 3, 6: 5},
        "results": {1: "💀 Ужас!", 2: "😢 Обидно!", 3: "🤔 Неплохо!", 4: "😊 Хорошо!", 5: "😎 Отлично!", 6: "🤯 ДЖЕКПОТ!"}
    },
    "🎯": {  # Дартс
        "name": "Дартс",
        "emoji": "🎯",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 4, 6: 10},
        "results": {1: "💀 Мимо!", 2: "😢 Рядом!", 3: "🤔 В десятку!", 4: "😊 Точный бросок!", 5: "😎 Отличный дротик!", 6: "🤯 ЯБЛОЧКО!"}
    },
    "⚽️": {  # Футбол (пенальти)
        "name": "Пенальти",
        "emoji": "⚽️",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 3, 6: 5},
        "results": {1: "💀 Сейв!", 2: "😢 Мимо ворот!", 3: "🤔 Гол!", 4: "😊 Красивый гол!", 5: "😎 В девятку!", 6: "🤯 ШЕДЕВР!"}
    },
    "🏀": {  # Баскетбол (3-очковый)
        "name": "Трёхочковый",
        "emoji": "🏀",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 4, 6: 6},
        "results": {1: "💀 Промах!", 2: "😢 В кольцо!", 3: "🤔 Попадание!", 4: "😊 Сверху!", 5: "😎 Издали!", 6: "🤯 БАЗЗЕР БИТЕР!"}
    },
    "🎳": {  # Боулинг
        "name": "Боулинг",
        "emoji": "🎳",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 5, 6: 10},
        "results": {1: "💀 Страйк-аут!", 2: "😢 Почти!", 3: "🤔 Спэр!", 4: "😊 Страйк!", 5: "😎 Идеальный!", 6: "🤯 10 СТРАЙКОВ!"}
    }
}


# ===================== КЛАВИАТУРЫ =====================
def get_main_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="💰 Баланс")
    builder.button(text="⭐️ Пополнить")
    builder.button(text="🎮 Игры")
    builder.button(text="👥 Рефералы")
    builder.button(text="🏆 Топ")
    builder.button(text="📊 Профиль")
    builder.button(text="🎁 Ежедневный бонус")
    builder.button(text="🎊 Еженедельный бонус")
    builder.button(text="🌙 Ежемесячный бонус")
    builder.button(text="🎲 Промокод")
    builder.button(text="👑 Админ панель")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_admin_panel_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📊 Статистика бота")
    builder.button(text="💰 Изменить баланс")
    builder.button(text="📢 Сделать рассылку")
    builder.button(text="👥 Список пользователей")
    builder.button(text="📜 Логи транзакций")
    builder.button(text="💾 Сохранить данные")
    builder.button(text="⚠️ Выдать предупреждение")
    builder.button(text="🚫 Забанить пользователя")
    builder.button(text="🔓 Разбанить пользователя")
    builder.button(text="🔇 Замутить пользователя")
    builder.button(text="🔊 Размутить пользователя")
    builder.button(text="🎁 Создать промокод")
    builder.button(text="📊 Активность за день")
    builder.button(text="💰 Топ донатеров")
    builder.button(text="📈 График активности")
    builder.button(text="💾 Загрузить бэкап")
    builder.button(text="🔄 Очистить БД")
    builder.button(text="🔙 В главное меню")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_games_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="🎲 Кубик")
    builder.button(text="🎯 Дартс")
    builder.button(text="⚽️ Пенальти")
    builder.button(text="🏀 Трёхочковый")
    builder.button(text="🎳 Боулинг")
    builder.button(text="🎰 Слоты")
    builder.button(text="💣 Мины")
    builder.button(text="🏛 Пирамида")
    builder.button(text="🔙 Главное меню")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_bet_keyboard(game_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐️ 5", callback_data=f"{game_key}_bet_5"),
         InlineKeyboardButton(text="⭐️ 10", callback_data=f"{game_key}_bet_10"),
         InlineKeyboardButton(text="⭐️ 25", callback_data=f"{game_key}_bet_25")],
        [InlineKeyboardButton(text="⭐️ 50", callback_data=f"{game_key}_bet_50"),
         InlineKeyboardButton(text="⭐️ 100", callback_data=f"{game_key}_bet_100"),
         InlineKeyboardButton(text="⭐️ 250", callback_data=f"{game_key}_bet_250")],
        [InlineKeyboardButton(text="⭐️ 500", callback_data=f"{game_key}_bet_500"),
         InlineKeyboardButton(text="⭐️ 1000", callback_data=f"{game_key}_bet_1000"),
         InlineKeyboardButton(text="⭐️ 2500", callback_data=f"{game_key}_bet_2500")],
        [InlineKeyboardButton(text="◀️ Назад к играм", callback_data="back_to_games")]
    ])

def get_deposit_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐️ 10", callback_data="deposit_10"),
         InlineKeyboardButton(text="⭐️ 50", callback_data="deposit_50"),
         InlineKeyboardButton(text="⭐️ 100", callback_data="deposit_100")],
        [InlineKeyboardButton(text="⭐️ 250", callback_data="deposit_250"),
         InlineKeyboardButton(text="⭐️ 500", callback_data="deposit_500"),
         InlineKeyboardButton(text="⭐️ 1000", callback_data="deposit_1000")],
        [InlineKeyboardButton(text="⭐️ 2500", callback_data="deposit_2500"),
         InlineKeyboardButton(text="⭐️ 5000", callback_data="deposit_5000"),
         InlineKeyboardButton(text="⭐️ 10000", callback_data="deposit_10000")],
        [InlineKeyboardButton(text="✏️ Другая сумма", callback_data="deposit_custom")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])

def get_slots_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Крутить (5⭐️)", callback_data="slots_spin_5"),
         InlineKeyboardButton(text="🎰 Крутить (10⭐️)", callback_data="slots_spin_10")],
        [InlineKeyboardButton(text="🎰 Крутить (25⭐️)", callback_data="slots_spin_25"),
         InlineKeyboardButton(text="🎰 Крутить (50⭐️)", callback_data="slots_spin_50")],
        [InlineKeyboardButton(text="🎰 Крутить (100⭐️)", callback_data="slots_spin_100"),
         InlineKeyboardButton(text="🎰 Крутить (250⭐️)", callback_data="slots_spin_250")],
        [InlineKeyboardButton(text="◀️ Назад к играм", callback_data="back_to_games")]
    ])

def get_mines_board_keyboard(board, revealed, bet, multiplier, cells_opened) -> InlineKeyboardMarkup:
    keyboard = []
    for i in range(5):
        row = []
        for j in range(5):
            if revealed[i][j]:
                emoji = "💣" if board[i][j] == "💣" else "💎"
                text = emoji
            else:
                text = "❓"
            row.append(InlineKeyboardButton(text=text, callback_data=f"mine_{i}_{j}_{bet}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text=f"💰 Забрать {format_stars(int(bet * multiplier))}", callback_data=f"mines_cashout_{bet}")])
    keyboard.append([InlineKeyboardButton(text="◀️ Выйти из игры", callback_data="back_to_games")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_pyramid_keyboard(level: int, current_win: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬆️ Подняться выше (x2)", callback_data="pyramid_up")],
        [InlineKeyboardButton(text=f"💰 Забрать {format_stars(current_win)}", callback_data="pyramid_cashout")],
        [InlineKeyboardButton(text="◀️ Выйти из игры", callback_data="back_to_games")]
    ])


# ===================== ОСНОВНЫЕ КОМАНДЫ =====================
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    
    if is_banned(user_id):
        await message.answer("🚫 Вы забанены в этом боте!")
        return
    
    users_username[user_id] = username
    users_last_active[user_id] = datetime.now().isoformat()
    
    if user_id not in users_join_date:
        users_join_date[user_id] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Реферальная система
    if " " in message.text:
        param = message.text.split()[1]
        if param.startswith("ref_"):
            try:
                referrer_id = int(param[4:])
                if referrer_id != user_id and user_id not in users_referrer:
                    users_referrer[user_id] = referrer_id
                    users_referrals.setdefault(referrer_id, []).append(user_id)
                    update_balance(user_id, REFERRAL_SIGNUP_BONUS)
                    update_balance(referrer_id, REFERRAL_INVITE_BONUS)
                    save_transaction(user_id, REFERRAL_SIGNUP_BONUS, "referral_bonus", f"от {referrer_id}")
                    save_transaction(referrer_id, REFERRAL_INVITE_BONUS, "referral_reward", f"пригласил {user_id}")
                    await message.answer(f"✅ Вы получили {format_stars(REFERRAL_SIGNUP_BONUS)} за регистрацию по ссылке!")
            except:
                pass
    
    welcome_text = (
        f"🌟 <b>Добро пожаловать в StarPlay!</b> 🌟\n\n"
        f"{get_random_emoji()} <b>Играй на Telegram Stars и выигрывай!</b>\n\n"
        f"<b>🎲 Доступные игры:</b>\n"
        f"🎲 Кубик | 🎯 Дартс | ⚽️ Пенальти | 🏀 Трёхочковый | 🎳 Боулинг\n"
        f"🎰 Слоты | 💣 Мины | 🏛 Пирамида\n\n"
        f"<b>💫 Как начать:</b>\n"
        f"1️⃣ Пополни баланс через Telegram Stars\n"
        f"2️⃣ Выбери игру\n"
        f"3️⃣ Делай ставки и выигрывай!\n\n"
        f"🎁 <b>Бонусы:</b>\n"
        f"• Ежедневный бонус\n"
        f"• Еженедельный бонус\n"
        f"• Ежемесячный бонус\n"
        f"• Промокоды\n\n"
        f"👇 <i>Используй кнопки внизу!</i>"
    )
    
    await message.answer(welcome_text, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard())


# ===================== ГЛАВНЫЕ КНОПКИ =====================
@dp.message(F.text == "💰 Баланс")
async def balance_reply(message: Message):
    user_id = message.from_user.id
    if is_banned(user_id):
        await message.answer("🚫 Вы забанены!")
        return
    await message.answer(
        f"💰 <b>Твой баланс:</b> {format_stars(get_user_balance(user_id))}\n\n"
        f"🎮 Приглашай друзей и зарабатывай больше!\n"
        f"👥 Реферальная ссылка: {generate_referral_link(user_id)[:30]}...",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "⭐️ Пополнить")
async def deposit_reply(message: Message):
    user_id = message.from_user.id
    if is_banned(user_id):
        await message.answer("🚫 Вы забанены!")
        return
    await message.answer(
        "⭐️ <b>Пополнение баланса</b>\n\n"
        "Выберите сумму пополнения:\n"
        "💰 Средства зачисляются мгновенно после оплаты!\n"
        "💳 Валюта: Telegram Stars (XTR)",
        parse_mode=ParseMode.HTML,
        reply_markup=get_deposit_keyboard()
    )

@dp.message(F.text == "🎮 Игры")
async def games_reply(message: Message):
    user_id = message.from_user.id
    if is_banned(user_id):
        await message.answer("🚫 Вы забанены!")
        return
    await message.answer(
        "🎮 <b>Выбери игру</b>\n\n"
        "🎲 <b>Кубик</b> — Множители до x5\n"
        "🎯 <b>Дартс</b> — Множители до x10\n"
        "⚽️ <b>Пенальти</b> — Множители до x5\n"
        "🏀 <b>Трёхочковый</b> — Множители до x6\n"
        "🎳 <b>Боулинг</b> — Множители до x10\n"
        "🎰 <b>Слоты</b> — Множители до x50\n"
        "💣 <b>Мины</b> — Множители до x18\n"
        "🏛 <b>Пирамида</b> — Множители до x16\n\n"
        "👇 <i>Нажми на кнопку с игрой!</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )

@dp.message(F.text == "👥 Рефералы")
async def referrals_reply(message: Message):
    user_id = message.from_user.id
    if is_banned(user_id):
        await message.answer("🚫 Вы забанены!")
        return
    
    ref_link = generate_referral_link(user_id)
    ref_count = len(users_referrals.get(user_id, []))
    
    total_earned = 0
    for tx in transactions.get(user_id, []):
        if tx["type"] in ["referral_reward", "referral_earning"]:
            total_earned += tx["amount"]
    
    text = (
        f"👥 <b>Реферальная система</b>\n\n"
        f"🏆 <b>Твоя статистика:</b>\n"
        f"• Приглашено: {ref_count} чел.\n"
        f"• Заработано: {format_stars(total_earned)}\n\n"
        f"<b>📋 Как это работает:</b>\n"
        f"• Друг получает +{REFERRAL_SIGNUP_BONUS} Stars при регистрации\n"
        f"• Ты получаешь +{REFERRAL_INVITE_BONUS} Stars за приглашение\n"
        f"• Ты получаешь {REFERRAL_BONUS_PERCENT}% от пополнений друга\n\n"
        f"<b>🔗 Твоя реферальная ссылка:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"Поделись ссылкой с друзьями и зарабатывай! 🚀"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться ссылкой", url=f"https://t.me/share/url?url={ref_link}&text=StarPlay — играй и зарабатывай Telegram Stars!")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

@dp.message(F.text == "🏆 Топ")
async def top_reply(message: Message):
    user_id = message.from_user.id
    if is_banned(user_id):
        await message.answer("🚫 Вы забанены!")
        return
    
    sorted_users = sorted(users_balance.items(), key=lambda x: x[1], reverse=True)[:15]
    
    if not sorted_users:
        await message.answer("🏆 Пока нет игроков в рейтинге! Будь первым!")
        return
    
    top_text = "🏆 <b>ТОП-15 ИГРОКОВ StarPlay</b> 🏆\n\n"
    for idx, (uid, bal) in enumerate(sorted_users, 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
        uname = users_username.get(uid, str(uid))
        name = f"@{uname}" if uname else str(uid)
        top_text += f"{medal} <b>{name}</b> — {bal} ⭐️\n"
    
    await message.answer(top_text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "📊 Профиль")
async def profile_reply(message: Message):
    uid = message.from_user.id
    if is_banned(uid):
        await message.answer("🚫 Вы забанены!")
        return
    
    stats = get_user_stats(uid)
    wr = (stats['games_won'] / max(stats['games_played'], 1)) * 100
    ref_count = len(users_referrals.get(uid, []))
    
    text = (
        f"👤 <b>Профиль игрока</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👤 Username: @{message.from_user.username or 'нет'}\n"
        f"📅 Регистрация: {users_join_date.get(uid, 'неизвестно')}\n"
        f"⏰ Последняя активность: {users_last_active.get(uid, 'неизвестно')[:16]}\n\n"
        f"💰 <b>Баланс:</b> {format_stars(get_user_balance(uid))}\n\n"
        f"📊 <b>Статистика игр:</b>\n"
        f"├ 🎮 Сыграно: {stats['games_played']}\n"
        f"├ 🏆 Побед: {stats['games_won']}\n"
        f"├ 📈 Винрейт: {wr:.1f}%\n"
        f"├ 💎 Выиграно: {format_stars(stats['total_won'])}\n"
        f"└ 💸 Проиграно: {format_stars(stats['total_lost'])}\n\n"
        f"👥 <b>Рефералов:</b> {ref_count}\n\n"
        f"{get_random_emoji()} Продолжай играть и побеждать!"
    )
    
    await message.answer(text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "🎁 Ежедневный бонус")
async def daily_bonus_reply(message: Message):
    user_id = message.from_user.id
    if is_banned(user_id):
        await message.answer("🚫 Вы забанены!")
        return
    
    today = datetime.now().date().isoformat()
    today_count = daily_players.get(today, 0)
    
    if users_daily_bonus.get(user_id) == today:
        await message.answer(
            f"🎁 <b>Ты уже получил сегодняшний бонус!</b>\n\n"
            f"📊 Сегодня бонус получили: {today_count} игроков\n"
            f"⏰ Возвращайся завтра!",
            parse_mode=ParseMode.HTML
        )
        return
    
    bonus_amount = random.randint(5, 15)
    update_balance(user_id, bonus_amount)
    users_daily_bonus[user_id] = today
    daily_players[today] = today_count + 1
    save_transaction(user_id, bonus_amount, "daily_bonus", "Ежедневный бонус")
    
    await message.answer(
        f"🎉 <b>Ежедневный бонус получен!</b> 🎉\n\n"
        f"+{format_stars(bonus_amount)}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}\n\n"
        f"📊 Сегодня бонус получили: {today_count + 1} игроков",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text == "🎊 Еженедельный бонус")
async def weekly_bonus_reply(message: Message):
    user_id = message.from_user.id
    if is_banned(user_id):
        await message.answer("🚫 Вы забанены!")
        return
    
    week = datetime.now().strftime("%Y-W%W")
    
    if users_weekly_bonus.get(user_id) == week:
        await message.answer(
            f"🎊 <b>Ты уже получил еженедельный бонус!</b>\n\n"
            f"⏰ Возвращайся на следующей неделе!",
            parse_mode=ParseMode.HTML
        )
        return
    
    bonus_amount = random.randint(50, 150)
    update_balance(user_id, bonus_amount)
    users_weekly_bonus[user_id] = week
    save_transaction(user_id, bonus_amount, "weekly_bonus", "Еженедельный бонус")
    
    await message.answer(
        f"🎉 <b>Еженедельный бонус получен!</b> 🎉\n\n"
        f"+{format_stars(bonus_amount)}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text == "🌙 Ежемесячный бонус")
async def monthly_bonus_reply(message: Message):
    user_id = message.from_user.id
    if is_banned(user_id):
        await message.answer("🚫 Вы забанены!")
        return
    
    month = datetime.now().strftime("%Y-%m")
    
    if users_monthly_bonus.get(user_id) == month:
        await message.answer(
            f"🌙 <b>Ты уже получил ежемесячный бонус!</b>\n\n"
            f"⏰ Возвращайся в следующем месяце!",
            parse_mode=ParseMode.HTML
        )
        return
    
    bonus_amount = random.randint(200, 500)
    update_balance(user_id, bonus_amount)
    users_monthly_bonus[user_id] = month
    save_transaction(user_id, bonus_amount, "monthly_bonus", "Ежемесячный бонус")
    
    await message.answer(
        f"🎉 <b>Ежемесячный бонус получен!</b> 🎉\n\n"
        f"+{format_stars(bonus_amount)}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text == "🎲 Промокод")
async def promo_code_reply(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if is_banned(user_id):
        await message.answer("🚫 Вы забанены!")
        return
    
    await state.set_state(GameStates.admin_set_promo)
    await message.answer(
        "🎲 <b>Введите промокод</b>\n\n"
        "Если у вас есть промокод, введите его ниже:\n\n"
        "<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML
    )


# ===================== DICE ИГРЫ (sendDice) =====================
async def play_dice_game(message: Message, game_key: str, bet: int, state: FSMContext):
    """Универсальная функция для запуска dice игры через sendDice"""
    user_id = message.from_user.id
    
    if is_banned(user_id):
        await message.answer("🚫 Вы забанены!")
        return
    
    if get_user_balance(user_id) < bet:
        await message.answer(f"❌ Не хватает {format_stars(bet)}")
        return
    
    game = DICE_RULES[game_key]
    
    update_balance(user_id, -bet)
    
    # Отправляем dice через sendDice
    dice_message = await message.answer_dice(emoji=game["emoji"])
    dice_value = dice_message.dice.value
    
    multiplier = game["multipliers"].get(dice_value, 0)
    result_message = game["results"].get(dice_value, "🎲 Игра завершена!")
    
    if multiplier > 0:
        win_amount = bet * multiplier
        update_balance(user_id, win_amount)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["total_won"] += win_amount
        
        if game_key == "🎲":
            stats["roulette_wins"] += 1
        elif game_key == "🎯":
            stats["darts_wins"] += 1
        elif game_key == "⚽️":
            stats["penalty_wins"] += 1
        elif game_key == "🏀":
            stats["three_point_wins"] += 1
        elif game_key == "🎳":
            stats["bowl_wins"] += 1
            
        save_transaction(user_id, win_amount, "game_win", f"{game['name']} x{multiplier}")
        
        await message.answer(
            f"{game['emoji']} <b>{game['name']}</b>\n\n"
            f"🎲 <b>Результат: {dice_value}</b>\n"
            f"{result_message}\n\n"
            f"💰 Ставка: {format_stars(bet)}\n"
            f"✨ Множитель: x{multiplier}\n"
            f"🏆 Выигрыш: +{format_stars(win_amount)}\n\n"
            f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_games_keyboard()
        )
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", game['name'])
        
        await message.answer(
            f"{game['emoji']} <b>{game['name']}</b>\n\n"
            f"🎲 <b>Результат: {dice_value}</b>\n"
            f"{result_message}\n\n"
            f"💰 Ставка: {format_stars(bet)}\n"
            f"😢 <b>Проигрыш</b>\n\n"
            f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_games_keyboard()
        )


# ---------- КАЖДАЯ ИГРА ПОЛУЧАЕТ СВОЙ ОБРАБОТЧИК ----------
@dp.message(F.text == "🎲 Кубик")
async def cube_start(message: Message):
    await message.answer(
        "🎲 <b>Игра КУБИК</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "Бросай кубик и получай множители:\n"
        "• 1-2 → проигрыш\n"
        "• 3 → x1\n"
        "• 4 → x2\n"
        "• 5 → x3\n"
        "• 6 → x5\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("dice")
    )

@dp.callback_query(F.data.startswith("dice_bet_"))
async def cube_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if is_banned(user_id):
        await callback.answer("🚫 Вы забанены!", show_alert=True)
        return
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    await callback.message.delete()
    await play_dice_game(callback.message, "🎲", bet, state)
    await callback.answer()

@dp.message(F.text == "🎯 Дартс")
async def darts_start(message: Message):
    await message.answer(
        "🎯 <b>Игра ДАРТС</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "Попади в цель и получи множители:\n"
        "• 1-2 → мимо\n"
        "• 3 → x1\n"
        "• 4 → x2\n"
        "• 5 → x4\n"
        "• 6 → ЯБЛОЧКО! x10\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("darts")
    )

@dp.callback_query(F.data.startswith("darts_bet_"))
async def darts_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if is_banned(user_id):
        await callback.answer("🚫 Вы забанены!", show_alert=True)
        return
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    await callback.message.delete()
    await play_dice_game(callback.message, "🎯", bet, state)
    await callback.answer()

@dp.message(F.text == "⚽️ Пенальти")
async def penalty_start(message: Message):
    await message.answer(
        "⚽️ <b>Игра ПЕНАЛЬТИ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "Пробей пенальти и получи множители:\n"
        "• 1-2 → сейв вратаря\n"
        "• 3 → гол x1\n"
        "• 4 → гол с рикошетом x2\n"
        "• 5 → красивый гол x3\n"
        "• 6 → ШЕДЕВР! x5\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("penalty")
    )

@dp.callback_query(F.data.startswith("penalty_bet_"))
async def penalty_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if is_banned(user_id):
        await callback.answer("🚫 Вы забанены!", show_alert=True)
        return
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    await callback.message.delete()
    await play_dice_game(callback.message, "⚽️", bet, state)
    await callback.answer()

@dp.message(F.text == "🏀 Трёхочковый")
async def three_point_start(message: Message):
    await message.answer(
        "🏀 <b>Игра ТРЁХОЧКОВЫЙ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "Брось трёхочковый и получи множители:\n"
        "• 1-2 → промах\n"
        "• 3 → попадание x1\n"
        "• 4 → сверху x2\n"
        "• 5 → издали x4\n"
        "• 6 → БАЗЗЕР БИТЕР! x6\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("three")
    )

@dp.callback_query(F.data.startswith("three_bet_"))
async def three_point_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if is_banned(user_id):
        await callback.answer("🚫 Вы забанены!", show_alert=True)
        return
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    await callback.message.delete()
    await play_dice_game(callback.message, "🏀", bet, state)
    await callback.answer()

@dp.message(F.text == "🎳 Боулинг")
async def bowling_start(message: Message):
    await message.answer(
        "🎳 <b>Игра БОУЛИНГ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "Брось шар и получи множители:\n"
        "• 1-2 → страйк-аут\n"
        "• 3 → спэр x1\n"
        "• 4 → страйк x2\n"
        "• 5 → идеальный x5\n"
        "• 6 → 10 СТРАЙКОВ! x10\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("bowl")
    )

@dp.callback_query(F.data.startswith("bowl_bet_"))
async def bowling_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if is_banned(user_id):
        await callback.answer("🚫 Вы забанены!", show_alert=True)
        return
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    await callback.message.delete()
    await play_dice_game(callback.message, "🎳", bet, state)
    await callback.answer()


# ---------- СЛОТЫ ----------
SLOT_SYMBOLS = ["🍒", "🍊", "🍋", "💎", "7️⃣", "🎰", "⭐️", "💫"]
SLOT_PAYOUTS = {
    ("🍒", "🍒", "🍒"): 5, ("🍊", "🍊", "🍊"): 7, ("🍋", "🍋", "🍋"): 10,
    ("💎", "💎", "💎"): 15, ("7️⃣", "7️⃣", "7️⃣"): 25, ("🎰", "🎰", "🎰"): 50,
    ("⭐️", "⭐️", "⭐️"): 30, ("💫", "💫", "💫"): 20
}

@dp.message(F.text == "🎰 Слоты")
async def slots_start(message: Message):
    await message.answer(
        "🎰 <b>СЛОТЫ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "Собери комбинацию и получи множители:\n"
        "• 🍒🍒🍒 → x5\n"
        "• 🍊🍊🍊 → x7\n"
        "• 🍋🍋🍋 → x10\n"
        "• 💎💎💎 → x15\n"
        "• 7️⃣7️⃣7️⃣ → x25\n"
        "• 🎰🎰🎰 → ДЖЕКПОТ x50!\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_slots_keyboard()
    )

@dp.callback_query(F.data.startswith("slots_spin_"))
async def slots_spin(callback: CallbackQuery):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if is_banned(user_id):
        await callback.answer("🚫 Вы забанены!", show_alert=True)
        return
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    
    reel1 = random.choice(SLOT_SYMBOLS)
    reel2 = random.choice(SLOT_SYMBOLS)
    reel3 = random.choice(SLOT_SYMBOLS)
    combo = (reel1, reel2, reel3)
    
    if combo in SLOT_PAYOUTS:
        mult = SLOT_PAYOUTS[combo]
        win = bet * mult
        update_balance(user_id, win)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["slots_wins"] += 1
        stats["total_won"] += win
        save_transaction(user_id, win, "game_win", f"Слоты x{mult}")
        res = f"🎉 <b>ДЖЕКПОТ!</b> x{mult}\n+{format_stars(win)}"
    elif reel1 == reel2 or reel1 == reel3 or reel2 == reel3:
        win = int(bet * 1.5)
        update_balance(user_id, win)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_won"] += win
        save_transaction(user_id, win, "game_win", f"Слоты пара")
        res = f"🎉 <b>ПАРА!</b> x1.5\n+{format_stars(win)}"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", "Слоты")
        res = f"😢 <b>Не повезло...</b>\n-{format_stars(bet)}"
    
    await callback.message.edit_text(
        f"🎰 <b>СЛОТЫ</b>\n\n"
        f"┌─────┬─────┬─────┐\n"
        f"│  {reel1}  │  {reel2}  │  {reel3}  │\n"
        f"└─────┴─────┴─────┘\n\n"
        f"💰 Ставка: {format_stars(bet)}\n\n"
        f"{res}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_slots_keyboard()
    )
    await callback.answer()


# ---------- МИНЫ ----------
active_mines_games: Dict[int, dict] = {}

@dp.message(F.text == "💣 Мины")
async def mines_start(message: Message):
    await message.answer(
        "💣 <b>МИНЫ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "Поле 5x5, скрыто 5 мин.\n"
        "• 💎 → увеличивает множитель x1.2\n"
        "• 💣 → мгновенный проигрыш\n"
        "• Максимальный множитель: x18\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("mines")
    )

@dp.callback_query(F.data.startswith("mines_bet_"))
async def mines_init(callback: CallbackQuery):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if is_banned(user_id):
        await callback.answer("🚫 Вы забанены!", show_alert=True)
        return
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    
    board = [["💎" for _ in range(5)] for _ in range(5)]
    mines_placed = 0
    while mines_placed < 5:
        x, y = random.randint(0, 4), random.randint(0, 4)
        if board[x][y] == "💎":
            board[x][y] = "💣"
            mines_placed += 1
    
    active_mines_games[user_id] = {
        "board": board,
        "revealed": [[False] * 5 for _ in range(5)],
        "bet": bet,
        "multiplier": 1.0,
        "cells_opened": 0
    }
    
    await callback.message.edit_text(
        f"💣 <b>МИНЫ</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"✨ Множитель: x{active_mines_games[user_id]['multiplier']:.1f}\n"
        f"📦 Открыто клеток: 0/20\n\n"
        f"👇 <b>Открывай 💎 и избегай 💣!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_mines_board_keyboard(board, active_mines_games[user_id]["revealed"], bet, 1.0, 0)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("mine_"))
async def mines_reveal(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    if is_banned(user_id):
        await callback.answer("🚫 Вы забанены!", show_alert=True)
        return
    
    if user_id not in active_mines_games:
        await callback.answer("Игра не найдена! Начни новую.", show_alert=True)
        return
    
    game = active_mines_games[user_id]
    parts = callback.data.split("_")
    x, y = int(parts[1]), int(parts[2])
    
    if game["revealed"][x][y]:
        await callback.answer("Эта клетка уже открыта!", show_alert=True)
        return
    
    game["revealed"][x][y] = True
    
    if game["board"][x][y] == "💣":
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += game["bet"]
        save_transaction(user_id, -game["bet"], "game_loss", "Мины")
        del active_mines_games[user_id]
        
        await callback.message.edit_text(
            f"💣 <b>МИНЫ</b>\n\n"
            f"💥 <b>БАХ! Ты наступил на мину!</b>\n\n"
            f"💰 Ставка: {format_stars(game['bet'])} — ПРОИГРАНА\n"
            f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_games_keyboard()
        )
    else:
        game["cells_opened"] += 1
        game["multiplier"] *= 1.2
        
        current_win = int(game["bet"] * game["multiplier"])
        
        await callback.message.edit_text(
            f"💣 <b>МИНЫ</b>\n\n"
            f"💰 Ставка: {format_stars(game['bet'])}\n"
            f"✨ Множитель: x{game['multiplier']:.1f}\n"
            f"💎 Найдено: {game['cells_opened']}/20\n"
            f"💰 Текущий выигрыш: {format_stars(current_win)}\n\n"
            f"✅ <b>Ты нашёл 💎! Множитель увеличен!</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_mines_board_keyboard(game["board"], game["revealed"], game["bet"], game["multiplier"], game["cells_opened"])
        )
        
        if game["cells_opened"] >= 20:
            win = int(game["bet"] * game["multiplier"])
            update_balance(user_id, win)
            stats = get_user_stats(user_id)
            stats["games_played"] += 1
            stats["games_won"] += 1
            stats["mines_wins"] += 1
            stats["total_won"] += win
            save_transaction(user_id, win, "game_win", f"Мины победа x{game['multiplier']:.1f}")
            del active_mines_games[user_id]
            
            await callback.message.edit_text(
                f"💣 <b>МИНЫ</b>\n\n"
                f"🎉 <b>ПОБЕДА!</b> Ты очистил всё поле! 🎉\n\n"
                f"📦 Открыто: 20/20\n"
                f"✨ Множитель: x{game['multiplier']:.1f}\n"
                f"🏆 Выигрыш: {format_stars(win)}\n"
                f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_games_keyboard()
            )
    
    await callback.answer()

@dp.callback_query(F.data.startswith("mines_cashout_"))
async def mines_cashout(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_mines_games:
        await callback.answer("Нет активной игры!", show_alert=True)
        return
    
    game = active_mines_games[user_id]
    win = int(game["bet"] * game["multiplier"])
    update_balance(user_id, win)
    stats = get_user_stats(user_id)
    stats["games_played"] += 1
    stats["games_won"] += 1
    stats["mines_wins"] += 1
    stats["total_won"] += win
    save_transaction(user_id, win, "game_win", f"Мины кэшаут x{game['multiplier']:.1f}")
    del active_mines_games[user_id]
    
    await callback.message.edit_text(
        f"💣 <b>МИНЫ</b>\n\n"
        f"💰 <b>Ты забрал выигрыш!</b> 💰\n\n"
        f"📦 Открыто: {game['cells_opened']}/20\n"
        f"✨ Множитель: x{game['multiplier']:.1f}\n"
        f"🏆 Выигрыш: {format_stars(win)}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()


# ---------- ПИРАМИДА ----------
active_pyramids: Dict[int, dict] = {}

@dp.message(F.text == "🏛 Пирамида")
async def pyramid_start(message: Message):
    await message.answer(
        "🏛 <b>ПИРАМИДА</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "У тебя есть 5 уровней.\n"
        "• Каждый шаг удваивает выигрыш\n"
        "• Шанс успеха: 50%\n"
        "• На 5 уровне множитель x16!\n\n"
        "Выбери начальную ставку:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("pyramid")
    )

@dp.callback_query(F.data.startswith("pyramid_bet_"))
async def pyramid_init(callback: CallbackQuery):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if is_banned(user_id):
        await callback.answer("🚫 Вы забанены!", show_alert=True)
        return
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    
    active_pyramids[user_id] = {
        "bet": bet,
        "level": 1,
        "current": bet,
        "max_level": 5
    }
    
    await callback.message.edit_text(
        f"🏛 <b>ПИРАМИДА</b>\n\n"
        f"🏆 <b>Уровень 1 / 5</b>\n\n"
        f"💰 Текущий выигрыш: {format_stars(bet)}\n"
        f"🎯 Следующий уровень: {format_stars(bet * 2)}\n"
        f"📊 Шанс успеха: 50%\n\n"
        f"👇 <b>Поднимешься выше или заберёшь выигрыш?</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_pyramid_keyboard(1, bet)
    )
    await callback.answer()

@dp.callback_query(F.data == "pyramid_up")
async def pyramid_up(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_pyramids:
        await callback.answer("Нет активной игры!", show_alert=True)
        return
    
    game = active_pyramids[user_id]
    
    if random.random() < 0.5:
        game["level"] += 1
        game["current"] *= 2
        
        if game["level"] >= 5:
            update_balance(user_id, game["current"])
            stats = get_user_stats(user_id)
            stats["games_played"] += 1
            stats["games_won"] += 1
            stats["pyramid_wins"] += 1
            stats["total_won"] += game["current"]
            save_transaction(user_id, game["current"], "game_win", f"Пирамида победа")
            del active_pyramids[user_id]
            
            await callback.message.edit_text(
                f"🏛 <b>ПИРАМИДА - ПОБЕДА!</b>\n\n"
                f"🎉 <b>Ты покорил вершину!</b> 🎉\n\n"
                f"🏆 Уровень: {game['level']}/5\n"
                f"💰 Выигрыш: {format_stars(game['current'])}\n"
                f"✨ Множитель: x{game['current'] // game['bet']}\n\n"
                f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_games_keyboard()
            )
        else:
            await callback.message.edit_text(
                f"🏛 <b>ПИРАМИДА</b>\n\n"
                f"✅ <b>УСПЕХ!</b> Ты поднялся на уровень {game['level']}!\n\n"
                f"🏆 Уровень {game['level']} / 5\n"
                f"💰 Текущий выигрыш: {format_stars(game['current'])}\n"
                f"🎯 Следующий уровень: {format_stars(game['current'] * 2)}\n"
                f"📊 Шанс успеха: 50%\n\n"
                f"👇 <b>Продолжим подъём?</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_pyramid_keyboard(game["level"], game["current"])
            )
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += game["bet"]
        save_transaction(user_id, -game["bet"], "game_loss", f"Пирамида уровень {game['level']}")
        del active_pyramids[user_id]
        
        await callback.message.edit_text(
            f"🏛 <b>ПИРАМИДА - ПРОИГРЫШ</b>\n\n"
            f"💔 <b>Ты рухнул вниз!</b>\n\n"
            f"💰 Ставка: {format_stars(game['bet'])} — ПРОИГРАНА\n"
            f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_games_keyboard()
        )
    
    await callback.answer()

@dp.callback_query(F.data == "pyramid_cashout")
async def pyramid_cashout(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_pyramids:
        await callback.answer("Нет активной игры!", show_alert=True)
        return
    
    game = active_pyramids[user_id]
    win = game["current"]
    update_balance(user_id, win)
    stats = get_user_stats(user_id)
    stats["games_played"] += 1
    stats["games_won"] += 1
    stats["pyramid_wins"] += 1
    stats["total_won"] += win
    save_transaction(user_id, win, "game_win", f"Пирамида кэшаут x{win // game['bet']}")
    del active_pyramids[user_id]
    
    await callback.message.edit_text(
        f"🏛 <b>ПИРАМИДА</b>\n\n"
        f"💰 <b>Ты забрал выигрыш!</b> 💰\n\n"
        f"🏆 Пройдено уровней: {game['level']}/5\n"
        f"✨ Множитель: x{win // game['bet']}\n"
        f"🏆 Выигрыш: {format_stars(win)}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()


# ===================== АДМИН-ПАНЕЛЬ (20+ ФУНКЦИЙ) =====================
@dp.message(F.text == "👑 Админ панель")
async def admin_panel_reply(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ У вас нет доступа к админ-панели!", reply_markup=get_main_keyboard())
        return
    
    await message.answer(
        "👑 <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n\n"
        "📊 <b>Доступные действия (20+):</b>\n\n"
        "• Статистика бота\n"
        "• Изменение баланса\n"
        "• Рассылка сообщений\n"
        "• Список пользователей\n"
        "• Логи транзакций\n"
        "• Сохранение данных\n"
        "• Выдача предупреждений\n"
        "• Бан/Разбан пользователей\n"
        "• Мут/Размут пользователей\n"
        "• Создание промокодов\n"
        "• Статистика активности\n"
        "• Топ донатеров\n"
        "• График активности\n"
        "• Загрузка/очистка БД\n\n"
        "👇 <b>Выберите действие:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard()
    )

@dp.message(F.text == "📊 Статистика бота")
async def admin_stats_reply(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    total_users = len(users_balance)
    total_balance = sum(users_balance.values())
    total_games = sum(s["games_played"] for s in users_stats.values())
    total_wins = sum(s["games_won"] for s in users_stats.values())
    total_deposits = sum(1 for tx_list in transactions.values() for tx in tx_list if tx["type"] == "deposit")
    deposit_sum = sum(tx["amount"] for tx_list in transactions.values() for tx in tx_list if tx["type"] == "deposit")
    banned_count = len(blacklist)
    promo_count = len(promo_codes)
    today = datetime.now().date().isoformat()
    daily_active = daily_players.get(today, 0)
    
    text = (
        f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
        f"👥 <b>Пользователей:</b> {total_users}\n"
        f"🚫 <b>Забанено:</b> {banned_count}\n"
        f"📊 <b>Активных сегодня:</b> {daily_active}\n"
        f"💰 <b>Общий баланс:</b> {format_stars(total_balance)}\n"
        f"🎮 <b>Всего игр:</b> {total_games}\n"
        f"🏆 <b>Всего побед:</b> {total_wins}\n"
    )
    if total_games > 0:
        text += f"📈 <b>Общий винрейт:</b> {(total_wins/total_games*100):.1f}%\n"
    text += (
        f"💸 <b>Пополнений:</b> {total_deposits}\n"
        f"💸 <b>Сумма пополнений:</b> {format_stars(deposit_sum)}\n"
        f"🎁 <b>Активных промокодов:</b> {promo_count}\n"
    )
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "💰 Изменить баланс")
async def admin_change_balance_reply(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_find_user)
    await message.answer(
        "💰 <b>ИЗМЕНЕНИЕ БАЛАНСА</b>\n\n"
        "Введи username игрока (без @) или ID:\n"
        "Пример: <code>hjklgf1</code> или <code>123456789</code>\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(F.text == "📢 Сделать рассылку")
async def admin_broadcast_reply(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_send_message)
    await message.answer(
        "📢 <b>РАССЫЛКА</b>\n\n"
        "Отправь сообщение для рассылки всем пользователям.\n"
        "Поддерживается: текст, фото, видео, документы.\n\n"
        "<b>Внимание!</b> Рассылка придёт ВСЕМ пользователям!\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(F.text == "👥 Список пользователей")
async def admin_users_list(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    users_list = []
    for uid, uname in users_username.items():
        balance = get_user_balance(uid)
        banned = "🚫" if uid in blacklist else "✅"
        users_list.append(f"{banned} @{uname or str(uid)} — {balance}⭐️")
    
    if not users_list:
        text = "👥 Пользователей пока нет"
    else:
        text = "👥 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ</b>\n\n" + "\n".join(users_list[:50])
        if len(users_list) > 50:
            text += f"\n\n... и ещё {len(users_list)-50} пользователей"
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "📜 Логи транзакций")
async def admin_logs(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    all_txs = []
    for uid, tx_list in transactions.items():
        uname = users_username.get(uid, str(uid))
        for tx in tx_list[-3:]:
            all_txs.append((tx["timestamp"], f"@{uname}: {tx['type']} {tx['amount']}⭐️ - {tx['details']}"))
    
    all_txs.sort(reverse=True)
    recent = all_txs[:30]
    
    if not recent:
        text = "📜 Логов транзакций пока нет"
    else:
        text = "📜 <b>ПОСЛЕДНИЕ ТРАНЗАКЦИИ</b>\n\n" + "\n".join([f"• {tx[1]}" for tx in recent])
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "💾 Сохранить данные")
async def admin_save(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    data = {
        "balance": users_balance,
        "referrer": users_referrer,
        "referrals": users_referrals,
        "stats": users_stats,
        "transactions": transactions,
        "username": users_username,
        "join_date": users_join_date,
        "blacklist": blacklist,
        "promo_codes": promo_codes
    }
    
    try:
        with open("backup.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        await message.answer(
            "✅ <b>Данные успешно сохранены!</b>\n\n"
            "📁 Файл: backup.json\n"
            "💾 Размер: " + str(len(json.dumps(data))) + " байт",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "⚠️ Выдать предупреждение")
async def admin_set_warning(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_set_warning)
    await message.answer(
        "⚠️ <b>ВЫДАЧА ПРЕДУПРЕЖДЕНИЯ</b>\n\n"
        "Введи username пользователя (без @):\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(F.text == "🚫 Забанить пользователя")
async def admin_ban_user(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_edit_user)
    await state.update_data(admin_action="ban")
    await message.answer(
        "🚫 <b>БАН ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введи username пользователя (без @) для бана:\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(F.text == "🔓 Разбанить пользователя")
async def admin_unban_user(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_edit_user)
    await state.update_data(admin_action="unban")
    await message.answer(
        "🔓 <b>РАЗБАН ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введи username пользователя (без @) для разбана:\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(F.text == "🔇 Замутить пользователя")
async def admin_mute_user(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_edit_user)
    await state.update_data(admin_action="mute")
    await message.answer(
        "🔇 <b>МУТ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введи username пользователя (без @) для мута:\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(F.text == "🔊 Размутить пользователя")
async def admin_unmute_user(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_edit_user)
    await state.update_data(admin_action="unmute")
    await message.answer(
        "🔊 <b>РАЗМУТ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введи username пользователя (без @) для размута:\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(F.text == "🎁 Создать промокод")
async def admin_create_promo(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_set_promo)
    await message.answer(
        "🎁 <b>СОЗДАНИЕ ПРОМОКОДА</b>\n\n"
        "Введи сумму для промокода (например: 100):\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(F.text == "📊 Активность за день")
async def admin_daily_activity(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    today = datetime.now().date().isoformat()
    today_count = daily_players.get(today, 0)
    
    # Последние 7 дней
    week_stats = ""
    for i in range(7):
        date = (datetime.now().date() - timedelta(days=i)).isoformat()
        count = daily_players.get(date, 0)
        bar = "█" * min(count // 10, 20)
        week_stats += f"📅 {date}: {bar} {count}\n"
    
    text = (
        f"📊 <b>АКТИВНОСТЬ ЗА ДЕНЬ</b>\n\n"
        f"🎁 Сегодня бонус получили: {today_count} игроков\n\n"
        f"📈 <b>Статистика за неделю:</b>\n{week_stats}"
    )
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "💰 Топ донатеров")
async def admin_top_donators(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    # Собираем сумму пополнений по пользователям
    donators = {}
    for uid, tx_list in transactions.items():
        total_deposit = sum(tx["amount"] for tx in tx_list if tx["type"] == "deposit")
        if total_deposit > 0:
            donators[uid] = total_deposit
    
    sorted_donators = sorted(donators.items(), key=lambda x: x[1], reverse=True)[:15]
    
    if not sorted_donators:
        text = "💰 Пока нет донатеров"
    else:
        text = "💰 <b>ТОП ДОНАТЕРОВ</b>\n\n"
        for idx, (uid, amount) in enumerate(sorted_donators, 1):
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
            uname = users_username.get(uid, str(uid))
            text += f"{medal} @{uname} — {format_stars(amount)}\n"
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "📈 График активности")
async def admin_activity_chart(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    # Генерация текстового графика
    chart = "📈 <b>ГРАФИК АКТИВНОСТИ</b>\n\n"
    for i in range(30):
        date = (datetime.now().date() - timedelta(days=i)).isoformat()
        count = daily_players.get(date, 0)
        bar = "█" * min(count, 50)
        chart += f"📅 {date[:10]}: {bar} ({count})\n"
    
    await message.answer(chart[:4000], parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "💾 Загрузить бэкап")
async def admin_load_backup(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    try:
        with open("backup.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Восстановление данных
        users_balance.update(data.get("balance", {}))
        users_referrer.update(data.get("referrer", {}))
        users_referrals.update(data.get("referrals", {}))
        users_stats.update(data.get("stats", {}))
        transactions.update(data.get("transactions", {}))
        users_username.update(data.get("username", {}))
        users_join_date.update(data.get("join_date", {}))
        
        await message.answer(
            "✅ <b>Бэкап успешно загружен!</b>\n\n"
            "📁 Файл: backup.json\n"
            "📊 Данные восстановлены!",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка загрузки: {e}", reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "🔄 Очистить БД")
async def admin_clear_db(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    # Создаём подтверждение
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ДА, ОЧИСТИТЬ", callback_data="admin_clear_confirm")],
        [InlineKeyboardButton(text="❌ НЕТ, ОТМЕНА", callback_data="admin_clear_cancel")]
    ])
    
    await message.answer(
        "⚠️ <b>ПРЕДУПРЕЖДЕНИЕ!</b>\n\n"
        "Вы уверены, что хотите очистить БД?\n"
        "Это действие НЕОБРАТИМО!\n\n"
        "Будут удалены:\n"
        "• Все пользователи\n"
        "• Все балансы\n"
        "• Все транзакции\n"
        "• Вся статистика\n\n"
        "Подтвердите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

@dp.callback_query(F.data == "admin_clear_confirm")
async def admin_clear_confirm(callback: CallbackQuery):
    username = callback.from_user.username or ""
    if not is_admin(username):
        await callback.answer("Нет доступа!", show_alert=True)
        return
    
    # Очистка всех данных
    users_balance.clear()
    users_referrer.clear()
    users_referrals.clear()
    users_stats.clear()
    users_daily_bonus.clear()
    transactions.clear()
    users_username.clear()
    users_join_date.clear()
    blacklist.clear()
    promo_codes.clear()
    daily_players.clear()
    
    await callback.message.edit_text(
        "✅ <b>БАЗА ДАННЫХ ОЧИЩЕНА!</b>\n\n"
        "Все данные удалены.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_clear_cancel")
async def admin_clear_cancel(callback: CallbackQuery):
    await callback.message.edit_text(
        "❌ Очистка БД отменена.",
        reply_markup=get_admin_panel_keyboard()
    )
    await callback.answer()

@dp.message(F.text == "🔙 В главное меню")
async def back_to_main_from_admin(message: Message):
    await message.answer(
        "🌟 <b>Главное меню</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )


# ===================== АДМИН FSM ОБРАБОТЧИКИ =====================
@dp.message(GameStates.admin_find_user)
async def admin_find_user(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await state.clear()
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Операция отменена.", reply_markup=get_admin_panel_keyboard())
        return
    
    input_text = message.text.strip().replace("@", "")
    user_id = await get_user_id_by_username(input_text)
    
    if not user_id:
        try:
            user_id = int(input_text)
        except:
            pass
    
    if not user_id or user_id not in users_balance:
        await message.answer("❌ Пользователь не найден! Попробуйте другой username или ID.")
        return
    
    await state.update_data(admin_target_user=user_id, admin_target_username=input_text)
    await state.set_state(GameStates.admin_change_balance)
    
    current_balance = get_user_balance(user_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ +100", callback_data="admin_add_100"),
         InlineKeyboardButton(text="➕ +500", callback_data="admin_add_500")],
        [InlineKeyboardButton(text="➕ +1000", callback_data="admin_add_1000"),
         InlineKeyboardButton(text="➕ +5000", callback_data="admin_add_5000")],
        [InlineKeyboardButton(text="➖ -100", callback_data="admin_remove_100"),
         InlineKeyboardButton(text="➖ -500", callback_data="admin_remove_500")],
        [InlineKeyboardButton(text="➖ -1000", callback_data="admin_remove_1000"),
         InlineKeyboardButton(text="➖ -5000", callback_data="admin_remove_5000")],
        [InlineKeyboardButton(text="✏️ Своя сумма", callback_data="admin_custom")],
        [InlineKeyboardButton(text="◀️ Назад в админ-панель", callback_data="admin_back_to_panel")]
    ])
    
    await message.answer(
        f"💰 <b>ИЗМЕНЕНИЕ БАЛАНСА</b>\n\n"
        f"👤 Пользователь: @{input_text}\n"
        f"💰 Текущий баланс: {format_stars(current_balance)}\n\n"
        f"👇 <b>Выберите действие:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

@dp.callback_query(F.data.startswith("admin_"))
async def admin_balance_action(callback: CallbackQuery, state: FSMContext):
    username = callback.from_user.username or ""
    if not is_admin(username):
        await callback.answer("Нет доступа!", show_alert=True)
        return
    
    data = await state.get_data()
    target_user = data.get("admin_target_user")
    target_username = data.get("admin_target_username")
    
    if not target_user:
        await callback.answer("Ошибка: пользователь не найден", show_alert=True)
        await state.clear()
        return
    
    if callback.data == "admin_custom":
        await state.set_state(GameStates.admin_change_balance)
        await callback.message.answer(
            "✏️ <b>Введи сумму</b> (можно с минусом для снятия):\n\n"
            "Примеры:\n"
            "<code>500</code> — добавить 500 Stars\n"
            "<code>-200</code> — снять 200 Stars\n\n"
            "<i>Для отмены отправь /cancel</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
        )
        await callback.answer()
        return
    
    if callback.data == "admin_back_to_panel":
        await state.clear()
        await callback.message.edit_text(
            "👑 <b>Панель администратора</b>\n\nВыберите действие:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )
        await callback.answer()
        return
    
    parts = callback.data.split("_")
    action = parts[1]
    amount = int(parts[2])
    
    if action == "add":
        new_balance = update_balance(target_user, amount)
        save_transaction(target_user, amount, "admin_add", f"Админ добавил {amount} Stars")
        await bot.send_message(
            target_user,
            f"👑 <b>Администратор изменил ваш баланс!</b>\n\n"
            f"+{format_stars(amount)}\n"
            f"💰 Новый баланс: {format_stars(new_balance)}",
            parse_mode=ParseMode.HTML
        )
        result_text = f"✅ Добавлено +{format_stars(amount)} пользователю @{target_username}"
    else:
        new_balance = update_balance(target_user, -amount)
        save_transaction(target_user, -amount, "admin_remove", f"Админ забрал {amount} Stars")
        await bot.send_message(
            target_user,
            f"👑 <b>Администратор изменил ваш баланс!</b>\n\n"
            f"-{format_stars(amount)}\n"
            f"💰 Новый баланс: {format_stars(new_balance)}",
            parse_mode=ParseMode.HTML
        )
        result_text = f"✅ Снято -{format_stars(amount)} у @{target_username}"
    
    await state.clear()
    await callback.message.edit_text(
        f"{result_text}\n\n💰 Новый баланс пользователя: {format_stars(get_user_balance(target_user))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard()
    )
    await callback.answer()

@dp.message(GameStates.admin_change_balance)
async def admin_custom_balance(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await state.clear()
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Операция отменена.", reply_markup=get_admin_panel_keyboard())
        return
    
    data = await state.get_data()
    target_user = data.get("admin_target_user")
    target_username = data.get("admin_target_username")
    
    if not target_user:
        await state.clear()
        await message.answer("❌ Ошибка: пользователь не найден", reply_markup=get_admin_panel_keyboard())
        return
    
    try:
        amount = int(message.text.strip())
        new_balance = update_balance(target_user, amount)
        tx_type = "admin_add" if amount > 0 else "admin_remove"
        save_transaction(target_user, amount, tx_type, f"Админ изменил баланс на {amount}")
        
        await bot.send_message(
            target_user,
            f"👑 <b>Администратор изменил ваш баланс!</b>\n\n"
            f"{'+' if amount > 0 else ''}{format_stars(amount)}\n"
            f"💰 Новый баланс: {format_stars(new_balance)}",
            parse_mode=ParseMode.HTML
        )
        
        await state.clear()
        await message.answer(
            f"✅ Баланс @{target_username} изменён на {format_stars(amount)}\n"
            f"💰 Новый баланс: {format_stars(new_balance)}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )
    except ValueError:
        await message.answer("❌ Введи число!")

@dp.message(GameStates.admin_send_message)
async def admin_broadcast_handler(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await state.clear()
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Рассылка отменена.", reply_markup=get_admin_panel_keyboard())
        return
    
    success = 0
    fail = 0
    
    progress_msg = await message.answer("📢 <b>Начинаю рассылку...</b>\n\n⏳ Пожалуйста, подождите...", parse_mode=ParseMode.HTML)
    
    for user_id in users_balance.keys():
        if user_id in blacklist:
            continue
        try:
            if message.text:
                await bot.send_message(user_id, message.text, parse_mode=ParseMode.HTML)
            elif message.photo:
                await bot.send_photo(user_id, message.photo[-1].file_id, caption=message.caption)
            elif message.video:
                await bot.send_video(user_id, message.video.file_id, caption=message.caption)
            elif message.document:
                await bot.send_document(user_id, message.document.file_id, caption=message.caption)
            else:
                await bot.copy_message(user_id, message.chat.id, message.message_id)
            success += 1
            await asyncio.sleep(0.05)
        except:
            fail += 1
    
    await state.clear()
    await progress_msg.edit_text(
        f"✅ <b>РАССЫЛКА ЗАВЕРШЕНА</b>\n\n"
        f"📨 <b>Доставлено:</b> {success}\n"
        f"❌ <b>Ошибок:</b> {fail}\n\n"
        f"📊 Всего пользователей: {len(users_balance)}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard()
    )

@dp.message(GameStates.admin_set_warning)
async def admin_set_warning_handler(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await state.clear()
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Операция отменена.", reply_markup=get_admin_panel_keyboard())
        return
    
    target_username = message.text.strip().replace("@", "")
    target_id = await get_user_id_by_username(target_username)
    
    if not target_id:
        await message.answer("❌ Пользователь не найден!")
        return
    
    warnings = users_warning.get(target_id, 0) + 1
    users_warning[target_id] = warnings
    
    if warnings >= 3:
        blacklist.append(target_id)
        await bot.send_message(target_id, "⚠️ Вы получили 3 предупреждения и были забанены!")
        await message.answer(f"✅ Пользователь @{target_username} получил 3 предупреждения и был забанен!")
    else:
        await bot.send_message(target_id, f"⚠️ Вы получили предупреждение #{warnings}/3!")
        await message.answer(f"✅ Пользователю @{target_username} выдано предупреждение #{warnings}/3")
    
    await state.clear()
    await message.answer("✅ Готово!", reply_markup=get_admin_panel_keyboard())

@dp.message(GameStates.admin_edit_user)
async def admin_edit_user_handler(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await state.clear()
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Операция отменена.", reply_markup=get_admin_panel_keyboard())
        return
    
    data = await state.get_data()
    action = data.get("admin_action")
    target_username = message.text.strip().replace("@", "")
    target_id = await get_user_id_by_username(target_username)
    
    if not target_id:
        await message.answer("❌ Пользователь не найден!")
        return
    
    if action == "ban":
        if target_id not in blacklist:
            blacklist.append(target_id)
            await bot.send_message(target_id, "🚫 Вы были забанены в боте!")
            await message.answer(f"✅ Пользователь @{target_username} забанен!")
        else:
            await message.answer(f"⚠️ Пользователь @{target_username} уже в бане!")
    elif action == "unban":
        if target_id in blacklist:
            blacklist.remove(target_id)
            await bot.send_message(target_id, "🔓 Вы были разбанены в боте!")
            await message.answer(f"✅ Пользователь @{target_username} разбанен!")
        else:
            await message.answer(f"⚠️ Пользователь @{target_username} не в бане!")
    elif action == "mute":
        users_mute[target_id] = True
        await bot.send_message(target_id, "🔇 Вы были замучены в боте!")
        await message.answer(f"✅ Пользователь @{target_username} замучен!")
    elif action == "unmute":
        users_mute[target_id] = False
        await bot.send_message(target_id, "🔊 Вы были размучены в боте!")
        await message.answer(f"✅ Пользователь @{target_username} размучен!")
    
    await state.clear()

@dp.message(GameStates.admin_set_promo)
async def admin_create_promo_handler(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await state.clear()
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Операция отменена.", reply_markup=get_admin_panel_keyboard())
        return
    
    try:
        amount = int(message.text.strip())
        promo_code = generate_promo_code()
        promo_codes[promo_code] = {"amount": amount, "uses": 0, "created": datetime.now().isoformat()}
        
        await message.answer(
            f"✅ <b>Промокод создан!</b>\n\n"
            f"🎁 Код: <code>{promo_code}</code>\n"
            f"💰 Сумма: {format_stars(amount)}\n"
            f"📅 Создан: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Пользователи могут активировать его командой <code>/promo {promo_code}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )
    except ValueError:
        await message.answer("❌ Введи число!", reply_markup=get_admin_panel_keyboard())
    
    await state.clear()


# ===================== ПРОМОКОДЫ И НАВИГАЦИЯ =====================
@dp.message(Command("promo"))
async def promo_use(message: Message, state: FSMContext):
    user_id = message.from_user.id
    args = message.text.split()
    
    if len(args) != 2:
        await message.answer("❌ Использование: /promo КОД")
        return
    
    promo_code = args[1].upper()
    
    if promo_code not in promo_codes:
        await message.answer("❌ Неверный промокод!")
        return
    
    promo = promo_codes[promo_code]
    update_balance(user_id, promo["amount"])
    promo["uses"] += 1
    save_transaction(user_id, promo["amount"], "promo", f"Активация промокода {promo_code}")
    
    await message.answer(
        f"🎉 <b>Промокод активирован!</b>\n\n"
        f"+{format_stars(promo['amount'])}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML
    )

@dp.callback_query(F.data == "back_to_games")
async def back_to_games_callback(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer(
        "🎮 <b>Выбери игру</b>\n\n👇 Нажми на кнопку с игрой:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer(
        "🌟 <b>Главное меню</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )
    await callback.answer()

@dp.message(F.text == "🔙 Главное меню")
async def back_to_main_from_games(message: Message):
    await message.answer(
        "🌟 <b>Главное меню</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )


# ===================== ПЛАТЕЖИ =====================
async def create_stars_invoice(message: Message, user_id: int, amount: int):
    title = "⭐️ Пополнение StarPlay"
    payload = f"starplay_{user_id}_{amount}_{int(datetime.now().timestamp())}"
    prices = [LabeledPrice(label="Telegram Stars", amount=amount)]
    await bot.send_invoice(
        chat_id=user_id,
        title=title,
        description=f"Пополнение на {amount} Stars",
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=prices,
        start_parameter="starplay_deposit"
    )
    pending_payments[payload] = {"user_id": user_id, "amount": amount, "status": "pending"}

@dp.pre_checkout_query()
async def process_pre_checkout(query: PreCheckoutQuery):
    if query.invoice_payload in pending_payments:
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Ошибка платежа")

@dp.message(F.successful_payment)
async def process_payment(message: Message):
    payment = message.successful_payment
    payload = payment.invoice_payload
    if payload not in pending_payments:
        return
    amount = pending_payments[payload]["amount"]
    user_id = message.from_user.id
    new_balance = update_balance(user_id, amount)
    save_transaction(user_id, amount, "deposit", f"Пополнение {amount} Stars")
    
    if user_id in users_referrer:
        referrer = users_referrer[user_id]
        bonus = int(amount * REFERRAL_BONUS_PERCENT / 100)
        if bonus:
            update_balance(referrer, bonus)
            save_transaction(referrer, bonus, "referral_earning", f"10% с пополнения реферала")
            try:
                await bot.send_message(
                    referrer,
                    f"🎉 <b>Реферальный бонус!</b>\n\n"
                    f"Ваш реферал пополнил баланс на {format_stars(amount)}\n"
                    f"Вы получили {format_stars(bonus)}!",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
    
    await message.answer(
        f"✅ <b>Пополнение выполнено!</b>\n\n"
        f"+{format_stars(amount)}\n"
        f"💰 Новый баланс: {format_stars(new_balance)}\n\n"
        f"🎮 Приятной игры в StarPlay!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )


@dp.callback_query(F.data.startswith("deposit_"))
async def deposit_amount(callback: CallbackQuery, state: FSMContext):
    amount_str = callback.data.split("_")[1]
    if amount_str == "custom":
        await callback.message.answer(
            "✏️ <b>Введи сумму пополнения</b>\n\n"
            "Минимум: 1 Star\n"
            "Максимум: 10000 Stars\n\n"
            "<i>Просто отправь число в чат:</i>",
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GameStates.custom_deposit)
        await callback.answer()
        return
    amount = int(amount_str)
    await create_stars_invoice(callback.message, callback.from_user.id, amount)
    await callback.answer()

@dp.message(GameStates.custom_deposit)
async def process_custom_deposit(message: Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        if 1 <= amount <= 10000:
            await state.clear()
            await create_stars_invoice(message, message.from_user.id, amount)
        else:
            await message.answer("❌ Введи число от 1 до 10000")
    except:
        await message.answer("❌ Это не число")

@dp.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    username = message.from_user.username or ""
    if is_admin(username):
        await message.answer("❌ Действие отменено.", reply_markup=get_admin_panel_keyboard())
    else:
        await message.answer("❌ Действие отменено.", reply_markup=get_main_keyboard())


# ===================== ЗАПУСК =====================
async def main():
    logger.info("🚀 StarPlay Bot запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())