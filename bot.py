import asyncio
import hashlib
import logging
import random
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict

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
users_weekly_bonus: Dict[int, str] = {}
users_ban: Dict[int, bool] = {}
users_warns: Dict[int, int] = {}
users_mute: Dict[int, datetime] = {}
pending_payments: Dict[str, dict] = {}
transactions: Dict[int, list] = {}
users_username: Dict[int, str] = {}
users_join_date: Dict[int, str] = {}
users_last_active: Dict[int, str] = {}
users_ref_code: Dict[int, str] = {}
users_language: Dict[int, str] = {}
users_notify: Dict[int, bool] = {}
users_vip: Dict[int, bool] = {}
users_vip_until: Dict[int, str] = {}
daily_bonus_streak: Dict[int, int] = {}
promo_codes: Dict[str, dict] = {}
giveaway_active: Dict[str, dict] = {}
giveaway_participants: Dict[str, List[int]] = {}
lottery_tickets: Dict[int, int] = {}
lottery_active = False
lottery_pool = 0
lottery_participants: Dict[int, int] = {}
support_requests: Dict[int, dict] = {}
feedback_list: List[dict] = []
admin_logs: List[dict] = []
system_settings: Dict[str, any] = {
    "maintenance": False,
    "min_withdraw": 100,
    "max_withdraw": 10000,
    "bonus_percent": 10,
    "ref_percent": 10
}

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
    admin_mailing = State()
    admin_set_bonus = State()
    admin_set_ref_percent = State()
    admin_create_promo = State()
    admin_create_giveaway = State()
    dice_game = State()
    mines_game = State()
    pyramid_game = State()
    support_message = State()
    withdraw_amount = State()
    transfer_amount = State()
    promo_enter = State()


# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
def is_admin(username: str) -> bool:
    return username.lower() in [adm.lower() for adm in ADMIN_USERNAMES]

def log_admin_action(admin_name: str, action: str, target: str = None, details: str = ""):
    admin_logs.append({
        "admin": admin_name,
        "action": action,
        "target": target,
        "details": details,
        "timestamp": datetime.now().isoformat()
    })
    logger.info(f"Admin {admin_name}: {action} -> {target} ({details})")

async def get_user_id_by_username(username: str) -> Optional[int]:
    for uid, uname in users_username.items():
        if uname and uname.lower() == username.lower():
            return uid
    return None

def generate_referral_link(user_id: int) -> str:
    if user_id not in users_ref_code:
        code = hashlib.md5(f"starplay_{user_id}_{datetime.now()}".encode()).hexdigest()[:8]
        users_ref_code[user_id] = code
    return f"https://t.me/{bot.username}?start=ref_{users_ref_code[user_id]}"

def get_user_stats(user_id: int) -> dict:
    if user_id not in users_stats:
        users_stats[user_id] = {
            "games_played": 0, "games_won": 0, "total_won": 0, "total_lost": 0,
            "dice_wins": 0, "darts_wins": 0, "football_wins": 0,
            "bowling_wins": 0, "basketball_wins": 0, "baseball_wins": 0,
            "tennis_wins": 0, "cricket_wins": 0, "mines_wins": 0,
            "pyramid_wins": 0, "slots_wins": 0, "roulette_wins": 0
        }
    return users_stats[user_id]

def update_balance(user_id: int, delta: int) -> int:
    if users_ban.get(user_id, False):
        return get_user_balance(user_id)
    current = users_balance.get(user_id, 0)
    new_balance = current + delta
    if new_balance < 0:
        new_balance = 0
    users_balance[user_id] = new_balance
    return new_balance

def get_user_balance(user_id: int) -> int:
    if users_ban.get(user_id, False):
        return 0
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


# ===================== ПРАВИЛА DICE ИГР =====================
# Значения dice от 1 до 6 для всех эмодзи
DICE_RULES = {
    "🎲": {
        "name": "Кубик",
        "emoji": "🎲",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 3, 6: 5},
        "description": "Бросай кубик! 1-2 → проигрыш, 3 → x1, 4 → x2, 5 → x3, 6 → x5"
    },
    "🎯": {
        "name": "Дартс",
        "emoji": "🎯",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 4, 6: 10},
        "description": "Попади в яблочко! 1-2 → мимо, 3 → x1, 4 → x2, 5 → x4, 6 → ЯБЛОЧКО x10!"
    },
    "⚽️": {
        "name": "Футбол",
        "emoji": "⚽️",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 3, 6: 5},
        "description": "Пенальти! 1-2 → сейв, 3 → гол x1, 4 → рикошет x2, 5 → красивый x3, 6 → шедевр x5!"
    },
    "🏀": {
        "name": "Баскетбол",
        "emoji": "🏀",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 4, 6: 6},
        "description": "Трёхочковый! 1-2 → промах, 3 → попадание x1, 4 → сверху x2, 5 → издали x4, 6 → БАЗЗЕР x6!"
    },
    "🎳": {
        "name": "Боулинг",
        "emoji": "🎳",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 5, 6: 10},
        "description": "Бросай шар! 1-2 → страйк-аут, 3 → спэр x1, 4 → страйк x2, 5 → идеальный x5, 6 → 10 СТРАЙКОВ x10!"
    },
    "⚾️": {
        "name": "Бейсбол",
        "emoji": "⚾️",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 4, 6: 8},
        "description": "Хоум-ран! 1-2 → страйк-аут, 3 → сингл x1, 4 → дабл x2, 5 → трипл x4, 6 → ХОУМ-РАН x8!"
    },
    "🎾": {
        "name": "Теннис",
        "emoji": "🎾",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 4, 6: 7},
        "description": "Эйс! 1-2 → двойная ошибка, 3 → форхенд x1, 4 → бэкхенд x2, 5 → смэш x4, 6 → ЭЙС x7!"
    },
    "🏏": {
        "name": "Крикет",
        "emoji": "🏏",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 3, 5: 5, 6: 12},
        "description": "Шестёрка! 1-2 → аута, 3 → сингл x1, 4 → бондари x3, 5 → четвёрка x5, 6 → ШЕСТЁРКА x12!"
    }
}

