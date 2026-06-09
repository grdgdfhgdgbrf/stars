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
BOT_TOKEN = "8251949164:AAH9dxlioIEhmzZNazWzMHg0NhfaEsGYFMk"
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
user_last_bonus: Dict[int, str] = {}
user_weekly_bonus: Dict[int, str] = {}
user_monthly_bonus: Dict[int, str] = {}
user_achievements: Dict[int, List[str]] = {}

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
    admin_send_broadcast = State()
    admin_edit_game = State()
    dice_game = State()
    mines_game = State()
    pyramid_game = State()
    roulette_game = State()


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
            "dice_wins": 0, "darts_wins": 0, "football_wins": 0,
            "bowling_wins": 0, "basketball_wins": 0, "slot_wins": 0,
            "mines_wins": 0, "pyramid_wins": 0, "roulette_wins": 0,
            "slot_wins": 0, "darts_180": 0, "football_hattrick": 0,
            "basketball_perfect": 0, "bowling_strike": 0
        }
    return users_stats[user_id]

def update_balance(user_id: int, delta: int) -> int:
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

def add_achievement(user_id: int, achievement: str):
    if user_id not in user_achievements:
        user_achievements[user_id] = []
    if achievement not in user_achievements[user_id]:
        user_achievements[user_id].append(achievement)


# ===================== DICE ИГРЫ (ВСЕ ЧЕРЕЗ sendDice) =====================
# Правила для всех dice игр (значения от 1 до 6)
DICE_GAMES = {
    "🎲": {
        "name": "Кубик",
        "emoji": "🎲",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 3, 6: 5},
        "descriptions": {1: "😭 Ужас!", 2: "😢 Обидно!", 3: "🤔 Неплохо", 4: "😊 Хорошо", 5: "😎 Отлично", 6: "🤯 ИДЕАЛЬНО!"},
        "win_texts": {3: "Обычный бросок", 4: "Хороший бросок!", 5: "Отличный бросок!!", 6: "КРИТИЧЕСКИЙ УСПЕХ!!!"}
    },
    "🎯": {
        "name": "Дартс",
        "emoji": "🎯",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 4, 6: 10},
        "descriptions": {1: "💨 Мимо!", 2: "🎯 Рядом!", 3: "🎯 Попадание!", 4: "🎯 Тройное 20!", 5: "🎯 Бычок!", 6: "🏆 ЯБЛОЧКО! 🏆"},
        "win_texts": {3: "Попадание в сектор", 4: "Тройное 20!", 5: "Бычок!", 6: "ЯБЛОЧКО!!!"}
    },
    "⚽️": {
        "name": "Футбол",
        "emoji": "⚽️",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 3, 6: 5},
        "descriptions": {1: "🧤 Сейв!", 2: "📐 Штанга!", 3: "⚽️ ГОЛ!", 4: "⚽️ Красивый гол!", 5: "⚽️ Шедевр!", 6: "🏆 ПОБЕДНЫЙ ГОЛ! 🏆"},
        "win_texts": {3: "Гол!", 4: "Красивый гол!", 5: "Шедевр!", 6: "Победный гол!!!"}
    },
    "🏀": {
        "name": "Баскетбол",
        "emoji": "🏀",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 4, 6: 6},
        "descriptions": {1: "💨 Промах!", 2: "📐 Щит!", 3: "🏀 Очко!", 4: "🏀 Из-за дуги!", 5: "🏀 Аллей-уп!", 6: "🏆 БАЗЗЕР БИТЕР! 🏆"},
        "win_texts": {3: "Очко!", 4: "Трёхочковый!", 5: "Аллей-уп!", 6: "Баззер битер!!!"}
    },
    "🎳": {
        "name": "Боулинг",
        "emoji": "🎳",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 5, 6: 10},
        "descriptions": {1: "💨 Промах!", 2: "🎳 7 кегль!", 3: "🎳 Спэр!", 4: "🎳 Страйк!", 5: "🎳 Идеальный!", 6: "🏆 ДЕСЯТЬ СТРАЙКОВ! 🏆"},
        "win_texts": {3: "Спэр!", 4: "Страйк!", 5: "Идеальный!", 6: "Десять страйков!!!"}
    },
    "🎰": {
        "name": "Слоты",
        "emoji": "🎰",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 3, 6: 5},
        "descriptions": {1: "😭 Ничего!", 2: "😢 Почти!", 3: "🎰 Маленький выигрыш!", 4: "🎰 Хороший выигрыш!", 5: "🎰 Крупный выигрыш!", 6: "🏆 ДЖЕКПОТ! 🏆"},
        "win_texts": {3: "Маленький выигрыш", 4: "Хороший выигрыш", 5: "Крупный выигрыш", 6: "ДЖЕКПОТ!!!"}
    }
}

# Дополнительные игры
DICE_EXTRA = {
    "🎲": {"game": "dice", "name": "Кубик"},
    "🎯": {"game": "darts", "name": "Дартс"},
    "⚽️": {"game": "football", "name": "Футбол"},
    "🏀": {"game": "basketball", "name": "Баскетбол"},
    "🎳": {"game": "bowling", "name": "Боулинг"},
    "🎰": {"game": "slots", "name": "Слоты"}
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
    builder.button(text="🏅 Достижения")
    builder.button(text="👑 Админ панель")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_admin_panel_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📊 Статистика бота")
    builder.button(text="💰 Изменить баланс")
    builder.button(text="📢 Рассылка")
    builder.button(text="👥 Список пользователей")
    builder.button(text="📜 Логи транзакций")
    builder.button(text="🏆 Сбросить винрейт")
    builder.button(text="🎮 Изменить множители")
    builder.button(text="💾 Сохранить данные")
    builder.button(text="📤 Выгрузить JSON")
    builder.button(text="📥 Загрузить JSON")
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
    builder.button(text="🎡 Рулетка")
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
        [InlineKeyboardButton(text="⭐️ 5000", callback_data=f"{game_key}_bet_5000"),
         InlineKeyboardButton(text="⭐️ 10000", callback_data=f"{game_key}_bet_10000")],
        [InlineKeyboardButton(text="◀️ Назад к играм", callback_data="back_to_games")]
    ])

