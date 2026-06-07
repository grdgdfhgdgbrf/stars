import asyncio
import hashlib
import logging
import random
from datetime import datetime
from typing import Dict, List

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    LabeledPrice, Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, PreCheckoutQuery, SuccessfulPayment
)
from aiogram.enums import ParseMode

# ===================== КОНФИГУРАЦИЯ =====================
BOT_TOKEN = "8251949164:AAE1fYvR_cMK7PnykcqpCxaXS9vIWxo1VjQ"
ADMIN_IDS = [5356400377]

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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# ===================== FSM =====================
class GameStates(StatesGroup):
    custom_deposit = State()
    roulette_bet = State()
    darts_bet = State()
    football_bet = State()
    bowling_bet = State()
    basketball_bet = State()
    mines_game = State()
    pyramid_game = State()
    slots_game = State()


# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
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


# ===================== КЛАВИАТУРЫ =====================
def get_main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    balance = get_user_balance(user_id)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💰 {balance} Stars", callback_data="balance_info")],
        [InlineKeyboardButton(text="⭐️ Пополнить", callback_data="deposit"),
         InlineKeyboardButton(text="🎮 Игры", callback_data="games_menu")],
        [InlineKeyboardButton(text="👥 Рефералы", callback_data="referrals"),
         InlineKeyboardButton(text="🏆 Топ", callback_data="top")],
        [InlineKeyboardButton(text="📊 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="🎁 Бонус", callback_data="daily_bonus")]
    ])

def get_games_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Рулетка", callback_data="game_roulette"),
         InlineKeyboardButton(text="🎯 Дартс", callback_data="game_darts")],
        [InlineKeyboardButton(text="⚽️ Футбол", callback_data="game_football"),
         InlineKeyboardButton(text="🎳 Боулинг", callback_data="game_bowling")],
        [InlineKeyboardButton(text="🏀 Баскетбол", callback_data="game_basketball"),
         InlineKeyboardButton(text="💣 Мины", callback_data="game_mines")],
        [InlineKeyboardButton(text="🏛 Пирамида", callback_data="game_pyramid"),
         InlineKeyboardButton(text="🎰 Слоты", callback_data="game_slots")],
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="main_menu")]
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

def get_bet_keyboard(game: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐️ 5", callback_data=f"{game}_bet_5"),
         InlineKeyboardButton(text="⭐️ 10", callback_data=f"{game}_bet_10"),
         InlineKeyboardButton(text="⭐️ 25", callback_data=f"{game}_bet_25")],
        [InlineKeyboardButton(text="⭐️ 50", callback_data=f"{game}_bet_50"),
         InlineKeyboardButton(text="⭐️ 100", callback_data=f"{game}_bet_100"),
         InlineKeyboardButton(text="⭐️ 250", callback_data=f"{game}_bet_250")],
        [InlineKeyboardButton(text="◀️ Назад к играм", callback_data="games_menu")]
    ])

def get_mines_board_keyboard(board, revealed, bet):
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
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="games_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_slots_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Крутить (5⭐️)", callback_data="slots_spin_5"),
         InlineKeyboardButton(text="🎰 Крутить (10⭐️)", callback_data="slots_spin_10")],
        [InlineKeyboardButton(text="🎰 Крутить (25⭐️)", callback_data="slots_spin_25"),
         InlineKeyboardButton(text="🎰 Крутить (50⭐️)", callback_data="slots_spin_50")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="games_menu")]
    ])


# ===================== КОМАНДЫ =====================
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    # Реферальная логика (если есть параметр start=ref_...)
    if " " in message.text:
        param = message.text.split()[1]
        if param.startswith("ref_"):
            try:
                referrer_id = int(param[4:])  # упрощённо; в реальности нужно декодировать
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
    await message.answer(
        f"🌟 <b>Добро пожаловать в StarPlay!</b> 🌟\n\n"
        f"{get_random_emoji()} Играй на Telegram Stars и выигрывай!\n\n"
        f"<b>🔥 Что тебя ждет:</b>\n"
        f"• 8 увлекательных игр\n"
        f"• Реферальная система — зарабатывай с друзьями\n"
        f"• Ежедневные бонусы\n"
        f"• Рейтинг лучших игроков\n\n"
        f"<b>💫 Как начать:</b>\n"
        f"1️⃣ Пополни баланс через Telegram Stars\n"
        f"2️⃣ Выбери игру\n"
        f"3️⃣ Делай ставки и выигрывай!\n\n"
        f"👇 <i>Нажми на кнопку меню!</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(user_id)
    )

