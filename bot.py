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
users_ban: Dict[int, bool] = {}
users_warns: Dict[int, int] = {}
admin_logs: List[dict] = []
bonus_claimed: Dict[int, Dict[str, bool]] = {}

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
    dice_game = State()
    mines_game = State()
    pyramid_game = State()
    admin_warn_user = State()
    admin_broadcast_confirm = State()
    admin_set_bonus = State()
    admin_edit_stats = State()


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
            "mines_wins": 0, "pyramid_wins": 0
        }
    return users_stats[user_id]

def update_balance(user_id: int, delta: int) -> int:
    if users_ban.get(user_id, False):
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
    admin_logs.append({
        "user_id": user_id, "username": users_username.get(user_id, str(user_id)),
        "amount": amount, "type": tx_type, "details": details,
        "timestamp": datetime.now().isoformat()
    })

def format_stars(amount: int) -> str:
    return f"⭐️ {amount} Stars"

def get_random_emoji() -> str:
    return random.choice(["🎲","🎯","⚡️","💫","🌟","⭐️","✨","🎮","🎰","🔥"])


# ===================== ПРАВИЛА ИГР (DICE) =====================
DICE_RULES = {
    "🎲": {
        "name": "Кубик", "emoji": "🎲",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 3, 6: 5},
        "messages": {1: "😭 Выпала единица!", 2: "😢 Двойка...", 3: "🤔 Тройка", 4: "😊 Четвёрка!", 5: "😎 Пятёрка!", 6: "🤯 ШЕСТЁРКА! 🔥"}
    },
    "🎯": {
        "name": "Дартс", "emoji": "🎯",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 4, 6: 10},
        "messages": {1: "💀 Мимо!", 2: "😢 Промах!", 3: "🎯 Попадание в 20!", 4: "🎯 Тройное 20!", 5: "🎯 Яблочко!", 6: "🤯 БЫЧИЙ ГЛАЗ! 🔥"}
    },
    "⚽️": {
        "name": "Футбол", "emoji": "⚽️",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 3, 6: 5},
        "messages": {1: "🧤 Сейв вратаря!", 2: "😢 Штанга!", 3: "⚽️ ГОЛ!", 4: "⚽️ Красивый гол!", 5: "⚽️ Шедевр!", 6: "🤯 ПАНЕНКА! 🔥"}
    },
    "🏀": {
        "name": "Баскетбол", "emoji": "🏀",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 4, 6: 6},
        "messages": {1: "💀 Промах!", 2: "😢 Кольцо выплюнуло!", 3: "🏀 Попадание!", 4: "🏀 Сверху!", 5: "🏀 Трёхочковый!", 6: "🤯 БАЗЗЕР БИТЕР! 🔥"}
    },
    "🎳": {
        "name": "Боулинг", "emoji": "🎳",
        "multipliers": {1: 0, 2: 0, 3: 1, 4: 2, 5: 5, 6: 10},
        "messages": {1: "😭 Страйк-аут!", 2: "😢 Осталась кегля!", 3: "🎳 Спэр!", 4: "🎳 Страйк!", 5: "🎳 Идеальный!", 6: "🤯 ДЕСЯТЬ СТРАЙКОВ! 🔥"}
    }
}

# Слоты
SLOT_SYMBOLS = ["🍒", "🍊", "🍋", "💎", "7️⃣", "🎰", "⭐️", "💫"]
SLOT_PAYOUTS = {
    ("🍒", "🍒", "🍒"): 5, ("🍊", "🍊", "🍊"): 7, ("🍋", "🍋", "🍋"): 10,
    ("💎", "💎", "💎"): 15, ("7️⃣", "7️⃣", "7️⃣"): 25, ("🎰", "🎰", "🎰"): 50,
    ("⭐️", "⭐️", "⭐️"): 30, ("💫", "💫", "💫"): 20
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
    builder.button(text="📊 Статистика")
    builder.button(text="💰 Изменить баланс")
    builder.button(text="📢 Рассылка")
    builder.button(text="👥 Список пользователей")
    builder.button(text="📜 Логи")
    builder.button(text="💾 Сохранить")
    builder.button(text="🔨 Баны")
    builder.button(text="⚠️ Предупреждения")
    builder.button(text="🎁 Бонусы")
    builder.button(text="📈 Транзакции")
    builder.button(text="⚙️ Настройки")
    builder.button(text="🔙 Главное меню")
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
         InlineKeyboardButton(text="⭐️ 1000", callback_data=f"{game_key}_bet_1000")],
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

