import asyncio
import hashlib
import json
import logging
import random
import aiohttp
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    LabeledPrice, Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, PreCheckoutQuery, SuccessfulPayment,
    FSInputFile, URLInputFile
)
from aiogram.enums import ParseMode

# ===================== КОНФИГУРАЦИЯ =====================
BOT_TOKEN = "8251949164:AAE1fYvR_cMK7PnykcqpCxaXS9vIWxo1VjQ"
ADMIN_IDS = [5356400377]  # Ваш Telegram ID

# Настройки реферальной системы
REFERRAL_BONUS_PERCENT = 10  # % от пополнения реферала
REFERRAL_SIGNUP_BONUS = 5    # Бонус за регистрацию по рефералке
REFERRAL_INVITE_BONUS = 10   # Бонус пригласившему за регистрацию реферала

# Настройки Botohub API
BOTOHUB_TOKEN = "2c69045b-0cf6-49dc-a9a2-2bb0d563ad20"  # Токен после регистрации на botohub.me
BOTOHUB_API_URL = "https://botohub.me/get-tasks"

# Обязательная подписка на ваш канал
REQUIRED_CHANNELS = ["@ваш_канал"]  # Список каналов для обязательной подписки

# Хранилища данных
users_balance: Dict[int, int] = {}
users_referrer: Dict[int, int] = {}           # user_id -> кто пригласил
users_referrals: Dict[int, List[int]] = {}    # user_id -> список приглашенных
users_stats: Dict[int, dict] = {}             # статистика игр
users_daily_bonus: Dict[int, str] = {}        # дата последнего бонуса
pending_payments: Dict[str, dict] = {}
transactions: Dict[int, list] = {}
user_subscription_status: Dict[int, bool] = {}  # Кэш статуса подписки пользователя

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ===================== FSM СОСТОЯНИЯ =====================
class GameStates(StatesGroup):
    roulette_bet = State()
    darts_bet = State()
    football_bet = State()
    bowling_bet = State()
    basketball_bet = State()
    mines_game = State()
    pyramid_game = State()
    slots_game = State()
    waiting_for_amount = State()
    transfer_amount = State()
    custom_deposit = State()


# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
def generate_referral_link(user_id: int) -> str:
    """Генерация реферальной ссылки"""
    code = hashlib.md5(f"starplay_{user_id}_{datetime.now().date()}".encode()).hexdigest()[:8]
    return f"https://t.me/{bot.username}?start=ref_{code}"

def get_user_stats(user_id: int) -> dict:
    """Получить статистику игрока"""
    if user_id not in users_stats:
        users_stats[user_id] = {
            "games_played": 0,
            "games_won": 0,
            "total_won": 0,
            "total_lost": 0,
            "roulette_wins": 0,
            "darts_wins": 0,
            "football_wins": 0,
            "bowling_wins": 0,
            "basketball_wins": 0,
            "mines_wins": 0,
            "pyramid_wins": 0,
            "slots_wins": 0
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
        "amount": amount,
        "type": tx_type,
        "details": details,
        "timestamp": datetime.now().isoformat()
    })

def format_stars(amount: int) -> str:
    return f"⭐️ {amount} Stars"

def get_random_emoji() -> str:
    """Случайный эмодзи для настроения"""
    emojis = ["🎲", "🎯", "⚡️", "💫", "🌟", "⭐️", "✨", "🎮", "🎰", "🔥"]
    return random.choice(emojis)


# ===================== ПРОВЕРКА ПОДПИСКИ =====================
async def check_user_subscription(user_id: int) -> bool:
    """
    Проверяет, подписан ли пользователь на обязательные каналы.
    Возвращает True, если подписка есть, иначе False.
    """
    # Проверяем кэш
    if user_id in user_subscription_status:
        return user_subscription_status[user_id]
    
    for channel in REQUIRED_CHANNELS:
        try:
            chat_member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if chat_member.status not in ["creator", "administrator", "member"]:
                user_subscription_status[user_id] = False
                return False
        except Exception as e:
            logger.error(f"Error checking subscription for user {user_id} on channel {channel}: {e}")
            # Если бот не администратор канала или канал не найден, пропускаем проверку
            continue
    
    user_subscription_status[user_id] = True
    return True

async def get_sponsor_tasks(user_id: int) -> Optional[List[str]]:
    """
    Получает список спонсорских каналов из Botohub API.
    Возвращает список ссылок на каналы или None при ошибке.
    """
    headers = {
        "Content-Type": "application/json",
        "Auth": BOTOHUB_TOKEN
    }
    payload = {
        "chat_id": user_id,
        "gender": "male",  # Можно заменить на реальные данные пользователя
        "age": 25          # Можно заменить на реальные данные пользователя
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(BOTOHUB_API_URL, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Проверяем, есть ли невыполненные задания
                    if not data.get("completed", True) and data.get("tasks"):
                        return data["tasks"]
                else:
                    logger.error(f"Botohub API error: {resp.status}")
        except Exception as e:
            logger.error(f"Botohub API request failed: {e}")
    return None


# ===================== ДЕКОРАТОР ПРОВЕРКИ ПОДПИСКИ =====================
def subscription_required(handler):
    """Декоратор для проверки подписки перед выполнением команды"""
    async def wrapper(message_or_callback, *args, **kwargs):
        user_id = None
        if isinstance(message_or_callback, Message):
            user_id = message_or_callback.from_user.id
        elif isinstance(message_or_callback, CallbackQuery):
            user_id = message_or_callback.from_user.id
        
        if not await check_user_subscription(user_id):
            # Формируем клавиатуру для подписки
            keyboard = InlineKeyboardMarkup(inline_keyboard=[])
            for channel in REQUIRED_CHANNELS:
                keyboard.inline_keyboard.append([InlineKeyboardButton(text=f"📢 Подписаться на {channel}", url=f"https://t.me/{channel[1:]}")])
            keyboard.inline_keyboard.append([InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_subscription")])
            
            text = (
                "🔒 <b>Доступ ограничен</b>\n\n"
                "Для использования бота необходимо подписаться на наши каналы:\n"
                + "\n".join([f"• {ch}" for ch in REQUIRED_CHANNELS]) +
                "\n\n<i>После подписки нажмите кнопку «Проверить подписку».</i>"
            )
            
            if isinstance(message_or_callback, Message):
                await message_or_callback.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
            else:
                await message_or_callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
                await message_or_callback.answer()
            return
        return await handler(message_or_callback, *args, **kwargs)
    return wrapper


# ===================== КЛАВИАТУРЫ =====================
def get_main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    balance = get_user_balance(user_id)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💰 {balance} Stars", callback_data="balance_info")],
        [
            InlineKeyboardButton(text="⭐️ Пополнить", callback_data="deposit"),
            InlineKeyboardButton(text="🎮 Игры", callback_data="games_menu")
        ],
        [
            InlineKeyboardButton(text="👥 Рефералы", callback_data="referrals"),
            InlineKeyboardButton(text="🏆 Топ", callback_data="top")
        ],
        [
            InlineKeyboardButton(text="📊 Профиль", callback_data="profile"),
            InlineKeyboardButton(text="🎁 Бонус", callback_data="daily_bonus")
        ]
    ])

def get_games_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎰 Рулетка", callback_data="game_roulette"),
            InlineKeyboardButton(text="🎯 Дартс", callback_data="game_darts")
        ],
        [
            InlineKeyboardButton(text="⚽️ Футбол", callback_data="game_football"),
            InlineKeyboardButton(text="🎳 Боулинг", callback_data="game_bowling")
        ],
        [
            InlineKeyboardButton(text="🏀 Баскетбол", callback_data="game_basketball"),
            InlineKeyboardButton(text="💣 Мины", callback_data="game_mines")
        ],
        [
            InlineKeyboardButton(text="🏛 Пирамида", callback_data="game_pyramid"),
            InlineKeyboardButton(text="🎰 Слоты", callback_data="game_slots")
        ],
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="main_menu")]
    ])

