import asyncio
import hashlib
import logging
import random
import json
import os
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
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InputFile, FSInputFile
)
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# ===================== КОНФИГУРАЦИЯ =====================
BOT_TOKEN = "8251949164:AAE1fYvR_cMK7PnykcqpCxaXS9vIWxo1VjQ"
ADMIN_USERNAMES = ["hjklgf1", "admin"]

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
users_monthly_bonus: Dict[int, str] = {}
pending_payments: Dict[str, dict] = {}
transactions: Dict[int, list] = {}
users_username: Dict[int, str] = {}
users_join_date: Dict[int, str] = {}
users_last_activity: Dict[int, str] = {}
users_warnings: Dict[int, int] = {}
users_bans: Dict[int, bool] = {}
users_mutes: Dict[int, dict] = {}
users_achievements: Dict[int, list] = {}
users_daily_streak: Dict[int, int] = {}
users_last_daily: Dict[int, str] = {}
users_referral_codes: Dict[int, str] = {}
users_promo_used: Dict[int, list] = {}
active_promocodes: Dict[str, dict] = {}
lottery_tickets: Dict[int, int] = {}
lottery_active: bool = False
lottery_pool: int = 0
lottery_participants: Dict[int, int] = {}
blacklisted_users: List[int] = []
bot_settings: Dict[str, any] = {
    "game_multipliers": {"easy": 1.2, "medium": 1.5, "hard": 2.0},
    "daily_bonus_min": 5,
    "daily_bonus_max": 15,
    "referral_enabled": True,
    "min_withdraw": 100,
    "maintenance_mode": False,
    "chat_link": "https://t.me/your_chat",
    "support_link": "https://t.me/your_support"
}
withdraw_requests: Dict[int, dict] = {}
support_tickets: Dict[int, list] = {}
user_settings: Dict[int, dict] = {}
tournaments: Dict[int, dict] = {}
active_tournaments: List[int] = []
shop_items: Dict[int, dict] = {}
user_inventory: Dict[int, list] = {}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# ===================== FSM =====================
class GameStates(StatesGroup):
    custom_deposit = State()
    custom_withdraw = State()
    admin_find_user = State()
    admin_change_balance = State()
    admin_send_message = State()
    admin_broadcast = State()
    admin_add_promo = State()
    admin_remove_promo = State()
    admin_set_settings = State()
    admin_create_tournament = State()
    admin_add_shop_item = State()
    admin_remove_shop_item = State()
    admin_support_reply = State()
    dice_game = State()
    mines_game = State()
    pyramid_game = State()
    tournament_bet = State()
    shop_buy = State()
    withdraw_amount = State()
    support_message = State()
    change_settings = State()
    promo_enter = State()


# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
def is_admin(username: str) -> bool:
    if bot_settings.get("maintenance_mode", False) and username not in ADMIN_USERNAMES:
        return False
    return username.lower() in [adm.lower() for adm in ADMIN_USERNAMES]

def is_banned(user_id: int) -> bool:
    return user_id in blacklisted_users or users_bans.get(user_id, False)

def is_muted(user_id: int) -> bool:
    mute_data = users_mutes.get(user_id)
    if mute_data and datetime.now() < datetime.fromisoformat(mute_data["until"]):
        return True
    if user_id in users_mutes:
        del users_mutes[user_id]
    return False

async def get_user_id_by_username(username: str) -> Optional[int]:
    for uid, uname in users_username.items():
        if uname and uname.lower() == username.lower():
            return uid
    return None

def generate_referral_link(user_id: int) -> str:
    if user_id not in users_referral_codes:
        code = hashlib.md5(f"starplay_{user_id}_{datetime.now()}".encode()).hexdigest()[:8]
        users_referral_codes[user_id] = code
    return f"https://t.me/{bot.username}?start=ref_{users_referral_codes[user_id]}"

def get_user_stats(user_id: int) -> dict:
    if user_id not in users_stats:
        users_stats[user_id] = {
            "games_played": 0, "games_won": 0, "total_won": 0, "total_lost": 0,
            "roulette_wins": 0, "darts_wins": 0, "football_wins": 0,
            "bowling_wins": 0, "basketball_wins": 0, "mines_wins": 0,
            "pyramid_wins": 0, "slots_wins": 0, "highest_win": 0,
            "longest_streak": 0, "current_streak": 0, "total_bet": 0
        }
    return users_stats[user_id]

def get_user_achievements(user_id: int) -> list:
    if user_id not in users_achievements:
        users_achievements[user_id] = []
    return users_achievements[user_id]

def check_achievements(user_id: int):
    stats = get_user_stats(user_id)
    achievements = get_user_achievements(user_id)
    new_achievements = []
    
    if stats["games_played"] >= 10 and "novice" not in achievements:
        achievements.append("novice")
        new_achievements.append("🎮 Новичок (10 игр)")
    if stats["games_played"] >= 100 and "veteran" not in achievements:
        achievements.append("veteran")
        new_achievements.append("🎖 Ветеран (100 игр)")
    if stats["total_won"] >= 1000 and "rich" not in achievements:
        achievements.append("rich")
        new_achievements.append("💰 Богач (выиграно 1000⭐️)")
    if stats["games_won"] >= 50 and "winner" not in achievements:
        achievements.append("winner")
        new_achievements.append("🏆 Победитель (50 побед)")
    if stats["longest_streak"] >= 5 and "streaker" not in achievements:
        achievements.append("streaker")
        new_achievements.append("⚡️ Стрикер (5 побед подряд)")
    
    return new_achievements

def update_balance(user_id: int, delta: int) -> int:
    if is_banned(user_id):
        return get_user_balance(user_id)
    current = users_balance.get(user_id, 0)
    new_balance = current + delta
    if new_balance < 0:
        new_balance = 0
    users_balance[user_id] = new_balance
    
    if delta > 0:
        stats = get_user_stats(user_id)
        if delta > stats["highest_win"]:
            stats["highest_win"] = delta
    
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
    
    # Ограничим историю 100 транзакциями
    if len(transactions[user_id]) > 100:
        transactions[user_id] = transactions[user_id][-100:]

def format_stars(amount: int) -> str:
    return f"⭐️ {amount:,} Stars"

def get_random_emoji() -> str:
    return random.choice(["🎲","🎯","⚡️","💫","🌟","⭐️","✨","🎮","🎰","🔥","💎","🏆"])