@dp.message(Command("balance"))
async def cmd_balance(message: Message):
    user_id = message.from_user.id
    await message.answer(
        f"💰 <b>Твой баланс:</b> {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(user_id)
    )

@dp.message(Command("bonus"))
async def cmd_bonus(message: Message):
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
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(user_id)
    )


# ===================== ИГРЫ =====================
# ---------- РУЛЕТКА ----------
roulette_numbers = list(range(0, 37))
roulette_colors = {0: "green"}
for i in range(1, 37):
    roulette_colors[i] = "red" if i % 2 == 1 else "black"

@dp.callback_query(F.data == "game_roulette")
async def roulette_start(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎰 <b>Рулетка</b>\n\nВыбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("roulette")
    )
    await callback.answer()

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
        [InlineKeyboardButton(text="◀️ Назад", callback_data="games_menu")]
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
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await state.clear()
    await callback.answer()

# ---------- ДАРТС ----------
@dp.callback_query(F.data == "game_darts")
async def darts_start(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎯 <b>Дартс</b>\n\nПравила: 3 броска, нужно набрать ≥150 очков.\nВыбери ставку:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("darts")
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("darts_bet_"))
async def darts_play(callback: CallbackQuery):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    update_balance(user_id, -bet)
    total = 0
    throws = []
    for _ in range(3):
        r = random.random()
        if r < 0.6:
            score = random.randint(1, 20)
        elif r < 0.85:
            score = 25
        elif r < 0.95:
            score = random.choice([40,45,50])
        else:
            score = 50
        throws.append(score)
        total += score
    if total >= 150:
        mult = 2 if total >= 200 else 1.5
        win_amount = int(bet * mult)
        update_balance(user_id, win_amount)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["darts_wins"] += 1
        stats["total_won"] += win_amount
        save_transaction(user_id, win_amount, "game_win", f"Дартс {total} очков")
        res = f"🎯 <b>ПОБЕДА!</b> +{format_stars(win_amount)}"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", f"Дартс {total} очков")
        res = f"😢 <b>Не повезло</b> -{format_stars(bet)}"
    await callback.message.edit_text(
        f"🎯 <b>Дартс</b>\n\nБроски: {throws[0]}, {throws[1]}, {throws[2]}\n<b>Всего: {total}</b>\n\n{res}\n\n💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()

# ---------- ФУТБОЛ ----------
@dp.callback_query(F.data == "game_football")
async def football_start(callback: CallbackQuery):
    await callback.message.edit_text(
        "⚽️ <b>Футбол</b>\n\n3 пенальти. Для выигрыша нужно забить 2+ гола.\nВыбери ставку:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("football")
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("football_bet_"))
async def football_play(callback: CallbackQuery):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    update_balance(user_id, -bet)
    goals = 0
    res_list = []
    for _ in range(3):
        if random.random() < 0.4:
            goals += 1
            res_list.append("⚽️ ГОЛ!")
        else:
            res_list.append("🧤 Сейв")
    if goals >= 2:
        mult = {2:2, 3:3}.get(goals,2)
        win_amount = bet * mult
        update_balance(user_id, win_amount)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["football_wins"] += 1
        stats["total_won"] += win_amount
        save_transaction(user_id, win_amount, "game_win", f"Футбол {goals} гола")
        res = f"⚽️ <b>ПОБЕДА!</b> +{format_stars(win_amount)}"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", f"Футбол {goals} гола")
        res = f"😢 <b>Поражение</b> -{format_stars(bet)}"
    await callback.message.edit_text(
        f"⚽️ <b>Футбол</b>\n\n{res_list[0]}\n{res_list[1]}\n{res_list[2]}\n\n<b>Голов: {goals}</b>\n\n{res}\n\n💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()

# ---------- БОУЛИНГ ----------
@dp.callback_query(F.data == "game_bowling")
async def bowling_start(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎳 <b>Боулинг</b>\n\nСтрайк (10) → x3, Спэр → x2, 8-9 очков → x1.2.\nВыбери ставку:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("bowling")
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("bowling_bet_"))
async def bowling_play(callback: CallbackQuery):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    update_balance(user_id, -bet)
    first = random.randint(0,10)
    if first == 10:
        mult = 3
        total = 10
        msg = f"🎳 Страйк! 💥"
    else:
        second = random.randint(0, 10-first)
        total = first+second
        if total == 10:
            mult = 2
            msg = f"🎳 Спэр! {first}+{second}"
        elif total >= 8:
            mult = 1.2
            msg = f"🎳 {total} кегль"
        else:
            mult = 0
            msg = f"🎳 {total} кегль — неудача"
    if mult > 0:
        win_amount = int(bet * mult)
        update_balance(user_id, win_amount)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["bowling_wins"] += 1
        stats["total_won"] += win_amount
        save_transaction(user_id, win_amount, "game_win", f"Боулинг {total} кегль")
        res = f"🏆 <b>Выигрыш x{mult}</b> +{format_stars(win_amount)}"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", f"Боулинг {total} кегль")
        res = f"😢 <b>Проигрыш</b> -{format_stars(bet)}"
    await callback.message.edit_text(
        f"{msg}\n\n{res}\n\n💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()

# ---------- БАСКЕТБОЛ ----------
@dp.callback_query(F.data == "game_basketball")
async def basketball_start(callback: CallbackQuery):
    await callback.message.edit_text(
        "🏀 <b>Баскетбол</b>\n\n5 трёхочковых бросков. 3+ попаданий = x2, 5 попаданий = x2.5.\nВыбери ставку:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("basketball")
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("basketball_bet_"))
async def basketball_play(callback: CallbackQuery):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    if get_user_balance(user_id) < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}", show_alert=True)
        return
    update_balance(user_id, -bet)
    hits = 0
    results = []
    for _ in range(5):
        if random.random() < 0.4:
            hits += 1
            results.append("🏀 +1")
        else:
            results.append("❌")
    if hits >= 3:
        mult = 2.5 if hits == 5 else 2
        win_amount = int(bet * mult)
        update_balance(user_id, win_amount)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["basketball_wins"] += 1
        stats["total_won"] += win_amount
        save_transaction(user_id, win_amount, "game_win", f"Баскетбол {hits}/5")
        res = f"🏀 <b>Победа! x{mult}</b> +{format_stars(win_amount)}"
    else:
        win_amount = int(bet * hits * 0.3)
        if win_amount > 0:
            update_balance(user_id, win_amount)
            stats = get_user_stats(user_id)
            stats["games_played"] += 1
            stats["total_won"] += win_amount
            save_transaction(user_id, win_amount, "game_win", f"Баскетбол {hits}/5")
            res = f"🏀 <b>{hits} попаданий</b> +{format_stars(win_amount)}"
        else:
            stats = get_user_stats(user_id)
            stats["games_played"] += 1
            stats["total_lost"] += bet
            save_transaction(user_id, -bet, "game_loss", f"Баскетбол {hits}/5")
            res = f"😢 <b>Неудача</b> -{format_stars(bet)}"
    await callback.message.edit_text(
        f"🏀 <b>Баскетбол</b>\n\nБроски: {', '.join(results)}\nПопаданий: {hits}/5\n\n{res}\n\n💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()

# ---------- МИНЫ ----------
active_mines_games: Dict[int, dict] = {}

@dp.callback_query(F.data == "game_mines")
async def mines_start(callback: CallbackQuery):
    await callback.message.edit_text(
        "💣 <b>МИНЫ</b>\n\nПоле 5x5, 5 мин. Каждая найденная 💎 увеличивает множитель x1.2.\nВыбери ставку:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("mines")
    )
    await callback.answer()

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
        x, y = random.randint(0,4), random.randint(0,4)
        if board[x][y] == "💎":
            board[x][y] = "💣"
            mines += 1
    active_mines_games[user_id] = {
        "board": board,
        "revealed": [[False]*5 for _ in range(5)],
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
            parse_mode=ParseMode.HTML,
            reply_markup=get_games_keyboard()
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
                parse_mode=ParseMode.HTML,
                reply_markup=get_games_keyboard()
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
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()

# ---------- ПИРАМИДА ----------
active_pyramids: Dict[int, dict] = {}

@dp.callback_query(F.data == "game_pyramid")
async def pyramid_start(callback: CallbackQuery):
    await callback.message.edit_text(
        "🏛 <b>Пирамида</b>\n\n5 уровней, каждый шаг удваивает выигрыш (50% успеха).\nВыбери начальную ставку:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("pyramid")
    )
    await callback.answer()

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
        [InlineKeyboardButton(text="◀️ Выйти", callback_data="games_menu")]
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
                parse_mode=ParseMode.HTML,
                reply_markup=get_games_keyboard()
            )
        else:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬆️ Подняться (x2)", callback_data="pyramid_up")],
                [InlineKeyboardButton(text="💰 Забрать выигрыш", callback_data="pyramid_cashout")],
                [InlineKeyboardButton(text="◀️ Выйти", callback_data="games_menu")]
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
            parse_mode=ParseMode.HTML,
            reply_markup=get_games_keyboard()
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
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()

# ---------- СЛОТЫ ----------
slot_symbols = ["🍒","🍊","🍋","💎","7️⃣","🎰","⭐️","💫"]
slot_payouts = {
    ("🍒","🍒","🍒"):5, ("🍊","🍊","🍊"):7, ("🍋","🍋","🍋"):10,
    ("💎","💎","💎"):15, ("7️⃣","7️⃣","7️⃣"):25, ("🎰","🎰","🎰"):50,
    ("⭐️","⭐️","⭐️"):30, ("💫","💫","💫"):20
}

@dp.callback_query(F.data == "game_slots")
async def slots_start(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎰 <b>Слоты</b>\n\nКрути барабаны и собирай комбинации!\nВыбери ставку:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_slots_keyboard()
    )
    await callback.answer()

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
        parse_mode=ParseMode.HTML,
        reply_markup=get_slots_keyboard()
    )
    await callback.answer()


# ===================== ПРОЧИЕ ОБРАБОТЧИКИ =====================
@dp.callback_query(F.data == "referrals")
async def show_referrals(callback: CallbackQuery):
    user_id = callback.from_user.id
    ref_link = generate_referral_link(user_id)
    ref_count = len(users_referrals.get(user_id, []))
    text = (
        f"👥 <b>Реферальная система</b>\n\n"
        f"Приглашено: {ref_count}\n"
        f"Твоя ссылка:\n<code>{ref_link}</code>\n\n"
        f"Друг получает +{REFERRAL_SIGNUP_BONUS} Stars, ты +{REFERRAL_INVITE_BONUS} Stars и 10% с его пополнений."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={ref_link}&text=StarPlay — играй и зарабатывай Stars!")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "top")
async def show_top(callback: CallbackQuery):
    sorted_users = sorted(users_balance.items(), key=lambda x: x[1], reverse=True)[:15]
    if not sorted_users:
        await callback.answer("Пока никого нет", show_alert=True)
        return
    top_text = "🏆 <b>ТОП-15 StarPlay</b>\n\n"
    for idx, (uid, bal) in enumerate(sorted_users, 1):
        medal = {1:"🥇",2:"🥈",3:"🥉"}.get(idx, f"{idx}.")
        try:
            user = await bot.get_chat(uid)
            name = user.first_name[:20] or str(uid)
        except:
            name = str(uid)
        top_text += f"{medal} <b>{name}</b> — {bal} ⭐️\n"
    await callback.message.edit_text(top_text, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard(callback.from_user.id))
    await callback.answer()

@dp.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    uid = callback.from_user.id
    stats = get_user_stats(uid)
    wr = (stats['games_won'] / max(stats['games_played'],1)) * 100
    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"💰 Баланс: {format_stars(get_user_balance(uid))}\n"
        f"🎮 Игр сыграно: {stats['games_played']}\n🏆 Побед: {stats['games_won']} ({wr:.1f}%)\n"
        f"💎 Выиграно: {format_stars(stats['total_won'])}\n💸 Проиграно: {format_stars(stats['total_lost'])}"
    )
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard(uid))
    await callback.answer()

@dp.callback_query(F.data == "balance_info")
async def balance_info(callback: CallbackQuery):
    await callback.answer(f"Баланс: {get_user_balance(callback.from_user.id)} Stars", show_alert=True)

@dp.callback_query(F.data == "daily_bonus")
async def daily_bonus_button(callback: CallbackQuery):
    await cmd_bonus(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "games_menu")
async def games_menu(callback: CallbackQuery):
    await callback.message.edit_text("🎮 <b>Выбери игру</b>", parse_mode=ParseMode.HTML, reply_markup=get_games_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "deposit")
async def deposit_menu(callback: CallbackQuery):
    await callback.message.edit_text("⭐️ <b>Пополнить Stars</b>", parse_mode=ParseMode.HTML, reply_markup=get_deposit_keyboard())
    await callback.answer()

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

@dp.callback_query(F.data == "main_menu")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🌟 <b>StarPlay — Главное меню</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(callback.from_user.id)
    )
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
    await message.answer(
        f"✅ Пополнение +{format_stars(amount)}\n💰 Новый баланс: {format_stars(new_balance)}",
        reply_markup=get_main_keyboard(user_id)
    )


# ===================== ЗАПУСК =====================
async def main():
    logger.info("🚀 StarPlay Bot запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    