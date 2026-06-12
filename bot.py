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
CRASH_HOUSE_EDGE = 0.95
MINES_BOARD_SIZE = 5
MINES_MINES_COUNT = 5
BLACKJACK_DECK_SIZE = 6  # Количество колод

# Реферальная система
REFERRAL_BONUS_PERCENT = 10
REFERRAL_SIGNUP_BONUS = 5
REFERRAL_INVITE_BONUS = 10

# Системные настройки
MIN_BET = 1
MAX_BET = 10000
DAILY_BONUS_MIN = 5
DAILY_BONUS_MAX = 25

# Сообщения после выигрыша
WIN_MESSAGES = [
    "🎉 ПОЗДРАВЛЯЮ! 🎉",
    "💰 ШИКАРНЫЙ ВЫИГРЫШ! 💰",
    "🏆 ВЫ ВЕЛИКИ! 🏆",
    "✨ ФАНТАСТИЧЕСКАЯ ПОБЕДА! ✨",
    "🔥 В ОГНЕ! 🔥",
    "💎 ДЖЕКПОТ! 💎",
    "🚀 ВЫ ЛЕТИТЕ К ЗВЁЗДАМ! 🚀",
    "⭐️ ЛЕГЕНДАРНЫЙ ВЫИГРЫШ! ⭐️",
    "🎰 УДАЧА НА ВАШЕЙ СТОРОНЕ! 🎰",
    "💪 ВЕЛИКОЛЕПНО! 💪"
]

LOSS_MESSAGES = [
    "😢 В следующий раз повезёт!",
    "💪 Не сдавайтесь! Удача придёт!",
    "🎲 Фортуна переменчива...",
    "⭐️ Продолжайте играть - выигрыш близко!",
    "🔥 Следующая ставка будет удачной!",
    "💎 Не отчаивайтесь!",
    "🎯 Попробуйте ещё раз!",
    "🚀 Удача уже в пути!"
]

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
users_admin_notes: Dict[int, str] = {}

# Игровые данные
active_crash: Dict[int, dict] = {}
active_mines: Dict[int, dict] = {}
active_blackjack: Dict[int, dict] = {}

# История игр
crash_history: List[dict] = []
mines_history: List[dict] = []
blackjack_history: List[dict] = []

# Промокоды
promo_codes: Dict[str, dict] = {}

# Системные уведомления
system_announcements: List[dict] = []
pending_withdrawals: Dict[int, dict] = {}

# Статистика бота
bot_stats = {
    "total_users": 0,
    "active_today": 0,
    "active_this_week": 0,
    "total_bets": 0,
    "total_wagered": 0.0,
    "total_paid": 0.0,
    "total_profit": 0.0,
    "total_deposits": 0,
    "total_deposit_amount": 0.0,
    "total_withdrawals": 0,
    "total_withdrawal_amount": 0.0,
    "crash_games_played": 0,
    "mines_games_played": 0,
    "blackjack_games_played": 0,
    "server_start_time": datetime.now().isoformat(),
    "daily_active_history": {}
}

# Настройки бота
bot_settings = {
    "maintenance_mode": False,
    "min_bet": MIN_BET,
    "max_bet": MAX_BET,
    "crash_max_multiplier": CRASH_MAX_MULTIPLIER,
    "crash_house_edge": CRASH_HOUSE_EDGE,
    "mines_board_size": MINES_BOARD_SIZE,
    "mines_count": MINES_MINES_COUNT,
    "referral_percent": REFERRAL_BONUS_PERCENT,
    "daily_bonus_enabled": True,
    "daily_bonus_min": DAILY_BONUS_MIN,
    "daily_bonus_max": DAILY_BONUS_MAX,
    "chat_link": "https://t.me/starplay_chat",
    "channel_link": "https://t.me/starplay_news",
    "support_link": "https://t.me/starplay_support",
    "auto_backup_enabled": True,
    "auto_backup_interval": 3600,
    "min_withdraw": 100,
    "max_withdraw": 10000
}

# Анти-спам
user_last_command: Dict[int, float] = {}
user_daily_bets: Dict[int, int] = {}
user_daily_bets_date: Dict[int, str] = {}

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
    blackjack_bet = State()
    blackjack_playing = State()
    custom_deposit = State()
    custom_withdraw = State()
    admin_find_user = State()
    admin_change_balance = State()
    admin_send_broadcast = State()
    admin_send_broadcast_confirm = State()
    admin_ban_user = State()
    admin_unban_user = State()
    admin_set_verify = State()
    admin_promo_create = State()
    admin_promo_amount = State()
    admin_global_bonus = State()
    admin_announcement = State()
    admin_settings_game = State()
    admin_edit_note = State()
    admin_withdraw_approve = State()


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
    elif tx_type == "withdraw":
        bot_stats["total_withdrawals"] += 1
        bot_stats["total_withdrawal_amount"] += amount
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
            "blackjack_games": 0, "blackjack_wins": 0, "blackjack_best_win": 0.0,
            "total_deposits": 0, "total_deposit_amount": 0.0,
            "total_withdrawals": 0, "total_withdrawal_amount": 0.0,
            "referral_count": 0, "referral_earned": 0.0,
            "daily_bonus_count": 0, "daily_bonus_streak": 0,
            "biggest_win": 0.0
        }
    return users_stats[user_id]

def get_random_emoji() -> str:
    emojis = ["🎲", "🎯", "⚡️", "💫", "🌟", "⭐️", "✨", "🎮", "🎰", "🔥", "💰", "💎", "🏆", "🎉", "🚀", "💪", "🎊", "🥳"]
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

def format_number(num: float) -> str:
    if num >= 1000000:
        return f"{num/1000000:.1f}M"
    elif num >= 1000:
        return f"{num/1000:.1f}K"
    return f"{num:.2f}"

def get_random_win_message() -> str:
    return random.choice(WIN_MESSAGES)

def get_random_loss_message() -> str:
    return random.choice(LOSS_MESSAGES)

def check_anti_spam(user_id: int, cooldown: int = 1) -> bool:
    now = time.time()
    if user_id in user_last_command:
        if now - user_last_command[user_id] < cooldown:
            return False
    user_last_command[user_id] = now
    return True

def update_active_users():
    today = datetime.now().date().isoformat()
    if today not in bot_stats["daily_active_history"]:
        bot_stats["daily_active_history"][today] = 0
    bot_stats["active_today"] = len([u for u in users_last_seen if users_last_seen[u].startswith(today)])


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
    builder.button(text="📢 Новости")
    
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
    builder.button(text="⚙️ Настройки игр")
    builder.button(text="🎁 Создать промокод")
    builder.button(text="🎲 Глобальный бонус")
    builder.button(text="📢 Анонс")
    builder.button(text="💾 Сохранить данные")
    builder.button(text="📤 Вывод средств")
    builder.button(text="🔙 В главное меню")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_games_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📈 CRASH")
    builder.button(text="💣 MINES")
    builder.button(text="♠️ BLACKJACK")
    builder.button(text="📊 История игр")
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
        [InlineKeyboardButton(text="⭐️ 2500", callback_data="crash_bet_2500"),
         InlineKeyboardButton(text="⭐️ 5000", callback_data="crash_bet_5000"),
         InlineKeyboardButton(text="⭐️ 10000", callback_data="crash_bet_10000")],
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
        [InlineKeyboardButton(text="⭐️ 2500", callback_data="mines_bet_2500"),
         InlineKeyboardButton(text="⭐️ 5000", callback_data="mines_bet_5000"),
         InlineKeyboardButton(text="⭐️ 10000", callback_data="mines_bet_10000")],
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

def get_blackjack_bet_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐️ 1", callback_data="blackjack_bet_1"),
         InlineKeyboardButton(text="⭐️ 5", callback_data="blackjack_bet_5"),
         InlineKeyboardButton(text="⭐️ 10", callback_data="blackjack_bet_10")],
        [InlineKeyboardButton(text="⭐️ 25", callback_data="blackjack_bet_25"),
         InlineKeyboardButton(text="⭐️ 50", callback_data="blackjack_bet_50"),
         InlineKeyboardButton(text="⭐️ 100", callback_data="blackjack_bet_100")],
        [InlineKeyboardButton(text="⭐️ 250", callback_data="blackjack_bet_250"),
         InlineKeyboardButton(text="⭐️ 500", callback_data="blackjack_bet_500"),
         InlineKeyboardButton(text="⭐️ 1000", callback_data="blackjack_bet_1000")],
        [InlineKeyboardButton(text="⭐️ 2500", callback_data="blackjack_bet_2500"),
         InlineKeyboardButton(text="⭐️ 5000", callback_data="blackjack_bet_5000"),
         InlineKeyboardButton(text="⭐️ 10000", callback_data="blackjack_bet_10000")],
        [InlineKeyboardButton(text="✏️ Своя сумма", callback_data="blackjack_bet_custom")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_games")]
    ])