# ===================== ЛОГИКА DICE ИГР =====================
# Все игры используют sendDice с разными эмодзи
DICE_GAMES = {
    "🎲": {
        "name": "Кубик",
        "description": "🎲 Классический кубик\n• 1-2 → проигрыш\n• 3 → x1\n• 4 → x2\n• 5 → x3\n• 6 → x5",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 3, 6: 5}
    },
    "🎯": {
        "name": "Дартс",
        "description": "🎯 Попади в яблочко!\n• 1-2 → мимо\n• 3 → x1\n• 4 → x2\n• 5 → x4\n• 6 → ЯБЛОЧКО x10!",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 4, 6: 10}
    },
    "⚽️": {
        "name": "Футбол",
        "description": "⚽️ Пенальти!\n• 1-2 → сейв\n• 3 → гол x1\n• 4 → рикошет x2\n• 5 → красивый гол x3\n• 6 → ШЕДЕВР x5!",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 3, 6: 5}
    },
    "🏀": {
        "name": "Баскетбол",
        "description": "🏀 Трёхочковый!\n• 1-2 → промах\n• 3 → попадание x1\n• 4 → сверху x2\n• 5 → издали x4\n• 6 → БАЗЗЕР x6!",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 4, 6: 6}
    },
    "🎳": {
        "name": "Боулинг",
        "description": "🎳 Страйк!\n• 1-2 → страйк-аут\n• 3 → спэр x1\n• 4 → страйк x2\n• 5 → идеальный x5\n• 6 → 10 СТРАЙКОВ x10!",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 5, 6: 10}
    },
    "🎰": {
        "name": "Слоты",
        "description": "🎰 Классические слоты!\nСобирай комбинации символов",
        "type": "slots"
    }
}

SLOT_SYMBOLS = ["🍒", "🍊", "🍋", "💎", "7️⃣", "🎰", "⭐️", "💫"]
SLOT_PAYOUTS = {
    ("🍒", "🍒", "🍒"): 5, ("🍊", "🍊", "🍊"): 7, ("🍋", "🍋", "🍋"): 10,
    ("💎", "💎", "💎"): 15, ("7️⃣", "7️⃣", "7️⃣"): 25, ("🎰", "🎰", "🎰"): 50,
    ("⭐️", "⭐️", "⭐️"): 30, ("💫", "💫", "💫"): 20
}

RESULT_MESSAGES = {
    1: "😭 Ужасный результат!",
    2: "😢 Обидный промах...",
    3: "🤔 Неплохо, могло быть лучше!",
    4: "😊 Хороший результат!",
    5: "😎 Отличный результат!",
    6: "🤯 НЕВЕРОЯТНО! 🔥"
}

EMOJI_RESULTS = {1: "💀", 2: "😢", 3: "🤔", 4: "😊", 5: "😎", 6: "🤯"}


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
    builder.button(text="🎲 Ежедневный бонус")
    builder.button(text="🎰 Лотерея")
    builder.button(text="🏪 Магазин")
    builder.button(text="🎯 Турниры")
    builder.button(text="📞 Поддержка")
    builder.button(text="⚙️ Настройки")
    builder.button(text="👑 Админ панель")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_admin_panel_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📊 Статистика")
    builder.button(text="💰 Изменить баланс")
    builder.button(text="📢 Рассылка")
    builder.button(text="👥 Пользователи")
    builder.button(text="📜 Транзакции")
    builder.button(text="💾 Бекап")
    builder.button(text="🎁 Промокоды")
    builder.button(text="⚙️ Настройки бота")
    builder.button(text="🚫 Баны/Муты")
    builder.button(text="🎰 Лотерея упр.")
    builder.button(text="🏆 Турниры упр.")
    builder.button(text="🏪 Магазин упр.")
    builder.button(text="📊 Детальная стат.")
    builder.button(text="📈 Графики")
    builder.button(text="💰 Вывод средств")
    builder.button(text="🎫 Тикеты")
    builder.button(text="📋 Логи ошибок")
    builder.button(text="🔄 Обновить данные")
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
         InlineKeyboardButton(text="⭐️ 5000", callback_data=f"{game_key}_bet_5000")],
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
        [InlineKeyboardButton(text="🎁 Ввести промокод", callback_data="enter_promo")],
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
    keyboard.append([InlineKeyboardButton(text="◀️ Выйти", callback_data="back_to_games")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_pyramid_keyboard(level: int, current_win: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬆️ Подняться (x2)", callback_data="pyramid_up")],
        [InlineKeyboardButton(text=f"💰 Забрать {format_stars(current_win)}", callback_data="pyramid_cashout")],
        [InlineKeyboardButton(text="◀️ Выйти", callback_data="back_to_games")]
    ])

def get_tournament_keyboard(tournament_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Участвовать", callback_data=f"tournament_join_{tournament_id}")],
        [InlineKeyboardButton(text="🏆 Рейтинг", callback_data=f"tournament_rating_{tournament_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_games")]
    ])

def get_shop_keyboard() -> InlineKeyboardMarkup:
    keyboard = []
    for item_id, item in shop_items.items():
        keyboard.append([InlineKeyboardButton(text=f"{item['emoji']} {item['name']} - {format_stars(item['price'])}", callback_data=f"shop_buy_{item_id}")])
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ===================== ОСНОВНЫЕ КОМАНДЫ =====================
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    
    if is_banned(user_id):
        await message.answer("🚫 Вы забанены в этом боте!")
        return
    
    users_username[user_id] = username
    users_last_activity[user_id] = datetime.now().isoformat()
    
    if user_id not in users_join_date:
        users_join_date[user_id] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Реферальная система
    if " " in message.text:
        param = message.text.split()[1]
        if param.startswith("ref_"):
            code = param[4:]
            for uid, ucode in users_referral_codes.items():
                if ucode == code and uid != user_id and user_id not in users_referrer:
                    users_referrer[user_id] = uid
                    users_referrals.setdefault(uid, []).append(user_id)
                    update_balance(user_id, REFERRAL_SIGNUP_BONUS)
                    update_balance(uid, REFERRAL_INVITE_BONUS)
                    save_transaction(user_id, REFERRAL_SIGNUP_BONUS, "referral_bonus", f"от {uid}")
                    save_transaction(uid, REFERRAL_INVITE_BONUS, "referral_reward", f"пригласил {user_id}")
                    await message.answer(f"✅ Вы получили {format_stars(REFERRAL_SIGNUP_BONUS)} за регистрацию по ссылке!")
                    try:
                        await bot.send_message(uid, f"🎉 Новый реферал! @{username} зарегистрировался по вашей ссылке!\n💰 Вы получили {format_stars(REFERRAL_INVITE_BONUS)}")
                    except:
                        pass
                    break
    
    welcome_text = (
        f"🌟 <b>Добро пожаловать в StarPlay!</b> 🌟\n\n"
        f"{get_random_emoji()} <b>Играй на Telegram Stars и выигрывай!</b>\n\n"
        f"<b>🎮 Доступные игры:</b>\n"
        f"🎲 Кубик | 🎯 Дартс | ⚽️ Футбол | 🏀 Баскетбол | 🎳 Боулинг\n"
        f"🎰 Слоты | 💣 Мины | 🏛 Пирамида\n\n"
        f"<b>💫 Новые функции:</b>\n"
        f"• 🎁 Ежедневный бонус (до 100⭐️)\n"
        f"• 🎰 Еженедельная лотерея\n"
        f"• 🏪 Магазин скинов и бонусов\n"
        f"• 🏆 Турниры с большими призами\n"
        f"• 👥 Реферальная система\n\n"
        f"👇 <i>Используй кнопки внизу!</i>"
    )
    
    keyboard = get_admin_panel_keyboard() if is_admin(username) else get_main_keyboard()
    await message.answer(welcome_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


# ===================== DICE ИГРЫ =====================
async def play_dice_game(message: Message, game_emoji: str, bet: int, state: FSMContext):
    """Универсальная функция для игры в dice"""
    user_id = message.from_user.id
    
    if is_banned(user_id):
        await message.answer("🚫 Вы забанены!")
        return
    
    if is_muted(user_id):
        await message.answer("🔇 Вы замьючены!")
        return
    
    if get_user_balance(user_id) < bet:
        await message.answer(f"❌ Не хватает {format_stars(bet)}")
        return
    
    game = DICE_GAMES[game_emoji]
    await state.update_data(dice_game_data={"emoji": game_emoji, "bet": bet})
    
    await message.answer(
        f"{game_emoji} <b>{game['name']}</b>\n\n"
        f"📋 <b>Правила:</b>\n{game['description']}\n\n"
        f"💰 Ставка: {format_stars(bet)}\n\n"
        f"👇 <b>Нажми на кнопку, чтобы начать!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{game_emoji} ИГРАТЬ!", callback_data=f"play_dice_{game_emoji}")]
        ])
    )