def get_roulette_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Красное (x2)", callback_data="roulette_red"),
         InlineKeyboardButton(text="⚫️ Черное (x2)", callback_data="roulette_black")],
        [InlineKeyboardButton(text="🟢 Зеро (x35)", callback_data="roulette_zero"),
         InlineKeyboardButton(text="🎯 Четное (x2)", callback_data="roulette_even")],
        [InlineKeyboardButton(text="🎯 Нечетное (x2)", callback_data="roulette_odd"),
         InlineKeyboardButton(text="📊 1-18 (x2)", callback_data="roulette_low")],
        [InlineKeyboardButton(text="📊 19-36 (x2)", callback_data="roulette_high"),
         InlineKeyboardButton(text="🎲 Число (x35)", callback_data="roulette_number")],
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
        add_achievement(user_id, "🎉 Первый вход!")
    
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
                    add_achievement(referrer_id, "👥 Пригласил друга!")
                    await message.answer(f"✅ Вы получили {format_stars(REFERRAL_SIGNUP_BONUS)} за регистрацию по ссылке!")
            except:
                pass
    
    welcome_text = (
        f"🌟 <b>Добро пожаловать в StarPlay!</b> 🌟\n\n"
        f"{get_random_emoji()} <b>Играй на Telegram Stars и выигрывай!</b>\n\n"
        f"<b>🎮 9 игр на выбор:</b>\n"
        f"🎲 Кубик | 🎯 Дартс | ⚽️ Футбол | 🏀 Баскетбол | 🎳 Боулинг\n"
        f"🎰 Слоты | 💣 Мины | 🏛 Пирамида | 🎡 Рулетка\n\n"
        f"<b>💫 Как начать:</b>\n"
        f"1️⃣ Пополни баланс через Telegram Stars\n"
        f"2️⃣ Выбери игру\n"
        f"3️⃣ Делай ставки и выигрывай!\n\n"
        f"🏆 <b>Особенности:</b>\n"
        f"• Ежедневный бонус (5-15 Stars)\n"
        f"• Еженедельный бонус (50 Stars)\n"
        f"• Ежемесячный бонус (200 Stars)\n"
        f"• Система достижений\n"
        f"• Реферальная программа (10% от пополнений друга)\n\n"
        f"👇 <i>Используй кнопки внизу!</i>"
    )
    
    await message.answer(welcome_text, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard())


