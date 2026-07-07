import asyncio
import random
import json
import os
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple, Any
from collections import defaultdict
import time
import string
import hashlib

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
BOT_TOKEN = "8251949164:AAFRGh0wB7C0ZdMQ95oNPrrFGTsd6R-5h_U"

BOTOHUB_TOKEN = "ae49fee8-827d-4771-a6bd-7e9ba579b710"
BOTOHUB_API_URL = "https://botohub.me/api/v1/sponsors"

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
        self.bans: Dict[int, Dict] = {}
        self.global_stats: Dict = {
            "total_users": 0,
            "total_mcoins_earned": 0,
            "total_withdrawn": 0,
            "total_tasks_completed": 0,
            "total_referrals": 0
        }
        self.active_tasks: Dict[int, Dict] = {}
        self.used_task_links: Dict[int, List[str]] = {}
        self.promo_codes: Dict[str, Dict] = {}
        self.used_promo: Dict[int, List[str]] = {}
        self.completed_tasks: Dict[int, List[str]] = {}
        self.top_users: Dict[int, Dict] = {}
        self.custom_tasks: Dict[int, Dict] = {}
        self.user_settings: Dict[int, Dict] = {}
        self.daily_claimed: Dict[int, datetime] = {}
        self.achievements: Dict[int, List[str]] = {}
        self.sponsors_cache: Dict = {}
        
    def save(self):
        data = {
            "users": self.users,
            "bans": self.bans,
            "global_stats": self.global_stats,
            "active_tasks": self.active_tasks,
            "used_task_links": self.used_task_links,
            "promo_codes": self.promo_codes,
            "used_promo": self.used_promo,
            "completed_tasks": self.completed_tasks,
            "top_users": self.top_users,
            "custom_tasks": self.custom_tasks,
            "user_settings": self.user_settings,
            "daily_claimed": {k: v.isoformat() for k, v in self.daily_claimed.items()},
            "achievements": self.achievements
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
                    self.bans = {int(k): v for k, v in data.get("bans", {}).items()}
                    self.global_stats = data.get("global_stats", self.global_stats)
                    self.active_tasks = {int(k): v for k, v in data.get("active_tasks", {}).items()}
                    self.used_task_links = {int(k): v for k, v in data.get("used_task_links", {}).items()}
                    self.promo_codes = data.get("promo_codes", {})
                    self.used_promo = {int(k): v for k, v in data.get("used_promo", {}).items()}
                    self.completed_tasks = {int(k): v for k, v in data.get("completed_tasks", {}).items()}
                    self.top_users = {int(k): v for k, v in data.get("top_users", {}).items()}
                    self.custom_tasks = {int(k): v for k, v in data.get("custom_tasks", {}).items()}
                    self.user_settings = {int(k): v for k, v in data.get("user_settings", {}).items()}
                    self.daily_claimed = {int(k): datetime.fromisoformat(v) for k, v in data.get("daily_claimed", {}).items()}
                    self.achievements = {int(k): v for k, v in data.get("achievements", {}).items()}
                logger.info("Данные загружены")
            except Exception as e:
                logger.error(f"Ошибка загрузки данных: {e}")

class BotSettings:
    def __init__(self):
        self.task_reward = 10
        self.referral_reward = 5
        self.daily_reward = 15
        self.min_withdraw = 50
        self.force_sub_sponsors = True
        self.admin_list = [ADMIN_ID]
        self.bot_name = "MCoin Bot"
        self.currency_name = "MCoin"
        self.currency_emoji = "🪙"
        self.max_daily_tasks = 50
        self.maintenance_mode = False
        self.sponsor_gender = None
        self.sponsor_age = None
        self.force_sub_channels = []
        
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
            "notifications_enabled": True
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
    
    if source in ["task", "botohub", "piarflow", "custom"]:
        user["task_earned"] += amount
        user["total_tasks_completed"] += 1
        db.global_stats["total_tasks_completed"] += 1
        update_top_users(user_id)
        check_achievements(user_id)
    elif source == "referral":
        user["referral_earned"] += amount
        db.global_stats["total_referrals"] += 1
    
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
    
    db.top_users[user_id] = {
        "tasks": user["total_tasks_completed"],
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
    
    if user["daily_streak"] >= 7 and "7_streak" not in achievements:
        achievements.append("7_streak")
        add_mcoins(user_id, 50, "achievement_7_streak", "other")
    
    db.achievements[user_id] = achievements
    db.save()

# ========== ИНТЕГРАЦИЯ BOTOHUB ==========
async def call_botohub_api(chat_id: int, gender: str = None, age: str = None) -> dict:
    """Получение спонсоров от BotoHub"""
    headers = {
        "Content-Type": "application/json",
        "Auth": BOTOHUB_TOKEN
    }
    
    payload = {"chat_id": chat_id}
    if gender:
        payload["gender"] = gender
    if age:
        payload["age"] = age

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{BOTOHUB_API_URL}/get-sponsors", json=payload, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"BotoHub ответ для {chat_id}: получены спонсоры")
                    return data
                else:
                    logger.error(f"BotoHub API ошибка: {resp.status}")
                    return {"sponsors": []}
    except Exception as e:
        logger.error(f"BotoHub API исключение: {e}")
        return {"sponsors": []}

async def check_botohub_subscription(chat_id: int, sponsor_ids: List[str]) -> dict:
    """Проверка подписки на спонсоров BotoHub"""
    headers = {
        "Content-Type": "application/json",
        "Auth": BOTOHUB_TOKEN
    }
    
    payload = {
        "chat_id": chat_id,
        "sponsor_ids": sponsor_ids
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{BOTOHUB_API_URL}/check-subscriptions", json=payload, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data
                else:
                    logger.error(f"BotoHub check ошибка: {resp.status}")
                    return {"subscribed": []}
    except Exception as e:
        logger.error(f"BotoHub check исключение: {e}")
        return {"subscribed": []}

# ========== ПРОВЕРКА ПОДПИСОК ==========
async def check_force_subs(user_id: int, bot) -> Tuple[bool, List[Dict]]:
    """Проверка обязательных подписок с получением спонсоров от BotoHub"""
    if not settings.force_sub_sponsors and not settings.force_sub_channels:
        return True, []
    
    not_subscribed = []
    
    # Получаем спонсоров от BotoHub
    if settings.force_sub_sponsors:
        try:
            result = await call_botohub_api(
                user_id, 
                gender=settings.sponsor_gender,
                age=settings.sponsor_age
            )
            sponsors = result.get("sponsors", [])
            
            if sponsors:
                # Проверяем подписку на каждого спонсора
                sponsor_ids = [s.get("id") for s in sponsors if s.get("id")]
                if sponsor_ids:
                    check_result = await check_botohub_subscription(user_id, sponsor_ids)
                    subscribed_ids = check_result.get("subscribed", [])
                    
                    for sponsor in sponsors:
                        if sponsor.get("id") not in subscribed_ids:
                            not_subscribed.append({
                                "name": sponsor.get("name", "Спонсор"),
                                "link": sponsor.get("link", ""),
                                "source": "botohub"
                            })
        except Exception as e:
            logger.error(f"Ошибка проверки спонсоров: {e}")
    
    # Проверка дополнительных каналов
    for channel in settings.force_sub_channels:
        try:
            member = await bot.get_chat_member(chat_id=f"@{channel}", user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                not_subscribed.append({
                    "name": channel,
                    "link": f"https://t.me/{channel}",
                    "source": "custom"
                })
        except Exception:
            not_subscribed.append({
                "name": channel,
                "link": f"https://t.me/{channel}",
                "source": "custom"
            })
    
    return len(not_subscribed) == 0, not_subscribed

# ========== ЗАДАНИЯ ==========
async def tasks_mode(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    currency = get_currency_symbol()
    
    if settings.maintenance_mode:
        await update.message.reply_text("🔧 Бот на техническом обслуживании.")
        return
    
    # Проверяем обязательные подписки
    passed, not_subscribed = await check_force_subs(user_id, context.bot)
    if not passed:
        await show_subscription_required(update, not_subscribed)
        return
    
    # Проверяем лимит заданий
    user = get_user_data(user_id)
    today = datetime.now().date().isoformat()
    
    if user.get("last_task_date") != today:
        user["tasks_today"] = 0
        user["last_task_date"] = today
        db.save()
    
    if user["tasks_today"] >= settings.max_daily_tasks:
        await update.message.reply_text(
            f"⏰ **Дневной лимит заданий исчерпан!**\n\n"
            f"Вы выполнили {settings.max_daily_tasks} заданий сегодня."
        )
        return
    
    # Проверяем есть ли активное задание
    if user_id in db.active_tasks:
        task = db.active_tasks[user_id]
        await show_task(update, context, task, user_id)
        return
    
    msg = await update.message.reply_text("🔄 Получаем задание...")
    
    # Получаем список выполненных ссылок
    used_links = db.used_task_links.get(user_id, [])
    
    # Пробуем получить задание из BotoHub
    try:
        result = await call_botohub_api(user_id, gender=settings.sponsor_gender, age=settings.sponsor_age)
        tasks = result.get("tasks", [])
        
        if tasks:
            task_link = tasks[0] if isinstance(tasks[0], str) else tasks[0].get("link", "")
            if task_link and task_link not in used_links:
                task = {
                    "link": task_link,
                    "source": "botohub",
                    "price": settings.task_reward
                }
                db.active_tasks[user_id] = task
                db.save()
                await msg.delete()
                await show_task(update, context, task, user_id)
                return
    except Exception as e:
        logger.error(f"Ошибка BotoHub: {e}")
    
    await msg.edit_text(
        "🎉 **Нет активных заданий!**\n\n"
        "Зайдите позже или пригласите друзей!"
    )

async def show_subscription_required(update: Update, not_subscribed: List[Dict]):
    """Показывает сообщение о необходимости подписки"""
    keyboard = []
    
    for i, sponsor in enumerate(not_subscribed[:10]):
        if sponsor.get("link"):
            keyboard.append([InlineKeyboardButton(
                f"🔗 {sponsor.get('name', 'Спонсор')}",
                url=sponsor["link"]
            )])
    
    keyboard.append([InlineKeyboardButton("✅ Проверить подписки", callback_data="check_subscriptions")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "⚠️ **Для использования бота необходимо подписаться:**\n\n"
    for sponsor in not_subscribed:
        text += f"• {sponsor.get('name', 'Спонсор')}\n"
    
    text += "\nПосле подписки нажмите «Проверить подписки»"
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def show_task(update: Update, context: CallbackContext, task: Dict, user_id: int):
    task_url = task.get("link", "")
    task_price = task.get("price", settings.task_reward)
    currency = get_currency_symbol()
    source = task.get("source", "unknown").upper()
    
    keyboard = [
        [InlineKeyboardButton(f"🔗 Перейти к заданию ({source})", url=task_url)],
        [InlineKeyboardButton("✅ Проверить выполнение", callback_data=f"check_task_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    task_text = (
        f"📢 **Новое задание!** 📢\n\n"
        f"🔗 **Ссылка:** {task_url}\n"
        f"💰 **Награда:** {task_price} {currency}\n\n"
        f"**Как выполнить:**\n"
        f"1️⃣ Нажмите «Перейти к заданию»\n"
        f"2️⃣ Подпишитесь на канал\n"
        f"3️⃣ Вернитесь и нажмите «Проверить выполнение»"
    )
    
    if update.callback_query:
        await update.callback_query.message.edit_text(
            task_text, 
            reply_markup=reply_markup, 
            disable_web_page_preview=True
        )
    else:
        await update.message.reply_text(
            task_text, 
            reply_markup=reply_markup, 
            disable_web_page_preview=True
        )

async def check_subscriptions_callback(update: Update, context: CallbackContext):
    """Проверка подписок по кнопке"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    passed, not_subscribed = await check_force_subs(user_id, context.bot)
    
    if passed:
        await query.message.edit_text(
            "✅ **Все подписки подтверждены!**\n\n"
            "Теперь вы можете использовать бота."
        )
    else:
        await query.message.delete()
        await show_subscription_required(update, not_subscribed)

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
    task_url = task.get("link", "")
    task_price = task.get("price", settings.task_reward)
    currency = get_currency_symbol()
    
    await query.message.edit_text("🔍 **Проверяем выполнение задания...**")
    
    try:
        # Проверка подписки через BotoHub
        result = await call_botohub_api(user_id, gender=settings.sponsor_gender, age=settings.sponsor_age)
        
        # Если пользователь подписался (простая проверка)
        if result.get("success"):
            # Добавляем ссылку в выполненные
            if user_id not in db.used_task_links:
                db.used_task_links[user_id] = []
            if task_url not in db.used_task_links[user_id]:
                db.used_task_links[user_id].append(task_url)
            
            add_mcoins(user_id, task_price, f"task_{task_url}", "task")
            user = get_user_data(user_id)
            user["tasks_today"] += 1
            
            db.active_tasks.pop(user_id, None)
            db.save()
            
            await query.message.edit_text(
                f"✅ **Задание выполнено!** ✅\n\n"
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
                f"🔗 Пожалуйста, подпишитесь:\n{task_url}\n\n"
                f"После подписки нажмите «Проверить выполнение»",
                disable_web_page_preview=True
            )
            
            keyboard = [
                [InlineKeyboardButton("🔗 Перейти к заданию", url=task_url)],
                [InlineKeyboardButton("✅ Проверить выполнение", callback_data=f"check_task_{user_id}")]
            ]
            await query.edit_message_reply_markup(InlineKeyboardMarkup(keyboard))
                
    except Exception as e:
        logger.error(f"Ошибка проверки задания: {e}")
        await query.message.edit_text(
            f"❌ Ошибка при проверке: {e}\n\nПопробуйте еще раз.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Проверить еще раз", callback_data=f"check_task_{user_id}")]
            ])
        )

async def next_task_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Проверяем лимит
    user = get_user_data(user_id)
    today = datetime.now().date().isoformat()
    
    if user.get("last_task_date") != today:
        user["tasks_today"] = 0
        user["last_task_date"] = today
        db.save()
    
    if user["tasks_today"] >= settings.max_daily_tasks:
        await query.message.edit_text(f"⏰ **Дневной лимит заданий исчерпан!**")
        return
    
    await query.message.edit_text("🔄 Получаем новое задание...")
    
    # Логика получения нового задания аналогична tasks_mode
    used_links = db.used_task_links.get(user_id, [])
    
    try:
        result = await call_botohub_api(user_id, gender=settings.sponsor_gender, age=settings.sponsor_age)
        tasks = result.get("tasks", [])
        
        if tasks:
            task_link = tasks[0] if isinstance(tasks[0], str) else tasks[0].get("link", "")
            if task_link and task_link not in used_links:
                task = {
                    "link": task_link,
                    "source": "botohub",
                    "price": settings.task_reward
                }
                db.active_tasks[user_id] = task
                db.save()
                await show_task(update, context, task, user_id)
                return
    except Exception as e:
        logger.error(f"Ошибка BotoHub: {e}")
    
    await query.message.edit_text("🎉 **Нет активных заданий!**\n\nЗайдите позже.")

# ========== РЕФЕРАЛЬНАЯ СИСТЕМА ==========
async def referrals_menu(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    currency = get_currency_symbol()
    
    bot_username = context.bot.username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    ref_count = len(user["referrals"])
    
    keyboard = [
        [InlineKeyboardButton("📋 Список рефералов", callback_data="my_referrals")],
        [InlineKeyboardButton("📊 Статистика", callback_data="ref_stats")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👥 **Реферальная программа** 👥\n\n"
        f"👥 **Рефералов:** {ref_count}\n"
        f"💰 **Заработано:** {user['referral_earned']} {currency}\n\n"
        f"🎁 **Награда за реферала:** {settings.referral_reward} {currency}\n\n"
        f"🔗 **Ваша реферальная ссылка:**\n`{ref_link}`",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

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
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👤 **Профиль** 👤\n\n"
        f"👤 Username: @{username}\n"
        f"💰 {currency}: {format_number(user['mcoin'])}\n"
        f"📈 Всего заработано: {format_number(user['total_earned'])}\n"
        f"✅ Выполнено заданий: {user['total_tasks_completed']}\n"
        f"👥 Рефералов: {len(user['referrals'])}\n"
        f"🔥 Серия: {user['daily_streak']} дней\n"
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
                f"📊 Серия: {user['daily_streak']} дней"
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
    
    reward = settings.daily_reward + int(settings.daily_reward * (user["daily_streak"] * 0.1))
    add_mcoins(user_id, reward, "daily_bonus", "daily")
    
    user["daily_last"] = now.isoformat()
    user["last_streak_date"] = now.isoformat()
    db.daily_claimed[user_id] = now
    db.save()
    
    await query.message.edit_text(
        f"🎁 **Ежедневный бонус!** 🎁\n\n"
        f"💰 Вы получили: {reward} {currency}\n"
        f"📊 Серия: {user['daily_streak']} дней\n"
        f"💰 Ваш баланс: {format_number(user['mcoin'])} {currency}"
    )

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
        [InlineKeyboardButton("📨 Рассылка", callback_data="admin_mailing")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="admin_settings")],
        [InlineKeyboardButton("📋 Задания", callback_data="admin_create_task")],
        [InlineKeyboardButton("🎫 Промокоды", callback_data="admin_promo")],
        [InlineKeyboardButton("⚙️ Спонсоры", callback_data="admin_sponsors")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"⚙️ **Админ панель** ⚙️\n\n"
        f"👥 Пользователей: {db.global_stats['total_users']}\n"
        f"💰 Всего заработано: {format_number(db.global_stats['total_mcoins_earned'])} {currency}\n"
        f"✅ Заданий выполнено: {db.global_stats['total_tasks_completed']}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

async def admin_sponsors_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton(f"Обязательные спонсоры: {'✅' if settings.force_sub_sponsors else '❌'}", 
                             callback_data="toggle_sponsors")],
        [InlineKeyboardButton(f"Пол: {settings.sponsor_gender or 'Не указан'}", 
                             callback_data="set_sponsor_gender")],
        [InlineKeyboardButton(f"Возраст: {settings.sponsor_age or 'Не указан'}", 
                             callback_data="set_sponsor_age")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "⚙️ **Настройки спонсоров** ⚙️\n\n"
        f"Обязательные спонсоры: {'Включены' if settings.force_sub_sponsors else 'Выключены'}\n"
        f"Пол: {settings.sponsor_gender or 'Не указан'}\n"
        f"Возраст: {settings.sponsor_age or 'Не указан'}\n\n"
        "Эти настройки влияют на задания от BotoHub",
        reply_markup=reply_markup
    )

async def toggle_sponsors_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    settings.force_sub_sponsors = not settings.force_sub_sponsors
    settings.save()
    await query.message.edit_text(f"Обязательные спонсоры {'включены' if settings.force_sub_sponsors else 'выключены'}!")

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if user_id in db.bans:
        await update.message.reply_text("⛔ **Вы забанены!** ⛔")
        return
    
    user_data = get_user_data(user_id)
    if update.effective_user.username:
        user_data["username"] = update.effective_user.username
        db.save()
    
    # Обработка реферальной ссылки
    if context.args and context.args[0].startswith("ref_"):
        referrer_id = int(context.args[0].replace("ref_", ""))
        if referrer_id != user_id and referrer_id not in db.bans:
            if not user_data.get("referrer"):
                user_data["referrer"] = referrer_id
                referrer_data = get_user_data(referrer_id)
                referrer_data["referrals"].append(user_id)
                
                add_mcoins(referrer_id, settings.referral_reward, "referral_bonus", "referral")
                db.save()
                
                try:
                    await context.bot.send_message(
                        referrer_id,
                        f"👥 **Новый реферал!**\n\n"
                        f"{update.effective_user.first_name} присоединился по вашей ссылке!\n"
                        f"💰 Вы получили: {settings.referral_reward} {get_currency_symbol()}"
                    )
                except Exception as e:
                    logger.error(f"Не удалось отправить сообщение рефереру: {e}")
    
    # Обработка промокода
    if context.args and context.args[0].startswith("promo_"):
        code = context.args[0].replace("promo_", "").upper()
        
        if code in db.promo_codes:
            promo = db.promo_codes[code]
            
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
                        f"🎁 Вы получили: {reward} {get_currency_symbol()}"
                    )
    
    # Проверка подписок
    passed, not_subscribed = await check_force_subs(user_id, context.bot)
    
    welcome_text = (
        f"👋 Привет, {update.effective_user.first_name}!\n\n"
        f"Выполняй задания и зарабатывай {get_currency_symbol()}!\n\n"
        f"💰 Награда за задание: {settings.task_reward} {get_currency_symbol()}"
    )
    
    if not passed:
        await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard(user_id))
        await show_subscription_required(update, not_subscribed)
    else:
        await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard(user_id))

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
    
    # Проверка подписок при любом действии
    passed, not_subscribed = await check_force_subs(user_id, context.bot)
    if not passed and text != "⚙️ Админ панель":
        await show_subscription_required(update, not_subscribed)
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
    
    await update.message.reply_text(
        f"💰 **Ваш баланс** 💰\n\n"
        f"🎮 {currency}: {format_number(user['mcoin'])}\n\n"
        f"📊 **Статистика:**\n"
        f"💰 Всего заработано: {format_number(user['total_earned'])}\n"
        f"✅ С заданий: {format_number(user['task_earned'])}\n"
        f"👥 С рефералов: {format_number(user['referral_earned'])}\n"
        f"🔥 Серия: {user['daily_streak']} дней",
        parse_mode="Markdown"
    )

async def back_to_main(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text="Главное меню:",
        reply_markup=get_main_keyboard(query.from_user.id)
    )

# ========== ЗАПУСК БОТА ==========
def main():
    db.load()
    settings.load()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tasks", tasks_mode))
    app.add_handler(CommandHandler("balance", balance_handler))
    
    # Callback обработчики
    app.add_handler(CallbackQueryHandler(check_task_callback, pattern="^check_task_"))
    app.add_handler(CallbackQueryHandler(next_task_callback, pattern="^next_task$"))
    app.add_handler(CallbackQueryHandler(check_subscriptions_callback, pattern="^check_subscriptions$"))
    
    # Профиль
    app.add_handler(CallbackQueryHandler(profile_menu, pattern="^profile$"))
    app.add_handler(CallbackQueryHandler(daily_bonus_callback, pattern="^daily_bonus$"))
    
    # Админ
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_sponsors_callback, pattern="^admin_sponsors$"))
    app.add_handler(CallbackQueryHandler(toggle_sponsors_callback, pattern="^toggle_sponsors$"))
    
    # Навигация
    app.add_handler(CallbackQueryHandler(back_to_main, pattern="^back_to_main$"))
    
    # Текстовые сообщения
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("🚀 Бот запущен...")
    print(f"📊 Администратор: {ADMIN_ID}")
    print(f"💎 Название: {settings.bot_name}")
    print(f"👥 Пользователей: {db.global_stats['total_users']}")
    print(f"💰 Награда за задание: {settings.task_reward} {settings.currency_name}")
    print(f"🔄 Обязательные спонсоры: {'Включены' if settings.force_sub_sponsors else 'Выключены'}")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()