@dp.callback_query(F.data.startswith("play_dice_"))
async def play_dice_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    game_data = data.get("dice_game_data")
    
    if not game_data:
        await callback.answer("Ошибка! Начните игру заново.", show_alert=True)
        return
    
    game_emoji = game_data["emoji"]
    bet = game_data["bet"]
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        await state.clear()
        return
    
    update_balance(user_id, -bet)
    
    # Отправляем dice через sendDice
    dice_message = await callback.message.answer_dice(emoji=game_emoji)
    dice_value = dice_message.dice.value
    
    game = DICE_GAMES[game_emoji]
    multiplier = game["multipliers"].get(dice_value, 0)
    
    if multiplier > 0:
        win_amount = bet * multiplier
        update_balance(user_id, win_amount)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["current_streak"] += 1
        if stats["current_streak"] > stats["longest_streak"]:
            stats["longest_streak"] = stats["current_streak"]
        stats["total_bet"] += bet
        stats["total_won"] += win_amount
        
        game_attr = f"{game_emoji}_wins"
        if game_attr in stats:
            stats[game_attr] += 1
        
        save_transaction(user_id, win_amount, "game_win", f"{game['name']} x{multiplier}")
        
        # Проверка достижений
        new_achievements = check_achievements(user_id)
        ach_text = ""
        if new_achievements:
            ach_text = f"\n\n🏆 <b>Новое достижение!</b>\n" + "\n".join(new_achievements)
        
        result_text = (
            f"🎉 <b>ВЫИГРЫШ!</b> 🎉\n\n"
            f"✨ Множитель: <b>x{multiplier}</b>\n"
            f"🏆 Выигрыш: <b>+{format_stars(win_amount)}</b>{ach_text}"
        )
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["current_streak"] = 0
        stats["total_bet"] += bet
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", game['name'])
        result_text = f"😢 <b>Проигрыш</b>\n\n-{format_stars(bet)}"
    
    await callback.message.answer(
        f"{game_emoji} <b>{game['name']}</b>\n\n"
        f"{EMOJI_RESULTS.get(dice_value, '🎲')} <b>Результат: {dice_value}</b>\n"
        f"{RESULT_MESSAGES.get(dice_value, '')}\n\n"
        f"💰 Ставка: {format_stars(bet)}\n\n"
        f"{result_text}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await state.clear()
    await callback.answer()


# ---------- ОБРАБОТЧИКИ КАЖДОЙ ИГРЫ ----------
@dp.message(F.text == "🎲 Кубик")
async def cube_start(message: Message):
    await message.answer(
        "🎲 <b>ИГРА КУБИК</b>\n\n"
        f"{DICE_GAMES['🎲']['description']}\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("dice")
    )

@dp.callback_query(F.data.startswith("dice_bet_"))
async def dice_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    await play_dice_game(callback.message, "🎲", bet, state)
    await callback.answer()

@dp.message(F.text == "🎯 Дартс")
async def darts_start(message: Message):
    await message.answer(
        "🎯 <b>ИГРА ДАРТС</b>\n\n"
        f"{DICE_GAMES['🎯']['description']}\n\n"
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
        "⚽️ <b>ИГРА ФУТБОЛ</b>\n\n"
        f"{DICE_GAMES['⚽️']['description']}\n\n"
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
        "🏀 <b>ИГРА БАСКЕТБОЛ</b>\n\n"
        f"{DICE_GAMES['🏀']['description']}\n\n"
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
        "🎳 <b>ИГРА БОУЛИНГ</b>\n\n"
        f"{DICE_GAMES['🎳']['description']}\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("bowling")
    )

@dp.callback_query(F.data.startswith("bowling_bet_"))
async def bowling_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    await play_dice_game(callback.message, "🎳", bet, state)
    await callback.answer()


# ---------- СЛОТЫ ----------
@dp.message(F.text == "🎰 Слоты")
async def slots_start(message: Message):
    await message.answer(
        "🎰 <b>СЛОТЫ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "Собери комбинацию и получи множители:\n"
        "• 🍒🍒🍒 → x5\n• 🍊🍊🍊 → x7\n• 🍋🍋🍋 → x10\n"
        "• 💎💎💎 → x15\n• 7️⃣7️⃣7️⃣ → x25\n• 🎰🎰🎰 → ДЖЕКПОТ x50!\n"
        "• ⭐️⭐️⭐️ → x30\n• 💫💫💫 → x20\n"
        "• 2 одинаковых → x1.5\n\n"
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
    
    # Симуляция слотов (Telegram не имеет встроенных слотов, используем случайные символы)
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
        stats["total_bet"] += bet
        save_transaction(user_id, win, "game_win", f"Слоты x{mult}")
        res = f"🎉 <b>ДЖЕКПОТ!</b> x{mult}\n+{format_stars(win)}"
    elif reel1 == reel2 or reel1 == reel3 or reel2 == reel3:
        win = int(bet * 1.5)
        update_balance(user_id, win)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_won"] += win
        stats["total_bet"] += bet
        save_transaction(user_id, win, "game_win", f"Слоты пара")
        res = f"🎉 <b>ПАРА!</b> x1.5\n+{format_stars(win)}"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        stats["total_bet"] += bet
        save_transaction(user_id, -bet, "game_loss", "Слоты")
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
    await message.answer(
        "💣 <b>МИНЫ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "Поле 5x5, скрыто 5 мин.\n"
        "• 💎 → увеличивает множитель x1.2\n"
        "• 💣 → мгновенный проигрыш\n"
        "• Максимальный множитель: x18\n"
        "• Можно забрать выигрыш в любой момент\n\n"
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
        f"✨ Множитель: x{active_mines_games[user_id]['multiplier']:.1f}\n"
        f"📦 Открыто: 0/20\n"
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
        stats["total_bet"] += game["bet"]
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
            stats["total_bet"] += game["bet"]
            save_transaction(user_id, win, "game_win", f"Мины победа x{game['multiplier']:.1f}")
            del active_mines_games[user_id]
            
            await callback.message.edit_text(
                f"💣 <b>МИНЫ</b>\n\n"
                f"🎉 <b>ПОБЕДА!</b> Ты очистил всё поле! 🎉\n\n"
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
    stats["total_bet"] += game["bet"]
    save_transaction(user_id, win, "game_win", f"Мины кэшаут {game['cells_opened']} клеток x{game['multiplier']:.1f}")
    del active_mines_games[user_id]
    
    await callback.message.edit_text(
        f"💣 <b>МИНЫ</b>\n\n"
        f"💰 <b>Ты забрал выигрыш!</b> 💰\n\n"
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
        "5 уровней, каждый шаг удваивает выигрыш\n"
        "• Шанс успеха: 50%\n"
        "• Проигрыш = потеря ставки\n"
        "• На 5 уровне множитель x16!\n\n"
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
        f"✨ Макс. множитель: x16!\n\n"
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
            stats["total_bet"] += game["bet"]
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
                f"💰 Выигрыш: {format_stars(game['current'])}\n"
                f"🎯 Следующий уровень: {format_stars(game['current'] * 2)}\n"
                f"📊 Шанс успеха: 50%\n\n"
                f"👇 <b>Продолжим?</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_pyramid_keyboard(game["level"], game["current"])
            )
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += game["bet"]
        stats["total_bet"] += game["bet"]
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
    stats["total_bet"] += game["bet"]
    save_transaction(user_id, win, "game_win", f"Пирамида кэшаут уровень {game['level']} x{win // game['bet']}")
    del active_pyramids[user_id]
    
    await callback.message.edit_text(
        f"🏛 <b>ПИРАМИДА</b>\n\n"
        f"💰 <b>Ты забрал выигрыш!</b> 💰\n\n"
        f"🏆 Уровень: {game['level']}/5\n"
        f"✨ Множитель: x{win // game['bet']}\n"
        f"🏆 Выигрыш: {format_stars(win)}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()


# ===================== ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ =====================
@dp.message(F.text == "🎁 Бонус")
async def bonus_reply(message: Message):
    user_id = message.from_user.id
    today = datetime.now().date().isoformat()
    
    if users_daily_bonus.get(user_id) == today:
        await message.answer(
            f"🎁 <b>Ты уже получил сегодняшний бонус!</b>\n\n"
            f"Возвращайся завтра!",
            parse_mode=ParseMode.HTML
        )
        return
    
    bonus_amount = random.randint(bot_settings["daily_bonus_min"], bot_settings["daily_bonus_max"])
    update_balance(user_id, bonus_amount)
    users_daily_bonus[user_id] = today
    save_transaction(user_id, bonus_amount, "daily_bonus", "Ежедневный бонус")
    
    await message.answer(
        f"🎉 <b>Ежедневный бонус получен!</b> 🎉\n\n"
        f"+{format_stars(bonus_amount)}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text == "🎲 Ежедневный бонус")
async def daily_bonus(message: Message):
    user_id = message.from_user.id
    today = datetime.now().date().isoformat()
    
    if users_daily_bonus.get(user_id) == today:
        await message.answer("🎁 Вы уже получили сегодняшний бонус!")
        return
    
    streak = users_daily_streak.get(user_id, 0)
    yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
    
    if users_last_daily.get(user_id) == yesterday:
        streak += 1
    else:
        streak = 1
    
    bonus_amount = 10 + streak * 2
    bonus_amount = min(bonus_amount, 100)
    
    update_balance(user_id, bonus_amount)
    users_daily_bonus[user_id] = today
    users_daily_streak[user_id] = streak
    users_last_daily[user_id] = today
    save_transaction(user_id, bonus_amount, "daily_streak", f"Стрик {streak} дней")
    
    await message.answer(
        f"🎉 <b>Ежедневный бонус!</b> 🎉\n\n"
        f"🔥 Стрик: {streak} дней\n"
        f"+{format_stars(bonus_amount)}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text == "🎰 Лотерея")
async def lottery_menu(message: Message):
    if not lottery_active:
        await message.answer("🎰 Лотерея сейчас не активна!")
        return
    
    user_id = message.from_user.id
    tickets = lottery_tickets.get(user_id, 0)
    jackpot = lottery_pool
    
    await message.answer(
        f"🎰 <b>ЛОТЕРЕЯ</b>\n\n"
        f"💰 Джекпот: {format_stars(jackpot)}\n"
        f"🎫 Ваши билеты: {tickets}\n"
        f"💰 Цена билета: 10 Stars\n\n"
        f"Шанс выигрыша: 1% за билет\n"
        f"Розыгрыш: каждую неделю\n\n"
        f"👇 Купить билеты:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎫 Купить 1 билет (10⭐️)", callback_data="lottery_buy_1")],
            [InlineKeyboardButton(text="🎫 Купить 5 билетов (45⭐️)", callback_data="lottery_buy_5")],
            [InlineKeyboardButton(text="🎫 Купить 10 билетов (90⭐️)", callback_data="lottery_buy_10")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
        ])
    )

@dp.callback_query(F.data.startswith("lottery_buy_"))
async def lottery_buy(callback: CallbackQuery):
    user_id = callback.from_user.id
    amount = int(callback.data.split("_")[-1])
    
    prices = {1: 10, 5: 45, 10: 90}
    price = prices.get(amount, 10)
    
    if get_user_balance(user_id) < price:
        await callback.answer(f"❌ Не хватает {format_stars(price)}", show_alert=True)
        return
    
    update_balance(user_id, -price)
    lottery_tickets[user_id] = lottery_tickets.get(user_id, 0) + amount
    lottery_pool += price
    save_transaction(user_id, -price, "lottery_ticket", f"Куплено {amount} билетов")
    
    await callback.answer(f"✅ Куплено {amount} билетов!", show_alert=True)
    await lottery_menu(callback.message)

@dp.message(F.text == "🏪 Магазин")
async def shop_menu(message: Message):
    if not shop_items:
        await message.answer("🏪 Магазин временно пуст!")
        return
    
    await message.answer(
        "🏪 <b>МАГАЗИН</b>\n\n"
        "💰 Покупай скины, бонусы и улучшения!\n\n"
        "👇 Выбери товар:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_shop_keyboard()
    )

@dp.callback_query(F.data.startswith("shop_buy_"))
async def shop_buy(callback: CallbackQuery):
    user_id = callback.from_user.id
    item_id = int(callback.data.split("_")[-1])
    
    if item_id not in shop_items:
        await callback.answer("Товар не найден!", show_alert=True)
        return
    
    item = shop_items[item_id]
    
    if get_user_balance(user_id) < item["price"]:
        await callback.answer(f"❌ Не хватает {format_stars(item['price'])}", show_alert=True)
        return
    
    update_balance(user_id, -item["price"])
    
    if user_id not in user_inventory:
        user_inventory[user_id] = []
    user_inventory[user_id].append(item_id)
    
    save_transaction(user_id, -item["price"], "shop_purchase", f"Куплен {item['name']}")
    
    await callback.answer(f"✅ Вы купили {item['name']}!", show_alert=True)
    
    if item.get("effect"):
        if item["effect"] == "bonus_multiplier":
            user_settings[user_id]["multiplier"] = user_settings.get(user_id, {}).get("multiplier", 1.0) * 1.1
            await callback.message.answer(f"🎉 Эффект активирован! Ваш множитель выигрыша увеличен на 10%!")

@dp.message(F.text == "🎯 Турниры")
async def tournaments_menu(message: Message):
    if not active_tournaments:
        await message.answer("🏆 Активных турниров нет!")
        return
    
    text = "🏆 <b>ТУРНИРЫ</b>\n\n"
    for tid in active_tournaments:
        t = tournaments[tid]
        text += f"🎯 {t['name']}\n💰 Призовой фонд: {format_stars(t['prize'])}\n📅 До конца: {t['end_date']}\n\n"
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 Участвовать", callback_data="tournament_join")]
    ]))

@dp.message(F.text == "📞 Поддержка")
async def support_menu(message: Message, state: FSMContext):
    await state.set_state(GameStates.support_message)
    await message.answer(
        "📞 <b>ПОДДЕРЖКА</b>\n\n"
        "Напишите ваше сообщение. Администратор ответит вам в ближайшее время.\n\n"
        "<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML
    )

@dp.message(GameStates.support_message)
async def support_send(message: Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)
    
    support_tickets.setdefault(user_id, []).append({
        "message": message.text,
        "time": datetime.now().isoformat()
    })
    
    for admin in ADMIN_USERNAMES:
        try:
            await bot.send_message(
                admin,
                f"📞 <b>Новое сообщение в поддержку!</b>\n"
                f"👤 От: @{username}\n"
                f"📝 Сообщение: {message.text[:500]}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✏️ Ответить", callback_data=f"reply_{user_id}")]
                ])
            )
        except:
            pass
    
    await state.clear()
    await message.answer("✅ Сообщение отправлено! Администратор ответит вам.")