def get_blackjack_game_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎴 ВЗЯТЬ КАРТУ", callback_data="blackjack_hit"),
         InlineKeyboardButton(text="✋ ОСТАНОВИТЬСЯ", callback_data="blackjack_stand")],
        [InlineKeyboardButton(text="💰 УДВОИТЬ", callback_data="blackjack_double")],
        [InlineKeyboardButton(text="❌ ВЫЙТИ", callback_data="blackjack_exit")]
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
        [InlineKeyboardButton(text="📤 Запросить вывод", callback_data="withdraw_request")],
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
    update_active_users()
    
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
                    await message.answer(f"✅ Вы получили {format_stars(REFERRAL_SIGNUP_BONUS)} за регистрацию по ссылке!")
                    try:
                        await bot.send_message(referrer_id, f"🎉 По вашей ссылке зарегистрировался @{username or user_id}!\n+{format_stars(REFERRAL_INVITE_BONUS)}", parse_mode=ParseMode.HTML)
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
        f"♠️ BLACKJACK — Классический блэкджек 21\n\n"
        f"<b>💫 Как начать:</b>\n"
        f"1️⃣ Пополните баланс\n"
        f"2️⃣ Выберите игру\n"
        f"3️⃣ Делайте ставки и выигрывайте!\n\n"
        f"<b>🎁 Бонусы:</b>\n"
        f"• Ежедневный бонус до {DAILY_BONUS_MAX} Stars\n"
        f"• Реферальная программа: +{REFERRAL_BONUS_PERCENT}% от пополнений\n"
        f"• Промокоды и розыгрыши\n\n"
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
        f"♠️ BLACKJACK — Соберите 21 очко и победите дилера!\n\n"
        f"<b>💰 Баланс:</b>\n"
        f"• Пополнение через Telegram Stars\n"
        f"• Вывод средств через администратора\n"
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
        f"• Канал: {bot_settings['channel_link']}\n"
        f"• Поддержка: {bot_settings['support_link']}"
    )
    await message.answer(help_text, parse_mode=ParseMode.HTML)


# ===================== ГЛАВНЫЕ КНОПКИ =====================
@dp.message(F.text == "💰 Баланс")
async def balance_reply(message: Message):
    user_id = message.from_user.id
    stats = get_user_stats(user_id)
    await message.answer(
        f"💰 <b>Ваш баланс</b>\n\n"
        f"{format_stars(get_user_balance(user_id))}\n\n"
        f"📊 <b>Краткая статистика:</b>\n"
        f"• Сыграно игр: {stats['games_played']}\n"
        f"• Побед: {stats['games_won']}\n"
        f"• Выиграно: {format_stars(stats['total_won'])}\n"
        f"• Рекорд: {format_stars(stats['biggest_win'])}\n\n"
        f"💡 Приглашайте друзей и зарабатывайте больше!",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text == "⭐️ Пополнить")
async def deposit_reply(message: Message):
    await message.answer(
        "⭐️ <b>Пополнение баланса</b>\n\n"
        "💰 <b>Способы пополнения:</b>\n"
        "• Telegram Stars — мгновенно\n\n"
        "💡 <b>Выберите сумму:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_deposit_keyboard()
    )

