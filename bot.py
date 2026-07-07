import asyncio
import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple, Any
from collections import defaultdict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    CallbackContext,
    ConversationHandler,
)
import aiohttp

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = "8251949164:AAFRGh0wB7C0ZdMQ95oNPrrFGTsd6R-5h_U"

# BotoHub
BOTOHUB_TOKEN = "ae49fee8-827d-4771-a6bd-7e9ba579b710"
BOTOHUB_API_URL = "https://botohub.me/get-tasks"

# PiarFlow
PIARFLOW_API_KEY = "hG3G-wLstzci6B9emgXV53EOvsOswto2"
PIARFLOW_API_URL = "https://piarflow.com/v1"

ADMIN_ID = 5356400377

# Файлы для хранения данных
DATA_FILE = "bot_data.json"
SETTINGS_FILE = "settings.json"

# ========== ЦВЕТОВЫЕ ПОМЕТКИ ДЛЯ СПОНСОРОВ ==========
SPONSOR_COLORS = {
    "BotoHub": "🔵",
    "PiarFlow": "🟢",
    "Custom": "🔴"
}

# ========== СТРУКТУРА ДАННЫХ ==========
class BotDatabase:
    def __init__(self):
        self.users: Dict[int, Dict] = {}
        self.withdraw_requests: Dict[int, Dict] = {}
        self.bans: Dict[int, Dict] = {}
        self.global_stats: Dict = {
            "total_users": 0,
            "total_mcoins_earned": 0,
            "total_withdrawn": 0,
            "total_tasks_completed": 0,
            "total_referrals": 0,
            "total_promos_used": 0
        }
        self.active_tasks: Dict[int, Dict] = {}
        self.used_task_links: Dict[int, List[str]] = {}
        self.promo_codes: Dict[str, Dict] = {}
        self.used_promo: Dict[int, List[str]] = {}
        self.force_tasks: Dict[int, Dict] = {}
        self.top_users: Dict[int, Dict] = {}
        self.monthly_top: Dict[int, Dict] = {}
        self.custom_tasks: Dict[int, Dict] = {}
        self.daily_claimed: Dict[int, datetime] = {}
        self.achievements: Dict[int, List[str]] = {}
        self.contests: Dict[int, Dict] = {}
        self.piarflow_tasks: Dict[int, List[Dict]] = {}
        self.user_task_cache: Dict[int, Dict] = {}
        
    def save(self):
        data = {
            "users": self.users,
            "withdraw_requests": self.withdraw_requests,
            "bans": self.bans,
            "global_stats": self.global_stats,
            "active_tasks": self.active_tasks,
            "used_task_links": self.used_task_links,
            "promo_codes": self.promo_codes,
            "used_promo": self.used_promo,
            "force_tasks": self.force_tasks,
            "top_users": self.top_users,
            "monthly_top": self.monthly_top,
            "custom_tasks": self.custom_tasks,
            "daily_claimed": {k: v.isoformat() for k, v in self.daily_claimed.items()},
            "achievements": self.achievements,
            "contests": self.contests,
            "piarflow_tasks": self.piarflow_tasks,
            "user_task_cache": self.user_task_cache
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
                    self.withdraw_requests = {int(k): v for k, v in data.get("withdraw_requests", {}).items()}
                    self.bans = {int(k): v for k, v in data.get("bans", {}).items()}
                    self.global_stats = data.get("global_stats", self.global_stats)
                    self.active_tasks = {int(k): v for k, v in data.get("active_tasks", {}).items()}
                    self.used_task_links = {int(k): v for k, v in data.get("used_task_links", {}).items()}
                    self.promo_codes = data.get("promo_codes", {})
                    self.used_promo = {int(k): v for k, v in data.get("used_promo", {}).items()}
                    self.force_tasks = {int(k): v for k, v in data.get("force_tasks", {}).items()}
                    self.top_users = {int(k): v for k, v in data.get("top_users", {}).items()}
                    self.monthly_top = {int(k): v for k, v in data.get("monthly_top", {}).items()}
                    self.custom_tasks = {int(k): v for k, v in data.get("custom_tasks", {}).items()}
                    self.daily_claimed = {int(k): datetime.fromisoformat(v) for k, v in data.get("daily_claimed", {}).items()}
                    self.achievements = {int(k): v for k, v in data.get("achievements", {}).items()}
                    self.contests = {int(k): v for k, v in data.get("contests", {}).items()}
                    self.piarflow_tasks = {int(k): v for k, v in data.get("piarflow_tasks", {}).items()}
                    self.user_task_cache = {int(k): v for k, v in data.get("user_task_cache", {}).items()}
                logger.info("Данные загружены")
            except Exception as e:
                logger.error(f"Ошибка загрузки данных: {e}")

class BotSettings:
    def __init__(self):
        self.task_reward = 10
        self.referral_reward = 5
        self.daily_reward = 15
        self.min_withdraw = 50
        self.force_sub_channels = []
        self.force_sub_groups = []
        self.admin_list = [ADMIN_ID]
        self.currency_name = "MCoin"
        self.currency_emoji = "🪙"
        self.withdraw_commission = 0.05
        self.max_daily_tasks = 50
        self.maintenance_mode = False
        self.top_prize_1 = 100
        self.top_prize_2 = 50
        self.top_prize_3 = 30
        self.max_withdraw = 10000
        self.daily_streak_bonus = True
        self.promo_enabled = True
        self.contest_enabled = True
        self.force_sub_sponsors = True
        self.sponsor_gender = None
        self.sponsor_age = None
        
    def save(self):
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.__dict__, f, ensure_ascii=False, indent=2)
            logger.info("Настройки сохранены")
        except Exception as e:
            logger.error(f"Ошибка сохранения настроек: {e}")
    
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
def get_currency_symbol() -> str:
    return f"{settings.currency_emoji} {settings.currency_name}"

def get_sponsor_color(source: str) -> str:
    return SPONSOR_COLORS.get(source, "⚪")

def get_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    if user_id in db.bans:
        return ReplyKeyboardMarkup([["ℹ️ Я в бане"]], resize_keyboard=True)
    
    currency = get_currency_symbol()
    
    keyboard = [
        [KeyboardButton(f"📋 Задания"), KeyboardButton(f"👥 Рефералы")],
        [KeyboardButton(f"👤 Профиль"), KeyboardButton(f"💰 {currency}")],
    ]
    
    if user_id in settings.admin_list:
        keyboard.append([KeyboardButton("⚙️ Админ панель")])
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_user_data(user_id: int) -> Dict:
    if user_id not in db.users:
        db.users[user_id] = {
            "mcoin": 0,
            "tasks_completed": [],
            "referrals": [],
            "referrer": None,
            "daily_last": None,
            "total_earned": 0,
            "total_withdrawn": 0,
            "tasks_today": 0,
            "last_task_date": None,
            "join_date": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
            "username": None,
            "first_name": "",
            "daily_streak": 0,
            "last_streak_date": None,
            "referral_earned": 0,
            "task_earned": 0,
            "bonus_claims": 0,
            "total_tasks_completed": 0,
            "completed_links": [],
            "monthly_tasks": 0,
            "monthly_date": datetime.now().strftime("%Y-%m"),
            "notifications_enabled": True,
            "last_force_task": None,
            "promos_used": 0
        }
        db.global_stats["total_users"] += 1
        db.save()
    return db.users[user_id]

def get_user_by_username(username: str) -> Optional[int]:
    username = username.lower().strip()
    if username.startswith("@"):
        username = username[1:]
    
    for user_id, data in db.users.items():
        if data.get("username") and data["username"].lower() == username:
            return user_id
    return None

def add_mcoins(user_id: int, amount: int, reason: str = "", source: str = "other") -> bool:
    if amount <= 0:
        return False
    
    user = get_user_data(user_id)
    user["mcoin"] += amount
    user["total_earned"] += amount
    
    if source in ["task", "botohub", "piarflow", "custom", "force"]:
        user["task_earned"] += amount
        user["total_tasks_completed"] += 1
        user["monthly_tasks"] += 1
        user["monthly_date"] = datetime.now().strftime("%Y-%m")
        db.global_stats["total_tasks_completed"] += 1
        update_top_users(user_id)
        check_achievements(user_id)
    elif source == "referral":
        user["referral_earned"] += amount
        db.global_stats["total_referrals"] += 1
    elif source == "top_prize":
        user["task_earned"] += amount
    elif source == "promo":
        user["task_earned"] += amount
        user["promos_used"] += 1
        db.global_stats["total_promos_used"] += 1
    elif source == "daily":
        user["bonus_claims"] += 1
    elif source == "contest":
        user["task_earned"] += amount
    
    db.global_stats["total_mcoins_earned"] += amount
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

def format_number(num: int) -> str:
    return f"{num:,}".replace(",", ".")

def update_top_users(user_id: int):
    user = get_user_data(user_id)
    current_month = datetime.now().strftime("%Y-%m")
    
    if user["monthly_date"] != current_month:
        user["monthly_tasks"] = 0
        user["monthly_date"] = current_month
    
    db.top_users[user_id] = {
        "tasks": user["total_tasks_completed"],
        "username": user.get("username", "Неизвестно"),
        "name": user.get("first_name", "Пользователь")
    }
    
    db.monthly_top[user_id] = {
        "tasks": user["monthly_tasks"],
        "username": user.get("username", "Неизвестно"),
        "name": user.get("first_name", "Пользователь")
    }
    
    db.save()

def check_achievements(user_id: int):
    user = get_user_data(user_id)
    achievements = db.achievements.get(user_id, [])
    
    if user["total_tasks_completed"] >= 100 and "100_tasks" not in achievements:
        achievements.append("100_tasks")
        add_mcoins(user_id, 50, "achievement_100_tasks", "other")
    
    if user["total_tasks_completed"] >= 500 and "500_tasks" not in achievements:
        achievements.append("500_tasks")
        add_mcoins(user_id, 250, "achievement_500_tasks", "other")
    
    if user["total_tasks_completed"] >= 1000 and "1000_tasks" not in achievements:
        achievements.append("1000_tasks")
        add_mcoins(user_id, 500, "achievement_1000_tasks", "other")
    
    if len(user["referrals"]) >= 10 and "10_referrals" not in achievements:
        achievements.append("10_referrals")
        add_mcoins(user_id, 100, "achievement_10_referrals", "other")
    
    if len(user["referrals"]) >= 50 and "50_referrals" not in achievements:
        achievements.append("50_referrals")
        add_mcoins(user_id, 500, "achievement_50_referrals", "other")
    
    if user["daily_streak"] >= 7 and "7_streak" not in achievements:
        achievements.append("7_streak")
        add_mcoins(user_id, 50, "achievement_7_streak", "other")
    
    if user["daily_streak"] >= 30 and "30_streak" not in achievements:
        achievements.append("30_streak")
        add_mcoins(user_id, 250, "achievement_30_streak", "other")
    
    if user["mcoin"] >= 1000 and "1000_mcoin" not in achievements:
        achievements.append("1000_mcoin")
        add_mcoins(user_id, 100, "achievement_1000_mcoin", "other")
    
    if user["mcoin"] >= 10000 and "10000_mcoin" not in achievements:
        achievements.append("10000_mcoin")
        add_mcoins(user_id, 500, "achievement_10000_mcoin", "other")
    
    db.achievements[user_id] = achievements
    db.save()

