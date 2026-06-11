import asyncio
import hashlib
import logging
import random
import json
import time
import math
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Union
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
    FSInputFile, InputFile, InputMediaPhoto
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
DICE_MULTIPLIER = 1.9

# Реферальная система
REFERRAL_BONUS_PERCENT = 10
REFERRAL_SIGNUP_BONUS = 5
REFERRAL_INVITE_BONUS = 10

# Системные настройки
MIN_BET = 1
MAX_BET = 10000
DAILY_BONUS_MIN = 5
DAILY_BONUS_MAX = 25
DAILY_BONUS_STREAK_MULTIPLIER = 0.5

# Админ-панель
ADMIN_STATS_UPDATE_INTERVAL = 60  # секунд
BACKUP_INTERVAL = 3600  # 1 час

# Пути для файлов
DATA_DIR = "data"
BACKUP_DIR = "backups"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

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
users_admin_notes: Dict[int, str] = {}
users_verify: Dict[int, bool] = {}
users_verify_code: Dict[int, str] = {}
users_settings: Dict[int, dict] = {}
users_notifications: Dict[int, bool] = {}
users_language: Dict[int, str] = {}

# Игровые данные
active_crash: Dict[int, dict] = {}
active_mines: Dict[int, dict] = {}
active_dice: Dict[int, dict] = {}

# История игр
crash_history: List[dict] = []
mines_history: List[dict] = []
dice_history: List[dict] = []

# Промокоды
promo_codes: Dict[str, dict] = {}

# Системные переменные
system_settings = {
    "maintenance_mode": False,
    "maintenance_message": "🔧 Бот на техническом обслуживании",
    "min_bet": MIN_BET,
    "max_bet": MAX_BET,
    "crash_house_edge": CRASH_HOUSE_EDGE,
    "referral_percent": REFERRAL_BONUS_PERCENT,
    "daily_bonus_enabled": True,
    "chat_link": "https://t.me/starplay_chat",
    "channel_link": "https://t.me/starplay_news",
    "support_link": "https://t.me/starplay_support"
}

# Статистика бота
bot_stats = {
    "total_users": 0,
    "active_today": 0,
    "active_this_week": 0,
    "active_this_month": 0,
    "total_bets": 0,
    "total_wagered": 0.0,
    "total_paid": 0.0,
    "total_profit": 0.0,
    "total_deposits": 0,
    "total_deposit_amount": 0.0,
    "total_withdrawals": 0,
    "total_withdrawal_amount": 0.0,
    "crash_games_played": 0,
    "crash_games_won": 0,
    "mines_games_played": 0,
    "mines_games_won": 0,
    "dice_games_played": 0,
    "dice_games_won": 0,
    "server_start_time": datetime.now().isoformat(),
    "last_backup": None,
    "total_bonus_given": 0.0,
    "total_referral_bonus": 0.0
}

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'{DATA_DIR}/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# ===================== FSM СОСТОЯНИЯ =====================
class GameStates(StatesGroup):
    # Основные
    main_menu = State()
    
    # Игры
    crash_bet = State()
    crash_waiting = State()
    mines_bet = State()
    mines_playing = State()
    dice_bet = State()
    dice_playing = State()
    
    # Платежи
    custom_deposit = State()
    custom_withdraw = State()
    
    # Рефералы
    referral_menu = State()
    
    # Админ
    admin_main = State()
    admin_find_user = State()
    admin_change_balance = State()
    admin_send_broadcast = State()
    admin_send_broadcast_text = State()
    admin_send_broadcast_confirm = State()
    admin_ban_user = State()
    admin_unban_user = State()
    admin_set_verify = State()
    admin_settings = State()
    admin_crash_settings = State()
    admin_mines_settings = State()
    admin_dice_settings = State()
    admin_promo_create = State()
    admin_promo_amount = State()
    admin_backup = State()
    admin_restore = State()
    admin_export = State()
    admin_import_data = State()
    admin_announcement = State()
    admin_global_bonus = State()
    admin_global_bonus_amount = State()
    admin_reset_stats = State()
    admin_clear_history = State()
    admin_view_user = State()
    admin_user_transactions = State()
    admin_user_stats = State()
    admin_edit_user_note = State()
    admin_blacklist_add = State()
    admin_blacklist_remove = State()


# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
def is_admin(username: str) -> bool:
    """Проверка является ли пользователь админом"""
    return username.lower() in [adm.lower() for adm in ADMIN_USERNAMES]

async def get_user_id_by_username(username: str) -> Optional[int]:
    """Получение user_id по username"""
    for uid, uname in users_username.items():
        if uname and uname.lower() == username.lower():
            return uid
    return None

def format_stars(amount: float) -> str:
    """Форматирование суммы Stars"""
    if amount >= 1000000:
        return f"⭐️ {amount/1000000:.1f}M"
    elif amount >= 1000:
        return f"⭐️ {amount/1000:.1f}K"
    return f"⭐️ {amount:.2f}"

def get_user_balance(user_id: int) -> float:
    """Получение баланса пользователя"""
    return users_balance.get(user_id, 0.0)

def update_balance(user_id: int, delta: float) -> float:
    """Обновление баланса пользователя"""
    current = users_balance.get(user_id, 0.0)
    new_balance = current + delta
    if new_balance < 0:
        new_balance = 0.0
    users_balance[user_id] = round(new_balance, 2)
    return users_balance[user_id]

def save_transaction(user_id: int, amount: float, tx_type: str, details: str = "", game: str = ""):
    """Сохранение транзакции"""
    if user_id not in transactions:
        transactions[user_id] = []
    
    transactions[user_id].append({
        "amount": round(amount, 2),
        "type": tx_type,
        "details": details,
        "game": game,
        "timestamp": datetime.now().isoformat()
    })
    
    # Ограничиваем историю транзакций
    if len(transactions[user_id]) > 100:
        transactions[user_id] = transactions[user_id][-100:]
    
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
    elif tx_type == "daily_bonus":
        bot_stats["total_bonus_given"] += amount
    elif tx_type == "referral_reward":
        bot_stats["total_referral_bonus"] += amount
    
    bot_stats["total_profit"] = bot_stats["total_wagered"] - bot_stats["total_paid"]

def get_user_stats(user_id: int) -> dict:
    """Получение статистики пользователя"""
    if user_id not in users_stats:
        users_stats[user_id] = {
            "games_played": 0,
            "games_won": 0,
            "total_won": 0.0,
            "total_lost": 0.0,
            "crash_games": 0,
            "crash_wins": 0,
            "crash_best_multiplier": 0.0,
            "mines_games": 0,
            "mines_wins": 0,
            "mines_best_multiplier": 0.0,
            "dice_games": 0,
            "dice_wins": 0,
            "dice_best_multiplier": 0.0,
            "total_deposits": 0,
            "total_deposit_amount": 0.0,
            "total_withdrawals": 0,
            "total_withdrawal_amount": 0.0,
            "referral_count": 0,
            "referral_earned": 0.0,
            "daily_bonus_count": 0,
            "daily_bonus_streak": 0,
            "last_game_played": None,
            "total_bets": 0
        }
    return users_stats[user_id]

def get_random_emoji() -> str:
    """Случайный эмодзи для настроения"""
    emojis = ["🎲", "🎯", "⚡️", "💫", "🌟", "⭐️", "✨", "🎮", "🎰", "🔥", "💰", "💎", "🏆", "🎉", "🚀", "⚡", "💪", "🏅", "🌟", "🎪"]
    return random.choice(emojis)

def generate_referral_link(user_id: int) -> str:
    """Генерация реферальной ссылки"""
    code = hashlib.md5(f"starplay_{user_id}_{datetime.now().date()}".encode()).hexdigest()[:8]
    return f"https://t.me/{bot.username}?start=ref_{code}"

def format_time(seconds: int) -> str:
    """Форматирование времени"""
    if seconds < 60:
        return f"{seconds} сек"
    elif seconds < 3600:
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins} мин {secs} сек"
    elif seconds < 86400:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours} ч {mins} мин"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days} д {hours} ч"

def calculate_crash_multiplier() -> float:
    """Расчёт множителя для Crash игры"""
    # Используем экспоненциальное распределение
    r = random.random()
    multiplier = 1.0 / (1.0 - r * (1.0 - CRASH_HOUSE_EDGE))
    return min(multiplier, CRASH_MAX_MULTIPLIER)

def generate_mines_board() -> Tuple[List[List[str]], List[List[bool]]]:
    """Генерация поля для Mines"""
    board = [["💎" for _ in range(MINES_BOARD_SIZE)] for _ in range(MINES_BOARD_SIZE)]
    mines_placed = 0
    while mines_placed < MINES_MINES_COUNT:
        x, y = random.randint(0, MINES_BOARD_SIZE - 1), random.randint(0, MINES_BOARD_SIZE - 1)
        if board[x][y] == "💎":
            board[x][y] = "💣"
            mines_placed += 1
    revealed = [[False] * MINES_BOARD_SIZE for _ in range(MINES_BOARD_SIZE)]
    return board, revealed

def save_backup():
    """Сохранение резервной копии данных"""
    backup_data = {
        "users_balance": users_balance,
        "users_referrer": users_referrer,
        "users_referrals": users_referrals,
        "users_stats": users_stats,
        "users_daily_bonus": users_daily_bonus,
        "users_username": users_username,
        "users_join_date": users_join_date,
        "users_ban": users_ban,
        "users_verify": users_verify,
        "transactions": transactions,
        "crash_history": crash_history,
        "mines_history": mines_history,
        "dice_history": dice_history,
        "promo_codes": promo_codes,
        "bot_stats": bot_stats,
        "backup_date": datetime.now().isoformat()
    }
    
    filename = f"{BACKUP_DIR}/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, indent=2, ensure_ascii=False, default=str)
    
    # Удаляем старые бэкапы (оставляем последние 10)
    backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith("backup_")])
    for old_backup in backups[:-10]:
        os.remove(os.path.join(BACKUP_DIR, old_backup))
    
    bot_stats["last_backup"] = datetime.now().isoformat()
    logger.info(f"Backup saved: {filename}")
    return filename

def load_backup(filepath: str) -> bool:
    """Загрузка резервной копии"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        global users_balance, users_referrer, users_referrals, users_stats
        global users_daily_bonus, users_username, users_join_date, users_ban, users_verify
        global transactions, crash_history, mines_history, dice_history, promo_codes, bot_stats
        
        users_balance = data.get("users_balance", {})
        users_referrer = data.get("users_referrer", {})
        users_referrals = data.get("users_referrals", {})
        users_stats = data.get("users_stats", {})
        users_daily_bonus = data.get("users_daily_bonus", {})
        users_username = data.get("users_username", {})
        users_join_date = data.get("users_join_date", {})
        users_ban = data.get("users_ban", {})
        users_verify = data.get("users_verify", {})
        transactions = data.get("transactions", {})
        crash_history = data.get("crash_history", [])
        mines_history = data.get("mines_history", [])
        dice_history = data.get("dice_history", [])
        promo_codes = data.get("promo_codes", {})
        bot_stats.update(data.get("bot_stats", {}))
        
        logger.info(f"Backup loaded: {filepath}")
        return True
    except Exception as e:
        logger.error(f"Failed to load backup: {e}")
        return False

def auto_backup_task():
    """Автоматическое резервное копирование"""
    async def backup_loop():
        while True:
            await asyncio.sleep(BACKUP_INTERVAL)
            save_backup()
    return backup_loop

def update_user_activity(user_id: int):
    """Обновление активности пользователя"""
    users_last_seen[user_id] = datetime.now().isoformat()
    
    today = datetime.now().date().isoformat()
    week_ago = (datetime.now() - timedelta(days=7)).date().isoformat()
    month_ago = (datetime.now() - timedelta(days=30)).date().isoformat()
    
    # Здесь можно добавить логику подсчёта активных пользователей
    # Для простоты пока обновляем только last_seen


# ===================== КЛАВИАТУРЫ =====================
def get_main_keyboard(user_id: int = None) -> ReplyKeyboardMarkup:
    """Главная клавиатура"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="💰 Баланс")
    builder.button(text="⭐️ Пополнить")
    builder.button(text="🎮 Игры")
    builder.button(text="👥 Рефералы")
    builder.button(text="🏆 Топ")
    builder.button(text="📊 Профиль")
    builder.button(text="🎁 Бонус")
    builder.button(text="⚙️ Настройки")
    builder.button(text="❓ Помощь")
    
    if user_id and is_admin(users_username.get(user_id, "")):
        builder.button(text="👑 Админ панель")
    
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_admin_main_keyboard() -> ReplyKeyboardMarkup:
    """Главная админ-клавиатура"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="📊 Статистика")
    builder.button(text="💰 Изменить баланс")
    builder.button(text="📢 Рассылка")
    builder.button(text="👥 Пользователи")
    builder.button(text="🔨 Бан/Разбан")
    builder.button(text="✅ Верификация")
    builder.button(text="⚙️ Настройки")
    builder.button(text="🎮 Управление играми")
    builder.button(text="🎁 Промокоды")
    builder.button(text="💾 Резервное копирование")
    builder.button(text="📈 Экспорт данных")
    builder.button(text="🔧 Системные настройки")
    builder.button(text="🔙 В главное меню")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_games_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура игр"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="📈 CRASH")
    builder.button(text="💣 MINES")
    builder.button(text="🎲 DICE")
    builder.button(text="📊 История игр")
    builder.button(text="🔙 Главное меню")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_user_settings_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура настроек пользователя"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔔 Уведомления", callback_data="settings_notifications"),
         InlineKeyboardButton(text="🌐 Язык", callback_data="settings_language")],
        [InlineKeyboardButton(text="🔒 Безопасность", callback_data="settings_security"),
         InlineKeyboardButton(text="📊 Сбросить статистику", callback_data="settings_reset_stats")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])

def get_language_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора языка"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="settings_back")]
    ])

def get_crash_bet_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора ставки для Crash"""
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
    """Клавиатура во время игры Crash"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 ЗАБРАТЬ ВЫИГРЫШ", callback_data="crash_cashout")],
        [InlineKeyboardButton(text="❌ ВЫЙТИ", callback_data="crash_exit")]
    ])

def get_mines_bet_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора ставки для Mines"""
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

