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

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    LabeledPrice, Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, PreCheckoutQuery, SuccessfulPayment,
    ReplyKeyboardMarkup, KeyboardButton, FSInputFile
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
    "chat_link": "https://t.me/starplay_chat"
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# ===================== FSM СОСТОЯНИЯ =====================
class GameStates(StatesGroup):
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
    admin_ban_user = State()
    admin_set_verify = State()
    admin_global_bonus = State()
    admin_promo_create = State()
    admin_promo_amount = State()
    admin_promo_activate = State()


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
        "amount": round(amount, 2), "type": tx_type, "details": details,
        "game": game, "timestamp": datetime.now().isoformat()
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
    return random.choice(["🎲", "🎯", "⚡️", "💫", "🌟", "⭐️", "✨", "🎮", "🎰", "🔥"])

def generate_referral_link(user_id: int) -> str:
    code = hashlib.md5(f"starplay_{user_id}_{datetime.now().date()}".encode()).hexdigest()[:8]
    return f"https://t.me/{bot.username}?start=ref_{code}"

def format_time(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} сек"
    elif seconds < 3600:
        return f"{seconds//60} мин {seconds%60} сек"
    return f"{seconds//3600} ч {(seconds%3600)//60} мин"

def create_backup():
    data = {
        "balance": users_balance, "referrer": users_referrer, "referrals": users_referrals,
        "stats": users_stats, "transactions": transactions, "username": users_username,
        "join_date": users_join_date, "ban": users_ban, "ban_reason": users_ban_reason,
        "verify": users_verify, "promo_codes": promo_codes,
        "bot_stats": bot_stats, "bot_settings": bot_settings
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
    builder.button(text="🎟 Промокод")
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
        [InlineKeyboardButton(text="⭐️ 1", callback_data="crash_bet_1"), InlineKeyboardButton(text="⭐️ 5", callback_data="crash_bet_5"), InlineKeyboardButton(text="⭐️ 10", callback_data="crash_bet_10")],
        [InlineKeyboardButton(text="⭐️ 25", callback_data="crash_bet_25"), InlineKeyboardButton(text="⭐️ 50", callback_data="crash_bet_50"), InlineKeyboardButton(text="⭐️ 100", callback_data="crash_bet_100")],
        [InlineKeyboardButton(text="⭐️ 250", callback_data="crash_bet_250"), InlineKeyboardButton(text="⭐️ 500", callback_data="crash_bet_500"), InlineKeyboardButton(text="⭐️ 1000", callback_data="crash_bet_1000")],
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
        [InlineKeyboardButton(text="⭐️ 1", callback_data="mines_bet_1"), InlineKeyboardButton(text="⭐️ 5", callback_data="mines_bet_5"), InlineKeyboardButton(text="⭐️ 10", callback_data="mines_bet_10")],
        [InlineKeyboardButton(text="⭐️ 25", callback_data="mines_bet_25"), InlineKeyboardButton(text="⭐️ 50", callback_data="mines_bet_50"), InlineKeyboardButton(text="⭐️ 100", callback_data="mines_bet_100")],
        [InlineKeyboardButton(text="⭐️ 250", callback_data="mines_bet_250"), InlineKeyboardButton(text="⭐️ 500", callback_data="mines_bet_500"), InlineKeyboardButton(text="⭐️ 1000", callback_data="mines_bet_1000")],
        [InlineKeyboardButton(text="✏️ Своя сумма", callback_data="mines_bet_custom")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_games")]
    ])

def get_mines_board_keyboard(board, revealed, bet, multiplier) -> InlineKeyboardMarkup:
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
        [InlineKeyboardButton(text="⭐️ 1", callback_data="slots_bet_1"), InlineKeyboardButton(text="⭐️ 5", callback_data="slots_bet_5"), InlineKeyboardButton(text="⭐️ 10", callback_data="slots_bet_10")],
        [InlineKeyboardButton(text="⭐️ 25", callback_data="slots_bet_25"), InlineKeyboardButton(text="⭐️ 50", callback_data="slots_bet_50"), InlineKeyboardButton(text="⭐️ 100", callback_data="slots_bet_100")],
        [InlineKeyboardButton(text="⭐️ 250", callback_data="slots_bet_250"), InlineKeyboardButton(text="⭐️ 500", callback_data="slots_bet_500"), InlineKeyboardButton(text="⭐️ 1000", callback_data="slots_bet_1000")],
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
        [InlineKeyboardButton(text="⭐️ 10", callback_data="deposit_10"), InlineKeyboardButton(text="⭐️ 50", callback_data="deposit_50"), InlineKeyboardButton(text="⭐️ 100", callback_data="deposit_100")],
        [InlineKeyboardButton(text="⭐️ 250", callback_data="deposit_250"), InlineKeyboardButton(text="⭐️ 500", callback_data="deposit_500"), InlineKeyboardButton(text="⭐️ 1000", callback_data="deposit_1000")],
        [InlineKeyboardButton(text="⭐️ 2500", callback_data="deposit_2500"), InlineKeyboardButton(text="⭐️ 5000", callback_data="deposit_5000"), InlineKeyboardButton(text="⭐️ 10000", callback_data="deposit_10000")],
        [InlineKeyboardButton(text="✏️ Другая сумма", callback_data="deposit_custom")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])


