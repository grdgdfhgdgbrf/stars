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
duel_requests: Dict[int, dict] = {}
ladder_games: Dict[int, dict] = {}

# Статистика бота
bot_stats = {
    "total_bets": 0,
    "total_wagered": 0.0,
    "total_paid": 0.0,
    "profit": 0.0
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# ===================== FSM СОСТОЯНИЯ =====================
class GameStates(StatesGroup):
    # Crash
    crash_bet = State()
    crash_playing = State()
    
    # Duel
    duel_bet = State()
    duel_waiting = State()
    
    # Ladder
    ladder_bet = State()
    
    # Deposit
    waiting_deposit = State()
    
    # Admin
    admin_find_user = State()
    admin_change_balance = State()
    admin_send_message = State()
    admin_broadcast = State()


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
            "crash_wins": 0, "duel_wins": 0, "ladder_wins": 0
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

def get_games_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📈 Classic Crash")
    builder.button(text="💰 Coin Duel")
    builder.button(text="🏆 Step Ladder")
    builder.button(text="🔙 Главное меню")
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
    builder.button(text="🔨 Забанить/Разбанить")
    builder.button(text="💸 Бонус всем")
    builder.button(text="📈 Экспорт данных")
    builder.button(text="🔄 Сброс статистики")
    builder.button(text="🔙 В главное меню")
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
        f"{get_random_emoji()} <b>Играй и выигрывай Telegram Stars!</b>\n\n"
        f"<b>🎮 Доступные игры:</b>\n"
        f"📈 Classic Crash — растущий множитель до взрыва\n"
        f"💰 Coin Duel — дуэль 1x1 на монетке\n"
        f"🏆 Step Ladder — турнир 8 игроков\n\n"
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
        "📈 Classic Crash — забери множитель до взрыва\n"
        "💰 Coin Duel — сразись с другим игроком\n"
        "🏆 Step Ladder — турнир на вылет\n\n"
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
        await message.answer("🎁 <b>Ты уже получил сегодняшний бонус!</b>", parse_mode=ParseMode.HTML)
        return
    bonus_amount = random.uniform(5, 15)
    update_balance(user_id, bonus_amount)
    users_daily_bonus[user_id] = today
    save_transaction(user_id, bonus_amount, "daily_bonus", "Ежедневный бонус")
    await message.answer(f"🎉 <b>Бонус получен!</b>\n+{format_stars(bonus_amount)}", parse_mode=ParseMode.HTML)


# ===================== ИГРА 1: CLASSIC CRASH =====================
@dp.message(F.text == "📈 Classic Crash")
async def classic_crash_start(message: Message):
    await message.answer(
        "📈 <b>Classic Crash</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• Множитель растёт от x1.00\n"
        "• Нужно успеть нажать 'ЗАБРАТЬ' до взрыва\n"
        "• Чем дольше ждёшь — тем выше множитель\n"
        "• Если не забрать — ставка сгорает\n\n"
        "💰 Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("crash")
    )

@dp.callback_query(F.data.startswith("crash_bet_"))
async def crash_bet(callback: CallbackQuery, state: FSMContext):
    bet = float(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    await state.update_data(crash_bet=bet)
    await state.set_state(GameStates.crash_playing)
    await callback.message.delete()
    
    await callback.message.answer(
        f"📈 <b>Classic Crash - ИГРА</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"📈 Множитель: <b>x1.00</b>\n\n"
        f"👇 <b>Жди роста и забери выигрыш!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 ЗАБРАТЬ", callback_data="crash_cashout")]
        ])
    )
    
    asyncio.create_task(run_crash_game(callback.message, bet, state))
    await callback.answer()