def get_dice_bet_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора ставки для Dice"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐️ 1", callback_data="dice_bet_1"),
         InlineKeyboardButton(text="⭐️ 5", callback_data="dice_bet_5"),
         InlineKeyboardButton(text="⭐️ 10", callback_data="dice_bet_10")],
        [InlineKeyboardButton(text="⭐️ 25", callback_data="dice_bet_25"),
         InlineKeyboardButton(text="⭐️ 50", callback_data="dice_bet_50"),
         InlineKeyboardButton(text="⭐️ 100", callback_data="dice_bet_100")],
        [InlineKeyboardButton(text="⭐️ 250", callback_data="dice_bet_250"),
         InlineKeyboardButton(text="⭐️ 500", callback_data="dice_bet_500"),
         InlineKeyboardButton(text="⭐️ 1000", callback_data="dice_bet_1000")],
        [InlineKeyboardButton(text="✏️ Своя сумма", callback_data="dice_bet_custom")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_games")]
    ])

def get_dice_predict_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора предсказания для Dice"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬆️ ВЫШЕ 50", callback_data="dice_higher"),
         InlineKeyboardButton(text="⬇️ НИЖЕ 50", callback_data="dice_lower")],
        [InlineKeyboardButton(text="🎲 БРОСИТЬ КУБИК", callback_data="dice_roll")]
    ])

def get_mines_board_keyboard(board: List[List[str]], revealed: List[List[bool]], bet: float, multiplier: float) -> InlineKeyboardMarkup:
    """Клавиатура для игры Mines"""
    keyboard = []
    for i in range(5):
        row = []
        for j in range(5):
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

def get_deposit_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура пополнения"""
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

def get_back_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура возврата"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_games")]
    ])

def get_confirm_keyboard(action: str, data: str = "") -> InlineKeyboardMarkup:
    """Клавиатура подтверждения действия"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_{action}_{data}"),
         InlineKeyboardButton(text="❌ Нет", callback_data="confirm_no")]
    ])


# ===================== ОСНОВНЫЕ КОМАНДЫ =====================
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username or ""
    
    # Проверка на бан
    if users_ban.get(user_id, False):
        await message.answer(
            f"🚫 <b>Ваш аккаунт заблокирован!</b>\n\n"
            f"Причина: {users_ban_reason.get(user_id, 'Не указана')}\n\n"
            f"Для решения вопроса обратитесь к администратору: {system_settings['support_link']}",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Проверка режима обслуживания
    if system_settings["maintenance_mode"] and not is_admin(username):
        await message.answer(
            f"{system_settings['maintenance_message']}\n\n"
            f"Пожалуйста, зайдите позже.",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Сохраняем данные пользователя
    users_username[user_id] = username
    update_user_activity(user_id)
    
    if user_id not in users_join_date:
        users_join_date[user_id] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        bot_stats["total_users"] += 1
    
    if user_id not in users_settings:
        users_settings[user_id] = {
            "notifications": True,
            "language": "ru",
            "auto_cashout": False,
            "auto_cashout_multiplier": 2.0
        }
    
    # Реферальная система
    if " " in message.text:
        param = message.text.split()[1]
        if param.startswith("ref_"):
            try:
                referrer_id = int(param[4:])
                if (referrer_id != user_id and 
                    user_id not in users_referrer and 
                    not users_ban.get(referrer_id, False)):
                    
                    users_referrer[user_id] = referrer_id
                    users_referrals.setdefault(referrer_id, []).append(user_id)
                    
                    # Начисляем бонусы
                    update_balance(user_id, REFERRAL_SIGNUP_BONUS)
                    update_balance(referrer_id, REFERRAL_INVITE_BONUS)
                    
                    # Обновляем статистику
                    stats = get_user_stats(referrer_id)
                    stats["referral_count"] += 1
                    stats["referral_earned"] += REFERRAL_INVITE_BONUS
                    
                    # Сохраняем транзакции
                    save_transaction(user_id, REFERRAL_SIGNUP_BONUS, "referral_bonus", 
                                   f"Регистрация по ссылке от {referrer_id}")
                    save_transaction(referrer_id, REFERRAL_INVITE_BONUS, "referral_reward", 
                                   f"Приглашение пользователя {user_id}")
                    
                    await message.answer(
                        f"✅ <b>Вы получили бонус за регистрацию!</b>\n\n"
                        f"+{format_stars(REFERRAL_SIGNUP_BONUS)}\n\n"
                        f"💡 Приглашайте друзей и получайте {REFERRAL_BONUS_PERCENT}% "
                        f"от их пополнений!",
                        parse_mode=ParseMode.HTML
                    )
                    
                    # Уведомляем реферера
                    try:
                        await bot.send_message(
                            referrer_id,
                            f"🎉 <b>По вашей реферальной ссылке зарегистрировался новый пользователь!</b>\n\n"
                            f"👤 {username or user_id}\n"
                            f"+{format_stars(REFERRAL_INVITE_BONUS)}\n\n"
                            f"Теперь вы будете получать {REFERRAL_BONUS_PERCENT}% "
                            f"от его пополнений!",
                            parse_mode=ParseMode.HTML
                        )
                    except:
                        pass
            except Exception as e:
                logger.error(f"Referral error: {e}")
    
    # Приветственное сообщение
    welcome_text = (
        f"🌟 <b>Добро пожаловать в StarPlay Casino!</b> 🌟\n\n"
        f"{get_random_emoji()} <b>Лучшее игровое казино в Telegram!</b>\n\n"
        f"<b>🎮 Игры:</b>\n"
        f"📈 <b>CRASH</b> — Растущий множитель до x{CRASH_MAX_MULTIPLIER}\n"
        f"💣 <b>MINES</b> — Сапёр с множителем до x{(1.2 ** (MINES_BOARD_SIZE * MINES_BOARD_SIZE - MINES_MINES_COUNT)):.1f}\n"
        f"🎲 <b>DICE</b> — Угадай число, множитель x{DICE_MULTIPLIER}\n\n"
        f"<b>💫 Как начать играть:</b>\n"
        f"1️⃣ Пополните баланс через Telegram Stars\n"
        f"2️⃣ Выберите игру в меню «🎮 Игры»\n"
        f"3️⃣ Делайте ставки и выигрывайте!\n\n"
        f"<b>🎁 Бонусы:</b>\n"
        f"• Ежедневный бонус до {DAILY_BONUS_MAX} Stars\n"
        f"• Реферальная программа: +{REFERRAL_BONUS_PERCENT}% с пополнений друзей\n"
        f"• Промокоды и розыгрыши\n\n"
        f"👇 <i>Используйте кнопки меню для навигации!</i>"
    )
    
    await state.clear()
    await message.answer(
        welcome_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(user_id)
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    help_text = (
        f"❓ <b>Помощь по боту StarPlay</b>\n\n"
        f"<b>🎮 Игры:</b>\n"
        f"📈 <b>CRASH</b> — Ставка растёт. Заберите выигрыш до взрыва!\n"
        f"   • Множитель увеличивается каждые 0.1 сек\n"
        f"   • Чем дольше ждёте — тем выше множитель\n"
        f"   • Если не забрали до взрыва — ставка сгорает\n"
        f"   • Максимальный множитель: x{CRASH_MAX_MULTIPLIER}\n\n"
        f"💣 <b>MINES</b> — Открывайте клетки с 💎, избегайте 💣\n"
        f"   • Поле {MINES_BOARD_SIZE}x{MINES_BOARD_SIZE}\n"
        f"   • Спрятано {MINES_MINES_COUNT} мин\n"
        f"   • Каждая 💎 увеличивает множитель x1.2\n"
        f"   • Можно забрать выигрыш в любой момент\n\n"
        f"🎲 <b>DICE</b> — Угадайте, выпадет число выше или ниже 50\n"
        f"   • Кубик бросается автоматически\n"
        f"   • При правильном угадывании выигрыш x{DICE_MULTIPLIER}\n"
        f"   • При неправильном — ставка сгорает\n\n"
        f"<b>💰 Баланс и пополнение:</b>\n"
        f"• Пополнение через Telegram Stars\n"
        f"• Минимальная ставка: {MIN_BET} Star\n"
        f"• Максимальная ставка: {MAX_BET} Stars\n\n"
        f"<b>👥 Реферальная система:</b>\n"
        f"• Пригласите друга — получите {REFERRAL_INVITE_BONUS} Stars\n"
        f"• Друг получает {REFERRAL_SIGNUP_BONUS} Stars\n"
        f"• Вы получаете {REFERRAL_BONUS_PERCENT}% от пополнений друга\n\n"
        f"<b>🎁 Ежедневный бонус:</b>\n"
        f"• Забирайте бонус каждый день в меню «🎁 Бонус»\n"
        f"• Чем дольше стрик — тем больше бонус!\n\n"
        f"<b>📞 Контакты:</b>\n"
        f"• Чат: {system_settings['chat_link']}\n"
        f"• Новости: {system_settings['channel_link']}\n"
        f"• Поддержка: {system_settings['support_link']}"
    )
    
    await message.answer(help_text, parse_mode=ParseMode.HTML)


# ===================== ГЛАВНЫЕ КНОПКИ =====================
@dp.message(F.text == "💰 Баланс")
async def balance_reply(message: Message):
    """Показать баланс"""
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    stats = get_user_stats(user_id)
    
    await message.answer(
        f"💰 <b>Ваш баланс</b>\n\n"
        f"{format_stars(balance)}\n\n"
        f"<b>📊 Краткая статистика сегодня:</b>\n"
        f"• Сыграно игр: {stats['games_played']}\n"
        f"• Побед: {stats['games_won']}\n"
        f"• Выиграно: {format_stars(stats['total_won'])}\n\n"
        f"💡 Приглашайте друзей и зарабатывайте больше!\n"
        f"🔗 Ваша реферальная ссылка: /referral",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(user_id)
    )


@dp.message(F.text == "⭐️ Пополнить")
async def deposit_reply(message: Message):
    """Пополнение баланса"""
    await message.answer(
        "⭐️ <b>Пополнение баланса</b>\n\n"
        "💰 <b>Способы пополнения:</b>\n"
        "• Telegram Stars — мгновенно, без комиссии\n\n"
        "💡 <b>Выберите сумму:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_deposit_keyboard()
    )


@dp.message(F.text == "🎮 Игры")
async def games_reply(message: Message):
    """Меню игр"""
    await message.answer(
        "🎮 <b>Выберите игру</b>\n\n"
        "📈 <b>CRASH</b> — Рискни и умножь ставку до x1000!\n"
        "💣 <b>MINES</b> — Найди сокровища, избегая мин\n"
        "🎲 <b>DICE</b> — Угадай выпадение кубика\n\n"
        "👇 <b>Нажмите на кнопку с игрой:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )


@dp.message(F.text == "👥 Рефералы")
async def referrals_reply(message: Message):
    """Реферальная система"""
    user_id = message.from_user.id
    ref_link = generate_referral_link(user_id)
    ref_count = len(users_referrals.get(user_id, []))
    
    stats = get_user_stats(user_id)
    total_earned = stats.get("referral_earned", 0.0)
    
    # Подсчёт потенциального заработка
    referral_stats = []
    for ref_id in users_referrals.get(user_id, []):
        ref_stats = get_user_stats(ref_id)
        referral_stats.append({
            "username": users_username.get(ref_id, str(ref_id)),
            "deposits": ref_stats.get("total_deposit_amount", 0)
        })
    
    text = (
        f"👥 <b>Реферальная программа</b>\n\n"
        f"🏆 <b>Ваша статистика:</b>\n"
        f"• Приглашено друзей: {ref_count}\n"
        f"• Заработано: {format_stars(total_earned)}\n\n"
        f"<b>📋 Как это работает:</b>\n"
        f"• Друг регистрируется по вашей ссылке\n"
        f"• Он получает +{REFERRAL_SIGNUP_BONUS} Stars\n"
        f"• Вы получаете +{REFERRAL_INVITE_BONUS} Stars\n"
        f"• Вы получаете {REFERRAL_BONUS_PERCENT}% от каждого пополнения друга\n\n"
        f"<b>🔗 Ваша реферальная ссылка:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"💡 Поделитесь ссылкой с друзьями и зарабатывайте!"
    )
    
    if referral_stats:
        text += f"\n\n<b>📊 Ваши рефералы:</b>\n"
        for ref in referral_stats[:5]:
            text += f"• @{ref['username']} — пополнил на {format_stars(ref['deposits'])}\n"
        if len(referral_stats) > 5:
            text += f"• ... и ещё {len(referral_stats) - 5} рефералов\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться ссылкой", 
                              url=f"https://t.me/share/url?url={ref_link}&text=StarPlay — лучшие игры с выигрышами! Присоединяйся!")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@dp.message(F.text == "🏆 Топ")
async def top_reply(message: Message):
    """Топ игроков"""
    # Сортируем по балансу
    sorted_by_balance = sorted(users_balance.items(), key=lambda x: x[1], reverse=True)[:15]
    
    # Сортируем по количеству побед
    sorted_by_wins = sorted(users_stats.items(), 
                           key=lambda x: x[1].get("games_won", 0), 
                           reverse=True)[:15]
    
    # Сортируем по общему выигрышу
    sorted_by_total_won = sorted(users_stats.items(), 
                                 key=lambda x: x[1].get("total_won", 0), 
                                 reverse=True)[:15]
    
    top_balance = "🏆 <b>ТОП-15 ПО БАЛАНСУ</b>\n\n"
    for idx, (uid, bal) in enumerate(sorted_by_balance, 1):
        if users_ban.get(uid, False):
            continue
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
        uname = users_username.get(uid, str(uid))
        name = f"@{uname}" if uname else str(uid)
        top_balance += f"{medal} {name} — {format_stars(bal)}\n"
    
    top_wins = "\n🏆 <b>ТОП-15 ПО ПОБЕДАМ</b>\n\n"
    for idx, (uid, stats) in enumerate(sorted_by_wins, 1):
        if users_ban.get(uid, False):
            continue
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
        uname = users_username.get(uid, str(uid))
        name = f"@{uname}" if uname else str(uid)
        wins = stats.get("games_won", 0)
        top_wins += f"{medal} {name} — {wins} 🏆\n"
    
    top_won = "\n🏆 <b>ТОП-15 ПО ВЫИГРЫШАМ</b>\n\n"
    for idx, (uid, stats) in enumerate(sorted_by_total_won, 1):
        if users_ban.get(uid, False):
            continue
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
        uname = users_username.get(uid, str(uid))
        name = f"@{uname}" if uname else str(uid)
        won = stats.get("total_won", 0)
        top_won += f"{medal} {name} — {format_stars(won)}\n"
    
    # Используем инлайн-клавиатуру для переключения между категориями
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 По балансу", callback_data="top_balance"),
         InlineKeyboardButton(text="🏆 По победам", callback_data="top_wins")],
        [InlineKeyboardButton(text="💎 По выигрышам", callback_data="top_won")]
    ])
    
    await message.answer(
        f"{top_balance}",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


@dp.callback_query(F.data.startswith("top_"))
async def top_callback(callback: CallbackQuery):
    """Обработчик переключения категорий топа"""
    category = callback.data.split("_")[1]
    
    if category == "balance":
        sorted_users = sorted(users_balance.items(), key=lambda x: x[1], reverse=True)[:15]
        text = "🏆 <b>ТОП-15 ПО БАЛАНСУ</b>\n\n"
        for idx, (uid, bal) in enumerate(sorted_users, 1):
            if users_ban.get(uid, False):
                continue
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
            uname = users_username.get(uid, str(uid))
            name = f"@{uname}" if uname else str(uid)
            text += f"{medal} {name} — {format_stars(bal)}\n"
    elif category == "wins":
        sorted_users = sorted(users_stats.items(), key=lambda x: x[1].get("games_won", 0), reverse=True)[:15]
        text = "🏆 <b>ТОП-15 ПО ПОБЕДАМ</b>\n\n"
        for idx, (uid, stats) in enumerate(sorted_users, 1):
            if users_ban.get(uid, False):
                continue
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
            uname = users_username.get(uid, str(uid))
            name = f"@{uname}" if uname else str(uid)
            wins = stats.get("games_won", 0)
            text += f"{medal} {name} — {wins} 🏆\n"
    else:
        sorted_users = sorted(users_stats.items(), key=lambda x: x[1].get("total_won", 0), reverse=True)[:15]
        text = "🏆 <b>ТОП-15 ПО ВЫИГРЫШАМ</b>\n\n"
        for idx, (uid, stats) in enumerate(sorted_users, 1):
            if users_ban.get(uid, False):
                continue
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
            uname = users_username.get(uid, str(uid))
            name = f"@{uname}" if uname else str(uid)
            won = stats.get("total_won", 0)
            text += f"{medal} {name} — {format_stars(won)}\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 По балансу", callback_data="top_balance"),
         InlineKeyboardButton(text="🏆 По победам", callback_data="top_wins")],
        [InlineKeyboardButton(text="💎 По выигрышам", callback_data="top_won")]
    ])
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()