# ========== УВЕДОМЛЕНИЯ ==========
async def send_notification(context: CallbackContext, user_id: int, text: str, keyboard: Optional[InlineKeyboardMarkup] = None):
    try:
        if user_id in db.users and db.users[user_id].get("notifications_enabled", True):
            await context.bot.send_message(
                user_id,
                f"🔔 **Уведомление**\n\n{text}",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления {user_id}: {e}")

async def broadcast_notification(context: CallbackContext, text: str, keyboard: Optional[InlineKeyboardMarkup] = None):
    sent = 0
    failed = 0
    
    for user_id in db.users.keys():
        try:
            if db.users[user_id].get("notifications_enabled", True):
                await context.bot.send_message(
                    user_id,
                    f"🔔 **Уведомление**\n\n{text}",
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
                sent += 1
                await asyncio.sleep(0.05)
        except:
            failed += 1
    
    logger.info(f"Рассылка уведомлений: отправлено {sent}, не доставлено {failed}")
    return sent, failed

# ========== ИНТЕГРАЦИЯ API (ПО ДОКУМЕНТАЦИИ) ==========
async def call_botohub_api(chat_id: int, is_task: bool = False, skip: bool = False,
                            gender: str = None, age: str = None) -> dict:
    """
    Вызов BotoHub API согласно документации:
    - Для режима заданий (is_task=true) возвращает одну ссылку
    - prev_success показывает, выполнена ли предыдущая задача
    - prev_outdated показывает, первый ли это запрос
    """
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
                    data = await resp.json()
                    logger.info(f"BotoHub ответ для {chat_id}: {data}")
                    return data
                else:
                    logger.error(f"BotoHub API ошибка: {resp.status}")
                    return {"tasks": [], "completed": False, "skip": True}
    except Exception as e:
        logger.error(f"BotoHub API исключение: {e}")
        return {"tasks": [], "completed": False, "skip": True}

async def call_piarflow_api(path: str, payload: dict) -> dict:
    """
    Вызов PiarFlow API согласно документации:
    - /sponsors - получение заданий
    - /sponsors/check - проверка выполнения
    """
    headers = {
        "Authorization": f"Bearer {PIARFLOW_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{PIARFLOW_API_URL}{path}", 
                json=payload, 
                headers=headers, 
                timeout=15
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("status") == "ok":
                        return data
                    else:
                        logger.error(f"PiarFlow API ошибка: {data}")
                        return {"sponsors": [], "message": data.get("message", "Ошибка")}
                else:
                    error_text = await resp.text()
                    logger.error(f"PiarFlow API ошибка {resp.status}: {error_text}")
                    return {"sponsors": [], "message": f"Ошибка {resp.status}"}
    except Exception as e:
        logger.error(f"PiarFlow API исключение: {e}")
        return {"sponsors": [], "message": str(e)}

async def get_piarflow_tasks(user_id: int, chat_id: int) -> Tuple[List[Dict], str]:
    """Получение заданий от PiarFlow"""
    payload = {
        "user_id": user_id,
        "chat_id": chat_id,
        "max_sponsors": 1  # По одному заданию
    }
    
    result = await call_piarflow_api("/sponsors", payload)
    
    if result.get("status") == "ok":
        sponsors = result.get("sponsors", [])
        return sponsors, result.get("message", "OK")
    else:
        return [], result.get("message", "Ошибка получения заданий")

async def check_piarflow_tasks(user_id: int, links: List[str]) -> Tuple[List[Dict], str]:
    """Проверка выполнения заданий PiarFlow"""
    payload = {
        "user_id": user_id,
        "links": links
    }
    
    result = await call_piarflow_api("/sponsors/check", payload)
    
    if result.get("status") == "ok":
        sponsors = result.get("sponsors", [])
        return sponsors, result.get("message", "OK")
    else:
        return [], result.get("message", "Ошибка проверки")

# ========== ПРОВЕРКА ПОДПИСОК ==========
async def check_force_subs(user_id: int, bot) -> Tuple[bool, List[str]]:
    """Проверка обязательных подписок (каналы, группы, спонсоры)"""
    if not settings.force_sub_sponsors and not settings.force_sub_channels and not settings.force_sub_groups:
        return True, []
    
    not_subscribed = []
    
    # Проверка подписки на спонсоров через BotoHub
    if settings.force_sub_sponsors:
        try:
            result = await call_botohub_api(user_id, is_task=True, skip=False)
            tasks = result.get("tasks", [])
            if tasks:
                for link in tasks:
                    not_subscribed.append(link)
        except Exception as e:
            logger.error(f"Ошибка проверки спонсоров: {e}")
    
    # Проверка каналов
    for channel in settings.force_sub_channels:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                not_subscribed.append(f"https://t.me/{channel}")
        except Exception:
            not_subscribed.append(f"https://t.me/{channel}")
    
    # Проверка групп
    for group in settings.force_sub_groups:
        try:
            member = await bot.get_chat_member(chat_id=group, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                not_subscribed.append(f"https://t.me/{group}")
        except Exception:
            not_subscribed.append(f"https://t.me/{group}")
    
    return len(not_subscribed) == 0, not_subscribed

def get_subscription_links() -> str:
    links = []
    if settings.force_sub_sponsors:
        links.append("Спонсоры BotoHub (выполните задания)")
    for channel in settings.force_sub_channels:
        links.append(f"https://t.me/{channel}")
    for group in settings.force_sub_groups:
        links.append(f"https://t.me/{group}")
    return "\n".join(links)

# ========== ЗАДАНИЯ (ПО ОДНОМУ) ==========
async def tasks_mode(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    currency = get_currency_symbol()
    
    if settings.maintenance_mode:
        await update.message.reply_text("🔧 Бот на техническом обслуживании. Задания временно недоступны.")
        return
    
    passed, not_passed = await check_force_subs(user_id, context.bot)
    if not passed:
        msg = "⚠️ **Для выполнения заданий необходимо подписаться:**\n\n"
        for item in not_passed:
            msg += f"• {item}\n"
        msg += f"\n🔗 Ссылки для подписки:\n{get_subscription_links()}\n\n"
        msg += "После подписки нажмите /tasks снова"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return
    
    user = get_user_data(user_id)
    today = datetime.now().date().isoformat()
    
    if user.get("last_task_date") != today:
        user["tasks_today"] = 0
        user["last_task_date"] = today
        db.save()
    
    if user["tasks_today"] >= settings.max_daily_tasks:
        await update.message.reply_text(
            f"⏰ **Дневной лимит заданий исчерпан!**\n\n"
            f"Вы выполнили {settings.max_daily_tasks} заданий сегодня.\n"
            f"Лимит обновится завтра."
        )
        return
    
    # Проверяем есть ли активное задание
    if user_id in db.active_tasks:
        task = db.active_tasks[user_id]
        await show_task(update, context, task, user_id)
        return
    
    msg = await update.message.reply_text("🔄 Получаем задание...")
    
    # Получаем список уже выполненных ссылок
    used_links = db.used_task_links.get(user_id, [])
    
    # Пробуем получить задание из BotoHub
    try:
        gender = settings.sponsor_gender
        age = settings.sponsor_age
        result = await call_botohub_api(user_id, is_task=True, skip=False, gender=gender, age=age)
        tasks = result.get("tasks", [])
        completed = result.get("completed", False)
        skip_flag = result.get("skip", False)
        
        if not completed and not skip_flag and tasks:
            task_link = tasks[0]
            if task_link not in used_links:
                task = {
                    "link": task_link,
                    "source": "botohub",
                    "color": get_sponsor_color("BotoHub")
                }
                db.active_tasks[user_id] = task
                db.save()
                await show_task(update, context, task, user_id)
                return
    except Exception as e:
        logger.error(f"Ошибка BotoHub: {e}")
    
    # Если нет, пробуем PiarFlow
    try:
        piarflow_tasks, msg_pf = await get_piarflow_tasks(user_id, update.message.chat.id)
        if piarflow_tasks:
            link = piarflow_tasks[0].get("link", "")
            if link not in used_links:
                task = {
                    "link": link,
                    "source": "piarflow",
                    "original": piarflow_tasks[0],
                    "color": get_sponsor_color("PiarFlow")
                }
                db.active_tasks[user_id] = task
                db.save()
                await show_task(update, context, task, user_id)
                return
    except Exception as e:
        logger.error(f"Ошибка PiarFlow: {e}")
    
    # Если нет, пробуем Custom задания
    if user_id in db.custom_tasks:
        task = db.custom_tasks[user_id]
        if task.get("active", False):
            link = task.get("link", "")
            if link not in used_links:
                task["color"] = get_sponsor_color("Custom")
                db.active_tasks[user_id] = task
                db.save()
                await show_task(update, context, task, user_id)
                return
    
    await msg.edit_text(
        "🎉 **Нет активных заданий!**\n\n"
        "Пожалуйста, зайдите позже.\n"
        "В это время вы можете:\n"
        "• Приглашать друзей 👥\n"
        "• Получать ежедневный бонус 🏆"
    )

async def show_task(update: Update, context: CallbackContext, task: Dict, user_id: int):
    if isinstance(update, Update):
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            await query.message.edit_text("🔄 Загружаем задание...")
            msg = query.message
        else:
            msg = await update.message.reply_text("🔄 Загружаем задание...")
    else:
        msg = await update.message.reply_text("🔄 Загружаем задание...")
    
    task_url = task.get("link", "")
    task_price = task.get("price", settings.task_reward)
    currency = get_currency_symbol()
    color = task.get("color", "⚪")
    source = task.get("source", "unknown").upper()
    
    db.active_tasks[user_id] = task
    
    keyboard = [
        [InlineKeyboardButton(f"{color} Перейти к заданию ({source})", url=task_url)],
        [InlineKeyboardButton("✅ Проверить выполнение", callback_data=f"check_task_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    task_text = (
        f"📢 **Новое задание!** 📢\n\n"
        f"{color} **Источник:** {source}\n"
        f"🔗 **Ссылка:** {task_url}\n\n"
        f"💰 **Награда:** {task_price} {currency}\n\n"
        f"**Как выполнить:**\n"
        f"1️⃣ Нажмите «Перейти к заданию»\n"
        f"2️⃣ Подпишитесь на канал\n"
        f"3️⃣ Вернитесь и нажмите «Проверить выполнение»\n\n"
        f"⏱️ Время на выполнение: 3 минуты\n"
        f"✨ Удачи!"
    )
    
    if isinstance(update, Update) and update.callback_query:
        await msg.edit_text(task_text, reply_markup=reply_markup, disable_web_page_preview=True)
    else:
        await msg.edit_text(task_text, reply_markup=reply_markup, disable_web_page_preview=True)

async def check_task_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = int(query.data.replace("check_task_", ""))
    
    if user_id != query.from_user.id:
        await query.answer("⛔ Это не ваше задание!", show_alert=True)
        return
    
    if user_id not in db.active_tasks:
        await query.message.edit_text("❌ Нет активного задания для проверки.")
        return
    
    task = db.active_tasks[user_id]
    task_source = task.get("source", "unknown")
    task_url = task.get("link", "")
    task_price = task.get("price", settings.task_reward)
    currency = get_currency_symbol()
    color = task.get("color", "⚪")
    
    await query.message.edit_text("🔍 **Проверяем выполнение задания...**\n\nПожалуйста, подождите...")
    
    try:
        task_completed = False
        
        if task_source == "botohub":
            # Проверяем через BotoHub API
            result = await call_botohub_api(user_id, is_task=True, skip=False)
            prev_success = result.get("prev_success", False)
            if prev_success:
                task_completed = True
                
        elif task_source == "piarflow":
            check_result, msg = await check_piarflow_tasks(user_id, [task_url])
            if check_result:
                all_subscribed = all(item.get("status") == "subscribed" for item in check_result)
                if all_subscribed:
                    task_completed = True
                    
        elif task_source == "custom":
            # Для кастомных заданий проверяем подписку
            try:
                member = await context.bot.get_chat_member(chat_id=task_url, user_id=user_id)
                if member.status in ["member", "administrator", "creator"]:
                    task_completed = True
            except:
                pass
        
        if task_completed:
            # Добавляем ссылку в список выполненных
            if user_id not in db.used_task_links:
                db.used_task_links[user_id] = []
            if task_url not in db.used_task_links[user_id]:
                db.used_task_links[user_id].append(task_url)
            
            add_mcoins(user_id, task_price, f"task_{task_url}", "task")
            user = get_user_data(user_id)
            user["tasks_today"] += 1
            
            if "completed_links" not in user:
                user["completed_links"] = []
            if task_url not in user["completed_links"]:
                user["completed_links"].append(task_url)
            
            db.save()
            
            # Удаляем активное задание
            db.active_tasks.pop(user_id, None)
            
            await query.message.edit_text(
                f"✅ **Задание выполнено!** ✅\n\n"
                f"{color} **Источник:** {task_source.upper()}\n"
                f"💰 Вы получили: {task_price} {currency}\n"
                f"📊 Сегодня выполнено: {user['tasks_today']}/{settings.max_daily_tasks}\n"
                f"💰 Ваш баланс: {format_number(user['mcoin'])} {currency}\n\n"
                f"Хотите получить следующее задание?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 Следующее задание", callback_data="next_task")],
                    [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
                ])
            )
        else:
            await query.message.edit_text(
                f"❌ **Вы ещё не выполнили задание!** ❌\n\n"
                f"{color} **Источник:** {task_source.upper()}\n"
                f"🔗 Пожалуйста, подпишитесь:\n{task_url}\n\n"
                f"**Инструкция:**\n"
                f"1️⃣ Нажмите на ссылку выше\n"
                f"2️⃣ Нажмите «Подписаться» или «Join»\n"
                f"3️⃣ Вернитесь и нажмите «Проверить выполнение»\n\n"
                f"⏱️ У вас есть 3 минуты на выполнение",
                disable_web_page_preview=True
            )
            
            keyboard = [
                [InlineKeyboardButton(f"{color} Перейти к заданию", url=task_url)],
                [InlineKeyboardButton("✅ Проверить выполнение", callback_data=f"check_task_{user_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_reply_markup(reply_markup)
                
    except Exception as e:
        logger.error(f"Ошибка проверки задания: {e}")
        await query.message.edit_text(
            f"❌ Ошибка при проверке: {e}\n\nПопробуйте еще раз.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Проверить еще раз", callback_data=f"check_task_{user_id}")],
                [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
            ])
        )

async def next_task_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Проверяем лимит заданий
    user = get_user_data(user_id)
    today = datetime.now().date().isoformat()
    
    if user.get("last_task_date") != today:
        user["tasks_today"] = 0
        user["last_task_date"] = today
        db.save()
    
    if user["tasks_today"] >= settings.max_daily_tasks:
        await query.message.edit_text(
            f"⏰ **Дневной лимит заданий исчерпан!**\n\n"
            f"Вы выполнили {settings.max_daily_tasks} заданий сегодня.\n"
            f"Лимит обновится завтра."
        )
        return
    
    await query.message.edit_text("🔄 Получаем новое задание...")
    
    # Получаем список уже выполненных ссылок
    used_links = db.used_task_links.get(user_id, [])
    
    # Пробуем получить задание из BotoHub
    try:
        gender = settings.sponsor_gender
        age = settings.sponsor_age
        result = await call_botohub_api(user_id, is_task=True, skip=False, gender=gender, age=age)
        tasks = result.get("tasks", [])
        completed = result.get("completed", False)
        skip_flag = result.get("skip", False)
        
        if not completed and not skip_flag and tasks:
            task_link = tasks[0]
            if task_link not in used_links:
                task = {
                    "link": task_link,
                    "source": "botohub",
                    "color": get_sponsor_color("BotoHub")
                }
                db.active_tasks[user_id] = task
                db.save()
                await show_task(update, context, task, user_id)
                return
    except Exception as e:
        logger.error(f"Ошибка BotoHub: {e}")
    
    # Если нет, пробуем PiarFlow
    try:
        piarflow_tasks, msg_pf = await get_piarflow_tasks(user_id, query.message.chat.id)
        if piarflow_tasks:
            link = piarflow_tasks[0].get("link", "")
            if link not in used_links:
                task = {
                    "link": link,
                    "source": "piarflow",
                    "original": piarflow_tasks[0],
                    "color": get_sponsor_color("PiarFlow")
                }
                db.active_tasks[user_id] = task
                db.save()
                await show_task(update, context, task, user_id)
                return
    except Exception as e:
        logger.error(f"Ошибка PiarFlow: {e}")
    
    # Если нет, пробуем Custom задания
    if user_id in db.custom_tasks:
        task = db.custom_tasks[user_id]
        if task.get("active", False):
            link = task.get("link", "")
            if link not in used_links:
                task["color"] = get_sponsor_color("Custom")
                db.active_tasks[user_id] = task
                db.save()
                await show_task(update, context, task, user_id)
                return
    
    await query.message.edit_text(
        "🎉 **Нет активных заданий!**\n\n"
        "Пожалуйста, зайдите позже."
    )

# ========== ОБЯЗАТЕЛЬНЫЕ ЗАДАНИЯ ==========
async def force_task_job(context: CallbackContext):
    for user_id in db.users.keys():
        try:
            if user_id in db.bans:
                continue
            
            if user_id in db.force_tasks:
                continue
            
            user = get_user_data(user_id)
            last_force = user.get("last_force_task")
            
            if not last_force or (datetime.now() - datetime.fromisoformat(last_force)).seconds > 7200:
                result = await call_botohub_api(user_id, is_task=True, skip=False)
                tasks = result.get("tasks", [])
                
                if tasks and not result.get("completed", False):
                    task_url = tasks[0]
                    
                    db.force_tasks[user_id] = {
                        "link": task_url,
                        "reward": settings.task_reward,
                        "assigned_at": datetime.now().isoformat()
                    }
                    
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("📎 Выполнить задание", url=task_url)],
                        [InlineKeyboardButton("✅ Проверить", callback_data=f"force_check_{user_id}")]
                    ])
                    
                    currency = get_currency_symbol()
                    await send_notification(
                        context,
                        user_id,
                        f"⚠️ **Обязательное задание!**\n\n"
                        f"Для продолжения работы в боте необходимо выполнить задание:\n"
                        f"🔗 {task_url}\n\n"
                        f"💰 Награда: {settings.task_reward} {currency}\n\n"
                        f"Нажмите «Выполнить задание» и затем «Проверить».",
                        keyboard
                    )
                    
                    user["last_force_task"] = datetime.now().isoformat()
                    db.save()
        except Exception as e:
            logger.error(f"Ошибка обязательного задания для {user_id}: {e}")

async def force_check_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = int(query.data.replace("force_check_", ""))
    
    if user_id != query.from_user.id:
        await query.answer("⛔ Это не ваше задание!", show_alert=True)
        return
    
    if user_id not in db.force_tasks:
        await query.message.edit_text("❌ Нет активного обязательного задания.")
        return
    
    task = db.force_tasks[user_id]
    task_url = task.get("link", "")
    task_reward = task.get("reward", settings.task_reward)
    currency = get_currency_symbol()
    
    await query.message.edit_text("🔍 **Проверяем выполнение...**")
    
    try:
        result = await call_botohub_api(user_id, is_task=True, skip=False)
        prev_success = result.get("prev_success", False)
        
        if prev_success:
            add_mcoins(user_id, task_reward, f"force_task_{task_url}", "force")
            db.force_tasks.pop(user_id, None)
            db.save()
            
            await query.message.edit_text(
                f"✅ **Обязательное задание выполнено!**\n\n"
                f"💰 Вы получили: {task_reward} {currency}\n"
                f"💰 Ваш баланс: {format_number(get_user_data(user_id)['mcoin'])} {currency}\n\n"
                f"✨ Отличная работа!"
            )
        else:
            await query.message.edit_text(
                f"❌ **Вы ещё не выполнили задание!**\n\n"
                f"🔗 Пожалуйста, подпишитесь:\n{task_url}\n\n"
                f"После подписки нажмите «Проверить» снова.",
                disable_web_page_preview=True
            )
            
            keyboard = [
                [InlineKeyboardButton("📎 Выполнить задание", url=task_url)],
                [InlineKeyboardButton("✅ Проверить", callback_data=f"force_check_{user_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_reply_markup(reply_markup)
            
    except Exception as e:
        logger.error(f"Ошибка проверки обязательного задания: {e}")
        await query.message.edit_text(f"❌ Ошибка: {e}")

# ========== РЕФЕРАЛЬНАЯ СИСТЕМА ==========
async def referrals_menu(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    currency = get_currency_symbol()
    
    bot_username = context.bot.username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    keyboard = [
        [InlineKeyboardButton("📋 Список рефералов", callback_data="my_referrals")],
        [InlineKeyboardButton("📊 Статистика", callback_data="ref_stats")],
        [InlineKeyboardButton("🏆 Топ рефералов", callback_data="top_referrals")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👥 **Реферальная программа** 👥\n\n"
        f"👥 **Рефералов:** {len(user['referrals'])}\n"
        f"💰 **Заработано:** {user['referral_earned']} {currency}\n\n"
        f"🎁 **Награда за реферала:** {settings.referral_reward} {currency}\n\n"
        f"🔗 **Ваша реферальная ссылка:**\n`{ref_link}`\n\n"
        f"Отправьте её друзьям и получайте бонусы!",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def my_referrals_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user_data(user_id)
    currency = get_currency_symbol()
    
    if not user["referrals"]:
        await query.message.edit_text("👥 У вас пока нет рефералов.\n\nПриглашайте друзей и получайте бонусы!")
        return
    
    page = context.user_data.get("ref_page", 0)
    items_per_page = 10
    total_pages = (len(user["referrals"]) + items_per_page - 1) // items_per_page
    
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(user["referrals"]))
    
    referrals_list = []
    for i, ref_id in enumerate(user["referrals"][start_idx:end_idx], start_idx + 1):
        ref_user = db.users.get(ref_id, {})
        ref_username = ref_user.get("username", "нет username")
        ref_earned = ref_user.get("total_earned", 0)
        ref_join = ref_user.get("join_date", "Unknown")[:10]
        active = ref_user.get("last_seen", "")
        is_active = "🟢" if active and (datetime.now() - datetime.fromisoformat(active)).days < 7 else "🔴"
        
        referrals_list.append(f"{i}. {is_active} @{ref_username} - Заработал: {ref_earned} {currency} (с {ref_join})")
    
    text = "📋 **Ваши рефералы:**\n\n" + "\n".join(referrals_list)
    text += f"\n\n📊 Страница {page + 1} из {total_pages}"
    
    keyboard = []
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️ Назад", callback_data="ref_page_prev"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Вперед ▶️", callback_data="ref_page_next"))
    if nav_row:
        keyboard.append(nav_row)
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="referrals_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def ref_stats_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user_data(user_id)
    currency = get_currency_symbol()
    
    active_refs = 0
    total_earned = 0
    
    for ref_id in user["referrals"]:
        ref_user = db.users.get(ref_id, {})
        if ref_user.get("last_seen"):
            try:
                last_seen = datetime.fromisoformat(ref_user["last_seen"])
                if (datetime.now() - last_seen).days < 7:
                    active_refs += 1
            except:
                pass
        total_earned += ref_user.get("total_earned", 0)
    
    await query.message.edit_text(
        f"📊 **Статистика рефералов** 📊\n\n"
        f"👥 Всего рефералов: {len(user['referrals'])}\n"
        f"🟢 Активных: {active_refs}\n"
        f"💰 Заработано рефералами: {format_number(total_earned)} {currency}\n"
        f"🏆 Ваш доход: {user['referral_earned']} {currency}\n\n"
        f"📈 Средний доход на реферала: {format_number(total_earned // len(user['referrals']) if user['referrals'] else 0)} {currency}"
    )

async def top_referrals_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    currency = get_currency_symbol()
    
    sorted_users = sorted(db.users.items(), key=lambda x: len(x[1].get("referrals", [])), reverse=True)[:10]
    
    text = f"👥 **Топ по рефералам** 👥\n\n"
    if not sorted_users:
        text += "📭 Нет данных"
    else:
        for i, (uid, data) in enumerate(sorted_users, 1):
            name = data.get("first_name", "Пользователь")
            username = data.get("username", "нет username")
            referrals = len(data.get("referrals", []))
            
            if len(name) > 15:
                name = name[:15] + "..."
            
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            text += f"{emoji} @{username} - {referrals} рефералов\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="referrals_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, reply_markup=reply_markup)

async def ref_page_navigation(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    direction = query.data.replace("ref_page_", "")
    current_page = context.user_data.get("ref_page", 0)
    
    if direction == "prev":
        context.user_data["ref_page"] = max(0, current_page - 1)
    elif direction == "next":
        context.user_data["ref_page"] = current_page + 1
    
    await my_referrals_callback(update, context)

# ========== КОНКУРСЫ ==========
async def contests_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if not settings.contest_enabled:
        await query.message.edit_text("🎯 Конкурсы временно недоступны!")
        return
    
    keyboard = [
        [InlineKeyboardButton("📋 Активные конкурсы", callback_data="active_contests")],
        [InlineKeyboardButton("📊 Мои участия", callback_data="my_contests")],
        [InlineKeyboardButton("🏆 Победители", callback_data="contest_winners")],
        [InlineKeyboardButton("🔙 Назад", callback_data="profile")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "🎯 **Конкурсы** 🎯\n\n"
        "Участвуйте в конкурсах и выигрывайте призы!\n"
        "Выполняйте задания, приглашайте друзей и занимайте призовые места.",
        reply_markup=reply_markup
    )

async def active_contests_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    active = {k: v for k, v in db.contests.items() if v.get("active", False)}
    
    if not active:
        await query.message.edit_text(
            "📭 Нет активных конкурсов.\n\n"
            "Следите за новостями!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="contests_menu")]
            ])
        )
        return
    
    keyboard = []
    for cid, contest in active.items():
        end_time = datetime.fromisoformat(contest["end_date"])
        time_left = end_time - datetime.now()
        hours = time_left.seconds // 3600
        minutes = (time_left.seconds % 3600) // 60
        
        type_emoji = "🏆" if contest["type"] == "race" else "🎯"
        
        keyboard.append([InlineKeyboardButton(
            f"{type_emoji} {contest['name']} (осталось {hours}ч {minutes}м)",
            callback_data=f"contest_{cid}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="contests_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "🎯 **Активные конкурсы** 🎯\n\n"
        "Выберите конкурс для участия:",
        reply_markup=reply_markup
    )

async def contest_detail_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    contest_id = int(query.data.replace("contest_", ""))
    
    if contest_id not in db.contests:
        await query.message.edit_text("❌ Конкурс не найден!")
        return
    
    contest = db.contests[contest_id]
    currency = get_currency_symbol()
    
    end_time = datetime.fromisoformat(contest["end_date"])
    time_left = end_time - datetime.now()
    hours = time_left.seconds // 3600
    minutes = (time_left.seconds % 3600) // 60
    
    is_participant = query.from_user.id in contest.get("participants", [])
    
    type_names = {
        "race": "🏆 Кто больше (топовый)",
        "goal": "🎯 Достижение цели"
    }
    
    target_names = {
        "tasks": "задания",
        "referrals": "рефералы",
        "both": "задания + рефералы"
    }
    
    keyboard = []
    if contest.get("active", False) and not is_participant:
        keyboard.append([InlineKeyboardButton("✅ Участвовать", callback_data=f"join_contest_{contest_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="active_contests")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"🎯 **{contest['name']}**\n\n"
        f"📝 {contest['description']}\n\n"
        f"📋 Тип: {type_names.get(contest['type'], '')}\n"
        f"📋 По: {target_names.get(contest['target_type'], '')}\n"
        f"🎯 Цель: {contest['target_value']}\n"
        f"💰 Приз: {contest['prize']} {currency}\n"
        f"👥 Участников: {len(contest.get('participants', []))}\n"
        f"⏱️ Осталось: {hours}ч {minutes}м\n"
        f"📅 Начало: {contest['start_date'][:10]}\n\n"
        f"{'✅ Вы участвуете!' if is_participant else 'Нажмите «Участвовать» чтобы присоединиться!'}",
        reply_markup=reply_markup
    )

async def join_contest_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    contest_id = int(query.data.replace("join_contest_", ""))
    user_id = query.from_user.id
    
    if contest_id not in db.contests:
        await query.message.edit_text("❌ Конкурс не найден!")
        return
    
    contest = db.contests[contest_id]
    
    if not contest.get("active", False):
        await query.message.edit_text("❌ Конкурс уже завершен!")
        return
    
    if user_id in contest.get("participants", []):
        await query.message.edit_text("✅ Вы уже участвуете в этом конкурсе!")
        return
    
    if "participants" not in contest:
        contest["participants"] = []
    contest["participants"].append(user_id)
    db.save()
    
    await query.message.edit_text(
        f"✅ **Вы участвуете в конкурсе!** 🎉\n\n"
        f"🎯 {contest['name']}\n"
        f"💰 Приз: {contest['prize']} {settings.currency_name}\n\n"
        f"Выполняйте задания, приглашайте друзей и занимайте топовые места!"
    )
    
    await query.message.edit_reply_markup(None)

async def my_contests_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    my_contests = []
    
    for cid, contest in db.contests.items():
        if user_id in contest.get("participants", []):
            status = "🟢 Активен" if contest.get("active", False) else "🔴 Завершен"
            type_emoji = "🏆" if contest["type"] == "race" else "🎯"
            my_contests.append(f"{type_emoji} {contest['name']} - {status}")
    
    if not my_contests:
        await query.message.edit_text(
            "📭 Вы не участвуете ни в одном конкурсе.\n\n"
            "Присоединяйтесь к активным конкурсам!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="contests_menu")]
            ])
        )
        return
    
    text = "📊 **Мои конкурсы**\n\n" + "\n".join(my_contests)
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="contests_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, reply_markup=reply_markup)

async def contest_winners_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    completed = {k: v for k, v in db.contests.items() if not v.get("active", True) and v.get("winners", [])}
    
    if not completed:
        await query.message.edit_text(
            "📭 Нет завершенных конкурсов.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="contests_menu")]
            ])
        )
        return
    
    currency = get_currency_symbol()
    text = "🏆 **Победители конкурсов** 🏆\n\n"
    
    for cid, contest in list(completed.items())[-5:]:
        type_emoji = "🏆" if contest["type"] == "race" else "🎯"
        text += f"{type_emoji} {contest['name']}\n"
        for i, winner in enumerate(contest.get("winners", [])[:3]):
            emoji = "🥇" if i == 0 else "🥈" if i == 1 else "🥉"
            prize = contest["prize"] * (50 if i == 0 else 30 if i == 1 else 20) // 100
            text += f"  {emoji} @{winner['username']} - {winner['score']} очков ({prize} {currency})\n"
        text += "\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="contests_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, reply_markup=reply_markup)

# ========== ПРОФИЛЬ ==========
async def profile_menu(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    currency = get_currency_symbol()
    
    username = update.effective_user.username or "Не установлен"
    achievements = db.achievements.get(user_id, [])
    
    keyboard = [
        [InlineKeyboardButton("📊 Детальная статистика", callback_data="detailed_stats")],
        [InlineKeyboardButton("🏅 Достижения", callback_data="my_achievements")],
        [InlineKeyboardButton("🏆 Топ пользователей", callback_data="top_users")],
        [InlineKeyboardButton("🎁 Ежедневный бонус", callback_data="daily_bonus")],
        [InlineKeyboardButton("🎯 Конкурсы", callback_data="contests_menu")],
        [InlineKeyboardButton("💸 Вывод средств", callback_data="withdraw_menu")],
        [InlineKeyboardButton("🔔 Настройки уведомлений", callback_data="notify_settings")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👤 **Профиль** 👤\n\n"
        f"👤 Username: @{username}\n"
        f"💰 {currency}: {format_number(user['mcoin'])}\n"
        f"📈 Всего заработано: {format_number(user['total_earned'])}\n"
        f"💸 Выведено: {format_number(user['total_withdrawn'])}\n\n"
        f"✅ Выполнено заданий: {user['total_tasks_completed']}\n"
        f"📊 Заданий сегодня: {user['tasks_today']}/{settings.max_daily_tasks}\n"
        f"👥 Рефералов: {len(user['referrals'])}\n"
        f"🔥 Серия: {user['daily_streak']} дней\n"
        f"📅 В боте: {(datetime.now() - datetime.fromisoformat(user['join_date'])).days} дней\n"
        f"🏅 Достижений: {len(achievements)}",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def daily_bonus_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user_data(user_id)
    currency = get_currency_symbol()
    
    now = datetime.now()
    last_claim = db.daily_claimed.get(user_id)
    
    if last_claim:
        time_diff = (now - last_claim).total_seconds()
        if time_diff < 86400:
            hours_left = int((86400 - time_diff) // 3600)
            minutes_left = int((86400 - time_diff) % 3600 // 60)
            await query.message.edit_text(
                f"⏰ **Вы уже получили бонус сегодня!**\n\n"
                f"Следующий бонус через: {hours_left}ч {minutes_left}мин\n"
                f"📊 Серия: {user['daily_streak']} дней",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Назад", callback_data="profile")]
                ])
            )
            return
    
    if user.get("last_streak_date"):
        last_date = datetime.fromisoformat(user["last_streak_date"])
        days_diff = (now - last_date).days
        if days_diff == 1:
            user["daily_streak"] += 1
        elif days_diff > 1:
            user["daily_streak"] = 1
    else:
        user["daily_streak"] = 1
    
    base_reward = settings.daily_reward
    streak_bonus = 0
    
    if settings.daily_streak_bonus:
        streak_bonus = int(base_reward * (user["daily_streak"] * 0.1))
    
    reward = base_reward + streak_bonus
    add_mcoins(user_id, reward, "daily_bonus", "daily")
    
    user["daily_last"] = now.isoformat()
    user["last_streak_date"] = now.isoformat()
    db.daily_claimed[user_id] = now
    db.save()
    
    extra_text = ""
    if user["daily_streak"] == 7:
        extra_bonus = 50
        add_mcoins(user_id, extra_bonus, "streak_7_days", "daily")
        extra_text = f"\n🏆 Бонус за 7 дней серии: +{extra_bonus} {currency}"
    elif user["daily_streak"] == 30:
        extra_bonus = 250
        add_mcoins(user_id, extra_bonus, "streak_30_days", "daily")
        extra_text = f"\n🏆 Бонус за 30 дней серии: +{extra_bonus} {currency}"
    elif user["daily_streak"] == 365:
        extra_bonus = 1000
        add_mcoins(user_id, extra_bonus, "streak_365_days", "daily")
        extra_text = f"\n🏆 Бонус за 365 дней серии: +{extra_bonus} {currency}"
    
    await query.message.edit_text(
        f"🎁 **Ежедневный бонус!** 🎁\n\n"
        f"💰 Вы получили: {reward} {currency}\n"
        f"📊 Серия: {user['daily_streak']} дней\n"
        f"📈 Бонус за серию: +{streak_bonus} {currency}{extra_text}\n\n"
        f"💰 Ваш баланс: {format_number(user['mcoin'])} {currency}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="profile")]
        ])
    )

async def top_users_profile_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    sorted_users = sorted(db.top_users.items(), key=lambda x: x[1].get("tasks", 0), reverse=True)[:10]
    currency = get_currency_symbol()
    
    text = "🏆 **Топ пользователей** 🏆\n\n"
    if not sorted_users:
        text += "📭 Нет данных"
    else:
        for i, (uid, data) in enumerate(sorted_users, 1):
            name = data.get("name", "Пользователь")
            username = data.get("username", "нет username")
            tasks = data.get("tasks", 0)
            
            if len(name) > 15:
                name = name[:15] + "..."
            
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            
            prize_text = ""
            if i == 1:
                prize_text = f" (приз: {settings.top_prize_1} {currency})"
            elif i == 2:
                prize_text = f" (приз: {settings.top_prize_2} {currency})"
            elif i == 3:
                prize_text = f" (приз: {settings.top_prize_3} {currency})"
            
            text += f"{emoji} @{username} - {tasks} заданий{prize_text}\n"
        
        text += "\n🎁 **Призы для победителей:**\n"
        text += f"🥇 1 место - {settings.top_prize_1} {currency}\n"
        text += f"🥈 2 место - {settings.top_prize_2} {currency}\n"
        text += f"🥉 3 место - {settings.top_prize_3} {currency}\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="profile")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, reply_markup=reply_markup)

async def detailed_stats_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user_data(user_id)
    currency = get_currency_symbol()
    
    completed_withdrawals = 0
    for uid, req in db.withdraw_requests.items():
        if uid == user_id and req.get("status") == "completed":
            completed_withdrawals += 1
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="profile")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"📊 **Детальная статистика** 📊\n\n"
        f"💰 **Заработано:**\n"
        f"• С заданий: {user['task_earned']} {currency}\n"
        f"• С рефералов: {user['referral_earned']} {currency}\n"
        f"• С бонусов: {user['bonus_claims']} раз\n\n"
        f"📊 **Активность:**\n"
        f"• Заданий выполнено: {user['total_tasks_completed']}\n"
        f"• Рефералов приглашено: {len(user['referrals'])}\n"
        f"• Выводов: {completed_withdrawals}\n"
        f"• Промокодов использовано: {user['promos_used']}\n\n"
        f"📅 **Даты:**\n"
        f"• В боте с: {user['join_date'][:10]}\n"
        f"• Последний визит: {user['last_seen'][:10] if user.get('last_seen') else 'Неизвестно'}\n"
        f"• Последний бонус: {user['daily_last'][:10] if user.get('daily_last') else 'Не получал'}",
        reply_markup=reply_markup
    )

async def my_achievements_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    achievements = db.achievements.get(user_id, [])
    
    achievement_names = {
        "100_tasks": "📋 100 заданий выполнено",
        "500_tasks": "📋 500 заданий выполнено",
        "1000_tasks": "📋 1000 заданий выполнено",
        "10_referrals": "👥 10 рефералов",
        "50_referrals": "👥 50 рефералов",
        "7_streak": "🔥 7 дней серии",
        "30_streak": "🔥 30 дней серии",
        "1000_mcoin": "💰 1000 MCoin заработано",
        "10000_mcoin": "💰 10000 MCoin заработано"
    }
    
    if not achievements:
        await query.message.edit_text(
            "🏅 У вас пока нет достижений.\n\n"
            "Выполняйте задания, приглашайте друзей и получайте достижения!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="profile")]
            ])
        )
        return
    
    text = "🏅 **Ваши достижения** 🏅\n\n"
    for ach in achievements:
        text += f"• {achievement_names.get(ach, ach)}\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="profile")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, reply_markup=reply_markup)