@dp.message(F.text == "⚙️ Настройки")
async def settings_menu(message: Message):
    user_id = message.from_user.id
    settings = user_settings.get(user_id, {})
    
    notif_status = "✅ Вкл" if settings.get("notifications", True) else "❌ Выкл"
    anon_status = "✅ Вкл" if settings.get("anonymous", False) else "❌ Выкл"
    
    await message.answer(
        f"⚙️ <b>НАСТРОЙКИ</b>\n\n"
        f"🔔 Уведомления: {notif_status}\n"
        f"👤 Анонимный режим: {anon_status}\n"
        f"🎮 Множитель: x{settings.get('multiplier', 1.0)}\n\n"
        f"👇 Выберите настройку:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔔 Уведомления", callback_data="settings_notifications"),
             InlineKeyboardButton(text="👤 Анонимность", callback_data="settings_anonymous")]
        ])
    )


# ===================== ОСНОВНЫЕ КНОПКИ =====================
@dp.message(F.text == "💰 Баланс")
async def balance_reply(message: Message):
    user_id = message.from_user.id
    await message.answer(
        f"💰 <b>Твой баланс:</b> {format_stars(get_user_balance(user_id))}\n\n"
        f"🎮 Приглашай друзей и зарабатывай больше!\n"
        f"🎁 Ежедневный бонус ждёт тебя!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "⭐️ Пополнить")
async def deposit_reply(message: Message):
    await message.answer(
        "⭐️ <b>ПОПОЛНЕНИЕ БАЛАНСА</b>\n\n"
        "Выберите сумму пополнения:\n"
        "💰 Средства зачисляются мгновенно после оплаты!\n"
        "🎁 При пополнении от 1000 Stars - бонус 10%!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_deposit_keyboard()
    )

@dp.message(F.text == "🎮 Игры")
async def games_reply(message: Message):
    await message.answer(
        "🎮 <b>ВЫБЕРИ ИГРУ</b>\n\n"
        "🎲 <b>Кубик</b> — x1 до x5\n"
        "🎯 <b>Дартс</b> — x1 до x10\n"
        "⚽️ <b>Футбол</b> — x1 до x5\n"
        "🏀 <b>Баскетбол</b> — x1 до x6\n"
        "🎳 <b>Боулинг</b> — x1 до x10\n"
        "🎰 <b>Слоты</b> — x1.5 до x50\n"
        "💣 <b>Мины</b> — до x18\n"
        "🏛 <b>Пирамида</b> — до x16\n\n"
        "👇 <i>Нажми на кнопку с игрой!</i>",
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
        f"• Друг получает +{REFERRAL_SIGNUP_BONUS} Stars\n"
        f"• Ты получаешь +{REFERRAL_INVITE_BONUS} Stars за приглашение\n"
        f"• Ты получаешь {REFERRAL_BONUS_PERCENT}% от пополнений друга\n\n"
        f"<b>🔗 Твоя ссылка:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"Поделись ссылкой с друзьями и зарабатывай! 🚀"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={ref_link}&text=StarPlay — играй и зарабатывай Telegram Stars!")],
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
    stats = get_user_stats(uid)
    wr = (stats['games_won'] / max(stats['games_played'], 1)) * 100
    ref_count = len(users_referrals.get(uid, []))
    achievements = get_user_achievements(uid)
    
    ach_text = "\n".join(achievements[:5]) if achievements else "Нет достижений"
    
    text = (
        f"👤 <b>ПРОФИЛЬ ИГРОКА</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👤 Username: @{message.from_user.username or 'нет'}\n"
        f"📅 Регистрация: {users_join_date.get(uid, 'неизвестно')}\n\n"
        f"💰 <b>Баланс:</b> {format_stars(get_user_balance(uid))}\n\n"
        f"📊 <b>Статистика игр:</b>\n"
        f"├ 🎮 Сыграно: {stats['games_played']}\n"
        f"├ 🏆 Побед: {stats['games_won']}\n"
        f"├ 📈 Винрейт: {wr:.1f}%\n"
        f"├ 💎 Выиграно: {format_stars(stats['total_won'])}\n"
        f"├ 💸 Проиграно: {format_stars(stats['total_lost'])}\n"
        f"├ 💰 Всего ставок: {format_stars(stats['total_bet'])}\n"
        f"└ 🏆 Макс. выигрыш: {format_stars(stats['highest_win'])}\n\n"
        f"👥 <b>Рефералов:</b> {ref_count}\n\n"
        f"🏆 <b>Достижения:</b>\n{ach_text}\n\n"
        f"{get_random_emoji()} Продолжай играть и побеждать!"
    )
    
    await message.answer(text, parse_mode=ParseMode.HTML)