# ===================== ГЛАВНЫЕ КНОПКИ =====================
@dp.message(F.text == "💰 Баланс")
async def balance_reply(message: Message):
    user_id = message.from_user.id
    await message.answer(
        f"💰 <b>Твой баланс:</b> {format_stars(get_user_balance(user_id))}\n\n"
        f"🎮 Приглашай друзей и зарабатывай больше!\n"
        f"👥 Твоя реферальная ссылка: {generate_referral_link(user_id)}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "⭐️ Пополнить")
async def deposit_reply(message: Message):
    await message.answer(
        "⭐️ <b>Пополнение баланса</b>\n\n"
        "💰 <b>Telegram Stars</b> — внутренняя валюта Telegram\n"
        "• 1 Star = 1 цент (покупка через Apple/Google)\n"
        "• Средства зачисляются мгновенно\n"
        "• Можно вывести обратно в Stars\n\n"
        "👇 <b>Выберите сумму:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_deposit_keyboard()
    )

@dp.message(F.text == "🎮 Игры")
async def games_reply(message: Message):
    await message.answer(
        "🎮 <b>ВЫБЕРИ ИГРУ</b>\n\n"
        "🎲 <b>Кубик</b> — Простой кубик, множители x1-x5\n"
        "🎯 <b>Дартс</b> — Попади в яблочко до x10!\n"
        "⚽️ <b>Футбол</b> — Забей пенальти до x5\n"
        "🏀 <b>Баскетбол</b> — Трёхочковый до x6\n"
        "🎳 <b>Боулинг</b> — Сделай страйк до x10!\n"
        "🎰 <b>Слоты</b> — Классические автоматы\n"
        "💣 <b>Мины</b> — Поле 5x5, множитель до x18\n"
        "🏛 <b>Пирамида</b> — 5 уровней, x16 максимум\n"
        "🎡 <b>Рулетка</b> — Европейская рулетка\n\n"
        "👇 <b>Нажми на кнопку с игрой!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )

@dp.message(F.text == "👥 Рефералы")
async def referrals_reply(message: Message):
    user_id = message.from_user.id
    ref_link = generate_referral_link(user_id)
    ref_count = len(users_referrals.get(user_id, []))
    
    total_earned = 0
    for tx in transactions.get(user_id, []):
        if tx["type"] in ["referral_reward", "referral_earning"]:
            total_earned += tx["amount"]
    
    text = (
        f"👥 <b>РЕФЕРАЛЬНАЯ СИСТЕМА</b>\n\n"
        f"🏆 <b>Твоя статистика:</b>\n"
        f"• Приглашено: {ref_count} чел.\n"
        f"• Заработано: {format_stars(total_earned)}\n\n"
        f"<b>📋 Как это работает:</b>\n"
        f"• Друг получает +{REFERRAL_SIGNUP_BONUS} Stars при регистрации\n"
        f"• Ты получаешь +{REFERRAL_INVITE_BONUS} Stars за приглашение\n"
        f"• Ты получаешь {REFERRAL_BONUS_PERCENT}% от пополнений друга\n\n"
        f"<b>🔗 Твоя реферальная ссылка:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"<b>💡 Совет:</b> Поделись ссылкой в соцсетях и чатах!"
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
        stats = get_user_stats(uid)
        wr = (stats['games_won'] / max(stats['games_played'], 1)) * 100
        top_text += f"{medal} <b>{name}</b>\n   💰 {bal} ⭐️ | 🎮 {stats['games_played']} игр | 📈 {wr:.1f}%\n"
    
    await message.answer(top_text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "📊 Профиль")
async def profile_reply(message: Message):
    uid = message.from_user.id
    stats = get_user_stats(uid)
    wr = (stats['games_won'] / max(stats['games_played'], 1)) * 100
    ref_count = len(users_referrals.get(uid, []))
    achievements = user_achievements.get(uid, [])
    
    text = (
        f"👤 <b>ПРОФИЛЬ ИГРОКА</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👤 Username: @{message.from_user.username or 'нет'}\n"
        f"📅 Регистрация: {users_join_date.get(uid, 'неизвестно')}\n\n"
        f"💰 <b>Баланс:</b> {format_stars(get_user_balance(uid))}\n\n"
        f"📊 <b>СТАТИСТИКА ИГР:</b>\n"
        f"├ 🎮 Сыграно: {stats['games_played']}\n"
        f"├ 🏆 Побед: {stats['games_won']}\n"
        f"├ 📈 Винрейт: {wr:.1f}%\n"
        f"├ 💎 Выиграно: {format_stars(stats['total_won'])}\n"
        f"└ 💸 Проиграно: {format_stars(stats['total_lost'])}\n\n"
        f"🎲 <b>Победы по играм:</b>\n"
        f"├ 🎲 Кубик: {stats['dice_wins']}\n"
        f"├ 🎯 Дартс: {stats['darts_wins']}\n"
        f"├ ⚽️ Футбол: {stats['football_wins']}\n"
        f"├ 🏀 Баскетбол: {stats['basketball_wins']}\n"
        f"├ 🎳 Боулинг: {stats['bowling_wins']}\n"
        f"├ 🎰 Слоты: {stats['slot_wins']}\n"
        f"├ 💣 Мины: {stats['mines_wins']}\n"
        f"├ 🏛 Пирамида: {stats['pyramid_wins']}\n"
        f"└ 🎡 Рулетка: {stats['roulette_wins']}\n\n"
        f"👥 <b>Рефералов:</b> {ref_count}\n\n"
        f"🏅 <b>ДОСТИЖЕНИЯ:</b>\n"
    )
    
    if achievements:
        text += "\n".join([f"├ {ach}" for ach in achievements[:10]])
        if len(achievements) > 10:
            text += f"\n└ ... и ещё {len(achievements)-10}"
    else:
        text += "└ Пока нет достижений. Играй и побеждай!"
    
    text += f"\n\n{get_random_emoji()} Продолжай играть и побеждать!"
    
    await message.answer(text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "🎁 Бонус")
async def bonus_reply(message: Message):
    user_id = message.from_user.id
    today = datetime.now().date().isoformat()
    week = datetime.now().strftime("%Y-W%W")
    month = datetime.now().strftime("%Y-%m")
    
    bonus_text = "🎁 <b>БОНУСЫ</b>\n\n"
    bonus_given = False
    
    # Ежедневный бонус
    if user_last_bonus.get(user_id) != today:
        daily_bonus = random.randint(5, 15)
        update_balance(user_id, daily_bonus)
        user_last_bonus[user_id] = today
        save_transaction(user_id, daily_bonus, "daily_bonus", "Ежедневный бонус")
        bonus_text += f"📅 <b>Ежедневный:</b> +{format_stars(daily_bonus)}\n"
        bonus_given = True
    else:
        bonus_text += f"📅 <b>Ежедневный:</b> ❌ Уже получен\n"
    
    # Еженедельный бонус
    if user_weekly_bonus.get(user_id) != week:
        weekly_bonus = 50
        update_balance(user_id, weekly_bonus)
        user_weekly_bonus[user_id] = week
        save_transaction(user_id, weekly_bonus, "weekly_bonus", "Еженедельный бонус")
        bonus_text += f"📆 <b>Еженедельный:</b> +{format_stars(weekly_bonus)}\n"
        bonus_given = True
    else:
        bonus_text += f"📆 <b>Еженедельный:</b> ❌ Уже получен\n"
    
    # Ежемесячный бонус
    if user_monthly_bonus.get(user_id) != month:
        monthly_bonus = 200
        update_balance(user_id, monthly_bonus)
        user_monthly_bonus[user_id] = month
        save_transaction(user_id, monthly_bonus, "monthly_bonus", "Ежемесячный бонус")
        bonus_text += f"📅 <b>Ежемесячный:</b> +{format_stars(monthly_bonus)}\n"
        bonus_given = True
    else:
        bonus_text += f"📅 <b>Ежемесячный:</b> ❌ Уже получен\n"
    
    bonus_text += f"\n💰 <b>Твой баланс:</b> {format_stars(get_user_balance(user_id))}"
    
    if not bonus_given:
        bonus_text += "\n\n❌ Сегодня ты уже получил все доступные бонусы!"
        bonus_text += "\n⏳ Возвращайся завтра, в понедельник или в начале месяца!"
    
    await message.answer(bonus_text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "🏅 Достижения")
async def achievements_reply(message: Message):
    user_id = message.from_user.id
    stats = get_user_stats(user_id)
    achievements = user_achievements.get(user_id, [])
    
    # Проверяем новые достижения
    if stats['games_played'] >= 10 and "🎮 10 игр сыграно" not in achievements:
        add_achievement(user_id, "🎮 10 игр сыграно")
    if stats['games_played'] >= 100 and "🎮 100 игр сыграно" not in achievements:
        add_achievement(user_id, "🎮 100 игр сыграно")
    if stats['games_played'] >= 1000 and "🎮 1000 игр сыграно" not in achievements:
        add_achievement(user_id, "🎮 1000 игр сыграно")
    if stats['total_won'] >= 1000 and "💰 Выиграно 1000 Stars" not in achievements:
        add_achievement(user_id, "💰 Выиграно 1000 Stars")
    if stats['total_won'] >= 10000 and "💰 Выиграно 10000 Stars" not in achievements:
        add_achievement(user_id, "💰 Выиграно 10000 Stars")
    if stats['games_won'] >= 50 and "🏆 50 побед" not in achievements:
        add_achievement(user_id, "🏆 50 побед")
    if stats['games_won'] >= 500 and "🏆 500 побед" not in achievements:
        add_achievement(user_id, "🏆 500 побед")
    if stats['darts_wins'] >= 10 and "🎯 Мастер дартса" not in achievements:
        add_achievement(user_id, "🎯 Мастер дартса")
    if stats['football_wins'] >= 10 and "⚽️ Легенда футбола" not in achievements:
        add_achievement(user_id, "⚽️ Легенда футбола")
    if stats['basketball_wins'] >= 10 and "🏀 Звезда баскетбола" not in achievements:
        add_achievement(user_id, "🏀 Звезда баскетбола")
    if stats['bowling_wins'] >= 10 and "🎳 Король боулинга" not in achievements:
        add_achievement(user_id, "🎳 Король боулинга")
    if stats['mines_wins'] >= 10 and "💣 Сапёр" not in achievements:
        add_achievement(user_id, "💣 Сапёр")
    if stats['pyramid_wins'] >= 5 and "🏛 Покоритель пирамиды" not in achievements:
        add_achievement(user_id, "🏛 Покоритель пирамиды")
    
    achievements = user_achievements.get(user_id, [])
    
    text = "🏅 <b>ТВОИ ДОСТИЖЕНИЯ</b>\n\n"
    if achievements:
        for ach in achievements:
            text += f"✅ {ach}\n"
    else:
        text += "❌ Пока нет достижений.\n\nИграй и побеждай, чтобы получать награды!"
    
    text += f"\n📊 <b>Прогресс:</b>\n"
    text += f"├ 🎮 Игр сыграно: {stats['games_played']}/1000\n"
    text += f"├ 🏆 Побед: {stats['games_won']}/500\n"
    text += f"└ 💰 Выиграно: {stats['total_won']}/10000 ⭐️"
    
    await message.answer(text, parse_mode=ParseMode.HTML)


# ===================== DICE ИГРЫ (ЧЕРЕЗ sendDice) =====================
async def play_dice_game(message: Message, game_key: str, bet: int, state: FSMContext):
    user_id = message.from_user.id
    
    if get_user_balance(user_id) < bet:
        await message.answer(f"❌ Не хватает {format_stars(bet)}")
        return
    
    game = DICE_GAMES[game_key]
    await state.update_data(dice_game_data={"game": game_key, "bet": bet, "emoji": game["emoji"]})
    
    await message.answer(
        f"{game['emoji']} <b>{game['name']}</b>\n\n"
        f"📋 <b>Правила:</b>\n"
        f"• Выпадает число от 1 до 6\n"
        f"• Чем выше число, тем больше выигрыш!\n\n"
        f"💰 Ставка: {format_stars(bet)}\n\n"
        f"🎲 Максимальный выигрыш: {format_stars(bet * max(game['multipliers'].values()))}\n\n"
        f"👇 <b>Нажми на кнопку, чтобы начать игру!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{game['emoji']} {game['name'].upper()}!", callback_data=f"play_dice_{game_key}")]
        ])
    )

