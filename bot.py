import asyncio
import hashlib
import logging
import random
import json
import time
import math
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    LabeledPrice, Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, PreCheckoutQuery, SuccessfulPayment,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    FSInputFile, InputFile
)
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# ===================== КОНФИГУРАЦИЯ =====================
BOT_TOKEN = "8251949164:AAEUSmnhX_S4p-vWDD4fvC6mDclV0LvIFe0"
ADMIN_USERNAMES = ["hjklgf1", "admin"]

# Настройки игр
CRASH_MAX_MULTIPLIER = 1000
MINES_BOARD_SIZE = 5
MINES_MINES_COUNT = 5
SLOTS_SYMBOLS = ["🍒", "🍊", "🍋", "💎", "7️⃣", "🎰", "⭐️", "💫"]
SLOTS_PAYOUTS = {
    ("🍒", "🍒", "🍒"): 5, ("🍊", "🍊", "🍊"): 7, ("🍋", "🍋", "🍋"): 10,
    ("💎", "💎", "💎"): 15, ("7️⃣", "7️⃣", "7️⃣"): 25, ("🎰", "🎰", "🎰"): 50,
    ("⭐️", "⭐️", "⭐️"): 30, ("💫", "💫", "💫"): 20
}

# Реферальная система
REFERRAL_BONUS_PERCENT = 10
REFERRAL_SIGNUP_BONUS = 5
REFERRAL_INVITE_BONUS = 10

# Системные настройки
MIN_BET = 1
MAX_BET = 10000
DAILY_BONUS_MIN = 5
DAILY_BONUS_MAX = 25

# ===================== ХРАНИЛИЩА ДАННЫХ =====================
users_balance: Dict[int, float] = {}
users_referrer: Dict[int, int] = {}
users_referrals: Dict[int, List[int]] = {}
users_stats: Dict[int, dict] = {}
users_daily_bonus: Dict[int, str] = {}
users_daily_bonus_streak: Dict[int, int] = {}
pending_payments: Dict[str, dict] = {}
transactions: Dict[int, list] = {}
users_username: Dict[int, str] = {}
users_join_date: Dict[int, str] = {}
users_last_seen: Dict[int, str] = {}
users_ban: Dict[int, bool] = {}
users_ban_reason: Dict[int, str] = {}
users_verify: Dict[int, bool] = {}

# Игровые данные
active_crash: Dict[int, dict] = {}
active_mines: Dict[int, dict] = {}
active_slots: Dict[int, dict] = {}

# История игр
crash_history: List[dict] = []
mines_history: List[dict] = []
slots_history: List[dict] = []

# Промокоды
promo_codes: Dict[str, dict] = {}

# Статистика бота
bot_stats = {
    "total_users": 0,
    "active_today": 0,
    "total_bets": 0,
    "total_wagered": 0.0,
    "total_paid": 0.0,
    "total_profit": 0.0,
    "total_deposits": 0,
    "total_deposit_amount": 0.0,
    "crash_games_played": 0,
    "mines_games_played": 0,
    "slots_games_played": 0,
    "server_start_time": datetime.now().isoformat()
}

# Настройки бота
bot_settings = {
    "maintenance_mode": False,
    "min_bet": MIN_BET,
    "max_bet": MAX_BET,
    "daily_bonus_enabled": True,
    "chat_link": "https://t.me/starplay_chat",
    "channel_link": "https://t.me/starplay_news"
}

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# ===================== FSM СОСТОЯНИЯ =====================
class GameStates(StatesGroup):
    main_menu = State()
    crash_bet = State()
    crash_waiting = State()
    mines_bet = State()
    mines_playing = State()
    slots_bet = State()
    slots_playing = State()
    custom_deposit = State()
    admin_find_user = State()
    admin_change_balance = State()
    admin_send_broadcast = State()
    admin_send_broadcast_confirm = State()
    admin_ban_user = State()
    admin_set_verify = State()
    admin_promo_create = State()
    admin_promo_amount = State()
    admin_global_bonus = State()


# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
def is_admin(username: str) -> bool:
    return username.lower() in [adm.lower() for adm in ADMIN_USERNAMES]

async def get_user_id_by_username(username: str) -> Optional[int]:
    for uid, uname in users_username.items():
        if uname and uname.lower() == username.lower():
            return uid
    return None

def format_stars(amount: float) -> str:
    return f"⭐️ {amount:.2f} Stars"

def get_user_balance(user_id: int) -> float:
    return users_balance.get(user_id, 0.0)

def update_balance(user_id: int, delta: float) -> float:
    current = users_balance.get(user_id, 0.0)
    new_balance = current + delta
    if new_balance < 0:
        new_balance = 0.0
    users_balance[user_id] = round(new_balance, 2)
    return users_balance[user_id]

def save_transaction(user_id: int, amount: float, tx_type: str, details: str = "", game: str = ""):
    if user_id not in transactions:
        transactions[user_id] = []
    
    transactions[user_id].append({
        "amount": round(amount, 2),
        "type": tx_type,
        "details": details,
        "game": game,
        "timestamp": datetime.now().isoformat()
    })
    
    if tx_type == "deposit":
        bot_stats["total_deposits"] += 1
        bot_stats["total_deposit_amount"] += amount
    elif tx_type == "bet":
        bot_stats["total_bets"] += 1
        bot_stats["total_wagered"] += abs(amount)
    elif tx_type == "game_win":
        bot_stats["total_paid"] += amount
    
    bot_stats["total_profit"] = bot_stats["total_wagered"] - bot_stats["total_paid"]

def get_user_stats(user_id: int) -> dict:
    if user_id not in users_stats:
        users_stats[user_id] = {
            "games_played": 0, "games_won": 0, "total_won": 0.0, "total_lost": 0.0,
            "crash_games": 0, "crash_wins": 0, "crash_best_multiplier": 0.0,
            "mines_games": 0, "mines_wins": 0, "mines_best_multiplier": 0.0,
            "slots_games": 0, "slots_wins": 0, "slots_best_multiplier": 0.0,
            "total_deposits": 0, "total_deposit_amount": 0.0,
            "referral_count": 0, "referral_earned": 0.0,
            "daily_bonus_count": 0, "daily_bonus_streak": 0
        }
    return users_stats[user_id]

def get_random_emoji() -> str:
    emojis = ["🎲", "🎯", "⚡️", "💫", "🌟", "⭐️", "✨", "🎮", "🎰", "🔥", "💰", "💎", "🏆", "🎉", "🚀"]
    return random.choice(emojis)

def generate_referral_link(user_id: int) -> str:
    code = hashlib.md5(f"starplay_{user_id}_{datetime.now().date()}".encode()).hexdigest()[:8]
    return f"https://t.me/{bot.username}?start=ref_{code}"

def format_time(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} сек"
    elif seconds < 3600:
        return f"{seconds//60} мин {seconds%60} сек"
    else:
        return f"{seconds//3600} ч {(seconds%3600)//60} мин"