SLOT_SYMBOLS = ["🍒", "🍊", "🍋", "💎", "7️⃣", "🎰", "⭐️", "💫", "🔔", "🍉"]
SLOT_PAYOUTS = {
    ("🍒", "🍒", "🍒"): 5, ("🍊", "🍊", "🍊"): 7, ("🍋", "🍋", "🍋"): 10,
    ("💎", "💎", "💎"): 15, ("7️⃣", "7️⃣", "7️⃣"): 25, ("🎰", "🎰", "🎰"): 50,
    ("⭐️", "⭐️", "⭐️"): 30, ("💫", "💫", "💫"): 20, ("🔔", "🔔", "🔔"): 12,
    ("🍉", "🍉", "🍉"): 8
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
    builder.button(text="📞 Поддержка")
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
    builder.button(text="💾 Сохранить данные")
    builder.button(text="🔨 Управление пользователями")
    builder.button(text="🎁 Управление бонусами")
    builder.button(text="🏆 Лотерея/Розыгрыш")
    builder.button(text="📝 Промокоды")
    builder.button(text="⚙️ Настройки бота")
    builder.button(text="📊 Детальная статистика")
    builder.button(text="🔙 В главное меню")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_user_management_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="⛔ Забанить пользователя")
    builder.button(text="✅ Разбанить пользователя")
    builder.button(text="⚠️ Выдать предупреждение")
    builder.button(text="🔇 Замутить пользователя")
    builder.button(text="👑 Выдать VIP")
    builder.button(text="⭐️ Снять VIP")
    builder.button(text="📊 Статистика пользователя")
    builder.button(text="🔙 Назад в админку")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_games_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="🎲 Кубик")
    builder.button(text="🎯 Дартс")
    builder.button(text="⚽️ Футбол")
    builder.button(text="🏀 Баскетбол")
    builder.button(text="🎳 Боулинг")
    builder.button(text="⚾️ Бейсбол")
    builder.button(text="🎾 Теннис")
    builder.button(text="🏏 Крикет")
    builder.button(text="🎰 Слоты")
    builder.button(text="💣 Мины")
    builder.button(text="🏛 Пирамида")
    builder.button(text="🎲 Рулетка")
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

def get_roulette_keyboard(bet: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Красное (x2)", callback_data=f"roulette_red_{bet}"),
         InlineKeyboardButton(text="⚫️ Черное (x2)", callback_data=f"roulette_black_{bet}")],
        [InlineKeyboardButton(text="🟢 Зеро (x35)", callback_data=f"roulette_zero_{bet}"),
         InlineKeyboardButton(text="🎯 Число (x35)", callback_data=f"roulette_number_{bet}")],
        [InlineKeyboardButton(text="📊 Четное (x2)", callback_data=f"roulette_even_{bet}"),
         InlineKeyboardButton(text="📊 Нечетное (x2)", callback_data=f"roulette_odd_{bet}")],
        [InlineKeyboardButton(text="📈 1-18 (x2)", callback_data=f"roulette_low_{bet}"),
         InlineKeyboardButton(text="📉 19-36 (x2)", callback_data=f"roulette_high_{bet}")],
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

