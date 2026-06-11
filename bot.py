import asyncio
import hashlib
import logging
import random
import json
import time
import math
import os
import secrets
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
BOT_TOKEN = "8251949164:AAH9dxlioIEhmzZNazWzMHg0NhfaEsGYFMk"
ADMIN_USERNAMES = ["hjklgf1", "admin"]

# Настройки игр
CRASH_MAX_MULTIPLIER = 1000
CRASH_HOUSE_EDGE = 0.95
MINES_BOARD_SIZE = 5
MINES_MINES_COUNT = 5
PLINKO_MULTIPLIERS = {
    8: [0.2, 0.5, 1, 2, 5, 10, 20, 50],
    12: [0.2, 0.3, 0.5, 1, 2, 5, 10, 20, 30, 50, 100, 200],
    16: [0.1, 0.2, 0.3, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]
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
WITHDRAWAL_MIN = 50
WITHDRAWAL_MAX = 10000

# ===================== ХРАНИЛИЩА ДАННЫХ =====================
users_balance: Dict[int, float] = {}
users_referrer: Dict[int, int] = {}
users_referrals: Dict[int, List[int]] = {}
users_stats: Dict[int, dict] = {}
users_daily_bonus: Dict[int, str] = {}
users_daily_bonus_streak: Dict[int, int] = {}
pending_payments: Dict[str, dict] = {}
pending_withdrawals: Dict[int, dict] = {}
transactions: Dict[int, list] = {}
users_username: Dict[int, str] = {}
users_join_date: Dict[int, str] = {}
users_last_seen: Dict[int, str] = {}
users_ban: Dict[int, bool] = {}
users_ban_reason: Dict[int, str] = {}
users_verify: Dict[int, bool] = {}
users_admin_notes: Dict[int, str] = {}
users_2fa_secret: Dict[int, str] = {}
users_2fa_enabled: Dict[int, bool] = {}
users_antispam: Dict[int, List[float]] = {}
users_daily_limit: Dict[int, float] = {}
users_weekly_limit: Dict[int, float] = {}
users_monthly_limit: Dict[int, float] = {}

# Игровые данные
active_crash: Dict[int, dict] = {}
active_mines: Dict[int, dict] = {}
active_plinko: Dict[int, dict] = {}

# История игр
crash_history: List[dict] = []
mines_history: List[dict] = []
plinko_history: List[dict] = []

# Промокоды
promo_codes: Dict[str, dict] = {}

# Баннеры и объявления
announcements: List[dict] = []
banners: List[dict] = []

# Системные уведомления
system_notifications: List[dict] = []

# Статистика бота
bot_stats = {
    "total_users": 0,
    "active_today": 0,
    "active_week": 0,
    "active_month": 0,
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
    "plinko_games_played": 0,
    "total_referral_paid": 0.0,
    "server_start_time": datetime.now().isoformat(),
    "last_backup": None,
    "last_maintenance": None,
    "total_admin_actions": 0
}

# Настройки бота
bot_settings = {
    "maintenance_mode": False,
    "maintenance_message": "🔧 Бот на техническом обслуживании. Зайдите позже.",
    "min_bet": MIN_BET,
    "max_bet": MAX_BET,
    "crash_house_edge": CRASH_HOUSE_EDGE,
    "crash_max_multiplier": CRASH_MAX_MULTIPLIER,
    "mines_board_size": MINES_BOARD_SIZE,
    "mines_mines_count": MINES_MINES_COUNT,
    "plinko_multipliers": PLINKO_MULTIPLIERS,
    "referral_percent": REFERRAL_BONUS_PERCENT,
    "daily_bonus_enabled": True,
    "daily_bonus_min": DAILY_BONUS_MIN,
    "daily_bonus_max": DAILY_BONUS_MAX,
    "withdrawal_min": WITHDRAWAL_MIN,
    "withdrawal_max": WITHDRAWAL_MAX,
    "antispam_enabled": True,
    "antispam_cooldown": 3,
    "chat_link": "https://t.me/starplay_chat",
    "channel_link": "https://t.me/starplay_news",
    "support_link": "https://t.me/starplay_support",
    "welcome_message": "Добро пожаловать в StarPlay!",
    "currency_symbol": "⭐️",
    "currency_name": "Stars"
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
    crash_cashout_delay = State()
    mines_bet = State()
    mines_playing = State()
    plinko_bet = State()
    plinko_lines = State()
    custom_deposit = State()
    custom_withdraw = State()
    withdraw_amount = State()
    withdraw_wallet = State()
    admin_find_user = State()
    admin_change_balance = State()
    admin_send_broadcast = State()
    admin_send_broadcast_confirm = State()
    admin_ban_user = State()
    admin_unban_user = State()
    admin_set_verify = State()
    admin_promo_create = State()
    admin_promo_amount = State()
    admin_promo_max_uses = State()
    admin_global_bonus = State()
    admin_set_min_bet = State()
    admin_set_max_bet = State()
    admin_set_house_edge = State()
    admin_set_daily_bonus = State()
    admin_set_maintenance = State()
    admin_set_maintenance_msg = State()
    admin_announcement = State()
    admin_announcement_msg = State()
    admin_banner_add = State()
    admin_banner_url = State()
    admin_banner_delete = State()
    admin_system_notify = State()
    admin_system_notify_msg = State()
    admin_export_data = State()
    admin_import_data = State()
    admin_reset_stats = State()
    admin_reset_user = State()
    admin_user_notes = State()
    admin_user_notes_text = State()
    admin_antispam_settings = State()
    admin_limit_settings = State()


# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
def is_admin(username: str) -> bool:
    return username.lower() in [adm.lower() for adm in ADMIN_USERNAMES]

async def get_user_id_by_username(username: str) -> Optional[int]:
    for uid, uname in users_username.items():
        if uname and uname.lower() == username.lower():
            return uid
    return None

def format_stars(amount: float) -> str:
    return f"{bot_settings['currency_symbol']} {amount:.2f} {bot_settings['currency_name']}"

def get_user_balance(user_id: int) -> float:
    return users_balance.get(user_id, 0.0)

def update_balance(user_id: int, delta: float) -> float:
    current = users_balance.get(user_id, 0.0)
    new_balance = current + delta
    if new_balance < 0:
        new_balance = 0.0
    users_balance[user_id] = round(new_balance, 2)
    
    # Обновляем лимиты
    today = datetime.now().date().isoformat()
    week = datetime.now().strftime("%Y-%W")
    month = datetime.now().strftime("%Y-%m")
    
    if delta < 0:
        users_daily_limit[user_id] = users_daily_limit.get(user_id, 0) + abs(delta)
        users_weekly_limit[user_id] = users_weekly_limit.get(user_id, 0) + abs(delta)
        users_monthly_limit[user_id] = users_monthly_limit.get(user_id, 0) + abs(delta)
    
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
    
    if len(transactions[user_id]) > 1000:
        transactions[user_id] = transactions[user_id][-500:]
    
    # Обновляем статистику бота
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
            "crash_games": 0, "crash_wins": 0, "crash_best_multiplier": 0.0, "crash_total_win": 0.0,
            "mines_games": 0, "mines_wins": 0, "mines_best_multiplier": 0.0, "mines_total_win": 0.0,
            "plinko_games": 0, "plinko_wins": 0, "plinko_best_multiplier": 0.0, "plinko_total_win": 0.0,
            "total_deposits": 0, "total_deposit_amount": 0.0,
            "total_withdrawals": 0, "total_withdrawal_amount": 0.0,
            "referral_count": 0, "referral_earned": 0.0,
            "daily_bonus_count": 0, "daily_bonus_streak": 0, "total_bonus": 0.0,
            "last_game_played": None, "favorite_game": None
        }
    return users_stats[user_id]

def get_random_emoji() -> str:
    emojis = ["🎲", "🎯", "⚡️", "💫", "🌟", "⭐️", "✨", "🎮", "🎰", "🔥", "💰", "💎", "🏆", "🎉", "🚀", "💪", "🎯", "🏅", "🌟"]
    return random.choice(emojis)

def generate_referral_link(user_id: int) -> str:
    code = hashlib.md5(f"starplay_{user_id}_{datetime.now().date()}".encode()).hexdigest()[:8]
    return f"https://t.me/{bot.username}?start=ref_{code}"

def format_time(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} сек"
    elif seconds < 3600:
        return f"{seconds//60} мин {seconds%60} сек"
    elif seconds < 86400:
        return f"{seconds//3600} ч {(seconds%3600)//60} мин"
    else:
        return f"{seconds//86400} дн {(seconds%86400)//3600} ч"

def check_antispam(user_id: int) -> bool:
    if not bot_settings["antispam_enabled"]:
        return True
    
    now = time.time()
    if user_id not in users_antispam:
        users_antispam[user_id] = []
    
    users_antispam[user_id] = [t for t in users_antispam[user_id] if now - t < bot_settings["antispam_cooldown"]]
    
    if len(users_antispam[user_id]) >= 5:
        return False
    
    users_antispam[user_id].append(now)
    return True

def generate_2fa_secret() -> str:
    return secrets.token_hex(16)

def validate_2fa(code: str, secret: str) -> bool:
    # Упрощённая проверка 2FA
    return code == secret[:6]


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
    builder.button(text="💸 Вывод")
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
    builder.button(text="⚙️ Настройки игр")
    builder.button(text="🎁 Промокоды")
    builder.button(text="🎲 Глобальный бонус")
    builder.button(text="📈 Экспорт данных")
    builder.button(text="📥 Импорт данных")
    builder.button(text="🔧 Системные настройки")
    builder.button(text="📢 Анонсы")
    builder.button(text="🖼 Баннеры")
    builder.button(text="📨 Системные уведомления")
    builder.button(text="🔄 Сброс статистики")
    builder.button(text="💾 Сохранить данные")
    builder.button(text="🔙 В главное меню")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_games_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📈 CRASH")
    builder.button(text="💣 MINES")
    builder.button(text="⚡ PLINKO")
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
    
    current_win = bet * multiplier
    keyboard.append([InlineKeyboardButton(text=f"💰 ЗАБРАТЬ ВЫИГРЫШ ({format_stars(current_win)})", callback_data="mines_cashout")])
    keyboard.append([InlineKeyboardButton(text="❌ ВЫЙТИ ИЗ ИГРЫ", callback_data="mines_exit")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_plinko_bet_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐️ 1", callback_data="plinko_bet_1"),
         InlineKeyboardButton(text="⭐️ 5", callback_data="plinko_bet_5"),
         InlineKeyboardButton(text="⭐️ 10", callback_data="plinko_bet_10")],
        [InlineKeyboardButton(text="⭐️ 25", callback_data="plinko_bet_25"),
         InlineKeyboardButton(text="⭐️ 50", callback_data="plinko_bet_50"),
         InlineKeyboardButton(text="⭐️ 100", callback_data="plinko_bet_100")],
        [InlineKeyboardButton(text="⭐️ 250", callback_data="plinko_bet_250"),
         InlineKeyboardButton(text="⭐️ 500", callback_data="plinko_bet_500"),
         InlineKeyboardButton(text="⭐️ 1000", callback_data="plinko_bet_1000")],
        [InlineKeyboardButton(text="✏️ Своя сумма", callback_data="plinko_bet_custom")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_games")]
    ])

def get_plinko_lines_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 8 линий (низкий риск)", callback_data="plinko_lines_8")],
        [InlineKeyboardButton(text="📊 12 линий (средний риск)", callback_data="plinko_lines_12")],
        [InlineKeyboardButton(text="📊 16 линий (высокий риск)", callback_data="plinko_lines_16")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_games")]
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

def get_withdraw_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐️ 50", callback_data="withdraw_50"),
         InlineKeyboardButton(text="⭐️ 100", callback_data="withdraw_100"),
         InlineKeyboardButton(text="⭐️ 250", callback_data="withdraw_250")],
        [InlineKeyboardButton(text="⭐️ 500", callback_data="withdraw_500"),
         InlineKeyboardButton(text="⭐️ 1000", callback_data="withdraw_1000"),
         InlineKeyboardButton(text="⭐️ 2500", callback_data="withdraw_2500")],
        [InlineKeyboardButton(text="✏️ Другая сумма", callback_data="withdraw_custom")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])