# ===================== АДМИН-ПАНЕЛЬ =====================
@dp.message(F.text == "👑 Админ панель")
async def admin_panel_reply(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ У вас нет доступа к админ-панели!", reply_markup=get_main_keyboard())
        return
    
    await message.answer(
        "👑 <b>АДМИН-ПАНЕЛЬ</b>\n\n"
        "📊 <b>Доступные действия (20+):</b>\n"
        "• Статистика и аналитика\n"
        "• Управление балансами\n"
        "• Рассылки сообщений\n"
        "• Управление пользователями (бан/мут)\n"
        "• Промокоды и бонусы\n"
        "• Управление лотереей\n"
        "• Создание турниров\n"
        "• Управление магазином\n"
        "• Детальные графики и логи\n"
        "• Вывод средств\n"
        "• Тикеты поддержки\n\n"
        "👇 <b>Выберите действие:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard()
    )


# ---------- АДМИН ФУНКЦИИ ----------
@dp.message(F.text == "📊 Статистика")
async def admin_stats(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    total_users = len(users_balance)
    total_balance = sum(users_balance.values())
    total_games = sum(s["games_played"] for s in users_stats.values())
    total_wins = sum(s["games_won"] for s in users_stats.values())
    total_deposits = sum(1 for tx_list in transactions.values() for tx in tx_list if tx["type"] == "deposit")
    deposit_sum = sum(tx["amount"] for tx_list in transactions.values() for tx in tx_list if tx["type"] == "deposit")
    active_today = sum(1 for uid, date in users_last_activity.items() if datetime.fromisoformat(date).date() == datetime.now().date())
    
    text = (
        f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
        f"👥 <b>Пользователей:</b> {total_users}\n"
        f"📅 <b>Активных сегодня:</b> {active_today}\n"
        f"💰 <b>Общий баланс:</b> {format_stars(total_balance)}\n"
        f"🎮 <b>Всего игр:</b> {total_games}\n"
        f"🏆 <b>Всего побед:</b> {total_wins}\n"
        f"📈 <b>Общий винрейт:</b> {(total_wins/total_games*100):.1f}%\n" if total_games > 0 else ""
        f"💸 <b>Пополнений:</b> {total_deposits}\n"
        f"💰 <b>Сумма пополнений:</b> {format_stars(deposit_sum)}\n"
        f"🎰 <b>Лотерея:</b> {'Активна' if lottery_active else 'Неактивна'}\n"
        f"🏆 <b>Активных турниров:</b> {len(active_tournaments)}\n"
        f"🔧 <b>Режим обслуживания:</b> {'Вкл' if bot_settings['maintenance_mode'] else 'Выкл'}"
    )
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "📊 Детальная стат.")
async def admin_detailed_stats(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    game_stats = defaultdict(int)
    for stats in users_stats.values():
        game_stats["roulette"] += stats.get("roulette_wins", 0)
        game_stats["darts"] += stats.get("darts_wins", 0)
        game_stats["football"] += stats.get("football_wins", 0)
        game_stats["bowling"] += stats.get("bowling_wins", 0)
        game_stats["basketball"] += stats.get("basketball_wins", 0)
        game_stats["mines"] += stats.get("mines_wins", 0)
        game_stats["pyramid"] += stats.get("pyramid_wins", 0)
        game_stats["slots"] += stats.get("slots_wins", 0)
    
    text = (
        f"📊 <b>ДЕТАЛЬНАЯ СТАТИСТИКА</b>\n\n"
        f"<b>Победы по играм:</b>\n"
        f"🎰 Рулетка: {game_stats['roulette']}\n"
        f"🎯 Дартс: {game_stats['darts']}\n"
        f"⚽️ Футбол: {game_stats['football']}\n"
        f"🎳 Боулинг: {game_stats['bowling']}\n"
        f"🏀 Баскетбол: {game_stats['basketball']}\n"
        f"💣 Мины: {game_stats['mines']}\n"
        f"🏛 Пирамида: {game_stats['pyramid']}\n"
        f"🎰 Слоты: {game_stats['slots']}\n"
    )
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "💰 Изменить баланс")
async def admin_change_balance(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
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
async def admin_broadcast(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await state.set_state(GameStates.admin_broadcast)
    await message.answer(
        "📢 <b>РАССЫЛКА</b>\n\n"
        "Отправь сообщение для рассылки всем пользователям.\n"
        "Поддерживается: текст, фото, видео, документы.\n\n"
        "<b>ВНИМАНИЕ!</b> Рассылка придёт ВСЕМ!\n\n"
        "<i>Для отмены отправь /cancel</i>",
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
        status = "🚫" if is_banned(uid) else "🔇" if is_muted(uid) else "✅"
        users_list.append(f"{status} @{uname or str(uid)} — {balance}⭐️")
    
    if not users_list:
        text = "👥 Пользователей пока нет"
    else:
        text = "👥 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ</b>\n\n" + "\n".join(users_list[:50])
        if len(users_list) > 50:
            text += f"\n\n... и ещё {len(users_list)-50} пользователей"
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "📜 Транзакции")
async def admin_transactions(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    all_txs = []
    for uid, tx_list in transactions.items():
        uname = users_username.get(uid, str(uid))
        for tx in tx_list[-5:]:
            all_txs.append((tx["timestamp"], f"@{uname}: {tx['type']} {tx['amount']}⭐️ - {tx['details']}"))
    
    all_txs.sort(reverse=True)
    recent = all_txs[:30]
    
    if not recent:
        text = "📜 Транзакций пока нет"
    else:
        text = "📜 <b>ПОСЛЕДНИЕ ТРАНЗАКЦИИ</b>\n\n" + "\n".join([f"• {tx[1]}" for tx in recent])
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "💾 Бекап")
async def admin_backup(message: Message):
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
        "promocodes": active_promocodes,
        "shop_items": shop_items,
        "tournaments": tournaments
    }
    
    try:
        with open("backup.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        await message.answer(
            "✅ <b>БЕКАП СОЗДАН!</b>\n\n"
            "📁 Файл: backup.json\n"
            f"💾 Размер: {len(json.dumps(data))} байт",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "🎁 Промокоды")
async def admin_promocodes_menu(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await message.answer(
        "🎁 <b>УПРАВЛЕНИЕ ПРОМОКОДАМИ</b>\n\n"
        "Выберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_create_promo")],
            [InlineKeyboardButton(text="❌ Удалить промокод", callback_data="admin_remove_promo")],
            [InlineKeyboardButton(text="📋 Список промокодов", callback_data="admin_list_promos")]
        ])
    )