# ===================== ОСНОВНЫЕ КОМАНДЫ =====================
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    
    if bot_settings["maintenance_mode"] and not is_admin(username):
        await message.answer("🔧 Бот на обслуживании. Зайдите позже.", parse_mode=ParseMode.HTML)
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
        f"{get_random_emoji()} <b>Лучшее казино в Telegram!</b>\n\n"
        f"<b>🎮 Игры:</b>\n📈 CRASH — до x{CRASH_MAX_MULTIPLIER}\n💣 MINES — до x18\n🎰 SLOTS — до x50\n\n"
        f"<b>💫 Как начать:</b>\n1️⃣ Пополните баланс\n2️⃣ Выберите игру\n3️⃣ Выигрывайте!\n\n"
        f"<b>🎁 Бонусы:</b>\n• Ежедневный бонус до {DAILY_BONUS_MAX} Stars\n• Реферальная программа: +{REFERRAL_BONUS_PERCENT}%\n• Промокоды на бонусы\n\n"
        f"👇 <i>Используйте кнопки!</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(user_id)
    )


# ===================== ГЛАВНЫЕ КНОПКИ =====================
@dp.message(F.text == "💰 Баланс")
async def balance_reply(message: Message):
    user_id = message.from_user.id
    await message.answer(f"💰 <b>Ваш баланс:</b>\n\n{format_stars(get_user_balance(user_id))}", parse_mode=ParseMode.HTML)

@dp.message(F.text == "⭐️ Пополнить")
async def deposit_reply(message: Message):
    await message.answer("⭐️ <b>Пополнение баланса</b>\n\n💰 Выберите сумму для пополнения через Telegram Stars:", parse_mode=ParseMode.HTML, reply_markup=get_deposit_keyboard())

@dp.message(F.text == "🎮 Игры")
async def games_reply(message: Message):
    await message.answer("🎮 <b>Выберите игру</b>\n\n📈 CRASH — Растущий множитель\n💣 MINES — Найди сокровища\n🎰 SLOTS — Классические слоты", parse_mode=ParseMode.HTML, reply_markup=get_games_keyboard())

@dp.message(F.text == "👥 Рефералы")
async def referrals_reply(message: Message):
    user_id = message.from_user.id
    ref_link = generate_referral_link(user_id)
    stats = get_user_stats(user_id)
    referrals_list = users_referrals.get(user_id, [])
    
    referrals_text = ""
    for ref_id in referrals_list[:10]:
        ref_name = users_username.get(ref_id, str(ref_id))
        ref_balance = get_user_balance(ref_id)
        referrals_text += f"• @{ref_name} — {format_stars(ref_balance)}\n"
    
    if not referrals_text:
        referrals_text = "Пока нет рефералов\n💡 Поделитесь ссылкой с друзьями!"
    
    text = (
        f"👥 <b>РЕФЕРАЛЬНАЯ ПРОГРАММА</b>\n\n"
        f"🏆 <b>Ваша статистика:</b>\n"
        f"├ Приглашено: <b>{stats['referral_count']}</b> чел.\n"
        f"├ Заработано: {format_stars(stats['referral_earned'])}\n"
        f"└ Доступно к выводу: {format_stars(stats['referral_earned'])}\n\n"
        f"<b>📋 Как это работает:</b>\n"
        f"• Друг регистрируется по вашей ссылке\n"
        f"• Вы получаете +{REFERRAL_INVITE_BONUS} Stars\n"
        f"• Друг получает +{REFERRAL_SIGNUP_BONUS} Stars\n"
        f"• Вы получаете <b>{REFERRAL_BONUS_PERCENT}%</b> от каждого пополнения друга\n\n"
        f"<b>🔗 Ваша реферальная ссылка:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"<b>👥 Ваши рефералы:</b>\n{referrals_text}\n\n"
        f"💡 <b>Совет:</b> Поделитесь ссылкой в соцсетях и с друзьями!\n"
        f"📊 За каждого активного реферала вы получаете постоянный доход!"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 ПОДЕЛИТЬСЯ ССЫЛКОЙ", url=f"https://t.me/share/url?url={ref_link}&text=StarPlay — лучшие игры с реальными выигрышами! Присоединяйся по моей ссылке!")],
        [InlineKeyboardButton(text="📊 СТАТИСТИКА РЕФЕРАЛОВ", callback_data="referral_stats")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="main_menu")]
    ])
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

@dp.callback_query(F.data == "referral_stats")
async def referral_stats(callback: CallbackQuery):
    user_id = callback.from_user.id
    referrals = users_referrals.get(user_id, [])
    
    total_deposits = 0
    total_earned = 0
    
    for ref_id in referrals:
        for tx in transactions.get(ref_id, []):
            if tx["type"] == "deposit":
                total_deposits += tx["amount"]
                total_earned += tx["amount"] * REFERRAL_BONUS_PERCENT / 100
    
    text = (
        f"📊 <b>ДЕТАЛЬНАЯ СТАТИСТИКА РЕФЕРАЛОВ</b>\n\n"
        f"👥 Всего рефералов: {len(referrals)}\n"
        f"💰 Общая сумма пополнений: {format_stars(total_deposits)}\n"
        f"🎁 Заработано с пополнений: {format_stars(total_earned)}\n"
        f"🎉 Реферальный бонус за регистрацию: {format_stars(len(referrals) * REFERRAL_INVITE_BONUS)}\n\n"
        f"💡 Чем больше рефералов — тем больше ваш пассивный доход!"
    )
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД К РЕФЕРАЛАМ", callback_data="back_to_referrals")]
    ]))
    await callback.answer()

@dp.callback_query(F.data == "back_to_referrals")
async def back_to_referrals(callback: CallbackQuery):
    user_id = callback.from_user.id
    await referrals_reply(callback.message)
    await callback.answer()

