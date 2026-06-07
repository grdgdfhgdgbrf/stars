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
    ReplyKeyboardMarkup, KeyboardButton
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
            "pyramid_wins": 0, "slots_wins": 0
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


# ===================== ЛОГИКА DICE ИГР =====================
DICE_MULTIPLIERS = {
    "🎯": {1: 0, 2: 0, 3: 1, 4: 2, 5: 4, 6: 10},
    "⚽️": {1: 0, 2: 0, 3: 1, 4: 2, 5: 3, 6: 5},
    "🏀": {1: 0, 2: 0, 3: 1, 4: 2, 5: 4, 6: 6},
    "🎳": {1: 0, 2: 0, 3: 1, 4: 2, 5: 5, 6: 10}
}

GAME_NAMES = {
    "darts": "🎯 Дартс", "football": "⚽️ Футбол",
    "basketball": "🏀 Баскетбол", "bowling": "🎳 Боулинг"
}


# ===================== REPLY КЛАВИАТУРЫ =====================
def get_main_keyboard(user_id: int = None) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="💰 Баланс")
    builder.button(text="⭐️ Пополнить")
    builder.button(text="🎮 Игры")
    builder.button(text="👥 Рефералы")
    builder.button(text="🏆 Топ")
    builder.button(text="📊 Профиль")
    builder.button(text="🎁 Бонус")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_admin_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="👑 Админ панель")
    builder.button(text="📊 Статистика")
    builder.button(text="📢 Рассылка")
    builder.button(text="💰 Изменить баланс")
    builder.button(text="🔙 В главное меню")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_admin_actions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика бота", callback_data="admin_stats")],
        [InlineKeyboardButton(text="💰 Изменить баланс", callback_data="admin_change_balance")],
        [InlineKeyboardButton(text="📢 Сделать рассылку", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="👥 Список пользователей", callback_data="admin_users")],
        [InlineKeyboardButton(text="📜 Логи транзакций", callback_data="admin_logs")],
        [InlineKeyboardButton(text="💾 Сохранить данные", callback_data="admin_save")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ])

def get_games_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="🎰 Рулетка")
    builder.button(text="🎯 Дартс")
    builder.button(text="⚽️ Футбол")
    builder.button(text="🎳 Боулинг")
    builder.button(text="🏀 Баскетбол")
    builder.button(text="💣 Мины")
    builder.button(text="🏛 Пирамида")
    builder.button(text="🎰 Слоты")
    builder.button(text="🔙 Главное меню")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_bet_keyboard(game_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐️ 5", callback_data=f"{game_name}_bet_5"),
         InlineKeyboardButton(text="⭐️ 10", callback_data=f"{game_name}_bet_10"),
         InlineKeyboardButton(text="⭐️ 25", callback_data=f"{game_name}_bet_25")],
        [InlineKeyboardButton(text="⭐️ 50", callback_data=f"{game_name}_bet_50"),
         InlineKeyboardButton(text="⭐️ 100", callback_data=f"{game_name}_bet_100"),
         InlineKeyboardButton(text="⭐️ 250", callback_data=f"{game_name}_bet_250")],
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
        [InlineKeyboardButton(text="✏️ Другая сумма", callback_data="deposit_custom")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])

def get_mines_board_keyboard(board, revealed, bet) -> InlineKeyboardMarkup:
    keyboard = []
    for i in range(5):
        row = []
        for j in range(5):
            if revealed[i][j]:
                emoji = "💣" if board[i][j] == "💣" else "💎"
                text = emoji
            else:
                text = "❓"
            row.append(InlineKeyboardButton(text=text, callback_data=f"mine_{i}_{j}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="💰 Забрать выигрыш", callback_data=f"mines_cashout_{bet}")])
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_games")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_slots_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Крутить (5⭐️)", callback_data="slots_spin_5"),
         InlineKeyboardButton(text="🎰 Крутить (10⭐️)", callback_data="slots_spin_10")],
        [InlineKeyboardButton(text="🎰 Крутить (25⭐️)", callback_data="slots_spin_25"),
         InlineKeyboardButton(text="🎰 Крутить (50⭐️)", callback_data="slots_spin_50")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_games")]
    ])


