import asyncio
import hashlib
import logging
import random
import json
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from decimal import Decimal

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

# Настройки игр
HOUSE_EDGE = 0.95  # 95% возврата
MIN_BET = 1
MAX_BET = 10000
MAX_MULTIPLIER = 1000

# Реферальная система
REFERRAL_BONUS_PERCENT = 10
REFERRAL_SIGNUP_BONUS = 5
REFERRAL_INVITE_BONUS = 10

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
users_admin_notes: Dict[int, str] = {}
users_verify: Dict[int, bool] = {}

# Игровые данные
active_crash: Dict[int, dict] = {}
active_mines: Dict[int, dict] = {}
active_plinko: Dict[int, dict] = {}
active_wheel: Dict[int, dict] = {}
active_tower: Dict[int, dict] = {}
active_blackjack: Dict[int, dict] = {}
active_duel: Dict[int, dict] = {}
active_ladder: Dict[int, dict] = {}
active_hilo: Dict[int, dict] = {}

# Статистика бота
bot_stats = {
    "total_bets": 0,
    "total_wagered": 0.0,
    "total_paid": 0.0,
    "profit": 0.0,
    "active_users": 0,
    "daily_active": 0
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
    classic_crash = State()
    multi_crash = State()
    reverse_crash = State()
    
    # Игры на удачу
    mines_bet = State()
    mines_play = State()
    plinko_bet = State()
    plinko_lines = State()
    dice_bet = State()
    dice_guess = State()
    wheel_bet = State()
    wheel_spin = State()
    hilo_bet = State()
    hilo_guess = State()
    tower_bet = State()
    tower_play = State()
    
    # Карточные игры
    blackjack_bet = State()
    blackjack_play = State()
    baccarat_bet = State()
    baccarat_play = State()
    poker_bet = State()
    poker_play = State()
    holdem_bet = State()
    holdem_play = State()
    
    # PvP
    duel_bet = State()
    duel_accept = State()
    ladder_join = State()
    ladder_play = State()
    
    # Админ
    admin_find_user = State()
    admin_change_balance = State()
    admin_send_message = State()
    admin_set_multiplier = State()
    admin_set_house_edge = State()
    admin_add_code = State()
    
    # Платежи
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
        "amount": round(amount, 2), "type": tx_type, "details": details,
        "timestamp": datetime.now().isoformat()
    })
    # Обновляем статистику бота
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
            "crash_wins": 0, "mines_wins": 0, "plinko_wins": 0, "dice_wins": 0,
            "wheel_wins": 0, "hilo_wins": 0, "tower_wins": 0, "blackjack_wins": 0,
            "baccarat_wins": 0, "poker_wins": 0, "duel_wins": 0, "ladder_wins": 0
        }
    return users_stats[user_id]

def get_random_emoji() -> str:
    return random.choice(["🎲","🎯","⚡️","💫","🌟","⭐️","✨","🎮","🎰","🔥"])

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
    builder.button(text="✅ Верификация")
    builder.button(text="💸 Бонусы всем")
    builder.button(text="📈 Экспорт данных")
    builder.button(text="🔄 Сброс статистики")
    builder.button(text="🎁 Создать промокод")
    builder.button(text="📊 Отчёт по прибыли")
    builder.button(text="🔙 В главное меню")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_games_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📈 Classic Crash")
    builder.button(text="💣 Mines")
    builder.button(text="⚡ Plinko")
    builder.button(text="🎲 Dice")
    builder.button(text="🎡 Wheel of Fortune")
    builder.button(text="🃏 Hi-Lo")
    builder.button(text="🏗️ Tower")
    builder.button(text="♠️ Blackjack")
    builder.button(text="🎴 Baccarat")
    builder.button(text="💰 Coin Duel")
    builder.button(text="🏆 Step Ladder")
    builder.button(text="🔙 Главное меню")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_bet_keyboard(game: str, min_bet: int = 1) -> InlineKeyboardMarkup:
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


# ===================== ОСНОВНЫЕ КОМАНДЫ =====================
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    
    users_username[user_id] = username
    users_verify[user_id] = True
    
    if user_id not in users_join_date:
        users_join_date[user_id] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Реферальная система
    if " " in message.text:
        param = message.text.split()[1]
        if param.startswith("ref_"):
            try:
                referrer_id = int(param[4:])
                if referrer_id != user_id and user_id not in users_referrer and not users_ban.get(user_id, False):
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
        f"📈 Crash игры — множители до x1000\n"
        f"🎲 Игры на удачу — Mines, Plinko, Dice, Wheel, Hi-Lo, Tower\n"
        f"🃏 Карточные игры — Blackjack, Baccarat\n"
        f"⚔️ PvP арена — Coin Duel, Step Ladder\n\n"
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
        f"🎮 Приглашай друзей и зарабатывай больше!\n"
        f"👥 За каждого друга +{REFERRAL_SIGNUP_BONUS} Stars\n"
        f"🎁 {REFERRAL_BONUS_PERCENT}% с пополнений друзей",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text == "⭐️ Пополнить")
async def deposit_reply(message: Message):
    await message.answer(
        "⭐️ <b>Пополнение баланса</b>\n\n"
        "Выберите сумму пополнения:\n"
        "💰 Средства зачисляются мгновенно после оплаты!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_deposit_keyboard()
    )

