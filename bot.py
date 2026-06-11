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
BOT_TOKEN = "8251949164:AAH9dxlioIEhmzZNazWzMHg0NhfaEsGYFMk"
ADMIN_USERNAMES = ["hjklgf1", "admin"]

# Настройки игр
CRASH_MAX_MULTIPLIER = 1000
CRASH_HOUSE_EDGE = 0.95
MINES_BOARD_SIZE = 5
MINES_MINES_COUNT = 5
DICE_MULTIPLIER = 1.9
DICE_MAX_NUMBER = 100

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
users_admin_notes: Dict[int, str] = {}
users_verify: Dict[int, bool] = {}
users_verify_code: Dict[int, str] = {}

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

# Чёрный список
blacklist: Dict[int, dict] = {}

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
    "server_start_time": datetime.now().isoformat()
}

# Настройки бота
bot_settings = {
    "maintenance_mode": False,
    "min_bet": MIN_BET,
    "max_bet": MAX_BET,
    "crash_house_edge": CRASH_HOUSE_EDGE,
    "referral_percent": REFERRAL_BONUS_PERCENT,
    "daily_bonus_enabled": True,
    "chat_link": "https://t.me/starplay_chat",
    "channel_link": "https://t.me/starplay_news",
    "support_link": "https://t.me/starplay_support"
}

# Системные сообщения
system_messages = {
    "welcome": "🌟 Добро пожаловать в StarPlay!",
    "maintenance": "🔧 Бот на техническом обслуживании",
    "ban": "🚫 Ваш аккаунт заблокирован",
    "error": "⚠️ Произошла ошибка"
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
    
    # Админ
    admin_main = State()
    admin_find_user = State()
    admin_change_balance = State()
    admin_send_broadcast = State()
    admin_send_broadcast_confirm = State()
    admin_ban_user = State()
    admin_ban_reason = State()
    admin_set_verify = State()
    admin_promo_create = State()
    admin_promo_amount = State()
    admin_global_bonus = State()
    admin_global_bonus_amount = State()
    admin_edit_note = State()


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
    
    # Обновляем статистику бота
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
    """Получение статистики пользователя"""
    if user_id not in users_stats:
        users_stats[user_id] = {
            "games_played": 0, "games_won": 0, "total_won": 0.0, "total_lost": 0.0,
            "crash_games": 0, "crash_wins": 0, "crash_best_multiplier": 0.0,
            "mines_games": 0, "mines_wins": 0, "mines_best_multiplier": 0.0,
            "dice_games": 0, "dice_wins": 0, "dice_best_multiplier": 0.0,
            "total_deposits": 0, "total_deposit_amount": 0.0,
            "referral_count": 0, "referral_earned": 0.0,
            "daily_bonus_count": 0, "daily_bonus_streak": 0
        }
    return users_stats[user_id]

def get_random_emoji() -> str:
    """Случайный эмодзи"""
    emojis = ["🎲", "🎯", "⚡️", "💫", "🌟", "⭐️", "✨", "🎮", "🎰", "🔥", "💰", "💎", "🏆", "🎉", "🚀"]
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
        return f"{seconds // 60} мин {seconds % 60} сек"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours} ч {minutes} мин"

def save_backup():
    """Сохранение резервной копии"""
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
        "bot_stats": bot_stats,
        "crash_history": crash_history[-50:],
        "mines_history": mines_history[-50:],
        "dice_history": dice_history[-50:]
    }
    try:
        with open("backup.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Backup error: {e}")
        return False

def load_backup():
    """Загрузка резервной копии"""
    try:
        with open("backup.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return data
    except:
        return None


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
    builder.button(text="🎁 Промокоды")
    builder.button(text="💰 Бонус всем")
    builder.button(text="📝 Заметки")
    builder.button(text="💾 Сохранить")
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

def get_bet_keyboard(game: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора ставки"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐️ 1", callback_data=f"{game}_bet_1"),
         InlineKeyboardButton(text="⭐️ 5", callback_data=f"{game}_bet_5"),
         InlineKeyboardButton(text="⭐️ 10", callback_data=f"{game}_bet_10")],
        [InlineKeyboardButton(text="⭐️ 25", callback_data=f"{game}_bet_25"),
         InlineKeyboardButton(text="⭐️ 50", callback_data=f"{game}_bet_50"),
         InlineKeyboardButton(text="⭐️ 100", callback_data=f"{game}_bet_100")],
        [InlineKeyboardButton(text="⭐️ 250", callback_data=f"{game}_bet_250"),
         InlineKeyboardButton(text="⭐️ 500", callback_data=f"{game}_bet_500"),
         InlineKeyboardButton(text="⭐️ 1000", callback_data=f"{game}_bet_1000")],
        [InlineKeyboardButton(text="✏️ Своя сумма", callback_data=f"{game}_bet_custom")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_games")]
    ])

def get_crash_game_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура во время игры Crash"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 ЗАБРАТЬ ВЫИГРЫШ", callback_data="crash_cashout")],
        [InlineKeyboardButton(text="❌ ВЫЙТИ", callback_data="crash_exit")]
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
            row.append(InlineKeyboardButton(text=text, callback_data=f"mine_cell_{i}_{j}"))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton(text=f"💰 ЗАБРАТЬ ({format_stars(bet * multiplier)})", callback_data="mines_cashout")])
    keyboard.append([InlineKeyboardButton(text="❌ ВЫЙТИ", callback_data="mines_exit")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_dice_game_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для игры Dice"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬆️ ВЫШЕ 50", callback_data="dice_higher"),
         InlineKeyboardButton(text="⬇️ НИЖЕ 50", callback_data="dice_lower")],
        [InlineKeyboardButton(text="❌ ВЫЙТИ", callback_data="dice_exit")]
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