@dp.callback_query(F.data.startswith("play_dice_"))
async def play_dice_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    game_data = data.get("dice_game_data")
    
    if not game_data:
        await callback.answer("Ошибка! Начните игру заново.", show_alert=True)
        return
    
    game_key = game_data["game"]
    bet = game_data["bet"]
    emoji = game_data["emoji"]
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        await state.clear()
        return
    
    update_balance(user_id, -bet)
    
    # Отправляем dice через sendDice
    dice_message = await callback.message.answer_dice(emoji=emoji)
    dice_value = dice_message.dice.value
    
    game = DICE_GAMES[game_key]
    multiplier = game["multipliers"].get(dice_value, 0)
    
    if multiplier > 0:
        win_amount = bet * multiplier
        update_balance(user_id, win_amount)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        
        if game_key == "🎲":
            stats["dice_wins"] += 1
        elif game_key == "🎯":
            stats["darts_wins"] += 1
            if dice_value == 6:
                stats["darts_180"] += 1
                if stats["darts_180"] >= 10 and "🎯 10 яблочек" not in user_achievements.get(user_id, []):
                    add_achievement(user_id, "🎯 10 яблочек")
        elif game_key == "⚽️":
            stats["football_wins"] += 1
            if dice_value >= 5:
                stats["football_hattrick"] += 1
                if stats["football_hattrick"] >= 5 and "⚽️ 5 хет-триков" not in user_achievements.get(user_id, []):
                    add_achievement(user_id, "⚽️ 5 хет-триков")
        elif game_key == "🏀":
            stats["basketball_wins"] += 1
            if dice_value == 6:
                stats["basketball_perfect"] += 1
                if stats["basketball_perfect"] >= 5 and "🏀 5 баззер-битеров" not in user_achievements.get(user_id, []):
                    add_achievement(user_id, "🏀 5 баззер-битеров")
        elif game_key == "🎳":
            stats["bowling_wins"] += 1
            if dice_value >= 5:
                stats["bowling_strike"] += 1
                if stats["bowling_strike"] >= 10 and "🎳 10 страйков" not in user_achievements.get(user_id, []):
                    add_achievement(user_id, "🎳 10 страйков")
        elif game_key == "🎰":
            stats["slot_wins"] += 1
            
        stats["total_won"] += win_amount
        save_transaction(user_id, win_amount, "game_win", f"{game['name']} x{multiplier}")
        
        result_text = (
            f"🎉 <b>ВЫИГРЫШ!</b> 🎉\n\n"
            f"{game['win_texts'].get(dice_value, 'Отличный результат!')}\n"
            f"✨ Множитель: <b>x{multiplier}</b>\n"
            f"🏆 Выигрыш: <b>+{format_stars(win_amount)}</b>"
        )
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", game['name'])
        result_text = f"😢 <b>Проигрыш</b>\n\n-{format_stars(bet)}"
    
    await callback.message.answer(
        f"{emoji} <b>{game['name']}</b>\n\n"
        f"🎲 <b>Результат: {dice_value}</b>\n"
        f"{game['descriptions'].get(dice_value, '')}\n\n"
        f"💰 Ставка: {format_stars(bet)}\n\n"
        f"{result_text}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await state.clear()
    await callback.answer()


# ---------- ОБРАБОТЧИКИ ДЛЯ КАЖДОЙ ИГРЫ ----------
@dp.message(F.text == "🎲 Кубик")
async def cube_start(message: Message):
    await message.answer(
        "🎲 <b>ИГРА КУБИК</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• 1-2 → проигрыш\n"
        "• 3 → x1\n"
        "• 4 → x2\n"
        "• 5 → x3\n"
        "• 6 → x5\n\n"
        "🎲 Максимальный выигрыш: x5\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("dice")
    )

@dp.callback_query(F.data.startswith("dice_bet_"))
async def cube_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    await state.update_data(dice_game_data={"game": "🎲", "bet": bet, "emoji": "🎲"})
    await callback.message.delete()
    await callback.message.answer(
        f"🎲 <b>КУБИК</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"🎯 Макс. выигрыш: {format_stars(bet * 5)}\n\n"
        f"👇 <b>Нажми на кнопку, чтобы бросить кубик!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎲 БРОСИТЬ КУБИК", callback_data="play_dice_🎲")]
        ])
    )
    await callback.answer()