@dp.message(F.text == "🎮 Игры")
async def games_reply(message: Message):
    await message.answer(
        "🎮 <b>Выбери игру</b>\n\n"
        "📈 <b>Crash игры:</b> Classic Crash\n"
        "🎲 <b>На удачу:</b> Mines, Plinko, Dice, Wheel, Hi-Lo, Tower\n"
        "🃏 <b>Карточные:</b> Blackjack, Baccarat\n"
        "⚔️ <b>PvP:</b> Coin Duel, Step Ladder\n\n"
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
    
    top_text = "🏆 <b>ТОП-15 ИГРОКОВ StarPlay</b> 🏆\n\n"
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
        f"📅 Регистрация: {users_join_date.get(uid, 'неизвестно')}\n"
        f"✅ Верификация: {'✅ Да' if users_verify.get(uid, False) else '❌ Нет'}\n\n"
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
@dp.message(F.text == "📈 Classic Crash")
async def classic_crash_start(message: Message):
    await message.answer(
        "📈 <b>Classic Crash</b>\n\n"
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
    
    await state.update_data(crash_bet=bet)
    await state.set_state(GameStates.classic_crash)
    await callback.message.delete()
    
    await callback.message.answer(
        f"📈 <b>Classic Crash - ИГРА</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"📈 Множитель: <b>x1.00</b>\n\n"
        f"👇 <b>Жди роста множителя и забери выигрыш!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 ЗАБРАТЬ", callback_data="crash_cashout")]
        ])
    )
    
    # Запускаем рост множителя
    asyncio.create_task(run_crash_game(callback.message, bet, state))
    await callback.answer()

async def run_crash_game(message: Message, bet: float, state: FSMContext):
    crash_point = random.uniform(1.01, 1000)
    multiplier = 1.0
    
    for _ in range(int(crash_point * 10)):
        multiplier = round(multiplier + 0.01, 2)
        if multiplier >= crash_point:
            await message.edit_text(
                f"📈 <b>Classic Crash - ВЗРЫВ!</b>\n\n"
                f"💰 Ставка: {format_stars(bet)}\n"
                f"📈 Множитель: x{multiplier}\n\n"
                f"💥 <b>КРАХ! Ставка сгорела!</b>\n\n"
                f"💰 Новый баланс: {format_stars(get_user_balance(message.chat.id))}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_games_keyboard()
            )
            await state.clear()
            return
        try:
            await message.edit_text(
                f"📈 <b>Classic Crash - ИГРА</b>\n\n"
                f"💰 Ставка: {format_stars(bet)}\n"
                f"📈 Множитель: <b>x{multiplier}</b>\n"
                f"💎 Потенциальный выигрыш: {format_stars(bet * multiplier)}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💰 ЗАБРАТЬ", callback_data="crash_cashout")]
                ])
            )
        except:
            pass
        await asyncio.sleep(0.3)