@dp.message(F.text == "🏆 Топ")
async def top_reply(message: Message):
    # Топ по балансу с верификацией
    sorted_users = sorted(users_balance.items(), key=lambda x: x[1], reverse=True)[:20]
    
    if not sorted_users:
        await message.answer("🏆 Пока нет игроков в рейтинге!", parse_mode=ParseMode.HTML)
        return
    
    top_text = "🏆 <b>ТОП-20 ПО БАЛАНСУ</b>\n\n"
    for idx, (uid, bal) in enumerate(sorted_users, 1):
        if users_ban.get(uid, False):
            continue
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
        verify_icon = "✅" if users_verify.get(uid, False) else "📝"
        name = users_username.get(uid, str(uid))
        top_text += f"{medal} {verify_icon} @{name} — {bal:.2f} ⭐️\n"
    
    # Топ по победам
    sorted_wins = sorted(users_stats.items(), key=lambda x: x[1].get("games_won", 0), reverse=True)[:20]
    top_text += "\n🏆 <b>ТОП-20 ПО ПОБЕДАМ</b>\n\n"
    for idx, (uid, stats) in enumerate(sorted_wins, 1):
        if users_ban.get(uid, False):
            continue
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
        verify_icon = "✅" if users_verify.get(uid, False) else "📝"
        name = users_username.get(uid, str(uid))
        wins = stats.get("games_won", 0)
        top_text += f"{medal} {verify_icon} @{name} — {wins} 🏆\n"
    
    await message.answer(top_text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "📊 Профиль")
