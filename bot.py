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
    ReplyKeyboardMarkup, KeyboardButton, FSInputFile
)
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# ===================== КОНФИГУРАЦИЯ =====================
BOT_TOKEN = "8251949164:AAE1fYvR_cMK7PnykcqpCxaXS9vIWxo1VjQ"
ADMIN_USERNAMES = ["tim2011", "admin"]

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
    roulette_bet = State()
    darts_bet = State()
    football_bet = State()
    bowling_bet = State()
    basketball_bet = State()
    mines_game = State()
    pyramid_game = State()
    slots_game = State()
    admin_find_user = State()
    admin_change_balance = State()
    admin_send_message = State()


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
            "pyramid_wins": 0, "slots_wins": 0,
            "darts_high_score": 0, "football_goals": 0, "basketball_hits": 0, "bowling_strikes": 0
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


# ===================== ИГРА: ДАРТС =====================
@dp.message(F.text == "🎯 Дартс")
async def darts_start(message: Message):
    await message.answer(
        "🎯 <b>ИГРА ДАРТС</b> 🎯\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🎲 <b>Правила:</b>\n"
        "• У тебя есть 3 броска дротика\n"
        "• Цель — набрать 150+ очков\n"
        "• Каждый бросок попадает в случайный сектор:\n"
        "  🎯 1-20 — обычный сектор\n"
        "  🟢 25 — зеленое кольцо\n"
        "  🔴 40-50 — около яблочка\n"
        "  💥 50 — ЯБЛОЧКО!\n\n"
        "🎁 <b>Выигрыш:</b>\n"
        "• 150+ очков → x1.5 к ставке\n"
        "• 200+ очков → x2 к ставке\n"
        "• 250+ очков → x3 к ставке (МАСТЕР!)\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("darts")
    )

@dp.callback_query(F.data.startswith("darts_bet_"))
async def darts_play(callback: CallbackQuery):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    balance = get_user_balance(user_id)
    
    if balance < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}!", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    
    # Генерация 3 бросков с визуальным оформлением
    throws = []
    throw_details = []
    total = 0
    
    for i in range(3):
        r = random.random()
        if r < 0.55:
            score = random.randint(1, 20)
            if score <= 5:
                icon = "🎯"
            elif score <= 10:
                icon = "🎯"
            elif score <= 15:
                icon = "🎯"
            else:
                icon = "🎯"
            detail = f"{icon} {score} очков"
        elif r < 0.75:
            score = 25
            icon = "🟢"
            detail = f"{icon} ЗЕЛЕНОЕ КОЛЬЦО! +25"
        elif r < 0.92:
            score = random.choice([40, 45, 50])
            icon = "🔴"
            if score == 50:
                icon = "💥"
                detail = f"{icon} ЯБЛОЧКО!!! +50"
            else:
                detail = f"{icon} {score} очков!"
        else:
            score = 50
            icon = "💥"
            detail = f"{icon} ЯБЛОЧКО!!! +50"
        
        throws.append(score)
        throw_details.append(detail)
        total += score
    
    # Визуализация бросков
    darts_visual = ""
    for i, t in enumerate(throws, 1):
        if t < 20:
            darts_visual += f"┌─────┐\n│  {t:2d}  │\n└─────┘ "
        elif t < 40:
            darts_visual += f"┌─────┐\n│ {t} │\n└─────┘ "
        else:
            darts_visual += f"┌─────┐\n│ {t} │\n└─────┘ "
    
    # Определение выигрыша
    if total >= 250:
        multiplier = 3
        win_message = "🔥🔥🔥 <b>НЕВЕРОЯТНО!</b> 🔥🔥🔥\nТы показал мастер-класс!"
    elif total >= 200:
        multiplier = 2
        win_message = "🎯🎯 <b>ОТЛИЧНАЯ ИГРА!</b> 🎯🎯\nПрофессиональный уровень!"
    elif total >= 150:
        multiplier = 1.5
        win_message = "🎯 <b>ХОРОШИЙ РЕЗУЛЬТАТ!</b> 🎯\nТы справился отлично!"
    else:
        multiplier = 0
        win_message = "😢 <b>НЕ ПОВЕЗЛО</b> 😢\nВ следующий раз обязательно получится!"
    
    if multiplier > 0:
        winnings = int(bet * multiplier)
        update_balance(user_id, winnings)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["darts_wins"] += 1
        stats["total_won"] += winnings
        if total > stats.get("darts_high_score", 0):
            stats["darts_high_score"] = total
        save_transaction(user_id, winnings, "game_win", f"Дартс {total} очков x{multiplier}")
        result = f"🏆 <b>ВЫИГРЫШ!</b> +{format_stars(winnings)} 🏆"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", f"Дартс {total} очков")
        result = f"💔 <b>ПРОИГРЫШ</b> -{format_stars(bet)} 💔"
    
    # Анимация попаданий
    animation_frames = []
    for i, detail in enumerate(throw_details, 1):
        frame = f"🎯 <b>Бросок {i}/3</b>\n\n{detail}"
        animation_frames.append(frame)
    
    # Отправляем анимацию бросков
    for frame in animation_frames:
        await callback.message.edit_text(
            frame,
            parse_mode=ParseMode.HTML
        )
        await asyncio.sleep(0.8)
    
    # Финальный результат
    final_message = (
        f"🎯 <b>ИГРА ДАРТС</b> 🎯\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"{darts_visual}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Результат:</b>\n"
        f"├ Бросок 1: {throw_details[0]}\n"
        f"├ Бросок 2: {throw_details[1]}\n"
        f"└ Бросок 3: {throw_details[2]}\n\n"
        f"✨ <b>ИТОГО: {total} очков</b>\n\n"
        f"{win_message}\n\n"
        f"{result}\n\n"
        f"💰 <b>Новый баланс:</b> {format_stars(get_user_balance(user_id))}\n\n"
        f"{'🎯' * min(5, total//50)}"
    )
    
    await callback.message.edit_text(final_message, parse_mode=ParseMode.HTML)
    await callback.answer()


