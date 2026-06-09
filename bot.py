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
users_warnings: Dict[int, int] = {}
users_mutes: Dict[int, dict] = {}
users_bans: Dict[int, bool] = {}

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
    dice_game = State()
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
            "roulette_wins": 0, "darts_wins": 0, "football_wins": 0,
            "bowling_wins": 0, "basketball_wins": 0, "mines_wins": 0,
            "pyramid_wins": 0, "slots_wins": 0, "volleyball_wins": 0,
            "hockey_wins": 0, "golf_wins": 0, "tennis_wins": 0
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


# ===================== ПРАВИЛА ИГР ЧЕРЕЗ DICE =====================
# Все игры используют метод sendDice с разными эмодзи
# Значения dice от 1 до 6

DICE_GAMES = {
    "🎲": {  # Кубик
        "name": "Кубик",
        "emoji": "🎲",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 3, 6: 5},
        "results": {
            1: "😭 Ужасный результат! Ставка проиграна.",
            2: "😢 Обидный промах... В следующий раз повезёт!",
            3: "🤔 Неплохо, но могло быть лучше! +x1",
            4: "😊 Хороший результат! +x2",
            5: "😎 Отличный бросок! +x3",
            6: "🤯 ДЖЕКПОТ! +x5"
        }
    },
    "🎯": {  # Дартс
        "name": "Дартс",
        "emoji": "🎯",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 4, 6: 10},
        "results": {
            1: "💨 Дротик пролетел мимо! Проигрыш.",
            2: "🎯 Попал в молоко! Почти... Проигрыш.",
            3: "🎯 Попадание в 20! +x1",
            4: "🎯 Тройное попадание! +x2",
            5: "🎯 БЫЧИЙ ГЛАЗ! +x4",
            6: "🎯 ЯБЛОЧКО!!! ДЖЕКПОТ x10! 🔥"
        }
    },
    "⚽️": {  # Футбол
        "name": "Футбол",
        "emoji": "⚽️",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 3, 6: 5},
        "results": {
            1: "🧤 Вратарь поймал мяч! Проигрыш.",
            2: "📐 Удар в штангу! Проигрыш.",
            3: "⚽️ ГОЛ! +x1",
            4: "⚽️ ГОЛ с рикошета! +x2",
            5: "⚽️ КРАСИВЫЙ ГОЛ! +x3",
            6: "⚽️ ШЕДЕВР! Удар через себя! ДЖЕКПОТ x5!"
        }
    },
    "🏀": {  # Баскетбол
        "name": "Баскетбол",
        "emoji": "🏀",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 4, 6: 6},
        "results": {
            1: "🏀 Воздух! Мяч улетел на трибуны. Проигрыш.",
            2: "🏀 Щит! Мяч отскочил. Проигрыш.",
            3: "🏀 ПОПАДАНИЕ! +x1",
            4: "🏀 СВЕРХУ! +x2",
            5: "🏀 ТРЁХОЧКОВЫЙ! +x4",
            6: "🏀 БАЗЗЕР БИТЕР! ПОБЕДА! ДЖЕКПОТ x6!"
        }
    },
    "🎳": {  # Боулинг
        "name": "Боулинг",
        "emoji": "🎳",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 5, 6: 10},
        "results": {
            1: "🎳 Желоб! Шар упал в желоб. Проигрыш.",
            2: "🎳 Сбито мало кеглей. Проигрыш.",
            3: "🎳 СПЭР! +x1",
            4: "🎳 СТРАЙК! +x2",
            5: "🎳 ИДЕАЛЬНЫЙ СТРАЙК! +x5",
            6: "🎳 ДЕСЯТЬ СТРАЙКОВ! ДЖЕКПОТ x10!"
        }
    },
    "🏐": {  # Волейбол (НОВАЯ ИГРА)
        "name": "Волейбол",
        "emoji": "🏐",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 4, 6: 8},
        "results": {
            1: "🏐 Мяч в аут! Проигрыш.",
            2: "🏐 Сетка! Мяч застрял. Проигрыш.",
            3: "🏐 Подача принята! +x1",
            4: "🏐 АТАКА! +x2",
            5: "🏐 БЛОК! +x4",
            6: "🏐 ЭЙС! ПОДАЧА НА ВЫЛЕТ! ДЖЕКПОТ x8!"
        }
    },
    "🏒": {  # Хоккей (НОВАЯ ИГРА)
        "name": "Хоккей",
        "emoji": "🏒",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 3, 5: 5, 6: 10},
        "results": {
            1: "🏒 Вратарь отбил шайбу! Проигрыш.",
            2: "🏒 Штанга! Проигрыш.",
            3: "🏒 ГОЛ! +x1",
            4: "🏒 ГОЛ с рикошета! +x3",
            5: "🏒 БУЛЛИТ! +x5",
            6: "🏒 ХЕТ-ТРИК! ДЖЕКПОТ x10!"
        }
    },
    "⛳️": {  # Гольф (НОВАЯ ИГРА)
        "name": "Гольф",
        "emoji": "⛳️",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 4, 6: 8},
        "results": {
            1: "⛳️ Бункер! Проигрыш.",
            2: "⛳️ Оvershoot! Перелёт. Проигрыш.",
            3: "⛳️ Пар! +x1",
            4: "⛳️ Бёрди! +x2",
            5: "⛳️ Игл! +x4",
            6: "⛳️ АЛЬБАТРОС! ДЖЕКПОТ x8!"
        }
    },
    "🎾": {  # Теннис (НОВАЯ ИГРА)
        "name": "Теннис",
        "emoji": "🎾",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 4, 6: 8},
        "results": {
            1: "🎾 Аут! Проигрыш.",
            2: "🎾 Сетка! Проигрыш.",
            3: "🎾 Эйс! +x1",
            4: "🎾 СМЭШ! +x2",
            5: "🎾 ПРОХОДНОЙ УДАР! +x4",
            6: "🎾 ТВИНЕР! ДЖЕКПОТ x8!"
        }
    }
}