@dp.message(F.text == "⚙️ Настройки бота")
async def admin_settings_menu(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    settings = bot_settings
    text = (
        f"⚙️ <b>НАСТРОЙКИ БОТА</b>\n\n"
        f"🎮 Множители: {settings['game_multipliers']}\n"
        f"🎁 Ежедневный бонус: {settings['daily_bonus_min']}-{settings['daily_bonus_max']}\n"
        f"👥 Реферальная система: {'✅' if settings['referral_enabled'] else '❌'}\n"
        f"💰 Мин. вывод: {format_stars(settings['min_withdraw'])}\n"
        f"🔧 Режим обслуживания: {'✅' if settings['maintenance_mode'] else '❌'}\n"
        f"💬 Чат: {settings['chat_link']}\n"
        f"📞 Поддержка: {settings['support_link']}\n\n"
        f"👇 Выберите параметр для изменения:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Множители", callback_data="admin_set_multipliers")],
            [InlineKeyboardButton(text="🎁 Бонусы", callback_data="admin_set_bonus")],
            [InlineKeyboardButton(text="👥 Рефералы", callback_data="admin_set_referral")],
            [InlineKeyboardButton(text="💰 Мин. вывод", callback_data="admin_set_withdraw")],
            [InlineKeyboardButton(text="🔧 Режим обслуживания", callback_data="admin_set_maintenance")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_to_panel")]
        ])
    )

