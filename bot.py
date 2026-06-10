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
BOT_TOKEN = "8251949164:AAH9dxlioIEhmzZNazWzMHg0NhfaEsGYFMk"
ADMIN_USERNAMES = ["hjklgf1", "admin"]

REFERRAL_BONUS_PERCENT = 10
REFERRAL_SIGNUP_BONUS = 5
REFERRAL_INVITE_BONUS = 10
MIN_BET = 1
MAX_BET = 10000

# Хранилища данных
users_balance: Dict[int, float] = {}
users_referrer: Dict[int, int] = {}
users_referrals: Dict[int, List[int]] = {}
users_stats: Dict[int, dict] = {}
users_daily_bonus: Dict[int, str] = {}
pending_payments: Dict[str, dict] = {}
transactions: Dict[int, list] = {}
users_username: Dict[int, str] = {}
users_join_date: Dict[int, str] = {}
users_ban: Dict[int, bool] = {}

# Игровые данные
active_crash: Dict[int, dict] = {}
active_mines: Dict[int, dict] = {}
active_dice: Dict[int, dict] = {}

# Статистика бота
bot_stats = {
    "total_bets": 0,
    "total_wagered": 0.0,
    "total_paid": 0.0,
    "profit": 0.0,
    "active_users": 0
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# ===================== FSM СОСТОЯНИЯ =====================
class GameStates(StatesGroup):
    # Crash игры
    crash_bet = State()
    crash_playing = State()
    
    # Mines
    mines_bet = State()
    mines_playing = State()
    
    # Dice
    dice_bet = State()
    dice_threshold = State()
    
    # Админ
    admin_find_user = State()
    admin_change_balance = State()
    admin_send_message = State()
    admin_broadcast_msg = State()
    admin_promo_code = State()
    
    # Пополнение
    custom_deposit = State()


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

def save_transaction(user_id: int, amount: float, tx_type: str, details: str = ""):
    if user_id not in transactions:
        transactions[user_id] = []
    transactions[user_id].append({
        "amount": round(amount, 2),
        "type": tx_type,
        "details": details,
        "timestamp": datetime.now().isoformat()
    })
    if tx_type == "bet":
        bot_stats["total_bets"] += 1
        bot_stats["total_wagered"] += abs(amount)
    elif tx_type == "game_win":
        bot_stats["total_paid"] += amount
    bot_stats["profit"] = bot_stats["total_wagered"] - bot_stats["total_paid"]

def get_user_stats(user_id: int) -> dict:
    if user_id not in users_stats:
        users_stats[user_id] = {
            "games_played": 0, "games_won": 0, "total_won": 0.0, "total_lost": 0.0,
            "crash_wins": 0, "mines_wins": 0, "dice_wins": 0
        }
    return users_stats[user_id]

def get_random_emoji() -> str:
    return random.choice(["🎲", "🎯", "⚡️", "💫", "🌟", "⭐️", "✨", "🎮", "🎰", "🔥"])

def generate_referral_link(user_id: int) -> str:
    code = hashlib.md5(f"starplay_{user_id}_{datetime.now().date()}".encode()).hexdigest()[:8]
    return f"https://t.me/{bot.username}?start=ref_{code}"


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
    builder.button(text="📢 Рассылка")
    builder.button(text="👥 Список пользователей")
    builder.button(text="📜 Логи транзакций")
    builder.button(text="💾 Сохранить данные")
    builder.button(text="⚙️ Настройки игр")
    builder.button(text="🔨 Забанить/Разбанить")
    builder.button(text="🎁 Создать промокод")
    builder.button(text="📈 Экспорт данных")
    builder.button(text="🔄 Сброс статистики")
    builder.button(text="📊 Отчёт по прибыли")
    builder.button(text="🔙 В главное меню")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_games_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📈 Classic Crash")
    builder.button(text="💣 Mines")
    builder.button(text="🎲 Dice")
    builder.button(text="🔙 Главное меню")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_bet_keyboard(game: str) -> InlineKeyboardMarkup:
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
            row.append(InlineKeyboardButton(text=text, callback_data=f"mine_{i}_{j}_{bet}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="💰 Забрать выигрыш", callback_data="mines_cashout")])
    keyboard.append([InlineKeyboardButton(text="◀️ Выйти", callback_data="back_to_games")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


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
                    await message.answer(f"✅ Вы получили {format_stars(REFERRAL_SIGNUP_BONUS)} за регистрацию по ссылке!")
            except:
                pass
    
    if users_ban.get(user_id, False):
        await message.answer("❌ Ваш аккаунт заблокирован! Обратитесь к администратору.")
        return
    
    welcome_text = (
        f"🌟 <b>Добро пожаловать в StarPlay Casino!</b> 🌟\n\n"
        f"{get_random_emoji()} <b>Лучшее казино в Telegram!</b>\n\n"
        f"<b>🎮 Доступные игры:</b>\n"
        f"📈 Classic Crash — растущий множитель до x1000\n"
        f"💣 Mines — сапёр с множителем до x18\n"
        f"🎲 Dice — угадай число и получи множитель\n\n"
        f"<b>💫 Как начать:</b>\n"
        f"1️⃣ Пополни баланс через Telegram Stars\n"
        f"2️⃣ Выбери игру\n"
        f"3️⃣ Делай ставки и выигрывай!\n\n"
        f"👇 <i>Используй кнопки внизу!</i>"
    )
    
    await message.answer(welcome_text, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard())

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ У вас нет доступа к админ-панели!")
        return
    await message.answer("👑 <b>Панель администратора</b>\n\nВыберите действие:", parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())


# ===================== ГЛАВНЫЕ КНОПКИ =====================
@dp.message(F.text == "💰 Баланс")
async def balance_reply(message: Message):
    user_id = message.from_user.id
    await message.answer(
        f"💰 <b>Твой баланс:</b> {format_stars(get_user_balance(user_id))}\n\n"
        f"👥 За каждого друга +{REFERRAL_SIGNUP_BONUS} Stars\n"
        f"🎁 {REFERRAL_BONUS_PERCENT}% с пополнений друзей",
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
        "🎮 <b>Выбери игру</b>\n\n"
        "📈 Crash — забери множитель до взрыва\n"
        "💣 Mines — открывай клетки, избегая мин\n"
        "🎲 Dice — угадай выше или ниже\n\n"
        "👇 <i>Нажми на кнопку с игрой!</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )

@dp.message(F.text == "👥 Рефералы")
async def referrals_reply(message: Message):
    user_id = message.from_user.id
    ref_link = generate_referral_link(user_id)
    ref_count = len(users_referrals.get(user_id, []))
    
    total_earned = sum(tx["amount"] for tx in transactions.get(user_id, []) if tx["type"] in ["referral_reward", "referral_earning"])
    
    text = (
        f"👥 <b>Реферальная система</b>\n\n"
        f"🏆 <b>Твоя статистика:</b>\n"
        f"• Приглашено: {ref_count} чел.\n"
        f"• Заработано: {format_stars(total_earned)}\n\n"
        f"<b>📋 Как это работает:</b>\n"
        f"• Друг получает +{REFERRAL_SIGNUP_BONUS} Stars\n"
        f"• Ты получаешь +{REFERRAL_INVITE_BONUS} Stars за приглашение\n"
        f"• Ты получаешь {REFERRAL_BONUS_PERCENT}% от пополнений друга\n\n"
        f"<b>🔗 Твоя реферальная ссылка:</b>\n"
        f"<code>{ref_link}</code>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={ref_link}&text=StarPlay — играй и зарабатывай Stars!")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

@dp.message(F.text == "🏆 Топ")
async def top_reply(message: Message):
    sorted_users = sorted(users_balance.items(), key=lambda x: x[1], reverse=True)[:15]
    
    if not sorted_users:
        await message.answer("🏆 Пока нет игроков в рейтинге!")
        return
    
    top_text = "🏆 <b>ТОП-15 ИГРОКОВ</b> 🏆\n\n"
    for idx, (uid, bal) in enumerate(sorted_users, 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
        uname = users_username.get(uid, str(uid))
        name = f"@{uname}" if uname else str(uid)
        top_text += f"{medal} <b>{name}</b> — {bal:.2f} ⭐️\n"
    
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
        f"👥 <b>Рефералов:</b> {ref_count}"
    )
    
    await message.answer(text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "🎁 Бонус")
async def bonus_reply(message: Message):
    user_id = message.from_user.id
    today = datetime.now().date().isoformat()
    if users_daily_bonus.get(user_id) == today:
        await message.answer("🎁 <b>Ты уже получил сегодняшний бонус!</b>\n\nВозвращайся завтра!", parse_mode=ParseMode.HTML)
        return
    bonus_amount = random.uniform(5, 15)
    update_balance(user_id, bonus_amount)
    users_daily_bonus[user_id] = today
    save_transaction(user_id, bonus_amount, "daily_bonus", "Ежедневный бонус")
    await message.answer(f"🎉 <b>Ежедневный бонус получен!</b>\n\n+{format_stars(bonus_amount)}\n💰 Новый баланс: {format_stars(get_user_balance(user_id))}", parse_mode=ParseMode.HTML)


# ===================== ИГРА 1: CLASSIC CRASH =====================
async def run_crash_game(user_id: int, message: Message, bet: float):
    crash_point = random.uniform(1.01, 1000)
    multiplier = 1.0
    
    for _ in range(int(crash_point * 10)):
        if user_id not in active_crash:
            return
        multiplier = round(multiplier + 0.01, 2)
        if multiplier >= crash_point:
            active_crash.pop(user_id, None)
            await message.edit_text(
                f"📈 <b>CLASSIC CRASH - ВЗРЫВ!</b>\n\n"
                f"💰 Ставка: {format_stars(bet)}\n"
                f"📈 Множитель: x{multiplier}\n\n"
                f"💥 <b>КРАХ! Ставка сгорела!</b>\n\n"
                f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_games_keyboard()
            )
            return
        try:
            await message.edit_text(
                f"📈 <b>CLASSIC CRASH - ИГРА</b>\n\n"
                f"💰 Ставка: {format_stars(bet)}\n"
                f"📈 Множитель: <b>x{multiplier}</b>\n"
                f"💎 Потенциальный выигрыш: {format_stars(bet * multiplier)}\n\n"
                f"👇 <b>Успей забрать до взрыва!</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💰 ЗАБРАТЬ", callback_data="crash_cashout")]
                ])
            )
        except:
            pass
        await asyncio.sleep(0.3)

@dp.message(F.text == "📈 Classic Crash")
async def classic_crash_start(message: Message, state: FSMContext):
    await message.answer(
        "📈 <b>CLASSIC CRASH</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• Множитель растёт от x1.00 до случайного значения\n"
        "• Нужно успеть нажать 'Забрать' до взрыва!\n"
        "• Чем дольше ждёшь — тем выше множитель\n"
        "• Если не забрать до взрыва — ставка сгорает\n\n"
        "🎯 Максимальный множитель: x1000\n"
        "💰 Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("crash")
    )

@dp.callback_query(F.data.startswith("crash_bet_"))
async def classic_crash_bet(callback: CallbackQuery, state: FSMContext):
    bet = float(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    save_transaction(user_id, -bet, "bet", f"Classic Crash ставка")
    
    await callback.message.delete()
    msg = await callback.message.answer(
        f"📈 <b>CLASSIC CRASH - ИГРА</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"📈 Множитель: <b>x1.00</b>\n\n"
        f"👇 <b>Жди роста и забери выигрыш!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 ЗАБРАТЬ", callback_data="crash_cashout")]
        ])
    )
    
    active_crash[user_id] = {"bet": bet, "message": msg}
    asyncio.create_task(run_crash_game(user_id, msg, bet))
    await callback.answer()

