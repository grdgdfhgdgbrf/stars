import asyncio
import hashlib
import logging
import random
import json
import time
import math
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Union
from decimal import Decimal
from pathlib import Path

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
from aiogram.exceptions import TelegramBadRequest

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
MAX_TRANSACTIONS_PER_USER = 1000
MAX_HISTORY_ITEMS = 100
BACKUP_INTERVAL_HOURS = 24

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
users_2fa_enabled: Dict[int, bool] = {}
users_2fa_code: Dict[int, str] = {}
users_language: Dict[int, str] = {}
users_notifications: Dict[int, bool] = {}

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

# Системные уведомления
announcements: List[dict] = []
pending_announcements: List[dict] = []

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
    "total_withdrawals": 0,
    "total_withdrawal_amount": 0.0,
    "crash_games_played": 0,
    "mines_games_played": 0,
    "dice_games_played": 0,
    "server_start_time": datetime.now().isoformat(),
    "last_backup": None
}

# Чёрный список
blacklist: Dict[int, dict] = {}

# Системные сообщения
system_messages = {
    "welcome": "🌟 Добро пожаловать в StarPlay!",
    "maintenance": "🔧 Бот на техническом обслуживании",
    "ban": "🚫 Ваш аккаунт заблокирован"
}

# Настройки бота
bot_settings = {
    "maintenance_mode": False,
    "min_bet": MIN_BET,
    "max_bet": MAX_BET,
    "crash_house_edge": CRASH_HOUSE_EDGE,
    "crash_max_multiplier": CRASH_MAX_MULTIPLIER,
    "mines_board_size": MINES_BOARD_SIZE,
    "mines_mines_count": MINES_MINES_COUNT,
    "dice_multiplier": DICE_MULTIPLIER,
    "referral_percent": REFERRAL_BONUS_PERCENT,
    "daily_bonus_enabled": True,
    "daily_bonus_min": DAILY_BONUS_MIN,
    "daily_bonus_max": DAILY_BONUS_MAX,
    "chat_link": "https://t.me/starplay_chat",
    "channel_link": "https://t.me/starplay_news",
    "support_link": "https://t.me/starplay_support"
}

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

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
    return f"⭐️ {amount:.2f} Stars"

def format_number(num: float) -> str:
    """Форматирование числа"""
    if num >= 1000000:
        return f"{num/1000000:.1f}M"
    elif num >= 1000:
        return f"{num/1000:.1f}K"
    return f"{num:.2f}"

def format_time(seconds: int) -> str:
    """Форматирование времени"""
    if seconds < 60:
        return f"{seconds} сек"
    elif seconds < 3600:
        return f"{seconds//60} мин {seconds%60} сек"
    elif seconds < 86400:
        return f"{seconds//3600} ч {(seconds%3600)//60} мин"
    else:
        return f"{seconds//86400} д { (seconds%86400)//3600 } ч"

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
    
    # Ограничиваем количество транзакций
    if len(transactions[user_id]) > MAX_TRANSACTIONS_PER_USER:
        transactions[user_id] = transactions[user_id][-MAX_TRANSACTIONS_PER_USER:]
    
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
            "last_game_played": None
        }
    return users_stats[user_id]

def get_random_emoji() -> str:
    """Случайный эмодзи для настроения"""
    emojis = [
        "🎲", "🎯", "⚡️", "💫", "🌟", "⭐️", "✨", "🎮", "🎰", "🔥",
        "💰", "💎", "🏆", "🎉", "🚀", "⚡", "💪", "🎯", "🏅", "🌟"
    ]
    return random.choice(emojis)

def generate_referral_link(user_id: int) -> str:
    """Генерация реферальной ссылки"""
    code = hashlib.md5(f"starplay_{user_id}_{datetime.now().date()}".encode()).hexdigest()[:8]
    return f"https://t.me/{bot.username}?start=ref_{code}"

def generate_verify_code() -> str:
    """Генерация кода верификации"""
    return str(random.randint(100000, 999999))

def generate_promo_code() -> str:
    """Генерация промокода"""
    import string
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(8))

def save_backup():
    """Сохранение резервной копии"""
    backup_data = {
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
        "crash_history": crash_history[-100:],
        "mines_history": mines_history[-100:],
        "dice_history": dice_history[-100:],
        "bot_stats": bot_stats,
        "timestamp": datetime.now().isoformat()
    }
    
    filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, indent=2, ensure_ascii=False)
    
    # Удаляем старые бэкапы
    backups = sorted([f for f in os.listdir() if f.startswith("backup_") and f.endswith(".json")])
    for old_backup in backups[:-10]:
        os.remove(old_backup)
    
    bot_stats["last_backup"] = datetime.now().isoformat()
    logger.info(f"Бэкап сохранён: {filename}")
    return filename

def load_backup(filename: str) -> bool:
    """Загрузка резервной копии"""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        users_balance.update(data.get("balance", {}))
        users_referrer.update(data.get("referrer", {}))
        users_referrals.update(data.get("referrals", {}))
        users_stats.update(data.get("stats", {}))
        transactions.update(data.get("transactions", {}))
        users_username.update(data.get("username", {}))
        users_join_date.update(data.get("join_date", {}))
        users_ban.update(data.get("ban", {}))
        users_verify.update(data.get("verify", {}))
        promo_codes.update(data.get("promo_codes", {}))
        
        logger.info(f"Бэкап загружен: {filename}")
        return True
    except Exception as e:
        logger.error(f"Ошибка загрузки бэкапа: {e}")
        return False

def auto_backup():
    """Автоматическое резервное копирование"""
    if bot_stats["last_backup"]:
        last_backup = datetime.fromisoformat(bot_stats["last_backup"])
        hours_passed = (datetime.now() - last_backup).total_seconds() / 3600
        if hours_passed >= BACKUP_INTERVAL_HOURS:
            save_backup()
    else:
        save_backup()

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
    builder.button(text="❓ Помощь")
    builder.button(text="⚙️ Настройки")
    
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
    builder.button(text="⚙️ Настройки игр")
    builder.button(text="🎮 Управление играми")
    builder.button(text="🎁 Промокоды")
    builder.button(text="💾 Резервное копирование")
    builder.button(text="📈 Экспорт данных")
    builder.button(text="🔧 Системные настройки")
    builder.button(text="📢 Объявления")
    builder.button(text="🎁 Глобальный бонус")
    builder.button(text="📊 Отчёт по прибыли")
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

def get_settings_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура настроек пользователя"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔔 Уведомления", callback_data="settings_notifications"),
         InlineKeyboardButton(text="🌐 Язык", callback_data="settings_language")],
        [InlineKeyboardButton(text="🔐 2FA", callback_data="settings_2fa"),
         InlineKeyboardButton(text="📊 Сброс статистики", callback_data="settings_reset_stats")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])

def get_language_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора языка"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="settings_back")]
    ])

def get_back_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура возврата"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_games")]
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
            f"Для решения вопроса обратитесь к администратору: {bot_settings['support_link']}",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Проверка режима обслуживания
    if bot_settings["maintenance_mode"] and not is_admin(username):
        await message.answer(
            f"🔧 <b>Бот на техническом обслуживании!</b>\n\n"
            f"Пожалуйста, зайдите позже.\n\n"
            f"По всем вопросам: {bot_settings['support_link']}",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Сохраняем данные пользователя
    users_username[user_id] = username
    users_last_seen[user_id] = datetime.now().isoformat()
    
    if user_id not in users_join_date:
        users_join_date[user_id] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        bot_stats["total_users"] += 1
    
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
                    
                    # Обновляем статистику реферера
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
        f"💣 <b>MINES</b> — Сапёр с множителем до x{1.2 ** 20:.1f}\n"
        f"🎲 <b>DICE</b> — Угадай число, множитель x{DICE_MULTIPLIER}\n\n"
        f"<b>💫 Как начать играть:</b>\n"
        f"1️⃣ Пополните баланс через Telegram Stars\n"
        f"2️⃣ Выберите игру в меню «🎮 Игры»\n"
        f"3️⃣ Делайте ставки и выигрывайте!\n\n"
        f"<b>🎁 Бонусы:</b>\n"
        f"• Ежедневный бонус до {DAILY_BONUS_MAX} Stars\n"
        f"• Реферальная программа: +{REFERRAL_BONUS_PERCENT}% с пополнений друзей\n"
        f"• Промокоды и розыгрыши\n\n"
        f"<b>📞 Контакты:</b>\n"
        f"• Чат: {bot_settings['chat_link']}\n"
        f"• Канал: {bot_settings['channel_link']}\n"
        f"• Поддержка: {bot_settings['support_link']}\n\n"
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
        f"💣 <b>MINES</b> — Открывайте клетки с 💎, избегайте 💣\n"
        f"🎲 <b>DICE</b> — Угадайте, выпадет число выше или ниже 50\n\n"
        f"<b>💰 Баланс и пополнение:</b>\n"
        f"• Пополнение через Telegram Stars\n"
        f"• Минимальная ставка: {bot_settings['min_bet']} Stars\n"
        f"• Максимальная ставка: {bot_settings['max_bet']} Stars\n\n"
        f"<b>👥 Реферальная система:</b>\n"
        f"• Пригласите друга — получите {REFERRAL_INVITE_BONUS} Stars\n"
        f"• Друг получает {REFERRAL_SIGNUP_BONUS} Stars\n"
        f"• Вы получаете {bot_settings['referral_percent']}% от пополнений друга\n\n"
        f"<b>🎁 Ежедневный бонус:</b>\n"
        f"• Забирайте бонус каждый день в меню «🎁 Бонус»\n"
        f"• За ежедневный вход бонус увеличивается!\n"
        f"• Максимальный бонус: {DAILY_BONUS_MAX} Stars\n\n"
        f"<b>⚙️ Команды:</b>\n"
        f"• /start — Запуск бота\n"
        f"• /help — Помощь\n"
        f"• /balance — Баланс\n"
        f"• /bonus — Ежедневный бонус\n"
        f"• /games — Игры\n"
        f"• /profile — Профиль\n"
        f"• /top — Топ игроков\n"
        f"• /referral — Реферальная ссылка\n\n"
        f"<b>📞 Контакты:</b>\n"
        f"• Чат: {bot_settings['chat_link']}\n"
        f"• Поддержка: {bot_settings['support_link']}"
    )
    
    await message.answer(help_text, parse_mode=ParseMode.HTML)

@dp.message(Command("balance"))
async def cmd_balance(message: Message):
    """Команда /balance"""
    await balance_reply(message)

@dp.message(Command("bonus"))
async def cmd_bonus_command(message: Message):
    """Команда /bonus"""
    await bonus_reply(message)

@dp.message(Command("games"))
async def cmd_games(message: Message):
    """Команда /games"""
    await games_reply(message)

@dp.message(Command("profile"))
async def cmd_profile(message: Message):
    """Команда /profile"""
    await profile_reply(message)

@dp.message(Command("top"))
async def cmd_top(message: Message):
    """Команда /top"""
    await top_reply(message)

@dp.message(Command("referral"))
async def cmd_referral(message: Message):
    """Команда /referral"""
    await referrals_reply(message)