# ===================== КОМАНДЫ =====================
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username or ""
    
    if bot_settings["maintenance_mode"] and not is_admin(username):
        await message.answer("🔧 Бот на техническом обслуживании. Зайдите позже.", parse_mode=ParseMode.HTML)
        return
    
    if users_ban.get(user_id, False):
        await message.answer(
            f"🚫 <b>Ваш аккаунт заблокирован!</b>\n\nПричина: {users_ban_reason.get(user_id, 'Не указана')}",
            parse_mode=ParseMode.HTML
        )
        return
    
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
                if referrer_id != user_id and user_id not in users_referrer:
                    users_referrer[user_id] = referrer_id
                    users_referrals.setdefault(referrer_id, []).append(user_id)
                    
                    update_balance(user_id, REFERRAL_SIGNUP_BONUS)
                    update_balance(referrer_id, REFERRAL_INVITE_BONUS)
                    
                    stats_ref = get_user_stats(referrer_id)
                    stats_ref["referral_count"] += 1
                    stats_ref["referral_earned"] += REFERRAL_INVITE_BONUS
                    
                    save_transaction(user_id, REFERRAL_SIGNUP_BONUS, "referral_bonus", f"от {referrer_id}")
                    save_transaction(referrer_id, REFERRAL_INVITE_BONUS, "referral_reward", f"пригласил {user_id}")
                    
                    await message.answer(f"✅ Получен бонус {format_stars(REFERRAL_SIGNUP_BONUS)} за регистрацию по ссылке!")
                    
                    try:
                        await bot.send_message(referrer_id, f"🎉 По вашей ссылке зарегистрировался @{username or user_id}!\n+{format_stars(REFERRAL_INVITE_BONUS)}")
                    except:
                        pass
            except:
                pass
    
    welcome_text = (
        f"🌟 <b>Добро пожаловать в StarPlay!</b> 🌟\n\n"
        f"{get_random_emoji()} <b>Лучшее казино в Telegram!</b>\n\n"
        f"<b>🎮 Игры:</b>\n"
        f"📈 CRASH — множитель до x{CRASH_MAX_MULTIPLIER}\n"
        f"💣 MINES — найди сокровища, избегая мин\n"
        f"🎲 DICE — угадай число, множитель x{DICE_MULTIPLIER}\n\n"
        f"<b>💫 Как начать:</b>\n"
        f"1️⃣ Пополните баланс\n"
        f"2️⃣ Выберите игру\n"
        f"3️⃣ Выигрывайте!\n\n"
        f"👇 <i>Используйте кнопки меню</i>"
    )
    
    await state.clear()
    await message.answer(welcome_text, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard(user_id))