@dp.callback_query(F.data == "crash_cashout")
async def crash_cashout(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    bet = data.get("crash_bet")
    multiplier = 1.0
    
    if not bet:
        await callback.answer("Игра не найдена!", show_alert=True)
        return
    
    win = bet * multiplier
    update_balance(user_id, win)
    stats = get_user_stats(user_id)
    stats["games_played"] += 1
    stats["games_won"] += 1
    stats["crash_wins"] += 1
    stats["total_won"] += win
    save_transaction(user_id, win, "game_win", f"Classic Crash x{multiplier}")
    
    await callback.message.edit_text(
        f"📈 <b>Classic Crash - ВЫИГРЫШ!</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"📈 Множитель: x{multiplier}\n"
        f"🎉 Выигрыш: {format_stars(win)}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await state.clear()
    await callback.answer()


# ===================== ИГРА 2: MINES (САПЁР) =====================
@dp.message(F.text == "💣 Mines")
async def mines_start(message: Message):
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
async def mines_bet(callback: CallbackQuery):
    bet = float(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    
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
            f"💥 <b>БАХ! Ты наступил на мину!</b>\n"
            f"💰 Ставка: {format_stars(game['bet'])} — проиграна",
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
            f"💎 Найдено сокровище! Множитель увеличен!",
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
            await callback.message.edit_text(f"🎉 <b>ПОБЕДА!</b>\nВыигрыш: {format_stars(win)}", reply_markup=get_games_keyboard())
    
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
        f"🏆 Выигрыш: {format_stars(win)}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()


# ===================== ИГРА 3: PLINKO =====================
@dp.message(F.text == "⚡ Plinko")
async def plinko_start(message: Message):
    await message.answer(
        "⚡ <b>PLINKO</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• Шарик падает по пинам\n"
        "• Множители от x0.2 до x1000\n"
        "• Выбери количество линий (8, 12, 16)\n\n"
        "💰 Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("plinko")
    )

@dp.callback_query(F.data.startswith("plinko_bet_"))
async def plinko_bet(callback: CallbackQuery, state: FSMContext):
    bet = float(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    await state.update_data(plinko_bet=bet)
    await state.set_state(GameStates.plinko_lines)
    
    await callback.message.edit_text(
        "⚡ <b>PLINKO</b>\n\n"
        "Выбери количество линий (8, 12, 16):",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 8 линий", callback_data="plinko_lines_8")],
            [InlineKeyboardButton(text="📊 12 линий", callback_data="plinko_lines_12")],
            [InlineKeyboardButton(text="📊 16 линий", callback_data="plinko_lines_16")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_games")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("plinko_lines_"))
async def plinko_lines(callback: CallbackQuery, state: FSMContext):
    lines = int(callback.data.split("_")[-1])
    data = await state.get_data()
    bet = data.get("plinko_bet")
    user_id = callback.from_user.id
    
    # Множители для Plinko
    multipliers = {
        8: [0.2, 0.5, 1, 2, 5, 10, 20, 50],
        12: [0.2, 0.3, 0.5, 1, 2, 5, 10, 20, 30, 50, 100, 200],
        16: [0.1, 0.2, 0.3, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]
    }
    
    result = random.choice(multipliers[lines])
    win = bet * result
    
    update_balance(user_id, -bet)
    update_balance(user_id, win)
    
    stats = get_user_stats(user_id)
    stats["games_played"] += 1
    if win > bet:
        stats["games_won"] += 1
        stats["plinko_wins"] += 1
        stats["total_won"] += win
        save_transaction(user_id, win, "game_win", f"Plinko x{result}")
        res_text = f"🎉 <b>ВЫИГРЫШ!</b> x{result}\n+{format_stars(win - bet)}"
    else:
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", f"Plinko x{result}")
        res_text = f"😢 <b>Проигрыш</b>\n-{format_stars(bet - win)}"
    
    await callback.message.edit_text(
        f"⚡ <b>PLINKO</b>\n\n"
        f"🎯 Линий: {lines}\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"✨ Множитель: x{result}\n"
        f"{res_text}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await state.clear()
    await callback.answer()


# ===================== ИГРА 4: DICE =====================
@dp.message(F.text == "🎲 Dice")
async def dice_start(message: Message):
    await message.answer(
        "🎲 <b>DICE</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• Выбери число от 1 до 99\n"
        "• Угадай, выпадет больше или меньше\n"
        "• Множитель = 100 / (порог)\n\n"
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
    await state.set_state(GameStates.dice_guess)
    
    await callback.message.edit_text(
        "🎲 <b>DICE</b>\n\n"
        "Выбери порог (1-99):\n"
        "Напиши число от 1 до 99",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

@dp.message(GameStates.dice_guess)
async def dice_guess(message: Message, state: FSMContext):
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
    
    roll_dice = await message.answer_dice(emoji="🎲")
    result = roll_dice.dice.value * 16
    
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
        res_text = f"🎉 <b>ВЫИГРЫШ!</b> x{multiplier:.2f}\n+{format_stars(win - bet)}"
    else:
        update_balance(user_id, -bet)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", f"Dice {result}<={threshold}")
        res_text = f"😢 <b>Проигрыш</b>\n-{format_stars(bet)}"
    
    await message.answer(
        f"🎲 <b>DICE</b>\n\n"
        f"🎯 Порог: {threshold}\n"
        f"🎲 Выпало: {result}\n"
        f"💰 Ставка: {format_stars(bet)}\n\n"
        f"{res_text}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await state.clear()


# ===================== ИГРА 5: WHEEL OF FORTUNE =====================
@dp.message(F.text == "🎡 Wheel of Fortune")
async def wheel_start(message: Message):
    await message.answer(
        "🎡 <b>WHEEL OF FORTUNE</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• Крути колесо с множителями\n"
        "• Множители: x0, x0.5, x1, x2, x5, x10, x25, x50, x100\n\n"
        "💰 Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("wheel")
    )

@dp.callback_query(F.data.startswith("wheel_bet_"))
async def wheel_bet(callback: CallbackQuery, state: FSMContext):
    bet = float(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    await state.update_data(wheel_bet=bet)
    await state.set_state(GameStates.wheel_spin)
    
    await callback.message.edit_text(
        "🎡 <b>WHEEL OF FORTUNE</b>\n\n"
        "Нажми на кнопку, чтобы крутить колесо!",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎡 КРУТИТЬ КОЛЕСО", callback_data="wheel_spin")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "wheel_spin")
async def wheel_spin(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet = data.get("wheel_bet")
    user_id = callback.from_user.id
    
    wheel_multipliers = [0, 0.5, 1, 2, 5, 10, 25, 50, 100]
    result = random.choice(wheel_multipliers)
    
    win = bet * result
    
    update_balance(user_id, -bet)
    update_balance(user_id, win)
    
    stats = get_user_stats(user_id)
    stats["games_played"] += 1
    if win > bet:
        stats["games_won"] += 1
        stats["wheel_wins"] += 1
        stats["total_won"] += win
        save_transaction(user_id, win, "game_win", f"Wheel x{result}")
        res_text = f"🎉 <b>ВЫИГРЫШ!</b> x{result}\n+{format_stars(win - bet)}"
    else:
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", f"Wheel x{result}")
        res_text = f"😢 <b>Проигрыш</b>\n-{format_stars(bet - win)}"
    
    await callback.message.edit_text(
        f"🎡 <b>WHEEL OF FORTUNE</b>\n\n"
        f"✨ Множитель: x{result}\n"
        f"💰 Ставка: {format_stars(bet)}\n\n"
        f"{res_text}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Крутить ещё", callback_data="wheel_spin")],
            [InlineKeyboardButton(text="🎲 Другая игра", callback_data="back_to_games")]
        ])
    )
    await callback.answer()


# ===================== ИГРА 6: HI-LO =====================
@dp.message(F.text == "🃏 Hi-Lo")
async def hilo_start(message: Message):
    await message.answer(
        "🃏 <b>HI-LO</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• Вам показывают карту\n"
        "• Угадай, будет следующая выше или ниже\n"
        "• При правильном угадывании множитель растёт\n"
        "• Можно забрать выигрыш в любой момент\n\n"
        "💰 Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("hilo")
    )

@dp.callback_query(F.data.startswith("hilo_bet_"))
async def hilo_bet(callback: CallbackQuery, state: FSMContext):
    bet = float(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    await state.update_data(hilo_bet=bet, hilo_multiplier=1.0, hilo_current_card=random.randint(2, 14))
    await state.set_state(GameStates.hilo_guess)
    
    card_names = {11: "J", 12: "Q", 13: "K", 14: "A"}
    data = await state.get_data()
    card = card_names.get(data["hilo_current_card"], str(data["hilo_current_card"]))
    
    await callback.message.edit_text(
        f"🃏 <b>HI-LO</b>\n\n"
        f"🎴 Текущая карта: {card}\n"
        f"💰 Текущий выигрыш: {format_stars(bet)}\n"
        f"✨ Множитель: x1.0\n\n"
        f"👇 <b>Следующая карта будет выше или ниже?</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬆️ ВЫШЕ", callback_data="hilo_higher"),
             InlineKeyboardButton(text="⬇️ НИЖЕ", callback_data="hilo_lower")],
            [InlineKeyboardButton(text="💰 ЗАБРАТЬ", callback_data="hilo_cashout")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "hilo_higher")
async def hilo_higher(callback: CallbackQuery, state: FSMContext):
    await hilo_play(callback, state, "higher")

@dp.callback_query(F.data == "hilo_lower")
async def hilo_lower(callback: CallbackQuery, state: FSMContext):
    await hilo_play(callback, state, "lower")

@dp.callback_query(F.data == "hilo_cashout")
async def hilo_cashout(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet = data.get("hilo_bet")
    multiplier = data.get("hilo_multiplier", 1.0)
    user_id = callback.from_user.id
    
    win = bet * multiplier
    update_balance(user_id, win)
    stats = get_user_stats(user_id)
    stats["games_played"] += 1
    stats["games_won"] += 1
    stats["hilo_wins"] += 1
    stats["total_won"] += win
    save_transaction(user_id, win, "game_win", f"Hi-Lo кэшаут x{multiplier:.2f}")
    
    await callback.message.edit_text(
        f"🃏 <b>HI-LO - ВЫИГРЫШ!</b>\n\n"
        f"💰 Выигрыш: {format_stars(win)}\n"
        f"✨ Множитель: x{multiplier:.2f}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await state.clear()
    await callback.answer()

async def hilo_play(callback: CallbackQuery, state: FSMContext, choice: str):
    data = await state.get_data()
    bet = data.get("hilo_bet")
    current_card = data.get("hilo_current_card")
    multiplier = data.get("hilo_multiplier", 1.0)
    user_id = callback.from_user.id
    
    next_card = random.randint(2, 14)
    
    if (choice == "higher" and next_card > current_card) or (choice == "lower" and next_card < current_card):
        multiplier *= 2
        await state.update_data(hilo_current_card=next_card, hilo_multiplier=multiplier)
        
        card_names = {11: "J", 12: "Q", 13: "K", 14: "A"}
        card = card_names.get(next_card, str(next_card))
        
        await callback.message.edit_text(
            f"🃏 <b>HI-LO</b>\n\n"
            f"✅ <b>ВЕРНО!</b>\n"
            f"🎴 Новая карта: {card}\n"
            f"💰 Текущий выигрыш: {format_stars(bet * multiplier)}\n"
            f"✨ Множитель: x{multiplier:.2f}\n\n"
            f"👇 <b>Продолжаем?</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬆️ ВЫШЕ", callback_data="hilo_higher"),
                 InlineKeyboardButton(text="⬇️ НИЖЕ", callback_data="hilo_lower")],
                [InlineKeyboardButton(text="💰 ЗАБРАТЬ", callback_data="hilo_cashout")]
            ])
        )
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", f"Hi-Lo проигрыш")
        await state.clear()
        await callback.message.edit_text(
            f"🃏 <b>HI-LO - ПРОИГРЫШ!</b>\n\n"
            f"❌ Неправильно! Ставка {format_stars(bet)} проиграна",
            parse_mode=ParseMode.HTML,
            reply_markup=get_games_keyboard()
        )
    await callback.answer()


# ===================== ИГРА 7: TOWER =====================
@dp.message(F.text == "🏗️ Tower")
async def tower_start(message: Message):
    await message.answer(
        "🏗️ <b>TOWER</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• Строй башню из блоков\n"
        "• На каждом уровне множитель растёт\n"
        "• Можно забрать выигрыш в любой момент\n"
        "• Максимальный уровень: 10\n\n"
        "💰 Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("tower")
    )

@dp.callback_query(F.data.startswith("tower_bet_"))
async def tower_bet(callback: CallbackQuery):
    bet = float(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    active_tower[user_id] = {"bet": bet, "level": 1, "multiplier": 1.0}
    
    await callback.message.edit_text(
        f"🏗️ <b>TOWER</b>\n\n"
        f"🏢 Уровень: 1/10\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"✨ Множитель: x1.0\n"
        f"💎 Текущий выигрыш: {format_stars(bet)}\n\n"
        f"👇 <b>Построй следующий уровень или забери выигрыш!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏗️ ПОСТРОИТЬ", callback_data="tower_build")],
            [InlineKeyboardButton(text="💰 ЗАБРАТЬ", callback_data="tower_cashout")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "tower_build")
async def tower_build(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_tower:
        await callback.answer("Игра не найдена!", show_alert=True)
        return
    
    game = active_tower[user_id]
    
    if random.random() < 0.85:
        game["level"] += 1
        game["multiplier"] *= 1.5
        win = game["bet"] * game["multiplier"]
        
        if game["level"] >= 10:
            update_balance(user_id, win)
            stats = get_user_stats(user_id)
            stats["games_played"] += 1
            stats["games_won"] += 1
            stats["tower_wins"] += 1
            stats["total_won"] += win
            save_transaction(user_id, win, "game_win", f"Tower победа x{game['multiplier']:.1f}")
            del active_tower[user_id]
            await callback.message.edit_text(f"🎉 <b>ПОБЕДА! Башня построена!</b>\nВыигрыш: {format_stars(win)}", reply_markup=get_games_keyboard())
        else:
            await callback.message.edit_text(
                f"🏗️ <b>TOWER</b>\n\n"
                f"✅ <b>УСПЕХ! Уровень {game['level']}/10</b>\n"
                f"💰 Ставка: {format_stars(game['bet'])}\n"
                f"✨ Множитель: x{game['multiplier']:.1f}\n"
                f"💎 Текущий выигрыш: {format_stars(win)}\n\n"
                f"👇 <b>Продолжай строить!</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏗️ ПОСТРОИТЬ", callback_data="tower_build")],
                    [InlineKeyboardButton(text="💰 ЗАБРАТЬ", callback_data="tower_cashout")]
                ])
            )
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += game["bet"]
        save_transaction(user_id, -game["bet"], "game_loss", "Tower проигрыш")
        del active_tower[user_id]
        await callback.message.edit_text(
            f"🏗️ <b>TOWER - ПРОИГРЫШ!</b>\n\n"
            f"💥 <b>Башня рухнула!</b>\n"
            f"💰 Ставка: {format_stars(game['bet'])} — проиграна",
            parse_mode=ParseMode.HTML,
            reply_markup=get_games_keyboard()
        )
    await callback.answer()

@dp.callback_query(F.data == "tower_cashout")
async def tower_cashout(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_tower:
        await callback.answer("Нет активной игры!", show_alert=True)
        return
    
    game = active_tower[user_id]
    win = game["bet"] * game["multiplier"]
    update_balance(user_id, win)
    stats = get_user_stats(user_id)
    stats["games_played"] += 1
    stats["games_won"] += 1
    stats["tower_wins"] += 1
    stats["total_won"] += win
    save_transaction(user_id, win, "game_win", f"Tower кэшаут x{game['multiplier']:.1f}")
    del active_tower[user_id]
    
    await callback.message.edit_text(
        f"💰 <b>Вы забрали выигрыш!</b>\n\n"
        f"🏢 Уровень: {game['level']}/10\n"
        f"✨ Множитель: x{game['multiplier']:.1f}\n"
        f"🏆 Выигрыш: {format_stars(win)}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()


# ===================== ИГРА 8: BLACKJACK =====================
@dp.message(F.text == "♠️ Blackjack")
async def blackjack_start(message: Message):
    await message.answer(
        "♠️ <b>BLACKJACK (21)</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• Собери 21 очко или ближе к дилеру\n"
        "• Карты: 2-10 по номиналу, J/Q/K = 10, A = 1 или 11\n"
        "• Можно удвоить ставку\n\n"
        "💰 Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("blackjack")
    )

@dp.callback_query(F.data.startswith("blackjack_bet_"))
async def blackjack_bet(callback: CallbackQuery):
    bet = float(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    
    deck = [2,3,4,5,6,7,8,9,10,10,10,10,11] * 4
    random.shuffle(deck)
    
    player_cards = [deck.pop(), deck.pop()]
    dealer_cards = [deck.pop(), deck.pop()]
    
    active_blackjack[user_id] = {
        "bet": bet, "deck": deck, "player_cards": player_cards,
        "dealer_cards": dealer_cards, "state": "playing"
    }
    
    await callback.message.edit_text(
        f"♠️ <b>BLACKJACK</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n\n"
        f"🃏 <b>Ваши карты:</b> {player_cards} = {sum(player_cards)}\n"
        f"🃏 <b>Карты дилера:</b> [{dealer_cards[0]}, ?]\n\n"
        f"👇 <b>Ваш ход:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎴 ВЗЯТЬ", callback_data="blackjack_hit"),
             InlineKeyboardButton(text="✋ ХВАТИТ", callback_data="blackjack_stand")],
            [InlineKeyboardButton(text="💰 УДВОИТЬ", callback_data="blackjack_double")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "blackjack_hit")
async def blackjack_hit(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_blackjack:
        await callback.answer("Игра не найдена!", show_alert=True)
        return
    
    game = active_blackjack[user_id]
    game["player_cards"].append(game["deck"].pop())
    score = sum(game["player_cards"])
    
    if score > 21:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += game["bet"]
        save_transaction(user_id, -game["bet"], "game_loss", "Blackjack перебор")
        del active_blackjack[user_id]
        await callback.message.edit_text(f"💥 <b>ПЕРЕБОР!</b> {score} > 21\nСтавка проиграна", reply_markup=get_games_keyboard())
    else:
        await callback.message.edit_text(
            f"♠️ <b>BLACKJACK</b>\n\n"
            f"🃏 <b>Ваши карты:</b> {game['player_cards']} = {score}\n"
            f"🃏 <b>Карты дилера:</b> [{game['dealer_cards'][0]}, ?]\n\n"
            f"👇 <b>Продолжаем?</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎴 ВЗЯТЬ", callback_data="blackjack_hit"),
                 InlineKeyboardButton(text="✋ ХВАТИТ", callback_data="blackjack_stand")]
            ])
        )
    await callback.answer()

@dp.callback_query(F.data == "blackjack_stand")
async def blackjack_stand(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_blackjack:
        await callback.answer("Игра не найдена!", show_alert=True)
        return
    
    game = active_blackjack[user_id]
    player_score = sum(game["player_cards"])
    dealer_score = sum(game["dealer_cards"])
    
    while dealer_score < 17:
        game["dealer_cards"].append(game["deck"].pop())
        dealer_score = sum(game["dealer_cards"])
    
    if dealer_score > 21 or player_score > dealer_score:
        win = game["bet"] * 2
        update_balance(user_id, win)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["blackjack_wins"] += 1
        stats["total_won"] += win
        save_transaction(user_id, win, "game_win", f"Blackjack победа")
        result = f"🎉 <b>ВЫИГРЫШ!</b> +{format_stars(win - game['bet'])}"
    elif player_score == dealer_score:
        update_balance(user_id, game["bet"])
        result = f"🔄 <b>НИЧЬЯ!</b> Возврат ставки"
    else:
        result = f"😢 <b>ПРОИГРЫШ!</b> -{format_stars(game['bet'])}"
    
    await callback.message.edit_text(
        f"♠️ <b>BLACKJACK - РЕЗУЛЬТАТ</b>\n\n"
        f"🃏 <b>Ваши карты:</b> {game['player_cards']} = {player_score}\n"
        f"🃏 <b>Карты дилера:</b> {game['dealer_cards']} = {dealer_score}\n\n"
        f"{result}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    del active_blackjack[user_id]
    await callback.answer()


# ===================== ИГРА 9: BACCARAT =====================
@dp.message(F.text == "🎴 Baccarat")
async def baccarat_start(message: Message):
    await message.answer(
        "🎴 <b>BACCARAT</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• Ставь на Игрока, Банкира или Ничью\n"
        "• Выигрыш: Игрок x2, Банкир x1.95, Ничья x8\n\n"
        "💰 Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("baccarat")
    )

@dp.callback_query(F.data.startswith("baccarat_bet_"))
async def baccarat_bet(callback: CallbackQuery, state: FSMContext):
    bet = float(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    await state.update_data(baccarat_bet=bet)
    await state.set_state(GameStates.baccarat_play)
    
    await callback.message.edit_text(
        "🎴 <b>BACCARAT</b>\n\n"
        "На кого ставим?",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👤 ИГРОК (x2)", callback_data="baccarat_player")],
            [InlineKeyboardButton(text="🏦 БАНКИР (x1.95)", callback_data="baccarat_banker")],
            [InlineKeyboardButton(text="🔄 НИЧЬЯ (x8)", callback_data="baccarat_tie")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_games")]
        ])
    )
    await callback.answer()

def get_card_value(card):
    return card if card <= 10 else 0

def calculate_baccarat(cards):
    total = sum(get_card_value(c) for c in cards) % 10
    return total

@dp.callback_query(F.data.startswith("baccarat_"))
async def baccarat_play(callback: CallbackQuery, state: FSMContext):
    bet_type = callback.data.split("_")[-1]
    data = await state.get_data()
    bet = data.get("baccarat_bet")
    user_id = callback.from_user.id
    
    update_balance(user_id, -bet)
    
    deck = [2,3,4,5,6,7,8,9,10,10,10,10] * 4
    random.shuffle(deck)
    
    player_cards = [deck.pop(), deck.pop()]
    banker_cards = [deck.pop(), deck.pop()]
    
    player_score = calculate_baccarat(player_cards)
    banker_score = calculate_baccarat(banker_cards)
    
    if player_score <= 5:
        player_cards.append(deck.pop())
        player_score = calculate_baccarat(player_cards)
    
    if banker_score <= 5:
        banker_cards.append(deck.pop())
        banker_score = calculate_baccarat(banker_cards)
    
    if player_score > banker_score:
        winner = "player"
    elif banker_score > player_score:
        winner = "banker"
    else:
        winner = "tie"
    
    if bet_type == winner:
        if winner == "player":
            win = bet * 2
        elif winner == "banker":
            win = bet * 1.95
        else:
            win = bet * 8
        update_balance(user_id, win)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["baccarat_wins"] += 1
        stats["total_won"] += win
        save_transaction(user_id, win, "game_win", f"Baccarat победа {bet_type}")
        result = f"🎉 <b>ВЫИГРЫШ!</b> +{format_stars(win - bet)}"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", f"Baccarat проигрыш {bet_type}")
        result = f"😢 <b>ПРОИГРЫШ!</b> -{format_stars(bet)}"
    
    await callback.message.edit_text(
        f"🎴 <b>BACCARAT - РЕЗУЛЬТАТ</b>\n\n"
        f"👤 Игрок: {player_cards} = {player_score}\n"
        f"🏦 Банкир: {banker_cards} = {banker_score}\n"
        f"🏆 Победитель: {'Игрок' if winner == 'player' else 'Банкир' if winner == 'banker' else 'Ничья'}\n\n"
        f"{result}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await state.clear()
    await callback.answer()


# ===================== PVP ИГРА 10: COIN DUEL =====================
duel_requests: Dict[int, dict] = {}

@dp.message(F.text == "💰 Coin Duel")
async def duel_start(message: Message):
    await message.answer(
        "💰 <b>COIN DUEL</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• Создай дуэль с другим игроком\n"
        "• Оба игрока делают ставку\n"
        "• Монетка определяет победителя (50/50)\n"
        "• Бот забирает 5% комиссии\n\n"
        "💰 Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("duel")
    )

@dp.callback_query(F.data.startswith("duel_bet_"))
async def duel_create(callback: CallbackQuery, state: FSMContext):
    bet = float(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    await state.update_data(duel_bet=bet)
    await state.set_state(GameStates.duel_bet)
    await callback.message.edit_text(
        "💰 <b>COIN DUEL</b>\n\n"
        "Введи username противника (без @):\n"
        "Пример: <code>username</code>",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

@dp.message(GameStates.duel_bet)
async def duel_opponent(message: Message, state: FSMContext):
    username = message.text.strip().replace("@", "")
    opponent_id = await get_user_id_by_username(username)
    user_id = message.from_user.id
    
    if not opponent_id or opponent_id == user_id:
        await message.answer("❌ Противник не найден или это вы!")
        return
    
    data = await state.get_data()
    bet = data.get("duel_bet")
    
    duel_requests[opponent_id] = {"from": user_id, "bet": bet, "username": message.from_user.username}
    
    await message.answer(
        f"💰 <b>ДУЭЛЬ СОЗДАНА!</b>\n\n"
        f"👤 Противник: @{username}\n"
        f"💰 Ставка: {format_stars(bet)}\n\n"
        f"⏳ Ожидаем согласия...",
        parse_mode=ParseMode.HTML
    )
    
    await bot.send_message(
        opponent_id,
        f"💰 <b>Вам бросили вызов на дуэль!</b>\n\n"
        f"👤 Противник: @{message.from_user.username}\n"
        f"💰 Ставка: {format_stars(bet)}\n\n"
        f"👇 <b>Принять бой?</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"duel_accept_{user_id}_{bet}"),
             InlineKeyboardButton(text="❌ ОТКАЗАТЬ", callback_data="duel_decline")]
        ])
    )
    await state.clear()

@dp.callback_query(F.data.startswith("duel_accept_"))
async def duel_accept(callback: CallbackQuery):
    parts = callback.data.split("_")
    opponent_id = int(parts[2])
    bet = float(parts[3])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)} для ставки!", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    update_balance(opponent_id, -bet)
    
    result = random.choice(["heads", "tails"])
    coin = await callback.message.answer_dice(emoji="🎲")
    
    winner_id = user_id if (coin.dice.value % 2 == 0) else opponent_id
    prize = bet * 2 * 0.95
    
    update_balance(winner_id, prize)
    
    stats_winner = get_user_stats(winner_id)
    stats_winner["games_played"] += 1
    stats_winner["games_won"] += 1
    stats_winner["duel_wins"] += 1
    stats_winner["total_won"] += prize
    save_transaction(winner_id, prize, "game_win", f"Coin Duel победа")
    
    stats_loser = get_user_stats(user_id if winner_id != user_id else opponent_id)
    stats_loser["games_played"] += 1
    stats_loser["total_lost"] += bet
    save_transaction(user_id if winner_id != user_id else opponent_id, -bet, "game_loss", "Coin Duel проигрыш")
    
    await callback.message.edit_text(
        f"💰 <b>COIN DUEL - РЕЗУЛЬТАТ</b>\n\n"
        f"🎲 Монетка: {'Орёл' if result == 'heads' else 'Решка'}\n"
        f"🏆 <b>Победитель:</b> {'Вы!' if winner_id == user_id else 'Противник!'}\n"
        f"💰 Приз: {format_stars(prize)}\n\n"
        f"💰 Ваш новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()


# ===================== PVP ИГРА 11: STEP LADDER =====================
ladder_games: Dict[int, dict] = {}

@dp.message(F.text == "🏆 Step Ladder")
async def ladder_start(message: Message):
    await message.answer(
        "🏆 <b>STEP LADDER</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• 8 игроков → 4 → 2 → 1 победитель\n"
        "• Каждый раунд игра на монетке (50/50)\n"
        "• Победитель забирает весь банк (80% от суммы ставок)\n\n"
        "💰 Выбери сумму ставки для участия:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("ladder")
    )

@dp.callback_query(F.data.startswith("ladder_bet_"))
async def ladder_join(callback: CallbackQuery):
    bet = float(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    
    game_id = None
    for gid, game in ladder_games.items():
        if len(game["players"]) < 8 and game["bet"] == bet:
            game_id = gid
            break
    
    if not game_id:
        game_id = len(ladder_games) + 1
        ladder_games[game_id] = {"bet": bet, "players": [], "state": "waiting"}
    
    ladder_games[game_id]["players"].append(user_id)
    
    if len(ladder_games[game_id]["players"]) == 8:
        await start_ladder(game_id, callback.message)
        await callback.message.edit_text(f"🏆 <b>ИГРА НАЧАТА!</b>\n\nУчастники собраны!", reply_markup=get_games_keyboard())
    else:
        await callback.message.edit_text(
            f"🏆 <b>STEP LADDER</b>\n\n"
            f"💰 Ставка: {format_stars(bet)}\n"
            f"👥 Участников: {len(ladder_games[game_id]['players'])}/8\n\n"
            f"⏳ Ожидаем остальных игроков...",
            parse_mode=ParseMode.HTML
        )
    await callback.answer()

async def start_ladder(game_id: int, message: Message):
    game = ladder_games[game_id]
    players = game["players"]
    current_round = 1
    total_bet = game["bet"] * 8
    prize = total_bet * 0.8
    
    while len(players) > 1:
        winners = []
        for i in range(0, len(players), 2):
            if i + 1 < len(players):
                winner = players[i] if random.choice([True, False]) else players[i + 1]
                winners.append(winner)
                try:
                    await bot.send_message(players[i], f"🏆 Раунд {current_round}: Вы {'победили!' if winner == players[i] else 'проиграли'}")
                    await bot.send_message(players[i+1], f"🏆 Раунд {current_round}: Вы {'победили!' if winner == players[i+1] else 'проиграли'}")
                except:
                    pass
            else:
                winners.append(players[i])
        players = winners
        current_round += 1
    
    winner_id = players[0]
    update_balance(winner_id, prize)
    stats = get_user_stats(winner_id)
    stats["games_played"] += 1
    stats["games_won"] += 1
    stats["ladder_wins"] += 1
    stats["total_won"] += prize
    save_transaction(winner_id, prize, "game_win", f"Step Ladder победа")
    
    try:
        await bot.send_message(winner_id, f"🏆 <b>ПОБЕДА В STEP LADDER!</b>\n\n💰 Выигрыш: {format_stars(prize)}", parse_mode=ParseMode.HTML)
    except:
        pass
    del ladder_games[game_id]


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
        f"💰 Профит бота: {format_stars(bot_stats['profit'])}\n"
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
    await message.answer("Введи username игрока:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True))

@dp.message(F.text == "📢 Рассылка")
async def admin_broadcast(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await state.set_state(GameStates.admin_send_message)
    await message.answer("Отправь сообщение для рассылки:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True))

@dp.message(F.text == "👥 Список пользователей")
async def admin_users_list(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    users_list = [f"@{uname or str(uid)} — {get_user_balance(uid):.2f}⭐️" for uid, uname in users_username.items()]
    text = "👥 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ</b>\n\n" + "\n".join(users_list[:50])
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
            all_txs.append(f"@{uname}: {tx['type']} {tx['amount']:.2f}⭐️")
    
    text = "📜 <b>ПОСЛЕДНИЕ ТРАНЗАКЦИИ</b>\n\n" + "\n".join(all_txs[-30:])
    await message.answer(text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "💾 Сохранить данные")
async def admin_save(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    data = {
        "balance": users_balance, "referrer": users_referrer, "referrals": users_referrals,
        "stats": users_stats, "transactions": transactions, "username": users_username,
        "join_date": users_join_date, "ban": users_ban
    }
    with open("backup.json", "w") as f:
        json.dump(data, f, indent=2)
    await message.answer("✅ Данные сохранены в backup.json")

@dp.message(F.text == "⚙️ Настройки игр")
async def admin_settings(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await message.answer(
        "⚙️ <b>НАСТРОЙКИ ИГР</b>\n\n"
        f"🎯 House Edge: {HOUSE_EDGE*100}%\n"
        f"💰 Min Bet: {MIN_BET}\n"
        f"💰 Max Bet: {MAX_BET}\n"
        f"✨ Max Multiplier: x{MAX_MULTIPLIER}",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text == "🔨 Забанить/Разбанить")
async def admin_ban(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await state.set_state(GameStates.admin_find_user)
    await message.answer("Введи username для бана/разбана:")

@dp.message(F.text == "✅ Верификация")
async def admin_verify(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await state.set_state(GameStates.admin_find_user)
    await message.answer("Введи username для верификации:")

@dp.message(F.text == "💸 Бонусы всем")
async def admin_give_bonus(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await message.answer("Введи сумму бонуса для всех пользователей:")
    await state.set_state(GameStates.admin_change_balance)
    await state.update_data(broadcast_bonus=True)

@dp.message(F.text == "📈 Экспорт данных")
async def admin_export(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    export = {
        "users": {uid: {"balance": bal, "username": users_username.get(uid)} for uid, bal in users_balance.items()},
        "stats": users_stats,
        "profit": bot_stats["profit"]
    }
    with open("export.json", "w") as f:
        json.dump(export, f, indent=2)
    await message.answer_document(types.FSInputFile("export.json"))

@dp.message(F.text == "🔄 Сброс статистики")
async def admin_reset_stats(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    bot_stats["total_bets"] = 0
    bot_stats["total_wagered"] = 0
    bot_stats["total_paid"] = 0
    bot_stats["profit"] = 0
    await message.answer("✅ Статистика бота сброшена!")

@dp.message(F.text == "🎁 Создать промокод")
async def admin_create_promo(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await message.answer("Введи сумму для промокода:")
    await state.set_state(GameStates.admin_add_code)

@dp.message(F.text == "📊 Отчёт по прибыли")
async def admin_profit_report(message: Message):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    
    text = (
        f"📊 <b>ОТЧЁТ ПО ПРИБЫЛИ</b>\n\n"
        f"💰 Общая прибыль: {format_stars(bot_stats['profit'])}\n"
        f"📈 За сегодня: {format_stars(bot_stats['profit'])}\n"
        f"🎯 House Edge: {HOUSE_EDGE*100}%\n"
        f"💸 Выплачено: {format_stars(bot_stats['total_paid'])}\n"
        f"📊 Всего ставок: {bot_stats['total_wagered']:.2f}"
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


# ===================== FSM ОБРАБОТЧИКИ =====================
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
        f"💰 Баланс: {format_stars(get_user_balance(user_id))}\n\n"
        f"Введи сумму (можно с минусом):",
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
    is_broadcast = data.get("broadcast_bonus", False)
    
    try:
        amount = float(message.text.strip())
        
        if is_broadcast:
            for uid in users_balance.keys():
                update_balance(uid, amount)
                try:
                    await bot.send_message(uid, f"🎁 <b>Бонус от администратора!</b>\n+{format_stars(amount)}", parse_mode=ParseMode.HTML)
                except:
                    pass
            await message.answer(f"✅ Бонус {format_stars(amount)} выдан всем пользователям!")
        else:
            new_balance = update_balance(target_user, amount)
            try:
                await bot.send_message(target_user, f"👑 <b>Администратор изменил баланс!</b>\n{'+' if amount>0 else ''}{format_stars(amount)}\n💰 Новый баланс: {format_stars(new_balance)}", parse_mode=ParseMode.HTML)
            except:
                pass
            await message.answer(f"✅ Баланс @{target_username} изменён на {format_stars(amount)}")
    except:
        await message.answer("❌ Введи число!")
    
    await state.clear()
    await message.answer("✅ Готово!", reply_markup=get_admin_panel_keyboard())

@dp.message(GameStates.admin_send_message)
async def admin_broadcast_msg(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=get_admin_panel_keyboard())
        return
    
    success = 0
    for uid in users_balance.keys():
        try:
            await bot.copy_message(uid, message.chat.id, message.message_id)
            success += 1
            await asyncio.sleep(0.05)
        except:
            pass
    
    await state.clear()
    await message.answer(f"✅ Рассылка завершена! Доставлено: {success}", reply_markup=get_admin_panel_keyboard())


# ===================== ПЛАТЕЖИ =====================
async def create_stars_invoice(message: Message, user_id: int, amount: int):
    title = "⭐️ Пополнение StarPlay"
    payload = f"starplay_{user_id}_{amount}_{int(datetime.now().timestamp())}"
    prices = [LabeledPrice(label="Telegram Stars", amount=amount)]
    await bot.send_invoice(
        chat_id=user_id, title=title, description=f"Пополнение на {amount} Stars",
        payload=payload, provider_token="", currency="XTR", prices=prices,
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
            try:
                await bot.send_message(referrer, f"🎉 <b>Реферальный бонус!</b>\n+{format_stars(bonus)}", parse_mode=ParseMode.HTML)
            except:
                pass
    
    await message.answer(f"✅ <b>Пополнение выполнено!</b>\n+{format_stars(amount)}\n💰 Новый баланс: {format_stars(new_balance)}", parse_mode=ParseMode.HTML)

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


# ===================== ЗАПУСК =====================
async def main():
    logger.info("🚀 StarPlay Casino Bot запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())