@dp.message(F.text == "📊 Профиль")
async def profile_reply(message: Message):
    """Профиль пользователя"""
    uid = message.from_user.id
    stats = get_user_stats(uid)
    balance = get_user_balance(uid)
    
    win_rate = 0
    if stats['games_played'] > 0:
        win_rate = (stats['games_won'] / stats['games_played']) * 100
    
    total_profit = stats['total_won'] - stats['total_lost']
    
    profile_text = (
        f"👤 <b>Профиль игрока</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👤 Username: @{message.from_user.username or 'не установлен'}\n"
        f"📅 Регистрация: {users_join_date.get(uid, 'неизвестно')}\n"
        f"✅ Верификация: {'✅ Верифицирован' if users_verify.get(uid, False) else '❌ Не верифицирован'}\n\n"
        f"💰 <b>Баланс:</b> {format_stars(balance)}\n\n"
        f"📊 <b>Общая статистика:</b>\n"
        f"├ 🎮 Сыграно игр: {stats['games_played']}\n"
        f"├ 🏆 Побед: {stats['games_won']}\n"
        f"├ 📈 Винрейт: {win_rate:.1f}%\n"
        f"├ 💎 Выиграно: {format_stars(stats['total_won'])}\n"
        f"├ 💸 Проиграно: {format_stars(stats['total_lost'])}\n"
        f"└ 💰 Чистая прибыль: {format_stars(total_profit)}\n\n"
        f"📈 <b>Статистика по играм:</b>\n"
        f"├ 📈 CRASH: {stats['crash_games']} игр, {stats['crash_wins']} побед\n"
        f"│   └ Лучший множитель: x{stats['crash_best_multiplier']:.2f}\n"
        f"├ 💣 MINES: {stats['mines_games']} игр, {stats['mines_wins']} побед\n"
        f"│   └ Лучший множитель: x{stats['mines_best_multiplier']:.2f}\n"
        f"└ 🎲 DICE: {stats['dice_games']} игр, {stats['dice_wins']} побед\n\n"
        f"👥 <b>Рефералы:</b> {stats['referral_count']} чел., заработано: {format_stars(stats['referral_earned'])}\n"
        f"🎁 <b>Ежедневные бонусы:</b> {stats['daily_bonus_count']} раз\n"
        f"📅 <b>Стрик:</b> {stats['daily_bonus_streak']} дней"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Детальная статистика", callback_data="profile_stats")],
        [InlineKeyboardButton(text="📜 История транзакций", callback_data="profile_transactions")]
    ])
    
    await message.answer(profile_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@dp.callback_query(F.data == "profile_stats")
async def profile_stats_callback(callback: CallbackQuery):
    """Детальная статистика профиля"""
    uid = callback.from_user.id
    stats = get_user_stats(uid)
    
    text = (
        f"📊 <b>ДЕТАЛЬНАЯ СТАТИСТИКА</b>\n\n"
        f"<b>💰 Финансовая статистика:</b>\n"
        f"├ Пополнений: {stats['total_deposits']}\n"
        f"├ Сумма пополнений: {format_stars(stats['total_deposit_amount'])}\n"
        f"├ Выводов: {stats['total_withdrawals']}\n"
        f"├ Сумма выводов: {format_stars(stats['total_withdrawal_amount'])}\n"
        f"└ Всего ставок: {stats['total_bets']}\n\n"
        f"<b>🏆 Рекорды:</b>\n"
        f"├ Лучший множитель CRASH: x{stats['crash_best_multiplier']:.2f}\n"
        f"├ Лучший множитель MINES: x{stats['mines_best_multiplier']:.2f}\n"
        f"├ Лучший множитель DICE: x{stats['dice_best_multiplier']:.2f}\n"
        f"├ Максимальный выигрыш: {format_stars(max(stats['total_won'], stats['total_lost']))}\n"
        f"└ Дней в игре: {stats['daily_bonus_streak']}\n\n"
        f"<b>🎮 Активность:</b>\n"
        f"├ Последняя игра: {stats['last_game_played'] or 'Нет данных'}\n"
        f"└ Всего бонусов: {format_stars(stats['total_won'] + stats['total_lost'])}"
    )
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML)
    await callback.answer()


@dp.callback_query(F.data == "profile_transactions")
async def profile_transactions_callback(callback: CallbackQuery):
    """История транзакций пользователя"""
    uid = callback.from_user.id
    user_txs = transactions.get(uid, [])[-20:]
    
    if not user_txs:
        await callback.answer("У вас пока нет транзакций", show_alert=True)
        return
    
    text = "📜 <b>ИСТОРИЯ ТРАНЗАКЦИЙ</b>\n\n"
    for tx in reversed(user_txs):
        sign = "+" if tx["amount"] > 0 else ""
        emoji = "✅" if tx["amount"] > 0 else "❌"
        text += f"{emoji} {tx['type'].upper()}: {sign}{format_stars(tx['amount'])}\n"
        text += f"   📅 {tx['timestamp'][:19]}\n"
        if tx.get("game"):
            text += f"   🎮 {tx['game']}\n"
        text += "\n"
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML)
    await callback.answer()


@dp.message(F.text == "🎁 Бонус")
async def bonus_reply(message: Message):
    """Ежедневный бонус"""
    user_id = message.from_user.id
    today = datetime.now().date().isoformat()
    
    if users_ban.get(user_id, False):
        await message.answer("❌ Ваш аккаунт заблокирован!", parse_mode=ParseMode.HTML)
        return
    
    if not system_settings["daily_bonus_enabled"]:
        await message.answer("🔧 Ежедневный бонус временно отключён!", parse_mode=ParseMode.HTML)
        return
    
    if users_daily_bonus.get(user_id) == today:
        # Подсчитываем оставшееся время
        next_bonus = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        time_left = next_bonus - datetime.now()
        hours = time_left.seconds // 3600
        minutes = (time_left.seconds % 3600) // 60
        
        await message.answer(
            f"🎁 <b>Вы уже получили сегодняшний бонус!</b>\n\n"
            f"Следующий бонус будет доступен через:\n"
            f"⏰ {hours} ч {minutes} мин\n\n"
            f"💡 Заходите каждый день — бонус растёт!\n"
            f"📅 Текущий стрик: {users_daily_bonus_streak.get(user_id, 0)} дней",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Расчёт бонуса с учётом стрика
    streak = users_daily_bonus_streak.get(user_id, 0)
    if users_daily_bonus.get(user_id) == (datetime.now() - timedelta(days=1)).date().isoformat():
        streak += 1
    else:
        streak = 1
    
    bonus_amount = min(DAILY_BONUS_MAX, DAILY_BONUS_MIN + (streak - 1) * DAILY_BONUS_STREAK_MULTIPLIER)
    bonus_amount = random.uniform(bonus_amount - 2, bonus_amount + 2)
    bonus_amount = round(bonus_amount, 2)
    
    update_balance(user_id, bonus_amount)
    users_daily_bonus[user_id] = today
    users_daily_bonus_streak[user_id] = streak
    
    # Обновляем статистику
    stats = get_user_stats(user_id)
    stats["daily_bonus_count"] += 1
    stats["daily_bonus_streak"] = streak
    
    save_transaction(user_id, bonus_amount, "daily_bonus", f"Ежедневный бонус (стрик: {streak})")
    
    # Бонус за стрик
    bonus_text = ""
    if streak >= 7:
        bonus_text = f"\n🎉 <b>ЮБИЛЕЙНЫЙ БОНУС!</b> Вы получаете ежедневный бонус уже {streak} дней подряд!"
    
    await message.answer(
        f"🎉 <b>Ежедневный бонус получен!</b> 🎉\n\n"
        f"+{format_stars(bonus_amount)}\n"
        f"📅 Стрик: {streak} дней{bonus_text}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}\n\n"
        f"💡 Завтра бонус будет ещё больше!",
        parse_mode=ParseMode.HTML
    )


@dp.message(F.text == "⚙️ Настройки")
async def settings_reply(message: Message):
    """Настройки пользователя"""
    user_id = message.from_user.id
    settings = users_settings.get(user_id, {})
    
    text = (
        f"⚙️ <b>Настройки пользователя</b>\n\n"
        f"🔔 Уведомления: {'✅ Вкл' if settings.get('notifications', True) else '❌ Выкл'}\n"
        f"🌐 Язык: {settings.get('language', 'ru').upper()}\n"
        f"💰 Автовывод в CRASH: {'✅ Вкл' if settings.get('auto_cashout', False) else '❌ Выкл'}\n"
        f"🎯 Множитель автовывода: x{settings.get('auto_cashout_multiplier', 2.0):.2f}\n\n"
        f"👇 <b>Выберите действие:</b>"
    )
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_user_settings_keyboard())