# ===================== ГЛАВНЫЕ КНОПКИ =====================
@dp.message(F.text == "💰 Баланс")
async def balance_reply(message: Message):
    """Показать баланс"""
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    
    await message.answer(
        f"💰 <b>Ваш баланс</b>\n\n"
        f"{format_stars(balance)}\n\n"
        f"💡 <b>Способы пополнения:</b>\n"
        f"• Telegram Stars — мгновенно\n\n"
        f"🎁 <b>Как получить бонусы:</b>\n"
        f"• Ежедневный бонус — до {DAILY_BONUS_MAX} Stars\n"
        f"• Реферальная программа — {bot_settings['referral_percent']}% от пополнений друзей\n"
        f"• Промокоды — следите в канале!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@dp.message(F.text == "⭐️ Пополнить")
async def deposit_reply(message: Message):
    """Пополнение баланса"""
    await message.answer(
        "⭐️ <b>Пополнение баланса</b>\n\n"
        "💰 <b>Способы пополнения:</b>\n"
        "• Telegram Stars — мгновенно\n"
        "• Минимальная сумма: 1 Star\n"
        "• Максимальная сумма: 10000 Stars\n\n"
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
        "📊 <b>История игр</b> — Посмотреть свои результаты\n\n"
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
    
    text = (
        f"👥 <b>Реферальная программа</b>\n\n"
        f"🏆 <b>Ваша статистика:</b>\n"
        f"• Приглашено друзей: {ref_count}\n"
        f"• Заработано: {format_stars(total_earned)}\n\n"
        f"<b>📋 Как это работает:</b>\n"
        f"• Друг регистрируется по вашей ссылке\n"
        f"• Он получает +{REFERRAL_SIGNUP_BONUS} Stars\n"
        f"• Вы получаете +{REFERRAL_INVITE_BONUS} Stars\n"
        f"• Вы получаете {bot_settings['referral_percent']}% от каждого пополнения друга\n\n"
        f"<b>🔗 Ваша реферальная ссылка:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"💡 Поделитесь ссылкой с друзьями и зарабатывайте!\n"
        f"📢 Чем больше друзей — тем больше бонусов!"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться ссылкой", 
                              url=f"https://t.me/share/url?url={ref_link}&text=StarPlay — лучшие игры с выигрышами! Присоединяйся по моей ссылке и получи бонус!")],
        [InlineKeyboardButton(text="📊 Статистика рефералов", callback_data="referral_stats")],
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
    
    # Сортируем по выигрышам
    sorted_by_won = sorted(users_stats.items(),
                          key=lambda x: x[1].get("total_won", 0),
                          reverse=True)[:15]
    
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
    
    top_won = "\n🏆 <b>ТОП-15 ПО ВЫИГРЫШАМ</b>\n\n"
    for idx, (uid, stats) in enumerate(sorted_by_won, 1):
        if users_ban.get(uid, False):
            continue
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
        uname = users_username.get(uid, str(uid))
        name = f"@{uname}" if uname else str(uid)
        won = stats.get("total_won", 0)
        top_won += f"{medal} {name} — {format_stars(won)}\n"
    
    # Отправляем с кнопками переключения
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 По балансу", callback_data="top_balance"),
         InlineKeyboardButton(text="🏆 По победам", callback_data="top_wins"),
         InlineKeyboardButton(text="💎 По выигрышам", callback_data="top_won")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])
    
    await message.answer(
        top_balance,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

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
        f"✅ Верификация: {'✅ Верифицирован' if users_verify.get(uid, False) else '❌ Не верифицирован'}\n"
        f"🔐 2FA: {'✅ Включена' if users_2fa_enabled.get(uid, False) else '❌ Выключена'}\n"
        f"🕐 Последний визит: {users_last_seen.get(uid, 'неизвестно')[:19]}\n\n"
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
        f"💳 <b>Финансы:</b>\n"
        f"├ 💰 Пополнений: {stats['total_deposits']} ({format_stars(stats['total_deposit_amount'])})\n"
        f"├ 💸 Выводов: {stats['total_withdrawals']} ({format_stars(stats['total_withdrawal_amount'])})\n"
        f"├ 👥 Рефералов: {stats['referral_count']}\n"
        f"├ 🎁 Реферальный доход: {format_stars(stats['referral_earned'])}\n"
        f"├ 🎁 Бонусов получено: {stats['daily_bonus_count']}\n"
        f"└ 📅 Текущий стрик: {stats['daily_bonus_streak']} дней\n\n"
        f"💡 <b>Советы:</b>\n"
        f"• Забирайте ежедневный бонус каждый день\n"
        f"• Приглашайте друзей для дополнительного дохода\n"
        f"• Следите за промокодами в канале"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 История транзакций", callback_data="profile_transactions"),
         InlineKeyboardButton(text="🎮 История игр", callback_data="profile_games")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])
    
    await message.answer(profile_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

@dp.message(F.text == "🎁 Бонус")
async def bonus_reply(message: Message):
    """Ежедневный бонус"""
    user_id = message.from_user.id
    today = datetime.now().date().isoformat()
    
    if users_ban.get(user_id, False):
        await message.answer("❌ Ваш аккаунт заблокирован!", parse_mode=ParseMode.HTML)
        return
    
    if not bot_settings["daily_bonus_enabled"]:
        await message.answer("🔧 Ежедневный бонус временно отключён!", parse_mode=ParseMode.HTML)
        return
    
    if users_daily_bonus.get(user_id) == today:
        # Подсчитываем оставшееся время
        next_bonus = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        time_left = next_bonus - datetime.now()
        hours = time_left.seconds // 3600
        minutes = (time_left.seconds % 3600) // 60
        
        # Показываем следующий бонус
        next_streak = users_daily_bonus_streak.get(user_id, 0) + 1
        next_bonus_amount = min(DAILY_BONUS_MAX, DAILY_BONUS_MIN + (next_streak - 1) * 2)
        
        await message.answer(
            f"🎁 <b>Вы уже получили сегодняшний бонус!</b>\n\n"
            f"⏰ Следующий бонус через: {hours} ч {minutes} мин\n"
            f"📅 Текущий стрик: {users_daily_bonus_streak.get(user_id, 0)} дней\n"
            f"🎯 Завтрашний бонус: ~{next_bonus_amount:.0f} Stars\n\n"
            f"💡 <b>Совет:</b>\n"
            f"• Забирайте бонус каждый день\n"
            f"• Стрик увеличивает бонус\n"
            f"• Максимальный бонус: {DAILY_BONUS_MAX} Stars",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Расчёт бонуса с учётом стрика
    streak = users_daily_bonus_streak.get(user_id, 0)
    if users_daily_bonus.get(user_id) == (datetime.now() - timedelta(days=1)).date().isoformat():
        streak += 1
    else:
        streak = 1
    
    bonus_amount = min(DAILY_BONUS_MAX, DAILY_BONUS_MIN + (streak - 1) * 2)
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
    
    # Поздравления в зависимости от стрика
    congrats = [
        "🎉 Отличное начало!",
        "🎉 Хорошая привычка!",
        "🎉 Так держать!",
        "🎉 Вы на правильном пути!",
        "🎉 Прекрасная серия!",
        "🎉 Вы настоящий профи!",
        "🎉 Невероятный стрик!",
        "🎉 Легендарная серия!"
    ]
    congrats_text = congrats[min(streak - 1, len(congrats) - 1)]
    
    next_bonus = min(DAILY_BONUS_MAX, DAILY_BONUS_MIN + streak * 2)
    
    await message.answer(
        f"🎉 <b>Ежедневный бонус получен!</b> 🎉\n\n"
        f"{congrats_text}\n\n"
        f"+{format_stars(bonus_amount)}\n"
        f"📅 Стрик: {streak} {'день' if streak == 1 else 'дня' if streak < 5 else 'дней'}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}\n\n"
        f"🎯 Завтра вы получите до {next_bonus:.0f} Stars!\n"
        f"💡 Не пропускайте дни, чтобы увеличить бонус!",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text == "❓ Помощь")
async def help_reply(message: Message):
    """Помощь"""
    await cmd_help(message)

@dp.message(F.text == "⚙️ Настройки")
async def settings_reply(message: Message):
    """Настройки пользователя"""
    user_id = message.from_user.id
    
    settings_text = (
        f"⚙️ <b>Настройки пользователя</b>\n\n"
        f"🔔 <b>Уведомления:</b> {'✅ Включены' if users_notifications.get(user_id, True) else '❌ Выключены'}\n"
        f"🌐 <b>Язык:</b> {users_language.get(user_id, '🇷🇺 Русский')}\n"
        f"🔐 <b>2FA:</b> {'✅ Включена' if users_2fa_enabled.get(user_id, False) else '❌ Выключена'}\n\n"
        f"👇 <b>Выберите настройку для изменения:</b>"
    )
    
    await message.answer(settings_text, parse_mode=ParseMode.HTML, reply_markup=get_settings_keyboard())

# ===================== ОБРАБОТЧИКИ НАСТРОЕК =====================
@dp.callback_query(F.data == "settings_notifications")
async def settings_notifications(callback: CallbackQuery):
    """Настройка уведомлений"""
    user_id = callback.from_user.id
    current = users_notifications.get(user_id, True)
    users_notifications[user_id] = not current
    
    status = "включены" if users_notifications[user_id] else "выключены"
    await callback.message.edit_text(
        f"✅ <b>Уведомления {status}!</b>\n\n"
        f"Теперь вы {'будете' if users_notifications[user_id] else 'не будете'} получать уведомления о играх и бонусах.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_settings_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "settings_language")
async def settings_language(callback: CallbackQuery):
    """Выбор языка"""
    await callback.message.edit_text(
        "🌐 <b>Выберите язык / Choose language</b>\n\n"
        "👇 Нажмите на кнопку с языком:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_language_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("lang_"))
async def set_language(callback: CallbackQuery):
    """Установка языка"""
    user_id = callback.from_user.id
    lang = callback.data.split("_")[-1]
    
    languages = {"ru": "🇷🇺 Русский", "en": "🇬🇧 English"}
    users_language[user_id] = languages.get(lang, "🇷🇺 Русский")
    
    await callback.message.edit_text(
        f"✅ <b>Язык изменён на {users_language[user_id]}!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_settings_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "settings_2fa")
async def settings_2fa(callback: CallbackQuery):
    """Настройка 2FA"""
    user_id = callback.from_user.id
    current = users_2fa_enabled.get(user_id, False)
    
    if not current:
        code = generate_verify_code()
        users_2fa_code[user_id] = code
        await callback.message.edit_text(
            f"🔐 <b>Включение 2FA</b>\n\n"
            f"Ваш код подтверждения:\n"
            f"<code>{code}</code>\n\n"
            f"⚠️ <b>Важно:</b> Сохраните этот код в надёжном месте!\n"
            f"Он понадобится для входа в аккаунт.\n\n"
            f"✅ Нажмите «Подтвердить», чтобы включить 2FA.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Подтвердить", callback_data="2fa_enable")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="settings_back")]
            ])
        )
    else:
        users_2fa_enabled[user_id] = False
        users_2fa_code[user_id] = ""
        await callback.message.edit_text(
            f"✅ <b>2FA выключена!</b>\n\n"
            f"Теперь вход в аккаунт не требует дополнительного кода.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_settings_keyboard()
        )
    await callback.answer()