def get_deposit_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐️ 10", callback_data="deposit_10"),
            InlineKeyboardButton(text="⭐️ 50", callback_data="deposit_50"),
            InlineKeyboardButton(text="⭐️ 100", callback_data="deposit_100")
        ],
        [
            InlineKeyboardButton(text="⭐️ 250", callback_data="deposit_250"),
            InlineKeyboardButton(text="⭐️ 500", callback_data="deposit_500"),
            InlineKeyboardButton(text="⭐️ 1000", callback_data="deposit_1000")
        ],
        [
            InlineKeyboardButton(text="✏️ Другая сумма", callback_data="deposit_custom")
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])

def get_bet_keyboard(game: str, min_bet: int = 5) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐️ 5", callback_data=f"{game}_bet_5"),
            InlineKeyboardButton(text="⭐️ 10", callback_data=f"{game}_bet_10"),
            InlineKeyboardButton(text="⭐️ 25", callback_data=f"{game}_bet_25")
        ],
        [
            InlineKeyboardButton(text="⭐️ 50", callback_data=f"{game}_bet_50"),
            InlineKeyboardButton(text="⭐️ 100", callback_data=f"{game}_bet_100"),
            InlineKeyboardButton(text="⭐️ 250", callback_data=f"{game}_bet_250")
        ],
        [InlineKeyboardButton(text="◀️ Назад к играм", callback_data="games_menu")]
    ])