def create_backup():
    data = {
        "balance": users_balance,
        "referrer": users_referrer,
        "referrals": users_referrals,
        "stats": users_stats,
        "transactions": transactions,
        "username": users_username,
        "join_date": users_join_date,
        "ban": users_ban,
        "ban_reason": users_ban_reason,
        "verify": users_verify,
        "promo_codes": promo_codes,
        "bot_stats": bot_stats,
        "bot_settings": bot_settings
    }
    with open("backup.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return True


# ===================== КЛАВИАТУРЫ =====================
def get_main_keyboard(user_id: int = None) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="💰 Баланс")
    builder.button(text="⭐️ Пополнить")
    builder.button(text="🎮 Игры")
    builder.button(text="👥 Рефералы")
    builder.button(text="🏆 Топ")
    builder.button(text="📊 Профиль")
    builder.button(text="🎁 Бонус")
    builder.button(text="❓ Помощь")
    
    if user_id and is_admin(users_username.get(user_id, "")):
        builder.button(text="👑 Админ панель")
    
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_admin_main_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📊 Статистика")
    builder.button(text="💰 Изменить баланс")
    builder.button(text="📢 Рассылка")
    builder.button(text="👥 Пользователи")
    builder.button(text="🔨 Бан/Разбан")
    builder.button(text="✅ Верификация")
    builder.button(text="⚙️ Настройки")
    builder.button(text="🎁 Создать промокод")
    builder.button(text="🎲 Глобальный бонус")
    builder.button(text="💾 Сохранить данные")
    builder.button(text="🔙 В главное меню")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_games_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📈 CRASH")
    builder.button(text="💣 MINES")
    builder.button(text="🎰 SLOTS")
    builder.button(text="🔙 Главное меню")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_crash_bet_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐️ 1", callback_data="crash_bet_1"),
         InlineKeyboardButton(text="⭐️ 5", callback_data="crash_bet_5"),
         InlineKeyboardButton(text="⭐️ 10", callback_data="crash_bet_10")],
        [InlineKeyboardButton(text="⭐️ 25", callback_data="crash_bet_25"),
         InlineKeyboardButton(text="⭐️ 50", callback_data="crash_bet_50"),
         InlineKeyboardButton(text="⭐️ 100", callback_data="crash_bet_100")],
        [InlineKeyboardButton(text="⭐️ 250", callback_data="crash_bet_250"),
         InlineKeyboardButton(text="⭐️ 500", callback_data="crash_bet_500"),
         InlineKeyboardButton(text="⭐️ 1000", callback_data="crash_bet_1000")],
        [InlineKeyboardButton(text="✏️ Своя сумма", callback_data="crash_bet_custom")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_games")]
    ])

def get_crash_game_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 ЗАБРАТЬ ВЫИГРЫШ", callback_data="crash_cashout")],
        [InlineKeyboardButton(text="❌ ВЫЙТИ", callback_data="crash_exit")]
    ])

def get_mines_bet_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐️ 1", callback_data="mines_bet_1"),
         InlineKeyboardButton(text="⭐️ 5", callback_data="mines_bet_5"),
         InlineKeyboardButton(text="⭐️ 10", callback_data="mines_bet_10")],
        [InlineKeyboardButton(text="⭐️ 25", callback_data="mines_bet_25"),
         InlineKeyboardButton(text="⭐️ 50", callback_data="mines_bet_50"),
         InlineKeyboardButton(text="⭐️ 100", callback_data="mines_bet_100")],
        [InlineKeyboardButton(text="⭐️ 250", callback_data="mines_bet_250"),
         InlineKeyboardButton(text="⭐️ 500", callback_data="mines_bet_500"),
         InlineKeyboardButton(text="⭐️ 1000", callback_data="mines_bet_1000")],
        [InlineKeyboardButton(text="✏️ Своя сумма", callback_data="mines_bet_custom")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_games")]
    ])

def get_mines_board_keyboard(board: List[List[str]], revealed: List[List[bool]], bet: float, multiplier: float) -> InlineKeyboardMarkup:
    keyboard = []
    for i in range(MINES_BOARD_SIZE):
        row = []
        for j in range(MINES_BOARD_SIZE):
            if revealed[i][j]:
                emoji = "💣" if board[i][j] == "💣" else "💎"
                text = emoji
            else:
                text = "❓"
            row.append(InlineKeyboardButton(text=text, callback_data=f"mines_cell_{i}_{j}"))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton(text=f"💰 ЗАБРАТЬ ({format_stars(bet * multiplier)})", callback_data="mines_cashout")])
    keyboard.append([InlineKeyboardButton(text="❌ ВЫЙТИ", callback_data="mines_exit")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_slots_bet_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐️ 1", callback_data="slots_bet_1"),
         InlineKeyboardButton(text="⭐️ 5", callback_data="slots_bet_5"),
         InlineKeyboardButton(text="⭐️ 10", callback_data="slots_bet_10")],
        [InlineKeyboardButton(text="⭐️ 25", callback_data="slots_bet_25"),
         InlineKeyboardButton(text="⭐️ 50", callback_data="slots_bet_50"),
         InlineKeyboardButton(text="⭐️ 100", callback_data="slots_bet_100")],
        [InlineKeyboardButton(text="⭐️ 250", callback_data="slots_bet_250"),
         InlineKeyboardButton(text="⭐️ 500", callback_data="slots_bet_500"),
         InlineKeyboardButton(text="⭐️ 1000", callback_data="slots_bet_1000")],
        [InlineKeyboardButton(text="✏️ Своя сумма", callback_data="slots_bet_custom")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_games")]
    ])

def get_slots_game_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 КРУТИТЬ", callback_data="slots_spin")],
        [InlineKeyboardButton(text="❌ ВЫЙТИ", callback_data="slots_exit")]
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

def get_referral_keyboard(user_id: int) -> InlineKeyboardMarkup:
    ref_link = generate_referral_link(user_id)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться ссылкой", url=f"https://t.me/share/url?url={ref_link}&text=StarPlay — лучшие игры с выигрышами! Присоединяйся по моей ссылке!")],
        [InlineKeyboardButton(text="📋 Копировать ссылку", callback_data="copy_referral_link")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])