@dp.message(F.text == "🎮 Игры")
async def games_reply(message: Message):
    await message.answer(
        "🎮 <b>Выберите игру</b>\n\n"
        "📈 <b>CRASH</b> — Рискни и умножь ставку до x1000!\n"
        "💣 <b>MINES</b> — Найди сокровища, избегая мин\n"
        "♠️ <b>BLACKJACK</b> — Сыграй в классический блэкджек\n\n"
        "👇 <b>Нажмите на кнопку с игрой:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )

@dp.message(F.text == "👥 Рефералы")
async def referrals_reply(message: Message):
    user_id = message.from_user.id
    ref_link = generate_referral_link(user_id)
    stats = get_user_stats(user_id)
    text = (
        f"👥 <b>Реферальная программа</b>\n\n"
        f"🏆 <b>Ваша статистика:</b>\n"
        f"• Приглашено: {stats['referral_count']} чел.\n"
        f"• Заработано: {format_stars(stats['referral_earned'])}\n\n"
        f"<b>📋 Как это работает:</b>\n"
        f"• Друг регистрируется по вашей ссылке\n"
        f"• Он получает +{REFERRAL_SIGNUP_BONUS} Stars\n"
        f"• Вы получаете +{REFERRAL_INVITE_BONUS} Stars\n"
        f"• Вы получаете {REFERRAL_BONUS_PERCENT}% от пополнений друга\n\n"
        f"<b>🔗 Ваша реферальная ссылка:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"💡 Поделитесь ссылкой с друзьями и зарабатывайте!"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться ссылкой", url=f"https://t.me/share/url?url={ref_link}&text=StarPlay — лучшие игры с выигрышами! Присоединяйся!")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

@dp.message(F.text == "🏆 Топ")
async def top_reply(message: Message):
    sorted_users = sorted(users_balance.items(), key=lambda x: x[1], reverse=True)[:15]
    sorted_wins = sorted(users_stats.items(), key=lambda x: x[1].get("games_won", 0), reverse=True)[:15]
    
    if not sorted_users:
        await message.answer("🏆 Пока нет игроков в рейтинге!")
        return
    
    top_text = "🏆 <b>ТОП-15 ПО БАЛАНСУ</b>\n\n"
    for idx, (uid, bal) in enumerate(sorted_users, 1):
        if users_ban.get(uid, False):
            continue
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
        uname = users_username.get(uid, str(uid))
        name = f"@{uname}" if uname else str(uid)
        top_text += f"{medal} {name} — {bal:.2f} ⭐️\n"
    
    top_text += "\n🏆 <b>ТОП-15 ПО ПОБЕДАМ</b>\n\n"
    for idx, (uid, stats) in enumerate(sorted_wins, 1):
        if users_ban.get(uid, False):
            continue
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
        uname = users_username.get(uid, str(uid))
        name = f"@{uname}" if uname else str(uid)
        top_text += f"{medal} {name} — {stats.get('games_won', 0)} 🏆\n"
    
    await message.answer(top_text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "📊 Профиль")
async def profile_reply(message: Message):
    uid = message.from_user.id
    stats = get_user_stats(uid)
    win_rate = (stats['games_won'] / max(stats['games_played'], 1)) * 100
    balance = get_user_balance(uid)
    total_profit = stats['total_won'] - stats['total_lost']
    
    text = (
        f"👤 <b>Профиль игрока</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👤 Username: @{message.from_user.username or 'нет'}\n"
        f"📅 Регистрация: {users_join_date.get(uid, 'неизвестно')}\n"
        f"✅ Верификация: {'✅ Да' if users_verify.get(uid, False) else '❌ Нет'}\n\n"
        f"💰 <b>Баланс:</b> {format_stars(balance)}\n\n"
        f"📊 <b>Общая статистика:</b>\n"
        f"├ 🎮 Сыграно: {stats['games_played']}\n"
        f"├ 🏆 Побед: {stats['games_won']}\n"
        f"├ 📈 Винрейт: {win_rate:.1f}%\n"
        f"├ 💎 Выиграно: {format_stars(stats['total_won'])}\n"
        f"├ 💸 Проиграно: {format_stars(stats['total_lost'])}\n"
        f"├ 💰 Чистая прибыль: {format_stars(total_profit)}\n"
        f"└ 🏅 Рекордный выигрыш: {format_stars(stats['biggest_win'])}\n\n"
        f"📈 <b>По играм:</b>\n"
        f"├ 📈 CRASH: {stats['crash_wins']}/{stats['crash_games']} побед\n"
        f"├ 💣 MINES: {stats['mines_wins']}/{stats['mines_games']} побед\n"
        f"├ ♠️ BLACKJACK: {stats['blackjack_wins']}/{stats['blackjack_games']} побед\n"
        f"├ 📈 Лучший множитель CRASH: x{stats['crash_best_multiplier']:.2f}\n"
        f"└ 💎 Лучший множитель MINES: x{stats['mines_best_multiplier']:.2f}\n\n"
        f"👥 <b>Рефералы:</b> {stats['referral_count']} чел., заработано: {format_stars(stats['referral_earned'])}"
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
    
    await message.answer(
        f"🎉 <b>Ежедневный бонус получен!</b> 🎉\n\n"
        f"+{format_stars(bonus)}\n"
        f"📅 Стрик: {streak} дней\n\n"
        f"💡 Завтра бонус будет ещё больше!\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text == "❓ Помощь")
async def help_reply(message: Message):
    await cmd_help(message)

@dp.message(F.text == "📢 Новости")
async def news_reply(message: Message):
    if system_announcements:
        last_news = system_announcements[-1]
        await message.answer(
            f"📢 <b>Последние новости</b>\n\n"
            f"{last_news['message']}\n\n"
            f"📅 {last_news['date']}",
            parse_mode=ParseMode.HTML
        )
    else:
        await message.answer("📢 Новостей пока нет. Следите за обновлениями!", parse_mode=ParseMode.HTML)


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
                f"💎 Потенциальный выигрыш: {format_stars(bet * multiplier)}\n\n"
                f"⚠️ Заберите выигрыш до взрыва!\n"
                f"🎯 Максимальный множитель: x{crash_point:.2f}",
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
                f"📈 Множитель в момент взрыва: x{multiplier:.2f}\n\n"
                f"{get_random_loss_message()}\n\n"
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
        await message.answer("⚠️ У вас уже есть активная игра!\nЗаберите выигрыш или дождитесь окончания.", parse_mode=ParseMode.HTML)
        return
    await state.set_state(GameStates.crash_bet)
    await message.answer(
        "📈 <b>CRASH</b>\n\n"
        "📋 <b>Правила игры:</b>\n"
        "• Вы делаете ставку\n"
        "• Множитель начинает расти\n"
        "• Нужно забрать выигрыш ДО взрыва\n"
        "• Если не забрали — ставка сгорает\n"
        f"• Максимальный множитель: x{CRASH_MAX_MULTIPLIER}\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Всего сыграно: {bot_stats['crash_games_played']} игр\n"
        f"• Текущий банк: {format_stars(sum(users_balance.values()))}\n\n"
        f"💰 <b>Выберите сумму ставки:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_crash_bet_keyboard()
    )

@dp.callback_query(F.data.startswith("crash_bet_"))
async def crash_bet(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    bet_str = callback.data.split("_")[-1]
    
    if not check_anti_spam(user_id):
        await callback.answer("⏳ Подождите секунду перед следующей ставкой!", show_alert=True)
        return
    
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
        await callback.answer(f"❌ Ставка должна быть от {MIN_BET} до {MAX_BET} Stars!", show_alert=True)
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
        f"📈 <b>CRASH — ИГРА НАЧАЛАСЬ!</b>\n\n"
        f"💰 Ваша ставка: {format_stars(bet)}\n"
        f"📈 Текущий множитель: x1.00\n"
        f"💎 Потенциальный выигрыш: {format_stars(bet)}\n\n"
        f"⚠️ Множитель растёт! Заберите выигрыш до взрыва!",
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
    if win > stats["biggest_win"]:
        stats["biggest_win"] = win
    if game["multiplier"] > stats["crash_best_multiplier"]:
        stats["crash_best_multiplier"] = game["multiplier"]
    save_transaction(user_id, win, "game_win", f"Crash x{game['multiplier']:.2f}", "crash")
    bot_stats["crash_games_played"] += 1
    crash_history.append({"multiplier": game["multiplier"], "player": user_id, "bet": game["bet"], "win": win, "timestamp": datetime.now().isoformat()})
    if len(crash_history) > 100:
        crash_history.pop(0)
    del active_crash[user_id]
    await state.clear()
    
    win_message = get_random_win_message()
    profit = win - game["bet"]
    
    await callback.message.edit_text(
        f"{win_message}\n\n"
        f"📈 <b>CRASH — ВЫ ПОБЕДИЛИ!</b>\n\n"
        f"💰 Ваша ставка: {format_stars(game['bet'])}\n"
        f"📈 Множитель: <b>x{game['multiplier']:.2f}</b>\n"
        f"🎉 Чистый выигрыш: <b>+{format_stars(profit)}</b>\n"
        f"🏆 Общий выигрыш: {format_stars(win)}\n\n"
        f"{get_random_emoji()} <b>Поздравляем!</b> {get_random_emoji()}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "crash_exit")
async def crash_exit(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id in active_crash:
        del active_crash[user_id]
    await state.clear()
    await callback.message.edit_text(
        "❌ Вы вышли из игры.\n\n"
        "💰 Ваш баланс не изменился.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
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
        await message.answer("⚠️ У вас уже есть активная игра!\nЗаберите выигрыш или завершите игру.", parse_mode=ParseMode.HTML)
        return
    await state.set_state(GameStates.mines_bet)
    await message.answer(
        "💣 <b>MINES — Сапёр</b>\n\n"
        "📋 <b>Правила игры:</b>\n"
        f"• Поле {MINES_BOARD_SIZE}x{MINES_BOARD_SIZE}\n"
        f"• Спрятано {MINES_MINES_COUNT} мин\n"
        "• Каждая найденная 💎 увеличивает множитель x1.2\n"
        "• Наступите на 💣 — проигрыш\n"
        "• Можно забрать выигрыш в любой момент\n"
        f"• Максимальный множитель: x{1.2 ** 20:.1f}\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Всего сыграно: {bot_stats['mines_games_played']} игр\n\n"
        f"💰 <b>Выберите сумму ставки:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_mines_bet_keyboard()
    )

@dp.callback_query(F.data.startswith("mines_bet_"))
async def mines_bet(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    bet_str = callback.data.split("_")[-1]
    
    if not check_anti_spam(user_id):
        await callback.answer("⏳ Подождите секунду перед следующей ставкой!", show_alert=True)
        return
    
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
    max_cells = MINES_BOARD_SIZE * MINES_BOARD_SIZE - MINES_MINES_COUNT
    await callback.message.edit_text(
        f"💣 <b>MINES — ИГРА</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"✨ Множитель: x1.0\n"
        f"📦 Открыто: 0/{max_cells}\n"
        f"💎 Текущий выигрыш: {format_stars(bet)}\n"
        f"🎯 Максимальный выигрыш: {format_stars(bet * (1.2 ** max_cells))}\n\n"
        f"👇 <b>Открывайте клетки и находите 💎!</b>",
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
            f"💥 <b>MINES — ПРОИГРЫШ!</b>\n\n"
            f"💣 Вы наступили на мину!\n\n"
            f"{get_random_loss_message()}\n\n"
            f"💰 Ставка: {format_stars(game['bet'])} — проиграна\n"
            f"✨ Множитель в момент проигрыша: x{game['multiplier']:.2f}\n\n"
            f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
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
            if current_win > stats["biggest_win"]:
                stats["biggest_win"] = current_win
            if game["multiplier"] > stats["mines_best_multiplier"]:
                stats["mines_best_multiplier"] = game["multiplier"]
            save_transaction(user_id, current_win, "game_win", f"Mines победа x{game['multiplier']:.1f}", "mines")
            bot_stats["mines_games_played"] += 1
            mines_history.append({"multiplier": game["multiplier"], "player": user_id, "bet": game["bet"], "win": current_win, "timestamp": datetime.now().isoformat()})
            if len(mines_history) > 100:
                mines_history.pop(0)
            del active_mines[user_id]
            
            win_message = get_random_win_message()
            profit = current_win - game["bet"]
            
            await callback.message.edit_text(
                f"{win_message}\n\n"
                f"💣 <b>MINES — ПОЛНАЯ ПОБЕДА!</b>\n\n"
                f"💰 Ставка: {format_stars(game['bet'])}\n"
                f"✨ Множитель: x{game['multiplier']:.2f}\n"
                f"🎉 Чистый выигрыш: <b>+{format_stars(profit)}</b>\n"
                f"🏆 Общий выигрыш: {format_stars(current_win)}\n"
                f"📦 Открыто: {game['cells_opened']}/{max_cells} клеток\n\n"
                f"🌟 <b>Вы нашли все сокровища!</b> 🌟\n\n"
                f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_games_keyboard()
            )
        else:
            await callback.message.edit_text(
                f"💣 <b>MINES — ИГРА</b>\n\n"
                f"💰 Ставка: {format_stars(game['bet'])}\n"
                f"✨ Множитель: x{game['multiplier']:.2f}\n"
                f"📦 Открыто: {game['cells_opened']}/{max_cells}\n"
                f"💎 Текущий выигрыш: {format_stars(current_win)}\n"
                f"🎯 Максимальный выигрыш: {format_stars(game['bet'] * (1.2 ** max_cells))}\n\n"
                f"✅ <b>Вы нашли 💎! Множитель увеличен!</b>\n\n"
                f"👇 <b>Продолжайте открывать или заберите выигрыш!</b>",
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
    if win > stats["biggest_win"]:
        stats["biggest_win"] = win
    if game["multiplier"] > stats["mines_best_multiplier"]:
        stats["mines_best_multiplier"] = game["multiplier"]
    save_transaction(user_id, win, "game_win", f"Mines кэшаут x{game['multiplier']:.1f}", "mines")
    bot_stats["mines_games_played"] += 1
    mines_history.append({"multiplier": game["multiplier"], "player": user_id, "bet": game["bet"], "win": win, "timestamp": datetime.now().isoformat()})
    if len(mines_history) > 100:
        mines_history.pop(0)
    del active_mines[user_id]
    
    win_message = get_random_win_message()
    profit = win - game["bet"]
    
    await callback.message.edit_text(
        f"{win_message}\n\n"
        f"💣 <b>MINES — ВЫ ЗАБРАЛИ ВЫИГРЫШ!</b>\n\n"
        f"💰 Ставка: {format_stars(game['bet'])}\n"
        f"✨ Множитель: x{game['multiplier']:.2f}\n"
        f"📦 Открыто клеток: {game['cells_opened']}\n"
        f"🎉 Чистый выигрыш: <b>+{format_stars(profit)}</b>\n"
        f"🏆 Общий выигрыш: {format_stars(win)}\n\n"
        f"{get_random_emoji()} <b>Отличная игра!</b> {get_random_emoji()}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "mines_exit")
async def mines_exit(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id in active_mines:
        del active_mines[user_id]
    await state.clear()
    await callback.message.edit_text(
        "❌ Вы вышли из игры.\n\n"
        "💰 Ваш баланс не изменился.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()


# ===================== ИГРА BLACKJACK =====================
def create_deck():
    suits = ['♠️', '♥️', '♣️', '♦️']
    values = {'2':2, '3':3, '4':4, '5':5, '6':6, '7':7, '8':8, '9':9, '10':10, 'J':10, 'Q':10, 'K':10, 'A':11}
    deck = []
    for suit in suits:
        for value in values:
            deck.append({'value': value, 'suit': suit, 'points': values[value]})
    return deck * BLACKJACK_DECK_SIZE

def get_card_value(card):
    return card['points']

def calculate_hand(hand):
    total = sum(get_card_value(card) for card in hand)
    aces = sum(1 for card in hand if card['value'] == 'A')
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total

def format_card(card):
    return f"{card['value']}{card['suit']}"

@dp.message(F.text == "♠️ BLACKJACK")
async def blackjack_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in active_blackjack:
        await message.answer("⚠️ У вас уже есть активная игра!\nЗавершите текущую игру.", parse_mode=ParseMode.HTML)
        return
    await state.set_state(GameStates.blackjack_bet)
    await message.answer(
        "♠️ <b>BLACKJACK — 21</b>\n\n"
        "📋 <b>Правила игры:</b>\n"
        "• Соберите 21 очко или больше, чем у дилера\n"
        "• Карты: 2-10 по номиналу, J/Q/K = 10, A = 1 или 11\n"
        "• Дилер обязан брать до 17 очков\n"
        "• Выигрыш: x2, Блэкджек: x2.5\n"
        "• Можно удвоить ставку\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Всего сыграно: {bot_stats['blackjack_games_played']} игр\n\n"
        f"💰 <b>Выберите сумму ставки:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_blackjack_bet_keyboard()
    )

@dp.callback_query(F.data.startswith("blackjack_bet_"))
async def blackjack_bet(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    bet_str = callback.data.split("_")[-1]
    
    if not check_anti_spam(user_id):
        await callback.answer("⏳ Подождите секунду перед следующей ставкой!", show_alert=True)
        return
    
    if bet_str == "custom":
        await callback.message.answer("✏️ Введите сумму ставки (1-10000):", parse_mode=ParseMode.HTML)
        await state.set_state(GameStates.blackjack_bet)
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
    save_transaction(user_id, -bet, "bet", f"Blackjack ставка", "blackjack")
    
    deck = create_deck()
    random.shuffle(deck)
    
    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]
    
    active_blackjack[user_id] = {
        "bet": bet,
        "deck": deck,
        "player_hand": player_hand,
        "dealer_hand": dealer_hand,
        "double": False
    }
    
    await state.set_state(GameStates.blackjack_playing)
    
    player_score = calculate_hand(player_hand)
    dealer_card = format_card(dealer_hand[0])
    
    await callback.message.edit_text(
        f"♠️ <b>BLACKJACK — ИГРА</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n\n"
        f"🃏 <b>Ваши карты:</b> {', '.join(format_card(c) for c in player_hand)} = {player_score}\n"
        f"🃏 <b>Карты дилера:</b> [{dealer_card}, ?]\n\n"
        f"👇 <b>Ваш ход:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_blackjack_game_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "blackjack_hit")
async def blackjack_hit(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_blackjack:
        await callback.answer("Игра не найдена!", show_alert=True)
        return
    
    game = active_blackjack[user_id]
    game["player_hand"].append(game["deck"].pop())
    player_score = calculate_hand(game["player_hand"])
    
    if player_score > 21:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["blackjack_games"] += 1
        stats["total_lost"] += game["bet"]
        save_transaction(user_id, -game["bet"], "game_loss", "Blackjack перебор", "blackjack")
        bot_stats["blackjack_games_played"] += 1
        blackjack_history.append({"player": user_id, "bet": game["bet"], "win": 0, "timestamp": datetime.now().isoformat()})
        if len(blackjack_history) > 100:
            blackjack_history.pop(0)
        del active_blackjack[user_id]
        
        await callback.message.edit_text(
            f"♠️ <b>BLACKJACK — ПЕРЕБОР!</b>\n\n"
            f"💥 У вас {player_score} очков!\n\n"
            f"{get_random_loss_message()}\n\n"
            f"💰 Ставка: {format_stars(game['bet'])} — проиграна\n"
            f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_games_keyboard()
        )
    else:
        dealer_card = format_card(game["dealer_hand"][0])
        await callback.message.edit_text(
            f"♠️ <b>BLACKJACK — ИГРА</b>\n\n"
            f"💰 Ставка: {format_stars(game['bet'])}\n\n"
            f"🃏 <b>Ваши карты:</b> {', '.join(format_card(c) for c in game['player_hand'])} = {player_score}\n"
            f"🃏 <b>Карты дилера:</b> [{dealer_card}, ?]\n\n"
            f"👇 <b>Ваш ход:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_blackjack_game_keyboard()
        )
    await callback.answer()

@dp.callback_query(F.data == "blackjack_stand")
async def blackjack_stand(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_blackjack:
        await callback.answer("Игра не найдена!", show_alert=True)
        return
    
    game = active_blackjack[user_id]
    player_score = calculate_hand(game["player_hand"])
    dealer_score = calculate_hand(game["dealer_hand"])
    
    while dealer_score < 17:
        game["dealer_hand"].append(game["deck"].pop())
        dealer_score = calculate_hand(game["dealer_hand"])
    
    is_blackjack = len(game["player_hand"]) == 2 and player_score == 21
    multiplier = 2.5 if is_blackjack else 2
    
    if dealer_score > 21 or player_score > dealer_score:
        win = game["bet"] * multiplier
        update_balance(user_id, win)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["blackjack_games"] += 1
        stats["blackjack_wins"] += 1
        stats["total_won"] += win
        if win > stats["biggest_win"]:
            stats["biggest_win"] = win
        save_transaction(user_id, win, "game_win", f"Blackjack победа", "blackjack")
        result_text = f"🎉 <b>ВЫ ПОБЕДИЛИ!</b>\n🎉 Чистый выигрыш: +{format_stars(win - game['bet'])}"
        win_message = get_random_win_message()
    elif player_score == dealer_score:
        update_balance(user_id, game["bet"])
        result_text = f"🔄 <b>НИЧЬЯ!</b>\n💰 Ставка возвращена"
        win_message = "🤝 Ничья!"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["blackjack_games"] += 1
        stats["total_lost"] += game["bet"]
        save_transaction(user_id, -game["bet"], "game_loss", "Blackjack проигрыш", "blackjack")
        result_text = f"😢 <b>ВЫ ПРОИГРАЛИ!</b>\n💸 Потеряно: {format_stars(game['bet'])}"
        win_message = get_random_loss_message()
    
    bot_stats["blackjack_games_played"] += 1
    blackjack_history.append({"player": user_id, "bet": game["bet"], "win": win if 'win' in locals() else 0, "timestamp": datetime.now().isoformat()})
    if len(blackjack_history) > 100:
        blackjack_history.pop(0)
    del active_blackjack[user_id]
    
    await callback.message.edit_text(
        f"♠️ <b>BLACKJACK — РЕЗУЛЬТАТ</b>\n\n"
        f"{win_message}\n\n"
        f"💰 Ставка: {format_stars(game['bet'])}\n"
        f"🃏 <b>Ваши карты:</b> {', '.join(format_card(c) for c in game['player_hand'])} = {player_score}\n"
        f"🃏 <b>Карты дилера:</b> {', '.join(format_card(c) for c in game['dealer_hand'])} = {dealer_score}\n\n"
        f"{result_text}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "blackjack_double")
async def blackjack_double(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_blackjack:
        await callback.answer("Игра не найдена!", show_alert=True)
        return
    
    game = active_blackjack[user_id]
    
    if get_user_balance(user_id) < game["bet"]:
        await callback.answer(f"❌ Не хватает {format_stars(game['bet'])} для удвоения!", show_alert=True)
        return
    
    if len(game["player_hand"]) != 2:
        await callback.answer("❌ Удвоить можно только на первых двух картах!", show_alert=True)
        return
    
    update_balance(user_id, -game["bet"])
    game["bet"] *= 2
    game["double"] = True
    
    game["player_hand"].append(game["deck"].pop())
    player_score = calculate_hand(game["player_hand"])
    dealer_score = calculate_hand(game["dealer_hand"])
    
    while dealer_score < 17:
        game["dealer_hand"].append(game["deck"].pop())
        dealer_score = calculate_hand(game["dealer_hand"])
    
    if player_score > 21:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["blackjack_games"] += 1
        stats["total_lost"] += game["bet"]
        save_transaction(user_id, -game["bet"], "game_loss", "Blackjack перебор", "blackjack")
        result_text = f"😢 <b>ПЕРЕБОР!</b>\n💸 Потеряно: {format_stars(game['bet'])}"
        win_message = get_random_loss_message()
    elif dealer_score > 21 or player_score > dealer_score:
        win = game["bet"] * 2
        update_balance(user_id, win)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["blackjack_games"] += 1
        stats["blackjack_wins"] += 1
        stats["total_won"] += win
        if win > stats["biggest_win"]:
            stats["biggest_win"] = win
        save_transaction(user_id, win, "game_win", f"Blackjack победа x2", "blackjack")
        result_text = f"🎉 <b>ВЫ ПОБЕДИЛИ!</b>\n🎉 Чистый выигрыш: +{format_stars(win - game['bet'])}"
        win_message = get_random_win_message()
    elif player_score == dealer_score:
        update_balance(user_id, game["bet"])
        result_text = f"🔄 <b>НИЧЬЯ!</b>\n💰 Ставка возвращена"
        win_message = "🤝 Ничья!"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["blackjack_games"] += 1
        stats["total_lost"] += game["bet"]
        save_transaction(user_id, -game["bet"], "game_loss", "Blackjack проигрыш", "blackjack")
        result_text = f"😢 <b>ВЫ ПРОИГРАЛИ!</b>\n💸 Потеряно: {format_stars(game['bet'])}"
        win_message = get_random_loss_message()
    
    bot_stats["blackjack_games_played"] += 1
    del active_blackjack[user_id]
    
    await callback.message.edit_text(
        f"♠️ <b>BLACKJACK — РЕЗУЛЬТАТ</b>\n\n"
        f"{win_message}\n\n"
        f"💰 Ставка: {format_stars(game['bet'])}\n"
        f"🃏 <b>Ваши карты:</b> {', '.join(format_card(c) for c in game['player_hand'])} = {player_score}\n"
        f"🃏 <b>Карты дилера:</b> {', '.join(format_card(c) for c in game['dealer_hand'])} = {dealer_score}\n\n"
        f"{result_text}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "blackjack_exit")
async def blackjack_exit(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id in active_blackjack:
        del active_blackjack[user_id]
    await state.clear()
    await callback.message.edit_text(
        "❌ Вы вышли из игры.\n\n"
        "💰 Ваш баланс не изменился.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()


# ===================== ИСТОРИЯ ИГР =====================
@dp.message(F.text == "📊 История игр")
async def games_history(message: Message):
    user_id = message.from_user.id
    
    user_crash = [g for g in crash_history if g.get("player") == user_id][-5:]
    user_mines = [g for g in mines_history if g.get("player") == user_id][-5:]
    user_blackjack = [g for g in blackjack_history if g.get("player") == user_id][-5:]
    
    history_text = "📊 <b>ИСТОРИЯ ВАШИХ ИГР</b>\n\n"
    
    if user_crash:
        history_text += "<b>📈 CRASH:</b>\n"
        for game in user_crash:
            if game.get("win"):
                history_text += f"• Ставка: {game['bet']:.0f}⭐️ | Множитель: x{game['multiplier']:.2f} | Выигрыш: +{game['win'] - game['bet']:.0f}⭐️\n"
            else:
                history_text += f"• Ставка: {game['bet']:.0f}⭐️ | Множитель: x{game['multiplier']:.2f} | ❌ Проигрыш\n"
        history_text += "\n"
    
    if user_mines:
        history_text += "<b>💣 MINES:</b>\n"
        for game in user_mines:
            if game.get("win"):
                history_text += f"• Ставка: {game['bet']:.0f}⭐️ | Множитель: x{game['multiplier']:.2f} | Выигрыш: +{game['win'] - game['bet']:.0f}⭐️\n"
            else:
                history_text += f"• Ставка: {game['bet']:.0f}⭐️ | Множитель: x{game['multiplier']:.2f} | ❌ Проигрыш\n"
        history_text += "\n"
    
    if user_blackjack:
        history_text += "<b>♠️ BLACKJACK:</b>\n"
        for game in user_blackjack:
            if game.get("win"):
                history_text += f"• Ставка: {game['bet']:.0f}⭐️ | Выигрыш: +{game['win'] - game['bet']:.0f}⭐️\n"
            else:
                history_text += f"• Ставка: {game['bet']:.0f}⭐️ | ❌ Проигрыш\n"
        history_text += "\n"
    
    if not user_crash and not user_mines and not user_blackjack:
        history_text += "📭 У вас пока нет сыгранных игр.\n\n💡 Начните играть, чтобы видеть историю!"
    
    await message.answer(history_text, parse_mode=ParseMode.HTML, reply_markup=get_games_keyboard())


# ===================== АДМИН-ПАНЕЛЬ =====================
@dp.message(F.text == "👑 Админ панель")
async def admin_panel(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ У вас нет доступа к админ-панели!", reply_markup=get_main_keyboard())
        return
    await message.answer(
        "👑 <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n\n"
        "📊 Статистика — просмотр общей статистики\n"
        "💰 Изменить баланс — пополнение/снятие\n"
        "📢 Рассылка — массовая рассылка\n"
        "👥 Пользователи — список всех пользователей\n"
        "🔨 Бан/Разбан — блокировка пользователей\n"
        "✅ Верификация — верификация аккаунтов\n"
        "⚙️ Настройки игр — изменение параметров\n"
        "🎁 Создать промокод — создание промокодов\n"
        "🎲 Глобальный бонус — бонус всем пользователям\n"
        "📢 Анонс — отправка анонса\n"
        "💾 Сохранить данные — резервное копирование\n"
        "📤 Вывод средств — обработка выводов\n\n"
        "👇 <b>Выберите действие:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_main_keyboard()
    )

@dp.message(F.text == "📊 Статистика")
async def admin_stats(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    update_active_users()
    uptime = datetime.now() - datetime.fromisoformat(bot_stats["server_start_time"])
    total_balance = sum(users_balance.values())
    
    text = (
        f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
        f"<b>👥 ПОЛЬЗОВАТЕЛИ:</b>\n"
        f"├ Всего: {bot_stats['total_users']}\n"
        f"├ Активны сегодня: {bot_stats['active_today']}\n"
        f"├ Активны за неделю: {bot_stats['active_this_week']}\n"
        f"└ Забанено: {len([u for u, b in users_ban.items() if b])}\n\n"
        f"<b>💰 ФИНАНСЫ:</b>\n"
        f"├ Общий баланс: {format_stars(total_balance)}\n"
        f"├ Всего ставок: {bot_stats['total_bets']}\n"
        f"├ Объём ставок: {format_stars(bot_stats['total_wagered'])}\n"
        f"├ Выплачено: {format_stars(bot_stats['total_paid'])}\n"
        f"├ Прибыль бота: {format_stars(bot_stats['total_profit'])}\n"
        f"├ Пополнений: {bot_stats['total_deposits']}\n"
        f"├ Сумма пополнений: {format_stars(bot_stats['total_deposit_amount'])}\n"
        f"├ Выводов: {bot_stats['total_withdrawals']}\n"
        f"└ Сумма выводов: {format_stars(bot_stats['total_withdrawal_amount'])}\n\n"
        f"<b>🎮 ИГРЫ:</b>\n"
        f"├ CRASH: {bot_stats['crash_games_played']} игр\n"
        f"├ MINES: {bot_stats['mines_games_played']} игр\n"
        f"└ BLACKJACK: {bot_stats['blackjack_games_played']} игр\n\n"
        f"<b>🕐 СИСТЕМА:</b>\n"
        f"├ Время работы: {format_time(int(uptime.total_seconds()))}\n"
        f"├ Старт: {bot_stats['server_start_time'][:19]}\n"
        f"├ Режим обслуживания: {'Вкл' if bot_settings['maintenance_mode'] else 'Выкл'}\n"
        f"└ Авто-бэкап: {'Вкл' if bot_settings['auto_backup_enabled'] else 'Выкл'}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())

@dp.message(F.text == "💰 Изменить баланс")
async def admin_change_balance_start(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await state.set_state(GameStates.admin_find_user)
    await message.answer(
        "💰 <b>ИЗМЕНЕНИЕ БАЛАНСА</b>\n\n"
        "Введите username (без @) или ID пользователя:\n"
        "Пример: <code>hjklgf1</code> или <code>123456789</code>\n\n"
        "<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(F.text == "📢 Рассылка")
async def admin_broadcast_start(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await state.set_state(GameStates.admin_send_broadcast)
    await message.answer(
        "📢 <b>РАССЫЛКА</b>\n\n"
        "Введите сообщение для рассылки всем пользователям.\n\n"
        "<b>Поддерживается:</b>\n"
        "• Текст\n"
        "• Фото\n"
        "• Видео\n"
        "• Документы\n\n"
        "<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(F.text == "👥 Пользователи")
async def admin_users_list(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    users_list = []
    for uid, uname in users_username.items():
        balance = get_user_balance(uid)
        banned = "🚫" if users_ban.get(uid, False) else "✅"
        verified = "✓" if users_verify.get(uid, False) else "○"
        users_list.append(f"{banned}{verified} @{uname or uid} — {balance:.2f}⭐️")
    
    text = "👥 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ</b>\n\n"
    text += "\n".join(users_list[:50])
    
    if len(users_list) > 50:
        text += f"\n\n... и ещё {len(users_list) - 50} пользователей"
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())

@dp.message(F.text == "🔨 Бан/Разбан")
async def admin_ban_start(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await state.set_state(GameStates.admin_ban_user)
    await message.answer(
        "🔨 <b>БАН ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введите username (без @) или ID пользователя для бана:\n\n"
        "<i>Для разбана используйте ту же команду</i>\n"
        "<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(F.text == "✅ Верификация")
async def admin_verify_start(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await state.set_state(GameStates.admin_set_verify)
    await message.answer(
        "✅ <b>ВЕРИФИКАЦИЯ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введите username (без @) или ID пользователя:\n\n"
        "<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(F.text == "⚙️ Настройки игр")
async def admin_settings_games(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await state.set_state(GameStates.admin_settings_game)
    await message.answer(
        "⚙️ <b>НАСТРОЙКИ ИГР</b>\n\n"
        f"📈 CRASH:\n"
        f"├ Макс. множитель: x{bot_settings['crash_max_multiplier']}\n"
        f"└ House Edge: {(1 - bot_settings['crash_house_edge']) * 100}%\n\n"
        f"💣 MINES:\n"
        f"├ Размер поля: {bot_settings['mines_board_size']}x{bot_settings['mines_board_size']}\n"
        f"└ Количество мин: {bot_settings['mines_count']}\n\n"
        f"♠️ BLACKJACK:\n"
        f"└ Кол-во колод: {BLACKJACK_DECK_SIZE}\n\n"
        f"<b>Для изменения параметров введите команду:</b>\n"
        f"• /set_crash_mult <число>\n"
        f"• /set_crash_edge <процент>\n"
        f"• /set_mines_size <число>\n"
        f"• /set_mines_count <число>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_main_keyboard()
    )
    await state.clear()

@dp.message(F.text == "🎁 Создать промокод")
async def admin_promo_create(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await state.set_state(GameStates.admin_promo_create)
    await message.answer(
        "🎁 <b>СОЗДАНИЕ ПРОМОКОДА</b>\n\n"
        "Введите название промокода (латиницей):\n\n"
        "<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(F.text == "🎲 Глобальный бонус")
async def admin_global_bonus(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await state.set_state(GameStates.admin_global_bonus)
    await message.answer(
        "🎲 <b>ГЛОБАЛЬНЫЙ БОНУС</b>\n\n"
        "Введите сумму бонуса для всех пользователей:\n"
        f"Пример: <code>100</code>\n\n"
        "<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(F.text == "📢 Анонс")
async def admin_announcement(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await state.set_state(GameStates.admin_announcement)
    await message.answer(
        "📢 <b>АНОНС</b>\n\n"
        "Введите текст анонса для всех пользователей:\n\n"
        "<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(F.text == "💾 Сохранить данные")
async def admin_save_data(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    data = {
        "balance": users_balance,
        "referrer": users_referrer,
        "referrals": users_referrals,
        "stats": users_stats,
        "transactions": transactions,
        "username": users_username,
        "join_date": users_join_date,
        "ban": users_ban,
        "verify": users_verify,
        "promo_codes": promo_codes,
        "bot_stats": bot_stats,
        "bot_settings": bot_settings
    }
    
    try:
        with open("backup.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        await message.answer(
            "✅ <b>Данные сохранены!</b>\n\n"
            f"📁 Файл: backup.json\n"
            f"📊 Размер: {len(json.dumps(data))} байт\n"
            f"👥 Пользователей: {len(users_balance)}\n"
            f"💰 Общий баланс: {format_stars(sum(users_balance.values()))}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_main_keyboard()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=get_admin_main_keyboard())

@dp.message(F.text == "📤 Вывод средств")
async def admin_withdraw_list(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    if not pending_withdrawals:
        await message.answer("📤 Нет активных заявок на вывод!", reply_markup=get_admin_main_keyboard())
        return
    
    text = "📤 <b>ЗАЯВКИ НА ВЫВОД</b>\n\n"
    for uid, req in pending_withdrawals.items():
        uname = users_username.get(uid, str(uid))
        text += f"👤 @{uname} — {format_stars(req['amount'])}\n"
        text += f"📅 {req['date']}\n"
        text += f"✅ /approve_{uid} | ❌ /decline_{uid}\n\n"
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())


# ===================== АДМИН FSM ОБРАБОТЧИКИ =====================
@dp.message(GameStates.admin_find_user)
async def admin_find_user(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Операция отменена.", reply_markup=get_admin_main_keyboard())
        return
    
    input_text = message.text.strip().replace("@", "")
    user_id = await get_user_id_by_username(input_text)
    
    if not user_id:
        try:
            user_id = int(input_text)
        except:
            pass
    
    if not user_id or user_id not in users_balance:
        await message.answer("❌ Пользователь не найден! Попробуйте снова.")
        return
    
    await state.update_data(target_user=user_id, target_username=input_text)
    await state.set_state(GameStates.admin_change_balance)
    
    await message.answer(
        f"💰 <b>ИЗМЕНЕНИЕ БАЛАНСА</b>\n\n"
        f"👤 Пользователь: @{input_text}\n"
        f"💰 Текущий баланс: {format_stars(get_user_balance(user_id))}\n\n"
        f"Введите сумму изменения:\n"
        f"• <b>+100</b> — добавить 100 Stars\n"
        f"• <b>-50</b> — снять 50 Stars\n\n"
        f"<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(GameStates.admin_change_balance)
async def admin_change_balance_amount(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Операция отменена.", reply_markup=get_admin_main_keyboard())
        return
    
    data = await state.get_data()
    target_user = data.get("target_user")
    target_username = data.get("target_username")
    
    try:
        amount = float(message.text.strip())
        new_balance = update_balance(target_user, amount)
        try:
            await bot.send_message(
                target_user,
                f"👑 <b>Администратор изменил ваш баланс!</b>\n\n"
                f"{'+' if amount > 0 else ''}{format_stars(amount)}\n"
                f"💰 Новый баланс: {format_stars(new_balance)}\n\n"
                f"📝 Причина: изменение администратором",
                parse_mode=ParseMode.HTML
            )
        except:
            pass
        save_transaction(target_user, amount, "admin_change", f"Админ: {amount}", "admin")
        await state.clear()
        await message.answer(
            f"✅ <b>Баланс изменён!</b>\n\n"
            f"👤 @{target_username}\n"
            f"💰 Изменение: {format_stars(amount)}\n"
            f"💰 Новый баланс: {format_stars(new_balance)}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_main_keyboard()
        )
    except:
        await message.answer("❌ Введите число!")

@dp.message(GameStates.admin_send_broadcast)
async def admin_broadcast_message(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Рассылка отменена.", reply_markup=get_admin_main_keyboard())
        return
    
    await state.update_data(broadcast_msg=message)
    await state.set_state(GameStates.admin_send_broadcast_confirm)
    recipients = [uid for uid in users_balance.keys() if not users_ban.get(uid, False)]
    await message.answer(
        f"📢 <b>ПОДТВЕРЖДЕНИЕ РАССЫЛКИ</b>\n\n"
        f"📨 Получателей: {len(recipients)}\n\n"
        f"Сообщение:\n{message.text if message.text else '[Медиафайл]'}\n\n"
        f"✅ Отправить рассылку?",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ОТПРАВИТЬ", callback_data="broadcast_confirm")],
            [InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="broadcast_cancel")]
        ])
    )

@dp.callback_query(F.data == "broadcast_confirm")
async def admin_broadcast_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg = data.get("broadcast_msg")
    if not msg:
        await callback.answer("Ошибка!", show_alert=True)
        return
    
    success = 0
    fail = 0
    
    progress_msg = await callback.message.edit_text("📢 <b>ИДЁТ РАССЫЛКА...</b>\n\n⏳ Пожалуйста, подождите...", parse_mode=ParseMode.HTML)
    
    for user_id in users_balance.keys():
        if users_ban.get(user_id, False):
            continue
        try:
            if msg.text:
                await bot.send_message(user_id, msg.text, parse_mode=ParseMode.HTML)
            elif msg.photo:
                await bot.send_photo(user_id, msg.photo[-1].file_id, caption=msg.caption)
            elif msg.video:
                await bot.send_video(user_id, msg.video.file_id, caption=msg.caption)
            else:
                await bot.copy_message(user_id, msg.chat.id, msg.message_id)
            success += 1
        except:
            fail += 1
        await asyncio.sleep(0.05)
    
    await state.clear()
    await progress_msg.edit_text(
        f"✅ <b>РАССЫЛКА ЗАВЕРШЕНА!</b>\n\n"
        f"📨 Доставлено: {success}\n"
        f"❌ Ошибок: {fail}\n"
        f"📊 Всего пользователей: {len(users_balance)}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_main_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "broadcast_cancel")
async def admin_broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Рассылка отменена.", reply_markup=get_admin_main_keyboard())
    await callback.answer()

@dp.message(GameStates.admin_ban_user)
async def admin_ban_user(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Операция отменена.", reply_markup=get_admin_main_keyboard())
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
        await bot.send_message(
            user_id,
            f"🚫 <b>Ваш аккаунт {status}!</b>\n\n"
            f"{'Причина: Нарушение правил' if users_ban[user_id] else 'Вы снова можете пользоваться ботом.'}",
            parse_mode=ParseMode.HTML
        )
    except:
        pass
    
    await state.clear()
    await message.answer(
        f"✅ <b>Пользователь {status}!</b>\n\n"
        f"👤 @{input_text}\n"
        f"🚫 Статус: {'Забанен' if users_ban[user_id] else 'Активен'}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_main_keyboard()
    )

@dp.message(GameStates.admin_set_verify)
async def admin_set_verify(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Операция отменена.", reply_markup=get_admin_main_keyboard())
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
        await bot.send_message(
            user_id,
            f"✅ <b>Ваш аккаунт {status}!</b>\n\n"
            f"Статус: {'Верифицирован' if users_verify[user_id] else 'Не верифицирован'}",
            parse_mode=ParseMode.HTML
        )
    except:
        pass
    
    await state.clear()
    await message.answer(
        f"✅ <b>Пользователь {status}!</b>\n\n"
        f"👤 @{input_text}\n"
        f"✅ Статус: {'Верифицирован' if users_verify[user_id] else 'Не верифицирован'}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_main_keyboard()
    )

@dp.message(GameStates.admin_promo_create)
async def admin_promo_code(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Операция отменена.", reply_markup=get_admin_main_keyboard())
        return
    
    code = message.text.strip().upper()
    await state.update_data(promo_code=code)
    await state.set_state(GameStates.admin_promo_amount)
    await message.answer(
        f"🎁 <b>СОЗДАНИЕ ПРОМОКОДА</b>\n\n"
        f"Код: <code>{code}</code>\n\n"
        f"Введите сумму бонуса для промокода:",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(GameStates.admin_promo_amount)
async def admin_promo_amount(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Операция отменена.", reply_markup=get_admin_main_keyboard())
        return
    
    try:
        amount = float(message.text.strip())
        data = await state.get_data()
        code = data.get("promo_code")
        promo_codes[code] = {
            "amount": amount,
            "uses": 0,
            "max_uses": 100,
            "created": datetime.now().isoformat(),
            "creator": message.from_user.username
        }
        await state.clear()
        await message.answer(
            f"✅ <b>Промокод создан!</b>\n\n"
            f"🎁 Код: <code>{code}</code>\n"
            f"💰 Сумма: {format_stars(amount)}\n"
            f"📊 Макс. использований: 100\n\n"
            f"🔗 Пользователи могут активировать промокод командой:\n"
            f"<code>/promo {code}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_main_keyboard()
        )
    except:
        await message.answer("❌ Введите число!")

@dp.message(GameStates.admin_global_bonus)
async def admin_global_bonus_amount(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Операция отменена.", reply_markup=get_admin_main_keyboard())
        return
    
    try:
        amount = float(message.text.strip())
        count = 0
        total_amount = 0
        
        progress_msg = await message.answer(f"🎲 <b>ВЫДАЧА БОНУСА</b>\n\n⏳ Выдаём {format_stars(amount)} всем пользователям...", parse_mode=ParseMode.HTML)
        
        for user_id in users_balance.keys():
            if not users_ban.get(user_id, False):
                update_balance(user_id, amount)
                total_amount += amount
                try:
                    await bot.send_message(
                        user_id,
                        f"🎉 <b>ГЛОБАЛЬНЫЙ БОНУС ОТ АДМИНИСТРАТОРА!</b>\n\n"
                        f"+{format_stars(amount)}\n"
                        f"💰 Ваш новый баланс: {format_stars(get_user_balance(user_id))}",
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass
                count += 1
            await asyncio.sleep(0.05)
        
        await state.clear()
        await progress_msg.edit_text(
            f"✅ <b>Глобальный бонус выдан!</b>\n\n"
            f"💰 Сумма: {format_stars(amount)}\n"
            f"👥 Получили: {count} пользователей\n"
            f"💎 Всего выдано: {format_stars(total_amount)}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_main_keyboard()
        )
    except:
        await message.answer("❌ Введите число!")

@dp.message(GameStates.admin_announcement)
async def admin_announcement_send(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Операция отменена.", reply_markup=get_admin_main_keyboard())
        return
    
    announcement_text = message.text
    system_announcements.append({
        "message": announcement_text,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "author": message.from_user.username
    })
    
    # Сохраняем только последние 10 анонсов
    if len(system_announcements) > 10:
        system_announcements.pop(0)
    
    await state.clear()
    await message.answer(
        f"✅ <b>Анонс сохранён!</b>\n\n"
        f"📢 {announcement_text}\n\n"
        f"Пользователи увидят его в разделе «📢 Новости»",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_main_keyboard()
    )


# ===================== КОМАНДЫ НАСТРОЕК =====================
@dp.message(Command("set_crash_mult"))
async def set_crash_mult(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_crash_mult <число>")
        return
    
    try:
        new_mult = float(args[1])
        if new_mult < 10 or new_mult > 10000:
            await message.answer("❌ Множитель должен быть от 10 до 10000")
            return
        bot_settings["crash_max_multiplier"] = new_mult
        await message.answer(f"✅ Максимальный множитель CRASH установлен: x{new_mult}")
    except:
        await message.answer("❌ Введите число!")

@dp.message(Command("set_crash_edge"))
async def set_crash_edge(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_crash_edge <процент>")
        return
    
    try:
        percent = float(args[1])
        if percent < 0 or percent > 50:
            await message.answer("❌ House edge должен быть от 0 до 50%")
            return
        bot_settings["crash_house_edge"] = (100 - percent) / 100
        await message.answer(f"✅ House edge CRASH установлен: {percent}% (множитель: x{bot_settings['crash_house_edge']})")
    except:
        await message.answer("❌ Введите число!")

@dp.message(Command("set_mines_size"))
async def set_mines_size(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_mines_size <число>")
        return
    
    try:
        new_size = int(args[1])
        if new_size < 3 or new_size > 10:
            await message.answer("❌ Размер поля должен быть от 3 до 10")
            return
        global MINES_BOARD_SIZE
        MINES_BOARD_SIZE = new_size
        bot_settings["mines_board_size"] = new_size
        await message.answer(f"✅ Размер поля MINES установлен: {new_size}x{new_size}")
    except:
        await message.answer("❌ Введите число!")

@dp.message(Command("set_mines_count"))
async def set_mines_count(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_mines_count <число>")
        return
    
    try:
        new_count = int(args[1])
        if new_count < 1 or new_count > MINES_BOARD_SIZE * MINES_BOARD_SIZE - 1:
            await message.answer(f"❌ Количество мин должно быть от 1 до {MINES_BOARD_SIZE * MINES_BOARD_SIZE - 1}")
            return
        global MINES_MINES_COUNT
        MINES_MINES_COUNT = new_count
        bot_settings["mines_count"] = new_count
        await message.answer(f"✅ Количество мин MINES установлено: {new_count}")
    except:
        await message.answer("❌ Введите число!")

@dp.message(Command("set_maintenance"))
async def set_maintenance(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_maintenance <вкл/выкл>")
        return
    
    value = args[1].lower()
    if value in ["вкл", "on"]:
        bot_settings["maintenance_mode"] = True
        await message.answer("🔧 Режим обслуживания ВКЛЮЧЁН! Пользователи не смогут играть.")
    elif value in ["выкл", "off"]:
        bot_settings["maintenance_mode"] = False
        await message.answer("✅ Режим обслуживания ВЫКЛЮЧЁН! Бот снова работает.")
    else:
        await message.answer("❌ Используйте 'вкл' или 'выкл'")


# ===================== ПРОМОКОДЫ =====================
@dp.message(Command("promo"))
async def use_promo(message: Message):
    user_id = message.from_user.id
    args = message.text.split()
    
    if len(args) != 2:
        await message.answer(
            "🎁 <b>Активация промокода</b>\n\n"
            "Использование: <code>/promo КОД</code>\n\n"
            "Пример: <code>/promo WELCOME2024</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    code = args[1].upper()
    
    if code not in promo_codes:
        await message.answer("❌ Промокод не найден или уже недействителен!", parse_mode=ParseMode.HTML)
        return
    
    promo = promo_codes[code]
    
    if promo["uses"] >= promo["max_uses"]:
        await message.answer("❌ Лимит использований промокода исчерпан!", parse_mode=ParseMode.HTML)
        return
    
    # Проверяем, не использовал ли пользователь уже этот промокод
    if f"{user_id}_{code}" in [t.get("details", "") for t in transactions.get(user_id, []) if t["type"] == "promo"]:
        await message.answer("❌ Вы уже использовали этот промокод!", parse_mode=ParseMode.HTML)
        return
    
    amount = promo["amount"]
    update_balance(user_id, amount)
    promo["uses"] += 1
    save_transaction(user_id, amount, "promo", f"Промокод {code}", "promo")
    
    await message.answer(
        f"🎉 <b>Промокод активирован!</b>\n\n"
        f"🎁 Код: <code>{code}</code>\n"
        f"+{format_stars(amount)}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML
    )


# ===================== ВЫВОД СРЕДСТВ =====================
@dp.callback_query(F.data == "withdraw_request")
async def withdraw_request(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    if not users_verify.get(user_id, False):
        await callback.answer("❌ Для вывода средств необходимо пройти верификацию!", show_alert=True)
        return
    
    await state.set_state(GameStates.custom_withdraw)
    await callback.message.answer(
        "📤 <b>ВЫВОД СРЕДСТВ</b>\n\n"
        f"💰 Ваш баланс: {format_stars(get_user_balance(user_id))}\n"
        f"💰 Минимальный вывод: {format_stars(bot_settings['min_withdraw'])}\n"
        f"💰 Максимальный вывод: {format_stars(bot_settings['max_withdraw'])}\n\n"
        f"Введите сумму для вывода:\n\n"
        f"<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

@dp.message(GameStates.custom_withdraw)
async def process_withdraw(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    try:
        amount = float(message.text.strip())
        
        if amount < bot_settings["min_withdraw"]:
            await message.answer(f"❌ Минимальная сумма вывода: {format_stars(bot_settings['min_withdraw'])}")
            return
        
        if amount > bot_settings["max_withdraw"]:
            await message.answer(f"❌ Максимальная сумма вывода: {format_stars(bot_settings['max_withdraw'])}")
            return
        
        if get_user_balance(user_id) < amount:
            await message.answer(f"❌ Недостаточно средств! Ваш баланс: {format_stars(get_user_balance(user_id))}")
            return
        
        pending_withdrawals[user_id] = {
            "amount": amount,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "username": message.from_user.username
        }
        
        await state.clear()
        await message.answer(
            f"✅ <b>Заявка на вывод создана!</b>\n\n"
            f"💰 Сумма: {format_stars(amount)}\n"
            f"📅 Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"⏳ Ожидайте подтверждения администратора.\n\n"
            f"💡 Статус заявки можно узнать у администратора.",
            parse_mode=ParseMode.HTML
        )
        
        # Уведомляем админов
        for admin_name in ADMIN_USERNAMES:
            try:
                await bot.send_message(
                    await get_user_id_by_username(admin_name),
                    f"📤 <b>НОВАЯ ЗАЯВКА НА ВЫВОД!</b>\n\n"
                    f"👤 @{message.from_user.username}\n"
                    f"💰 Сумма: {format_stars(amount)}\n"
                    f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"Для подтверждения: /approve_{user_id}\n"
                    f"Для отклонения: /decline_{user_id}",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
    except:
        await message.answer("❌ Введите число!")

@dp.message(Command("approve"))
async def approve_withdraw(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /approve <user_id>")
        return
    
    try:
        user_id = int(args[1])
    except:
        await message.answer("❌ Неверный ID пользователя!")
        return
    
    if user_id not in pending_withdrawals:
        await message.answer("❌ Заявка не найдена или уже обработана!")
        return
    
    req = pending_withdrawals[user_id]
    amount = req["amount"]
    
    if get_user_balance(user_id) < amount:
        await message.answer(f"❌ У пользователя недостаточно средств для вывода!")
        del pending_withdrawals[user_id]
        return
    
    update_balance(user_id, -amount)
    save_transaction(user_id, -amount, "withdraw", f"Вывод {amount} Stars", "withdraw")
    
    stats = get_user_stats(user_id)
    stats["total_withdrawals"] += 1
    stats["total_withdrawal_amount"] += amount
    
    del pending_withdrawals[user_id]
    
    try:
        await bot.send_message(
            user_id,
            f"✅ <b>Ваша заявка на вывод одобрена!</b>\n\n"
            f"💰 Сумма: {format_stars(amount)}\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"💡 Средства отправлены на ваш кошелёк.",
            parse_mode=ParseMode.HTML
        )
    except:
        pass
    
    await message.answer(f"✅ Вывод {format_stars(amount)} пользователю @{req['username']} подтверждён!")

@dp.message(Command("decline"))
async def decline_withdraw(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /decline <user_id>")
        return
    
    try:
        user_id = int(args[1])
    except:
        await message.answer("❌ Неверный ID пользователя!")
        return
    
    if user_id not in pending_withdrawals:
        await message.answer("❌ Заявка не найдена или уже обработана!")
        return
    
    req = pending_withdrawals[user_id]
    amount = req["amount"]
    
    del pending_withdrawals[user_id]
    
    try:
        await bot.send_message(
            user_id,
            f"❌ <b>Ваша заявка на вывод отклонена!</b>\n\n"
            f"💰 Сумма: {format_stars(amount)}\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"💡 Обратитесь к администратору для уточнения причины.",
            parse_mode=ParseMode.HTML
        )
    except:
        pass
    
    await message.answer(f"❌ Вывод {format_stars(amount)} пользователю @{req['username']} отклонён!")


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
    
    stats = get_user_stats(user_id)
    stats["total_deposits"] += 1
    stats["total_deposit_amount"] += amount
    
    if user_id in users_referrer:
        referrer_id = users_referrer[user_id]
        bonus = amount * REFERRAL_BONUS_PERCENT / 100
        if bonus > 0:
            update_balance(referrer_id, bonus)
            save_transaction(referrer_id, bonus, "referral_earning", f"10% с пополнения реферала", "referral")
            try:
                await bot.send_message(
                    referrer_id,
                    f"🎉 <b>Реферальный бонус!</b>\n\n"
                    f"👤 @{message.from_user.username or user_id} пополнил баланс!\n"
                    f"💰 Пополнение: {format_stars(amount)}\n"
                    f"🎁 Ваш бонус: {format_stars(bonus)}\n"
                    f"💰 Новый баланс: {format_stars(get_user_balance(referrer_id))}",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
    
    await message.answer(
        f"✅ <b>Платеж успешно обработан!</b>\n\n"
        f"💰 Пополнение: +{format_stars(amount)}\n"
        f"💰 Новый баланс: {format_stars(new_balance)}\n\n"
        f"🎮 Приятной игры в StarPlay!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(user_id)
    )
    
    del pending_payments[payload]

@dp.callback_query(F.data.startswith("deposit_"))
async def deposit_callback(callback: CallbackQuery, state: FSMContext):
    amount_str = callback.data.split("_")[-1]
    if amount_str == "custom":
        await callback.message.answer(
            "✏️ <b>Введите сумму пополнения</b>\n\n"
            f"💰 Минимум: 1 Star\n"
            f"💰 Максимум: 10000 Stars\n\n"
            f"<i>Просто отправьте число в чат:</i>",
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
            await message.answer("❌ Введите число от 1 до 10000!")
    except:
        await message.answer("❌ Пожалуйста, введите число!")


# ===================== НАВИГАЦИЯ =====================
@dp.message(F.text == "🔙 В главное меню")
async def back_to_main(message: Message):
    await message.answer(
        "🌟 <b>Главное меню</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@dp.callback_query(F.data == "back_to_games")
async def back_to_games(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎮 <b>Выберите игру</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery):
    await callback.message.edit_text(
        "🌟 <b>Главное меню</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(callback.from_user.id)
    )
    await callback.answer()

@dp.message(F.text == "❌ Отмена")
async def cancel_button(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Операция отменена.",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@dp.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Действие отменено.",
        reply_markup=get_main_keyboard(message.from_user.id)
    )


# ===================== ОБРАБОТЧИК ОШИБОК =====================
@dp.errors()
async def errors_handler(update, exception):
    logger.error(f"Произошла ошибка: {exception}")
    return True


# ===================== ЗАПУСК БОТА =====================
async def main():
    logger.info("🚀 StarPlay Casino Bot запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())