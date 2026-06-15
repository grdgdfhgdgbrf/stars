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
BOT_TOKEN = "ВАШ_ТОКЕН_БОТА"  # Замените на ваш токен
BOTOHUB_TOKEN = "ВАШ_ТОКЕН_BOTOHUB"  # Замените на ваш токен
BOTOHUB_API_URL = "https://botohub.me/get-tasks"
ADMIN_ID = 5356400377

# Состояния для ConversationHandler
(SET_REWARD, SET_PRICE, SET_NAME, SET_DESCRIPTION, SET_WIN_CHANCE, 
 SET_ADMIN_ID, SET_CHANNEL, SET_PROMO, SET_WITHDRAW, SET_CHEQUE_AMOUNT,
 MAILING_TEXT, SET_TAX, SET_LIMIT, SET_REF_BONUS, EDIT_ITEM,
 SET_CHEQUE_CODE, SET_WITHDRAW_ADDRESS, SET_LOTTERY_TIME, SET_CASE_ITEM) = range(20)

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
            "last_draw": None
        }
        self.promo_codes: Dict[str, Dict] = {}
        self.cheques: Dict[str, Dict] = {}  # cheque_code: {amount, creator, created_by, used_by, created_at}
        self.withdraw_requests: Dict[int, Dict] = {}
        self.game_history: Dict[int, List[Dict]] = {}
        self.bans: Dict[int, Dict] = {}
        self.achievements: Dict[int, List[str]] = {}
        self.global_stats: Dict = {
            "total_users": 0,
            "total_mcoins_earned": 0,
            "total_withdrawn": 0,
            "total_tasks_completed": 0,
            "total_cheques_created": 0,
            "total_cheques_activated": 0
        }
        self.pending_tasks: Dict[int, Dict] = {}  # user_id: {task_url, timestamp}
        
    def save(self):
        data = {
            "users": self.users,
            "cases": self.cases,
            "lottery": self.lottery,
            "promo_codes": self.promo_codes,
            "cheques": self.cheques,
            "withdraw_requests": self.withdraw_requests,
            "game_history": self.game_history,
            "bans": self.bans,
            "achievements": self.achievements,
            "global_stats": self.global_stats,
            "pending_tasks": self.pending_tasks
        }
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("Данные сохранены")
        except Exception as e:
            logger.error(f"Ошибка сохранения данных: {e}")
    
    def load(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.users = {int(k): v for k, v in data.get("users", {}).items()}
                    self.cases = data.get("cases", {})
                    self.lottery = data.get("lottery", {"active": True, "tickets": {}, "prize": 1000, "current_round": 1, "history": []})
                    self.promo_codes = data.get("promo_codes", {})
                    self.cheques = data.get("cheques", {})
                    self.withdraw_requests = {int(k): v for k, v in data.get("withdraw_requests", {}).items()}
                    self.game_history = {int(k): v for k, v in data.get("game_history", {}).items()}
                    self.bans = {int(k): v for k, v in data.get("bans", {}).items()}
                    self.achievements = {int(k): v for k, v in data.get("achievements", {}).items()}
                    self.global_stats = data.get("global_stats", self.global_stats)
                    self.pending_tasks = {int(k): v for k, v in data.get("pending_tasks", {}).items()}
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
        self.force_sub_channels = ["@example_channel"]  # Замените на реальные
        self.force_sub_groups = []
        self.welcome_message = "Добро пожаловать в бот! 🎉"
        self.referral_program = True
        self.games_enabled = True
        self.cases_enabled = True
        self.lottery_enabled = True
        self.daily_limit = 1000
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
        self.lottery_draw_hour = 20
        self.lottery_draw_minute = 0
        self.auto_lottery = True
        self.cheque_fee = 0.05  # 5% комиссия за создание чека
        
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

db = BotDatabase()
settings = BotSettings()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(f"💰 {settings.currency_name}"), KeyboardButton("📋 Задания")],
        [KeyboardButton("🎲 Игры"), KeyboardButton("📦 Кейсы")],
        [KeyboardButton("🎰 Лотерея"), KeyboardButton("👥 Рефералы")],
        [KeyboardButton("🏆 Ежедневный бонус"), KeyboardButton("💸 Вывод средств")],
        [KeyboardButton("🎫 Промокоды"), KeyboardButton("📊 Статистика")],
        [KeyboardButton("🎫 Чеки"), KeyboardButton("🎁 Инвентарь")]
    ]
    
    if user_id in settings.admin_list:
        keyboard.append([KeyboardButton("⚙️ Админ панель")])
    
    if user_id in db.bans:
        return ReplyKeyboardMarkup([["ℹ️ Я в бане"]], resize_keyboard=True)
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_user_data(user_id: int) -> Dict:
    if user_id not in db.users:
        db.users[user_id] = {
            "mcoin": 100,  # Стартовый бонус
            "tasks_completed": [],
            "inventory": [],
            "referrals": [],
            "referrer": None,
            "daily_last": None,
            "total_earned": 100,
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
            "daily_streak": 0,
            "last_streak_date": None,
            "referral_earned": 0,
            "task_earned": 0,
            "game_earned": 0,
            "case_earned": 0,
            "lottery_earned": 0,
            "cheques_used": []
        }
        db.global_stats["total_users"] += 1
        db.save()
    return db.users[user_id]

def add_mcoins(user_id: int, amount: int, reason: str = "", source: str = "other") -> bool:
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
    elif source == "case":
        user["case_earned"] += amount
    elif source == "lottery":
        user["lottery_earned"] += amount
    
    db.global_stats["total_mcoins_earned"] += amount
    update_user_level(user_id)
    check_achievements(user_id)
    db.save()
    logger.info(f"Пользователю {user_id} начислено {amount} MCoin. Причина: {reason}")
    return True

def remove_mcoins(user_id: int, amount: int, reason: str = "") -> bool:
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
        add_mcoins(user_id, level * 10, f"level_up_{level}", "other")
        return True
    return False

def check_achievements(user_id: int):
    user = get_user_data(user_id)
    if user_id not in db.achievements:
        db.achievements[user_id] = []
    
    achievements_list = db.achievements[user_id]
    
    # Проверка достижений
    if user["total_earned"] >= 1000 and "earn_1000" not in achievements_list:
        achievements_list.append("earn_1000")
        add_mcoins(user_id, 100, "achievement_earn_1000", "other")
    elif user["total_earned"] >= 5000 and "earn_5000" not in achievements_list:
        achievements_list.append("earn_5000")
        add_mcoins(user_id, 500, "achievement_earn_5000", "other")
    
    if user["games_won"] >= 10 and "games_10" not in achievements_list:
        achievements_list.append("games_10")
        add_mcoins(user_id, 50, "achievement_games_10", "other")
    
    if user["cases_opened"] >= 50 and "cases_50" not in achievements_list:
        achievements_list.append("cases_50")
        add_mcoins(user_id, 200, "achievement_cases_50", "other")

def format_number(num: int) -> str:
    return f"{num:,}".replace(",", ".")

def generate_cheque_code() -> str:
    import string
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))