# ===================== ИГРА: ФУТБОЛ =====================
@dp.message(F.text == "⚽️ Футбол")
async def football_start(message: Message):
    await message.answer(
        "⚽️ <b>ИГРА ФУТБОЛ</b> ⚽️\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🎲 <b>Правила:</b>\n"
        "• У тебя 3 пенальти\n"
        "• Нужно забить 2+ гола для выигрыша\n"
        "• Вратарь двигается случайно\n\n"
        "🎁 <b>Выигрыш:</b>\n"
        "• 2 гола → x2 к ставке\n"
        "• 3 гола → x3 к ставке (ХЕТ-ТРИК!)\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("football")
    )

@dp.callback_query(F.data.startswith("football_bet_"))
async def football_play(callback: CallbackQuery):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    balance = get_user_balance(user_id)
    
    if balance < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}!", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    
    # Визуализация ударов
    goal_animation = ["🧤", "⚽️", "🥅", "🧤⚽️", "⚽️🥅", "🥅⚽️🧤"]
    goals = 0
    results = []
    animation_messages = []
    
    # Поле для визуализации
    field = "┌─────────────────┐\n│      ⚽️🥅      │\n└─────────────────┘"
    
    for i in range(3):
        # Шанс гола 40%
        is_goal = random.random() < 0.4
        
        if is_goal:
            goals += 1
            goal_type = random.choice(["нижний угол", "верхний угол", "девятка", "штанга-гол"])
            results.append(f"⚽️ <b>ГОЛ!</b> ({goal_type})")
            animation = "⚽️ ===> 🥅  ГООООЛ!"
        else:
            save_type = random.choice(["в руки", "на угол", "штанга", "перекладина", "мимо"])
            results.append(f"🧤 <b>СЕЙВ!</b> (вратарь поймал в {save_type})")
            animation = "🧤 <=== ⚽️  СЕЙВ!"
        
        animation_messages.append(animation)
        
        # Отправляем анимацию удара
        await callback.message.edit_text(
            f"⚽️ <b>Пенальти {i+1}/3</b>\n\n"
            f"{field}\n\n"
            f"🏃‍♂️ Удар...\n\n"
            f"{animation}\n\n"
            f"<i>Результат: {results[-1]}</i>",
            parse_mode=ParseMode.HTML
        )
        await asyncio.sleep(1)
    
    # Определение выигрыша
    if goals >= 3:
        multiplier = 3
        win_message = "🎉🎉🎉 <b>ХЕТ-ТРИК!</b> 🎉🎉🎉\nТы забил 3 гола — невероятный результат!"
    elif goals >= 2:
        multiplier = 2
        win_message = "🎉 <b>ПОБЕДА!</b> 🎉\nОтличная игра! Ты забил нужное количество голов!"
    else:
        multiplier = 0
        win_message = "😢 <b>ПОРАЖЕНИЕ</b> 😢\nВратарь был сегодня на высоте..."
    
    if multiplier > 0:
        winnings = bet * multiplier
        update_balance(user_id, winnings)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["football_wins"] += 1
        stats["total_won"] += winnings
        if goals > stats.get("football_goals", 0):
            stats["football_goals"] = goals
        save_transaction(user_id, winnings, "game_win", f"Футбол {goals} гола x{multiplier}")
        result = f"🏆 <b>ВЫИГРЫШ!</b> +{format_stars(winnings)} 🏆"
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", f"Футбол {goals} гола")
        result = f"💔 <b>ПРОИГРЫШ</b> -{format_stars(bet)} 💔"
    
    # Таблица результатов
    table = ""
    for i, r in enumerate(results, 1):
        table += f"├ Удар {i}: {r}\n"
    
    final_message = (
        f"⚽️ <b>ИГРА ФУТБОЛ</b> ⚽️\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Результаты пенальти:</b>\n"
        f"{table}"
        f"└═══════════════════════\n\n"
        f"✨ <b>ИТОГО: {goals}/3 голов</b>\n\n"
        f"{win_message}\n\n"
        f"{result}\n\n"
        f"💰 <b>Новый баланс:</b> {format_stars(get_user_balance(user_id))}\n\n"
        f"{'⚽️' * goals}"
    )
    
    await callback.message.edit_text(final_message, parse_mode=ParseMode.HTML)
    await callback.answer()