# ===================== ОСНОВНЫЕ КОМАНДЫ =====================
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    
    if bot_settings["maintenance_mode"] and not is_admin(username):
        await message.answer(bot_settings["maintenance_message"], parse_mode=ParseMode.HTML)
        return
    
    if users_ban.get(user_id, False):
        await message.answer(f"🚫 Ваш аккаунт заблокирован!\nПричина: {users_ban_reason.get(user_id, 'Не указана')}\n\nДля решения вопроса: {bot_settings['support_link']}", parse_mode=ParseMode.HTML)
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
                    bot_stats["total_referral_paid"] += REFERRAL_INVITE_BONUS
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
    
    # Показываем баннер если есть
    if banners:
        banner = random.choice(banners)
        await message.answer_photo(banner["url"], caption=f"🌟 {banner['text']}", parse_mode=ParseMode.HTML)
    
    await message.answer(
        f"{bot_settings['welcome_message']}\n\n"
        f"🌟 <b>Добро пожаловать в StarPlay Casino!</b> 🌟\n\n"
        f"{get_random_emoji()} <b>Лучшее игровое казино в Telegram!</b>\n\n"
        f"<b>🎮 Игры:</b>\n"
        f"📈 CRASH — Растущий множитель до x{CRASH_MAX_MULTIPLIER}\n"
        f"💣 MINES — Сапёр с множителем до x{1.2 ** 20:.1f}\n"
        f"⚡ PLINKO — Множители от x0.2 до x1000\n\n"
        f"<b>💫 Как начать:</b>\n"
        f"1️⃣ Пополните баланс\n"
        f"2️⃣ Выберите игру\n"
        f"3️⃣ Делайте ставки и выигрывайте!\n\n"
        f"<b>🎁 Бонусы:</b>\n"
        f"• Ежедневный бонус до {DAILY_BONUS_MAX} Stars\n"
        f"• Реферальная программа: +{REFERRAL_BONUS_PERCENT}% от пополнений друзей\n"
        f"• Промокоды и розыгрыши\n\n"
        f"📞 <b>Контакты:</b>\n"
        f"├ Чат: {bot_settings['chat_link']}\n"
        f"├ Новости: {bot_settings['channel_link']}\n"
        f"└ Поддержка: {bot_settings['support_link']}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(user_id)
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        f"❓ <b>Помощь по боту StarPlay</b>\n\n"
        f"<b>🎮 Игры:</b>\n"
        f"📈 <b>CRASH</b> — Ставка растёт. Заберите выигрыш до взрыва!\n"
        f"💣 <b>MINES</b> — Открывайте клетки с 💎, избегайте 💣. Каждая 💎 увеличивает множитель x1.2\n"
        f"⚡ <b>PLINKO</b> — Шарик падает по пинам. Выберите уровень риска и получите множитель!\n\n"
        f"<b>💰 Баланс:</b>\n"
        f"• Пополнение через Telegram Stars\n"
        f"• Минимальная ставка: {MIN_BET} Star\n"
        f"• Максимальная ставка: {MAX_BET} Stars\n"
        f"• Минимальный вывод: {WITHDRAWAL_MIN} Stars\n\n"
        f"<b>👥 Рефералы:</b>\n"
        f"• Пригласите друга → +{REFERRAL_INVITE_BONUS} Stars\n"
        f"• Друг получает → +{REFERRAL_SIGNUP_BONUS} Stars\n"
        f"• Вы получаете {REFERRAL_BONUS_PERCENT}% от пополнений друга\n\n"
        f"<b>🎁 Ежедневный бонус:</b>\n"
        f"• Забирайте бонус каждый день\n"
        f"• Чем больше стрик — тем больше бонус!\n\n"
        f"<b>📞 Контакты:</b>\n"
        f"├ Чат: {bot_settings['chat_link']}\n"
        f"├ Новости: {bot_settings['channel_link']}\n"
        f"└ Поддержка: {bot_settings['support_link']}"
    )
    await message.answer(help_text, parse_mode=ParseMode.HTML)


# ===================== ГЛАВНЫЕ КНОПКИ =====================
@dp.message(F.text == "💰 Баланс")
async def balance_reply(message: Message):
    user_id = message.from_user.id
    stats = get_user_stats(user_id)
    daily_limit = users_daily_limit.get(user_id, 0)
    weekly_limit = users_weekly_limit.get(user_id, 0)
    monthly_limit = users_monthly_limit.get(user_id, 0)
    
    await message.answer(
        f"💰 <b>Ваш баланс</b>\n\n"
        f"{format_stars(get_user_balance(user_id))}\n\n"
        f"<b>📊 Ставки сегодня:</b> {format_stars(daily_limit)}\n"
        f"<b>📊 Ставки за неделю:</b> {format_stars(weekly_limit)}\n"
        f"<b>📊 Ставки за месяц:</b> {format_stars(monthly_limit)}\n\n"
        f"💡 Приглашайте друзей и зарабатывайте больше!",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text == "⭐️ Пополнить")
async def deposit_reply(message: Message):
    await message.answer(
        "⭐️ <b>Пополнение баланса</b>\n\n"
        f"💰 Минимальная сумма: 10 Stars\n"
        f"💰 Максимальная сумма: 10000 Stars\n"
        f"💡 Средства зачисляются мгновенно!\n\n"
        f"👇 <b>Выберите сумму:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_deposit_keyboard()
    )