# ========== ПРОВЕРКА ПОДПИСОК ==========
async def check_force_subs(user_id: int, bot) -> Tuple[bool, List[str]]:
    """Проверяет обязательные подписки пользователя"""
    not_subscribed = []
    
    # Проверяем каналы
    for channel in settings.force_sub_channels:
        channel_username = channel.replace("@", "")
        try:
            member = await bot.get_chat_member(chat_id=f"@{channel_username}", user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                not_subscribed.append(f"https://t.me/{channel_username}")
        except Exception as e:
            logger.error(f"Ошибка проверки канала {channel}: {e}")
            not_subscribed.append(f"канал {channel}")
    
    # Проверяем группы
    for group in settings.force_sub_groups:
        try:
            member = await bot.get_chat_member(chat_id=group, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                not_subscribed.append(f"группа {group}")
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
            f"Шанс выигрыша: 45%\n"
            f"Максимальный выигрыш: x3 от ставки"
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
    
    if not remove_mcoins(user_id, bet, f"casino_bet_{bet}"):
        await update.message.reply_text(f"❌ Недостаточно средств! У вас {user['mcoin']} {settings.currency_name}")
        return
    
    user["games_played"] += 1
    
    win_chance = random.random()
    
    if win_chance < settings.casino_win_rate:
        multiplier = random.uniform(1.5, 3.0)
        win_amount = int(bet * multiplier)
        add_mcoins(user_id, win_amount, f"casino_win_{bet}", "game")
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
            f"Ставка: {bet} {settings.currency_name}\n"
            f"Выигрыш: {win_amount} {settings.currency_name}\n"
            f"Множитель: x{multiplier:.1f}\n\n"
            f"💰 Баланс: {format_number(user['mcoin'])} {settings.currency_name}"
        )
    else:
        await update.message.reply_text(
            f"😢 **ПРОИГРЫШ** 😢\n\n"
            f"Ставка: {bet} {settings.currency_name}\n"
            f"💰 Баланс: {format_number(user['mcoin'])} {settings.currency_name}"
        )
    
    db.save()

async def game_dice(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not settings.games_enabled:
        await update.message.reply_text("🎮 Игры временно недоступны!")
        return
    
    args = context.args
    
    if not args:
        await update.message.reply_text(
            f"🎲 **Кости** 🎲\n\n"
            f"Использование: /dice <сумма>\n"
            f"Минимальная ставка: {settings.min_game_bet} {settings.currency_name}"
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
    
    if not remove_mcoins(user_id, bet, f"dice_bet_{bet}"):
        await update.message.reply_text(f"❌ Недостаточно средств!")
        return
    
    user["games_played"] += 1
    
    user_dice = random.randint(1, 6)
    bot_dice = random.randint(1, 6)
    
    if user_dice > bot_dice:
        win_amount = bet * 2
        add_mcoins(user_id, win_amount, f"dice_win_{bet}", "game")
        user["games_won"] += 1
        
        await update.message.reply_text(
            f"🎲 **ВЫ ПОБЕДИЛИ!** 🎲\n\n"
            f"Ваш бросок: {user_dice}\n"
            f"Бросок бота: {bot_dice}\n"
            f"Выигрыш: {win_amount} {settings.currency_name}\n"
            f"💰 Баланс: {format_number(user['mcoin'])} {settings.currency_name}"
        )
    elif user_dice < bot_dice:
        await update.message.reply_text(
            f"😢 **ВЫ ПРОИГРАЛИ** 😢\n\n"
            f"Ваш бросок: {user_dice}\n"
            f"Бросок бота: {bot_dice}\n"
            f"💰 Баланс: {format_number(user['mcoin'])} {settings.currency_name}"
        )
    else:
        add_mcoins(user_id, bet, f"dice_draw_{bet}", "game")
        await update.message.reply_text(
            f"🤝 **НИЧЬЯ** 🤝\n\n"
            f"Ваш бросок: {user_dice}\n"
            f"Бросок бота: {bot_dice}\n"
            f"Ставка возвращена!\n"
            f"💰 Баланс: {format_number(user['mcoin'])} {settings.currency_name}"
        )
    
    db.save()

async def game_slots(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not settings.games_enabled:
        await update.message.reply_text("🎮 Игры временно недоступны!")
        return
    
    args = context.args
    
    if not args:
        await update.message.reply_text(
            f"🎰 **Слоты** 🎰\n\n"
            f"Использование: /slots <сумма>\n"
            f"Минимальная ставка: {settings.min_game_bet} {settings.currency_name}"
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
    
    if not remove_mcoins(user_id, bet, f"slots_bet_{bet}"):
        await update.message.reply_text(f"❌ Недостаточно средств!")
        return
    
    user["games_played"] += 1
    
    symbols = ["🍒", "🍊", "🍋", "🍉", "🔔", "💎"]
    result = [random.choice(symbols) for _ in range(3)]
    
    if result[0] == result[1] == result[2]:
        multiplier = {"🍒": 1.5, "🍊": 1.5, "🍋": 1.5, "🍉": 2.0, "🔔": 2.5, "💎": 3.0}[result[0]]
        win_amount = int(bet * multiplier)
        add_mcoins(user_id, win_amount, f"slots_win_{bet}", "game")
        user["games_won"] += 1
        
        await update.message.reply_text(
            f"🎰 **ДЖЕКПОТ!** 🎰\n\n"
            f"[ {result[0]} | {result[1]} | {result[2]} ]\n"
            f"Выигрыш: {win_amount} {settings.currency_name}\n"
            f"Множитель: x{multiplier}\n"
            f"💰 Баланс: {format_number(user['mcoin'])} {settings.currency_name}"
        )
    else:
        await update.message.reply_text(
            f"🎰 **СЛОТЫ** 🎰\n\n"
            f"[ {result[0]} | {result[1]} | {result[2]} ]\n"
            f"😢 ПРОИГРЫШ\n"
            f"💰 Баланс: {format_number(user['mcoin'])} {settings.currency_name}"
        )
    
    db.save()

# ========== КЕЙСЫ ==========
async def cases_menu(update: Update, context: CallbackContext):
    if not settings.cases_enabled:
        await update.message.reply_text("📦 Кейсы временно недоступны!")
        return
    
    keyboard = []
    for case_name, case_data in db.cases.items():
        keyboard.append([InlineKeyboardButton(
            f"📦 {case_name} - {case_data['price']} {settings.currency_name}", 
            callback_data=f"case_info_{case_name}"
        )])
    
    if not keyboard:
        await update.message.reply_text("📦 Кейсы временно недоступны!")
        return
    
    keyboard.append([InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    user = get_user_data(update.effective_user.id)
    await update.message.reply_text(
        f"🎁 **Магазин кейсов** 🎁\n\n"
        f"💰 Ваш баланс: {format_number(user['mcoin'])} {settings.currency_name}",
        reply_markup=reply_markup
    )

async def case_info_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    case_name = query.data.replace("case_info_", "")
    
    if case_name not in db.cases:
        await query.message.edit_text("❌ Кейс не найден!")
        return
    
    case_data = db.cases[case_name]
    
    items_list = []
    for i, item in enumerate(case_data["items"], 1):
        items_list.append(f"{i}. {item['name']} - {item['chance']}% - {item['reward']} {settings.currency_name}")
    
    keyboard = [
        [InlineKeyboardButton("🎲 Открыть кейс", callback_data=f"open_case_{case_name}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="cases_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"📦 **Кейс: {case_name}** 📦\n\n"
        f"💰 Цена: {case_data['price']} {settings.currency_name}\n\n"
        f"**Возможные предметы:**\n" + "\n".join(items_list),
        reply_markup=reply_markup
    )

async def open_case(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    case_name = query.data.replace("open_case_", "")
    
    if case_name not in db.cases:
        await query.message.edit_text("❌ Кейс не найден!")
        return
    
    case_data = db.cases[case_name]
    user = get_user_data(user_id)
    
    if not remove_mcoins(user_id, case_data["price"], f"open_case_{case_name}"):
        await query.answer(f"Недостаточно {settings.currency_name}!", show_alert=True)
        return
    
    # Выбор предмета
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
    add_mcoins(user_id, reward, f"case_{case_name}_{selected_item['name']}", "case")
    user["cases_opened"] += 1
    
    # Добавляем в инвентарь
    user["inventory"].append({
        "name": selected_item['name'],
        "from_case": case_name,
        "date": datetime.now().isoformat()
    })
    
    await query.message.edit_text(
        f"🎉 **Вы открыли кейс '{case_name}'** 🎉\n\n"
        f"📦 Вам выпало: {selected_item['name']}\n"
        f"💰 Награда: {reward} {settings.currency_name}\n\n"
        f"💰 Баланс: {format_number(user['mcoin'])} {settings.currency_name}"
    )
    
    db.save()

# ========== ЧЕКИ ==========
async def cheques_menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("💳 Создать чек", callback_data="create_cheque")],
        [InlineKeyboardButton("🎫 Активировать чек", callback_data="activate_cheque")],
        [InlineKeyboardButton("📋 Мои чеки", callback_data="my_cheques")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🎫 **Чековая система** 🎫\n\n"
        f"💰 Комиссия за создание чека: {settings.cheque_fee * 100}%\n\n"
        f"**Как это работает:**\n"
        f"1. Создайте чек на нужную сумму\n"
        f"2. Получите уникальный код\n"
        f"3. Отправьте код другу\n"
        f"4. Друг активирует чек и получает средства\n\n"
        f"Чек действителен 7 дней!",
        reply_markup=reply_markup
    )

async def create_cheque(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    context.user_data["action"] = "create_cheque"
    
    await query.message.edit_text(
        f"💳 **Создание чека** 💳\n\n"
        f"Введите сумму чека (от 10 до 10000 {settings.currency_name}):\n\n"
        f"Комиссия: {settings.cheque_fee * 100}%"
    )
    return SET_CHEQUE_AMOUNT

async def process_cheque_amount(update: Update, context: CallbackContext):
    try:
        amount = int(update.message.text)
        if amount < 10 or amount > 10000:
            await update.message.reply_text("❌ Сумма должна быть от 10 до 10000!")
            return SET_CHEQUE_AMOUNT
    except:
        await update.message.reply_text("❌ Введите корректное число!")
        return SET_CHEQUE_AMOUNT
    
    user_id = update.effective_user.id
    fee = int(amount * settings.cheque_fee)
    total = amount + fee
    
    user = get_user_data(user_id)
    if user["mcoin"] < total:
        await update.message.reply_text(f"❌ Недостаточно средств! Нужно: {total} {settings.currency_name}")
        return SET_CHEQUE_AMOUNT
    
    remove_mcoins(user_id, total, f"create_cheque_{amount}")
    
    # Создаем чек
    code = generate_cheque_code()
    db.cheques[code] = {
        "amount": amount,
        "creator": user_id,
        "created_at": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(days=7)).isoformat(),
        "used_by": None,
        "used_at": None,
        "active": True
    }
    db.global_stats["total_cheques_created"] += 1
    db.save()
    
    await update.message.reply_text(
        f"✅ **Чек создан!** ✅\n\n"
        f"💰 Сумма: {amount} {settings.currency_name}\n"
        f"💸 Комиссия: {fee} {settings.currency_name}\n"
        f"🎫 **Код чека:** `{code}`\n\n"
        f"Отправьте этот код другу!\n"
        f"⏰ Чек действителен до: {(datetime.now() + timedelta(days=7)).strftime('%d.%m.%Y')}",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def activate_cheque(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["action"] = "activate_cheque"
    
    await query.message.edit_text(
        f"🎫 **Активация чека** 🎫\n\n"
        f"Введите код чека:"
    )
    return SET_CHEQUE_CODE

async def process_cheque_code(update: Update, context: CallbackContext):
    code = update.message.text.upper().strip()
    user_id = update.effective_user.id
    
    if code not in db.cheques:
        await update.message.reply_text("❌ Неверный код чека!")
        return ConversationHandler.END
    
    cheque = db.cheques[code]
    
    if not cheque["active"]:
        await update.message.reply_text("❌ Этот чек уже использован!")
        return ConversationHandler.END
    
    expires_at = datetime.fromisoformat(cheque["expires_at"])
    if datetime.now() > expires_at:
        await update.message.reply_text("❌ Срок действия чека истек!")
        return ConversationHandler.END
    
    # Активация чека
    amount = cheque["amount"]
    add_mcoins(user_id, amount, f"cheque_{code}", "other")
    cheque["active"] = False
    cheque["used_by"] = user_id
    cheque["used_at"] = datetime.now().isoformat()
    db.global_stats["total_cheques_activated"] += 1
    
    # Уведомляем создателя
    creator = cheque["creator"]
    user = get_user_data(user_id)
    try:
        await update.message.bot.send_message(
            creator,
            f"🎉 **Чек активирован!** 🎉\n\n"
            f"Ваш чек на {amount} {settings.currency_name}\n"
            f"Активировал: {user['first_name']}\n"
            f"💰 Средства получены!"
        )
    except:
        pass
    
    db.save()
    
    await update.message.reply_text(
        f"✅ **Чек активирован!** ✅\n\n"
        f"💰 Вы получили: {amount} {settings.currency_name}\n"
        f"🎉 Поздравляем!"
    )
    return ConversationHandler.END

async def my_cheques(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    
    created = []
    for code, cheque in db.cheques.items():
        if cheque["creator"] == user_id:
            status = "✅ Активен" if cheque["active"] else "❌ Использован"
            created.append(f"• {code} - {cheque['amount']} {settings.currency_name} ({status})")
    
    if not created:
        await query.message.edit_text("📋 У вас нет созданных чеков!")
        return
    
    await query.message.edit_text(
        f"📋 **Ваши чеки:**\n\n" + "\n".join(created[:20]) + 
        f"\n\n💡 Чек действителен 7 дней с момента создания"
    )

# ========== ЗАДАНИЯ BOTOHUB ==========
async def tasks_mode(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    # Проверка обязательных подписок
    passed, not_subscribed = await check_force_subs(user_id, context.bot)
    if not passed:
        msg = "⚠️ **Для выполнения заданий подпишитесь:**\n\n"
        for item in not_subscribed:
            msg += f"• {item}\n"
        msg += "\nПосле подписки нажмите /tasks"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return
    
    msg = await update.message.reply_text("🔄 Получаем задание...")
    
    try:
        result = await call_botohub_api(user_id, is_task=True, skip=False)
        
        tasks = result.get("tasks", [])
        completed = result.get("completed", False)
        skip_flag = result.get("skip", False)
        
        if completed:
            await msg.edit_text("✅ Вы выполнили все задания!")
            task_reward = settings.task_reward
            add_mcoins(user_id, task_reward, "all_tasks_completed", "task")
            await update.message.reply_text(f"🎉 Награда: {task_reward} {settings.currency_name}")
            return
        
        if skip_flag or not tasks:
            await msg.edit_text("🎉 Нет активных заданий! Зайдите позже.")
            return
        
        task_url = tasks[0]
        context.user_data["current_task_url"] = task_url
        
        keyboard = [
            [InlineKeyboardButton("✅ Я выполнил", callback_data=f"check_task_{task_url}")],
            [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await msg.edit_text(
            f"📢 **Новое задание!**\n\n"
            f"🔗 {task_url}\n\n"
            f"💰 Награда: {settings.task_reward} {settings.currency_name}\n\n"
            f"1. Перейдите по ссылке\n"
            f"2. Подпишитесь\n"
            f"3. Нажмите «✅ Я выполнил»",
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logger.error(f"Ошибка в tasks_mode: {e}")
        await msg.edit_text(f"❌ Ошибка: {e}")

async def check_task_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    task_url = query.data.replace("check_task_", "")
    
    await query.edit_message_text("🔍 Проверяем выполнение...")
    
    try:
        result = await call_botohub_api(user_id, is_task=True, skip=False)
        
        prev_success = result.get("prev_success", False)
        completed = result.get("completed", False)
        tasks = result.get("tasks", [])
        
        if prev_success:
            # Задание выполнено
            reward = settings.task_reward
            add_mcoins(user_id, reward, "task_completed", "task")
            
            if completed:
                await query.edit_message_text(
                    f"✅ Задание выполнено!\n"
                    f"💰 Получено: {reward} {settings.currency_name}\n"
                    f"🎉 Все задания выполнены!"
                )
            elif tasks:
                new_url = tasks[0]
                context.user_data["current_task_url"] = new_url
                
                keyboard = [
                    [InlineKeyboardButton("✅ Я выполнил", callback_data=f"check_task_{new_url}")],
                    [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"✅ Задание выполнено! +{reward} {settings.currency_name}\n\n"
                    f"📢 **Следующее задание:**\n{new_url}",
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
            else:
                await query.edit_message_text(f"✅ Задание выполнено! +{reward} {settings.currency_name}")
        else:
            await query.edit_message_text(
                f"❌ Вы ещё не подписались!\n\n"
                f"Пожалуйста, подпишитесь:\n{task_url}\n\n"
                f"После подписки нажмите «✅ Я выполнил»"
            )
            
            keyboard = [
                [InlineKeyboardButton("✅ Я выполнил", callback_data=f"check_task_{task_url}")],
                [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_reply_markup(reply_markup)
            
    except Exception as e:
        logger.error(f"Ошибка в check_task_callback: {e}")
        await query.edit_message_text(f"❌ Ошибка: {e}")

async def skip_task_callback(update: Update, context: CallbackContext):
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
            keyboard = [
                [InlineKeyboardButton("✅ Я выполнил", callback_data=f"check_task_{new_url}")],
                [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"⏩ Задание пропущено!\n\n"
                f"📢 **Новое задание:**\n{new_url}",
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
        else:
            await query.edit_message_text("🎉 Нет доступных заданий!")
            
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {e}")

# ========== АДМИН ПАНЕЛЬ ==========
async def admin_panel(update: Update, context: CallbackContext):
    if update.effective_user.id not in settings.admin_list:
        await update.message.reply_text("⛔ Доступ запрещен!")
        return
    
    keyboard = [
        [InlineKeyboardButton("💰 Настройка наград", callback_data="admin_rewards")],
        [InlineKeyboardButton("📦 Управление кейсами", callback_data="admin_cases")],
        [InlineKeyboardButton("🎰 Управление лотереей", callback_data="admin_lottery")],
        [InlineKeyboardButton("📢 Обязательные подписки", callback_data="admin_forcesub")],
        [InlineKeyboardButton("👥 Управление пользователями", callback_data="admin_users")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("💸 Выплаты", callback_data="admin_withdrawals")],
        [InlineKeyboardButton("📨 Рассылка", callback_data="admin_mailing")],
        [InlineKeyboardButton("🎫 Промокоды", callback_data="admin_promo")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="admin_settings")],
        [InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "⚙️ **Админ панель** ⚙️\n\n"
        f"👥 Пользователей: {db.global_stats['total_users']}\n"
        f"💰 Всего заработано: {format_number(db.global_stats['total_mcoins_earned'])}",
        reply_markup=reply_markup
    )

async def admin_rewards_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton(f"💰 За задание: {settings.task_reward}", callback_data="set_task_reward")],
        [InlineKeyboardButton(f"👥 За реферала: {settings.referral_reward}", callback_data="set_ref_reward")],
        [InlineKeyboardButton(f"🏆 Ежедневный: {settings.daily_reward}", callback_data="set_daily_reward")],
        [InlineKeyboardButton(f"💸 Мин. вывод: {settings.min_withdraw}", callback_data="set_min_withdraw")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "💰 **Настройка наград**\n\nВыберите параметр:",
        reply_markup=reply_markup
    )

async def set_task_reward(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["setting"] = "task_reward"
    await query.message.edit_text("Введите новую награду за задание:")
    return SET_REWARD

async def set_ref_reward(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["setting"] = "referral_reward"
    await query.message.edit_text("Введите новую награду за реферала:")
    return SET_REWARD

async def set_daily_reward(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["setting"] = "daily_reward"
    await query.message.edit_text("Введите новую ежедневную награду:")
    return SET_REWARD

async def set_min_withdraw(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["setting"] = "min_withdraw"
    await query.message.edit_text("Введите минимальную сумму вывода:")
    return SET_REWARD

async def process_reward_setting(update: Update, context: CallbackContext):
    try:
        value = int(update.message.text)
        if value <= 0:
            await update.message.reply_text("❌ Значение должно быть больше 0!")
            return SET_REWARD
        
        setting = context.user_data.get("setting")
        if setting == "task_reward":
            settings.task_reward = value
        elif setting == "referral_reward":
            settings.referral_reward = value
        elif setting == "daily_reward":
            settings.daily_reward = value
        elif setting == "min_withdraw":
            settings.min_withdraw = value
        
        settings.save()
        await update.message.reply_text(f"✅ Настройка обновлена!")
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Введите корректное число!")
        return SET_REWARD

async def admin_cases_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📦 Создать кейс", callback_data="create_case")],
        [InlineKeyboardButton("🗑 Удалить кейс", callback_data="delete_case")],
        [InlineKeyboardButton("📋 Список кейсов", callback_data="list_cases")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    cases_list = "\n".join([f"• {name}" for name in db.cases.keys()]) if db.cases else "Кейсы отсутствуют"
    
    await query.message.edit_text(
        f"📦 **Управление кейсами**\n\n{cases_list}",
        reply_markup=reply_markup
    )

async def create_case_start(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text("Введите название кейса:")
    return SET_NAME

async def create_case_name(update: Update, context: CallbackContext):
    name = update.message.text
    context.user_data["case_name"] = name
    await update.message.reply_text(f"Введите цену кейса (в {settings.currency_name}):")
    return SET_PRICE

async def create_case_price(update: Update, context: CallbackContext):
    try:
        price = int(update.message.text)
        context.user_data["case_price"] = price
        await update.message.reply_text(
            "Введите предметы в формате:\n"
            "Название | шанс | награда\n"
            "Пример: Легенда | 5 | 500\n\n"
            "Каждый предмет с новой строки. Для завершения отправьте 'готово':"
        )
        context.user_data["case_items"] = []
        return SET_DESCRIPTION
    except:
        await update.message.reply_text("❌ Введите число!")
        return SET_PRICE

async def create_case_items(update: Update, context: CallbackContext):
    text = update.message.text
    
    if text.lower() == 'готово':
        if not context.user_data["case_items"]:
            await update.message.reply_text("❌ Добавьте хотя бы один предмет!")
            return SET_DESCRIPTION
        
        db.cases[context.user_data["case_name"]] = {
            "price": context.user_data["case_price"],
            "items": context.user_data["case_items"]
        }
        db.save()
        
        await update.message.reply_text(f"✅ Кейс '{context.user_data['case_name']}' создан!")
        return ConversationHandler.END
    
    try:
        parts = text.split('|')
        if len(parts) != 3:
            await update.message.reply_text("❌ Формат: Название | шанс | награда")
            return SET_DESCRIPTION
        
        name = parts[0].strip()
        chance = float(parts[1].strip())
        reward = int(parts[2].strip())
        
        context.user_data["case_items"].append({
            "name": name,
            "chance": chance,
            "reward": reward
        })
        
        await update.message.reply_text(f"✅ Добавлен: {name}\nВсего предметов: {len(context.user_data['case_items'])}")
        return SET_DESCRIPTION
    except:
        await update.message.reply_text("❌ Ошибка! Пример: Название | 5 | 100")
        return SET_DESCRIPTION

async def delete_case(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if not db.cases:
        await query.message.edit_text("❌ Нет кейсов для удаления!")
        return
    
    keyboard = []
    for case_name in db.cases.keys():
        keyboard.append([InlineKeyboardButton(f"🗑 {case_name}", callback_data=f"delete_this_case_{case_name}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_cases")])
    
    await query.message.edit_text(
        "Выберите кейс для удаления:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def delete_this_case(update: Update, context: CallbackContext):
    query = update.callback_query
    case_name = query.data.replace("delete_this_case_", "")
    
    if case_name in db.cases:
        del db.cases[case_name]
        db.save()
        await query.message.edit_text(f"✅ Кейс '{case_name}' удален!")
    else:
        await query.message.edit_text("❌ Кейс не найден!")

async def list_cases(update: Update, context: CallbackContext):
    query = update.callback_query
    
    if not db.cases:
        await query.message.edit_text("📦 Кейсы отсутствуют")
        return
    
    cases_text = "📦 **Список кейсов:**\n\n"
    for name, data in db.cases.items():
        cases_text += f"• {name} - {data['price']} {settings.currency_name}\n"
        for item in data["items"]:
            cases_text += f"  - {item['name']}: {item['chance']}%, {item['reward']} {settings.currency_name}\n"
    
    await query.message.edit_text(cases_text[:4000])

async def admin_forcesub_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить канал", callback_data="add_channel")],
        [InlineKeyboardButton("➖ Удалить канал", callback_data="remove_channel")],
        [InlineKeyboardButton("📋 Список каналов", callback_data="list_channels")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    channels = "\n".join(settings.force_sub_channels) if settings.force_sub_channels else "Нет каналов"
    
    await query.message.edit_text(
        f"📢 **Обязательные подписки**\n\nТекущие каналы:\n{channels}",
        reply_markup=reply_markup
    )

async def add_channel(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["action"] = "add_channel"
    await query.message.edit_text("Введите username канала (например: @channel):")
    return SET_CHANNEL

async def remove_channel(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if not settings.force_sub_channels:
        await query.message.edit_text("❌ Нет каналов для удаления!")
        return
    
    keyboard = []
    for channel in settings.force_sub_channels:
        keyboard.append([InlineKeyboardButton(f"❌ {channel}", callback_data=f"remove_channel_{channel}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_forcesub")])
    
    await query.message.edit_text(
        "Выберите канал для удаления:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def remove_channel_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    channel = query.data.replace("remove_channel_", "")
    
    if channel in settings.force_sub_channels:
        settings.force_sub_channels.remove(channel)
        settings.save()
        await query.message.edit_text(f"✅ Канал {channel} удален!")
    else:
        await query.message.edit_text("❌ Канал не найден!")

async def list_channels(update: Update, context: CallbackContext):
    query = update.callback_query
    
    if not settings.force_sub_channels:
        await query.message.edit_text("📋 Нет обязательных каналов для подписки")
        return
    
    channels = "\n".join(settings.force_sub_channels)
    await query.message.edit_text(f"📋 **Обязательные каналы:**\n\n{channels}")

async def process_channel(update: Update, context: CallbackContext):
    channel = update.message.text.strip()
    
    if not channel.startswith("@"):
        channel = "@" + channel
    
    if context.user_data.get("action") == "add_channel":
        if channel not in settings.force_sub_channels:
            settings.force_sub_channels.append(channel)
            settings.save()
            await update.message.reply_text(f"✅ Канал {channel} добавлен!")
        else:
            await update.message.reply_text("❌ Канал уже в списке!")
    
    return ConversationHandler.END

async def admin_lottery_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🎲 Провести розыгрыш", callback_data="draw_lottery")],
        [InlineKeyboardButton("💰 Пополнить призовой фонд", callback_data="add_to_prize")],
        [InlineKeyboardButton("⏰ Настроить время розыгрыша", callback_data="set_lottery_time")],
        [InlineKeyboardButton("📊 Статистика лотереи", callback_data="lottery_stats")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"🎰 **Управление лотереей**\n\n"
        f"💰 Призовой фонд: {format_number(db.lottery['prize'])} {settings.currency_name}\n"
        f"🎫 Всего билетов: {sum(db.lottery['tickets'].values())}\n"
        f"⏰ Розыгрыш каждый день в {settings.lottery_draw_hour}:{settings.lottery_draw_minute:02d}",
        reply_markup=reply_markup
    )

async def draw_lottery(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in settings.admin_list:
        await query.answer("Только для админа!", show_alert=True)
        return
    
    total_tickets = sum(db.lottery["tickets"].values())
    
    if total_tickets == 0:
        await query.message.edit_text("❌ Нет билетов для розыгрыша!")
        return
    
    # Выбор победителя
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
    next_prize = int(db.lottery["prize"] * 0.2)
    
    add_mcoins(winner_id, prize, "lottery_win", "lottery")
    
    # Сохраняем историю
    winner_name = db.users.get(winner_id, {}).get("first_name", f"User_{winner_id}")
    db.lottery["history"].append({
        "round": db.lottery["current_round"],
        "winner": winner_id,
        "winner_name": winner_name,
        "prize": prize,
        "tickets": total_tickets,
        "date": datetime.now().isoformat()
    })
    
    # Сброс
    db.lottery["tickets"] = {}
    db.lottery["prize"] = next_prize
    db.lottery["current_round"] += 1
    db.lottery["last_draw"] = datetime.now().isoformat()
    db.save()
    
    await query.message.edit_text(
        f"🎉 **РОЗЫГРЫШ ЛОТЕРЕИ!** 🎉\n\n"
        f"🏆 Победитель: [{winner_name}](tg://user?id={winner_id})\n"
        f"💰 Приз: {format_number(prize)} {settings.currency_name}\n"
        f"🎫 Всего билетов: {total_tickets}\n\n"
        f"✨ Следующий розыгрыш скоро!",
        parse_mode="Markdown"
    )
    
    # Поздравляем победителя
    try:
        await context.bot.send_message(
            winner_id,
            f"🎉 **ВЫ ПОБЕДИЛИ В ЛОТЕРЕЕ!** 🎉\n\n"
            f"💰 Ваш выигрыш: {format_number(prize)} {settings.currency_name}\n"
            f"🎊 Поздравляем!"
        )
    except:
        pass

async def add_to_prize(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["action"] = "add_prize"
    await query.message.edit_text("Введите сумму для пополнения призового фонда:")
    return SET_REWARD

async def add_prize_process(update: Update, context: CallbackContext):
    try:
        amount = int(update.message.text)
        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть больше 0!")
            return SET_REWARD
        
        user_id = update.effective_user.id
        if not remove_mcoins(user_id, amount, "add_to_lottery_prize"):
            await update.message.reply_text(f"❌ Недостаточно {settings.currency_name}!")
            return SET_REWARD
        
        db.lottery["prize"] += amount
        db.save()
        
        await update.message.reply_text(
            f"✅ Призовой фонд пополнен на {amount} {settings.currency_name}\n"
            f"💰 Теперь в фонде: {format_number(db.lottery['prize'])} {settings.currency_name}"
        )
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Введите число!")
        return SET_REWARD

async def admin_users_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🔍 Найти пользователя", callback_data="find_user")],
        [InlineKeyboardButton("🚫 Забанить", callback_data="ban_user")],
        [InlineKeyboardButton("✅ Разбанить", callback_data="unban_user")],
        [InlineKeyboardButton("💰 Выдать MCoin", callback_data="give_mcoin")],
        [InlineKeyboardButton("📊 Топ пользователей", callback_data="top_users")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"👥 **Управление пользователями**\n\n"
        f"Всего пользователей: {db.global_stats['total_users']}\n"
        f"Забанено: {len(db.bans)}",
        reply_markup=reply_markup
    )

async def find_user(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["action"] = "find_user"
    await query.message.edit_text("Введите ID пользователя:")
    return SET_ADMIN_ID

async def process_find_user(update: Update, context: CallbackContext):
    try:
        user_id = int(update.message.text)
        if user_id not in db.users:
            await update.message.reply_text("❌ Пользователь не найден!")
            return ConversationHandler.END
        
        user = db.users[user_id]
        await update.message.reply_text(
            f"👤 **Пользователь:**\n\n"
            f"ID: {user_id}\n"
            f"Имя: {user.get('first_name', 'Unknown')}\n"
            f"💰 Баланс: {format_number(user['mcoin'])} {settings.currency_name}\n"
            f"📈 Всего заработано: {format_number(user['total_earned'])}\n"
            f"👥 Рефералов: {len(user['referrals'])}\n"
            f"🎮 Игр сыграно: {user['games_played']}\n"
            f"📅 В боте с: {user['join_date'][:10]}"
        )
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Введите корректный ID!")
        return SET_ADMIN_ID

async def ban_user(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["action"] = "ban_user"
    await query.message.edit_text("Введите ID пользователя для бана:")
    return SET_ADMIN_ID

async def unban_user(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["action"] = "unban_user"
    await query.message.edit_text("Введите ID пользователя для разбана:")
    return SET_ADMIN_ID

async def give_mcoin(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["action"] = "give_mcoin"
    await query.message.edit_text("Введите ID пользователя:")
    return SET_ADMIN_ID

async def process_give_mcoin_id(update: Update, context: CallbackContext):
    try:
        user_id = int(update.message.text)
        context.user_data["target_user"] = user_id
        await update.message.reply_text("Введите сумму:")
        return SET_REWARD
    except:
        await update.message.reply_text("❌ Введите корректный ID!")
        return SET_ADMIN_ID

async def process_give_mcoin_amount(update: Update, context: CallbackContext):
    try:
        amount = int(update.message.text)
        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть больше 0!")
            return SET_REWARD
        
        user_id = context.user_data["target_user"]
        add_mcoins(user_id, amount, "admin_gift", "other")
        
        await update.message.reply_text(f"✅ Выдано {amount} {settings.currency_name} пользователю {user_id}")
        
        # Уведомляем пользователя
        try:
            await update.message.bot.send_message(
                user_id,
                f"🎉 Администратор выдал вам {amount} {settings.currency_name}!"
            )
        except:
            pass
        
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Введите число!")
        return SET_REWARD

async def process_ban(update: Update, context: CallbackContext):
    try:
        user_id = int(update.message.text)
        db.bans[user_id] = {
            "reason": "Нарушение правил",
            "date": datetime.now().isoformat(),
            "admin": update.effective_user.id
        }
        db.save()
        await update.message.reply_text(f"✅ Пользователь {user_id} забанен!")
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Введите корректный ID!")
        return SET_ADMIN_ID

async def process_unban(update: Update, context: CallbackContext):
    try:
        user_id = int(update.message.text)
        if user_id in db.bans:
            del db.bans[user_id]
            db.save()
            await update.message.reply_text(f"✅ Пользователь {user_id} разбанен!")
        else:
            await update.message.reply_text("❌ Пользователь не в бане!")
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Введите корректный ID!")
        return SET_ADMIN_ID

async def top_users(update: Update, context: CallbackContext):
    query = update.callback_query
    
    # Сортируем по балансу
    top_by_balance = sorted(db.users.items(), key=lambda x: x[1]["mcoin"], reverse=True)[:10]
    top_by_earned = sorted(db.users.items(), key=lambda x: x[1]["total_earned"], reverse=True)[:10]
    
    balance_text = "💰 **Топ по балансу:**\n"
    for i, (uid, data) in enumerate(top_by_balance, 1):
        name = data.get("first_name", f"User_{uid}")
        balance_text += f"{i}. {name}: {format_number(data['mcoin'])} {settings.currency_name}\n"
    
    earned_text = "\n📈 **Топ по заработку:**\n"
    for i, (uid, data) in enumerate(top_by_earned, 1):
        name = data.get("first_name", f"User_{uid}")
        earned_text += f"{i}. {name}: {format_number(data['total_earned'])} {settings.currency_name}\n"
    
    await query.message.edit_text(balance_text + earned_text)

async def admin_stats(update: Update, context: CallbackContext):
    query = update.callback_query
    
    # Подробная статистика
    total_users = db.global_stats["total_users"]
    active_today = sum(1 for u in db.users.values() if u.get("last_seen", "").startswith(datetime.now().date().isoformat()))
    
    stats_text = (
        f"📊 **Детальная статистика** 📊\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"🟢 Активны сегодня: {active_today}\n"
        f"💰 Всего заработано: {format_number(db.global_stats['total_mcoins_earned'])} {settings.currency_name}\n"
        f"💸 Всего выведено: {format_number(db.global_stats['total_withdrawn'])} {settings.currency_name}\n"
        f"✅ Заданий выполнено: {db.global_stats['total_tasks_completed']}\n"
        f"🎫 Создано чеков: {db.global_stats['total_cheques_created']}\n"
        f"🎫 Активировано чеков: {db.global_stats['total_cheques_activated']}\n\n"
        f"📦 Кейсов: {len(db.cases)}\n"
        f"🎫 Промокодов: {len(db.promo_codes)}\n"
        f"💰 В лотерее: {format_number(db.lottery['prize'])} {settings.currency_name}\n"
        f"🎰 Раунд лотереи: {db.lottery['current_round']}\n\n"
        f"⚙️ **Настройки:**\n"
        f"💰 Награда за задание: {settings.task_reward}\n"
        f"👥 Награда за реферала: {settings.referral_reward}\n"
        f"🏆 Ежедневный бонус: {settings.daily_reward}\n"
        f"💸 Мин. вывод: {settings.min_withdraw}"
    )
    
    await query.message.edit_text(stats_text)

async def admin_withdrawals_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    pending = {uid: req for uid, req in db.withdraw_requests.items() if req.get("status") == "pending"}
    
    if not pending:
        await query.message.edit_text("📋 Нет активных заявок на вывод!")
        return
    
    keyboard = []
    for uid, req in pending.items():
        user = db.users.get(uid, {})
        name = user.get("first_name", f"User_{uid}")
        keyboard.append([InlineKeyboardButton(
            f"💸 {name}: {req['amount']} {settings.currency_name}",
            callback_data=f"process_withdraw_{uid}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")])
    
    await query.message.edit_text(
        f"📋 **Заявки на вывод:**\nВсего: {len(pending)}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def process_withdraw(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = int(query.data.replace("process_withdraw_", ""))
    
    if user_id not in db.withdraw_requests:
        await query.message.edit_text("❌ Заявка не найдена!")
        return
    
    req = db.withdraw_requests[user_id]
    amount = req["amount"]
    
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_withdraw_{user_id}")],
        [InlineKeyboardButton("❌ Отказать", callback_data=f"reject_withdraw_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"💸 **Заявка на вывод**\n\n"
        f"Пользователь: {user_id}\n"
        f"Сумма: {amount} {settings.currency_name}\n"
        f"Способ: {req.get('method', 'Не указан')}\n"
        f"Реквизиты: {req.get('address', 'Не указаны')}\n\n"
        f"Подтвердить или отказать?",
        reply_markup=reply_markup
    )

async def approve_withdraw(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = int(query.data.replace("approve_withdraw_", ""))
    
    if user_id not in db.withdraw_requests:
        await query.message.edit_text("❌ Заявка не найдена!")
        return
    
    req = db.withdraw_requests[user_id]
    amount = req["amount"]
    
    # Обновляем статус
    req["status"] = "approved"
    req["approved_at"] = datetime.now().isoformat()
    
    user = get_user_data(user_id)
    user["total_withdrawn"] += amount
    db.global_stats["total_withdrawn"] += amount
    db.save()
    
    await query.message.edit_text(f"✅ Вывод {amount} {settings.currency_name} для пользователя {user_id} подтвержден!")
    
    # Уведомляем пользователя
    try:
        await context.bot.send_message(
            user_id,
            f"✅ **Ваша заявка на вывод одобрена!**\n\n"
            f"💰 Сумма: {amount} {settings.currency_name}\n"
            f"⏱️ Ожидайте поступления в ближайшее время."
        )
    except:
        pass

async def reject_withdraw(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = int(query.data.replace("reject_withdraw_", ""))
    
    if user_id not in db.withdraw_requests:
        await query.message.edit_text("❌ Заявка не найдена!")
        return
    
    req = db.withdraw_requests[user_id]
    amount = req["amount"]
    
    # Возвращаем средства
    add_mcoins(user_id, amount, "withdraw_rejected", "other")
    
    # Обновляем статус
    req["status"] = "rejected"
    db.save()
    
    await query.message.edit_text(f"❌ Вывод {amount} {settings.currency_name} для пользователя {user_id} отклонен!")
    
    # Уведомляем пользователя
    try:
        await context.bot.send_message(
            user_id,
            f"❌ **Ваша заявка на вывод отклонена!**\n\n"
            f"💰 Сумма {amount} {settings.currency_name} возвращена на баланс.\n"
            f"Причина: проверьте правильность реквизитов."
        )
    except:
        pass

async def admin_mailing(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        "📨 **Рассылка**\n\n"
        "Введите текст сообщения для рассылки всем пользователям:\n\n"
        "Поддерживается Markdown формат."
    )
    return MAILING_TEXT

async def process_mailing(update: Update, context: CallbackContext):
    text = update.message.text
    
    success = 0
    fail = 0
    
    await update.message.reply_text("🔄 Начинаю рассылку...")
    
    for user_id in db.users.keys():
        try:
            await update.message.bot.send_message(
                user_id,
                f"📢 **Массовая рассылка**\n\n{text}",
                parse_mode="Markdown"
            )
            success += 1
            await asyncio.sleep(0.05)  # Защита от флуда
        except:
            fail += 1
    
    await update.message.reply_text(
        f"✅ **Рассылка завершена!**\n\n"
        f"📨 Доставлено: {success}\n"
        f"❌ Не доставлено: {fail}\n"
        f"👥 Всего: {success + fail}"
    )
    return ConversationHandler.END

async def admin_promo_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("➕ Создать промокод", callback_data="create_promo")],
        [InlineKeyboardButton("📋 Список промокодов", callback_data="list_promo")],
        [InlineKeyboardButton("❌ Удалить промокод", callback_data="delete_promo")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "🎫 **Управление промокодами**",
        reply_markup=reply_markup
    )

async def create_promo(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        "🎫 **Создание промокода**\n\n"
        "Введите код промокода (латиница и цифры):"
    )
    return SET_NAME

async def create_promo_code(update: Update, context: CallbackContext):
    code = update.message.text.upper().strip()
    context.user_data["promo_code"] = code
    
    await update.message.reply_text("Введите сумму награды:")
    return SET_PRICE

async def create_promo_reward(update: Update, context: CallbackContext):
    try:
        reward = int(update.message.text)
        context.user_data["promo_reward"] = reward
        
        await update.message.reply_text("Введите лимит использований (1-1000):")
        return SET_DESCRIPTION
    except:
        await update.message.reply_text("❌ Введите число!")
        return SET_PRICE

async def create_promo_limit(update: Update, context: CallbackContext):
    try:
        limit = int(update.message.text)
        
        code = context.user_data["promo_code"]
        db.promo_codes[code] = {
            "reward": context.user_data["promo_reward"],
            "max_uses": limit,
            "used_by": [],
            "created_at": datetime.now().isoformat(),
            "created_by": update.effective_user.id
        }
        db.save()
        
        await update.message.reply_text(
            f"✅ **Промокод создан!**\n\n"
            f"🎫 Код: `{code}`\n"
            f"💰 Награда: {context.user_data['promo_reward']} {settings.currency_name}\n"
            f"📊 Лимит: {limit}\n\n"
            f"Активация: /promo {code}",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Введите число!")
        return SET_DESCRIPTION

async def list_promo(update: Update, context: CallbackContext):
    query = update.callback_query
    
    if not db.promo_codes:
        await query.message.edit_text("📋 Нет активных промокодов")
        return
    
    text = "🎫 **Список промокодов:**\n\n"
    for code, data in db.promo_codes.items():
        used = len(data["used_by"])
        max_uses = data["max_uses"]
        text += f"• {code} - {data['reward']} {settings.currency_name} (использовано: {used}/{max_uses})\n"
    
    await query.message.edit_text(text)

async def delete_promo(update: Update, context: CallbackContext):
    query = update.callback_query
    
    if not db.promo_codes:
        await query.message.edit_text("❌ Нет промокодов для удаления!")
        return
    
    keyboard = []
    for code in db.promo_codes.keys():
        keyboard.append([InlineKeyboardButton(f"❌ {code}", callback_data=f"delete_promo_{code}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_promo")])
    
    await query.message.edit_text(
        "Выберите промокод для удаления:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def delete_promo_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    code = query.data.replace("delete_promo_", "")
    
    if code in db.promo_codes:
        del db.promo_codes[code]
        db.save()
        await query.message.edit_text(f"✅ Промокод {code} удален!")
    else:
        await query.message.edit_text("❌ Промокод не найден!")

async def admin_settings_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton(f"🎮 Игры: {'Вкл' if settings.games_enabled else 'Выкл'}", callback_data="toggle_games")],
        [InlineKeyboardButton(f"📦 Кейсы: {'Вкл' if settings.cases_enabled else 'Выкл'}", callback_data="toggle_cases")],
        [InlineKeyboardButton(f"🎰 Лотерея: {'Вкл' if settings.lottery_enabled else 'Выкл'}", callback_data="toggle_lottery")],
        [InlineKeyboardButton(f"👥 Рефералы: {'Вкл' if settings.referral_program else 'Выкл'}", callback_data="toggle_ref")],
        [InlineKeyboardButton("💰 Комиссия за чеки", callback_data="set_cheque_fee")],
        [InlineKeyboardButton("⏰ Время лотереи", callback_data="set_lottery_hour")],
        [InlineKeyboardButton("🎲 Настройки игр", callback_data="game_settings")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "⚙️ **Настройки бота**",
        reply_markup=reply_markup
    )

async def toggle_setting(update: Update, context: CallbackContext):
    query = update.callback_query
    setting = query.data.replace("toggle_", "")
    
    if setting == "games":
        settings.games_enabled = not settings.games_enabled
    elif setting == "cases":
        settings.cases_enabled = not settings.cases_enabled
    elif setting == "lottery":
        settings.lottery_enabled = not settings.lottery_enabled
    elif setting == "ref":
        settings.referral_program = not settings.referral_program
    
    settings.save()
    await query.answer("Настройка обновлена!")
    await admin_settings_menu(update, context)

async def set_cheque_fee(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        "💰 **Комиссия за чеки**\n\n"
        "Введите процент комиссии (0-50):"
    )
    return SET_TAX

async def process_cheque_fee(update: Update, context: CallbackContext):
    try:
        fee = float(update.message.text)
        if fee < 0 or fee > 50:
            await update.message.reply_text("❌ Комиссия должна быть от 0 до 50%!")
            return SET_TAX
        
        settings.cheque_fee = fee / 100
        settings.save()
        
        await update.message.reply_text(f"✅ Комиссия за чеки установлена: {fee}%")
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Введите число!")
        return SET_TAX

async def set_lottery_hour(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        "⏰ **Время розыгрыша лотереи**\n\n"
        "Введите час (0-23):"
    )
    return SET_LOTTERY_TIME

async def process_lottery_hour(update: Update, context: CallbackContext):
    try:
        hour = int(update.message.text)
        if hour < 0 or hour > 23:
            await update.message.reply_text("❌ Час должен быть от 0 до 23!")
            return SET_LOTTERY_TIME
        
        settings.lottery_draw_hour = hour
        settings.save()
        
        await update.message.reply_text(f"✅ Время розыгрыша установлено: {hour}:00")
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Введите число!")
        return SET_LOTTERY_TIME

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if user_id in db.bans:
        await update.message.reply_text("⛔ **Вы забанены!** ⛔")
        return
    
    # Реферальная ссылка
    if context.args and context.args[0].startswith("ref_"):
        referrer_id = int(context.args[0].replace("ref_", ""))
        if referrer_id != user_id and referrer_id not in db.bans:
            user_data = get_user_data(user_id)
            if not user_data.get("referrer"):
                user_data["referrer"] = referrer_id
                referrer_data = get_user_data(referrer_id)
                referrer_data["referrals"].append(user_id)
                
                ref_reward = settings.referral_reward
                add_mcoins(referrer_id, ref_reward, "referral_bonus", "referral")
                db.save()
                
                try:
                    await context.bot.send_message(
                        referrer_id,
                        f"👥 **Новый реферал!**\n\n"
                        f"{update.effective_user.first_name} присоединился!\n"
                        f"💰 +{ref_reward} {settings.currency_name}"
                    )
                except:
                    pass
    
    get_user_data(user_id)
    
    await update.message.reply_text(
        f"👋 **Привет, {update.effective_user.first_name}!**\n\n"
        f"{settings.welcome_message}\n\n"
        f"💰 Вам начислено 100 {settings.currency_name} стартового бонуса!\n\n"
        f"Используйте кнопки меню для навигации 👇",
        reply_markup=get_main_keyboard(user_id)
    )

async def balance_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    level, exp_needed, current_exp = update_user_level_and_get(user_id)
    progress = int((current_exp / exp_needed) * 20)
    progress_bar = "█" * progress + "░" * (20 - progress)
    
    await update.message.reply_text(
        f"💰 **Ваш баланс** 💰\n\n"
        f"🎮 {settings.currency_name}: `{format_number(user['mcoin'])}`\n\n"
        f"🏅 Уровень: {level}\n"
        f"📈 Опыт: {progress_bar} {current_exp}/{exp_needed}\n\n"
        f"📊 Всего заработано: {format_number(user['total_earned'])}\n"
        f"💸 Выведено: {format_number(user['total_withdrawn'])}\n"
        f"✅ С заданий: {format_number(user['task_earned'])}\n"
        f"🎲 С игр: {format_number(user['game_earned'])}\n"
        f"📦 С кейсов: {format_number(user['case_earned'])}\n"
        f"👥 С рефералов: {format_number(user['referral_earned'])}\n"
        f"🎰 С лотереи: {format_number(user['lottery_earned'])}",
        parse_mode="Markdown"
    )

def update_user_level_and_get(user_id: int) -> Tuple[int, int, int]:
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

async def daily_bonus(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    last_daily = user.get("daily_last")
    now = datetime.now()
    
    if last_daily:
        last_date = datetime.fromisoformat(last_daily)
        if last_date.date() == now.date():
            await update.message.reply_text(
                f"⏰ Вы уже получали бонус сегодня!\n\n"
                f"Серия: {user['daily_streak']} дней"
            )
            return
        elif (now - last_date).days == 1:
            user["daily_streak"] += 1
        else:
            user["daily_streak"] = 1
    
    base_reward = settings.daily_reward
    streak_multiplier = 1 + (user["daily_streak"] * 0.05)
    reward = int(base_reward * min(streak_multiplier, 2.0))
    
    add_mcoins(user_id, reward, "daily_bonus", "other")
    user["daily_last"] = now.isoformat()
    db.save()
    
    await update.message.reply_text(
        f"🎁 **Ежедневный бонус!** 🎁\n\n"
        f"💰 Получено: {reward} {settings.currency_name}\n"
        f"📊 Серия: {user['daily_streak']} дней\n"
        f"📈 Множитель: x{streak_multiplier:.2f}\n\n"
        f"💰 Баланс: {format_number(user['mcoin'])} {settings.currency_name}"
    )

async def referrals_menu(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    if not settings.referral_program:
        await update.message.reply_text("❌ Реферальная программа отключена!")
        return
    
    bot_username = context.bot.username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    await update.message.reply_text(
        f"👥 **Реферальная программа** 👥\n\n"
        f"💰 За реферала: {settings.referral_reward} {settings.currency_name}\n"
        f"👥 Ваших рефералов: {len(user['referrals'])}\n"
        f"💰 Заработано: {user['referral_earned']} {settings.currency_name}\n\n"
        f"🔗 **Ваша ссылка:**\n`{ref_link}`\n\n"
        f"Отправьте её друзьям и получайте бонусы!",
        parse_mode="Markdown"
    )

async def withdraw_menu(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    if user["mcoin"] < settings.min_withdraw:
        await update.message.reply_text(
            f"❌ Минимальная сумма вывода: {settings.min_withdraw} {settings.currency_name}\n"
            f"💰 Ваш баланс: {format_number(user['mcoin'])} {settings.currency_name}"
        )
        return
    
    context.user_data["withdraw_step"] = "amount"
    await update.message.reply_text(
        f"💸 **Вывод средств** 💸\n\n"
        f"💰 Доступно: {format_number(user['mcoin'])} {settings.currency_name}\n"
        f"📉 Мин. сумма: {settings.min_withdraw}\n"
        f"📈 Макс. сумма: {settings.max_withdraw}\n\n"
        f"Введите сумму для вывода:"
    )
    return SET_WITHDRAW

async def process_withdraw_amount(update: Update, context: CallbackContext):
    try:
        amount = int(update.message.text)
        user_id = update.effective_user.id
        user = get_user_data(user_id)
        
        if amount < settings.min_withdraw:
            await update.message.reply_text(f"❌ Минимальная сумма: {settings.min_withdraw}")
            return SET_WITHDRAW
        if amount > settings.max_withdraw:
            await update.message.reply_text(f"❌ Максимальная сумма: {settings.max_withdraw}")
            return SET_WITHDRAW
        if amount > user["mcoin"]:
            await update.message.reply_text(f"❌ Недостаточно средств!")
            return SET_WITHDRAW
        
        context.user_data["withdraw_amount"] = amount
        await update.message.reply_text(
            "Выберите способ вывода:\n"
            "1. QIWI\n"
            "2. Банковская карта\n"
            "3. Криптовалюта\n\n"
            "Введите номер способа или реквизиты:"
        )
        return SET_WITHDRAW_ADDRESS
    except:
        await update.message.reply_text("❌ Введите число!")
        return SET_WITHDRAW

async def process_withdraw_address(update: Update, context: CallbackContext):
    address = update.message.text
    user_id = update.effective_user.id
    amount = context.user_data["withdraw_amount"]
    
    # Проверяем и снимаем средства
    if not remove_mcoins(user_id, amount, f"withdraw_request_{amount}"):
        await update.message.reply_text("❌ Ошибка при списании средств!")
        return ConversationHandler.END
    
    # Создаем заявку
    db.withdraw_requests[user_id] = {
        "amount": amount,
        "address": address,
        "method": "manual",
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }
    db.save()
    
    await update.message.reply_text(
        f"✅ **Заявка на вывод создана!**\n\n"
        f"💰 Сумма: {amount} {settings.currency_name}\n"
        f"📮 Реквизиты: {address}\n\n"
        f"⏱️ Заявка будет обработана в течение 24 часов."
    )
    
    # Уведомляем админа
    for admin_id in settings.admin_list:
        try:
            await update.message.bot.send_message(
                admin_id,
                f"💸 **Новая заявка на вывод!**\n\n"
                f"👤 Пользователь: {user_id}\n"
                f"💰 Сумма: {amount} {settings.currency_name}\n"
                f"📮 Реквизиты: {address}"
            )
        except:
            pass
    
    return ConversationHandler.END

async def promo_use(update: Update, context: CallbackContext):
    args = context.args
    
    if not args:
        await update.message.reply_text("Использование: /promo <код>")
        return
    
    code = args[0].upper()
    user_id = update.effective_user.id
    
    if code not in db.promo_codes:
        await update.message.reply_text("❌ Неверный промокод!")
        return
    
    promo = db.promo_codes[code]
    
    if user_id in promo.get("used_by", []):
        await update.message.reply_text("❌ Вы уже использовали этот промокод!")
        return
    
    if len(promo.get("used_by", [])) >= promo.get("max_uses", 1):
        await update.message.reply_text("❌ Промокод больше не действителен!")
        return
    
    # Активация
    reward = promo["reward"]
    add_mcoins(user_id, reward, f"promo_{code}", "other")
    
    if "used_by" not in promo:
        promo["used_by"] = []
    promo["used_by"].append(user_id)
    db.save()
    
    await update.message.reply_text(
        f"✅ **Промокод активирован!**\n\n"
        f"💰 Вы получили: {reward} {settings.currency_name}\n"
        f"🎉 Поздравляем!"
    )

async def inventory_menu(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    if not user["inventory"]:
        await update.message.reply_text("📦 Ваш инвентарь пуст!\n\nОткрывайте кейсы, чтобы получать предметы!")
        return
    
    # Группируем предметы
    items_count = {}
    for item in user["inventory"]:
        name = item["name"]
        items_count[name] = items_count.get(name, 0) + 1
    
    inventory_text = "📦 **Ваш инвентарь:**\n\n"
    for name, count in items_count.items():
        inventory_text += f"• {name} x{count}\n"
    
    await update.message.reply_text(inventory_text)

async def stats_menu(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    # Достижения
    achievements_list = db.achievements.get(user_id, [])
    achievements_text = "\n".join([f"🏆 {ach}" for ach in achievements_list]) if achievements_list else "Нет достижений"
    
    await update.message.reply_text(
        f"📊 **Ваша статистика** 📊\n\n"
        f"💰 Баланс: {format_number(user['mcoin'])} {settings.currency_name}\n"
        f"📈 Всего заработано: {format_number(user['total_earned'])}\n"
        f"💸 Выведено: {format_number(user['total_withdrawn'])}\n\n"
        f"🎮 Игр сыграно: {user['games_played']}\n"
        f"🏆 Побед: {user['games_won']}\n"
        f"📦 Кейсов открыто: {user['cases_opened']}\n"
        f"👥 Рефералов: {len(user['referrals'])}\n"
        f"🔥 Серия: {user['daily_streak']} дней\n\n"
        f"🏅 **Достижения:**\n{achievements_text}"
    )

async def handle_text(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id in db.bans:
        await update.message.reply_text("⛔ Вы забанены!")
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
        await promo_use(update, context)
    elif text == "📊 Статистика":
        await stats_menu(update, context)
    elif text == "🎫 Чеки":
        await cheques_menu(update, context)
    elif text == "🎁 Инвентарь":
        await inventory_menu(update, context)
    elif text == "⚙️ Админ панель" and user_id in settings.admin_list:
        await admin_panel(update, context)
    else:
        await update.message.reply_text(
            "Используйте кнопки меню 👇",
            reply_markup=get_main_keyboard(user_id)
        )

async def games_menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("🎰 Казино (/casino)", callback_data="game_casino")],
        [InlineKeyboardButton("🎲 Кости (/dice)", callback_data="game_dice")],
        [InlineKeyboardButton("🎰 Слоты (/slots)", callback_data="game_slots")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎮 **Игры** 🎮\n\n"
        "Выберите игру:",
        reply_markup=reply_markup
    )

async def lottery_menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("🎫 Купить билет (10 MCoin)", callback_data="buy_ticket")],
        [InlineKeyboardButton("🎫 Купить 10 билетов (95 MCoin)", callback_data="buy_10_tickets")],
        [InlineKeyboardButton("📊 Информация", callback_data="lottery_info")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    total_tickets = sum(db.lottery["tickets"].values())
    
    await update.message.reply_text(
        f"🎰 **Лотерея** 🎰\n\n"
        f"💰 Призовой фонд: {format_number(db.lottery['prize'])} {settings.currency_name}\n"
        f"🎫 Всего билетов: {total_tickets}\n"
        f"🎟️ Цена билета: 10 {settings.currency_name}\n\n"
        f"Победитель получает 80% призового фонда!",
        reply_markup=reply_markup
    )

async def buy_ticket(update: Update, context: CallbackContext, count: int = 1):
    query = update.callback_query
    user_id = query.from_user.id
    
    if not db.lottery["active"]:
        await query.answer("Лотерея не активна!", show_alert=True)
        return
    
    price = 10 * count
    if count == 10:
        price = 95
    
    if not remove_mcoins(user_id, price, f"lottery_ticket_{count}"):
        await query.answer(f"Недостаточно {settings.currency_name}!", show_alert=True)
        return
    
    if user_id not in db.lottery["tickets"]:
        db.lottery["tickets"][user_id] = 0
    db.lottery["tickets"][user_id] += count
    db.lottery["prize"] += int(price * 0.8)
    db.save()
    
    await query.answer(f"Куплено {count} билетов!", show_alert=True)
    await query.message.edit_text(
        f"✅ **Куплено {count} билетов!**\n\n"
        f"💰 Ваших билетов: {db.lottery['tickets'][user_id]}\n"
        f"💰 Призовой фонд: {format_number(db.lottery['prize'])} {settings.currency_name}"
    )

async def lottery_info(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    history = db.lottery.get("history", [])
    if history:
        last_winners = "\n".join([f"• Раунд {h['round']}: {h['winner_name']} - {format_number(h['prize'])} MCoin" for h in history[-5:]])
    else:
        last_winners = "Еще не было розыгрышей"
    
    await query.message.edit_text(
        f"📊 **Информация о лотерее**\n\n"
        f"💰 Текущий фонд: {format_number(db.lottery['prize'])} {settings.currency_name}\n"
        f"🎰 Раунд: {db.lottery['current_round']}\n\n"
        f"🏆 **Последние победители:**\n{last_winners}\n\n"
        f"⏰ Ежедневный розыгрыш в {settings.lottery_draw_hour}:00"
    )

# ========== АВТОМАТИЧЕСКИЙ РОЗЫГРЫШ ЛОТЕРЕИ ==========
async def auto_lottery_draw(context: CallbackContext):
    if not settings.auto_lottery or not db.lottery["active"]:
        return
    
    total_tickets = sum(db.lottery["tickets"].values())
    if total_tickets == 0:
        return
    
    # Выбор победителя
    winner_roll = random.randint(1, total_tickets)
    current = 0
    winner_id = None
    
    for uid, tickets in db.lottery["tickets"].items():
        current += tickets
        if current >= winner_roll:
            winner_id = uid
            break
    
    if not winner_id:
        return
    
    prize = int(db.lottery["prize"] * 0.8)
    next_prize = int(db.lottery["prize"] * 0.2)
    
    add_mcoins(winner_id, prize, "lottery_auto_win", "lottery")
    
    winner_name = db.users.get(winner_id, {}).get("first_name", f"User_{winner_id}")
    db.lottery["history"].append({
        "round": db.lottery["current_round"],
        "winner": winner_id,
        "winner_name": winner_name,
        "prize": prize,
        "tickets": total_tickets,
        "date": datetime.now().isoformat()
    })
    
    db.lottery["tickets"] = {}
    db.lottery["prize"] = next_prize
    db.lottery["current_round"] += 1
    db.lottery["last_draw"] = datetime.now().isoformat()
    db.save()
    
    # Уведомляем всех админов
    for admin_id in settings.admin_list:
        try:
            await context.bot.send_message(
                admin_id,
                f"🎉 **Автоматический розыгрыш лотереи!**\n\n"
                f"🏆 Победитель: {winner_name}\n"
                f"💰 Приз: {format_number(prize)} {settings.currency_name}"
            )
        except:
            pass
    
    # Поздравляем победителя
    try:
        await context.bot.send_message(
            winner_id,
            f"🎉 **ВЫ ПОБЕДИЛИ В ЛОТЕРЕЕ!** 🎉\n\n"
            f"💰 Ваш выигрыш: {format_number(prize)} {settings.currency_name}\n"
            f"🎊 Поздравляем!"
        )
    except:
        pass

# ========== ЗАПУСК БОТА ==========
def main():
    db.load()
    settings.load()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Conversation handlers
    conv_reward = ConversationHandler(
        entry_points=[CallbackQueryHandler(set_task_reward, pattern="^set_task_reward$"),
                     CallbackQueryHandler(set_ref_reward, pattern="^set_ref_reward$"),
                     CallbackQueryHandler(set_daily_reward, pattern="^set_daily_reward$"),
                     CallbackQueryHandler(set_min_withdraw, pattern="^set_min_withdraw$")],
        states={SET_REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_reward_setting)]},
        fallbacks=[]
    )
    
    conv_case = ConversationHandler(
        entry_points=[CallbackQueryHandler(create_case_start, pattern="^create_case$")],
        states={
            SET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_case_name)],
            SET_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_case_price)],
            SET_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_case_items)],
        },
        fallbacks=[]
    )
    
    conv_channel = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_channel, pattern="^add_channel$")],
        states={SET_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_channel)]},
        fallbacks=[]
    )
    
    conv_cheque = ConversationHandler(
        entry_points=[CallbackQueryHandler(create_cheque, pattern="^create_cheque$"),
                     CallbackQueryHandler(activate_cheque, pattern="^activate_cheque$")],
        states={
            SET_CHEQUE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_cheque_amount)],
            SET_CHEQUE_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_cheque_code)],
        },
        fallbacks=[]
    )
    
    conv_withdraw = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💸 Вывод средств$"), withdraw_menu)],
        states={
            SET_WITHDRAW: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_withdraw_amount)],
            SET_WITHDRAW_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_withdraw_address)],
        },
        fallbacks=[]
    )
    
    conv_mailing = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_mailing, pattern="^admin_mailing$")],
        states={MAILING_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_mailing)]},
        fallbacks=[]
    )
    
    conv_promo = ConversationHandler(
        entry_points=[CallbackQueryHandler(create_promo, pattern="^create_promo$")],
        states={
            SET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_promo_code)],
            SET_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_promo_reward)],
            SET_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_promo_limit)],
        },
        fallbacks=[]
    )
    
    conv_prize = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_to_prize, pattern="^add_to_prize$")],
        states={SET_REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_prize_process)]},
        fallbacks=[]
    )
    
    conv_user_find = ConversationHandler(
        entry_points=[CallbackQueryHandler(find_user, pattern="^find_user$")],
        states={SET_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_find_user)]},
        fallbacks=[]
    )
    
    conv_ban = ConversationHandler(
        entry_points=[CallbackQueryHandler(ban_user, pattern="^ban_user$")],
        states={SET_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_ban)]},
        fallbacks=[]
    )
    
    conv_unban = ConversationHandler(
        entry_points=[CallbackQueryHandler(unban_user, pattern="^unban_user$")],
        states={SET_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_unban)]},
        fallbacks=[]
    )
    
    conv_give = ConversationHandler(
        entry_points=[CallbackQueryHandler(give_mcoin, pattern="^give_mcoin$")],
        states={
            SET_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_give_mcoin_id)],
            SET_REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_give_mcoin_amount)],
        },
        fallbacks=[]
    )
    
    conv_fee = ConversationHandler(
        entry_points=[CallbackQueryHandler(set_cheque_fee, pattern="^set_cheque_fee$")],
        states={SET_TAX: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_cheque_fee)]},
        fallbacks=[]
    )
    
    conv_lottery_time = ConversationHandler(
        entry_points=[CallbackQueryHandler(set_lottery_hour, pattern="^set_lottery_hour$")],
        states={SET_LOTTERY_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_lottery_hour)]},
        fallbacks=[]
    )
    
    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("casino", game_casino))
    app.add_handler(CommandHandler("dice", game_dice))
    app.add_handler(CommandHandler("slots", game_slots))
    app.add_handler(CommandHandler("promo", promo_use))
    app.add_handler(CommandHandler("tasks", tasks_mode))
    
    app.add_handler(conv_reward)
    app.add_handler(conv_case)
    app.add_handler(conv_channel)
    app.add_handler(conv_cheque)
    app.add_handler(conv_withdraw)
    app.add_handler(conv_mailing)
    app.add_handler(conv_promo)
    app.add_handler(conv_prize)
    app.add_handler(conv_user_find)
    app.add_handler(conv_ban)
    app.add_handler(conv_unban)
    app.add_handler(conv_give)
    app.add_handler(conv_fee)
    app.add_handler(conv_lottery_time)
    
    # Callback handlers
    app.add_handler(CallbackQueryHandler(admin_rewards_menu, pattern="^admin_rewards$"))
    app.add_handler(CallbackQueryHandler(admin_cases_menu, pattern="^admin_cases$"))
    app.add_handler(CallbackQueryHandler(admin_forcesub_menu, pattern="^admin_forcesub$"))
    app.add_handler(CallbackQueryHandler(admin_lottery_menu, pattern="^admin_lottery$"))
    app.add_handler(CallbackQueryHandler(admin_users_menu, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_withdrawals_menu, pattern="^admin_withdrawals$"))
    app.add_handler(CallbackQueryHandler(admin_promo_menu, pattern="^admin_promo$"))
    app.add_handler(CallbackQueryHandler(admin_settings_menu, pattern="^admin_settings$"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    
    app.add_handler(CallbackQueryHandler(delete_case, pattern="^delete_case$"))
    app.add_handler(CallbackQueryHandler(delete_this_case, pattern="^delete_this_case_"))
    app.add_handler(CallbackQueryHandler(list_cases, pattern="^list_cases$"))
    
    app.add_handler(CallbackQueryHandler(remove_channel, pattern="^remove_channel$"))
    app.add_handler(CallbackQueryHandler(remove_channel_callback, pattern="^remove_channel_"))
    app.add_handler(CallbackQueryHandler(list_channels, pattern="^list_channels$"))
    
    app.add_handler(CallbackQueryHandler(draw_lottery, pattern="^draw_lottery$"))
    app.add_handler(CallbackQueryHandler(lottery_info, pattern="^lottery_info$"))
    
    app.add_handler(CallbackQueryHandler(process_withdraw, pattern="^process_withdraw_"))
    app.add_handler(CallbackQueryHandler(approve_withdraw, pattern="^approve_withdraw_"))
    app.add_handler(CallbackQueryHandler(reject_withdraw, pattern="^reject_withdraw_"))
    
    app.add_handler(CallbackQueryHandler(list_promo, pattern="^list_promo$"))
    app.add_handler(CallbackQueryHandler(delete_promo, pattern="^delete_promo$"))
    app.add_handler(CallbackQueryHandler(delete_promo_callback, pattern="^delete_promo_"))
    
    app.add_handler(CallbackQueryHandler(toggle_setting, pattern="^toggle_"))
    
    app.add_handler(CallbackQueryHandler(top_users, pattern="^top_users$"))
    
    app.add_handler(CallbackQueryHandler(case_info_callback, pattern="^case_info_"))
    app.add_handler(CallbackQueryHandler(open_case, pattern="^open_case_"))
    app.add_handler(CallbackQueryHandler(buy_ticket, pattern="^buy_ticket$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: buy_ticket(u,c,10), pattern="^buy_10_tickets$"))
    app.add_handler(CallbackQueryHandler(check_task_callback, pattern="^check_task_"))
    app.add_handler(CallbackQueryHandler(skip_task_callback, pattern="^skip_task$"))
    
    app.add_handler(CallbackQueryHandler(my_cheques, pattern="^my_cheques$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.message.delete(), pattern="^cases_back$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: games_menu(u,c), pattern="^games_back$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.message.delete(), pattern="^back_to_main$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.message.delete(), pattern="^lottery_back$"))
    
    # Message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Job queue для автоматической лотереи
    job_queue = app.job_queue
    if job_queue:
        # Запускаем каждый день в указанное время
        job_queue.run_daily(
            auto_lottery_draw,
            time=datetime.time(hour=settings.lottery_draw_hour, minute=settings.lottery_draw_minute),
            days=(0,1,2,3,4,5,6)
        )
        logger.info(f"Автоматическая лотерея запланирована на {settings.lottery_draw_hour}:{settings.lottery_draw_minute:02d}")
    
    # Запуск
    print(f"🚀 Бот запущен!")
    print(f"👑 Администратор: {ADMIN_ID}")
    print(f"💰 Валюта: {settings.currency_name}")
    print(f"🎰 Лотерея: ежедневно в {settings.lottery_draw_hour}:00")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()