def get_mines_board_keyboard(board: List[List[str]], revealed: List[List[bool]], bet: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру для игры Мины"""
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
        [
            InlineKeyboardButton(text="🎰 Крутить (5⭐️)", callback_data="slots_spin_5"),
            InlineKeyboardButton(text="🎰 Крутить (10⭐️)", callback_data="slots_spin_10")
        ],
        [
            InlineKeyboardButton(text="🎰 Крутить (25⭐️)", callback_data="slots_spin_25"),
            InlineKeyboardButton(text="🎰 Крутить (50⭐️)", callback_data="slots_spin_50")
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="games_menu")]
    ])


# ===================== РЕФЕРАЛЬНАЯ СИСТЕМА =====================
def process_referral(new_user_id: int, referrer_id: int) -> str:
    """Обработка реферальной регистрации"""
    if new_user_id == referrer_id:
        return "❌ Нельзя пригласить самого себя!"
    
    if new_user_id in users_referrer:
        return "ℹ️ Вы уже зарегистрированы в системе!"
    
    # Записываем реферера
    users_referrer[new_user_id] = referrer_id
    
    # Добавляем в список рефералов пригласившего
    if referrer_id not in users_referrals:
        users_referrals[referrer_id] = []
    users_referrals[referrer_id].append(new_user_id)
    
    # Начисляем бонусы
    update_balance(new_user_id, REFERRAL_SIGNUP_BONUS)
    update_balance(referrer_id, REFERRAL_INVITE_BONUS)
    
    save_transaction(new_user_id, REFERRAL_SIGNUP_BONUS, "referral_bonus", f"Приветственный бонус от {referrer_id}")
    save_transaction(referrer_id, REFERRAL_INVITE_BONUS, "referral_reward", f"Приглашение {new_user_id}")
    
    return f"✅ Вы получили {format_stars(REFERRAL_SIGNUP_BONUS)} за регистрацию по ссылке!"


# ===================== КОМАНДЫ =====================
@dp.message(Command("start"))
@subscription_required
async def cmd_start(message: Message):
    user_id = message.from_user.id
    text = message.text
    
    # Обработка реферального параметра
    if " " in text and text.split()[1].startswith("ref_"):
        ref_code = text.split()[1][4:]
        # Здесь нужно было бы декодировать реферальный код, но для простоты пропустим
        pass
    
    # Базовое приветствие
    welcome_text = (
        f"🌟 <b>Добро пожаловать в StarPlay!</b> 🌟\n\n"
        f"{get_random_emoji()} Уникальный игровой бот, где ты играешь на <b>Telegram Stars</b>!\n\n"
        f"<b>🔥 Что тебя ждет:</b>\n"
        f"• 8 увлекательных игр с реальными выигрышами\n"
        f"• Реферальная система — приглашай друзей и зарабатывай\n"
        f"• Ежедневные бонусы и розыгрыши\n"
        f"• Рейтинг лучших игроков\n\n"
        f"<b>💫 Как начать:</b>\n"
        f"1️⃣ Пополни баланс через Telegram Stars\n"
        f"2️⃣ Выбери любую игру\n"
        f"3️⃣ Делай ставки и выигрывай!\n\n"
        f"👇 <i>Нажми на кнопку меню, чтобы начать!</i>"
    )
    
    await message.answer(welcome_text, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard(user_id))

@dp.message(Command("balance"))
@subscription_required
async def cmd_balance(message: Message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    await message.answer(
        f"💰 <b>Твой баланс:</b> {format_stars(balance)}\n\n"
        f"{get_random_emoji()} Приглашай друзей — получай бонусы!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(user_id)
    )

@dp.message(Command("bonus"))
@subscription_required
async def cmd_bonus(message: Message):
    user_id = message.from_user.id
    today = datetime.now().date().isoformat()
    
    if users_daily_bonus.get(user_id) == today:
        await message.answer(
            f"🎁 <b>Ты уже получил сегодняшний бонус!</b>\n\n"
            f"Возвращайся завтра за новой порцией Stars! 🌟",
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
        f"💰 Твой баланс: {format_stars(get_user_balance(user_id))}\n\n"
        f"{get_random_emoji()} Заглядывай завтра снова!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(user_id)
    )


# ===================== ИГРЫ =====================
# ----- РУЛЕТКА -----
roulette_numbers = list(range(0, 37))
roulette_colors = {0: "green"}
for i in range(1, 37):
    if i % 2 == 1:
        roulette_colors[i] = "red"
    else:
        roulette_colors[i] = "black"
roulette_red = [i for i in range(1, 37) if roulette_colors[i] == "red"]
roulette_black = [i for i in range(1, 37) if roulette_colors[i] == "black"]

@dp.callback_query(F.data == "game_roulette")
@subscription_required
async def roulette_start(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎰 <b>Европейская Рулетка</b> 🎰\n\n"
        "<b>Ставки и коэффициенты:</b>\n"
        "• 🎯 <b>Число</b> (0-36) — x35\n"
        "• 🔴 <b>Красное</b> — x2\n"
        "• ⚫️ <b>Черное</b> — x2\n"
        "• 🟢 <b>Зеро (0)</b> — x35\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("roulette")
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("roulette_bet_"))
@subscription_required
async def roulette_bet(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    balance = get_user_balance(user_id)
    
    if balance < bet:
        await callback.answer(f"❌ Недостаточно Stars! Нужно {bet}", show_alert=True)
        return
    
    await state.update_data(roulette_bet=bet)
    
    # Клавиатура выбора типа ставки
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Конкретное число", callback_data="roulette_type_number")],
        [InlineKeyboardButton(text="🔴 Красное (x2)", callback_data="roulette_type_red")],
        [InlineKeyboardButton(text="⚫️ Черное (x2)", callback_data="roulette_type_black")],
        [InlineKeyboardButton(text="🟢 Зеро (0) x35", callback_data="roulette_type_zero")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="games_menu")]
    ])
    
    await callback.message.edit_text(
        f"🎰 <b>Рулетка</b>\n\n"
        f"Ставка: {format_stars(bet)}\n\n"
        f"Выбери тип ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("roulette_type_"))
@subscription_required
async def roulette_play(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet = data.get("roulette_bet", 5)
    bet_type = callback.data.split("_")[-1]
    user_id = callback.from_user.id
    
    # Списываем ставку
    update_balance(user_id, -bet)
    
    # Определяем выпавшее число
    result = random.choice(roulette_numbers)
    result_color = roulette_colors[result]
    
    # Проверяем выигрыш
    win = False
    multiplier = 0
    
    if bet_type == "number":
        # Попросим ввести число в отдельном сообщении (упрощенно)
        await callback.answer("🚧 Функция выбора числа в разработке", show_alert=True)
        update_balance(user_id, bet)  # Возвращаем ставку
        await state.clear()
        return
    elif bet_type == "red" and result_color == "red":
        win = True
        multiplier = 2
    elif bet_type == "black" and result_color == "black":
        win = True
        multiplier = 2
    elif bet_type == "zero" and result == 0:
        win = True
        multiplier = 35
    
    if win:
        winnings = bet * multiplier
        update_balance(user_id, winnings)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["roulette_wins"] += 1
        stats["total_won"] += winnings
        save_transaction(user_id, winnings, "game_win", f"Рулетка x{multiplier}")
        
        result_emoji = "🎉"
        result_text = f"<b>ТЫ ВЫИГРАЛ!</b> {result_emoji}\n+{format_stars(winnings)}"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", "Рулетка")
        
        result_emoji = "😢"
        result_text = f"<b>К сожалению, проигрыш...</b> {result_emoji}\n-{format_stars(bet)}"
    
    # Отображение результата
    color_emoji = {"red": "🔴", "black": "⚫️", "green": "🟢"}[result_color]
    
    message_text = (
        f"🎰 <b>Рулетка</b> 🎰\n\n"
        f"Ваша ставка: {format_stars(bet)}\n"
        f"Выпало: <b>{result}</b> {color_emoji}\n\n"
        f"{result_text}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}"
    )
    
    await callback.message.edit_text(message_text, parse_mode=ParseMode.HTML, reply_markup=get_games_keyboard())
    await state.clear()
    await callback.answer()


# ----- ДАРТС -----
@dp.callback_query(F.data == "game_darts")
@subscription_required
async def darts_start(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎯 <b>Дартс — Попади в яблочко!</b> 🎯\n\n"
        "<b>Правила:</b>\n"
        "У тебя 3 броска, цель — набрать больше 150 очков!\n"
        "• 1-20 очков — обычный сектор\n"
        "• 25 очков — зеленое кольцо\n"
        "• 50 очков — яблочко!\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("darts")
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("darts_bet_"))
@subscription_required
async def darts_play(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    balance = get_user_balance(user_id)
    
    if balance < bet:
        await callback.answer(f"❌ Недостаточно Stars! Нужно {bet}", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    
    # Симуляция 3 бросков
    throws = []
    total_score = 0
    for i in range(3):
        # Шансы: 60% обычный сектор, 25% x2, 10% x3, 5% яблочко
        r = random.random()
        if r < 0.6:
            score = random.randint(1, 20)
        elif r < 0.85:
            score = random.choice([25, 25])
        elif r < 0.95:
            score = random.choice([40, 45, 50])
        else:
            score = 50
        throws.append(score)
        total_score += score
    
    # Определяем выигрыш
    if total_score >= 150:
        multiplier = 2 if total_score >= 200 else 1.5
        winnings = int(bet * multiplier)
        update_balance(user_id, winnings)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["darts_wins"] += 1
        stats["total_won"] += winnings
        save_transaction(user_id, winnings, "game_win", f"Дартс {total_score} очков")
        
        result_text = f"🎯 <b>ПОБЕДА!</b> 🎉\n+{format_stars(winnings)}"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", f"Дартс {total_score} очков")
        
        result_text = f"🎯 <b>Не повезло...</b> 😢\n-{format_stars(bet)}"
    
    darts_emoji = "🎯" * min(3, total_score // 50)
    
    message_text = (
        f"🎯 <b>Игра в Дартс</b> {darts_emoji}\n\n"
        f"Твои броски: {throws[0]} + {throws[1]} + {throws[2]} = <b>{total_score}</b>\n"
        f"Нужно было: 150+\n\n"
        f"{result_text}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}"
    )
    
    await callback.message.edit_text(message_text, parse_mode=ParseMode.HTML, reply_markup=get_games_keyboard())
    await state.clear()
    await callback.answer()


# ----- ФУТБОЛ -----
@dp.callback_query(F.data == "game_football")
@subscription_required
async def football_start(callback: CallbackQuery):
    await callback.message.edit_text(
        "⚽️ <b>Футбол — Забей гол!</b> ⚽️\n\n"
        "<b>Правила:</b>\n"
        "У тебя 3 попытки забить пенальти вратарю!\n"
        "Твоя задача — забить 2+ гола для выигрыша\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("football")
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("football_bet_"))
@subscription_required
async def football_play(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    balance = get_user_balance(user_id)
    
    if balance < bet:
        await callback.answer(f"❌ Недостаточно Stars!", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    
    goals = 0
    results = []
    for i in range(3):
        # 40% шанс забить
        if random.random() < 0.4:
            goals += 1
            results.append("⚽️ ГОЛ!")
        else:
            results.append("🧤 Сейв!")
    
    if goals >= 2:
        multiplier = {2: 2, 3: 3}.get(goals, 2)
        winnings = bet * multiplier
        update_balance(user_id, winnings)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["football_wins"] += 1
        stats["total_won"] += winnings
        save_transaction(user_id, winnings, "game_win", f"Футбол {goals} гола")
        
        result_text = f"⚽️ <b>ГОЛ! Ты выиграл!</b> 🎉\n+{format_stars(winnings)}"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", f"Футбол {goals} гола")
        
        result_text = f"⚽️ <b>Вратарь выиграл...</b> 😢\n-{format_stars(bet)}"
    
    message_text = (
        f"⚽️ <b>Футбольный пенальти</b>\n\n"
        f"Попытка 1: {results[0]}\n"
        f"Попытка 2: {results[1]}\n"
        f"Попытка 3: {results[2]}\n\n"
        f"<b>Итог: {goals} гола</b>\n\n"
        f"{result_text}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}"
    )
    
    await callback.message.edit_text(message_text, parse_mode=ParseMode.HTML, reply_markup=get_games_keyboard())
    await state.clear()
    await callback.answer()


# ----- БОУЛИНГ -----
@dp.callback_query(F.data == "game_bowling")
@subscription_required
async def bowling_start(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎳 <b>Боулинг — Сбей кегли!</b> 🎳\n\n"
        "<b>Правила:</b>\n"
        "У тебя 2 броска в фрейме.\n"
        "Страйк (10 кегль с 1 броска) = x3 выигрыш\n"
        "Спэр (10 с 2 бросков) = x2 выигрыш\n"
        "Меньше 8 кегль = проигрыш\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("bowling")
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("bowling_bet_"))
@subscription_required
async def bowling_play(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    balance = get_user_balance(user_id)
    
    if balance < bet:
        await callback.answer(f"❌ Недостаточно Stars!", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    
    # Первый бросок
    first = random.randint(0, 10)
    
    if first == 10:  # СТРАЙК
        result = "СТРАЙК! 🎳✨"
        multiplier = 3
        winnings = bet * multiplier
        update_balance(user_id, winnings)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["bowling_wins"] += 1
        stats["total_won"] += winnings
        save_transaction(user_id, winnings, "game_win", "Боулинг Страйк")
        
        result_text = f"🎳 <b>СТРАЙК! Выигрыш x3!</b> 🎉\n+{format_stars(winnings)}"
        message_text = f"🎳 <b>Боулинг</b>\n\nПервый бросок: {first} кегль 💥\nСТРАЙК!\n\n{result_text}"
    else:
        second = random.randint(0, 10 - first)
        total = first + second
        
        if total == 10:  # СПЭР
            multiplier = 2
            winnings = bet * multiplier
            update_balance(user_id, winnings)
            stats = get_user_stats(user_id)
            stats["games_played"] += 1
            stats["games_won"] += 1
            stats["bowling_wins"] += 1
            stats["total_won"] += winnings
            save_transaction(user_id, winnings, "game_win", "Боулинг Спэр")
            
            result_text = f"🎳 <b>СПЭР! Выигрыш x2!</b> 🎉\n+{format_stars(winnings)}"
        elif total >= 8:
            multiplier = 1.2
            winnings = int(bet * multiplier)
            update_balance(user_id, winnings)
            stats = get_user_stats(user_id)
            stats["games_played"] += 1
            stats["games_won"] += 1
            stats["bowling_wins"] += 1
            stats["total_won"] += winnings
            save_transaction(user_id, winnings, "game_win", f"Боулинг {total} кегль")
            
            result_text = f"🎳 <b>Хороший бросок! +{multiplier}x</b>\n+{format_stars(winnings)}"
        else:
            stats = get_user_stats(user_id)
            stats["games_played"] += 1
            stats["total_lost"] += bet
            save_transaction(user_id, -bet, "game_loss", f"Боулинг {total} кегль")
            
            result_text = f"🎳 <b>Неудача...</b> 😢\n-{format_stars(bet)}"
        
        message_text = (
            f"🎳 <b>Боулинг</b>\n\n"
            f"Первый бросок: {first} кегль\n"
            f"Второй бросок: {second} кегль\n"
            f"Всего: {total} кегль\n\n"
            f"{result_text}"
        )
    
    message_text += f"\n\n💰 Новый баланс: {format_stars(get_user_balance(user_id))}"
    
    await callback.message.edit_text(message_text, parse_mode=ParseMode.HTML, reply_markup=get_games_keyboard())
    await state.clear()
    await callback.answer()


# ----- БАСКЕТБОЛ -----
@dp.callback_query(F.data == "game_basketball")
@subscription_required
async def basketball_start(callback: CallbackQuery):
    await callback.message.edit_text(
        "🏀 <b>Баскетбол — Трехочковый!</b> 🏀\n\n"
        "<b>Правила:</b>\n"
        "У тебя 5 бросков из-за дуги!\n"
        "Каждое попадание = x1.5 к ставке\n"
        "3+ попадания = бонус x2!\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("basketball")
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("basketball_bet_"))
@subscription_required
async def basketball_play(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    balance = get_user_balance(user_id)
    
    if balance < bet:
        await callback.answer(f"❌ Недостаточно Stars!", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    
    hits = 0
    results = []
    for i in range(5):
        # 40% шанс попадания
        if random.random() < 0.4:
            hits += 1
            results.append("🏀 +1")
        else:
            results.append("❌ мимо")
    
    if hits >= 3:
        multiplier = 2.5 if hits == 5 else 2
        winnings = int(bet * multiplier)
        update_balance(user_id, winnings)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["basketball_wins"] += 1
        stats["total_won"] += winnings
        save_transaction(user_id, winnings, "game_win", f"Баскетбол {hits}/5")
        
        result_text = f"🏀 <b>ОТЛИЧНАЯ ИГРА! x{multiplier}</b> 🎉\n+{format_stars(winnings)}"
    else:
        winnings = int(bet * hits * 0.3)
        if winnings > 0:
            update_balance(user_id, winnings)
            stats = get_user_stats(user_id)
            stats["games_played"] += 1
            stats["total_won"] += winnings
            save_transaction(user_id, winnings, "game_win", f"Баскетбол {hits}/5")
            result_text = f"🏀 <b>{hits} попаданий</b>\n+{format_stars(winnings)}"
        else:
            stats = get_user_stats(user_id)
            stats["games_played"] += 1
            stats["total_lost"] += bet
            save_transaction(user_id, -bet, "game_loss", f"Баскетбол {hits}/5")
            result_text = f"🏀 <b>Неудача...</b> 😢\n-{format_stars(bet)}"
    
    message_text = (
        f"🏀 <b>Баскетбол — Броски из-за дуги</b>\n\n"
        f"Бросок 1: {results[0]}\n"
        f"Бросок 2: {results[1]}\n"
        f"Бросок 3: {results[2]}\n"
        f"Бросок 4: {results[3]}\n"
        f"Бросок 5: {results[4]}\n\n"
        f"<b>Попаданий: {hits}/5</b>\n\n"
        f"{result_text}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}"
    )
    
    await callback.message.edit_text(message_text, parse_mode=ParseMode.HTML, reply_markup=get_games_keyboard())
    await state.clear()
    await callback.answer()


# ----- МИНЫ (игра в реальном времени) -----
active_mines_games: Dict[int, dict] = {}

@dp.callback_query(F.data == "game_mines")
@subscription_required
async def mines_start(callback: CallbackQuery):
    await callback.message.edit_text(
        "💣 <b>МИНЫ — Найди безопасный путь!</b> 💣\n\n"
        "<b>Правила:</b>\n"
        "Перед тобой поле 5x5. В некоторых клетках — мины 💣, в остальных — сокровища 💎\n"
        "Каждая открытая 💎 увеличивает выигрыш!\n"
        "Наступишь на 💣 — потеряешь ставку!\n\n"
        "<b>Выбери сумму ставки:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("mines")
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("mines_bet_"))
@subscription_required
async def mines_init(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    balance = get_user_balance(user_id)
    
    if balance < bet:
        await callback.answer(f"❌ Недостаточно Stars!", show_alert=True)
        return
    
    # Создаем новую игру
    update_balance(user_id, -bet)
    
    # Создаем поле 5x5 с 5 минами
    board = [["💎" for _ in range(5)] for _ in range(5)]
    mines_placed = 0
    while mines_placed < 5:
        x, y = random.randint(0, 4), random.randint(0, 4)
        if board[x][y] == "💎":
            board[x][y] = "💣"
            mines_placed += 1
    
    active_mines_games[user_id] = {
        "board": board,
        "revealed": [[False for _ in range(5)] for _ in range(5)],
        "bet": bet,
        "multiplier": 1.0,
        "cells_opened": 0
    }
    
    await callback.message.edit_text(
        f"💣 <b>Игра МИНЫ</b> 💣\n\n"
        f"Ставка: {format_stars(bet)}\n"
        f"Найди 💎 и не наступи на 💣!\n"
        f"Каждая найденная 💎 увеличивает выигрыш x1.2\n\n"
        f"<i>Нажми на клетку, чтобы открыть</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_mines_board_keyboard(board, active_mines_games[user_id]["revealed"], bet)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("mine_"))
@subscription_required
async def mines_reveal(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_mines_games:
        await callback.answer("Игра не найдена! Начни новую.", show_alert=True)
        return
    
    game = active_mines_games[user_id]
    x, y = map(int, callback.data.split("_")[1:])
    
    if game["revealed"][x][y]:
        await callback.answer("Эта клетка уже открыта!", show_alert=True)
        return
    
    game["revealed"][x][y] = True
    
    if game["board"][x][y] == "💣":
        # Проигрыш
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += game["bet"]
        save_transaction(user_id, -game["bet"], "game_loss", f"Мины - наступил на мину")
        
        del active_mines_games[user_id]
        
        await callback.message.edit_text(
            f"💣 <b>Игра МИНЫ</b> 💣\n\n"
            f"💥 <b>БАХ! Ты наступил на мину!</b> 💥\n\n"
            f"Ставка: {format_stars(game['bet'])} — проиграна.\n"
            f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_games_keyboard()
        )
    else:
        game["cells_opened"] += 1
        game["multiplier"] *= 1.2
        
        await callback.message.edit_reply_markup(
            reply_markup=get_mines_board_keyboard(game["board"], game["revealed"], game["bet"])
        )
        
        # Если открыто много клеток, можно предложить забрать выигрыш
        if game["cells_opened"] >= 15:
            winnings = int(game["bet"] * game["multiplier"])
            update_balance(user_id, winnings)
            stats = get_user_stats(user_id)
            stats["games_played"] += 1
            stats["games_won"] += 1
            stats["mines_wins"] += 1
            stats["total_won"] += winnings
            save_transaction(user_id, winnings, "game_win", f"Мины - очищено {game['cells_opened']} клеток")
            
            del active_mines_games[user_id]
            
            await callback.message.edit_text(
                f"💣 <b>Игра МИНЫ</b> 💣\n\n"
                f"🎉 <b>ПОБЕДА! Ты очистил почти всё поле!</b> 🎉\n\n"
                f"Открыто клеток: {game['cells_opened']}\n"
                f"Множитель: x{game['multiplier']:.1f}\n"
                f"Выигрыш: {format_stars(winnings)}\n"
                f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_games_keyboard()
            )
    
    await callback.answer()

@dp.callback_query(F.data.startswith("mines_cashout_"))
@subscription_required
async def mines_cashout(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_mines_games:
        await callback.answer("Игра не найдена!", show_alert=True)
        return
    
    game = active_mines_games[user_id]
    winnings = int(game["bet"] * game["multiplier"])
    update_balance(user_id, winnings)
    
    stats = get_user_stats(user_id)
    stats["games_played"] += 1
    stats["games_won"] += 1
    stats["mines_wins"] += 1
    stats["total_won"] += winnings
    save_transaction(user_id, winnings, "game_win", f"Мины - кэшаут {game['cells_opened']} клеток")
    
    del active_mines_games[user_id]
    
    await callback.message.edit_text(
        f"💣 <b>Игра МИНЫ</b> 💣\n\n"
        f"💰 <b>Ты забрал выигрыш!</b> 💰\n\n"
        f"Открыто клеток: {game['cells_opened']}\n"
        f"Множитель: x{game['multiplier']:.1f}\n"
        f"Выигрыш: {format_stars(winnings)}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()


# ----- ПИРАМИДА -----
@dp.callback_query(F.data == "game_pyramid")
@subscription_required
async def pyramid_start(callback: CallbackQuery):
    await callback.message.edit_text(
        "🏛 <b>ПИРАМИДА — Поднимайся выше!</b> 🏛\n\n"
        "<b>Правила:</b>\n"
        "У тебя есть 5 уровней. На каждом уровне ты можешь:\n"
        "• Подняться выше (x2 к ставке, 50% шанс)\n"
        "• Забрать выигрыш\n"
        "Если проигрываешь — теряешь всё!\n\n"
        "Выбери начальную ставку:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("pyramid")
    )
    await callback.answer()

active_pyramids: Dict[int, dict] = {}

@dp.callback_query(F.data.startswith("pyramid_bet_"))
@subscription_required
async def pyramid_init(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    balance = get_user_balance(user_id)
    
    if balance < bet:
        await callback.answer(f"❌ Недостаточно Stars!", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    
    active_pyramids[user_id] = {
        "bet": bet,
        "level": 1,
        "current_win": bet
    }
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬆️ Подняться выше (x2)", callback_data="pyramid_up")],
        [InlineKeyboardButton(text="💰 Забрать выигрыш", callback_data="pyramid_cashout")],
        [InlineKeyboardButton(text="◀️ Выйти", callback_data="games_menu")]
    ])
    
    await callback.message.edit_text(
        f"🏛 <b>Пирамида — Уровень 1</b> 🏛\n\n"
        f"Текущий выигрыш: {format_stars(bet)}\n"
        f"Следующий уровень: {format_stars(bet * 2)}\n"
        f"Шанс успеха: 50%\n\n"
        f"Поднимешься или заберешь выигрыш?",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data == "pyramid_up")
@subscription_required
async def pyramid_up(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_pyramids:
        await callback.answer("Игра не найдена!", show_alert=True)
        return
    
    game = active_pyramids[user_id]
    
    # 50% шанс успеха
    if random.random() < 0.5:
        game["level"] += 1
        game["current_win"] *= 2
        
        if game["level"] >= 5:
            # Победа на максимальном уровне
            update_balance(user_id, game["current_win"])
            stats = get_user_stats(user_id)
            stats["games_played"] += 1
            stats["games_won"] += 1
            stats["pyramid_wins"] += 1
            stats["total_won"] += game["current_win"]
            save_transaction(user_id, game["current_win"], "game_win", f"Пирамида уровень {game['level']}")
            
            await callback.message.edit_text(
                f"🏛 <b>ПИРАМИДА — ПОБЕДА!</b> 🏛\n\n"
                f"🎉 Ты покорил вершину! 🎉\n"
                f"Выигрыш: {format_stars(game['current_win'])}\n"
                f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_games_keyboard()
            )
            del active_pyramids[user_id]
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬆️ Подняться выше (x2)", callback_data="pyramid_up")],
                [InlineKeyboardButton(text="💰 Забрать выигрыш", callback_data="pyramid_cashout")],
                [InlineKeyboardButton(text="◀️ Выйти", callback_data="games_menu")]
            ])
            
            await callback.message.edit_text(
                f"🏛 <b>Пирамида — Уровень {game['level']}</b> 🏛\n\n"
                f"✅ <b>Успех! Ты поднялся!</b>\n\n"
                f"Текущий выигрыш: {format_stars(game['current_win'])}\n"
                f"Следующий уровень: {format_stars(game['current_win'] * 2)}\n"
                f"Шанс успеха: 50%\n\n"
                f"Продолжишь подъем?",
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
    else:
        # Проигрыш
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += game["bet"]
        save_transaction(user_id, -game["bet"], "game_loss", f"Пирамида уровень {game['level']}")
        
        await callback.message.edit_text(
            f"🏛 <b>Пирамида — ПРОИГРЫШ</b> 🏛\n\n"
            f"💔 <b>Ты рухнул вниз!</b>\n\n"
            f"Ставка: {format_stars(game['bet'])} — проиграна\n"
            f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_games_keyboard()
        )
        del active_pyramids[user_id]
    
    await callback.answer()

@dp.callback_query(F.data == "pyramid_cashout")
@subscription_required
async def pyramid_cashout(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_pyramids:
        await callback.answer("Игра не найдена!", show_alert=True)
        return
    
    game = active_pyramids[user_id]
    update_balance(user_id, game["current_win"])
    
    stats = get_user_stats(user_id)
    stats["games_played"] += 1
    stats["games_won"] += 1
    stats["pyramid_wins"] += 1
    stats["total_won"] += game["current_win"]
    save_transaction(user_id, game["current_win"], "game_win", f"Пирамида кэшаут уровень {game['level']}")
    
    await callback.message.edit_text(
        f"🏛 <b>Пирамида</b> 🏛\n\n"
        f"💰 <b>Ты забрал выигрыш!</b>\n\n"
        f"Выигрыш: {format_stars(game['current_win'])}\n"
        f"Пройдено уровней: {game['level']}\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    del active_pyramids[user_id]
    await callback.answer()


# ----- СЛОТЫ -----
@dp.callback_query(F.data == "game_slots")
@subscription_required
async def slots_start(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎰 <b>СЛОТЫ — Классический автомат</b> 🎰\n\n"
        "Крути барабаны и собирай комбинации!\n\n"
        "Выбери ставку:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_slots_keyboard()
    )
    await callback.answer()

slot_symbols = ["🍒", "🍊", "🍋", "💎", "7️⃣", "🎰", "⭐️", "💫"]
slot_payouts = {
    ("🍒", "🍒", "🍒"): 5,
    ("🍊", "🍊", "🍊"): 7,
    ("🍋", "🍋", "🍋"): 10,
    ("💎", "💎", "💎"): 15,
    ("7️⃣", "7️⃣", "7️⃣"): 25,
    ("🎰", "🎰", "🎰"): 50,
    ("⭐️", "⭐️", "⭐️"): 30,
    ("💫", "💫", "💫"): 20,
}

@dp.callback_query(F.data.startswith("slots_spin_"))
@subscription_required
async def slots_spin(callback: CallbackQuery):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    balance = get_user_balance(user_id)
    
    if balance < bet:
        await callback.answer(f"❌ Недостаточно Stars! Нужно {bet}", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    
    # Генерация результата
    reel1 = random.choice(slot_symbols)
    reel2 = random.choice(slot_symbols)
    reel3 = random.choice(slot_symbols)
    
    result = (reel1, reel2, reel3)
    
    if result in slot_payouts:
        multiplier = slot_payouts[result]
        winnings = bet * multiplier
        update_balance(user_id, winnings)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["slots_wins"] += 1
        stats["total_won"] += winnings
        save_transaction(user_id, winnings, "game_win", f"Слоты {''.join(result)}")
        
        result_text = f"🎉 <b>ДЖЕКПОТ! x{multiplier}</b> 🎉\n+{format_stars(winnings)}"
    else:
        # Проверка на 2 одинаковых символа
        if reel1 == reel2 or reel1 == reel3 or reel2 == reel3:
            if reel1 == reel2 or reel1 == reel3:
                common = reel1
            else:
                common = reel2
            multiplier = 1.5
            winnings = int(bet * multiplier)
            update_balance(user_id, winnings)
            stats = get_user_stats(user_id)
            stats["games_played"] += 1
            stats["total_won"] += winnings
            save_transaction(user_id, winnings, "game_win", f"Слоты 2x{common}")
            
            result_text = f"🎉 <b>Пара! x{multiplier}</b>\n+{format_stars(winnings)}"
        else:
            stats = get_user_stats(user_id)
            stats["games_played"] += 1
            stats["total_lost"] += bet
            save_transaction(user_id, -bet, "game_loss", "Слоты")
            
            result_text = f"😢 <b>Не повезло...</b>\n-{format_stars(bet)}"
    
    message_text = (
        f"🎰 <b>Слоты</b>\n\n"
        f"┌─────┬─────┬─────┐\n"
        f"│  {reel1}  │  {reel2}  │  {reel3}  │\n"
        f"└─────┴─────┴─────┘\n\n"
        f"Ставка: {format_stars(bet)}\n"
        f"{result_text}\n\n"
        f"💰 Новый баланс: {format_stars(get_user_balance(user_id))}"
    )
    
    await callback.message.edit_text(message_text, parse_mode=ParseMode.HTML, reply_markup=get_slots_keyboard())
    await callback.answer()


# ===================== ПРОЧИЕ ОБРАБОТЧИКИ =====================
@dp.callback_query(F.data == "referrals")
@subscription_required
async def show_referrals(callback: CallbackQuery):
    user_id = callback.from_user.id
    referrals = users_referrals.get(user_id, [])
    ref_count = len(referrals)
    
    # Суммарный доход от рефералов
    total_earned = 0
    for tx in transactions.get(user_id, []):
        if tx["type"] == "referral_reward":
            total_earned += tx["amount"]
    
    ref_link = generate_referral_link(user_id)
    
    text = (
        f"👥 <b>Реферальная система</b> 👥\n\n"
        f"🏆 <b>Твоя статистика:</b>\n"
        f"• Приглашено: {ref_count} чел.\n"
        f"• Заработано: {format_stars(total_earned)}\n\n"
        f"<b>📋 Как это работает:</b>\n"
        f"• Твой друг получает {format_stars(REFERRAL_SIGNUP_BONUS)} при регистрации\n"
        f"• Ты получаешь {format_stars(REFERRAL_INVITE_BONUS)} за приглашение\n"
        f"• Ты получаешь {REFERRAL_BONUS_PERCENT}% от каждого пополнения друга\n\n"
        f"<b>🔗 Твоя реферальная ссылка:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"Поделись ссылкой с друзьями и зарабатывай! 🚀"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться ссылкой", url=f"https://t.me/share/url?url={ref_link}&text=Играй+в+StarPlay+и+зарабатывай+Telegram+Stars!+Моя+реферальная+ссылка:")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "top")
@subscription_required
async def show_top(callback: CallbackQuery):
    sorted_users = sorted(users_balance.items(), key=lambda x: x[1], reverse=True)[:15]
    
    if not sorted_users:
        await callback.answer("Пока нет игроков в рейтинге!", show_alert=True)
        return
    
    top_text = "🏆 <b>ТОП-15 ИГРОКОВ StarPlay</b> 🏆\n\n"
    for idx, (user_id, balance) in enumerate(sorted_users, 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
        try:
            user = await bot.get_chat(user_id)
            name = user.first_name[:20] if user.first_name else str(user_id)
        except:
            name = str(user_id)
        
        top_text += f"{medal} <b>{name}</b> — {balance} ⭐️\n"
    
    top_text += f"\n{get_random_emoji()} Присоединяйся к топу! {get_random_emoji()}"
    
    await callback.message.edit_text(top_text, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard(callback.from_user.id))
    await callback.answer()

@dp.callback_query(F.data == "profile")
@subscription_required
async def show_profile(callback: CallbackQuery):
    user_id = callback.from_user.id
    balance = get_user_balance(user_id)
    stats = get_user_stats(user_id)
    ref_count = len(users_referrals.get(user_id, []))
    
    win_rate = 0
    if stats["games_played"] > 0:
        win_rate = (stats["games_won"] / stats["games_played"]) * 100
    
    profile_text = (
        f"👤 <b>Профиль игрока</b>\n\n"
        f"🎮 <b>@StarPlay Bot</b>\n"
        f"├ 🆔 ID: <code>{user_id}</code>\n"
        f"├ 👤 Имя: {callback.from_user.first_name}\n"
        f"└ 🌟 Username: @{callback.from_user.username if callback.from_user.username else 'нет'}\n\n"
        f"💰 <b>Баланс:</b> {format_stars(balance)}\n\n"
        f"📊 <b>Статистика игр:</b>\n"
        f"├ 🎮 Сыграно: {stats['games_played']}\n"
        f"├ 🏆 Побед: {stats['games_won']}\n"
        f"├ 📈 Винрейт: {win_rate:.1f}%\n"
        f"├ 💰 Всего выиграно: {format_stars(stats['total_won'])}\n"
        f"└ 💸 Всего проиграно: {format_stars(stats['total_lost'])}\n\n"
        f"👥 <b>Рефералы:</b> {ref_count}\n\n"
        f"{get_random_emoji()} Продолжай играть и побеждать! {get_random_emoji()}"
    )
    
    await callback.message.edit_text(profile_text, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard(user_id))
    await callback.answer()

@dp.callback_query(F.data == "balance_info")
@subscription_required
async def balance_info(callback: CallbackQuery):
    await callback.answer(f"Твой баланс: {get_user_balance(callback.from_user.id)} Stars", show_alert=True)

@dp.callback_query(F.data == "daily_bonus")
@subscription_required
async def daily_bonus_button(callback: CallbackQuery):
    await cmd_bonus(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "games_menu")
@subscription_required
async def games_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎮 <b>Выбери игру</b> 🎮\n\n"
        f"{get_random_emoji()} Каждая игра — это шанс увеличить свой баланс!\n\n"
        "<i>Нажми на любую игру, чтобы начать</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "deposit")
@subscription_required
async def deposit_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "⭐️ <b>Пополнение баланса</b> ⭐️\n\n"
        "Пополняй баланс через Telegram Stars (XTR).\n"
        "После оплаты Stars поступят на твой счет мгновенно!\n\n"
        "<i>Выбери сумму:</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_deposit_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("deposit_"))
@subscription_required
async def deposit_amount(callback: CallbackQuery, state: FSMContext):
    amount_str = callback.data.split("_")[1]
    
    if amount_str == "custom":
        await callback.message.answer(
            "✏️ <b>Введи сумму пополнения</b>\n\n"
            "Минимум: 1 Star\n"
            "Максимум: 10000 Stars\n\n"
            "Просто отправь число в чат:",
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GameStates.custom_deposit)
        await callback.answer()
        return
    
    amount = int(amount_str)
    await create_stars_invoice(callback.message, callback.from_user.id, amount)
    await callback.answer()

@dp.message(GameStates.custom_deposit)
@subscription_required
async def process_custom_deposit(message: Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        if amount < 1:
            await message.answer("❌ Минимум 1 Star. Попробуй снова:")
            return
        if amount > 10000:
            await message.answer("❌ Максимум 10000 Stars. Попробуй снова:")
            return
    except ValueError:
        await message.answer("❌ Введи число. Попробуй снова:")
        return
    
    await state.clear()
    await create_stars_invoice(message, message.from_user.id, amount)


# ===================== ПЛАТЕЖИ =====================
async def create_stars_invoice(message: types.Message, user_id: int, amount: int):
    if amount < 1:
        await message.answer("❌ Сумма должна быть не менее 1 Star")
        return
    
    if amount > 10000:
        await message.answer("❌ Максимальная сумма — 10000 Stars")
        return
    
    title = "⭐️ Пополнение StarPlay"
    description = f"Пополнение игрового баланса на {amount} Telegram Stars"
    payload = f"starplay_{user_id}_{amount}_{int(datetime.now().timestamp())}"
    prices = [LabeledPrice(label="Telegram Stars", amount=amount)]
    
    await bot.send_invoice(
        chat_id=user_id,
        title=title,
        description=description,
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=prices,
        start_parameter="starplay_deposit",
        need_name=False,
        need_phone_number=False,
        need_email=False,
        need_shipping_address=False,
        is_flexible=False
    )
    
    pending_payments[payload] = {
        "user_id": user_id,
        "amount": amount,
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }

@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    payload = pre_checkout_query.invoice_payload
    
    if payload not in pending_payments:
        await pre_checkout_query.answer(ok=False, error_message="Ошибка платежа. Попробуй снова.")
        return
    
    await pre_checkout_query.answer(ok=True)

@dp.message(F.successful_payment)
@subscription_required
async def process_payment(message: Message):
    payment = message.successful_payment
    payload = payment.invoice_payload
    amount = payment.total_amount  # Для XTR это количество Stars
    user_id = message.from_user.id
    
    payment_info = pending_payments.get(payload)
    if not payment_info:
        await message.answer(
            "⚠️ Получен неизвестный платеж. Обратись к администратору.",
            reply_markup=get_main_keyboard(user_id)
        )
        return
    
    deposit_amount = payment_info["amount"]
    new_balance = update_balance(user_id, deposit_amount)
    save_transaction(user_id, deposit_amount, "deposit", f"Пополнение {deposit_amount} Stars")
    
    # Начисляем реферальный бонус пригласившему (если есть)
    if user_id in users_referrer:
        referrer_id = users_referrer[user_id]
        referral_bonus = int(deposit_amount * REFERRAL_BONUS_PERCENT / 100)
        if referral_bonus > 0:
            update_balance(referrer_id, referral_bonus)
            save_transaction(referrer_id, referral_bonus, "referral_earning", f"{REFERRAL_BONUS_PERCENT}% от пополнения реферала")
    
    payment_info["status"] = "completed"
    
    await message.answer(
        f"✅ <b>Платеж успешно обработан!</b>\n\n"
        f"Пополнение: +{format_stars(deposit_amount)}\n"
        f"💰 Новый баланс: {format_stars(new_balance)}\n\n"
        f"🎮 Приятной игры в StarPlay!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(user_id)
    )
    
    # Уведомление админу
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"💸 <b>Новый платеж</b>\n"
                f"👤 {message.from_user.first_name} (@{message.from_user.username or 'нет'})\n"
                f"⭐️ +{deposit_amount} Stars\n"
                f"💰 Баланс: {new_balance}",
                parse_mode=ParseMode.HTML
            )
        except:
            pass


@dp.callback_query(F.data == "main_menu")
@subscription_required
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        f"🌟 <b>StarPlay — Главное меню</b> 🌟\n\n"
        f"{get_random_emoji()} Выбери действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(callback.from_user.id)
    )
    await callback.answer()

@dp.callback_query(F.data == "check_subscription")
@subscription_required
async def check_subscription(callback: CallbackQuery):
    """Обработчик для проверки подписки после нажатия кнопки"""
    user_id = callback.from_user.id
    # Обновляем кэш статуса подписки
    user_subscription_status.pop(user_id, None)
    if await check_user_subscription(user_id):
        await callback.message.delete()
        await cmd_start(callback.message)
    else:
        await callback.answer("Вы еще не подписались на все каналы!", show_alert=True)


# ===================== ЗАПУСК =====================
async def main():
    logger.info("🚀 StarPlay Bot запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())