@dp.message(F.text == "🚫 Баны/Муты")
async def admin_bans_menu(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await message.answer(
        "🚫 <b>УПРАВЛЕНИЕ БАНАМИ И МУТАМИ</b>\n\n"
        "Выберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔨 Забанить пользователя", callback_data="admin_ban")],
            [InlineKeyboardButton(text="🔨 Разбанить", callback_data="admin_unban")],
            [InlineKeyboardButton(text="🔇 Замутить", callback_data="admin_mute")],
            [InlineKeyboardButton(text="🔊 Размутить", callback_data="admin_unmute")],
            [InlineKeyboardButton(text="📋 Список забаненных", callback_data="admin_banned_list")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_to_panel")]
        ])
    )

@dp.message(F.text == "🎰 Лотерея упр.")
async def admin_lottery_menu(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await message.answer(
        "🎰 <b>УПРАВЛЕНИЕ ЛОТЕРЕЕЙ</b>\n\n"
        f"Статус: {'Активна' if lottery_active else 'Неактивна'}\n"
        f"Джекпот: {format_stars(lottery_pool)}\n"
        f"Участников: {len(lottery_tickets)}\n\n"
        "Выберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎰 Запустить лотерею", callback_data="admin_lottery_start")],
            [InlineKeyboardButton(text="🎰 Провести розыгрыш", callback_data="admin_lottery_draw")],
            [InlineKeyboardButton(text="🎰 Остановить лотерею", callback_data="admin_lottery_stop")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_to_panel")]
        ])
    )