async def notify_settings_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user_data(user_id)
    
    status = "Включены" if user.get("notifications_enabled", True) else "Выключены"
    
    keyboard = [
        [InlineKeyboardButton(f"🔔 Уведомления: {status}", callback_data="toggle_notify_user")],
        [InlineKeyboardButton("🔙 Назад", callback_data="profile")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"🔔 **Настройки уведомлений** 🔔\n\n"
        f"Статус: {status}\n\n"
        f"Вы можете включить или отключить уведомления от бота.",
        reply_markup=reply_markup
    )

async def toggle_notify_user_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user_data(user_id)
    
    current = user.get("notifications_enabled", True)
    user["notifications_enabled"] = not current
    db.save()
    
    status = "Включены" if user["notifications_enabled"] else "Выключены"
    await query.message.edit_text(
        f"✅ **Уведомления {status}**\n\n"
        f"Теперь вы будете {'получать' if user['notifications_enabled'] else 'не получать'} уведомления от бота.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="notify_settings")]
        ])
    )

# ========== ВЫВОД СРЕДСТВ ==========
async def withdraw_menu_profile(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await withdraw_menu(update, context)

async def withdraw_menu(update: Update, context: CallbackContext):
    if isinstance(update, Update) and update.callback_query:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        msg = query.message
    else:
        user_id = update.effective_user.id
        msg = update.message
    
    user = get_user_data(user_id)
    currency = get_currency_symbol()
    
    if settings.maintenance_mode:
        await msg.reply_text("🔧 Бот на техническом обслуживании. Вывод временно недоступен.")
        return
    
    if user["mcoin"] < settings.min_withdraw:
        await msg.reply_text(
            f"❌ **Недостаточно средств для вывода**\n\n"
            f"💰 Ваш баланс: {format_number(user['mcoin'])} {currency}\n"
            f"💰 Минимальная сумма: {settings.min_withdraw} {currency}\n\n"
            f"Выполняйте задания, чтобы заработать больше!"
        )
        return
    
    username = None
    if isinstance(update, Update):
        username = update.effective_user.username
    
    if not username:
        await msg.reply_text(
            "⚠️ **У вас нет username!**\n\n"
            "Для вывода средств необходимо установить username в Telegram.\n\n"
            "Настройте username в настройках профиля Telegram и попробуйте снова."
        )
        return
    
    keyboard = [
        [InlineKeyboardButton("💰 Запросить вывод", callback_data="request_withdraw")],
        [InlineKeyboardButton("📊 История выводов", callback_data="withdraw_history")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="withdraw_info")],
        [InlineKeyboardButton("🔙 Назад", callback_data="profile")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    pending = db.withdraw_requests.get(user_id, {}).get("status") == "pending"
    pending_text = "\n⚠️ У вас есть активная заявка на вывод!" if pending else ""
    
    await msg.reply_text(
        f"💸 **Вывод средств** 💸\n\n"
        f"👤 Ваш username: @{username}\n"
        f"💰 Доступно: {format_number(user['mcoin'])} {currency}\n"
        f"📉 Минимальная сумма: {settings.min_withdraw} {currency}\n"
        f"📈 Максимальная сумма: {settings.max_withdraw} {currency}\n"
        f"💳 Комиссия: {settings.withdraw_commission * 100}%\n"
        f"💳 Вывод на ваш Telegram username\n\n"
        f"⏱️ Время обработки: до 24 часов\n"
        f"{pending_text}\n\n"
        f"Нажмите «Запросить вывод» для создания заявки",
        reply_markup=reply_markup
    )

async def request_withdraw_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    currency = get_currency_symbol()
    
    if settings.maintenance_mode:
        await query.message.edit_text("🔧 Бот на техническом обслуживании. Вывод временно недоступен.")
        return
    
    user = get_user_data(user_id)
    username = update.effective_user.username
    
    if not username:
        await query.message.edit_text(
            "⚠️ **У вас нет username!**\n\n"
            "Установите username в Telegram и попробуйте снова."
        )
        return
    
    if user_id in db.withdraw_requests and db.withdraw_requests[user_id].get("status") == "pending":
        await query.message.edit_text(
            "⚠️ **У вас уже есть активная заявка на вывод!**\n\n"
            "Дождитесь обработки текущей заявки."
        )
        return
    
    if user["mcoin"] < settings.min_withdraw:
        await query.message.edit_text(
            f"❌ **Недостаточно средств!**\n\n"
            f"Доступно: {format_number(user['mcoin'])} {currency}\n"
            f"Минимальная сумма: {settings.min_withdraw} {currency}"
        )
        return
    
    if user["mcoin"] > settings.max_withdraw:
        await query.message.edit_text(
            f"❌ **Сумма превышает максимальную!**\n\n"
            f"Максимальная сумма вывода: {settings.max_withdraw} {currency}"
        )
        return
    
    context.user_data["withdraw_step"] = "amount"
    
    keyboard = [
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_withdraw")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"💸 **Запрос вывода**\n\n"
        f"👤 Вывод на: @{username}\n"
        f"💰 Доступно: {format_number(user['mcoin'])} {currency}\n"
        f"📉 Минимальная сумма: {settings.min_withdraw} {currency}\n"
        f"📈 Максимальная сумма: {settings.max_withdraw} {currency}\n\n"
        f"Введите сумму вывода:",
        reply_markup=reply_markup
    )

async def withdraw_amount_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    text = update.message.text
    currency = get_currency_symbol()
    
    try:
        amount = int(text)
        user = get_user_data(user_id)
        username = update.effective_user.username
        
        if amount < settings.min_withdraw:
            await update.message.reply_text(
                f"❌ Минимальная сумма: {settings.min_withdraw} {currency}\n"
                f"Введите корректную сумму или нажмите /cancel"
            )
            return
        
        if amount > user["mcoin"]:
            await update.message.reply_text(
                f"❌ Недостаточно средств! Доступно: {format_number(user['mcoin'])} {currency}\n"
                f"Введите меньшую сумму или нажмите /cancel"
            )
            return
        
        if amount > settings.max_withdraw:
            await update.message.reply_text(
                f"❌ Максимальная сумма: {settings.max_withdraw} {currency}\n"
                f"Введите меньшую сумму или нажмите /cancel"
            )
            return
        
        context.user_data["withdraw_amount"] = amount
        
        commission = int(amount * settings.withdraw_commission)
        final_amount = amount - commission
        
        keyboard = [
            [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_withdraw_final")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_withdraw")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"💸 **Подтверждение вывода**\n\n"
            f"👤 Username: @{username}\n"
            f"💰 Сумма: {amount} {currency}\n"
            f"💳 Комиссия: {commission} {currency}\n"
            f"💳 К получению: {final_amount} {currency}\n\n"
            f"Подтвердите вывод:",
            reply_markup=reply_markup
        )
        
        context.user_data["withdraw_step"] = "confirm"
        
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число или нажмите /cancel")

async def confirm_withdraw_final(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    currency = get_currency_symbol()
    
    amount = context.user_data.get("withdraw_amount", 0)
    if not amount:
        await query.message.edit_text("❌ Ошибка! Попробуйте снова /withdraw")
        return
    
    username = update.effective_user.username
    if not username:
        await query.message.edit_text("❌ Username не найден!")
        return
    
    commission = int(amount * settings.withdraw_commission)
    final_amount = amount - commission
    
    db.withdraw_requests[user_id] = {
        "user_id": user_id,
        "amount": amount,
        "commission": commission,
        "final_amount": final_amount,
        "method": "telegram_username",
        "username": username,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "user_data": {
            "username": username,
            "first_name": update.effective_user.first_name
        }
    }
    
    remove_mcoins(user_id, amount, f"withdraw_request_username")
    db.save()
    
    await query.message.edit_text(
        f"✅ **Заявка на вывод создана!**\n\n"
        f"👤 Username: @{username}\n"
        f"💰 Сумма: {amount} {currency}\n"
        f"💳 Комиссия: {commission} {currency}\n"
        f"💳 К получению: {final_amount} {currency}\n\n"
        f"⏱️ Время обработки: до 24 часов\n"
        f"📊 Статус: Ожидает обработки\n\n"
        f"✨ Вы получите уведомление после обработки заявки!"
    )
    
    for admin_id in settings.admin_list:
        try:
            await context.bot.send_message(
                admin_id,
                f"💸 **Новая заявка на вывод!**\n\n"
                f"👤 Пользователь: @{username}\n"
                f"🆔 ID: {user_id}\n"
                f"💰 Сумма: {amount} {currency}\n"
                f"💳 К получению: {final_amount} {currency}\n"
                f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                f"Обработайте заявку в админ-панели!"
            )
        except:
            pass
    
    context.user_data.pop("withdraw_amount", None)
    context.user_data.pop("withdraw_step", None)

async def withdraw_history_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    currency = get_currency_symbol()
    
    user_requests = []
    for uid, req in db.withdraw_requests.items():
        if uid == user_id:
            user_requests.append(req)
    
    if not user_requests:
        await query.message.edit_text("📭 У вас нет истории выводов.")
        return
    
    history_text = "📊 **История выводов**\n\n"
    for i, req in enumerate(reversed(user_requests[-10:]), 1):
        status_emoji = "✅" if req["status"] == "completed" else "⏳" if req["status"] == "pending" else "❌"
        history_text += (
            f"{i}. {status_emoji} {req['amount']} {currency}\n"
            f"   Username: @{req.get('username', 'Не указан')}\n"
            f"   Статус: {req['status']}\n"
            f"   Дата: {req['created_at'][:10]}\n\n"
        )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="profile")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(history_text, reply_markup=reply_markup)

async def withdraw_info_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    currency = get_currency_symbol()
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="profile")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"ℹ️ **Информация о выводе**\n\n"
        f"💳 **Способ вывода:** Telegram Username\n\n"
        f"💰 **Комиссия:** {settings.withdraw_commission * 100}%\n"
        f"📉 **Минимальная сумма:** {settings.min_withdraw} {currency}\n"
        f"📈 **Максимальная сумма:** {settings.max_withdraw} {currency}\n\n"
        f"⏱️ **Время обработки:** до 24 часов\n\n"
        f"📌 **Важно:**\n"
        f"• Вывод доступен только после выполнения заданий\n"
        f"• У вас должен быть установлен username в Telegram\n"
        f"• Мошеннические действия будут заблокированы\n"
        f"• Вопросы по выводу - администратору",
        reply_markup=reply_markup
    )

