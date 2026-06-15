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
ADMIN_ID = 5356400377

# Состояния для ConversationHandler
(SET_REWARD, SET_PRICE, SET_NAME, SET_DESCRIPTION, SET_WIN_CHANCE, 
 SET_ADMIN_ID, SET_CHANNEL, SET_PROMO, SET_WITHDRAW, SET_CHEQUE_AMOUNT,
 MAILING_TEXT, SET_TAX, SET_LIMIT, SET_REF_BONUS, EDIT_ITEM,
 SET_CASE_ITEM_NAME, SET_CASE_ITEM_CHANCE, SET_CASE_ITEM_REWARD,
 DELETE_CASE_NAME, EDIT_CASE_PRICE, CREATE_PROMO_CODE, CREATE_PROMO_REWARD,
 CREATE_PROMO_EXPIRY, CREATE_PROMO_USES, PROCESS_WITHDRAW, BAN_USER,
 UNBAN_USER, ADD_MCOINS_ADMIN, SET_FORCE_SUB) = range(30)

# Типы игр
class GameType(Enum):
    CASINO = "casino"
    DICE = "dice"
    SLOTS = "slots"

# Файлы для хранения данных
DATA_FILE = "bot_data.json"
SETTINGS_FILE = "settings.json"
PROMO_FILE = "promo_codes.json"
CHEQUES_FILE = "cheques.json"