@dp.callback_query(F.data == "settings_notifications")
async def settings_notifications(callback: CallbackQuery):
    """Настройка уведомлений"""
    user_id = callback.from_user.id
    users_settings[user_id]["notifications"] = not users_settings[user_id].get("notifications", True)
    status = "включены" if users_settings[user_id]["notifications"] else "выключены"
    
    await callback.answer(f"Уведомления {status}!", show_alert=True)
    await callback.message.edit_text(
        f"✅ Уведомления {status}!\n\n"
        f"Теперь вы будете получать {'уведомления о событиях' if users_settings[user_id]['notifications'] else 'только важные сообщения'}.",
        parse_mode=ParseMode.HTML
    )
    await asyncio.sleep(2)
    await settings_reply(callback.message)
    await callback.answer()


@dp.callback_query(F.data == "settings_language")
async def settings_language(callback: CallbackQuery):
    """Выбор языка"""
    await callback.message.edit_text(
        "🌐 <b>Выберите язык / Select language</b>\n\n"
        "🇷🇺 Русский\n"
        "🇬🇧 English",
        parse_mode=ParseMode.HTML,
        reply_markup=get_language_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("lang_"))
async def set_language(callback: CallbackQuery):
    """Установка языка"""
    lang = callback.data.split("_")[1]
    user_id = callback.from_user.id
    users_settings[user_id]["language"] = lang
    
    lang_name = "Русский" if lang == "ru" else "English"
    await callback.answer(f"Язык установлен: {lang_name}", show_alert=True)
    await settings_reply(callback.message)
    await callback.answer()