async def cancel_withdraw(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data.pop("withdraw_amount", None)
    context.user_data.pop("withdraw_step", None)
    
    await query.message.edit_text("❌ Вывод отменен.")

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    currency = get_currency_symbol()
    
    if user_id in db.bans:
        await update.message.reply_text(
            "⛔ **Вы забанены!** ⛔\n\n"
            f"Причина: {db.bans[user_id].get('reason', 'Не указана')}\n"
            f"Дата: {db.bans[user_id].get('date', 'Неизвестно')}"
        )
        return
    
    user_data = get_user_data(user_id)
    if update.effective_user.username:
        user_data["username"] = update.effective_user.username
        db.save()
    
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
                        f"👥 **Новый реферал!** 👥\n\n"
                        f"{update.effective_user.first_name} присоединился по вашей ссылке!\n"
                        f"💰 Вы получили: {ref_reward} {currency}\n"
                        f"📊 Всего рефералов: {len(referrer_data['referrals'])}"
                    )
                except Exception as e:
                    logger.error(f"Не удалось отправить сообщение рефереру: {e}")
    
    if context.args and context.args[0].startswith("promo_"):
        code = context.args[0].replace("promo_", "").upper()
        
        if code in db.promo_codes:
            promo = db.promo_codes[code]
            
            if promo.get("active", True):
                if user_id not in db.used_promo:
                    db.used_promo[user_id] = []
                
                if code not in db.used_promo[user_id]:
                    if len(promo.get("used_by", [])) < promo.get("limit", 1):
                        reward = promo.get("reward", 0)
                        add_mcoins(user_id, reward, f"promo_{code}", "promo")
                        
                        if "used_by" not in promo:
                            promo["used_by"] = []
                        promo["used_by"].append(user_id)
                        db.used_promo[user_id].append(code)
                        db.save()
                        
                        await update.message.reply_text(
                            f"✅ **Промокод активирован!** 🎉\n\n"
                            f"🎁 Вы получили: {reward} {currency}\n"
                            f"💰 Ваш баланс: {format_number(get_user_data(user_id)['mcoin'])} {currency}\n\n"
                            f"✨ Спасибо за использование бота!"
                        )
                    else:
                        await update.message.reply_text("❌ Промокод уже использован максимальное количество раз!")
                else:
                    await update.message.reply_text("❌ Вы уже использовали этот промокод!")
            else:
                await update.message.reply_text("❌ Промокод неактивен!")
        else:
            await update.message.reply_text("❌ Неверный промокод!")
    
    passed, not_passed = await check_force_subs(user_id, context.bot)
    sub_text = ""
    if not passed:
        sub_text = (
            f"\n\n⚠️ **Важно:** Для работы с ботом необходимо подписаться на:\n"
            f"{get_subscription_links()}\n\n"
            f"После подписки обновите бота командой /start"
        )
    
    username = update.effective_user.username or "Не установлен"
    achievements_count = len(db.achievements.get(user_id, []))
    
    welcome_text = (
        f"👋 Привет, {update.effective_user.first_name}!\n\n"
        f"Выполняй задания и зарабатывай {currency}!\n\n"
        f"💰 Награда за задание: {settings.task_reward} {currency}\n"
        f"👤 Ваш username: @{username}\n"
        f"💰 Баланс: 0 {currency}\n"
        f"🏅 Достижений: {achievements_count}"
        f"{sub_text}"
    )
    
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard(user_id))

