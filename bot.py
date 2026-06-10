import asyncio
import hashlib
import logging
import random
import json
from datetime import datetime
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
pending_payments: Dict[str, dict] = {}
transactions: Dict[int, list] = {}
users_username: Dict[int, str] = {}
users_join_date: Dict[int, str] = {}
users_bans: Dict[int, bool] = {}
users_warnings: Dict[int, int] = {}
users_mutes: Dict[int, dict] = {}

# Настройки бота
PROMO_MESSAGE = "🎉 Добро пожаловать в StarPlay!\nИграй и выигрывай Telegram Stars!"
COIN_PRICE = 100
DAILY_BONUS_RANGE = (5, 15)

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
    admin_send_poll = State()
    admin_edit_promo = State()
    admin_set_coin_price = State()
    admin_set_bonus = State()
    admin_set_win_chance = State()
    admin_manage_games = State()
    admin_edit_multipliers = State()
    admin_ban_user = State()
    admin_warn_user = State()
    admin_mute_user = State()
    mines_game = State()
    pyramid_game = State()


# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
def is_admin(username: str) -> bool:
    return username.lower() in [adm.lower() for adm in ADMIN_USERNAMES]

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
            "cube_wins": 0, "darts_wins": 0, "football_wins": 0,
            "basketball_wins": 0, "bowling_wins": 0, "mines_wins": 0,
            "pyramid_wins": 0, "slots_wins": 0
        }
    return users_stats[user_id]

def update_balance(user_id: int, delta: int) -> int:
    if users_bans.get(user_id, False):
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


# ===================== ПРАВИЛА ИГР =====================
# Dice игры (значения от 1 до 6)
DICE_GAMES = {
    "🎲": {"name": "Кубик", "emoji": "🎲", "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 3, 6: 5},
           "results": {1: "😭 Ужасный результат!", 2: "😢 Обидный промах...", 3: "🤔 Неплохо!",
                       4: "😊 Хороший результат!", 5: "😎 Отличный бросок!", 6: "🤯 НЕВЕРОЯТНО!"}},
    "🎯": {"name": "Дартс", "emoji": "🎯", "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 4, 6: 10},
           "results": {1: "💨 Дротик пролетел мимо!", 2: "🎯 Попал в молоко!", 3: "🎯 Попадание в 20!",
                       4: "🎯 Тройное попадание!", 5: "🎯 БЫЧИЙ ГЛАЗ!", 6: "🎯 ЯБЛОЧКО!!! 🔥"}},
    "⚽️": {"name": "Футбол", "emoji": "⚽️", "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 3, 6: 5},
           "results": {1: "🧤 Вратарь поймал мяч!", 2: "📐 Удар в штангу!", 3: "⚽️ ГОЛ!",
                       4: "⚽️ ГОЛ с рикошета!", 5: "⚽️ КРАСИВЫЙ ГОЛ!", 6: "⚽️ ШЕДЕВР!"}},
    "🏀": {"name": "Баскетбол", "emoji": "🏀", "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 4, 6: 6},
           "results": {1: "🏀 Воздух!", 2: "🏀 Щит!", 3: "🏀 ПОПАДАНИЕ!",
                       4: "🏀 СВЕРХУ!", 5: "🏀 ТРЁХОЧКОВЫЙ!", 6: "🏀 БАЗЗЕР БИТЕР!"}},
    "🎳": {"name": "Боулинг", "emoji": "🎳", "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 5, 6: 10},
           "results": {1: "🎳 Желоб!", 2: "🎳 Сбито мало кеглей", 3: "🎳 СПЭР!",
                       4: "🎳 СТРАЙК!", 5: "🎳 ИДЕАЛЬНЫЙ СТРАЙК!", 6: "🎳 ДЕСЯТЬ СТРАЙКОВ!"}},
    "🎰": {"name": "Слоты", "emoji": "🎰", "multipliers": {}, "results": {}}  # Слоты - особая логика
}

# Слоты через dice 🎰 (значения от 1 до 64)
SLOT_VALUES = {
    1: "🍒🍒🍒", 2: "🍒🍒🍒", 3: "🍒🍒🍒", 4: "🍒🍒🍒", 5: "🍒🍒🍒",
    6: "🍊🍊🍊", 7: "🍊🍊🍊", 8: "🍊🍊🍊", 9: "🍊🍊🍊", 10: "🍊🍊🍊",
    11: "🍋🍋🍋", 12: "🍋🍋🍋", 13: "🍋🍋🍋", 14: "🍋🍋🍋", 15: "🍋🍋🍋",
    16: "💎💎💎", 17: "💎💎💎", 18: "💎💎💎", 19: "💎💎💎", 20: "💎💎💎",
    21: "7️⃣7️⃣7️⃣", 22: "7️⃣7️⃣7️⃣", 23: "7️⃣7️⃣7️⃣", 24: "7️⃣7️⃣7️⃣", 25: "7️⃣7️⃣7️⃣",
    26: "🎰🎰🎰", 27: "🎰🎰🎰", 28: "🎰🎰🎰", 29: "🎰🎰🎰", 30: "🎰🎰🎰",
    31: "⭐️⭐️⭐️", 32: "⭐️⭐️⭐️", 33: "⭐️⭐️⭐️", 34: "⭐️⭐️⭐️", 35: "⭐️⭐️⭐️",
    36: "💫💫💫", 37: "💫💫💫", 38: "💫💫💫", 39: "💫💫💫", 40: "💫💫💫"
}

