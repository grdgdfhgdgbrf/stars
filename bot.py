"""
TELEGRAM БОТ С ИНТЕГРАЦИЕЙ BOTOHUB, ИГРОВОЙ ВАЛЮТОЙ И АДМИН-ПАНЕЛЬЮ
Версия: 2.0.0
Автор: Полный функциональный бот
"""

import asyncio
import random
import json
import os
import logging
import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple, Any
from collections import defaultdict
from dataclasses import dataclass, asdict
from enum import Enum
import threading

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    CallbackContext,
    ConversationHandler,
    PreCheckoutQueryHandler,
)
from telegram.constants import ParseMode
import aiohttp

# ========== НАСТРОЙКА ЛОГГИРОВАНИЯ ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = "ВАШ_ТОКЕН_БОТА"  # Замените на реальный токен
BOTOHUB_TOKEN = "ВАШ_ТОКЕН_BOTOHUB"  # Замените на реальный токен
BOTOHUB_API_URL = "https://botohub.me/get-tasks"
ADMIN_IDS = [5356403777]  # Список ID администраторов

# ========== ENUM ДЛЯ ТИПОВ ==========
class UserStatus(Enum):
    ACTIVE = "active"
    BANNED = "banned"
    VIP = "vip"
    PREMIUM = "premium"

class TransactionType(Enum):
    TASK_REWARD = "task_reward"
    DAILY_BONUS = "daily_bonus"
    REFERRAL_REWARD = "referral_reward"
    LOTTERY_WIN = "lottery_win"
    CASE_REWARD = "case_reward"
    GAME_WIN = "game_win"
    GAME_LOSS = "game_loss"
    WITHDRAW = "withdraw"
    ADMIN_GIVE = "admin_give"
    ADMIN_TAKE = "admin_take"

class GameType(Enum):
    CASINO = "casino"
    DICE = "dice"
    SLOTS = "slots"
    BLACKJACK = "blackjack"
    ROULETTE = "roulette"

# ========== DATACLASSES ==========
@dataclass
class UserData:
    user_id: int
    mcoin: int = 0
    username: str = ""
    first_name: str = ""
    last_name: str = ""
    status: str = "active"
    join_date: str = ""
    last_active: str = ""
    total_earned: int = 0
    total_spent: int = 0
    tasks_completed: List[int] = None
    inventory: List[Dict] = None
    referrals: List[int] = None
    referrer: int = None
    daily_last: str = None
    daily_streak: int = 0
    game_stats: Dict = None
    withdrawal_address: str = ""
    total_withdrawn: int = 0
    language: str = "ru"
    notification_settings: Dict = None
    
    def __post_init__(self):
        if self.tasks_completed is None:
            self.tasks_completed = []
        if self.inventory is None:
            self.inventory = []
        if self.referrals is None:
            self.referrals = []
        if self.game_stats is None:
            self.game_stats = {"wins": 0, "losses": 0, "total_bet": 0, "total_win": 0}
        if self.notification_settings is None:
            self.notification_settings = {"task_notify": True, "lottery_notify": True, "daily_notify": True}

@dataclass
class CaseItem:
    name: str
    chance: float
    reward: int
    description: str = ""

@dataclass
class Case:
    name: str
    price: int
    items: List[CaseItem]
    image_url: str = ""
    description: str = ""
    created_by: int = 0
    created_at: str = ""
    total_opened: int = 0

@dataclass
class Lottery:
    active: bool = False
    ticket_price: int = 10
    tickets: Dict[int, int] = None
    prize_pool: int = 0
    start_time: str = ""
    end_time: str = ""
    winner_id: int = None
    winner_amount: int = 0
    draw_time: str = ""
    
    def __post_init__(self):
        if self.tickets is None:
            self.tickets = {}

@dataclass
class Check:
    code: str
    amount: int
    created_by: int
    created_at: str
    used_by: int = None
    used_at: str = None
    is_used: bool = False

@dataclass
class WithdrawRequest:
    user_id: int
    amount: int
    address: str
    status: str  # pending, approved, rejected
    created_at: str
    processed_at: str = None
    processed_by: int = None

# ========== ГЛОБАЛЬНЫЕ ДАННЫЕ ==========
class BotDatabase:
    def __init__(self):
        self.users: Dict[int, UserData] = {}
        self.cases: Dict[str, Case] = {}
        self.lottery: Lottery = Lottery()
        self.checks: Dict[str, Check] = {}
        self.withdraw_requests: List[WithdrawRequest] = []
        self.pending_tasks: Dict[int, Dict] = {}
        self.daily_claims: Dict[int, str] = {}
        self.game_sessions: Dict[int, Dict] = {}
        self.temp_data: Dict[int, Dict] = {}
        
    def save(self, filename: str = "bot_data.json"):
        """Сохраняет все данные в JSON файл"""
        data = {
            "users": {str(k): asdict(v) for k, v in self.users.items()},
            "cases": {k: asdict(v) for k, v in self.cases.items()},
            "lottery": asdict(self.lottery),
            "checks": {k: asdict(v) for k, v in self.checks.items()},
            "withdraw_requests": [asdict(r) for r in self.withdraw_requests],
            "daily_claims": self.daily_claims
        }
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Data saved to {filename}")
    
    def load(self, filename: str = "bot_data.json"):
        """Загружает данные из JSON файла"""
        if not os.path.exists(filename):
            logger.info(f"File {filename} not found, creating new database")
            return
            
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Загрузка пользователей
            for user_id_str, user_data in data.get("users", {}).items():
                user_id = int(user_id_str)
                self.users[user_id] = UserData(**user_data)
            
            # Загрузка кейсов
            for case_name, case_data in data.get("cases", {}).items():
                items = [CaseItem(**item) for item in case_data.get("items", [])]
                case_data["items"] = items
                self.cases[case_name] = Case(**case_data)
            
            # Загрузка лотереи
            lottery_data = data.get("lottery", {})
            self.lottery = Lottery(**lottery_data)
            
            # Загрузка чеков
            for check_code, check_data in data.get("checks", {}).items():
                self.checks[check_code] = Check(**check_data)
            
            # Загрузка запросов на вывод
            for req_data in data.get("withdraw_requests", []):
                self.withdraw_requests.append(WithdrawRequest(**req_data))
            
            # Загрузка ежедневных наград
            self.daily_claims = data.get("daily_claims", {})
            
            logger.info(f"Data loaded from {filename}")
        except Exception as e:
            logger.error(f"Error loading data: {e}")

# ========== ИНИЦИАЛИЗАЦИЯ ==========
db = BotDatabase()
db.load()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_user(user_id: int) -> UserData:
    """Получает пользователя, создаёт если не существует"""
    if user_id not in db.users:
        db.users[user_id] = UserData(
            user_id=user_id,
            join_date=datetime.now().isoformat(),
            last_active=datetime.now().isoformat()
        )
        db.save()
    return db.users[user_id]

def add_mcoins(user_id: int, amount: int, reason: TransactionType, description: str = "") -> int:
    """Добавляет MCoin пользователю"""
    user = get_user(user_id)
    user.mcoin += amount
    user.total_earned += amount
    user.last_active = datetime.now().isoformat()
    db.save()
    logger.info(f"Added {amount} MCoin to user {user_id} for {reason.value}")
    return user.mcoin

def remove_mcoins(user_id: int, amount: int, reason: TransactionType, description: str = "") -> bool:
    """Снимает MCoin, возвращает True если достаточно"""
    user = get_user(user_id)
    if user.mcoin >= amount:
        user.mcoin -= amount
        user.total_spent += amount
        user.last_active = datetime.now().isoformat()
        db.save()
        logger.info(f"Removed {amount} MCoin from user {user_id} for {reason.value}")
        return True
    return False

def generate_check_code() -> str:
    """Генерирует уникальный код для чека"""
    timestamp = str(int(time.time()))
    random_str = str(random.randint(100000, 999999))
    code = hashlib.md5(f"{timestamp}{random_str}".encode()).hexdigest()[:12].upper()
    return code

def format_number(num: int) -> str:
    """Форматирует число с разделителями"""
    return f"{num:,}".replace(",", " ")