@dp.callback_query(F.data == "2fa_enable")
async def enable_2fa(callback: CallbackQuery):
    """Включение 2FA"""
    user_id = callback.from_user.id
    users_2fa_enabled[user_id] = True
    
    await callback.message.edit_text(
        f"✅ <b>2FA успешно включена!</b>\n\n"
        f"Теперь при входе в аккаунт вам потребуется вводить код.\n"
        f"<b>Ваш код:</b> <code>{users_2fa_code.get(user_id)}</code>\n\n"
        f"⚠️ Сохраните код в безопасном месте!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_settings_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "settings_reset_stats")
async def settings_reset_stats(callback: CallbackQuery):
    """Сброс статистики"""
    await callback.message.edit_text(
        f"⚠️ <b>Внимание!</b>\n\n"
        f"Вы действительно хотите сбросить статистику игр?\n"
        f"Это действие нельзя отменить.\n\n"
        f"Статистика игр будет обнулена, но баланс останется неизменным.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, сбросить", callback_data="reset_stats_confirm")],
            [InlineKeyboardButton(text="❌ Нет, отмена", callback_data="settings_back")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "reset_stats_confirm")
async def reset_stats_confirm(callback: CallbackQuery):
    """Подтверждение сброса статистики"""
    user_id = callback.from_user.id
    users_stats[user_id] = get_user_stats(user_id)  # Сброс через пересоздание
    
    await callback.message.edit_text(
        f"✅ <b>Статистика успешно сброшена!</b>\n\n"
        f"Ваша игровая статистика обнулена.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_settings_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "settings_back")
async def settings_back(callback: CallbackQuery):
    """Возврат в настройки"""
    user_id = callback.from_user.id
    
    settings_text = (
        f"⚙️ <b>Настройки пользователя</b>\n\n"
        f"🔔 <b>Уведомления:</b> {'✅ Включены' if users_notifications.get(user_id, True) else '❌ Выключены'}\n"
        f"🌐 <b>Язык:</b> {users_language.get(user_id, '🇷🇺 Русский')}\n"
        f"🔐 <b>2FA:</b> {'✅ Включена' if users_2fa_enabled.get(user_id, False) else '❌ Выключена'}\n\n"
        f"👇 <b>Выберите настройку для изменения:</b>"
    )
    
    await callback.message.edit_text(settings_text, parse_mode=ParseMode.HTML, reply_markup=get_settings_keyboard())
    await callback.answer()

# ===================== ИГРА 1: CRASH =====================
@dp.message(F.text == "📈 CRASH")
async def crash_start(message: Message, state: FSMContext):
    """Начало игры Crash"""
    user_id = message.from_user.id
    
    if users_ban.get(user_id, False):
        await message.answer("❌ Ваш аккаунт заблокирован!", parse_mode=ParseMode.HTML)
        return
    
    if bot_settings["maintenance_mode"]:
        await message.answer("🔧 Бот на техническом обслуживании!", parse_mode=ParseMode.HTML)
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
        f"📈 <b>CRASH — Умножай ставку!</b>\n\n"
        f"📋 <b>Правила игры:</b>\n"
        f"• Вы делаете ставку\n"
        f"• Множитель начинает расти\n"
        f"• Нужно забрать выигрыш ДО взрыва\n"
        f"• Если не забрали — ставка сгорает\n"
        f"• Максимальный множитель: x{bot_settings['crash_max_multiplier']}\n\n"
        f"📊 <b>Текущая статистика:</b>\n"
        f"• Всего сыграно: {bot_stats['crash_games_played']} игр\n"
        f"• Средний множитель: {sum(h.get('multiplier', 0) for h in crash_history[-100:]) / len(crash_history[-100:]) if crash_history else 0:.2f}x\n"
        f"• Последний краш: {crash_history[-1].get('multiplier', 0):.2f}x" if crash_history else "• Нет данных\n\n"
        f"💡 <b>Совет:</b> Не жадничайте — лучше забрать маленький выигрыш, чем потерять всё!"
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
            f"📊 Минимальная ставка: {bot_settings['min_bet']} Stars\n"
            f"📊 Максимальная ставка: {bot_settings['max_bet']} Stars",
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
    
    if bet < bot_settings["min_bet"] or bet > bot_settings["max_bet"]:
        await callback.answer(
            f"❌ Ставка должна быть от {bot_settings['min_bet']} до {bot_settings['max_bet']} Stars!",
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
    crash_point = random.uniform(1.01, bot_settings["crash_max_multiplier"])
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
        f"💀 Но можете не успеть забрать!\n\n"
        f"🎯 Цель: x{crash_point:.2f}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_crash_game_keyboard()
    )
    
    # Запускаем процесс роста множителя
    asyncio.create_task(run_crash_game(user_id, game_msg, state))
    await callback.answer()

async def run_crash_game(user_id: int, game_msg: Message, state: FSMContext):
    """Запуск процесса игры Crash"""
    game = active_crash.get(user_id)
    if not game:
        return
    
    bet = game["bet"]
    crash_point = game["crash_point"]
    multiplier = 1.00
    
    # Обновляем статистику бота
    bot_stats["crash_games_played"] += 1
    
    while multiplier < crash_point and user_id in active_crash:
        multiplier = round(multiplier + 0.01, 2)
        
        try:
            await game_msg.edit_text(
                f"📈 <b>CRASH — ИГРА ИДЁТ!</b>\n\n"
                f"💰 Ваша ставка: {format_stars(bet)}\n"
                f"📈 Текущий множитель: <b>x{multiplier:.2f}</b>\n"
                f"💎 Потенциальный выигрыш: {format_stars(bet * multiplier)}\n\n"
                f"⚠️ Заберите выигрыш до взрыва!\n"
                f"🎯 Цель: x{crash_point:.2f}\n"
                f"🔥 До взрыва: {int((crash_point - multiplier) / 0.01 * 0.1)} сек",
                parse_mode=ParseMode.HTML,
                reply_markup=get_crash_game_keyboard()
            )
        except:
            pass
        
        await asyncio.sleep(0.1)
    
    # Проверяем, не забрал ли пользователь выигрыш
    if user_id in active_crash:
        # Взрыв
        win = bet * multiplier
        
        # Обновляем статистику
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["crash_games"] += 1
        stats["total_lost"] += bet
        
        if win > bet:
            stats["games_won"] += 1
            stats["crash_wins"] += 1
            stats["total_won"] += win
        
        if multiplier > stats["crash_best_multiplier"]:
            stats["crash_best_multiplier"] = multiplier
        
        save_transaction(user_id, -bet, "game_loss", f"Crash краш на x{multiplier:.2f}", "crash")
        
        # Сохраняем историю
        crash_history.append({
            "multiplier": multiplier,
            "player": user_id,
            "bet": bet,
            "timestamp": datetime.now().isoformat()
        })
        if len(crash_history) > MAX_HISTORY_ITEMS:
            crash_history.pop(0)
        
        del active_crash[user_id]
        
        try:
            await game_msg.edit_text(
                f"💥 <b>CRASH — ВЗРЫВ!</b>\n\n"
                f"💰 Ваша ставка: {format_stars(bet)}\n"
                f"📈 Множитель в момент взрыва: x{multiplier:.2f}\n\n"
                f"😢 <b>Ставка сгорела!</b>\n"
                f"💰 Потеряно: {format_stars(bet)}\n\n"
                f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}\n\n"
                f"🎮 Чтобы сыграть снова, нажмите «Игры» в меню.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_games_keyboard()
            )
        except:
            pass