# ===================== ИГРА: БОУЛИНГ =====================
@dp.message(F.text == "🎳 Боулинг")
async def bowling_start(message: Message):
    await message.answer(
        "🎳 <b>ИГРА БОУЛИНГ</b> 🎳\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🎲 <b>Правила:</b>\n"
        "• У тебя есть 1 фрейм (2 броска)\n"
        "• Нужно сбить как можно больше кеглей\n\n"
        "🎁 <b>Выигрыш:</b>\n"
        "• 10 кегль (СТРАЙК) → x3 к ставке\n"
        "• Спэр (10 кегль за 2 броска) → x2 к ставке\n"
        "• 8-9 кегль → x1.2 к ставке\n"
        "• Меньше 8 кегль → проигрыш\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("bowling")
    )

@dp.callback_query(F.data.startswith("bowling_bet_"))
async def bowling_play(callback: CallbackQuery):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    balance = get_user_balance(user_id)
    
    if balance < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}!", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    
    # Визуализация кеглей
    pins = ["🎳" for _ in range(10)]
    
    # Первый бросок
    first = random.randint(0, 10)
    pins_left = 10 - first
    
    # Визуализация после первого броска
    pins_visual_first = "".join(pins[:first]) + "💥" * first + "".join(pins[first:]) if first < 10 else "💥" * 10 + " ВСЕ СБИТЫ!"
    
    await callback.message.edit_text(
        f"🎳 <b>БОУЛИНГ</b> 🎳\n\n"
        f"┌─────────────────┐\n"
        f"│  {pins_visual_first[:15]}  │\n"
        f"└─────────────────┘\n\n"
        f"🎳 <b>Первый бросок:</b>\n"
        f"Сбито кеглей: {first}\n"
        f"Осталось: {pins_left}\n\n"
        f"💫 <i>Готовимся ко второму броску...</i>",
        parse_mode=ParseMode.HTML
    )
    await asyncio.sleep(1.5)
    
    if first == 10:
        # СТРАЙК
        multiplier = 3
        winnings = int(bet * multiplier)
        update_balance(user_id, winnings)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["bowling_wins"] += 1
        stats["bowling_strikes"] = stats.get("bowling_strikes", 0) + 1
        stats["total_won"] += winnings
        save_transaction(user_id, winnings, "game_win", "Боулинг СТРАЙК")
        
        final_message = (
            f"🎳 <b>БОУЛИНГ</b> 🎳\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"┌─────────────────┐\n"
            f"│  💥💥💥 СТРАЙК! 💥💥💥  │\n"
            f"└─────────────────┘\n\n"
            f"🎳 <b>Результат:</b>\n"
            f"├ Первый бросок: <b>{first} кегль</b>\n"
            f"└ СТРАЙК! Все кегли сбиты с первого раза!\n\n"
            f"🏆 <b>ВЫИГРЫШ x3!</b>\n"
            f"{format_stars(winnings)}\n\n"
            f"💰 <b>Новый баланс:</b> {format_stars(get_user_balance(user_id))}\n\n"
            f"🎳✨🎳"
        )
        
        await callback.message.edit_text(final_message, parse_mode=ParseMode.HTML)
        await callback.answer()
        return
    
    # Второй бросок
    second = random.randint(0, pins_left)
    total = first + second
    
    # Визуализация второго броска
    pins_visual_second = "💥" * second + "🎳" * (pins_left - second)
    
    await callback.message.edit_text(
        f"🎳 <b>БОУЛИНГ</b> 🎳\n\n"
        f"┌─────────────────┐\n"
        f"│  {pins_visual_second[:15]}  │\n"
        f"└─────────────────┘\n\n"
        f"🎳 <b>Второй бросок:</b>\n"
        f"Сбито кеглей: {second}\n"
        f"Всего сбито: {total}\n\n"
        f"🎯 <i>Считаем результат...</i>",
        parse_mode=ParseMode.HTML
    )
    await asyncio.sleep(1.5)
    
    # Определение результата
    if total == 10:
        multiplier = 2
        winnings = int(bet * multiplier)
        update_balance(user_id, winnings)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["bowling_wins"] += 1
        stats["total_won"] += winnings
        save_transaction(user_id, winnings, "game_win", f"Боулинг СПЭР {first}+{second}")
        
        final_message = (
            f"🎳 <b>БОУЛИНГ</b> 🎳\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎳 <b>Результат:</b>\n"
            f"├ Первый бросок: {first} кегль\n"
            f"└ Второй бросок: {second} кегль\n\n"
            f"✨ <b>СПЭР!</b> ✨\n"
            f"Всего сбито: {total}/10 кеглей\n\n"
            f"🏆 <b>ВЫИГРЫШ x2!</b>\n"
            f"+{format_stars(winnings)}\n\n"
            f"💰 <b>Новый баланс:</b> {format_stars(get_user_balance(user_id))}\n\n"
            f"🎳🎯🎳"
        )
        
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
        
        final_message = (
            f"🎳 <b>БОУЛИНГ</b> 🎳\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎳 <b>Результат:</b>\n"
            f"├ Первый бросок: {first} кегль\n"
            f"└ Второй бросок: {second} кегль\n\n"
            f"✨ <b>ХОРОШИЙ РЕЗУЛЬТАТ!</b> ✨\n"
            f"Всего сбито: {total}/10 кеглей\n\n"
            f"🏆 <b>ВЫИГРЫШ x{multiplier}!</b>\n"
            f"+{format_stars(winnings)}\n\n"
            f"💰 <b>Новый баланс:</b> {format_stars(get_user_balance(user_id))}\n\n"
            f"🎳💪🎳"
        )
        
    else:
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["total_lost"] += bet
        save_transaction(user_id, -bet, "game_loss", f"Боулинг {total} кегль")
        
        final_message = (
            f"🎳 <b>БОУЛИНГ</b> 🎳\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎳 <b>Результат:</b>\n"
            f"├ Первый бросок: {first} кегль\n"
            f"└ Второй бросок: {second} кегль\n\n"
            f"😢 <b>НЕУДАЧА</b> 😢\n"
            f"Всего сбито: {total}/10 кеглей\n\n"
            f"💔 <b>ПРОИГРЫШ</b>\n"
            f"-{format_stars(bet)}\n\n"
            f"💰 <b>Новый баланс:</b> {format_stars(get_user_balance(user_id))}\n\n"
            f"🎳😢🎳"
        )
    
    await callback.message.edit_text(final_message, parse_mode=ParseMode.HTML)
    await callback.answer()