async def profile_reply(message: Message):
    uid = message.from_user.id
    stats = get_user_stats(uid)
    win_rate = (stats['games_won'] / max(stats['games_played'], 1)) * 100
    
    verify_status = "✅ Верифицирован" if users_verify.get(uid, False) else "📝 Не верифицирован"
    ban_status = "🚫 Заблокирован" if users_ban.get(uid, False) else "✅ Активен"
    
    text = (
        f"👤 <b>ПРОФИЛЬ ИГРОКА</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👤 Username: @{message.from_user.username or 'не установлен'}\n"
        f"📅 Регистрация: {users_join_date.get(uid, 'неизвестно')}\n"
        f"✅ Статус: {verify_status}\n"
        f"🔒 Бан: {ban_status}\n\n"
        f"💰 <b>Баланс:</b> {format_stars(get_user_balance(uid))}\n\n"
        f"📊 <b>ОБЩАЯ СТАТИСТИКА:</b>\n"
        f"├ 🎮 Сыграно игр: {stats['games_played']}\n"
        f"├ 🏆 Побед: {stats['games_won']}\n"
        f"├ 📈 Винрейт: {win_rate:.1f}%\n"
        f"├ 💎 Выиграно: {format_stars(stats['total_won'])}\n"
        f"└ 💸 Проиграно: {format_stars(stats['total_lost'])}\n\n"
        f"📈 <b>СТАТИСТИКА ПО ИГРАМ:</b>\n"
        f"├ 📈 CRASH: {stats['crash_wins']}/{stats['crash_games']} побед\n"
        f"├ 💣 MINES: {stats['mines_wins']}/{stats['mines_games']} побед\n"
        f"└ 🎰 SLOTS: {stats['slots_wins']}/{stats['slots_games']} побед\n\n"
        f"👥 <b>РЕФЕРАЛЫ:</b>\n"
        f"├ Приглашено: {stats['referral_count']} чел.\n"
        f"├ Заработано: {format_stars(stats['referral_earned'])}\n"
        f"└ Бонус за регистрацию: {format_stars(stats['referral_count'] * REFERRAL_INVITE_BONUS)}\n\n"
        f"🎁 <b>ЕЖЕДНЕВНЫЙ БОНУС:</b>\n"
        f"├ Получено бонусов: {stats['daily_bonus_count']}\n"
        f"└ Текущий стрик: {stats['daily_bonus_streak']} дней\n\n"
        f"💎 <b>ЛУЧШИЕ РЕЗУЛЬТАТЫ:</b>\n"
        f"├ CRASH: x{stats['crash_best_multiplier']:.2f}\n"
        f"├ MINES: x{stats['mines_best_multiplier']:.1f}\n"
        f"└ SLOTS: x{stats['slots_best_multiplier']}\n\n"
        f"{get_random_emoji()} <i>Продолжайте играть и улучшайте свои результаты!</i>"
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
    
    await message.answer(f"🎉 <b>ЕЖЕДНЕВНЫЙ БОНУС ПОЛУЧЕН!</b>\n\n+{format_stars(bonus)}\n📅 Стрик: {streak} дней\n💰 Новый баланс: {format_stars(get_user_balance(user_id))}\n\n💡 Заходите завтра — бонус будет больше!", parse_mode=ParseMode.HTML)

@dp.message(F.text == "🎟 Промокод")
async def promo_code_reply(message: Message, state: FSMContext):
    await state.set_state(GameStates.admin_promo_activate)
    await message.answer("🎟 <b>АКТИВАЦИЯ ПРОМОКОДА</b>\n\nВведите промокод для получения бонуса:\n\n💡 Пример: <code>WELCOME100</code>", parse_mode=ParseMode.HTML)

@dp.message(GameStates.admin_promo_activate)
async def activate_promo(message: Message, state: FSMContext):
    user_id = message.from_user.id
    code = message.text.strip().upper()
    
    if code in promo_codes:
        promo = promo_codes[code]
        if promo.get("uses", 0) >= promo.get("max_uses", 100):
            await message.answer("❌ Промокод уже использован максимальное количество раз!")
            await state.clear()
            return
        
        if promo.get("expires") and datetime.now() > datetime.fromisoformat(promo["expires"]):
            await message.answer("❌ Срок действия промокода истёк!")
            await state.clear()
            return
        
        promo["uses"] = promo.get("uses", 0) + 1
        amount = promo["amount"]
        update_balance(user_id, amount)
        save_transaction(user_id, amount, "promo_bonus", f"Промокод: {code}")
        
        await message.answer(f"✅ <b>ПРОМОКОД АКТИВИРОВАН!</b>\n\n🎁 Вы получили: {format_stars(amount)}\n💰 Новый баланс: {format_stars(get_user_balance(user_id))}", parse_mode=ParseMode.HTML)
    else:
        await message.answer("❌ Неверный промокод! Попробуйте другой.", parse_mode=ParseMode.HTML)
    
    await state.clear()

@dp.message(F.text == "❓ Помощь")
async def help_reply(message: Message):
    await message.answer(
        f"❓ <b>ПОМОЩЬ ПО БОТУ</b>\n\n"
        f"<b>🎮 ИГРЫ:</b>\n"
        f"📈 CRASH — Ставка растёт. Заберите выигрыш до взрыва!\n"
        f"💣 MINES — Открывайте клетки с 💎, избегайте 💣\n"
        f"🎰 SLOTS — Классические слоты. Собирайте комбинации!\n\n"
        f"<b>💰 БАЛАНС:</b>\n"
        f"• Пополнение через Telegram Stars\n"
        f"• Минимальная ставка: {MIN_BET} Star\n"
        f"• Максимальная ставка: {MAX_BET} Stars\n\n"
        f"<b>👥 РЕФЕРАЛЫ:</b>\n"
        f"• Пригласите друга → +{REFERRAL_INVITE_BONUS} Stars\n"
        f"• Друг получает → +{REFERRAL_SIGNUP_BONUS} Stars\n"
        f"• Вы получаете {REFERRAL_BONUS_PERCENT}% от пополнений друга\n\n"
        f"<b>🎁 БОНУСЫ:</b>\n"
        f"• Ежедневный бонус: до {DAILY_BONUS_MAX} Stars\n"
        f"• Промокоды: следите за новостями!\n\n"
        f"<b>📞 КОНТАКТЫ:</b>\n"
        f"• Чат поддержки: {bot_settings['chat_link']}\n"
        f"• Администратор: @{ADMIN_USERNAMES[0]}",
        parse_mode=ParseMode.HTML
    )


# ===================== ИГРА CRASH =====================
async def run_crash_game(user_id: int, game_msg: Message, bet: float):
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
                f"📈 <b>CRASH</b>\n\n💰 Ставка: {format_stars(bet)}\n📈 Множитель: <b>x{multiplier:.2f}</b>\n💎 Выигрыш: {format_stars(bet * multiplier)}\n\n⚠️ Заберите до взрыва!",
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
        save_transaction(user_id, -bet, "game_loss", f"Краш на x{multiplier:.2f}", "crash")
        bot_stats["crash_games_played"] += 1
        crash_history.append({"multiplier": multiplier, "player": user_id, "bet": bet, "win": 0})
        if len(crash_history) > 100:
            crash_history.pop(0)
        del active_crash[user_id]
        try:
            await game_msg.edit_text(
                f"💥 <b>CRASH — ВЗРЫВ!</b>\n\n💰 Ставка: {format_stars(bet)}\n📈 Множитель: x{multiplier:.2f}\n\n😢 Ставка сгорела!\n💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_games_keyboard()
            )
        except:
            pass

@dp.message(F.text == "📈 CRASH")
async def crash_start(message: Message, state: FSMContext):
    if message.from_user.id in active_crash:
        await message.answer("⚠️ У вас уже есть активная игра!", parse_mode=ParseMode.HTML)
        return
    await state.set_state(GameStates.crash_bet)
    await message.answer("📈 <b>CRASH</b>\n\nВыберите сумму ставки:", parse_mode=ParseMode.HTML, reply_markup=get_crash_bet_keyboard())

@dp.callback_query(F.data.startswith("crash_bet_"))
async def crash_bet(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    bet_str = callback.data.split("_")[-1]
    
    if bet_str == "custom":
        await callback.message.answer("✏️ Введите сумму (1-10000):", parse_mode=ParseMode.HTML)
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
        f"📈 <b>CRASH</b>\n\n💰 Ставка: {format_stars(bet)}\n📈 Множитель: x1.00\n💎 Выигрыш: {format_stars(bet)}\n\n⚠️ Заберите до взрыва!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_crash_game_keyboard()
    )
    asyncio.create_task(run_crash_game(user_id, game_msg, bet))
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
    save_transaction(user_id, win, "game_win", f"x{game['multiplier']:.2f}", "crash")
    bot_stats["crash_games_played"] += 1
    crash_history.append({"multiplier": game["multiplier"], "player": user_id, "bet": game["bet"], "win": win})
    if len(crash_history) > 100:
        crash_history.pop(0)
    del active_crash[user_id]
    await state.clear()
    
    await callback.message.answer(
        f"💰 <b>ВЫ ЗАБРАЛИ ВЫИГРЫШ!</b>\n\n"
        f"✅ <b>Поздравляем!</b> Вы успели забрать выигрыш до взрыва!\n\n"
        f"📊 <b>Детали игры:</b>\n"
        f"├ Ставка: {format_stars(game['bet'])}\n"
        f"├ Множитель: <b>x{game['multiplier']:.2f}</b>\n"
        f"└ Выигрыш: <b>{format_stars(win)}</b>\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}\n\n"
        f"🎮 <b>Хотите сыграть ещё?</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📈 ИГРАТЬ СНОВА", callback_data="crash_play_again")],
            [InlineKeyboardButton(text="🎮 ДРУГАЯ ИГРА", callback_data="back_to_games")]
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
    if message.from_user.id in active_mines:
        await message.answer("⚠️ У вас уже есть активная игра!", parse_mode=ParseMode.HTML)
        return
    await state.set_state(GameStates.mines_bet)
    await message.answer("💣 <b>MINES</b>\n\n💎 Ищите сокровища, избегайте мин!\n💰 Выберите сумму ставки:", parse_mode=ParseMode.HTML, reply_markup=get_mines_bet_keyboard())