@dp.message(F.text == "💸 Вывод")
async def withdraw_reply(message: Message, state: FSMContext):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    
    if balance < WITHDRAWAL_MIN:
        await message.answer(
            f"❌ <b>Недостаточно средств для вывода</b>\n\n"
            f"💰 Минимальная сумма вывода: {format_stars(WITHDRAWAL_MIN)}\n"
            f"💰 Ваш баланс: {format_stars(balance)}\n\n"
            f"💡 Пополните баланс, чтобы вывести средства.",
            parse_mode=ParseMode.HTML
        )
        return
    
    await state.set_state(GameStates.withdraw_amount)
    await message.answer(
        f"💸 <b>Вывод средств</b>\n\n"
        f"💰 Ваш баланс: {format_stars(balance)}\n"
        f"💰 Минимальный вывод: {format_stars(WITHDRAWAL_MIN)}\n"
        f"💰 Максимальный вывод: {format_stars(min(balance, WITHDRAWAL_MAX))}\n\n"
        f"👇 <b>Выберите сумму вывода:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_withdraw_keyboard()
    )

@dp.callback_query(F.data.startswith("withdraw_"))
async def withdraw_amount(callback: CallbackQuery, state: FSMContext):
    amount_str = callback.data.split("_")[-1]
    user_id = callback.from_user.id
    
    if amount_str == "custom":
        await callback.message.answer(
            "✏️ <b>Введите сумму вывода</b>\n\n"
            f"💰 Минимальный вывод: {format_stars(WITHDRAWAL_MIN)}\n"
            f"💰 Максимальный вывод: {format_stars(min(get_user_balance(user_id), WITHDRAWAL_MAX))}\n\n"
            f"<i>Просто отправьте число в чат:</i>",
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GameStates.withdraw_amount)
        await callback.answer()
        return
    
    try:
        amount = float(amount_str)
    except:
        await callback.answer("Неверная сумма!", show_alert=True)
        return
    
    if amount < WITHDRAWAL_MIN:
        await callback.answer(f"❌ Минимальная сумма вывода: {format_stars(WITHDRAWAL_MIN)}", show_alert=True)
        return
    
    balance = get_user_balance(user_id)
    if amount > balance:
        await callback.answer(f"❌ Недостаточно средств! Ваш баланс: {format_stars(balance)}", show_alert=True)
        return
    
    if amount > WITHDRAWAL_MAX:
        await callback.answer(f"❌ Максимальная сумма вывода за раз: {format_stars(WITHDRAWAL_MAX)}", show_alert=True)
        return
    
    await state.update_data(withdraw_amount=amount)
    await state.set_state(GameStates.withdraw_wallet)
    await callback.message.answer(
        f"💸 <b>Вывод средств</b>\n\n"
        f"💰 Сумма вывода: {format_stars(amount)}\n\n"
        f"✏️ <b>Введите адрес кошелька</b> (USDT TRC20 или другой):\n\n"
        f"<i>Напишите адрес в чат</i>",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

@dp.message(GameStates.withdraw_wallet)
async def withdraw_wallet(message: Message, state: FSMContext):
    data = await state.get_data()
    amount = data.get("withdraw_amount")
    user_id = message.from_user.id
    wallet = message.text.strip()
    
    if not wallet or len(wallet) < 10:
        await message.answer("❌ Неверный адрес кошелька! Попробуйте снова.")
        return
    
    update_balance(user_id, -amount)
    save_transaction(user_id, -amount, "withdraw", f"Вывод {amount} Stars на {wallet[:20]}...")
    
    pending_withdrawals[user_id] = {
        "amount": amount,
        "wallet": wallet,
        "status": "pending",
        "timestamp": datetime.now().isoformat()
    }
    
    # Уведомляем админов
    for admin_id in ADMIN_USERNAMES:
        try:
            await bot.send_message(
                admin_id,
                f"💰 <b>НОВЫЙ ЗАПРОС НА ВЫВОД</b>\n\n"
                f"👤 @{message.from_user.username or user_id}\n"
                f"💰 Сумма: {format_stars(amount)}\n"
                f"📦 Кошелёк: {wallet}\n"
                f"🕐 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                parse_mode=ParseMode.HTML
            )
        except:
            pass
    
    await state.clear()
    await message.answer(
        f"✅ <b>Заявка на вывод создана!</b>\n\n"
        f"💰 Сумма: {format_stars(amount)}\n"
        f"📦 Кошелёк: {wallet[:30]}...\n\n"
        f"⏳ Ожидайте обработки администратором.\n"
        f"💡 Обычно обработка занимает до 24 часов.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@dp.message(F.text == "🎮 Игры")
async def games_reply(message: Message):
    await message.answer(
        "🎮 <b>Выберите игру</b>\n\n"
        "📈 <b>CRASH</b> — Рискни и умножь ставку!\n"
        "💣 <b>MINES</b> — Найди сокровища, избегая мин\n"
        "⚡ <b>PLINKO</b> — Шарик падает по пинам\n\n"
        "👇 <b>Нажмите на кнопку с игрой:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )

@dp.message(F.text == "👥 Рефералы")
async def referrals_reply(message: Message):
    user_id = message.from_user.id
    ref_link = generate_referral_link(user_id)
    stats = get_user_stats(user_id)
    referrals_list = users_referrals.get(user_id, [])
    
    text = (
        f"👥 <b>Реферальная программа</b>\n\n"
        f"🏆 <b>Ваша статистика:</b>\n"
        f"• Приглашено: {stats['referral_count']} чел.\n"
        f"• Заработано: {format_stars(stats['referral_earned'])}\n"
        f"• Процент от пополнений: {REFERRAL_BONUS_PERCENT}%\n\n"
        f"<b>👥 Ваши рефералы:</b>\n"
    )
    
    if referrals_list:
        for ref_id in referrals_list[-10:]:
            ref_name = users_username.get(ref_id, str(ref_id))
            text += f"• @{ref_name}\n"
    else:
        text += "• Пока никого\n"
    
    text += f"\n<b>🔗 Ваша реферальная ссылка:</b>\n<code>{ref_link}</code>\n\n"
    text += f"💡 Поделитесь ссылкой с друзьями и зарабатывайте!\n"
    text += f"🎁 За каждого друга вы получаете {REFERRAL_INVITE_BONUS} Stars + {REFERRAL_BONUS_PERCENT}% от его пополнений!"
    
    await message.answer(text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "🏆 Топ")
async def top_reply(message: Message):
    # Топ по балансу
    sorted_by_balance = sorted(users_balance.items(), key=lambda x: x[1], reverse=True)[:15]
    # Топ по выигрышам
    sorted_by_wins = sorted(users_stats.items(), key=lambda x: x[1].get("games_won", 0), reverse=True)[:15]
    
    top_balance = "🏆 <b>ТОП-15 ПО БАЛАНСУ</b>\n\n"
    for idx, (uid, bal) in enumerate(sorted_by_balance, 1):
        if users_ban.get(uid, False):
            continue
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
        uname = users_username.get(uid, str(uid))
        name = f"@{uname}" if uname else str(uid)
        top_balance += f"{medal} {name} — {bal:.2f} ⭐️\n"
    
    top_wins = "\n🏆 <b>ТОП-15 ПО ПОБЕДАМ</b>\n\n"
    for idx, (uid, stats) in enumerate(sorted_by_wins, 1):
        if users_ban.get(uid, False):
            continue
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
        uname = users_username.get(uid, str(uid))
        name = f"@{uname}" if uname else str(uid)
        wins = stats.get("games_won", 0)
        top_wins += f"{medal} {name} — {wins} 🏆\n"
    
    await message.answer(f"{top_balance}\n{top_wins}", parse_mode=ParseMode.HTML)

@dp.message(F.text == "📊 Профиль")
async def profile_reply(message: Message):
    uid = message.from_user.id
    stats = get_user_stats(uid)
    balance = get_user_balance(uid)
    win_rate = (stats['games_won'] / max(stats['games_played'], 1)) * 100
    total_profit = stats['total_won'] - stats['total_lost']
    
    # Определяем любимую игру
    crash_win_rate = (stats['crash_wins'] / max(stats['crash_games'], 1)) * 100
    mines_win_rate = (stats['mines_wins'] / max(stats['mines_games'], 1)) * 100
    plinko_win_rate = (stats['plinko_wins'] / max(stats['plinko_games'], 1)) * 100
    
    favorite = "CRASH"
    if mines_win_rate > crash_win_rate and mines_win_rate > plinko_win_rate:
        favorite = "MINES"
    elif plinko_win_rate > crash_win_rate and plinko_win_rate > mines_win_rate:
        favorite = "PLINKO"
    
    text = (
        f"👤 <b>Профиль игрока</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👤 Username: @{message.from_user.username or 'не установлен'}\n"
        f"📅 Регистрация: {users_join_date.get(uid, 'неизвестно')}\n"
        f"✅ Верификация: {'✅ Верифицирован' if users_verify.get(uid, False) else '❌ Не верифицирован'}\n"
        f"🏆 Любимая игра: {favorite}\n\n"
        f"💰 <b>Баланс:</b> {format_stars(balance)}\n\n"
        f"📊 <b>Общая статистика:</b>\n"
        f"├ 🎮 Сыграно игр: {stats['games_played']}\n"
        f"├ 🏆 Побед: {stats['games_won']}\n"
        f"├ 📈 Винрейт: {win_rate:.1f}%\n"
        f"├ 💎 Выиграно: {format_stars(stats['total_won'])}\n"
        f"├ 💸 Проиграно: {format_stars(stats['total_lost'])}\n"
        f"└ 💰 Чистая прибыль: {format_stars(total_profit)}\n\n"
        f"📈 <b>Статистика по играм:</b>\n"
        f"├ 📈 CRASH: {stats['crash_wins']}/{stats['crash_games']} побед (Лучший множитель: x{stats['crash_best_multiplier']:.2f})\n"
        f"├ 💣 MINES: {stats['mines_wins']}/{stats['mines_games']} побед (Лучший множитель: x{stats['mines_best_multiplier']:.2f})\n"
        f"└ ⚡ PLINKO: {stats['plinko_wins']}/{stats['plinko_games']} побед (Лучший множитель: x{stats['plinko_best_multiplier']:.2f})\n\n"
        f"👥 <b>Рефералы:</b> {stats['referral_count']} чел., заработано: {format_stars(stats['referral_earned'])}\n"
        f"🎁 <b>Бонусов получено:</b> {stats['daily_bonus_count']} раз, {format_stars(stats['total_bonus'])}\n\n"
        f"💎 <b>Общий выигрыш:</b> {format_stars(stats['crash_total_win'] + stats['mines_total_win'] + stats['plinko_total_win'])}"
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
        await message.answer(
            f"🎁 <b>Вы уже получили сегодняшний бонус!</b>\n\n"
            f"⏰ Следующий бонус через: {format_time(int(time_left.total_seconds()))}\n"
            f"📅 Текущий стрик: {users_daily_bonus_streak.get(user_id, 0)} дней\n\n"
            f"💡 Заходите каждый день — бонус растёт!",
            parse_mode=ParseMode.HTML
        )
        return
    
    streak = users_daily_bonus_streak.get(user_id, 0)
    if users_daily_bonus.get(user_id) == (datetime.now() - timedelta(days=1)).date().isoformat():
        streak += 1
    else:
        streak = 1
    
    bonus = min(bot_settings["daily_bonus_max"], bot_settings["daily_bonus_min"] + (streak - 1) * 2)
    bonus = round(random.uniform(bonus - 2, bonus + 2), 2)
    
    update_balance(user_id, bonus)
    users_daily_bonus[user_id] = today
    users_daily_bonus_streak[user_id] = streak
    stats = get_user_stats(user_id)
    stats["daily_bonus_count"] += 1
    stats["daily_bonus_streak"] = streak
    stats["total_bonus"] += bonus
    save_transaction(user_id, bonus, "daily_bonus", f"Стрик: {streak}")
    
    # Анимация получения бонуса
    msg = await message.answer(f"🎁 <b>Забираем бонус...</b>", parse_mode=ParseMode.HTML)
    await asyncio.sleep(1)
    await msg.edit_text(f"🎉 <b>Ежедневный бонус получен!</b>\n\n+{format_stars(bonus)}\n📅 Стрик: {streak} дней\n💰 Новый баланс: {format_stars(get_user_balance(user_id))}\n\n💡 Завтра бонус будет ещё больше!", parse_mode=ParseMode.HTML)

@dp.message(F.text == "❓ Помощь")
async def help_reply(message: Message):
    await cmd_help(message)

@dp.message(F.text == "📊 История игр")
async def games_history(message: Message):
    user_id = message.from_user.id
    
    user_crash = [g for g in crash_history if g.get("player") == user_id][-5:]
    user_mines = [g for g in mines_history if g.get("player") == user_id][-5:]
    user_plinko = [g for g in plinko_history if g.get("player") == user_id][-5:]
    
    text = "📊 <b>ИСТОРИЯ ВАШИХ ИГР</b>\n\n"
    
    if user_crash:
        text += "<b>📈 CRASH:</b>\n"
        for game in user_crash:
            if "win" in game and game.get("win", 0) > 0:
                text += f"• Ставка: {game['bet']:.0f}⭐️ | x{game['multiplier']:.2f} | +{game['win'] - game['bet']:.0f}⭐️\n"
            else:
                text += f"• Ставка: {game['bet']:.0f}⭐️ | x{game['multiplier']:.2f} | ❌ Проигрыш\n"
        text += "\n"
    
    if user_mines:
        text += "<b>💣 MINES:</b>\n"
        for game in user_mines:
            if game.get("win", 0) > 0:
                text += f"• Ставка: {game['bet']:.0f}⭐️ | x{game['multiplier']:.2f} | +{game['win'] - game['bet']:.0f}⭐️\n"
            else:
                text += f"• Ставка: {game['bet']:.0f}⭐️ | ❌ Проигрыш\n"
        text += "\n"
    
    if user_plinko:
        text += "<b>⚡ PLINKO:</b>\n"
        for game in user_plinko:
            if game.get("win", 0) > 0:
                text += f"• Ставка: {game['bet']:.0f}⭐️ | x{game['multiplier']:.2f} | +{game['win'] - game['bet']:.0f}⭐️\n"
            else:
                text += f"• Ставка: {game['bet']:.0f}⭐️ | ❌ Проигрыш\n"
        text += "\n"
    
    if not user_crash and not user_mines and not user_plinko:
        text += "📭 У вас пока нет сыгранных игр.\n\n💡 Начните играть, чтобы видеть историю!"
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_games_keyboard())


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
                f"📈 Текущий множитель: <b>x{multiplier:.2f}</b>\n"
                f"💎 Потенциальный выигрыш: {format_stars(bet * multiplier)}\n\n"
                f"⚠️ Заберите выигрыш ДО взрыва!\n"
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
                f"😢 <b>К сожалению, вы не успели забрать выигрыш!</b>\n"
                f"💰 Потеряно: {format_stars(bet)}\n\n"
                f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_games_keyboard()
            )
        except:
            pass

@dp.message(F.text == "📈 CRASH")
async def crash_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    if not check_antispam(user_id):
        await message.answer("⚠️ <b>Слишком много действий!</b>\nПожалуйста, подождите несколько секунд.", parse_mode=ParseMode.HTML)
        return
    
    if user_id in active_crash:
        await message.answer("⚠️ У вас уже есть активная игра! Заберите выигрыш или дождитесь окончания.", parse_mode=ParseMode.HTML)
        return
    
    await state.set_state(GameStates.crash_bet)
    await message.answer(
        "📈 <b>CRASH — Умножай ставку!</b>\n\n"
        f"💰 Минимальная ставка: {MIN_BET} Stars\n"
        f"💰 Максимальная ставка: {MAX_BET} Stars\n"
        f"🎯 Максимальный множитель: x{CRASH_MAX_MULTIPLIER}\n\n"
        f"👇 <b>Выберите сумму ставки:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_crash_bet_keyboard()
    )

@dp.callback_query(F.data.startswith("crash_bet_"))
async def crash_bet(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    bet_str = callback.data.split("_")[-1]
    
    if bet_str == "custom":
        await callback.message.answer(
            "✏️ <b>Введите сумму ставки</b>\n\n"
            f"💰 Минимальная ставка: {MIN_BET} Stars\n"
            f"💰 Максимальная ставка: {MAX_BET} Stars\n"
            f"💰 Ваш баланс: {format_stars(get_user_balance(user_id))}",
            parse_mode=ParseMode.HTML
        )
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
        await callback.answer(f"❌ Недостаточно средств! Нужно {format_stars(bet)}", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    save_transaction(user_id, -bet, "bet", f"Crash ставка {bet} Stars", "crash")
    
    crash_point = random.uniform(1.05, CRASH_MAX_MULTIPLIER)
    active_crash[user_id] = {"bet": bet, "crash_point": crash_point, "multiplier": 1.0}
    
    await state.set_state(GameStates.crash_waiting)
    game_msg = await callback.message.edit_text(
        f"📈 <b>CRASH — СТАВКА СДЕЛАНА!</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"📈 Множитель: x1.00\n"
        f"💎 Потенциальный выигрыш: {format_stars(bet)}\n\n"
        f"⏳ Игра начинается через 3 секунды...",
        parse_mode=ParseMode.HTML
    )
    
    await asyncio.sleep(3)
    
    await game_msg.edit_text(
        f"📈 <b>CRASH — ИГРА ИДЁТ!</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"📈 Текущий множитель: <b>x1.00</b>\n"
        f"💎 Потенциальный выигрыш: {format_stars(bet)}\n\n"
        f"⚠️ Заберите выигрыш ДО взрыва!\n"
        f"🎯 Максимальный множитель: x{crash_point:.2f}",
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
    bet = game["bet"]
    multiplier = game["multiplier"]
    win = bet * multiplier
    
    # Показываем анимацию забора выигрыша
    await callback.message.edit_text(
        f"💰 <b>ЗАБИРАЕМ ВЫИГРЫШ...</b>\n\n"
        f"📈 Множитель: x{multiplier:.2f}\n"
        f"💎 Выигрыш: {format_stars(win)}",
        parse_mode=ParseMode.HTML
    )
    
    await asyncio.sleep(1.5)
    
    update_balance(user_id, win)
    
    stats = get_user_stats(user_id)
    stats["games_played"] += 1
    stats["games_won"] += 1
    stats["crash_games"] += 1
    stats["crash_wins"] += 1
    stats["total_won"] += win
    stats["crash_total_win"] += win
    
    if multiplier > stats["crash_best_multiplier"]:
        stats["crash_best_multiplier"] = multiplier
    
    save_transaction(user_id, win, "game_win", f"Crash выигрыш x{multiplier:.2f}", "crash")
    bot_stats["crash_games_played"] += 1
    crash_history.append({"multiplier": multiplier, "player": user_id, "bet": bet, "win": win, "timestamp": datetime.now().isoformat()})
    if len(crash_history) > 100:
        crash_history.pop(0)
    
    del active_crash[user_id]
    await state.clear()
    
    await callback.message.edit_text(
        f"🎉 <b>CRASH — ВЫ ПОБЕДИЛИ!</b> 🎉\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"📈 Множитель: <b>x{multiplier:.2f}</b>\n"
        f"🏆 Выигрыш: {format_stars(win)}\n"
        f"💎 Чистая прибыль: {format_stars(win - bet)}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}\n\n"
        f"🎮 Поздравляем! Отличный выигрыш!",
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
    
    if not check_antispam(user_id):
        await message.answer("⚠️ <b>Слишком много действий!</b>\nПожалуйста, подождите несколько секунд.", parse_mode=ParseMode.HTML)
        return
    
    if user_id in active_mines:
        await message.answer("⚠️ У вас уже есть активная игра! Заберите выигрыш или завершите игру.", parse_mode=ParseMode.HTML)
        return
    
    await state.set_state(GameStates.mines_bet)
    await message.answer(
        "💣 <b>MINES — Найди сокровища!</b>\n\n"
        f"📋 <b>Правила игры:</b>\n"
        f"• Поле {MINES_BOARD_SIZE}x{MINES_BOARD_SIZE}\n"
        f"• Спрятано {MINES_MINES_COUNT} мин\n"
        f"• Каждая найденная 💎 увеличивает множитель x1.2\n"
        f"• Наступите на 💣 — проигрыш\n"
        f"• Можно забрать выигрыш в любой момент\n"
        f"• Максимальный множитель: x{1.2 ** 20:.1f}\n\n"
        f"👇 <b>Выберите сумму ставки:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_mines_bet_keyboard()
    )

@dp.callback_query(F.data.startswith("mines_bet_"))
async def mines_bet(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    bet_str = callback.data.split("_")[-1]
    
    if bet_str == "custom":
        await callback.message.answer(
            "✏️ <b>Введите сумму ставки</b>\n\n"
            f"💰 Минимальная ставка: {MIN_BET} Stars\n"
            f"💰 Максимальная ставка: {MAX_BET} Stars\n"
            f"💰 Ваш баланс: {format_stars(get_user_balance(user_id))}",
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GameStates.mines_bet)
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
        await callback.answer(f"❌ Недостаточно средств! Нужно {format_stars(bet)}", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    save_transaction(user_id, -bet, "bet", f"Mines ставка {bet} Stars", "mines")
    
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
        f"✨ Текущий множитель: x1.0\n"
        f"📦 Открыто клеток: 0/{max_cells}\n"
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
        await callback.answer("Игра не найдена! Начните новую игру.", show_alert=True)
        return
    
    game = active_mines[user_id]
    parts = callback.data.split("_")
    x, y = int(parts[2]), int(parts[3])
    
    if game["revealed"][x][y]:
        await callback.answer("Эта клетка уже открыта!", show_alert=True)
        return
    
    game["revealed"][x][y] = True
    
    if game["board"][x][y] == "💣":
        stats = get_user_stats(user_id)
        stats["games_played"] += 1        stats["mines_games"] += 1
        stats["total_lost"] += game["bet"]
        save_transaction(user_id, -game["bet"], "game_loss", "Mines проигрыш", "mines")
        bot_stats["mines_games_played"] += 1
        mines_history.append({"multiplier": game["multiplier"], "player": user_id, "bet": game["bet"], "win": 0, "timestamp": datetime.now().isoformat()})
        if len(mines_history) > 100:
            mines_history.pop(0)
        del active_mines[user_id]
        
        await callback.message.edit_text(
            f"💥 <b>MINES — ПРОИГРЫШ!</b>\n\n"
            f"💣 <b>Вы наступили на мину!</b>\n\n"
            f"💰 Ставка: {format_stars(game['bet'])} — ПРОИГРАНА\n"
            f"✨ Множитель в момент проигрыша: x{game['multiplier']:.2f}\n"
            f"📦 Открыто клеток: {game['cells_opened']}\n\n"
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
            stats["mines_total_win"] += current_win
            if game["multiplier"] > stats["mines_best_multiplier"]:
                stats["mines_best_multiplier"] = game["multiplier"]
            save_transaction(user_id, current_win, "game_win", f"Mines победа x{game['multiplier']:.1f}", "mines")
            bot_stats["mines_games_played"] += 1
            mines_history.append({"multiplier": game["multiplier"], "player": user_id, "bet": game["bet"], "win": current_win, "timestamp": datetime.now().isoformat()})
            if len(mines_history) > 100:
                mines_history.pop(0)
            del active_mines[user_id]
            
            await callback.message.edit_text(
                f"🎉 <b>MINES — ПОБЕДА!</b> 🎉\n\n"
                f"🎯 <b>Вы нашли все сокровища!</b>\n\n"
                f"💰 Ставка: {format_stars(game['bet'])}\n"
                f"✨ Множитель: x{game['multiplier']:.2f}\n"
                f"🏆 Выигрыш: {format_stars(current_win)}\n"
                f"💎 Чистая прибыль: {format_stars(current_win - game['bet'])}\n\n"
                f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_games_keyboard()
            )
        else:
            await callback.message.edit_text(
                f"💣 <b>MINES — ИГРА</b>\n\n"
                f"💰 Ставка: {format_stars(game['bet'])}\n"
                f"✨ Текущий множитель: x{game['multiplier']:.2f}\n"
                f"📦 Открыто клеток: {game['cells_opened']}/{max_cells}\n"
                f"💎 Текущий выигрыш: {format_stars(current_win)}\n"
                f"🎯 Максимальный выигрыш: {format_stars(game['bet'] * (1.2 ** max_cells))}\n\n"
                f"✅ <b>Вы нашли 💎! Множитель увеличен до x{game['multiplier']:.2f}</b>\n\n"
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
    
    # Анимация забора выигрыша
    await callback.message.edit_text(
        f"💰 <b>ЗАБИРАЕМ ВЫИГРЫШ...</b>\n\n"
        f"✨ Множитель: x{game['multiplier']:.2f}\n"
        f"💎 Выигрыш: {format_stars(win)}",
        parse_mode=ParseMode.HTML
    )
    
    await asyncio.sleep(1.5)
    
    update_balance(user_id, win)
    
    stats = get_user_stats(user_id)
    stats["games_played"] += 1
    stats["games_won"] += 1
    stats["mines_games"] += 1
    stats["mines_wins"] += 1
    stats["total_won"] += win
    stats["mines_total_win"] += win
    
    if game["multiplier"] > stats["mines_best_multiplier"]:
        stats["mines_best_multiplier"] = game["multiplier"]
    
    save_transaction(user_id, win, "game_win", f"Mines кэшаут x{game['multiplier']:.1f}", "mines")
    bot_stats["mines_games_played"] += 1
    mines_history.append({"multiplier": game["multiplier"], "player": user_id, "bet": game["bet"], "win": win, "timestamp": datetime.now().isoformat()})
    if len(mines_history) > 100:
        mines_history.pop(0)
    
    del active_mines[user_id]
    
    await callback.message.edit_text(
        f"💰 <b>MINES — ВЫ ЗАБРАЛИ ВЫИГРЫШ!</b>\n\n"
        f"💰 Ставка: {format_stars(game['bet'])}\n"
        f"✨ Множитель: x{game['multiplier']:.2f}\n"
        f"📦 Открыто клеток: {game['cells_opened']}\n"
        f"🏆 Выигрыш: {format_stars(win)}\n"
        f"💎 Чистая прибыль: {format_stars(win - game['bet'])}\n\n"
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


# ===================== ИГРА PLINKO =====================
@dp.message(F.text == "⚡ PLINKO")
async def plinko_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    if not check_antispam(user_id):
        await message.answer("⚠️ <b>Слишком много действий!</b>\nПожалуйста, подождите несколько секунд.", parse_mode=ParseMode.HTML)
        return
    
    if user_id in active_plinko:
        await message.answer("⚠️ У вас уже есть активная игра!", parse_mode=ParseMode.HTML)
        return
    
    await state.set_state(GameStates.plinko_bet)
    await message.answer(
        "⚡ <b>PLINKO — Шарик падает по пинам!</b>\n\n"
        f"📋 <b>Правила игры:</b>\n"
        f"• Шарик падает по пинам в ячейку\n"
        f"• Выберите уровень риска (8/12/16 линий)\n"
        f"• Множители от x0.2 до x1000\n\n"
        f"👇 <b>Выберите сумму ставки:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_plinko_bet_keyboard()
    )

@dp.callback_query(F.data.startswith("plinko_bet_"))
async def plinko_bet(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    bet_str = callback.data.split("_")[-1]
    
    if bet_str == "custom":
        await callback.message.answer(
            "✏️ <b>Введите сумму ставки</b>\n\n"
            f"💰 Минимальная ставка: {MIN_BET} Stars\n"
            f"💰 Максимальная ставка: {MAX_BET} Stars\n"
            f"💰 Ваш баланс: {format_stars(get_user_balance(user_id))}",
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GameStates.plinko_bet)
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
        await callback.answer(f"❌ Недостаточно средств! Нужно {format_stars(bet)}", show_alert=True)
        return
    
    await state.update_data(plinko_bet=bet)
    await state.set_state(GameStates.plinko_lines)
    
    await callback.message.edit_text(
        f"⚡ <b>PLINKO</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n\n"
        f"👇 <b>Выберите уровень риска:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_plinko_lines_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("plinko_lines_"))
async def plinko_lines(callback: CallbackQuery, state: FSMContext):
    lines = int(callback.data.split("_")[-1])
    data = await state.get_data()
    bet = data.get("plinko_bet")
    user_id = callback.from_user.id
    
    if not bet:
        await callback.answer("Ошибка! Начните заново.", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    save_transaction(user_id, -bet, "bet", f"Plinko ставка {bet} Stars", "plinko")
    
    # Симуляция падения шарика
    await callback.message.edit_text(
        f"⚡ <b>PLINKO — ШАРИК ПАДАЕТ...</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"📊 Линий: {lines}\n\n"
        f"🎯 Шарик проходит через пины...",
        parse_mode=ParseMode.HTML
    )
    
    await asyncio.sleep(2)
    
    multipliers = PLINKO_MULTIPLIERS[lines]
    result_multiplier = random.choice(multipliers)
    win = bet * result_multiplier
    
    # Визуализация падения
    positions = ["⬅️", "⬇️", "➡️", "⬇️", "⬅️", "⬇️", "➡️", "⬇️"]
    visual = " ".join(random.choices(positions, k=lines))
    
    await callback.message.edit_text(
        f"⚡ <b>PLINKO — РЕЗУЛЬТАТ</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"📊 Линий: {lines}\n"
        f"🎯 Путь шарика: {visual}\n\n"
        f"✨ Множитель: <b>x{result_multiplier}</b>\n\n"
        f"💎 Выигрыш: {format_stars(win)}\n"
        f"📈 Чистая прибыль: {format_stars(win - bet)}",
        parse_mode=ParseMode.HTML
    )
    
    await asyncio.sleep(1)
    
    if win > bet:
        update_balance(user_id, win)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["plinko_games"] += 1
        stats["plinko_wins"] += 1
        stats["total_won"] += win
        stats["plinko_total_win"] += win
        if result_multiplier > stats["plinko_best_multiplier"]:
            stats["plinko_best_multiplier"] = result_multiplier
        save_transaction(user_id, win, "game_win", f"Plinko выигрыш x{result_multiplier}", "plinko")
        result_text = f"🎉 <b>ПОБЕДА!</b> +{format_stars(win - bet)}"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["plinko_games"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", f"Plinko проигрыш x{result_multiplier}", "plinko")
        result_text = f"😢 <b>ПРОИГРЫШ</b> -{format_stars(bet - win)}"
    
    bot_stats["plinko_games_played"] += 1
    plinko_history.append({"multiplier": result_multiplier, "player": user_id, "bet": bet, "win": win if win > bet else 0, "timestamp": datetime.now().isoformat()})
    if len(plinko_history) > 100:
        plinko_history.pop(0)
    
    await callback.message.edit_text(
        f"⚡ <b>PLINKO — ИТОГ</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"📊 Линий: {lines}\n"
        f"✨ Множитель: x{result_multiplier}\n\n"
        f"{result_text}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await state.clear()
    await callback.answer()


# ===================== АДМИН-ПАНЕЛЬ =====================
@dp.message(F.text == "👑 Админ панель")
async def admin_panel(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ У вас нет доступа к админ-панели!", reply_markup=get_main_keyboard())
        return
    
    await message.answer(
        "👑 <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n\n"
        f"📊 <b>Быстрая статистика:</b>\n"
        f"├ 👥 Пользователей: {bot_stats['total_users']}\n"
        f"├ 💰 Прибыль: {format_stars(bot_stats['total_profit'])}\n"
        f"├ 🎮 Игр сыграно: {bot_stats['total_bets']}\n"
        f"└ 💸 Выплачено: {format_stars(bot_stats['total_paid'])}\n\n"
        f"👇 <b>Выберите действие:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_main_keyboard()
    )


# ===================== АДМИН: СТАТИСТИКА =====================
@dp.message(F.text == "📊 Статистика")
async def admin_stats(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    uptime = datetime.now() - datetime.fromisoformat(bot_stats["server_start_time"])
    
    text = (
        f"📊 <b>ПОЛНАЯ СТАТИСТИКА БОТА</b>\n\n"
        f"<b>👥 ПОЛЬЗОВАТЕЛИ:</b>\n"
        f"├ Всего: {bot_stats['total_users']}\n"
        f"├ Активны сегодня: {bot_stats['active_today']}\n"
        f"├ Активны за неделю: {bot_stats['active_week']}\n"
        f"└ Активны за месяц: {bot_stats['active_month']}\n\n"
        f"<b>💰 ФИНАНСЫ:</b>\n"
        f"├ Общий баланс: {format_stars(sum(users_balance.values()))}\n"
        f"├ Всего ставок: {bot_stats['total_bets']}\n"
        f"├ Объём ставок: {format_stars(bot_stats['total_wagered'])}\n"
        f"├ Выплачено: {format_stars(bot_stats['total_paid'])}\n"
        f"├ Прибыль бота: {format_stars(bot_stats['total_profit'])}\n"
        f"├ Пополнений: {bot_stats['total_deposits']}\n"
        f"├ Сумма пополнений: {format_stars(bot_stats['total_deposit_amount'])}\n"
        f"├ Выводов: {bot_stats['total_withdrawals']}\n"
        f"├ Сумма выводов: {format_stars(bot_stats['total_withdrawal_amount'])}\n"
        f"└ Выплачено рефералам: {format_stars(bot_stats['total_referral_paid'])}\n\n"
        f"<b>🎮 ИГРЫ:</b>\n"
        f"├ CRASH: {bot_stats['crash_games_played']} игр\n"
        f"├ MINES: {bot_stats['mines_games_played']} игр\n"
        f"└ PLINKO: {bot_stats['plinko_games_played']} игр\n\n"
        f"<b>🕐 СИСТЕМА:</b>\n"
        f"├ Время работы: {format_time(int(uptime.total_seconds()))}\n"
        f"├ Последний бэкап: {bot_stats['last_backup'] or 'никогда'}\n"
        f"├ Всего действий админов: {bot_stats['total_admin_actions']}\n"
        f"└ Активных игр: {len(active_crash) + len(active_mines) + len(active_plinko)}"
    )
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())


# ===================== АДМИН: НАСТРОЙКИ ИГР =====================
@dp.message(F.text == "⚙️ Настройки игр")
async def admin_game_settings(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    text = (
        f"⚙️ <b>НАСТРОЙКИ ИГР</b>\n\n"
        f"<b>📈 CRASH:</b>\n"
        f"├ Макс. множитель: x{bot_settings['crash_max_multiplier']}\n"
        f"└ House Edge: {(1 - bot_settings['crash_house_edge']) * 100}%\n\n"
        f"<b>💣 MINES:</b>\n"
        f"├ Размер поля: {bot_settings['mines_board_size']}x{bot_settings['mines_board_size']}\n"
        f"└ Количество мин: {bot_settings['mines_mines_count']}\n\n"
        f"<b>⚡ PLINKO:</b>\n"
        f"└ Множители: 8/12/16 линий\n\n"
        f"<b>💰 Системные:</b>\n"
        f"├ Мин. ставка: {MIN_BET}\n"
        f"├ Макс. ставка: {MAX_BET}\n"
        f"├ Реферальный %: {REFERRAL_BONUS_PERCENT}%\n"
        f"├ Ежедневный бонус: {'Вкл' if bot_settings['daily_bonus_enabled'] else 'Выкл'}\n"
        f"├ Мин. бонус: {DAILY_BONUS_MIN}\n"
        f"├ Макс. бонус: {DAILY_BONUS_MAX}\n"
        f"├ Мин. вывод: {WITHDRAWAL_MIN}\n"
        f"├ Макс. вывод: {WITHDRAWAL_MAX}\n"
        f"├ Антиспам: {'Вкл' if bot_settings['antispam_enabled'] else 'Выкл'}\n"
        f"└ Режим обслуживания: {'Вкл' if bot_settings['maintenance_mode'] else 'Выкл'}\n\n"
        f"💡 Для изменения настроек используйте команды:\n"
        f"• /set_min_bet <сумма>\n"
        f"• /set_max_bet <сумма>\n"
        f"• /set_house_edge <процент>\n"
        f"• /set_daily_bonus <вкл/выкл>\n"
        f"• /set_maintenance <вкл/выкл>\n"
        f"• /set_withdrawal_min <сумма>\n"
        f"• /set_withdrawal_max <сумма>\n"
        f"• /set_antispam <вкл/выкл>"
    )
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())


# ===================== АДМИН: ИЗМЕНЕНИЕ НАСТРОЕК =====================
@dp.message(Command("set_min_bet"))
async def set_min_bet(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_min_bet <сумма>")
        return
    
    try:
        new_min = float(args[1])
        if new_min < 0.1:
            await message.answer("❌ Минимальная ставка не может быть меньше 0.1")
            return
        
        global MIN_BET
        MIN_BET = new_min
        bot_settings["min_bet"] = new_min
        
        await message.answer(f"✅ Минимальная ставка установлена: {format_stars(MIN_BET)}")
        bot_stats["total_admin_actions"] += 1
    except:
        await message.answer("❌ Введите число!")

@dp.message(Command("set_max_bet"))
async def set_max_bet(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_max_bet <сумма>")
        return
    
    try:
        new_max = float(args[1])
        if new_max < MIN_BET:
            await message.answer(f"❌ Максимальная ставка не может быть меньше минимальной ({MIN_BET})")
            return
        
        global MAX_BET
        MAX_BET = new_max
        bot_settings["max_bet"] = new_max
        
        await message.answer(f"✅ Максимальная ставка установлена: {format_stars(MAX_BET)}")
        bot_stats["total_admin_actions"] += 1
    except:
        await message.answer("❌ Введите число!")

@dp.message(Command("set_house_edge"))
async def set_house_edge(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_house_edge <процент>")
        return
    
    try:
        percent = float(args[1])
        if percent < 0 or percent > 50:
            await message.answer("❌ House edge должен быть от 0 до 50%")
            return
        
        bot_settings["crash_house_edge"] = (100 - percent) / 100
        
        await message.answer(f"✅ House edge установлен: {percent}% (множитель: x{bot_settings['crash_house_edge']})")
        bot_stats["total_admin_actions"] += 1
    except:
        await message.answer("❌ Введите число!")

@dp.message(Command("set_daily_bonus"))
async def set_daily_bonus(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_daily_bonus <вкл/выкл>")
        return
    
    value = args[1].lower()
    if value in ["вкл", "on"]:
        bot_settings["daily_bonus_enabled"] = True
        await message.answer("✅ Ежедневный бонус ВКЛЮЧЁН!")
    elif value in ["выкл", "off"]:
        bot_settings["daily_bonus_enabled"] = False
        await message.answer("✅ Ежедневный бонус ВЫКЛЮЧЁН!")
    else:
        await message.answer("❌ Используйте 'вкл' или 'выкл'")
    
    bot_stats["total_admin_actions"] += 1

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
        bot_stats["last_maintenance"] = datetime.now().isoformat()
        await message.answer("🔧 Режим обслуживания ВКЛЮЧЁН! Пользователи не смогут играть.")
    elif value in ["выкл", "off"]:
        bot_settings["maintenance_mode"] = False
        await message.answer("✅ Режим обслуживания ВЫКЛЮЧЁН! Бот снова работает.")
    else:
        await message.answer("❌ Используйте 'вкл' или 'выкл'")
    
    bot_stats["total_admin_actions"] += 1

@dp.message(Command("set_withdrawal_min"))
async def set_withdrawal_min(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_withdrawal_min <сумма>")
        return
    
    try:
        new_min = float(args[1])
        if new_min < 1:
            await message.answer("❌ Минимальный вывод не может быть меньше 1")
            return
        
        global WITHDRAWAL_MIN
        WITHDRAWAL_MIN = new_min
        bot_settings["withdrawal_min"] = new_min
        
        await message.answer(f"✅ Минимальный вывод установлен: {format_stars(WITHDRAWAL_MIN)}")
        bot_stats["total_admin_actions"] += 1
    except:
        await message.answer("❌ Введите число!")

@dp.message(Command("set_withdrawal_max"))
async def set_withdrawal_max(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_withdrawal_max <сумма>")
        return
    
    try:
        new_max = float(args[1])
        if new_max < WITHDRAWAL_MIN:
            await message.answer(f"❌ Максимальный вывод не может быть меньше минимального ({WITHDRAWAL_MIN})")
            return
        
        global WITHDRAWAL_MAX
        WITHDRAWAL_MAX = new_max
        bot_settings["withdrawal_max"] = new_max
        
        await message.answer(f"✅ Максимальный вывод установлен: {format_stars(WITHDRAWAL_MAX)}")
        bot_stats["total_admin_actions"] += 1
    except:
        await message.answer("❌ Введите число!")

@dp.message(Command("set_antispam"))
async def set_antispam(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_antispam <вкл/выкл>")
        return
    
    value = args[1].lower()
    if value in ["вкл", "on"]:
        bot_settings["antispam_enabled"] = True
        await message.answer("✅ Антиспам система ВКЛЮЧЕНА!")
    elif value in ["выкл", "off"]:
        bot_settings["antispam_enabled"] = False
        await message.answer("✅ Антиспам система ВЫКЛЮЧЕНА!")
    else:
        await message.answer("❌ Используйте 'вкл' или 'выкл'")
    
    bot_stats["total_admin_actions"] += 1


# ===================== АДМИН: ПРОЧИЕ ФУНКЦИИ =====================
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
        await message.answer("❌ Пользователь не найден!")
        return
    
    await state.update_data(target_user=user_id, target_username=input_text)
    await state.set_state(GameStates.admin_change_balance)
    await message.answer(
        f"👤 @{input_text}\n"
        f"💰 Баланс: {format_stars(get_user_balance(user_id))}\n\n"
        f"💰 Введите сумму изменения:\n"
        f"• <b>+100</b> — добавить 100 Stars\n"
        f"• <b>-50</b> — снять 50 Stars",
        parse_mode=ParseMode.HTML
    )

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
            await bot.send_message(
                target_user,
                f"👑 <b>Администратор изменил ваш баланс!</b>\n\n"
                f"{'+' if amount > 0 else ''}{format_stars(amount)}\n"
                f"💰 Новый баланс: {format_stars(new_balance)}",
                parse_mode=ParseMode.HTML
            )
        except:
            pass
        
        save_transaction(target_user, amount, "admin_change", f"Админ: {amount}", "admin")
        bot_stats["total_admin_actions"] += 1
        
        await state.clear()
        await message.answer(
            f"✅ Баланс @{target_username} изменён на {format_stars(amount)}\n"
            f"💰 Новый баланс: {format_stars(new_balance)}",
            reply_markup=get_admin_main_keyboard()
        )
    except:
        await message.answer("❌ Введите число!")

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

@dp.message(GameStates.admin_send_broadcast)
async def admin_broadcast_message(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Рассылка отменена.", reply_markup=get_admin_main_keyboard())
        return
    
    await state.update_data(broadcast_msg=message)
    await state.set_state(GameStates.admin_send_broadcast_confirm)
    
    recipients = len([uid for uid in users_balance.keys() if not users_ban.get(uid, False)])
    
    await message.answer(
        f"📨 <b>ПОДТВЕРЖДЕНИЕ РАССЫЛКИ</b>\n\n"
        f"📊 Получателей: {recipients}\n\n"
        f"<b>Сообщение:</b>\n{message.text if message.text else '[Медиафайл]'}\n\n"
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
    
    progress_msg = await callback.message.edit_text(
        "📢 <b>ИДЁТ РАССЫЛКА...</b>\n\n"
        "⏳ Пожалуйста, подождите...",
        parse_mode=ParseMode.HTML
    )
    
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
            elif msg.document:
                await bot.send_document(user_id, msg.document.file_id, caption=msg.caption)
            else:
                await bot.copy_message(user_id, msg.chat.id, msg.message_id)
            success += 1
        except:
            fail += 1
        await asyncio.sleep(0.05)
    
    await state.clear()
    bot_stats["total_admin_actions"] += 1
    
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
    
    text = "👥 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ</b>\n\n" + "\n".join(users_list[:50])
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
        "<i>Для разбана используйте /unban</i>\n"
        "<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

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
        if users_ban[user_id]:
            await bot.send_message(
                user_id,
                f"🚫 <b>Ваш аккаунт заблокирован!</b>\n\n"
                f"Причина: Нарушение правил\n"
                f"Для получения информации: {bot_settings['support_link']}",
                parse_mode=ParseMode.HTML
            )
        else:
            await bot.send_message(
                user_id,
                f"✅ <b>Ваш аккаунт разблокирован!</b>\n\n"
                f"Вы снова можете пользоваться ботом.\n"
                f"💰 Ваш баланс сохранён.",
                parse_mode=ParseMode.HTML
            )
    except:
        pass
    
    await state.clear()
    bot_stats["total_admin_actions"] += 1
    await message.answer(f"✅ Пользователь {status}!", reply_markup=get_admin_main_keyboard())

@dp.message(Command("unban"))
async def admin_unban(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Укажите username или ID!\nПример: <code>/unban username</code>", parse_mode=ParseMode.HTML)
        return
    
    input_text = args[1].replace("@", "")
    user_id = await get_user_id_by_username(input_text)
    if not user_id:
        try:
            user_id = int(input_text)
        except:
            pass
    
    if not user_id or user_id not in users_balance:
        await message.answer("❌ Пользователь не найден!")
        return
    
    if not users_ban.get(user_id, False):
        await message.answer("⚠️ Пользователь не забанен!")
        return
    
    users_ban[user_id] = False
    users_ban_reason[user_id] = ""
    
    try:
        await bot.send_message(
            user_id,
            f"✅ <b>Ваш аккаунт разблокирован!</b>\n\n"
            f"Вы снова можете пользоваться ботом.\n"
            f"💰 Ваш баланс сохранён.",
            parse_mode=ParseMode.HTML
        )
    except:
        pass
    
    bot_stats["total_admin_actions"] += 1
    await message.answer(f"✅ Пользователь разбанен!", reply_markup=get_admin_main_keyboard())

@dp.message(F.text == "✅ Верификация")
async def admin_verify_start(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await state.set_state(GameStates.admin_set_verify)
    await message.answer(
        "✅ <b>ВЕРИФИКАЦИЯ</b>\n\n"
        "Введите username (без @) или ID пользователя для верификации:\n\n"
        "<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

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
        await bot.send_message(
            user_id,
            f"✅ <b>Ваш аккаунт {status}!</b>\n\n"
            f"Статус: {'Верифицирован' if users_verify[user_id] else 'Не верифицирован'}",
            parse_mode=ParseMode.HTML
        )
    except:
        pass
    
    await state.clear()
    bot_stats["total_admin_actions"] += 1
    await message.answer(f"✅ Пользователь {status}!", reply_markup=get_admin_main_keyboard())

@dp.message(F.text == "🎁 Промокоды")
async def admin_promo_create(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await state.set_state(GameStates.admin_promo_create)
    await message.answer(
        "🎁 <b>СОЗДАНИЕ ПРОМОКОДА</b>\n\n"
        "Введите название промокода (латиницей):\n"
        "Пример: <code>WELCOME100</code>\n\n"
        "<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML
    )

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
        
        promo_codes[code] = {
            "amount": amount,
            "uses": 0,
            "max_uses": 100,
            "created": datetime.now().isoformat(),
            "created_by": message.from_user.id
        }
        
        await state.clear()
        bot_stats["total_admin_actions"] += 1
        await message.answer(
            f"✅ Промокод <code>{code}</code> создан!\n\n"
            f"💰 Сумма: {format_stars(amount)}\n"
            f"📊 Макс. использований: 100\n"
            f"🕐 Создан: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_main_keyboard()
        )
    except:
        await message.answer("❌ Введите число!")

@dp.message(F.text == "🎲 Глобальный бонус")
async def admin_global_bonus(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await state.set_state(GameStates.admin_global_bonus)
    await message.answer(
        "🎲 <b>ГЛОБАЛЬНЫЙ БОНУС</b>\n\n"
        "Введите сумму бонуса для всех пользователей:\n\n"
        "<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML
    )

@dp.message(GameStates.admin_global_bonus)
async def admin_global_bonus_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
        count = 0
        
        progress_msg = await message.answer("🎁 <b>Выдача бонуса...</b>", parse_mode=ParseMode.HTML)
        
        for user_id in users_balance.keys():
            if not users_ban.get(user_id, False):
                update_balance(user_id, amount)
                try:
                    await bot.send_message(
                        user_id,
                        f"🎉 <b>Глобальный бонус от администратора!</b>\n\n"
                        f"+{format_stars(amount)}\n"
                        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass
                count += 1
            await asyncio.sleep(0.05)
        
        await state.clear()
        bot_stats["total_admin_actions"] += 1
        await progress_msg.edit_text(
            f"✅ <b>Глобальный бонус выдан!</b>\n\n"
            f"💰 Сумма: {format_stars(amount)}\n"
            f"👥 Получили: {count} пользователей",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_main_keyboard()
        )
    except:
        await message.answer("❌ Введите число!")

@dp.message(F.text == "📈 Экспорт данных")
async def admin_export_data(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    data = {
        "users": {uid: {"balance": bal, "username": users_username.get(uid), "verify": users_verify.get(uid, False)} for uid, bal in users_balance.items()},
        "stats": users_stats,
        "transactions": {uid: tx[-50:] for uid, tx in transactions.items()},
        "promo_codes": promo_codes,
        "bot_stats": bot_stats,
        "export_date": datetime.now().isoformat()
    }
    
    filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    await message.answer_document(FSInputFile(filename), caption=f"📊 Экспорт данных от {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    os.remove(filename)
    bot_stats["total_admin_actions"] += 1

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
        "ban_reason": users_ban_reason,
        "verify": users_verify,
        "promo_codes": promo_codes,
        "bot_stats": bot_stats,
        "daily_bonus": users_daily_bonus,
        "daily_bonus_streak": users_daily_bonus_streak,
        "settings": bot_settings
    }
    
    try:
        with open("backup.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        bot_stats["last_backup"] = datetime.now().isoformat()
        bot_stats["total_admin_actions"] += 1
        
        await message.answer(
            f"✅ <b>Данные сохранены!</b>\n\n"
            f"📁 Файл: backup.json\n"
            f"🕐 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"📊 Размер: {os.path.getsize('backup.json')} байт",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_main_keyboard()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=get_admin_main_keyboard())


@dp.message(F.text == "🔙 В главное меню")
async def back_to_main(message: Message):
    await message.answer(
        "🌟 <b>Главное меню</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(message.from_user.id)
    )


@dp.callback_query(F.data == "back_to_games")
async def back_to_games_callback(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎮 <b>Выберите игру</b>\n\n"
        "👇 Нажмите на кнопку с игрой:",
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


# ===================== ПЛАТЕЖИ =====================
async def create_stars_invoice(message: Message, user_id: int, amount: int):
    title = "⭐️ Пополнение StarPlay"
    description = f"Пополнение игрового баланса на {amount} Telegram Stars"
    payload = f"starplay_{user_id}_{amount}_{int(datetime.now().timestamp())}"
    prices = [LabeledPrice(label="Telegram Stars", amount=amount)]
    
    await bot.send_invoice(
        chat_id=user_id,
        title=title,
        description=description,
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=prices,
        start_parameter="starplay_deposit",
        need_name=False,
        need_phone_number=False,
        need_email=False,
        need_shipping_address=False,
        is_flexible=False
    )
    
    pending_payments[payload] = {
        "user_id": user_id,
        "amount": amount,
        "status": "pending",
        "timestamp": datetime.now().isoformat()
    }

@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    payload = pre_checkout_query.invoice_payload
    
    if payload in pending_payments:
        await pre_checkout_query.answer(ok=True)
    else:
        await pre_checkout_query.answer(ok=False, error_message="Ошибка платежа")

@dp.message(F.successful_payment)
async def process_successful_payment(message: Message):
    payment = message.successful_payment
    payload = payment.invoice_payload
    amount = payment.total_amount
    user_id = message.from_user.id
    
    if payload not in pending_payments:
        await message.answer("⚠️ Ошибка обработки платежа!")
        return
    
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
            save_transaction(referrer_id, bonus, "referral_earning", f"{REFERRAL_BONUS_PERCENT}% от пополнения реферала")
            bot_stats["total_referral_paid"] += bonus
            try:
                await bot.send_message(
                    referrer_id,
                    f"🎉 <b>Реферальный бонус!</b>\n\n"
                    f"Ваш реферал @{message.from_user.username or user_id} пополнил баланс!\n"
                    f"💰 Пополнение: {format_stars(amount)}\n"
                    f"🎁 Ваш бонус: {format_stars(bonus)}",
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
            f"💰 Минимальная сумма: 10 Stars\n"
            f"💰 Максимальная сумма: 10000 Stars\n\n"
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
        if amount < 10:
            await message.answer("❌ Минимальная сумма: 10 Stars")
            return
        if amount > 10000:
            await message.answer("❌ Максимальная сумма: 10000 Stars")
            return
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число!")
        return
    
    await state.clear()
    await create_stars_invoice(message, message.from_user.id, amount)

@dp.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Действие отменено.",
        reply_markup=get_main_keyboard(message.from_user.id)
    )


# ===================== ЗАПУСК =====================
async def main():
    logger.info("🚀 StarPlay Casino Bot запускается...")
    
    # Загружаем данные из бэкапа если есть
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
                users_daily_bonus.update(data.get("daily_bonus", {}))
                users_daily_bonus_streak.update(data.get("daily_bonus_streak", {}))
                logger.info("✅ Данные загружены из backup.json")
        except:
            logger.warning("⚠️ Не удалось загрузить backup.json")
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())