# ===================== ОСНОВНЫЕ КОМАНДЫ =====================
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    
    if bot_settings["maintenance_mode"] and not is_admin(username):
        await message.answer("🔧 Бот на техническом обслуживании. Зайдите позже.", parse_mode=ParseMode.HTML)
        return
    
    if users_ban.get(user_id, False):
        await message.answer(f"🚫 Ваш аккаунт заблокирован!\nПричина: {users_ban_reason.get(user_id, 'Не указана')}", parse_mode=ParseMode.HTML)
        return
    
    users_username[user_id] = username
    users_last_seen[user_id] = datetime.now().isoformat()
    
    if user_id not in users_join_date:
        users_join_date[user_id] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        bot_stats["total_users"] += 1
        update_balance(user_id, 0)
    
    # Реферальная система
    if " " in message.text:
        param = message.text.split()[1]
        if param.startswith("ref_"):
            try:
                referrer_id = int(param[4:])
                if referrer_id != user_id and user_id not in users_referrer and not users_ban.get(referrer_id, False):
                    users_referrer[user_id] = referrer_id
                    users_referrals.setdefault(referrer_id, []).append(user_id)
                    update_balance(user_id, REFERRAL_SIGNUP_BONUS)
                    update_balance(referrer_id, REFERRAL_INVITE_BONUS)
                    stats = get_user_stats(referrer_id)
                    stats["referral_count"] += 1
                    stats["referral_earned"] += REFERRAL_INVITE_BONUS
                    save_transaction(user_id, REFERRAL_SIGNUP_BONUS, "referral_bonus", f"от {referrer_id}")
                    save_transaction(referrer_id, REFERRAL_INVITE_BONUS, "referral_reward", f"пригласил {user_id}")
                    
                    await message.answer(
                        f"✅ <b>Вы получили бонус за регистрацию!</b>\n\n"
                        f"+{format_stars(REFERRAL_SIGNUP_BONUS)}\n\n"
                        f"💡 Приглашайте друзей и получайте {REFERRAL_BONUS_PERCENT}% от их пополнений!",
                        parse_mode=ParseMode.HTML
                    )
                    
                    try:
                        await bot.send_message(
                            referrer_id,
                            f"🎉 <b>По вашей реферальной ссылке зарегистрировался новый пользователь!</b>\n\n"
                            f"👤 @{username or user_id}\n"
                            f"+{format_stars(REFERRAL_INVITE_BONUS)}\n\n"
                            f"Теперь вы будете получать {REFERRAL_BONUS_PERCENT}% от его пополнений!",
                            parse_mode=ParseMode.HTML
                        )
                    except:
                        pass
            except:
                pass
    
    await state.clear()
    await message.answer(
        f"🌟 <b>Добро пожаловать в StarPlay Casino!</b> 🌟\n\n"
        f"{get_random_emoji()} <b>Лучшее игровое казино в Telegram!</b>\n\n"
        f"<b>🎮 Игры:</b>\n"
        f"📈 CRASH — Растущий множитель до x{CRASH_MAX_MULTIPLIER}\n"
        f"💣 MINES — Сапёр с множителем до x18\n"
        f"🎰 SLOTS — Классические слоты с множителями до x50\n\n"
        f"<b>💫 Как начать:</b>\n"
        f"1️⃣ Пополните баланс\n"
        f"2️⃣ Выберите игру\n"
        f"3️⃣ Делайте ставки и выигрывайте!\n\n"
        f"👇 <i>Используйте кнопки меню!</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(user_id)
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        f"❓ <b>Помощь по боту StarPlay</b>\n\n"
        f"<b>🎮 Игры:</b>\n"
        f"📈 CRASH — Ставка растёт. Заберите выигрыш до взрыва!\n"
        f"💣 MINES — Открывайте клетки с 💎, избегайте 💣\n"
        f"🎰 SLOTS — Классические слоты. Собирайте комбинации!\n\n"
        f"<b>💰 Баланс:</b>\n"
        f"• Пополнение через Telegram Stars\n"
        f"• Минимальная ставка: {MIN_BET} Star\n"
        f"• Максимальная ставка: {MAX_BET} Stars\n\n"
        f"<b>👥 Рефералы:</b>\n"
        f"• Пригласите друга → +{REFERRAL_INVITE_BONUS} Stars\n"
        f"• Друг получает → +{REFERRAL_SIGNUP_BONUS} Stars\n"
        f"• Вы получаете {REFERRAL_BONUS_PERCENT}% от пополнений друга\n\n"
        f"<b>🎁 Ежедневный бонус:</b>\n"
        f"• Забирайте бонус каждый день\n"
        f"• Чем больше стрик — тем больше бонус!\n\n"
        f"<b>📞 Контакты:</b>\n"
        f"• Чат: {bot_settings['chat_link']}\n"
        f"• Поддержка: @StarPlaySupport"
    )
    await message.answer(help_text, parse_mode=ParseMode.HTML)


# ===================== ГЛАВНЫЕ КНОПКИ =====================
@dp.message(F.text == "💰 Баланс")
async def balance_reply(message: Message):
    user_id = message.from_user.id
    await message.answer(f"💰 <b>Ваш баланс:</b>\n\n{format_stars(get_user_balance(user_id))}", parse_mode=ParseMode.HTML)

@dp.message(F.text == "⭐️ Пополнить")
async def deposit_reply(message: Message):
    await message.answer("⭐️ <b>Пополнение баланса</b>\n\nВыберите сумму:", parse_mode=ParseMode.HTML, reply_markup=get_deposit_keyboard())

@dp.message(F.text == "🎮 Игры")
async def games_reply(message: Message):
    await message.answer("🎮 <b>Выберите игру</b>\n\n📈 CRASH — Растущий множитель\n💣 MINES — Найди сокровища\n🎰 SLOTS — Классические слоты", parse_mode=ParseMode.HTML, reply_markup=get_games_keyboard())

@dp.message(F.text == "👥 Рефералы")
async def referrals_reply(message: Message):
    user_id = message.from_user.id
    stats = get_user_stats(user_id)
    ref_link = generate_referral_link(user_id)
    
    text = (
        f"👥 <b>Реферальная программа</b>\n\n"
        f"🏆 <b>Ваша статистика:</b>\n"
        f"• Приглашено друзей: <b>{stats['referral_count']}</b> чел.\n"
        f"• Заработано: <b>{format_stars(stats['referral_earned'])}</b>\n\n"
        f"📋 <b>Как это работает:</b>\n"
        f"1️⃣ Вы приглашаете друга по своей ссылке\n"
        f"2️⃣ Друг получает <b>{format_stars(REFERRAL_SIGNUP_BONUS)}</b> при регистрации\n"
        f"3️⃣ Вы получаете <b>{format_stars(REFERRAL_INVITE_BONUS)}</b> за приглашение\n"
        f"4️⃣ Вы получаете <b>{REFERRAL_BONUS_PERCENT}%</b> от каждого пополнения друга\n\n"
        f"🔗 <b>Ваша реферальная ссылка:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"💡 Поделитесь ссылкой с друзьями и зарабатывайте вместе с нами!"
    )
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_referral_keyboard(user_id))

@dp.callback_query(F.data == "copy_referral_link")
async def copy_referral_link(callback: CallbackQuery):
    user_id = callback.from_user.id
    ref_link = generate_referral_link(user_id)
    await callback.answer(f"🔗 Ссылка скопирована!\n{ref_link}", show_alert=True)
    await callback.message.answer(
        f"🔗 <b>Ваша реферальная ссылка:</b>\n<code>{ref_link}</code>\n\n"
        f"Вы можете скопировать её и отправить друзьям!",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text == "🏆 Топ")