@dp.callback_query(F.data.startswith("mines_bet_"))
async def mines_bet(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    bet_str = callback.data.split("_")[-1]
    
    if bet_str == "custom":
        await callback.message.answer("✏️ Введите сумму (1-10000):", parse_mode=ParseMode.HTML)
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
        "bet": bet, "board": board, "revealed": [[False] * MINES_BOARD_SIZE for _ in range(MINES_BOARD_SIZE)],
        "multiplier": 1.0, "cells_opened": 0
    }
    
    await state.set_state(GameStates.mines_playing)
    max_cells = MINES_BOARD_SIZE * MINES_BOARD_SIZE - MINES_MINES_COUNT
    await callback.message.edit_text(
        f"💣 <b>MINES</b>\n\n💰 Ставка: {format_stars(bet)}\n✨ Множитель: x1.0\n📦 Осталось клеток: {max_cells}\n💎 Текущий выигрыш: {format_stars(bet)}\n\n👇 Открывайте клетки, находите 💎 и увеличивайте множитель!",
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
        mines_history.append({"multiplier": game["multiplier"], "player": user_id, "bet": game["bet"], "win": 0})
        if len(mines_history) > 100:
            mines_history.pop(0)
        del active_mines[user_id]
        await callback.message.edit_text(
            f"💥 <b>MINES — ПРОИГРЫШ!</b>\n\n💣 Вы наступили на мину!\n💰 Ставка: {format_stars(game['bet'])} — проиграна\n💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
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
            save_transaction(user_id, current_win, "game_win", f"x{game['multiplier']:.1f}", "mines")
            bot_stats["mines_games_played"] += 1
            mines_history.append({"multiplier": game["multiplier"], "player": user_id, "bet": game["bet"], "win": current_win})
            if len(mines_history) > 100:
                mines_history.pop(0)
            del active_mines[user_id]
            await callback.message.edit_text(
                f"🎉 <b>MINES — ПОБЕДА!</b>\n\n💎 Вы нашли все сокровища!\n💰 Ставка: {format_stars(game['bet'])}\n✨ Множитель: x{game['multiplier']:.2f}\n🏆 Выигрыш: {format_stars(current_win)}\n💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_games_keyboard()
            )
        else:
            cells_left = max_cells - game["cells_opened"]
            await callback.message.edit_text(
                f"💣 <b>MINES</b>\n\n💰 Ставка: {format_stars(game['bet'])}\n✨ Множитель: x{game['multiplier']:.2f}\n📦 Осталось клеток: {cells_left}\n💎 Текущий выигрыш: {format_stars(current_win)}\n🎯 Максимальный выигрыш: {format_stars(game['bet'] * (1.2 ** max_cells))}\n\n✅ <b>Найдена 💎! Множитель увеличен!</b>\n\n👇 Продолжайте открывать клетки!",
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
    save_transaction(user_id, win, "game_win", f"x{game['multiplier']:.1f}", "mines")
    bot_stats["mines_games_played"] += 1
    mines_history.append({"multiplier": game["multiplier"], "player": user_id, "bet": game["bet"], "win": win})
    if len(mines_history) > 100:
        mines_history.pop(0)
    del active_mines[user_id]
    
    await callback.message.answer(
        f"💰 <b>ВЫ ЗАБРАЛИ ВЫИГРЫШ!</b>\n\n"
        f"✅ <b>Поздравляем!</b> Вы успешно забрали выигрыш!\n\n"
        f"📊 <b>Детали игры:</b>\n"
        f"├ Ставка: {format_stars(game['bet'])}\n"
        f"├ Множитель: <b>x{game['multiplier']:.2f}</b>\n"
        f"├ Открыто клеток: {game['cells_opened']}/20\n"
        f"└ Выигрыш: <b>{format_stars(win)}</b>\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}\n\n"
        f"🎮 <b>Хотите сыграть ещё?</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💣 ИГРАТЬ СНОВА", callback_data="mines_play_again")],
            [InlineKeyboardButton(text="🎮 ДРУГАЯ ИГРА", callback_data="back_to_games")]
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
    await state.set_state(GameStates.slots_bet)
    await message.answer(
        "🎰 <b>SLOTS — Классические слоты</b>\n\n"
        "📋 <b>Выигрышные комбинации:</b>\n"
        "🍒🍒🍒 → x5 | 🍊🍊🍊 → x7 | 🍋🍋🍋 → x10\n"
        "💎💎💎 → x15 | 7️⃣7️⃣7️⃣ → x25 | 🎰🎰🎰 → x50\n"
        "⭐️⭐️⭐️ → x30 | 💫💫💫 → x20\n"
        "• Любая пара → x1.5\n\n"
        "💰 Выберите сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_slots_bet_keyboard()
    )

@dp.callback_query(F.data.startswith("slots_bet_"))
async def slots_bet(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    bet_str = callback.data.split("_")[-1]
    
    if bet_str == "custom":
        await callback.message.answer("✏️ Введите сумму (1-10000):", parse_mode=ParseMode.HTML)
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
        f"🎰 <b>SLOTS</b>\n\n💰 Ставка: {format_stars(bet)}\n🎰 Нажмите «КРУТИТЬ», чтобы начать игру!",
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
        save_transaction(user_id, win, "game_win", f"x{mult}", "slots")
        result_text = f"🎉 <b>ДЖЕКПОТ!</b> x{mult}\n🏆 Выигрыш: +{format_stars(win - bet)}"
    elif reel1 == reel2 or reel1 == reel3 or reel2 == reel3:
        win = bet * 1.5
        update_balance(user_id, win)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["slots_games"] += 1
        stats["slots_wins"] += 1
        stats["total_won"] += win
        save_transaction(user_id, win, "game_win", f"Пара", "slots")
        result_text = f"🎉 <b>ПАРА!</b> x1.5\n🏆 Выигрыш: +{format_stars(win - bet)}"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["slots_games"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", f"Проигрыш", "slots")
        result_text = f"😢 <b>Не повезло...</b>\n💸 Потеряно: {format_stars(bet)}"
    
    bot_stats["slots_games_played"] += 1
    slots_history.append({"combo": f"{reel1}{reel2}{reel3}", "player": user_id, "bet": bet, "win": win if 'win' in dir() else 0})
    if len(slots_history) > 100:
        slots_history.pop(0)
    
    await callback.message.answer(
        f"🎰 <b>SLOTS — РЕЗУЛЬТАТ</b>\n\n"
        f"┌─────┬─────┬─────┐\n"
        f"│  {reel1}  │  {reel2}  │  {reel3}  │\n"
        f"└─────┴─────┴─────┘\n\n"
        f"💰 Ставка: {format_stars(bet)}\n\n"
        f"{result_text}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}\n\n"
        f"🎰 <b>Хотите крутить ещё?</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎰 КРУТИТЬ ЕЩЁ", callback_data="slots_spin")],
            [InlineKeyboardButton(text="🎮 ДРУГАЯ ИГРА", callback_data="back_to_games")]
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
    if not is_admin(message.from_user.username or ""):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    await message.answer("👑 <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n\n📊 Управление ботом и пользователями\n\n👇 Выберите действие:", parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())

@dp.message(F.text == "📊 Статистика")
async def admin_stats(message: Message):
    if not is_admin(message.from_user.username or ""):
        return
    uptime = datetime.now() - datetime.fromisoformat(bot_stats["server_start_time"])
    await message.answer(
        f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
        f"<b>👥 ПОЛЬЗОВАТЕЛИ:</b>\n"
        f"├ Всего: {bot_stats['total_users']}\n"
        f"├ Забанено: {len([u for u, b in users_ban.items() if b])}\n"
        f"└ Верифицировано: {len([u for u, v in users_verify.items() if v])}\n\n"
        f"<b>💰 ФИНАНСЫ:</b>\n"
        f"├ Общий баланс: {format_stars(sum(users_balance.values()))}\n"
        f"├ Всего ставок: {bot_stats['total_bets']}\n"
        f"├ Объём ставок: {format_stars(bot_stats['total_wagered'])}\n"
        f"├ Выплачено: {format_stars(bot_stats['total_paid'])}\n"
        f"├ Прибыль бота: {format_stars(bot_stats['total_profit'])}\n"
        f"├ Пополнений: {bot_stats['total_deposits']}\n"
        f"└ Сумма пополнений: {format_stars(bot_stats['total_deposit_amount'])}\n\n"
        f"<b>🎮 ИГРЫ:</b>\n"
        f"├ CRASH: {bot_stats['crash_games_played']} игр\n"
        f"├ MINES: {bot_stats['mines_games_played']} игр\n"
        f"└ SLOTS: {bot_stats['slots_games_played']} игр\n\n"
        f"<b>🕐 СИСТЕМА:</b>\n"
        f"├ Аптайм: {format_time(int(uptime.total_seconds()))}\n"
        f"└ Запуск: {bot_stats['server_start_time'][:19]}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_main_keyboard()
    )

@dp.message(F.text == "💰 Изменить баланс")
async def admin_change_balance_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.username or ""):
        return
    await state.set_state(GameStates.admin_find_user)
    await message.answer("💰 <b>ИЗМЕНЕНИЕ БАЛАНСА</b>\n\nВведите username (без @) или ID пользователя:", parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True))

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
        f"👤 <b>ПОЛЬЗОВАТЕЛЬ:</b> @{input_text}\n"
        f"💰 <b>ТЕКУЩИЙ БАЛАНС:</b> {format_stars(get_user_balance(user_id))}\n\n"
        f"📝 <b>ВВЕДИТЕ СУММУ ИЗМЕНЕНИЯ:</b>\n"
        f"• +100 — добавить 100 Stars\n"
        f"• -50 — снять 50 Stars\n\n"
        f"<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML
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
            await bot.send_message(target_user, f"👑 <b>Администратор изменил баланс!</b>\n{'+' if amount>0 else ''}{format_stars(amount)}\n💰 Новый баланс: {format_stars(new_balance)}", parse_mode=ParseMode.HTML)
        except:
            pass
        save_transaction(target_user, amount, "admin_change", f"Админ: {amount}", "admin")
        await state.clear()
        await message.answer(f"✅ <b>БАЛАНС ИЗМЕНЁН!</b>\n\n👤 @{target_username}\n💰 Изменение: {format_stars(amount)}\n💰 Новый баланс: {format_stars(new_balance)}", parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())
    except:
        await message.answer("❌ Введите число!")

@dp.message(F.text == "📢 Рассылка")
async def admin_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.username or ""):
        return
    await state.set_state(GameStates.admin_send_broadcast)
    await message.answer("📢 <b>РАССЫЛКА</b>\n\nВведите сообщение для рассылки всем пользователям:\n\n<i>Для отмены отправьте /cancel</i>", parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True))