@dp.callback_query(F.data == "crash_cashout")
async def crash_cashout(callback: CallbackQuery, state: FSMContext):
    """Забор выигрыша в Crash"""
    user_id = callback.from_user.id
    
    if user_id not in active_crash:
        await callback.answer("Нет активной игры!", show_alert=True)
        return
    
    game = active_crash[user_id]
    bet = game["bet"]
    multiplier = game["multiplier"]
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
    
    save_transaction(user_id, win, "game_win", f"Crash выигрыш x{multiplier:.2f}", "crash")
    
    # Сохраняем историю
    crash_history.append({
        "multiplier": multiplier,
        "player": user_id,
        "bet": bet,
        "win": win,
        "timestamp": datetime.now().isoformat()
    })
    if len(crash_history) > MAX_HISTORY_ITEMS:
        crash_history.pop(0)
    
    del active_crash[user_id]
    await state.clear()
    
    await callback.message.edit_text(
        f"🎉 <b>CRASH — ВЫ ПОБЕДИЛИ!</b> 🎉\n\n"
        f"💰 Ваша ставка: {format_stars(bet)}\n"
        f"📈 Множитель: <b>x{multiplier:.2f}</b>\n"
        f"🏆 Выигрыш: {format_stars(win)}\n"
        f"💎 Чистая прибыль: {format_stars(win - bet)}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}\n\n"
        f"🎮 Чтобы сыграть снова, нажмите «Игры» в меню.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
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
        "💰 Ваш баланс не изменился.\n\n"
        "🎮 Чтобы начать новую игру, нажмите «Игры».",
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
    
    if bot_settings["maintenance_mode"]:
        await message.answer("🔧 Бот на техническом обслуживании!", parse_mode=ParseMode.HTML)
        return
    
    if user_id in active_mines:
        await message.answer(
            "⚠️ У вас уже есть активная игра!\n"
            "Заберите выигрыш или завершите игру.",
            parse_mode=ParseMode.HTML
        )
        return
    
    await state.set_state(GameStates.mines_bet)
    
    board_size = bot_settings["mines_board_size"]
    mines_count = bot_settings["mines_mines_count"]
    max_cells = board_size * board_size - mines_count
    max_multiplier = 1.2 ** max_cells
    
    mines_info = (
        f"💣 <b>MINES — Найди сокровища!</b>\n\n"
        f"📋 <b>Правила игры:</b>\n"
        f"• Поле {board_size}x{board_size}\n"
        f"• Спрятано {mines_count} мин\n"
        f"• Всего безопасных клеток: {max_cells}\n"
        f"• Каждая найденная 💎 увеличивает множитель x1.2\n"
        f"• Наступите на 💣 — проигрыш\n"
        f"• Можно забрать выигрыш в любой момент\n"
        f"• Максимальный множитель: x{max_multiplier:.1f}\n\n"
        f"📊 <b>Текущая статистика:</b>\n"
        f"• Всего сыграно: {bot_stats['mines_games_played']} игр\n"
        f"• Средний множитель: {sum(h.get('multiplier', 0) for h in mines_history[-100:]) / len(mines_history[-100:]) if mines_history else 0:.1f}x\n"
        f"• Лучший множитель: {max([h.get('multiplier', 0) for h in mines_history]) if mines_history else 0:.1f}x\n\n"
        f"💡 <b>Совет:</b> Забирайте выигрыш, когда множитель вас устраивает — риск не всегда оправдан!"
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
            f"📊 Минимальная ставка: {bot_settings['min_bet']} Stars\n"
            f"📊 Максимальная ставка: {bot_settings['max_bet']} Stars",
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
    
    if bet < bot_settings["min_bet"] or bet > bot_settings["max_bet"]:
        await callback.answer(
            f"❌ Ставка должна быть от {bot_settings['min_bet']} до {bot_settings['max_bet']} Stars!",
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
    board_size = bot_settings["mines_board_size"]
    mines_count = bot_settings["mines_mines_count"]
    
    board = [["💎" for _ in range(board_size)] for _ in range(board_size)]
    mines_placed = 0
    while mines_placed < mines_count:
        x, y = random.randint(0, board_size - 1), random.randint(0, board_size - 1)
        if board[x][y] == "💎":
            board[x][y] = "💣"
            mines_placed += 1
    
    active_mines[user_id] = {
        "bet": bet,
        "board": board,
        "revealed": [[False] * board_size for _ in range(board_size)],
        "multiplier": 1.0,
        "cells_opened": 0
    }
    
    await state.set_state(GameStates.mines_playing)
    
    max_cells = board_size * board_size - mines_count
    current_win = bet
    
    await callback.message.edit_text(
        f"💣 <b>MINES — ИГРА</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"✨ Текущий множитель: x1.0\n"
        f"📦 Открыто клеток: 0/{max_cells}\n"
        f"💎 Текущий выигрыш: {format_stars(current_win)}\n"
        f"🎯 Максимальный выигрыш: {format_stars(bet * (1.2 ** max_cells))}\n\n"
        f"👇 <b>Открывайте клетки и находите 💎!</b>\n"
        f"💡 Нажмите «Забрать», чтобы выйти с выигрышем",
        parse_mode=ParseMode.HTML,
        reply_markup=get_mines_board_keyboard(board, active_mines[user_id]["revealed"], bet, 1.0)
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
    
    if game["board"][x][y] == "💣":
        # Проигрыш
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["mines_games"] += 1
        stats["total_lost"] += game["bet"]
        
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
        if len(mines_history) > MAX_HISTORY_ITEMS:
            mines_history.pop(0)
        
        del active_mines[user_id]
        
        await callback.message.edit_text(
            f"💣 <b>MINES — ПРОИГРЫШ!</b>\n\n"
            f"💥 <b>Вы наступили на мину!</b>\n\n"
            f"💰 Ставка: {format_stars(game['bet'])} — проиграна\n"
            f"✨ Множитель в момент проигрыша: x{game['multiplier']:.2f}\n"
            f"📦 Открыто клеток: {game['cells_opened']}\n\n"
            f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_games_keyboard()
        )
    else:
        # Успех
        game["cells_opened"] += 1
        game["multiplier"] *= 1.2
        current_win = game["bet"] * game["multiplier"]
        
        board_size = bot_settings["mines_board_size"]
        mines_count = bot_settings["mines_mines_count"]
        max_cells = board_size * board_size - mines_count
        
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
            
            save_transaction(user_id, current_win, "game_win", 
                           f"Mines победа x{game['multiplier']:.1f}", "mines")
            
            bot_stats["mines_games_played"] += 1
            
            mines_history.append({
                "multiplier": game["multiplier"],
                "player": user_id,
                "bet": game["bet"],
                "win": current_win,
                "timestamp": datetime.now().isoformat()
            })
            if len(mines_history) > MAX_HISTORY_ITEMS:
                mines_history.pop(0)
            
            del active_mines[user_id]
            
            await callback.message.edit_text(
                f"🎉 <b>MINES — ПОБЕДА!</b> 🎉\n\n"
                f"🎯 <b>Вы нашли все сокровища!</b>\n\n"
                f"💰 Ставка: {format_stars(game['bet'])}\n"
                f"✨ Множитель: x{game['multiplier']:.2f}\n"
                f"📦 Открыто клеток: {max_cells}/{max_cells}\n"
                f"🏆 Выигрыш: {format_stars(current_win)}\n"
                f"💎 Чистая прибыль: {format_stars(current_win - game['bet'])}\n\n"
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
                f"✅ <b>Вы нашли 💎! Множитель увеличен до x{game['multiplier']:.2f}</b>\n\n"
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
    
    save_transaction(user_id, win, "game_win", 
                    f"Mines кэшаут x{game['multiplier']:.1f}", "mines")
    
    bot_stats["mines_games_played"] += 1
    
    mines_history.append({
        "multiplier": game["multiplier"],
        "player": user_id,
        "bet": game["bet"],
        "win": win,
        "timestamp": datetime.now().isoformat()
    })
    if len(mines_history) > MAX_HISTORY_ITEMS:
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
    """Выход из игры Mines"""
    user_id = callback.from_user.id
    
    if user_id in active_mines:
        del active_mines[user_id]
    
    await state.clear()
    await callback.message.edit_text(
        "❌ Вы вышли из игры.\n\n"
        "💰 Ваш баланс не изменился.\n\n"
        "🎮 Чтобы начать новую игру, нажмите «Игры».",
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
    
    if bot_settings["maintenance_mode"]:
        await message.answer("🔧 Бот на техническом обслуживании!", parse_mode=ParseMode.HTML)
        return
    
    await state.set_state(GameStates.dice_bet)
    
    dice_info = (
        f"🎲 <b>DICE — Угадай число!</b>\n\n"
        f"📋 <b>Правила игры:</b>\n"
        f"• Вы делаете ставку\n"
        f"• Предсказываете, выпадет число выше 50 или ниже 50\n"
        f"• Кубик бросается автоматически\n"
        f"• При правильном угадывании выигрыш x{bot_settings['dice_multiplier']}\n"
        f"• При неправильном — ставка сгорает\n\n"
        f"📊 <b>Текущая статистика:</b>\n"
        f"• Всего сыграно: {bot_stats['dice_games_played']} игр\n"
        f"• Процент побед: {len([h for h in dice_history if h.get('win', 0) > 0]) / len(dice_history) * 100 if dice_history else 0:.1f}%\n"
        f"• Последний результат: {'Выше 50' if dice_history[-1].get('result', 0) > 50 else 'Ниже 50'}" if dice_history else "• Нет данных\n\n"
        f"💡 <b>Совет:</b> Шанс выигрыша ~50%, не делайте слишком больших ставок!"
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
            f"📊 Минимальная ставка: {bot_settings['min_bet']} Stars\n"
            f"📊 Максимальная ставка: {bot_settings['max_bet']} Stars",
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
    
    if bet < bot_settings["min_bet"] or bet > bot_settings["max_bet"]:
        await callback.answer(
            f"❌ Ставка должна быть от {bot_settings['min_bet']} до {bot_settings['max_bet']} Stars!",
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
        f"🎯 Множитель при победе: x{bot_settings['dice_multiplier']}\n"
        f"💎 Потенциальный выигрыш: {format_stars(bet * bot_settings['dice_multiplier'])}\n\n"
        f"👇 <b>Выберите предсказание:</b>\n"
        f"⬆️ Выше 50 — выигрыш x{bot_settings['dice_multiplier']}\n"
        f"⬇️ Ниже 50 — выигрыш x{bot_settings['dice_multiplier']}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_dice_predict_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "dice_higher")
async def dice_higher(callback: CallbackQuery, state: FSMContext):
    """Предсказание выше 50"""
    await dice_play(callback, state, "higher")

@dp.callback_query(F.data == "dice_lower")
async def dice_lower(callback: CallbackQuery, state: FSMContext):
    """Предсказание ниже 50"""
    await dice_play(callback, state, "lower")

async def dice_play(callback: CallbackQuery, state: FSMContext, prediction: str):
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
    
    # Проверяем результат
    if (prediction == "higher" and dice_value > 50) or (prediction == "lower" and dice_value < 50):
        win = bet * bot_settings["dice_multiplier"]
        update_balance(user_id, win)
        
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["dice_games"] += 1
        stats["dice_wins"] += 1
        stats["total_won"] += win
        
        if bot_settings["dice_multiplier"] > stats["dice_best_multiplier"]:
            stats["dice_best_multiplier"] = bot_settings["dice_multiplier"]
        
        save_transaction(user_id, win, "game_win", f"Dice победа {dice_value}", "dice")
        
        result_text = f"🎉 <b>ВЫ УГАДАЛИ!</b> 🎉\n\nВыпало: <b>{dice_value}</b>\nВыигрыш: +{format_stars(win - bet)}"
        bot_stats["dice_games_played"] += 1
        
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
    
    if len(dice_history) > MAX_HISTORY_ITEMS:
        dice_history.pop(0)
    
    await state.clear()
    
    await callback.message.answer(
        f"🎲 <b>DICE — РЕЗУЛЬТАТ</b>\n\n"
        f"💰 Ваша ставка: {format_stars(bet)}\n"
        f"🎯 Ваше предсказание: {'Выше 50 ⬆️' if prediction == 'higher' else 'Ниже 50 ⬇️'}\n\n"
        f"{result_text}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}\n\n"
        f"🎮 Чтобы сыграть снова, нажмите «Игры» в меню.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "dice_roll")
async def dice_roll(callback: CallbackQuery):
    """Просто бросок кубика без ставки"""
    await callback.message.answer_dice(emoji="🎲")
    await callback.answer("🎲 Кубик брошен!")

# ===================== ИСТОРИЯ ИГР =====================
@dp.message(F.text == "📊 История игр")
async def games_history(message: Message):
    """История последних игр пользователя"""
    user_id = message.from_user.id
    
    # Получаем историю игр пользователя
    user_crash = [g for g in crash_history if g.get("player") == user_id][-10:]
    user_mines = [g for g in mines_history if g.get("player") == user_id][-10:]
    user_dice = [g for g in dice_history if g.get("player") == user_id][-10:]
    
    history_text = "📊 <b>ИСТОРИЯ ВАШИХ ИГР</b>\n\n"
    
    if user_crash:
        history_text += "<b>📈 CRASH:</b>\n"
        for game in user_crash:
            if "win" in game:
                profit = game.get("win", 0) - game["bet"]
                history_text += f"• {game['bet']:.0f}⭐️ → x{game['multiplier']:.2f} → {'+' + str(profit) + '⭐️' if profit > 0 else str(profit) + '⭐️'}\n"
            else:
                history_text += f"• {game['bet']:.0f}⭐️ → x{game['multiplier']:.2f} → ❌ Проигрыш\n"
        history_text += "\n"
    
    if user_mines:
        history_text += "<b>💣 MINES:</b>\n"
        for game in user_mines:
            if game.get("win"):
                profit = game["win"] - game["bet"]
                history_text += f"• {game['bet']:.0f}⭐️ → x{game['multiplier']:.1f} → +{profit:.0f}⭐️\n"
            else:
                history_text += f"• {game['bet']:.0f}⭐️ → ❌ Проигрыш\n"
        history_text += "\n"
    
    if user_dice:
        history_text += "<b>🎲 DICE:</b>\n"
        for game in user_dice:
            if game.get("win"):
                profit = game["win"] - game["bet"]
                history_text += f"• {game['bet']:.0f}⭐️ → {game['result']} → {'Выше' if game['prediction'] == 'higher' else 'Ниже'} → +{profit:.0f}⭐️\n"
            else:
                history_text += f"• {game['bet']:.0f}⭐️ → {game['result']} → ❌ Проигрыш\n"
        history_text += "\n"
    
    if not user_crash and not user_mines and not user_dice:
        history_text += "📭 У вас пока нет сыгранных игр.\n\n💡 Начните играть, чтобы видеть историю!"
    
    # Подсчёт общей статистики
    total_games = len(user_crash) + len(user_mines) + len(user_dice)
    total_wins = sum(1 for g in user_crash if "win" in g) + sum(1 for g in user_mines if g.get("win")) + sum(1 for g in user_dice if g.get("win"))
    total_profit = sum((g.get("win", 0) - g["bet"]) for g in user_crash if "win" in g) + sum((g["win"] - g["bet"]) for g in user_mines if g.get("win")) + sum((g["win"] - g["bet"]) for g in user_dice if g.get("win"))
    
    history_text += f"\n📊 <b>Общая статистика за период:</b>\n"
    history_text += f"• Сыграно: {total_games}\n"
    history_text += f"• Побед: {total_wins}\n"
    history_text += f"• Профит: {format_stars(total_profit)}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📈 Детальная статистика", callback_data="detailed_stats")]
    ])
    
    await message.answer(history_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

# ===================== ПРОФАЙЛ: ДЕТАЛЬНАЯ СТАТИСТИКА =====================
@dp.callback_query(F.data == "profile_transactions")
async def profile_transactions(callback: CallbackQuery):
    """История транзакций пользователя"""
    user_id = callback.from_user.id
    user_txs = transactions.get(user_id, [])[-20:]
    
    if not user_txs:
        await callback.message.edit_text(
            "📭 У вас пока нет транзакций.\n\n💡 Пополните баланс или сыграйте в игры!",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад в профиль", callback_data="profile_back")]
            ])
        )
        await callback.answer()
        return
    
    txs_text = "📜 <b>ИСТОРИЯ ТРАНЗАКЦИЙ</b>\n\n"
    for tx in reversed(user_txs):
        amount = tx["amount"]
        amount_str = f"+{amount:.0f}⭐️" if amount > 0 else f"{amount:.0f}⭐️"
        txs_text += f"• {tx['type'].upper()}: {amount_str} — {tx['details'][:30]}\n"
        txs_text += f"  └ {tx['timestamp'][:19]}\n"
    
    await callback.message.edit_text(
        txs_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад в профиль", callback_data="profile_back")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "profile_games")
async def profile_games(callback: CallbackQuery):
    """Детальная статистика игр пользователя"""
    user_id = callback.from_user.id
    stats = get_user_stats(user_id)
    
    win_rate = 0
    if stats['games_played'] > 0:
        win_rate = (stats['games_won'] / stats['games_played']) * 100
    
    games_text = (
        f"🎮 <b>ДЕТАЛЬНАЯ СТАТИСТИКА ИГР</b>\n\n"
        f"<b>📈 CRASH:</b>\n"
        f"├ Сыграно: {stats['crash_games']}\n"
        f"├ Побед: {stats['crash_wins']}\n"
        f"├ Винрейт: {(stats['crash_wins'] / max(stats['crash_games'], 1) * 100):.1f}%\n"
        f"└ Лучший множитель: x{stats['crash_best_multiplier']:.2f}\n\n"
        f"<b>💣 MINES:</b>\n"
        f"├ Сыграно: {stats['mines_games']}\n"
        f"├ Побед: {stats['mines_wins']}\n"
        f"├ Винрейт: {(stats['mines_wins'] / max(stats['mines_games'], 1) * 100):.1f}%\n"
        f"└ Лучший множитель: x{stats['mines_best_multiplier']:.2f}\n\n"
        f"<b>🎲 DICE:</b>\n"
        f"├ Сыграно: {stats['dice_games']}\n"
        f"├ Побед: {stats['dice_wins']}\n"
        f"└ Винрейт: {(stats['dice_wins'] / max(stats['dice_games'], 1) * 100):.1f}%\n\n"
        f"<b>📊 ОБЩАЯ СТАТИСТИКА:</b>\n"
        f"├ Сыграно: {stats['games_played']}\n"
        f"├ Побед: {stats['games_won']}\n"
        f"├ Винрейт: {win_rate:.1f}%\n"
        f"├ Выиграно: {format_stars(stats['total_won'])}\n"
        f"├ Проиграно: {format_stars(stats['total_lost'])}\n"
        f"└ Чистая прибыль: {format_stars(stats['total_won'] - stats['total_lost'])}"
    )
    
    await callback.message.edit_text(
        games_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад в профиль", callback_data="profile_back")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "profile_back")
async def profile_back(callback: CallbackQuery):
    """Возврат в профиль"""
    user_id = callback.from_user.id
    stats = get_user_stats(user_id)
    balance = get_user_balance(user_id)
    
    win_rate = 0
    if stats['games_played'] > 0:
        win_rate = (stats['games_won'] / stats['games_played']) * 100
    
    total_profit = stats['total_won'] - stats['total_lost']
    
    profile_text = (
        f"👤 <b>Профиль игрока</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"👤 Username: @{callback.from_user.username or 'не установлен'}\n"
        f"📅 Регистрация: {users_join_date.get(user_id, 'неизвестно')}\n"
        f"✅ Верификация: {'✅ Верифицирован' if users_verify.get(user_id, False) else '❌ Не верифицирован'}\n"
        f"🔐 2FA: {'✅ Включена' if users_2fa_enabled.get(user_id, False) else '❌ Выключена'}\n"
        f"🕐 Последний визит: {users_last_seen.get(user_id, 'неизвестно')[:19]}\n\n"
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
        f"💳 <b>Финансы:</b>\n"
        f"├ 💰 Пополнений: {stats['total_deposits']} ({format_stars(stats['total_deposit_amount'])})\n"
        f"├ 💸 Выводов: {stats['total_withdrawals']} ({format_stars(stats['total_withdrawal_amount'])})\n"
        f"├ 👥 Рефералов: {stats['referral_count']}\n"
        f"├ 🎁 Реферальный доход: {format_stars(stats['referral_earned'])}\n"
        f"├ 🎁 Бонусов получено: {stats['daily_bonus_count']}\n"
        f"└ 📅 Текущий стрик: {stats['daily_bonus_streak']} дней"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 История транзакций", callback_data="profile_transactions"),
         InlineKeyboardButton(text="🎮 История игр", callback_data="profile_games")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(profile_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()

# ===================== ДЕТАЛЬНАЯ СТАТИСТИКА =====================
@dp.callback_query(F.data == "detailed_stats")
async def detailed_stats(callback: CallbackQuery):
    """Детальная статистика"""
    user_id = callback.from_user.id
    stats = get_user_stats(user_id)
    
    win_rate = 0
    if stats['games_played'] > 0:
        win_rate = (stats['games_won'] / stats['games_played']) * 100
    
    stats_text = (
        f"📊 <b>ДЕТАЛЬНАЯ СТАТИСТИКА</b>\n\n"
        f"<b>📈 CRASH:</b>\n"
        f"├ Сыграно: {stats['crash_games']}\n"
        f"├ Побед: {stats['crash_wins']}\n"
        f"├ Винрейт: {(stats['crash_wins'] / max(stats['crash_games'], 1) * 100):.1f}%\n"
        f"├ Всего выиграно: {format_stars(sum(g.get('win', 0) for g in crash_history if g.get('player') == user_id))}\n"
        f"└ Лучший множитель: x{stats['crash_best_multiplier']:.2f}\n\n"
        f"<b>💣 MINES:</b>\n"
        f"├ Сыграно: {stats['mines_games']}\n"
        f"├ Побед: {stats['mines_wins']}\n"
        f"├ Винрейт: {(stats['mines_wins'] / max(stats['mines_games'], 1) * 100):.1f}%\n"
        f"├ Всего выиграно: {format_stars(sum(g.get('win', 0) for g in mines_history if g.get('player') == user_id))}\n"
        f"└ Лучший множитель: x{stats['mines_best_multiplier']:.2f}\n\n"
        f"<b>🎲 DICE:</b>\n"
        f"├ Сыграно: {stats['dice_games']}\n"
        f"├ Побед: {stats['dice_wins']}\n"
        f"├ Винрейт: {(stats['dice_wins'] / max(stats['dice_games'], 1) * 100):.1f}%\n"
        f"└ Всего выиграно: {format_stars(sum(g.get('win', 0) for g in dice_history if g.get('player') == user_id))}\n\n"
        f"<b>📊 ОБЩАЯ СТАТИСТИКА:</b>\n"
        f"├ Сыграно: {stats['games_played']}\n"
        f"├ Побед: {stats['games_won']}\n"
        f"├ Винрейт: {win_rate:.1f}%\n"
        f"├ Выиграно: {format_stars(stats['total_won'])}\n"
        f"├ Проиграно: {format_stars(stats['total_lost'])}\n"
        f"└ Чистая прибыль: {format_stars(stats['total_won'] - stats['total_lost'])}"
    )
    
    await callback.message.edit_text(
        stats_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_games")]
        ])
    )
    await callback.answer()

# ===================== ТОП КНОПКИ =====================
@dp.callback_query(F.data == "top_balance")
async def top_balance(callback: CallbackQuery):
    """Топ по балансу"""
    sorted_by_balance = sorted(users_balance.items(), key=lambda x: x[1], reverse=True)[:15]
    
    top_text = "🏆 <b>ТОП-15 ПО БАЛАНСУ</b>\n\n"
    for idx, (uid, bal) in enumerate(sorted_by_balance, 1):
        if users_ban.get(uid, False):
            continue
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
        uname = users_username.get(uid, str(uid))
        name = f"@{uname}" if uname else str(uid)
        top_text += f"{medal} {name} — {bal:.2f} ⭐️\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 По балансу", callback_data="top_balance"),
         InlineKeyboardButton(text="🏆 По победам", callback_data="top_wins"),
         InlineKeyboardButton(text="💎 По выигрышам", callback_data="top_won")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(top_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "top_wins")
async def top_wins(callback: CallbackQuery):
    """Топ по победам"""
    sorted_by_wins = sorted(users_stats.items(), 
                           key=lambda x: x[1].get("games_won", 0), 
                           reverse=True)[:15]
    
    top_text = "🏆 <b>ТОП-15 ПО ПОБЕДАМ</b>\n\n"
    for idx, (uid, stats) in enumerate(sorted_by_wins, 1):
        if users_ban.get(uid, False):
            continue
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
        uname = users_username.get(uid, str(uid))
        name = f"@{uname}" if uname else str(uid)
        wins = stats.get("games_won", 0)
        top_text += f"{medal} {name} — {wins} 🏆\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 По балансу", callback_data="top_balance"),
         InlineKeyboardButton(text="🏆 По победам", callback_data="top_wins"),
         InlineKeyboardButton(text="💎 По выигрышам", callback_data="top_won")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(top_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "top_won")
async def top_won(callback: CallbackQuery):
    """Топ по выигрышам"""
    sorted_by_won = sorted(users_stats.items(),
                          key=lambda x: x[1].get("total_won", 0),
                          reverse=True)[:15]
    
    top_text = "🏆 <b>ТОП-15 ПО ВЫИГРЫШАМ</b>\n\n"
    for idx, (uid, stats) in enumerate(sorted_by_won, 1):
        if users_ban.get(uid, False):
            continue
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
        uname = users_username.get(uid, str(uid))
        name = f"@{uname}" if uname else str(uid)
        won = stats.get("total_won", 0)
        top_text += f"{medal} {name} — {format_stars(won)}\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 По балансу", callback_data="top_balance"),
         InlineKeyboardButton(text="🏆 По победам", callback_data="top_wins"),
         InlineKeyboardButton(text="💎 По выигрышам", callback_data="top_won")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(top_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()

# ===================== РЕФЕРАЛЬНАЯ СТАТИСТИКА =====================
@dp.callback_query(F.data == "referral_stats")
async def referral_stats(callback: CallbackQuery):
    """Статистика рефералов"""
    user_id = callback.from_user.id
    referrals = users_referrals.get(user_id, [])
    
    if not referrals:
        await callback.message.edit_text(
            "👥 <b>Статистика рефералов</b>\n\n"
            "У вас пока нет приглашённых пользователей.\n\n"
            "💡 Поделитесь своей реферальной ссылкой с друзьями!\n"
            "📢 За каждого приглашённого вы получаете бонусы и % от пополнений.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
            ])
        )
        await callback.answer()
        return
    
    ref_text = "👥 <b>СПИСОК РЕФЕРАЛОВ</b>\n\n"
    for ref_id in referrals:
        uname = users_username.get(ref_id, str(ref_id))
        balance = get_user_balance(ref_id)
        stats = get_user_stats(ref_id)
        ref_text += f"• @{uname} — {format_stars(balance)} (сыграл {stats['games_played']} игр)\n"
    
    total_earned = sum(stats.get("referral_earned", 0) for stats in users_stats.values() if stats.get("referral_count", 0) > 0)
    
    ref_text += f"\n📊 <b>Общая статистика:</b>\n"
    ref_text += f"├ Приглашено: {len(referrals)}\n"
    ref_text += f"└ Заработано: {format_stars(total_earned)}"
    
    await callback.message.edit_text(
        ref_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
        ])
    )
    await callback.answer()

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
        "• ⚙️ Настройки игр — изменение параметров игр\n"
        "• 🎮 Управление играми — управление активными играми\n"
        "• 🎁 Промокоды — создание и управление промокодами\n"
        "• 💾 Резервное копирование — сохранение данных\n"
        "• 📈 Экспорт данных — выгрузка в JSON\n"
        "• 🔧 Системные настройки — общие настройки\n"
        "• 📢 Объявления — создание объявлений\n"
        "• 🎁 Глобальный бонус — выдача бонуса всем\n"
        "• 📊 Отчёт по прибыли — финансовая отчётность\n\n"
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
    
    stats_text = (
        f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
        f"<b>👥 Пользователи:</b>\n"
        f"├ Всего: {bot_stats['total_users']}\n"
        f"├ Активны сегодня: {bot_stats['active_today']}\n"
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
        f"├ CRASH: {bot_stats['crash_games_played']} игр\n"
        f"├ MINES: {bot_stats['mines_games_played']} игр\n"
        f"└ DICE: {bot_stats['dice_games_played']} игр\n\n"
        f"<b>📊 Средние показатели:</b>\n"
        f"├ Средняя ставка: {format_stars(bot_stats['total_wagered'] / max(bot_stats['total_bets'], 1))}\n"
        f"├ Средний выигрыш: {format_stars(bot_stats['total_paid'] / max(bot_stats['total_bets'], 1))}\n"
        f"└ RTP: {(bot_stats['total_paid'] / max(bot_stats['total_wagered'], 1) * 100):.1f}%\n\n"
        f"<b>🕐 Система:</b>\n"
        f"├ Время работы: {format_time(uptime.seconds)}\n"
        f"├ Последний бэкап: {bot_stats['last_backup'][:19] if bot_stats['last_backup'] else 'Не было'}\n"
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
    
    # Показываем информацию о пользователе
    balance = get_user_balance(user_id)
    stats = get_user_stats(user_id)
    
    info_text = (
        f"👤 <b>Информация о пользователе</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"👤 Username: @{input_text}\n"
        f"💰 Баланс: {format_stars(balance)}\n"
        f"🎮 Сыграно: {stats['games_played']} игр\n"
        f"🏆 Побед: {stats['games_won']}\n"
        f"💎 Выиграно: {format_stars(stats['total_won'])}\n"
        f"👥 Рефералов: {stats['referral_count']}\n\n"
        f"💰 <b>Введите сумму изменения:</b>\n"
        f"• <b>+100</b> — добавить 100 Stars\n"
        f"• <b>-50</b> — снять 50 Stars\n\n"
        f"<i>Для отмены отправьте /cancel</i>"
    )
    
    await message.answer(info_text, parse_mode=ParseMode.HTML)

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
        
        # Сохраняем в заметки админа
        note = f"{datetime.now().strftime('%Y-%m-%d %H:%M')} - Изменение баланса на {amount} Stars от {message.from_user.username}"
        users_admin_notes[target_user] = users_admin_notes.get(target_user, "") + "\n" + note
        
        # Уведомляем пользователя
        try:
            await bot.send_message(
                target_user,
                f"👑 <b>Администратор изменил ваш баланс!</b>\n\n"
                f"{'+' if amount > 0 else ''}{format_stars(amount)}\n"
                f"💰 Новый баланс: {format_stars(new_balance)}\n\n"
                f"💡 Изменение: {note}",
                parse_mode=ParseMode.HTML
            )
        except:
            pass
        
        # Сохраняем транзакцию
        save_transaction(target_user, amount, "admin_change", 
                        f"Админ: {amount} Stars от {message.from_user.username}", "admin")
        
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
        "📊 Будет отправлено: {} пользователей\n\n"
        "<i>Для отмены отправьте /cancel</i>".format(len([u for u in users_balance.keys() if not users_ban.get(u, False)])),
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
        users_list.append(f"{banned}{verified} @{uname or str(uid)} — {balance:.2f}⭐️")
    
    # Пагинация
    page_size = 20
    total_pages = (len(users_list) + page_size - 1) // page_size
    page = 0
    
    text = "👥 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ</b>\n\n"
    text += "\n".join(users_list[page * page_size:(page + 1) * page_size])
    
    if len(users_list) > page_size:
        text += f"\n\n📄 Страница {page + 1}/{total_pages}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    if page > 0:
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="◀️ Предыдущая", callback_data="users_prev")])
    if page < total_pages - 1:
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="Следующая ▶️", callback_data="users_next")])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="users_refresh")])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