@dp.message(F.text == "🎯 Дартс")
async def darts_start(message: Message):
    await message.answer(
        "🎯 <b>ИГРА ДАРТС</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• 1-2 → мимо\n"
        "• 3 → x1\n"
        "• 4 → x2\n"
        "• 5 → x4\n"
        "• 6 → ЯБЛОЧКО x10!\n\n"
        "🎯 Максимальный выигрыш: x10\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("darts")
    )

@dp.callback_query(F.data.startswith("darts_bet_"))
async def darts_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    await state.update_data(dice_game_data={"game": "🎯", "bet": bet, "emoji": "🎯"})
    await callback.message.delete()
    await callback.message.answer(
        f"🎯 <b>ДАРТС</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"🎯 Макс. выигрыш: {format_stars(bet * 10)}\n\n"
        f"👇 <b>Нажми на кнопку, чтобы бросить дротик!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎯 БРОСИТЬ ДРОТИК", callback_data="play_dice_🎯")]
        ])
    )
    await callback.answer()

@dp.message(F.text == "⚽️ Футбол")
async def football_start(message: Message):
    await message.answer(
        "⚽️ <b>ИГРА ФУТБОЛ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• 1-2 → сейв вратаря\n"
        "• 3 → гол x1\n"
        "• 4 → гол с рикошетом x2\n"
        "• 5 → красивый гол x3\n"
        "• 6 → победный гол x5!\n\n"
        "⚽️ Максимальный выигрыш: x5\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("football")
    )

@dp.callback_query(F.data.startswith("football_bet_"))
async def football_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    await state.update_data(dice_game_data={"game": "⚽️", "bet": bet, "emoji": "⚽️"})
    await callback.message.delete()
    await callback.message.answer(
        f"⚽️ <b>ФУТБОЛ</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"⚽️ Макс. выигрыш: {format_stars(bet * 5)}\n\n"
        f"👇 <b>Нажми на кнопку, чтобы пробить пенальти!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚽️ ПРОБИТЬ ПЕНАЛЬТИ", callback_data="play_dice_⚽️")]
        ])
    )
    await callback.answer()

@dp.message(F.text == "🏀 Баскетбол")
async def basketball_start(message: Message):
    await message.answer(
        "🏀 <b>ИГРА БАСКЕТБОЛ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• 1-2 → промах\n"
        "• 3 → очко x1\n"
        "• 4 → из-за дуги x2\n"
        "• 5 → аллей-уп x4\n"
        "• 6 → баззер-битер x6!\n\n"
        "🏀 Максимальный выигрыш: x6\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("basketball")
    )

@dp.callback_query(F.data.startswith("basketball_bet_"))
async def basketball_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    await state.update_data(dice_game_data={"game": "🏀", "bet": bet, "emoji": "🏀"})
    await callback.message.delete()
    await callback.message.answer(
        f"🏀 <b>БАСКЕТБОЛ</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"🏀 Макс. выигрыш: {format_stars(bet * 6)}\n\n"
        f"👇 <b>Нажми на кнопку, чтобы бросить мяч!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏀 БРОСИТЬ МЯЧ", callback_data="play_dice_🏀")]
        ])
    )
    await callback.answer()

@dp.message(F.text == "🎳 Боулинг")
async def bowling_start(message: Message):
    await message.answer(
        "🎳 <b>ИГРА БОУЛИНГ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• 1-2 → промах\n"
        "• 3 → спэр x1\n"
        "• 4 → страйк x2\n"
        "• 5 → идеальный x5\n"
        "• 6 → 10 страйков x10!\n\n"
        "🎳 Максимальный выигрыш: x10\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("bowling")
    )

@dp.callback_query(F.data.startswith("bowling_bet_"))
async def bowling_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    await state.update_data(dice_game_data={"game": "🎳", "bet": bet, "emoji": "🎳"})
    await callback.message.delete()
    await callback.message.answer(
        f"🎳 <b>БОУЛИНГ</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"🎳 Макс. выигрыш: {format_stars(bet * 10)}\n\n"
        f"👇 <b>Нажми на кнопку, чтобы бросить шар!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎳 БРОСИТЬ ШАР", callback_data="play_dice_🎳")]
        ])
    )
    await callback.answer()

@dp.message(F.text == "🎰 Слоты")
async def slots_start(message: Message):
    await message.answer(
        "🎰 <b>ИГРА СЛОТЫ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• 1-2 → проигрыш\n"
        "• 3 → x1\n"
        "• 4 → x2\n"
        "• 5 → x3\n"
        "• 6 → ДЖЕКПОТ x5!\n\n"
        "🎰 Максимальный выигрыш: x5\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("slots")
    )

@dp.callback_query(F.data.startswith("slots_bet_"))
async def slots_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    await state.update_data(dice_game_data={"game": "🎰", "bet": bet, "emoji": "🎰"})
    await callback.message.delete()
    await callback.message.answer(
        f"🎰 <b>СЛОТЫ</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"🎰 Макс. выигрыш: {format_stars(bet * 5)}\n\n"
        f"👇 <b>Нажми на кнопку, чтобы крутить слоты!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎰 КРУТИТЬ СЛОТЫ", callback_data="play_dice_🎰")]
        ])
    )
    await callback.answer()


# ---------- РУЛЕТКА ----------
@dp.message(F.text == "🎡 Рулетка")
async def roulette_start(message: Message, state: FSMContext):
    await message.answer(
        "🎡 <b>ЕВРОПЕЙСКАЯ РУЛЕТКА</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• Красное/Черное → x2\n"
        "• Четное/Нечетное → x2\n"
        "• 1-18/19-36 → x2\n"
        "• Зеро (0) → x35\n"
        "• Точное число → x35\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("roulette")
    )