@dp.message(GameStates.admin_send_broadcast)
async def admin_broadcast_send(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Рассылка отменена.", reply_markup=get_admin_main_keyboard())
        return
    
    success = 0
    fail = 0
    progress_msg = await message.answer("📢 Начинаю рассылку...⏳")
    
    for user_id in users_balance.keys():
        if users_ban.get(user_id, False):
            continue
        try:
            await bot.send_message(user_id, f"📢 <b>РАССЫЛКА ОТ АДМИНИСТРАТОРА</b>\n\n{message.text}", parse_mode=ParseMode.HTML)
            success += 1
        except:
            fail += 1
        await asyncio.sleep(0.05)
    
    await state.clear()
    await progress_msg.edit_text(f"✅ <b>РАССЫЛКА ЗАВЕРШЕНА</b>\n\n📨 Доставлено: {success}\n❌ Ошибок: {fail}", reply_markup=get_admin_main_keyboard())

@dp.message(F.text == "👥 Пользователи")
async def admin_users_list(message: Message):
    if not is_admin(message.from_user.username or ""):
        return
    users_list = []
    for uid, uname in users_username.items():
        ban_icon = "🚫" if users_ban.get(uid, False) else "✅"
        verify_icon = "✓" if users_verify.get(uid, False) else "○"
        balance = get_user_balance(uid)
        users_list.append(f"{ban_icon}{verify_icon} @{uname or uid} — {balance:.2f}⭐️")
    
    text = "👥 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ</b>\n\n" + "\n".join(users_list[:50])
    if len(users_list) > 50:
        text += f"\n\n... и ещё {len(users_list) - 50} пользователей"
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())