async def top_reply(message: Message):
    sorted_users = sorted(users_balance.items(), key=lambda x: x[1], reverse=True)[:15]
    if not sorted_users:
        await message.answer("🏆 Пока нет игроков в рейтинге!")
        return
    top_text = "🏆 <b>ТОП-15 ПО БАЛАНСУ</b>\n\n"
    for idx, (uid, bal) in enumerate(sorted_users, 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
        uname = users_username.get(uid, str(uid))
        name = f"@{uname}" if uname else str(uid)
        top_text += f"{medal} {name} — {bal:.2f} ⭐️\n"
    await message.answer(top_text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "📊 Профиль")
async def profile_reply(message: Message):
    uid = message.from_user.id
    stats = get_user_stats(uid)
    win_rate = (stats['games_won'] / max(stats['games_played'], 1)) * 100
    text = (
        f"👤 <b>Профиль игрока</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👤 Username: @{message.from_user.username or 'нет'}\n"
        f"📅 Регистрация: {users_join_date.get(uid, 'неизвестно')}\n"
        f"✅ Верификация: {'✅ Да' if users_verify.get(uid, False) else '❌ Нет'}\n\n"
        f"💰 <b>Баланс:</b> {format_stars(get_user_balance(uid))}\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"├ 🎮 Сыграно: {stats['games_played']}\n"
        f"├ 🏆 Побед: {stats['games_won']}\n"
        f"├ 📈 Винрейт: {win_rate:.1f}%\n"
        f"├ 💎 Выиграно: {format_stars(stats['total_won'])}\n"
        f"└ 💸 Проиграно: {format_stars(stats['total_lost'])}\n\n"
        f"📈 <b>По играм:</b>\n"
        f"├ 📈 CRASH: {stats['crash_wins']}/{stats['crash_games']} побед\n"
        f"├ 💣 MINES: {stats['mines_wins']}/{stats['mines_games']} побед\n"
        f"└ 🎰 SLOTS: {stats['slots_wins']}/{stats['slots_games']} побед\n\n"
        f"👥 <b>Рефералы:</b> {stats['referral_count']} чел., {format_stars(stats['referral_earned'])}\n"
        f"🎁 <b>Ежедневный бонус:</b> стрик {stats['daily_bonus_streak']} дней"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "🎁 Бонус")
async def bonus_reply(message: Message):
    user_id = message.from_user.id
    today = datetime.now().date().isoformat()
    
    if not bot_settings["daily_bonus_enabled"]:
        await message.answer("🔧 Ежедневный бонус временно отключён!", parse_mode=ParseMode.HTML)
        return
    
    if users_daily_bonus.get(user_id) == today:
        next_bonus = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        time_left = next_bonus - datetime.now()
        await message.answer(f"🎁 <b>Вы уже получили сегодняшний бонус!</b>\n\nСледующий через: {format_time(int(time_left.total_seconds()))}", parse_mode=ParseMode.HTML)
        return
    
    streak = users_daily_bonus_streak.get(user_id, 0)
    if users_daily_bonus.get(user_id) == (datetime.now() - timedelta(days=1)).date().isoformat():
        streak += 1
    else:
        streak = 1
    
    bonus = min(DAILY_BONUS_MAX, DAILY_BONUS_MIN + (streak - 1) * 2)
    bonus = round(random.uniform(bonus - 2, bonus + 2), 2)
    
    update_balance(user_id, bonus)
    users_daily_bonus[user_id] = today
    users_daily_bonus_streak[user_id] = streak
    stats = get_user_stats(user_id)
    stats["daily_bonus_count"] += 1
    stats["daily_bonus_streak"] = streak
    save_transaction(user_id, bonus, "daily_bonus", f"Стрик: {streak}")
    
    await message.answer(f"🎉 <b>Ежедневный бонус получен!</b>\n\n+{format_stars(bonus)}\n📅 Стрик: {streak} дней\n💰 Новый баланс: {format_stars(get_user_balance(user_id))}", parse_mode=ParseMode.HTML)

@dp.message(F.text == "❓ Помощь")
async def help_reply(message: Message):
    await cmd_help(message)


# ===================== ИГРА CRASH =====================
async def run_crash_game(user_id: int, game_msg: Message, bet: float, state: FSMContext):
    game = active_crash.get(user_id)
    if not game:
        return
    
    crash_point = game["crash_point"]
    multiplier = 1.0
    
    while multiplier < crash_point and user_id in active_crash:
        multiplier = round(multiplier + 0.02, 2)
        game["multiplier"] = multiplier
        try:
            await game_msg.edit_text(
                f"📈 <b>CRASH — ИГРА ИДЁТ!</b>\n\n"
                f"💰 Ставка: {format_stars(bet)}\n"
                f"📈 Множитель: <b>x{multiplier:.2f}</b>\n"
                f"💎 Выигрыш: {format_stars(bet * multiplier)}\n\n"
                f"⚠️ Заберите до взрыва!",
                parse_mode=ParseMode.HTML,
                reply_markup=get_crash_game_keyboard()
            )
        except:
            pass
        await asyncio.sleep(0.15)
    
    if user_id in active_crash:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["crash_games"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", f"Crash краш на x{multiplier:.2f}", "crash")
        bot_stats["crash_games_played"] += 1
        crash_history.append({"multiplier": multiplier, "player": user_id, "bet": bet, "win": 0, "timestamp": datetime.now().isoformat()})
        if len(crash_history) > 100:
            crash_history.pop(0)
        del active_crash[user_id]
        try:
            await game_msg.edit_text(
                f"💥 <b>CRASH — ВЗРЫВ!</b>\n\n"
                f"💰 Ставка: {format_stars(bet)}\n"
                f"📈 Множитель: x{multiplier:.2f}\n\n"
                f"😢 <b>Ставка сгорела!</b>\n"
                f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_games_keyboard()
            )
        except:
            pass

@dp.message(F.text == "📈 CRASH")
async def crash_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in active_crash:
        await message.answer("⚠️ У вас уже есть активная игра!", parse_mode=ParseMode.HTML)
        return
    await state.set_state(GameStates.crash_bet)
    await message.answer("📈 <b>CRASH</b>\n\nВыберите сумму ставки:", parse_mode=ParseMode.HTML, reply_markup=get_crash_bet_keyboard())

@dp.callback_query(F.data.startswith("crash_bet_"))
async def crash_bet(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    bet_str = callback.data.split("_")[-1]
    
    if bet_str == "custom":
        await callback.message.answer("✏️ Введите сумму ставки (1-10000):", parse_mode=ParseMode.HTML)
        await state.set_state(GameStates.crash_bet)
        await callback.answer()
        return
    
    try:
        bet = float(bet_str)
    except:
        await callback.answer("Неверная сумма!", show_alert=True)
        return
    
    if bet < MIN_BET or bet > MAX_BET:
        await callback.answer(f"❌ Ставка от {MIN_BET} до {MAX_BET} Stars!", show_alert=True)
        return
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}!", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    save_transaction(user_id, -bet, "bet", f"Crash ставка", "crash")
    
    crash_point = random.uniform(1.05, CRASH_MAX_MULTIPLIER)
    active_crash[user_id] = {"bet": bet, "crash_point": crash_point, "multiplier": 1.0}
    
    await state.set_state(GameStates.crash_waiting)
    game_msg = await callback.message.edit_text(
        f"📈 <b>CRASH — ИГРА ИДЁТ!</b>\n\n💰 Ставка: {format_stars(bet)}\n📈 Множитель: x1.00\n💎 Выигрыш: {format_stars(bet)}\n\n⚠️ Заберите до взрыва!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_crash_game_keyboard()
    )
    asyncio.create_task(run_crash_game(user_id, game_msg, bet, state))
    await callback.answer()

@dp.callback_query(F.data == "crash_cashout")
async def crash_cashout(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id not in active_crash:
        await callback.answer("Нет активной игры!", show_alert=True)
        return
    
    game = active_crash[user_id]
    win = game["bet"] * game["multiplier"]
    update_balance(user_id, win)
    stats = get_user_stats(user_id)
    stats["games_played"] += 1
    stats["games_won"] += 1
    stats["crash_games"] += 1
    stats["crash_wins"] += 1
    stats["total_won"] += win
    if game["multiplier"] > stats["crash_best_multiplier"]:
        stats["crash_best_multiplier"] = game["multiplier"]
    save_transaction(user_id, win, "game_win", f"Crash x{game['multiplier']:.2f}", "crash")
    bot_stats["crash_games_played"] += 1
    crash_history.append({"multiplier": game["multiplier"], "player": user_id, "bet": game["bet"], "win": win, "timestamp": datetime.now().isoformat()})
    if len(crash_history) > 100:
        crash_history.pop(0)
    del active_crash[user_id]
    await state.clear()
    
    # Сообщение после забора выигрыша
    await callback.message.answer(
        f"💰 <b>ВЫ ЗАБРАЛИ ВЫИГРЫШ!</b> 💰\n\n"
        f"✅ <b>Поздравляем!</b> Вы успешно забрали выигрыш до взрыва!\n\n"
        f"📊 <b>Детали игры:</b>\n"
        f"├ 💰 Ставка: {format_stars(game['bet'])}\n"
        f"├ 📈 Множитель: <b>x{game['multiplier']:.2f}</b>\n"
        f"└ 🏆 Выигрыш: <b>{format_stars(win)}</b>\n\n"
        f"💰 <b>Новый баланс:</b> {format_stars(get_user_balance(user_id))}\n\n"
        f"🎮 <b>Хотите сыграть ещё?</b> Нажмите на кнопку ниже.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📈 ИГРАТЬ СНОВА", callback_data="crash_play_again")],
            [InlineKeyboardButton(text="🎮 ВЫБРАТЬ ДРУГУЮ ИГРУ", callback_data="back_to_games")]
        ])
    )
    await callback.message.delete()
    await callback.answer()