def get_slots_keyboard() -> InlineKeyboardMarkup:
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
    users_last_active[user_id] = datetime.now().isoformat()
    
    if user_id not in users_join_date:
        users_join_date[user_id] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if user_id not in users_language:
        users_language[user_id] = "ru"
    if user_id not in users_notify:
        users_notify[user_id] = True
    
    if " " in message.text:
        param = message.text.split()[1]
        if param.startswith("ref_"):
            try:
                code = param[4:]
                for uid, c in users_ref_code.items():
                    if c == code and uid != user_id and user_id not in users_referrer:
                        users_referrer[user_id] = uid
                        users_referrals.setdefault(uid, []).append(user_id)
                        update_balance(user_id, REFERRAL_SIGNUP_BONUS)
                        update_balance(uid, REFERRAL_INVITE_BONUS)
                        save_transaction(user_id, REFERRAL_SIGNUP_BONUS, "referral_bonus", f"от {uid}")
                        save_transaction(uid, REFERRAL_INVITE_BONUS, "referral_reward", f"пригласил {user_id}")
                        await message.answer(f"✅ Вы получили {format_stars(REFERRAL_SIGNUP_BONUS)} за регистрацию по ссылке!")
                        break
            except:
                pass
    
    welcome_text = (
        f"🌟 <b>Добро пожаловать в StarPlay!</b> 🌟\n\n"
        f"{get_random_emoji()} <b>Играй на Telegram Stars и выигрывай!</b>\n\n"
        f"<b>🎮 12 игр на выбор:</b>\n"
        f"🎲 Кубик | 🎯 Дартс | ⚽️ Футбол | 🏀 Баскетбол | 🎳 Боулинг\n"
        f"⚾️ Бейсбол | 🎾 Теннис | 🏏 Крикет | 🎰 Слоты | 💣 Мины | 🏛 Пирамида | 🎲 Рулетка\n\n"
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
    if users_ban.get(user_id, False):
        await message.answer("❌ Ваш аккаунт заблокирован!", reply_markup=get_main_keyboard())
        return
    await message.answer(
        f"💰 <b>Твой баланс:</b> {format_stars(get_user_balance(user_id))}\n\n"
        f"🎮 Приглашай друзей и зарабатывай больше!\n"
        f"👥 Рефералов: {len(users_referrals.get(user_id, []))}\n"
        f"⭐️ VIP статус: {'✅ Да' if users_vip.get(user_id, False) else '❌ Нет'}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "⭐️ Пополнить")
async def deposit_reply(message: Message):
    if users_ban.get(message.from_user.id, False):
        await message.answer("❌ Ваш аккаунт заблокирован!", reply_markup=get_main_keyboard())
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
    if users_ban.get(message.from_user.id, False):
        await message.answer("❌ Ваш аккаунт заблокирован!", reply_markup=get_main_keyboard())
        return
    await message.answer(
        "🎮 <b>Выбери игру</b>\n\n"
        "🎲 <b>Кубик</b> — Простой кубик, множители до x5\n"
        "🎯 <b>Дартс</b> — Попади в яблочко до x10!\n"
        "⚽️ <b>Футбол</b> — Забей пенальти до x5\n"
        "🏀 <b>Баскетбол</b> — Трёхочковый бросок до x6\n"
        "🎳 <b>Боулинг</b> — Сделай страйк до x10!\n"
        "⚾️ <b>Бейсбол</b> — Хоум-ран до x8!\n"
        "🎾 <b>Теннис</b> — Подай эйс до x7!\n"
        "🏏 <b>Крикет</b> — Выбей шестёрку до x12!\n"
        "🎰 <b>Слоты</b> — Классические автоматы до x50\n"
        "💣 <b>Мины</b> — Рискни и увеличь выигрыш до x18\n"
        "🏛 <b>Пирамида</b> — Поднимайся выше до x16\n"
        "🎲 <b>Рулетка</b> — Европейская рулетка\n\n"
        "👇 <i>Нажми на кнопку с игрой!</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )

@dp.message(F.text == "👥 Рефералы")
async def referrals_reply(message: Message):
    user_id = message.from_user.id
    if users_ban.get(user_id, False):
        await message.answer("❌ Ваш аккаунт заблокирован!", reply_markup=get_main_keyboard())
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
        f"<code>{ref_link}</code>\n\n"
        f"Поделись ссылкой с друзьями и зарабатывай! 🚀"
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
        vip = " 👑" if users_vip.get(uid, False) else ""
        top_text += f"{medal} <b>{name}</b>{vip} — {bal} ⭐️\n"
    
    await message.answer(top_text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "📊 Профиль")
async def profile_reply(message: Message):
    uid = message.from_user.id
    if users_ban.get(uid, False):
        await message.answer("❌ Ваш аккаунт заблокирован!", reply_markup=get_main_keyboard())
        return
    stats = get_user_stats(uid)
    wr = (stats['games_won'] / max(stats['games_played'], 1)) * 100
    ref_count = len(users_referrals.get(uid, []))
    
    text = (
        f"👤 <b>Профиль игрока</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👤 Username: @{message.from_user.username or 'нет'}\n"
        f"📅 Регистрация: {users_join_date.get(uid, 'неизвестно')}\n"
        f"⭐️ VIP статус: {'✅ Да' if users_vip.get(uid, False) else '❌ Нет'}\n"
        f"⚠️ Предупреждений: {users_warns.get(uid, 0)}/3\n\n"
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
    if users_ban.get(user_id, False):
        await message.answer("❌ Ваш аккаунт заблокирован!", reply_markup=get_main_keyboard())
        return
    
    today = datetime.now().date().isoformat()
    
    # Ежедневный бонус
    if users_daily_bonus.get(user_id) == today:
        daily_available = False
    else:
        daily_available = True
    
    # Еженедельный бонус
    week = datetime.now().strftime("%Y-%W")
    weekly_available = users_weekly_bonus.get(user_id) != week
    
    if not daily_available and not weekly_available:
        await message.answer(
            f"🎁 <b>Бонусы</b>\n\n"
            f"❌ Ежедневный бонус уже получен сегодня!\n"
            f"❌ Еженедельный бонус уже получен на этой неделе!\n\n"
            f"Возвращайся завтра за новыми бонусами! 🌟",
            parse_mode=ParseMode.HTML
        )
        return
    
    bonus_text = ""
    total_bonus = 0
    
    if daily_available:
        streak = daily_bonus_streak.get(user_id, 0) + 1
        daily_bonus_amount = min(5 + streak, 25)
        update_balance(user_id, daily_bonus_amount)
        users_daily_bonus[user_id] = today
        daily_bonus_streak[user_id] = streak
        save_transaction(user_id, daily_bonus_amount, "daily_bonus", f"День {streak}")
        bonus_text += f"🎁 Ежедневный бонус: +{format_stars(daily_bonus_amount)} (День {streak})\n"
        total_bonus += daily_bonus_amount
    
    if weekly_available:
        weekly_bonus_amount = 50 if users_vip.get(user_id, False) else 25
        update_balance(user_id, weekly_bonus_amount)
        users_weekly_bonus[user_id] = week
        save_transaction(user_id, weekly_bonus_amount, "weekly_bonus", "Еженедельный бонус")
        bonus_text += f"📅 Еженедельный бонус: +{format_stars(weekly_bonus_amount)}\n"
        total_bonus += weekly_bonus_amount
    
    await message.answer(
        f"🎉 <b>Бонусы получены!</b> 🎉\n\n"
        f"{bonus_text}\n"
        f"💰 Всего получено: {format_stars(total_bonus)}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text == "📞 Поддержка")
async def support_reply(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if users_ban.get(user_id, False):
        await message.answer("❌ Ваш аккаунт заблокирован!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.support_message)
    await message.answer(
        "📞 <b>Поддержка</b>\n\n"
        "Напишите ваше сообщение для администратора.\n"
        "Мы ответим вам в ближайшее время!\n\n"
        "<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )


# ===================== DICE ИГРЫ =====================
async def play_dice_game(message: Message, game_key: str, bet: int, state: FSMContext):
    user_id = message.from_user.id
    if get_user_balance(user_id) < bet:
        await message.answer(f"❌ Не хватает {format_stars(bet)}")
        return
    
    game = DICE_RULES[game_key]
    await state.update_data(dice_game_data={"game": game_key, "bet": bet, "emoji": game["emoji"]})
    
    await message.answer(
        f"{game['emoji']} <b>{game['name']}</b>\n\n"
        f"📋 <b>Правила:</b>\n{game['description']}\n\n"
        f"💰 Ставка: {format_stars(bet)}\n\n"
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
    
    dice_message = await callback.message.answer_dice(emoji=emoji)
    dice_value = dice_message.dice.value
    
    game = DICE_RULES[game_key]
    multiplier = game["multipliers"].get(dice_value, 0)
    
    result_messages = {
        1: "😭 Ужасный результат!", 2: "😢 Обидный промах...",
        3: "🤔 Неплохо, но могло быть лучше!", 4: "😊 Хороший результат!",
        5: "😎 Отличный бросок!", 6: "🤯 НЕВЕРОЯТНО! 🔥"
    }
    
    emoji_results = {1: "💀", 2: "😢", 3: "🤔", 4: "😊", 5: "😎", 6: "🤯"}
    
    if multiplier > 0:
        win_amount = bet * multiplier
        update_balance(user_id, win_amount)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats[f"{game_key}_wins"] = stats.get(f"{game_key}_wins", 0) + 1
        stats["total_won"] += win_amount
        save_transaction(user_id, win_amount, "game_win", f"{game['name']} x{multiplier}")
        
        result_text = f"🎉 <b>ВЫИГРЫШ!</b> 🎉\n\n✨ Множитель: <b>x{multiplier}</b>\n🏆 Выигрыш: <b>+{format_stars(win_amount)}</b>"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", game['name'])
        result_text = f"😢 <b>Проигрыш</b>\n\n-{format_stars(bet)}"
    
    await callback.message.answer(
        f"{emoji} <b>{game['name']}</b>\n\n"
        f"{emoji_results.get(dice_value, '🎲')} <b>Результат: {dice_value}</b>\n"
        f"{result_messages.get(dice_value, '')}\n\n"
        f"💰 Ставка: {format_stars(bet)}\n\n"
        f"{result_text}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await state.clear()
    await callback.answer()


# ---------- ОБРАБОТЧИКИ ВСЕХ ИГР ----------
@dp.message(F.text == "🎲 Кубик")
async def cube_start(message: Message):
    await message.answer(
        "🎲 <b>Игра КУБИК</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "Кидай кубик и получай множители:\n"
        "• 1-2 → проигрыш\n• 3 → x1\n• 4 → x2\n• 5 → x3\n• 6 → x5\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("dice")
    )

@dp.callback_query(F.data.startswith("dice_bet_"))
async def cube_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    await play_dice_game(callback.message, "🎲", bet, state)
    await callback.answer()

@dp.message(F.text == "🎯 Дартс")
async def darts_start(message: Message):
    await message.answer(
        "🎯 <b>Игра ДАРТС</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• 1-2 → мимо\n• 3 → x1\n• 4 → x2\n• 5 → x4\n• 6 → ЯБЛОЧКО x10!\n\n"
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
        "• 1-2 → сейв\n• 3 → гол x1\n• 4 → рикошет x2\n• 5 → красивый x3\n• 6 → шедевр x5!\n\n"
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
        "• 1-2 → промах\n• 3 → попадание x1\n• 4 → сверху x2\n• 5 → издали x4\n• 6 → БАЗЗЕР x6!\n\n"
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
        "• 1-2 → страйк-аут\n• 3 → спэр x1\n• 4 → страйк x2\n• 5 → идеальный x5\n• 6 → 10 СТРАЙКОВ x10!\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("bowling")
    )

@dp.callback_query(F.data.startswith("bowling_bet_"))
async def bowling_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    await play_dice_game(callback.message, "🎳", bet, state)
    await callback.answer()

@dp.message(F.text == "⚾️ Бейсбол")
async def baseball_start(message: Message):
    await message.answer(
        "⚾️ <b>Игра БЕЙСБОЛ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• 1-2 → страйк-аут\n• 3 → сингл x1\n• 4 → дабл x2\n• 5 → трипл x4\n• 6 → ХОУМ-РАН x8!\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("baseball")
    )

@dp.callback_query(F.data.startswith("baseball_bet_"))
async def baseball_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    await play_dice_game(callback.message, "⚾️", bet, state)
    await callback.answer()

@dp.message(F.text == "🎾 Теннис")
async def tennis_start(message: Message):
    await message.answer(
        "🎾 <b>Игра ТЕННИС</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• 1-2 → двойная ошибка\n• 3 → форхенд x1\n• 4 → бэкхенд x2\n• 5 → смэш x4\n• 6 → ЭЙС x7!\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("tennis")
    )

@dp.callback_query(F.data.startswith("tennis_bet_"))
async def tennis_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    await play_dice_game(callback.message, "🎾", bet, state)
    await callback.answer()

@dp.message(F.text == "🏏 Крикет")
async def cricket_start(message: Message):
    await message.answer(
        "🏏 <b>Игра КРИКЕТ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• 1-2 → аута\n• 3 → сингл x1\n• 4 → бондари x3\n• 5 → четвёрка x5\n• 6 → ШЕСТЁРКА x12!\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("cricket")
    )

@dp.callback_query(F.data.startswith("cricket_bet_"))
async def cricket_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    await play_dice_game(callback.message, "🏏", bet, state)
    await callback.answer()


# ---------- РУЛЕТКА ----------
roulette_numbers = list(range(0, 37))
roulette_colors = {0: "green"}
for i in range(1, 37):
    roulette_colors[i] = "red" if i % 2 == 1 else "black"

@dp.message(F.text == "🎲 Рулетка")
async def roulette_start(message: Message):
    await message.answer(
        "🎲 <b>Европейская Рулетка</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• Красное/Черное → x2\n• Четное/Нечетное → x2\n• 1-18/19-36 → x2\n"
        "• Зеро → x35\n• Точное число → x35\n\n"
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
        f"🎲 <b>Рулетка</b>\n\n💰 Ставка: {format_stars(bet)}\n\nВыбери тип ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_roulette_keyboard(bet)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("roulette_"))
async def roulette_play(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet = data.get("roulette_bet", 5)
    parts = callback.data.split("_")
    bet_type = parts[1]
    user_id = callback.from_user.id
    
    update_balance(user_id, -bet)
    result = random.choice(roulette_numbers)
    color = roulette_colors[result]
    win = False
    multiplier = 0
    
    if bet_type == "red" and color == "red":
        win, multiplier = True, 2
    elif bet_type == "black" and color == "black":
        win, multiplier = True, 2
    elif bet_type == "zero" and result == 0:
        win, multiplier = True, 35
    elif bet_type == "even" and result > 0 and result % 2 == 0:
        win, multiplier = True, 2
    elif bet_type == "odd" and result > 0 and result % 2 == 1:
        win, multiplier = True, 2
    elif bet_type == "low" and 1 <= result <= 18:
        win, multiplier = True, 2
    elif bet_type == "high" and 19 <= result <= 36:
        win, multiplier = True, 2
    
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
    
    color_emoji = {"red":"🔴","black":"⚫️","green":"🟢"}[color]
    await callback.message.edit_text(
        f"🎲 <b>Рулетка</b>\n\n💰 Ставка: {format_stars(bet)}\n🎯 Выпало: {result} {color_emoji}\n\n{res_text}\n\n💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await state.clear()
    await callback.answer()


# ---------- СЛОТЫ ----------
@dp.message(F.text == "🎰 Слоты")
async def slots_start(message: Message):
    await message.answer(
        "🎰 <b>СЛОТЫ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "Собери комбинацию и получи множители до x50!\n"
        "2 одинаковых символа → x1.5\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_slots_keyboard()
    )

@dp.callback_query(F.data.startswith("slots_spin_"))
async def slots_spin(callback: CallbackQuery):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
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
        f"💰 Ставка: {format_stars(bet)}\n\n{res}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_slots_keyboard()
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
            f"💣 <b>МИНЫ</b>\n\n💥 <b>БАХ! Ты наступил на мину!</b>\n\n"
            f"💰 Ставка: {format_stars(game['bet'])} — ПРОИГРАНА\n"
            f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_games_keyboard()
        )
    else:
        game["cells_opened"] += 1
        game["multiplier"] *= 1.2
        
        await callback.message.edit_text(
            f"💣 <b>МИНЫ</b>\n\n"
            f"💰 Ставка: {format_stars(game['bet'])}\n"
            f"✨ Множитель: x{game['multiplier']:.1f}\n"
            f"📦 Открыто клеток: {game['cells_opened']}/20\n\n"
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
                f"💣 <b>МИНЫ</b>\n\n🎉 <b>ПОБЕДА!</b> Ты очистил всё поле! 🎉\n\n"
                f"📦 Открыто: 20/20\n✨ Множитель: x{game['multiplier']:.1f}\n"
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
        f"💣 <b>МИНЫ</b>\n\n💰 <b>Ты забрал выигрыш!</b> 💰\n\n"
        f"📦 Открыто: {game['cells_opened']}/20\n✨ Множитель: x{game['multiplier']:.1f}\n"
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
        "5 уровней, каждый шаг удваивает выигрыш (50% успеха).\n"
        "На 5 уровне выигрыш x16 от ставки!\n\n"
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
    
    active_pyramids[user_id] = {"bet": bet, "level": 1, "current": bet}
    
    await callback.message.edit_text(
        f"🏛 <b>ПИРАМИДА</b>\n\n"
        f"🏆 <b>Уровень 1 / 5</b>\n\n"
        f"💰 Текущий выигрыш: {format_stars(bet)}\n"
        f"🎯 Следующий уровень: {format_stars(bet * 2)}\n"
        f"📊 Шанс успеха: 50%\n\n"
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
                f"🏛 <b>ПИРАМИДА - ПОБЕДА!</b>\n\n🎉 <b>Ты покорил вершину!</b> 🎉\n\n"
                f"🏆 Уровень: {game['level']}/5\n"
                f"💰 Выигрыш: {format_stars(game['current'])}\n"
                f"✨ Множитель: x{game['current'] // game['bet']}\n\n"
                f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_games_keyboard()
            )
        else:
            await callback.message.edit_text(
                f"🏛 <b>ПИРАМИДА</b>\n\n✅ <b>УСПЕХ!</b> Ты поднялся на уровень {game['level']}!\n\n"
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
        f"🏛 <b>ПИРАМИДА</b>\n\n💰 <b>Ты забрал выигрыш!</b> 💰\n\n"
        f"🏆 Пройдено уровней: {game['level']}/5\n"
        f"✨ Множитель: x{win // game['bet']}\n"
        f"🏆 Выигрыш: {format_stars(win)}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()


# ===================== АДМИН-ПАНЕЛЬ (20+ ФУНКЦИЙ) =====================
@dp.message(F.text == "👑 Админ панель")
async def admin_panel_reply(message: Message):
    if not is_admin(message.from_user.username or ""):
        await message.answer("❌ У вас нет доступа!", reply_markup=get_main_keyboard())
        return
    await message.answer(
        "👑 <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n\n"
        "📊 <b>20+ функций управления:</b>\n"
        "• Статистика бота\n• Изменение баланса\n• Рассылка\n"
        "• Управление пользователями (бан/мут/VIP)\n"
        "• Бонусы и промокоды\n"
        "• Лотереи и розыгрыши\n"
        "• Настройки бота\n\n"
        "👇 <b>Выберите действие:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard()
    )

@dp.message(F.text == "📊 Статистика бота")
async def admin_stats(message: Message):
    if not is_admin(message.from_user.username or ""):
        return
    total_users = len(users_balance)
    total_balance = sum(users_balance.values())
    total_games = sum(s["games_played"] for s in users_stats.values())
    total_wins = sum(s["games_won"] for s in users_stats.values())
    banned = sum(1 for b in users_ban.values() if b)
    vip = sum(1 for v in users_vip.values() if v)
    
    text = (
        f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
        f"👥 <b>Пользователей:</b> {total_users}\n"
        f"⛔ <b>Забанено:</b> {banned}\n"
        f"👑 <b>VIP:</b> {vip}\n"
        f"💰 <b>Общий баланс:</b> {format_stars(total_balance)}\n"
        f"🎮 <b>Всего игр:</b> {total_games}\n"
        f"🏆 <b>Всего побед:</b> {total_wins}\n"
        f"📈 <b>Винрейт:</b> {(total_wins/total_games*100):.1f}%\n" if total_games > 0 else ""
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "📊 Детальная статистика")
async def admin_detailed_stats(message: Message):
    if not is_admin(message.from_user.username or ""):
        return
    
    # Статистика по играм
    game_stats = defaultdict(int)
    for stats in users_stats.values():
        for key in ["dice_wins", "darts_wins", "football_wins", "bowling_wins", 
                    "basketball_wins", "baseball_wins", "tennis_wins", "cricket_wins",
                    "slots_wins", "mines_wins", "pyramid_wins", "roulette_wins"]:
            game_stats[key] += stats.get(key, 0)
    
    text = f"📊 <b>ДЕТАЛЬНАЯ СТАТИСТИКА ИГР</b>\n\n"
    text += f"🎲 Кубик: {game_stats['dice_wins']} побед\n"
    text += f"🎯 Дартс: {game_stats['darts_wins']} побед\n"
    text += f"⚽️ Футбол: {game_stats['football_wins']} побед\n"
    text += f"🏀 Баскетбол: {game_stats['basketball_wins']} побед\n"
    text += f"🎳 Боулинг: {game_stats['bowling_wins']} побед\n"
    text += f"⚾️ Бейсбол: {game_stats['baseball_wins']} побед\n"
    text += f"🎾 Теннис: {game_stats['tennis_wins']} побед\n"
    text += f"🏏 Крикет: {game_stats['cricket_wins']} побед\n"
    text += f"🎰 Слоты: {game_stats['slots_wins']} побед\n"
    text += f"💣 Мины: {game_stats['mines_wins']} побед\n"
    text += f"🏛 Пирамида: {game_stats['pyramid_wins']} побед\n"
    text += f"🎲 Рулетка: {game_stats['roulette_wins']} побед\n"
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "💰 Изменить баланс")
async def admin_change_balance(message: Message, state: FSMContext):
    if not is_admin(message.from_user.username or ""):
        return
    await state.set_state(GameStates.admin_find_user)
    await message.answer(
        "💰 <b>ИЗМЕНЕНИЕ БАЛАНСА</b>\n\n"
        "Введи username игрока (без @):\n"
        "Пример: <code>hjklgf1</code>\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(F.text == "🔨 Управление пользователями")
async def admin_user_management(message: Message):
    if not is_admin(message.from_user.username or ""):
        return
    await message.answer(
        "🔨 <b>УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ</b>\n\n"
        "Выберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_user_management_keyboard()
    )

@dp.message(F.text == "⛔ Забанить пользователя")
async def admin_ban_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.username or ""):
        return
    await state.set_state(GameStates.admin_find_user)
    await state.update_data(admin_action="ban")
    await message.answer(
        "⛔ <b>ЗАБАНИТЬ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введи username игрока (без @):",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(F.text == "✅ Разбанить пользователя")
async def admin_unban_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.username or ""):
        return
    await state.set_state(GameStates.admin_find_user)
    await state.update_data(admin_action="unban")
    await message.answer(
        "✅ <b>РАЗБАНИТЬ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введи username игрока (без @):",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(F.text == "⚠️ Выдать предупреждение")
async def admin_warn_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.username or ""):
        return
    await state.set_state(GameStates.admin_find_user)
    await state.update_data(admin_action="warn")
    await message.answer(
        "⚠️ <b>ВЫДАТЬ ПРЕДУПРЕЖДЕНИЕ</b>\n\n"
        "Введи username игрока (без @):",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(F.text == "🔇 Замутить пользователя")
async def admin_mute_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.username or ""):
        return
    await state.set_state(GameStates.admin_find_user)
    await state.update_data(admin_action="mute")
    await message.answer(
        "🔇 <b>ЗАМУТИТЬ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введи username игрока (без @):\n"
        "Мут на 1 час",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(F.text == "👑 Выдать VIP")
async def admin_give_vip(message: Message, state: FSMContext):
    if not is_admin(message.from_user.username or ""):
        return
    await state.set_state(GameStates.admin_find_user)
    await state.update_data(admin_action="vip_give")
    await message.answer(
        "👑 <b>ВЫДАТЬ VIP СТАТУС</b>\n\n"
        "Введи username игрока (без @):",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(F.text == "⭐️ Снять VIP")
async def admin_remove_vip(message: Message, state: FSMContext):
    if not is_admin(message.from_user.username or ""):
        return
    await state.set_state(GameStates.admin_find_user)
    await state.update_data(admin_action="vip_remove")
    await message.answer(
        "⭐️ <b>СНЯТЬ VIP СТАТУС</b>\n\n"
        "Введи username игрока (без @):",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(F.text == "📊 Статистика пользователя")
async def admin_user_stats(message: Message, state: FSMContext):
    if not is_admin(message.from_user.username or ""):
        return
    await state.set_state(GameStates.admin_find_user)
    await state.update_data(admin_action="stats")
    await message.answer(
        "📊 <b>СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введи username игрока (без @):",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(GameStates.admin_find_user)
async def admin_find_user_handler(message: Message, state: FSMContext):
    if not is_admin(message.from_user.username or ""):
        await state.clear()
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
        await message.answer("❌ Пользователь не найден!")
        return
    
    data = await state.get_data()
    action = data.get("admin_action", "balance")
    
    if action == "ban":
        users_ban[user_id] = True
        await bot.send_message(user_id, "⛔ Ваш аккаунт был заблокирован администратором!")
        log_admin_action(message.from_user.username, "БАН", input_text, "Пользователь забанен")
        await message.answer(f"✅ Пользователь @{input_text} забанен!")
        
    elif action == "unban":
        users_ban[user_id] = False
        await bot.send_message(user_id, "✅ Ваш аккаунт был разблокирован!")
        log_admin_action(message.from_user.username, "РАЗБАН", input_text, "Пользователь разбанен")
        await message.answer(f"✅ Пользователь @{input_text} разбанен!")
        
    elif action == "warn":
        users_warns[user_id] = users_warns.get(user_id, 0) + 1
        await bot.send_message(user_id, f"⚠️ Вы получили предупреждение! ({users_warns[user_id]}/3)")
        if users_warns[user_id] >= 3:
            users_ban[user_id] = True
            await bot.send_message(user_id, "⛔ Вы забанены за 3 предупреждения!")
        log_admin_action(message.from_user.username, "ПРЕДУПРЕЖДЕНИЕ", input_text, f"Предупреждение {users_warns[user_id]}/3")
        await message.answer(f"✅ Выдано предупреждение @{input_text} ({users_warns[user_id]}/3)")
        
    elif action == "mute":
        users_mute[user_id] = datetime.now() + timedelta(hours=1)
        await bot.send_message(user_id, "🔇 Вы были замучены на 1 час!")
        log_admin_action(message.from_user.username, "МУТ", input_text, "Мут на 1 час")
        await message.answer(f"✅ Пользователь @{input_text} замучен на 1 час!")
        
    elif action == "vip_give":
        users_vip[user_id] = True
        users_vip_until[user_id] = (datetime.now() + timedelta(days=30)).isoformat()
        await bot.send_message(user_id, "👑 Вам выдан VIP статус на 30 дней!")
        log_admin_action(message.from_user.username, "VIP ВЫДАН", input_text, "VIP на 30 дней")
        await message.answer(f"✅ Пользователю @{input_text} выдан VIP статус!")
        
    elif action == "vip_remove":
        users_vip[user_id] = False
        await bot.send_message(user_id, "⭐️ Ваш VIP статус был снят!")
        log_admin_action(message.from_user.username, "VIP СНЯТ", input_text, "VIP удалён")
        await message.answer(f"✅ VIP статус снят с @{input_text}!")
        
    elif action == "stats":
        stats = get_user_stats(user_id)
        wr = (stats['games_won'] / max(stats['games_played'], 1)) * 100
        text = (
            f"📊 <b>СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ</b>\n\n"
            f"👤 @{input_text}\n"
            f"🆔 ID: {user_id}\n"
            f"👑 VIP: {'Да' if users_vip.get(user_id, False) else 'Нет'}\n"
            f"⛔ Бан: {'Да' if users_ban.get(user_id, False) else 'Нет'}\n"
            f"⚠️ Предупреждений: {users_warns.get(user_id, 0)}/3\n\n"
            f"💰 Баланс: {format_stars(get_user_balance(user_id))}\n\n"
            f"🎮 Сыграно: {stats['games_played']}\n"
            f"🏆 Побед: {stats['games_won']}\n"
            f"📈 Винрейт: {wr:.1f}%\n"
            f"💎 Выиграно: {format_stars(stats['total_won'])}\n"
            f"💸 Проиграно: {format_stars(stats['total_lost'])}\n"
        )
        await message.answer(text, parse_mode=ParseMode.HTML)
        
    else:
        await state.update_data(admin_target_user=user_id, admin_target_username=input_text)
        await state.set_state(GameStates.admin_change_balance)
        
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
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
        ])
        
        current_balance = get_user_balance(user_id)
        await message.answer(
            f"💰 <b>БАЛАНС ПОЛЬЗОВАТЕЛЯ</b>\n\n"
            f"👤 @{input_text}\n"
            f"💰 Текущий баланс: {format_stars(current_balance)}\n\n"
            f"Выберите действие:",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    
    await state.clear()

@dp.callback_query(F.data.startswith("admin_"))
async def admin_balance_action(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.username or ""):
        await callback.answer("Нет доступа!", show_alert=True)
        return
    
    data = await state.get_data()
    target_user = data.get("admin_target_user")
    target_username = data.get("admin_target_username")
    
    if not target_user:
        await callback.answer("Ошибка!", show_alert=True)
        await state.clear()
        return
    
    if callback.data == "admin_custom":
        await state.set_state(GameStates.admin_change_balance)
        await callback.message.answer(
            "✏️ <b>Введи сумму</b> (можно с минусом для снятия):\n"
            "Примеры:\n<code>500</code> — добавить\n<code>-200</code> — снять\n\n"
            "<i>Для отмены /cancel</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
        )
        await callback.answer()
        return
    
    if callback.data == "admin_back":
        await state.clear()
        await callback.message.edit_text(
            "👑 <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n\nВыберите действие:",
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
        await bot.send_message(target_user, f"👑 <b>Админ изменил баланс!</b>\n\n+{format_stars(amount)}\n💰 Новый баланс: {format_stars(new_balance)}", parse_mode=ParseMode.HTML)
        log_admin_action(callback.from_user.username, "БАЛАНС +", target_username, f"+{amount}")
        result_text = f"✅ Добавлено +{format_stars(amount)} пользователю @{target_username}"
    else:
        new_balance = update_balance(target_user, -amount)
        save_transaction(target_user, -amount, "admin_remove", f"Админ забрал {amount} Stars")
        await bot.send_message(target_user, f"👑 <b>Админ изменил баланс!</b>\n\n-{format_stars(amount)}\n💰 Новый баланс: {format_stars(new_balance)}", parse_mode=ParseMode.HTML)
        log_admin_action(callback.from_user.username, "БАЛАНС -", target_username, f"-{amount}")
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
    if not is_admin(message.from_user.username or ""):
        await state.clear()
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
        await message.answer("❌ Ошибка!", reply_markup=get_admin_panel_keyboard())
        return
    
    try:
        amount = int(message.text.strip())
        new_balance = update_balance(target_user, amount)
        tx_type = "admin_add" if amount > 0 else "admin_remove"
        save_transaction(target_user, amount, tx_type, f"Админ изменил баланс на {amount}")
        await bot.send_message(target_user, f"👑 <b>Админ изменил баланс!</b>\n\n{'+' if amount > 0 else ''}{format_stars(amount)}\n💰 Новый баланс: {format_stars(new_balance)}", parse_mode=ParseMode.HTML)
        log_admin_action(message.from_user.username, "БАЛАНС", target_username, f"{amount}")
        await state.clear()
        await message.answer(
            f"✅ Баланс @{target_username} изменён на {format_stars(amount)}\n"
            f"💰 Новый баланс: {format_stars(new_balance)}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )
    except ValueError:
        await message.answer("❌ Введи число!")

@dp.message(F.text == "📢 Рассылка")
async def admin_mailing(message: Message, state: FSMContext):
    if not is_admin(message.from_user.username or ""):
        return
    await state.set_state(GameStates.admin_mailing)
    await message.answer(
        "📢 <b>РАССЫЛКА</b>\n\n"
        "Отправь сообщение для рассылки ВСЕМ пользователям.\n"
        "Поддерживается: текст, фото, видео, документы.\n\n"
        "<i>Для отмены /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(GameStates.admin_mailing)
async def admin_mailing_handler(message: Message, state: FSMContext):
    if not is_admin(message.from_user.username or ""):
        await state.clear()
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Рассылка отменена.", reply_markup=get_admin_panel_keyboard())
        return
    
    success = 0
    fail = 0
    
    progress = await message.answer("📢 <b>Начинаю рассылку...</b>\n\n⏳ Пожалуйста, подождите...", parse_mode=ParseMode.HTML)
    
    for user_id in users_balance.keys():
        if users_ban.get(user_id, False):
            continue
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
    await progress.edit_text(
        f"✅ <b>РАССЫЛКА ЗАВЕРШЕНА</b>\n\n"
        f"📨 Доставлено: {success}\n❌ Ошибок: {fail}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard()
    )
    log_admin_action(message.from_user.username, "РАССЫЛКА", f"Успешно: {success}, Ошибок: {fail}", "")

@dp.message(F.text == "👥 Список пользователей")
async def admin_users_list(message: Message):
    if not is_admin(message.from_user.username or ""):
        return
    
    users_list = []
    for uid, uname in users_username.items():
        balance = get_user_balance(uid)
        vip = "👑" if users_vip.get(uid, False) else ""
        ban = "⛔" if users_ban.get(uid, False) else ""
        users_list.append(f"{vip}{ban} @{uname or uid} — {balance}⭐️")
    
    if not users_list:
        text = "👥 Пользователей пока нет"
    else:
        text = "👥 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ</b>\n\n" + "\n".join(users_list[:50])
        if len(users_list) > 50:
            text += f"\n\n... и ещё {len(users_list)-50} пользователей"
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "📜 Логи транзакций")
async def admin_logs(message: Message):
    if not is_admin(message.from_user.username or ""):
        return
    
    all_txs = []
    for uid, tx_list in transactions.items():
        uname = users_username.get(uid, str(uid))
        for tx in tx_list[-3:]:
            all_txs.append((tx["timestamp"], f"@{uname}: {tx['type']} {tx['amount']}⭐️"))
    
    all_txs.sort(reverse=True)
    recent = all_txs[:30]
    
    if not recent:
        text = "📜 Логов пока нет"
    else:
        text = "📜 <b>ПОСЛЕДНИЕ ТРАНЗАКЦИИ</b>\n\n" + "\n".join([f"• {tx[1]}" for tx in recent])
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "💾 Сохранить данные")
async def admin_save(message: Message):
    if not is_admin(message.from_user.username or ""):
        return
    
    data = {
        "balance": users_balance, "referrer": users_referrer, "referrals": users_referrals,
        "stats": users_stats, "transactions": transactions, "username": users_username,
        "join_date": users_join_date, "ban": users_ban, "warns": users_warns,
        "vip": users_vip, "daily_bonus": users_daily_bonus
    }
    
    try:
        with open("backup.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        await message.answer("✅ <b>Данные сохранены!</b>", parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())
        log_admin_action(message.from_user.username, "СОХРАНЕНИЕ", "backup.json", "OK")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "🎁 Управление бонусами")
async def admin_bonus_management(message: Message, state: FSMContext):
    if not is_admin(message.from_user.username or ""):
        return
    await state.set_state(GameStates.admin_set_bonus)
    await message.answer(
        "🎁 <b>УПРАВЛЕНИЕ БОНУСАМИ</b>\n\n"
        "Введи сумму бонуса и username (через пробел):\n"
        "Пример: <code>100 hjklgf1</code>\n\n"
        "<i>/cancel - отмена</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(GameStates.admin_set_bonus)
async def admin_bonus_handler(message: Message, state: FSMContext):
    if not is_admin(message.from_user.username or ""):
        await state.clear()
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=get_admin_panel_keyboard())
        return
    
    try:
        parts = message.text.split()
        amount = int(parts[0])
        username = parts[1].replace("@", "")
        user_id = await get_user_id_by_username(username)
        
        if not user_id:
            await message.answer("❌ Пользователь не найден!")
            return
        
        new_balance = update_balance(user_id, amount)
        save_transaction(user_id, amount, "admin_bonus", f"Бонус от админа")
        await bot.send_message(user_id, f"🎁 <b>Вы получили бонус!</b>\n\n+{format_stars(amount)}\n💰 Новый баланс: {format_stars(new_balance)}", parse_mode=ParseMode.HTML)
        log_admin_action(message.from_user.username, "БОНУС", username, f"+{amount}")
        await message.answer(f"✅ Выдан бонус {format_stars(amount)} пользователю @{username}!")
        await state.clear()
        await message.answer("👑 Админ-панель", reply_markup=get_admin_panel_keyboard())
    except:
        await message.answer("❌ Ошибка! Формат: <code>100 username</code>", parse_mode=ParseMode.HTML)

@dp.message(F.text == "📝 Промокоды")
async def admin_promo(message: Message, state: FSMContext):
    if not is_admin(message.from_user.username or ""):
        return
    await state.set_state(GameStates.admin_create_promo)
    await message.answer(
        "📝 <b>СОЗДАНИЕ ПРОМОКОДА</b>\n\n"
        "Введи: <code>название сумма лимит</code>\n"
        "Пример: <code>WELCOME100 100 50</code>\n\n"
        "<i>/cancel - отмена</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(GameStates.admin_create_promo)
async def admin_promo_handler(message: Message, state: FSMContext):
    if not is_admin(message.from_user.username or ""):
        await state.clear()
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=get_admin_panel_keyboard())
        return
    
    try:
        parts = message.text.split()
        code = parts[0].upper()
        amount = int(parts[1])
        limit = int(parts[2])
        
        promo_codes[code] = {"amount": amount, "limit": limit, "used": 0}
        log_admin_action(message.from_user.username, "ПРОМОКОД", code, f"{amount}⭐️ лимит {limit}")
        await message.answer(f"✅ Промокод <code>{code}</code> создан!\nСумма: {amount}⭐️\nЛимит: {limit} использований")
        await state.clear()
        await message.answer("👑 Админ-панель", reply_markup=get_admin_panel_keyboard())
    except:
        await message.answer("❌ Ошибка! Формат: <code>CODE 100 50</code>", parse_mode=ParseMode.HTML)

@dp.message(F.text == "🏆 Лотерея/Розыгрыш")
async def admin_lottery(message: Message, state: FSMContext):
    if not is_admin(message.from_user.username or ""):
        return
    await state.set_state(GameStates.admin_create_giveaway)
    await message.answer(
        "🏆 <b>СОЗДАНИЕ РОЗЫГРЫША</b>\n\n"
        "Введи: <code>название приз длительность_минут</code>\n"
        "Пример: <code>1000⭐️ 1000 60</code>\n\n"
        "<i>/cancel - отмена</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(GameStates.admin_create_giveaway)
async def admin_giveaway_handler(message: Message, state: FSMContext):
    if not is_admin(message.from_user.username or ""):
        await state.clear()
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=get_admin_panel_keyboard())
        return
    
    try:
        parts = message.text.split()
        prize = parts[0]
        amount = int(parts[1])
        duration = int(parts[2])
        
        giveaway_id = f"giveaway_{datetime.now().timestamp()}"
        giveaway_active[giveaway_id] = {"prize": prize, "amount": amount, "end_time": datetime.now() + timedelta(minutes=duration)}
        giveaway_participants[giveaway_id] = []
        
        await bot.send_message(message.chat.id, 
            f"🎉 <b>РОЗЫГРЫШ ЗАПУЩЕН!</b> 🎉\n\n"
            f"🏆 Приз: {prize} ({amount}⭐️)\n"
            f"⏰ Длительность: {duration} минут\n\n"
            f"Участвуй — отправь /giveaway {giveaway_id}",
            parse_mode=ParseMode.HTML)
        
        log_admin_action(message.from_user.username, "РОЗЫГРЫШ", giveaway_id, f"{prize} {amount}⭐️")
        await message.answer(f"✅ Розыгрыш запущен! ID: {giveaway_id}")
        await state.clear()
        await message.answer("👑 Админ-панель", reply_markup=get_admin_panel_keyboard())
    except:
        await message.answer("❌ Ошибка! Формат: <code>Название 1000 60</code>", parse_mode=ParseMode.HTML)

@dp.message(F.text == "⚙️ Настройки бота")
async def admin_settings(message: Message):
    if not is_admin(message.from_user.username or ""):
        return
    
    text = (
        f"⚙️ <b>НАСТРОЙКИ БОТА</b>\n\n"
        f"💰 Мин. вывод: {system_settings['min_withdraw']}⭐️\n"
        f"💰 Макс. вывод: {system_settings['max_withdraw']}⭐️\n"
        f"🎁 Бонус %: {system_settings['bonus_percent']}%\n"
        f"👥 Реф. %: {system_settings['ref_percent']}%\n"
        f"🔧 Режим обслуживания: {'ВКЛ' if system_settings['maintenance'] else 'ВЫКЛ'}\n\n"
        f"Используйте команды:\n"
        f"/set_min [сумма] - мин. вывод\n"
        f"/set_max [сумма] - макс. вывод\n"
        f"/set_bonus [%] - бонус %\n"
        f"/set_ref [%] - реф. %\n"
        f"/maintenance - вкл/выкл режим"
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "🔙 Назад в админку")
async def back_to_admin(message: Message):
    if not is_admin(message.from_user.username or ""):
        return
    await message.answer("👑 Админ-панель", reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "🔙 В главное меню")
async def back_to_main(message: Message):
    await message.answer("🌟 Главное меню", reply_markup=get_main_keyboard())

@dp.message(F.text == "🔙 Главное меню")
async def back_to_main_from_games(message: Message):
    await message.answer("🌟 Главное меню", reply_markup=get_main_keyboard())

@dp.message(F.text == "🔙 Назад")
async def back_callback(message: Message):
    if is_admin(message.from_user.username or ""):
        await message.answer("👑 Админ-панель", reply_markup=get_admin_panel_keyboard())
    else:
        await message.answer("🌟 Главное меню", reply_markup=get_main_keyboard())


# ===================== ПОДДЕРЖКА =====================
@dp.message(GameStates.support_message)
async def support_handler(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=get_main_keyboard())
        return
    
    support_requests[message.from_user.id] = {
        "message": message.text,
        "user": message.from_user.username,
        "timestamp": datetime.now().isoformat()
    }
    
    for admin in ADMIN_USERNAMES:
        try:
            await bot.send_message(
                await get_user_id_by_username(admin),
                f"📞 <b>НОВОЕ ОБРАЩЕНИЕ</b>\n\n"
                f"👤 От: @{message.from_user.username}\n"
                f"💬 Сообщение: {message.text}\n\n"
                f"Ответьте пользователю @{message.from_user.username}",
                parse_mode=ParseMode.HTML
            )
        except:
            pass
    
    await state.clear()
    await message.answer(
        "✅ <b>Сообщение отправлено!</b>\n\n"
        "Администратор свяжется с вами в ближайшее время.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )


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
                await bot.send_message(referrer, f"🎉 <b>Реферальный бонус!</b>\n\nВаш реферал пополнил на {format_stars(amount)}\nВы получили {format_stars(bonus)}!", parse_mode=ParseMode.HTML)
            except:
                pass
    
    await message.answer(
        f"✅ <b>Пополнение выполнено!</b>\n\n+{format_stars(amount)}\n💰 Новый баланс: {format_stars(new_balance)}\n\n🎮 Приятной игры!",
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


# ===================== КОМАНДЫ АДМИНА =====================
@dp.message(Command("admin"))
async def admin_command(message: Message):
    if is_admin(message.from_user.username or ""):
        await admin_panel_reply(message)
    else:
        await message.answer("❌ Нет доступа!")

@dp.message(Command("set_min"))
async def set_min_withdraw(message: Message):
    if not is_admin(message.from_user.username or ""):
        return
    try:
        amount = int(message.text.split()[1])
        system_settings["min_withdraw"] = amount
        await message.answer(f"✅ Мин. вывод установлен: {amount}⭐️")
    except:
        await message.answer("❌ Использование: /set_min 100")

@dp.message(Command("set_max"))
async def set_max_withdraw(message: Message):
    if not is_admin(message.from_user.username or ""):
        return
    try:
        amount = int(message.text.split()[1])
        system_settings["max_withdraw"] = amount
        await message.answer(f"✅ Макс. вывод установлен: {amount}⭐️")
    except:
        await message.answer("❌ Использование: /set_max 10000")

@dp.message(Command("maintenance"))
async def toggle_maintenance(message: Message):
    if not is_admin(message.from_user.username or ""):
        return
    system_settings["maintenance"] = not system_settings["maintenance"]
    status = "ВКЛЮЧЕН" if system_settings["maintenance"] else "ВЫКЛЮЧЕН"
    await message.answer(f"🔧 Режим обслуживания {status}")


# ===================== НАВИГАЦИЯ =====================
@dp.callback_query(F.data == "back_to_games")
async def back_to_games_callback(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("🎮 <b>Выбери игру</b>", parse_mode=ParseMode.HTML, reply_markup=get_games_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("🌟 <b>Главное меню</b>", parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard())
    await callback.answer()

@dp.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    username = message.from_user.username or ""
    if is_admin(username):
        await message.answer("❌ Действие отменено.", reply_markup=get_admin_panel_keyboard())
    else:
        await message.answer("❌ Действие отменено.", reply_markup=get_main_keyboard())


# ===================== ЗАПУСК =====================
async def main():
    logger.info("🚀 StarPlay Bot запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())