SLOT_PAYOUTS = {
    "🍒🍒🍒": 5, "🍊🍊🍊": 7, "🍋🍋🍋": 10, "💎💎💎": 15,
    "7️⃣7️⃣7️⃣": 25, "🎰🎰🎰": 50, "⭐️⭐️⭐️": 30, "💫💫💫": 20
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
    builder.button(text="🎁 Бонус")
    builder.button(text="👑 Админ панель")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_admin_panel_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📊 Статистика бота")
    builder.button(text="💰 Изменить баланс")
    builder.button(text="📢 Сделать рассылку")
    builder.button(text="📊 Создать опрос")
    builder.button(text="👥 Список пользователей")
    builder.button(text="📜 Логи транзакций")
    builder.button(text="💾 Сохранить данные")
    builder.button(text="🔄 Загрузить данные")
    builder.button(text="🎮 Управление играми")
    builder.button(text="🎲 Изменить множители")
    builder.button(text="⚙️ Настройка бота")
    builder.button(text="📝 Редактировать промо")
    builder.button(text="💰 Курс монет")
    builder.button(text="🎁 Настроить бонус")
    builder.button(text="🚫 Забанить пользователя")
    builder.button(text="🔓 Разбанить")
    builder.button(text="⚠️ Выдать варн")
    builder.button(text="🔇 Замутить")
    builder.button(text="🔊 Размутить")
    builder.button(text="🔙 В главное меню")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_games_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="🎲 Кубик")
    builder.button(text="🎯 Дартс")
    builder.button(text="⚽️ Футбол")
    builder.button(text="🏀 Баскетбол")
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
    
    users_username[user_id] = username
    
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
        f"{PROMO_MESSAGE}\n\n"
        f"🌟 <b>Добро пожаловать в StarPlay!</b> 🌟\n\n"
        f"{get_random_emoji()} <b>Играй на Telegram Stars и выигрывай!</b>\n\n"
        f"<b>🎮 Доступные игры:</b>\n"
        f"🎲 Кубик | 🎯 Дартс | ⚽️ Футбол | 🏀 Баскетбол | 🎳 Боулинг\n"
        f"🎰 Слоты | 💣 Мины | 🏛 Пирамида\n\n"
        f"<b>💫 Как начать:</b>\n"
        f"1️⃣ Пополни баланс через Telegram Stars\n"
        f"2️⃣ Выбери игру\n"
        f"3️⃣ Делай ставки и выигрывай!\n\n"
        f"👇 <i>Используй кнопки внизу!</i>"
    )
    
    await message.answer(welcome_text, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard())