# Настройки для админ-панели
PROMO_MESSAGE = "🎉 Добро пожаловать в StarPlay!\nИграй и выигрывай Telegram Stars!"
COIN_PRICE = 100  # Stars за 1 монету
DAILY_BONUS_RANGE = (5, 15)
WIN_CHANCES = {}


# ===================== КЛАВИАТУРЫ =====================
def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Главная клавиатура"""
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
    """Расширенная клавиатура админ-панели (20+ функций)"""
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
    builder.button(text="📊 Топ по играм")
    builder.button(text="🔙 В главное меню")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_games_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура игр (все 9 игр)"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="🎲 Кубик")
    builder.button(text="🎯 Дартс")
    builder.button(text="⚽️ Футбол")
    builder.button(text="🏀 Баскетбол")
    builder.button(text="🎳 Боулинг")
    builder.button(text="🏐 Волейбол")
    builder.button(text="🏒 Хоккей")
    builder.button(text="⛳️ Гольф")
    builder.button(text="🎾 Теннис")
    builder.button(text="🎰 Слоты")
    builder.button(text="💣 Мины")
    builder.button(text="🏛 Пирамида")
    builder.button(text="🔙 Главное меню")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_bet_keyboard(game_key: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора ставки для игры"""
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

def get_slots_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для слотов"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Крутить (5⭐️)", callback_data="slots_spin_5"),
         InlineKeyboardButton(text="🎰 Крутить (10⭐️)", callback_data="slots_spin_10")],
        [InlineKeyboardButton(text="🎰 Крутить (25⭐️)", callback_data="slots_spin_25"),
         InlineKeyboardButton(text="🎰 Крутить (50⭐️)", callback_data="slots_spin_50")],
        [InlineKeyboardButton(text="🎰 Крутить (100⭐️)", callback_data="slots_spin_100"),
         InlineKeyboardButton(text="🎰 Крутить (250⭐️)", callback_data="slots_spin_250")],
        [InlineKeyboardButton(text="🎰 Крутить (500⭐️)", callback_data="slots_spin_500"),
         InlineKeyboardButton(text="🎰 Крутить (1000⭐️)", callback_data="slots_spin_1000")],
        [InlineKeyboardButton(text="◀️ Назад к играм", callback_data="back_to_games")]
    ])