# ===================== КОМАНДЫ =====================
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
                    await message.answer(f"✅ Вы получили {format_stars(REFERRAL_SIGNUP_BONUS)} за регистрацию по ссылке!")
            except:
                pass
    
    welcome_text = (
        f"🌟 <b>Добро пожаловать в StarPlay!</b> 🌟\n\n"
        f"{get_random_emoji()} Играй на Telegram Stars и выигрывай!\n\n"
        f"<b>🔥 Что тебя ждет:</b>\n"
        f"• 8 увлекательных игр с реальными выигрышами\n"
        f"• Реферальная система — зарабатывай с друзьями\n"
        f"• Ежедневные бонусы\n"
        f"• Рейтинг лучших игроков\n\n"
        f"<b>💫 Как начать:</b>\n"
        f"1️⃣ Пополни баланс через Telegram Stars\n"
        f"2️⃣ Выбери игру\n"
        f"3️⃣ Делай ставки и выигрывай!\n\n"
        f"👇 <i>Используй кнопки внизу!</i>"
    )
    
    keyboard = get_admin_keyboard() if is_admin(username) else get_main_keyboard()
    
    await message.answer(welcome_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ У вас нет доступа к админ-панели!")
        return
    
    await message.answer(
        "👑 <b>Админ-панель</b>\n\nВыберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_actions_keyboard()
    )


# ===================== ОБРАБОТЧИКИ REPLY КЛАВИАТУРЫ =====================
@dp.message(F.text == "💰 Баланс")
async def balance_reply(message: Message):
    user_id = message.from_user.id
    await message.answer(
        f"💰 <b>Твой баланс:</b> {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text == "⭐️ Пополнить")
async def deposit_reply(message: Message):
    await message.answer(
        "⭐️ <b>Пополнение баланса</b>\n\nВыберите сумму:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_deposit_keyboard()
    )

@dp.message(F.text == "🎮 Игры")
async def games_reply(message: Message):
    await message.answer(
        "🎮 <b>Выбери игру</b>\n\nНажми на кнопку с игрой:",
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
        top_text += f"{medal} <b>{name}</b> — {bal} ⭐️\n"
    
    await message.answer(top_text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "📊 Профиль")
async def profile_reply(message: Message):
    uid = message.from_user.id
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
        f"🎉 <b>Ежедневный бонус получен!</b> 🎉\n\n+{format_stars(bonus_amount)}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text == "👑 Админ панель")
async def admin_panel_reply(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ У вас нет доступа!")
        return
    await message.answer(
        "👑 <b>Админ-панель</b>\n\nВыберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_actions_keyboard()
    )

@dp.message(F.text == "📊 Статистика")
async def admin_stats_reply(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    total_users = len(users_balance)
    total_balance = sum(users_balance.values())
    total_games = sum(s["games_played"] for s in users_stats.values())
    total_wins = sum(s["games_won"] for s in users_stats.values())
    total_deposits = sum(1 for tx_list in transactions.values() for tx in tx_list if tx["type"] == "deposit")
    deposit_sum = sum(tx["amount"] for tx_list in transactions.values() for tx in tx_list if tx["type"] == "deposit")
    
    text = (
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 <b>Пользователей:</b> {total_users}\n"
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
    
    await message.answer(text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "📢 Рассылка")
async def admin_broadcast_reply(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await state.set_state(GameStates.admin_send_message)
    await message.answer(
        "📢 <b>Рассылка</b>\n\n"
        "Отправь сообщение для рассылки всем пользователям.\n"
        "Это может быть текст, фото, видео или документ.\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text == "💰 Изменить баланс")
async def admin_change_balance_reply(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    await state.set_state(GameStates.admin_find_user)
    await message.answer(
        "💰 <b>Изменение баланса</b>\n\n"
        "Введи username игрока (без @) или ID:\n"
        "<code>username</code> или <code>123456789</code>\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text == "🔙 В главное меню")
async def back_to_main_reply(message: Message):
    username = message.from_user.username or ""
    keyboard = get_admin_keyboard() if is_admin(username) else get_main_keyboard()
    await message.answer(
        "🌟 <b>Главное меню</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

@dp.message(F.text == "🔙 Главное меню")
async def back_to_main_from_games(message: Message):
    username = message.from_user.username or ""
    keyboard = get_admin_keyboard() if is_admin(username) else get_main_keyboard()
    await message.answer(
        "🌟 <b>Главное меню</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


# ===================== DICE ИГРЫ =====================
@dp.message(F.text == "🎯 Дартс")
async def darts_start(message: Message):
    await message.answer(
        "🎯 <b>Дартс</b>\n\nВыбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("darts")
    )

@dp.callback_query(F.data.startswith("darts_bet_"))
async def darts_play_callback(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    await state.update_data(dice_game_data={"game": "darts", "bet": bet, "emoji": "🎯"})
    await callback.message.delete()
    await callback.message.answer(
        f"🎯 <b>Дартс</b>\n\nСтавка: {format_stars(bet)}\n"
        f"🎯 Кидай дротик! Нажми на кнопку ниже:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎯 БРОСОК", callback_data="throw_dice")]
        ])
    )
    await callback.answer()

@dp.message(F.text == "⚽️ Футбол")
async def football_start(message: Message):
    await message.answer(
        "⚽️ <b>Футбол</b>\n\nВыбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("football")
    )

@dp.callback_query(F.data.startswith("football_bet_"))
async def football_play_callback(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    await state.update_data(dice_game_data={"game": "football", "bet": bet, "emoji": "⚽️"})
    await callback.message.delete()
    await callback.message.answer(
        f"⚽️ <b>Футбол</b>\n\nСтавка: {format_stars(bet)}\n"
        f"⚽️ Бей пенальти! Нажми на кнопку ниже:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚽️ УДАР", callback_data="throw_dice")]
        ])
    )
    await callback.answer()

@dp.message(F.text == "🏀 Баскетбол")
async def basketball_start(message: Message):
    await message.answer(
        "🏀 <b>Баскетбол</b>\n\nВыбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("basketball")
    )

@dp.callback_query(F.data.startswith("basketball_bet_"))
async def basketball_play_callback(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    await state.update_data(dice_game_data={"game": "basketball", "bet": bet, "emoji": "🏀"})
    await callback.message.delete()
    await callback.message.answer(
        f"🏀 <b>Баскетбол</b>\n\nСтавка: {format_stars(bet)}\n"
        f"🏀 Бросай мяч! Нажми на кнопку ниже:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏀 БРОСОК", callback_data="throw_dice")]
        ])
    )
    await callback.answer()

@dp.message(F.text == "🎳 Боулинг")
async def bowling_start(message: Message):
    await message.answer(
        "🎳 <b>Боулинг</b>\n\nВыбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("bowling")
    )

@dp.callback_query(F.data.startswith("bowling_bet_"))
async def bowling_play_callback(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    await state.update_data(dice_game_data={"game": "bowling", "bet": bet, "emoji": "🎳"})
    await callback.message.delete()
    await callback.message.answer(
        f"🎳 <b>Боулинг</b>\n\nСтавка: {format_stars(bet)}\n"
        f"🎳 Бросай шар! Нажми на кнопку ниже:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎳 БРОСОК", callback_data="throw_dice")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "throw_dice")
async def throw_dice(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    game_data = data.get("dice_game_data")
    
    if not game_data:
        await callback.answer("Ошибка! Начните игру заново.", show_alert=True)
        return
    
    game = game_data["game"]
    bet = game_data["bet"]
    emoji = game_data["emoji"]
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        await state.clear()
        return
    
    # Списываем ставку
    update_balance(user_id, -bet)
    
    # Отправляем dice
    dice_message = await callback.message.answer_dice(emoji=emoji)
    dice_value = dice_message.dice.value
    
    # Получаем множитель
    multiplier = DICE_MULTIPLIERS.get(emoji, {}).get(dice_value, 0)
    
    if multiplier > 0:
        win_amount = bet * multiplier
        update_balance(user_id, win_amount)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        
        if game == "darts":
            stats["darts_wins"] += 1
        elif game == "football":
            stats["football_wins"] += 1
        elif game == "basketball":
            stats["basketball_wins"] += 1
        elif game == "bowling":
            stats["bowling_wins"] += 1
            
        stats["total_won"] += win_amount
        save_transaction(user_id, win_amount, "game_win", f"{game} x{multiplier}")
        
        result_text = f"🎉 <b>ВЫИГРЫШ!</b> x{multiplier}\n+{format_stars(win_amount)}"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", game)
        result_text = f"😢 <b>Проигрыш</b>\n-{format_stars(bet)}"
    
    await callback.message.answer(
        f"{GAME_NAMES.get(game, '🎲')}\n\n"
        f"Твой результат: <b>{dice_value}</b>\n"
        f"Ставка: {format_stars(bet)}\n\n"
        f"{result_text}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await state.clear()
    await callback.answer()


# ===================== ОСТАЛЬНЫЕ ИГРЫ =====================
roulette_numbers = list(range(0, 37))
roulette_colors = {0: "green"}
for i in range(1, 37):
    roulette_colors[i] = "red" if i % 2 == 1 else "black"

@dp.message(F.text == "🎰 Рулетка")
async def roulette_start(message: Message):
    await message.answer(
        "🎰 <b>Европейская Рулетка</b>\n\nВыбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("roulette")
    )

@dp.callback_query(F.data.startswith("roulette_bet_"))
async def roulette_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    if get_user_balance(callback.from_user.id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    await state.update_data(roulette_bet=bet)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Красное (x2)", callback_data="roulette_type_red")],
        [InlineKeyboardButton(text="⚫️ Черное (x2)", callback_data="roulette_type_black")],
        [InlineKeyboardButton(text="🟢 Зеро (0) x35", callback_data="roulette_type_zero")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_games")]
    ])
    await callback.message.edit_text(
        f"🎰 Ставка: {format_stars(bet)}\n\nВыбери тип ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("roulette_type_"))
async def roulette_play(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet = data.get("roulette_bet", 5)
    bet_type = callback.data.split("_")[-1]
    user_id = callback.from_user.id
    update_balance(user_id, -bet)
    result = random.choice(roulette_numbers)
    color = roulette_colors[result]
    win, mult = False, 0
    if bet_type == "red" and color == "red":
        win, mult = True, 2
    elif bet_type == "black" and color == "black":
        win, mult = True, 2
    elif bet_type == "zero" and result == 0:
        win, mult = True, 35
    if win:
        winnings = bet * mult
        update_balance(user_id, winnings)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["roulette_wins"] += 1
        stats["total_won"] += winnings
        save_transaction(user_id, winnings, "game_win", f"Рулетка x{mult}")
        res_text = f"🎉 <b>ВЫИГРЫШ!</b> +{format_stars(winnings)}"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", "Рулетка")
        res_text = f"😢 <b>Проигрыш</b> -{format_stars(bet)}"
    color_emoji = {"red":"🔴","black":"⚫️","green":"🟢"}[color]
    await callback.message.edit_text(
        f"🎰 <b>Рулетка</b>\n\nСтавка: {format_stars(bet)}\nВыпало: {result} {color_emoji}\n\n{res_text}\n\n💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML
    )
    await state.clear()
    await callback.answer()


# ---------- МИНЫ ----------
active_mines_games: Dict[int, dict] = {}

@dp.message(F.text == "💣 Мины")
async def mines_start(message: Message):
    await message.answer(
        "💣 <b>МИНЫ</b>\n\nПоле 5x5, 5 мин. Каждая найденная 💎 увеличивает множитель x1.2.\nВыбери сумму ставки:",
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
        "cells": 0
    }
    await callback.message.edit_text(
        f"💣 <b>Игра МИНЫ</b>\n\nСтавка: {format_stars(bet)}\nОткрывай клетки, избегай мин!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_mines_board_keyboard(board, active_mines_games[user_id]["revealed"], bet)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("mine_"))
async def mines_reveal(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_mines_games:
        await callback.answer("Игра не найдена. Начни новую.", show_alert=True)
        return
    game = active_mines_games[user_id]
    x, y = map(int, callback.data.split("_")[1:])
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
            f"💣 <b>МИНЫ</b>\n\n💥 БАХ! Ты наступил на мину!\nСтавка проиграна.\n💰 Баланс: {format_stars(get_user_balance(user_id))}",
            parse_mode=ParseMode.HTML
        )
    else:
        game["cells"] += 1
        game["multiplier"] *= 1.2
        await callback.message.edit_reply_markup(reply_markup=get_mines_board_keyboard(game["board"], game["revealed"], game["bet"]))
        if game["cells"] >= 15:
            win = int(game["bet"] * game["multiplier"])
            update_balance(user_id, win)
            stats = get_user_stats(user_id)
            stats["games_played"] += 1
            stats["games_won"] += 1
            stats["mines_wins"] += 1
            stats["total_won"] += win
            save_transaction(user_id, win, "game_win", "Мины победа")
            del active_mines_games[user_id]
            await callback.message.edit_text(
                f"💣 <b>МИНЫ</b>\n\n🎉 ПОБЕДА! Очищено {game['cells']} клеток.\nВыигрыш: {format_stars(win)}\n💰 Баланс: {format_stars(get_user_balance(user_id))}",
                parse_mode=ParseMode.HTML
            )
    await callback.answer()

@dp.callback_query(F.data.startswith("mines_cashout_"))
async def mines_cashout(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_mines_games:
        await callback.answer("Нет активной игры", show_alert=True)
        return
    game = active_mines_games[user_id]
    win = int(game["bet"] * game["multiplier"])
    update_balance(user_id, win)
    stats = get_user_stats(user_id)
    stats["games_played"] += 1
    stats["games_won"] += 1
    stats["mines_wins"] += 1
    stats["total_won"] += win
    save_transaction(user_id, win, "game_win", f"Мины кэшаут {game['cells']} клеток")
    del active_mines_games[user_id]
    await callback.message.edit_text(
        f"💣 <b>МИНЫ</b>\n\n💰 Ты забрал {format_stars(win)}!\n💰 Баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


# ---------- ПИРАМИДА ----------
active_pyramids: Dict[int, dict] = {}

@dp.message(F.text == "🏛 Пирамида")
async def pyramid_start(message: Message):
    await message.answer(
        "🏛 <b>Пирамида</b>\n\n5 уровней, каждый шаг удваивает выигрыш (50% успеха).\nВыбери начальную ставку:",
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
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬆️ Подняться (x2)", callback_data="pyramid_up")],
        [InlineKeyboardButton(text="💰 Забрать выигрыш", callback_data="pyramid_cashout")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_games")]
    ])
    await callback.message.edit_text(
        f"🏛 <b>Пирамида — Уровень 1</b>\n\nТекущий выигрыш: {format_stars(bet)}\nСледующий уровень: {format_stars(bet*2)}\nШанс 50%.\n\nЧто делаем?",
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )
    await callback.answer()

@dp.callback_query(F.data == "pyramid_up")
async def pyramid_up(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_pyramids:
        await callback.answer("Нет активной игры", show_alert=True)
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
            save_transaction(user_id, game["current"], "game_win", f"Пирамида ур.{game['level']}")
            del active_pyramids[user_id]
            await callback.message.edit_text(
                f"🏛 <b>ПИРАМИДА ПОБЕДА!</b>\n\n🎉 Ты покорил вершину!\nВыигрыш: {format_stars(game['current'])}\n💰 Баланс: {format_stars(get_user_balance(user_id))}",
                parse_mode=ParseMode.HTML
            )
        else:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬆️ Подняться (x2)", callback_data="pyramid_up")],
                [InlineKeyboardButton(text="💰 Забрать выигрыш", callback_data="pyramid_cashout")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_games")]
            ])
            await callback.message.edit_text(
                f"🏛 <b>Пирамида — Уровень {game['level']}</b>\n\n✅ Успех! Текущий выигрыш: {format_stars(game['current'])}\nСледующий уровень: {format_stars(game['current']*2)}\n\nПродолжим?",
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += game["bet"]
        save_transaction(user_id, -game["bet"], "game_loss", f"Пирамида ур.{game['level']}")
        del active_pyramids[user_id]
        await callback.message.edit_text(
            f"🏛 <b>Пирамида</b>\n\n💔 Проигрыш! Ты рухнул.\nСтавка {format_stars(game['bet'])} потеряна.\n💰 Баланс: {format_stars(get_user_balance(user_id))}",
            parse_mode=ParseMode.HTML
        )
    await callback.answer()

@dp.callback_query(F.data == "pyramid_cashout")
async def pyramid_cashout(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_pyramids:
        await callback.answer("Нет активной игры", show_alert=True)
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
        f"🏛 <b>Пирамида</b>\n\n💰 Ты забрал {format_stars(win)}!\n💰 Баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


# ---------- СЛОТЫ ----------
slot_symbols = ["🍒", "🍊", "🍋", "💎", "7️⃣", "🎰", "⭐️", "💫"]
slot_payouts = {
    ("🍒", "🍒", "🍒"): 5, ("🍊", "🍊", "🍊"): 7, ("🍋", "🍋", "🍋"): 10,
    ("💎", "💎", "💎"): 15, ("7️⃣", "7️⃣", "7️⃣"): 25, ("🎰", "🎰", "🎰"): 50,
    ("⭐️", "⭐️", "⭐️"): 30, ("💫", "💫", "💫"): 20
}

@dp.message(F.text == "🎰 Слоты")
async def slots_start(message: Message):
    await message.answer(
        "🎰 <b>Слоты</b>\n\nКрути барабаны и собирай комбинации!\nВыбери ставку:",
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
    reel1, reel2, reel3 = random.choice(slot_symbols), random.choice(slot_symbols), random.choice(slot_symbols)
    combo = (reel1, reel2, reel3)
    if combo in slot_payouts:
        mult = slot_payouts[combo]
        win = bet * mult
        update_balance(user_id, win)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["slots_wins"] += 1
        stats["total_won"] += win
        save_transaction(user_id, win, "game_win", f"Слоты {''.join(combo)}")
        res = f"🎉 ДЖЕКПОТ! x{mult} +{format_stars(win)}"
    elif reel1 == reel2 or reel1 == reel3 or reel2 == reel3:
        win = int(bet * 1.5)
        update_balance(user_id, win)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_won"] += win
        save_transaction(user_id, win, "game_win", f"Слоты пара")
        res = f"🎉 Пара! x1.5 +{format_stars(win)}"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", "Слоты")
        res = f"😢 Не повезло -{format_stars(bet)}"
    await callback.message.edit_text(
        f"🎰 <b>Слоты</b>\n\n┌─────┬─────┬─────┐\n│ {reel1}  │ {reel2}  │ {reel3}  │\n└─────┴─────┴─────┘\n\nСтавка: {format_stars(bet)}\n{res}\n\n💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


# ===================== АДМИН ОБРАБОТЧИКИ =====================
@dp.callback_query(F.data == "admin_stats")
async def admin_stats_callback(callback: CallbackQuery):
    username = callback.from_user.username or ""
    if not is_admin(username):
        await callback.answer("Нет доступа!")
        return
    
    total_users = len(users_balance)
    total_balance = sum(users_balance.values())
    total_games = sum(s["games_played"] for s in users_stats.values())
    total_wins = sum(s["games_won"] for s in users_stats.values())
    total_deposits = sum(1 for tx_list in transactions.values() for tx in tx_list if tx["type"] == "deposit")
    deposit_sum = sum(tx["amount"] for tx_list in transactions.values() for tx in tx_list if tx["type"] == "deposit")
    
    text = (
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 <b>Пользователей:</b> {total_users}\n"
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
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_actions_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "admin_change_balance")
async def admin_change_balance_start(callback: CallbackQuery, state: FSMContext):
    username = callback.from_user.username or ""
    if not is_admin(username):
        await callback.answer("Нет доступа!")
        return
    
    await state.set_state(GameStates.admin_find_user)
    await callback.message.edit_text(
        "💰 <b>Изменение баланса</b>\n\n"
        "Введи username игрока (без @):\n"
        "<code>hjklgf1</code>\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    username = callback.from_user.username or ""
    if not is_admin(username):
        await callback.answer("Нет доступа!")
        return
    
    await state.set_state(GameStates.admin_send_message)
    await callback.message.edit_text(
        "📢 <b>Рассылка</b>\n\n"
        "Отправь сообщение для рассылки всем пользователям.\n\n"
        "<i>Для отмены отправь /cancel</i>",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_users")
async def admin_users_list(callback: CallbackQuery):
    username = callback.from_user.username or ""
    if not is_admin(username):
        await callback.answer("Нет доступа!")
        return
    
    users_list = []
    for uid, uname in users_username.items():
        balance = get_user_balance(uid)
        users_list.append(f"@{uname or str(uid)} — {balance}⭐️")
    
    if not users_list:
        text = "👥 Пользователей пока нет"
    else:
        text = "👥 <b>Список пользователей</b>\n\n" + "\n".join(users_list[:50])
        if len(users_list) > 50:
            text += f"\n\n... и ещё {len(users_list)-50} пользователей"
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_actions_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "admin_logs")
async def admin_logs(callback: CallbackQuery):
    username = callback.from_user.username or ""
    if not is_admin(username):
        await callback.answer("Нет доступа!")
        return
    
    all_txs = []
    for uid, tx_list in transactions.items():
        uname = users_username.get(uid, str(uid))
        for tx in tx_list[-5:]:
            all_txs.append((tx["timestamp"], f"@{uname}: {tx['type']} {tx['amount']}⭐️ - {tx['details']}"))
    
    all_txs.sort(reverse=True)
    recent = all_txs[:20]
    
    if not recent:
        text = "📜 Логов пока нет"
    else:
        text = "📜 <b>Последние 20 транзакций</b>\n\n" + "\n".join([f"• {tx[1]}" for tx in recent])
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_actions_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "admin_save")
async def admin_save(callback: CallbackQuery):
    username = callback.from_user.username or ""
    if not is_admin(username):
        await callback.answer("Нет доступа!")
        return
    
    data = {
        "balance": users_balance,
        "referrer": users_referrer,
        "referrals": users_referrals,
        "stats": users_stats,
        "transactions": transactions,
        "username": users_username,
        "join_date": users_join_date
    }
    
    try:
        with open("backup.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        await callback.message.edit_text(
            "✅ <b>Данные сохранены!</b>\n\nФайл backup.json создан.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_actions_keyboard()
        )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка сохранения: {e}",
            reply_markup=get_admin_actions_keyboard()
        )
    await callback.answer()

@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    await callback.message.edit_text(
        "👑 <b>Админ-панель</b>\n\nВыберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_actions_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "back_to_games")
async def back_to_games(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer(
        "🎮 <b>Выбери игру</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery):
    username = callback.from_user.username or ""
    keyboard = get_admin_keyboard() if is_admin(username) else get_main_keyboard()
    await callback.message.delete()
    await callback.message.answer(
        "🌟 <b>Главное меню</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await callback.answer()


# ===================== АДМИН FSM ОБРАБОТЧИКИ =====================
@dp.message(GameStates.admin_find_user)
async def admin_find_user(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await state.clear()
        return
    
    input_text = message.text.strip().replace("@", "")
    
    if input_text.lower() == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=get_admin_keyboard())
        return
    
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
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ +100", callback_data="admin_balance_add_100"),
         InlineKeyboardButton(text="➕ +500", callback_data="admin_balance_add_500")],
        [InlineKeyboardButton(text="➖ -100", callback_data="admin_balance_remove_100"),
         InlineKeyboardButton(text="➖ -500", callback_data="admin_balance_remove_500")],
        [InlineKeyboardButton(text="✏️ Своя сумма", callback_data="admin_balance_custom")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ])
    
    await message.answer(
        f"💰 <b>Изменение баланса</b>\n\n"
        f"👤 Пользователь: @{input_text}\n"
        f"💰 Текущий баланс: {format_stars(current_balance)}\n\n"
        f"Выберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

@dp.callback_query(F.data.startswith("admin_balance_"))
async def admin_balance_action(callback: CallbackQuery, state: FSMContext):
    username = callback.from_user.username or ""
    if not is_admin(username):
        await callback.answer("Нет доступа!")
        return
    
    data = await state.get_data()
    target_user = data.get("admin_target_user")
    target_username = data.get("admin_target_username")
    
    if not target_user:
        await callback.answer("Ошибка: пользователь не найден")
        await state.clear()
        return
    
    if callback.data == "admin_balance_custom":
        await state.set_state(GameStates.admin_change_balance)
        await callback.message.answer(
            "✏️ Введи сумму (можно с минусом для снятия):\n"
            "Пример: <code>500</code> или <code>-200</code>",
            parse_mode=ParseMode.HTML
        )
        await callback.answer()
        return
    
    parts = callback.data.split("_")
    action = parts[2]
    amount = int(parts[3])
    
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
        reply_markup=get_admin_actions_keyboard()
    )
    await callback.answer()

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
        await message.answer("❌ Ошибка: пользователь не найден")
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
            reply_markup=get_admin_keyboard()
        )
    except ValueError:
        await message.answer("❌ Введи число!")

@dp.message(GameStates.admin_send_message)
async def admin_broadcast_handler(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        await state.clear()
        return
    
    if message.text and message.text.lower() == "/cancel":
        await state.clear()
        await message.answer("❌ Рассылка отменена.", reply_markup=get_admin_keyboard())
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
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📨 Доставлено: {success}\n"
        f"❌ Ошибок: {fail}",
        parse_mode=ParseMode.HTML
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
        f"🎮 Приятной игры!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(user_id)
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
    keyboard = get_admin_keyboard() if is_admin(username) else get_main_keyboard()
    await message.answer("❌ Действие отменено.", reply_markup=keyboard)


# ===================== ЗАПУСК =====================
async def main():
    logger.info("🚀 StarPlay Bot запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())