@dp.callback_query(F.data == "settings_security")
async def settings_security(callback: CallbackQuery):
    """Настройки безопасности"""
    user_id = callback.from_user.id
    
    await callback.message.edit_text(
        f"🔒 <b>Настройки безопасности</b>\n\n"
        f"🆔 Ваш ID: <code>{user_id}</code>\n"
        f"✅ Верификация: {'Верифицирован' if users_verify.get(user_id, False) else 'Не верифицирован'}\n\n"
        f"<b>⚠️ Внимание!</b>\n"
        f"• Никому не сообщайте ваш ID\n"
        f"• Администраторы никогда не попросят пароль\n"
        f"• Для верификации обратитесь к администратору\n\n"
        f"💡 Для смены пароля или дополнительной защиты свяжитесь с поддержкой: {system_settings['support_link']}",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@dp.callback_query(F.data == "settings_reset_stats")
async def settings_reset_stats(callback: CallbackQuery):
    """Сброс статистики пользователя"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, сбросить", callback_data="confirm_reset_stats"),
         InlineKeyboardButton(text="❌ Нет, отмена", callback_data="settings_back")]
    ])
    
    await callback.message.edit_text(
        "⚠️ <b>Внимание!</b>\n\n"
        "Вы действительно хотите сбросить свою игровую статистику?\n"
        "Это действие необратимо.\n\n"
        "Баланс и транзакции останутся неизменными.",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await callback.answer()


@dp.callback_query(F.data == "confirm_reset_stats")
async def confirm_reset_stats(callback: CallbackQuery):
    """Подтверждение сброса статистики"""
    user_id = callback.from_user.id
    users_stats[user_id] = get_user_stats(user_id)  # Сброс к дефолту
    
    await callback.answer("Статистика сброшена!", show_alert=True)
    await settings_reply(callback.message)
    await callback.answer()


@dp.callback_query(F.data == "settings_back")
async def settings_back(callback: CallbackQuery):
    """Возврат к настройкам"""
    await settings_reply(callback.message)
    await callback.answer()


@dp.message(F.text == "❓ Помощь")
async def help_reply(message: Message):
    """Помощь"""
    await cmd_help(message)


# ===================== ИГРА 1: CRASH =====================
async def run_crash_game(user_id: int, game_msg: Message, state: FSMContext):
    """Запуск процесса игры Crash"""
    game = active_crash.get(user_id)
    if not game:
        return
    
    bet = game["bet"]
    crash_point = game["crash_point"]
    multiplier = 1.00
    
    bot_stats["crash_games_played"] += 1
    
    while multiplier < crash_point and user_id in active_crash:
        multiplier = round(multiplier + 0.01, 2)
        
        # Проверка на автовывод
        settings = users_settings.get(user_id, {})
        if settings.get("auto_cashout", False) and multiplier >= settings.get("auto_cashout_multiplier", 2.0):
            await process_crash_cashout(user_id, game_msg, state, multiplier, bet)
            return
        
        try:
            await game_msg.edit_text(
                f"📈 <b>CRASH — ИГРА ИДЁТ!</b>\n\n"
                f"💰 Ваша ставка: {format_stars(bet)}\n"
                f"📈 Текущий множитель: <b>x{multiplier:.2f}</b>\n"
                f"💎 Потенциальный выигрыш: {format_stars(bet * multiplier)}\n\n"
                f"⚠️ Заберите выигрыш до взрыва!\n"
                f"🎯 Максимальный множитель: x{crash_point:.2f}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_crash_game_keyboard()
            )
        except:
            pass
        
        await asyncio.sleep(0.1)
    
    # Проверяем, не забрал ли пользователь выигрыш
    if user_id in active_crash:
        await process_crash_loss(user_id, game_msg, state, multiplier, bet)


async def process_crash_cashout(user_id: int, game_msg: Message, state: FSMContext, multiplier: float, bet: float):
    """Обработка выигрыша в Crash"""
    win = bet * multiplier
    update_balance(user_id, win)
    
    # Обновляем статистику
    stats = get_user_stats(user_id)
    stats["games_played"] += 1
    stats["games_won"] += 1
    stats["crash_games"] += 1
    stats["crash_wins"] += 1
    stats["total_won"] += win
    
    if multiplier > stats["crash_best_multiplier"]:
        stats["crash_best_multiplier"] = multiplier
    
    stats["last_game_played"] = datetime.now().isoformat()
    
    save_transaction(user_id, win, "game_win", f"Crash выигрыш x{multiplier:.2f}", "crash")
    
    # Сохраняем историю
    crash_history.append({
        "multiplier": multiplier,
        "player": user_id,
        "bet": bet,
        "win": win,
        "timestamp": datetime.now().isoformat()
    })
    if len(crash_history) > 100:
        crash_history.pop(0)
    
    del active_crash[user_id]
    await state.clear()
    
    await game_msg.edit_text(
        f"🎉 <b>CRASH — ВЫ ПОБЕДИЛИ!</b> 🎉\n\n"
        f"💰 Ваша ставка: {format_stars(bet)}\n"
        f"📈 Множитель: <b>x{multiplier:.2f}</b>\n"
        f"🏆 Выигрыш: {format_stars(win)}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )


async def process_crash_loss(user_id: int, game_msg: Message, state: FSMContext, multiplier: float, bet: float):
    """Обработка проигрыша в Crash"""
    stats = get_user_stats(user_id)
    stats["games_played"] += 1
    stats["crash_games"] += 1
    stats["total_lost"] += bet
    stats["last_game_played"] = datetime.now().isoformat()
    
    save_transaction(user_id, -bet, "game_loss", f"Crash крах на x{multiplier:.2f}", "crash")
    
    crash_history.append({
        "multiplier": multiplier,
        "player": user_id,
        "bet": bet,
        "win": 0,
        "timestamp": datetime.now().isoformat()
    })
    if len(crash_history) > 100:
        crash_history.pop(0)
    
    del active_crash[user_id]
    await state.clear()
    
    await game_msg.edit_text(
        f"💥 <b>CRASH — ВЗРЫВ!</b>\n\n"
        f"💰 Ваша ставка: {format_stars(bet)}\n"
        f"📈 Множитель в момент взрыва: x{multiplier:.2f}\n\n"
        f"😢 <b>Ставка сгорела!</b>\n"
        f"💰 Потеряно: {format_stars(bet)}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )


@dp.message(F.text == "📈 CRASH")
async def crash_start(message: Message, state: FSMContext):
    """Начало игры Crash"""
    user_id = message.from_user.id
    
    if users_ban.get(user_id, False):
        await message.answer("❌ Ваш аккаунт заблокирован!", parse_mode=ParseMode.HTML)
        return
    
    if system_settings["maintenance_mode"] and not is_admin(message.from_user.username or ""):
        await message.answer(system_settings["maintenance_message"], parse_mode=ParseMode.HTML)
        return
    
    if user_id in active_crash:
        await message.answer(
            "⚠️ У вас уже есть активная игра!\n"
            "Заберите выигрыш или дождитесь окончания.",
            parse_mode=ParseMode.HTML
        )
        return
    
    await state.set_state(GameStates.crash_bet)
    
    crash_info = (
        "📈 <b>CRASH — Умножай ставку!</b>\n\n"
        "📋 <b>Правила игры:</b>\n"
        "• Вы делаете ставку\n"
        "• Множитель начинает расти\n"
        "• Нужно забрать выигрыш ДО взрыва\n"
        "• Если не забрали — ставка сгорает\n"
        f"• Максимальный множитель: x{CRASH_MAX_MULTIPLIER}\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Всего сыграно: {bot_stats['crash_games_played']} игр\n"
        f"• Побед: {bot_stats['crash_games_won']}\n"
        f"• Последний краш: x{crash_history[-1]['multiplier']:.2f}" if crash_history else "• Нет данных"
    )
    
    await message.answer(
        crash_info,
        parse_mode=ParseMode.HTML,
        reply_markup=get_crash_bet_keyboard()
    )


@dp.callback_query(F.data.startswith("crash_bet_"))
async def crash_place_bet(callback: CallbackQuery, state: FSMContext):
    """Размещение ставки в Crash"""
    user_id = callback.from_user.id
    
    if users_ban.get(user_id, False):
        await callback.answer("Ваш аккаунт заблокирован!", show_alert=True)
        return
    
    if user_id in active_crash:
        await callback.answer("У вас уже есть активная игра!", show_alert=True)
        return
    
    bet_str = callback.data.split("_")[-1]
    
    if bet_str == "custom":
        await callback.message.answer(
            "✏️ <b>Введите сумму ставки</b>\n\n"
            f"💰 Доступный баланс: {format_stars(get_user_balance(user_id))}\n"
            f"📊 Минимальная ставка: {MIN_BET} Stars\n"
            f"📊 Максимальная ставка: {MAX_BET} Stars",
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
        await callback.answer(
            f"❌ Ставка должна быть от {MIN_BET} до {MAX_BET} Stars!",
            show_alert=True
        )
        return
    
    balance = get_user_balance(user_id)
    if balance < bet:
        await callback.answer(
            f"❌ Недостаточно средств! Нужно {format_stars(bet)}",
            show_alert=True
        )
        return
    
    # Списываем ставку
    update_balance(user_id, -bet)
    save_transaction(user_id, -bet, "bet", f"Crash ставка {bet} Stars", "crash")
    
    # Создаём игру
    crash_point = calculate_crash_multiplier()
    active_crash[user_id] = {
        "bet": bet,
        "crash_point": crash_point,
        "multiplier": 1.00,
        "start_time": time.time()
    }
    
    await state.set_state(GameStates.crash_waiting)
    
    # Отправляем игровое сообщение
    game_msg = await callback.message.edit_text(
        f"📈 <b>CRASH — ИГРА ИДЁТ!</b>\n\n"
        f"💰 Ваша ставка: {format_stars(bet)}\n"
        f"📈 Текущий множитель: <b>x1.00</b>\n"
        f"💎 Потенциальный выигрыш: {format_stars(bet)}\n\n"
        f"⚠️ Чем дольше ждёте — тем выше множитель!\n"
        f"💀 Но можете не успеть забрать!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_crash_game_keyboard()
    )
    
    # Запускаем процесс роста множителя
    asyncio.create_task(run_crash_game(user_id, game_msg, state))
    await callback.answer()


@dp.callback_query(F.data == "crash_cashout")
async def crash_cashout(callback: CallbackQuery, state: FSMContext):
    """Забор выигрыша в Crash"""
    user_id = callback.from_user.id
    
    if user_id not in active_crash:
        await callback.answer("Нет активной игры!", show_alert=True)
        return
    
    game = active_crash[user_id]
    bet = game["bet"]
    multiplier = game.get("multiplier", 1.00)
    
    await process_crash_cashout(user_id, callback.message, state, multiplier, bet)
    await callback.answer()


@dp.callback_query(F.data == "crash_exit")
async def crash_exit(callback: CallbackQuery, state: FSMContext):
    """Выход из игры Crash"""
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


# ===================== ИГРА 2: MINES =====================
@dp.message(F.text == "💣 MINES")
async def mines_start(message: Message, state: FSMContext):
    """Начало игры Mines"""
    user_id = message.from_user.id
    
    if users_ban.get(user_id, False):
        await message.answer("❌ Ваш аккаунт заблокирован!", parse_mode=ParseMode.HTML)
        return
    
    if system_settings["maintenance_mode"] and not is_admin(message.from_user.username or ""):
        await message.answer(system_settings["maintenance_message"], parse_mode=ParseMode.HTML)
        return
    
    if user_id in active_mines:
        await message.answer(
            "⚠️ У вас уже есть активная игра!\n"
            "Заберите выигрыш или завершите игру.",
            parse_mode=ParseMode.HTML
        )
        return
    
    await state.set_state(GameStates.mines_bet)
    
    max_multiplier = 1.2 ** (MINES_BOARD_SIZE * MINES_BOARD_SIZE - MINES_MINES_COUNT)
    
    mines_info = (
        "💣 <b>MINES — Найди сокровища!</b>\n\n"
        "📋 <b>Правила игры:</b>\n"
        f"• Поле {MINES_BOARD_SIZE}x{MINES_BOARD_SIZE}\n"
        f"• Спрятано {MINES_MINES_COUNT} мин\n"
        "• Каждая найденная 💎 увеличивает множитель x1.2\n"
        "• Наступите на 💣 — проигрыш\n"
        "• Можно забрать выигрыш в любой момент\n"
        f"• Максимальный множитель: x{max_multiplier:.1f}\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Всего сыграно: {bot_stats['mines_games_played']} игр\n"
        f"• Побед: {bot_stats['mines_games_won']}\n"
        f"• Лучший множитель: x{mines_history[-1]['multiplier']:.1f}" if mines_history else "• Нет данных"
    )
    
    await message.answer(
        mines_info,
        parse_mode=ParseMode.HTML,
        reply_markup=get_mines_bet_keyboard()
    )


@dp.callback_query(F.data.startswith("mines_bet_"))
async def mines_place_bet(callback: CallbackQuery, state: FSMContext):
    """Размещение ставки в Mines"""
    user_id = callback.from_user.id
    
    if users_ban.get(user_id, False):
        await callback.answer("Ваш аккаунт заблокирован!", show_alert=True)
        return
    
    bet_str = callback.data.split("_")[-1]
    
    if bet_str == "custom":
        await callback.message.answer(
            "✏️ <b>Введите сумму ставки</b>\n\n"
            f"💰 Доступный баланс: {format_stars(get_user_balance(user_id))}\n"
            f"📊 Минимальная ставка: {MIN_BET} Stars\n"
            f"📊 Максимальная ставка: {MAX_BET} Stars",
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
        await callback.answer(
            f"❌ Ставка должна быть от {MIN_BET} до {MAX_BET} Stars!",
            show_alert=True
        )
        return
    
    balance = get_user_balance(user_id)
    if balance < bet:
        await callback.answer(
            f"❌ Недостаточно средств! Нужно {format_stars(bet)}",
            show_alert=True
        )
        return
    
    # Списываем ставку
    update_balance(user_id, -bet)
    save_transaction(user_id, -bet, "bet", f"Mines ставка {bet} Stars", "mines")
    
    # Создаём игровое поле
    board, revealed = generate_mines_board()
    
    active_mines[user_id] = {
        "bet": bet,
        "board": board,
        "revealed": revealed,
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
        f"💎 Потенциальный выигрыш: {format_stars(bet)}\n\n"
        f"👇 <b>Открывайте клетки и находите 💎!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_mines_board_keyboard(board, revealed, bet, 1.0)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("mines_cell_"))
async def mines_open_cell(callback: CallbackQuery):
    """Открытие клетки в Mines"""
    user_id = callback.from_user.id
    
    if user_id not in active_mines:
        await callback.answer("Игра не найдена!", show_alert=True)
        return
    
    game = active_mines[user_id]
    coords = callback.data.split("_")
    x, y = int(coords[2]), int(coords[3])
    
    if game["revealed"][x][y]:
        await callback.answer("Эта клетка уже открыта!", show_alert=True)
        return
    
    game["revealed"][x][y] = True
    max_cells = MINES_BOARD_SIZE * MINES_BOARD_SIZE - MINES_MINES_COUNT
    
    if game["board"][x][y] == "💣":
        # Проигрыш
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["mines_games"] += 1
        stats["total_lost"] += game["bet"]
        stats["last_game_played"] = datetime.now().isoformat()
        
        save_transaction(user_id, -game["bet"], "game_loss", "Mines проигрыш", "mines")
        
        bot_stats["mines_games_played"] += 1
        
        # Сохраняем историю
        mines_history.append({
            "multiplier": game["multiplier"],
            "player": user_id,
            "bet": game["bet"],
            "win": False,
            "timestamp": datetime.now().isoformat()
        })
        if len(mines_history) > 100:
            mines_history.pop(0)
        
        del active_mines[user_id]
        
        await callback.message.edit_text(
            f"💣 <b>MINES — ПРОИГРЫШ!</b>\n\n"
            f"💥 <b>Вы наступили на мину!</b>\n\n"
            f"💰 Ставка: {format_stars(game['bet'])} — проиграна\n"
            f"✨ Множитель в момент проигрыша: x{game['multiplier']:.2f}\n\n"
            f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_games_keyboard()
        )
    else:
        # Успех
        game["cells_opened"] += 1
        game["multiplier"] *= 1.2
        current_win = game["bet"] * game["multiplier"]
        
        # Проверка на победу (все клетки открыты)
        if game["cells_opened"] >= max_cells:
            # Победа
            update_balance(user_id, current_win)
            
            stats = get_user_stats(user_id)
            stats["games_played"] += 1
            stats["games_won"] += 1
            stats["mines_games"] += 1
            stats["mines_wins"] += 1
            stats["total_won"] += current_win
            
            if game["multiplier"] > stats["mines_best_multiplier"]:
                stats["mines_best_multiplier"] = game["multiplier"]
            
            stats["last_game_played"] = datetime.now().isoformat()
            
            save_transaction(user_id, current_win, "game_win", 
                           f"Mines победа x{game['multiplier']:.1f}", "mines")
            
            bot_stats["mines_games_played"] += 1
            bot_stats["mines_games_won"] += 1
            
            mines_history.append({
                "multiplier": game["multiplier"],
                "player": user_id,
                "bet": game["bet"],
                "win": current_win,
                "timestamp": datetime.now().isoformat()
            })
            if len(mines_history) > 100:
                mines_history.pop(0)
            
            del active_mines[user_id]
            
            await callback.message.edit_text(
                f"🎉 <b>MINES — ПОБЕДА!</b> 🎉\n\n"
                f"🎯 <b>Вы нашли все сокровища!</b>\n\n"
                f"💰 Ставка: {format_stars(game['bet'])}\n"
                f"✨ Множитель: x{game['multiplier']:.2f}\n"
                f"🏆 Выигрыш: {format_stars(current_win)}\n\n"
                f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_games_keyboard()
            )
        else:
            # Продолжаем игру
            await callback.message.edit_text(
                f"💣 <b>MINES — ИГРА</b>\n\n"
                f"💰 Ставка: {format_stars(game['bet'])}\n"
                f"✨ Текущий множитель: x{game['multiplier']:.2f}\n"
                f"📦 Открыто клеток: {game['cells_opened']}/{max_cells}\n"
                f"💎 Текущий выигрыш: {format_stars(current_win)}\n"
                f"🎯 Максимальный выигрыш: {format_stars(game['bet'] * (1.2 ** max_cells))}\n\n"
                f"✅ <b>Вы нашли 💎! Множитель увеличен!</b>\n\n"
                f"👇 <b>Продолжайте открывать или заберите выигрыш!</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_mines_board_keyboard(game["board"], game["revealed"], 
                                                     game["bet"], game["multiplier"])
            )
    
    await callback.answer()


@dp.callback_query(F.data == "mines_cashout")
async def mines_cashout(callback: CallbackQuery):
    """Забор выигрыша в Mines"""
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
    
    stats["last_game_played"] = datetime.now().isoformat()
    
    save_transaction(user_id, win, "game_win", 
                    f"Mines кэшаут x{game['multiplier']:.1f}", "mines")
    
    bot_stats["mines_games_played"] += 1
    bot_stats["mines_games_won"] += 1
    
    mines_history.append({
        "multiplier": game["multiplier"],
        "player": user_id,
        "bet": game["bet"],
        "win": win,
        "timestamp": datetime.now().isoformat()
    })
    if len(mines_history) > 100:
        mines_history.pop(0)
    
    del active_mines[user_id]
    
    await callback.message.edit_text(
        f"💰 <b>MINES — ВЫ ЗАБРАЛИ ВЫИГРЫШ!</b>\n\n"
        f"💰 Ставка: {format_stars(game['bet'])}\n"
        f"✨ Множитель: x{game['multiplier']:.2f}\n"
        f"📦 Открыто клеток: {game['cells_opened']}\n"
        f"🏆 Выигрыш: {format_stars(win)}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data == "mines_exit")
async def mines_exit(callback: CallbackQuery, state: FSMContext):
    """Выход из игры Mines"""
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


# ===================== ИГРА 3: DICE =====================
@dp.message(F.text == "🎲 DICE")
async def dice_start(message: Message, state: FSMContext):
    """Начало игры Dice"""
    user_id = message.from_user.id
    
    if users_ban.get(user_id, False):
        await message.answer("❌ Ваш аккаунт заблокирован!", parse_mode=ParseMode.HTML)
        return
    
    if system_settings["maintenance_mode"] and not is_admin(message.from_user.username or ""):
        await message.answer(system_settings["maintenance_message"], parse_mode=ParseMode.HTML)
        return
    
    await state.set_state(GameStates.dice_bet)
    
    dice_info = (
        "🎲 <b>DICE — Угадай число!</b>\n\n"
        "📋 <b>Правила игры:</b>\n"
        "• Вы делаете ставку\n"
        "• Предсказываете, выпадет число выше 50 или ниже 50\n"
        "• Кубик бросается автоматически\n"
        f"• При правильном угадывании выигрыш x{DICE_MULTIPLIER}\n"
        f"• При неправильном — ставка сгорает\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Всего сыграно: {bot_stats['dice_games_played']} игр\n"
        f"• Побед: {bot_stats['dice_games_won']}\n"
        f"• Последний результат: {'Выше 50' if dice_history[-1]['result'] > 50 else 'Ниже 50'}" if dice_history else "• Нет данных"
    )
    
    await message.answer(
        dice_info,
        parse_mode=ParseMode.HTML,
        reply_markup=get_dice_bet_keyboard()
    )


@dp.callback_query(F.data.startswith("dice_bet_"))
async def dice_place_bet(callback: CallbackQuery, state: FSMContext):
    """Размещение ставки в Dice"""
    user_id = callback.from_user.id
    
    if users_ban.get(user_id, False):
        await callback.answer("Ваш аккаунт заблокирован!", show_alert=True)
        return
    
    bet_str = callback.data.split("_")[-1]
    
    if bet_str == "custom":
        await callback.message.answer(
            "✏️ <b>Введите сумму ставки</b>\n\n"
            f"💰 Доступный баланс: {format_stars(get_user_balance(user_id))}\n"
            f"📊 Минимальная ставка: {MIN_BET} Stars\n"
            f"📊 Максимальная ставка: {MAX_BET} Stars",
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GameStates.dice_bet)
        await callback.answer()
        return
    
    try:
        bet = float(bet_str)
    except:
        await callback.answer("Неверная сумма!", show_alert=True)
        return
    
    if bet < MIN_BET or bet > MAX_BET:
        await callback.answer(
            f"❌ Ставка должна быть от {MIN_BET} до {MAX_BET} Stars!",
            show_alert=True
        )
        return
    
    balance = get_user_balance(user_id)
    if balance < bet:
        await callback.answer(
            f"❌ Недостаточно средств! Нужно {format_stars(bet)}",
            show_alert=True
        )
        return
    
    await state.update_data(dice_bet=bet)
    await state.set_state(GameStates.dice_playing)
    
    await callback.message.edit_text(
        f"🎲 <b>DICE — СДЕЛАЙ СТАВКУ</b>\n\n"
        f"💰 Ваша ставка: {format_stars(bet)}\n"
        f"🎯 Множитель при победе: x{DICE_MULTIPLIER}\n"
        f"💎 Потенциальный выигрыш: {format_stars(bet * DICE_MULTIPLIER)}\n\n"
        f"👇 <b>Выберите предсказание:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_dice_predict_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data == "dice_higher")
async def dice_higher(callback: CallbackQuery, state: FSMContext):
    """Предсказание выше 50"""
    await process_dice_game(callback, state, "higher")


@dp.callback_query(F.data == "dice_lower")
async def dice_lower(callback: CallbackQuery, state: FSMContext):
    """Предсказание ниже 50"""
    await process_dice_game(callback, state, "lower")


async def process_dice_game(callback: CallbackQuery, state: FSMContext, prediction: str):
    """Основная логика игры Dice"""
    user_id = callback.from_user.id
    data = await state.get_data()
    bet = data.get("dice_bet", 0)
    
    if bet == 0:
        await callback.answer("Ошибка! Начните игру заново.", show_alert=True)
        await state.clear()
        return
    
    # Списываем ставку
    update_balance(user_id, -bet)
    save_transaction(user_id, -bet, "bet", f"Dice ставка {bet} Stars", "dice")
    
    # Бросаем кубик
    dice_msg = await callback.message.answer_dice(emoji="🎲")
    dice_value = dice_msg.dice.value * 16  # Преобразуем 1-6 в 1-96
    dice_value = min(dice_value, 100)
    
    # Проверяем результат
    if (prediction == "higher" and dice_value > 50) or (prediction == "lower" and dice_value < 50):
        win = bet * DICE_MULTIPLIER
        update_balance(user_id, win)
        
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["dice_games"] += 1
        stats["dice_wins"] += 1
        stats["total_won"] += win
        stats["last_game_played"] = datetime.now().isoformat()
        
        if DICE_MULTIPLIER > stats["dice_best_multiplier"]:
            stats["dice_best_multiplier"] = DICE_MULTIPLIER
        
        save_transaction(user_id, win, "game_win", f"Dice победа {dice_value}", "dice")
        
        result_text = f"🎉 <b>ВЫ УГАДАЛИ!</b> 🎉\n\nВыпало: <b>{dice_value}</b>\nВыигрыш: +{format_stars(win - bet)}"
        bot_stats["dice_games_played"] += 1
        bot_stats["dice_games_won"] += 1
        
        dice_history.append({
            "result": dice_value,
            "prediction": prediction,
            "player": user_id,
            "bet": bet,
            "win": win,
            "timestamp": datetime.now().isoformat()
        })
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["dice_games"] += 1
        stats["total_lost"] += bet
        stats["last_game_played"] = datetime.now().isoformat()
        
        save_transaction(user_id, -bet, "game_loss", f"Dice проигрыш {dice_value}", "dice")
        
        result_text = f"😢 <b>ВЫ НЕ УГАДАЛИ!</b>\n\nВыпало: <b>{dice_value}</b>\nПотеряно: {format_stars(bet)}"
        bot_stats["dice_games_played"] += 1
        
        dice_history.append({
            "result": dice_value,
            "prediction": prediction,
            "player": user_id,
            "bet": bet,
            "win": 0,
            "timestamp": datetime.now().isoformat()
        })
    
    if len(dice_history) > 100:
        dice_history.pop(0)
    
    await state.clear()
    
    await callback.message.answer(
        f"🎲 <b>DICE — РЕЗУЛЬТАТ</b>\n\n"
        f"💰 Ваша ставка: {format_stars(bet)}\n"
        f"🎯 Ваше предсказание: {'Выше 50 ⬆️' if prediction == 'higher' else 'Ниже 50 ⬇️'}\n\n"
        f"{result_text}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data == "dice_roll")
async def dice_roll(callback: CallbackQuery):
    """Просто бросок кубика без ставки"""
    await callback.message.answer_dice(emoji="🎲")
    await callback.answer()


# ===================== ИСТОРИЯ ИГР =====================
@dp.message(F.text == "📊 История игр")
async def games_history(message: Message):
    """История последних игр"""
    user_id = message.from_user.id
    
    # Получаем историю игр пользователя
    user_crash = [g for g in crash_history if g.get("player") == user_id][-10:]
    user_mines = [g for g in mines_history if g.get("player") == user_id][-10:]
    user_dice = [g for g in dice_history if g.get("player") == user_id][-10:]
    
    history_text = "📊 <b>ИСТОРИЯ ВАШИХ ИГР</b>\n\n"
    
    if user_crash:
        history_text += "<b>📈 CRASH:</b>\n"
        for game in user_crash:
            if game.get("win") and game.get("win") > 0:
                history_text += f"• Ставка: {format_stars(game['bet'])} | Множитель: x{game['multiplier']:.2f} | "
                history_text += f"+{format_stars(game['win'] - game['bet'])}\n"
            else:
                history_text += f"• Ставка: {format_stars(game['bet'])} | Множитель: x{game['multiplier']:.2f} | Проигрыш\n"
        history_text += "\n"
    
    if user_mines:
        history_text += "<b>💣 MINES:</b>\n"
        for game in user_mines:
            if game.get("win") and game.get("win") > 0:
                history_text += f"• Ставка: {format_stars(game['bet'])} | Множитель: x{game['multiplier']:.2f} | "
                history_text += f"+{format_stars(game['win'] - game['bet'])}\n"
            else:
                history_text += f"• Ставка: {format_stars(game['bet'])} | Проигрыш\n"
        history_text += "\n"
    
    if user_dice:
        history_text += "<b>🎲 DICE:</b>\n"
        for game in user_dice:
            if game.get("win") and game.get("win") > 0:
                history_text += f"• Ставка: {format_stars(game['bet'])} | Выпало: {game['result']} | "
                history_text += f"+{format_stars(game['win'] - game['bet'])}\n"
            else:
                history_text += f"• Ставка: {format_stars(game['bet'])} | Выпало: {game['result']} | Проигрыш\n"
        history_text += "\n"
    
    if not user_crash and not user_mines and not user_dice:
        history_text += "📭 У вас пока нет сыгранных игр.\n\n💡 Начните играть, чтобы видеть историю!"
    
    await message.answer(history_text, parse_mode=ParseMode.HTML, reply_markup=get_games_keyboard())


# ===================== АДМИН-ПАНЕЛЬ =====================
@dp.message(F.text == "👑 Админ панель")
async def admin_panel(message: Message):
    """Вход в админ-панель"""
    username = message.from_user.username or ""
    
    if not is_admin(username):
        await message.answer("❌ У вас нет доступа к админ-панели!", reply_markup=get_main_keyboard())
        return
    
    await message.answer(
        "👑 <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n\n"
        "📊 <b>Доступные действия:</b>\n\n"
        "• 📊 Статистика — просмотр общей статистики\n"
        "• 💰 Изменить баланс — пополнение/снятие средств\n"
        "• 📢 Рассылка — массовая рассылка сообщений\n"
        "• 👥 Пользователи — список всех пользователей\n"
        "• 🔨 Бан/Разбан — блокировка пользователей\n"
        "• ✅ Верификация — верификация аккаунтов\n"
        "• ⚙️ Настройки — изменение параметров бота\n"
        "• 🎮 Управление играми — настройка игр\n"
        "• 🎁 Промокоды — создание и управление\n"
        "• 💾 Резервное копирование — сохранение данных\n"
        "• 📈 Экспорт данных — выгрузка в JSON\n"
        "• 🔧 Системные настройки — общие настройки\n\n"
        "👇 <b>Выберите действие:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_main_keyboard()
    )


# ===================== АДМИН: СТАТИСТИКА =====================
@dp.message(F.text == "📊 Статистика")
async def admin_stats(message: Message):
    """Просмотр статистики бота"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    uptime = datetime.now() - datetime.fromisoformat(bot_stats["server_start_time"])
    
    active_today = len([uid for uid, last in users_last_seen.items() 
                       if datetime.fromisoformat(last).date() == datetime.now().date()])
    
    stats_text = (
        f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
        f"<b>👥 Пользователи:</b>\n"
        f"├ Всего: {bot_stats['total_users']}\n"
        f"├ Активны сегодня: {active_today}\n"
        f"├ Забанено: {len([u for u, b in users_ban.items() if b])}\n"
        f"└ Верифицировано: {len([u for u, v in users_verify.items() if v])}\n\n"
        f"<b>💰 Финансы:</b>\n"
        f"├ Общий баланс: {format_stars(sum(users_balance.values()))}\n"
        f"├ Всего ставок: {bot_stats['total_bets']}\n"
        f"├ Общая сумма ставок: {format_stars(bot_stats['total_wagered'])}\n"
        f"├ Выплачено: {format_stars(bot_stats['total_paid'])}\n"
        f"├ Прибыль бота: {format_stars(bot_stats['total_profit'])}\n"
        f"├ Пополнений: {bot_stats['total_deposits']}\n"
        f"├ Сумма пополнений: {format_stars(bot_stats['total_deposit_amount'])}\n"
        f"├ Выводов: {bot_stats['total_withdrawals']}\n"
        f"└ Сумма выводов: {format_stars(bot_stats['total_withdrawal_amount'])}\n\n"
        f"<b>🎮 Игры:</b>\n"
        f"├ CRASH: {bot_stats['crash_games_played']} игр, {bot_stats['crash_games_won']} побед\n"
        f"├ MINES: {bot_stats['mines_games_played']} игр, {bot_stats['mines_games_won']} побед\n"
        f"└ DICE: {bot_stats['dice_games_played']} игр, {bot_stats['dice_games_won']} побед\n\n"
        f"<b>🎁 Бонусы:</b>\n"
        f"├ Выдано бонусов: {format_stars(bot_stats['total_bonus_given'])}\n"
        f"└ Реферальных: {format_stars(bot_stats['total_referral_bonus'])}\n\n"
        f"<b>🕐 Система:</b>\n"
        f"├ Время работы: {format_time(uptime.seconds)}\n"
        f"├ Последний бэкап: {bot_stats['last_backup'][:19] if bot_stats['last_backup'] else 'Никогда'}\n"
        f"└ Запуск: {bot_stats['server_start_time'][:19]}"
    )
    
    await message.answer(stats_text, parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())


# ===================== АДМИН: ИЗМЕНЕНИЕ БАЛАНСА =====================
@dp.message(F.text == "💰 Изменить баланс")
async def admin_change_balance_start(message: Message, state: FSMContext):
    """Начало изменения баланса"""
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
    """Поиск пользователя для изменения баланса"""
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
    """Изменение баланса"""
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
        
        # Уведомляем пользователя
        try:
            await bot.send_message(
                target_user,
                f"👑 <b>Администратор изменил ваш баланс!</b>\n\n"
                f"{'+' if amount > 0 else ''}{format_stars(amount)}\n"
                f"💰 Новый баланс: {format_stars(new_balance)}\n\n"
                f"💡 Причина: изменение администратором",
                parse_mode=ParseMode.HTML
            )
        except:
            pass
        
        # Сохраняем транзакцию
        save_transaction(target_user, amount, "admin_change", 
                        f"Админ: {amount} Stars", "admin")
        
        await state.clear()
        await message.answer(
            f"✅ <b>Баланс изменён!</b>\n\n"
            f"👤 Пользователь: @{target_username}\n"
            f"💰 Изменение: {format_stars(amount)}\n"
            f"💰 Новый баланс: {format_stars(new_balance)}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_main_keyboard()
        )
    except ValueError:
        await message.answer("❌ Введите число!")


# ===================== АДМИН: РАССЫЛКА =====================
@dp.message(F.text == "📢 Рассылка")
async def admin_broadcast_start(message: Message, state: FSMContext):
    """Начало рассылки"""
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
    """Получение сообщения для рассылки"""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Рассылка отменена.", reply_markup=get_admin_main_keyboard())
        return
    
    await state.update_data(broadcast_msg=message)
    await state.set_state(GameStates.admin_send_broadcast_confirm)
    
    # Подсчитываем количество получателей
    recipients = [uid for uid in users_balance.keys() if not users_ban.get(uid, False)]
    
    await message.answer(
        f"📢 <b>ПОДТВЕРЖДЕНИЕ РАССЫЛКИ</b>\n\n"
        f"📨 Получателей: {len(recipients)}\n\n"
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
    """Подтверждение рассылки"""
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
        except Exception as e:
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
    """Отмена рассылки"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Рассылка отменена.",
        reply_markup=get_admin_main_keyboard()
    )
    await callback.answer()


# ===================== АДМИН: ПОЛЬЗОВАТЕЛИ =====================
@dp.message(F.text == "👥 Пользователи")
async def admin_users_list(message: Message):
    """Список пользователей"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    users_list = []
    for uid, uname in users_username.items():
        balance = get_user_balance(uid)
        banned = "🚫" if users_ban.get(uid, False) else "✅"
        verified = "✓" if users_verify.get(uid, False) else "○"
        users_list.append(f"{banned}{verified} @{uname or str(uid)} — {format_stars(balance)}")
    
    text = "👥 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ</b>\n\n"
    text += "\n".join(users_list[:50])
    
    if len(users_list) > 50:
        text += f"\n\n... и ещё {len(users_list) - 50} пользователей"
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())


# ===================== АДМИН: БАН/РАЗБАН =====================
@dp.message(F.text == "🔨 Бан/Разбан")
async def admin_ban_start(message: Message, state: FSMContext):
    """Начало бана пользователя"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await state.set_state(GameStates.admin_ban_user)
    await message.answer(
        "🔨 <b>БАН ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введите username (без @) или ID пользователя для бана:\n\n"
        "<i>Для разбана используйте команду /unban</i>\n"
        "<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )


@dp.message(GameStates.admin_ban_user)
async def admin_ban_user(message: Message, state: FSMContext):
    """Бан пользователя"""
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
    
    if users_ban.get(user_id, False):
        await message.answer(f"⚠️ Пользователь уже забанен!")
        return
    
    users_ban[user_id] = True
    users_ban_reason[user_id] = "Нарушение правил"
    
    # Уведомляем пользователя
    try:
        await bot.send_message(
            user_id,
            f"🚫 <b>Ваш аккаунт заблокирован!</b>\n\n"
            f"Причина: Нарушение правил\n\n"
            f"Для получения информации обратитесь к администратору: {system_settings['support_link']}",
            parse_mode=ParseMode.HTML
        )
    except:
        pass
    
    await state.clear()
    await message.answer(
        f"✅ <b>Пользователь забанен!</b>\n\n"
        f"👤 @{input_text}\n"
        f"🚫 Статус: Забанен",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_main_keyboard()
    )


@dp.message(Command("unban"))
async def admin_unban(message: Message, state: FSMContext):
    """Разбан пользователя"""
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "❌ Укажите username или ID пользователя!\n"
            "Пример: <code>/unban username</code>",
            parse_mode=ParseMode.HTML
        )
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
    
    # Уведомляем пользователя
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
    
    await message.answer(
        f"✅ <b>Пользователь разбанен!</b>\n\n"
        f"👤 @{input_text}\n"
        f"✅ Статус: Активен",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_main_keyboard()
    )


# ===================== АДМИН: ВЕРИФИКАЦИЯ =====================
@dp.message(F.text == "✅ Верификация")
async def admin_verify_start(message: Message, state: FSMContext):
    """Начало верификации"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await state.set_state(GameStates.admin_set_verify)
    await message.answer(
        "✅ <b>ВЕРИФИКАЦИЯ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введите username (без @) или ID пользователя для верификации:\n\n"
        "<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )


@dp.message(GameStates.admin_set_verify)
async def admin_set_verify(message: Message, state: FSMContext):
    """Установка верификации"""
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
    
    # Уведомляем пользователя
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
        f"✅ Новый статус: {'Верифицирован' if users_verify[user_id] else 'Не верифицирован'}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_main_keyboard()
    )


# ===================== АДМИН: НАСТРОЙКИ =====================
@dp.message(F.text == "⚙️ Настройки")
async def admin_settings(message: Message):
    """Настройки бота"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    settings_text = (
        f"⚙️ <b>НАСТРОЙКИ БОТА</b>\n\n"
        f"<b>💰 Финансовые:</b>\n"
        f"├ Мин. ставка: {system_settings['min_bet']} Stars\n"
        f"├ Макс. ставка: {system_settings['max_bet']} Stars\n"
        f"├ Реферальный %: {system_settings['referral_percent']}%\n"
        f"└ House Edge: {(1 - system_settings['crash_house_edge']) * 100}%\n\n"
        f"<b>🎮 Игровые:</b>\n"
        f"├ CRASH макс. множитель: x{CRASH_MAX_MULTIPLIER}\n"
        f"├ MINES поле: {MINES_BOARD_SIZE}x{MINES_BOARD_SIZE}\n"
        f"├ MINES мин: {MINES_MINES_COUNT}\n"
        f"└ DICE множитель: x{DICE_MULTIPLIER}\n\n"
        f"<b>🎁 Бонусы:</b>\n"
        f"├ Ежедневный бонус: {'Вкл' if system_settings['daily_bonus_enabled'] else 'Выкл'}\n"
        f"├ Мин. бонус: {DAILY_BONUS_MIN} Stars\n"
        f"└ Макс. бонус: {DAILY_BONUS_MAX} Stars\n\n"
        f"<b>🔧 Системные:</b>\n"
        f"├ Режим обслуживания: {'Вкл' if system_settings['maintenance_mode'] else 'Выкл'}\n"
        f"├ Чат: {system_settings['chat_link']}\n"
        f"├ Канал: {system_settings['channel_link']}\n"
        f"└ Поддержка: {system_settings['support_link']}\n\n"
        f"💡 Для изменения настроек используйте команды:\n"
        f"• /set_min_bet <сумма>\n"
        f"• /set_max_bet <сумма>\n"
        f"• /set_house_edge <процент>\n"
        f"• /set_daily_bonus <вкл/выкл>\n"
        f"• /set_maintenance <вкл/выкл>\n"
        f"• /set_chat <ссылка>\n"
        f"• /set_channel <ссылка>\n"
        f"• /set_support <ссылка>"
    )
    
    await message.answer(settings_text, parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())


# ===================== АДМИН: УПРАВЛЕНИЕ ИГРАМИ =====================
@dp.message(F.text == "🎮 Управление играми")
async def admin_games_control(message: Message):
    """Управление играми"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📈 CRASH настройки", callback_data="admin_crash_settings")],
        [InlineKeyboardButton(text="💣 MINES настройки", callback_data="admin_mines_settings")],
        [InlineKeyboardButton(text="🎲 DICE настройки", callback_data="admin_dice_settings")],
        [InlineKeyboardButton(text="🔄 Сбросить статистику игр", callback_data="admin_reset_games_stats")],
        [InlineKeyboardButton(text="📊 Очистить историю игр", callback_data="admin_clear_games_history")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ])
    
    await message.answer(
        "🎮 <b>УПРАВЛЕНИЕ ИГРАМИ</b>\n\n"
        "Выберите игру для настройки:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "admin_crash_settings")
async def admin_crash_settings(callback: CallbackQuery):
    """Настройки Crash игры"""
    await callback.message.edit_text(
        "📈 <b>НАСТРОЙКИ CRASH</b>\n\n"
        f"📊 Максимальный множитель: x{CRASH_MAX_MULTIPLIER}\n"
        f"🎯 House Edge: {(1 - CRASH_HOUSE_EDGE) * 100}%\n"
        f"💰 Минимальная ставка: {MIN_BET}\n"
        f"💰 Максимальная ставка: {MAX_BET}\n\n"
        f"Для изменения параметров используйте команды:\n"
        f"• /set_crash_max <множитель>\n"
        f"• /set_crash_house <процент>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_games_back")]
        ])
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_mines_settings")
async def admin_mines_settings(callback: CallbackQuery):
    """Настройки Mines игры"""
    await callback.message.edit_text(
        "💣 <b>НАСТРОЙКИ MINES</b>\n\n"
        f"📊 Размер поля: {MINES_BOARD_SIZE}x{MINES_BOARD_SIZE}\n"
        f"💣 Количество мин: {MINES_MINES_COUNT}\n"
        f"✨ Множитель за клетку: x1.2\n"
        f"💰 Минимальная ставка: {MIN_BET}\n"
        f"💰 Максимальная ставка: {MAX_BET}\n\n"
        f"Для изменения параметров используйте команды:\n"
        f"• /set_mines_size <размер>\n"
        f"• /set_mines_count <количество>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_games_back")]
        ])
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_dice_settings")
async def admin_dice_settings(callback: CallbackQuery):
    """Настройки Dice игры"""
    await callback.message.edit_text(
        "🎲 <b>НАСТРОЙКИ DICE</b>\n\n"
        f"🎯 Множитель победы: x{DICE_MULTIPLIER}\n"
        f"💰 Минимальная ставка: {MIN_BET}\n"
        f"💰 Максимальная ставка: {MAX_BET}\n\n"
        f"Для изменения параметров используйте команды:\n"
        f"• /set_dice_multiplier <множитель>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_games_back")]
        ])
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_games_back")
async def admin_games_back(callback: CallbackQuery):
    """Возврат к управлению играми"""
    await admin_games_control(callback.message)
    await callback.answer()