# ===================== АДМИН: БАН/РАЗБАН =====================
@dp.message(F.text == "🔨 Бан/Разбан")
async def admin_ban_start(message: Message, state: FSMContext):
    """Начало бана пользователя"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await state.set_state(GameStates.admin_ban_user)
    await message.answer(
        "🔨 <b>БАН/РАЗБАН ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введите username (без @) или ID пользователя:\n"
        "Пример: <code>hjklgf1</code> или <code>123456789</code>\n\n"
        "<b>Действия:</b>\n"
        "• Если пользователь не забанен — будет забанен\n"
        "• Если пользователь забанен — будет разбанен\n\n"
        "<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(GameStates.admin_ban_user)
async def admin_ban_user(message: Message, state: FSMContext):
    """Бан/разбан пользователя"""
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
        # Разбан
        users_ban[user_id] = False
        users_ban_reason[user_id] = ""
        
        # Уведомляем пользователя
        try:
            await bot.send_message(
                user_id,
                f"✅ <b>Ваш аккаунт разблокирован!</b>\n\n"
                f"Вы снова можете пользоваться ботом.\n"
                f"💰 Ваш баланс сохранён: {format_stars(get_user_balance(user_id))}",
                parse_mode=ParseMode.HTML
            )
        except:
            pass
        
        await state.clear()
        await message.answer(
            f"✅ <b>Пользователь разбанен!</b>\n\n"
            f"👤 @{input_text}\n"
            f"✅ Статус: Активен",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_main_keyboard()
        )
    else:
        # Бан
        users_ban[user_id] = True
        users_ban_reason[user_id] = "Нарушение правил пользовательского соглашения"
        
        # Уведомляем пользователя
        try:
            await bot.send_message(
                user_id,
                f"🚫 <b>Ваш аккаунт заблокирован!</b>\n\n"
                f"Причина: {users_ban_reason[user_id]}\n\n"
                f"Для получения информации обратитесь к администратору: {bot_settings['support_link']}",
                parse_mode=ParseMode.HTML
            )
        except:
            pass
        
        await state.clear()
        await message.answer(
            f"✅ <b>Пользователь забанен!</b>\n\n"
            f"👤 @{input_text}\n"
            f"🚫 Статус: Забанен\n"
            f"📝 Причина: {users_ban_reason[user_id]}",
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
        "<b>Действие:</b>\n"
        "• Если пользователь не верифицирован — будет верифицирован\n"
        "• Если пользователь верифицирован — будет деверифицирован\n\n"
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
            f"Статус: {'Верифицирован' if users_verify[user_id] else 'Не верифицирован'}\n"
            f"Верифицированные пользователи получают приоритетную поддержку.",
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

# ===================== АДМИН: НАСТРОЙКИ ИГР =====================
@dp.message(F.text == "⚙️ Настройки игр")
async def admin_game_settings(message: Message):
    """Настройки игр"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    settings_text = (
        f"⚙️ <b>НАСТРОЙКИ ИГР</b>\n\n"
        f"<b>📈 CRASH:</b>\n"
        f"├ Макс. множитель: x{bot_settings['crash_max_multiplier']}\n"
        f"└ House Edge: {(1 - bot_settings['crash_house_edge']) * 100}%\n\n"
        f"<b>💣 MINES:</b>\n"
        f"├ Размер поля: {bot_settings['mines_board_size']}x{bot_settings['mines_board_size']}\n"
        f"└ Количество мин: {bot_settings['mines_mines_count']}\n\n"
        f"<b>🎲 DICE:</b>\n"
        f"└ Множитель: x{bot_settings['dice_multiplier']}\n\n"
        f"<b>💰 Общие:</b>\n"
        f"├ Мин. ставка: {format_stars(bot_settings['min_bet'])}\n"
        f"└ Макс. ставка: {format_stars(bot_settings['max_bet'])}\n\n"
        f"💡 <b>Для изменения используйте команды:</b>\n"
        f"• /set_crash_multiplier <число>\n"
        f"• /set_mines_size <число>\n"
        f"• /set_mines_count <число>\n"
        f"• /set_dice_multiplier <число>\n"
        f"• /set_min_bet <сумма>\n"
        f"• /set_max_bet <сумма>"
    )
    
    await message.answer(settings_text, parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())