# ===================== ИГРА: БАСКЕТБОЛ =====================
@dp.message(F.text == "🏀 Баскетбол")
async def basketball_start(message: Message):
    await message.answer(
        "🏀 <b>ИГРА БАСКЕТБОЛ</b> 🏀\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🎲 <b>Правила:</b>\n"
        "• У тебя 5 трёхочковых бросков\n"
        "• Каждое попадание увеличивает выигрыш\n\n"
        "🎁 <b>Выигрыш:</b>\n"
        "• 1-2 попадания → x0.3 за каждое\n"
        "• 3-4 попадания → x2 к ставке\n"
        "• 5 попаданий → x2.5 к ставке (ПЕРФЕКТ!)\n\n"
        "Выбери сумму ставки:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bet_keyboard("basketball")
    )

@dp.callback_query(F.data.startswith("basketball_bet_"))
async def basketball_play(callback: CallbackQuery):
    bet = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    balance = get_user_balance(user_id)
    
    if balance < bet:
        await callback.answer(f"❌ Не хватает {format_stars(bet)}!", show_alert=True)
        return
    
    update_balance(user_id, -bet)
    
    # Симуляция бросков
    hits = 0
    results = []
    shot_animations = []
    
    # Корзина для визуализации
    basket = "🏀"
    
    for i in range(5):
        # Шанс попадания 40%
        is_hit = random.random() < 0.4
        
        if is_hit:
            hits += 1
            shot_type = random.choice(["сверху", "со средней", "из-за дуги", "с рикошетом"])
            results.append(f"🏀 <b>ПОПАДАНИЕ!</b> ({shot_type})")
            shot_animations.append("🏀 ===> 🧺   ПОПАЛ!")
        else:
            miss_type = random.choice(["в кольцо", "мимо", "в щит", "блок", "не докинул"])
            results.append(f"❌ <b>ПРОМАХ</b> (бросок {miss_type})")
            shot_animations.append("🏀 ===> ❌   МИМО!")
        
        # Анимация броска
        progress = "█" * (i + 1) + "░" * (4 - i)
        
        await callback.message.edit_text(
            f"🏀 <b>БАСКЕТБОЛ</b> 🏀\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Бросок {i+1}/5</b>\n\n"
            f"{basket * (i+1) + '🚫' * (5-i-1)}\n"
            f"┌─────────────────┐\n"
            f"│   🏀 → 🧺       │\n"
            f"└─────────────────┘\n\n"
            f"<b>Прогресс:</b> [{progress}] {i+1}/5\n\n"
            f"{shot_animations[-1]}\n\n"
            f"<i>Результат: {results[-1]}</i>",
            parse_mode=ParseMode.HTML
        )
        await asyncio.sleep(0.8)
    
    # Анимация финальной симуляции
    for i in range(3):
        await callback.message.edit_text(
            f"🏀 <b>БАСКЕТБОЛ</b> 🏀\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>Подсчёт результатов...</b>\n\n"
            f"{'.' * (i+1)}",
            parse_mode=ParseMode.HTML
        )
        await asyncio.sleep(0.5)
    
    # Определение выигрыша
    if hits == 5:
        multiplier = 2.5
        win_message = "🔥🔥🔥 <b>ПЕРФЕКТ!</b> 🔥🔥🔥\n5 из 5! Ты настоящая звезда баскетбола!"
    elif hits >= 3:
        multiplier = 2
        win_message = "🎉🎉 <b>ОТЛИЧНАЯ ИГРА!</b> 🎉🎉\nОтличная реализация бросков!"
    else:
        multiplier = 0
        win_message = "😢 <b>НУЖНО БОЛЬШЕ ТРЕНИРОВОК</b> 😢\nВ следующий раз обязательно получится!"
    
    if multiplier > 0:
        winnings = int(bet * multiplier)
        update_balance(user_id, winnings)
        stats = get_user_stats(user_id)
        stats["games_played"] += 1
        stats["games_won"] += 1
        stats["basketball_wins"] += 1
        stats["total_won"] += winnings
        if hits > stats.get("basketball_hits", 0):
            stats["basketball_hits"] = hits
        save_transaction(user_id, winnings, "game_win", f"Баскетбол {hits}/5 x{multiplier}")
        result = f"🏆 <b>ВЫИГРЫШ!</b> +{format_stars(winnings)} 🏆"
    else:
        # Даже при 0-2 попаданиях даём утешительный приз
        consolation = int(bet * hits * 0.3)
        if consolation > 0:
            update_balance(user_id, consolation)
            stats = get_user_stats(user_id)
            stats["games_played"] += 1
            stats["total_won"] += consolation
            save_transaction(user_id, consolation, "game_win", f"Баскетбол {hits}/5 утешительный")
            result = f"🎁 <b>УТЕШИТЕЛЬНЫЙ ПРИЗ!</b> +{format_stars(consolation)} 🎁"
            win_message = "👍 <b>НЕПЛОХО</b> 👍\nВ следующий раз будет больше!"
        else:
            stats = get_user_stats(user_id)
            stats["games_played"] += 1
            stats["total_lost"] += bet
            save_transaction(user_id, -bet, "game_loss", f"Баскетбол {hits}/5")
            result = f"💔 <b>ПРОИГРЫШ</b> -{format_stars(bet)} 💔"
    
    # Звёздный рейтинг
    stars = "⭐️" * hits + "☆" * (5 - hits)
    
    final_message = (
        f"🏀 <b>БАСКЕТБОЛ</b> 🏀\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Статистика бросков:</b>\n"
        f"├ Бросок 1: {results[0]}\n"
        f"├ Бросок 2: {results[1]}\n"
        f"├ Бросок 3: {results[2]}\n"
        f"├ Бросок 4: {results[3]}\n"
        f"└ Бросок 5: {results[4]}\n\n"
        f"✨ <b>ИТОГО: {hits}/5 попаданий</b>\n"
        f"📊 <b>Рейтинг:</b> {stars}\n\n"
        f"{win_message}\n\n"
        f"{result}\n\n"
        f"💰 <b>Новый баланс:</b> {format_stars(get_user_balance(user_id))}\n\n"
        f"{'🏀' * hits}"
    )
    
    await callback.message.edit_text(final_message, parse_mode=ParseMode.HTML)
    await callback.answer()