def get_mines_board_keyboard(board, revealed, bet, multiplier, cells_opened) -> InlineKeyboardMarkup:
    """Клавиатура для игры Мины"""
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
    """Клавиатура для игры Пирамида"""
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
        f"<b>🎮 Доступные игры (9):</b>\n"
        f"🎲 Кубик | 🎯 Дартс | ⚽️ Футбол\n"
        f"🏀 Баскетбол | 🎳 Боулинг | 🏐 Волейбол\n"
        f"🏒 Хоккей | ⛳️ Гольф | 🎾 Теннис\n"
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
        f"🎮 Приглашай друзей и зарабатывай больше!\n"
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
        "💰 Средства зачисляются мгновенно после оплаты!\n"
        f"💵 Курс: 1 Star = 1 XTR (Telegram Star)",
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
        "🎲 <b>Кубик</b> — Простой кубик, множители до x5\n"
        "🎯 <b>Дартс</b> — Попади в яблочко и получи x10!\n"
        "⚽️ <b>Футбол</b> — Забей пенальти, множители до x5\n"
        "🏀 <b>Баскетбол</b> — Трёхочковый бросок до x6\n"
        "🎳 <b>Боулинг</b> — Сделай страйк и получи x10!\n"
        "🏐 <b>Волейбол</b> — Эйс подача до x8\n"
        "🏒 <b>Хоккей</b> — Забей шайбу до x10\n"
        "⛳️ <b>Гольф</b> — Альбатрос до x8\n"
        "🎾 <b>Теннис</b> — Твинер до x8\n"
        "🎰 <b>Слоты</b> — Классические автоматы до x50\n"
        "💣 <b>Мины</b> — Рискни и увеличь выигрыш до x18\n"
        "🏛 <b>Пирамида</b> — Поднимайся выше до x16\n\n"
        "👇 <i>Нажми на кнопку с игрой!</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )


# ===================== DICE ИГРЫ (ВСЕ 9 ИГР ЧЕРЕЗ sendDice) =====================
async def play_dice_game(message: Message, game_key: str, bet: int, state: FSMContext):
    """Универсальная функция для запуска dice игры через sendDice"""
    user_id = message.from_user.id
    
    if users_bans.get(user_id, False):
        await message.answer("❌ Вы забанены! Обратитесь к администратору.")
        return
    
    if get_user_balance(user_id) < bet:
        await message.answer(f"❌ Не хватает {format_stars(bet)}")
        return
    
    game = DICE_GAMES[game_key]
    await state.update_data(dice_game_data={"game": game_key, "bet": bet, "emoji": game["emoji"]})
    
    # Отправляем dice через sendDice
    dice_message = await message.answer_dice(emoji=game["emoji"])
    dice_value = dice_message.dice.value
    
    update_balance(user_id, -bet)
    
    multiplier = game["multipliers"].get(dice_value, 0)
    result_text = game["results"].get(dice_value, "Результат...")
    
    if multiplier > 0:
        win_amount = bet * multiplier
        update_balance(user_id, win_amount)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        
        # Обновляем статистику для конкретной игры
        game_stats_map = {
            "🎲": "roulette_wins", "🎯": "darts_wins", "⚽️": "football_wins",
            "🏀": "basketball_wins", "🎳": "bowling_wins", "🏐": "volleyball_wins",
            "🏒": "hockey_wins", "⛳️": "golf_wins", "🎾": "tennis_wins"
        }
        if game_key in game_stats_map:
            stats[game_stats_map[game_key]] += 1
            
        stats["total_won"] += win_amount
        save_transaction(user_id, win_amount, "game_win", f"{game['name']} x{multiplier}")
        
        win_text = f"🎉 <b>ВЫИГРЫШ!</b> 🎉\n✨ Множитель: <b>x{multiplier}</b>\n🏆 Выигрыш: <b>+{format_stars(win_amount)}</b>"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", game['name'])
        win_text = f"😢 <b>Проигрыш</b>\n-{format_stars(bet)}"
    
    await message.answer(
        f"{game['emoji']} <b>{game['name']}</b>\n\n"
        f"🎲 <b>Результат броска: {dice_value}</b>\n"
        f"{result_text}\n\n"
        f"💰 Ставка: {format_stars(bet)}\n\n"
        f"{win_text}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await state.clear()


# ---------- ОБРАБОТЧИКИ ДЛЯ КАЖДОЙ DICE ИГРЫ ----------
@dp.message(F.text == "🎲 Кубик")
async def cube_start(message: Message):
    await message.answer(
        "🎲 <b>Игра КУБИК</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "Кидай кубик и получай множители:\n"
        "• 1-2 → проигрыш\n"
        "• 3 → x1\n"
        "• 4 → x2\n"
        "• 5 → x3\n"
        "• 6 → x5\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("cube")
    )

@dp.callback_query(F.data.startswith("cube_bet_"))
async def cube_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    await play_dice_game(callback.message, "🎲", bet, state)
    await callback.answer()

@dp.message(F.text == "🎯 Дартс")
async def darts_start(message: Message):
    await message.answer(
        "🎯 <b>Игра ДАРТС</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "Попади в цель и получи множители:\n"
        "• 1-2 → мимо (проигрыш)\n"
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
    await play_dice_game(callback.message, "🎯", bet, state)
    await callback.answer()

@dp.message(F.text == "⚽️ Футбол")
async def football_start(message: Message):
    await message.answer(
        "⚽️ <b>Игра ФУТБОЛ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "Пробей пенальти и получи множители:\n"
        "• 1-2 → сейв вратаря (проигрыш)\n"
        "• 3 → гол x1\n"
        "• 4 → гол с рикошетом x2\n"
        "• 5 → красивый гол x3\n"
        "• 6 → ШЕДЕВР! x5\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("football")
    )

@dp.callback_query(F.data.startswith("football_bet_"))
async def football_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    await play_dice_game(callback.message, "⚽️", bet, state)
    await callback.answer()

@dp.message(F.text == "🏀 Баскетбол")
async def basketball_start(message: Message):
    await message.answer(
        "🏀 <b>Игра БАСКЕТБОЛ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "Брось трёхочковый и получи множители:\n"
        "• 1-2 → промах (проигрыш)\n"
        "• 3 → попадание x1\n"
        "• 4 → сверху x2\n"
        "• 5 → издали x4\n"
        "• 6 → БАЗЗЕР БИТЕР! x6\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("basketball")
    )

@dp.callback_query(F.data.startswith("basketball_bet_"))
async def basketball_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    await play_dice_game(callback.message, "🏀", bet, state)
    await callback.answer()

@dp.message(F.text == "🎳 Боулинг")
async def bowling_start(message: Message):
    await message.answer(
        "🎳 <b>Игра БОУЛИНГ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "Брось шар и получи множители:\n"
        "• 1-2 → страйк-аут (проигрыш)\n"
        "• 3 → спэр x1\n"
        "• 4 → страйк x2\n"
        "• 5 → идеальный x5\n"
        "• 6 → ДЕСЯТЬ СТРАЙКОВ! x10\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("bowling")
    )

@dp.callback_query(F.data.startswith("bowling_bet_"))
async def bowling_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    await play_dice_game(callback.message, "🎳", bet, state)
    await callback.answer()

@dp.message(F.text == "🏐 Волейбол")
async def volleyball_start(message: Message):
    await message.answer(
        "🏐 <b>Игра ВОЛЕЙБОЛ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "Сделай подачу и получи множители:\n"
        "• 1-2 → аут (проигрыш)\n"
        "• 3 → приём x1\n"
        "• 4 → атака x2\n"
        "• 5 → блок x4\n"
        "• 6 → ЭЙС! x8\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("volleyball")
    )

@dp.callback_query(F.data.startswith("volleyball_bet_"))
async def volleyball_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    await play_dice_game(callback.message, "🏐", bet, state)
    await callback.answer()

@dp.message(F.text == "🏒 Хоккей")
async def hockey_start(message: Message):
    await message.answer(
        "🏒 <b>Игра ХОККЕЙ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "Брось шайбу и получи множители:\n"
        "• 1-2 → сейв (проигрыш)\n"
        "• 3 → гол x1\n"
        "• 4 → рикошет x3\n"
        "• 5 → буллит x5\n"
        "• 6 → ХЕТ-ТРИК! x10\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("hockey")
    )

@dp.callback_query(F.data.startswith("hockey_bet_"))
async def hockey_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    await play_dice_game(callback.message, "🏒", bet, state)
    await callback.answer()

@dp.message(F.text == "⛳️ Гольф")
async def golf_start(message: Message):
    await message.answer(
        "⛳️ <b>Игра ГОЛЬФ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "Сделай удар и получи множители:\n"
        "• 1-2 → бункер (проигрыш)\n"
        "• 3 → пар x1\n"
        "• 4 → бёрди x2\n"
        "• 5 → игл x4\n"
        "• 6 → АЛЬБАТРОС! x8\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("golf")
    )

@dp.callback_query(F.data.startswith("golf_bet_"))
async def golf_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    await play_dice_game(callback.message, "⛳️", bet, state)
    await callback.answer()

@dp.message(F.text == "🎾 Теннис")
async def tennis_start(message: Message):
    await message.answer(
        "🎾 <b>Игра ТЕННИС</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "Сделай подачу и получи множители:\n"
        "• 1-2 → аут (проигрыш)\n"
        "• 3 → эйс x1\n"
        "• 4 → смэш x2\n"
        "• 5 → проходной x4\n"
        "• 6 → ТВИНЕР! x8\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("tennis")
    )

@dp.callback_query(F.data.startswith("tennis_bet_"))
async def tennis_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    await play_dice_game(callback.message, "🎾", bet, state)
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
    user_id = message.from_user.id
    if users_bans.get(user_id, False):
        await message.answer("❌ Вы забанены! Обратитесь к администратору.")
        return
    await message.answer(
        "🎰 <b>СЛОТЫ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "Собери комбинацию и получи множители:\n"
        "• 🍒🍒🍒 → x5\n"
        "• 🍊🍊🍊 → x7\n"
        "• 🍋🍋🍋 → x10\n"
        "• 💎💎💎 → x15\n"
        "• 7️⃣7️⃣7️⃣ → x25\n"
        "• 🎰🎰🎰 → ДЖЕКПОТ x50!\n"
        "• ⭐️⭐️⭐️ → x30\n"
        "• 💫💫💫 → x20\n"
        "• 2 одинаковых → x1.5\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_slots_keyboard()
    )

@dp.callback_query(F.data.startswith("slots_spin_"))
async def slots_spin(callback: CallbackQuery):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if users_bans.get(user_id, False):
        await callback.answer("❌ Вы забанены!", show_alert=True)
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
        save_transaction(user_id, win, "game_win", f"Слоты x{mult} {''.join(combo)}")
        res = f"🎉 <b>ДЖЕКПОТ!</b> x{mult}\n+{format_stars(win)}"
    elif reel1 == reel2 or reel1 == reel3 or reel2 == reel3:
        win = int(bet * 1.5)
        update_balance(user_id, win)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_won"] += win
        save_transaction(user_id, win, "game_win", f"Слоты пара {reel1}{reel2}{reel3}")
        res = f"🎉 <b>ПАРА!</b> x1.5\n+{format_stars(win)}"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", f"Слоты {reel1}{reel2}{reel3}")
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
    user_id = message.from_user.id
    if users_bans.get(user_id, False):
        await message.answer("❌ Вы забанены! Обратитесь к администратору.")
        return
    await message.answer(
        "💣 <b>МИНЫ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "Поле 5x5, скрыто 5 мин.\n"
        "• 💎 → увеличивает множитель x1.2\n"
        "• 💣 → мгновенный проигрыш\n"
        "• Максимальный множитель: x18 (20 клеток)\n"
        "• Можно забрать выигрыш в любой момент\n\n"
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
        f"📦 Открыто клеток: 0/20\n"
        f"🎯 Потенциальный выигрыш: {format_stars(int(bet * 1.2 ** 20))}\n\n"
        f"👇 <b>Открывай 💎 и избегай 💣!</b>",
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
            f"🎯 Макс. выигрыш: {format_stars(max_win)}\n\n"
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
    user_id = message.from_user.id
    if users_bans.get(user_id, False):
        await message.answer("❌ Вы забанены! Обратитесь к администратору.")
        return
    await message.answer(
        "🏛 <b>ПИРАМИДА</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "У тебя есть 5 уровней.\n"
        "• Каждый шаг удваивает выигрыш\n"
        "• Шанс успеха: 50%\n"
        "• Проигрыш на любом уровне = потеря ставки\n"
        "• На 5 уровне множитель x16!\n\n"
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
        f"✨ Множитель на 5 уровне: x16!\n\n"
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


# ===================== РЕФЕРАЛЫ, ТОП, ПРОФИЛЬ =====================
@dp.message(F.text == "👥 Рефералы")
async def referrals_reply(message: Message):
    user_id = message.from_user.id
    if users_bans.get(user_id, False):
        await message.answer("❌ Вы забанены! Обратитесь к администратору.")
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


# ===================== АДМИН-ПАНЕЛЬ (РАСШИРЕННАЯ) =====================
@dp.message(F.text == "👑 Админ панель")
async def admin_panel_reply(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ У вас нет доступа к админ-панели!", reply_markup=get_main_keyboard())
        return
    
    await message.answer(
        "👑 <b>РАСШИРЕННАЯ ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n\n"
        "📊 <b>Управление ботом:</b>\n"
        "• Статистика и мониторинг\n"
        "• Управление балансами\n"
        "• Рассылки и опросы\n\n"
        "⚙️ <b>Настройки игр:</b>\n"
        "• Редактирование множителей\n"
        "• Настройка бонусов\n"
        "• Управление играми\n\n"
        "👥 <b>Модерация:</b>\n"
        "• Бан/Разбан пользователей\n"
        "• Выдача варнов\n"
        "• Мут/Размут\n\n"
        "👇 <b>Выберите действие:</b>",
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
    muted = len(users_mutes)
    
    text = (
        f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
        f"👥 <b>Пользователей:</b> {total_users}\n"
        f"🚫 <b>Забанено:</b> {banned}\n"
        f"🔇 <b>Замучено:</b> {muted}\n"
        f"💰 <b>Общий баланс:</b> {format_stars(total_balance)}\n"
        f"🎮 <b>Всего игр:</b> {total_games}\n"
        f"🏆 <b>Всего побед:</b> {total_wins}\n"
    )
    if total_games > 0:
        text += f"📈 <b>Общий винрейт:</b> {(total_wins/total_games*100):.1f}%\n"
    text += (
        f"💸 <b>Пополнений:</b> {total_deposits}\n"
        f"💸 <b>Сумма пополнений:</b> {format_stars(deposit_sum)}\n"
        f"👥 <b>Реферальная система активна</b>\n"
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
        "Введи username игрока (без @) или ID:\n"
        "Пример: <code>hjklgf1</code> или <code>123456789</code>\n\n"
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
        "Отправь сообщение для рассылки всем пользователям.\n"
        "Поддерживается: текст, фото, видео, документы.\n\n"
        "<b>Внимание!</b> Рассылка придёт ВСЕМ пользователям бота!\n\n"
        f"📊 Всего пользователей: {len(users_balance)}\n\n"
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
        "Отправь опрос для всех пользователей.\n"
        "Формат: сначала вопрос, затем варианты через запятую.\n\n"
        "Пример:\n"
        "<code>Какая игра вам нравится больше?|Дартс,Футбол,Баскетбол,Слоты</code>\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML
    )


# ---------- РЕДАКТИРОВАНИЕ ПРОМО ----------
@dp.message(F.text == "📝 Редактировать промо")
async def admin_edit_promo_reply(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_edit_promo)
    await message.answer(
        "📝 <b>РЕДАКТИРОВАНИЕ ПРОМО-СООБЩЕНИЯ</b>\n\n"
        f"Текущее промо:\n{PROMO_MESSAGE}\n\n"
        "Введи новое промо-сообщение (оно будет показываться при /start):\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML
    )


# ---------- УПРАВЛЕНИЕ ИГРАМИ ----------
@dp.message(F.text == "🎮 Управление играми")
async def admin_manage_games(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    games_list = "\n".join([f"{k} — {v['name']}" for k, v in DICE_GAMES.items()])
    text = (
        f"🎮 <b>УПРАВЛЕНИЕ ИГРАМИ</b>\n\n"
        f"<b>Доступные игры:</b>\n{games_list}\n\n"
        f"<b>Слоты</b> — множители до x50\n"
        f"<b>Мины</b> — множитель до x18\n"
        f"<b>Пирамида</b> — множитель до x16\n\n"
        f"Используйте кнопку «Изменить множители» для настройки"
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())


# ---------- ИЗМЕНИТЬ МНОЖИТЕЛИ ----------
@dp.message(F.text == "🎲 Изменить множители")
async def admin_change_multipliers(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    games_list = "\n".join([f"{k} — {v['name']}: {v['multipliers']}" for k, v in DICE_GAMES.items()])
    await message.answer(
        "🎲 <b>ИЗМЕНЕНИЕ МНОЖИТЕЛЕЙ</b>\n\n"
        f"<b>Текущие множители:</b>\n{games_list}\n\n"
        "Для изменения создайте issue в GitHub или обратитесь к разработчику.\n"
        "В следующей версии будет добавлен интерфейс для изменения множителей.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard()
    )


# ---------- НАСТРОЙКИ БОТА ----------
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
        status = ""
        if users_bans.get(uid, False):
            status = "🚫"
        elif uid in users_mutes:
            status = "🔇"
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
        "balance": users_balance,
        "referrer": users_referrer,
        "referrals": users_referrals,
        "stats": users_stats,
        "transactions": transactions,
        "username": users_username,
        "join_date": users_join_date,
        "bans": users_bans,
        "mutes": users_mutes,
        "warnings": users_warnings,
        "promo": PROMO_MESSAGE,
        "coin_price": COIN_PRICE,
        "daily_bonus_range": DAILY_BONUS_RANGE
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
        users_mutes.update(data.get("mutes", {}))
        users_warnings.update(data.get("warnings", {}))
        
        await message.answer(
            "✅ <b>Данные успешно загружены из резервной копии!</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )
    except FileNotFoundError:
        await message.answer(
            "❌ <b>Файл backup.json не найден!</b>\n\nСначала сохраните данные.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )
    except Exception as e:
        await message.answer(
            f"❌ <b>Ошибка загрузки:</b>\n<code>{e}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )


# ---------- БАН ПОЛЬЗОВАТЕЛЯ ----------
@dp.message(F.text == "🚫 Забанить пользователя")
async def admin_ban_user(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_find_user)
    await message.answer(
        "🚫 <b>БАН ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введи username игрока (без @) или ID для бана:\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )


# ---------- РАЗБАН ----------
@dp.message(F.text == "🔓 Разбанить")
async def admin_unban_user(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_find_user)
    await message.answer(
        "🔓 <b>РАЗБАН ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введи username игрока (без @) или ID для разбана:\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )


# ---------- ВЫДАТЬ ВАРН ----------
@dp.message(F.text == "⚠️ Выдать варн")
async def admin_warn_user(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_find_user)
    await message.answer(
        "⚠️ <b>ВЫДАЧА ВАРНА</b>\n\n"
        "Введи username игрока (без @) или ID для выдачи варна:\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )


# ---------- ЗАМУТИТЬ ----------
@dp.message(F.text == "🔇 Замутить")
async def admin_mute_user(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_find_user)
    await message.answer(
        "🔇 <b>МУТ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введи username игрока (без @) или ID для мута:\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )


# ---------- РАЗМУТИТЬ ----------
@dp.message(F.text == "🔊 Размутить")
async def admin_unmute_user(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_find_user)
    await message.answer(
        "🔊 <b>РАЗМУТ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введи username игрока (без @) или ID для размута:\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )


# ---------- ТОП ПО ИГРАМ ----------
@dp.message(F.text == "📊 Топ по играм")
async def admin_top_games(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    game_stats = {
        "Кубик": sum(s["roulette_wins"] for s in users_stats.values()),
        "Дартс": sum(s["darts_wins"] for s in users_stats.values()),
        "Футбол": sum(s["football_wins"] for s in users_stats.values()),
        "Баскетбол": sum(s["basketball_wins"] for s in users_stats.values()),
        "Боулинг": sum(s["bowling_wins"] for s in users_stats.values()),
        "Слоты": sum(s["slots_wins"] for s in users_stats.values()),
        "Мины": sum(s["mines_wins"] for s in users_stats.values()),
        "Пирамида": sum(s["pyramid_wins"] for s in users_stats.values())
    }
    
    sorted_games = sorted(game_stats.items(), key=lambda x: x[1], reverse=True)
    
    text = "📊 <b>ТОП ИГР ПО ПОБЕДАМ</b>\n\n"
    for idx, (game, wins) in enumerate(sorted_games, 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
        text += f"{medal} <b>{game}</b> — {wins} побед\n"
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())


# ---------- НАСТРОЙКА БОНУСА ----------
@dp.message(F.text == "🎁 Настроить бонус")
async def admin_set_bonus_reply(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_set_bonus)
    await message.answer(
        "🎁 <b>НАСТРОЙКА ЕЖЕДНЕВНОГО БОНУСА</b>\n\n"
        f"Текущий диапазон: {DAILY_BONUS_RANGE[0]}-{DAILY_BONUS_RANGE[1]} Stars\n\n"
        "Введи новый диапазон в формате:\n"
        "<code>мин,макс</code>\n"
        "Пример: <code>10,25</code>\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML
    )


# ---------- КУРС МОНЕТ ----------
@dp.message(F.text == "💰 Курс монет")
async def admin_set_coin_price_reply(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_set_coin_price)
    await message.answer(
        f"💰 <b>КУРС МОНЕТ</b>\n\n"
        f"Текущий курс: {COIN_PRICE} Stars = 1 монета\n\n"
        "Введи новый курс (количество Stars за 1 монету):\n"
        "Пример: <code>150</code>\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML
    )


# ---------- В ГЛАВНОЕ МЕНЮ ----------
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
    
    # Определяем, какое действие выполняется (из контекста)
    current_state = await state.get_state()
    
    if current_state == GameStates.admin_find_user.state:
        # Обычный поиск пользователя (с главного меню админки)
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
        await state.set_state(GameStates.admin_change_balance)
    else:
        # Другое действие (бан, мут, и т.д.)
        await message.answer(
            f"✅ Пользователь @{input_text} найден!\n"
            f"💰 Баланс: {format_stars(get_user_balance(user_id))}\n\n"
            f"Действие будет выполнено...",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )
        await state.clear()

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
            await message.answer("❌ Некорректный диапазон! Мин должен быть >=1, макс >= мин.")
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
        await message.answer("❌ Ошибка! Формат: мин,макс (пример: 10,25)")

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
        price = int(message.text.strip())
        if price < 1:
            await message.answer("❌ Курс должен быть >= 1")
            return
        
        global COIN_PRICE
        COIN_PRICE = price
        
        await state.clear()
        await message.answer(
            f"✅ <b>КУРС МОНЕТ НАСТРОЕН</b>\n\n"
            f"Новый курс: {COIN_PRICE} Stars = 1 монета",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )
    except:
        await message.answer("❌ Ошибка! Введи число.")


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