@dp.callback_query(F.data == "crash_cashout")
async def crash_cashout(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_crash:
        await callback.answer("Игра не найдена!", show_alert=True)
        return
    
    game = active_crash[user_id]
    bet = game["bet"]
    multiplier = 1.0
    
    active_crash.pop(user_id, None)
    win = bet * multiplier
    update_balance(user_id, win)
    
    stats = get_user_stats(user_id)
    stats["games_played"] += 1
    stats["games_won"] += 1
    stats["crash_wins"] += 1
    stats["total_won"] += win
    save_transaction(user_id, win, "game_win", f"Classic Crash x{multiplier}")
    
    await callback.message.edit_text(
        f"📈 <b>CLASSIC CRASH - ВЫИГРЫШ!</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"📈 Множитель: x{multiplier}\n"
        f"🎉 Выигрыш: {format_stars(win)}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()


# ===================== ИГРА 2: MINES =====================
@dp.message(F.text == "💣 Mines")
async def mines_start(message: Message, state: FSMContext):
    await message.answer(
        "💣 <b>MINES (Сапёр)</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• Поле 5x5, скрыто 5 мин\n"
        "• 💎 → увеличивает множитель x1.2\n"
        "• 💣 → мгновенный проигрыш\n"
        "• Можно забрать выигрыш в любой момент\n"
        "• Максимальный множитель: x18\n\n"
        "💰 Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("mines")
    )

@dp.callback_query(F.data.startswith("mines_bet_"))
async def mines_bet(callback: CallbackQuery, state: FSMContext):
    bet = float(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    save_transaction(user_id, -bet, "bet", f"Mines ставка")
    
    # Создаём поле
    board = [["💎" for _ in range(5)] for _ in range(5)]
    mines = 0
    while mines < 5:
        x, y = random.randint(0, 4), random.randint(0, 4)
        if board[x][y] == "💎":
            board[x][y] = "💣"
            mines += 1
    
    active_mines[user_id] = {
        "board": board,
        "revealed": [[False] * 5 for _ in range(5)],
        "bet": bet,
        "multiplier": 1.0,
        "cells": 0
    }
    
    await callback.message.edit_text(
        f"💣 <b>MINES</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"✨ Множитель: x1.0\n"
        f"📦 Открыто: 0/20\n\n"
        f"👇 <b>Открывай клетки!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_mines_board_keyboard(board, active_mines[user_id]["revealed"], bet)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("mine_"))
async def mine_reveal(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_mines:
        await callback.answer("Игра не найдена!", show_alert=True)
        return
    
    game = active_mines[user_id]
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
        save_transaction(user_id, -game["bet"], "game_loss", "Mines")
        del active_mines[user_id]
        
        await callback.message.edit_text(
            f"💣 <b>MINES - ПРОИГРЫШ</b>\n\n"
            f"💥 <b>БАХ! Ты наступил на мину!</b>\n\n"
            f"💰 Ставка: {format_stars(game['bet'])} — проиграна\n\n"
            f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_games_keyboard()
        )
    else:
        game["cells"] += 1
        game["multiplier"] *= 1.2
        
        await callback.message.edit_text(
            f"💣 <b>MINES</b>\n\n"
            f"💰 Ставка: {format_stars(game['bet'])}\n"
            f"✨ Множитель: x{game['multiplier']:.1f}\n"
            f"📦 Открыто: {game['cells']}/20\n"
            f"💎 Найдено сокровище! Множитель увеличен!\n\n"
            f"👇 <b>Продолжай открывать или забери выигрыш!</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_mines_board_keyboard(game["board"], game["revealed"], game["bet"])
        )
        
        if game["cells"] >= 20:
            win = game["bet"] * game["multiplier"]
            update_balance(user_id, win)
            stats = get_user_stats(user_id)
            stats["games_played"] += 1
            stats["games_won"] += 1
            stats["mines_wins"] += 1
            stats["total_won"] += win
            save_transaction(user_id, win, "game_win", f"Mines победа x{game['multiplier']:.1f}")
            del active_mines[user_id]
            await callback.message.edit_text(
                f"🎉 <b>ПОБЕДА!</b>\n\n"
                f"💎 Вы очистили всё поле!\n"
                f"🏆 Выигрыш: {format_stars(win)}\n\n"
                f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_games_keyboard()
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
    stats["mines_wins"] += 1
    stats["total_won"] += win
    save_transaction(user_id, win, "game_win", f"Mines кэшаут x{game['multiplier']:.1f}")
    del active_mines[user_id]
    
    await callback.message.edit_text(
        f"💰 <b>Вы забрали выигрыш!</b>\n\n"
        f"💎 Открыто: {game['cells']}/20\n"
        f"✨ Множитель: x{game['multiplier']:.1f}\n"
        f"🏆 Выигрыш: {format_stars(win)}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()


# ===================== ИГРА 3: DICE =====================
@dp.message(F.text == "🎲 Dice")
async def dice_start(message: Message, state: FSMContext):
    await message.answer(
        "🎲 <b>DICE</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• Выбери число от 1 до 99\n"
        "• Угадай, выпадет больше или меньше\n"
        "• Множитель = 100 / (100 - порог)\n\n"
        "💰 Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("dice")
    )

@dp.callback_query(F.data.startswith("dice_bet_"))
async def dice_bet(callback: CallbackQuery, state: FSMContext):
    bet = float(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    await state.update_data(dice_bet=bet)
    await state.set_state(GameStates.dice_threshold)
    
    await callback.message.edit_text(
        "🎲 <b>DICE</b>\n\n"
        "Введи число от 1 до 99 (порог):\n"
        "Если выпадет БОЛЬШЕ порога — ты выиграешь!\n\n"
        "<i>Пример: если порог 70, выигрываешь при 71-100</i>",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

@dp.message(GameStates.dice_threshold)
async def dice_play(message: Message, state: FSMContext):
    try:
        threshold = int(message.text.strip())
        if threshold < 1 or threshold > 99:
            await message.answer("❌ Число должно быть от 1 до 99!")
            return
    except:
        await message.answer("❌ Введи число от 1 до 99!")
        return
    
    data = await state.get_data()
    bet = data.get("dice_bet")
    user_id = message.from_user.id
    
    if get_user_balance(user_id) < bet:
        await message.answer(f"❌ Не хватает {format_stars(bet)}")
        await state.clear()
        return
    
    update_balance(user_id, -bet)
    save_transaction(user_id, -bet, "bet", f"Dice ставка")
    
    # Кидаем кубик
    dice_msg = await message.answer_dice(emoji="🎲")
    dice_value = dice_msg.dice.value * 16  # 1-6 -> 1-96
    result = dice_value + random.randint(0, 4)  # 1-100
    
    if result > threshold:
        multiplier = 100 / (100 - threshold)
        win = bet * multiplier
        update_balance(user_id, win)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["dice_wins"] += 1
        stats["total_won"] += win
        save_transaction(user_id, win, "game_win", f"Dice {result}>{threshold} x{multiplier:.2f}")
        result_text = f"🎉 <b>ВЫИГРЫШ!</b> x{multiplier:.2f}\n+{format_stars(win - bet)}"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", f"Dice {result}<={threshold}")
        result_text = f"😢 <b>Проигрыш</b>\n-{format_stars(bet)}"
    
    await message.answer(
        f"🎲 <b>DICE</b>\n\n"
        f"🎯 Порог: {threshold}\n"
        f"🎲 Выпало: {result}\n"
        f"💰 Ставка: {format_stars(bet)}\n\n"
        f"{result_text}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await state.clear()


# ===================== АДМИН-ПАНЕЛЬ =====================
@dp.message(F.text == "👑 Админ панель")
async def admin_panel(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        await message.answer("❌ У вас нет доступа!", reply_markup=get_main_keyboard())
        return
    await message.answer("👑 <b>Панель администратора</b>\n\nВыберите действие:", parse_mode=ParseMode.HTML, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "📊 Статистика бота")
async def admin_stats(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    total_users = len(users_balance)
    total_balance = sum(users_balance.values())
    total_games = sum(s["games_played"] for s in users_stats.values())
    total_wins = sum(s["games_won"] for s in users_stats.values())
    
    text = (
        f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
        f"👥 Пользователей: {total_users}\n"
        f"💰 Общий баланс: {format_stars(total_balance)}\n"
        f"🎮 Всего игр: {total_games}\n"
        f"🏆 Всего побед: {total_wins}\n"
    )
    if total_games > 0:
        text += f"📈 Винрейт: {(total_wins/total_games*100):.1f}%\n"
    text += (
        f"\n💰 Профит бота: {format_stars(bot_stats['profit'])}\n"
        f"📊 Общая ставок: {bot_stats['total_wagered']:.2f}\n"
        f"💸 Выплачено: {bot_stats['total_paid']:.2f}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "💰 Изменить баланс")
async def admin_change_balance(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await state.set_state(GameStates.admin_find_user)
    await message.answer(
        "Введи username игрока (без @) или ID:",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(GameStates.admin_find_user)
async def admin_find_user(message: Message, state: FSMContext):
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
    
    await state.update_data(target_user=user_id, target_username=input_text)
    await state.set_state(GameStates.admin_change_balance)
    
    await message.answer(
        f"💰 <b>ИЗМЕНЕНИЕ БАЛАНСА</b>\n\n"
        f"👤 {input_text}\n"
        f"💰 Текущий баланс: {format_stars(get_user_balance(user_id))}\n\n"
        f"Введи сумму (можно с минусом):\n"
        f"Пример: <code>500</code> или <code>-200</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(GameStates.admin_change_balance)
async def admin_change_balance_amount(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=get_admin_panel_keyboard())
        return
    
    data = await state.get_data()
    target_user = data.get("target_user")
    target_username = data.get("target_username")
    
    try:
        amount = float(message.text.strip())
        new_balance = update_balance(target_user, amount)
        
        await bot.send_message(
            target_user,
            f"👑 <b>Администратор изменил ваш баланс!</b>\n\n"
            f"{'+' if amount > 0 else ''}{format_stars(amount)}\n"
            f"💰 Новый баланс: {format_stars(new_balance)}",
            parse_mode=ParseMode.HTML
        )
        
        tx_type = "admin_add" if amount > 0 else "admin_remove"
        save_transaction(target_user, amount, tx_type, f"Админ изменил баланс на {amount}")
        
        await message.answer(
            f"✅ Баланс @{target_username} изменён на {format_stars(amount)}\n"
            f"💰 Новый баланс: {format_stars(new_balance)}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard()
        )
    except:
        await message.answer("❌ Введи число!")
    
    await state.clear()

@dp.message(F.text == "📢 Рассылка")
async def admin_broadcast(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await state.set_state(GameStates.admin_broadcast_msg)
    await message.answer(
        "📢 <b>РАССЫЛКА</b>\n\nОтправь сообщение для рассылки всем пользователям:",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(GameStates.admin_broadcast_msg)
async def admin_broadcast_send(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=get_admin_panel_keyboard())
        return
    
    success = 0
    for user_id in users_balance.keys():
        try:
            await bot.copy_message(user_id, message.chat.id, message.message_id)
            success += 1
            await asyncio.sleep(0.05)
        except:
            pass
    
    await state.clear()
    await message.answer(f"✅ Рассылка завершена!\n📨 Доставлено: {success}", reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "👥 Список пользователей")
async def admin_users_list(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    users_list = []
    for uid, uname in users_username.items():
        balance = get_user_balance(uid)
        users_list.append(f"@{uname or str(uid)} — {balance:.2f}⭐️")
    
    text = "👥 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ</b>\n\n" + "\n".join(users_list[:50])
    if len(users_list) > 50:
        text += f"\n\n... и ещё {len(users_list)-50} пользователей"
    
    await message.answer(text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "📜 Логи транзакций")
async def admin_logs(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    all_txs = []
    for uid, tx_list in transactions.items():
        uname = users_username.get(uid, str(uid))
        for tx in tx_list[-3:]:
            all_txs.append(f"@{uname}: {tx['type']} {tx['amount']:.2f}⭐️ - {tx['details']}")
    
    text = "📜 <b>ПОСЛЕДНИЕ ТРАНЗАКЦИИ</b>\n\n" + "\n".join(all_txs[-30:])
    await message.answer(text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "💾 Сохранить данные")
async def admin_save(message: Message):
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
        "ban": users_ban
    }
    with open("backup.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    await message.answer("✅ Данные сохранены в backup.json", reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "⚙️ Настройки игр")
async def admin_settings(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await message.answer(
        "⚙️ <b>НАСТРОЙКИ ИГР</b>\n\n"
        f"💰 Min Bet: {MIN_BET} Stars\n"
        f"💰 Max Bet: {MAX_BET} Stars\n"
        f"📈 Crash макс: x1000\n"
        f"💣 Mines множитель: x1.2 за клетку\n"
        f"🎲 Dice коэф: 100/(100-порог)",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text == "🔨 Забанить/Разбанить")
async def admin_ban_user(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await state.set_state(GameStates.admin_find_user)
    await message.answer(
        "Введи username для бана/разбана:",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )
    await state.update_data(ban_action=True)

@dp.message(F.text == "🎁 Создать промокод")
async def admin_create_promo(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await state.set_state(GameStates.admin_promo_code)
    await message.answer(
        "Введи сумму для промокода:",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(GameStates.admin_promo_code)
async def admin_promo_amount(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=get_admin_panel_keyboard())
        return
    
    try:
        amount = float(message.text.strip())
        code = hashlib.md5(f"{amount}_{datetime.now()}".encode()).hexdigest()[:8]
        await message.answer(
            f"✅ <b>Промокод создан!</b>\n\n"
            f"🎁 Код: <code>{code}</code>\n"
            f"💰 Сумма: {format_stars(amount)}\n\n"
            f"<i>Использование: /promo {code}</i>",
            parse_mode=ParseMode.HTML
        )
    except:
        await message.answer("❌ Введи число!")
    
    await state.clear()

@dp.message(F.text == "📈 Экспорт данных")
async def admin_export(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    export = {
        "users": {uid: {"balance": bal, "username": users_username.get(uid)} for uid, bal in users_balance.items()},
        "stats": users_stats,
        "profit": bot_stats["profit"],
        "transactions": transactions
    }
    with open("export.json", "w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False)
    await message.answer_document(types.FSInputFile("export.json"), caption="📊 Экспорт данных")

@dp.message(F.text == "🔄 Сброс статистики")
async def admin_reset_stats(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    bot_stats["total_bets"] = 0
    bot_stats["total_wagered"] = 0
    bot_stats["total_paid"] = 0
    bot_stats["profit"] = 0
    await message.answer("✅ Статистика бота сброшена!", reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "📊 Отчёт по прибыли")
async def admin_profit_report(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    text = (
        f"📊 <b>ОТЧЁТ ПО ПРИБЫЛИ</b>\n\n"
        f"💰 Общая прибыль: {format_stars(bot_stats['profit'])}\n"
        f"📈 Всего ставок: {bot_stats['total_bets']}\n"
        f"💸 Сумма ставок: {format_stars(bot_stats['total_wagered'])}\n"
        f"🎁 Выплачено: {format_stars(bot_stats['total_paid'])}\n"
        f"📊 Разница: {format_stars(bot_stats['total_wagered'] - bot_stats['total_paid'])}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "🔙 В главное меню")
async def back_to_main(message: Message):
    await message.answer("🌟 <b>Главное меню</b>", parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "back_to_games")
async def back_to_games(callback: CallbackQuery):
    await callback.message.edit_text("🎮 <b>Выбери игру</b>", parse_mode=ParseMode.HTML, reply_markup=get_games_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery):
    await callback.message.edit_text("🌟 <b>Главное меню</b>", parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard())
    await callback.answer()


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
    
    if user_id in users_referrer:
        referrer = users_referrer[user_id]
        bonus = int(amount * REFERRAL_BONUS_PERCENT / 100)
        if bonus:
            update_balance(referrer, bonus)
            save_transaction(referrer, bonus, "referral_earning", f"10% с пополнения реферала")
            await bot.send_message(referrer, f"🎉 <b>Реферальный бонус!</b>\n+{format_stars(bonus)}", parse_mode=ParseMode.HTML)
    
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
        await callback.message.answer("✏️ Введи сумму (1-10000):")
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
    await message.answer("❌ Действие отменено.", reply_markup=get_main_keyboard())

@dp.message(Command("promo"))
async def promo_handler(message: Message):
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❌ Использование: /promo КОД")
        return
    
    code = parts[1]
    # Здесь можно реализовать проверку промокодов
    await message.answer("❌ Промокод не найден или уже использован!")


# ===================== ЗАПУСК =====================
async def main():
    logger.info("🚀 StarPlay Casino Bot запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())