# ===================== ГЛАВНЫЕ КНОПКИ =====================
@dp.message(F.text == "💰 Баланс")
async def balance_reply(message: Message):
    user_id = message.from_user.id
    if users_bans.get(user_id, False):
        await message.answer("❌ Вы забанены! Обратитесь к администратору.")
        return
    await message.answer(
        f"💰 <b>Твой баланс:</b> {format_stars(get_user_balance(user_id))}\n\n"
        f"👥 Рефералов: {len(users_referrals.get(user_id, []))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "⭐️ Пополнить")
async def deposit_reply(message: Message):
    user_id = message.from_user.id
    if users_bans.get(user_id, False):
        await message.answer("❌ Вы забанены! Обратитесь к администратору.")
        return
    await message.answer(
        "⭐️ <b>Пополнение баланса</b>\n\n"
        "Выберите сумму пополнения:\n"
        "💰 Средства зачисляются мгновенно после оплаты!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_deposit_keyboard()
    )

@dp.message(F.text == "🎮 Игры")
async def games_reply(message: Message):
    user_id = message.from_user.id
    if users_bans.get(user_id, False):
        await message.answer("❌ Вы забанены! Обратитесь к администратору.")
        return
    await message.answer(
        "🎮 <b>Выбери игру</b>\n\n"
        "🎲 <b>Кубик</b> — x5\n"
        "🎯 <b>Дартс</b> — x10\n"
        "⚽️ <b>Футбол</b> — x5\n"
        "🏀 <b>Баскетбол</b> — x6\n"
        "🎳 <b>Боулинг</b> — x10\n"
        "🎰 <b>Слоты</b> — x50\n"
        "💣 <b>Мины</b> — x18\n"
        "🏛 <b>Пирамида</b> — x16\n\n"
        "👇 <i>Нажми на кнопку с игрой!</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )

@dp.message(F.text == "👥 Рефералы")
async def referrals_reply(message: Message):
    user_id = message.from_user.id
    if users_bans.get(user_id, False):
        await message.answer("❌ Вы забанены! Обратитесь к администратору.")
        return
    
    bot_info = await bot.get_me()
    bot_username = bot_info.username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
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
        f"<code>{ref_link}</code>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться ссылкой", url=f"https://t.me/share/url?url={ref_link}&text=StarPlay — играй и зарабатывай Telegram Stars!")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

@dp.message(F.text == "🏆 Топ")
async def top_reply(message: Message):
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
    if users_bans.get(uid, False):
        await message.answer("❌ Вы забанены! Обратитесь к администратору.")
        return
    
    stats = get_user_stats(uid)
    wr = (stats['games_won'] / max(stats['games_played'], 1)) * 100
    ref_count = len(users_referrals.get(uid, []))
    
    text = (
        f"👤 <b>Профиль игрока</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👤 Username: @{message.from_user.username or 'нет'}\n"
        f"📅 Регистрация: {users_join_date.get(uid, 'неизвестно')}\n\n"
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

@dp.message(F.text == "🎁 Бонус")
async def bonus_reply(message: Message):
    user_id = message.from_user.id
    if users_bans.get(user_id, False):
        await message.answer("❌ Вы забанены! Обратитесь к администратору.")
        return
    
    today = datetime.now().date().isoformat()
    if users_daily_bonus.get(user_id) == today:
        await message.answer(
            f"🎁 <b>Ты уже получил сегодняшний бонус!</b>\n\nВозвращайся завтра!",
            parse_mode=ParseMode.HTML
        )
        return
    bonus_amount = random.randint(DAILY_BONUS_RANGE[0], DAILY_BONUS_RANGE[1])
    update_balance(user_id, bonus_amount)
    users_daily_bonus[user_id] = today
    save_transaction(user_id, bonus_amount, "daily_bonus", "Ежедневный бонус")
    await message.answer(
        f"🎉 <b>Ежедневный бонус получен!</b> 🎉\n\n"
        f"+{format_stars(bonus_amount)}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML
    )


# ===================== DICE ИГРЫ =====================
async def play_dice_game(callback: CallbackQuery, game_key: str, bet: int):
    """Универсальная функция для dice игр (кубик, дартс, футбол, баскетбол, боулинг)"""
    user_id = callback.from_user.id
    
    if users_bans.get(user_id, False):
        await callback.answer("❌ Вы забанены!", show_alert=True)
        return
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    game = DICE_GAMES[game_key]
    update_balance(user_id, -bet)
    
    # Отправляем dice через sendDice
    dice_message = await callback.message.answer_dice(emoji=game["emoji"])
    dice_value = dice_message.dice.value
    
    multiplier = game["multipliers"].get(dice_value, 0)
    result_text = game["results"].get(dice_value, "Результат...")
    
    if multiplier > 0:
        win_amount = bet * multiplier
        update_balance(user_id, win_amount)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        
        win_key = f"{game_key}_wins"
        if win_key in stats:
            stats[win_key] += 1
            
        stats["total_won"] += win_amount
        save_transaction(user_id, win_amount, "game_win", f"{game['name']} x{multiplier}")
        
        result = f"🎉 <b>ВЫИГРЫШ!</b> 🎉\n✨ Множитель: <b>x{multiplier}</b>\n🏆 Выигрыш: <b>+{format_stars(win_amount)}</b>"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", game['name'])
        result = f"😢 <b>Проигрыш</b>\n-{format_stars(bet)}"
    
    await callback.message.answer(
        f"{game['emoji']} <b>{game['name']}</b>\n\n"
        f"🎲 <b>Результат: {dice_value}</b>\n"
        f"{result_text}\n\n"
        f"💰 Ставка: {format_stars(bet)}\n\n"
        f"{result}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()


# ---------- КУБИК ----------
@dp.message(F.text == "🎲 Кубик")
async def cube_start(message: Message):
    await message.answer(
        "🎲 <b>Игра КУБИК</b>\n\n"
        "📋 <b>Множители:</b>\n"
        "• 1-2 → проигрыш\n• 3 → x1\n• 4 → x2\n• 5 → x3\n• 6 → x5\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("cube")
    )

@dp.callback_query(F.data.startswith("cube_bet_"))
async def cube_play(callback: CallbackQuery):
    bet = int(callback.data.split("_")[-1])
    await play_dice_game(callback, "🎲", bet)


# ---------- ДАРТС ----------
@dp.message(F.text == "🎯 Дартс")
async def darts_start(message: Message):
    await message.answer(
        "🎯 <b>Игра ДАРТС</b>\n\n"
        "📋 <b>Множители:</b>\n"
        "• 1-2 → мимо\n• 3 → x1\n• 4 → x2\n• 5 → x4\n• 6 → ЯБЛОЧКО x10!\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("darts")
    )

@dp.callback_query(F.data.startswith("darts_bet_"))
async def darts_play(callback: CallbackQuery):
    bet = int(callback.data.split("_")[-1])
    await play_dice_game(callback, "🎯", bet)


# ---------- ФУТБОЛ ----------
@dp.message(F.text == "⚽️ Футбол")
async def football_start(message: Message):
    await message.answer(
        "⚽️ <b>Игра ФУТБОЛ</b>\n\n"
        "📋 <b>Множители:</b>\n"
        "• 1-2 → сейв\n• 3 → гол x1\n• 4 → рикошет x2\n• 5 → красивый x3\n• 6 → ШЕДЕВР x5!\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("football")
    )

@dp.callback_query(F.data.startswith("football_bet_"))
async def football_play(callback: CallbackQuery):
    bet = int(callback.data.split("_")[-1])
    await play_dice_game(callback, "⚽️", bet)


# ---------- БАСКЕТБОЛ ----------
@dp.message(F.text == "🏀 Баскетбол")
async def basketball_start(message: Message):
    await message.answer(
        "🏀 <b>Игра БАСКЕТБОЛ</b>\n\n"
        "📋 <b>Множители:</b>\n"
        "• 1-2 → промах\n• 3 → попадание x1\n• 4 → сверху x2\n• 5 → издали x4\n• 6 → БАЗЗЕР x6!\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("basketball")
    )

@dp.callback_query(F.data.startswith("basketball_bet_"))
async def basketball_play(callback: CallbackQuery):
    bet = int(callback.data.split("_")[-1])
    await play_dice_game(callback, "🏀", bet)


# ---------- БОУЛИНГ ----------
@dp.message(F.text == "🎳 Боулинг")
async def bowling_start(message: Message):
    await message.answer(
        "🎳 <b>Игра БОУЛИНГ</b>\n\n"
        "📋 <b>Множители:</b>\n"
        "• 1-2 → желоб\n• 3 → спэр x1\n• 4 → страйк x2\n• 5 → идеальный x5\n• 6 → ДЕСЯТЬ СТРАЙКОВ x10!\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("bowling")
    )

@dp.callback_query(F.data.startswith("bowling_bet_"))
async def bowling_play(callback: CallbackQuery):
    bet = int(callback.data.split("_")[-1])
    await play_dice_game(callback, "🎳", bet)


# ---------- СЛОТЫ (через dice 🎰) ----------
@dp.message(F.text == "🎰 Слоты")
async def slots_start(message: Message):
    await message.answer(
        "🎰 <b>Игра СЛОТЫ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "Крути барабаны и собирай комбинации!\n"
        "🎰 <b>ДЖЕКПОТ x50</b> при трёх 🎰!\n"
        "• 2 одинаковых символа → x1.5\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("slots")
    )

@dp.callback_query(F.data.startswith("slots_bet_"))
async def slots_play(callback: CallbackQuery):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if users_bans.get(user_id, False):
        await callback.answer("❌ Вы забанены!", show_alert=True)
        return
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    
    # Отправляем dice с эмодзи 🎰
    dice_message = await callback.message.answer_dice(emoji="🎰")
    dice_value = dice_message.dice.value
    
    # Определяем комбинацию по значению (1-64)
    if dice_value <= 5:
        combo = "🍒🍒🍒"
    elif dice_value <= 10:
        combo = "🍊🍊🍊"
    elif dice_value <= 15:
        combo = "🍋🍋🍋"
    elif dice_value <= 20:
        combo = "💎💎💎"
    elif dice_value <= 25:
        combo = "7️⃣7️⃣7️⃣"
    elif dice_value <= 30:
        combo = "🎰🎰🎰"
    elif dice_value <= 35:
        combo = "⭐️⭐️⭐️"
    elif dice_value <= 40:
        combo = "💫💫💫"
    else:
        # Пара (2 одинаковых)
        symbols = ["🍒", "🍊", "🍋", "💎", "7️⃣", "🎰", "⭐️", "💫"]
        two_same = random.choice(symbols)
        third = random.choice(symbols)
        combo = f"{two_same}{two_same}{third}"
    
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
    elif len(set(combo)) == 2:
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
    
    # Форматируем комбинацию для отображения
    display_combo = " ".join(list(combo))
    
    await callback.message.answer(
        f"🎰 <b>СЛОТЫ</b>\n\n"
        f"┌─────┬─────┬─────┐\n"
        f"│  {combo[0]}  │  {combo[1]}  │  {combo[2]}  │\n"
        f"└─────┴─────┴─────┘\n\n"
        f"💰 Ставка: {format_stars(bet)}\n\n"
        f"{res}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
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
    
    if users_bans.get(user_id, False):
        await callback.answer("❌ Вы забанены!", show_alert=True)
        return
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    
    board = [["💎" for _ in range(5)] for _ in range(5)]
    mines = 0
    while mines < 5:
        x, y = random.randint(0, 4), random.randint(0, 4)
        if board[x][y] == "💎":
            board[x][y] = "💣"
            mines += 1
    
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
        f"✨ Множитель: x1.0\n"
        f"📦 Открыто клеток: 0/20\n\n"
        f"👇 <b>Открывай 💎 и избегай 💣!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_mines_board_keyboard(board, active_mines_games[user_id]["revealed"], bet, 1.0, 0)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("mine_"))
async def mines_reveal(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_mines_games:
        await callback.answer("Игра не найдена!", show_alert=True)
        return
    
    game = active_mines_games[user_id]
    parts = callback.data.split("_")
    x, y = int(parts[1]), int(parts[2])
    
    if game["revealed"][x][y]:
        await callback.answer("Уже открыто!", show_alert=True)
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
            f"✅ <b>Найдена 💎! Множитель увеличен!</b>",
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
                f"🎉 <b>ПОБЕДА!</b> Ты очистил всё поле!\n\n"
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
        f"💰 <b>Ты забрал выигрыш!</b>\n\n"
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
        "5 уровней, каждый шаг удваивает выигрыш (50% успеха)\n"
        "• 1 уровень → x1\n• 2 уровень → x2\n• 3 уровень → x4\n"
        "• 4 уровень → x8\n• 5 уровень → x16\n\n"
        "Выбери начальную ставку:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("pyramid")
    )

@dp.callback_query(F.data.startswith("pyramid_bet_"))
async def pyramid_init(callback: CallbackQuery):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if users_bans.get(user_id, False):
        await callback.answer("❌ Вы забанены!", show_alert=True)
        return
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    active_pyramids[user_id] = {"bet": bet, "level": 1, "current": bet}
    
    await callback.message.edit_text(
        f"🏛 <b>ПИРАМИДА</b>\n\n"
        f"🏆 <b>Уровень 1 / 5</b>\n\n"
        f"💰 Текущий выигрыш: {format_stars(bet)}\n"
        f"🎯 Следующий уровень: {format_stars(bet * 2)}\n"
        f"📊 Шанс успеха: 50%\n\n"
        f"👇 <b>Поднимешься или заберёшь выигрыш?</b>",
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
            save_transaction(user_id, game["current"], "game_win", f"Пирамида победа ур.{game['level']}")
            del active_pyramids[user_id]
            
            await callback.message.edit_text(
                f"🏛 <b>ПИРАМИДА - ПОБЕДА!</b>\n\n"
                f"🎉 <b>Ты покорил вершину!</b>\n\n"
                f"🏆 Уровень: 5/5\n"
                f"💰 Выигрыш: {format_stars(game['current'])}\n"
                f"✨ Множитель: x{game['current'] // game['bet']}\n\n"
                f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_games_keyboard()
            )
        else:
            await callback.message.edit_text(
                f"🏛 <b>ПИРАМИДА</b>\n\n"
                f"✅ <b>УСПЕХ!</b> Уровень {game['level']}!\n\n"
                f"🏆 <b>Уровень {game['level']} / 5</b>\n"
                f"💰 Выигрыш: {format_stars(game['current'])}\n"
                f"🎯 Следующий: {format_stars(game['current'] * 2)}\n\n"
                f"👇 <b>Продолжим подъём?</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_pyramid_keyboard(game["level"], game["current"])
            )
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += game["bet"]
        save_transaction(user_id, -game["bet"], "game_loss", f"Пирамида ур.{game['level']}")
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
    save_transaction(user_id, win, "game_win", f"Пирамида кэшаут ур.{game['level']}")
    del active_pyramids[user_id]
    
    await callback.message.edit_text(
        f"🏛 <b>ПИРАМИДА</b>\n\n"
        f"💰 <b>Ты забрал выигрыш!</b>\n\n"
        f"🏆 Пройдено: {game['level']}/5 уровней\n"
        f"✨ Множитель: x{win // game['bet']}\n"
        f"🏆 Выигрыш: {format_stars(win)}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()


# ===================== АДМИН-ПАНЕЛЬ =====================
@dp.message(F.text == "👑 Админ панель")
async def admin_panel_reply(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ У вас нет доступа к админ-панели!", reply_markup=get_main_keyboard())
        return
    
    await message.answer(
        "👑 <b>Панель администратора</b>\n\n"
        "Выберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard()
    )

# ---------- СТАТИСТИКА ----------
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
    banned = len([u for u, b in users_bans.items() if b])
    
    text = (
        f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
        f"👥 <b>Пользователей:</b> {total_users}\n"
        f"🚫 <b>Забанено:</b> {banned}\n"
        f"💰 <b>Общий баланс:</b> {format_stars(total_balance)}\n"
        f"🎮 <b>Всего игр:</b> {total_games}\n"
        f"🏆 <b>Всего побед:</b> {total_wins}\n"
    )
    if total_games > 0:
        text += f"📈 <b>Винрейт:</b> {(total_wins/total_games*100):.1f}%\n"
    text += (
        f"💸 <b>Пополнений:</b> {total_deposits}\n"
        f"💸 <b>Сумма пополнений:</b> {format_stars(deposit_sum)}\n"
    )
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

# ---------- ИЗМЕНЕНИЕ БАЛАНСА ----------
@dp.message(F.text == "💰 Изменить баланс")
async def admin_change_balance_reply(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_find_user)
    await message.answer(
        "💰 <b>ИЗМЕНЕНИЕ БАЛАНСА</b>\n\n"
        "Введи username игрока (без @) или ID:\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

# ---------- РАССЫЛКА ----------
@dp.message(F.text == "📢 Сделать рассылку")
async def admin_broadcast_reply(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_send_message)
    await message.answer(
        "📢 <b>РАССЫЛКА</b>\n\n"
        "Отправь сообщение для рассылки всем пользователям.\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

# ---------- СОЗДАТЬ ОПРОС ----------
@dp.message(F.text == "📊 Создать опрос")
async def admin_poll_reply(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_send_poll)
    await message.answer(
        "📊 <b>СОЗДАНИЕ ОПРОСА</b>\n\n"
        "Отправь опрос в формате:\n"
        "<code>Вопрос|Вариант1,Вариант2,Вариант3</code>\n\n"
        "Пример:\n"
        "<code>Какая игра вам нравится?|Дартс,Футбол,Слоты</code>\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML
    )

# ---------- СПИСОК ПОЛЬЗОВАТЕЛЕЙ ----------
@dp.message(F.text == "👥 Список пользователей")
async def admin_users_list(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    users_list = []
    for uid, uname in users_username.items():
        balance = get_user_balance(uid)
        status = "🚫" if users_bans.get(uid, False) else ""
        users_list.append(f"{status} @{uname or str(uid)} — {balance}⭐️")
    
    if not users_list:
        text = "👥 Пользователей пока нет"
    else:
        text = "👥 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ</b>\n\n" + "\n".join(users_list[:50])
        if len(users_list) > 50:
            text += f"\n\n... и ещё {len(users_list)-50} пользователей"
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

# ---------- ЛОГИ ТРАНЗАКЦИЙ ----------
@dp.message(F.text == "📜 Логи транзакций")
async def admin_logs(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    all_txs = []
    for uid, tx_list in transactions.items():
        uname = users_username.get(uid, str(uid))
        for tx in tx_list[-5:]:
            all_txs.append((tx["timestamp"], f"@{uname}: {tx['type']} {tx['amount']}⭐️ - {tx['details']}"))
    
    all_txs.sort(reverse=True)
    recent = all_txs[:30]
    
    if not recent:
        text = "📜 Логов транзакций пока нет"
    else:
        text = "📜 <b>ПОСЛЕДНИЕ ТРАНЗАКЦИИ</b>\n\n" + "\n".join([f"• {tx[1]}" for tx in recent])
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

# ---------- СОХРАНЕНИЕ ДАННЫХ ----------
@dp.message(F.text == "💾 Сохранить данные")
async def admin_save(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    data = {
        "balance": users_balance, "referrer": users_referrer, "referrals": users_referrals,
        "stats": users_stats, "transactions": transactions, "username": users_username,
        "join_date": users_join_date, "bans": users_bans, "warnings": users_warnings,
        "promo": PROMO_MESSAGE, "coin_price": COIN_PRICE, "daily_bonus_range": DAILY_BONUS_RANGE
    }
    
    try:
        with open("backup.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        await message.answer(
            "✅ <b>Данные сохранены!</b>\n\nФайл: backup.json",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=get_admin_panel_keyboard())

# ---------- ЗАГРУЗКА ДАННЫХ ----------
@dp.message(F.text == "🔄 Загрузить данные")
async def admin_load(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
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
        users_bans.update(data.get("bans", {}))
        
        await message.answer("✅ <b>Данные загружены!</b>", parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())
    except FileNotFoundError:
        await message.answer("❌ Файл backup.json не найден!", reply_markup=get_admin_panel_keyboard())
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=get_admin_panel_keyboard())

# ---------- УПРАВЛЕНИЕ ИГРАМИ ----------
@dp.message(F.text == "🎮 Управление играми")
async def admin_manage_games(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    games_info = "\n".join([f"{g['emoji']} {g['name']} — множители: {g['multipliers']}" for g in DICE_GAMES.values() if g['multipliers']])
    
    await message.answer(
        f"🎮 <b>УПРАВЛЕНИЕ ИГРАМИ</b>\n\n"
        f"{games_info}\n\n"
        f"🎰 Слоты — x50 джекпот\n"
        f"💣 Мины — множитель до x18\n"
        f"🏛 Пирамида — множитель до x16\n\n"
        f"Используйте кнопку «Изменить множители» для настройки",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard()
    )

# ---------- ИЗМЕНИТЬ МНОЖИТЕЛИ ----------
@dp.message(F.text == "🎲 Изменить множители")
async def admin_change_multipliers(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_edit_multipliers)
    await message.answer(
        "🎲 <b>ИЗМЕНЕНИЕ МНОЖИТЕЛЕЙ</b>\n\n"
        "Введи новые множители в формате:\n"
        "<code>игра:1:0,2:0,3:1,4:2,5:3,6:5</code>\n\n"
        "Доступные игры: 🎲 🎯 ⚽️ 🏀 🎳\n"
        "Пример для кубика:\n"
        "<code>🎲:1:0,2:0,3:1,4:2,5:3,6:5</code>\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML
    )

# ---------- НАСТРОЙКА БОТА ----------
@dp.message(F.text == "⚙️ Настройка бота")
async def admin_settings(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    text = (
        f"⚙️ <b>НАСТРОЙКИ БОТА</b>\n\n"
        f"💵 <b>Курс монет:</b> {COIN_PRICE} Stars за монету\n"
        f"🎁 <b>Ежедневный бонус:</b> {DAILY_BONUS_RANGE[0]}-{DAILY_BONUS_RANGE[1]} Stars\n"
        f"👥 <b>Реферальная система:</b> активна\n"
        f"💰 <b>Реферальный бонус за регистрацию:</b> {REFERRAL_SIGNUP_BONUS} Stars\n"
        f"🎁 <b>Реферальный бонус пригласившему:</b> {REFERRAL_INVITE_BONUS} Stars\n"
        f"📊 <b>Реферальный процент с пополнений:</b> {REFERRAL_BONUS_PERCENT}%\n\n"
        f"Используйте кнопки ниже для изменения настроек:"
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

# ---------- РЕДАКТИРОВАНИЕ ПРОМО ----------
@dp.message(F.text == "📝 Редактировать промо")
async def admin_edit_promo(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_edit_promo)
    await message.answer(
        f"📝 <b>РЕДАКТИРОВАНИЕ ПРОМО</b>\n\n"
        f"Текущее промо:\n{PROMO_MESSAGE}\n\n"
        f"Введи новое промо-сообщение:\n\n"
        f"<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML
    )

# ---------- КУРС МОНЕТ ----------
@dp.message(F.text == "💰 Курс монет")
async def admin_set_coin_price(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_set_coin_price)
    await message.answer(
        f"💰 <b>КУРС МОНЕТ</b>\n\n"
        f"Текущий курс: {COIN_PRICE} Stars = 1 монета\n\n"
        f"Введи новый курс (количество Stars за 1 монету):\n\n"
        f"<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML
    )

# ---------- НАСТРОЙКА БОНУСА ----------
@dp.message(F.text == "🎁 Настроить бонус")
async def admin_set_bonus(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_set_bonus)
    await message.answer(
        f"🎁 <b>НАСТРОЙКА БОНУСА</b>\n\n"
        f"Текущий диапазон: {DAILY_BONUS_RANGE[0]}-{DAILY_BONUS_RANGE[1]} Stars\n\n"
        f"Введи новый диапазон в формате:\n"
        f"<code>мин,макс</code>\n"
        f"Пример: <code>10,25</code>\n\n"
        f"<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML
    )

# ---------- ЗАБАНИТЬ ----------
@dp.message(F.text == "🚫 Забанить пользователя")
async def admin_ban(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_ban_user)
    await message.answer(
        "🚫 <b>БАН ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введи username (без @) или ID пользователя:\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML
    )

# ---------- РАЗБАНИТЬ ----------
@dp.message(F.text == "🔓 Разбанить")
async def admin_unban(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_ban_user)
    await message.answer(
        "🔓 <b>РАЗБАН ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введи username (без @) или ID пользователя:\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML
    )

# ---------- ВЫДАТЬ ВАРН ----------
@dp.message(F.text == "⚠️ Выдать варн")
async def admin_warn(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_warn_user)
    await message.answer(
        "⚠️ <b>ВЫДАЧА ВАРНА</b>\n\n"
        "Введи username (без @) или ID пользователя:\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML
    )

# ---------- ЗАМУТИТЬ ----------
@dp.message(F.text == "🔇 Замутить")
async def admin_mute(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_mute_user)
    await message.answer(
        "🔇 <b>МУТ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введи username (без @) или ID пользователя:\n\n"
        "Затем введи время мута в минутах\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML
    )

# ---------- РАЗМУТИТЬ ----------
@dp.message(F.text == "🔊 Размутить")
async def admin_unmute(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_mute_user)
    await message.answer(
        "🔊 <b>РАЗМУТ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введи username (без @) или ID пользователя:\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML
    )

# ---------- НАЗАД ----------
@dp.message(F.text == "🔙 В главное меню")
async def back_to_main_from_admin(message: Message):
    await message.answer(
        "🌟 <b>Главное меню</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "🔙 Главное меню")
async def back_to_main_from_games(message: Message):
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
        await message.answer("❌ Отменено.", reply_markup=get_admin_panel_keyboard())
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
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_to_panel")]
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
            "✏️ <b>Введи сумму</b> (можно с минусом для снятия):\n"
            "Пример: 500 или -200\n\n"
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
        f"{result_text}\n\n💰 Новый баланс: {format_stars(get_user_balance(target_user))}",
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
        await message.answer("❌ Отменено.", reply_markup=get_admin_panel_keyboard())
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
    
    progress_msg = await message.answer("📢 Начинаю рассылку...")
    
    for user_id in users_balance.keys():
        try:
            if message.text:
                await bot.send_message(user_id, message.text, parse_mode=ParseMode.HTML)
            elif message.photo:
                await bot.send_photo(user_id, message.photo[-1].file_id, caption=message.caption)
            elif message.video:
                await bot.send_video(user_id, message.video.file_id, caption=message.caption)
            else:
                await bot.copy_message(user_id, message.chat.id, message.message_id)
            success += 1
            await asyncio.sleep(0.05)
        except:
            fail += 1
    
    await state.clear()
    await progress_msg.edit_text(
        f"✅ <b>РАССЫЛКА ЗАВЕРШЕНА</b>\n\n"
        f"📨 Доставлено: {success}\n"
        f"❌ Ошибок: {fail}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard()
    )

@dp.message(GameStates.admin_send_poll)
async def admin_poll_handler(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await state.clear()
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Создание опроса отменено.", reply_markup=get_admin_panel_keyboard())
        return
    
    try:
        parts = message.text.split("|")
        question = parts[0]
        options = parts[1].split(",")
        
        if len(options) < 2 or len(options) > 10:
            await message.answer("❌ Количество вариантов должно быть от 2 до 10!")
            return
        
        sent = 0
        for user_id in users_balance.keys():
            try:
                await bot.send_poll(
                    chat_id=user_id,
                    question=question,
                    options=options,
                    is_anonymous=False,
                    allows_multiple_answers=False
                )
                sent += 1
                await asyncio.sleep(0.05)
            except:
                pass
        
        await state.clear()
        await message.answer(
            f"✅ <b>ОПРОС ОТПРАВЛЕН</b>\n\n"
            f"📨 Вопрос: {question}\n"
            f"📊 Доставлено: {sent} пользователям",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=get_admin_panel_keyboard())

@dp.message(GameStates.admin_edit_promo)
async def admin_edit_promo_handler(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await state.clear()
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Редактирование отменено.", reply_markup=get_admin_panel_keyboard())
        return
    
    global PROMO_MESSAGE
    PROMO_MESSAGE = message.text
    
    await state.clear()
    await message.answer(
        f"✅ <b>ПРОМО-СООБЩЕНИЕ ОБНОВЛЕНО</b>\n\n"
        f"Новое сообщение:\n{PROMO_MESSAGE}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard()
    )

@dp.message(GameStates.admin_set_coin_price)
async def admin_set_coin_price_handler(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await state.clear()
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Настройка отменена.", reply_markup=get_admin_panel_keyboard())
        return
    
    try:
        global COIN_PRICE
        COIN_PRICE = int(message.text.strip())
        if COIN_PRICE < 1:
            await message.answer("❌ Курс должен быть >= 1")
            return
        
        await state.clear()
        await message.answer(
            f"✅ <b>КУРС МОНЕТ НАСТРОЕН</b>\n\n"
            f"Новый курс: {COIN_PRICE} Stars = 1 монета",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )
    except:
        await message.answer("❌ Ошибка! Введи число.")

@dp.message(GameStates.admin_set_bonus)
async def admin_set_bonus_handler(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await state.clear()
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Настройка отменена.", reply_markup=get_admin_panel_keyboard())
        return
    
    try:
        parts = message.text.split(",")
        min_bonus = int(parts[0].strip())
        max_bonus = int(parts[1].strip())
        
        if min_bonus < 1 or max_bonus < min_bonus:
            await message.answer("❌ Некорректный диапазон!")
            return
        
        global DAILY_BONUS_RANGE
        DAILY_BONUS_RANGE = (min_bonus, max_bonus)
        
        await state.clear()
        await message.answer(
            f"✅ <b>ЕЖЕДНЕВНЫЙ БОНУС НАСТРОЕН</b>\n\n"
            f"Новый диапазон: {min_bonus}-{max_bonus} Stars",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )
    except:
        await message.answer("❌ Ошибка! Формат: мин,макс")

@dp.message(GameStates.admin_edit_multipliers)
async def admin_edit_multipliers_handler(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await state.clear()
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Редактирование отменено.", reply_markup=get_admin_panel_keyboard())
        return
    
    try:
        parts = message.text.split(":")
        emoji = parts[0]
        multipliers = {}
        
        for p in parts[1].split(","):
            val, mult = p.split(":")
            multipliers[int(val)] = int(mult)
        
        if emoji in DICE_GAMES:
            DICE_GAMES[emoji]["multipliers"] = multipliers
            await state.clear()
            await message.answer(
                f"✅ <b>МНОЖИТЕЛИ ИЗМЕНЕНЫ</b>\n\n"
                f"Игра {DICE_GAMES[emoji]['name']}: {multipliers}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_panel_keyboard()
            )
        else:
            await message.answer("❌ Неверный эмодзи игры!")
    except Exception as e:
        await message.answer(f"❌ Ошибка формата: {e}")

@dp.message(GameStates.admin_ban_user)
async def admin_ban_handler(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await state.clear()
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=get_admin_panel_keyboard())
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
    
    users_bans[user_id] = True
    await bot.send_message(user_id, "🚫 <b>Вы были забанены администратором!</b>", parse_mode=ParseMode.HTML)
    
    await state.clear()
    await message.answer(
        f"✅ Пользователь @{input_text} забанен!",
        reply_markup=get_admin_panel_keyboard()
    )


# ===================== НАВИГАЦИОННЫЕ CALLBACK =====================
@dp.callback_query(F.data == "back_to_games")
async def back_to_games_callback(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer(
        "🎮 <b>Выбери игру</b>",
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


# ===================== ПЛАТЕЖИ =====================
async def create_stars_invoice(message: Message, user_id: int, amount: int):
    if amount < 1 or amount > 10000:
        await message.answer("❌ Сумма должна быть от 1 до 10000 Stars")
        return
    
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
        f"💰 Новый баланс: {format_stars(new_balance)}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )

@dp.callback_query(F.data.startswith("deposit_"))
async def deposit_amount(callback: CallbackQuery, state: FSMContext):
    amount_str = callback.data.split("_")[1]
    if amount_str == "custom":
        await callback.message.answer("✏️ Введи сумму (1-10000):", parse_mode=ParseMode.HTML)
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
        await message.answer("❌ Отменено.", reply_markup=get_admin_panel_keyboard())
    else:
        await message.answer("❌ Отменено.", reply_markup=get_main_keyboard())


# ===================== ЗАПУСК =====================
async def main():
    logger.info("🚀 StarPlay Bot запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())