@dp.message(F.text == "🔨 Бан/Разбан")
async def admin_ban(message: Message, state: FSMContext):
    if not is_admin(message.from_user.username or ""):
        return
    await state.set_state(GameStates.admin_ban_user)
    await message.answer("🔨 <b>БАН/РАЗБАН</b>\n\nВведите username (без @) или ID пользователя:\n\n💡 Пользователь будет забанен или разбанен", parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True))

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
    status = "ЗАБЛОКИРОВАН" if users_ban[user_id] else "РАЗБЛОКИРОВАН"
    try:
        await bot.send_message(user_id, f"🚫 <b>Ваш аккаунт {status}!</b>\n\nПричина: {users_ban_reason[user_id] if users_ban[user_id] else 'Администратор разблокировал аккаунт'}", parse_mode=ParseMode.HTML)
    except:
        pass
    await state.clear()
    await message.answer(f"✅ <b>ПОЛЬЗОВАТЕЛЬ {status}!</b>\n\n👤 @{input_text}", reply_markup=get_admin_main_keyboard())

@dp.message(F.text == "✅ Верификация")
async def admin_verify(message: Message, state: FSMContext):
    if not is_admin(message.from_user.username or ""):
        return
    await state.set_state(GameStates.admin_set_verify)
    await message.answer("✅ <b>ВЕРИФИКАЦИЯ</b>\n\nВведите username (без @) или ID пользователя для верификации:", parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True))

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
    status = "ВЕРИФИЦИРОВАН" if users_verify[user_id] else "ДЕВЕРИФИЦИРОВАН"
    try:
        await bot.send_message(user_id, f"✅ <b>Ваш аккаунт {status}!</b>", parse_mode=ParseMode.HTML)
    except:
        pass
    await state.clear()
    await message.answer(f"✅ <b>ПОЛЬЗОВАТЕЛЬ {status}!</b>\n\n👤 @{input_text}", reply_markup=get_admin_main_keyboard())

@dp.message(F.text == "🎁 Создать промокод")
async def admin_promo_create(message: Message, state: FSMContext):
    if not is_admin(message.from_user.username or ""):
        return
    await state.set_state(GameStates.admin_promo_create)
    await message.answer("🎁 <b>СОЗДАНИЕ ПРОМОКОДА</b>\n\nВведите название промокода (латиницей, цифры):", parse_mode=ParseMode.HTML)