def get_slots_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 5⭐️", callback_data="slots_spin_5"),
         InlineKeyboardButton(text="🎰 10⭐️", callback_data="slots_spin_10"),
         InlineKeyboardButton(text="🎰 25⭐️", callback_data="slots_spin_25")],
        [InlineKeyboardButton(text="🎰 50⭐️", callback_data="slots_spin_50"),
         InlineKeyboardButton(text="🎰 100⭐️", callback_data="slots_spin_100"),
         InlineKeyboardButton(text="🎰 250⭐️", callback_data="slots_spin_250")],
        [InlineKeyboardButton(text="🎰 500⭐️", callback_data="slots_spin_500"),
         InlineKeyboardButton(text="🎰 1000⭐️", callback_data="slots_spin_1000")],
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


# ===================== ОСНОВНЫЕ КОМАНДЫ =====================
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    
    users_username[user_id] = username
    
    if user_id not in users_join_date:
        users_join_date[user_id] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
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
                    await message.answer(f"✅ Вы получили {format_stars(REFERRAL_SIGNUP_BONUS)} по реферальной ссылке!")
            except:
                pass
    
    welcome_text = (
        f"🌟 <b>Добро пожаловать в StarPlay!</b> 🌟\n\n"
        f"{get_random_emoji()} <b>Играй на Telegram Stars и выигрывай!</b>\n\n"
        f"<b>🎲 Доступные игры:</b>\n"
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
    if users_ban.get(user_id, False):
        await message.answer("❌ Ваш аккаунт заблокирован!")
        return
    await message.answer(
        f"💰 <b>Твой баланс:</b> {format_stars(get_user_balance(user_id))}\n\n"
        f"🎮 Приглашай друзей и зарабатывай больше!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "⭐️ Пополнить")
async def deposit_reply(message: Message):
    if users_ban.get(message.from_user.id, False):
        await message.answer("❌ Ваш аккаунт заблокирован!")
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
        await message.answer("❌ Ваш аккаунт заблокирован!")
        return
    await message.answer(
        "🎮 <b>Выбери игру</b>\n\n"
        "👇 <i>Нажми на кнопку с игрой!</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )

@dp.message(F.text == "👥 Рефералы")
async def referrals_reply(message: Message):
    user_id = message.from_user.id
    if users_ban.get(user_id, False):
        await message.answer("❌ Ваш аккаунт заблокирован!")
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
    if users_ban.get(uid, False):
        await message.answer("❌ Ваш аккаунт заблокирован!")
        return
    
    stats = get_user_stats(uid)
    wr = (stats['games_won'] / max(stats['games_played'], 1)) * 100
    ref_count = len(users_referrals.get(uid, []))
    warns = users_warns.get(uid, 0)
    
    text = (
        f"👤 <b>Профиль игрока</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👤 Username: @{message.from_user.username or 'нет'}\n"
        f"📅 Регистрация: {users_join_date.get(uid, 'неизвестно')}\n"
        f"⚠️ Предупреждения: {warns}\n\n"
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
        await message.answer("❌ Ваш аккаунт заблокирован!")
        return
    
    today = datetime.now().date().isoformat()
    if users_daily_bonus.get(user_id) == today:
        await message.answer(
            f"🎁 <b>Ты уже получил сегодняшний бонус!</b>\n\nВозвращайся завтра!",
            parse_mode=ParseMode.HTML
        )
        return
    bonus_amount = random.randint(5, 15)
    update_balance(user_id, bonus_amount)
    users_daily_bonus[user_id] = today
    save_transaction(user_id, bonus_amount, "daily_bonus", "Ежедневный бонус")
    await message.answer(
        f"🎉 <b>Ежедневный бонус получен!</b> 🎉\n\n"
        f"+{format_stars(bonus_amount)}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML
    )


# ===================== DICE ИГРЫ (ЧЕРЕЗ sendDice) =====================
async def play_dice_game(message: Message, game_key: str, bet: int, state: FSMContext):
    user_id = message.from_user.id
    if get_user_balance(user_id) < bet:
        await message.answer(f"❌ Не хватает {format_stars(bet)}")
        return
    
    game = DICE_RULES[game_key]
    await state.update_data(dice_game_data={"game": game_key, "bet": bet})
    
    await message.answer(
        f"{game['emoji']} <b>{game['name']}</b>\n\n"
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
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        await state.clear()
        return
    
    update_balance(user_id, -bet)
    
    # Отправляем dice через sendDice
    dice_message = await callback.message.answer_dice(emoji=game_key)
    dice_value = dice_message.dice.value
    
    game = DICE_RULES[game_key]
    multiplier = game["multipliers"].get(dice_value, 0)
    result_msg = game["messages"].get(dice_value, "")
    
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
        elif game_key == "⚽️":
            stats["football_wins"] += 1
        elif game_key == "🏀":
            stats["basketball_wins"] += 1
        elif game_key == "🎳":
            stats["bowling_wins"] += 1
            
        stats["total_won"] += win_amount
        save_transaction(user_id, win_amount, "game_win", f"{game['name']} x{multiplier}")
        
        result_text = f"🎉 <b>ВЫИГРЫШ!</b>\n✨ Множитель: <b>x{multiplier}</b>\n🏆 Выигрыш: <b>+{format_stars(win_amount)}</b>"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", game['name'])
        result_text = f"😢 <b>Проигрыш</b>\n-{format_stars(bet)}"
    
    await callback.message.answer(
        f"{game['emoji']} <b>{game['name']}</b>\n\n"
        f"🎲 <b>Результат: {dice_value}</b>\n"
        f"{result_msg}\n\n"
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
async def cube_start(message: Message, state: FSMContext):
    await message.answer(
        "🎲 <b>Игра КУБИК</b>\n\n"
        "📋 <b>Правила:</b>\n"
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
async def darts_start(message: Message, state: FSMContext):
    await message.answer(
        "🎯 <b>Игра ДАРТС</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• 1-2 → мимо\n• 3 → x1\n• 4 → x2\n• 5 → x4\n• 6 → x10\n\n"
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
async def football_start(message: Message, state: FSMContext):
    await message.answer(
        "⚽️ <b>Игра ФУТБОЛ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• 1-2 → сейв\n• 3 → x1\n• 4 → x2\n• 5 → x3\n• 6 → x5\n\n"
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
async def basketball_start(message: Message, state: FSMContext):
    await message.answer(
        "🏀 <b>Игра БАСКЕТБОЛ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• 1-2 → промах\n• 3 → x1\n• 4 → x2\n• 5 → x4\n• 6 → x6\n\n"
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
async def bowling_start(message: Message, state: FSMContext):
    await message.answer(
        "🎳 <b>Игра БОУЛИНГ</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• 1-2 → страйк-аут\n• 3 → x1\n• 4 → x2\n• 5 → x5\n• 6 → x10\n\n"
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
        "• 3 одинаковых → x5-x50\n"
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
        stats["slot_wins"] += 1
        stats["total_won"] += win
        save_transaction(user_id, win, "game_win", f"Слоты x{mult}")
        res = f"🎉 <b>ДЖЕКПОТ!</b> x{mult}\n+{format_stars(win)}"
    elif reel1 == reel2 or reel1 == reel3 or reel2 == reel3:
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
        "• 💎 → x1.2\n• 💣 → проигрыш\n"
        "• Макс. множитель: x18\n\n"
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
        "board": board, "revealed": [[False] * 5 for _ in range(5)],
        "bet": bet, "multiplier": 1.0, "cells_opened": 0
    }
    
    await callback.message.edit_text(
        f"💣 <b>МИНЫ</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"✨ Множитель: x{active_mines_games[user_id]['multiplier']:.1f}\n"
        f"📦 Открыто: 0/20\n\n"
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
        
        await callback.message.edit_text(
            f"💣 <b>МИНЫ</b>\n\n"
            f"💰 Ставка: {format_stars(game['bet'])}\n"
            f"✨ Множитель: x{game['multiplier']:.1f}\n"
            f"💎 Найдено: {game['cells_opened']}/20\n"
            f"💰 Текущий выигрыш: {format_stars(int(game['bet'] * game['multiplier']))}\n\n"
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
        f"💰 <b>Ты забрал выигрыш!</b> 💰\n\n"
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
        "5 уровней, шаг удваивает выигрыш (50% успеха).\n"
        "Проигрыш = потеря ставки. Максимум x16!\n\n"
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
            save_transaction(user_id, game["current"], "game_win", f"Пирамида победа x{game['current']//game['bet']}")
            del active_pyramids[user_id]
            
            await callback.message.edit_text(
                f"🏛 <b>ПИРАМИДА - ПОБЕДА!</b>\n\n"
                f"🎉 <b>Ты покорил вершину!</b> 🎉\n\n"
                f"💰 Выигрыш: {format_stars(game['current'])}\n"
                f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_games_keyboard()
            )
        else:
            await callback.message.edit_text(
                f"🏛 <b>ПИРАМИДА</b>\n\n"
                f"✅ <b>УСПЕХ! Уровень {game['level']}</b>\n\n"
                f"💰 Текущий выигрыш: {format_stars(game['current'])}\n"
                f"🎯 Следующий: {format_stars(game['current'] * 2)}\n\n"
                f"👇 <b>Продолжим?</b>",
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
            f"💔 <b>Ты рухнул!</b>\n\n"
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
    save_transaction(user_id, win, "game_win", f"Пирамида кэшаут x{win//game['bet']}")
    del active_pyramids[user_id]
    
    await callback.message.edit_text(
        f"🏛 <b>ПИРАМИДА</b>\n\n"
        f"💰 <b>Ты забрал {format_stars(win)}!</b>\n\n"
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
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    await message.answer(
        "👑 <b>Панель администратора</b>\n\n"
        "📊 Статистика | 💰 Изменить баланс | 📢 Рассылка\n"
        "👥 Список пользователей | 📜 Логи | 💾 Сохранить\n"
        "🔨 Баны | ⚠️ Предупреждения | 🎁 Бонусы\n"
        "📈 Транзакции | ⚙️ Настройки\n\n"
        "👇 <b>Выберите действие:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard()
    )

@dp.message(F.text == "📊 Статистика")
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
    banned = sum(1 for b in users_ban.values() if b)
    
    text = (
        f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
        f"👥 <b>Пользователей:</b> {total_users}\n"
        f"🔨 <b>Заблокировано:</b> {banned}\n"
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

@dp.message(F.text == "💰 Изменить баланс")
async def admin_change_balance_reply(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_find_user)
    await message.answer(
        "💰 <b>ИЗМЕНЕНИЕ БАЛАНСА</b>\n\n"
        "Введи username (без @) или ID:\n"
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
        banned = "🔨" if users_ban.get(uid, False) else ""
        users_list.append(f"{banned} @{uname or str(uid)} — {balance}⭐️")
    
    if not users_list:
        text = "👥 Пользователей пока нет"
    else:
        text = "👥 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ</b>\n\n" + "\n".join(users_list[:50])
        if len(users_list) > 50:
            text += f"\n\n... и ещё {len(users_list)-50} пользователей"
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "📜 Логи")
async def admin_logs(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    recent = admin_logs[-30:]
    if not recent:
        text = "📜 Логов пока нет"
    else:
        text = "📜 <b>ПОСЛЕДНИЕ ДЕЙСТВИЯ</b>\n\n"
        for log in recent:
            text += f"• @{log['username']}: {log['type']} {log['amount']}⭐️ - {log['details']}\n"
    
    await message.answer(text[:4000], parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "💾 Сохранить")
async def admin_save(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    data = {
        "balance": users_balance, "referrer": users_referrer,
        "referrals": users_referrals, "stats": users_stats,
        "transactions": transactions, "username": users_username,
        "join_date": users_join_date, "ban": users_ban, "warns": users_warns
    }
    
    try:
        with open("backup.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        await message.answer(
            "✅ <b>Данные сохранены!</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "🔨 Баны")
async def admin_ban_menu(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_find_user)
    await message.answer(
        "🔨 <b>БАН/РАЗБАН</b>\n\n"
        "Введи username (без @) или ID:\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )
    await state.update_data(admin_action="ban")

@dp.message(F.text == "⚠️ Предупреждения")
async def admin_warn_menu(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_find_user)
    await message.answer(
        "⚠️ <b>ПРЕДУПРЕЖДЕНИЯ</b>\n\n"
        "Введи username (без @) или ID:\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )
    await state.update_data(admin_action="warn")

@dp.message(F.text == "🎁 Бонусы")
async def admin_bonus_menu(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    await state.set_state(GameStates.admin_find_user)
    await message.answer(
        "🎁 <b>ВЫДАЧА БОНУСА</b>\n\n"
        "Введи username (без @) или ID:\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )
    await state.update_data(admin_action="bonus")

@dp.message(F.text == "📈 Транзакции")
async def admin_transactions(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    total_deposits = sum(1 for tx_list in transactions.values() for tx in tx_list if tx["type"] == "deposit")
    total_withdraws = sum(1 for tx_list in transactions.values() for tx in tx_list if tx["type"] == "withdraw")
    deposit_sum = sum(tx["amount"] for tx_list in transactions.values() for tx in tx_list if tx["type"] == "deposit")
    withdraw_sum = sum(abs(tx["amount"]) for tx_list in transactions.values() for tx in tx_list if tx["type"] == "withdraw")
    
    text = (
        f"📈 <b>СТАТИСТИКА ТРАНЗАКЦИЙ</b>\n\n"
        f"💸 <b>Пополнений:</b> {total_deposits}\n"
        f"💸 <b>Сумма пополнений:</b> {format_stars(deposit_sum)}\n"
        f"💸 <b>Выводов:</b> {total_withdraws}\n"
        f"💸 <b>Сумма выводов:</b> {format_stars(withdraw_sum)}\n"
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "⚙️ Настройки")
async def admin_settings(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ Нет доступа!", reply_markup=get_main_keyboard())
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Сбросить статистику", callback_data="admin_reset_stats")],
        [InlineKeyboardButton(text="🗑 Очистить логи", callback_data="admin_clear_logs")],
        [InlineKeyboardButton(text="📁 Бэкап", callback_data="admin_backup")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ])
    await message.answer("⚙️ <b>НАСТРОЙКИ</b>\n\nВыберите действие:", parse_mode=ParseMode.HTML, reply_markup=keyboard)

@dp.message(F.text == "🔙 Главное меню")
async def back_to_main(message: Message):
    await message.answer("🌟 <b>Главное меню</b>", parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard())


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
    
    data = await state.get_data()
    action = data.get("admin_action", "balance")
    
    if action == "ban":
        new_status = not users_ban.get(user_id, False)
        users_ban[user_id] = new_status
        status_text = "забанен" if new_status else "разбанен"
        await message.answer(f"✅ Пользователь @{input_text} {status_text}!", reply_markup=get_admin_panel_keyboard())
        await bot.send_message(user_id, f"👑 Администратор {status_text} ваш аккаунт!")
    elif action == "warn":
        current_warns = users_warns.get(user_id, 0) + 1
        users_warns[user_id] = current_warns
        await message.answer(f"⚠️ Пользователь @{input_text} получил предупреждение! Всего: {current_warns}/3", reply_markup=get_admin_panel_keyboard())
        await bot.send_message(user_id, f"⚠️ Вы получили предупреждение! Всего: {current_warns}/3")
        if current_warns >= 3:
            users_ban[user_id] = True
            await bot.send_message(user_id, "🔨 Вы забанены за 3 предупреждения!")
    elif action == "bonus":
        await state.update_data(admin_target_user=user_id, admin_target_username=input_text)
        await state.set_state(GameStates.admin_set_bonus)
        await message.answer(
            f"🎁 Введи сумму бонуса для @{input_text}:\n"
            "Пример: <code>100</code>",
            parse_mode=ParseMode.HTML
        )
        return
    else:
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
             InlineKeyboardButton(text="✏️ Своя сумма", callback_data="admin_custom")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
        ])
        await message.answer(
            f"💰 <b>Баланс @{input_text}:</b> {format_stars(current_balance)}\n\n"
            f"Выберите действие:",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
        return
    
    await state.clear()

@dp.message(GameStates.admin_set_bonus)
async def admin_set_bonus(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await state.clear()
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
        if amount <= 0:
            raise ValueError
        update_balance(target_user, amount)
        save_transaction(target_user, amount, "admin_bonus", f"Админ выдал бонус {amount}")
        await bot.send_message(target_user, f"🎁 Администратор выдал вам бонус +{format_stars(amount)}!")
        await message.answer(f"✅ Бонус {format_stars(amount)} выдан @{target_username}!", reply_markup=get_admin_panel_keyboard())
    except:
        await message.answer("❌ Введи корректную сумму!")
    
    await state.clear()

@dp.message(GameStates.admin_change_balance)
async def admin_custom_balance(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await state.clear()
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
        await bot.send_message(target_user, f"👑 Администратор изменил баланс на {'+' if amount > 0 else ''}{format_stars(amount)}!")
        await message.answer(f"✅ Баланс @{target_username} изменён на {format_stars(amount)}!\n💰 Новый баланс: {format_stars(new_balance)}", reply_markup=get_admin_panel_keyboard())
    except:
        await message.answer("❌ Введи число!")
    await state.clear()

@dp.message(GameStates.admin_send_message)
async def admin_broadcast_handler(message: Message, state: FSMContext):
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


# ===================== CALLBACK ОБРАБОТЧИКИ =====================
@dp.callback_query(F.data.startswith("admin_"))
async def admin_callback(callback: CallbackQuery, state: FSMContext):
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
            "Пример: <code>500</code> или <code>-200</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
        )
        await callback.answer()
        return
    
    if callback.data == "admin_back":
        await state.clear()
        await callback.message.edit_text(
            "👑 <b>Панель администратора</b>\n\nВыберите действие:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )
        await callback.answer()
        return
    
    parts = callback.data.split("_")
    if len(parts) >= 3:
        action = parts[1]
        amount = int(parts[2])
        
        if action == "add":
            new_balance = update_balance(target_user, amount)
            save_transaction(target_user, amount, "admin_add", f"Админ добавил {amount}")
            await bot.send_message(target_user, f"👑 Администратор добавил +{format_stars(amount)}!")
            await callback.message.edit_text(f"✅ Добавлено +{format_stars(amount)} @{target_username}\n💰 Новый баланс: {format_stars(new_balance)}", reply_markup=get_admin_panel_keyboard())
        else:
            new_balance = update_balance(target_user, -amount)
            save_transaction(target_user, -amount, "admin_remove", f"Админ снял {amount}")
            await bot.send_message(target_user, f"👑 Администратор снял -{format_stars(amount)}!")
            await callback.message.edit_text(f"✅ Снято -{format_stars(amount)} у @{target_username}\n💰 Новый баланс: {format_stars(new_balance)}", reply_markup=get_admin_panel_keyboard())
        await state.clear()
    
    await callback.answer()

@dp.callback_query(F.data == "admin_reset_stats")
async def admin_reset_stats(callback: CallbackQuery):
    username = callback.from_user.username or ""
    if not is_admin(username):
        await callback.answer("Нет доступа!", show_alert=True)
        return
    
    for uid in users_stats:
        users_stats[uid] = {"games_played": 0, "games_won": 0, "total_won": 0, "total_lost": 0,
                            "dice_wins": 0, "darts_wins": 0, "football_wins": 0,
                            "bowling_wins": 0, "basketball_wins": 0, "slot_wins": 0,
                            "mines_wins": 0, "pyramid_wins": 0}
    await callback.message.edit_text("✅ Статистика всех пользователей сброшена!", reply_markup=get_admin_panel_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "admin_clear_logs")
async def admin_clear_logs(callback: CallbackQuery):
    username = callback.from_user.username or ""
    if not is_admin(username):
        await callback.answer("Нет доступа!", show_alert=True)
        return
    
    admin_logs.clear()
    await callback.message.edit_text("✅ Логи очищены!", reply_markup=get_admin_panel_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "admin_backup")
async def admin_backup(callback: CallbackQuery):
    username = callback.from_user.username or ""
    if not is_admin(username):
        await callback.answer("Нет доступа!", show_alert=True)
        return
    
    data = {
        "balance": users_balance, "referrer": users_referrer,
        "referrals": users_referrals, "stats": users_stats,
        "transactions": transactions, "username": users_username,
        "join_date": users_join_date, "ban": users_ban, "warns": users_warns
    }
    
    with open("backup.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    await callback.message.edit_text("✅ Бэкап создан: backup.json", reply_markup=get_admin_panel_keyboard())
    await callback.answer()

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


# ===================== ПЛАТЕЖИ =====================
async def create_stars_invoice(message: Message, user_id: int, amount: int):
    title = "⭐️ Пополнение StarPlay"
    payload = f"starplay_{user_id}_{amount}_{int(datetime.now().timestamp())}"
    prices = [LabeledPrice(label="Telegram Stars", amount=amount)]
    await bot.send_invoice(
        chat_id=user_id, title=title, description=f"Пополнение на {amount} Stars",
        payload=payload, provider_token="", currency="XTR",
        prices=prices, start_parameter="starplay_deposit"
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
    save_transaction(user_id, amount, "deposit", f"Пополнение {amount}")
    
    if user_id in users_referrer:
        referrer = users_referrer[user_id]
        bonus = int(amount * REFERRAL_BONUS_PERCENT / 100)
        if bonus:
            update_balance(referrer, bonus)
            save_transaction(referrer, bonus, "referral_earning", f"10% с пополнения")
            try:
                await bot.send_message(referrer, f"🎉 Реферальный бонус! +{format_stars(bonus)}")
            except:
                pass
    
    await message.answer(
        f"✅ +{format_stars(amount)}\n💰 Новый баланс: {format_stars(new_balance)}",
        parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard()
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
    await message.answer("❌ Отменено.", reply_markup=get_main_keyboard())


# ===================== ЗАПУСК =====================
async def main():
    logger.info("🚀 StarPlay Bot запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())