# ========== СТРУКТУРА ДАННЫХ ==========
class BotDatabase:
    def __init__(self):
        self.users: Dict[int, Dict] = {}
        self.cases: Dict[str, Dict] = {}
        self.lottery: Dict = {
            "active": True,
            "tickets": {},
            "prize": 1000,
            "end_time": (datetime.now() + timedelta(days=7)).isoformat(),
            "winner": None,
            "current_round": 1,
            "history": [],
            "auto_draw": True,
            "draw_hour": 20,
            "draw_minute": 0
        }
        self.promo_codes: Dict[str, Dict] = {}
        self.cheques: Dict[str, Dict] = {}  # cheque_code: {amount, creator, created_by, used_by, created_at, expires_at}
        self.withdraw_requests: Dict[int, Dict] = {}
        self.game_history: Dict[int, List[Dict]] = {}
        self.bans: Dict[int, Dict] = {}
        self.mailing_jobs: List[Dict] = []
        self.global_stats: Dict = {
            "total_users": 0,
            "total_mcoins_earned": 0,
            "total_withdrawn": 0,
            "total_tasks_completed": 0,
            "total_games_played": 0,
            "total_cases_opened": 0,
            "total_lottery_tickets": 0,
            "total_promos_used": 0,
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
            with open(PROMO_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.promo_codes, f, ensure_ascii=False, indent=2)
            with open(CHEQUES_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.cheques, f, ensure_ascii=False, indent=2)
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
                    self.lottery = data.get("lottery", {"active": True, "tickets": {}, "prize": 1000, "current_round": 1})
                    self.promo_codes = data.get("promo_codes", {})
                    self.cheques = data.get("cheques", {})
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
        self.ref_levels = [5, 10, 15, 20, 25]
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
        self.cheque_prefix = "MC"
        self.cheque_expiry_days = 7
        
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
def generate_cheque_code() -> str:
    """Генерирует уникальный код для чека"""
    import string
    chars = string.ascii_uppercase + string.digits
    code = settings.cheque_prefix + ''.join(random.choices(chars, k=12))
    while code in db.cheques:
        code = settings.cheque_prefix + ''.join(random.choices(chars, k=12))
    return code

def get_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Создает главную клавиатуру с динамическими кнопками"""
    keyboard = [
        [KeyboardButton(f"💰 {settings.currency_name}"), KeyboardButton("📋 Задания")],
        [KeyboardButton("🎲 Игры"), KeyboardButton("📦 Кейсы")],
        [KeyboardButton("🎰 Лотерея"), KeyboardButton("👥 Рефералы")],
        [KeyboardButton("🏆 Ежедневный бонус"), KeyboardButton("💸 Вывод средств")],
        [KeyboardButton("🎫 Промокоды"), KeyboardButton("📊 Статистика")],
        [KeyboardButton("🎟️ Чек"), KeyboardButton("📢 Информация")]
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
            "lottery_earned": 0,
            "cheques_used": [],
            "cheques_created": []
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
    
    if source == "task":
        user["task_earned"] += amount
        db.global_stats["total_tasks_completed"] += 1
    elif source == "referral":
        user["referral_earned"] += amount
    elif source == "game":
        user["game_earned"] += amount
        db.global_stats["total_games_played"] += 1
    elif source == "case":
        user["case_earned"] += amount
        db.global_stats["total_cases_opened"] += 1
    elif source == "lottery":
        user["lottery_earned"] += amount
    elif source == "cheque":
        user["cheques_used"].append({"code": reason, "amount": amount, "date": datetime.now().isoformat()})
    
    db.global_stats["total_mcoins_earned"] += amount
    update_user_level(user_id)
    db.save()
    
    logger.info(f"Пользователю {user_id} начислено {amount} MCoin. Причина: {reason}")
    return True

def remove_mcoins(user_id: int, amount: int, reason: str = "") -> bool:
    """Снимает MCoin, возвращает True если достаточно средств"""
    if amount <= 0:
        return False
    
    user = get_user_data(user_id)
    if user["mcoin"] >= amount:
        user["mcoin"] -= amount
        db.save()
        logger.info(f"С пользователя {user_id} списано {amount} MCoin. Причина: {reason}")
        return True
    return False

def update_user_level(user_id: int) -> bool:
    """Обновляет уровень пользователя"""
    user = get_user_data(user_id)
    total_earned = user["total_earned"]
    
    level = 1
    exp_needed = 100
    exp = total_earned
    
    while exp >= exp_needed and level < 100:
        exp -= exp_needed
        level += 1
        exp_needed = int(exp_needed * 1.5)
    
    if level > user["level"]:
        user["level"] = level
        return True
    return False

def format_number(num: int) -> str:
    """Форматирует число с разделителями"""
    return f"{num:,}".replace(",", ".")

# ========== ПРОВЕРКА ПОДПИСОК ==========
async def check_force_subs(user_id: int, bot) -> Tuple[bool, List[str]]:
    """Проверяет обязательные подписки пользователя"""
    not_subscribed = []
    
    for channel in settings.force_sub_channels:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                not_subscribed.append(channel)
        except Exception as e:
            logger.error(f"Ошибка проверки канала {channel}: {e}")
            not_subscribed.append(channel)
    
    for group in settings.force_sub_groups:
        try:
            member = await bot.get_chat_member(chat_id=group, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                not_subscribed.append(group)
        except Exception as e:
            logger.error(f"Ошибка проверки группы {group}: {e}")
    
    return len(not_subscribed) == 0, not_subscribed

# ========== BOTOHUB ИНТЕГРАЦИЯ ==========
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
    """Игра Казино"""
    user_id = update.effective_user.id
    
    if not settings.games_enabled:
        await update.message.reply_text("🎮 Игры временно недоступны!")
        return
    
    args = context.args
    
    if not args:
        await update.message.reply_text(
            f"🎰 **Казино** 🎰\n\n"
            f"Использование: /casino <сумма>\n"
            f"Минимальная ставка: {settings.min_game_bet} {settings.currency_name}\n"
            f"Максимальная ставка: {settings.max_game_bet} {settings.currency_name}\n\n"
            f"Шанс выигрыша: 45%\nМаксимальный выигрыш: x3 от ставки"
        )
        return
    
    try:
        bet = int(args[0])
        if bet < settings.min_game_bet or bet > settings.max_game_bet:
            await update.message.reply_text(f"❌ Ставка должна быть от {settings.min_game_bet} до {settings.max_game_bet}")
            return
    except:
        await update.message.reply_text("❌ Введите корректную сумму!")
        return
    
    user = get_user_data(user_id)
    
    if not remove_mcoins(user_id, bet, f"casino_bet"):
        await update.message.reply_text(f"❌ Недостаточно средств! У вас {user['mcoin']} {settings.currency_name}")
        return
    
    user["games_played"] += 1
    
    # Сохраняем историю игры
    win_chance = random.random()
    win = win_chance < settings.casino_win_rate
    
    if win:
        multiplier = random.uniform(1.5, 3.0)
        win_amount = int(bet * multiplier)
        add_mcoins(user_id, win_amount, f"casino_win", "game")
        user["games_won"] += 1
        
        # Сохраняем историю
        if user_id not in db.game_history:
            db.game_history[user_id] = []
        db.game_history[user_id].append({
            "game": "casino",
            "bet": bet,
            "win": win_amount,
            "multiplier": multiplier,
            "date": datetime.now().isoformat()
        })
        
        await update.message.reply_text(
            f"🎉 **ПОБЕДА!** 🎉\n\n"
            f"🎲 Ставка: {bet} {settings.currency_name}\n"
            f"🎁 Выигрыш: {win_amount} {settings.currency_name}\n"
            f"📈 Множитель: x{multiplier:.1f}\n\n"
            f"💰 Баланс: {format_number(user['mcoin'])} {settings.currency_name}"
        )
    else:
        db.game_history[user_id].append({
            "game": "casino",
            "bet": bet,
            "win": 0,
            "date": datetime.now().isoformat()
        })
        
        await update.message.reply_text(
            f"😢 **ПРОИГРЫШ** 😢\n\n"
            f"🎲 Ставка: {bet} {settings.currency_name}\n"
            f"💸 Проигрыш: {bet} {settings.currency_name}\n\n"
            f"💰 Баланс: {format_number(user['mcoin'])} {settings.currency_name}"
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
            f"🎲 **Кости** 🎲\n\n"
            f"Использование: /dice <сумма>\n"
            f"Минимальная ставка: {settings.min_game_bet} {settings.currency_name}\n"
            f"Максимальная ставка: {settings.max_game_bet} {settings.currency_name}"
        )
        return
    
    try:
        bet = int(args[0])
        if bet < settings.min_game_bet or bet > settings.max_game_bet:
            await update.message.reply_text(f"❌ Ставка должна быть от {settings.min_game_bet} до {settings.max_game_bet}")
            return
    except:
        await update.message.reply_text("❌ Введите корректную сумму!")
        return
    
    user = get_user_data(user_id)
    
    if not remove_mcoins(user_id, bet, f"dice_bet"):
        await update.message.reply_text(f"❌ Недостаточно средств! У вас {user['mcoin']} {settings.currency_name}")
        return
    
    user["games_played"] += 1
    
    user_dice = random.randint(1, 6)
    bot_dice = random.randint(1, 6)
    
    message = await update.message.reply_text(f"🎲 Бросаем кости...\nВаш бросок: ?\nБросок бота: ?")
    await asyncio.sleep(1)
    
    if user_dice > bot_dice:
        win_amount = bet * 2
        add_mcoins(user_id, win_amount, f"dice_win", "game")
        user["games_won"] += 1
        
        await message.edit_text(
            f"🎲 **ВЫ ПОБЕДИЛИ!** 🎲\n\n"
            f"Ваш бросок: {user_dice}\n"
            f"Бросок бота: {bot_dice}\n"
            f"🎁 Выигрыш: {win_amount} {settings.currency_name}\n\n"
            f"💰 Баланс: {format_number(user['mcoin'])} {settings.currency_name}"
        )
    elif user_dice < bot_dice:
        await message.edit_text(
            f"😢 **ВЫ ПРОИГРАЛИ** 😢\n\n"
            f"Ваш бросок: {user_dice}\n"
            f"Бросок бота: {bot_dice}\n"
            f"💸 Проигрыш: {bet} {settings.currency_name}\n\n"
            f"💰 Баланс: {format_number(user['mcoin'])} {settings.currency_name}"
        )
    else:
        add_mcoins(user_id, bet, f"dice_draw", "game")
        await message.edit_text(
            f"🤝 **НИЧЬЯ** 🤝\n\n"
            f"Ваш бросок: {user_dice}\n"
            f"Бросок бота: {bot_dice}\n"
            f"🔄 Ставка возвращена!\n\n"
            f"💰 Баланс: {format_number(user['mcoin'])} {settings.currency_name}"
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
            f"🎰 **Слоты** 🎰\n\n"
            f"Использование: /slots <сумма>\n"
            f"Минимальная ставка: {settings.min_game_bet} {settings.currency_name}\n"
            f"Максимальная ставка: {settings.max_game_bet} {settings.currency_name}"
        )
        return
    
    try:
        bet = int(args[0])
        if bet < settings.min_game_bet or bet > settings.max_game_bet:
            await update.message.reply_text(f"❌ Ставка должна быть от {settings.min_game_bet} до {settings.max_game_bet}")
            return
    except:
        await update.message.reply_text("❌ Введите корректную сумму!")
        return
    
    user = get_user_data(user_id)
    
    if not remove_mcoins(user_id, bet, f"slots_bet"):
        await update.message.reply_text(f"❌ Недостаточно средств! У вас {user['mcoin']} {settings.currency_name}")
        return
    
    user["games_played"] += 1
    
    symbols = ["🍒", "🍊", "🍋", "🍉", "🔔", "💎"]
    result = [random.choice(symbols) for _ in range(3)]
    
    message = await update.message.reply_text(f"🎰 Крутим слоты...\n[ ? | ? | ? ]")
    await asyncio.sleep(1.5)
    
    if result[0] == result[1] == result[2]:
        multiplier = 3.0
        win_amount = int(bet * multiplier)
        add_mcoins(user_id, win_amount, f"slots_win", "game")
        user["games_won"] += 1
        
        await message.edit_text(
            f"🎰 **ДЖЕКПОТ!** 🎰\n\n"
            f"[ {result[0]} | {result[1]} | {result[2]} ]\n\n"
            f"🎁 Выигрыш: {win_amount} {settings.currency_name}\n"
            f"💰 Баланс: {format_number(user['mcoin'])} {settings.currency_name}"
        )
    elif result.count(result[0]) == 2 or result.count(result[1]) == 2:
        add_mcoins(user_id, bet, f"slots_two", "game")
        await message.edit_text(
            f"🎰 **СЛОТЫ** 🎰\n\n"
            f"[ {result[0]} | {result[1]} | {result[2]} ]\n\n"
            f"😐 2 одинаковых символа!\n"
            f"🔄 Ставка возвращена!\n\n"
            f"💰 Баланс: {format_number(user['mcoin'])} {settings.currency_name}"
        )
    else:
        await message.edit_text(
            f"🎰 **СЛОТЫ** 🎰\n\n"
            f"[ {result[0]} | {result[1]} | {result[2]} ]\n\n"
            f"😢 **ПРОИГРЫШ**\n"
            f"💸 Проигрыш: {bet} {settings.currency_name}\n\n"
            f"💰 Баланс: {format_number(user['mcoin'])} {settings.currency_name}"
        )
    
    db.save()

# ========== КЕЙСЫ ==========
async def cases_menu(update: Update, context: CallbackContext):
    """Меню кейсов"""
    if not settings.cases_enabled:
        await update.message.reply_text("📦 Кейсы временно недоступны!")
        return
    
    keyboard = []
    for case_name, case_data in db.cases.items():
        keyboard.append([InlineKeyboardButton(
            f"📦 {case_name} - {case_data['price']} {settings.currency_name}", 
            callback_data=f"case_open_{case_name}"
        )])
    
    if not keyboard:
        await update.message.reply_text("📦 Кейсы временно недоступны! Зайдите позже.")
        return
    
    keyboard.append([InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🎁 **Магазин кейсов** 🎁\n\n"
        f"Выберите кейс для открытия:\n"
        f"💰 Ваш баланс: {format_number(get_user_data(update.effective_user.id)['mcoin'])} {settings.currency_name}",
        reply_markup=reply_markup
    )

async def case_open_callback(update: Update, context: CallbackContext):
    """Открытие кейса"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    case_name = query.data.replace("case_open_", "")
    
    if case_name not in db.cases:
        await query.message.edit_text("❌ Кейс не найден!")
        return
    
    case_data = db.cases[case_name]
    price = case_data["price"]
    
    user = get_user_data(user_id)
    
    if not remove_mcoins(user_id, price, f"case_open_{case_name}"):
        await query.answer(f"Недостаточно средств! Нужно {price} {settings.currency_name}", show_alert=True)
        return
    
    # Выбираем предмет
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
    
    reward = selected_item["reward"]
    add_mcoins(user_id, reward, f"case_{case_name}", "case")
    user["cases_opened"] += 1
    
    user["inventory"].append({
        "name": selected_item['name'],
        "obtained": datetime.now().isoformat(),
        "from_case": case_name
    })
    
    await query.message.edit_text(
        f"🎉 **Вы открыли кейс '{case_name}'** 🎉\n\n"
        f"📦 Вам выпало: **{selected_item['name']}**\n"
        f"🎁 Награда: {reward} {settings.currency_name}\n\n"
        f"💰 Ваш баланс: {format_number(user['mcoin'])} {settings.currency_name}"
    )
    
    db.save()

# ========== ЛОТЕРЕЯ ==========
async def lottery_menu(update: Update, context: CallbackContext):
    """Меню лотереи"""
    if not settings.lottery_enabled:
        await update.message.reply_text("🎰 Лотерея временно недоступна!")
        return
    
    user_id = update.effective_user.id
    tickets = db.lottery["tickets"].get(user_id, 0)
    total_tickets = sum(db.lottery["tickets"].values())
    
    keyboard = [
        [InlineKeyboardButton("🎫 Купить билет (10 MCoin)", callback_data="lottery_buy")],
        [InlineKeyboardButton("🎫 Купить 10 билетов (95 MCoin)", callback_data="lottery_buy_10")],
        [InlineKeyboardButton("📊 Мои билеты", callback_data="lottery_my_tickets")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    
    if user_id in settings.admin_list:
        keyboard.insert(0, [InlineKeyboardButton("🎲 Провести розыгрыш", callback_data="lottery_draw")])
        keyboard.insert(1, [InlineKeyboardButton("⚙️ Настройки лотереи", callback_data="lottery_settings")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    end_time = datetime.fromisoformat(db.lottery["end_time"]) if db.lottery["end_time"] else datetime.now() + timedelta(days=7)
    time_left = end_time - datetime.now()
    days_left = time_left.days
    
    await update.message.reply_text(
        f"🎰 **Лотерея** 🎰\n\n"
        f"💰 Призовой фонд: {format_number(db.lottery['prize'])} {settings.currency_name}\n"
        f"🎫 Ваших билетов: {tickets}\n"
        f"🎫 Всего билетов: {total_tickets}\n"
        f"⏱️ До розыгрыша: {days_left} дней\n\n"
        f"🎟️ Цена билета: 10 {settings.currency_name}\n"
        f"🏆 Победитель получает 80% призового фонда!\n\n"
        f"🍀 Удачи!",
        reply_markup=reply_markup
    )

async def lottery_buy_callback(update: Update, context: CallbackContext, count: int = 1):
    """Покупка билетов лотереи"""
    query = update.callback_query
    user_id = query.from_user.id
    
    price = 10 * count
    if count == 10:
        price = 95
    
    if not remove_mcoins(user_id, price, f"lottery_tickets_{count}"):
        await query.answer(f"Недостаточно средств! Нужно {price} {settings.currency_name}", show_alert=True)
        return
    
    if user_id not in db.lottery["tickets"]:
        db.lottery["tickets"][user_id] = 0
    db.lottery["tickets"][user_id] += count
    db.lottery["prize"] += int(price * 0.8)
    db.global_stats["total_lottery_tickets"] += count
    
    db.save()
    
    await query.answer(f"Куплено {count} билетов! Удачи!", show_alert=True)
    await query.message.edit_text(
        f"✅ **Куплено {count} билетов!**\n\n"
        f"💰 Стоимость: {price} {settings.currency_name}\n"
        f"🎫 Ваших билетов: {db.lottery['tickets'][user_id]}\n"
        f"💰 Призовой фонд: {format_number(db.lottery['prize'])} {settings.currency_name}"
    )

async def lottery_draw_callback(update: Update, context: CallbackContext):
    """Проведение розыгрыша лотереи"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in settings.admin_list:
        await query.answer("Только для администратора!", show_alert=True)
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
    
    prize = int(db.lottery["prize"] * 0.8)
    add_mcoins(winner_id, prize, "lottery_win", "lottery")
    
    # Сохраняем историю
    winner_data = get_user_data(winner_id)
    db.lottery["history"].append({
        "round": db.lottery["current_round"],
        "winner_id": winner_id,
        "winner_name": winner_data.get("first_name", f"User_{winner_id}"),
        "prize": prize,
        "total_tickets": total_tickets,
        "date": datetime.now().isoformat()
    })
    
    # Сбрасываем лотерею
    db.lottery["tickets"] = {}
    db.lottery["prize"] = int(db.lottery["prize"] * 0.1)
    db.lottery["current_round"] += 1
    db.lottery["end_time"] = (datetime.now() + timedelta(days=7)).isoformat()
    
    db.save()
    
    await query.message.edit_text(
        f"🎉 **РОЗЫГРЫШ ЛОТЕРЕИ!** 🎉\n\n"
        f"🏆 Победитель: [пользователь](tg://user?id={winner_id})\n"
        f"💰 Приз: {format_number(prize)} {settings.currency_name}\n"
        f"🎫 Всего билетов: {total_tickets}\n\n"
        f"✨ Следующий розыгрыш через 7 дней!",
        parse_mode="Markdown"
    )
    
    # Поздравляем победителя
    try:
        await context.bot.send_message(
            winner_id,
            f"🎉 **ПОЗДРАВЛЯЕМ!** 🎉\n\n"
            f"Вы выиграли в лотерее!\n"
            f"💰 Ваш выигрыш: {format_number(prize)} {settings.currency_name}"
        )
    except Exception as e:
        logger.error(f"Не удалось поздравить победителя: {e}")

async def lottery_my_tickets_callback(update: Update, context: CallbackContext):
    """Показывает билеты пользователя"""
    query = update.callback_query
    user_id = query.from_user.id
    
    tickets = db.lottery["tickets"].get(user_id, 0)
    total_tickets = sum(db.lottery["tickets"].values())
    win_chance = (tickets / total_tickets * 100) if total_tickets > 0 else 0
    
    await query.message.edit_text(
        f"📊 **Ваши билеты в лотерее**\n\n"
        f"🎫 Ваших билетов: {tickets}\n"
        f"🎫 Всего билетов: {total_tickets}\n"
        f"📈 Шанс победы: {win_chance:.2f}%\n\n"
        f"💰 Призовой фонд: {format_number(db.lottery['prize'])} {settings.currency_name}\n\n"
        f"Купите больше билетов для увеличения шанса!"
    )

async def lottery_settings_callback(update: Update, context: CallbackContext):
    """Настройки лотереи для админа"""
    query = update.callback_query
    
    if query.from_user.id not in settings.admin_list:
        await query.answer("Только для администратора!", show_alert=True)
        return
    
    keyboard = [
        [InlineKeyboardButton(f"{'✅' if db.lottery['active'] else '❌'} Активна", callback_data="lottery_toggle_active")],
        [InlineKeyboardButton(f"🕐 Часовой пояс: {db.lottery['draw_hour']}:00", callback_data="lottery_set_hour")],
        [InlineKeyboardButton(f"💰 Призовой фонд: {db.lottery['prize']}", callback_data="lottery_set_prize")],
        [InlineKeyboardButton("📊 История розыгрышей", callback_data="lottery_history")],
        [InlineKeyboardButton("🔙 Назад", callback_data="lottery_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"⚙️ **Настройки лотереи**\n\n"
        f"Статус: {'Активна' if db.lottery['active'] else 'Неактивна'}\n"
        f"Время розыгрыша: {db.lottery['draw_hour']}:{db.lottery['draw_minute']:02d}\n"
        f"Призовой фонд: {format_number(db.lottery['prize'])} {settings.currency_name}\n"
        f"Раунд: {db.lottery['current_round']}",
        reply_markup=reply_markup
    )

# ========== ЧЕКИ ==========
async def cheque_menu(update: Update, context: CallbackContext):
    """Меню чеков"""
    keyboard = [
        [InlineKeyboardButton("🎟️ Создать чек", callback_data="cheque_create")],
        [InlineKeyboardButton("💰 Активировать чек", callback_data="cheque_activate")],
        [InlineKeyboardButton("📊 Мои чеки", callback_data="cheque_my")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🎟️ **Система чеков** 🎟️\n\n"
        f"**Создать чек:** За определенную сумму вы создаете чек, который можно передать другому пользователю\n"
        f"**Активировать чек:** Введите код чека для получения MCoin\n\n"
        f"💡 Чеки действительны {settings.cheque_expiry_days} дней\n"
        f"💰 Комиссия за создание чека: 5%",
        reply_markup=reply_markup
    )

async def cheque_create_callback(update: Update, context: CallbackContext):
    """Создание чека"""
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        f"🎟️ **Создание чека**\n\n"
        f"Введите сумму чека (от 10 до 100000 {settings.currency_name}):\n\n"
        f"Комиссия: 5%\n"
        f"Пример: 1000"
    )
    return SET_CHEQUE_AMOUNT

async def cheque_create_amount(update: Update, context: CallbackContext):
    """Обработка суммы чека"""
    try:
        amount = int(update.message.text)
        if amount < 10 or amount > 100000:
            await update.message.reply_text("❌ Сумма должна быть от 10 до 100000!")
            return SET_CHEQUE_AMOUNT
    except:
        await update.message.reply_text("❌ Введите корректное число!")
        return SET_CHEQUE_AMOUNT
    
    user_id = update.effective_user.id
    commission = int(amount * 0.05)
    total_cost = amount + commission
    
    user = get_user_data(user_id)
    
    if not remove_mcoins(user_id, total_cost, f"cheque_create_{amount}"):
        await update.message.reply_text(f"❌ Недостаточно средств! Нужно {total_cost} {settings.currency_name}")
        return ConversationHandler.END
    
    code = generate_cheque_code()
    expires_at = datetime.now() + timedelta(days=settings.cheque_expiry_days)
    
    db.cheques[code] = {
        "amount": amount,
        "created_by": user_id,
        "created_at": datetime.now().isoformat(),
        "expires_at": expires_at.isoformat(),
        "used_by": None,
        "used_at": None,
        "active": True
    }
    
    if "cheques_created" not in user:
        user["cheques_created"] = []
    user["cheques_created"].append({"code": code, "amount": amount, "date": datetime.now().isoformat()})
    
    db.save()
    
    await update.message.reply_text(
        f"✅ **Чек создан!**\n\n"
        f"💰 Сумма: {amount} {settings.currency_name}\n"
        f"💸 Комиссия: {commission} {settings.currency_name}\n"
        f"📝 Код: `{code}`\n"
        f"⏱️ Действителен до: {expires_at.strftime('%d.%m.%Y')}\n\n"
        f"Передайте код получателю!",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def cheque_activate_callback(update: Update, context: CallbackContext):
    """Активация чека"""
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        f"🎟️ **Активация чека**\n\n"
        f"Введите код чека:\n\n"
        f"Пример: `{settings.cheque_prefix}ABC123XYZ`",
        parse_mode="Markdown"
    )
    return SET_CHEQUE_AMOUNT

async def cheque_activate_code(update: Update, context: CallbackContext):
    """Обработка кода чека"""
    code = update.message.text.strip().upper()
    user_id = update.effective_user.id
    
    if code not in db.cheques:
        await update.message.reply_text("❌ Неверный код чека!")
        return ConversationHandler.END
    
    cheque = db.cheques[code]
    
    if not cheque.get("active", True):
        await update.message.reply_text("❌ Чек уже использован!")
        return ConversationHandler.END
    
    expires_at = datetime.fromisoformat(cheque["expires_at"])
    if datetime.now() > expires_at:
        await update.message.reply_text("❌ Срок действия чека истек!")
        return ConversationHandler.END
    
    if cheque["created_by"] == user_id:
        await update.message.reply_text("❌ Нельзя активировать свой собственный чек!")
        return ConversationHandler.END
    
    amount = cheque["amount"]
    add_mcoins(user_id, amount, f"cheque_{code}", "cheque")
    
    cheque["active"] = False
    cheque["used_by"] = user_id
    cheque["used_at"] = datetime.now().isoformat()
    
    user = get_user_data(user_id)
    if "cheques_used" not in user:
        user["cheques_used"] = []
    user["cheques_used"].append({"code": code, "amount": amount, "date": datetime.now().isoformat()})
    
    db.save()
    
    await update.message.reply_text(
        f"✅ **Чек активирован!**\n\n"
        f"💰 Вы получили: {amount} {settings.currency_name}\n"
        f"📝 Код: {code}\n\n"
        f"💰 Ваш баланс: {format_number(user['mcoin'])} {settings.currency_name}"
    )
    return ConversationHandler.END

# ========== ПРОМОКОДЫ ==========
async def promo_menu(update: Update, context: CallbackContext):
    """Меню промокодов"""
    await update.message.reply_text(
        f"🎫 **Промокоды** 🎫\n\n"
        f"Использование: /promo <код>\n\n"
        f"Пример: /promo WELCOME100\n\n"
        f"Активные промокоды можно получить в наших соцсетях!"
    )

async def use_promo(update: Update, context: CallbackContext):
    """Использование промокода"""
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text("Использование: /promo <код>")
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
    
    reward = promo.get("reward", 0)
    add_mcoins(user_id, reward, f"promo_{code}", "other")
    
    if "used_by" not in promo:
        promo["used_by"] = []
    promo["used_by"].append(user_id)
    
    db.global_stats["total_promos_used"] += 1
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
            next_bonus = last_date + timedelta(days=1)
            time_left = next_bonus - now
            hours = time_left.seconds // 3600
            minutes = (time_left.seconds % 3600) // 60
            
            await update.message.reply_text(
                f"⏰ **Вы уже получали бонус сегодня!**\n\n"
                f"Следующий бонус через: {hours}ч {minutes}мин\n"
                f"📊 Текущая серия: {user['daily_streak']} дней"
            )
            return
        elif days_diff == 1:
            user["daily_streak"] += 1
        else:
            user["daily_streak"] = 1
    
    base_reward = settings.daily_reward
    streak_multiplier = 1 + (user["daily_streak"] * 0.05)
    reward = int(base_reward * min(streak_multiplier, 3.0))
    
    add_mcoins(user_id, reward, "daily_bonus", "other")
    user["daily_last"] = now.isoformat()
    
    extra_bonus = 0
    if user["daily_streak"] == 7:
        extra_bonus = 50
        add_mcoins(user_id, extra_bonus, "streak_7", "other")
    elif user["daily_streak"] == 30:
        extra_bonus = 250
        add_mcoins(user_id, extra_bonus, "streak_30", "other")
    elif user["daily_streak"] == 100:
        extra_bonus = 1000
        add_mcoins(user_id, extra_bonus, "streak_100", "other")
    
    db.save()
    
    extra_text = f"\n🎁 Бонус за серию: +{extra_bonus} {settings.currency_name}" if extra_bonus else ""
    
    await update.message.reply_text(
        f"🎁 **Ежедневный бонус!** 🎁\n\n"
        f"💰 Вы получили: {reward} {settings.currency_name}{extra_text}\n"
        f"📊 Серия: {user['daily_streak']} дней\n"
        f"📈 Множитель: x{streak_multiplier:.2f}\n\n"
        f"💰 Ваш баланс: {format_number(user['mcoin'])} {settings.currency_name}"
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
    
    ref_count = len(user["referrals"])
    current_level = 0
    
    for i, level in enumerate(settings.ref_levels):
        if ref_count >= level:
            current_level = i + 1
        else:
            break
    
    level_multiplier = settings.ref_multipliers[current_level] if current_level < len(settings.ref_multipliers) else 1.5
    
    keyboard = [
        [InlineKeyboardButton("📋 Список рефералов", callback_data="ref_list")],
        [InlineKeyboardButton("📊 Статистика", callback_data="ref_stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👥 **Реферальная программа** 👥\n\n"
        f"🏆 Ваш уровень: {current_level + 1}\n"
        f"📈 Множитель: x{level_multiplier}\n"
        f"👥 Рефералов: {ref_count}\n"
        f"💰 Заработано: {user['referral_earned']} {settings.currency_name}\n\n"
        f"🎁 Награда за реферала: {settings.referral_reward} {settings.currency_name}\n\n"
        f"🔗 Ваша ссылка:\n`{ref_link}`\n\n"
        f"Отправьте её друзьям!",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def ref_list_callback(update: Update, context: CallbackContext):
    """Список рефералов"""
    query = update.callback_query
    user_id = query.from_user.id
    user = get_user_data(user_id)
    
    if not user["referrals"]:
        await query.answer("У вас пока нет рефералов!", show_alert=True)
        return
    
    ref_list = []
    for i, ref_id in enumerate(user["referrals"][:20], 1):
        ref_user = db.users.get(ref_id, {})
        ref_name = ref_user.get("first_name", f"User_{ref_id}")
        ref_earned = ref_user.get("total_earned", 0)
        ref_list.append(f"{i}. {ref_name} - Заработал: {ref_earned} {settings.currency_name}")
    
    text = "📋 **Ваши рефералы:**\n\n" + "\n".join(ref_list)
    if len(user["referrals"]) > 20:
        text += f"\n\n... и еще {len(user['referrals']) - 20} рефералов"
    
    await query.message.edit_text(text, parse_mode="Markdown")

async def ref_stats_callback(update: Update, context: CallbackContext):
    """Статистика рефералов"""
    query = update.callback_query
    user_id = query.from_user.id
    user = get_user_data(user_id)
    
    total_earned = sum([db.users.get(ref_id, {}).get("total_earned", 0) for ref_id in user["referrals"]])
    active_refs = len([ref_id for ref_id in user["referrals"] if db.users.get(ref_id, {}).get("total_earned", 0) > 100])
    
    await query.message.edit_text(
        f"📊 **Статистика рефералов**\n\n"
        f"👥 Всего рефералов: {len(user['referrals'])}\n"
        f"⭐ Активных рефералов: {active_refs}\n"
        f"💰 Заработано рефералами: {format_number(total_earned)} {settings.currency_name}\n"
        f"🎁 Ваш доход: {user['referral_earned']} {settings.currency_name}"
    )

# ========== ВЫВОД СРЕДСТВ ==========
async def withdraw_menu(update: Update, context: CallbackContext):
    """Меню вывода средств"""
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    if user["mcoin"] < settings.min_withdraw:
        await update.message.reply_text(
            f"❌ **Недостаточно средств для вывода!**\n\n"
            f"💰 Ваш баланс: {format_number(user['mcoin'])} {settings.currency_name}\n"
            f"💰 Минимальная сумма: {settings.min_withdraw} {settings.currency_name}"
        )
        return
    
    keyboard = [
        [InlineKeyboardButton("💰 Создать заявку", callback_data="withdraw_request")],
        [InlineKeyboardButton("📊 Мои заявки", callback_data="withdraw_my")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="withdraw_info")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"💸 **Вывод средств** 💸\n\n"
        f"💰 Доступно: {format_number(user['mcoin'])} {settings.currency_name}\n"
        f"📉 Минимальная сумма: {settings.min_withdraw} {settings.currency_name}\n"
        f"📈 Максимальная сумма: {settings.max_withdraw} {settings.currency_name}\n\n"
        f"💳 Способы вывода: QIWI, Карта, Криптовалюта\n"
        f"⏱️ Время обработки: до 24 часов\n\n"
        f"Нажмите «Создать заявку»",
        reply_markup=reply_markup
    )

async def withdraw_request_callback(update: Update, context: CallbackContext):
    """Создание заявки на вывод"""
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        f"💸 **Создание заявки на вывод**\n\n"
        f"Введите сумму вывода (от {settings.min_withdraw} до {settings.max_withdraw} {settings.currency_name}):"
    )
    return SET_WITHDRAW

async def withdraw_amount_input(update: Update, context: CallbackContext):
    """Обработка суммы вывода"""
    try:
        amount = int(update.message.text)
        if amount < settings.min_withdraw or amount > settings.max_withdraw:
            await update.message.reply_text(f"❌ Сумма должна быть от {settings.min_withdraw} до {settings.max_withdraw}")
            return SET_WITHDRAW
    except:
        await update.message.reply_text("❌ Введите корректное число!")
        return SET_WITHDRAW
    
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    if user["mcoin"] < amount:
        await update.message.reply_text(f"❌ Недостаточно средств! У вас {user['mcoin']} {settings.currency_name}")
        return SET_WITHDRAW
    
    context.user_data["withdraw_amount"] = amount
    
    await update.message.reply_text(
        f"💰 Сумма: {amount} {settings.currency_name}\n\n"
        f"Введите реквизиты для вывода:\n"
        f"(QIWI кошелек, номер карты или адрес криптокошелька)"
    )
    return SET_NAME

async def withdraw_details_input(update: Update, context: CallbackContext):
    """Обработка реквизитов вывода"""
    details = update.message.text
    user_id = update.effective_user.id
    amount = context.user_data.get("withdraw_amount", 0)
    
    if amount <= 0:
        await update.message.reply_text("❌ Ошибка! Попробуйте заново.")
        return ConversationHandler.END
    
    # Создаем заявку
    withdraw_id = len(db.withdraw_requests) + 1
    db.withdraw_requests[withdraw_id] = {
        "user_id": user_id,
        "amount": amount,
        "details": details,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "processed_at": None,
        "admin_id": None
    }
    
    db.save()
    
    await update.message.reply_text(
        f"✅ **Заявка на вывод создана!**\n\n"
        f"💰 Сумма: {amount} {settings.currency_name}\n"
        f"🆔 Номер заявки: {withdraw_id}\n\n"
        f"⏱️ Ожидайте обработки (до 24 часов)\n"
        f"Статус заявки можно проверить в меню «Мои заявки»"
    )
    
    # Уведомляем админа
    for admin_id in settings.admin_list:
        try:
            await update.message.bot.send_message(
                admin_id,
                f"💸 **Новая заявка на вывод!**\n\n"
                f"🆔 Заявка: #{withdraw_id}\n"
                f"👤 Пользователь: [user](tg://user?id={user_id})\n"
                f"💰 Сумма: {amount} {settings.currency_name}\n"
                f"💳 Реквизиты: {details}\n\n"
                f"Для обработки используйте админ-панель",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить админа: {e}")
    
    return ConversationHandler.END

async def withdraw_my_callback(update: Update, context: CallbackContext):
    """Показывает заявки пользователя"""
    query = update.callback_query
    user_id = query.from_user.id
    
    user_requests = []
    for req_id, req in db.withdraw_requests.items():
        if req["user_id"] == user_id:
            status_emoji = {
                "pending": "⏳",
                "approved": "✅",
                "rejected": "❌",
                "completed": "💰"
            }.get(req["status"], "❓")
            
            user_requests.append(
                f"{status_emoji} #{req_id}: {req['amount']} {settings.currency_name} - {req['status']}"
            )
    
    if not user_requests:
        await query.message.edit_text("📊 У вас пока нет заявок на вывод")
        return
    
    text = "📊 **Ваши заявки на вывод:**\n\n" + "\n".join(user_requests[-10:])
    await query.message.edit_text(text, parse_mode="Markdown")

async def withdraw_info_callback(update: Update, context: CallbackContext):
    """Информация о выводе"""
    query = update.callback_query
    
    await query.message.edit_text(
        f"ℹ️ **Информация о выводе средств**\n\n"
        f"💸 **Как вывести средства:**\n"
        f"1. Создайте заявку в меню вывода\n"
        f"2. Укажите сумму и реквизиты\n"
        f"3. Дождитесь обработки (до 24 часов)\n\n"
        f"💰 **Комиссия:** 0%\n"
        f"⏱️ **Минимальная сумма:** {settings.min_withdraw} {settings.currency_name}\n"
        f"📈 **Максимальная сумма:** {settings.max_withdraw} {settings.currency_name}\n\n"
        f"💳 **Доступные способы:**\n"
        f"• QIWI кошелек\n"
        f"• Банковская карта\n"
        f"• Криптовалюта (USDT, BTC)\n\n"
        f"❓ По вопросам вывода обращайтесь к администратору"
    )

# ========== СТАТИСТИКА ==========
async def stats_menu(update: Update, context: CallbackContext):
    """Показывает статистику пользователя"""
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    level, exp_needed, current_exp = update_user_level_return(user_id)
    progress = int((current_exp / exp_needed) * 20) if exp_needed > 0 else 0
    progress_bar = "█" * progress + "░" * (20 - progress)
    
    achievements = []
    if user["total_earned"] >= 1000:
        achievements.append("🏆 1000 MCoin")
    if user["games_won"] >= 10:
        achievements.append("🎲 10 побед в играх")
    if user["cases_opened"] >= 50:
        achievements.append("📦 50 кейсов")
    if user["daily_streak"] >= 7:
        achievements.append("🔥 7-дневная серия")
    if len(user["referrals"]) >= 5:
        achievements.append("👥 5 рефералов")
    
    await update.message.reply_text(
        f"📊 **Ваша статистика** 📊\n\n"
        f"🏅 Уровень: {level}\n"
        f"📈 Прогресс: {progress_bar} {current_exp}/{exp_needed}\n\n"
        f"💰 Баланс: {format_number(user['mcoin'])} {settings.currency_name}\n"
        f"📈 Всего заработано: {format_number(user['total_earned'])} {settings.currency_name}\n"
        f"💸 Выведено: {format_number(user['total_withdrawn'])} {settings.currency_name}\n\n"
        f"🎮 Игр сыграно: {user['games_played']}\n"
        f"🏆 Побед: {user['games_won']}\n"
        f"📦 Кейсов открыто: {user['cases_opened']}\n"
        f"👥 Рефералов: {len(user['referrals'])}\n"
        f"🔥 Серия: {user['daily_streak']} дней\n\n"
        f"🏅 Достижения: {', '.join(achievements) if achievements else 'Нет'}\n"
        f"📅 В боте: {(datetime.now() - datetime.fromisoformat(user['join_date'])).days} дней",
        parse_mode="Markdown"
    )

def update_user_level_return(user_id: int) -> Tuple[int, int, int]:
    """Возвращает (уровень, опыт для след уровня, текущий опыт)"""
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

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
async def start(update: Update, context: CallbackContext):
    """Обработка команды /start"""
    user_id = update.effective_user.id
    
    if user_id in db.bans:
        await update.message.reply_text("⛔ **Вы забанены!** ⛔")
        return
    
    # Реферальная система
    if context.args and context.args[0].startswith("ref_"):
        referrer_id = int(context.args[0].replace("ref_", ""))
        if referrer_id != user_id and referrer_id not in db.bans:
            user_data = get_user_data(user_id)
            if not user_data.get("referrer"):
                user_data["referrer"] = referrer_id
                referrer_data = get_user_data(referrer_id)
                if user_id not in referrer_data["referrals"]:
                    referrer_data["referrals"].append(user_id)
                    
                    ref_reward = settings.referral_reward
                    add_mcoins(referrer_id, ref_reward, "referral_bonus", "referral")
                    db.save()
                    
                    try:
                        await context.bot.send_message(
                            referrer_id,
                            f"👥 **Новый реферал!**\n\n"
                            f"{update.effective_user.first_name} присоединился по вашей ссылке!\n"
                            f"💰 Вы получили: {ref_reward} {settings.currency_name}"
                        )
                    except Exception as e:
                        logger.error(f"Не удалось уведомить реферера: {e}")
    
    get_user_data(user_id)
    
    await update.message.reply_text(
        f"👋 **Привет, {update.effective_user.first_name}!**\n\n"
        f"{settings.welcome_message}\n\n"
        f"💎 **{settings.bot_name}**\n"
        f"{settings.bot_description}\n\n"
        f"✨ **Что вы можете делать:**\n"
        f"• 📋 Выполнять задания\n"
        f"• 🎲 Играть в игры\n"
        f"• 📦 Открывать кейсы\n"
        f"• 🎰 Участвовать в лотерее\n"
        f"• 👥 Приглашать друзей\n\n"
        f"🌟 **Удачного заработка!** 🌟",
        reply_markup=get_main_keyboard(user_id)
    )

async def balance_handler(update: Update, context: CallbackContext):
    """Показывает баланс"""
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    level, exp_needed, current_exp = update_user_level_return(user_id)
    progress = int((current_exp / exp_needed) * 20) if exp_needed > 0 else 0
    progress_bar = "█" * progress + "░" * (20 - progress)
    
    await update.message.reply_text(
        f"💰 **Ваш баланс** 💰\n\n"
        f"🎮 {settings.currency_name}: `{format_number(user['mcoin'])}`\n\n"
        f"📊 **Прогресс:**\n"
        f"🏅 Уровень: {level}\n"
        f"📈 Опыт: {progress_bar} {current_exp}/{exp_needed}\n\n"
        f"📈 **Заработано:**\n"
        f"💰 Всего: {format_number(user['total_earned'])}\n"
        f"💸 Выведено: {format_number(user['total_withdrawn'])}\n"
        f"🎲 Из игр: {format_number(user['game_earned'])}\n"
        f"📦 Из кейсов: {format_number(user['case_earned'])}\n"
        f"👥 С рефералов: {format_number(user['referral_earned'])}\n"
        f"✅ С заданий: {format_number(user['task_earned'])}\n\n"
        f"📅 В боте: {(datetime.now() - datetime.fromisoformat(user['join_date'])).days} дней",
        parse_mode="Markdown"
    )

async def info_handler(update: Update, context: CallbackContext):
    """Информация о боте"""
    uptime = datetime.now() - start_time if 'start_time' in globals() else timedelta(seconds=0)
    
    await update.message.reply_text(
        f"📢 **Информация о боте**\n\n"
        f"🤖 Название: {settings.bot_name}\n"
        f"📝 Описание: {settings.bot_description}\n\n"
        f"📊 **Статистика бота:**\n"
        f"👥 Пользователей: {db.global_stats['total_users']}\n"
        f"💰 Всего заработано: {format_number(db.global_stats['total_mcoins_earned'])} {settings.currency_name}\n"
        f"✅ Заданий выполнено: {db.global_stats['total_tasks_completed']}\n"
        f"🎮 Игр сыграно: {db.global_stats['total_games_played']}\n"
        f"📦 Кейсов открыто: {db.global_stats['total_cases_opened']}\n\n"
        f"⚡ **Команды:**\n"
        f"/start - Запуск бота\n"
        f"/casino <сумма> - Игра в казино\n"
        f"/dice <сумма> - Игра в кости\n"
        f"/slots <сумма> - Игровые слоты\n"
        f"/promo <код> - Активация промокода\n"
        f"/tasks - Выполнение заданий\n\n"
        f"👨‍💻 По всем вопросам: @admin"
    )

async def tasks_command(update: Update, context: CallbackContext):
    """Команда для выполнения заданий"""
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
        
        if completed:
            await msg.edit_text("✅ Вы выполнили все задания! Получите награду!")
            task_reward = settings.task_reward
            add_mcoins(user_id, task_reward, "all_tasks_completed", "task")
            await update.message.reply_text(
                f"🎉 **Поздравляем!** 🎉\n\n"
                f"Вы выполнили все доступные задания!\n"
                f"💰 Награда: {task_reward} {settings.currency_name}"
            )
            return
        
        if skip_flag or not tasks:
            await msg.edit_text("🎉 **Нет активных заданий!** Зайдите позже.")
            return
        
        task_url = tasks[0]
        context.user_data["current_task_url"] = task_url
        
        keyboard = [
            [InlineKeyboardButton("✅ Я выполнил", callback_data=f"task_check_{task_url}")],
            [InlineKeyboardButton("❌ Пропустить", callback_data="task_skip")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await msg.edit_text(
            f"📢 **Новое задание!** 📢\n\n"
            f"🔗 **Ссылка:** {task_url}\n\n"
            f"💰 **Награда:** {settings.task_reward} {settings.currency_name}\n\n"
            f"**Как выполнить:**\n"
            f"1. Перейдите по ссылке\n"
            f"2. Подпишитесь на канал\n"
            f"3. Нажмите «✅ Я выполнил»\n\n"
            f"⏱️ Время на выполнение: 3 минуты",
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logger.error(f"Ошибка в tasks_command: {e}")
        await msg.edit_text(f"❌ Ошибка: {e}\n\nПопробуйте позже.")

async def task_check_callback(update: Update, context: CallbackContext):
    """Проверка выполнения задания"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    task_url = query.data.replace("task_check_", "")
    
    await query.edit_message_text("🔍 Проверяем выполнение...")
    
    try:
        result = await call_botohub_api(user_id, is_task=True, skip=False)
        
        prev_success = result.get("prev_success", False)
        completed = result.get("completed", False)
        tasks = result.get("tasks", [])
        
        if prev_success:
            task_reward = settings.task_reward
            add_mcoins(user_id, task_reward, "task_completed", "task")
            
            if completed:
                await query.edit_message_text(
                    f"✅ **Задание выполнено!**\n\n"
                    f"💰 Вы получили: {task_reward} {settings.currency_name}\n"
                    f"🎉 **Поздравляем! Вы выполнили все задания!**\n\n"
                    f"💰 Ваш баланс: {format_number(get_user_data(user_id)['mcoin'])} {settings.currency_name}"
                )
            elif tasks:
                new_url = tasks[0]
                context.user_data["current_task_url"] = new_url
                
                keyboard = [
                    [InlineKeyboardButton("✅ Я выполнил", callback_data=f"task_check_{new_url}")],
                    [InlineKeyboardButton("❌ Пропустить", callback_data="task_skip")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"✅ **Задание выполнено!**\n\n"
                    f"💰 Вы получили: {task_reward} {settings.currency_name}\n\n"
                    f"📢 **Следующее задание:**\n{new_url}\n\n"
                    f"💰 **Награда:** {settings.task_reward} {settings.currency_name}",
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
            else:
                await query.edit_message_text(
                    f"✅ **Задание выполнено!**\n\n"
                    f"💰 Вы получили: {task_reward} {settings.currency_name}\n\n"
                    f"💰 Ваш баланс: {format_number(get_user_data(user_id)['mcoin'])} {settings.currency_name}"
                )
        else:
            await query.edit_message_text(
                f"❌ **Вы ещё не подписались!**\n\n"
                f"🔗 Пожалуйста, подпишитесь:\n{task_url}\n\n"
                f"После подписки нажмите «✅ Я выполнил»",
                disable_web_page_preview=True
            )
            
            keyboard = [
                [InlineKeyboardButton("✅ Я выполнил", callback_data=f"task_check_{task_url}")],
                [InlineKeyboardButton("❌ Пропустить", callback_data="task_skip")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_reply_markup(reply_markup)
            
    except Exception as e:
        logger.error(f"Ошибка в task_check_callback: {e}")
        await query.edit_message_text(f"❌ Ошибка: {e}")

async def task_skip_callback(update: Update, context: CallbackContext):
    """Пропуск задания"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    await query.edit_message_text("⏩ Пропускаем задание...")
    
    try:
        result = await call_botohub_api(user_id, is_task=True, skip=True)
        
        tasks = result.get("tasks", [])
        completed = result.get("completed", False)
        
        if completed:
            await query.edit_message_text("✅ Все задания выполнены!")
            return
        
        if tasks:
            new_url = tasks[0]
            context.user_data["current_task_url"] = new_url
            
            keyboard = [
                [InlineKeyboardButton("✅ Я выполнил", callback_data=f"task_check_{new_url}")],
                [InlineKeyboardButton("❌ Пропустить", callback_data="task_skip")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"⏩ Задание пропущено!\n\n"
                f"📢 **Новое задание:**\n{new_url}\n\n"
                f"💰 **Награда:** {settings.task_reward} {settings.currency_name}",
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
        else:
            await query.edit_message_text("🎉 Нет доступных заданий!")
            
    except Exception as e:
        logger.error(f"Ошибка в task_skip_callback: {e}")
        await query.edit_message_text(f"❌ Ошибка: {e}")

# ========== ОБРАБОТЧИКИ ТЕКСТА ==========
async def handle_text(update: Update, context: CallbackContext):
    """Обработка текстовых сообщений"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id in db.bans:
        await update.message.reply_text("⛔ **Вы забанены!**")
        return
    
    # Обновляем информацию о пользователе
    if user_id in db.users:
        db.users[user_id]["last_seen"] = datetime.now().isoformat()
        db.users[user_id]["username"] = update.effective_user.username
        db.users[user_id]["first_name"] = update.effective_user.first_name
        db.save()
    
    if text == f"💰 {settings.currency_name}":
        await balance_handler(update, context)
    elif text == "📋 Задания":
        await tasks_command(update, context)
    elif text == "🎲 Игры":
        await games_menu_callback(update, context)
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
    elif text == "🎟️ Чек":
        await cheque_menu(update, context)
    elif text == "📢 Информация":
        await info_handler(update, context)
    elif text == "⚙️ Админ панель" and user_id in settings.admin_list:
        await admin_panel(update, context)
    else:
        await update.message.reply_text(
            "❓ **Неизвестная команда**\n\nИспользуйте кнопки меню 👇",
            reply_markup=get_main_keyboard(user_id)
        )

async def games_menu_callback(update: Update, context: CallbackContext):
    """Меню игр"""
    keyboard = [
        [InlineKeyboardButton("🎰 Казино (/casino)", callback_data="game_casino_help")],
        [InlineKeyboardButton("🎲 Кости (/dice)", callback_data="game_dice_help")],
        [InlineKeyboardButton("🎰 Слоты (/slots)", callback_data="game_slots_help")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🎮 **Игровой центр** 🎮\n\n"
        f"Выберите игру:\n\n"
        f"🎰 **Казино** - Шанс 45%, множитель до x3\n"
        f"🎲 **Кости** - Сравнение двух кубиков\n"
        f"🎰 **Слоты** - Три барабана\n\n"
        f"💰 Ваш баланс: {format_number(get_user_data(update.effective_user.id)['mcoin'])} {settings.currency_name}",
        reply_markup=reply_markup
    )

# ========== АДМИН ПАНЕЛЬ ==========
async def admin_panel(update: Update, context: CallbackContext):
    """Главное меню админ панели"""
    if update.effective_user.id not in settings.admin_list:
        await update.message.reply_text("⛔ У вас нет доступа!")
        return
    
    keyboard = [
        [InlineKeyboardButton("💰 Настройка наград", callback_data="admin_rewards")],
        [InlineKeyboardButton("📦 Управление кейсами", callback_data="admin_cases")],
        [InlineKeyboardButton("🎰 Управление лотереей", callback_data="admin_lottery")],
        [InlineKeyboardButton("📢 Обязательные подписки", callback_data="admin_forcesub")],
        [InlineKeyboardButton("👥 Управление пользователями", callback_data="admin_users")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("💸 Управление выводами", callback_data="admin_withdrawals")],
        [InlineKeyboardButton("📨 Рассылка", callback_data="admin_mailing")],
        [InlineKeyboardButton("🎫 Промокоды", callback_data="admin_promo")],
        [InlineKeyboardButton("🎟️ Чеки", callback_data="admin_cheques")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="admin_settings")],
        [InlineKeyboardButton("🔙 Выход", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"⚙️ **Админ панель** ⚙️\n\n"
        f"📊 Статистика:\n"
        f"👥 Пользователей: {db.global_stats['total_users']}\n"
        f"💰 Всего заработано: {format_number(db.global_stats['total_mcoins_earned'])} {settings.currency_name}\n"
        f"✅ Заданий: {db.global_stats['total_tasks_completed']}\n"
        f"💸 Заявок на вывод: {len([r for r in db.withdraw_requests.values() if r['status'] == 'pending'])}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

async def admin_rewards_callback(update: Update, context: CallbackContext):
    """Настройка наград"""
    query = update.callback_query
    
    keyboard = [
        [InlineKeyboardButton(f"📋 Задание: {settings.task_reward}", callback_data="admin_set_task_reward")],
        [InlineKeyboardButton(f"👥 Реферал: {settings.referral_reward}", callback_data="admin_set_ref_reward")],
        [InlineKeyboardButton(f"🏆 Ежедневный: {settings.daily_reward}", callback_data="admin_set_daily_reward")],
        [InlineKeyboardButton(f"💸 Мин. вывод: {settings.min_withdraw}", callback_data="admin_set_min_withdraw")],
        [InlineKeyboardButton(f"📈 Макс. вывод: {settings.max_withdraw}", callback_data="admin_set_max_withdraw")],
        [InlineKeyboardButton(f"🎮 Мин. ставка: {settings.min_game_bet}", callback_data="admin_set_min_bet")],
        [InlineKeyboardButton(f"🎮 Макс. ставка: {settings.max_game_bet}", callback_data="admin_set_max_bet")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"💰 **Настройка наград**\n\n"
        f"📋 За задание: {settings.task_reward} {settings.currency_name}\n"
        f"👥 За реферала: {settings.referral_reward} {settings.currency_name}\n"
        f"🏆 Ежедневный бонус: {settings.daily_reward} {settings.currency_name}\n"
        f"💸 Минимальный вывод: {settings.min_withdraw} {settings.currency_name}\n"
        f"📈 Максимальный вывод: {settings.max_withdraw} {settings.currency_name}\n"
        f"🎮 Мин. ставка: {settings.min_game_bet} {settings.currency_name}\n"
        f"🎮 Макс. ставка: {settings.max_game_bet} {settings.currency_name}",
        reply_markup=reply_markup
    )

async def admin_cases_callback(update: Update, context: CallbackContext):
    """Управление кейсами"""
    query = update.callback_query
    
    cases_list = "\n".join([f"• {name}: {data['price']} MCoin" for name, data in db.cases.items()]) if db.cases else "Нет кейсов"
    
    keyboard = [
        [InlineKeyboardButton("📦 Создать кейс", callback_data="admin_create_case")],
        [InlineKeyboardButton("🗑 Удалить кейс", callback_data="admin_delete_case")],
        [InlineKeyboardButton("✏️ Редактировать кейс", callback_data="admin_edit_case")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"📦 **Управление кейсами**\n\n"
        f"**Существующие кейсы:**\n{cases_list}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

async def admin_create_case_start(update: Update, context: CallbackContext):
    """Начало создания кейса"""
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text("📦 **Создание кейса**\n\nВведите название кейса:")
    return SET_NAME

async def admin_create_case_name(update: Update, context: CallbackContext):
    """Получение названия кейса"""
    case_name = update.message.text
    context.user_data['case_name'] = case_name
    
    await update.message.reply_text(f"📦 Кейс '{case_name}'\n\nВведите цену кейса (в {settings.currency_name}):")
    return SET_PRICE

async def admin_create_case_price(update: Update, context: CallbackContext):
    """Получение цены кейса"""
    try:
        price = int(update.message.text)
        context.user_data['case_price'] = price
        
        await update.message.reply_text(
            f"💰 Цена: {price} {settings.currency_name}\n\n"
            f"Введите предметы в формате:\n"
            f"Название | шанс | награда\n"
            f"Пример: Легендарный | 10 | 500\n\n"
            f"Каждый предмет с новой строки. Для завершения отправьте 'готово':"
        )
        context.user_data['case_items'] = []
        return SET_DESCRIPTION
    except:
        await update.message.reply_text("❌ Введите корректное число!")
        return SET_PRICE

async def admin_create_case_items(update: Update, context: CallbackContext):
    """Добавление предметов в кейс"""
    text = update.message.text
    
    if text.lower() == 'готово':
        if len(context.user_data['case_items']) == 0:
            await update.message.reply_text("❌ Добавьте хотя бы один предмет!")
            return SET_DESCRIPTION
        
        db.cases[context.user_data['case_name']] = {
            "price": context.user_data['case_price'],
            "items": context.user_data['case_items']
        }
        db.save()
        
        await update.message.reply_text(
            f"✅ **Кейс создан!**\n\n"
            f"📦 Название: {context.user_data['case_name']}\n"
            f"💰 Цена: {context.user_data['case_price']} {settings.currency_name}\n"
            f"📦 Предметов: {len(context.user_data['case_items'])}"
        )
        return ConversationHandler.END
    
    try:
        parts = text.split('|')
        if len(parts) != 3:
            await update.message.reply_text("❌ Неверный формат! Пример: Название | 10 | 500")
            return SET_DESCRIPTION
        
        name = parts[0].strip()
        chance = float(parts[1].strip())
        reward = int(parts[2].strip())
        
        context.user_data['case_items'].append({
            "name": name,
            "chance": chance,
            "reward": reward
        })
        
        await update.message.reply_text(
            f"✅ Добавлен предмет: {name}\n"
            f"Шанс: {chance}%, Награда: {reward} {settings.currency_name}\n\n"
            f"Всего предметов: {len(context.user_data['case_items'])}\n"
            f"Добавьте следующий или отправьте 'готово':"
        )
        return SET_DESCRIPTION
    except:
        await update.message.reply_text("❌ Ошибка! Пример: Название | 10 | 500")
        return SET_DESCRIPTION

async def admin_users_callback(update: Update, context: CallbackContext):
    """Управление пользователями"""
    query = update.callback_query
    
    keyboard = [
        [InlineKeyboardButton("⛔ Забанить пользователя", callback_data="admin_ban")],
        [InlineKeyboardButton("✅ Разбанить пользователя", callback_data="admin_unban")],
        [InlineKeyboardButton("💰 Начислить MCoin", callback_data="admin_add_mcoins")],
        [InlineKeyboardButton("📊 Статистика пользователя", callback_data="admin_user_stats")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"👥 **Управление пользователями**\n\n"
        f"👥 Всего пользователей: {db.global_stats['total_users']}\n"
        f"⛔ Забанено: {len(db.bans)}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

async def admin_ban_start(update: Update, context: CallbackContext):
    """Начало бана пользователя"""
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        f"⛔ **Бан пользователя**\n\n"
        f"Введите ID пользователя для бана:\n"
        f"Пример: 123456789"
    )
    return BAN_USER

async def admin_ban_user(update: Update, context: CallbackContext):
    """Бан пользователя"""
    try:
        user_id = int(update.message.text)
        db.bans[user_id] = {
            "reason": "Нарушение правил",
            "banned_by": update.effective_user.id,
            "banned_at": datetime.now().isoformat()
        }
        db.save()
        
        await update.message.reply_text(f"✅ Пользователь {user_id} забанен!")
        
        try:
            await update.message.bot.send_message(
                user_id,
                "⛔ **Вы были забанены в боте!**\n\nПричина: Нарушение правил"
            )
        except:
            pass
        
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Неверный ID!")
        return BAN_USER

async def admin_add_mcoins_start(update: Update, context: CallbackContext):
    """Начало начисления MCoin"""
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        f"💰 **Начисление MCoin**\n\n"
        f"Введите ID пользователя и сумму через пробел:\n"
        f"Пример: 123456789 100"
    )
    return ADD_MCOINS_ADMIN

async def admin_add_mcoins(update: Update, context: CallbackContext):
    """Начисление MCoin админом"""
    try:
        parts = update.message.text.split()
        user_id = int(parts[0])
        amount = int(parts[1])
        
        add_mcoins(user_id, amount, f"admin_bonus", "other")
        
        await update.message.reply_text(f"✅ Пользователю {user_id} начислено {amount} {settings.currency_name}!")
        
        try:
            await update.message.bot.send_message(
                user_id,
                f"🎁 **Бонус от администратора!**\n\n"
                f"💰 Вам начислено: {amount} {settings.currency_name}"
            )
        except:
            pass
        
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Неверный формат! Пример: 123456789 100")
        return ADD_MCOINS_ADMIN

async def admin_withdrawals_callback(update: Update, context: CallbackContext):
    """Управление выводами"""
    query = update.callback_query
    
    pending_requests = []
    for req_id, req in db.withdraw_requests.items():
        if req["status"] == "pending":
            pending_requests.append(f"#{req_id} | {req['amount']} MCoin | user:{req['user_id']}")
    
    pending_text = "\n".join(pending_requests[-10:]) if pending_requests else "Нет заявок"
    
    keyboard = [
        [InlineKeyboardButton("✅ Одобрить заявку", callback_data="admin_approve_withdraw")],
        [InlineKeyboardButton("❌ Отклонить заявку", callback_data="admin_reject_withdraw")],
        [InlineKeyboardButton("📊 Список заявок", callback_data="admin_list_withdrawals")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"💸 **Управление выводами**\n\n"
        f"**Ожидающие заявки:**\n{pending_text}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

async def admin_approve_withdraw_start(update: Update, context: CallbackContext):
    """Начало одобрения вывода"""
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        f"✅ **Одобрение вывода**\n\n"
        f"Введите номер заявки для одобрения:\n"
        f"Пример: 1"
    )
    return PROCESS_WITHDRAW

async def admin_approve_withdraw(update: Update, context: CallbackContext):
    """Одобрение вывода"""
    try:
        req_id = int(update.message.text)
        
        if req_id not in db.withdraw_requests:
            await update.message.reply_text("❌ Заявка не найдена!")
            return PROCESS_WITHDRAW
        
        req = db.withdraw_requests[req_id]
        
        if req["status"] != "pending":
            await update.message.reply_text(f"❌ Заявка уже {req['status']}")
            return PROCESS_WITHDRAW
        
        # Обновляем статус
        req["status"] = "approved"
        req["processed_at"] = datetime.now().isoformat()
        req["admin_id"] = update.effective_user.id
        
        user = get_user_data(req["user_id"])
        user["total_withdrawn"] += req["amount"]
        
        db.save()
        
        await update.message.reply_text(f"✅ Заявка #{req_id} одобрена!")
        
        try:
            await update.message.bot.send_message(
                req["user_id"],
                f"✅ **Заявка на вывод одобрена!**\n\n"
                f"💰 Сумма: {req['amount']} {settings.currency_name}\n"
                f"💳 Реквизиты: {req['details']}\n\n"
                f"⏱️ Средства будут отправлены в ближайшее время"
            )
        except:
            pass
        
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Неверный номер заявки!")
        return PROCESS_WITHDRAW

async def admin_mailing_start(update: Update, context: CallbackContext):
    """Начало рассылки"""
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        f"📨 **Рассылка**\n\n"
        f"Введите текст сообщения для рассылки:\n"
        f"(можно использовать HTML разметку)"
    )
    return MAILING_TEXT

async def admin_mailing_send(update: Update, context: CallbackContext):
    """Отправка рассылки"""
    text = update.message.text
    user_id = update.effective_user.id
    
    await update.message.reply_text("⏳ Начинаю рассылку...")
    
    success = 0
    fail = 0
    
    for uid in db.users.keys():
        try:
            await update.message.bot.send_message(uid, text, parse_mode="HTML")
            success += 1
            await asyncio.sleep(0.05)  # Защита от блокировки
        except:
            fail += 1
    
    await update.message.reply_text(
        f"✅ **Рассылка завершена!**\n\n"
        f"📤 Отправлено: {success}\n"
        f"❌ Не доставлено: {fail}"
    )
    return ConversationHandler.END

async def admin_promo_callback(update: Update, context: CallbackContext):
    """Управление промокодами"""
    query = update.callback_query
    
    keyboard = [
        [InlineKeyboardButton("🎫 Создать промокод", callback_data="admin_create_promo")],
        [InlineKeyboardButton("🗑 Удалить промокод", callback_data="admin_delete_promo")],
        [InlineKeyboardButton("📋 Список промокодов", callback_data="admin_list_promo")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"🎫 **Управление промокодами**\n\n"
        f"Активных промокодов: {len(db.promo_codes)}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

async def admin_create_promo_start(update: Update, context: CallbackContext):
    """Создание промокода"""
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        f"🎫 **Создание промокода**\n\n"
        f"Введите название промокода (латиницей, без пробелов):"
    )
    return CREATE_PROMO_CODE

async def admin_create_promo_code(update: Update, context: CallbackContext):
    """Ввод кода промокода"""
    code = update.message.text.upper()
    context.user_data['promo_code'] = code
    
    await update.message.reply_text(f"🎫 Промокод: {code}\n\nВведите сумму награды (в {settings.currency_name}):")
    return CREATE_PROMO_REWARD

async def admin_create_promo_reward(update: Update, context: CallbackContext):
    """Ввод награды промокода"""
    try:
        reward = int(update.message.text)
        context.user_data['promo_reward'] = reward
        
        await update.message.reply_text(
            f"💰 Награда: {reward} {settings.currency_name}\n\n"
            f"Введите срок действия (в днях) или 0 для бессрочного:"
        )
        return CREATE_PROMO_EXPIRY
    except:
        await update.message.reply_text("❌ Введите число!")
        return CREATE_PROMO_REWARD

async def admin_create_promo_expiry(update: Update, context: CallbackContext):
    """Ввод срока действия"""
    try:
        days = int(update.message.text)
        
        expiry = None
        if days > 0:
            expiry = (datetime.now() + timedelta(days=days)).isoformat()
        
        db.promo_codes[context.user_data['promo_code']] = {
            "reward": context.user_data['promo_reward'],
            "expiry": expiry,
            "max_uses": 1,
            "used_by": []
        }
        db.save()
        
        await update.message.reply_text(
            f"✅ **Промокод создан!**\n\n"
            f"🎫 Код: {context.user_data['promo_code']}\n"
            f"💰 Награда: {context.user_data['promo_reward']} {settings.currency_name}\n"
            f"⏱️ Действителен: {'бессрочно' if days == 0 else f'{days} дней'}"
        )
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Введите число!")
        return CREATE_PROMO_EXPIRY

# ========== ЗАПУСК БОТА ==========
start_time = datetime.now()

async def auto_lottery_draw(context: CallbackContext):
    """Автоматический розыгрыш лотереи"""
    if not db.lottery.get("active", True):
        return
    
    now = datetime.now()
    end_time = datetime.fromisoformat(db.lottery["end_time"]) if db.lottery["end_time"] else None
    
    if end_time and now >= end_time:
        total_tickets = sum(db.lottery["tickets"].values())
        
        if total_tickets > 0:
            # Выбираем победителя
            winner_roll = random.randint(1, total_tickets)
            current = 0
            winner_id = None
            
            for uid, tickets in db.lottery["tickets"].items():
                current += tickets
                if current >= winner_roll:
                    winner_id = uid
                    break
            
            if winner_id:
                prize = int(db.lottery["prize"] * 0.8)
                add_mcoins(winner_id, prize, "lottery_auto_win", "lottery")
                
                # Сбрасываем лотерею
                db.lottery["tickets"] = {}
                db.lottery["prize"] = int(db.lottery["prize"] * 0.1)
                db.lottery["current_round"] += 1
                db.lottery["end_time"] = (datetime.now() + timedelta(days=7)).isoformat()
                db.save()
                
                # Уведомляем победителя
                try:
                    await context.bot.send_message(
                        winner_id,
                        f"🎉 **РОЗЫГРЫШ ЛОТЕРЕИ!** 🎉\n\n"
                        f"💰 Вы выиграли: {format_number(prize)} {settings.currency_name}"
                    )
                except:
                    pass
                
                logger.info(f"Автоматический розыгрыш лотереи: победитель {winner_id}, приз {prize}")

def main():
    """Запуск бота"""
    # Загружаем данные
    db.load()
    settings.load()
    
    # Создаем приложение
    app = Application.builder().token(BOT_TOKEN).build()
    
    # JobQueue для автоматической лотереи
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(auto_lottery_draw, interval=3600, first=10)
    
    # Регистрируем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("casino", game_casino))
    app.add_handler(CommandHandler("dice", game_dice))
    app.add_handler(CommandHandler("slots", game_slots))
    app.add_handler(CommandHandler("promo", use_promo))
    app.add_handler(CommandHandler("tasks", tasks_command))
    
    # Conversation handlers
    cheque_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cheque_create_callback, pattern="^cheque_create$")],
        states={
            SET_CHEQUE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, cheque_create_amount)],
        },
        fallbacks=[]
    )
    
    cheque_activate_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cheque_activate_callback, pattern="^cheque_activate$")],
        states={
            SET_CHEQUE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, cheque_activate_code)],
        },
        fallbacks=[]
    )
    
    withdraw_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(withdraw_request_callback, pattern="^withdraw_request$")],
        states={
            SET_WITHDRAW: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount_input)],
            SET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_details_input)],
        },
        fallbacks=[]
    )
    
    case_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_create_case_start, pattern="^admin_create_case$")],
        states={
            SET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_create_case_name)],
            SET_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_create_case_price)],
            SET_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_create_case_items)],
        },
        fallbacks=[]
    )
    
    ban_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_ban_start, pattern="^admin_ban$")],
        states={
            BAN_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_ban_user)],
        },
        fallbacks=[]
    )
    
    add_mcoins_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_mcoins_start, pattern="^admin_add_mcoins$")],
        states={
            ADD_MCOINS_ADMIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_mcoins)],
        },
        fallbacks=[]
    )
    
    approve_withdraw_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_approve_withdraw_start, pattern="^admin_approve_withdraw$")],
        states={
            PROCESS_WITHDRAW: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_approve_withdraw)],
        },
        fallbacks=[]
    )
    
    mailing_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_mailing_start, pattern="^admin_mailing$")],
        states={
            MAILING_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_mailing_send)],
        },
        fallbacks=[]
    )
    
    promo_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_create_promo_start, pattern="^admin_create_promo$")],
        states={
            CREATE_PROMO_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_create_promo_code)],
            CREATE_PROMO_REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_create_promo_reward)],
            CREATE_PROMO_EXPIRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_create_promo_expiry)],
        },
        fallbacks=[]
    )
    
    # Добавляем Conversation handlers
    app.add_handler(cheque_conv)
    app.add_handler(cheque_activate_conv)
    app.add_handler(withdraw_conv)
    app.add_handler(case_conv)
    app.add_handler(ban_conv)
    app.add_handler(add_mcoins_conv)
    app.add_handler(approve_withdraw_conv)
    app.add_handler(mailing_conv)
    app.add_handler(promo_conv)
    
    # Callback handlers
    app.add_handler(CallbackQueryHandler(case_open_callback, pattern="^case_open_"))
    app.add_handler(CallbackQueryHandler(lottery_buy_callback, pattern="^lottery_buy$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: lottery_buy_callback(u,c,10), pattern="^lottery_buy_10$"))
    app.add_handler(CallbackQueryHandler(lottery_draw_callback, pattern="^lottery_draw$"))
    app.add_handler(CallbackQueryHandler(lottery_my_tickets_callback, pattern="^lottery_my_tickets$"))
    app.add_handler(CallbackQueryHandler(lottery_settings_callback, pattern="^lottery_settings$"))
    app.add_handler(CallbackQueryHandler(task_check_callback, pattern="^task_check_"))
    app.add_handler(CallbackQueryHandler(task_skip_callback, pattern="^task_skip$"))
    app.add_handler(CallbackQueryHandler(ref_list_callback, pattern="^ref_list$"))
    app.add_handler(CallbackQueryHandler(ref_stats_callback, pattern="^ref_stats$"))
    app.add_handler(CallbackQueryHandler(withdraw_my_callback, pattern="^withdraw_my$"))
    app.add_handler(CallbackQueryHandler(withdraw_info_callback, pattern="^withdraw_info$"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_rewards_callback, pattern="^admin_rewards$"))
    app.add_handler(CallbackQueryHandler(admin_cases_callback, pattern="^admin_cases$"))
    app.add_handler(CallbackQueryHandler(admin_users_callback, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(admin_withdrawals_callback, pattern="^admin_withdrawals$"))
    app.add_handler(CallbackQueryHandler(admin_promo_callback, pattern="^admin_promo$"))
    app.add_handler(CallbackQueryHandler(games_menu_callback, pattern="^game_casino_help$"))
    app.add_handler(CallbackQueryHandler(games_menu_callback, pattern="^game_dice_help$"))
    app.add_handler(CallbackQueryHandler(games_menu_callback, pattern="^game_slots_help$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.message.delete(), pattern="^back_to_main$"))
    
    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Запускаем бота
    print("🚀 Бот запущен!")
    print(f"📊 Администратор: {ADMIN_ID}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()