@dp.callback_query(F.data == "crash_play_again")
async def crash_play_again(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await crash_start(callback.message, state)
    await callback.answer()

@dp.callback_query(F.data == "crash_exit")
async def crash_exit(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id in active_crash:
        del active_crash[user_id]
    await state.clear()
    await callback.message.edit_text("❌ Вы вышли из игры.", parse_mode=ParseMode.HTML, reply_markup=get_games_keyboard())
    await callback.answer()


# ===================== ИГРА MINES =====================
def create_mines_board():
    board = [["💎" for _ in range(MINES_BOARD_SIZE)] for _ in range(MINES_BOARD_SIZE)]
    mines = 0
    while mines < MINES_MINES_COUNT:
        x, y = random.randint(0, MINES_BOARD_SIZE - 1), random.randint(0, MINES_BOARD_SIZE - 1)
        if board[x][y] == "💎":
            board[x][y] = "💣"
            mines += 1
    return board

@dp.message(F.text == "💣 MINES")
async def mines_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in active_mines:
        await message.answer("⚠️ У вас уже есть активная игра!", parse_mode=ParseMode.HTML)
        return
    await state.set_state(GameStates.mines_bet)
    await message.answer("💣 <b>MINES</b>\n\nВыберите сумму ставки:", parse_mode=ParseMode.HTML, reply_markup=get_mines_bet_keyboard())

@dp.callback_query(F.data.startswith("mines_bet_"))
async def mines_bet(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    bet_str = callback.data.split("_")[-1]
    
    if bet_str == "custom":
        await callback.message.answer("✏️ Введите сумму ставки (1-10000):", parse_mode=ParseMode.HTML)
        await state.set_state(GameStates.mines_bet)
        await callback.answer()
        return
    
    try:
        bet = float(bet_str)
    except:
        await callback.answer("Неверная сумма!", show_alert=True)
        return
    
    if bet < MIN_BET or bet > MAX_BET:
        await callback.answer(f"❌ Ставка от {MIN_BET} до {MAX_BET} Stars!", show_alert=True)
        return
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}!", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    save_transaction(user_id, -bet, "bet", f"Mines ставка", "mines")
    
    board = create_mines_board()
    active_mines[user_id] = {
        "bet": bet,
        "board": board,
        "revealed": [[False] * MINES_BOARD_SIZE for _ in range(MINES_BOARD_SIZE)],
        "multiplier": 1.0,
        "cells_opened": 0
    }
    
    await state.set_state(GameStates.mines_playing)
    await callback.message.edit_text(
        f"💣 <b>MINES — ИГРА</b>\n\n💰 Ставка: {format_stars(bet)}\n✨ Множитель: x1.0\n📦 Открыто: 0\n💎 Выигрыш: {format_stars(bet)}\n\n👇 Открывайте клетки!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_mines_board_keyboard(board, active_mines[user_id]["revealed"], bet, 1.0)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("mines_cell_"))
async def mines_cell(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_mines:
        await callback.answer("Игра не найдена!", show_alert=True)
        return
    
    game = active_mines[user_id]
    parts = callback.data.split("_")
    x, y = int(parts[2]), int(parts[3])
    
    if game["revealed"][x][y]:
        await callback.answer("Уже открыто!", show_alert=True)
        return
    
    game["revealed"][x][y] = True
    
    if game["board"][x][y] == "💣":
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["mines_games"] += 1
        stats["total_lost"] += game["bet"]
        save_transaction(user_id, -game["bet"], "game_loss", "Mines проигрыш", "mines")
        bot_stats["mines_games_played"] += 1
        mines_history.append({"multiplier": game["multiplier"], "player": user_id, "bet": game["bet"], "win": 0, "timestamp": datetime.now().isoformat()})
        if len(mines_history) > 100:
            mines_history.pop(0)
        del active_mines[user_id]
        await callback.message.edit_text(
            f"💥 <b>MINES — ПРОИГРЫШ!</b>\n\nВы наступили на мину!\n💰 Ставка: {format_stars(game['bet'])} — проиграна\n💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_games_keyboard()
        )
    else:
        game["cells_opened"] += 1
        game["multiplier"] *= 1.2
        max_cells = MINES_BOARD_SIZE * MINES_BOARD_SIZE - MINES_MINES_COUNT
        current_win = game["bet"] * game["multiplier"]
        
        if game["cells_opened"] >= max_cells:
            update_balance(user_id, current_win)
            stats = get_user_stats(user_id)
            stats["games_played"] += 1
            stats["games_won"] += 1
            stats["mines_games"] += 1
            stats["mines_wins"] += 1
            stats["total_won"] += current_win
            if game["multiplier"] > stats["mines_best_multiplier"]:
                stats["mines_best_multiplier"] = game["multiplier"]
            save_transaction(user_id, current_win, "game_win", f"Mines победа x{game['multiplier']:.1f}", "mines")
            bot_stats["mines_games_played"] += 1
            mines_history.append({"multiplier": game["multiplier"], "player": user_id, "bet": game["bet"], "win": current_win, "timestamp": datetime.now().isoformat()})
            if len(mines_history) > 100:
                mines_history.pop(0)
            del active_mines[user_id]
            await callback.message.edit_text(
                f"🎉 <b>MINES — ПОБЕДА!</b>\n\n💰 Ставка: {format_stars(game['bet'])}\n✨ Множитель: x{game['multiplier']:.2f}\n🏆 Выигрыш: {format_stars(current_win)}\n💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_games_keyboard()
            )
        else:
            await callback.message.edit_text(
                f"💣 <b>MINES — ИГРА</b>\n\n💰 Ставка: {format_stars(game['bet'])}\n✨ Множитель: x{game['multiplier']:.2f}\n📦 Открыто: {game['cells_opened']}/{max_cells}\n💎 Выигрыш: {format_stars(current_win)}\n\n✅ Найдена 💎! Продолжайте!",
                parse_mode=ParseMode.HTML,
                reply_markup=get_mines_board_keyboard(game["board"], game["revealed"], game["bet"], game["multiplier"])
            )
    await callback.answer()

@dp.callback_query(F.data == "mines_cashout")
async def mines_cashout(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_mines:
        await callback.answer("Нет активной игры!", show_alert=True)
        return
    
    game = active_mines[user_id]
    win = game["bet"] * game["multiplier"]
    update_balance(user_id, win)
    stats = get_user_stats(user_id)
    stats["games_played"] += 1
    stats["games_won"] += 1
    stats["mines_games"] += 1
    stats["mines_wins"] += 1
    stats["total_won"] += win
    if game["multiplier"] > stats["mines_best_multiplier"]:
        stats["mines_best_multiplier"] = game["multiplier"]
    save_transaction(user_id, win, "game_win", f"Mines кэшаут x{game['multiplier']:.1f}", "mines")
    bot_stats["mines_games_played"] += 1
    mines_history.append({"multiplier": game["multiplier"], "player": user_id, "bet": game["bet"], "win": win, "timestamp": datetime.now().isoformat()})
    if len(mines_history) > 100:
        mines_history.pop(0)
    del active_mines[user_id]
    
    # Сообщение после забора выигрыша
    await callback.message.answer(
        f"💰 <b>ВЫ ЗАБРАЛИ ВЫИГРЫШ!</b> 💰\n\n"
        f"✅ <b>Поздравляем!</b> Вы успешно забрали выигрыш!\n\n"
        f"📊 <b>Детали игры:</b>\n"
        f"├ 💰 Ставка: {format_stars(game['bet'])}\n"
        f"├ ✨ Множитель: <b>x{game['multiplier']:.2f}</b>\n"
        f"├ 📦 Открыто клеток: {game['cells_opened']}/{MINES_BOARD_SIZE * MINES_BOARD_SIZE - MINES_MINES_COUNT}\n"
        f"└ 🏆 Выигрыш: <b>{format_stars(win)}</b>\n\n"
        f"💰 <b>Новый баланс:</b> {format_stars(get_user_balance(user_id))}\n\n"
        f"🎮 <b>Хотите сыграть ещё?</b> Нажмите на кнопку ниже.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💣 ИГРАТЬ СНОВА", callback_data="mines_play_again")],
            [InlineKeyboardButton(text="🎮 ВЫБРАТЬ ДРУГУЮ ИГРУ", callback_data="back_to_games")]
        ])
    )
    await callback.message.delete()
    await callback.answer()

@dp.callback_query(F.data == "mines_play_again")
async def mines_play_again(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await mines_start(callback.message, state)
    await callback.answer()

@dp.callback_query(F.data == "mines_exit")
async def mines_exit(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id in active_mines:
        del active_mines[user_id]
    await state.clear()
    await callback.message.edit_text("❌ Вы вышли из игры.", parse_mode=ParseMode.HTML, reply_markup=get_games_keyboard())
    await callback.answer()


# ===================== ИГРА SLOTS =====================
@dp.message(F.text == "🎰 SLOTS")
async def slots_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    await state.set_state(GameStates.slots_bet)
    await message.answer(
        "🎰 <b>SLOTS — Классические слоты</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• Крутите барабаны и собирайте комбинации\n"
        "• 🍒🍒🍒 → x5 | 🍊🍊🍊 → x7 | 🍋🍋🍋 → x10\n"
        "• 💎💎💎 → x15 | 7️⃣7️⃣7️⃣ → x25 | 🎰🎰🎰 → x50\n"
        "• ⭐️⭐️⭐️ → x30 | 💫💫💫 → x20\n\n"
        "Выберите сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_slots_bet_keyboard()
    )

@dp.callback_query(F.data.startswith("slots_bet_"))
async def slots_bet(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    bet_str = callback.data.split("_")[-1]
    
    if bet_str == "custom":
        await callback.message.answer("✏️ Введите сумму ставки (1-10000):", parse_mode=ParseMode.HTML)
        await state.set_state(GameStates.slots_bet)
        await callback.answer()
        return
    
    try:
        bet = float(bet_str)
    except:
        await callback.answer("Неверная сумма!", show_alert=True)
        return
    
    if bet < MIN_BET or bet > MAX_BET:
        await callback.answer(f"❌ Ставка от {MIN_BET} до {MAX_BET} Stars!", show_alert=True)
        return
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}!", show_alert=True)
        return
    
    await state.update_data(slots_bet=bet)
    active_slots[user_id] = {"bet": bet}
    await state.set_state(GameStates.slots_playing)
    
    await callback.message.edit_text(
        f"🎰 <b>SLOTS</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"🎰 Нажмите «КРУТИТЬ», чтобы начать игру!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_slots_game_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "slots_spin")
async def slots_spin(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    if user_id not in active_slots:
        await callback.answer("Начните игру заново!", show_alert=True)
        return
    
    bet = active_slots[user_id]["bet"]
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}!", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    save_transaction(user_id, -bet, "bet", f"Slots ставка", "slots")
    
    reel1 = random.choice(SLOTS_SYMBOLS)
    reel2 = random.choice(SLOTS_SYMBOLS)
    reel3 = random.choice(SLOTS_SYMBOLS)
    combo = (reel1, reel2, reel3)
    
    if combo in SLOTS_PAYOUTS:
        mult = SLOTS_PAYOUTS[combo]
        win = bet * mult
        update_balance(user_id, win)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["slots_games"] += 1
        stats["slots_wins"] += 1
        stats["total_won"] += win
        if mult > stats["slots_best_multiplier"]:
            stats["slots_best_multiplier"] = mult
        save_transaction(user_id, win, "game_win", f"Slots x{mult}", "slots")
        result_text = f"🎉 <b>ДЖЕКПОТ!</b> x{mult}\n+{format_stars(win - bet)}"
    elif reel1 == reel2 or reel1 == reel3 or reel2 == reel3:
        win = bet * 1.5
        update_balance(user_id, win)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["slots_games"] += 1
        stats["slots_wins"] += 1
        stats["total_won"] += win
        save_transaction(user_id, win, "game_win", f"Slots пара", "slots")
        result_text = f"🎉 <b>ПАРА!</b> x1.5\n+{format_stars(win - bet)}"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["slots_games"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", f"Slots проигрыш", "slots")
        result_text = f"😢 <b>Не повезло...</b>\n-{format_stars(bet)}"
    
    bot_stats["slots_games_played"] += 1
    slots_history.append({"combo": f"{reel1}{reel2}{reel3}", "player": user_id, "bet": bet, "win": win if 'win' in dir() else 0, "timestamp": datetime.now().isoformat()})
    if len(slots_history) > 100:
        slots_history.pop(0)
    
    # Сообщение после игры
    await callback.message.answer(
        f"🎰 <b>SLOTS — РЕЗУЛЬТАТ</b>\n\n"
        f"┌─────┬─────┬─────┐\n"
        f"│  {reel1}  │  {reel2}  │  {reel3}  │\n"
        f"└─────┴─────┴─────┘\n\n"
        f"💰 Ставка: {format_stars(bet)}\n\n"
        f"{result_text}\n\n"
        f"💰 <b>Новый баланс:</b> {format_stars(get_user_balance(user_id))}\n\n"
        f"🎰 <b>Хотите крутить ещё?</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎰 КРУТИТЬ ЕЩЁ", callback_data="slots_spin")],
            [InlineKeyboardButton(text="🎮 ВЫБРАТЬ ДРУГУЮ ИГРУ", callback_data="back_to_games")],
            [InlineKeyboardButton(text="❌ ВЫЙТИ", callback_data="slots_exit")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "slots_exit")
async def slots_exit(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id in active_slots:
        del active_slots[user_id]
    await state.clear()
    await callback.message.edit_text("❌ Вы вышли из игры.", parse_mode=ParseMode.HTML, reply_markup=get_games_keyboard())
    await callback.answer()


# ===================== АДМИН-ПАНЕЛЬ =====================
@dp.message(F.text == "👑 Админ панель")
async def admin_panel(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    await message.answer("👑 <b>Панель администратора</b>\n\nВыберите действие:", parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())

@dp.message(F.text == "📊 Статистика")
async def admin_stats(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    uptime = datetime.now() - datetime.fromisoformat(bot_stats["server_start_time"])
    text = (
        f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
        f"👥 Пользователей: {bot_stats['total_users']}\n"
        f"💰 Общий баланс: {format_stars(sum(users_balance.values()))}\n"
        f"📊 Всего ставок: {bot_stats['total_bets']}\n"
        f"💸 Объём ставок: {format_stars(bot_stats['total_wagered'])}\n"
        f"🎉 Выплачено: {format_stars(bot_stats['total_paid'])}\n"
        f"💰 Прибыль: {format_stars(bot_stats['total_profit'])}\n"
        f"📈 CRASH игр: {bot_stats['crash_games_played']}\n"
        f"💣 MINES игр: {bot_stats['mines_games_played']}\n"
        f"🎰 SLOTS игр: {bot_stats['slots_games_played']}\n"
        f"🕐 Аптайм: {format_time(int(uptime.total_seconds()))}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())

@dp.message(F.text == "💰 Изменить баланс")
async def admin_change_balance_start(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await state.set_state(GameStates.admin_find_user)
    await message.answer("💰 <b>Изменить баланс</b>\n\nВведите username или ID пользователя:", parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True))

@dp.message(GameStates.admin_find_user)
async def admin_find_user(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=get_admin_main_keyboard())
        return
    
    input_text = message.text.strip().replace("@", "")
    user_id = await get_user_id_by_username(input_text)
    if not user_id:
        try:
            user_id = int(input_text)
        except:
            pass
    
    if not user_id or user_id not in users_balance:
        await message.answer("❌ Пользователь не найден!")
        return
    
    await state.update_data(target_user=user_id, target_username=input_text)
    await state.set_state(GameStates.admin_change_balance)
    await message.answer(f"👤 @{input_text}\n💰 Баланс: {format_stars(get_user_balance(user_id))}\n\nВведите сумму изменения (+100 или -50):", parse_mode=ParseMode.HTML)

@dp.message(GameStates.admin_change_balance)
async def admin_change_balance_amount(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=get_admin_main_keyboard())
        return
    
    data = await state.get_data()
    target_user = data.get("target_user")
    target_username = data.get("target_username")
    
    try:
        amount = float(message.text.strip())
        new_balance = update_balance(target_user, amount)
        try:
            await bot.send_message(target_user, f"👑 <b>Администратор изменил баланс!</b>\n{'+' if amount>0 else ''}{format_stars(amount)}\n💰 Новый баланс: {format_stars(new_balance)}", parse_mode=ParseMode.HTML)
        except:
            pass
        save_transaction(target_user, amount, "admin_change", f"Админ: {amount}", "admin")
        await state.clear()
        await message.answer(f"✅ Баланс @{target_username} изменён на {format_stars(amount)}", reply_markup=get_admin_main_keyboard())
    except:
        await message.answer("❌ Введите число!")

@dp.message(F.text == "📢 Рассылка")
async def admin_broadcast_start(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await state.set_state(GameStates.admin_send_broadcast)
    await message.answer("📢 <b>Рассылка</b>\n\nВведите сообщение для рассылки:", parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True))

@dp.message(GameStates.admin_send_broadcast)
async def admin_broadcast_message(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=get_admin_main_keyboard())
        return
    await state.update_data(broadcast_msg=message)
    await state.set_state(GameStates.admin_send_broadcast_confirm)
    recipients = [uid for uid in users_balance.keys() if not users_ban.get(uid, False)]
    await message.answer(f"📨 Получателей: {len(recipients)}\n\nОтправить рассылку?", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ОТПРАВИТЬ", callback_data="broadcast_confirm")]]))

@dp.callback_query(F.data == "broadcast_confirm")
async def admin_broadcast_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg = data.get("broadcast_msg")
    if not msg:
        await callback.answer("Ошибка!", show_alert=True)
        return
    
    success = 0
    for user_id in users_balance.keys():
        if users_ban.get(user_id, False):
            continue
        try:
            if msg.text:
                await bot.send_message(user_id, msg.text, parse_mode=ParseMode.HTML)
            elif msg.photo:
                await bot.send_photo(user_id, msg.photo[-1].file_id, caption=msg.caption)
            else:
                await bot.copy_message(user_id, msg.chat.id, msg.message_id)
            success += 1
        except:
            pass
        await asyncio.sleep(0.05)
    
    await state.clear()
    await callback.message.edit_text(f"✅ Рассылка завершена!\n📨 Доставлено: {success}", reply_markup=get_admin_main_keyboard())
    await callback.answer()

@dp.message(F.text == "👥 Пользователи")
async def admin_users_list(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    users_list = [f"{'🚫' if users_ban.get(uid, False) else '✅'} @{uname or uid} — {get_user_balance(uid):.2f}⭐️" for uid, uname in users_username.items()]
    text = "👥 <b>ПОЛЬЗОВАТЕЛИ</b>\n\n" + "\n".join(users_list[:50])
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())

@dp.message(F.text == "🔨 Бан/Разбан")
async def admin_ban_start(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await state.set_state(GameStates.admin_ban_user)
    await message.answer("🔨 <b>БАН ПОЛЬЗОВАТЕЛЯ</b>\n\nВведите username или ID:", parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True))

@dp.message(GameStates.admin_ban_user)
async def admin_ban_user(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=get_admin_main_keyboard())
        return
    
    input_text = message.text.strip().replace("@", "")
    user_id = await get_user_id_by_username(input_text)
    if not user_id:
        try:
            user_id = int(input_text)
        except:
            pass
    
    if not user_id or user_id not in users_balance:
        await message.answer("❌ Пользователь не найден!")
        return
    
    users_ban[user_id] = not users_ban.get(user_id, False)
    users_ban_reason[user_id] = "Нарушение правил" if users_ban[user_id] else ""
    status = "забанен" if users_ban[user_id] else "разбанен"
    try:
        await bot.send_message(user_id, f"🚫 Ваш аккаунт {status}!" if users_ban[user_id] else f"✅ Ваш аккаунт {status}!", parse_mode=ParseMode.HTML)
    except:
        pass
    await state.clear()
    await message.answer(f"✅ Пользователь {status}!", reply_markup=get_admin_main_keyboard())

@dp.message(F.text == "✅ Верификация")
async def admin_verify_start(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await state.set_state(GameStates.admin_set_verify)
    await message.answer("✅ <b>ВЕРИФИКАЦИЯ</b>\n\nВведите username или ID:", parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True))

@dp.message(GameStates.admin_set_verify)
async def admin_set_verify(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=get_admin_main_keyboard())
        return
    
    input_text = message.text.strip().replace("@", "")
    user_id = await get_user_id_by_username(input_text)
    if not user_id:
        try:
            user_id = int(input_text)
        except:
            pass
    
    if not user_id or user_id not in users_balance:
        await message.answer("❌ Пользователь не найден!")
        return
    
    users_verify[user_id] = not users_verify.get(user_id, False)
    status = "верифицирован" if users_verify[user_id] else "деверифицирован"
    try:
        await bot.send_message(user_id, f"✅ Ваш аккаунт {status}!", parse_mode=ParseMode.HTML)
    except:
        pass
    await state.clear()
    await message.answer(f"✅ Пользователь {status}!", reply_markup=get_admin_main_keyboard())

@dp.message(F.text == "⚙️ Настройки")
async def admin_settings(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    text = (
        f"⚙️ <b>НАСТРОЙКИ</b>\n\n"
        f"💰 Мин. ставка: {MIN_BET}\n"
        f"💰 Макс. ставка: {MAX_BET}\n"
        f"🎁 Ежедневный бонус: {'Вкл' if bot_settings['daily_bonus_enabled'] else 'Выкл'}\n"
        f"👥 Реферальный %: {REFERRAL_BONUS_PERCENT}%\n"
        f"🔧 Режим обслуживания: {'Вкл' if bot_settings['maintenance_mode'] else 'Выкл'}\n"
        f"📈 Макс. множитель CRASH: x{CRASH_MAX_MULTIPLIER}\n"
        f"💣 Размер MINES: {MINES_BOARD_SIZE}x{MINES_BOARD_SIZE}\n"
        f"💣 Количество мин: {MINES_MINES_COUNT}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())

@dp.message(F.text == "🎁 Создать промокод")
async def admin_promo_create(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await state.set_state(GameStates.admin_promo_create)
    await message.answer("🎁 <b>СОЗДАНИЕ ПРОМОКОДА</b>\n\nВведите название промокода:", parse_mode=ParseMode.HTML)

@dp.message(GameStates.admin_promo_create)
async def admin_promo_code(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    await state.update_data(promo_code=code)
    await state.set_state(GameStates.admin_promo_amount)
    await message.answer(f"Введите сумму бонуса для промокода <code>{code}</code>:", parse_mode=ParseMode.HTML)

@dp.message(GameStates.admin_promo_amount)
async def admin_promo_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
        data = await state.get_data()
        code = data.get("promo_code")
        promo_codes[code] = {"amount": amount, "uses": 0, "max_uses": 100, "created": datetime.now().isoformat()}
        await state.clear()
        await message.answer(f"✅ Промокод <code>{code}</code> создан на {format_stars(amount)}!", parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())
    except:
        await message.answer("❌ Введите число!")

@dp.message(F.text == "🎲 Глобальный бонус")
async def admin_global_bonus(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await state.set_state(GameStates.admin_global_bonus)
    await message.answer("🎲 <b>ГЛОБАЛЬНЫЙ БОНУС</b>\n\nВведите сумму бонуса для всех пользователей:", parse_mode=ParseMode.HTML)

@dp.message(GameStates.admin_global_bonus)
async def admin_global_bonus_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
        count = 0
        for user_id in users_balance.keys():
            if not users_ban.get(user_id, False):
                update_balance(user_id, amount)
                try:
                    await bot.send_message(user_id, f"🎉 <b>Глобальный бонус от администратора!</b>\n+{format_stars(amount)}", parse_mode=ParseMode.HTML)
                except:
                    pass
                count += 1
            await asyncio.sleep(0.05)
        await state.clear()
        await message.answer(f"✅ Бонус {format_stars(amount)} выдан {count} пользователям!", reply_markup=get_admin_main_keyboard())
    except:
        await message.answer("❌ Введите число!")

@dp.message(F.text == "💾 Сохранить данные")
async def admin_save_data(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    if create_backup():
        await message.answer("✅ Данные сохранены в backup.json!", reply_markup=get_admin_main_keyboard())
    else:
        await message.answer("❌ Ошибка сохранения!", reply_markup=get_admin_main_keyboard())

@dp.message(F.text == "🔙 В главное меню")
async def back_to_main(message: Message):
    await message.answer("🌟 <b>Главное меню</b>", parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard(message.from_user.id))

@dp.callback_query(F.data == "back_to_games")
async def back_to_games(callback: CallbackQuery):
    await callback.message.edit_text("🎮 <b>Выберите игру</b>", parse_mode=ParseMode.HTML, reply_markup=get_games_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery):
    await callback.message.edit_text("🌟 <b>Главное меню</b>", parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard(callback.from_user.id))
    await callback.answer()


# ===================== ПЛАТЕЖИ =====================
async def create_stars_invoice(message: Message, user_id: int, amount: int):
    title = "⭐️ Пополнение StarPlay"
    payload = f"starplay_{user_id}_{amount}_{int(datetime.now().timestamp())}"
    prices = [LabeledPrice(label="Telegram Stars", amount=amount)]
    await bot.send_invoice(chat_id=user_id, title=title, description=f"Пополнение на {amount} Stars", payload=payload, provider_token="", currency="XTR", prices=prices, start_parameter="starplay_deposit")
    pending_payments[payload] = {"user_id": user_id, "amount": amount}

@dp.pre_checkout_query()
async def process_pre_checkout(query: PreCheckoutQuery):
    if query.invoice_payload in pending_payments:
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Ошибка")

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
        bonus = amount * REFERRAL_BONUS_PERCENT / 100
        if bonus > 0:
            update_balance(referrer, bonus)
            save_transaction(referrer, bonus, "referral_earning", f"10% с пополнения реферала")
            try:
                await bot.send_message(referrer, f"🎉 Реферальный бонус!\n+{format_stars(bonus)}", parse_mode=ParseMode.HTML)
            except:
                pass
    
    await message.answer(f"✅ Пополнение выполнено!\n+{format_stars(amount)}\n💰 Новый баланс: {format_stars(new_balance)}", parse_mode=ParseMode.HTML)

@dp.callback_query(F.data.startswith("deposit_"))
async def deposit_callback(callback: CallbackQuery, state: FSMContext):
    amount_str = callback.data.split("_")[-1]
    if amount_str == "custom":
        await callback.message.answer("✏️ Введите сумму (1-10000):", parse_mode=ParseMode.HTML)
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
            await message.answer("❌ От 1 до 10000!")
    except:
        await message.answer("❌ Введите число!")

@dp.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Отменено.", reply_markup=get_main_keyboard(message.from_user.id))


# ===================== ЗАПУСК =====================
async def main():
    logger.info("🚀 StarPlay Casino Bot запускается...")
    if os.path.exists("backup.json"):
        try:
            with open("backup.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                users_balance.update(data.get("balance", {}))
                users_referrer.update(data.get("referrer", {}))
                users_referrals.update(data.get("referrals", {}))
                users_stats.update(data.get("stats", {}))
                transactions.update(data.get("transactions", {}))
                users_username.update(data.get("username", {}))
                users_join_date.update(data.get("join_date", {}))
                users_ban.update(data.get("ban", {}))
                users_ban_reason.update(data.get("ban_reason", {}))
                users_verify.update(data.get("verify", {}))
                promo_codes.update(data.get("promo_codes", {}))
                bot_stats.update(data.get("bot_stats", {}))
                bot_settings.update(data.get("bot_settings", {}))
            logger.info("✅ Данные восстановлены из backup.json")
        except:
            logger.warning("⚠️ Не удалось загрузить backup.json")
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())