# ===================== ОСТАЛЬНЫЕ ОБРАБОТЧИКИ (кратко) =====================
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

@dp.message(Command("balance"))
async def cmd_balance(message: Message):
    user_id = message.from_user.id
    await message.answer(
        f"💰 <b>Твой баланс:</b> {format_stars(get_user_balance(user_id))}",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text == "💰 Баланс")
async def balance_reply(message: Message):
    await cmd_balance(message)

@dp.message(F.text == "🔙 Главное меню")
async def back_to_main_from_games(message: Message):
    username = message.from_user.username or ""
    keyboard = get_admin_keyboard() if is_admin(username) else get_main_keyboard()
    await message.answer(
        "🌟 <b>Главное меню</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

@dp.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    username = message.from_user.username or ""
    keyboard = get_admin_keyboard() if is_admin(username) else get_main_keyboard()
    await message.answer("❌ Действие отменено.", reply_markup=keyboard)

@dp.callback_query(F.data == "back_to_games")
async def back_to_games(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer(
        "🎮 <b>Выбери игру</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_games_keyboard()
    )
    await callback.answer()


# ===================== ПЛАТЕЖИ И АДМИН-ПАНЕЛЬ =====================
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
        f"✅ <b>Пополнение выполнено!</b>\n\n+{format_stars(amount)}\n💰 Новый баланс: {format_stars(new_balance)}",
        parse_mode=ParseMode.HTML
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
    text = (
        f"👥 <b>Реферальная система</b>\n\n"
        f"🔗 Твоя ссылка:\n<code>{ref_link}</code>\n\n"
        f"📋 Друг получает +{REFERRAL_SIGNUP_BONUS} Stars\n"
        f"🎁 Ты получаешь +{REFERRAL_INVITE_BONUS} Stars\n"
        f"💰 Ты получаешь {REFERRAL_BONUS_PERCENT}% с пополнений друга"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "🏆 Топ")
async def top_reply(message: Message):
    sorted_users = sorted(users_balance.items(), key=lambda x: x[1], reverse=True)[:15]
    if not sorted_users:
        await message.answer("🏆 Пока нет игроков в рейтинге!")
        return
    top_text = "🏆 <b>ТОП-15 ИГРОКОВ</b>\n\n"
    for idx, (uid, bal) in enumerate(sorted_users, 1):
        medal = {1:"🥇",2:"🥈",3:"🥉"}.get(idx, f"{idx}.")
        uname = users_username.get(uid, str(uid))
        name = f"@{uname}" if uname else str(uid)
        top_text += f"{medal} <b>{name}</b> — {bal} ⭐️\n"
    await message.answer(top_text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "📊 Профиль")
async def profile_reply(message: Message):
    uid = message.from_user.id
    stats = get_user_stats(uid)
    wr = (stats['games_won'] / max(stats['games_played'], 1)) * 100
    text = (
        f"👤 <b>Профиль игрока</b>\n\n"
        f"💰 Баланс: {format_stars(get_user_balance(uid))}\n"
        f"🎮 Игр сыграно: {stats['games_played']}\n"
        f"🏆 Побед: {stats['games_won']} ({wr:.1f}%)\n"
        f"💎 Выиграно: {format_stars(stats['total_won'])}\n"
        f"💸 Проиграно: {format_stars(stats['total_lost'])}\n\n"
        f"🏅 <b>Достижения:</b>\n"
        f"├ 🎯 Лучший дартс: {stats.get('darts_high_score', 0)}\n"
        f"├ ⚽️ Лучший футбол: {stats.get('football_goals', 0)} голов\n"
        f"├ 🎳 Страйков: {stats.get('bowling_strikes', 0)}\n"
        f"└ 🏀 Точность: {stats.get('basketball_hits', 0)}/5"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "🎁 Бонус")
async def bonus_reply(message: Message):
    user_id = message.from_user.id
    today = datetime.now().date().isoformat()
    if users_daily_bonus.get(user_id) == today:
        await message.answer("🎁 Ты уже получил сегодняшний бонус! Возвращайся завтра!")
        return
    bonus = random.randint(5, 15)
    update_balance(user_id, bonus)
    users_daily_bonus[user_id] = today
    await message.answer(f"🎉 <b>Ежедневный бонус!</b> +{format_stars(bonus)}")

@dp.message(F.text == "⭐️ Пополнить")
async def deposit_reply(message: Message):
    await message.answer(
        "⭐️ <b>Пополнение баланса</b>\n\nВыберите сумму:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_deposit_keyboard()
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

@dp.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery):
    username = callback.from_user.username or ""
    keyboard = get_admin_keyboard() if is_admin(username) else get_main_keyboard()
    await callback.message.delete()
    await callback.message.answer("🌟 <b>Главное меню</b>", parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()


# ===================== ЗАПУСК =====================
async def main():
    logger.info("🚀 StarPlay Bot запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    