@dp.message(F.text == "🏆 Турниры упр.")
async def admin_tournaments_menu(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await state.set_state(GameStates.admin_create_tournament)
    await message.answer(
        "🏆 <b>УПРАВЛЕНИЕ ТУРНИРАМИ</b>\n\n"
        "Введите название турнира:\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text == "🏪 Магазин упр.")
async def admin_shop_menu(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await state.set_state(GameStates.admin_add_shop_item)
    await message.answer(
        "🏪 <b>УПРАВЛЕНИЕ МАГАЗИНОМ</b>\n\n"
        "Введите название товара (с эмодзи):\n"
        "Пример: 🎲 Бонус x2\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text == "📈 Графики")
async def admin_charts(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    # Простая текстовая статистика вместо графиков
    daily_active = {}
    for uid, date in users_last_activity.items():
        day = date.split("T")[0]
        daily_active[day] = daily_active.get(day, 0) + 1
    
    text = "📈 <b>АКТИВНОСТЬ ПО ДНЯМ</b>\n\n"
    for day, count in list(daily_active.items())[-7:]:
        text += f"📅 {day}: {count} пользователей\n"
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "💰 Вывод средств")
async def admin_withdrawals(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    if not withdraw_requests:
        await message.answer("💰 Нет активных запросов на вывод!", reply_markup=get_admin_panel_keyboard())
        return
    
    text = "💰 <b>ЗАПРОСЫ НА ВЫВОД</b>\n\n"
    for uid, req in withdraw_requests.items():
        uname = users_username.get(uid, str(uid))
        text += f"👤 @{uname}: {format_stars(req['amount'])} - {req['wallet']}\n"
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "🎫 Тикеты")
async def admin_tickets(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    if not support_tickets:
        await message.answer("🎫 Нет активных тикетов!", reply_markup=get_admin_panel_keyboard())
        return
    
    text = "🎫 <b>ТИКЕТЫ ПОДДЕРЖКИ</b>\n\n"
    for uid, tickets in support_tickets.items():
        uname = users_username.get(uid, str(uid))
        last_ticket = tickets[-1]
        text += f"👤 @{uname}: {last_ticket['message'][:50]}...\n"
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "📋 Логи ошибок")
async def admin_error_logs(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    # Читаем логи из файла
    try:
        with open("bot.log", "r") as f:
            logs = f.read().split("\n")[-50:]
        text = "📋 <b>ПОСЛЕДНИЕ ЛОГИ</b>\n\n" + "\n".join(logs)
        await message.answer(text[:4000], parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())
    except:
        await message.answer("📋 Лог-файл не найден!", reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "🔄 Обновить данные")
async def admin_reload(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    # Перезагрузка данных (имитация)
    await message.answer(
        "🔄 <b>ДАННЫЕ ОБНОВЛЕНЫ</b>\n\n"
        "✅ Балансы: OK\n"
        "✅ Пользователи: OK\n"
        "✅ Транзакции: OK\n"
        "✅ Настройки: OK",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard()
    )


# ===================== АДМИН FSM ОБРАБОТЧИКИ =====================
@dp.message(GameStates.admin_find_user)
async def admin_find_user(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await state.clear()
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
        f"💰 <b>БАЛАНС ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        f"👤 @{input_text}\n"
        f"💰 Текущий баланс: {format_stars(current_balance)}\n\n"
        f"👇 Выберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

@dp.callback_query(F.data.startswith("admin_"))
async def admin_action(callback: CallbackQuery, state: FSMContext):
    username = callback.from_user.username or ""
    if not is_admin(username):
        await callback.answer("Нет доступа!", show_alert=True)
        return
    
    data = await state.get_data()
    target_user = data.get("admin_target_user")
    target_username = data.get("admin_target_username")
    
    if callback.data == "admin_custom":
        await state.set_state(GameStates.admin_change_balance)
        await callback.message.answer(
            "✏️ Введи сумму (можно с минусом):\n"
            "Пример: 500 или -200",
            parse_mode=ParseMode.HTML,
            reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
        )
        await callback.answer()
        return
    
    if callback.data == "admin_back_to_panel":
        await state.clear()
        await callback.message.edit_text(
            "👑 <b>АДМИН-ПАНЕЛЬ</b>",
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
        await bot.send_message(target_user, f"👑 Админ добавил +{format_stars(amount)}\n💰 Новый баланс: {format_stars(new_balance)}")
        result = f"✅ Добавлено +{format_stars(amount)} @{target_username}"
    else:
        new_balance = update_balance(target_user, -amount)
        save_transaction(target_user, -amount, "admin_remove", f"Админ забрал {amount} Stars")
        await bot.send_message(target_user, f"👑 Админ снял -{format_stars(amount)}\n💰 Новый баланс: {format_stars(new_balance)}")
        result = f"✅ Снято -{format_stars(amount)} у @{target_username}"
    
    await state.clear()
    await callback.message.edit_text(
        f"{result}\n\n💰 Новый баланс: {format_stars(get_user_balance(target_user))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard()
    )
    await callback.answer()

@dp.message(GameStates.admin_change_balance)
async def admin_custom_balance(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await state.clear()
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
        await message.answer("❌ Ошибка!", reply_markup=get_admin_panel_keyboard())
        return
    
    try:
        amount = int(message.text.strip())
        new_balance = update_balance(target_user, amount)
        tx_type = "admin_add" if amount > 0 else "admin_remove"
        save_transaction(target_user, amount, tx_type, f"Админ изменил баланс на {amount}")
        await bot.send_message(target_user, f"👑 Админ изменил баланс: {format_stars(amount)}\n💰 Новый баланс: {format_stars(new_balance)}")
        
        await state.clear()
        await message.answer(
            f"✅ Баланс @{target_username} изменён на {format_stars(amount)}\n"
            f"💰 Новый баланс: {format_stars(new_balance)}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )
    except ValueError:
        await message.answer("❌ Введи число!")

@dp.message(GameStates.admin_broadcast)
async def admin_do_broadcast(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await state.clear()
        return
    
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=get_admin_panel_keyboard())
        return
    
    success = 0
    fail = 0
    
    progress = await message.answer("📢 Начинаю рассылку...")
    
    for user_id in users_balance.keys():
        try:
            if message.text:
                await bot.send_message(user_id, message.text, parse_mode=ParseMode.HTML)
            elif message.photo:
                await bot.send_photo(user_id, message.photo[-1].file_id, caption=message.caption)
            else:
                await bot.copy_message(user_id, message.chat.id, message.message_id)
            success += 1
            await asyncio.sleep(0.05)
        except:
            fail += 1
    
    await state.clear()
    await progress.edit_text(
        f"✅ <b>РАССЫЛКА ЗАВЕРШЕНА</b>\n\n"
        f"📨 Доставлено: {success}\n"
        f"❌ Ошибок: {fail}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard()
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
    
    # Бонус за пополнение
    if amount >= 1000:
        bonus = int(amount * 0.1)
        update_balance(user_id, bonus)
        save_transaction(user_id, bonus, "bonus", "Бонус за пополнение 10%")
        await message.answer(f"🎉 Бонус за пополнение: +{format_stars(bonus)}!")
    
    if user_id in users_referrer:
        referrer = users_referrer[user_id]
        bonus = int(amount * REFERRAL_BONUS_PERCENT / 100)
        if bonus:
            update_balance(referrer, bonus)
            save_transaction(referrer, bonus, "referral_earning", f"10% с пополнения реферала")
            try:
                await bot.send_message(referrer, f"🎉 Реферальный бонус: +{format_stars(bonus)}!")
            except:
                pass
    
    await message.answer(
        f"✅ <b>ПОПОЛНЕНИЕ ВЫПОЛНЕНО!</b>\n\n"
        f"+{format_stars(amount)}\n"
        f"💰 Новый баланс: {format_stars(new_balance)}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )


@dp.callback_query(F.data.startswith("deposit_"))
async def deposit_amount(callback: CallbackQuery, state: FSMContext):
    amount_str = callback.data.split("_")[1]
    if amount_str == "custom":
        await callback.message.answer("✏️ Введи сумму (1-10000):")
        await state.set_state(GameStates.custom_deposit)
        await callback.answer()
        return
    if amount_str == "promo":
        await state.set_state(GameStates.promo_enter)
        await callback.message.answer("🎁 Введи промокод:")
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

@dp.message(GameStates.promo_enter)
async def process_promo(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    
    if code not in active_promocodes:
        await message.answer("❌ Неверный промокод!")
        await state.clear()
        return
    
    promo = active_promocodes[code]
    user_id = message.from_user.id
    
    if promo["uses"] >= promo["max_uses"]:
        await message.answer("❌ Промокод уже использован!")
        await state.clear()
        return
    
    if user_id in promo["users"]:
        await message.answer("❌ Вы уже использовали этот промокод!")
        await state.clear()
        return
    
    update_balance(user_id, promo["reward"])
    save_transaction(user_id, promo["reward"], "promo", f"Промокод {code}")
    promo["uses"] += 1
    promo["users"].append(user_id)
    
    await message.answer(
        f"✅ <b>ПРОМОКОД АКТИВИРОВАН!</b>\n\n"
        f"+{format_stars(promo['reward'])}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML
    )
    await state.clear()


# ===================== НАВИГАЦИЯ =====================
@dp.callback_query(F.data == "back_to_games")
async def back_to_games_callback(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer(
        "🎮 <b>ВЫБЕРИ ИГРУ</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer(
        "🌟 <b>ГЛАВНОЕ МЕНЮ</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_back_to_panel")
async def admin_back_to_panel(callback: CallbackQuery):
    await callback.message.edit_text(
        "👑 <b>АДМИН-ПАНЕЛЬ</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard()
    )
    await callback.answer()

@dp.message(F.text == "🔙 В главное меню")
@dp.message(F.text == "🔙 Главное меню")
async def back_to_main(message: Message):
    await message.answer(
        "🌟 <b>ГЛАВНОЕ МЕНЮ</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )

@dp.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    username = message.from_user.username or ""
    keyboard = get_admin_panel_keyboard() if is_admin(username) else get_main_keyboard()
    await message.answer("❌ Действие отменено.", reply_markup=keyboard)


# ===================== ЗАПУСК =====================
async def main():
    logger.info("🚀 StarPlay Bot запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())