# ===================== АДМИН: УПРАВЛЕНИЕ ИГРАМИ =====================
@dp.message(F.text == "🎮 Управление играми")
async def admin_manage_games(message: Message):
    """Управление играми"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    active_crash_count = len(active_crash)
    active_mines_count = len(active_mines)
    active_dice_count = len(active_dice)
    
    games_text = (
        f"🎮 <b>УПРАВЛЕНИЕ ИГРАМИ</b>\n\n"
        f"<b>Активные игры:</b>\n"
        f"├ 📈 CRASH: {active_crash_count} игр\n"
        f"├ 💣 MINES: {active_mines_count} игр\n"
        f"└ 🎲 DICE: {active_dice_count} игр\n\n"
        f"<b>Действия:</b>\n"
        f"• /clear_crash — завершить все игры Crash\n"
        f"• /clear_mines — завершить все игры Mines\n"
        f"• /clear_dice — завершить все игры Dice\n"
        f"• /clear_all_games — завершить ВСЕ игры\n\n"
        f"<b>Статистика игр за сегодня:</b>\n"
        f"├ CRASH: {len([g for g in crash_history if g.get('timestamp', '').startswith(datetime.now().strftime('%Y-%m-%d'))])} игр\n"
        f"├ MINES: {len([g for g in mines_history if g.get('timestamp', '').startswith(datetime.now().strftime('%Y-%m-%d'))])} игр\n"
        f"└ DICE: {len([g for g in dice_history if g.get('timestamp', '').startswith(datetime.now().strftime('%Y-%m-%d'))])} игр"
    )
    
    await message.answer(games_text, parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())

# ===================== АДМИН: ПРОМОКОДЫ =====================
@dp.message(F.text == "🎁 Промокоды")
async def admin_promo_codes(message: Message, state: FSMContext):
    """Управление промокодами"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await state.set_state(GameStates.admin_promo_create)
    await message.answer(
        "🎁 <b>УПРАВЛЕНИЕ ПРОМОКОДАМИ</b>\n\n"
        f"<b>Активные промокоды:</b>\n"
        + "\n".join([f"• {code} — {data['amount']}⭐️ ({data['uses_left']} использований)" for code, data in promo_codes.items()]) if promo_codes else "• Нет активных промокодов\n\n"
        f"\n<b>Действия:</b>\n"
        f"• Введите сумму для создания промокода\n"
        f"• Или отправьте /cancel для отмены\n\n"
        f"<i>Пример: 100 — создаст промокод на 100 Stars</i>",
        parse_mode=ParseMode.HTML
    )