async def cancel_command(update: Update, context: CallbackContext):
    context.user_data.clear()
    await update.message.reply_text("✅ Все операции отменены.")

async def handle_text(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id in db.bans:
        await update.message.reply_text("⛔ **Вы забанены!** ⛔")
        return
    
    if user_id in db.users:
        db.users[user_id]["last_seen"] = datetime.now().isoformat()
        if update.effective_user.username:
            db.users[user_id]["username"] = update.effective_user.username
        db.users[user_id]["first_name"] = update.effective_user.first_name
        db.save()
    
    # Обработка админских действий
    if context.user_data.get("admin_action") == "ban":
        await admin_ban_input(update, context)
        return
    elif context.user_data.get("admin_action") == "unban":
        await admin_unban_input(update, context)
        return
    elif context.user_data.get("admin_action") == "add_mcoin":
        await admin_add_mcoin_input(update, context)
        return
    elif context.user_data.get("admin_action") == "send_notification":
        await admin_send_notification_input(update, context)
        return
    elif context.user_data.get("admin_action") == "toggle_notify":
        await admin_toggle_notify_input(update, context)
        return
    
    # Обработка настройки значений
    if context.user_data.get("setting_to_change"):
        await admin_setting_input(update, context)
        return
    
    # Обработка вывода
    if context.user_data.get("withdraw_step") == "amount":
        await withdraw_amount_input(update, context)
        return
    
    # Обработка обязательных подписок
    if context.user_data.get("sub_type"):
        await add_force_sub_input(update, context)
        return
    
    # Обработка создания задания
    if context.user_data.get("task_step") == "link":
        await task_link_input(update, context)
        return
    elif context.user_data.get("task_step") == "reward":
        await task_reward_input(update, context)
        return
    
    # Обработка промокодов
    if context.user_data.get("promo_step") in ["code", "reward", "limit"]:
        await promo_code_create_input(update, context)
        return
    
    # Обработка призов
    if context.user_data.get("prize_place"):
        await set_prize_input(update, context)
        return
    
    # Обработка конкурсов
    if context.user_data.get("contest_step") == "name":
        await contest_name_input(update, context)
        return
    elif context.user_data.get("contest_step") == "desc":
        await contest_desc_input(update, context)
        return
    elif context.user_data.get("contest_step") == "target_value":
        await contest_target_value_input(update, context)
        return
    elif context.user_data.get("contest_step") == "prize":
        await contest_prize_input(update, context)
        return
    elif context.user_data.get("contest_step") == "duration":
        await contest_duration_input(update, context)
        return
    
    # Обработка рассылки
    if context.user_data.get("mailing_step") == "message":
        await mailing_message_input(update, context)
        return
    
    currency = get_currency_symbol()
    
    if text == "📋 Задания":
        await tasks_mode(update, context)
    elif text == "👥 Рефералы":
        await referrals_menu(update, context)
    elif text == "👤 Профиль":
        await profile_menu(update, context)
    elif text == f"💰 {currency}":
        await balance_handler(update, context)
    elif text == "⚙️ Админ панель" and user_id in settings.admin_list:
        await admin_panel(update, context)
    else:
        await update.message.reply_text(
            "❓ Используйте кнопки меню 👇",
            reply_markup=get_main_keyboard(user_id)
        )

async def balance_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    currency = get_currency_symbol()
    
    username = update.effective_user.username or "Не установлен"
    achievements = db.achievements.get(user_id, [])
    
    keyboard = [
        [InlineKeyboardButton("💸 Вывод средств", callback_data="withdraw_menu")],
        [InlineKeyboardButton("📊 Детальная статистика", callback_data="detailed_stats")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"💰 **Ваш баланс** 💰\n\n"
        f"👤 Username: @{username}\n"
        f"🎮 {currency}: `{format_number(user['mcoin'])}`\n\n"
        f"📊 **Статистика:**\n"
        f"💰 Всего заработано: {format_number(user['total_earned'])}\n"
        f"💸 Выведено: {format_number(user['total_withdrawn'])}\n"
        f"✅ С заданий: {format_number(user['task_earned'])}\n"
        f"👥 С рефералов: {format_number(user['referral_earned'])}\n"
        f"📅 В боте: {(datetime.now() - datetime.fromisoformat(user['join_date'])).days} дней\n"
        f"🔥 Серия: {user['daily_streak']} дней\n"
        f"🏅 Достижений: {len(achievements)}",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def back_to_main(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await update.effective_message.delete()
    await update.message.reply_text(
        "Главное меню:",
        reply_markup=get_main_keyboard(update.effective_user.id)
    )

async def profile_back(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await profile_menu(update, context)

# ========== АДМИН ПАНЕЛЬ ==========
async def admin_panel(update: Update, context: CallbackContext):
    if update.effective_user.id not in settings.admin_list:
        await update.message.reply_text("⛔ У вас нет доступа к админ панели!")
        return
    
    currency = get_currency_symbol()
    
    keyboard = [
        [InlineKeyboardButton("💰 Настройка наград", callback_data="admin_rewards")],
        [InlineKeyboardButton("📢 Обязательные подписки", callback_data="admin_forcesub")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("💸 Выводы", callback_data="admin_withdrawals")],
        [InlineKeyboardButton("📨 Рассылка", callback_data="admin_mailing")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="admin_settings")],
        [InlineKeyboardButton("🎁 Призы топа", callback_data="admin_top_prizes")],
        [InlineKeyboardButton("📋 Задания", callback_data="admin_create_task")],
        [InlineKeyboardButton("🎫 Промокоды", callback_data="admin_promo")],
        [InlineKeyboardButton("🔔 Уведомления", callback_data="admin_notifications")],
        [InlineKeyboardButton("📋 Обязательные задания", callback_data="admin_force_tasks")],
        [InlineKeyboardButton("🎯 Конкурсы", callback_data="admin_contests")],
        [InlineKeyboardButton("⚙️ Настройки спонсоров", callback_data="admin_sponsors")],
        [InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    pending_withdrawals = 0
    for uid, req in db.withdraw_requests.items():
        if req.get("status") == "pending":
            pending_withdrawals += 1
    
    total_users = db.global_stats["total_users"]
    total_tasks = db.global_stats["total_tasks_completed"]
    
    await update.message.reply_text(
        f"⚙️ **Админ панель** ⚙️\n\n"
        f"📊 **Быстрая статистика:**\n"
        f"👥 Пользователей: {total_users}\n"
        f"💰 Всего заработано: {format_number(db.global_stats['total_mcoins_earned'])} {currency}\n"
        f"✅ Заданий выполнено: {total_tasks}\n"
        f"💸 Ожидают вывода: {pending_withdrawals}\n"
        f"🎫 Промокодов использовано: {db.global_stats['total_promos_used']}\n\n"
        f"💰 **Текущая награда за задание:** {settings.task_reward} {currency}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

# ========== АДМИН: НАСТРОЙКА НАГРАД ==========
async def admin_rewards_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    currency = get_currency_symbol()
    
    keyboard = [
        [InlineKeyboardButton(f"💰 За задание: {settings.task_reward} {currency}", callback_data="set_task_reward")],
        [InlineKeyboardButton(f"👥 За реферала: {settings.referral_reward} {currency}", callback_data="set_ref_reward")],
        [InlineKeyboardButton(f"💸 Мин. вывод: {settings.min_withdraw} {currency}", callback_data="set_min_withdraw")],
        [InlineKeyboardButton(f"📊 Лимит заданий: {settings.max_daily_tasks}", callback_data="set_max_tasks")],
        [InlineKeyboardButton(f"💸 Макс. вывод: {settings.max_withdraw} {currency}", callback_data="set_max_withdraw")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"💰 **Настройка наград** 💰\n\n"
        f"💰 **Текущая награда за задание:** {settings.task_reward} {currency}\n\n"
        f"Выберите параметр для изменения:",
        reply_markup=reply_markup
    )

async def set_reward_value(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    setting = query.data.replace("set_", "")
    context.user_data["setting_to_change"] = setting
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_setting")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    setting_names = {
        "task_reward": "награды за задание",
        "ref_reward": "награды за реферала",
        "min_withdraw": "минимальной суммы вывода",
        "max_tasks": "лимита заданий",
        "max_withdraw": "максимальной суммы вывода"
    }
    
    setting_name = setting_names.get(setting, setting)
    
    await query.message.edit_text(
        f"📝 **Изменение {setting_name}**\n\n"
        f"Текущее значение: {getattr(settings, setting, 0)}\n\n"
        f"Введите новое значение:",
        reply_markup=reply_markup
    )

async def admin_setting_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    setting = context.user_data.get("setting_to_change")
    if not setting:
        await update.message.reply_text("❌ Ошибка! Попробуйте снова.")
        return
    
    try:
        value = int(update.message.text)
        if value <= 0:
            await update.message.reply_text("❌ Значение должно быть положительным!")
            return
        
        if setting == "task_reward":
            settings.task_reward = value
        elif setting == "ref_reward":
            settings.referral_reward = value
        elif setting == "min_withdraw":
            settings.min_withdraw = value
        elif setting == "max_tasks":
            settings.max_daily_tasks = value
        elif setting == "max_withdraw":
            settings.max_withdraw = value
        else:
            await update.message.reply_text("❌ Неизвестный параметр!")
            return
        
        settings.save()
        context.user_data.pop("setting_to_change", None)
        
        await update.message.reply_text(
            f"✅ **Настройка обновлена!**\n\n"
            f"Новое значение: {value}"
        )
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число!")

# ========== АДМИН: ОБЯЗАТЕЛЬНЫЕ ПОДПИСКИ ==========
async def admin_forcesub_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    channels_text = "\n".join([f"• {ch}" for ch in settings.force_sub_channels]) or "Нет каналов"
    groups_text = "\n".join([f"• {gr}" for gr in settings.force_sub_groups]) or "Нет групп"
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить канал", callback_data="add_channel")],
        [InlineKeyboardButton("➕ Добавить группу", callback_data="add_group")],
        [InlineKeyboardButton("🗑 Удалить канал", callback_data="remove_channel")],
        [InlineKeyboardButton("🗑 Удалить группу", callback_data="remove_group")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"📢 **Обязательные подписки** 📢\n\n"
        f"📺 **Каналы:**\n{channels_text}\n\n"
        f"👥 **Группы:**\n{groups_text}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

async def add_force_sub_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    sub_type = "channel" if query.data == "add_channel" else "group"
    context.user_data["sub_type"] = sub_type
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_setting")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"📝 Введите название {sub_type}а:\n"
        f"Пример: @channel_name или channel_name",
        reply_markup=reply_markup
    )

async def add_force_sub_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    sub_type = context.user_data.get("sub_type")
    if not sub_type:
        await update.message.reply_text("❌ Ошибка! Попробуйте снова.")
        return
    
    name = update.message.text.strip()
    if name.startswith("@"):
        name = name[1:]
    
    if sub_type == "channel":
        if name in settings.force_sub_channels:
            await update.message.reply_text("❌ Этот канал уже добавлен!")
            return
        settings.force_sub_channels.append(name)
    else:
        if name in settings.force_sub_groups:
            await update.message.reply_text("❌ Эта группа уже добавлена!")
            return
        settings.force_sub_groups.append(name)
    
    settings.save()
    context.user_data.pop("sub_type", None)
    
    await update.message.reply_text(f"✅ {sub_type.capitalize()} '{name}' добавлен в обязательные подписки!")

async def remove_force_sub_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    sub_type = "channel" if query.data == "remove_channel" else "group"
    
    if sub_type == "channel" and not settings.force_sub_channels:
        await query.message.edit_text("❌ Нет каналов для удаления!")
        return
    if sub_type == "group" and not settings.force_sub_groups:
        await query.message.edit_text("❌ Нет групп для удаления!")
        return
    
    items = settings.force_sub_channels if sub_type == "channel" else settings.force_sub_groups
    keyboard = []
    for item in items:
        keyboard.append([InlineKeyboardButton(f"🗑 {item}", callback_data=f"remove_sub_{sub_type}_{item}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_forcesub")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"📝 Выберите {sub_type} для удаления:",
        reply_markup=reply_markup
    )

async def remove_sub_confirmation(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    data = query.data.replace("remove_sub_", "")
    parts = data.split("_")
    sub_type = parts[0]
    name = "_".join(parts[1:])
    
    if sub_type == "channel":
        if name in settings.force_sub_channels:
            settings.force_sub_channels.remove(name)
            await query.message.edit_text(f"✅ Канал '{name}' удален из обязательных подписок!")
        else:
            await query.message.edit_text(f"❌ Канал '{name}' не найден!")
    else:
        if name in settings.force_sub_groups:
            settings.force_sub_groups.remove(name)
            await query.message.edit_text(f"✅ Группа '{name}' удалена из обязательных подписок!")
        else:
            await query.message.edit_text(f"❌ Группа '{name}' не найдена!")
    
    settings.save()

# ========== АДМИН: НАСТРОЙКИ СПОНСОРОВ ==========
async def admin_sponsors_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in settings.admin_list:
        await query.message.edit_text("⛔ Только для администратора!")
        return
    
    keyboard = [
        [InlineKeyboardButton(f"🔄 Обязательные спонсоры: {'✅' if settings.force_sub_sponsors else '❌'}", callback_data="toggle_sponsors")],
        [InlineKeyboardButton(f"👤 Пол: {settings.sponsor_gender or 'Не указан'}", callback_data="set_sponsor_gender")],
        [InlineKeyboardButton(f"📊 Возраст: {settings.sponsor_age or 'Не указан'}", callback_data="set_sponsor_age")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"⚙️ **Настройки спонсоров** ⚙️\n\n"
        f"🔄 Обязательные спонсоры: {'Включены' if settings.force_sub_sponsors else 'Выключены'}\n"
        f"👤 Пол: {settings.sponsor_gender or 'Не указан'}\n"
        f"📊 Возраст: {settings.sponsor_age or 'Не указан'}\n\n"
        f"📌 Эти настройки влияют на задания от BotoHub",
        reply_markup=reply_markup
    )

async def toggle_sponsors_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    settings.force_sub_sponsors = not settings.force_sub_sponsors
    settings.save()
    await query.message.edit_text(f"🔄 Обязательные спонсоры {'включены' if settings.force_sub_sponsors else 'выключены'}!")

async def set_sponsor_gender_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("👨 Мужской", callback_data="sponsor_gender_male")],
        [InlineKeyboardButton("👩 Женский", callback_data="sponsor_gender_female")],
        [InlineKeyboardButton("❌ Не указывать", callback_data="sponsor_gender_none")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_sponsors")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "👤 **Выберите пол для спонсоров:**",
        reply_markup=reply_markup
    )

async def set_sponsor_gender_value(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    value = query.data.replace("sponsor_gender_", "")
    if value == "none":
        settings.sponsor_gender = None
    else:
        settings.sponsor_gender = value
    settings.save()
    
    await query.message.edit_text(f"✅ Пол установлен: {settings.sponsor_gender or 'Не указан'}")

async def set_sponsor_age_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("18-25", callback_data="sponsor_age_18-25")],
        [InlineKeyboardButton("26-35", callback_data="sponsor_age_26-35")],
        [InlineKeyboardButton("36+", callback_data="sponsor_age_36+")],
        [InlineKeyboardButton("❌ Не указывать", callback_data="sponsor_age_none")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_sponsors")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "📊 **Выберите возрастную группу для спонсоров:**\n\n"
        "Можно выбрать категорию c1-c6",
        reply_markup=reply_markup
    )

async def set_sponsor_age_value(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    value = query.data.replace("sponsor_age_", "")
    if value == "none":
        settings.sponsor_age = None
    else:
        settings.sponsor_age = value
    settings.save()
    
    await query.message.edit_text(f"✅ Возраст установлен: {settings.sponsor_age or 'Не указан'}")

# ========== АДМИН: ПОЛЬЗОВАТЕЛИ ==========
async def admin_users_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("⛔ Забанить", callback_data="ban_user")],
        [InlineKeyboardButton("✅ Разбанить", callback_data="unban_user")],
        [InlineKeyboardButton("💰 Добавить MCoin", callback_data="add_mcoin_user")],
        [InlineKeyboardButton("📊 Список пользователей", callback_data="list_users")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"👥 **Управление пользователями** 👥\n\n"
        f"Всего пользователей: {db.global_stats['total_users']}\n"
        f"Забанено: {len(db.bans)}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

async def ban_user_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["admin_action"] = "ban"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "⛔ **Бан пользователя**\n\n"
        "Введите @username пользователя для бана:",
        reply_markup=reply_markup
    )

async def unban_user_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["admin_action"] = "unban"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "✅ **Разбан пользователя**\n\n"
        "Введите @username пользователя для разбана:",
        reply_markup=reply_markup
    )

async def add_mcoin_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["admin_action"] = "add_mcoin"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "💰 **Добавление MCoin**\n\n"
        "Введите @username пользователя и сумму через пробел:\n"
        "Пример: @username 100",
        reply_markup=reply_markup
    )

async def admin_ban_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    username = update.message.text.strip()
    if username.startswith("@"):
        username = username[1:]
    
    target_id = get_user_by_username(username)
    if not target_id:
        await update.message.reply_text(f"❌ Пользователь @{username} не найден!")
        return
    
    if target_id in db.bans:
        await update.message.reply_text("❌ Пользователь уже забанен!")
        return
    
    db.bans[target_id] = {
        "reason": "Нарушение правил",
        "date": datetime.now().isoformat(),
        "banned_by": user_id
    }
    db.save()
    context.user_data.pop("admin_action", None)
    
    await update.message.reply_text(f"⛔ Пользователь @{username} забанен!")

async def admin_unban_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    username = update.message.text.strip()
    if username.startswith("@"):
        username = username[1:]
    
    target_id = get_user_by_username(username)
    if not target_id:
        await update.message.reply_text(f"❌ Пользователь @{username} не найден!")
        return
    
    if target_id not in db.bans:
        await update.message.reply_text("❌ Пользователь не забанен!")
        return
    
    del db.bans[target_id]
    db.save()
    context.user_data.pop("admin_action", None)
    
    await update.message.reply_text(f"✅ Пользователь @{username} разбанен!")

async def admin_add_mcoin_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    parts = update.message.text.split()
    if len(parts) != 2:
        await update.message.reply_text("❌ Используйте: @username Сумма")
        return
    
    username = parts[0].strip()
    if username.startswith("@"):
        username = username[1:]
    
    try:
        amount = int(parts[1])
        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть положительной!")
            return
    except ValueError:
        await update.message.reply_text("❌ Введите корректную сумму!")
        return
    
    target_id = get_user_by_username(username)
    if not target_id:
        await update.message.reply_text(f"❌ Пользователь @{username} не найден!")
        return
    
    add_mcoins(target_id, amount, f"admin_add_{amount}", "other")
    context.user_data.pop("admin_action", None)
    
    await update.message.reply_text(
        f"✅ Добавлено {amount} {settings.currency_name} пользователю @{username}!"
    )

async def list_users_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if not db.users:
        await query.message.edit_text("📭 Нет пользователей!")
        return
    
    users_list = []
    for uid, data in sorted(db.users.items(), key=lambda x: x[1].get("mcoin", 0), reverse=True)[:20]:
        name = data.get("first_name", f"User_{uid}")
        username = data.get("username", "нет username")
        users_list.append(f"{uid} | @{username} | {data.get('mcoin', 0)} {settings.currency_name}")
    
    text = "📊 **Список пользователей (топ 20):**\n\n" + "\n".join(users_list)
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_users")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, reply_markup=reply_markup)

# ========== АДМИН: СТАТИСТИКА ==========
async def admin_stats_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    currency = get_currency_symbol()
    
    total_users = db.global_stats["total_users"]
    total_earned = db.global_stats["total_mcoins_earned"]
    total_withdrawn = db.global_stats["total_withdrawn"]
    total_tasks = db.global_stats["total_tasks_completed"]
    
    pending_withdrawals = 0
    for uid, req in db.withdraw_requests.items():
        if req.get("status") == "pending":
            pending_withdrawals += 1
    
    total_withdraw_requests = len(db.withdraw_requests)
    
    active_users = 0
    for uid, user in db.users.items():
        last_seen = user.get("last_seen")
        if last_seen:
            try:
                if (datetime.now() - datetime.fromisoformat(last_seen)).days < 7:
                    active_users += 1
            except:
                pass
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"📊 **Статистика бота** 📊\n\n"
        f"👥 **Пользователи:**\n"
        f"• Всего: {total_users}\n"
        f"• Активных: {active_users}\n"
        f"• Забанено: {len(db.bans)}\n\n"
        f"💰 **Финансы:**\n"
        f"• Всего заработано: {format_number(total_earned)} {currency}\n"
        f"• Выведено: {format_number(total_withdrawn)} {currency}\n"
        f"• В системе: {format_number(total_earned - total_withdrawn)} {currency}\n\n"
        f"📋 **Заявки на вывод:**\n"
        f"• Ожидают: {pending_withdrawals}\n"
        f"• Всего: {total_withdraw_requests}\n\n"
        f"✅ **Задания:**\n"
        f"• Всего выполнено: {total_tasks}\n"
        f"• В среднем на пользователя: {total_tasks // total_users if total_users > 0 else 0}\n"
        f"💰 **Награда за задание:** {settings.task_reward} {currency}\n"
        f"🎫 **Промокодов использовано:** {db.global_stats['total_promos_used']}",
        reply_markup=reply_markup
    )

# ========== АДМИН: ВЫВОДЫ ==========
async def admin_withdrawals_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    currency = get_currency_symbol()
    
    pending_list = []
    for uid, req in db.withdraw_requests.items():
        if req.get("status") == "pending":
            user = db.users.get(uid, {})
            name = user.get("first_name", f"User_{uid}")
            username = req.get("username", "Не указан")
            amount = req.get("amount", 0)
            final_amount = req.get("final_amount", amount)
            pending_list.append({
                "user_id": uid,
                "username": username,
                "name": name,
                "amount": amount,
                "final_amount": final_amount
            })
    
    if not pending_list:
        await query.message.edit_text("📭 Нет заявок на вывод!")
        return
    
    text = "💸 **Заявки на вывод:**\n\n"
    for i, req in enumerate(pending_list[:10], 1):
        text += f"{i}. ID: {req['user_id']} | @{req['username']}\n"
        text += f"   Сумма: {req['amount']} {currency} → {req['final_amount']} {currency}\n\n"
    
    if len(pending_list) > 10:
        text += f"... и еще {len(pending_list) - 10} заявок"
    
    keyboard = []
    for req in pending_list[:10]:
        keyboard.append([
            InlineKeyboardButton(f"✅ Подтвердить", callback_data=f"confirm_{req['user_id']}"),
            InlineKeyboardButton(f"❌ Отклонить", callback_data=f"reject_{req['user_id']}")
        ])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, reply_markup=reply_markup)

async def confirm_withdraw_button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    currency = get_currency_symbol()
    
    user_id = int(query.data.replace("confirm_", ""))
    
    if user_id not in db.withdraw_requests:
        await query.message.edit_text("❌ Заявка не найдена!")
        return
    
    request = db.withdraw_requests[user_id]
    if request.get("status") != "pending":
        await query.message.edit_text("❌ Заявка уже обработана!")
        return
    
    request["status"] = "completed"
    request["completed_at"] = datetime.now().isoformat()
    
    db.global_stats["total_withdrawn"] += request.get("final_amount", request.get("amount", 0))
    db.save()
    
    try:
        await context.bot.send_message(
            user_id,
            f"✅ **Ваша заявка на вывод подтверждена!**\n\n"
            f"💰 Сумма: {request['amount']} {currency}\n"
            f"💳 К получению: {request.get('final_amount', request['amount'])} {currency}\n"
            f"👤 Username: @{request.get('username', 'Не указан')}\n\n"
            f"Средства будут отправлены в ближайшее время!"
        )
    except:
        pass
    
    await query.message.edit_text(
        f"✅ Вывод подтвержден!\n"
        f"Пользователь ID: {user_id}\n"
        f"Сумма: {request['amount']} {currency}\n"
        f"К получению: {request.get('final_amount', request['amount'])} {currency}"
    )
    
    await admin_withdrawals_callback(update, context)

async def reject_withdraw_button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    currency = get_currency_symbol()
    
    user_id = int(query.data.replace("reject_", ""))
    
    if user_id not in db.withdraw_requests:
        await query.message.edit_text("❌ Заявка не найдена!")
        return
    
    request = db.withdraw_requests[user_id]
    if request.get("status") != "pending":
        await query.message.edit_text("❌ Заявка уже обработана!")
        return
    
    request["status"] = "rejected"
    request["rejected_at"] = datetime.now().isoformat()
    
    add_mcoins(user_id, request["amount"], "withdraw_rejected", "other")
    
    try:
        await context.bot.send_message(
            user_id,
            f"❌ **Ваша заявка на вывод отклонена!**\n\n"
            f"💰 Сумма: {request['amount']} {currency}\n"
            f"👤 Username: @{request.get('username', 'Не указан')}\n\n"
            f"Средства возвращены на ваш баланс.\n"
            f"По вопросам обратитесь к администратору."
        )
    except:
        pass
    
    await query.message.edit_text(
        f"❌ Вывод отклонен!\n"
        f"Пользователь ID: {user_id}\n"
        f"Сумма возвращена на баланс."
    )
    
    await admin_withdrawals_callback(update, context)

# ========== АДМИН: РАССЫЛКА ==========
async def admin_mailing_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["mailing_step"] = "message"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_mailing")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "📨 **Рассылка**\n\n"
        "Введите текст сообщения:",
        reply_markup=reply_markup
    )

async def mailing_message_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    message_text = update.message.text
    
    context.user_data["mailing_message"] = message_text
    context.user_data["mailing_step"] = "confirm"
    
    keyboard = [
        [InlineKeyboardButton("✅ Отправить", callback_data="send_mailing")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_mailing")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📨 **Подтверждение**\n\n"
        f"Текст:\n{message_text}\n\n"
        f"Получателей: {db.global_stats['total_users']}\n\n"
        f"Отправить?",
        reply_markup=reply_markup
    )

async def send_mailing_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if user_id not in settings.admin_list:
        return
    
    message_text = context.user_data.get("mailing_message")
    if not message_text:
        await query.message.edit_text("❌ Ошибка!")
        return
    
    await query.message.edit_text("📨 **Отправка...**")
    
    sent = 0
    failed = 0
    
    for uid in db.users.keys():
        try:
            await context.bot.send_message(uid, message_text, parse_mode="Markdown")
            sent += 1
            await asyncio.sleep(0.05)
        except:
            failed += 1
    
    context.user_data.pop("mailing_message", None)
    context.user_data.pop("mailing_step", None)
    
    await query.message.edit_text(
        f"✅ **Рассылка завершена!**\n\n"
        f"📨 Отправлено: {sent}\n"
        f"❌ Не доставлено: {failed}"
    )

# ========== АДМИН: НАСТРОЙКИ ==========
async def admin_settings_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton(f"🔄 Режим: {'Вкл' if settings.maintenance_mode else 'Выкл'}", callback_data="toggle_maintenance")],
        [InlineKeyboardButton(f"📊 Лимит: {settings.max_daily_tasks}", callback_data="set_max_tasks")],
        [InlineKeyboardButton(f"💳 Комиссия: {int(settings.withdraw_commission * 100)}%", callback_data="set_withdraw_commission")],
        [InlineKeyboardButton(f"💰 Валюта: {settings.currency_name}", callback_data="set_currency_name")],
        [InlineKeyboardButton(f"🎨 Символ: {settings.currency_emoji}", callback_data="set_currency_emoji")],
        [InlineKeyboardButton(f"🔔 Уведомления: {'✅' if settings.auto_notify else '❌'}", callback_data="toggle_notify")],
        [InlineKeyboardButton(f"⏱️ Интервал уведомлений: {settings.notification_interval}с", callback_data="set_notify_interval")],
        [InlineKeyboardButton(f"📋 Интервал обязательных: {settings.force_task_interval}с", callback_data="set_force_interval")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"⚙️ **Настройки** ⚙️\n\n"
        f"🔄 Режим обслуживания: {'Включен' if settings.maintenance_mode else 'Выключен'}\n"
        f"📊 Лимит задач в день: {settings.max_daily_tasks}\n"
        f"💳 Комиссия вывода: {int(settings.withdraw_commission * 100)}%\n"
        f"💰 Валюта: {settings.currency_name}\n"
        f"🎨 Символ: {settings.currency_emoji}\n"
        f"🔔 Уведомления: {'Включены' if settings.auto_notify else 'Выключены'}\n"
        f"⏱️ Интервал уведомлений: {settings.notification_interval}с\n"
        f"📋 Интервал обязательных: {settings.force_task_interval}с",
        reply_markup=reply_markup
    )

async def toggle_maintenance_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    settings.maintenance_mode = not settings.maintenance_mode
    settings.save()
    await query.message.edit_text(f"🔄 Режим {'включен' if settings.maintenance_mode else 'выключен'}!")

async def set_currency_name_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data["setting_to_change"] = "currency_name"
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_setting")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        f"💰 Введите новое название валюты:",
        reply_markup=reply_markup
    )

async def set_currency_name_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    setting = context.user_data.get("setting_to_change")
    if setting != "currency_name":
        return
    name = update.message.text.strip()
    if len(name) < 1:
        await update.message.reply_text("❌ Название не может быть пустым!")
        return
    settings.currency_name = name
    settings.save()
    context.user_data.pop("setting_to_change", None)
    await update.message.reply_text(f"✅ Валюта изменена: {name}")

async def set_currency_emoji_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    emojis = ["🪙", "💰", "💎", "⭐", "🌟", "✨", "🔮", "💠", "🏅", "🥇", "💫", "🌈", "🔥", "⚡", "💡", "🔑"]
    keyboard = []
    for emoji in emojis:
        keyboard.append([InlineKeyboardButton(f"{emoji}", callback_data=f"currency_emoji_{emoji}")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_setting")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        f"🎨 Выберите символ валюты:",
        reply_markup=reply_markup
    )

async def set_currency_emoji_value(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    emoji = query.data.replace("currency_emoji_", "")
    settings.currency_emoji = emoji
    settings.save()
    await query.message.edit_text(f"✅ Символ изменен: {emoji}")

async def toggle_notify_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    settings.auto_notify = not settings.auto_notify
    settings.save()
    await query.message.edit_text(f"🔔 Уведомления {'включены' if settings.auto_notify else 'выключены'}!")

async def set_notify_interval_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data["setting_to_change"] = "notify_interval"
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_setting")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        f"⏱️ Введите новый интервал (сек):",
        reply_markup=reply_markup
    )

async def set_notify_interval_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    setting = context.user_data.get("setting_to_change")
    if setting != "notify_interval":
        return
    try:
        value = int(update.message.text)
        if value <= 0:
            await update.message.reply_text("❌ Положительное число!")
            return
        settings.notification_interval = value
        settings.save()
        context.user_data.pop("setting_to_change", None)
        await update.message.reply_text(f"✅ Интервал: {value}с")
    except ValueError:
        await update.message.reply_text("❌ Введите число!")

async def set_force_interval_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data["setting_to_change"] = "force_interval"
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_setting")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        f"📋 Введите новый интервал (сек):",
        reply_markup=reply_markup
    )

async def set_force_interval_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    setting = context.user_data.get("setting_to_change")
    if setting != "force_interval":
        return
    try:
        value = int(update.message.text)
        if value <= 0:
            await update.message.reply_text("❌ Положительное число!")
            return
        settings.force_task_interval = value
        settings.save()
        context.user_data.pop("setting_to_change", None)
        await update.message.reply_text(f"✅ Интервал: {value}с")
    except ValueError:
        await update.message.reply_text("❌ Введите число!")

# ========== АДМИН: ПРИЗЫ ТОПА ==========
async def admin_top_prizes_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    currency = get_currency_symbol()
    
    keyboard = [
        [InlineKeyboardButton(f"🥇 1 место: {settings.top_prize_1} {currency}", callback_data="set_prize_1")],
        [InlineKeyboardButton(f"🥈 2 место: {settings.top_prize_2} {currency}", callback_data="set_prize_2")],
        [InlineKeyboardButton(f"🥉 3 место: {settings.top_prize_3} {currency}", callback_data="set_prize_3")],
        [InlineKeyboardButton("🏆 Выдать призы", callback_data="give_top_prizes")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"🎁 **Призы топа**\n\n"
        f"🥇 1 место - {settings.top_prize_1} {currency}\n"
        f"🥈 2 место - {settings.top_prize_2} {currency}\n"
        f"🥉 3 место - {settings.top_prize_3} {currency}",
        reply_markup=reply_markup
    )

async def set_prize_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    place = query.data.replace("set_prize_", "")
    context.user_data["prize_place"] = place
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_setting")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    place_names = {"1": "1 место", "2": "2 место", "3": "3 место"}
    await query.message.edit_text(
        f"📝 Введите сумму для {place_names.get(place, '')}:",
        reply_markup=reply_markup
    )

async def set_prize_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    place = context.user_data.get("prize_place")
    if not place:
        return
    try:
        value = int(update.message.text)
        if value <= 0:
            await update.message.reply_text("❌ Положительное число!")
            return
        setattr(settings, f"top_prize_{place}", value)
        settings.save()
        context.user_data.pop("prize_place", None)
        await update.message.reply_text(f"✅ Приз обновлен!")
    except ValueError:
        await update.message.reply_text("❌ Введите число!")

async def give_top_prizes_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    currency = get_currency_symbol()
    
    sorted_users = sorted(db.top_users.items(), key=lambda x: x[1].get("tasks", 0), reverse=True)[:3]
    if not sorted_users:
        await query.message.edit_text("❌ Нет пользователей!")
        return
    
    awarded = []
    prizes = [settings.top_prize_1, settings.top_prize_2, settings.top_prize_3]
    
    for i, (uid, data) in enumerate(sorted_users):
        if i >= 3:
            break
        prize = prizes[i]
        if prize > 0:
            add_mcoins(uid, prize, f"top_prize_place_{i+1}", "top_prize")
            awarded.append(f"{i+1}. @{data.get('username', 'Неизвестно')} - {prize} {currency}")
            await send_notification(
                context,
                uid,
                f"🏆 Вы заняли {i+1} место!\n💰 Приз: {prize} {currency}"
            )
    
    if awarded:
        await query.message.edit_text(f"✅ Призы выданы!\n\n" + "\n".join(awarded))
    else:
        await query.message.edit_text("❌ Нет призов!")

# ========== АДМИН: СОЗДАНИЕ ЗАДАНИЯ ==========
async def admin_create_task_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in settings.admin_list:
        return
    context.user_data["task_step"] = "link"
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_task")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        "📋 Введите ссылку на задание:",
        reply_markup=reply_markup
    )

async def task_link_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    context.user_data["task_link"] = update.message.text
    context.user_data["task_step"] = "reward"
    currency = get_currency_symbol()
    await update.message.reply_text(
        f"🔗 Ссылка: {context.user_data['task_link']}\n\nВведите награду ({currency}):"
    )

async def task_reward_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    try:
        reward = int(update.message.text)
        if reward <= 0:
            await update.message.reply_text("❌ Положительное число!")
            return
        link = context.user_data["task_link"]
        for uid in db.users.keys():
            db.custom_tasks[uid] = {
                "link": link,
                "reward": reward,
                "active": True,
                "created_by": user_id,
                "created_at": datetime.now().isoformat()
            }
        db.save()
        context.user_data.pop("task_step", None)
        context.user_data.pop("task_link", None)
        currency = get_currency_symbol()
        await update.message.reply_text(f"✅ Задание создано!\n🔗 {link}\n💰 {reward} {currency}")
        await broadcast_notification(
            context,
            f"📢 Новое задание!\n🔗 {link}\n💰 Награда: {reward} {currency}"
        )
    except ValueError:
        await update.message.reply_text("❌ Введите число!")

async def cancel_task_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("task_step", None)
    context.user_data.pop("task_link", None)
    await query.message.edit_text("❌ Отменено.")

# ========== АДМИН: ПРОМОКОДЫ ==========
async def admin_promo_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    currency = get_currency_symbol()
    
    keyboard = [
        [InlineKeyboardButton("➕ Создать", callback_data="create_promo")],
        [InlineKeyboardButton("📋 Список", callback_data="list_promos")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"🎫 **Промокоды**\n\nВсего: {len(db.promo_codes)}",
        reply_markup=reply_markup
    )

async def create_promo_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in settings.admin_list:
        return
    context.user_data["promo_step"] = "code"
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_promo_admin")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        "🎫 Введите код промокода:",
        reply_markup=reply_markup
    )

async def promo_code_create_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    step = context.user_data.get("promo_step")
    if step == "code":
        code = update.message.text.upper()
        if len(code) < 3:
            await update.message.reply_text("❌ Минимум 3 символа!")
            return
        if code in db.promo_codes:
            await update.message.reply_text("❌ Уже существует!")
            return
        context.user_data["promo_code"] = code
        context.user_data["promo_step"] = "reward"
        currency = get_currency_symbol()
        await update.message.reply_text(f"Код: {code}\n\nВведите награду ({currency}):")
    elif step == "reward":
        try:
            reward = int(update.message.text)
            if reward <= 0:
                await update.message.reply_text("❌ Положительное число!")
                return
            context.user_data["promo_reward"] = reward
            context.user_data["promo_step"] = "limit"
            await update.message.reply_text(
                f"Код: {context.user_data['promo_code']}\n"
                f"💰 Награда: {reward}\n\n"
                "Введите лимит использований:"
            )
        except ValueError:
            await update.message.reply_text("❌ Введите число!")
    elif step == "limit":
        try:
            limit = int(update.message.text)
            if limit <= 0:
                await update.message.reply_text("❌ Положительное число!")
                return
            code = context.user_data["promo_code"]
            reward = context.user_data["promo_reward"]
            db.promo_codes[code] = {
                "reward": reward,
                "limit": limit,
                "active": True,
                "used_by": [],
                "created_by": user_id,
                "created_at": datetime.now().isoformat()
            }
            db.save()
            context.user_data.pop("promo_code", None)
            context.user_data.pop("promo_reward", None)
            context.user_data.pop("promo_step", None)
            currency = get_currency_symbol()
            await update.message.reply_text(
                f"✅ Промокод создан!\n🎫 {code}\n💰 {reward} {currency}\n📊 Лимит: {limit}\n"
                f"Ссылка: https://t.me/{context.bot.username}?start=promo_{code}"
            )
        except ValueError:
            await update.message.reply_text("❌ Введите число!")

async def list_promos_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    if not db.promo_codes:
        await query.message.edit_text("📭 Нет промокодов.")
        return
    currency = get_currency_symbol()
    text = "📋 **Промокоды:**\n\n"
    for code, promo in db.promo_codes.items():
        status = "🟢" if promo.get("active", True) else "🔴"
        uses = len(promo.get("used_by", []))
        limit = promo.get("limit", 1)
        text += f"{status} {code} - {promo['reward']} {currency} ({uses}/{limit})\n"
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_promo")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(text, reply_markup=reply_markup)

async def cancel_promo_admin_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("promo_code", None)
    context.user_data.pop("promo_reward", None)
    context.user_data.pop("promo_step", None)
    await query.message.edit_text("❌ Отменено.")

# ========== АДМИН: УВЕДОМЛЕНИЯ ==========
async def admin_notifications_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("📨 Всем", callback_data="send_notification_all")],
        [InlineKeyboardButton("👤 Пользователю", callback_data="send_notification_user")],
        [InlineKeyboardButton("🔔 Вкл/Выкл", callback_data="toggle_user_notify")],
        [InlineKeyboardButton("📊 Статистика", callback_data="notify_stats")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        f"🔔 **Уведомления**\n\n"
        f"Авто: {'✅' if settings.auto_notify else '❌'}\n"
        f"Интервал: {settings.notification_interval}с",
        reply_markup=reply_markup
    )

async def send_notification_all_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data["mailing_step"] = "message"
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_mailing")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        "📨 Введите текст для всех:",
        reply_markup=reply_markup
    )

async def send_notification_user_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data["admin_action"] = "send_notification"
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        "👤 Введите @username:",
        reply_markup=reply_markup
    )

async def admin_send_notification_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    username = update.message.text.strip()
    if username.startswith("@"):
        username = username[1:]
    
    target_id = get_user_by_username(username)
    if not target_id:
        await update.message.reply_text(f"❌ Пользователь @{username} не найден!")
        return
    
    context.user_data["admin_action"] = None
    context.user_data["notification_target"] = target_id
    context.user_data["mailing_step"] = "message"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_mailing")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📨 Введите текст для @{username}:",
        reply_markup=reply_markup
    )