@dp.message(GameStates.admin_promo_create)
async def admin_promo_code(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    await state.update_data(promo_code=code)
    await state.set_state(GameStates.admin_promo_amount)
    await message.answer(f"📝 Введите сумму бонуса для промокода <code>{code}</code>:", parse_mode=ParseMode.HTML)

@dp.message(GameStates.admin_promo_amount)
async def admin_promo_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
        data = await state.get_data()
        code = data.get("promo_code")
        promo_codes[code] = {
            "amount": amount, "uses": 0, "max_uses": 100,
            "created": datetime.now().isoformat(),
            "expires": (datetime.now() + timedelta(days=30)).isoformat()
        }
        await state.clear()
        await message.answer(
            f"✅ <b>ПРОМОКОД СОЗДАН!</b>\n\n"
            f"📌 Код: <code>{code}</code>\n"
            f"💰 Сумма: {format_stars(amount)}\n"
            f"📅 Действует до: {(datetime.now() + timedelta(days=30)).strftime('%d.%m.%Y')}\n"
            f"🎟 Макс. использований: 100",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_main_keyboard()
        )
    except:
        await message.answer("❌ Введите число!")

@dp.message(F.text == "🎲 Глобальный бонус")
async def admin_global_bonus(message: Message, state: FSMContext):
    if not is_admin(message.from_user.username or ""):
        return
    await state.set_state(GameStates.admin_global_bonus)
    await message.answer("🎲 <b>ГЛОБАЛЬНЫЙ БОНУС</b>\n\nВведите сумму бонуса для ВСЕХ пользователей:", parse_mode=ParseMode.HTML)

@dp.message(GameStates.admin_global_bonus)
async def admin_global_bonus_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
        count = 0
        progress_msg = await message.answer("🎁 Выдаю глобальный бонус...⏳")
        
        for user_id in users_balance.keys():
            if not users_ban.get(user_id, False):
                update_balance(user_id, amount)
                try:
                    await bot.send_message(user_id, f"🎉 <b>ГЛОБАЛЬНЫЙ БОНУС ОТ АДМИНИСТРАТОРА!</b>\n\n+{format_stars(amount)}\n💰 Новый баланс: {format_stars(get_user_balance(user_id))}", parse_mode=ParseMode.HTML)
                except:
                    pass
                count += 1
            await asyncio.sleep(0.05)
        
        await state.clear()
        await progress_msg.edit_text(f"✅ <b>ГЛОБАЛЬНЫЙ БОНУС ВЫДАН!</b>\n\n🎁 Сумма: {format_stars(amount)}\n👥 Получили: {count} пользователей", reply_markup=get_admin_main_keyboard())
    except:
        await message.answer("❌ Введите число!")

@dp.message(F.text == "💾 Сохранить данные")
async def admin_save_data(message: Message):
    if not is_admin(message.from_user.username or ""):
        return
    if create_backup():
        await message.answer("✅ <b>ДАННЫЕ СОХРАНЕНЫ!</b>\n\n📁 Файл: backup.json\n💾 Размер: {} байт".format(os.path.getsize("backup.json") if os.path.exists("backup.json") else 0), parse_mode=ParseMode.HTML, reply_markup=get_admin_main_keyboard())
    else:
        await message.answer("❌ Ошибка сохранения данных!", reply_markup=get_admin_main_keyboard())

@dp.message(F.text == "🔙 В главное меню")
async def back_to_main(message: Message):
    await message.answer("🌟 <b>ГЛАВНОЕ МЕНЮ</b>", parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard(message.from_user.id))

@dp.callback_query(F.data == "back_to_games")
async def back_to_games(callback: CallbackQuery):
    await callback.message.edit_text("🎮 <b>ВЫБЕРИТЕ ИГРУ</b>\n\n📈 CRASH — Растущий множитель\n💣 MINES — Найди сокровища\n🎰 SLOTS — Классические слоты", parse_mode=ParseMode.HTML, reply_markup=get_games_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery):
    await callback.message.edit_text("🌟 <b>ГЛАВНОЕ МЕНЮ</b>", parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard(callback.from_user.id))
    await callback.answer()


# ===================== ПЛАТЕЖИ =====================
async def create_stars_invoice(message: Message, user_id: int, amount: int):
    payload = f"starplay_{user_id}_{amount}_{int(datetime.now().timestamp())}"
    await bot.send_invoice(
        chat_id=user_id, title="⭐️ Пополнение StarPlay", description=f"Пополнение на {amount} Stars",
        payload=payload, provider_token="", currency="XTR", prices=[LabeledPrice(label="Stars", amount=amount)],
        start_parameter="starplay_deposit"
    )
    pending_payments[payload] = {"user_id": user_id, "amount": amount}

@dp.pre_checkout_query()
async def process_pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True) if query.invoice_payload in pending_payments else await query.answer(ok=False, error_message="Ошибка платежа")

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
            save_transaction(referrer, bonus, "referral_earning", f"10% с пополнения")
            try:
                await bot.send_message(referrer, f"🎉 <b>РЕФЕРАЛЬНЫЙ БОНУС!</b>\n\nВаш реферал пополнил баланс!\n💰 Сумма: {format_stars(amount)}\n🎁 Ваш бонус: +{format_stars(bonus)}", parse_mode=ParseMode.HTML)
            except:
                pass
    
    await message.answer(f"✅ <b>ПОПОЛНЕНИЕ ВЫПОЛНЕНО!</b>\n\n+{format_stars(amount)}\n💰 Новый баланс: {format_stars(new_balance)}\n\n🎮 Приятной игры!", parse_mode=ParseMode.HTML)

@dp.callback_query(F.data.startswith("deposit_"))
async def deposit_callback(callback: CallbackQuery, state: FSMContext):
    amount_str = callback.data.split("_")[-1]
    if amount_str == "custom":
        await callback.message.answer("✏️ <b>ВВЕДИТЕ СУММУ</b>\n\n💰 Минимум: 1 Star\n💰 Максимум: 10000 Stars", parse_mode=ParseMode.HTML)
        await state.set_state(GameStates.custom_deposit)
        await callback.answer()
        return
    await create_stars_invoice(callback.message, callback.from_user.id, int(amount_str))
    await callback.answer()

@dp.message(GameStates.custom_deposit)
async def process_custom_deposit(message: Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        if 1 <= amount <= 10000:
            await state.clear()
            await create_stars_invoice(message, message.from_user.id, amount)
        else:
            await message.answer("❌ Сумма должна быть от 1 до 10000 Stars!")
    except:
        await message.answer("❌ Введите число!")

@dp.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Операция отменена.", reply_markup=get_main_keyboard(message.from_user.id))

@dp.message(Command("admin"))
async def admin_command(message: Message):
    if is_admin(message.from_user.username or ""):
        await admin_panel(message)
    else:
        await message.answer("❌ Нет доступа к админ-панели!")


# ===================== ЗАПУСК =====================
async def main():
    logger.info("🚀 StarPlay Casino Bot запускается...")
    
    # Восстановление данных из бэкапа
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
        except Exception as e:
            logger.warning(f"⚠️ Не удалось загрузить backup.json: {e}")
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())