@dp.message(GameStates.admin_promo_create)
async def admin_promo_create_amount(message: Message, state: FSMContext):
    """Создание промокода"""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Операция отменена.", reply_markup=get_admin_main_keyboard())
        return
    
    try:
        amount = float(message.text.strip())
        if amount < 1:
            await message.answer("❌ Сумма должна быть больше 0!")
            return
        
        code = generate_promo_code()
        promo_codes[code] = {
            "amount": amount,
            "uses_left": 1,
            "created_by": message.from_user.id,
            "created_at": datetime.now().isoformat()
        }
        
        await state.clear()
        await message.answer(
            f"✅ <b>Промокод создан!</b>\n\n"
            f"📋 Код: <code>{code}</code>\n"
            f"💰 Сумма: {format_stars(amount)}\n"
            f"📊 Использований: 1\n\n"
            f"💡 Пользователи могут активировать промокод командой:\n"
            f"<code>/redeem {code}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_main_keyboard()
        )
    except ValueError:
        await message.answer("❌ Введите число!")

@dp.message(Command("redeem"))
async def redeem_promo(message: Message):
    """Активация промокода"""
    user_id = message.from_user.id
    
    if users_ban.get(user_id, False):
        await message.answer("❌ Ваш аккаунт заблокирован!", parse_mode=ParseMode.HTML)
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "❌ <b>Использование промокода</b>\n\n"
            "Отправьте: <code>/redeem КОД</code>\n"
            "Пример: <code>/redeem ABC123</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    code = args[1].upper()
    
    if code not in promo_codes:
        await message.answer("❌ Неверный промокод!", parse_mode=ParseMode.HTML)
        return
    
    promo = promo_codes[code]
    
    if promo["uses_left"] <= 0:
        await message.answer("❌ Промокод уже использован!", parse_mode=ParseMode.HTML)
        del promo_codes[code]
        return
    
    # Начисляем бонус
    amount = promo["amount"]
    update_balance(user_id, amount)
    save_transaction(user_id, amount, "promo", f"Активация промокода {code}")
    
    # Обновляем использование
    promo["uses_left"] -= 1
    if promo["uses_left"] <= 0:
        del promo_codes[code]
    
    await message.answer(
        f"✅ <b>Промокод активирован!</b>\n\n"
        f"+{format_stars(amount)}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML
    )

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
        f"📁 Файл: {filename}\n"
        f"📊 Размер: {os.path.getsize(filename) / 1024:.1f} KB\n"
        f"🕐 Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"📁 Файл сохранён на сервере.\n"
        f"💡 Для восстановления используйте /restore",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_main_keyboard()
    )

@dp.message(Command("restore"))
async def admin_restore(message: Message):
    """Восстановление из бэкапа"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) < 2:
        # Показываем список доступных бэкапов
        backups = sorted([f for f in os.listdir() if f.startswith("backup_") and f.endswith(".json")])
        if not backups:
            await message.answer("❌ Нет доступных резервных копий!")
            return
        
        text = "📁 <b>ДОСТУПНЫЕ БЭКАПЫ</b>\n\n"
        for b in backups[-10:]:
            size = os.path.getsize(b) / 1024
            text += f"• {b} — {size:.1f} KB\n"
        text += f"\n💡 Для восстановления: <code>/restore имя_файла</code>"
        await message.answer(text, parse_mode=ParseMode.HTML)
        return
    
    filename = args[1]
    if not os.path.exists(filename):
        await message.answer("❌ Файл не найден!")
        return
    
    if load_backup(filename):
        await message.answer(
            f"✅ <b>Данные восстановлены!</b>\n\n"
            f"📁 Файл: {filename}\n"
            f"🕐 Восстановление: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_main_keyboard()
        )
    else:
        await message.answer("❌ Ошибка восстановления данных!")

# ===================== АДМИН: ЭКСПОРТ ДАННЫХ =====================
@dp.message(F.text == "📈 Экспорт данных")
async def admin_export(message: Message):
    """Экспорт данных в JSON"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    export_data = {
        "users": {
            uid: {
                "balance": bal,
                "username": users_username.get(uid),
                "join_date": users_join_date.get(uid),
                "verify": users_verify.get(uid, False),
                "stats": get_user_stats(uid)
            } for uid, bal in users_balance.items()
        },
        "promo_codes": promo_codes,
        "bot_stats": bot_stats,
        "export_date": datetime.now().isoformat()
    }
    
    filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    
    await message.answer_document(
        FSInputFile(filename),
        caption=f"📊 Экспорт данных от {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"👥 Пользователей: {len(export_data['users'])}\n"
                f"💰 Общий баланс: {format_stars(sum(u['balance'] for u in export_data['users'].values()))}",
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
    
    settings_text = (
        f"🔧 <b>СИСТЕМНЫЕ НАСТРОЙКИ</b>\n\n"
        f"<b>Текущие настройки:</b>\n"
        f"├ Режим обслуживания: {'Вкл' if bot_settings['maintenance_mode'] else 'Выкл'}\n"
        f"├ Ежедневный бонус: {'Вкл' if bot_settings['daily_bonus_enabled'] else 'Выкл'}\n"
        f"├ Реферальный процент: {bot_settings['referral_percent']}%\n"
        f"├ Чат: {bot_settings['chat_link']}\n"
        f"├ Канал: {bot_settings['channel_link']}\n"
        f"└ Поддержка: {bot_settings['support_link']}\n\n"
        f"<b>Команды для изменения:</b>\n"
        f"• /set_maintenance <вкл/выкл>\n"
        f"• /set_daily_bonus <вкл/выкл>\n"
        f"• /set_referral_percent <процент>\n"
        f"• /set_chat_link <ссылка>\n"
        f"• /set_channel_link <ссылка>\n"
        f"• /set_support_link <ссылка>"
    )
    
    await message.answer(settings_text, parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())

# ===================== АДМИН: ОБЪЯВЛЕНИЯ =====================
@dp.message(F.text == "📢 Объявления")
async def admin_announcement(message: Message, state: FSMContext):
    """Создание объявления"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await state.set_state(GameStates.admin_announcement)
    await message.answer(
        "📢 <b>СОЗДАНИЕ ОБЪЯВЛЕНИЯ</b>\n\n"
        "Введите текст объявления для всех пользователей.\n\n"
        "<b>Поддерживается:</b>\n"
        "• Текст\n"
        "• Форматирование HTML\n\n"
        "<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(GameStates.admin_announcement)
async def admin_announcement_text(message: Message, state: FSMContext):
    """Отправка объявления"""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Операция отменена.", reply_markup=get_admin_main_keyboard())
        return
    
    announcement_text = message.text
    
    # Сохраняем объявление
    announcements.append({
        "text": announcement_text,
        "created_by": message.from_user.id,
        "created_at": datetime.now().isoformat()
    })
    
    # Отправляем всем пользователям
    success = 0
    for user_id in users_balance.keys():
        if users_ban.get(user_id, False):
            continue
        try:
            await bot.send_message(
                user_id,
                f"📢 <b>ОБЪЯВЛЕНИЕ</b>\n\n{announcement_text}\n\n"
                f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                parse_mode=ParseMode.HTML
            )
            success += 1
        except:
            pass
        await asyncio.sleep(0.05)
    
    await state.clear()
    await message.answer(
        f"✅ <b>Объявление отправлено!</b>\n\n"
        f"📨 Доставлено: {success}\n"
        f"📊 Всего пользователей: {len(users_balance)}\n\n"
        f"📝 Текст:\n{announcement_text}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_main_keyboard()
    )

# ===================== АДМИН: ГЛОБАЛЬНЫЙ БОНУС =====================
@dp.message(F.text == "🎁 Глобальный бонус")
async def admin_global_bonus(message: Message, state: FSMContext):
    """Выдача бонуса всем пользователям"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await state.set_state(GameStates.admin_global_bonus_amount)
    await message.answer(
        "🎁 <b>ГЛОБАЛЬНЫЙ БОНУС</b>\n\n"
        "Введите сумму бонуса для всех пользователей:\n"
        "💰 Минимальная сумма: 1 Star\n"
        "💰 Максимальная сумма: 1000 Stars\n\n"
        "<i>Бонус будет выдан всем активным пользователям!</i>\n"
        "<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(GameStates.admin_global_bonus_amount)
async def admin_global_bonus_send(message: Message, state: FSMContext):
    """Отправка глобального бонуса"""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Операция отменена.", reply_markup=get_admin_main_keyboard())
        return
    
    try:
        amount = float(message.text.strip())
        if amount < 1:
            await message.answer("❌ Сумма должна быть больше 0!")
            return
        if amount > 1000:
            await message.answer("❌ Сумма не должна превышать 1000 Stars!")
            return
    except ValueError:
        await message.answer("❌ Введите число!")
        return
    
    success = 0
    for user_id in users_balance.keys():
        if users_ban.get(user_id, False):
            continue
        update_balance(user_id, amount)
        save_transaction(user_id, amount, "global_bonus", f"Глобальный бонус от администратора")
        
        try:
            await bot.send_message(
                user_id,
                f"🎁 <b>ГЛОБАЛЬНЫЙ БОНУС!</b>\n\n"
                f"+{format_stars(amount)}\n"
                f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}\n\n"
                f"💡 Спасибо, что играете с нами!",
                parse_mode=ParseMode.HTML
            )
            success += 1
        except:
            pass
        await asyncio.sleep(0.05)
    
    await state.clear()
    await message.answer(
        f"✅ <b>Глобальный бонус выдан!</b>\n\n"
        f"💰 Сумма: {format_stars(amount)}\n"
        f"📨 Получили: {success}\n"
        f"💸 Всего выплачено: {format_stars(amount * success)}\n"
        f"📊 Всего пользователей: {len(users_balance)}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_main_keyboard()
    )

# ===================== АДМИН: ОТЧЁТ ПО ПРИБЫЛИ =====================
@dp.message(F.text == "📊 Отчёт по прибыли")
async def admin_profit_report(message: Message):
    """Отчёт по прибыли"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    # Прибыль за сегодня
    today = datetime.now().date().isoformat()
    today_bets = sum(1 for t in transactions.values() for tx in t if tx.get("timestamp", "").startswith(today) and tx["type"] == "bet")
    today_wagered = sum(tx["amount"] for t in transactions.values() for tx in t if tx.get("timestamp", "").startswith(today) and tx["type"] == "bet")
    today_paid = sum(tx["amount"] for t in transactions.values() for tx in t if tx.get("timestamp", "").startswith(today) and tx["type"] == "game_win")
    today_profit = today_wagered - today_paid
    
    # Прибыль за неделю
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    week_bets = sum(1 for t in transactions.values() for tx in t if tx.get("timestamp", "") > week_ago and tx["type"] == "bet")
    week_wagered = sum(tx["amount"] for t in transactions.values() for tx in t if tx.get("timestamp", "") > week_ago and tx["type"] == "bet")
    week_paid = sum(tx["amount"] for t in transactions.values() for tx in t if tx.get("timestamp", "") > week_ago and tx["type"] == "game_win")
    week_profit = week_wagered - week_paid
    
    # Прибыль за месяц
    month_ago = (datetime.now() - timedelta(days=30)).isoformat()
    month_bets = sum(1 for t in transactions.values() for tx in t if tx.get("timestamp", "") > month_ago and tx["type"] == "bet")
    month_wagered = sum(tx["amount"] for t in transactions.values() for tx in t if tx.get("timestamp", "") > month_ago and tx["type"] == "bet")
    month_paid = sum(tx["amount"] for t in transactions.values() for tx in t if tx.get("timestamp", "") > month_ago and tx["type"] == "game_win")
    month_profit = month_wagered - month_paid
    
    report_text = (
        f"📊 <b>ОТЧЁТ ПО ПРИБЫЛИ</b>\n\n"
        f"<b>📈 ЗА СЕГОДНЯ:</b>\n"
        f"├ Ставок: {today_bets}\n"
        f"├ Объём ставок: {format_stars(today_wagered)}\n"
        f"├ Выплачено: {format_stars(today_paid)}\n"
        f"└ Прибыль: {format_stars(today_profit)}\n\n"
        f"<b>📊 ЗА НЕДЕЛЮ:</b>\n"
        f"├ Ставок: {week_bets}\n"
        f"├ Объём ставок: {format_stars(week_wagered)}\n"
        f"├ Выплачено: {format_stars(week_paid)}\n"
        f"└ Прибыль: {format_stars(week_profit)}\n\n"
        f"<b>📉 ЗА МЕСЯЦ:</b>\n"
        f"├ Ставок: {month_bets}\n"
        f"├ Объём ставок: {format_stars(month_wagered)}\n"
        f"├ Выплачено: {format_stars(month_paid)}\n"
        f"└ Прибыль: {format_stars(month_profit)}\n\n"
        f"<b>📊 ОБЩАЯ СТАТИСТИКА:</b>\n"
        f"├ Всего ставок: {bot_stats['total_bets']}\n"
        f"├ Объём ставок: {format_stars(bot_stats['total_wagered'])}\n"
        f"├ Выплачено: {format_stars(bot_stats['total_paid'])}\n"
        f"├ Общая прибыль: {format_stars(bot_stats['total_profit'])}\n"
        f"└ RTP: {(bot_stats['total_paid'] / max(bot_stats['total_wagered'], 1) * 100):.1f}%"
    )
    
    await message.answer(report_text, parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())

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

@dp.callback_query(F.data == "admin_back")
async def admin_back_callback(callback: CallbackQuery):
    """Возврат в админ-панель"""
    await callback.message.edit_text(
        "👑 <b>Панель администратора</b>\n\nВыберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_main_keyboard()
    )
    await callback.answer()

# ===================== КОМАНДЫ АДМИНИСТРАТОРА =====================
@dp.message(Command("set_crash_multiplier"))
async def set_crash_multiplier(message: Message):
    """Установка максимального множителя Crash"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_crash_multiplier <число>")
        return
    
    try:
        value = int(args[1])
        if value < 10:
            await message.answer("❌ Множитель должен быть больше 10")
            return
        if value > 10000:
            await message.answer("❌ Множитель должен быть меньше 10000")
            return
        
        bot_settings["crash_max_multiplier"] = value
        await message.answer(f"✅ Максимальный множитель Crash установлен: x{value}")
    except:
        await message.answer("❌ Введите число!")

