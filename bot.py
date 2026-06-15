import asyncio
import random
import json
import os
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple, Any
from collections import defaultdict
from enum import Enum
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    CallbackContext,
    ConversationHandler,
    JobQueue,
)
import aiohttp

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = "8251949164:AAEUSmnhX_S4p-vWDD4fvC6mDclV0LvIFe0"
BOTOHUB_TOKEN = "3feed57e-9303-4343-8d87-ed8d9dd5650f"
BOTOHUB_API_URL = "https://botohub.me/get-tasks"
ADMIN_ID = 5356403777

# Состояния для ConversationHandler
(SET_REWARD, SET_PRICE, SET_NAME, SET_DESCRIPTION, SET_WIN_CHANCE, 
 SET_ADMIN_ID, SET_CHANNEL, SET_PROMO, SET_WITHDRAW, SET_CHEQUE_AMOUNT,
 MAILING_TEXT, SET_TAX, SET_LIMIT, SET_REF_BONUS, EDIT_ITEM) = range(15)

# Типы игр
class GameType(Enum):
    CASINO = "casino"
    DICE = "dice"
    SLOTS = "slots"
    BLACKJACK = "blackjack"
    ROULETTE = "roulette"

# Файлы для хранения данных
DATA_FILE = "bot_data.json"
SETTINGS_FILE = "settings.json"
PROMO_FILE = "promo_codes.json"

# ========== СТРУКТУРА ДАННЫХ ==========
class BotDatabase:
    def __init__(self):
        self.users: Dict[int, Dict] = {}
        self.cases: Dict[str, Dict] = {}
        self.lottery: Dict = {
            "active": False,
            "tickets": {},
            "prize": 0,
            "end_time": None,
            "winner": None,
            "current_round": 1,
            "history": []
        }
        self.promo_codes: Dict[str, Dict] = {}
        self.cheques: Dict[int, List[Dict]] = {}  # user_id: [cheques]
        self.withdraw_requests: Dict[int, Dict] = {}
        self.game_history: Dict[int, List[Dict]] = {}
        self.bans: Dict[int, Dict] = {}
        self.global_stats: Dict = {
            "total_users": 0,
            "total_mcoins_earned": 0,
            "total_withdrawn": 0,
            "total_tasks_completed": 0,
            "top_users": []
        }
        
    def save(self):
        """Сохраняет все данные в файлы"""
        data = {
            "users": self.users,
            "cases": self.cases,
            "lottery": self.lottery,
            "promo_codes": self.promo_codes,
            "cheques": self.cheques,
            "withdraw_requests": self.withdraw_requests,
            "game_history": self.game_history,
            "bans": self.bans,
            "global_stats": self.global_stats
        }
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("Данные сохранены")
        except Exception as e:
            logger.error(f"Ошибка сохранения данных: {e}")
    
    def load(self):
        """Загружает данные из файлов"""
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.users = {int(k): v for k, v in data.get("users", {}).items()}
                    self.cases = data.get("cases", {})
                    self.lottery = data.get("lottery", {})
                    self.promo_codes = data.get("promo_codes", {})
                    self.cheques = {int(k): v for k, v in data.get("cheques", {}).items()}
                    self.withdraw_requests = {int(k): v for k, v in data.get("withdraw_requests", {}).items()}
                    self.game_history = {int(k): v for k, v in data.get("game_history", {}).items()}
                    self.bans = {int(k): v for k, v in data.get("bans", {}).items()}
                    self.global_stats = data.get("global_stats", self.global_stats)
                logger.info("Данные загружены")
            except Exception as e:
                logger.error(f"Ошибка загрузки данных: {e}")