@dp.callback_query(F.data == "admin_reset_games_stats")
async def admin_reset_games_stats(callback: CallbackQuery):
    """Сброс статистики игр"""
    global crash_history, mines_history, dice_history
    crash_history = []
    mines_history = []
    dice_history = []
    
    await callback.message.edit_text(
        "✅ <b>Статистика игр сброшена!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_games_back")]
        ])
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_clear_games_history")
async def admin_clear_games_history(callback: CallbackQuery):
    """Очистка истории игр"""
    global crash_history, mines_history, dice_history
    crash_history = []
    mines_history = []
    dice_history = []
    
    await callback.message.edit_text(
        "✅ <b>История игр очищена!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_games_back")]
        ])
    )
    await callback.answer()


# ===================== АДМИН: ПРОМОКОДЫ =====================
@dp.message(F.text == "🎁 Промокоды")
async def admin_promocodes(message: Message, state: FSMContext):
    """Управление промокодами"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_create_promo")],
        [InlineKeyboardButton(text="📋 Список промокодов", callback_data="admin_list_promos")],
        [InlineKeyboardButton(text="🗑 Удалить промокод", callback_data="admin_delete_promo")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ])
    
    promos_list = "\n".join([f"• {code}: {data['amount']}⭐️ ({data['uses']}/{data['max_uses']} использований)" 
                             for code, data in promo_codes.items()])
    
    if not promos_list:
        promos_list = "Нет активных промокодов"
    
    await message.answer(
        f"🎁 <b>УПРАВЛЕНИЕ ПРОМОКОДАМИ</b>\n\n"
        f"<b>Активные промокоды:</b>\n{promos_list}\n\n"
        f"Выберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "admin_create_promo")
async def admin_create_promo_start(callback: CallbackQuery, state: FSMContext):
    """Начало создания промокода"""
    await state.set_state(GameStates.admin_promo_create)
    await callback.message.edit_text(
        "🎁 <b>СОЗДАНИЕ ПРОМОКОДА</b>\n\n"
        "Введите название промокода (латиница, цифры):\n\n"
        "<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@dp.message(GameStates.admin_promo_create)
async def admin_create_promo_name(message: Message, state: FSMContext):
    """Ввод названия промокода"""
    code = message.text.strip().upper()
    
    if code in promo_codes:
        await message.answer("❌ Промокод с таким названием уже существует!")
        return
    
    await state.update_data(promo_code=code)
    await state.set_state(GameStates.admin_promo_amount)
    await message.answer(
        f"🎁 <b>СОЗДАНИЕ ПРОМОКОДА</b>\n\n"
        f"Название: {code}\n\n"
        f"Введите сумму бонуса (в Stars):",
        parse_mode=ParseMode.HTML
    )


@dp.message(GameStates.admin_promo_amount)
async def admin_create_promo_amount(message: Message, state: FSMContext):
    """Ввод суммы бонуса"""
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше 0!")
            return
    except:
        await message.answer("❌ Введите число!")
        return
    
    data = await state.get_data()
    code = data.get("promo_code")
    
    promo_codes[code] = {
        "amount": amount,
        "uses": 0,
        "max_uses": 1,
        "created_by": message.from_user.id,
        "created_at": datetime.now().isoformat()
    }
    
    await state.clear()
    await message.answer(
        f"✅ <b>Промокод создан!</b>\n\n"
        f"🎁 {code}: {format_stars(amount)}\n"
        f"📊 Активаций: 0/1",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_main_keyboard()
    )


@dp.callback_query(F.data == "admin_list_promos")
async def admin_list_promos(callback: CallbackQuery):
    """Список промокодов"""
    if not promo_codes:
        await callback.answer("Нет активных промокодов", show_alert=True)
        return
    
    text = "🎁 <b>СПИСОК ПРОМОКОДОВ</b>\n\n"
    for code, data in promo_codes.items():
        text += f"• <b>{code}</b>: {format_stars(data['amount'])}\n"
        text += f"  Использований: {data['uses']}/{data['max_uses']}\n"
        text += f"  Создан: {data['created_at'][:19]}\n\n"
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_promo_back")]
    ]))
    await callback.answer()


@dp.callback_query(F.data == "admin_promo_back")
async def admin_promo_back(callback: CallbackQuery):
    """Возврат к управлению промокодами"""
    await admin_promocodes(callback.message, None)
    await callback.answer()


# ===================== АДМИН: РЕЗЕРВНОЕ КОПИРОВАНИЕ =====================
@dp.message(F.text == "💾 Резервное копирование")
async def admin_backup(message: Message):
    """Резервное копирование данных"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    filename = save_backup()
    
    await message.answer(
        f"✅ <b>Резервная копия создана!</b>\n\n"
        f"📁 Файл: {os.path.basename(filename)}\n"
        f"💾 Размер: {os.path.getsize(filename)} байт\n"
        f"📅 Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_main_keyboard()
    )