@dp.message(Command("set_mines_size"))
async def set_mines_size(message: Message):
    """Установка размера поля Mines"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_mines_size <число>")
        return
    
    try:
        value = int(args[1])
        if value < 3:
            await message.answer("❌ Размер поля должен быть не менее 3")
            return
        if value > 10:
            await message.answer("❌ Размер поля должен быть не более 10")
            return
        
        bot_settings["mines_board_size"] = value
        await message.answer(f"✅ Размер поля Mines установлен: {value}x{value}")
    except:
        await message.answer("❌ Введите число!")

@dp.message(Command("set_mines_count"))
async def set_mines_count(message: Message):
    """Установка количества мин в Mines"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_mines_count <число>")
        return
    
    try:
        value = int(args[1])
        max_mines = bot_settings["mines_board_size"] ** 2 - 1
        if value < 1:
            await message.answer("❌ Количество мин должно быть не менее 1")
            return
        if value > max_mines:
            await message.answer(f"❌ Количество мин не должно превышать {max_mines}")
            return
        
        bot_settings["mines_mines_count"] = value
        await message.answer(f"✅ Количество мин в Mines установлено: {value}")
    except:
        await message.answer("❌ Введите число!")

@dp.message(Command("set_dice_multiplier"))
async def set_dice_multiplier(message: Message):
    """Установка множителя Dice"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_dice_multiplier <число>")
        return
    
    try:
        value = float(args[1])
        if value < 1.1:
            await message.answer("❌ Множитель должен быть больше 1.1")
            return
        if value > 10:
            await message.answer("❌ Множитель должен быть меньше 10")
            return
        
        bot_settings["dice_multiplier"] = value
        await message.answer(f"✅ Множитель Dice установлен: x{value}")
    except:
        await message.answer("❌ Введите число!")

@dp.message(Command("set_min_bet"))
async def set_min_bet(message: Message):
    """Установка минимальной ставки"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_min_bet <сумма>")
        return
    
    try:
        value = float(args[1])
        if value < 0.1:
            await message.answer("❌ Минимальная ставка должна быть не менее 0.1")
            return
        if value > bot_settings["max_bet"]:
            await message.answer(f"❌ Минимальная ставка не может превышать максимальную ({bot_settings['max_bet']})")
            return
        
        bot_settings["min_bet"] = value
        await message.answer(f"✅ Минимальная ставка установлена: {format_stars(value)}")
    except:
        await message.answer("❌ Введите число!")

@dp.message(Command("set_max_bet"))
async def set_max_bet(message: Message):
    """Установка максимальной ставки"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_max_bet <сумма>")
        return
    
    try:
        value = float(args[1])
        if value < bot_settings["min_bet"]:
            await message.answer(f"❌ Максимальная ставка не может быть меньше минимальной ({bot_settings['min_bet']})")
            return
        if value > 100000:
            await message.answer("❌ Максимальная ставка не может превышать 100000")
            return
        
        bot_settings["max_bet"] = value
        await message.answer(f"✅ Максимальная ставка установлена: {format_stars(value)}")
    except:
        await message.answer("❌ Введите число!")

@dp.message(Command("set_referral_percent"))
async def set_referral_percent(message: Message):
    """Установка процента реферальных отчислений"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_referral_percent <процент>")
        return
    
    try:
        value = float(args[1])
        if value < 0:
            await message.answer("❌ Процент должен быть не менее 0")
            return
        if value > 50:
            await message.answer("❌ Процент должен быть не более 50")
            return
        
        bot_settings["referral_percent"] = value
        await message.answer(f"✅ Реферальный процент установлен: {value}%")
    except:
        await message.answer("❌ Введите число!")

@dp.message(Command("set_maintenance"))
async def set_maintenance(message: Message):
    """Включение/выключение режима обслуживания"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_maintenance <вкл/выкл>")
        return
    
    value = args[1].lower()
    if value == "вкл" or value == "on":
        bot_settings["maintenance_mode"] = True
        await message.answer("🔧 Режим обслуживания ВКЛЮЧЁН! Новые игры недоступны.")
    elif value == "выкл" or value == "off":
        bot_settings["maintenance_mode"] = False
        await message.answer("✅ Режим обслуживания ВЫКЛЮЧЁН! Бот снова работает.")
    else:
        await message.answer("❌ Используйте 'вкл' или 'выкл'")

@dp.message(Command("set_daily_bonus"))
async def set_daily_bonus(message: Message):
    """Включение/выключение ежедневного бонуса"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /set_daily_bonus <вкл/выкл>")
        return
    
    value = args[1].lower()
    if value == "вкл" or value == "on":
        bot_settings["daily_bonus_enabled"] = True
        await message.answer("✅ Ежедневный бонус ВКЛЮЧЁН!")
    elif value == "выкл" or value == "off":
        bot_settings["daily_bonus_enabled"] = False
        await message.answer("❌ Ежедневный бонус ВЫКЛЮЧЁН!")
    else:
        await message.answer("❌ Используйте 'вкл' или 'выкл'")

@dp.message(Command("clear_crash"))
async def clear_crash(message: Message):
    """Завершение всех игр Crash"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    count = len(active_crash)
    active_crash.clear()
    await message.answer(f"✅ Завершено {count} игр Crash")

@dp.message(Command("clear_mines"))
async def clear_mines(message: Message):
    """Завершение всех игр Mines"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    count = len(active_mines)
    active_mines.clear()
    await message.answer(f"✅ Завершено {count} игр Mines")

@dp.message(Command("clear_dice"))
async def clear_dice(message: Message):
    """Завершение всех игр Dice"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    count = len(active_dice)
    active_dice.clear()
    await message.answer(f"✅ Завершено {count} игр Dice")

@dp.message(Command("clear_all_games"))
async def clear_all_games(message: Message):
    """Завершение всех игр"""
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    crash_count = len(active_crash)
    mines_count = len(active_mines)
    dice_count = len(active_dice)
    
    active_crash.clear()
    active_mines.clear()
    active_dice.clear()
    
    await message.answer(
        f"✅ <b>Все игры завершены!</b>\n\n"
        f"📈 CRASH: {crash_count} игр\n"
        f"💣 MINES: {mines_count} игр\n"
        f"🎲 DICE: {dice_count} игр\n"
        f"📊 Всего: {crash_count + mines_count + dice_count} игр",
        parse_mode=ParseMode.HTML
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
        bonus = amount * bot_settings["referral_percent"] / 100
        
        if bonus > 0:
            update_balance(referrer_id, bonus)
            save_transaction(referrer_id, bonus, "referral_earning", 
                           f"{bot_settings['referral_percent']}% от пополнения реферала")
            
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
                    f"🎁 Ваш бонус ({bot_settings['referral_percent']}%): {format_stars(bonus)}",
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

# ===================== ОБРАБОТЧИК КНОПКИ ОТМЕНЫ =====================
@dp.message(F.text == "❌ Отмена")
async def cancel_button(message: Message, state: FSMContext):
    """Обработка кнопки отмены"""
    await state.clear()
    await message.answer(
        "❌ Операция отменена.",
        reply_markup=get_admin_main_keyboard() if is_admin(message.from_user.username or "") else get_main_keyboard(message.from_user.id)
    )

@dp.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext):
    """Обработка команды /cancel"""
    await state.clear()
    await message.answer(
        "❌ Действие отменено.",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

# ===================== ОБРАБОТЧИК ОШИБОК =====================
@dp.errors()
async def errors_handler(update, exception):
    """Глобальный обработчик ошибок"""
    logger.error(f"Произошла ошибка: {exception}")
    
    try:
        if update and hasattr(update, 'event') and hasattr(update.event, 'chat'):
            await bot.send_message(
                update.event.chat.id,
                "⚠️ Произошла техническая ошибка. Администраторы уже уведомлены.\n\n"
                "Пожалуйста, попробуйте позже или обратитесь в поддержку.",
                parse_mode=ParseMode.HTML
            )
    except:
        pass

# ===================== ЗАПУСК БОТА =====================
async def main():
    """Запуск бота"""
    logger.info("🚀 StarPlay Casino Bot запускается...")
    
    # Автоматический бэкап при запуске
    save_backup()
    
    # Запускаем фоновую задачу для авто-бэкапа
    async def auto_backup_task():
        while True:
            await asyncio.sleep(BACKUP_INTERVAL_HOURS * 3600)
            save_backup()
            logger.info("Автоматический бэкап выполнен")
    
    asyncio.create_task(auto_backup_task())
    
    # Удаляем вебхук и запускаем polling
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())