def get_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Создаёт главную клавиатуру"""
    keyboard = [
        [KeyboardButton("💰 БАЛАНС"), KeyboardButton("📋 ЗАДАНИЯ")],
        [KeyboardButton("🎮 ИГРЫ"), KeyboardButton("📦 КЕЙСЫ")],
        [KeyboardButton("🎰 ЛОТЕРЕЯ"), KeyboardButton("👥 РЕФЕРАЛЫ")],
        [KeyboardButton("🏆 ЕЖЕДНЕВНЫЙ"), KeyboardButton("💸 ВЫВОД")],
        [KeyboardButton("📝 ЧЕКИ"), KeyboardButton("❓ ПОМОЩЬ")]
    ]
    
    if user_id in ADMIN_IDS:
        keyboard.append([KeyboardButton("⚙️ АДМИН ПАНЕЛЬ")])
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ========== ИГРЫ ==========
async def game_casino(update: Update, context: CallbackContext):
    """Игра Казино (угадай число)"""
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "🎰 **ИГРА КАЗИНО** 🎰\n\n"
            "Правила: угадайте число от 1 до 10\n"
            "Выигрыш: x2 - x5 вашей ставки\n\n"
            "Использование: `/casino <сумма> <число>`\n"
            "Пример: `/casino 100 7`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    try:
        if len(args) < 2:
            raise ValueError
        bet = int(args[0])
        user_number = int(args[1])
        
        if bet <= 0 or user_number < 1 or user_number > 10:
            raise ValueError
    except:
        await update.message.reply_text("❌ Неверный формат! Используйте: `/casino 100 7`", parse_mode=ParseMode.MARKDOWN)
        return
    
    user = get_user(user_id)
    if user.mcoin < bet:
        await update.message.reply_text(f"❌ Недостаточно средств! У вас {format_number(user.mcoin)} MCoin")
        return
    
    # Проверка лимитов
    max_bet = min(10000, user.mcoin)
    if bet > max_bet:
        await update.message.reply_text(f"⚠️ Максимальная ставка: {format_number(max_bet)} MCoin")
        return
    
    remove_mcoins(user_id, bet, TransactionType.GAME_LOSS, f"Casino bet on {user_number}")
    
    # Генерация случайного числа
    lucky_number = random.randint(1, 10)
    
    if user_number == lucky_number:
        # Точное попадание - x5
        win_amount = bet * 5
        add_mcoins(user_id, win_amount, TransactionType.GAME_WIN, "Casino exact win")
        user.game_stats["wins"] += 1
        user.game_stats["total_win"] += win_amount
        db.save()
        
        await update.message.reply_text(
            f"🎉 **ПОБЕДА!** 🎉\n\n"
            f"🎲 Ваше число: {user_number}\n"
            f"🎯 Выигрышное число: {lucky_number}\n"
            f"💎 Вы угадали точно!\n"
            f"💰 Выигрыш: {format_number(win_amount)} MCoin\n"
            f"📊 Баланс: {format_number(user.mcoin)} MCoin",
            parse_mode=ParseMode.MARKDOWN
        )
    elif abs(user_number - lucky_number) <= 2:
        # Близко - x2
        win_amount = bet * 2
        add_mcoins(user_id, win_amount, TransactionType.GAME_WIN, "Casino close win")
        user.game_stats["wins"] += 1
        user.game_stats["total_win"] += win_amount
        db.save()
        
        await update.message.reply_text(
            f"🎉 **ПОБЕДА!** 🎉\n\n"
            f"🎲 Ваше число: {user_number}\n"
            f"🎯 Выигрышное число: {lucky_number}\n"
            f"📊 Вы были близки!\n"
            f"💰 Выигрыш: {format_number(win_amount)} MCoin\n"
            f"📊 Баланс: {format_number(user.mcoin)} MCoin",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        # Проигрыш
        user.game_stats["losses"] += 1
        user.game_stats["total_bet"] += bet
        db.save()
        
        await update.message.reply_text(
            f"😢 **ПРОИГРЫШ** 😢\n\n"
            f"🎲 Ваше число: {user_number}\n"
            f"🎯 Выигрышное число: {lucky_number}\n"
            f"📊 Проиграно: {format_number(bet)} MCoin\n"
            f"📊 Баланс: {format_number(user.mcoin)} MCoin",
            parse_mode=ParseMode.MARKDOWN
        )

async def game_dice(update: Update, context: CallbackContext):
    """Игра Кости"""
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "🎲 **ИГРА КОСТИ** 🎲\n\n"
            "Правила: угадайте, какое число выпадет (1-6)\n"
            "Выигрыш: x3 при точном попадании\n\n"
            "Использование: `/dice <сумма> <число>`\n"
            "Пример: `/dice 50 3`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    try:
        if len(args) < 2:
            raise ValueError
        bet = int(args[0])
        user_number = int(args[1])
        
        if bet <= 0 or user_number < 1 or user_number > 6:
            raise ValueError
    except:
        await update.message.reply_text("❌ Неверный формат! Используйте: `/dice 50 3`", parse_mode=ParseMode.MARKDOWN)
        return
    
    user = get_user(user_id)
    if user.mcoin < bet:
        await update.message.reply_text(f"❌ Недостаточно средств! У вас {format_number(user.mcoin)} MCoin")
        return
    
    remove_mcoins(user_id, bet, TransactionType.GAME_LOSS, "Dice bet")
    
    # Бросаем кости
    dice_result = random.randint(1, 6)
    
    if user_number == dice_result:
        win_amount = bet * 3
        add_mcoins(user_id, win_amount, TransactionType.GAME_WIN, "Dice win")
        user.game_stats["wins"] += 1
        user.game_stats["total_win"] += win_amount
        db.save()
        
        await update.message.reply_text(
            f"🎲 **ВЫ ПОБЕДИЛИ!** 🎲\n\n"
            f"🎯 Ваша ставка: {user_number}\n"
            f"🎲 Результат: {dice_result}\n"
            f"💰 Выигрыш: {format_number(win_amount)} MCoin\n"
            f"📊 Баланс: {format_number(user.mcoin)} MCoin",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        user.game_stats["losses"] += 1
        user.game_stats["total_bet"] += bet
        db.save()
        
        await update.message.reply_text(
            f"😢 **ВЫ ПРОИГРАЛИ** 😢\n\n"
            f"🎯 Ваша ставка: {user_number}\n"
            f"🎲 Результат: {dice_result}\n"
            f"📊 Проиграно: {format_number(bet)} MCoin\n"
            f"📊 Баланс: {format_number(user.mcoin)} MCoin",
            parse_mode=ParseMode.MARKDOWN
        )

async def game_slots(update: Update, context: CallbackContext):
    """Игра Слоты"""
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "🎰 **ИГРА СЛОТЫ** 🎰\n\n"
            "Правила: крутите слоты и собирайте комбинации\n"
            "Выигрыш: x2 - x10 вашей ставки\n\n"
            "Использование: `/slots <сумма>`\n"
            "Пример: `/slots 100`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    try:
        bet = int(args[0])
        if bet <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ Неверный формат! Используйте: `/slots 100`", parse_mode=ParseMode.MARKDOWN)
        return
    
    user = get_user(user_id)
    if user.mcoin < bet:
        await update.message.reply_text(f"❌ Недостаточно средств! У вас {format_number(user.mcoin)} MCoin")
        return
    
    remove_mcoins(user_id, bet, TransactionType.GAME_LOSS, "Slots bet")
    
    # Символы для слота
    symbols = ["🍒", "🍋", "🍊", "🍉", "🔔", "💎", "7️⃣", "⭐"]
    reel1 = random.choice(symbols)
    reel2 = random.choice(symbols)
    reel3 = random.choice(symbols)
    reel4 = random.choice(symbols)
    
    # Комбинации и выигрыши
    win_multiplier = 1
    
    # Все одинаковые
    if reel1 == reel2 == reel3 == reel4:
        if reel1 == "💎":
            win_multiplier = 20
        elif reel1 == "7️⃣":
            win_multiplier = 15
        elif reel1 == "⭐":
            win_multiplier = 12
        else:
            win_multiplier = 10
    # Три одинаковых
    elif reel1 == reel2 == reel3 or reel2 == reel3 == reel4:
        if reel2 == "💎":
            win_multiplier = 8
        elif reel2 == "7️⃣":
            win_multiplier = 6
        elif reel2 == "⭐":
            win_multiplier = 5
        else:
            win_multiplier = 4
    # Два одинаковых
    elif reel1 == reel2 or reel2 == reel3 or reel3 == reel4:
        win_multiplier = 2
    
    if win_multiplier > 1:
        win_amount = bet * win_multiplier
        add_mcoins(user_id, win_amount, TransactionType.GAME_WIN, f"Slots win x{win_multiplier}")
        user.game_stats["wins"] += 1
        user.game_stats["total_win"] += win_amount
        db.save()
        
        await update.message.reply_text(
            f"🎰 **РЕЗУЛЬТАТ СЛОТОВ** 🎰\n\n"
            f"┌─────┬─────┬─────┬─────┐\n"
            f"│  {reel1}  │  {reel2}  │  {reel3}  │  {reel4}  │\n"
            f"└─────┴─────┴─────┴─────┘\n\n"
            f"✨ Комбинация: x{win_multiplier}\n"
            f"💰 Выигрыш: {format_number(win_amount)} MCoin\n"
            f"📊 Баланс: {format_number(user.mcoin)} MCoin",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        user.game_stats["losses"] += 1
        user.game_stats["total_bet"] += bet
        db.save()
        
        await update.message.reply_text(
            f"🎰 **РЕЗУЛЬТАТ СЛОТОВ** 🎰\n\n"
            f"┌─────┬─────┬─────┬─────┐\n"
            f"│  {reel1}  │  {reel2}  │  {reel3}  │  {reel4}  │\n"
            f"└─────┴─────┴─────┴─────┘\n\n"
            f"😢 Нет выигрышной комбинации\n"
            f"📊 Проиграно: {format_number(bet)} MCoin\n"
            f"📊 Баланс: {format_number(user.mcoin)} MCoin",
            parse_mode=ParseMode.MARKDOWN
        )

async def game_blackjack(update: Update, context: CallbackContext):
    """Игра Блэкджек (21)"""
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "🃏 **ИГРА БЛЭКДЖЕК** 🃏\n\n"
            "Правила: наберите 21 очко или больше чем у дилера\n"
            "Выигрыш: x2 при победе, x2.5 при блэкджеке\n\n"
            "Использование: `/blackjack <сумма>`\n"
            "Пример: `/blackjack 100`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    try:
        bet = int(args[0])
        if bet <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ Неверный формат! Используйте: `/blackjack 100`", parse_mode=ParseMode.MARKDOWN)
        return
    
    user = get_user(user_id)
    if user.mcoin < bet:
        await update.message.reply_text(f"❌ Недостаточно средств! У вас {format_number(user.mcoin)} MCoin")
        return
    
    remove_mcoins(user_id, bet, TransactionType.GAME_LOSS, "Blackjack bet")
    
    # Функция для подсчёта очков
    def calculate_score(cards):
        score = 0
        aces = 0
        for card in cards:
            if card in ["J", "Q", "K"]:
                score += 10
            elif card == "A":
                aces += 1
                score += 11
            else:
                score += int(card)
        
        while score > 21 and aces > 0:
            score -= 10
            aces -= 1
        return score
    
    # Инициализация игры
    cards = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
    
    player_cards = [random.choice(cards), random.choice(cards)]
    dealer_cards = [random.choice(cards), random.choice(cards)]
    
    player_score = calculate_score(player_cards)
    dealer_score = calculate_score(dealer_cards)
    
    # Сохраняем сессию
    db.game_sessions[user_id] = {
        "bet": bet,
        "player_cards": player_cards,
        "dealer_cards": dealer_cards,
        "player_score": player_score,
        "dealer_score": dealer_score,
        "game_active": True
    }
    
    keyboard = [
        [InlineKeyboardButton("🎴 Ещё карту", callback_data="bj_hit")],
        [InlineKeyboardButton("✋ Остановиться", callback_data="bj_stand")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    cards_text = " ".join(player_cards)
    dealer_card = dealer_cards[0]
    
    await update.message.reply_text(
        f"🃏 **БЛЭКДЖЕК** 🃏\n\n"
        f"🎲 Ваши карты: {cards_text} (очки: {player_score})\n"
        f"🎲 Карта дилера: {dealer_card} (?) \n\n"
        f"💰 Ставка: {format_number(bet)} MCoin\n\n"
        f"Ваш ход:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def blackjack_hit(update: Update, context: CallbackContext):
    """Взять ещё карту в блэкджеке"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in db.game_sessions:
        await query.answer("Игра не найдена! Начните новую игру.", show_alert=True)
        return
    
    game = db.game_sessions[user_id]
    if not game["game_active"]:
        await query.answer("Игра уже завершена!", show_alert=True)
        return
    
    cards = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
    new_card = random.choice(cards)
    game["player_cards"].append(new_card)
    game["player_score"] = calculate_score(game["player_cards"])
    
    if game["player_score"] > 21:
        # Перебор - проигрыш
        game["game_active"] = False
        del db.game_sessions[user_id]
        
        await query.edit_message_text(
            f"🃏 **БЛЭКДЖЕК - ПРОИГРЫШ** 🃏\n\n"
            f"🎲 Ваши карты: {' '.join(game['player_cards'])} (очки: {game['player_score']})\n"
            f"🎲 Карты дилера: {' '.join(game['dealer_cards'])} (очки: {game['dealer_score']})\n\n"
            f"😢 ПЕРЕБОР! Вы проиграли {format_number(game['bet'])} MCoin\n"
            f"📊 Ваш баланс: {format_number(get_user(user_id).mcoin)} MCoin",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    keyboard = [
        [InlineKeyboardButton("🎴 Ещё карту", callback_data="bj_hit")],
        [InlineKeyboardButton("✋ Остановиться", callback_data="bj_stand")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🃏 **БЛЭКДЖЕК** 🃏\n\n"
        f"🎲 Ваши карты: {' '.join(game['player_cards'])} (очки: {game['player_score']})\n"
        f"🎲 Карта дилера: {game['dealer_cards'][0]} (?) \n\n"
        f"💰 Ставка: {format_number(game['bet'])} MCoin\n\n"
        f"Ваш ход:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def blackjack_stand(update: Update, context: CallbackContext):
    """Остановиться в блэкджеке"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in db.game_sessions:
        await query.answer("Игра не найдена!", show_alert=True)
        return
    
    game = db.game_sessions[user_id]
    if not game["game_active"]:
        await query.answer("Игра уже завершена!", show_alert=True)
        return
    
    # Ход дилера
    cards = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
    
    while game["dealer_score"] < 17:
        new_card = random.choice(cards)
        game["dealer_cards"].append(new_card)
        game["dealer_score"] = calculate_score(game["dealer_cards"])
    
    game["game_active"] = False
    
    # Определение победителя
    player_score = game["player_score"]
    dealer_score = game["dealer_score"]
    
    win_amount = 0
    result_text = ""
    
    if dealer_score > 21:
        win_amount = game["bet"] * 2
        result_text = "Дилер перебрал!"
    elif player_score > dealer_score:
        win_amount = game["bet"] * 2
        result_text = "Вы набрали больше очков!"
    elif player_score < dealer_score:
        result_text = "Дилер набрал больше очков!"
    else:
        win_amount = game["bet"]
        result_text = "Ничья! Ставка возвращена."
    
    if win_amount > 0 and win_amount != game["bet"]:
        add_mcoins(user_id, win_amount, TransactionType.GAME_WIN, "Blackjack win")
        result_emoji = "🎉 ПОБЕДА! 🎉"
    elif win_amount == game["bet"]:
        add_mcoins(user_id, win_amount, TransactionType.GAME_WIN, "Blackjack draw")
        result_emoji = "🤝 НИЧЬЯ 🤝"
    else:
        result_emoji = "😢 ПРОИГРЫШ 😢"
    
    del db.game_sessions[user_id]
    
    await query.edit_message_text(
        f"🃏 **БЛЭКДЖЕК - {result_emoji}** 🃏\n\n"
        f"🎲 Ваши карты: {' '.join(game['player_cards'])} (очки: {player_score})\n"
        f"🎲 Карты дилера: {' '.join(game['dealer_cards'])} (очки: {dealer_score})\n\n"
        f"📊 Результат: {result_text}\n"
        f"💰 Выигрыш: {format_number(win_amount)} MCoin\n"
        f"📊 Ваш баланс: {format_number(get_user(user_id).mcoin)} MCoin",
        parse_mode=ParseMode.MARKDOWN
    )

# Функция для подсчёта очков в блэкджеке
def calculate_score(cards):
    score = 0
    aces = 0
    for card in cards:
        if card in ["J", "Q", "K"]:
            score += 10
        elif card == "A":
            aces += 1
            score += 11
        else:
            score += int(card)
    
    while score > 21 and aces > 0:
        score -= 10
        aces -= 1
    return score

# ========== КЕЙСЫ ==========
async def cases_menu(update: Update, context: CallbackContext):
    """Меню кейсов"""
    if not db.cases:
        await update.message.reply_text(
            "📦 **Кейсы** 📦\n\n"
            "Кейсы временно недоступны.\n"
            "Следите за обновлениями!",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    keyboard = []
    for case_name, case in db.cases.items():
        keyboard.append([InlineKeyboardButton(
            f"📦 {case_name} - {format_number(case.price)} MCoin", 
            callback_data=f"case_info_{case_name}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎁 **МАГАЗИН КЕЙСОВ** 🎁\n\n"
        "Выберите кейс для просмотра и открытия:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def case_info(update: Update, context: CallbackContext, case_name: str):
    """Информация о кейсе"""
    query = update.callback_query
    case = db.cases.get(case_name)
    
    if not case:
        await query.answer("Кейс не найден!")
        return
    
    items_text = ""
    for item in case.items[:5]:  # Показываем первые 5 предметов
        items_text += f"• {item.name} - {item.chance}% ({format_number(item.reward)} MCoin)\n"
    
    if len(case.items) > 5:
        items_text += f"... и ещё {len(case.items) - 5} предметов"
    
    keyboard = [
        [InlineKeyboardButton("🎁 Открыть кейс", callback_data=f"open_case_{case_name}")],
        [InlineKeyboardButton("🔙 Назад к кейсам", callback_data="cases_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        f"📦 **КЕЙС: {case_name}** 📦\n\n"
        f"💰 Цена: {format_number(case.price)} MCoin\n"
        f"📊 Открытий: {case.total_opened}\n"
        f"📝 Описание: {case.description or 'Нет описания'}\n\n"
        f"**Возможные награды:**\n{items_text}\n\n"
        f"Шанс получить редкий предмет: {max(item.chance for item in case.items):.1f}%"
    )
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def open_case(update: Update, context: CallbackContext, case_name: str):
    """Открытие кейса"""
    query = update.callback_query
    user_id = query.from_user.id
    user = get_user(user_id)
    
    case = db.cases.get(case_name)
    if not case:
        await query.answer("Кейс не найден!", show_alert=True)
        return
    
    if user.mcoin < case.price:
        await query.answer(f"Недостаточно MCoin! Нужно {format_number(case.price)}", show_alert=True)
        return
    
    remove_mcoins(user_id, case.price, TransactionType.CASE_REWARD, f"Open case {case_name}")
    case.total_opened += 1
    
    # Выбор предмета
    total_chance = sum(item.chance for item in case.items)
    roll = random.random() * total_chance
    
    current = 0
    selected_item = None
    for item in case.items:
        current += item.chance
        if roll <= current:
            selected_item = item
            break
    
    if not selected_item:
        selected_item = case.items[0]
    
    # Выдача награды
    reward_amount = selected_item.reward
    add_mcoins(user_id, reward_amount, TransactionType.CASE_REWARD, f"Case {case_name}: {selected_item.name}")
    
    db.save()
    
    # Эффект открытия
    opening_messages = [
        "🎲 Крутим барабаны...",
        "🔮 Предсказываем судьбу...",
        "✨ Открываем кейс...",
        "🎁 Достаём приз..."
    ]
    
    await query.answer("🎁 Открываем кейс...")
    
    await query.edit_message_text(
        f"{random.choice(opening_messages)}\n\n"
        f"📦 **Кейс: {case_name}**\n\n"
        f"🏆 **Вам выпало:** {selected_item.name}\n"
        f"💰 **Награда:** {format_number(reward_amount)} MCoin\n\n"
        f"✨ Ваш баланс: {format_number(get_user(user_id).mcoin)} MCoin",
        parse_mode=ParseMode.MARKDOWN
    )

# ========== ЛОТЕРЕЯ ==========
async def lottery_menu(update: Update, context: CallbackContext):
    """Меню лотереи"""
    lottery = db.lottery
    
    if lottery.active:
        end_time = datetime.fromisoformat(lottery.end_time) if lottery.end_time else datetime.now() + timedelta(days=1)
        time_left = end_time - datetime.now()
        hours_left = time_left.seconds // 3600
        minutes_left = (time_left.seconds % 3600) // 60
        
        total_tickets = sum(lottery.tickets.values())
        user_tickets = lottery.tickets.get(update.effective_user.id, 0)
        
        keyboard = [
            [InlineKeyboardButton(f"🎫 Купить билет ({lottery.ticket_price} MCoin)", callback_data="buy_ticket")],
            [InlineKeyboardButton("🎫 Купить 10 билетов", callback_data="buy_10_tickets")],
            [InlineKeyboardButton("ℹ️ Информация о лотерее", callback_data="lottery_info")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🎰 **ЛОТЕРЕЯ** 🎰\n\n"
            f"📊 Статус: **АКТИВНА**\n"
            f"💰 Призовой фонд: {format_number(lottery.prize_pool)} MCoin\n"
            f"🎫 Всего билетов: {total_tickets}\n"
            f"👤 Ваших билетов: {user_tickets}\n"
            f"⏰ Осталось времени: {hours_left}ч {minutes_left}м\n\n"
            f"💎 Цена билета: {lottery.ticket_price} MCoin\n"
            f"🎁 Победитель получает 80% призового фонда!",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        keyboard = [
            [InlineKeyboardButton("ℹ️ Информация", callback_data="lottery_info")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🎰 **ЛОТЕРЕЯ** 🎰\n\n"
            f"📊 Статус: **НЕ АКТИВНА**\n"
            f"🎁 Следите за объявлениями о начале розыгрыша!",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )

async def buy_ticket(update: Update, context: CallbackContext):
    """Покупка лотерейного билета"""
    query = update.callback_query
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if not db.lottery.active:
        await query.answer("Лотерея не активна!", show_alert=True)
        return
    
    ticket_price = db.lottery.ticket_price
    
    if user.mcoin < ticket_price:
        await query.answer(f"Недостаточно MCoin! Нужно {ticket_price} MCoin", show_alert=True)
        return
    
    remove_mcoins(user_id, ticket_price, TransactionType.GAME_LOSS, "Lottery ticket")
    
    if user_id not in db.lottery.tickets:
        db.lottery.tickets[user_id] = 0
    db.lottery.tickets[user_id] += 1
    
    # 80% от билета идёт в призовой фонд
    db.lottery.prize_pool += int(ticket_price * 0.8)
    
    db.save()
    
    total_tickets = sum(db.lottery.tickets.values())
    user_tickets = db.lottery.tickets[user_id]
    
    await query.answer("Билет куплен! Удачи!", show_alert=True)
    await query.message.edit_text(
        f"✅ **БИЛЕТ КУПЛЕН!** ✅\n\n"
        f"🎫 Ваших билетов: {user_tickets}\n"
        f"📊 Всего билетов: {total_tickets}\n"
        f"💰 Призовой фонд: {format_number(db.lottery.prize_pool)} MCoin\n\n"
        f"✨ Удачи в розыгрыше!",
        parse_mode=ParseMode.MARKDOWN
    )

async def buy_10_tickets(update: Update, context: CallbackContext):
    """Покупка 10 лотерейных билетов"""
    query = update.callback_query
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if not db.lottery.active:
        await query.answer("Лотерея не активна!", show_alert=True)
        return
    
    ticket_price = db.lottery.ticket_price
    total_price = ticket_price * 10
    
    if user.mcoin < total_price:
        await query.answer(f"Недостаточно MCoin! Нужно {total_price} MCoin", show_alert=True)
        return
    
    remove_mcoins(user_id, total_price, TransactionType.GAME_LOSS, "Lottery 10 tickets")
    
    if user_id not in db.lottery.tickets:
        db.lottery.tickets[user_id] = 0
    db.lottery.tickets[user_id] += 10
    
    db.lottery.prize_pool += int(total_price * 0.8)
    
    db.save()
    
    total_tickets = sum(db.lottery.tickets.values())
    user_tickets = db.lottery.tickets[user_id]
    
    await query.answer("10 билетов куплено! Удачи!", show_alert=True)
    await query.message.edit_text(
        f"✅ **10 БИЛЕТОВ КУПЛЕНО!** ✅\n\n"
        f"🎫 Ваших билетов: {user_tickets}\n"
        f"📊 Всего билетов: {total_tickets}\n"
        f"💰 Призовой фонд: {format_number(db.lottery.prize_pool)} MCoin\n\n"
        f"✨ Шансы на победу увеличены!",
        parse_mode=ParseMode.MARKDOWN
    )

async def lottery_info(update: Update, context: CallbackContext):
    """Информация о лотерее"""
    query = update.callback_query
    lottery = db.lottery
    
    if lottery.active:
        end_time = datetime.fromisoformat(lottery.end_time) if lottery.end_time else None
        if end_time:
            time_left = end_time - datetime.now()
            days = time_left.days
            hours = time_left.seconds // 3600
            minutes = (time_left.seconds % 3600) // 60
            
            time_str = f"{days}д {hours}ч {minutes}м"
        else:
            time_str = "Неизвестно"
        
        info_text = (
            f"🎰 **ИНФОРМАЦИЯ О ЛОТЕРЕЕ** 🎰\n\n"
            f"📊 Текущий розыгрыш:\n"
            f"💰 Призовой фонд: {format_number(lottery.prize_pool)} MCoin\n"
            f"🎫 Цена билета: {lottery.ticket_price} MCoin\n"
            f"🎁 Победитель получает: 80% призового фонда\n"
            f"⏰ Осталось времени: {time_str}\n\n"
            f"📌 **Как участвовать:**\n"
            f"1. Купите билет(ы) за MCoin\n"
            f"2. Ждите розыгрыша\n"
            f"3. Победитель получит награду автоматически!\n\n"
            f"💡 Совет: больше билетов = больше шансов!"
        )
    else:
        info_text = (
            f"🎰 **ИНФОРМАЦИЯ О ЛОТЕРЕЕ** 🎰\n\n"
            f"📊 Лотерея проводится периодически.\n"
            f"🎫 Стоимость билета: {lottery.ticket_price} MCoin\n"
            f"🎁 Победитель получает 80% призового фонда\n\n"
            f"📌 **Следите за новостями!**\n"
            f"О начале новой лотереи будет объявлено отдельно."
        )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="lottery_back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(info_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

# ========== ЧЕКИ ==========
async def checks_menu(update: Update, context: CallbackContext):
    """Меню чеков"""
    keyboard = [
        [InlineKeyboardButton("🎁 Создать чек", callback_data="create_check")],
        [InlineKeyboardButton("💳 Активировать чек", callback_data="activate_check")],
        [InlineKeyboardButton("📋 Мои чеки", callback_data="my_checks")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎫 **СИСТЕМА ЧЕКОВ** 🎫\n\n"
        "Чеки позволяют переводить MCoin другим пользователям.\n\n"
        "**Возможности:**\n"
        "• Создать чек на любую сумму\n"
        "• Активировать чек по коду\n"
        "• Просматривать свои чеки\n\n"
        "Выберите действие:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def create_check_start(update: Update, context: CallbackContext):
    """Начало создания чека"""
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        "🎁 **СОЗДАНИЕ ЧЕКА** 🎁\n\n"
        "Введите сумму чека в MCoin:\n"
        "(минимум 10 MCoin, максимум 100000 MCoin)\n\n"
        "Для отмены введите /cancel"
    )
    return 1  # Состояние ожидания суммы

async def create_check_amount(update: Update, context: CallbackContext):
    """Получение суммы чека"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    try:
        amount = int(update.message.text)
        if amount < 10:
            await update.message.reply_text("❌ Минимальная сумма чека: 10 MCoin")
            return 1
        if amount > 100000:
            await update.message.reply_text("❌ Максимальная сумма чека: 100000 MCoin")
            return 1
        if user.mcoin < amount:
            await update.message.reply_text(f"❌ Недостаточно средств! У вас {format_number(user.mcoin)} MCoin")
            return 1
    except:
        await update.message.reply_text("❌ Введите корректное число!")
        return 1
    
    # Создаём чек
    remove_mcoins(user_id, amount, TransactionType.WITHDRAW, "Check creation")
    
    check_code = generate_check_code()
    check = Check(
        code=check_code,
        amount=amount,
        created_by=user_id,
        created_at=datetime.now().isoformat()
    )
    db.checks[check_code] = check
    db.save()
    
    await update.message.reply_text(
        f"✅ **ЧЕК СОЗДАН!** ✅\n\n"
        f"💰 Сумма: {format_number(amount)} MCoin\n"
        f"🔑 Код чека: `{check_code}`\n\n"
        f"📋 Инструкция:\n"
        f"1. Отправьте код получателю\n"
        f"2. Получатель активирует чек в разделе «Чеки»\n"
        f"3. MCoin автоматически зачислятся на его счёт\n\n"
        f"⚠️ Чек действителен 30 дней!",
        parse_mode=ParseMode.MARKDOWN
    )
    return ConversationHandler.END

async def activate_check_start(update: Update, context: CallbackContext):
    """Начало активации чека"""
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        "💳 **АКТИВАЦИЯ ЧЕКА** 💳\n\n"
        "Введите код чека:\n\n"
        "Для отмены введите /cancel"
    )
    return 1

async def activate_check_code(update: Update, context: CallbackContext):
    """Активация чека по коду"""
    user_id = update.effective_user.id
    code = update.message.text.strip().upper()
    
    check = db.checks.get(code)
    
    if not check:
        await update.message.reply_text("❌ Чек не найден! Проверьте правильность кода.")
        return 1
    
    if check.is_used:
        await update.message.reply_text("❌ Этот чек уже был активирован!")
        return 1
    
    # Проверка срока действия (30 дней)
    created_date = datetime.fromisoformat(check.created_at)
    if datetime.now() - created_date > timedelta(days=30):
        await update.message.reply_text("❌ Срок действия чека истёк!")
        return 1
    
    # Активируем чек
    check.is_used = True
    check.used_by = user_id
    check.used_at = datetime.now().isoformat()
    
    add_mcoins(user_id, check.amount, TransactionType.ADMIN_GIVE, f"Check activation: {code}")
    db.save()
    
    await update.message.reply_text(
        f"✅ **ЧЕК АКТИВИРОВАН!** ✅\n\n"
        f"💰 Получено: {format_number(check.amount)} MCoin\n"
        f"🔑 Код: {code}\n"
        f"✨ Ваш баланс: {format_number(get_user(user_id).mcoin)} MCoin\n\n"
        f"Спасибо за использование системы чеков!",
        parse_mode=ParseMode.MARKDOWN
    )
    return ConversationHandler.END

async def my_checks(update: Update, context: CallbackContext):
    """Просмотр созданных чеков"""
    query = update.callback_query
    user_id = query.from_user.id
    
    user_checks = [c for c in db.checks.values() if c.created_by == user_id]
    
    if not user_checks:
        await query.answer("У вас нет созданных чеков", show_alert=True)
        await query.message.edit_text(
            "📋 **МОИ ЧЕКИ** 📋\n\n"
            "У вас пока нет созданных чеков.\n"
            "Используйте «Создать чек» чтобы перевести MCoin другому пользователю.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    checks_text = "📋 **МОИ ЧЕКИ** 📋\n\n"
    for idx, check in enumerate(user_checks[:10], 1):
        status = "✅ Использован" if check.is_used else "⏳ Ожидает"
        used_by = f"\n📥 Использовал: ID {check.used_by}" if check.used_by else ""
        
        checks_text += (
            f"{idx}. 💰 {format_number(check.amount)} MCoin\n"
            f"   🔑 Код: `{check.code}`\n"
            f"   📊 Статус: {status}{used_by}\n"
            f"   📅 Создан: {check.created_at[:10]}\n\n"
        )
    
    if len(user_checks) > 10:
        checks_text += f"\n... и ещё {len(user_checks) - 10} чеков"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="checks_back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(checks_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

# ========== ЕЖЕДНЕВНЫЙ БОНУС ==========
async def daily_bonus(update: Update, context: CallbackContext):
    """Ежедневный бонус с системой стриков"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    today = datetime.now().date()
    
    # Базовая награда
    base_reward = 15
    streak_bonus = 0
    
    if user.daily_last:
        last_date = datetime.fromisoformat(user.daily_last).date()
        if last_date == today:
            await update.message.reply_text(
                f"⏰ Вы уже получали ежедневный бонус сегодня!\n\n"
                f"Возвращайтесь завтра за новой наградой!\n"
                f"🔥 Текущий стрик: {user.daily_streak} дней",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        elif last_date == today - timedelta(days=1):
            # Стрик продолжается
            user.daily_streak += 1
            streak_bonus = min(user.daily_streak * 5, 100)  # Максимум 100 бонус
        else:
            # Стрик сброшен
            user.daily_streak = 1
    else:
        user.daily_streak = 1
    
    total_reward = base_reward + streak_bonus
    
    # Бонус за стрик
    if user.daily_streak >= 7:
        total_reward += 50
        streak_text = f"\n✨ **Бонус 7 дней:** +50 MCoin"
    elif user.daily_streak >= 30:
        total_reward += 200
        streak_text = f"\n🏆 **Бонус 30 дней:** +200 MCoin"
    elif streak_bonus > 0:
        streak_text = f"\n🔥 **Бонус стрика ({user.daily_streak} дней):** +{streak_bonus} MCoin"
    else:
        streak_text = ""
    
    add_mcoins(user_id, total_reward, TransactionType.DAILY_BONUS, f"Daily streak {user.daily_streak}")
    user.daily_last = datetime.now().isoformat()
    db.save()
    
    # Прогресс до следующего бонуса
    next_bonus_days = 0
    if user.daily_streak < 7:
        next_bonus_days = 7 - user.daily_streak
    elif user.daily_streak < 30:
        next_bonus_days = 30 - user.daily_streak
    
    await update.message.reply_text(
        f"🎁 **ЕЖЕДНЕВНЫЙ БОНУС!** 🎁\n\n"
        f"💰 Основная награда: {base_reward} MCoin{streak_text}\n"
        f"✨ **Итого получено:** {total_reward} MCoin\n"
        f"🔥 **Стрик дней:** {user.daily_streak}\n"
        f"📊 **Ваш баланс:** {format_number(user.mcoin)} MCoin\n\n"
        f"{f'🎯 До следующего бонуса: {next_bonus_days} дней' if next_bonus_days > 0 else '🏆 Вы достигли максимального бонуса!'}",
        parse_mode=ParseMode.MARKDOWN
    )

# ========== РЕФЕРАЛЬНАЯ СИСТЕМА ==========
async def referrals_menu(update: Update, context: CallbackContext):
    """Меню реферальной системы"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    bot_username = context.bot.username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    total_ref_earnings = len(user.referrals) * 5  # 5 MCoin за реферала
    
    # Статистика рефералов
    active_refs = 0
    for ref_id in user.referrals:
        ref_user = get_user(ref_id)
        if ref_user.total_earned > 0:
            active_refs += 1
    
    keyboard = [
        [InlineKeyboardButton("🔗 Моя ссылка", callback_data=f"copy_ref_{ref_link}")],
        [InlineKeyboardButton("📊 Статистика рефералов", callback_data="ref_stats")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👥 **РЕФЕРАЛЬНАЯ ПРОГРАММА** 👥\n\n"
        f"📊 **Ваша статистика:**\n"
        f"👤 Приглашено: {len(user.referrals)}\n"
        f"✅ Активных: {active_refs}\n"
        f"💰 Заработано: {total_ref_earnings} MCoin\n\n"
        f"🎁 **Как это работает:**\n"
        f"• Пригласите друга по вашей ссылке\n"
        f"• Друг должен начать использовать бота\n"
        f"• Вы получите 5 MCoin на баланс\n\n"
        f"💎 **Ваша реферальная ссылка:**\n"
        f"`{ref_link}`\n\n"
        f"Поделитесь ссылкой с друзьями и получайте бонусы!",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def copy_ref_link(update: Update, context: CallbackContext, link: str):
    """Копирование реферальной ссылки"""
    query = update.callback_query
    await query.answer()
    # В реальном боте здесь была бы логика копирования
    await query.message.reply_text(f"🔗 Ваша реферальная ссылка:\n`{link}`", parse_mode=ParseMode.MARKDOWN)

async def ref_stats(update: Update, context: CallbackContext):
    """Статистика рефералов"""
    query = update.callback_query
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if not user.referrals:
        await query.answer("У вас пока нет рефералов", show_alert=True)
        return
    
    refs_text = "📊 **СТАТИСТИКА РЕФЕРАЛОВ** 📊\n\n"
    
    for idx, ref_id in enumerate(user.referrals[:20], 1):
        ref_user = get_user(ref_id)
        status = "✅ Активен" if ref_user.total_earned > 0 else "⏳ Новый"
        earnings = 5  # Базовая награда
        
        refs_text += (
            f"{idx}. ID: {ref_id}\n"
            f"   📊 Статус: {status}\n"
            f"   💰 Заработано: {earnings} MCoin\n"
            f"   📅 Присоединился: {ref_user.join_date[:10]}\n\n"
        )
    
    if len(user.referrals) > 20:
        refs_text += f"\n... и ещё {len(user.referrals) - 20} рефералов"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="referrals_back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(refs_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

# ========== ВЫВОД СРЕДСТВ ==========
async def withdraw_menu(update: Update, context: CallbackContext):
    """Меню вывода средств"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if user.mcoin < 10:
        await update.message.reply_text(
            f"❌ Минимальная сумма для вывода: 10 MCoin\n"
            f"💰 Ваш баланс: {format_number(user.mcoin)} MCoin\n\n"
            f"Выполняйте задания и участвуйте в играх, чтобы заработать больше!",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    keyboard = [
        [InlineKeyboardButton("💸 Запросить вывод", callback_data="request_withdraw")],
        [InlineKeyboardButton("📋 Мои заявки", callback_data="my_withdraws")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="withdraw_info")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"💸 **ВЫВОД СРЕДСТВ** 💸\n\n"
        f"💰 Доступно для вывода: {format_number(user.mcoin)} MCoin\n"
        f"📊 Минимальная сумма: 10 MCoin\n"
        f"⏰ Время обработки: до 24 часов\n\n"
        f"**Способы вывода:**\n"
        f"• USDT (TRC20)\n"
        f"• На карту\n"
        f"• Другие криптовалюты\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def request_withdraw_start(update: Update, context: CallbackContext):
    """Начало запроса на вывод"""
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        "💸 **ЗАПРОС НА ВЫВОД** 💸\n\n"
        "Введите сумму для вывода:\n"
        f"(минимум 10 MCoin)\n\n"
        "Для отмены введите /cancel"
    )
    return 1

async def request_withdraw_amount(update: Update, context: CallbackContext):
    """Получение суммы вывода"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    try:
        amount = int(update.message.text)
        if amount < 10:
            await update.message.reply_text("❌ Минимальная сумма вывода: 10 MCoin")
            return 1
        if user.mcoin < amount:
            await update.message.reply_text(f"❌ Недостаточно средств! У вас {format_number(user.mcoin)} MCoin")
            return 1
    except:
        await update.message.reply_text("❌ Введите корректное число!")
        return 1
    
    context.user_data['withdraw_amount'] = amount
    
    await update.message.reply_text(
        f"💰 Сумма: {format_number(amount)} MCoin\n\n"
        f"Введите адрес для вывода:\n"
        f"(USDT TRC20 или номер карты)\n\n"
        f"Для отмены введите /cancel"
    )
    return 2

async def request_withdraw_address(update: Update, context: CallbackContext):
    """Получение адреса для вывода"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    amount = context.user_data['withdraw_amount']
    address = update.message.text.strip()
    
    if not address:
        await update.message.reply_text("❌ Введите корректный адрес!")
        return 2
    
    # Создаём заявку
    withdraw_request = WithdrawRequest(
        user_id=user_id,
        amount=amount,
        address=address,
        status="pending",
        created_at=datetime.now().isoformat()
    )
    db.withdraw_requests.append(withdraw_request)
    
    # Блокируем средства
    remove_mcoins(user_id, amount, TransactionType.WITHDRAW, "Withdraw request")
    db.save()
    
    await update.message.reply_text(
        f"✅ **ЗАЯВКА НА ВЫВОД СОЗДАНА!** ✅\n\n"
        f"💰 Сумма: {format_number(amount)} MCoin\n"
        f"📊 Адрес: {address}\n"
        f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        f"⏳ Статус: **В обработке**\n"
        f"⏰ Ожидайте, администратор рассмотрит заявку в ближайшее время.\n\n"
        f"📌 Номер заявки: #{len(db.withdraw_requests)}",
        parse_mode=ParseMode.MARKDOWN
    )
    return ConversationHandler.END

async def my_withdraws(update: Update, context: CallbackContext):
    """Просмотр заявок на вывод"""
    query = update.callback_query
    user_id = query.from_user.id
    
    user_requests = [r for r in db.withdraw_requests if r.user_id == user_id]
    
    if not user_requests:
        await query.answer("У вас нет заявок на вывод", show_alert=True)
        await query.message.edit_text(
            "📋 **МОИ ЗАЯВКИ** 📋\n\n"
            "У вас пока нет заявок на вывод.\n"
            "Используйте «Запросить вывод» чтобы начать.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    requests_text = "📋 **МОИ ЗАЯВКИ НА ВЫВОД** 📋\n\n"
    
    for idx, req in enumerate(user_requests[-10:], 1):
        status_emoji = {
            "pending": "⏳",
            "approved": "✅",
            "rejected": "❌"
        }.get(req.status, "❓")
        
        status_text = {
            "pending": "В обработке",
            "approved": "Одобрена",
            "rejected": "Отклонена"
        }.get(req.status, "Неизвестно")
        
        requests_text += (
            f"{idx}. {status_emoji} **Заявка #{idx}**\n"
            f"   💰 Сумма: {format_number(req.amount)} MCoin\n"
            f"   📊 Статус: {status_text}\n"
            f"   📅 Создана: {req.created_at[:10]}\n"
            f"   🏦 Адрес: {req.address[:20]}...\n\n"
        )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="withdraw_back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(requests_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def withdraw_info(update: Update, context: CallbackContext):
    """Информация о выводе"""
    query = update.callback_query
    
    info_text = (
        "ℹ️ **ИНФОРМАЦИЯ О ВЫВОДЕ СРЕДСТВ** ℹ️\n\n"
        "**Как вывести MCoin:**\n"
        "1. Подайте заявку на вывод\n"
        "2. Укажите сумму и реквизиты\n"
        "3. Дождитесь обработки администратором\n"
        "4. Получите средства на указанный адрес\n\n"
        "**Условия вывода:**\n"
        "• Минимальная сумма: 10 MCoin\n"
        "• Комиссия: 0% (без комиссии)\n"
        "• Время обработки: до 24 часов\n"
        "• Вывод осуществляется в рабочие дни\n\n"
        "**Поддерживаемые способы:**\n"
        "• USDT (TRC20)\n"
        "• Банковские карты (Visa/Mastercard)\n"
        "• Другие криптовалюты (по запросу)\n\n"
        "⚠️ **Внимание:**\n"
        "• Указывайте корректные реквизиты\n"
        "• Средства выводятся только на ваше имя\n"
        "• При нарушении правил вывод может быть отклонён"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="withdraw_back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(info_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

# ========== BOTOHUB ЗАДАНИЯ ==========
async def tasks_mode(update: Update, context: CallbackContext):
    """Продвинутый режим заданий через BotoHub"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    msg = await update.message.reply_text("🔄 **Получаем задание...**", parse_mode=ParseMode.MARKDOWN)
    
    try:
        result = await call_botohub_api(user_id, is_task=True, skip=False)
        
        tasks = result.get("tasks", [])
        completed = result.get("completed", False)
        skip_flag = result.get("skip", False)
        
        if completed:
            # Все задания выполнены - выдаём награду
            task_reward = 10
            add_mcoins(user_id, task_reward, TransactionType.TASK_REWARD, "All tasks completed")
            await msg.edit_text(
                f"🎉 **ПОЗДРАВЛЯЮ!** 🎉\n\n"
                f"✅ Вы выполнили все задания!\n"
                f"💰 Получено: {task_reward} MCoin\n"
                f"✨ Ваш баланс: {format_number(user.mcoin)} MCoin\n\n"
                f"Новые задания появятся позже!",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        if skip_flag or not tasks:
            await msg.edit_text(
                "🎉 **Нет активных заданий** 🎉\n\n"
                "На данный момент нет доступных заданий.\n"
                "Попробуйте позже или проверьте другие разделы бота!",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        task_url = tasks[0]
        task_reward = 10
        
        keyboard = [
            [InlineKeyboardButton("✅ Я выполнил задание", callback_data=f"check_task_{task_url}")],
            [InlineKeyboardButton("❌ Пропустить задание", callback_data="skip_task")],
            [InlineKeyboardButton("ℹ️ Как выполнить?", callback_data="task_help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await msg.edit_text(
            f"📢 **НОВОЕ ЗАДАНИЕ!** 📢\n\n"
            f"🔗 **Ссылка:** {task_url}\n"
            f"💰 **Награда:** {task_reward} MCoin\n\n"
            f"**Инструкция:**\n"
            f"1. Перейдите по ссылке\n"
            f"2. Подпишитесь на канал/группу\n"
            f"3. Вернитесь и нажмите «Я выполнил»\n\n"
            f"⚠️ Подписку нужно удерживать минимум 3 минуты!",
            reply_markup=reply_markup,
            disable_web_page_preview=True,
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception as e:
        logger.error(f"Error in tasks_mode: {e}")
        await msg.edit_text(
            "❌ **Ошибка при получении заданий** ❌\n\n"
            "Пожалуйста, попробуйте позже.\n"
            "Если ошибка повторяется, обратитесь к администратору.",
            parse_mode=ParseMode.MARKDOWN
        )

async def check_task(update: Update, context: CallbackContext):
    """Проверка выполнения задания через BotoHub"""
    query = update.callback_query
    await query.answer("🔍 Проверяем выполнение...")
    user_id = query.from_user.id
    task_url = query.data.replace("check_task_", "")
    
    try:
        result = await call_botohub_api(user_id, is_task=True, skip=False)
        
        prev_success = result.get("prev_success", False)
        completed = result.get("completed", False)
        
        if prev_success:
            # Задание выполнено
            task_reward = 10
            add_mcoins(user_id, task_reward, TransactionType.TASK_REWARD, f"Task completed: {task_url}")
            user = get_user(user_id)
            
            if completed:
                await query.edit_message_text(
                    f"✅ **ЗАДАНИЕ ВЫПОЛНЕНО!** ✅\n\n"
                    f"💰 Получено: {task_reward} MCoin\n"
                    f"🎉 Вы выполнили все задания!\n"
                    f"✨ Ваш баланс: {format_number(user.mcoin)} MCoin",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                # Проверяем, есть ли следующее задание
                new_tasks = result.get("tasks", [])
                if new_tasks:
                    new_url = new_tasks[0]
                    keyboard = [
                        [InlineKeyboardButton("✅ Я выполнил", callback_data=f"check_task_{new_url}")],
                        [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await query.edit_message_text(
                        f"✅ **ЗАДАНИЕ ВЫПОЛНЕНО!** ✅\n\n"
                        f"💰 Получено: {task_reward} MCoin\n"
                        f"✨ Ваш баланс: {format_number(user.mcoin)} MCoin\n\n"
                        f"📢 **СЛЕДУЮЩЕЕ ЗАДАНИЕ:**\n"
                        f"🔗 {new_url}\n\n"
                        f"Подпишитесь и нажмите «Я выполнил»",
                        reply_markup=reply_markup,
                        disable_web_page_preview=True,
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await query.edit_message_text(
                        f"✅ **ЗАДАНИЕ ВЫПОЛНЕНО!** ✅\n\n"
                        f"💰 Получено: {task_reward} MCoin\n"
                        f"✨ Ваш баланс: {format_number(user.mcoin)} MCoin\n\n"
                        f"🎉 Больше заданий пока нет!",
                        parse_mode=ParseMode.MARKDOWN
                    )
        else:
            # Задание не выполнено
            await query.edit_message_text(
                f"❌ **ЗАДАНИЕ НЕ ВЫПОЛНЕНО** ❌\n\n"
                f"🔗 {task_url}\n\n"
                f"**Почему не засчиталось?**\n"
                f"• Вы не подписались на канал\n"
                f"• Подписка была отписана слишком рано\n"
                f"• Техническая ошибка\n\n"
                f"💡 **Решение:**\n"
                f"1. Убедитесь, что вы подписаны\n"
                f"2. Подождите 1-2 минуты\n"
                f"3. Нажмите «Я выполнил» снова",
                disable_web_page_preview=True,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Возвращаем кнопки
            keyboard = [
                [InlineKeyboardButton("✅ Я выполнил", callback_data=f"check_task_{task_url}")],
                [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_reply_markup(reply_markup)
            
    except Exception as e:
        logger.error(f"Error in check_task: {e}")
        await query.edit_message_text(
            "❌ **Ошибка при проверке** ❌\n\n"
            "Пожалуйста, попробуйте позже.\n"
            "Если ошибка повторяется, обратитесь к администратору.",
            parse_mode=ParseMode.MARKDOWN
        )

async def skip_task(update: Update, context: CallbackContext):
    """Пропуск задания"""
    query = update.callback_query
    await query.answer("⏩ Пропускаем задание...")
    user_id = query.from_user.id
    
    try:
        result = await call_botohub_api(user_id, is_task=True, skip=True)
        
        tasks = result.get("tasks", [])
        completed = result.get("completed", False)
        
        if completed:
            await query.edit_message_text(
                "✅ **ВСЕ ЗАДАНИЯ ВЫПОЛНЕНЫ!** ✅\n\n"
                "Поздравляем! Вы выполнили все доступные задания.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        if tasks:
            new_url = tasks[0]
            keyboard = [
                [InlineKeyboardButton("✅ Я выполнил", callback_data=f"check_task_{new_url}")],
                [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"⏩ **ЗАДАНИЕ ПРОПУЩЕНО** ⏩\n\n"
                f"📢 **НОВОЕ ЗАДАНИЕ:**\n"
                f"🔗 {new_url}\n\n"
                f"💰 Награда: 10 MCoin\n\n"
                f"Подпишитесь и нажмите «Я выполнил»",
                reply_markup=reply_markup,
                disable_web_page_preview=True,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await query.edit_message_text(
                "🎉 **НЕТ ДОСТУПНЫХ ЗАДАНИЙ** 🎉\n\n"
                "Попробуйте позже!",
                parse_mode=ParseMode.MARKDOWN
            )
            
    except Exception as e:
        logger.error(f"Error in skip_task: {e}")
        await query.edit_message_text(
            "❌ **Ошибка при пропуске задания** ❌\n\n"
            "Пожалуйста, попробуйте позже.",
            parse_mode=ParseMode.MARKDOWN
        )

async def task_help(update: Update, context: CallbackContext):
    """Помощь по заданиям"""
    query = update.callback_query
    await query.answer()
    
    help_text = (
        "ℹ️ **КАК ВЫПОЛНЯТЬ ЗАДАНИЯ** ℹ️\n\n"
        "**Пошаговая инструкция:**\n\n"
        "1️⃣ **Перейдите по ссылке**\n"
        "   • Нажмите на ссылку в задании\n"
        "   • Вы перейдёте в Telegram канал/группу\n\n"
        "2️⃣ **Подпишитесь**\n"
        "   • Нажмите кнопку «Подписаться»\n"
        "   • Дождитесь подтверждения подписки\n\n"
        "3️⃣ **Вернитесь в бот**\n"
        "   • Не отписывайтесь сразу!\n"
        "   • Подписку нужно удерживать минимум 3 минуты\n\n"
        "4️⃣ **Нажмите «Я выполнил»**\n"
        "   • Бот проверит вашу подписку\n"
        "   • При успехе вы получите награду\n\n"
        "**Частые ошибки:**\n"
        "• ❌ Слишком ранняя отписка\n"
        "• ❌ Использование VPN\n"
        "• ❌ Технические проблемы Telegram\n\n"
        "**Решение:**\n"
        "• ✅ Подождите 3-5 минут\n"
        "• ✅ Нажмите «Я выполнил» несколько раз\n"
        "• ✅ Обратитесь к администратору"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад к заданию", callback_data="back_to_task")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def call_botohub_api(chat_id: int, is_task: bool = False, skip: bool = False,
                            gender: str = None, age: str = None) -> dict:
    """Вызов API BotoHub"""
    payload = {"chat_id": chat_id}
    if is_task:
        payload["is_task"] = True
        if skip:
            payload["skip"] = True
    if gender:
        payload["gender"] = gender
    if age:
        payload["age"] = age
    
    headers = {
        "Content-Type": "application/json",
        "Auth": BOTOHUB_TOKEN
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(BOTOHUB_API_URL, json=payload, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error(f"BotoHub API error {resp.status}")
                    return {"tasks": [], "completed": False, "skip": True}
        except Exception as e:
            logger.error(f"BotoHub API exception: {e}")
            return {"tasks": [], "completed": False, "skip": True}

# ========== АДМИН ПАНЕЛЬ ==========
async def admin_panel(update: Update, context: CallbackContext):
    """Главное меню админ панели"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ У вас нет доступа к админ панели!", parse_mode=ParseMode.MARKDOWN)
        return
    
    keyboard = [
        [InlineKeyboardButton("💰 Управление балансами", callback_data="admin_balance")],
        [InlineKeyboardButton("📦 Управление кейсами", callback_data="admin_cases")],
        [InlineKeyboardButton("🎰 Управление лотереей", callback_data="admin_lottery")],
        [InlineKeyboardButton("💸 Заявки на вывод", callback_data="admin_withdraw_requests")],
        [InlineKeyboardButton("📊 Статистика бота", callback_data="admin_stats")],
        [InlineKeyboardButton("📨 Рассылка", callback_data="admin_mailing")],
        [InlineKeyboardButton("🎁 Создать чек", callback_data="admin_create_check")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="admin_settings")],
        [InlineKeyboardButton("🔙 Выход", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "⚙️ **АДМИН ПАНЕЛЬ** ⚙️\n\n"
        "Управление ботом и пользователями.\n"
        "Выберите действие:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def admin_balance_menu(update: Update, context: CallbackContext):
    """Меню управления балансами"""
    query = update.callback_query
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить MCoin", callback_data="admin_add_mcoin")],
        [InlineKeyboardButton("➖ Забрать MCoin", callback_data="admin_remove_mcoin")],
        [InlineKeyboardButton("📊 Посмотреть баланс", callback_data="admin_view_balance")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "💰 **УПРАВЛЕНИЕ БАЛАНСАМИ** 💰\n\n"
        "Выберите действие:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def admin_add_mcoin_start(update: Update, context: CallbackContext):
    """Начало добавления MCoin"""
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        "💰 **ДОБАВЛЕНИЕ MCOIN** 💰\n\n"
        "Введите ID пользователя и сумму через пробел:\n"
        "Пример: `123456789 100`\n\n"
        "Для отмены введите /cancel",
        parse_mode=ParseMode.MARKDOWN
    )
    return 1

async def admin_add_mcoin_process(update: Update, context: CallbackContext):
    """Обработка добавления MCoin"""
    try:
        parts = update.message.text.split()
        user_id = int(parts[0])
        amount = int(parts[1])
        
        if amount <= 0:
            raise ValueError
        
        add_mcoins(user_id, amount, TransactionType.ADMIN_GIVE, "Admin added")
        user = get_user(user_id)
        
        await update.message.reply_text(
            f"✅ **MCOIN ДОБАВЛЕНЫ!** ✅\n\n"
            f"👤 Пользователь: ID {user_id}\n"
            f"💰 Сумма: {format_number(amount)} MCoin\n"
            f"📊 Новый баланс: {format_number(user.mcoin)} MCoin",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Уведомляем пользователя
        try:
            await context.bot.send_message(
                user_id,
                f"🎁 **Вам начислено {format_number(amount)} MCoin!** 🎁\n\n"
                f"✨ Ваш баланс: {format_number(user.mcoin)} MCoin\n"
                f"Продолжайте использовать бота!",
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass
        
    except:
        await update.message.reply_text(
            "❌ **ОШИБКА!** ❌\n\n"
            "Используйте формат: `/add_mcoin 123456789 100`\n"
            "Где:\n"
            "• 123456789 - ID пользователя\n"
            "• 100 - сумма MCoin",
            parse_mode=ParseMode.MARKDOWN
        )
    
    return ConversationHandler.END

async def admin_withdraw_requests(update: Update, context: CallbackContext):
    """Просмотр заявок на вывод"""
    query = update.callback_query
    
    pending_requests = [r for r in db.withdraw_requests if r.status == "pending"]
    
    if not pending_requests:
        await query.answer("Нет активных заявок на вывод", show_alert=True)
        return
    
    requests_text = "💸 **ЗАЯВКИ НА ВЫВОД** 💸\n\n"
    
    for idx, req in enumerate(pending_requests[:10], 1):
        user = get_user(req.user_id)
        username = f"@{user.username}" if user.username else f"ID {req.user_id}"
        
        requests_text += (
            f"{idx}. **Заявка #{idx}**\n"
            f"   👤 Пользователь: {username}\n"
            f"   💰 Сумма: {format_number(req.amount)} MCoin\n"
            f"   🏦 Адрес: {req.address}\n"
            f"   📅 Создана: {req.created_at[:10]}\n\n"
        )
    
    keyboard = [
        [InlineKeyboardButton("✅ Одобрить", callback_data="approve_withdraw")],
        [InlineKeyboardButton("❌ Отклонить", callback_data="reject_withdraw")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(requests_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def admin_stats(update: Update, context: CallbackContext):
    """Статистика бота"""
    query = update.callback_query
    
    total_users = len(db.users)
    active_users = len([u for u in db.users.values() if u.last_active and 
                        datetime.fromisoformat(u.last_active) > datetime.now() - timedelta(days=7)])
    total_mcoin = sum(u.mcoin for u in db.users.values())
    total_earned = sum(u.total_earned for u in db.users.values())
    total_withdrawn = sum(u.total_withdrawn for u in db.users.values())
    
    total_cases_opened = sum(c.total_opened for c in db.cases.values())
    total_referrals = sum(len(u.referrals) for u in db.users.values())
    
    stats_text = (
        "📊 **СТАТИСТИКА БОТА** 📊\n\n"
        "**Пользователи:**\n"
        f"• Всего: {format_number(total_users)}\n"
        f"• Активных (7 дней): {format_number(active_users)}\n"
        f"• Рефералов всего: {format_number(total_referrals)}\n\n"
        "**Экономика:**\n"
        f"• В обращении: {format_number(total_mcoin)} MCoin\n"
        f"• Заработано всего: {format_number(total_earned)} MCoin\n"
        f"• Выведено всего: {format_number(total_withdrawn)} MCoin\n\n"
        "**Активность:**\n"
        f"• Открыто кейсов: {format_number(total_cases_opened)}\n"
        f"• Активных лотерей: {1 if db.lottery.active else 0}\n"
        f"• Чеков создано: {len(db.checks)}\n\n"
        f"📅 Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    
    keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data="admin_stats")],
                [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(stats_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def admin_mailing_start(update: Update, context: CallbackContext):
    """Начало рассылки"""
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        "📨 **РАССЫЛКА** 📨\n\n"
        "Введите текст сообщения для рассылки:\n"
        "(можно использовать HTML и Markdown)\n\n"
        "Для отмены введите /cancel"
    )
    return 1

async def admin_mailing_process(update: Update, context: CallbackContext):
    """Отправка рассылки"""
    message_text = update.message.text
    user_id = update.effective_user.id
    
    await update.message.reply_text(
        "🔄 **Начинаю рассылку...**\n\n"
        "Это может занять некоторое время.",
        parse_mode=ParseMode.MARKDOWN
    )
    
    success_count = 0
    fail_count = 0
    
    for user_id in db.users.keys():
        try:
            await context.bot.send_message(
                user_id,
                f"📢 **НОВОСТЬ ОТ АДМИНИСТРАЦИИ** 📢\n\n{message_text}",
                parse_mode=ParseMode.MARKDOWN
            )
            success_count += 1
            await asyncio.sleep(0.05)  # Защита от блокировки
        except:
            fail_count += 1
    
    await update.message.reply_text(
        f"✅ **РАССЫЛКА ЗАВЕРШЕНА** ✅\n\n"
        f"📨 Отправлено: {success_count}\n"
        f"❌ Не доставлено: {fail_count}\n"
        f"📊 Всего пользователей: {len(db.users)}",
        parse_mode=ParseMode.MARKDOWN
    )
    return ConversationHandler.END

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
async def start(update: Update, context: CallbackContext):
    """Обработка команды /start"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    # Обновляем информацию о пользователе
    user.username = update.effective_user.username or ""
    user.first_name = update.effective_user.first_name or ""
    user.last_name = update.effective_user.last_name or ""
    user.last_active = datetime.now().isoformat()
    db.save()
    
    # Проверяем реферальную ссылку
    if context.args and context.args[0].startswith("ref_"):
        referrer_id = int(context.args[0].replace("ref_", ""))
        if referrer_id != user_id and not user.referrer:
            user.referrer = referrer_id
            referrer = get_user(referrer_id)
            referrer.referrals.append(user_id)
            add_mcoins(referrer_id, 5, TransactionType.REFERRAL_REWARD, f"Referral {user_id}")
            db.save()
            
            # Уведомляем реферера
            try:
                await context.bot.send_message(
                    referrer_id,
                    f"👥 **НОВЫЙ РЕФЕРАЛ!** 👥\n\n"
                    f"Пользователь {user.first_name} присоединился по вашей ссылке!\n"
                    f"💰 Вы получили 5 MCoin!",
                    parse_mode=ParseMode.MARKDOWN
                )
            except:
                pass
    
    welcome_text = (
        f"👋 **ДОБРО ПОЖАЛОВАТЬ, {user.first_name}!** 👋\n\n"
        f"🎮 **Добро пожаловать в игрового бота!**\n\n"
        f"**Что вы можете делать:**\n"
        f"💰 Зарабатывать MCoin на заданиях\n"
        f"🎲 Играть в игры и выигрывать\n"
        f"📦 Открывать кейсы с наградами\n"
        f"🎰 Участвовать в лотерее\n"
        f"👥 Приглашать друзей и получать бонусы\n\n"
        f"💡 **Совет:** Начните с выполнения заданий!\n"
        f"📊 Ваш ID: `{user_id}`\n\n"
        f"Используйте кнопки меню для навигации 👇"
    )
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_keyboard(user_id),
        parse_mode=ParseMode.MARKDOWN
    )

async def balance(update: Update, context: CallbackContext):
    """Показывает баланс пользователя"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    # Подсчёт статистики
    total_tasks = len(user.tasks_completed)
    total_games_won = user.game_stats["wins"]
    total_games_lost = user.game_stats["losses"]
    win_rate = (total_games_won / (total_games_won + total_games_lost) * 100) if (total_games_won + total_games_lost) > 0 else 0
    
    # Ранг пользователя
    if user.mcoin >= 10000:
        rank = "👑 Легенда"
        rank_emoji = "👑"
    elif user.mcoin >= 5000:
        rank = "💎 Бриллиант"
        rank_emoji = "💎"
    elif user.mcoin >= 1000:
        rank = "🥇 Золото"
        rank_emoji = "🥇"
    elif user.mcoin >= 500:
        rank = "🥈 Серебро"
        rank_emoji = "🥈"
    elif user.mcoin >= 100:
        rank = "🥉 Бронза"
        rank_emoji = "🥉"
    else:
        rank = "🪙 Новичок"
        rank_emoji = "🪙"
    
    await update.message.reply_text(
        f"💰 **ВАШ БАЛАНС** 💰\n\n"
        f"{rank_emoji} **Ранг:** {rank}\n"
        f"🎮 **MCoin:** {format_number(user.mcoin)}\n"
        f"📊 **Всего заработано:** {format_number(user.total_earned)}\n"
        f"💸 **Всего потрачено:** {format_number(user.total_spent)}\n\n"
        f"**📊 Статистика:**\n"
        f"✅ Заданий выполнено: {total_tasks}\n"
        f"🎮 Игр выиграно: {total_games_won}\n"
        f"📉 Игр проиграно: {total_games_lost}\n"
        f"📈 Процент побед: {win_rate:.1f}%\n\n"
        f"👥 Рефералов: {len(user.referrals)}\n"
        f"🔥 Ежедневный стрик: {user.daily_streak} дней\n\n"
        f"📅 В боте с: {user.join_date[:10]}",
        parse_mode=ParseMode.MARKDOWN
    )

async def help_command(update: Update, context: CallbackContext):
    """Помощь"""
    help_text = (
        "❓ **ПОМОЩЬ И ИНСТРУКЦИЯ** ❓\n\n"
        "**📋 ЗАДАНИЯ**\n"
        "• Выполняйте задания и получайте MCoin\n"
        "• Подписывайтесь на каналы/группы\n"
        "• Нажимайте «Я выполнил» после подписки\n\n"
        "**🎮 ИГРЫ**\n"
        "• `/casino 100 7` - Казино (угадай число)\n"
        "• `/dice 50 3` - Кости (угадай выпадение)\n"
        "• `/slots 100` - Слоты\n"
        "• `/blackjack 100` - Блэкджек 21\n\n"
        "**📦 КЕЙСЫ**\n"
        "• Открывайте кейсы с разными наградами\n"
        "• Шансы зависят от редкости предмета\n\n"
        "**🎰 ЛОТЕРЕЯ**\n"
        "• Покупайте билеты за MCoin\n"
        "• Участвуйте в розыгрышах\n"
        "• Победитель получает 80% призового фонда\n\n"
        "**👥 РЕФЕРАЛЫ**\n"
        "• Приглашайте друзей по вашей ссылке\n"
        "• Получайте 5 MCoin за каждого друга\n\n"
        "**💸 ВЫВОД**\n"
        "• Минимальная сумма: 10 MCoin\n"
        "• Способы: USDT, карта, другие\n"
        "• Время обработки: до 24 часов\n\n"
        "**📝 ЧЕКИ**\n"
        "• Создавайте чеки на перевод MCoin\n"
        "• Активируйте чеки по коду\n"
        "• Чек действителен 30 дней\n\n"
        "**🏆 ЕЖЕДНЕВНЫЙ БОНУС**\n"
        "• Получайте бонус каждый день\n"
        "• Чем больше стрик - тем больше бонус\n\n"
        "**⚡ Быстрые команды:**\n"
        "/start - Начать\n"
        "/balance - Баланс\n"
        "/help - Помощь\n"
        "/stats - Статистика\n\n"
        "📞 **Поддержка:** @admin_username"
    )
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def stats(update: Update, context: CallbackContext):
    """Личная статистика пользователя"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    # Подсчёт дополнительной статистики
    cases_opened = sum(1 for item in user.inventory if isinstance(item, dict))
    
    stats_text = (
        f"📊 **ВАША СТАТИСТИКА** 📊\n\n"
        f"**Основная:**\n"
        f"• ID: `{user_id}`\n"
        f"• Имя: {user.first_name}\n"
        f"• Username: @{user.username if user.username else 'не указан'}\n"
        f"• В боте с: {user.join_date[:10]}\n\n"
        f"**Экономика:**\n"
        f"• MCoin: {format_number(user.mcoin)}\n"
        f"• Заработано: {format_number(user.total_earned)}\n"
        f"• Потрачено: {format_number(user.total_spent)}\n"
        f"• Выведено: {format_number(user.total_withdrawn)}\n\n"
        f"**Игры:**\n"
        f"• Побед: {user.game_stats['wins']}\n"
        f"• Поражений: {user.game_stats['losses']}\n"
        f"• Всего ставок: {format_number(user.game_stats['total_bet'])}\n"
        f"• Выиграно: {format_number(user.game_stats['total_win'])}\n\n"
        f"**Активность:**\n"
        f"• Заданий выполнено: {len(user.tasks_completed)}\n"
        f"• Кейсов открыто: {cases_opened}\n"
        f"• Рефералов: {len(user.referrals)}\n"
        f"• Ежедневный стрик: {user.daily_streak} дней",
        parse_mode=ParseMode.MARKDOWN
    )
    
    await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)

async def handle_text(update: Update, context: CallbackContext):
    """Обработка текстовых сообщений"""
    user_id = update.effective_user.id
    text = update.message.text.upper()
    
    if text == "💰 БАЛАНС":
        await balance(update, context)
    elif text == "📋 ЗАДАНИЯ":
        await tasks_mode(update, context)
    elif text == "🎮 ИГРЫ":
        keyboard = [
            [InlineKeyboardButton("🎰 Казино (/casino)", callback_data="game_casino_info")],
            [InlineKeyboardButton("🎲 Кости (/dice)", callback_data="game_dice_info")],
            [InlineKeyboardButton("🎰 Слоты (/slots)", callback_data="game_slots_info")],
            [InlineKeyboardButton("🃏 Блэкджек (/blackjack)", callback_data="game_blackjack_info")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🎮 **ВЫБЕРИТЕ ИГРУ** 🎮\n\n"
            "Доступные игры:\n"
            "• 🎰 Казино - угадай число (x2-x5)\n"
            "• 🎲 Кости - угадай выпадение (x3)\n"
            "• 🎰 Слоты - крути барабаны (x2-x20)\n"
            "• 🃏 Блэкджек - набери 21 очко (x2-x2.5)\n\n"
            "Все игры на MCoin!",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    elif text == "📦 КЕЙСЫ":
        await cases_menu(update, context)
    elif text == "🎰 ЛОТЕРЕЯ":
        await lottery_menu(update, context)
    elif text == "👥 РЕФЕРАЛЫ":
        await referrals_menu(update, context)
    elif text == "🏆 ЕЖЕДНЕВНЫЙ":
        await daily_bonus(update, context)
    elif text == "💸 ВЫВОД":
        await withdraw_menu(update, context)
    elif text == "📝 ЧЕКИ":
        await checks_menu(update, context)
    elif text == "❓ ПОМОЩЬ":
        await help_command(update, context)
    elif text == "⚙️ АДМИН ПАНЕЛЬ" and user_id in ADMIN_IDS:
        await admin_panel(update, context)
    else:
        await update.message.reply_text(
            "❓ **НЕИЗВЕСТНАЯ КОМАНДА** ❓\n\n"
            "Используйте кнопки меню для навигации:\n"
            "💰 БАЛАНС\n"
            "📋 ЗАДАНИЯ\n"
            "🎮 ИГРЫ\n"
            "📦 КЕЙСЫ\n"
            "🎰 ЛОТЕРЕЯ\n"
            "👥 РЕФЕРАЛЫ\n"
            "🏆 ЕЖЕДНЕВНЫЙ\n"
            "💸 ВЫВОД\n"
            "📝 ЧЕКИ\n"
            "❓ ПОМОЩЬ",
            reply_markup=get_main_keyboard(user_id),
            parse_mode=ParseMode.MARKDOWN
        )

# ========== ЗАПУСК БОТА ==========
def main():
    """Запуск бота"""
    # Создаём приложение
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Создаём ConversationHandler для чеков
    create_check_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(create_check_start, pattern="^create_check$")],
        states={
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_check_amount)],
        },
        fallbacks=[],
    )
    
    # ConversationHandler для активации чека
    activate_check_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(activate_check_start, pattern="^activate_check$")],
        states={
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, activate_check_code)],
        },
        fallbacks=[],
    )
    
    # ConversationHandler для вывода средств
    withdraw_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(request_withdraw_start, pattern="^request_withdraw$")],
        states={
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, request_withdraw_amount)],
            2: [MessageHandler(filters.TEXT & ~filters.COMMAND, request_withdraw_address)],
        },
        fallbacks=[],
    )
    
    # ConversationHandler для админ функций
    admin_add_mcoin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_mcoin_start, pattern="^admin_add_mcoin$")],
        states={
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_mcoin_process)],
        },
        fallbacks=[],
    )
    
    admin_mailing_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_mailing_start, pattern="^admin_mailing$")],
        states={
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_mailing_process)],
        },
        fallbacks=[],
    )
    
    # Регистрируем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("casino", game_casino))
    app.add_handler(CommandHandler("dice", game_dice))
    app.add_handler(CommandHandler("slots", game_slots))
    app.add_handler(CommandHandler("blackjack", game_blackjack))
    
    # Регистрируем ConversationHandler'ы
    app.add_handler(create_check_conv)
    app.add_handler(activate_check_conv)
    app.add_handler(withdraw_conv)
    app.add_handler(admin_add_mcoin_conv)
    app.add_handler(admin_mailing_conv)
    
    # Регистрируем CallbackQueryHandler'ы
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_balance_menu, pattern="^admin_balance$"))
    app.add_handler(CallbackQueryHandler(admin_withdraw_requests, pattern="^admin_withdraw_requests$"))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.message.delete(), pattern="^back_to_main$"))
    
    # Игры
    app.add_handler(CallbackQueryHandler(blackjack_hit, pattern="^bj_hit$"))
    app.add_handler(CallbackQueryHandler(blackjack_stand, pattern="^bj_stand$"))
    
    # Кейсы
    app.add_handler(CallbackQueryHandler(lambda u,c: cases_menu(u, c), pattern="^cases_back$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: lottery_menu(u, c), pattern="^lottery_back$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: checks_menu(u, c), pattern="^checks_back$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: withdraw_menu(u, c), pattern="^withdraw_back$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: referrals_menu(u, c), pattern="^referrals_back$"))
    
    # BotoHub задания
    app.add_handler(CallbackQueryHandler(check_task, pattern="^check_task_"))
    app.add_handler(CallbackQueryHandler(skip_task, pattern="^skip_task$"))
    app.add_handler(CallbackQueryHandler(task_help, pattern="^task_help$"))
    
    # Лотерея
    app.add_handler(CallbackQueryHandler(buy_ticket, pattern="^buy_ticket$"))
    app.add_handler(CallbackQueryHandler(buy_10_tickets, pattern="^buy_10_tickets$"))
    app.add_handler(CallbackQueryHandler(lottery_info, pattern="^lottery_info$"))
    
    # Рефералы
    app.add_handler(CallbackQueryHandler(ref_stats, pattern="^ref_stats$"))
    
    # Чеки
    app.add_handler(CallbackQueryHandler(my_checks, pattern="^my_checks$"))
    
    # Игровые info
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.message.reply_text(
        "🎰 **КАЗИНО** 🎰\n\nПравила: угадайте число от 1 до 10\n"
        "Выигрыш: x2-x5\nИспользование: /casino <сумма> <число>",
        parse_mode=ParseMode.MARKDOWN
    ), pattern="^game_casino_info$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.message.reply_text(
        "🎲 **КОСТИ** 🎲\n\nПравила: угадайте число от 1 до 6\n"
        "Выигрыш: x3\nИспользование: /dice <сумма> <число>",
        parse_mode=ParseMode.MARKDOWN
    ), pattern="^game_dice_info$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.message.reply_text(
        "🎰 **СЛОТЫ** 🎰\n\nПравила: крутите слоты и собирайте комбинации\n"
        "Выигрыш: x2-x20\nИспользование: /slots <сумма>",
        parse_mode=ParseMode.MARKDOWN
    ), pattern="^game_slots_info$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.message.reply_text(
        "🃏 **БЛЭКДЖЕК** 🃏\n\nПравила: наберите 21 очко или больше чем у дилера\n"
        "Выигрыш: x2-x2.5\nИспользование: /blackjack <сумма>",
        parse_mode=ParseMode.MARKDOWN
    ), pattern="^game_blackjack_info$"))
    
    # Обработчик текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Запуск бота
    logger.info("🚀 Бот запущен и готов к работе!")
    print("="*50)
    print("🤖 БОТ УСПЕШНО ЗАПУЩЕН!")
    print(f"📊 Всего пользователей в БД: {len(db.users)}")
    print(f"📦 Всего кейсов: {len(db.cases)}")
    print(f"🎰 Лотерея: {'Активна' if db.lottery.active else 'Не активна'}")
    print(f"👑 Администраторы: {ADMIN_IDS}")
    print("="*50)
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()