@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    help_text = (
        f"❓ <b>Помощь по боту StarPlay</b>\n\n"
        f"<b>🎮 Игры:</b>\n"
        f"📈 <b>CRASH</b> — Ставка растёт. Заберите выигрыш до взрыва!\n"
        f"💣 <b>MINES</b> — Открывайте клетки с 💎, избегайте 💣\n"
        f"🎲 <b>DICE</b> — Угадайте, выпадет число выше или ниже 50\n\n"
        f"<b>💰 Баланс:</b>\n"
        f"• Пополнение: кнопка «⭐️ Пополнить»\n"
        f"• Мин. ставка: {MIN_BET} Star\n"
        f"• Макс. ставка: {MAX_BET} Stars\n\n"
        f"<b>👥 Рефералы:</b>\n"
        f"• Пригласите друга — получите {REFERRAL_INVITE_BONUS} Stars\n"
        f"• Друг получает {REFERRAL_SIGNUP_BONUS} Stars\n"
        f"• Вы получаете {REFERRAL_BONUS_PERCENT}% от пополнений\n\n"
        f"<b>🎁 Бонусы:</b>\n"
        f"• Ежедневный бонус до {DAILY_BONUS_MAX} Stars\n"
        f"• За ежедневный вход бонус растёт!\n\n"
        f"<b>📞 Контакты:</b>\n"
        f"• Чат: {bot_settings['chat_link']}\n"
        f"• Поддержка: {bot_settings['support_link']}"
    )
    await message.answer(help_text, parse_mode=ParseMode.HTML)


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Обработчик команды /cancel"""
    await state.clear()
    await message.answer("❌ Действие отменено.", reply_markup=get_main_keyboard(message.from_user.id))


# ===================== ГЛАВНЫЕ КНОПКИ =====================
@dp.message(F.text == "💰 Баланс")
async def balance_reply(message: Message):
    user_id = message.from_user.id
    await message.answer(f"💰 <b>Ваш баланс:</b> {format_stars(get_user_balance(user_id))}", parse_mode=ParseMode.HTML)


@dp.message(F.text == "⭐️ Пополнить")
async def deposit_reply(message: Message):
    await message.answer("⭐️ <b>Пополнение баланса</b>\n\nВыберите сумму:", parse_mode=ParseMode.HTML, reply_markup=get_deposit_keyboard())


@dp.message(F.text == "🎮 Игры")
async def games_reply(message: Message):
    await message.answer("🎮 <b>Выберите игру</b>", parse_mode=ParseMode.HTML, reply_markup=get_games_keyboard())


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
        f"• Друг получает +{REFERRAL_SIGNUP_BONUS} Stars\n"
        f"• Вы получаете +{REFERRAL_INVITE_BONUS} Stars\n"
        f"• Вы получаете {REFERRAL_BONUS_PERCENT}% от пополнений\n\n"
        f"<b>🔗 Ваша ссылка:</b>\n"
        f"<code>{ref_link}</code>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={ref_link}&text=StarPlay — играй и выигрывай!")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@dp.message(F.text == "🏆 Топ")
async def top_reply(message: Message):
    sorted_users = sorted(users_balance.items(), key=lambda x: x[1], reverse=True)[:15]
    if not sorted_users:
        await message.answer("🏆 Пока нет игроков в рейтинге!")
        return
    
    text = "🏆 <b>ТОП-15 ПО БАЛАНСУ</b>\n\n"
    for idx, (uid, bal) in enumerate(sorted_users, 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
        uname = users_username.get(uid, str(uid))
        text += f"{medal} @{uname} — {bal:.2f} ⭐️\n"
    
    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(F.text == "📊 Профиль")
async def profile_reply(message: Message):
    uid = message.from_user.id
    stats = get_user_stats(uid)
    wr = (stats['games_won'] / max(stats['games_played'], 1)) * 100
    
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
        f"├ 📈 Винрейт: {wr:.1f}%\n"
        f"├ 💎 Выиграно: {format_stars(stats['total_won'])}\n"
        f"├ 💸 Проиграно: {format_stars(stats['total_lost'])}\n"
        f"├ 📈 CRASH: {stats['crash_wins']}/{stats['crash_games']}\n"
        f"├ 💣 MINES: {stats['mines_wins']}/{stats['mines_games']}\n"
        f"└ 🎲 DICE: {stats['dice_wins']}/{stats['dice_games']}\n\n"
        f"👥 <b>Рефералы:</b> {stats['referral_count']}\n"
        f"💰 <b>Заработано:</b> {format_stars(stats['referral_earned'])}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(F.text == "🎁 Бонус")
async def bonus_reply(message: Message):
    user_id = message.from_user.id
    today = datetime.now().date().isoformat()
    
    if not bot_settings["daily_bonus_enabled"]:
        await message.answer("🔧 Ежедневный бонус временно отключён!")
        return
    
    if users_daily_bonus.get(user_id) == today:
        await message.answer("🎁 Вы уже получили сегодняшний бонус! Возвращайтесь завтра.", parse_mode=ParseMode.HTML)
        return
    
    streak = users_daily_bonus_streak.get(user_id, 0)
    if users_daily_bonus.get(user_id) == (datetime.now() - timedelta(days=1)).date().isoformat():
        streak += 1
    else:
        streak = 1
    
    bonus = min(DAILY_BONUS_MAX, DAILY_BONUS_MIN + (streak - 1) * 2)
    bonus = round(bonus + random.uniform(-1, 1), 2)
    
    update_balance(user_id, bonus)
    users_daily_bonus[user_id] = today
    users_daily_bonus_streak[user_id] = streak
    save_transaction(user_id, bonus, "daily_bonus", f"Стрик: {streak}")
    
    await message.answer(f"🎉 <b>Ежедневный бонус получен!</b>\n\n+{format_stars(bonus)}\n📅 Стрик: {streak} дней\n💰 Новый баланс: {format_stars(get_user_balance(user_id))}", parse_mode=ParseMode.HTML)


@dp.message(F.text == "❓ Помощь")
async def help_reply(message: Message):
    await cmd_help(message)


# ===================== ИГРА 1: CRASH =====================
@dp.message(F.text == "📈 CRASH")
async def crash_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    if users_ban.get(user_id, False):
        await message.answer("❌ Ваш аккаунт заблокирован!")
        return
    
    if user_id in active_crash:
        await message.answer("⚠️ У вас уже есть активная игра!")
        return
    
    await state.set_state(GameStates.crash_bet)
    await message.answer(
        "📈 <b>CRASH — Умножай ставку!</b>\n\n"
        "📋 Правила:\n"
        "• Вы делаете ставку\n"
        "• Множитель начинает расти\n"
        "• Нужно забрать выигрыш ДО взрыва\n"
        f"• Максимальный множитель: x{CRASH_MAX_MULTIPLIER}\n\n"
        "💰 Выберите сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("crash")
    )


@dp.callback_query(F.data.startswith("crash_bet_"))
async def crash_place_bet(callback: CallbackQuery, state: FSMContext):
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
    
    # Случайная точка краша с учётом house edge
    crash_point = random.uniform(1.01, CRASH_MAX_MULTIPLIER * CRASH_HOUSE_EDGE)
    active_crash[user_id] = {"bet": bet, "crash_point": crash_point, "multiplier": 1.0, "running": True}
    
    await state.set_state(GameStates.crash_waiting)
    game_msg = await callback.message.edit_text(
        f"📈 <b>CRASH — ИГРА ИДЁТ!</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"📈 Множитель: <b>x1.00</b>\n"
        f"💎 Выигрыш: {format_stars(bet)}\n\n"
        f"⚠️ Чем дольше ждёте — тем выше множитель!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_crash_game_keyboard()
    )
    
    await callback.answer()
    
    # Запускаем рост множителя
    multiplier = 1.0
    while user_id in active_crash and multiplier < crash_point:
        multiplier = round(multiplier + 0.01, 2)
        active_crash[user_id]["multiplier"] = multiplier
        try:
            await game_msg.edit_text(
                f"📈 <b>CRASH — ИГРА ИДЁТ!</b>\n\n"
                f"💰 Ставка: {format_stars(bet)}\n"
                f"📈 Множитель: <b>x{multiplier:.2f}</b>\n"
                f"💎 Выигрыш: {format_stars(bet * multiplier)}\n\n"
                f"⚠️ Заберите выигрыш до взрыва!",
                parse_mode=ParseMode.HTML,
                reply_markup=get_crash_game_keyboard()
            )
        except:
            pass
        await asyncio.sleep(0.1)
    
    # Взрыв
    if user_id in active_crash:
        game = active_crash.pop(user_id)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["crash_games"] += 1
        stats["total_lost"] += game["bet"]
        save_transaction(user_id, -game["bet"], "game_loss", f"Crash крах x{game['multiplier']:.2f}", "crash")
        bot_stats["crash_games_played"] += 1
        
        try:
            await game_msg.edit_text(
                f"💥 <b>CRASH — ВЗРЫВ!</b>\n\n"
                f"💰 Ставка: {format_stars(game['bet'])}\n"
                f"📈 Множитель в момент взрыва: x{game['multiplier']:.2f}\n\n"
                f"😢 Ставка сгорела!\n"
                f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_games_keyboard()
            )
        except:
            pass


@dp.callback_query(F.data == "crash_cashout")
async def crash_cashout(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    if user_id not in active_crash:
        await callback.answer("Нет активной игры!", show_alert=True)
        return
    
    game = active_crash.pop(user_id)
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
    
    save_transaction(user_id, win, "game_win", f"Crash выигрыш x{game['multiplier']:.2f}", "crash")
    bot_stats["crash_games_played"] += 1
    
    crash_history.append({"multiplier": game["multiplier"], "player": user_id, "win": win})
    if len(crash_history) > 100:
        crash_history.pop(0)
    
    await state.clear()
    await callback.message.edit_text(
        f"🎉 <b>CRASH — ВЫ ПОБЕДИЛИ!</b>\n\n"
        f"💰 Ставка: {format_stars(game['bet'])}\n"
        f"📈 Множитель: <b>x{game['multiplier']:.2f}</b>\n"
        f"🏆 Выигрыш: {format_stars(win)}\n\n"
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
    await callback.message.edit_text("❌ Вы вышли из игры.", reply_markup=get_games_keyboard())
    await callback.answer()


# ===================== ИГРА 2: MINES =====================
@dp.message(F.text == "💣 MINES")
async def mines_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    if users_ban.get(user_id, False):
        await message.answer("❌ Ваш аккаунт заблокирован!")
        return
    
    if user_id in active_mines:
        await message.answer("⚠️ У вас уже есть активная игра!")
        return
    
    await state.set_state(GameStates.mines_bet)
    await message.answer(
        "💣 <b>MINES — Найди сокровища!</b>\n\n"
        "📋 Правила:\n"
        f"• Поле {MINES_BOARD_SIZE}x{MINES_BOARD_SIZE}\n"
        f"• Спрятано {MINES_MINES_COUNT} мин\n"
        "• Каждая 💎 увеличивает множитель x1.2\n"
        "• Наступите на 💣 — проигрыш\n"
        f"• Максимальный множитель: x{1.2 ** 20:.1f}\n\n"
        "💰 Выберите сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("mines")
    )


@dp.callback_query(F.data.startswith("mines_bet_"))
async def mines_place_bet(callback: CallbackQuery, state: FSMContext):
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
    
    # Создаём поле
    board = [["💎" for _ in range(5)] for _ in range(5)]
    mines = 0
    while mines < MINES_MINES_COUNT:
        x, y = random.randint(0, 4), random.randint(0, 4)
        if board[x][y] == "💎":
            board[x][y] = "💣"
            mines += 1
    
    active_mines[user_id] = {
        "bet": bet, "board": board, "revealed": [[False]*5 for _ in range(5)],
        "multiplier": 1.0, "cells_opened": 0
    }
    
    await state.set_state(GameStates.mines_playing)
    await callback.message.edit_text(
        f"💣 <b>MINES — ИГРА</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"✨ Множитель: x1.0\n"
        f"📦 Открыто: 0/20\n\n"
        f"👇 <b>Открывайте клетки!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_mines_board_keyboard(board, active_mines[user_id]["revealed"], bet, 1.0)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("mine_cell_"))
async def mines_open_cell(callback: CallbackQuery):
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
        save_transaction(user_id, -game["bet"], "game_loss", f"Mines проигрыш", "mines")
        bot_stats["mines_games_played"] += 1
        del active_mines[user_id]
        
        await callback.message.edit_text(
            f"💣 <b>MINES — ПРОИГРЫШ!</b>\n\n"
            f"💥 Вы наступили на мину!\n"
            f"💰 Ставка проиграна: {format_stars(game['bet'])}\n"
            f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_games_keyboard()
        )
    else:
        game["cells_opened"] += 1
        game["multiplier"] *= 1.2
        current_win = game["bet"] * game["multiplier"]
        
        if game["cells_opened"] >= 20:
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
            del active_mines[user_id]
            
            await callback.message.edit_text(
                f"🎉 <b>MINES — ПОБЕДА!</b>\n\n"
                f"✨ Множитель: x{game['multiplier']:.1f}\n"
                f"🏆 Выигрыш: {format_stars(current_win)}\n"
                f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_games_keyboard()
            )
        else:
            await callback.message.edit_text(
                f"💣 <b>MINES — ИГРА</b>\n\n"
                f"💰 Ставка: {format_stars(game['bet'])}\n"
                f"✨ Множитель: x{game['multiplier']:.1f}\n"
                f"📦 Открыто: {game['cells_opened']}/20\n"
                f"💎 Текущий выигрыш: {format_stars(current_win)}\n\n"
                f"✅ Найдена 💎! Множитель увеличен!",
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
    
    game = active_mines.pop(user_id)
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
    
    await callback.message.edit_text(
        f"💰 <b>MINES — ВЫ ЗАБРАЛИ ВЫИГРЫШ!</b>\n\n"
        f"📦 Открыто: {game['cells_opened']}/20\n"
        f"✨ Множитель: x{game['multiplier']:.1f}\n"
        f"🏆 Выигрыш: {format_stars(win)}\n"
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
    await callback.message.edit_text("❌ Вы вышли из игры.", reply_markup=get_games_keyboard())
    await callback.answer()


# ===================== ИГРА 3: DICE =====================
@dp.message(F.text == "🎲 DICE")
async def dice_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    if users_ban.get(user_id, False):
        await message.answer("❌ Ваш аккаунт заблокирован!")
        return
    
    await state.set_state(GameStates.dice_bet)
    await message.answer(
        "🎲 <b>DICE — Угадай число!</b>\n\n"
        "📋 Правила:\n"
        "• Вы делаете ставку\n"
        "• Угадываете, выпадет число выше 50 или ниже 50\n"
        f"• При правильном угадывании выигрыш x{DICE_MULTIPLIER}\n\n"
        "💰 Выберите сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("dice")
    )


@dp.callback_query(F.data.startswith("dice_bet_"))
async def dice_place_bet(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    bet_str = callback.data.split("_")[-1]
    
    if bet_str == "custom":
        await callback.message.answer("✏️ Введите сумму ставки (1-10000):", parse_mode=ParseMode.HTML)
        await state.set_state(GameStates.dice_bet)
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
    
    active_dice[user_id] = {"bet": bet}
    await state.set_state(GameStates.dice_playing)
    
    await callback.message.edit_text(
        f"🎲 <b>DICE — СДЕЛАЙТЕ ПРЕДСКАЗАНИЕ</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"🎯 Выигрыш: {format_stars(bet * DICE_MULTIPLIER)}\n\n"
        f"👇 <b>Выберите:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_dice_game_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data == "dice_higher")
async def dice_higher(callback: CallbackQuery, state: FSMContext):
    await dice_play(callback, state, "higher")


@dp.callback_query(F.data == "dice_lower")
async def dice_lower(callback: CallbackQuery, state: FSMContext):
    await dice_play(callback, state, "lower")


async def dice_play(callback: CallbackQuery, state: FSMContext, prediction: str):
    user_id = callback.from_user.id
    
    if user_id not in active_dice:
        await callback.answer("Ошибка! Начните игру заново.", show_alert=True)
        return
    
    game = active_dice.pop(user_id)
    bet = game["bet"]
    
    update_balance(user_id, -bet)
    save_transaction(user_id, -bet, "bet", f"Dice ставка", "dice")
    
    # Бросаем кубик
    dice_msg = await callback.message.answer_dice(emoji="🎲")
    dice_value = dice_msg.dice.value * 16  # 1-6 -> 1-96
    
    if (prediction == "higher" and dice_value > 50) or (prediction == "lower" and dice_value < 50):
        win = bet * DICE_MULTIPLIER
        update_balance(user_id, win)
        
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["dice_games"] += 1
        stats["dice_wins"] += 1
        stats["total_won"] += win
        save_transaction(user_id, win, "game_win", f"Dice победа {dice_value}", "dice")
        
        result_text = f"🎉 <b>ВЫ УГАДАЛИ!</b>\nВыпало: {dice_value}\nВыигрыш: +{format_stars(win - bet)}"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["dice_games"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", f"Dice проигрыш {dice_value}", "dice")
        
        result_text = f"😢 <b>ВЫ НЕ УГАДАЛИ!</b>\nВыпало: {dice_value}\nПотеряно: {format_stars(bet)}"
    
    bot_stats["dice_games_played"] += 1
    dice_history.append({"result": dice_value, "prediction": prediction, "player": user_id})
    if len(dice_history) > 100:
        dice_history.pop(0)
    
    await state.clear()
    await callback.message.answer(
        f"🎲 <b>DICE — РЕЗУЛЬТАТ</b>\n\n"
        f"{result_text}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data == "dice_exit")
async def dice_exit(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id in active_dice:
        del active_dice[user_id]
    await state.clear()
    await callback.message.edit_text("❌ Вы вышли из игры.", reply_markup=get_games_keyboard())
    await callback.answer()


# ===================== ИСТОРИЯ ИГР =====================
@dp.message(F.text == "📊 История игр")
async def games_history(message: Message):
    user_id = message.from_user.id
    
    user_crash = [g for g in crash_history if g.get("player") == user_id][-5:]
    user_mines = [g for g in mines_history if g.get("player") == user_id][-5:]
    user_dice = [g for g in dice_history if g.get("player") == user_id][-5:]
    
    text = "📊 <b>ИСТОРИЯ ВАШИХ ИГР</b>\n\n"
    
    if user_crash:
        text += "<b>📈 CRASH:</b>\n"
        for g in user_crash:
            text += f"• Множитель: x{g.get('multiplier', 0):.2f} | {g.get('win', 0):.0f}⭐️\n"
        text += "\n"
    
    if user_mines:
        text += "<b>💣 MINES:</b>\n"
        for g in user_mines:
            if g.get("win", 0) > 0:
                text += f"• Победа: {g.get('win', 0):.0f}⭐️\n"
            else:
                text += f"• Проигрыш\n"
        text += "\n"
    
    if user_dice:
        text += "<b>🎲 DICE:</b>\n"
        for g in user_dice:
            text += f"• Выпало: {g.get('result', 0)} | Предсказание: {'Выше' if g.get('prediction') == 'higher' else 'Ниже'}\n"
        text += "\n"
    
    if not user_crash and not user_mines and not user_dice:
        text += "📭 У вас пока нет сыгранных игр."
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_games_keyboard())


# ===================== АДМИН-ПАНЕЛЬ =====================
@dp.message(F.text == "👑 Админ панель")
async def admin_panel(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await message.answer(
        "👑 <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n\n"
        "📊 Статистика — просмотр общей статистики\n"
        "💰 Изменить баланс — пополнение/снятие\n"
        "📢 Рассылка — массовая рассылка\n"
        "👥 Пользователи — список всех\n"
        "🔨 Бан/Разбан — блокировка\n"
        "✅ Верификация — верификация аккаунтов\n"
        "🎁 Промокоды — создание промокодов\n"
        "💰 Бонус всем — выдача бонуса всем\n"
        "📝 Заметки — заметки о пользователях\n"
        "💾 Сохранить — резервное копирование\n\n"
        "👇 <b>Выберите действие:</b>",
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
        f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
        f"<b>👥 Пользователи:</b>\n"
        f"├ Всего: {bot_stats['total_users']}\n"
        f"├ Забанено: {len([u for u,b in users_ban.items() if b])}\n"
        f"└ Верифицировано: {len([u for u,v in users_verify.items() if v])}\n\n"
        f"<b>💰 Финансы:</b>\n"
        f"├ Общий баланс: {format_stars(sum(users_balance.values()))}\n"
        f"├ Всего ставок: {bot_stats['total_bets']}\n"
        f"├ Общая сумма: {format_stars(bot_stats['total_wagered'])}\n"
        f"├ Выплачено: {format_stars(bot_stats['total_paid'])}\n"
        f"└ Прибыль: {format_stars(bot_stats['total_profit'])}\n\n"
        f"<b>🎮 Игры:</b>\n"
        f"├ CRASH: {bot_stats['crash_games_played']} игр\n"
        f"├ MINES: {bot_stats['mines_games_played']} игр\n"
        f"└ DICE: {bot_stats['dice_games_played']} игр\n\n"
        f"<b>🕐 Система:</b>\n"
        f"├ Время работы: {format_time(uptime.seconds)}\n"
        f"└ Пополнений: {bot_stats['total_deposits']} на {format_stars(bot_stats['total_deposit_amount'])}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())


# ===================== АДМИН: ИЗМЕНЕНИЕ БАЛАНСА =====================
@dp.message(F.text == "💰 Изменить баланс")
async def admin_change_balance_start(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await state.set_state(GameStates.admin_find_user)
    await message.answer(
        "💰 <b>ИЗМЕНЕНИЕ БАЛАНСА</b>\n\n"
        "Введите username (без @) или ID:\n"
        "<i>Для отмены /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )


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
    
    await message.answer(
        f"👤 Пользователь: @{input_text}\n"
        f"💰 Текущий баланс: {format_stars(get_user_balance(user_id))}\n\n"
        f"Введите сумму изменения:\n"
        f"<code>+100</code> — добавить\n"
        f"<code>-50</code> — снять\n\n"
        f"<i>Для отмены /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
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
        save_transaction(target_user, amount, "admin_change", f"Админ: {amount}", "admin")
        
        try:
            await bot.send_message(target_user, f"👑 Администратор изменил баланс!\n{'+' if amount>0 else ''}{format_stars(amount)}\n💰 Новый баланс: {format_stars(new_balance)}", parse_mode=ParseMode.HTML)
        except:
            pass
        
        await state.clear()
        await message.answer(
            f"✅ Баланс @{target_username} изменён на {format_stars(amount)}\n"
            f"💰 Новый баланс: {format_stars(new_balance)}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_main_keyboard()
        )
    except:
        await message.answer("❌ Введите число!")


# ===================== АДМИН: РАССЫЛКА =====================
@dp.message(F.text == "📢 Рассылка")
async def admin_broadcast_start(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await state.set_state(GameStates.admin_send_broadcast)
    await message.answer(
        "📢 <b>РАССЫЛКА</b>\n\n"
        "Введите сообщение для рассылки:\n\n"
        "<i>Для отмены /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )


@dp.message(GameStates.admin_send_broadcast)
async def admin_broadcast_message(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=get_admin_main_keyboard())
        return
    
    await state.update_data(broadcast_msg=message)
    await state.set_state(GameStates.admin_send_broadcast_confirm)
    
    recipients = len([u for u in users_balance.keys() if not users_ban.get(u, False)])
    
    await message.answer(
        f"📢 <b>ПОДТВЕРЖДЕНИЕ</b>\n\n"
        f"📨 Получателей: {recipients}\n\n"
        f"<b>Сообщение:</b>\n{message.text[:200]}\n\n"
        f"✅ Отправить?",
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
        await callback.answer("Ошибка!")
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
            elif msg.video:
                await bot.send_video(user_id, msg.video.file_id, caption=msg.caption)
            else:
                await bot.copy_message(user_id, msg.chat.id, msg.message_id)
            success += 1
        except:
            pass
        await asyncio.sleep(0.05)
    
    await state.clear()
    await callback.message.edit_text(f"✅ Рассылка завершена!\n📨 Доставлено: {success}", reply_markup=get_admin_main_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "broadcast_cancel")
async def admin_broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Рассылка отменена.", reply_markup=get_admin_main_keyboard())
    await callback.answer()


# ===================== АДМИН: ПОЛЬЗОВАТЕЛИ =====================
@dp.message(F.text == "👥 Пользователи")
async def admin_users_list(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    users_list = []
    for uid, uname in users_username.items():
        banned = "🚫" if users_ban.get(uid, False) else "✅"
        verified = "✓" if users_verify.get(uid, False) else "○"
        users_list.append(f"{banned}{verified} @{uname or uid} — {get_user_balance(uid):.0f}⭐️")
    
    text = "👥 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ</b>\n\n" + "\n".join(users_list[:50])
    if len(users_list) > 50:
        text += f"\n\n... и ещё {len(users_list)-50}"
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())


# ===================== АДМИН: БАН/РАЗБАН =====================
@dp.message(F.text == "🔨 Бан/Разбан")
async def admin_ban_start(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await state.set_state(GameStates.admin_ban_user)
    await message.answer(
        "🔨 <b>БАН ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введите username (без @) или ID:\n"
        "<i>Для разбана используйте /unban</i>\n"
        "<i>Для отмены /cancel</i>",
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
    
    if users_ban.get(user_id, False):
        await message.answer(f"⚠️ Пользователь уже забанен!")
        return
    
    await state.update_data(ban_user_id=user_id, ban_username=input_text)
    await state.set_state(GameStates.admin_ban_reason)
    await message.answer("Введите причину бана:", parse_mode=ParseMode.HTML)


@dp.message(GameStates.admin_ban_reason)
async def admin_ban_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("ban_user_id")
    username = data.get("ban_username")
    reason = message.text.strip()
    
    users_ban[user_id] = True
    users_ban_reason[user_id] = reason
    
    try:
        await bot.send_message(user_id, f"🚫 <b>Ваш аккаунт заблокирован!</b>\n\nПричина: {reason}", parse_mode=ParseMode.HTML)
    except:
        pass
    
    await state.clear()
    await message.answer(f"✅ Пользователь @{username} забанен!\nПричина: {reason}", reply_markup=get_admin_main_keyboard())


@dp.message(Command("unban"))
async def admin_unban(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: /unban <username или ID>")
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
        await bot.send_message(user_id, "✅ <b>Ваш аккаунт разблокирован!</b>", parse_mode=ParseMode.HTML)
    except:
        pass
    
    await message.answer(f"✅ Пользователь разбанен!")


# ===================== АДМИН: ВЕРИФИКАЦИЯ =====================
@dp.message(F.text == "✅ Верификация")
async def admin_verify_start(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await state.set_state(GameStates.admin_set_verify)
    await message.answer(
        "✅ <b>ВЕРИФИКАЦИЯ</b>\n\n"
        "Введите username (без @) или ID:\n"
        "<i>Для отмены /cancel</i>",
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
        await bot.send_message(user_id, f"✅ Ваш аккаунт {status}!", parse_mode=ParseMode.HTML)
    except:
        pass
    
    await state.clear()
    await message.answer(f"✅ Пользователь {status}!", reply_markup=get_admin_main_keyboard())


# ===================== АДМИН: ПРОМОКОДЫ =====================
@dp.message(F.text == "🎁 Промокоды")
async def admin_promo_start(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await state.set_state(GameStates.admin_promo_create)
    await message.answer(
        "🎁 <b>СОЗДАНИЕ ПРОМОКОДА</b>\n\n"
        "Введите название промокода (буквы и цифры):\n"
        "<i>Для отмены /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )


@dp.message(GameStates.admin_promo_create)
async def admin_promo_create(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=get_admin_main_keyboard())
        return
    
    code = message.text.strip().upper()
    if not code or len(code) < 3:
        await message.answer("❌ Слишком короткий код!")
        return
    
    await state.update_data(promo_code=code)
    await state.set_state(GameStates.admin_promo_amount)
    await message.answer("Введите сумму промокода:", parse_mode=ParseMode.HTML)


@dp.message(GameStates.admin_promo_amount)
async def admin_promo_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            await message.answer("❌ Сумма должна быть положительной!")
            return
    except:
        await message.answer("❌ Введите число!")
        return
    
    data = await state.get_data()
    code = data.get("promo_code")
    
    promo_codes[code] = {"amount": amount, "uses": 0, "max_uses": 100, "created": datetime.now().isoformat()}
    
    await state.clear()
    await message.answer(
        f"✅ <b>Промокод создан!</b>\n\n"
        f"🎁 Код: <code>{code}</code>\n"
        f"💰 Сумма: {format_stars(amount)}\n"
        f"📊 Лимит использований: 100",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_main_keyboard()
    )


# ===================== АДМИН: БОНУС ВСЕМ =====================
@dp.message(F.text == "💰 Бонус всем")
async def admin_global_bonus_start(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await state.set_state(GameStates.admin_global_bonus)
    await message.answer(
        "💰 <b>БОНУС ВСЕМ ПОЛЬЗОВАТЕЛЯМ</b>\n\n"
        "Введите сумму бонуса для каждого пользователя:\n"
        "<i>Для отмены /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )


@dp.message(GameStates.admin_global_bonus)
async def admin_global_bonus(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=get_admin_main_keyboard())
        return
    
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            await message.answer("❌ Сумма должна быть положительной!")
            return
    except:
        await message.answer("❌ Введите число!")
        return
    
    success = 0
    for user_id in users_balance.keys():
        if users_ban.get(user_id, False):
            continue
        update_balance(user_id, amount)
        save_transaction(user_id, amount, "global_bonus", f"Бонус от админа: {amount}", "admin")
        try:
            await bot.send_message(user_id, f"🎁 <b>Бонус от администратора!</b>\n+{format_stars(amount)}", parse_mode=ParseMode.HTML)
            success += 1
        except:
            pass
        await asyncio.sleep(0.05)
    
    await state.clear()
    await message.answer(
        f"✅ <b>Бонус выдан!</b>\n\n"
        f"💰 Сумма: {format_stars(amount)}\n"
        f"👥 Получили: {success} пользователей",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_main_keyboard()
    )


# ===================== АДМИН: ЗАМЕТКИ =====================
@dp.message(F.text == "📝 Заметки")
async def admin_notes_start(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await state.set_state(GameStates.admin_find_user)
    await message.answer(
        "📝 <b>ЗАМЕТКИ О ПОЛЬЗОВАТЕЛЕ</b>\n\n"
        "Введите username (без @) или ID:\n"
        "<i>Для отмены /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )


@dp.message(GameStates.admin_find_user)
async def admin_find_for_note(message: Message, state: FSMContext):
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
    
    current_note = users_admin_notes.get(user_id, "Нет заметок")
    await state.update_data(note_user_id=user_id, note_username=input_text)
    await state.set_state(GameStates.admin_edit_note)
    
    await message.answer(
        f"📝 <b>ЗАМЕТКИ О @{input_text}</b>\n\n"
        f"Текущие заметки:\n{current_note}\n\n"
        f"Введите новую заметку:\n"
        f"<i>Для удаления введите /clear</i>\n"
        f"<i>Для отмены /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )


@dp.message(GameStates.admin_edit_note)
async def admin_save_note(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("note_user_id")
    username = data.get("note_username")
    
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=get_admin_main_keyboard())
        return
    
    if message.text == "/clear":
        users_admin_notes[user_id] = ""
        await message.answer(f"✅ Заметки о @{username} удалены!", reply_markup=get_admin_main_keyboard())
    else:
        users_admin_notes[user_id] = message.text
        await message.answer(f"✅ Заметки о @{username} сохранены!", reply_markup=get_admin_main_keyboard())
    
    await state.clear()


# ===================== АДМИН: СОХРАНЕНИЕ =====================
@dp.message(F.text == "💾 Сохранить")
async def admin_save(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    if save_backup():
        await message.answer("✅ <b>Данные сохранены!</b>\n\nФайл: backup.json", parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())
    else:
        await message.answer("❌ Ошибка сохранения!", reply_markup=get_admin_main_keyboard())


# ===================== НАВИГАЦИЯ =====================
@dp.message(F.text == "🔙 В главное меню")
async def back_to_main_from_admin(message: Message):
    await message.answer("🌟 <b>Главное меню</b>", parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard(message.from_user.id))


@dp.message(F.text == "🔙 Главное меню")
async def back_to_main_from_games(message: Message):
    await message.answer("🌟 <b>Главное меню</b>", parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard(message.from_user.id))


@dp.callback_query(F.data == "back_to_games")
async def back_to_games_callback(callback: CallbackQuery):
    await callback.message.edit_text("🎮 <b>Выберите игру</b>", parse_mode=ParseMode.HTML, reply_markup=get_games_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery):
    await callback.message.edit_text("🌟 <b>Главное меню</b>", parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard(callback.from_user.id))
    await callback.answer()


# ===================== ПЛАТЕЖИ =====================
async def create_stars_invoice(message: Message, user_id: int, amount: int):
    payload = f"starplay_{user_id}_{amount}_{int(datetime.now().timestamp())}"
    await bot.send_invoice(
        chat_id=user_id,
        title="⭐️ Пополнение StarPlay",
        description=f"Пополнение на {amount} Stars",
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Telegram Stars", amount=amount)],
        start_parameter="starplay_deposit"
    )
    pending_payments[payload] = {"user_id": user_id, "amount": amount}


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
    
    # Реферальный бонус
    if user_id in users_referrer:
        referrer = users_referrer[user_id]
        bonus = amount * REFERRAL_BONUS_PERCENT / 100
        if bonus > 0:
            update_balance(referrer, bonus)
            save_transaction(referrer, bonus, "referral_earning", f"10% от пополнения реферала")
            try:
                await bot.send_message(referrer, f"🎉 Реферальный бонус!\n+{format_stars(bonus)}", parse_mode=ParseMode.HTML)
            except:
                pass
    
    await message.answer(
        f"✅ <b>Пополнение выполнено!</b>\n\n"
        f"+{format_stars(amount)}\n"
        f"💰 Новый баланс: {format_stars(new_balance)}",
        parse_mode=ParseMode.HTML
    )


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
        if amount < 1 or amount > 10000:
            await message.answer("❌ Сумма от 1 до 10000 Stars!")
            return
    except:
        await message.answer("❌ Введите число!")
        return
    
    await state.clear()
    await create_stars_invoice(message, message.from_user.id, amount)


# ===================== ОБРАБОТЧИК ОШИБОК =====================
@dp.errors()
async def errors_handler(update, exception):
    logger.error(f"Ошибка: {exception}")
    return True


# ===================== ЗАПУСК =====================
async def main():
    logger.info("🚀 StarPlay Bot запускается...")
    
    # Загружаем резервную копию
    backup = load_backup()
    if backup:
        logger.info("📦 Загружена резервная копия")
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())