class BotSettings:
    def __init__(self):
        self.task_reward = 10
        self.referral_reward = 5
        self.daily_reward = 15
        self.min_withdraw = 50
        self.max_withdraw = 10000
        self.game_tax = 0.05
        self.force_sub_channels = []
        self.force_sub_groups = []
        self.welcome_message = "Добро пожаловать в бот! 🎉"
        self.referral_program = True
        self.games_enabled = True
        self.cases_enabled = True
        self.lottery_enabled = True
        self.daily_limit = 1000
        self.ref_levels = [5, 10, 15, 20, 25]  # Бонусы за количество рефералов
        self.ref_multipliers = [1.0, 1.1, 1.2, 1.3, 1.5]
        self.admin_list = [ADMIN_ID]
        self.bot_name = "MCoin Bot"
        self.bot_description = "Зарабатывай MCoin выполняя задания!"
        self.currency_name = "MCoin"
        self.withdraw_methods = ["qiwi", "card", "crypto"]
        self.min_game_bet = 10
        self.max_game_bet = 1000
        self.casino_win_rate = 0.45
        self.slots_win_rate = 0.35
        self.roulette_win_rate = 0.48
        self.blackjack_win_rate = 0.49
        
    def save(self):
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.__dict__, f, ensure_ascii=False, indent=2)
    
    def load(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, value in data.items():
                        setattr(self, key, value)
                logger.info("Настройки загружены")
            except Exception as e:
                logger.error(f"Ошибка загрузки настроек: {e}")

# Глобальные объекты
db = BotDatabase()
settings = BotSettings()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Создает главную клавиатуру с динамическими кнопками"""
    keyboard = [
        [KeyboardButton(f"💰 {settings.currency_name}"), KeyboardButton("📋 Задания")],
        [KeyboardButton("🎲 Игры"), KeyboardButton("📦 Кейсы")],
        [KeyboardButton("🎰 Лотерея"), KeyboardButton("👥 Рефералы")],
        [KeyboardButton("🏆 Ежедневный бонус"), KeyboardButton("💸 Вывод средств")],
        [KeyboardButton("🎫 Промокоды"), KeyboardButton("📊 Статистика")]
    ]
    
    if user_id in settings.admin_list:
        keyboard.append([KeyboardButton("⚙️ Админ панель")])
    
    if user_id in db.bans:
        return ReplyKeyboardMarkup([["ℹ️ Я в бане"]], resize_keyboard=True)
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_user_data(user_id: int) -> Dict:
    """Получает данные пользователя, создает если нет"""
    if user_id not in db.users:
        db.users[user_id] = {
            "mcoin": 0,
            "tasks_completed": [],
            "inventory": [],
            "referrals": [],
            "referrer": None,
            "daily_last": None,
            "total_earned": 0,
            "total_withdrawn": 0,
            "games_played": 0,
            "games_won": 0,
            "cases_opened": 0,
            "join_date": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
            "username": None,
            "first_name": "",
            "last_name": "",
            "level": 1,
            "experience": 0,
            "achievements": [],
            "daily_streak": 0,
            "last_streak_date": None,
            "referral_earned": 0,
            "task_earned": 0,
            "game_earned": 0,
            "case_earned": 0,
            "lottery_earned": 0
        }
        db.global_stats["total_users"] += 1
        db.save()
    return db.users[user_id]

def add_mcoins(user_id: int, amount: int, reason: str = "", source: str = "other") -> bool:
    """Добавляет MCoin пользователю с логированием"""
    if amount <= 0:
        return False
    
    user = get_user_data(user_id)
    user["mcoin"] += amount
    user["total_earned"] += amount
    
    # Логируем источник дохода
    if source == "task":
        user["task_earned"] += amount
        db.global_stats["total_tasks_completed"] += 1
    elif source == "referral":
        user["referral_earned"] += amount
    elif source == "game":
        user["game_earned"] += amount
    elif source == "case":
        user["case_earned"] += amount
    elif source == "lottery":
        user["lottery_earned"] += amount
    
    db.global_stats["total_mcoins_earned"] += amount
    
    # Обновляем уровень пользователя
    update_user_level(user_id)
    
    db.save()
    logger.info(f"Пользователю {user_id} начислено {amount} MCoin. Причина: {reason}. Баланс: {user['mcoin']}")
    return True

def remove_mcoins(user_id: int, amount: int, reason: str = "") -> bool:
    """Снимает MCoin, возвращает True если достаточно средств"""
    if amount <= 0:
        return False
    
    user = get_user_data(user_id)
    if user["mcoin"] >= amount:
        user["mcoin"] -= amount
        db.save()
        logger.info(f"С пользователя {user_id} списано {amount} MCoin. Причина: {reason}. Баланс: {user['mcoin']}")
        return True
    return False

def update_user_level(user_id: int):
    """Обновляет уровень пользователя на основе заработанных MCoin"""
    user = get_user_data(user_id)
    total_earned = user["total_earned"]
    
    # Простая формула уровня: level = floor(log2(total_earned / 100 + 1)) + 1
    if total_earned >= 100:
        new_level = 1
        exp_needed = 100
        exp = total_earned
        
        while exp >= exp_needed and new_level < 100:
            exp -= exp_needed
            new_level += 1
            exp_needed = int(exp_needed * 1.5)
        
        if new_level > user["level"]:
            user["level"] = new_level
            return True
    return False

def get_level_info(user_id: int) -> Tuple[int, int, int]:
    """Возвращает (текущий уровень, опыт для след уровня, текущий опыт)"""
    user = get_user_data(user_id)
    total_earned = user["total_earned"]
    
    level = 1
    exp_needed = 100
    exp = total_earned
    
    while exp >= exp_needed and level < 100:
        exp -= exp_needed
        level += 1
        exp_needed = int(exp_needed * 1.5)
    
    return level, exp_needed, exp

def format_number(num: int) -> str:
    """Форматирует число с разделителями"""
    return f"{num:,}".replace(",", ".")

# ========== ФУНКЦИИ ДЛЯ ПРОВЕРКИ ПОДПИСОК ==========
async def check_force_subs(user_id: int, bot) -> Tuple[bool, List[str]]:
    """Проверяет обязательные подписки пользователя"""
    if not settings.force_sub_channels and not settings.force_sub_groups:
        return True, []
    
    not_subscribed = []
    
    # Проверяем каналы
    for channel in settings.force_sub_channels:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                not_subscribed.append(f"https://t.me/{channel}")
        except Exception as e:
            logger.error(f"Ошибка проверки канала {channel}: {e}")
            not_subscribed.append(f"Канал {channel}")
    
    # Проверяем группы
    for group in settings.force_sub_groups:
        try:
            member = await bot.get_chat_member(chat_id=group, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                not_subscribed.append(f"Группа {group}")
        except Exception as e:
            logger.error(f"Ошибка проверки группы {group}: {e}")
    
    return len(not_subscribed) == 0, not_subscribed

# ========== ИНТЕГРАЦИЯ BOTOHUB ==========
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

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(BOTOHUB_API_URL, json=payload, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error(f"BotoHub API ошибка: {resp.status}")
                    return {"tasks": [], "completed": False, "skip": True}
    except Exception as e:
        logger.error(f"BotoHub API исключение: {e}")
        return {"tasks": [], "completed": False, "skip": True}

# ========== ИГРЫ ==========
async def game_casino(update: Update, context: CallbackContext):
    """Игра Казино с расширенной логикой"""
    user_id = update.effective_user.id
    
    if not settings.games_enabled:
        await update.message.reply_text("🎮 Игры временно недоступны!")
        return
    
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "🎰 **Казино** 🎰\n\n"
            "Использование: /casino <сумма>\n"
            f"Минимальная ставка: {settings.min_game_bet} {settings.currency_name}\n"
            f"Максимальная ставка: {settings.max_game_bet} {settings.currency_name}\n\n"
            "Шанс выигрыша: 45%\n"
            "Максимальный выигрыш: x3 от ставки"
        )
        return
    
    try:
        bet = int(args[0])
        if bet < settings.min_game_bet or bet > settings.max_game_bet:
            await update.message.reply_text(
                f"❌ Ставка должна быть от {settings.min_game_bet} до {settings.max_game_bet} {settings.currency_name}"
            )
            return
    except:
        await update.message.reply_text("❌ Введите корректную сумму!")
        return
    
    # Проверяем дневной лимит
    user = get_user_data(user_id)
    today = datetime.now().date().isoformat()
    daily_bet = context.user_data.get(f"daily_bet_{today}", 0)
    
    if daily_bet + bet > settings.daily_limit:
        await update.message.reply_text(
            f"⚠️ Превышен дневной лимит ставок!\n"
            f"Лимит: {settings.daily_limit} {settings.currency_name}"
        )
        return
    
    if not remove_mcoins(user_id, bet, f"casino_bet_{bet}"):
        await update.message.reply_text(f"❌ Недостаточно {settings.currency_name}! У вас {user['mcoin']}")
        return
    
    context.user_data[f"daily_bet_{today}"] = daily_bet + bet
    
    # Логика казино
    win_chance = random.random()
    user["games_played"] += 1
    
    if win_chance < settings.casino_win_rate:
        # Выигрыш
        multiplier = random.uniform(1.5, 3.0)
        win_amount = int(bet * multiplier)
        add_mcoins(user_id, win_amount, f"casino_win_{bet}", "game")
        user["games_won"] += 1
        
        # Эффект для сообщения
        effects = ["🎉", "💰", "💎", "🏆", "✨", "⭐", "🔥"]
        effect = random.choice(effects)
        
        await update.message.reply_text(
            f"{effect} **ПОБЕДА!** {effect}\n\n"
            f"🎲 Ставка: {bet} {settings.currency_name}\n"
            f"🎁 Выигрыш: {win_amount} {settings.currency_name}\n"
            f"📈 Множитель: x{multiplier:.1f}\n\n"
            f"💰 Ваш баланс: {format_number(user['mcoin'])} {settings.currency_name}"
        )
    else:
        # Проигрыш
        await update.message.reply_text(
            f"😢 **ПРОИГРЫШ** 😢\n\n"
            f"🎲 Ставка: {bet} {settings.currency_name}\n"
            f"💸 Вы проиграли: {bet} {settings.currency_name}\n\n"
            f"💰 Ваш баланс: {format_number(user['mcoin'])} {settings.currency_name}\n\n"
            "Попробуйте снова! 🍀"
        )
    
    db.save()

async def game_dice(update: Update, context: CallbackContext):
    """Игра Кости"""
    user_id = update.effective_user.id
    
    if not settings.games_enabled:
        await update.message.reply_text("🎮 Игры временно недоступны!")
        return
    
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "🎲 **Кости** 🎲\n\n"
            "Использование: /dice <сумма>\n"
            f"Минимальная ставка: {settings.min_game_bet} {settings.currency_name}\n"
            f"Максимальная ставка: {settings.max_game_bet} {settings.currency_name}\n\n"
            "Правила: У вас и бота по 2 кубика. У кого сумма больше - тот победил."
        )
        return
    
    try:
        bet = int(args[0])
        if bet < settings.min_game_bet or bet > settings.max_game_bet:
            await update.message.reply_text(
                f"❌ Ставка должна быть от {settings.min_game_bet} до {settings.max_game_bet} {settings.currency_name}"
            )
            return
    except:
        await update.message.reply_text("❌ Введите корректную сумму!")
        return
    
    user = get_user_data(user_id)
    
    if not remove_mcoins(user_id, bet, f"dice_bet_{bet}"):
        await update.message.reply_text(f"❌ Недостаточно {settings.currency_name}! У вас {user['mcoin']}")
        return
    
    user["games_played"] += 1
    
    # Бросаем кости
    user_dice1 = random.randint(1, 6)
    user_dice2 = random.randint(1, 6)
    bot_dice1 = random.randint(1, 6)
    bot_dice2 = random.randint(1, 6)
    
    user_sum = user_dice1 + user_dice2
    bot_sum = bot_dice1 + bot_dice2
    
    # Анимация броска
    message = await update.message.reply_text(
        f"🎲 **БРОСАЕМ КОСТИ** 🎲\n\n"
        f"Ваши кости: ? и ?\n"
        f"Кости бота: ? и ?\n\n"
        f"⏳ Результат..."
    )
    
    await asyncio.sleep(1.5)
    
    if user_sum > bot_sum:
        win_amount = bet * 2
        add_mcoins(user_id, win_amount, f"dice_win_{bet}", "game")
        user["games_won"] += 1
        
        await message.edit_text(
            f"🎲 **ВЫ ПОБЕДИЛИ!** 🎲\n\n"
            f"🎲 Ваши кости: {user_dice1} и {user_dice2} (сумма: {user_sum})\n"
            f"🤖 Кости бота: {bot_dice1} и {bot_dice2} (сумма: {bot_sum})\n\n"
            f"🎁 Выигрыш: {win_amount} {settings.currency_name}\n"
            f"💰 Ваш баланс: {format_number(user['mcoin'])} {settings.currency_name}"
        )
    elif user_sum < bot_sum:
        await message.edit_text(
            f"🎲 **ВЫ ПРОИГРАЛИ** 🎲\n\n"
            f"🎲 Ваши кости: {user_dice1} и {user_dice2} (сумма: {user_sum})\n"
            f"🤖 Кости бота: {bot_dice1} и {bot_dice2} (сумма: {bot_sum})\n\n"
            f"💸 Проигрыш: {bet} {settings.currency_name}\n"
            f"💰 Ваш баланс: {format_number(user['mcoin'])} {settings.currency_name}\n\n"
            "Попробуйте снова! 🍀"
        )
    else:
        add_mcoins(user_id, bet, f"dice_draw_{bet}", "game")
        await message.edit_text(
            f"🎲 **НИЧЬЯ** 🎲\n\n"
            f"🎲 Ваши кости: {user_dice1} и {user_dice2} (сумма: {user_sum})\n"
            f"🤖 Кости бота: {bot_dice1} и {bot_dice2} (сумма: {bot_sum})\n\n"
            f"🔄 Ставка возвращена!\n"
            f"💰 Ваш баланс: {format_number(user['mcoin'])} {settings.currency_name}"
        )
    
    db.save()

async def game_slots(update: Update, context: CallbackContext):
    """Игра Слоты"""
    user_id = update.effective_user.id
    
    if not settings.games_enabled:
        await update.message.reply_text("🎮 Игры временно недоступны!")
        return
    
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "🎰 **Слоты** 🎰\n\n"
            "Использование: /slots <сумма>\n"
            f"Минимальная ставка: {settings.min_game_bet} {settings.currency_name}\n"
            f"Максимальная ставка: {settings.max_game_bet} {settings.currency_name}\n\n"
            "Символы: 🍒 | 🍊 | 🍋 | 🍉 | 🔔 | 💎\n"
            "3 одинаковых символа = выигрыш!"
        )
        return
    
    try:
        bet = int(args[0])
        if bet < settings.min_game_bet or bet > settings.max_game_bet:
            await update.message.reply_text(
                f"❌ Ставка должна быть от {settings.min_game_bet} до {settings.max_game_bet} {settings.currency_name}"
            )
            return
    except:
        await update.message.reply_text("❌ Введите корректную сумму!")
        return
    
    user = get_user_data(user_id)
    
    if not remove_mcoins(user_id, bet, f"slots_bet_{bet}"):
        await update.message.reply_text(f"❌ Недостаточно {settings.currency_name}! У вас {user['mcoin']}")
        return
    
    user["games_played"] += 1
    
    # Символы для слотов
    symbols = ["🍒", "🍊", "🍋", "🍉", "🔔", "💎"]
    symbol_values = {
        "🍒": 1.5, "🍊": 1.5, "🍋": 1.5,
        "🍉": 2.0, "🔔": 2.5, "💎": 3.0
    }
    
    # Результаты
    result = [random.choice(symbols) for _ in range(3)]
    
    # Анимация
    message = await update.message.reply_text(
        f"🎰 **КРУТИМ СЛОТЫ** 🎰\n\n"
        f"[ ? | ? | ? ]\n\n"
        f"⏳ Результат..."
    )
    
    await asyncio.sleep(1.5)
    
    # Проверка выигрыша
    if result[0] == result[1] == result[2]:
        multiplier = symbol_values[result[0]]
        win_amount = int(bet * multiplier)
        add_mcoins(user_id, win_amount, f"slots_win_{bet}", "game")
        user["games_won"] += 1
        
        await message.edit_text(
            f"🎰 **СЛОТЫ** 🎰\n\n"
            f"[ {result[0]} | {result[1]} | {result[2]} ]\n\n"
            f"🎉 **ДЖЕКПОТ!** 🎉\n"
            f"🎁 Выигрыш: {win_amount} {settings.currency_name}\n"
            f"📈 Множитель: x{multiplier}\n\n"
            f"💰 Ваш баланс: {format_number(user['mcoin'])} {settings.currency_name}"
        )
    elif result.count(result[0]) == 2 or result.count(result[1]) == 2:
        # 2 одинаковых символа - возврат ставки
        add_mcoins(user_id, bet, f"slots_two_{bet}", "game")
        await message.edit_text(
            f"🎰 **СЛОТЫ** 🎰\n\n"
            f"[ {result[0]} | {result[1]} | {result[2]} ]\n\n"
            f"😐 Почти получилось! 2 одинаковых символа\n"
            f"🔄 Ставка возвращена!\n\n"
            f"💰 Ваш баланс: {format_number(user['mcoin'])} {settings.currency_name}"
        )
    else:
        await message.edit_text(
            f"🎰 **СЛОТЫ** 🎰\n\n"
            f"[ {result[0]} | {result[1]} | {result[2]} ]\n\n"
            f"😢 **ПРОИГРЫШ**\n"
            f"💸 Проигрыш: {bet} {settings.currency_name}\n\n"
            f"💰 Ваш баланс: {format_number(user['mcoin'])} {settings.currency_name}\n\n"
            "Попробуйте снова! 🍀"
        )
    
    db.save()

# ========== КЕЙСЫ ==========
async def cases_menu(update: Update, context: CallbackContext):
    """Меню кейсов с подробным описанием"""
    if not settings.cases_enabled:
        await update.message.reply_text("📦 Кейсы временно недоступны!")
        return
    
    keyboard = []
    
    for case_name, case_data in db.cases.items():
        # Получаем список предметов для отображения
        items_preview = []
        for item in case_data["items"][:3]:  # Показываем первые 3 предмета
            items_preview.append(f"{item['name']} ({item['chance']}%)")
        items_text = ", ".join(items_preview)
        if len(case_data["items"]) > 3:
            items_text += f" и еще {len(case_data['items'])-3}"
        
        keyboard.append([InlineKeyboardButton(
            f"📦 {case_name} - {case_data['price']} {settings.currency_name}", 
            callback_data=f"case_info_{case_name}"
        )])
    
    if not keyboard:
        await update.message.reply_text(
            "📦 **Кейсы временно недоступны** 📦\n\n"
            "Скоро появятся новые кейсы с крутыми призами!\n"
            "Следите за обновлениями!"
        )
        return
    
    keyboard.append([InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎁 **Магазин кейсов** 🎁\n\n"
        "Выберите кейс для просмотра или открытия:\n"
        f"💰 Ваш баланс: {format_number(get_user_data(update.effective_user.id)['mcoin'])} {settings.currency_name}",
        reply_markup=reply_markup
    )

async def case_info_callback(update: Update, context: CallbackContext):
    """Показывает информацию о кейсе"""
    query = update.callback_query
    await query.answer()
    
    case_name = query.data.replace("case_info_", "")
    
    if case_name not in db.cases:
        await query.message.edit_text("❌ Кейс не найден!")
        return
    
    case_data = db.cases[case_name]
    
    # Формируем список предметов
    items_list = []
    for i, item in enumerate(case_data["items"], 1):
        items_list.append(f"{i}. {item['name']} - {item['chance']}% (шанс), {item['reward']} {settings.currency_name}")
    
    items_text = "\n".join(items_list)
    
    keyboard = [
        [InlineKeyboardButton("🎲 Открыть кейс", callback_data=f"open_case_{case_name}")],
        [InlineKeyboardButton("🔙 Назад к кейсам", callback_data="cases_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"📦 **Кейс: {case_name}** 📦\n\n"
        f"💰 Цена: {case_data['price']} {settings.currency_name}\n"
        f"📦 Предметов в кейсе: {len(case_data['items'])}\n\n"
        f"**Возможные предметы:**\n{items_text}\n\n"
        f"Нажмите «Открыть кейс» чтобы попытать удачу!",
        reply_markup=reply_markup
    )

async def open_case(update: Update, context: CallbackContext, case_name: str):
    """Открытие кейса с анимацией"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if case_name not in db.cases:
        await query.answer("Кейс не найден!", show_alert=True)
        return
    
    case_data = db.cases[case_name]
    price = case_data["price"]
    
    user = get_user_data(user_id)
    
    if not remove_mcoins(user_id, price, f"case_{case_name}"):
        await query.answer(f"Недостаточно {settings.currency_name}!", show_alert=True)
        return
    
    # Анимация открытия
    await query.message.edit_text(
        f"🎲 **Открываем кейс '{case_name}'** 🎲\n\n"
        f"💰 С вас списано: {price} {settings.currency_name}\n\n"
        f"⏳ Выпадает предмет..."
    )
    
    await asyncio.sleep(1.5)
    
    # Выбираем предмет из кейса
    items = case_data["items"]
    total_chance = sum(item["chance"] for item in items)
    roll = random.random() * total_chance
    
    current = 0
    selected_item = None
    for item in items:
        current += item["chance"]
        if roll <= current:
            selected_item = item
            break
    
    if not selected_item:
        selected_item = items[0]
    
    # Выдаем награду
    reward = selected_item["reward"]
    add_mcoins(user_id, reward, f"case_{case_name}_item_{selected_item['name']}", "case")
    user["cases_opened"] += 1
    
    # Эффекты для разных предметов
    effects = {
        "Легендарный": "🌟",
        "Эпический": "💎",
        "Редкий": "✨",
        "Обычный": "📦"
    }
    
    effect = "🎉"
    for key in effects:
        if key in selected_item['name']:
            effect = effects[key]
            break
    
    # Добавляем предмет в инвентарь
    user["inventory"].append({
        "name": selected_item['name'],
        "obtained": datetime.now().isoformat(),
        "from_case": case_name
    })
    
    await query.message.edit_text(
        f"{effect} **Вы открыли кейс '{case_name}'** {effect}\n\n"
        f"📦 Вам выпало: **{selected_item['name']}**\n"
        f"🎁 Награда: {reward} {settings.currency_name}\n\n"
        f"📊 Всего предметов в инвентаре: {len(user['inventory'])}\n"
        f"💰 Ваш баланс: {format_number(user['mcoin'])} {settings.currency_name}\n\n"
        f"✨ Удачного дня! ✨"
    )
    
    db.save()

# ========== ЛОТЕРЕЯ ==========
async def lottery_menu(update: Update, context: CallbackContext):
    """Меню лотереи с подробной информацией"""
    if not settings.lottery_enabled:
        await update.message.reply_text("🎰 Лотерея временно недоступна!")
        return
    
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    # Получаем количество билетов пользователя
    tickets = db.lottery["tickets"].get(user_id, 0)
    total_tickets = sum(db.lottery["tickets"].values())
    
    status = "Активна" if db.lottery["active"] else "Не активна"
    
    keyboard = [
        [InlineKeyboardButton("🎫 Купить билет (10 MCoin)", callback_data="buy_ticket")],
        [InlineKeyboardButton("🎫 Купить 10 билетов (95 MCoin)", callback_data="buy_10_tickets")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="lottery_info")],
        [InlineKeyboardButton("📊 Мои билеты", callback_data="my_tickets")]
    ]
    
    if user_id in settings.admin_list and db.lottery["active"]:
        keyboard.append([InlineKeyboardButton("🎲 Провести розыгрыш", callback_data="draw_lottery")])
    
    keyboard.append([InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Информация о призе
    prize_info = f"{format_number(db.lottery['prize'])} {settings.currency_name}" if db.lottery["active"] else "0"
    
    await update.message.reply_text(
        f"🎰 **Лотерея** 🎰\n\n"
        f"📊 Статус: {status}\n"
        f"💰 Призовой фонд: {prize_info}\n"
        f"🎫 Всего билетов: {total_tickets}\n"
        f"🎫 Ваших билетов: {tickets}\n"
        f"🎟️ Цена билета: 10 {settings.currency_name}\n\n"
        f"⚡ **Правила:**\n"
        f"• Каждый билет увеличивает шанс на победу\n"
        f"• Победитель получает 80% призового фонда\n"
        f"• 10% идет в следующий розыгрыш\n"
        f"• 10% забирает бот\n\n"
        f"🍀 Удачи в розыгрыше! 🍀",
        reply_markup=reply_markup
    )

async def buy_ticket(update: Update, context: CallbackContext, count: int = 1):
    """Покупка лотерейных билетов"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if not db.lottery.get("active", False):
        await query.answer("Лотерея не активна!", show_alert=True)
        return
    
    price = 10 * count
    discount = 0
    if count == 10:
        price = 95
        discount = 5
    
    if not remove_mcoins(user_id, price, f"lottery_tickets_{count}"):
        await query.answer(f"Недостаточно {settings.currency_name}!", show_alert=True)
        return
    
    # Добавляем билеты
    if user_id not in db.lottery["tickets"]:
        db.lottery["tickets"][user_id] = 0
    db.lottery["tickets"][user_id] += count
    db.lottery["prize"] += int(price * 0.8)  # 80% от цены в призовой фонд
    
    db.save()
    
    total_tickets = sum(db.lottery["tickets"].values())
    
    discount_text = f" (экономия {discount} MCoin)" if discount > 0 else ""
    
    await query.answer(f"Куплено {count} билетов! Удачи!", show_alert=True)
    await query.message.edit_text(
        f"✅ **Билеты куплены!**\n\n"
        f"🎫 Куплено: {count} билетов{discount_text}\n"
        f"💰 Стоимость: {price} {settings.currency_name}\n"
        f"🎫 Ваших билетов: {db.lottery['tickets'][user_id]}\n"
        f"🎫 Всего билетов: {total_tickets}\n"
        f"💰 Призовой фонд: {format_number(db.lottery['prize'])} {settings.currency_name}\n\n"
        f"🍀 Желаем удачи! 🍀"
    )

async def draw_lottery(update: Update, context: CallbackContext):
    """Проводит розыгрыш лотереи"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in settings.admin_list:
        await query.answer("Только для администратора!", show_alert=True)
        return
    
    if not db.lottery["active"]:
        await query.answer("Лотерея не активна!", show_alert=True)
        return
    
    total_tickets = sum(db.lottery["tickets"].values())
    
    if total_tickets == 0:
        await query.message.edit_text("❌ Нет билетов для розыгрыша!")
        return
    
    # Выбираем победителя
    winner_roll = random.randint(1, total_tickets)
    current = 0
    winner_id = None
    
    for uid, tickets in db.lottery["tickets"].items():
        current += tickets
        if current >= winner_roll:
            winner_id = uid
            break
    
    if not winner_id:
        winner_id = list(db.lottery["tickets"].keys())[0]
    
    # Рассчитываем приз
    prize = int(db.lottery["prize"] * 0.8)  # 80% победителю
    next_prize = int(db.lottery["prize"] * 0.1)  # 10% в следующий розыгрыш
    
    add_mcoins(winner_id, prize, "lottery_win", "lottery")
    
    # Сохраняем информацию о розыгрыше
    winner_name = db.users.get(winner_id, {}).get("first_name", f"User_{winner_id}")
    round_history = {
        "round": db.lottery["current_round"],
        "winner_id": winner_id,
        "winner_name": winner_name,
        "prize": prize,
        "total_tickets": total_tickets,
        "date": datetime.now().isoformat()
    }
    db.lottery["history"].append(round_history)
    
    # Сбрасываем лотерею для нового розыгрыша
    db.lottery["tickets"] = {}
    db.lottery["prize"] = next_prize
    db.lottery["current_round"] += 1
    db.lottery["winner"] = winner_id
    
    db.save()
    
    # Отправляем результат
    keyboard = [[InlineKeyboardButton("🎫 Купить билет", callback_data="lottery_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"🎉 **РОЗЫГРЫШ ЛОТЕРЕИ!** 🎉\n\n"
        f"🏆 **Победитель:** [{winner_name}](tg://user?id={winner_id})\n"
        f"💰 **Приз:** {format_number(prize)} {settings.currency_name}\n"
        f"🎫 **Всего билетов:** {total_tickets}\n"
        f"📊 **Раунд:** {db.lottery['current_round'] - 1}\n\n"
        f"✨ Следующий розыгрыш скоро!\n"
        f"💰 Призовой фонд следующего раунда: {format_number(next_prize)} {settings.currency_name}",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    
    # Поздравляем победителя в личку
    try:
        await context.bot.send_message(
            winner_id,
            f"🎉 **ПОЗДРАВЛЯЕМ!** 🎉\n\n"
            f"Вы выиграли в лотерее!\n"
            f"💰 Ваш выигрыш: {format_number(prize)} {settings.currency_name}\n\n"
            f"Баланс обновлен! 🎊"
        )
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение победителю: {e}")

# ========== ПРОМОКОДЫ ==========
async def promo_menu(update: Update, context: CallbackContext):
    """Меню промокодов"""
    await update.message.reply_text(
        "🎫 **Промокоды** 🎫\n\n"
        "Использование: /promo <код>\n\n"
        "Пример: /promo WELCOME100\n\n"
        "Активные промокоды можно получить в наших соцсетях!\n"
        "📢 Следите за новостями!"
    )

async def use_promo(update: Update, context: CallbackContext):
    """Использование промокода"""
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "🎫 **Использование промокода** 🎫\n\n"
            "Напишите: /promo <код>\n"
            "Пример: /promo WELCOME100"
        )
        return
    
    code = args[0].upper()
    
    if code not in db.promo_codes:
        await update.message.reply_text("❌ Неверный промокод!")
        return
    
    promo = db.promo_codes[code]
    
    # Проверяем срок действия
    if promo.get("expiry"):
        expiry_date = datetime.fromisoformat(promo["expiry"])
        if datetime.now() > expiry_date:
            await update.message.reply_text("❌ Срок действия промокода истек!")
            return
    
    # Проверяем лимит использований
    if len(promo.get("used_by", [])) >= promo.get("max_uses", 1):
        await update.message.reply_text("❌ Промокод уже использован максимальное количество раз!")
        return
    
    # Проверяем, использовал ли пользователь
    if user_id in promo.get("used_by", []):
        await update.message.reply_text("❌ Вы уже использовали этот промокод!")
        return
    
    # Начисляем награду
    reward = promo.get("reward", 0)
    add_mcoins(user_id, reward, f"promo_{code}", "other")
    
    # Обновляем промокод
    if "used_by" not in promo:
        promo["used_by"] = []
    promo["used_by"].append(user_id)
    
    db.save()
    
    await update.message.reply_text(
        f"✅ **Промокод активирован!**\n\n"
        f"🎉 Вы получили: {reward} {settings.currency_name}\n"
        f"💰 Ваш баланс: {format_number(get_user_data(user_id)['mcoin'])} {settings.currency_name}"
    )

# ========== ЕЖЕДНЕВНЫЙ БОНУС ==========
async def daily_bonus(update: Update, context: CallbackContext):
    """Ежедневный бонус с системой стриков"""
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    last_daily = user.get("daily_last")
    now = datetime.now()
    
    if last_daily:
        last_date = datetime.fromisoformat(last_daily)
        days_diff = (now - last_date).days
        
        if days_diff == 0:
            # Уже получал сегодня
            next_bonus = last_date + timedelta(days=1)
            time_left = next_bonus - now
            hours = time_left.seconds // 3600
            minutes = (time_left.seconds % 3600) // 60
            
            await update.message.reply_text(
                f"⏰ **Вы уже получали бонус сегодня!**\n\n"
                f"🎁 Следующий бонус через: {hours}ч {minutes}мин\n"
                f"📊 Текущая серия: {user['daily_streak']} дней\n\n"
                f"Не пропустите завтрашний бонус, чтобы увеличить серию!"
            )
            return
        elif days_diff == 1:
            # Серия продолжается
            user["daily_streak"] += 1
        elif days_diff > 1:
            # Серия сброшена
            user["daily_streak"] = 1
    
    # Рассчитываем бонус
    base_reward = settings.daily_reward
    streak_multiplier = 1 + (user["daily_streak"] * 0.05)  # +5% за каждый день серии
    reward = int(base_reward * min(streak_multiplier, 3.0))  # Максимум x3
    
    add_mcoins(user_id, reward, "daily_bonus", "other")
    user["daily_last"] = now.isoformat()
    user["last_streak_date"] = now.isoformat()
    
    # Дополнительные бонусы за достижения в серии
    extra_bonus = 0
    if user["daily_streak"] == 7:
        extra_bonus = 50
        add_mcoins(user_id, extra_bonus, "streak_7_days", "other")
    elif user["daily_streak"] == 30:
        extra_bonus = 250
        add_mcoins(user_id, extra_bonus, "streak_30_days", "other")
    elif user["daily_streak"] == 100:
        extra_bonus = 1000
        add_mcoins(user_id, extra_bonus, "streak_100_days", "other")
    
    db.save()
    
    extra_text = f"\n🎁 Бонус за серию: +{extra_bonus} {settings.currency_name}" if extra_bonus else ""
    
    await update.message.reply_text(
        f"🎁 **Ежедневный бонус!** 🎁\n\n"
        f"💰 Вы получили: {reward} {settings.currency_name}{extra_text}\n"
        f"📊 Серия: {user['daily_streak']} дней\n"
        f"📈 Множитель: x{streak_multiplier:.2f}\n\n"
        f"💰 Ваш баланс: {format_number(user['mcoin'])} {settings.currency_name}\n\n"
        f"✨ Заходите завтра, чтобы продолжить серию!"
    )

# ========== РЕФЕРАЛЬНАЯ СИСТЕМА ==========
async def referrals_menu(update: Update, context: CallbackContext):
    """Меню реферальной системы"""
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    if not settings.referral_program:
        await update.message.reply_text("❌ Реферальная программа временно отключена!")
        return
    
    bot_username = context.bot.username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    # Рассчитываем бонус за количество рефералов
    ref_count = len(user["referrals"])
    current_level = 0
    next_level_bonus = 0
    
    for i, level in enumerate(settings.ref_levels):
        if ref_count >= level:
            current_level = i + 1
        else:
            if i < len(settings.ref_levels):
                next_level_bonus = level - ref_count
            break
    
    level_multiplier = settings.ref_multipliers[current_level] if current_level < len(settings.ref_multipliers) else 1.5
    
    keyboard = [
        [InlineKeyboardButton("📋 Список рефералов", callback_data="my_referrals")],
        [InlineKeyboardButton("📊 Статистика по рефералам", callback_data="ref_stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👥 **Реферальная программа** 👥\n\n"
        f"Приглашайте друзей и получайте бонусы!\n\n"
        f"🏆 **Ваш уровень:** {current_level + 1}\n"
        f"📈 **Множитель награды:** x{level_multiplier}\n"
        f"👥 **Рефералов:** {ref_count}\n"
        f"💰 **Заработано:** {user['referral_earned']} {settings.currency_name}\n\n"
        f"🎁 **Награда за реферала:** {settings.referral_reward} {settings.currency_name}\n\n"
        f"📊 **Следующий уровень:** {next_level_bonus} рефералов\n\n"
        f"🔗 **Ваша реферальная ссылка:**\n`{ref_link}`\n\n"
        f"Отправьте её друзьям и получайте бонусы!",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def my_referrals(update: Update, context: CallbackContext):
    """Показывает список рефералов"""
    query = update.callback_query
    user_id = query.from_user.id
    user = get_user_data(user_id)
    
    if not user["referrals"]:
        await query.answer("У вас пока нет рефералов!", show_alert=True)
        return
    
    referrals_list = []
    for i, ref_id in enumerate(user["referrals"], 1):
        ref_user = db.users.get(ref_id, {})
        ref_name = ref_user.get("first_name", f"User_{ref_id}")
        ref_earned = ref_user.get("total_earned", 0)
        ref_join = ref_user.get("join_date", "Unknown")[:10]
        
        referrals_list.append(f"{i}. {ref_name} - Заработал: {ref_earned} {settings.currency_name} (с {ref_join})")
    
    # Разбиваем на страницы
    page = 0
    items_per_page = 10
    total_pages = (len(referrals_list) + items_per_page - 1) // items_per_page
    
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    
    text = "📋 **Ваши рефералы:**\n\n" + "\n".join(referrals_list[start_idx:end_idx])
    text += f"\n\n📊 Страница {page + 1} из {total_pages}"
    
    keyboard = []
    if total_pages > 1:
        if page > 0:
            keyboard.append(InlineKeyboardButton("◀️ Назад", callback_data=f"ref_page_{page-1}"))
        if page < total_pages - 1:
            keyboard.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"ref_page_{page+1}"))
    
    keyboard.append(InlineKeyboardButton("🔙 Назад", callback_data="referrals_menu"))
    reply_markup = InlineKeyboardMarkup([keyboard]) if keyboard else InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="referrals_menu")]])
    
    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")

# ========== СТАТИСТИКА ==========
async def stats_menu(update: Update, context: CallbackContext):
    """Показывает статистику пользователя и глобальную"""
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    # Достижения
    achievements = []
    if user["total_earned"] >= 1000:
        achievements.append("🏆 Заработал 1000 MCoin")
    if user["games_won"] >= 10:
        achievements.append("🎲 Победил в 10 играх")
    if user["cases_opened"] >= 50:
        achievements.append("📦 Открыл 50 кейсов")
    if user["daily_streak"] >= 7:
        achievements.append("🔥 7-дневная серия")
    if len(user["referrals"]) >= 5:
        achievements.append("👥 Пригласил 5 друзей")
    
    stats_text = (
        f"📊 **Ваша статистика** 📊\n\n"
        f"💰 Баланс: {format_number(user['mcoin'])} {settings.currency_name}\n"
        f"📈 Всего заработано: {format_number(user['total_earned'])} {settings.currency_name}\n"
        f"💸 Выведено: {format_number(user['total_withdrawn'])} {settings.currency_name}\n\n"
        f"🎮 Игр сыграно: {user['games_played']}\n"
        f"🏆 Побед в играх: {user['games_won']}\n"
        f"📦 Кейсов открыто: {user['cases_opened']}\n\n"
        f"👥 Рефералов: {len(user['referrals'])}\n"
        f"🔥 Ежедневная серия: {user['daily_streak']} дней\n"
        f"📅 В боте с: {user['join_date'][:10]}\n\n"
    )
    
    if achievements:
        stats_text += "🏅 **Достижения:**\n" + "\n".join(achievements)
    
    # Глобальная статистика
    stats_text += (
        f"\n\n🌍 **Глобальная статистика** 🌍\n\n"
        f"👥 Всего пользователей: {db.global_stats['total_users']}\n"
        f"💰 Всего заработано: {format_number(db.global_stats['total_mcoins_earned'])} {settings.currency_name}\n"
        f"💸 Всего выведено: {format_number(db.global_stats['total_withdrawn'])} {settings.currency_name}\n"
        f"✅ Заданий выполнено: {db.global_stats['total_tasks_completed']}"
    )
    
    await update.message.reply_text(stats_text, parse_mode="Markdown")

# ========== ЗАДАНИЯ BOTOHUB ==========
async def tasks_mode(update: Update, context: CallbackContext):
    """Режим заданий с полной интеграцией BotoHub"""
    user_id = update.effective_user.id
    
    # Проверяем обязательные подписки
    passed, not_passed = await check_force_subs(user_id, context.bot)
    if not passed:
        msg = "⚠️ **Для выполнения заданий необходимо подписаться:**\n\n"
        for channel in not_passed:
            msg += f"• {channel}\n"
        msg += "\nПосле подписки нажмите /tasks снова"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return
    
    msg = await update.message.reply_text("🔄 Получаем задание...")
    
    try:
        result = await call_botohub_api(user_id, is_task=True, skip=False)
        
        tasks = result.get("tasks", [])
        completed = result.get("completed", False)
        skip_flag = result.get("skip", False)
        prev_success = result.get("prev_success", False)
        
        if completed:
            await msg.edit_text("✅ Вы выполнили все задания! Получите награду!")
            task_reward = settings.task_reward
            add_mcoins(user_id, task_reward, "all_tasks_completed", "task")
            await update.message.reply_text(
                f"🎉 **Поздравляем!** 🎉\n\n"
                f"Вы выполнили все доступные задания!\n"
                f"💰 Награда: {task_reward} {settings.currency_name}\n\n"
                f"✨ Новые задания появятся позже!"
            )
            return
        
        if skip_flag or not tasks:
            await msg.edit_text(
                "🎉 **Нет активных заданий!** 🎉\n\n"
                "Пожалуйста, зайдите позже.\n"
                "В это время вы можете:\n"
                "• Играть в игры 🎲\n"
                "• Открывать кейсы 📦\n"
                "• Участвовать в лотерее 🎰"
            )
            return
        
        task_url = tasks[0]
        
        # Сохраняем текущее задание
        context.user_data["current_task_url"] = task_url
        
        keyboard = [
            [InlineKeyboardButton("✅ Я выполнил", callback_data=f"check_task_{task_url}")],
            [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await msg.edit_text(
            f"📢 **Новое задание!** 📢\n\n"
            f"🔗 **Ссылка:** {task_url}\n\n"
            f"💰 **Награда:** {settings.task_reward} {settings.currency_name}\n\n"
            f"**Как выполнить:**\n"
            f"1. Перейдите по ссылке\n"
            f"2. Подпишитесь на канал\n"
            f"3. Вернитесь и нажмите «✅ Я выполнил»\n\n"
            f"⏱️ Время на выполнение: 3 минуты\n"
            f"✨ Удачи!",
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logger.error(f"Ошибка в tasks_mode: {e}")
        await msg.edit_text(f"❌ Ошибка при получении заданий: {e}\n\nПопробуйте позже.")

async def check_task_callback(update: Update, context: CallbackContext):
    """Проверка выполнения задания через callback"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    task_url = query.data.replace("check_task_", "")
    
    await query.edit_message_text("🔍 **Проверяем выполнение задания...**\n\nПожалуйста, подождите...")
    
    try:
        result = await call_botohub_api(user_id, is_task=True, skip=False)
        
        prev_success = result.get("prev_success", False)
        completed = result.get("completed", False)
        tasks = result.get("tasks", [])
        
        if prev_success:
            # Задание выполнено
            task_reward = settings.task_reward
            add_mcoins(user_id, task_reward, "task_completed", "task")
            
            if completed:
                await query.edit_message_text(
                    f"✅ **Задание выполнено!** ✅\n\n"
                    f"💰 Вы получили: {task_reward} {settings.currency_name}\n"
                    f"🎉 **Поздравляем! Вы выполнили все задания!**\n\n"
                    f"💰 Ваш баланс: {format_number(get_user_data(user_id)['mcoin'])} {settings.currency_name}"
                )
            elif tasks:
                # Есть следующее задание
                new_url = tasks[0]
                context.user_data["current_task_url"] = new_url
                
                keyboard = [
                    [InlineKeyboardButton("✅ Я выполнил", callback_data=f"check_task_{new_url}")],
                    [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"✅ **Задание выполнено!** ✅\n\n"
                    f"💰 Вы получили: {task_reward} {settings.currency_name}\n\n"
                    f"📢 **Следующее задание:**\n{new_url}\n\n"
                    f"💰 **Награда:** {settings.task_reward} {settings.currency_name}\n\n"
                    f"Нажмите «✅ Я выполнил» после подписки",
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
            else:
                await query.edit_message_text(
                    f"✅ **Задание выполнено!** ✅\n\n"
                    f"💰 Вы получили: {task_reward} {settings.currency_name}\n\n"
                    f"💰 Ваш баланс: {format_number(get_user_data(user_id)['mcoin'])} {settings.currency_name}"
                )
        else:
            # Задание не выполнено
            await query.edit_message_text(
                f"❌ **Вы ещё не подписались!** ❌\n\n"
                f"🔗 Пожалуйста, подпишитесь:\n{task_url}\n\n"
                f"**Инструкция:**\n"
                f"1. Нажмите на ссылку выше\n"
                f"2. Нажмите «Подписаться» или «Join»\n"
                f"3. Вернитесь и нажмите «✅ Я выполнил»\n\n"
                f"⏱️ У вас есть 3 минуты на выполнение",
                disable_web_page_preview=True
            )
            
            # Возвращаем кнопки
            keyboard = [
                [InlineKeyboardButton("✅ Я выполнил", callback_data=f"check_task_{task_url}")],
                [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_reply_markup(reply_markup)
            
    except Exception as e:
        logger.error(f"Ошибка в check_task_callback: {e}")
        await query.edit_message_text(f"❌ Ошибка при проверке: {e}\n\nПопробуйте еще раз.")

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
async def start(update: Update, context: CallbackContext):
    """Обработка команды /start"""
    user_id = update.effective_user.id
    
    # Проверка бана
    if user_id in db.bans:
        await update.message.reply_text("⛔ **Вы забанены!** ⛔\n\nВы не можете пользоваться ботом.")
        return
    
    # Обработка реферальной ссылки
    if context.args and context.args[0].startswith("ref_"):
        referrer_id = int(context.args[0].replace("ref_", ""))
        if referrer_id != user_id and referrer_id not in db.bans:
            user_data = get_user_data(user_id)
            if not user_data.get("referrer"):
                user_data["referrer"] = referrer_id
                referrer_data = get_user_data(referrer_id)
                referrer_data["referrals"].append(user_id)
                
                # Начисляем бонус
                ref_reward = settings.referral_reward
                add_mcoins(referrer_id, ref_reward, "referral_bonus", "referral")
                db.save()
                
                try:
                    await context.bot.send_message(
                        referrer_id,
                        f"👥 **Новый реферал!** 👥\n\n"
                        f"{update.effective_user.first_name} присоединился по вашей ссылке!\n"
                        f"💰 Вы получили: {ref_reward} {settings.currency_name}\n"
                        f"📊 Всего рефералов: {len(referrer_data['referrals'])}"
                    )
                except Exception as e:
                    logger.error(f"Не удалось отправить сообщение рефереру: {e}")
    
    get_user_data(user_id)
    
    welcome_text = (
        f"👋 **Привет, {update.effective_user.first_name}!**\n\n"
        f"{settings.welcome_message}\n\n"
        f"💎 **{settings.bot_name}** - {settings.bot_description}\n\n"
        f"✨ **Что вы можете делать:**\n"
        f"• 📋 Выполнять задания и получать {settings.currency_name}\n"
        f"• 🎲 Играть в игры и удваивать свой капитал\n"
        f"• 📦 Открывать кейсы с ценными призами\n"
        f"• 🎰 Участвовать в лотерее и выигрывать джекпот\n"
        f"• 👥 Приглашать друзей и получать бонусы\n\n"
        f"💰 Ваш баланс: 0 {settings.currency_name}\n\n"
        f"🌟 **Удачного заработка!** 🌟"
    )
    
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard(user_id))

async def balance_handler(update: Update, context: CallbackContext):
    """Показывает баланс с подробной статистикой"""
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    level, exp_needed, current_exp = get_level_info(user_id)
    
    # Создаем прогресс-бар для уровня
    progress = int((current_exp / exp_needed) * 20)
    progress_bar = "█" * progress + "░" * (20 - progress)
    
    keyboard = [
        [InlineKeyboardButton("📊 Детальная статистика", callback_data="detailed_stats")],
        [InlineKeyboardButton("🏆 Достижения", callback_data="achievements")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"💰 **Ваш баланс** 💰\n\n"
        f"🎮 {settings.currency_name}: `{format_number(user['mcoin'])}`\n\n"
        f"📊 **Прогресс:**\n"
        f"🏅 Уровень: {level}\n"
        f"📈 Опыт: {progress_bar} {current_exp}/{exp_needed}\n\n"
        f"📈 **Статистика:**\n"
        f"💰 Всего заработано: {format_number(user['total_earned'])}\n"
        f"💸 Выведено: {format_number(user['total_withdrawn'])}\n"
        f"🎲 Из игр: {format_number(user['game_earned'])}\n"
        f"📦 Из кейсов: {format_number(user['case_earned'])}\n"
        f"👥 С рефералов: {format_number(user['referral_earned'])}\n"
        f"✅ С заданий: {format_number(user['task_earned'])}\n\n"
        f"📅 В боте: {(datetime.now() - datetime.fromisoformat(user['join_date'])).days} дней",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def handle_text(update: Update, context: CallbackContext):
    """Обработка текстовых сообщений от кнопок"""
    user_id = update.effective_user.id
    text = update.message.text
    
    # Проверка бана
    if user_id in db.bans:
        await update.message.reply_text("⛔ **Вы забанены!** ⛔")
        return
    
    # Обновляем время последней активности
    if user_id in db.users:
        db.users[user_id]["last_seen"] = datetime.now().isoformat()
        db.users[user_id]["username"] = update.effective_user.username
        db.users[user_id]["first_name"] = update.effective_user.first_name
        db.users[user_id]["last_name"] = update.effective_user.last_name or ""
        db.save()
    
    # Обработка команд с кнопок
    if text == f"💰 {settings.currency_name}":
        await balance_handler(update, context)
    elif text == "📋 Задания":
        await tasks_mode(update, context)
    elif text == "🎲 Игры":
        await games_menu(update, context)
    elif text == "📦 Кейсы":
        await cases_menu(update, context)
    elif text == "🎰 Лотерея":
        await lottery_menu(update, context)
    elif text == "👥 Рефералы":
        await referrals_menu(update, context)
    elif text == "🏆 Ежедневный бонус":
        await daily_bonus(update, context)
    elif text == "💸 Вывод средств":
        await withdraw_menu(update, context)
    elif text == "🎫 Промокоды":
        await promo_menu(update, context)
    elif text == "📊 Статистика":
        await stats_menu(update, context)
    elif text == "⚙️ Админ панель" and user_id in settings.admin_list:
        await admin_panel(update, context)
    else:
        await update.message.reply_text(
            "❓ **Неизвестная команда** ❓\n\n"
            "Используйте кнопки меню для навигации 👇",
            reply_markup=get_main_keyboard(user_id)
        )

async def games_menu(update: Update, context: CallbackContext):
    """Меню игр"""
    keyboard = [
        [InlineKeyboardButton("🎰 Казино", callback_data="game_casino")],
        [InlineKeyboardButton("🎲 Кости", callback_data="game_dice")],
        [InlineKeyboardButton("🎰 Слоты", callback_data="game_slots")],
        [InlineKeyboardButton("📊 Моя статистика в играх", callback_data="game_stats")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎮 **Игровой центр** 🎮\n\n"
        "Выберите игру:\n\n"
        "🎰 **Казино** - Шанс 45%, множитель до x3\n"
        "🎲 **Кости** - Сравнение суммы двух кубиков\n"
        "🎰 **Слоты** - Три барабана, джекпот x3\n\n"
        f"💰 Ваш баланс: {format_number(get_user_data(update.effective_user.id)['mcoin'])} {settings.currency_name}",
        reply_markup=reply_markup
    )

async def withdraw_menu(update: Update, context: CallbackContext):
    """Меню вывода средств"""
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    if user["mcoin"] < settings.min_withdraw:
        await update.message.reply_text(
            f"❌ **Недостаточно средств для вывода!** ❌\n\n"
            f"💰 Ваш баланс: {format_number(user['mcoin'])} {settings.currency_name}\n"
            f"💰 Минимальная сумма: {settings.min_withdraw} {settings.currency_name}\n\n"
            f"Выполняйте задания и играйте в игры, чтобы заработать больше!"
        )
        return
    
    keyboard = [
        [InlineKeyboardButton("💰 Запросить вывод", callback_data="request_withdraw")],
        [InlineKeyboardButton("📊 История выводов", callback_data="withdraw_history")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="withdraw_info")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"💸 **Вывод средств** 💸\n\n"
        f"💰 Доступно: {format_number(user['mcoin'])} {settings.currency_name}\n"
        f"📉 Минимальная сумма: {settings.min_withdraw} {settings.currency_name}\n"
        f"📈 Максимальная сумма: {settings.max_withdraw} {settings.currency_name}\n\n"
        f"💳 **Доступные способы:**\n"
        f"• QIWI\n"
        f"• Банковская карта\n"
        f"• Криптовалюта\n\n"
        f"⏱️ Время обработки: до 24 часов\n"
        f"💰 Комиссия: 0%\n\n"
        f"Нажмите «Запросить вывод» для создания заявки",
        reply_markup=reply_markup
    )

# ========== АДМИН ПАНЕЛЬ ==========
async def admin_panel(update: Update, context: CallbackContext):
    """Главное меню админ панели"""
    if update.effective_user.id not in settings.admin_list:
        await update.message.reply_text("⛔ У вас нет доступа к админ панели!")
        return
    
    keyboard = [
        [InlineKeyboardButton("💰 Настройка наград", callback_data="admin_rewards")],
        [InlineKeyboardButton("📦 Управление кейсами", callback_data="admin_cases")],
        [InlineKeyboardButton("🎰 Управление лотереей", callback_data="admin_lottery")],
        [InlineKeyboardButton("📢 Обязательные подписки", callback_data="admin_forcesub")],
        [InlineKeyboardButton("👥 Управление пользователями", callback_data="admin_users")],
        [InlineKeyboardButton("📊 Статистика бота", callback_data="admin_stats")],
        [InlineKeyboardButton("💸 Управление выводами", callback_data="admin_withdrawals")],
        [InlineKeyboardButton("📨 Рассылка", callback_data="admin_mailing")],
        [InlineKeyboardButton("🎫 Промокоды", callback_data="admin_promo")],
        [InlineKeyboardButton("⚙️ Настройки бота", callback_data="admin_settings")],
        [InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "⚙️ **Админ панель** ⚙️\n\n"
        "Добро пожаловать в панель управления ботом!\n\n"
        f"📊 **Быстрая статистика:**\n"
        f"👥 Пользователей: {db.global_stats['total_users']}\n"
        f"💰 Всего заработано: {format_number(db.global_stats['total_mcoins_earned'])} {settings.currency_name}\n"
        f"✅ Заданий выполнено: {db.global_stats['total_tasks_completed']}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

# ========== ЗАПУСК БОТА ==========
def main():
    """Запуск бота"""
    # Загружаем данные
    db.load()
    settings.load()
    
    # Создаем приложение
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("casino", game_casino))
    app.add_handler(CommandHandler("dice", game_dice))
    app.add_handler(CommandHandler("slots", game_slots))
    app.add_handler(CommandHandler("promo", use_promo))
    app.add_handler(CommandHandler("tasks", tasks_mode))
    
    # Регистрируем callback обработчики
    app.add_handler(CallbackQueryHandler(case_info_callback, pattern="^case_info_"))
    app.add_handler(CallbackQueryHandler(lambda u,c: open_case(u,c, u.callback_query.data.replace("open_case_", "")), pattern="^open_case_"))
    app.add_handler(CallbackQueryHandler(lambda u,c: buy_ticket(u,c, 1), pattern="^buy_ticket$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: buy_ticket(u,c, 10), pattern="^buy_10_tickets$"))
    app.add_handler(CallbackQueryHandler(draw_lottery, pattern="^draw_lottery$"))
    app.add_handler(CallbackQueryHandler(check_task_callback, pattern="^check_task_"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(my_referrals, pattern="^my_referrals$"))
    app.add_handler(CallbackQueryHandler(referrals_menu, pattern="^referrals_menu$"))
    app.add_handler(CallbackQueryHandler(cases_menu, pattern="^cases_back$"))
    app.add_handler(CallbackQueryHandler(games_menu, pattern="^games_back$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.message.delete(), pattern="^back_to_main$"))
    
    # Обработчик текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Запускаем бота
    print("🚀 Бот запущен...")
    print(f"📊 Администратор: {ADMIN_ID}")
    print(f"💎 Название: {settings.bot_name}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()