# ===================== АДМИН: ЭКСПОРТ ДАННЫХ =====================
@dp.message(F.text == "📈 Экспорт данных")
async def admin_export(message: Message):
    """Экспорт данных"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    export_data = {
        "users": {uid: {"balance": bal, "username": users_username.get(uid)} for uid, bal in users_balance.items()},
        "stats": users_stats,
        "transactions": {uid: tx[:50] for uid, tx in transactions.items()},
        "profit": bot_stats["total_profit"],
        "export_date": datetime.now().isoformat()
    }
    
    filename = f"{DATA_DIR}/export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False, default=str)
    
    await message.answer_document(
        FSInputFile(filename),
        caption=f"📊 Экспорт данных от {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        reply_markup=get_admin_main_keyboard()
    )
    
    os.remove(filename)


# ===================== АДМИН: СИСТЕМНЫЕ НАСТРОЙКИ =====================
@dp.message(F.text == "🔧 Системные настройки")
async def admin_system_settings(message: Message):
    """Системные настройки"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Перезагрузить бота", callback_data="admin_restart")],
        [InlineKeyboardButton(text="🔧 Режим обслуживания", callback_data="admin_toggle_maintenance")],
        [InlineKeyboardButton(text="📢 Объявление", callback_data="admin_announcement")],
        [InlineKeyboardButton(text="🎁 Глобальный бонус", callback_data="admin_global_bonus")],
        [InlineKeyboardButton(text="📊 Сбросить статистику", callback_data="admin_reset_stats")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ])
    
    await message.answer(
        "🔧 <b>СИСТЕМНЫЕ НАСТРОЙКИ</b>\n\n"
        f"🔒 Режим обслуживания: {'Включен' if system_settings['maintenance_mode'] else 'Выключен'}\n"
        f"📊 Всего пользователей: {bot_stats['total_users']}\n"
        f"💰 Прибыль бота: {format_stars(bot_stats['total_profit'])}\n"
        f"⏱ Время работы: {format_time((datetime.now() - datetime.fromisoformat(bot_stats['server_start_time'])).seconds)}",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "admin_toggle_maintenance")