@dp.callback_query(F.data.startswith("roulette_bet_"))
async def roulette_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    await state.update_data(roulette_bet=bet)
    await callback.message.edit_text(
        f"🎡 <b>РУЛЕТКА</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n\n"
        f"👇 <b>Выбери тип ставки:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_roulette_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("roulette_"))
async def roulette_play(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet = data.get("roulette_bet", 5)
    bet_type = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    update_balance(user_id, -bet)
    
    result = random.randint(0, 36)
    win = False
    multiplier = 0
    
    if bet_type == "red":
        red_numbers = [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]
        if result in red_numbers:
            win, multiplier = True, 2
    elif bet_type == "black":
        black_numbers = [2,4,6,8,10,11,13,15,17,20,22,24,26,28,29,31,33,35]
        if result in black_numbers:
            win, multiplier = True, 2
    elif bet_type == "zero":
        if result == 0:
            win, multiplier = True, 35
    elif bet_type == "even":
        if result > 0 and result % 2 == 0:
            win, multiplier = True, 2
    elif bet_type == "odd":
        if result > 0 and result % 2 == 1:
            win, multiplier = True, 2
    elif bet_type == "low":
        if 1 <= result <= 18:
            win, multiplier = True, 2
    elif bet_type == "high":
        if 19 <= result <= 36:
            win, multiplier = True, 2
    elif bet_type == "number":
        await callback.message.answer("🎯 Введи число от 0 до 36:")
        await state.set_state(GameStates.roulette_game)
        await state.update_data(roulette_bet=bet)
        await callback.answer()
        return
    
    if win:
        winnings = bet * multiplier
        update_balance(user_id, winnings)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["roulette_wins"] += 1
        stats["total_won"] += winnings
        save_transaction(user_id, winnings, "game_win", f"Рулетка x{multiplier}")
        res_text = f"🎉 <b>ВЫИГРЫШ!</b> +{format_stars(winnings)}"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", "Рулетка")
        res_text = f"😢 <b>Проигрыш</b> -{format_stars(bet)}"
    
    # Цвет результата
    red_numbers = [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]
    if result == 0:
        color = "🟢"
    elif result in red_numbers:
        color = "🔴"
    else:
        color = "⚫️"
    
    await callback.message.edit_text(
        f"🎡 <b>РУЛЕТКА</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"🎲 Выпало: <b>{result}</b> {color}\n\n"
        f"{res_text}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await state.clear()
    await callback.answer()

@dp.message(GameStates.roulette_game)
async def roulette_number_bet(message: Message, state: FSMContext):
    try:
        number = int(message.text.strip())
        if number < 0 or number > 36:
            await message.answer("❌ Введи число от 0 до 36!")
            return
        
        data = await state.get_data()
        bet = data.get("roulette_bet", 5)
        user_id = message.from_user.id
        
        update_balance(user_id, -bet)
        
        result = random.randint(0, 36)
        
        if result == number:
            winnings = bet * 35
            update_balance(user_id, winnings)
            stats = get_user_stats(user_id)
            stats["games_played"] += 1
            stats["games_won"] += 1
            stats["roulette_wins"] += 1
            stats["total_won"] += winnings
            save_transaction(user_id, winnings, "game_win", f"Рулетка число x35")
            res_text = f"🎉 <b>ВЫИГРЫШ!</b> +{format_stars(winnings)}"
        else:
            stats = get_user_stats(user_id)
            stats["games_played"] += 1
            stats["total_lost"] += bet
            save_transaction(user_id, -bet, "game_loss", "Рулетка число")
            res_text = f"😢 <b>Проигрыш</b> -{format_stars(bet)}"
        
        # Цвет результата
        red_numbers = [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]
        if result == 0:
            color = "🟢"
        elif result in red_numbers:
            color = "🔴"
        else:
            color = "⚫️"
        
        await message.answer(
            f"🎡 <b>РУЛЕТКА</b>\n\n"
            f"💰 Ставка: {format_stars(bet)}\n"
            f"🎲 Выпало: <b>{result}</b> {color}\n"
            f"🎯 Твоё число: <b>{number}</b>\n\n"
            f"{res_text}\n\n"
            f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_games_keyboard()
        )
        await state.clear()
    except ValueError:
        await message.answer("❌ Введи число!")


# ---------- МИНЫ ----------
active_mines_games: Dict[int, dict] = {}

@dp.message(F.text == "💣 Мины")
async def mines_start(message: Message):
    await message.answer(
        "💣 <b>ИГРА МИНЫ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• Поле 5x5, скрыто 5 мин\n"
        "• 💎 → множитель x1.2\n"
        "• 💣 → мгновенный проигрыш\n"
        "• Максимальный множитель: x18\n"
        "• Можно забрать выигрыш в любой момент\n\n"
        "💣 Рискни и увеличь выигрыш!\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("mines")
    )

@dp.callback_query(F.data.startswith("mines_bet_"))
async def mines_init(callback: CallbackQuery):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
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
    
    max_win = int(bet * (1.2 ** 20))
    
    await callback.message.edit_text(
        f"💣 <b>МИНЫ</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"✨ Множитель: x{active_mines_games[user_id]['multiplier']:.1f}\n"
        f"📦 Открыто клеток: 0/20\n"
        f"🏆 Потенциальный выигрыш: {format_stars(max_win)}\n\n"
        f"👇 <b>Открывай 💎 и избегай 💣!</b>\n"
        f"💰 Нажми «Забрать» чтобы выйти с выигрышем",
        parse_mode=ParseMode.HTML,
        reply_markup=get_mines_board_keyboard(board, active_mines_games[user_id]["revealed"], bet, 1.0, 0)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("mine_"))
async def mines_reveal(callback: CallbackQuery):
    user_id = callback.from_user.id
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
        max_win = int(game["bet"] * (1.2 ** 20))
        
        await callback.message.edit_text(
            f"💣 <b>МИНЫ</b>\n\n"
            f"💰 Ставка: {format_stars(game['bet'])}\n"
            f"✨ Множитель: x{game['multiplier']:.1f}\n"
            f"💎 Найдено сокровищ: {game['cells_opened']}/20\n"
            f"💰 Текущий выигрыш: {format_stars(current_win)}\n"
            f"🏆 Макс. выигрыш: {format_stars(max_win)}\n\n"
            f"✅ <b>Ты нашёл 💎! Множитель увеличен!</b>\n\n"
            f"👇 <b>Продолжай открывать или забери выигрыш!</b>",
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
            add_achievement(user_id, "💣 Сапёр")
            del active_mines_games[user_id]
            
            await callback.message.edit_text(
                f"💣 <b>МИНЫ</b>\n\n"
                f"🎉 <b>ПОБЕДА!</b> Ты очистил всё поле! 🎉\n\n"
                f"📦 Открыто клеток: 20/20\n"
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
    save_transaction(user_id, win, "game_win", f"Мины кэшаут {game['cells_opened']} клеток x{game['multiplier']:.1f}")
    del active_mines_games[user_id]
    
    await callback.message.edit_text(
        f"💣 <b>МИНЫ</b>\n\n"
        f"💰 <b>Ты забрал выигрыш!</b> 💰\n\n"
        f"📦 Открыто клеток: {game['cells_opened']}/20\n"
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
        "🏛 <b>ИГРА ПИРАМИДА</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• 5 уровней\n"
        "• Каждый шаг удваивает выигрыш\n"
        "• Шанс успеха: 50%\n"
        "• Проигрыш = потеря ставки\n"
        "• На 5 уровне множитель x16!\n\n"
        "🏛 Максимальный выигрыш: x16\n\n"
        "Выбери начальную ставку:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("pyramid")
    )

@dp.callback_query(F.data.startswith("pyramid_bet_"))
async def pyramid_init(callback: CallbackQuery):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
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
        f"📊 Шанс успеха: 50%\n"
        f"✨ Макс. множитель: x16\n\n"
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
            save_transaction(user_id, game["current"], "game_win", f"Пирамида победа уровень {game['level']}")
            add_achievement(user_id, "🏛 Покоритель пирамиды")
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
                f"🏆 <b>Уровень {game['level']} / 5</b>\n"
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
    save_transaction(user_id, win, "game_win", f"Пирамида кэшаут уровень {game['level']} x{win // game['bet']}")
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


# ===================== АДМИН-ПАНЕЛЬ =====================
@dp.message(F.text == "👑 Админ панель")
async def admin_panel_reply(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ У вас нет доступа к админ-панели!", reply_markup=get_main_keyboard())
        return
    
    await message.answer(
        "👑 <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n\n"
        "📊 <b>Доступные действия:</b>\n"
        "• Просмотр статистики бота\n"
        "• Изменение баланса пользователей\n"
        "• Рассылка сообщений\n"
        "• Список всех пользователей\n"
        "• Логи транзакций\n"
        "• Сброс винрейта\n"
        "• Изменение множителей игр\n"
        "• Резервное копирование данных\n"
        "• Выгрузка/загрузка JSON\n\n"
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
    
    text = (
        f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
        f"👥 <b>Пользователей:</b> {total_users}\n"
        f"💰 <b>Общий баланс:</b> {format_stars(total_balance)}\n"
        f"🎮 <b>Всего игр:</b> {total_games}\n"
        f"🏆 <b>Всего побед:</b> {total_wins}\n"
    )
    if total_games > 0:
        text += f"📈 <b>Общий винрейт:</b> {(total_wins/total_games*100):.1f}%\n"
    text += (
        f"💸 <b>Пополнений:</b> {total_deposits}\n"
        f"💸 <b>Сумма пополнений:</b> {format_stars(deposit_sum)}\n\n"
        f"💰 <b>Средний баланс:</b> {format_stars(total_balance // total_users if total_users > 0 else 0)}\n"
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

@dp.message(F.text == "📢 Рассылка")
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
        f"📊 <b>Получателей:</b> {len(users_balance)} человек\n\n"
        "<b>Внимание!</b> Рассылка придёт ВСЕМ пользователям бота!\n\n"
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
        stats = get_user_stats(uid)
        users_list.append(f"@{uname or str(uid)} — {balance}⭐️ | 🎮 {stats['games_played']} игр | 🏆 {stats['games_won']} побед")
    
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
        for tx in tx_list[-10:]:
            all_txs.append((tx["timestamp"], f"@{uname}: {tx['type']} {tx['amount']}⭐️ - {tx['details']}"))
    
    all_txs.sort(reverse=True)
    recent = all_txs[:50]
    
    if not recent:
        text = "📜 Логов транзакций пока нет"
    else:
        text = "📜 <b>ПОСЛЕДНИЕ ТРАНЗАКЦИИ</b>\n\n" + "\n".join([f"• {tx[1]}" for tx in recent])
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "🏆 Сбросить винрейт")
async def admin_reset_stats(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    for uid in users_stats:
        users_stats[uid]["games_played"] = 0
        users_stats[uid]["games_won"] = 0
        users_stats[uid]["total_won"] = 0
        users_stats[uid]["total_lost"] = 0
    
    await message.answer(
        "✅ <b>Статистика всех пользователей сброшена!</b>\n\n"
        "🎮 Винрейт обнулён для всех игроков.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard()
    )

@dp.message(F.text == "🎮 Изменить множители")
async def admin_edit_game(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    games_list = "\n".join([f"• {g['emoji']} {g['name']}" for g in DICE_GAMES.values()])
    
    await state.set_state(GameStates.admin_edit_game)
    await message.answer(
        "🎮 <b>ИЗМЕНЕНИЕ МНОЖИТЕЛЕЙ</b>\n\n"
        f"<b>Доступные игры:</b>\n{games_list}\n\n"
        "Введи название игры и множители в формате:\n"
        "<code>🎲 1:0,2:0,3:1,4:2,5:3,6:5</code>\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(GameStates.admin_edit_game)
async def admin_edit_game_handler(message: Message, state: FSMContext):
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
        parts = message.text.split(" ")
        emoji = parts[0]
        multipliers_str = parts[1]
        
        if emoji not in DICE_GAMES:
            await message.answer("❌ Игра не найдена! Используй эмодзи из списка.")
            return
        
        multipliers = {}
        for item in multipliers_str.split(","):
            k, v = item.split(":")
            multipliers[int(k)] = int(v)
        
        DICE_GAMES[emoji]["multipliers"] = multipliers
        
        await state.clear()
        await message.answer(
            f"✅ Множители для {DICE_GAMES[emoji]['name']} обновлены!\n\n"
            f"Новые множители: {multipliers}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка формата! Попробуй снова.\n{e}")

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
        "achievements": user_achievements
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
        await message.answer(
            f"❌ <b>Ошибка сохранения:</b>\n<code>{e}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )

@dp.message(F.text == "📤 Выгрузить JSON")
async def admin_export(message: Message):
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
        "achievements": user_achievements,
        "dice_games": DICE_GAMES
    }
    
    try:
        with open("backup.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        await message.answer_document(
            types.FSInputFile("backup.json"),
            caption="📤 <b>Экспорт данных</b>\n\nВсе данные бота выгружены в файл.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка выгрузки: {e}",
            reply_markup=get_admin_panel_keyboard()
        )

@dp.message(F.text == "📥 Загрузить JSON")
async def admin_import(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_send_broadcast)  # Временное состояние
    await message.answer(
        "📥 <b>ЗАГРУЗКА JSON</b>\n\n"
        "Отправь файл backup.json для восстановления данных.\n\n"
        "<b>Внимание!</b> Это перезапишет текущие данные!\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

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
    stats = get_user_stats(user_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ +100", callback_data="admin_add_100"),
         InlineKeyboardButton(text="➕ +500", callback_data="admin_add_500")],
        [InlineKeyboardButton(text="➕ +1000", callback_data="admin_add_1000"),
         InlineKeyboardButton(text="➕ +5000", callback_data="admin_add_5000")],
        [InlineKeyboardButton(text="➕ +10000", callback_data="admin_add_10000"),
         InlineKeyboardButton(text="➕ +50000", callback_data="admin_add_50000")],
        [InlineKeyboardButton(text="➖ -100", callback_data="admin_remove_100"),
         InlineKeyboardButton(text="➖ -500", callback_data="admin_remove_500")],
        [InlineKeyboardButton(text="➖ -1000", callback_data="admin_remove_1000"),
         InlineKeyboardButton(text="➖ -5000", callback_data="admin_remove_5000")],
        [InlineKeyboardButton(text="➖ -10000", callback_data="admin_remove_10000"),
         InlineKeyboardButton(text="✏️ Своя сумма", callback_data="admin_custom")],
        [InlineKeyboardButton(text="🎮 Сбросить статистику", callback_data="admin_reset_stats")],
        [InlineKeyboardButton(text="◀️ Назад в админ-панель", callback_data="admin_back_to_panel")]
    ])
    
    await message.answer(
        f"💰 <b>ИЗМЕНЕНИЕ БАЛАНСА</b>\n\n"
        f"👤 Пользователь: @{input_text}\n"
        f"💰 Текущий баланс: {format_stars(current_balance)}\n"
        f"🎮 Игр сыграно: {stats['games_played']}\n"
        f"🏆 Побед: {stats['games_won']}\n\n"
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
    
    if callback.data == "admin_reset_stats":
        stats = get_user_stats(target_user)
        stats["games_played"] = 0
        stats["games_won"] = 0
        stats["total_won"] = 0
        stats["total_lost"] = 0
        stats["dice_wins"] = 0
        stats["darts_wins"] = 0
        stats["football_wins"] = 0
        stats["basketball_wins"] = 0
        stats["bowling_wins"] = 0
        stats["slot_wins"] = 0
        stats["mines_wins"] = 0
        stats["pyramid_wins"] = 0
        stats["roulette_wins"] = 0
        
        await callback.message.edit_text(
            f"✅ Статистика пользователя @{target_username} сброшена!",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )
        await state.clear()
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
    
    progress_msg = await message.answer(f"📢 <b>Начинаю рассылку...</b>\n\n⏳ Пожалуйста, подождите...\n👥 Всего пользователей: {len(users_balance)}", parse_mode=ParseMode.HTML)
    
    for user_id in users_balance.keys():
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

@dp.message(GameStates.admin_send_broadcast)
async def admin_import_handler(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await state.clear()
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Операция отменена.", reply_markup=get_admin_panel_keyboard())
        return
    
    if message.document:
        try:
            file = await bot.get_file(message.document.file_id)
            file_path = f"downloaded_{message.document.file_name}"
            await bot.download_file(file.file_path, file_path)
            
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Восстанавливаем данные
            users_balance.update(data.get("balance", {}))
            users_referrer.update(data.get("referrer", {}))
            users_referrals.update(data.get("referrals", {}))
            users_stats.update(data.get("stats", {}))
            transactions.update(data.get("transactions", {}))
            users_username.update(data.get("username", {}))
            users_join_date.update(data.get("join_date", {}))
            user_achievements.update(data.get("achievements", {}))
            
            await state.clear()
            await message.answer(
                "✅ <b>Данные успешно загружены!</b>\n\n"
                f"👥 Загружено пользователей: {len(users_balance)}\n"
                f"💾 Размер файла: {len(json.dumps(data))} байт",
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_panel_keyboard()
            )
        except Exception as e:
            await message.answer(f"❌ Ошибка загрузки: {e}", reply_markup=get_admin_panel_keyboard())
    else:
        await message.answer("❌ Отправь файл JSON!")


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
            "Максимум: 100000 Stars\n\n"
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
        if 1 <= amount <= 100000:
            await state.clear()
            await create_stars_invoice(message, message.from_user.id, amount)
        else:
            await message.answer("❌ Введи число от 1 до 100000")
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


# ===================== НАВИГАЦИОННЫЕ CALLBACK =====================
@dp.callback_query(F.data == "back_to_games")
async def back_to_games_callback(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer(
        "🎮 <b>Выбери игру</b>\n\n"
        "👇 Нажми на кнопку с игрой:",
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


# ===================== ЗАПУСК =====================
async def main():
    logger.info("🚀 StarPlay Bot запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())