async def run_crash_game(message: Message, bet: float, state: FSMContext):
    crash_point = random.uniform(1.01, 10.0)
    multiplier = 1.0
    msg = None
    
    while multiplier < crash_point:
        multiplier = round(multiplier + 0.05, 2)
        try:
            if msg:
                await msg.delete()
            msg = await message.edit_text(
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
    
    await message.edit_text(
        f"📈 <b>Classic Crash - ВЗРЫВ!</b>\n\n"
        f"💰 Ставка: {format_stars(bet)}\n"
        f"📈 Множитель: x{multiplier}\n\n"
        f"💥 <b>КРАХ! Ставка сгорела!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await state.clear()

@dp.callback_query(F.data == "crash_cashout")
async def crash_cashout(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet = data.get("crash_bet")
    user_id = callback.from_user.id
    
    if not bet:
        await callback.answer("Игра не найдена!", show_alert=True)
        return
    
    multiplier = 1.0
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


# ===================== ИГРА 2: COIN DUEL =====================
@dp.message(F.text == "💰 Coin Duel")
async def duel_start(message: Message, state: FSMContext):
    await message.answer(
        "💰 <b>COIN DUEL</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• Создай дуэль с другим игроком\n"
        "• Оба делают одинаковую ставку\n"
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
    await state.set_state(GameStates.duel_waiting)
    await callback.message.edit_text(
        "💰 <b>COIN DUEL</b>\n\n"
        "Введи username противника (без @):",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

@dp.message(GameStates.duel_waiting)
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
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    
    await bot.send_message(
        opponent_id,
        f"💰 <b>Вам бросили вызов на дуэль!</b>\n\n"
        f"👤 Противник: @{message.from_user.username}\n"
        f"💰 Ставка: {format_stars(bet)}\n\n"
        f"👇 <b>Принять бой?</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"duel_accept_{user_id}_{bet}")],
            [InlineKeyboardButton(text="❌ ОТКАЗАТЬ", callback_data="duel_decline")]
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
    
    # Бросок монетки через dice
    dice_msg = await callback.message.answer_dice(emoji="🎲")
    result = "heads" if dice_msg.dice.value % 2 == 0 else "tails"
    
    winner_id = user_id if (dice_msg.dice.value % 2 == 0) else opponent_id
    prize = bet * 2 * 0.95
    
    update_balance(winner_id, prize)
    
    stats_winner = get_user_stats(winner_id)
    stats_winner["games_played"] += 1
    stats_winner["games_won"] += 1
    stats_winner["duel_wins"] += 1
    stats_winner["total_won"] += prize
    save_transaction(winner_id, prize, "game_win", "Coin Duel победа")
    
    await callback.message.edit_text(
        f"💰 <b>COIN DUEL - РЕЗУЛЬТАТ</b>\n\n"
        f"🎲 Монетка: {'Орёл' if result == 'heads' else 'Решка'}\n"
        f"🏆 <b>Победитель:</b> {'Вы!' if winner_id == user_id else 'Противник!'}\n"
        f"💰 Приз: {format_stars(prize)}\n\n"
        f"💰 Ваш баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "duel_decline")
async def duel_decline(callback: CallbackQuery):
    await callback.message.edit_text("❌ Вы отказались от дуэли.", reply_markup=get_games_keyboard())
    await callback.answer()


# ===================== ИГРА 3: STEP LADDER =====================
@dp.message(F.text == "🏆 Step Ladder")
async def ladder_start(message: Message, state: FSMContext):
    await message.answer(
        "🏆 <b>STEP LADDER</b>\n\n"
        "📋 <b>Правила:</b>\n"
        "• 8 игроков → 4 → 2 → 1 победитель\n"
        "• Каждый раунд игра на монетке\n"
        "• Победитель забирает 80% от банка\n\n"
        "💰 Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("ladder")
    )

@dp.callback_query(F.data.startswith("ladder_bet_"))
async def ladder_join(callback: CallbackQuery, state: FSMContext):
    bet = float(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    
    # Ищем или создаём игру
    game_id = None
    for gid, game in ladder_games.items():
        if len(game["players"]) < 8 and game["bet"] == bet and game["state"] == "waiting":
            game_id = gid
            break
    
    if not game_id:
        game_id = len(ladder_games) + 1
        ladder_games[game_id] = {"bet": bet, "players": [], "state": "waiting", "bets": {}}
    
    ladder_games[game_id]["players"].append(user_id)
    ladder_games[game_id]["bets"][user_id] = bet
    
    if len(ladder_games[game_id]["players"]) == 8:
        await start_ladder(game_id, callback.message)
        await callback.message.edit_text(f"🏆 <b>ИГРА НАЧАТА!</b>\n\nУчастники собраны!", reply_markup=get_games_keyboard())
    else:
        await callback.message.edit_text(
            f"🏆 <b>STEP LADDER</b>\n\n"
            f"💰 Ставка: {format_stars(bet)}\n"
            f"👥 Участников: {len(ladder_games[game_id]['players'])}/8\n\n"
            f"⏳ Ожидаем остальных...",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Обновить", callback_data="ladder_refresh")]
            ])
        )
    await callback.answer()

@dp.callback_query(F.data == "ladder_refresh")
async def ladder_refresh(callback: CallbackQuery):
    await callback.answer("Ожидаем игроков...", show_alert=True)

async def start_ladder(game_id: int, message: Message):
    game = ladder_games[game_id]
    players = game["players"].copy()
    total_bet = game["bet"] * 8
    prize = total_bet * 0.8
    current_round = 1
    
    for p in players:
        await bot.send_message(p, f"🏆 <b>STEP LADDER НАЧАЛСЯ!</b>\n\nВаша ставка: {format_stars(game['bet'])}", parse_mode=ParseMode.HTML)
    
    while len(players) > 1:
        winners = []
        for i in range(0, len(players), 2):
            if i + 1 < len(players):
                dice = await bot.send_dice(players[i], emoji="🎲")
                winner = players[i] if dice.dice.value % 2 == 0 else players[i + 1]
                winners.append(winner)
                await bot.send_message(players[i], f"🏆 <b>Раунд {current_round}</b>: {'ПОБЕДА!' if winner == players[i] else 'ПРОИГРЫШ'}", parse_mode=ParseMode.HTML)
                await bot.send_message(players[i+1], f"🏆 <b>Раунд {current_round}</b>: {'ПОБЕДА!' if winner == players[i+1] else 'ПРОИГРЫШ'}", parse_mode=ParseMode.HTML)
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
    save_transaction(winner_id, prize, "game_win", "Step Ladder победа")
    
    await bot.send_message(winner_id, f"🏆 <b>ПОБЕДА В STEP LADDER!</b>\n\n💰 Выигрыш: {format_stars(prize)}", parse_mode=ParseMode.HTML)
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
        f"📊 Ставок: {bot_stats['total_wagered']:.2f}\n"
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

@dp.message(F.text == "🔨 Забанить/Разбанить")
async def admin_ban(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await state.set_state(GameStates.admin_find_user)
    await state.update_data(ban_mode=True)
    await message.answer("Введи username для бана/разбана:")

@dp.message(F.text == "💸 Бонус всем")
async def admin_give_bonus(message: Message, state: FSMContext):
    username = message.from_user.username or ""
    if not is_admin(username):
        return
    await state.update_data(broadcast_bonus=True)
    await state.set_state(GameStates.admin_change_balance)
    await message.answer("Введи сумму бонуса для всех пользователей:")

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

@dp.message(F.text == "🔙 В главное меню")
async def back_to_main(message: Message):
    await message.answer("🌟 <b>Главное меню</b>", parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard())


# ===================== АДМИН FSM ОБРАБОТЧИКИ =====================
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
    
    data = await state.get_data()
    ban_mode = data.get("ban_mode", False)
    
    if ban_mode:
        users_ban[user_id] = not users_ban.get(user_id, False)
        status = "забанен" if users_ban[user_id] else "разбанен"
        await message.answer(f"✅ Пользователь @{input_text} {status}!", reply_markup=get_admin_panel_keyboard())
        await state.clear()
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
            count = 0
            for uid in users_balance.keys():
                if not users_ban.get(uid, False):
                    update_balance(uid, amount)
                    await bot.send_message(uid, f"🎁 <b>Бонус от администратора!</b>\n+{format_stars(amount)}", parse_mode=ParseMode.HTML)
                    count += 1
                    await asyncio.sleep(0.05)
            await message.answer(f"✅ Бонус {format_stars(amount)} выдан {count} пользователям!")
        else:
            new_balance = update_balance(target_user, amount)
            await bot.send_message(target_user, f"👑 <b>Администратор изменил баланс!</b>\n{'+' if amount>0 else ''}{format_stars(amount)}\n💰 Новый баланс: {format_stars(new_balance)}", parse_mode=ParseMode.HTML)
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
        if not users_ban.get(uid, False):
            try:
                await bot.copy_message(uid, message.chat.id, message.message_id)
                success += 1
                await asyncio.sleep(0.05)
            except:
                pass
    
    await state.clear()
    await message.answer(f"✅ Рассылка завершена! Доставлено: {success}", reply_markup=get_admin_panel_keyboard())


# ===================== НАВИГАЦИЯ =====================
@dp.callback_query(F.data == "back_to_games")
async def back_to_games_callback(callback: CallbackQuery):
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
            await bot.send_message(referrer, f"🎉 <b>Реферальный бонус!</b>\n+{format_stars(bonus)}", parse_mode=ParseMode.HTML)
    
    await message.answer(f"✅ <b>Пополнение выполнено!</b>\n+{format_stars(amount)}\n💰 Новый баланс: {format_stars(new_balance)}", parse_mode=ParseMode.HTML)

@dp.callback_query(F.data.startswith("deposit_"))
async def deposit_amount(callback: CallbackQuery, state: FSMContext):
    amount_str = callback.data.split("_")[1]
    if amount_str == "custom":
        await callback.message.answer("✏️ Введи сумму (1-10000):")
        await state.set_state(GameStates.waiting_deposit)
        await callback.answer()
        return
    amount = int(amount_str)
    await create_stars_invoice(callback.message, callback.from_user.id, amount)
    await callback.answer()

@dp.message(GameStates.waiting_deposit)
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