async def admin_toggle_maintenance(callback: CallbackQuery):
    """Включение/выключение режима обслуживания"""
    system_settings["maintenance_mode"] = not system_settings["maintenance_mode"]
    status = "включен" if system_settings["maintenance_mode"] else "выключен"
    
    await callback.answer(f"Режим обслуживания {status}!", show_alert=True)
    await admin_system_settings(callback.message)
    await callback.answer()


@dp.callback_query(F.data == "admin_restart")
async def admin_restart(callback: CallbackQuery):
    """Перезагрузка бота"""
    await callback.answer("Бот перезагружается...", show_alert=True)
    await asyncio.sleep(1)
    # Здесь можно добавить логику перезагрузки
    await callback.message.edit_text("✅ Бот перезагружен!")
    await callback.answer()


@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    """Возврат в админ-панель"""
    await callback.message.edit_text(
        "👑 <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n\n"
        "Выберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_main_keyboard()
    )
    await callback.answer()


# ===================== НАВИГАЦИОННЫЕ КНОПКИ =====================
@dp.message(F.text == "🔙 В главное меню")
async def back_to_main_from_admin(message: Message):
    """Возврат в главное меню из админ-панели"""
    await message.answer(
        "🌟 <b>Главное меню</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(message.from_user.id)
    )


@dp.message(F.text == "🔙 Главное меню")
async def back_to_main_from_games(message: Message):
    """Возврат в главное меню из игр"""
    await message.answer(
        "🌟 <b>Главное меню</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(message.from_user.id)
    )


@dp.callback_query(F.data == "back_to_games")
async def back_to_games_callback(callback: CallbackQuery):
    """Возврат к играм"""
    await callback.message.edit_text(
        "🎮 <b>Выберите игру</b>\n\n"
        "👇 Нажмите на кнопку с игрой:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery):
    """Возврат в главное меню из callback"""
    await callback.message.edit_text(
        "🌟 <b>Главное меню</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(callback.from_user.id)
    )
    await callback.answer()


@dp.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext):
    """Обработка команды /cancel"""
    await state.clear()
    await message.answer(
        "❌ Действие отменено.",
        reply_markup=get_main_keyboard(message.from_user.id)
    )


# ===================== ОБРАБОТЧИК КНОПКИ ОТМЕНЫ =====================
@dp.message(F.text == "❌ Отмена")
async def cancel_button(message: Message, state: FSMContext):
    """Обработка кнопки отмены"""
    await state.clear()
    await message.answer(
        "❌ Операция отменена.",
        reply_markup=get_admin_main_keyboard() if is_admin(message.from_user.username or "") else get_main_keyboard(message.from_user.id)
    )


# ===================== ПЛАТЕЖИ =====================
async def create_stars_invoice(message: Message, user_id: int, amount: int):
    """Создание инвойса для пополнения"""
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
    """Обработка pre-checkout запроса"""
    payload = pre_checkout_query.invoice_payload
    
    if payload in pending_payments:
        await pre_checkout_query.answer(ok=True)
    else:
        await pre_checkout_query.answer(ok=False, error_message="Ошибка платежа")


@dp.message(F.successful_payment)
async def process_successful_payment(message: Message):
    """Обработка успешного платежа"""
    payment = message.successful_payment
    payload = payment.invoice_payload
    amount = payment.total_amount
    user_id = message.from_user.id
    
    if payload not in pending_payments:
        await message.answer("⚠️ Ошибка обработки платежа!")
        return
    
    # Начисляем средства
    new_balance = update_balance(user_id, amount)
    
    # Сохраняем транзакцию
    save_transaction(user_id, amount, "deposit", f"Пополнение {amount} Stars")
    
    # Обновляем статистику пользователя
    stats = get_user_stats(user_id)
    stats["total_deposits"] += 1
    stats["total_deposit_amount"] += amount
    
    # Обновляем статистику бота
    bot_stats["total_deposits"] += 1
    bot_stats["total_deposit_amount"] += amount
    
    # Реферальный бонус
    if user_id in users_referrer:
        referrer_id = users_referrer[user_id]
        bonus = amount * system_settings["referral_percent"] / 100
        
        if bonus > 0:
            update_balance(referrer_id, bonus)
            save_transaction(referrer_id, bonus, "referral_earning", 
                           f"{system_settings['referral_percent']}% от пополнения реферала")
            
            # Обновляем статистику реферера
            stats_ref = get_user_stats(referrer_id)
            stats_ref["referral_earned"] += bonus
            
            # Уведомляем реферера
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
    
    # Отправляем подтверждение
    await message.answer(
        f"✅ <b>Платеж успешно обработан!</b>\n\n"
        f"💰 Пополнение: +{format_stars(amount)}\n"
        f"💰 Новый баланс: {format_stars(new_balance)}\n\n"
        f"🎮 Приятной игры в StarPlay!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(user_id)
    )
    
    # Очищаем pending payment
    del pending_payments[payload]


@dp.callback_query(F.data.startswith("deposit_"))
async def deposit_callback(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора суммы пополнения"""
    amount_str = callback.data.split("_")[-1]
    
    if amount_str == "custom":
        await callback.message.answer(
            "✏️ <b>Введите сумму пополнения</b>\n\n"
            "💰 Минимум: 1 Star\n"
            "💰 Максимум: 10000 Stars\n\n"
            "<i>Просто отправьте число в чат:</i>",
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
    """Обработка пользовательской суммы пополнения"""
    try:
        amount = int(message.text.strip())
        if amount < 1:
            await message.answer("❌ Минимальная сумма: 1 Star")
            return
        if amount > 10000:
            await message.answer("❌ Максимальная сумма: 10000 Stars")
            return
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число!")
        return
    
    await state.clear()
    await create_stars_invoice(message, message.from_user.id, amount)


# ===================== ОБРАБОТЧИК ОШИБОК =====================
@dp.errors()
async def errors_handler(update, exception):
    """Глобальный обработчик ошибок"""
    logger.error(f"Произошла ошибка: {exception}")
    
    try:
        if update and hasattr(update, 'event') and hasattr(update.event, 'chat'):
            await bot.send_message(
                update.event.chat.id,
                "⚠️ Произошла техническая ошибка. Администраторы уже уведомлены.",
                parse_mode=ParseMode.HTML
            )
    except:
        pass


# ===================== КОМАНДЫ НАСТРОЕК =====================
@dp.message(Command("set_min_bet"))
async def set_min_bet(message: Message):
    """Установка минимальной ставки"""
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!")
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
        
        system_settings["min_bet"] = new_min
        await message.answer(f"✅ Минимальная ставка установлена: {format_stars(system_settings['min_bet'])}")
    except:
        await message.answer("❌ Введите число!")


@dp.message(Command("set_max_bet"))
async def set_max_bet(message: Message):
    """Установка максимальной ставки"""
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!")
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_max_bet <сумма>")
        return
    
    try:
        new_max = float(args[1])
        if new_max < system_settings["min_bet"]:
            await message.answer(f"❌ Максимальная ставка не может быть меньше минимальной ({system_settings['min_bet']})")
            return
        
        system_settings["max_bet"] = new_max
        await message.answer(f"✅ Максимальная ставка установлена: {format_stars(system_settings['max_bet'])}")
    except:
        await message.answer("❌ Введите число!")


@dp.message(Command("set_house_edge"))
async def set_house_edge(message: Message):
    """Установка house edge"""
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!")
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
        
        system_settings["crash_house_edge"] = (100 - percent) / 100
        await message.answer(f"✅ House edge установлен: {percent}% (множитель: x{system_settings['crash_house_edge']})")
    except:
        await message.answer("❌ Введите число!")


@dp.message(Command("set_daily_bonus"))
async def set_daily_bonus(message: Message):
    """Включение/выключение ежедневного бонуса"""
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!")
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_daily_bonus <вкл/выкл>")
        return
    
    value = args[1].lower()
    if value == "вкл" or value == "on":
        system_settings["daily_bonus_enabled"] = True
        await message.answer("✅ Ежедневный бонус ВКЛЮЧЁН!")
    elif value == "выкл" or value == "off":
        system_settings["daily_bonus_enabled"] = False
        await message.answer("✅ Ежедневный бонус ВЫКЛЮЧЁН!")
    else:
        await message.answer("❌ Используйте 'вкл' или 'выкл'")


@dp.message(Command("set_maintenance"))
async def set_maintenance(message: Message):
    """Включение/выключение режима обслуживания"""
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!")
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_maintenance <вкл/выкл>")
        return
    
    value = args[1].lower()
    if value == "вкл" or value == "on":
        system_settings["maintenance_mode"] = True
        await message.answer("🔧 Режим обслуживания ВКЛЮЧЁН! Пользователи не смогут играть.")
    elif value == "выкл" or value == "off":
        system_settings["maintenance_mode"] = False
        await message.answer("✅ Режим обслуживания ВЫКЛЮЧЁН! Бот снова работает.")
    else:
        await message.answer("❌ Используйте 'вкл' или 'выкл'")


@dp.message(Command("set_chat"))
async def set_chat(message: Message):
    """Установка ссылки на чат"""
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!")
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_chat <ссылка>")
        return
    
    system_settings["chat_link"] = args[1]
    await message.answer(f"✅ Ссылка на чат установлена: {system_settings['chat_link']}")


@dp.message(Command("set_channel"))
async def set_channel(message: Message):
    """Установка ссылки на канал"""
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!")
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_channel <ссылка>")
        return
    
    system_settings["channel_link"] = args[1]
    await message.answer(f"✅ Ссылка на канал установлена: {system_settings['channel_link']}")


@dp.message(Command("set_support"))
async def set_support(message: Message):
    """Установка ссылки на поддержку"""
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!")
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_support <ссылка>")
        return
    
    system_settings["support_link"] = args[1]
    await message.answer(f"✅ Ссылка на поддержку установлена: {system_settings['support_link']}")


# ===================== ЗАПУСК БОТА =====================
async def main():
    """Запуск бота"""
    logger.info("🚀 StarPlay Casino Bot запускается...")
    
    # Создаём директории если их нет
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    # Пытаемся загрузить последний бэкап
    backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith("backup_")])
    if backups:
        load_backup(os.path.join(BACKUP_DIR, backups[-1]))
        logger.info(f"Loaded latest backup: {backups[-1]}")
    
    # Удаляем вебхук
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())