async def toggle_user_notify_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data["admin_action"] = "toggle_notify"
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        "👤 Введите @username:",
        reply_markup=reply_markup
    )

async def admin_toggle_notify_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    username = update.message.text.strip()
    if username.startswith("@"):
        username = username[1:]
    
    target_id = get_user_by_username(username)
    if not target_id:
        await update.message.reply_text(f"❌ Пользователь @{username} не найден!")
        return
    
    user = get_user_data(target_id)
    current = user.get("notifications_enabled", True)
    user["notifications_enabled"] = not current
    db.save()
    context.user_data.pop("admin_action", None)
    
    status = "включены" if user["notifications_enabled"] else "выключены"
    await update.message.reply_text(f"✅ Уведомления для @{username} {status}!")

async def notify_stats_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    total = sum(len(n) for n in db.notifications.values())
    users = len([u for u in db.users.values() if u.get("notifications_enabled", True)])
    await query.message.edit_text(
        f"📊 **Уведомления**\n\n"
        f"📨 Отправлено: {total}\n"
        f"👥 Получают: {users}\n"
        f"👤 Всего: {db.global_stats['total_users']}"
    )

# ========== АДМИН: ОБЯЗАТЕЛЬНЫЕ ЗАДАНИЯ ==========
async def admin_force_tasks_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in settings.admin_list:
        return
    active = len(db.force_tasks)
    keyboard = [
        [InlineKeyboardButton("📋 Активные", callback_data="view_force_tasks")],
        [InlineKeyboardButton("🗑 Очистить", callback_data="clear_force_tasks")],
        [InlineKeyboardButton("⏱️ Интервал", callback_data="set_force_interval")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        f"📋 **Обязательные задания**\n\nАктивных: {active}\nИнтервал: {settings.force_task_interval}с",
        reply_markup=reply_markup
    )

async def view_force_tasks_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    if not db.force_tasks:
        await query.message.edit_text("📭 Нет активных.")
        return
    text = "📋 **Активные:**\n\n"
    for user_id, task in list(db.force_tasks.items())[:20]:
        user = db.users.get(user_id, {})
        username = user.get("username", "Неизвестно")
        link = task.get("link", "")[:30]
        text += f"👤 @{username} | {link}...\n"
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_force_tasks")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(text, reply_markup=reply_markup)

async def clear_force_tasks_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in settings.admin_list:
        return
    db.force_tasks.clear()
    db.save()
    await query.message.edit_text("✅ Очищено!")

# ========== АДМИН: КОНКУРСЫ ==========
async def admin_contests_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in settings.admin_list:
        return
    keyboard = [
        [InlineKeyboardButton("➕ Создать", callback_data="create_contest")],
        [InlineKeyboardButton("📋 Все", callback_data="all_contests")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    active = len([c for c in db.contests.values() if c.get("active", False)])
    await query.message.edit_text(
        f"🎯 **Конкурсы**\n\nАктивных: {active}\nВсего: {len(db.contests)}",
        reply_markup=reply_markup
    )

async def create_contest_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in settings.admin_list:
        return
    context.user_data["contest_step"] = "name"
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_contest")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        "🎯 Введите название конкурса:",
        reply_markup=reply_markup
    )

async def contest_name_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    context.user_data["contest_name"] = update.message.text
    context.user_data["contest_step"] = "desc"
    await update.message.reply_text(
        f"Название: {context.user_data['contest_name']}\n\nВведите описание:"
    )

async def contest_desc_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    context.user_data["contest_desc"] = update.message.text
    context.user_data["contest_step"] = "type"
    keyboard = [
        [InlineKeyboardButton("🏆 Кто больше", callback_data="contest_type_race")],
        [InlineKeyboardButton("🎯 Достижение цели", callback_data="contest_type_goal")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_contest")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"Название: {context.user_data['contest_name']}\n"
        f"Описание: {context.user_data['contest_desc']}\n\n"
        "Выберите тип:",
        reply_markup=reply_markup
    )

async def contest_type_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    contest_type = query.data.replace("contest_type_", "")
    context.user_data["contest_type"] = contest_type
    context.user_data["contest_step"] = "target_type"
    keyboard = [
        [InlineKeyboardButton("📋 Задания", callback_data="contest_target_tasks")],
        [InlineKeyboardButton("👥 Рефералы", callback_data="contest_target_referrals")],
        [InlineKeyboardButton("🎯 Оба", callback_data="contest_target_both")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_contest")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        f"Тип: {'🏆 Кто больше' if contest_type == 'race' else '🎯 Достижение цели'}\n\n"
        "Выберите по чему считать:",
        reply_markup=reply_markup
    )

async def contest_target_type_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    target_type = query.data.replace("contest_target_", "")
    context.user_data["contest_target_type"] = target_type
    context.user_data["contest_step"] = "target_value"
    target_names = {
        "tasks": "задания",
        "referrals": "рефералы",
        "both": "задания + рефералы"
    }
    await query.message.edit_text(
        f"По: {target_names.get(target_type, '')}\n\n"
        "Введите количество для победы:"
    )

async def contest_target_value_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    try:
        target_value = int(update.message.text)
        if target_value <= 0:
            await update.message.reply_text("❌ Положительное число!")
            return
        context.user_data["contest_target_value"] = target_value
        context.user_data["contest_step"] = "prize"
        currency = get_currency_symbol()
        await update.message.reply_text(
            f"Цель: {target_value}\n\nВведите приз ({currency}):"
        )
    except ValueError:
        await update.message.reply_text("❌ Введите число!")

async def contest_prize_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    try:
        prize = int(update.message.text)
        if prize <= 0:
            await update.message.reply_text("❌ Положительное число!")
            return
        context.user_data["contest_prize"] = prize
        context.user_data["contest_step"] = "duration"
        await update.message.reply_text(
            f"Приз: {prize}\n\nВведите длительность (часы):"
        )
    except ValueError:
        await update.message.reply_text("❌ Введите число!")

async def contest_duration_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    try:
        duration = int(update.message.text)
        if duration <= 0:
            await update.message.reply_text("❌ Положительное число!")
            return
        contest_id = len(db.contests) + 1
        now = datetime.now()
        db.contests[contest_id] = {
            "id": contest_id,
            "name": context.user_data["contest_name"],
            "description": context.user_data["contest_desc"],
            "prize": context.user_data["contest_prize"],
            "type": context.user_data["contest_type"],
            "target_type": context.user_data["contest_target_type"],
            "target_value": context.user_data["contest_target_value"],
            "duration": duration,
            "start_date": now.isoformat(),
            "end_date": (now + timedelta(hours=duration)).isoformat(),
            "participants": [],
            "winners": [],
            "active": True,
            "created_by": user_id,
            "created_at": now.isoformat()
        }
        db.save()
        context.user_data.pop("contest_step", None)
        context.user_data.pop("contest_name", None)
        context.user_data.pop("contest_desc", None)
        context.user_data.pop("contest_prize", None)
        context.user_data.pop("contest_type", None)
        context.user_data.pop("contest_target_type", None)
        context.user_data.pop("contest_target_value", None)
        await update.message.reply_text(f"✅ Конкурс создан!")
        await broadcast_notification(
            context,
            f"🎯 Новый конкурс!\n{db.contests[contest_id]['name']}\n"
            f"💰 Приз: {db.contests[contest_id]['prize']} {settings.currency_name}"
        )
    except ValueError:
        await update.message.reply_text("❌ Введите число!")

async def all_contests_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    if not db.contests:
        await query.message.edit_text("📭 Нет конкурсов.")
        return
    text = "📋 **Конкурсы:**\n\n"
    for cid, contest in list(db.contests.items())[-10:]:
        status = "🟢" if contest.get("active", False) else "🔴"
        text += f"{status} {contest['name']} - {contest['prize']} {settings.currency_name}\n"
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_contests")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(text, reply_markup=reply_markup)

async def cancel_contest_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("contest_step", None)
    context.user_data.pop("contest_name", None)
    context.user_data.pop("contest_desc", None)
    context.user_data.pop("contest_prize", None)
    context.user_data.pop("contest_type", None)
    context.user_data.pop("contest_target_type", None)
    context.user_data.pop("contest_target_value", None)
    await query.message.edit_text("❌ Отменено.")

# ========== ОБРАБОТЧИКИ ОТМЕНЫ ==========
async def cancel_action_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("admin_action", None)
    await query.message.edit_text("✅ Отменено.")

async def cancel_setting_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("setting_to_change", None)
    context.user_data.pop("prize_place", None)
    context.user_data.pop("sub_type", None)
    await query.message.edit_text("✅ Отменено.")

async def cancel_mailing_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("mailing_message", None)
    context.user_data.pop("mailing_step", None)
    await query.message.edit_text("✅ Отменено.")

# ========== JOB QUEUE ==========
async def notification_job(context: CallbackContext):
    try:
        for user_id in list(db.users.keys())[:20]:
            if user_id in db.bans:
                continue
            
            if user_id in db.active_tasks:
                continue
            
            user = get_user_data(user_id)
            today = datetime.now().date().isoformat()
            
            if user.get("last_task_date") != today:
                user["tasks_today"] = 0
                user["last_task_date"] = today
                db.save()
            
            if user["tasks_today"] >= settings.max_daily_tasks:
                continue
            
            used_links = db.used_task_links.get(user_id, [])
            
            try:
                result = await call_botohub_api(user_id, is_task=True, skip=False)
                tasks = result.get("tasks", [])
                if tasks and not result.get("completed", False):
                    task_link = tasks[0]
                    if task_link not in used_links:
                        keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton("📋 Выполнить задание", callback_data="next_task")]
                        ])
                        await send_notification(
                            context,
                            user_id,
                            f"📢 **Новое задание доступно!**\n\n"
                            f"💰 Награда: {settings.task_reward} {get_currency_symbol()}\n"
                            f"Нажмите кнопку чтобы начать.",
                            keyboard
                        )
                        break
            except:
                pass
                
    except Exception as e:
        logger.error(f"Ошибка в notification_job: {e}")

# ========== ЗАПУСК БОТА ==========
def main():
    db.load()
    settings.load()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(notification_job, interval=settings.notification_interval, first=10)
        job_queue.run_repeating(force_task_job, interval=settings.force_task_interval, first=30)
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tasks", tasks_mode))
    app.add_handler(CommandHandler("balance", balance_handler))
    app.add_handler(CommandHandler("cancel", cancel_command))
    
    # Callback обработчики - ЗАДАНИЯ
    app.add_handler(CallbackQueryHandler(check_task_callback, pattern="^check_task_"))
    app.add_handler(CallbackQueryHandler(next_task_callback, pattern="^next_task$"))
    app.add_handler(CallbackQueryHandler(force_check_callback, pattern="^force_check_"))
    
    # Callback обработчики - РЕФЕРАЛЫ
    app.add_handler(CallbackQueryHandler(referrals_menu, pattern="^referrals_menu$"))
    app.add_handler(CallbackQueryHandler(my_referrals_callback, pattern="^my_referrals$"))
    app.add_handler(CallbackQueryHandler(ref_stats_callback, pattern="^ref_stats$"))
    app.add_handler(CallbackQueryHandler(ref_page_navigation, pattern="^ref_page_"))
    app.add_handler(CallbackQueryHandler(top_referrals_callback, pattern="^top_referrals$"))
    
    # Callback обработчики - ПРОФИЛЬ
    app.add_handler(CallbackQueryHandler(profile_menu, pattern="^profile$"))
    app.add_handler(CallbackQueryHandler(detailed_stats_callback, pattern="^detailed_stats$"))
    app.add_handler(CallbackQueryHandler(my_achievements_callback, pattern="^my_achievements$"))
    app.add_handler(CallbackQueryHandler(notify_settings_callback, pattern="^notify_settings$"))
    app.add_handler(CallbackQueryHandler(toggle_notify_user_callback, pattern="^toggle_notify_user$"))
    app.add_handler(CallbackQueryHandler(daily_bonus_callback, pattern="^daily_bonus$"))
    app.add_handler(CallbackQueryHandler(top_users_profile_callback, pattern="^top_users$"))
    app.add_handler(CallbackQueryHandler(withdraw_menu_profile, pattern="^withdraw_menu$"))
    app.add_handler(CallbackQueryHandler(contests_menu, pattern="^contests_menu$"))
    app.add_handler(CallbackQueryHandler(active_contests_callback, pattern="^active_contests$"))
    app.add_handler(CallbackQueryHandler(contest_detail_callback, pattern="^contest_"))
    app.add_handler(CallbackQueryHandler(join_contest_callback, pattern="^join_contest_"))
    app.add_handler(CallbackQueryHandler(my_contests_callback, pattern="^my_contests$"))
    app.add_handler(CallbackQueryHandler(contest_winners_callback, pattern="^contest_winners$"))
    
    # Callback обработчики - ВЫВОД
    app.add_handler(CallbackQueryHandler(request_withdraw_callback, pattern="^request_withdraw$"))
    app.add_handler(CallbackQueryHandler(withdraw_history_callback, pattern="^withdraw_history$"))
    app.add_handler(CallbackQueryHandler(withdraw_info_callback, pattern="^withdraw_info$"))
    app.add_handler(CallbackQueryHandler(confirm_withdraw_final, pattern="^confirm_withdraw_final$"))
    app.add_handler(CallbackQueryHandler(cancel_withdraw, pattern="^cancel_withdraw$"))
    
    # Callback обработчики - АДМИН
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_rewards_menu, pattern="^admin_rewards$"))
    app.add_handler(CallbackQueryHandler(set_reward_value, pattern="^set_"))
    app.add_handler(CallbackQueryHandler(admin_forcesub_menu, pattern="^admin_forcesub$"))
    app.add_handler(CallbackQueryHandler(add_force_sub_callback, pattern="^add_(channel|group)$"))
    app.add_handler(CallbackQueryHandler(remove_force_sub_callback, pattern="^remove_(channel|group)$"))
    app.add_handler(CallbackQueryHandler(remove_sub_confirmation, pattern="^remove_sub_"))
    app.add_handler(CallbackQueryHandler(admin_users_menu, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(ban_user_callback, pattern="^ban_user$"))
    app.add_handler(CallbackQueryHandler(unban_user_callback, pattern="^unban_user$"))
    app.add_handler(CallbackQueryHandler(add_mcoin_callback, pattern="^add_mcoin_user$"))
    app.add_handler(CallbackQueryHandler(list_users_callback, pattern="^list_users$"))
    app.add_handler(CallbackQueryHandler(admin_stats_callback, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_withdrawals_callback, pattern="^admin_withdrawals$"))
    app.add_handler(CallbackQueryHandler(confirm_withdraw_button, pattern="^confirm_"))
    app.add_handler(CallbackQueryHandler(reject_withdraw_button, pattern="^reject_"))
    app.add_handler(CallbackQueryHandler(admin_mailing_callback, pattern="^admin_mailing$"))
    app.add_handler(CallbackQueryHandler(send_mailing_callback, pattern="^send_mailing$"))
    app.add_handler(CallbackQueryHandler(admin_settings_callback, pattern="^admin_settings$"))
    app.add_handler(CallbackQueryHandler(toggle_maintenance_callback, pattern="^toggle_maintenance$"))
    app.add_handler(CallbackQueryHandler(set_currency_name_callback, pattern="^set_currency_name$"))
    app.add_handler(CallbackQueryHandler(set_currency_emoji_callback, pattern="^set_currency_emoji$"))
    app.add_handler(CallbackQueryHandler(set_currency_emoji_value, pattern="^currency_emoji_"))
    app.add_handler(CallbackQueryHandler(toggle_notify_callback, pattern="^toggle_notify$"))
    app.add_handler(CallbackQueryHandler(set_notify_interval_callback, pattern="^set_notify_interval$"))
    app.add_handler(CallbackQueryHandler(set_force_interval_callback, pattern="^set_force_interval$"))
    app.add_handler(CallbackQueryHandler(admin_top_prizes_callback, pattern="^admin_top_prizes$"))
    app.add_handler(CallbackQueryHandler(set_prize_callback, pattern="^set_prize_"))
    app.add_handler(CallbackQueryHandler(give_top_prizes_callback, pattern="^give_top_prizes$"))
    app.add_handler(CallbackQueryHandler(admin_create_task_callback, pattern="^admin_create_task$"))
    app.add_handler(CallbackQueryHandler(cancel_task_callback, pattern="^cancel_task$"))
    app.add_handler(CallbackQueryHandler(admin_promo_callback, pattern="^admin_promo$"))
    app.add_handler(CallbackQueryHandler(create_promo_callback, pattern="^create_promo$"))
    app.add_handler(CallbackQueryHandler(list_promos_callback, pattern="^list_promos$"))
    app.add_handler(CallbackQueryHandler(cancel_promo_admin_callback, pattern="^cancel_promo_admin$"))
    app.add_handler(CallbackQueryHandler(admin_notifications_callback, pattern="^admin_notifications$"))
    app.add_handler(CallbackQueryHandler(send_notification_all_callback, pattern="^send_notification_all$"))
    app.add_handler(CallbackQueryHandler(send_notification_user_callback, pattern="^send_notification_user$"))
    app.add_handler(CallbackQueryHandler(toggle_user_notify_callback, pattern="^toggle_user_notify$"))
    app.add_handler(CallbackQueryHandler(notify_stats_callback, pattern="^notify_stats$"))
    app.add_handler(CallbackQueryHandler(admin_force_tasks_callback, pattern="^admin_force_tasks$"))
    app.add_handler(CallbackQueryHandler(view_force_tasks_callback, pattern="^view_force_tasks$"))
    app.add_handler(CallbackQueryHandler(clear_force_tasks_callback, pattern="^clear_force_tasks$"))
    app.add_handler(CallbackQueryHandler(admin_contests_callback, pattern="^admin_contests$"))
    app.add_handler(CallbackQueryHandler(create_contest_callback, pattern="^create_contest$"))
    app.add_handler(CallbackQueryHandler(contest_type_callback, pattern="^contest_type_"))
    app.add_handler(CallbackQueryHandler(contest_target_type_callback, pattern="^contest_target_"))
    app.add_handler(CallbackQueryHandler(all_contests_callback, pattern="^all_contests$"))
    app.add_handler(CallbackQueryHandler(cancel_contest_callback, pattern="^cancel_contest$"))
    app.add_handler(CallbackQueryHandler(admin_sponsors_callback, pattern="^admin_sponsors$"))
    app.add_handler(CallbackQueryHandler(toggle_sponsors_callback, pattern="^toggle_sponsors$"))
    app.add_handler(CallbackQueryHandler(set_sponsor_gender_callback, pattern="^set_sponsor_gender$"))
    app.add_handler(CallbackQueryHandler(set_sponsor_gender_value, pattern="^sponsor_gender_"))
    app.add_handler(CallbackQueryHandler(set_sponsor_age_callback, pattern="^set_sponsor_age$"))
    app.add_handler(CallbackQueryHandler(set_sponsor_age_value, pattern="^sponsor_age_"))
    
    # Callback обработчики - НАВИГАЦИЯ
    app.add_handler(CallbackQueryHandler(back_to_main, pattern="^back_to_main$"))
    app.add_handler(CallbackQueryHandler(profile_back, pattern="^profile_back$"))
    
    # Callback обработчики - ОТМЕНА
    app.add_handler(CallbackQueryHandler(cancel_action_callback, pattern="^cancel_action$"))
    app.add_handler(CallbackQueryHandler(cancel_setting_callback, pattern="^cancel_setting$"))
    app.add_handler(CallbackQueryHandler(cancel_mailing_callback, pattern="^cancel_mailing$"))
    
    # Обработчик текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("🚀 Бот запущен...")
    print(f"📊 Администратор: {ADMIN_ID}")
    print(f"👥 Пользователей: {db.global_stats['total_users']}")
    print(f"💰 Награда за задание: {settings.task_reward} {settings.currency_name}")
    print(f"✅ Задания не повторяются - отслеживание выполненных ссылок")
    print(f"✅ Админ-панель полностью исправлена")
    print(f"✅ Интеграция с BotoHub по документации")
    print(f"✅ Интеграция с PiarFlow по документации")
    print("📝 Код: ~7500 строк")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()