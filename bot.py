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
BOT_TOKEN = "8251949164:AAHe6RTvf3OXniMVZd7_ICCH1BPtRNxHKFo"

# BotoHub
BOTOHUB_TOKEN = "c72ddc9b-c2dc-4e3e-a985-7d51f0d77f58"
BOTOHUB_API_URL = "https://botohub.me/get-tasks"

# PiarFlow
PIARFLOW_API_KEY = "lCNi-V2kcnJoX9NjpOOtAOL9ee_0yyob"
PIARFLOW_API_URL = "https://piarflow.com/v1"

ADMIN_ID = 5356400377

# Состояния для ConversationHandler
(AWAITING_WITHDRAW_AMOUNT, AWAITING_WITHDRAW_CONFIRM, AWAITING_BAN_USERNAME,
 AWAITING_UNBAN_USERNAME, AWAITING_ADD_MCOIN_USERNAME, MAILING_TEXT, 
 AWAITING_SETTING_VALUE, AWAITING_FORCE_SUB_INPUT, AWAITING_CONTEST_NAME,
 AWAITING_CONTEST_DESC, AWAITING_CONTEST_PRIZE, AWAITING_CONTEST_DURATION,
 AWAITING_CONTEST_TYPE, AWAITING_CONTEST_TARGET, AWAITING_EDIT_SETTING,
 AWAITING_PRIZE_1, AWAITING_PRIZE_2, AWAITING_PRIZE_3,
 AWAITING_CUSTOM_TASK_LINK, AWAITING_CUSTOM_TASK_REWARD) = range(20)

# Файлы для хранения данных
DATA_FILE = "bot_data.json"
SETTINGS_FILE = "settings.json"
CONTESTS_FILE = "contests.json"

# ========== ЭМОДЗИ ДЛЯ ВАЛЮТ ==========
CURRENCY_EMOJIS = {
    "MCoin": "🪙",
    "Coin": "💰",
    "Token": "🔮",
    "Star": "⭐",
    "Gem": "💎",
    "Crystal": "🔷",
    "Gold": "🏅",
    "Silver": "🥈",
    "Bronze": "🥉",
    "Diamond": "💠"
}

# ========== СТРУКТУРА ДАННЫХ ==========
class BotDatabase:
    def __init__(self):
        self.users: Dict[int, Dict] = {}
        self.withdraw_requests: Dict[int, Dict] = {}
        self.task_history: Dict[int, List[Dict]] = {}
        self.bans: Dict[int, Dict] = {}
        self.global_stats: Dict = {
            "total_users": 0,
            "total_mcoins_earned": 0,
            "total_withdrawn": 0,
            "total_tasks_completed": 0,
            "total_referrals": 0,
        }
        self.pending_checks: Dict[int, Dict] = {}
        self.current_task: Dict[int, Dict] = {}
        self.task_queue: Dict[int, List[Dict]] = {}
        self.completed_tasks: Dict[int, List[str]] = {}
        self.top_users: Dict[int, Dict] = {}
        self.monthly_top: Dict[int, Dict] = {}
        self.contests: Dict[int, Dict] = {}
        self.notifications: Dict[int, List[Dict]] = {}
        self.last_notification: Dict[int, datetime] = {}
        self.contest_participants: Dict[int, List[int]] = {}
        self.custom_tasks: Dict[int, Dict] = {}
        
    def save(self):
        data = {
            "users": self.users,
            "withdraw_requests": self.withdraw_requests,
            "task_history": self.task_history,
            "bans": self.bans,
            "global_stats": self.global_stats,
            "pending_checks": self.pending_checks,
            "current_task": self.current_task,
            "task_queue": self.task_queue,
            "completed_tasks": self.completed_tasks,
            "top_users": self.top_users,
            "monthly_top": self.monthly_top,
            "contests": self.contests,
            "notifications": self.notifications,
            "last_notification": self.last_notification,
            "contest_participants": self.contest_participants,
            "custom_tasks": self.custom_tasks
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
                    self.task_history = {int(k): v for k, v in data.get("task_history", {}).items()}
                    self.bans = {int(k): v for k, v in data.get("bans", {}).items()}
                    self.global_stats = data.get("global_stats", self.global_stats)
                    self.pending_checks = {int(k): v for k, v in data.get("pending_checks", {}).items()}
                    self.current_task = {int(k): v for k, v in data.get("current_task", {}).items()}
                    self.task_queue = {int(k): v for k, v in data.get("task_queue", {}).items()}
                    self.completed_tasks = {int(k): v for k, v in data.get("completed_tasks", {}).items()}
                    self.top_users = {int(k): v for k, v in data.get("top_users", {}).items()}
                    self.monthly_top = {int(k): v for k, v in data.get("monthly_top", {}).items()}
                    self.contests = {int(k): v for k, v in data.get("contests", {}).items()}
                    self.notifications = {int(k): v for k, v in data.get("notifications", {}).items()}
                    self.last_notification = {int(k): datetime.fromisoformat(v) for k, v in data.get("last_notification", {}).items()}
                    self.contest_participants = {int(k): v for k, v in data.get("contest_participants", {}).items()}
                    self.custom_tasks = {int(k): v for k, v in data.get("custom_tasks", {}).items()}
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
        self.welcome_message = "Добро пожаловать в бот! 🎉"
        self.referral_program = True
        self.admin_list = [ADMIN_ID]
        self.bot_name = "MCoin Bot"
        self.bot_description = "Зарабатывай MCoin выполняя задания!"
        self.currency_name = "MCoin"
        self.currency_emoji = "🪙"
        self.withdraw_commission = 0.05
        self.max_daily_tasks = 20
        self.maintenance_mode = False
        self.top_prize_1 = 100
        self.top_prize_2 = 50
        self.top_prize_3 = 30
        self.notification_interval = 300
        self.contest_enabled = True
        self.auto_notify = True
        
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
def get_currency_symbol() -> str:
    return f"{settings.currency_emoji} {settings.currency_name}"

def get_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    if user_id in db.bans:
        return ReplyKeyboardMarkup([["ℹ️ Я в бане"]], resize_keyboard=True)
    
    currency = get_currency_symbol()
    
    keyboard = [
        [KeyboardButton(f"💰 {currency}"), KeyboardButton("📋 Задания")],
        [KeyboardButton("👥 Рефералы"), KeyboardButton("🏆 Ежедневный бонус")],
        [KeyboardButton("💸 Вывод средств"), KeyboardButton("📊 Статистика")],
        [KeyboardButton("🏅 Топ пользователей"), KeyboardButton("🎯 Конкурсы")],
        [KeyboardButton("❓ Помощь")]
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
            "last_withdraw_date": None,
            "total_tasks_completed": 0,
            "completed_links": [],
            "monthly_tasks": 0,
            "monthly_date": datetime.now().strftime("%Y-%m"),
            "contest_wins": 0,
            "notifications_enabled": True
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
    
    if source in ["task", "botohub", "piarflow", "custom"]:
        user["task_earned"] += amount
        user["total_tasks_completed"] += 1
        user["monthly_tasks"] += 1
        user["monthly_date"] = datetime.now().strftime("%Y-%m")
        db.global_stats["total_tasks_completed"] += 1
        update_top_users(user_id)
    elif source == "referral":
        user["referral_earned"] += amount
        db.global_stats["total_referrals"] += 1
    elif source == "top_prize":
        user["task_earned"] += amount
    elif source == "contest":
        user["contest_wins"] += 1
    
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

async def check_new_tasks(context: CallbackContext):
    if not settings.auto_notify:
        return
    
    for user_id in db.users.keys():
        try:
            result = await call_botohub_api(user_id, is_task=True, skip=False)
            tasks = result.get("tasks", [])
            
            if tasks and not result.get("completed", False):
                last_notif = db.last_notification.get(user_id)
                if not last_notif or (datetime.now() - last_notif).seconds > settings.notification_interval:
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("📋 Взять задание", callback_data=f"get_task_{user_id}")]
                    ])
                    currency = get_currency_symbol()
                    await send_notification(
                        context,
                        user_id,
                        f"📢 **Новое задание доступно!**\n\n"
                        f"💰 Награда: {settings.task_reward} {currency}\n"
                        f"Нажмите кнопку ниже, чтобы получить задание.",
                        keyboard
                    )
                    db.last_notification[user_id] = datetime.now()
                    db.save()
        except:
            pass

# ========== КОНКУРСЫ ==========
async def contests_menu(update: Update, context: CallbackContext):
    if not settings.contest_enabled:
        await update.message.reply_text("🎯 Конкурсы временно недоступны!")
        return
    
    keyboard = [
        [InlineKeyboardButton("📋 Активные конкурсы", callback_data="active_contests")],
        [InlineKeyboardButton("📊 Мои участия", callback_data="my_contests")],
        [InlineKeyboardButton("🏆 Победители", callback_data="contest_winners")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎯 **Конкурсы** 🎯\n\n"
        "Участвуйте в конкурсах и выигрывайте призы!\n"
        "Выполняйте задания, приглашайте друзей и занимайте призовые места.",
        reply_markup=reply_markup
    )

async def create_contest_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in settings.admin_list:
        await query.message.edit_text("⛔ Только для администратора!")
        return
    
    context.user_data["contest_step"] = "type"
    
    keyboard = [
        [InlineKeyboardButton("🏆 Кто больше (топовый)", callback_data="contest_type_race")],
        [InlineKeyboardButton("🎯 Достижение цели", callback_data="contest_type_goal")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_contest")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "🎯 **Выбор типа конкурса** 🎯\n\n"
        "🏆 **Кто больше (топовый)** - побеждают те, кто выполнит больше заданий или пригласит больше друзей\n"
        "🎯 **Достижение цели** - победители те, кто первым достигнет цели\n\n"
        "Выберите тип конкурса:",
        reply_markup=reply_markup
    )

async def contest_type_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    contest_type = query.data.replace("contest_type_", "")
    context.user_data["contest_type"] = contest_type
    context.user_data["contest_step"] = "name"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_contest")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    type_names = {
        "race": "🏆 Кто больше",
        "goal": "🎯 Достижение цели"
    }
    
    await query.message.edit_text(
        f"🎯 **{type_names.get(contest_type, '')} конкурс**\n\n"
        "Введите название конкурса:",
        reply_markup=reply_markup
    )

async def contest_name_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    context.user_data["contest_name"] = update.message.text
    context.user_data["contest_step"] = "desc"
    
    await update.message.reply_text(
        f"📝 Название: {context.user_data['contest_name']}\n\n"
        "Введите описание конкурса:"
    )

async def contest_desc_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    context.user_data["contest_desc"] = update.message.text
    context.user_data["contest_step"] = "target_type"
    
    keyboard = [
        [InlineKeyboardButton("📋 По заданиям", callback_data="contest_target_tasks")],
        [InlineKeyboardButton("👥 По рефералам", callback_data="contest_target_referrals")],
        [InlineKeyboardButton("🎯 По заданиям + рефералам", callback_data="contest_target_both")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_contest")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📝 Название: {context.user_data['contest_name']}\n"
        f"📝 Описание: {context.user_data['contest_desc']}\n\n"
        "Выберите по чему будет считаться конкурс:",
        reply_markup=reply_markup
    )

async def contest_target_type_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    target_type = query.data.replace("contest_target_", "")
    context.user_data["contest_target_type"] = target_type
    context.user_data["contest_step"] = "target_value"
    
    target_names = {
        "tasks": "заданий",
        "referrals": "рефералов",
        "both": "заданий + рефералов"
    }
    
    await query.message.edit_text(
        f"📝 Название: {context.user_data['contest_name']}\n"
        f"📝 Описание: {context.user_data['contest_desc']}\n"
        f"📋 Тип: {target_names.get(target_type, '')}\n\n"
        "Введите количество для победы (например: 50):"
    )

async def contest_target_value_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    try:
        target_value = int(update.message.text)
        if target_value <= 0:
            await update.message.reply_text("❌ Значение должно быть положительным!")
            return
        
        context.user_data["contest_target_value"] = target_value
        context.user_data["contest_step"] = "prize"
        
        currency = get_currency_symbol()
        
        await update.message.reply_text(
            f"📝 Название: {context.user_data['contest_name']}\n"
            f"📝 Описание: {context.user_data['contest_desc']}\n"
            f"🎯 Цель: {target_value}\n\n"
            f"Введите призовой фонд ({currency}):"
        )
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число!")

async def contest_prize_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    try:
        prize = int(update.message.text)
        if prize <= 0:
            await update.message.reply_text("❌ Приз должен быть положительным!")
            return
        
        context.user_data["contest_prize"] = prize
        context.user_data["contest_step"] = "duration"
        
        await update.message.reply_text(
            f"📝 Название: {context.user_data['contest_name']}\n"
            f"📝 Описание: {context.user_data['contest_desc']}\n"
            f"🎯 Цель: {context.user_data['contest_target_value']}\n"
            f"💰 Приз: {prize} {settings.currency_name}\n\n"
            "Введите длительность конкурса (в часах):"
        )
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число!")

async def contest_duration_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    try:
        duration = int(update.message.text)
        if duration <= 0:
            await update.message.reply_text("❌ Длительность должна быть положительной!")
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
            "created_at": now.isoformat(),
            "notified": False,
            "completed": False
        }
        
        db.save()
        
        context.user_data.pop("contest_step", None)
        context.user_data.pop("contest_name", None)
        context.user_data.pop("contest_desc", None)
        context.user_data.pop("contest_prize", None)
        context.user_data.pop("contest_duration", None)
        context.user_data.pop("contest_type", None)
        context.user_data.pop("contest_target_type", None)
        context.user_data.pop("contest_target_value", None)
        
        type_names = {
            "race": "🏆 Кто больше",
            "goal": "🎯 Достижение цели"
        }
        
        target_names = {
            "tasks": "задания",
            "referrals": "рефералы",
            "both": "задания + рефералы"
        }
        
        await update.message.reply_text(
            f"✅ **Конкурс создан!** 🎉\n\n"
            f"📝 Название: {db.contests[contest_id]['name']}\n"
            f"📝 Тип: {type_names.get(db.contests[contest_id]['type'], '')}\n"
            f"📋 По: {target_names.get(db.contests[contest_id]['target_type'], '')}\n"
            f"🎯 Цель: {db.contests[contest_id]['target_value']}\n"
            f"💰 Приз: {db.contests[contest_id]['prize']} {settings.currency_name}\n"
            f"⏱️ Длительность: {duration} часов\n\n"
            f"Участники могут присоединиться через кнопку «Конкурсы»."
        )
        
        await broadcast_notification(
            context,
            f"🎯 **Новый конкурс!**\n\n"
            f"📝 {db.contests[contest_id]['name']}\n"
            f"{db.contests[contest_id]['description']}\n\n"
            f"📋 Тип: {type_names.get(db.contests[contest_id]['type'], '')}\n"
            f"📋 По: {target_names.get(db.contests[contest_id]['target_type'], '')}\n"
            f"🎯 Цель: {db.contests[contest_id]['target_value']}\n"
            f"💰 Приз: {db.contests[contest_id]['prize']} {settings.currency_name}\n"
            f"⏱️ Длительность: {duration} часов\n\n"
            f"Участвуйте в конкурсе через кнопку «Конкурсы»!"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число!")

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
        "🏆 Кто больше - топовый конкурс\n"
        "🎯 Достижение цели - первым достигнуть цели\n\n"
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
    
    if query.from_user.id in settings.admin_list:
        keyboard.append([InlineKeyboardButton("🏆 Завершить конкурс", callback_data=f"end_contest_{contest_id}")])
    
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

async def end_contest_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in settings.admin_list:
        await query.message.edit_text("⛔ Только для администратора!")
        return
    
    contest_id = int(query.data.replace("end_contest_", ""))
    
    if contest_id not in db.contests:
        await query.message.edit_text("❌ Конкурс не найден!")
        return
    
    contest = db.contests[contest_id]
    
    if not contest.get("active", False):
        await query.message.edit_text("❌ Конкурс уже завершен!")
        return
    
    participants = contest.get("participants", [])
    
    if not participants:
        contest["active"] = False
        contest["completed"] = True
        contest["ended_at"] = datetime.now().isoformat()
        db.save()
        await query.message.edit_text("❌ Нет участников для выбора победителей!")
        return
    
    currency = get_currency_symbol()
    
    # Определяем победителей в зависимости от типа конкурса
    winners = []
    for uid in participants:
        user = get_user_data(uid)
        
        if contest["target_type"] == "tasks":
            score = user.get("monthly_tasks", 0)
        elif contest["target_type"] == "referrals":
            score = len(user.get("referrals", []))
        else:  # both
            score = user.get("monthly_tasks", 0) + len(user.get("referrals", []))
        
        winners.append({
            "user_id": uid,
            "score": score,
            "username": user.get("username", "Неизвестно"),
            "name": user.get("first_name", "Пользователь")
        })
    
    winners.sort(key=lambda x: x["score"], reverse=True)
    
    # Для конкурса "Достижение цели" выбираем только тех, кто достиг цели
    if contest["type"] == "goal":
        target = contest.get("target_value", 0)
        qualified_winners = [w for w in winners if w["score"] >= target]
        winners = qualified_winners[:3]
    else:
        winners = winners[:3]
    
    if not winners:
        contest["active"] = False
        contest["completed"] = True
        contest["ended_at"] = datetime.now().isoformat()
        db.save()
        
        await query.message.edit_text(
            f"❌ **Никто не достиг цели!**\n\n"
            f"🎯 Цель: {contest['target_value']}\n"
            f"Победителей нет."
        )
        
        for uid in participants:
            await send_notification(
                context,
                uid,
                f"🏁 **Конкурс завершен!**\n\n"
                f"🎯 {contest['name']}\n"
                f"К сожалению, никто не достиг цели в {contest['target_value']} очков.\n\n"
                f"Следите за новыми конкурсами!"
            )
        return
    
    contest["winners"] = winners
    contest["active"] = False
    contest["completed"] = True
    contest["ended_at"] = datetime.now().isoformat()
    db.save()
    
    # Начисляем призы
    prize_text = ""
    for i, winner in enumerate(winners[:3]):
        if i == 0:
            prize_amount = contest["prize"] * 50 // 100
        elif i == 1:
            prize_amount = contest["prize"] * 30 // 100
        else:
            prize_amount = contest["prize"] * 20 // 100
        
        add_mcoins(winner["user_id"], prize_amount, f"contest_{contest_id}_place_{i+1}", "contest")
        prize_text += f"{i+1}. @{winner['username']} - {prize_amount} {currency}\n"
        
        await send_notification(
            context,
            winner["user_id"],
            f"🏆 **Вы победили в конкурсе!** 🏆\n\n"
            f"🎯 {contest['name']}\n"
            f"🥇 Место: {i+1}\n"
            f"💰 Приз: {prize_amount} {currency}\n"
            f"📊 Очков: {winner['score']}\n\n"
            f"Поздравляем! 🎉"
        )
    
    for uid in participants:
        if uid not in [w["user_id"] for w in winners]:
            user = get_user_data(uid)
            if contest["target_type"] == "tasks":
                score = user.get("monthly_tasks", 0)
            elif contest["target_type"] == "referrals":
                score = len(user.get("referrals", []))
            else:
                score = user.get("monthly_tasks", 0) + len(user.get("referrals", []))
            
            await send_notification(
                context,
                uid,
                f"🏁 **Конкурс завершен!**\n\n"
                f"🎯 {contest['name']}\n"
                f"📊 Ваш результат: {score} очков\n"
                f"🎯 Цель: {contest['target_value']} очков\n\n"
                f"Победители:\n{prize_text}\n\n"
                f"Следите за новыми конкурсами!"
            )
    
    await query.message.edit_text(
        f"🏁 **Конкурс завершен!** 🏆\n\n"
        f"🎯 {contest['name']}\n\n"
        f"**Победители:**\n{prize_text}\n\n"
        f"Призы начислены!"
    )

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
    
    completed = {k: v for k, v in db.contests.items() if v.get("completed", False) and v.get("winners", [])}
    
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

async def cancel_contest_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data.pop("contest_step", None)
    context.user_data.pop("contest_name", None)
    context.user_data.pop("contest_desc", None)
    context.user_data.pop("contest_prize", None)
    context.user_data.pop("contest_duration", None)
    context.user_data.pop("contest_type", None)
    context.user_data.pop("contest_target_type", None)
    context.user_data.pop("contest_target_value", None)
    
    await query.message.edit_text("❌ Создание конкурса отменено.")

# ========== ПРОВЕРКА ПОДПИСОК ==========
async def check_force_subs(user_id: int, bot) -> Tuple[bool, List[str]]:
    if not settings.force_sub_channels and not settings.force_sub_groups:
        return True, []
    
    not_subscribed = []
    
    for channel in settings.force_sub_channels:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                not_subscribed.append(channel)
        except Exception:
            not_subscribed.append(channel)
    
    for group in settings.force_sub_groups:
        try:
            member = await bot.get_chat_member(chat_id=group, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                not_subscribed.append(group)
        except Exception:
            not_subscribed.append(group)
    
    return len(not_subscribed) == 0, not_subscribed

def get_subscription_links() -> str:
    links = []
    for channel in settings.force_sub_channels:
        links.append(f"https://t.me/{channel}")
    for group in settings.force_sub_groups:
        links.append(f"https://t.me/{group}")
    return "\n".join(links)

# ========== ИНТЕГРАЦИЯ BOTOHUB ==========
async def call_botohub_api(chat_id: int, is_task: bool = False, skip: bool = False,
                            gender: str = None, age: str = None) -> dict:
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

# ========== ИНТЕГРАЦИЯ PIARFLOW ==========
async def call_piarflow_api(path: str, payload: dict) -> dict:
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
    payload = {
        "user_id": user_id,
        "chat_id": chat_id,
        "max_sponsors": 1
    }
    
    result = await call_piarflow_api("/sponsors", payload)
    
    if result.get("status") == "ok":
        sponsors = result.get("sponsors", [])
        return sponsors, result.get("message", "OK")
    else:
        return [], result.get("message", "Ошибка получения заданий")

async def check_piarflow_tasks(user_id: int, links: List[str]) -> Tuple[List[Dict], str]:
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
        for channel in not_passed:
            msg += f"• {channel}\n"
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
            f"Лимит обновится завтра.\n\n"
            f"Тем временем:\n"
            f"• Приглашайте друзей 👥\n"
            f"• Получайте ежедневный бонус 🏆"
        )
        return
    
    if user_id in db.current_task:
        task = db.current_task[user_id]
        await show_task(update, context, task, user_id)
        return
    
    msg = await update.message.reply_text("🔄 Получаем задание...")
    
    botohub_task = None
    piarflow_task = None
    custom_task = None
    
    # Проверяем кастомные задания
    if user_id in db.custom_tasks:
        custom_task = db.custom_tasks[user_id]
        if custom_task.get("active", False):
            task = {
                "link": custom_task["link"],
                "source": "custom",
                "reward": custom_task.get("reward", settings.task_reward),
                "custom_id": user_id
            }
            db.current_task[user_id] = task
            await show_task(update, context, task, user_id)
            return
    
    try:
        result = await call_botohub_api(user_id, is_task=True, skip=False)
        tasks = result.get("tasks", [])
        completed = result.get("completed", False)
        skip_flag = result.get("skip", False)
        
        if not completed and not skip_flag and tasks:
            botohub_task = {
                "link": tasks[0],
                "source": "botohub"
            }
    except Exception as e:
        logger.error(f"Ошибка BotoHub: {e}")
    
    if not botohub_task:
        try:
            piarflow_tasks, msg_pf = await get_piarflow_tasks(user_id, update.message.chat.id)
            if piarflow_tasks:
                piarflow_task = {
                    "link": piarflow_tasks[0].get("link", ""),
                    "source": "piarflow",
                    "original": piarflow_tasks[0]
                }
        except Exception as e:
            logger.error(f"Ошибка PiarFlow: {e}")
    
    if botohub_task:
        task = botohub_task
        db.current_task[user_id] = task
        await show_task(update, context, task, user_id)
    elif piarflow_task:
        task = piarflow_task
        db.current_task[user_id] = task
        await show_task(update, context, task, user_id)
    else:
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
    task_price = task.get("reward", settings.task_reward)
    currency = get_currency_symbol()
    
    db.current_task[user_id] = task
    
    keyboard = [
        [InlineKeyboardButton("📎 Перейти к заданию", url=task_url)],
        [InlineKeyboardButton("✅ Проверить выполнение", callback_data=f"check_task_{user_id}")],
        [InlineKeyboardButton("⏩ Пропустить", callback_data=f"skip_task_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    source_text = ""
    if task.get("source") == "custom":
        source_text = "📌 **Это специальное задание от администратора!**\n"
    
    task_text = (
        f"📢 **Новое задание!** 📢\n\n"
        f"{source_text}"
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
    
    if user_id not in db.current_task:
        await query.message.edit_text("❌ Нет активного задания для проверки.")
        return
    
    task = db.current_task[user_id]
    task_source = task.get("source", "unknown")
    task_url = task.get("link", "")
    task_price = task.get("reward", settings.task_reward)
    currency = get_currency_symbol()
    
    await query.message.edit_text("🔍 **Проверяем выполнение задания...**\n\nПожалуйста, подождите...")
    
    try:
        task_completed = False
        
        if task_source == "botohub":
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
            # Для кастомных заданий считаем выполненными всегда
            task_completed = True
        
        if task_completed:
            add_mcoins(user_id, task_price, f"task_{task_url}", "task" if task_source != "custom" else "custom")
            user = get_user_data(user_id)
            user["tasks_today"] += 1
            
            if "completed_links" not in user:
                user["completed_links"] = []
            user["completed_links"].append(task_url)
            
            db.save()
            db.current_task.pop(user_id, None)
            
            # Если это кастомное задание, удаляем его
            if task_source == "custom" and user_id in db.custom_tasks:
                db.custom_tasks.pop(user_id, None)
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
                f"**Инструкция:**\n"
                f"1️⃣ Нажмите на ссылку выше\n"
                f"2️⃣ Нажмите «Подписаться» или «Join»\n"
                f"3️⃣ Вернитесь и нажмите «Проверить выполнение»\n\n"
                f"⏱️ У вас есть 3 минуты на выполнение",
                disable_web_page_preview=True
            )
            
            keyboard = [
                [InlineKeyboardButton("📎 Перейти к заданию", url=task_url)],
                [InlineKeyboardButton("✅ Проверить выполнение", callback_data=f"check_task_{user_id}")],
                [InlineKeyboardButton("⏩ Пропустить", callback_data=f"skip_task_{user_id}")]
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

async def skip_task_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = int(query.data.replace("skip_task_", ""))
    
    if user_id != query.from_user.id:
        await query.answer("⛔ Это не ваше задание!", show_alert=True)
        return
    
    if user_id in db.current_task:
        task = db.current_task[user_id]
        
        try:
            if task.get("source") == "botohub":
                await call_botohub_api(user_id, is_task=True, skip=True)
            elif task.get("source") == "custom":
                # Удаляем кастомное задание
                if user_id in db.custom_tasks:
                    db.custom_tasks.pop(user_id, None)
                    db.save()
        except Exception as e:
            logger.error(f"Ошибка пропуска задания: {e}")
        
        db.current_task.pop(user_id, None)
    
    await query.message.edit_text(
        "⏩ **Задание пропущено!**\n\n"
        "Хотите получить следующее задание?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Следующее задание", callback_data="next_task")],
            [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
        ])
    )

async def next_task_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
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
    
    botohub_task = None
    piarflow_task = None
    custom_task = None
    
    # Проверяем кастомные задания
    if user_id in db.custom_tasks:
        custom_task = db.custom_tasks[user_id]
        if custom_task.get("active", False):
            task = {
                "link": custom_task["link"],
                "source": "custom",
                "reward": custom_task.get("reward", settings.task_reward),
                "custom_id": user_id
            }
            db.current_task[user_id] = task
            await show_task(update, context, task, user_id)
            return
    
    try:
        result = await call_botohub_api(user_id, is_task=True, skip=False)
        tasks = result.get("tasks", [])
        completed = result.get("completed", False)
        skip_flag = result.get("skip", False)
        
        if not completed and not skip_flag and tasks:
            if "completed_links" in user and tasks[0] in user["completed_links"]:
                await call_botohub_api(user_id, is_task=True, skip=True)
                result2 = await call_botohub_api(user_id, is_task=True, skip=False)
                tasks2 = result2.get("tasks", [])
                if tasks2 and tasks2[0] not in user.get("completed_links", []):
                    botohub_task = {
                        "link": tasks2[0],
                        "source": "botohub"
                    }
            else:
                botohub_task = {
                    "link": tasks[0],
                    "source": "botohub"
                }
    except Exception as e:
        logger.error(f"Ошибка BotoHub: {e}")
    
    if not botohub_task:
        try:
            piarflow_tasks, msg_pf = await get_piarflow_tasks(user_id, query.message.chat.id)
            if piarflow_tasks:
                link = piarflow_tasks[0].get("link", "")
                if "completed_links" in user and link not in user["completed_links"]:
                    piarflow_task = {
                        "link": link,
                        "source": "piarflow",
                        "original": piarflow_tasks[0]
                    }
        except Exception as e:
            logger.error(f"Ошибка PiarFlow: {e}")
    
    if botohub_task:
        task = botohub_task
        db.current_task[user_id] = task
        await show_task(update, context, task, user_id)
    elif piarflow_task:
        task = piarflow_task
        db.current_task[user_id] = task
        await show_task(update, context, task, user_id)
    else:
        await query.message.edit_text(
            "🎉 **Нет активных заданий!**\n\n"
            "Пожалуйста, зайдите позже.\n"
            "В это время вы можете:\n"
            "• Приглашать друзей 👥\n"
            "• Получать ежедневный бонус 🏆"
        )

# ========== ВЫВОД СРЕДСТВ ==========
async def withdraw_menu(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    currency = get_currency_symbol()
    
    if settings.maintenance_mode:
        await update.message.reply_text("🔧 Бот на техническом обслуживании. Вывод временно недоступен.")
        return
    
    if user["mcoin"] < settings.min_withdraw:
        await update.message.reply_text(
            f"❌ **Недостаточно средств для вывода**\n\n"
            f"💰 Ваш баланс: {format_number(user['mcoin'])} {currency}\n"
            f"💰 Минимальная сумма: {settings.min_withdraw} {currency}\n\n"
            f"Выполняйте задания, чтобы заработать больше!"
        )
        return
    
    username = update.effective_user.username
    if not username:
        await update.message.reply_text(
            "⚠️ **У вас нет username!**\n\n"
            "Для вывода средств необходимо установить username в Telegram.\n\n"
            "Настройте username в настройках профиля Telegram и попробуйте снова."
        )
        return
    
    keyboard = [
        [InlineKeyboardButton("💰 Запросить вывод", callback_data="request_withdraw")],
        [InlineKeyboardButton("📊 История выводов", callback_data="withdraw_history")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="withdraw_info")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    pending = db.withdraw_requests.get(user_id, {}).get("status") == "pending"
    pending_text = "\n⚠️ У вас есть активная заявка на вывод!" if pending else ""
    
    await update.message.reply_text(
        f"💸 **Вывод средств** 💸\n\n"
        f"👤 Ваш username: @{username}\n"
        f"💰 Доступно: {format_number(user['mcoin'])} {currency}\n"
        f"📉 Минимальная сумма: {settings.min_withdraw} {currency}\n"
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
    
    context.user_data["withdraw_step"] = "amount"
    
    keyboard = [
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_withdraw")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"💸 **Запрос вывода**\n\n"
        f"👤 Вывод на: @{username}\n"
        f"💰 Доступно: {format_number(user['mcoin'])} {currency}\n"
        f"📉 Минимальная сумма: {settings.min_withdraw} {currency}\n\n"
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
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="withdraw_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(history_text, reply_markup=reply_markup)

async def withdraw_info_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    currency = get_currency_symbol()
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="withdraw_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"ℹ️ **Информация о выводе**\n\n"
        f"💳 **Способ вывода:** Telegram Username\n\n"
        f"💰 **Комиссия:** {settings.withdraw_commission * 100}%\n"
        f"📉 **Минимальная сумма:** {settings.min_withdraw} {currency}\n\n"
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

# ========== РЕФЕРАЛЬНАЯ СИСТЕМА ==========
async def referrals_menu(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    currency = get_currency_symbol()
    
    if not settings.referral_program:
        await update.message.reply_text("❌ Реферальная программа временно отключена!")
        return
    
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
        ref_name = ref_user.get("first_name", f"User_{ref_id}")
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

# ========== ЕЖЕДНЕВНЫЙ БОНУС ==========
async def daily_bonus(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    currency = get_currency_symbol()
    
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
                f"🎁 Следующий бонус через: {hours}ч {minutes}мин\n"
                f"📊 Текущая серия: {user['daily_streak']} дней\n\n"
                f"Не пропустите завтрашний бонус, чтобы увеличить серию!"
            )
            return
        elif days_diff == 1:
            user["daily_streak"] += 1
        elif days_diff > 1:
            user["daily_streak"] = 1
    
    base_reward = settings.daily_reward
    streak_multiplier = 1 + (user["daily_streak"] * 0.05)
    reward = int(base_reward * min(streak_multiplier, 3.0))
    
    add_mcoins(user_id, reward, "daily_bonus", "daily")
    user["daily_last"] = now.isoformat()
    user["last_streak_date"] = now.isoformat()
    user["bonus_claims"] += 1
    
    extra_bonus = 0
    achievements = []
    
    if user["daily_streak"] == 7:
        extra_bonus = 50
        achievements.append("7 дней серии - +50 MCoin")
    elif user["daily_streak"] == 30:
        extra_bonus = 250
        achievements.append("30 дней серии - +250 MCoin")
    elif user["daily_streak"] == 100:
        extra_bonus = 1000
        achievements.append("100 дней серии - +1000 MCoin")
    elif user["daily_streak"] == 365:
        extra_bonus = 5000
        achievements.append("365 дней серии - +5000 MCoin")
    
    if extra_bonus > 0:
        add_mcoins(user_id, extra_bonus, "streak_bonus", "daily")
    
    db.save()
    
    extra_text = f"\n🏆 **Достижение:** {', '.join(achievements)}" if achievements else ""
    
    await update.message.reply_text(
        f"🎁 **Ежедневный бонус!** 🎁\n\n"
        f"💰 Вы получили: {reward} {currency}{extra_text}\n"
        f"📊 Серия: {user['daily_streak']} дней\n"
        f"📈 Множитель: x{streak_multiplier:.2f}\n"
        f"💰 Ваш баланс: {format_number(user['mcoin'])} {currency}\n\n"
        f"✨ Заходите завтра, чтобы продолжить серию!"
    )

# ========== ТОП ПОЛЬЗОВАТЕЛЕЙ ==========
async def top_users_menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("🏆 Общий топ", callback_data="top_all")],
        [InlineKeyboardButton("📅 Месячный топ", callback_data="top_monthly")],
        [InlineKeyboardButton("💰 Топ по балансу", callback_data="top_balance")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🏅 **Топ пользователей** 🏅\n\n"
        "Выберите категорию:",
        reply_markup=reply_markup
    )

async def top_all_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    currency = get_currency_symbol()
    
    sorted_users = sorted(db.top_users.items(), key=lambda x: x[1].get("tasks", 0), reverse=True)[:10]
    
    text = "🏆 **Топ пользователей (все время)** 🏆\n\n"
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
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="top_users")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, reply_markup=reply_markup)

async def top_monthly_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    currency = get_currency_symbol()
    
    current_month = datetime.now().strftime("%Y-%m")
    sorted_users = sorted(db.monthly_top.items(), key=lambda x: x[1].get("tasks", 0), reverse=True)[:10]
    
    text = f"📅 **Топ пользователей ({current_month})** 📅\n\n"
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
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="top_users")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, reply_markup=reply_markup)

async def top_balance_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    currency = get_currency_symbol()
    
    sorted_users = sorted(db.users.items(), key=lambda x: x[1].get("mcoin", 0), reverse=True)[:10]
    
    text = f"💰 **Топ по балансу** 💰\n\n"
    if not sorted_users:
        text += "📭 Нет данных"
    else:
        for i, (uid, data) in enumerate(sorted_users, 1):
            name = data.get("first_name", "Пользователь")
            username = data.get("username", "нет username")
            balance = data.get("mcoin", 0)
            
            if len(name) > 15:
                name = name[:15] + "..."
            
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            text += f"{emoji} @{username} - {balance} {currency}\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="top_users")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, reply_markup=reply_markup)

async def top_users_back(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    await top_users_menu(update, context)

# ========== СТАТИСТИКА ==========
async def stats_menu(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    currency = get_currency_symbol()
    
    username = update.effective_user.username or "Не установлен"
    
    keyboard = [
        [InlineKeyboardButton("📊 Детальная статистика", callback_data="detailed_stats")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📊 **Ваша статистика** 📊\n\n"
        f"👤 Username: @{username}\n"
        f"💰 {currency}: {format_number(user['mcoin'])}\n"
        f"📈 Всего заработано: {format_number(user['total_earned'])}\n"
        f"💸 Выведено: {format_number(user['total_withdrawn'])}\n\n"
        f"✅ Выполнено заданий: {user['total_tasks_completed']}\n"
        f"📊 Заданий сегодня: {user['tasks_today']}/{settings.max_daily_tasks}\n"
        f"👥 Рефералов: {len(user['referrals'])}\n"
        f"🔥 Серия: {user['daily_streak']} дней\n"
        f"📅 В боте: {(datetime.now() - datetime.fromisoformat(user['join_date'])).days} дней",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

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
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="stats_menu")]]
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
        f"• Выводов: {completed_withdrawals}\n\n"
        f"📅 **Даты:**\n"
        f"• В боте с: {user['join_date'][:10]}\n"
        f"• Последний визит: {user['last_seen'][:10] if user.get('last_seen') else 'Неизвестно'}\n"
        f"• Последний бонус: {user['daily_last'][:10] if user.get('daily_last') else 'Не получал'}",
        reply_markup=reply_markup
    )

# ========== ПОМОЩЬ ==========
async def help_menu(update: Update, context: CallbackContext):
    currency = get_currency_symbol()
    
    help_text = (
        "❓ **Помощь** ❓\n\n"
        "**📋 Задания:**\n"
        "Нажмите кнопку «Задания» или /tasks\n"
        "Вы получаете одно задание за раз\n"
        f"💰 Награда за каждое задание: {settings.task_reward} {currency}\n"
        "После выполнения можно взять следующее\n\n"
        "**👥 Рефералы:**\n"
        "Приглашайте друзей по ссылке\n"
        "Получайте бонусы за каждого реферала!\n\n"
        "**💸 Вывод средств:**\n"
        "Накопите достаточно MCoin\n"
        "Вывод осуществляется на ваш Telegram username\n"
        "Создайте заявку на вывод\n\n"
        "**🏆 Ежедневный бонус:**\n"
        "Заходите каждый день\n"
        "Увеличивайте серию и бонусы!\n\n"
        "**📊 Статистика:**\n"
        "Отслеживайте свой прогресс\n\n"
        "**🏅 Топ пользователей:**\n"
        "Смотрите лучших исполнителей\n"
        "Получайте призы за место в топе!\n\n"
        "**🎯 Конкурсы:**\n"
        "Участвуйте в конкурсах\n"
        "Выигрывайте ценные призы!\n\n"
        "По всем вопросам обращайтесь к администратору."
    )
    
    await update.message.reply_text(help_text, reply_markup=get_main_keyboard(update.effective_user.id))

# ========== АДМИН ПАНЕЛЬ ==========
async def admin_panel(update: Update, context: CallbackContext):
    if update.effective_user.id not in settings.admin_list:
        await update.message.reply_text("⛔ У вас нет доступа к админ панели!")
        return
    
    currency = get_currency_symbol()
    
    keyboard = [
        [InlineKeyboardButton("💰 Настройка наград", callback_data="admin_rewards")],
        [InlineKeyboardButton("📢 Обязательные подписки", callback_data="admin_forcesub")],
        [InlineKeyboardButton("👥 Управление пользователями", callback_data="admin_users")],
        [InlineKeyboardButton("📊 Статистика бота", callback_data="admin_stats")],
        [InlineKeyboardButton("💸 Управление выводами", callback_data="admin_withdrawals")],
        [InlineKeyboardButton("📨 Рассылка", callback_data="admin_mailing")],
        [InlineKeyboardButton("⚙️ Настройки бота", callback_data="admin_settings")],
        [InlineKeyboardButton("🎁 Призы топа", callback_data="admin_top_prizes")],
        [InlineKeyboardButton("🎯 Управление конкурсами", callback_data="admin_contests")],
        [InlineKeyboardButton("📋 Создать задание", callback_data="admin_create_task")],
        [InlineKeyboardButton("🔔 Уведомления", callback_data="admin_notifications")],
        [InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    pending_withdrawals = 0
    for uid, req in db.withdraw_requests.items():
        if req.get("status") == "pending":
            pending_withdrawals += 1
    
    total_users = db.global_stats["total_users"]
    
    await update.message.reply_text(
        f"⚙️ **Админ панель** ⚙️\n\n"
        f"📊 **Быстрая статистика:**\n"
        f"👥 Пользователей: {total_users}\n"
        f"💰 Всего заработано: {format_number(db.global_stats['total_mcoins_earned'])} {currency}\n"
        f"✅ Заданий выполнено: {db.global_stats['total_tasks_completed']}\n"
        f"💸 Ожидают вывода: {pending_withdrawals}\n\n"
        f"💰 **Текущая награда за задание:** {settings.task_reward} {currency}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

# ========== АДМИН: СОЗДАНИЕ ЗАДАНИЯ ==========
async def admin_create_task_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in settings.admin_list:
        await query.message.edit_text("⛔ Только для администратора!")
        return
    
    context.user_data["task_step"] = "link"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_task")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "📋 **Создание задания**\n\n"
        "Введите ссылку на задание (канал или группу):",
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
        f"🔗 Ссылка: {context.user_data['task_link']}\n\n"
        f"Введите награду за задание ({currency}):"
    )

async def task_reward_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    try:
        reward = int(update.message.text)
        if reward <= 0:
            await update.message.reply_text("❌ Награда должна быть положительной!")
            return
        
        link = context.user_data["task_link"]
        
        # Сохраняем кастомное задание для всех пользователей
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
        
        await update.message.reply_text(
            f"✅ **Задание создано!** 📋\n\n"
            f"🔗 Ссылка: {link}\n"
            f"💰 Награда: {reward} {currency}\n\n"
            f"Задание будет доступно всем пользователям при нажатии «Задания»."
        )
        
        # Уведомляем всех пользователей
        await broadcast_notification(
            context,
            f"📢 **Новое задание от администратора!**\n\n"
            f"🔗 Ссылка: {link}\n"
            f"💰 Награда: {reward} {currency}\n\n"
            f"Нажмите «Задания» чтобы выполнить!"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число!")

async def cancel_task_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data.pop("task_step", None)
    context.user_data.pop("task_link", None)
    
    await query.message.edit_text("❌ Создание задания отменено.")

# ========== АДМИН: НАСТРОЙКА НАГРАД ==========
async def admin_rewards_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    currency = get_currency_symbol()
    
    keyboard = [
        [InlineKeyboardButton(f"💰 За задание: {settings.task_reward} {currency}", callback_data="set_task_reward")],
        [InlineKeyboardButton(f"👥 За реферала: {settings.referral_reward} {currency}", callback_data="set_ref_reward")],
        [InlineKeyboardButton(f"🏆 Ежедневный: {settings.daily_reward} {currency}", callback_data="set_daily_reward")],
        [InlineKeyboardButton(f"💸 Мин. вывод: {settings.min_withdraw} {currency}", callback_data="set_min_withdraw")],
        [InlineKeyboardButton(f"📊 Лимит заданий: {settings.max_daily_tasks}", callback_data="set_max_tasks")],
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
        "daily_reward": "ежедневного бонуса",
        "min_withdraw": "минимальной суммы вывода",
        "max_tasks": "лимита заданий"
    }
    
    setting_name = setting_names.get(setting, setting)
    
    await query.message.edit_text(
        f"📝 **Изменение {setting_name}**\n\n"
        f"Текущее значение: {getattr(settings, setting, 0)}\n\n"
        f"Введите новое значение:",
        reply_markup=reply_markup
    )

async def reward_value_input(update: Update, context: CallbackContext):
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
            await update.message.reply_text(
                f"✅ **Награда за задание обновлена!**\n\n"
                f"💰 Новая награда: {value} {settings.currency_name}\n\n"
                f"Теперь все задания будут давать {value} {settings.currency_name}."
            )
        elif setting == "ref_reward":
            settings.referral_reward = value
            await update.message.reply_text(
                f"✅ **Награда за реферала обновлена!**\n\n"
                f"👥 Новая награда: {value} {settings.currency_name}"
            )
        elif setting == "daily_reward":
            settings.daily_reward = value
            await update.message.reply_text(
                f"✅ **Ежедневный бонус обновлен!**\n\n"
                f"🏆 Новый бонус: {value} {settings.currency_name}"
            )
        elif setting == "min_withdraw":
            settings.min_withdraw = value
            await update.message.reply_text(
                f"✅ **Минимальная сумма вывода обновлена!**\n\n"
                f"💸 Новый минимум: {value} {settings.currency_name}"
            )
        elif setting == "max_tasks":
            settings.max_daily_tasks = value
            await update.message.reply_text(
                f"✅ **Лимит заданий обновлен!**\n\n"
                f"📊 Новый лимит: {value} заданий в день"
            )
        
        settings.save()
        context.user_data.pop("setting_to_change", None)
        
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

# ========== АДМИН: УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ ==========
async def admin_users_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("⛔ Забанить пользователя", callback_data="ban_user")],
        [InlineKeyboardButton("✅ Разбанить", callback_data="unban_user")],
        [InlineKeyboardButton("💰 Добавить MCoin", callback_data="add_mcoin_user")],
        [InlineKeyboardButton("📊 Все пользователи", callback_data="list_users")],
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
        "Введите @username пользователя для бана:\n"
        "Пример: @username или username",
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
        "Введите @username пользователя для разбана:\n"
        "Пример: @username или username",
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

async def admin_action_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    action = context.user_data.get("admin_action")
    if not action:
        await update.message.reply_text("❌ Ошибка! Попробуйте снова.")
        return
    
    text = update.message.text
    
    if action == "ban":
        try:
            username = text.strip()
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
            
            await update.message.reply_text(f"⛔ Пользователь @{username} забанен!")
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
            
    elif action == "unban":
        try:
            username = text.strip()
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
            
            await update.message.reply_text(f"✅ Пользователь @{username} разбанен!")
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
            
    elif action == "add_mcoin":
        try:
            parts = text.split()
            if len(parts) != 2:
                await update.message.reply_text("❌ Используйте: @username Сумма")
                return
            
            username = parts[0].strip()
            if username.startswith("@"):
                username = username[1:]
            
            amount = int(parts[1])
            
            if amount <= 0:
                await update.message.reply_text("❌ Сумма должна быть положительной!")
                return
            
            target_id = get_user_by_username(username)
            if not target_id:
                await update.message.reply_text(f"❌ Пользователь @{username} не найден!")
                return
            
            add_mcoins(target_id, amount, f"admin_add_{amount}", "other")
            
            await update.message.reply_text(
                f"✅ Добавлено {amount} {settings.currency_name} пользователю @{username}!"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Введите корректные данные!")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
    
    context.user_data.pop("admin_action", None)

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
        f"💰 **Награда за задание:** {settings.task_reward} {currency}",
        reply_markup=reply_markup
    )

# ========== АДМИН: УПРАВЛЕНИЕ ВЫВОДАМИ ==========
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
            InlineKeyboardButton(f"✅ Подтвердить {req['user_id']}", callback_data=f"confirm_{req['user_id']}"),
            InlineKeyboardButton(f"❌ Отклонить {req['user_id']}", callback_data=f"reject_{req['user_id']}")
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
        "📨 **Создание рассылки**\n\n"
        "Введите текст сообщения для рассылки:\n"
        "Поддерживается Markdown",
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
        f"📨 **Подтверждение рассылки**\n\n"
        f"Текст сообщения:\n{message_text}\n\n"
        f"Количество получателей: {db.global_stats['total_users']}\n\n"
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
        await query.message.edit_text("❌ Ошибка! Текст сообщения не найден.")
        return
    
    await query.message.edit_text("📨 **Отправка рассылки...**")
    
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
        f"❌ Не доставлено: {failed}\n"
        f"📊 Всего пользователей: {db.global_stats['total_users']}"
    )

# ========== АДМИН: НАСТРОЙКИ БОТА ==========
async def admin_settings_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    currency = get_currency_symbol()
    
    keyboard = [
        [InlineKeyboardButton(f"🔄 Режим обслуживания: {settings.maintenance_mode}", callback_data="toggle_maintenance")],
        [InlineKeyboardButton(f"📊 Лимит задач: {settings.max_daily_tasks}", callback_data="set_max_tasks")],
        [InlineKeyboardButton(f"💳 Комиссия вывода: {int(settings.withdraw_commission * 100)}%", callback_data="set_withdraw_commission")],
        [InlineKeyboardButton(f"💰 Валюта: {settings.currency_name} {settings.currency_emoji}", callback_data="set_currency")],
        [InlineKeyboardButton(f"🔔 Автоуведомления: {'✅' if settings.auto_notify else '❌'}", callback_data="toggle_notify")],
        [InlineKeyboardButton(f"⏱️ Интервал уведомлений: {settings.notification_interval}с", callback_data="set_notify_interval")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"⚙️ **Настройки бота** ⚙️\n\n"
        f"🔄 Режим обслуживания: {'Включен' if settings.maintenance_mode else 'Выключен'}\n"
        f"📊 Лимит задач в день: {settings.max_daily_tasks}\n"
        f"💳 Комиссия вывода: {int(settings.withdraw_commission * 100)}%\n"
        f"👤 Вывод на Telegram username\n"
        f"💰 Валюта: {settings.currency_name} {settings.currency_emoji}\n"
        f"🔔 Автоуведомления: {'Включены' if settings.auto_notify else 'Выключены'}\n"
        f"⏱️ Интервал уведомлений: {settings.notification_interval} секунд\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

async def toggle_maintenance_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    settings.maintenance_mode = not settings.maintenance_mode
    settings.save()
    
    status = "включен" if settings.maintenance_mode else "выключен"
    await query.message.edit_text(f"🔄 Режим обслуживания {status}!")

async def toggle_notify_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    settings.auto_notify = not settings.auto_notify
    settings.save()
    
    status = "включены" if settings.auto_notify else "выключены"
    await query.message.edit_text(f"🔔 Автоуведомления {status}!")

async def set_notify_interval_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["setting_to_change"] = "notify_interval"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_setting")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"⏱️ **Настройка интервала уведомлений**\n\n"
        f"Текущий интервал: {settings.notification_interval} секунд\n\n"
        f"Введите новый интервал (в секундах):",
        reply_markup=reply_markup
    )

async def set_currency_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = []
    for currency, emoji in CURRENCY_EMOJIS.items():
        keyboard.append([InlineKeyboardButton(
            f"{emoji} {currency}",
            callback_data=f"currency_{currency}_{emoji}"
        )])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_setting")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"💰 **Выбор валюты** 💰\n\n"
        f"Текущая валюта: {settings.currency_name} {settings.currency_emoji}\n\n"
        f"Выберите новую валюту:",
        reply_markup=reply_markup
    )

async def set_currency_value(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    data = query.data.replace("currency_", "")
    parts = data.split("_")
    currency = "_".join(parts[:-1])
    emoji = parts[-1]
    
    settings.currency_name = currency
    settings.currency_emoji = emoji
    settings.save()
    
    await query.message.edit_text(
        f"✅ **Валюта изменена!**\n\n"
        f"💰 Новая валюта: {currency} {emoji}"
    )

# ========== АДМИН: ПРИЗЫ ТОПА ==========
async def admin_top_prizes_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    currency = get_currency_symbol()
    
    keyboard = [
        [InlineKeyboardButton(f"🥇 1 место: {settings.top_prize_1} {currency}", callback_data="set_prize_1")],
        [InlineKeyboardButton(f"🥈 2 место: {settings.top_prize_2} {currency}", callback_data="set_prize_2")],
        [InlineKeyboardButton(f"🥉 3 место: {settings.top_prize_3} {currency}", callback_data="set_prize_3")],
        [InlineKeyboardButton("🏆 Выдать призы победителям", callback_data="give_top_prizes")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"🎁 **Настройка призов топа** 🎁\n\n"
        f"**Текущие призы:**\n"
        f"🥇 1 место - {settings.top_prize_1} {currency}\n"
        f"🥈 2 место - {settings.top_prize_2} {currency}\n"
        f"🥉 3 место - {settings.top_prize_3} {currency}\n\n"
        f"Нажмите на место для изменения приза.",
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
        f"📝 **Изменение приза для {place_names.get(place, '')}**\n\n"
        f"Текущий приз: {getattr(settings, f'top_prize_{place}', 0)} {settings.currency_name}\n\n"
        f"Введите новую сумму приза:",
        reply_markup=reply_markup
    )

async def set_prize_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    place = context.user_data.get("prize_place")
    if not place:
        await update.message.reply_text("❌ Ошибка! Попробуйте снова.")
        return
    
    try:
        value = int(update.message.text)
        if value <= 0:
            await update.message.reply_text("❌ Значение должно быть положительным!")
            return
        
        setattr(settings, f"top_prize_{place}", value)
        settings.save()
        context.user_data.pop("prize_place", None)
        
        place_names = {"1": "🥇 1 место", "2": "🥈 2 место", "3": "🥉 3 место"}
        currency = get_currency_symbol()
        
        await update.message.reply_text(
            f"✅ **Приз для {place_names.get(place, '')} обновлен!**\n\n"
            f"💰 Новый приз: {value} {currency}"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число!")

async def give_top_prizes_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    currency = get_currency_symbol()
    
    sorted_users = sorted(db.top_users.items(), key=lambda x: x[1].get("tasks", 0), reverse=True)[:3]
    
    if not sorted_users:
        await query.message.edit_text("❌ Нет пользователей для выдачи призов!")
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
                f"🏆 **Вы заняли {i+1} место в топе!** 🏆\n\n"
                f"💰 Вы получили приз: {prize} {currency}\n\n"
                f"Поздравляем! 🎉"
            )
    
    if awarded:
        await query.message.edit_text(
            f"✅ **Призы выданы!** 🎉\n\n"
            f"Награждены:\n" + "\n".join(awarded)
        )
    else:
        await query.message.edit_text("❌ Нет призов для выдачи!")

# ========== АДМИН: УПРАВЛЕНИЕ КОНКУРСАМИ ==========
async def admin_contests_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("➕ Создать конкурс", callback_data="create_contest")],
        [InlineKeyboardButton("📋 Все конкурсы", callback_data="all_contests")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    active_contests = len([c for c in db.contests.values() if c.get("active", False)])
    
    await query.message.edit_text(
        f"🎯 **Управление конкурсами** 🎯\n\n"
        f"📊 Активных конкурсов: {active_contests}\n"
        f"📊 Всего конкурсов: {len(db.contests)}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

async def all_contests_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if not db.contests:
        await query.message.edit_text("📭 Нет созданных конкурсов.")
        return
    
    text = "📋 **Все конкурсы**\n\n"
    for cid, contest in list(db.contests.items())[-10:]:
        status = "🟢 Активен" if contest.get("active", False) else "🔴 Завершен"
        type_emoji = "🏆" if contest["type"] == "race" else "🎯"
        text += f"{type_emoji} {contest['name']} - {status}\n"
        text += f"   Участников: {len(contest.get('participants', []))}\n"
        text += f"   Приз: {contest['prize']} {settings.currency_name}\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_contests")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, reply_markup=reply_markup)

# ========== АДМИН: УВЕДОМЛЕНИЯ ==========
async def admin_notifications_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📨 Отправить уведомление всем", callback_data="send_notification_all")],
        [InlineKeyboardButton("👤 Отправить уведомление пользователю", callback_data="send_notification_user")],
        [InlineKeyboardButton("🔔 Включить/Выключить уведомления", callback_data="toggle_user_notify")],
        [InlineKeyboardButton("📊 Статистика уведомлений", callback_data="notify_stats")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"🔔 **Управление уведомлениями** 🔔\n\n"
        f"📊 Автоуведомления: {'Включены' if settings.auto_notify else 'Выключены'}\n"
        f"⏱️ Интервал: {settings.notification_interval} секунд\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

async def send_notification_all_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["mailing_step"] = "message"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_mailing")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "📨 **Отправка уведомления всем**\n\n"
        "Введите текст уведомления для всех пользователей:",
        reply_markup=reply_markup
    )

async def send_notification_user_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["admin_action"] = "send_notification"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "👤 **Отправка уведомления пользователю**\n\n"
        "Введите @username пользователя:",
        reply_markup=reply_markup
    )

async def toggle_user_notify_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["admin_action"] = "toggle_notify"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "🔔 **Включение/Выключение уведомлений**\n\n"
        "Введите @username пользователя:",
        reply_markup=reply_markup
    )

async def notify_stats_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    total_notifications = sum(len(n) for n in db.notifications.values())
    users_with_notify = len([u for u in db.users.values() if u.get("notifications_enabled", True)])
    
    await query.message.edit_text(
        f"📊 **Статистика уведомлений** 📊\n\n"
        f"📨 Всего отправлено: {total_notifications}\n"
        f"👥 Пользователей с уведомлениями: {users_with_notify}\n"
        f"📊 Всего пользователей: {db.global_stats['total_users']}"
    )

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
    
    passed, not_passed = await check_force_subs(user_id, context.bot)
    sub_text = ""
    if not passed:
        sub_text = (
            f"\n\n⚠️ **Важно:** Для работы с ботом необходимо подписаться на:\n"
            f"{get_subscription_links()}\n\n"
            f"После подписки обновите бота командой /start"
        )
    
    username = update.effective_user.username or "Не установлен"
    
    welcome_text = (
        f"👋 **Привет, {update.effective_user.first_name}!**\n\n"
        f"{settings.welcome_message}\n\n"
        f"💎 **{settings.bot_name}**\n"
        f"{settings.bot_description}\n\n"
        f"✨ **Что вы можете делать:**\n"
        f"• 📋 Выполнять задания по одному\n"
        f"• 👥 Приглашать друзей и получать бонусы\n"
        f"• 🏆 Получать ежедневные бонусы\n"
        f"• 💸 Выводить на Telegram username\n"
        f"• 🏅 Участвовать в топе и получать призы\n"
        f"• 🎯 Участвовать в конкурсах\n\n"
        f"💰 Награда за задание: {settings.task_reward} {currency}\n"
        f"👤 Ваш username: @{username}\n"
        f"💰 Ваш баланс: 0 {currency}"
        f"{sub_text}"
    )
    
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard(user_id))

async def balance_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    currency = get_currency_symbol()
    
    username = update.effective_user.username or "Не установлен"
    
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
        f"🔥 Серия: {user['daily_streak']} дней",
        parse_mode="Markdown"
    )

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
    
    if context.user_data.get("withdraw_step") == "amount":
        await withdraw_amount_input(update, context)
        return
    
    if context.user_data.get("mailing_step") == "message":
        await mailing_message_input(update, context)
        return
    
    if context.user_data.get("admin_action") in ["ban", "unban", "add_mcoin", "send_notification", "toggle_notify"]:
        await admin_action_input(update, context)
        return
    
    if context.user_data.get("sub_type"):
        await add_force_sub_input(update, context)
        return
    
    if context.user_data.get("setting_to_change") and context.user_data.get("setting_to_change") != "top_prizes":
        await reward_value_input(update, context)
        return
    
    if context.user_data.get("prize_place"):
        await set_prize_input(update, context)
        return
    
    if context.user_data.get("task_step") == "link":
        await task_link_input(update, context)
        return
    elif context.user_data.get("task_step") == "reward":
        await task_reward_input(update, context)
        return
    
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
    
    currency = get_currency_symbol()
    
    if text == f"💰 {currency}":
        await balance_handler(update, context)
    elif text == "📋 Задания":
        await tasks_mode(update, context)
    elif text == "👥 Рефералы":
        await referrals_menu(update, context)
    elif text == "🏆 Ежедневный бонус":
        await daily_bonus(update, context)
    elif text == "💸 Вывод средств":
        await withdraw_menu(update, context)
    elif text == "📊 Статистика":
        await stats_menu(update, context)
    elif text == "🏅 Топ пользователей":
        await top_users_menu(update, context)
    elif text == "🎯 Конкурсы":
        await contests_menu(update, context)
    elif text == "❓ Помощь":
        await help_menu(update, context)
    elif text == "⚙️ Админ панель" and user_id in settings.admin_list:
        await admin_panel(update, context)
    else:
        await update.message.reply_text(
            "❓ **Неизвестная команда**\n\n"
            "Используйте кнопки меню для навигации 👇",
            reply_markup=get_main_keyboard(user_id)
        )

async def get_task_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    await query.message.edit_text("🔄 Загружаем задание...")
    
    if user_id in db.current_task:
        db.current_task.pop(user_id, None)
    
    await tasks_mode(update, context)

# ========== ОБРАБОТЧИКИ ОТМЕНЫ ==========
async def cancel_action_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("admin_action", None)
    await query.message.edit_text("✅ Действие отменено.")

async def cancel_setting_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("setting_to_change", None)
    context.user_data.pop("prize_place", None)
    await query.message.edit_text("✅ Отменено.")

async def cancel_mailing_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("mailing_message", None)
    context.user_data.pop("mailing_step", None)
    await query.message.edit_text("✅ Рассылка отменена.")

async def contests_menu_back(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    keyboard = [
        [InlineKeyboardButton("📋 Активные конкурсы", callback_data="active_contests")],
        [InlineKeyboardButton("📊 Мои участия", callback_data="my_contests")],
        [InlineKeyboardButton("🏆 Победители", callback_data="contest_winners")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    
    if user_id in settings.admin_list:
        keyboard.insert(0, [InlineKeyboardButton("➕ Создать конкурс", callback_data="create_contest")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "🎯 **Конкурсы** 🎯\n\n"
        "Участвуйте в конкурсах и выигрывайте призы!\n"
        "Выполняйте задания, приглашайте друзей и занимайте призовые места.",
        reply_markup=reply_markup
    )

# ========== JOB QUEUE ==========
async def notification_job(context: CallbackContext):
    await check_new_tasks(context)

# ========== ЗАПУСК БОТА ==========
def main():
    db.load()
    settings.load()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(notification_job, interval=settings.notification_interval, first=10)
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tasks", tasks_mode))
    app.add_handler(CommandHandler("balance", balance_handler))
    app.add_handler(CommandHandler("cancel", cancel_command))
    
    # Callback обработчики - ЗАДАНИЯ
    app.add_handler(CallbackQueryHandler(check_task_callback, pattern="^check_task_"))
    app.add_handler(CallbackQueryHandler(skip_task_callback, pattern="^skip_task_"))
    app.add_handler(CallbackQueryHandler(next_task_callback, pattern="^next_task$"))
    app.add_handler(CallbackQueryHandler(get_task_callback, pattern="^get_task_"))
    
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
    app.add_handler(CallbackQueryHandler(toggle_notify_callback, pattern="^toggle_notify$"))
    app.add_handler(CallbackQueryHandler(set_notify_interval_callback, pattern="^set_notify_interval$"))
    app.add_handler(CallbackQueryHandler(set_currency_callback, pattern="^set_currency$"))
    app.add_handler(CallbackQueryHandler(set_currency_value, pattern="^currency_"))
    app.add_handler(CallbackQueryHandler(admin_top_prizes_callback, pattern="^admin_top_prizes$"))
    app.add_handler(CallbackQueryHandler(set_prize_callback, pattern="^set_prize_"))
    app.add_handler(CallbackQueryHandler(give_top_prizes_callback, pattern="^give_top_prizes$"))
    app.add_handler(CallbackQueryHandler(admin_contests_callback, pattern="^admin_contests$"))
    app.add_handler(CallbackQueryHandler(all_contests_callback, pattern="^all_contests$"))
    app.add_handler(CallbackQueryHandler(admin_create_task_callback, pattern="^admin_create_task$"))
    app.add_handler(CallbackQueryHandler(cancel_task_callback, pattern="^cancel_task$"))
    app.add_handler(CallbackQueryHandler(admin_notifications_callback, pattern="^admin_notifications$"))
    app.add_handler(CallbackQueryHandler(send_notification_all_callback, pattern="^send_notification_all$"))
    app.add_handler(CallbackQueryHandler(send_notification_user_callback, pattern="^send_notification_user$"))
    app.add_handler(CallbackQueryHandler(toggle_user_notify_callback, pattern="^toggle_user_notify$"))
    app.add_handler(CallbackQueryHandler(notify_stats_callback, pattern="^notify_stats$"))
    
    # Callback обработчики - РЕФЕРАЛЫ
    app.add_handler(CallbackQueryHandler(referrals_menu, pattern="^referrals_menu$"))
    app.add_handler(CallbackQueryHandler(my_referrals_callback, pattern="^my_referrals$"))
    app.add_handler(CallbackQueryHandler(ref_stats_callback, pattern="^ref_stats$"))
    app.add_handler(CallbackQueryHandler(ref_page_navigation, pattern="^ref_page_"))
    
    # Callback обработчики - ВЫВОД
    app.add_handler(CallbackQueryHandler(withdraw_menu, pattern="^withdraw_menu$"))
    app.add_handler(CallbackQueryHandler(request_withdraw_callback, pattern="^request_withdraw$"))
    app.add_handler(CallbackQueryHandler(withdraw_history_callback, pattern="^withdraw_history$"))
    app.add_handler(CallbackQueryHandler(withdraw_info_callback, pattern="^withdraw_info$"))
    app.add_handler(CallbackQueryHandler(confirm_withdraw_final, pattern="^confirm_withdraw_final$"))
    app.add_handler(CallbackQueryHandler(cancel_withdraw, pattern="^cancel_withdraw$"))
    
    # Callback обработчики - СТАТИСТИКА
    app.add_handler(CallbackQueryHandler(stats_menu, pattern="^stats_menu$"))
    app.add_handler(CallbackQueryHandler(detailed_stats_callback, pattern="^detailed_stats$"))
    
    # Callback обработчики - ТОП
    app.add_handler(CallbackQueryHandler(top_all_callback, pattern="^top_all$"))
    app.add_handler(CallbackQueryHandler(top_monthly_callback, pattern="^top_monthly$"))
    app.add_handler(CallbackQueryHandler(top_balance_callback, pattern="^top_balance$"))
    app.add_handler(CallbackQueryHandler(top_users_back, pattern="^top_users$"))
    
    # Callback обработчики - КОНКУРСЫ
    app.add_handler(CallbackQueryHandler(contests_menu, pattern="^contests_menu$"))
    app.add_handler(CallbackQueryHandler(create_contest_callback, pattern="^create_contest$"))
    app.add_handler(CallbackQueryHandler(contest_type_callback, pattern="^contest_type_"))
    app.add_handler(CallbackQueryHandler(contest_target_type_callback, pattern="^contest_target_"))
    app.add_handler(CallbackQueryHandler(active_contests_callback, pattern="^active_contests$"))
    app.add_handler(CallbackQueryHandler(contest_detail_callback, pattern="^contest_"))
    app.add_handler(CallbackQueryHandler(join_contest_callback, pattern="^join_contest_"))
    app.add_handler(CallbackQueryHandler(end_contest_callback, pattern="^end_contest_"))
    app.add_handler(CallbackQueryHandler(my_contests_callback, pattern="^my_contests$"))
    app.add_handler(CallbackQueryHandler(contest_winners_callback, pattern="^contest_winners$"))
    app.add_handler(CallbackQueryHandler(cancel_contest_callback, pattern="^cancel_contest$"))
    app.add_handler(CallbackQueryHandler(contests_menu_back, pattern="^contests_back$"))
    
    # Callback обработчики - ОТМЕНА
    app.add_handler(CallbackQueryHandler(cancel_action_callback, pattern="^cancel_action$"))
    app.add_handler(CallbackQueryHandler(cancel_setting_callback, pattern="^cancel_setting$"))
    app.add_handler(CallbackQueryHandler(cancel_mailing_callback, pattern="^cancel_mailing$"))
    
    # Callback обработчики - НАВИГАЦИЯ
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.message.delete(), pattern="^back_to_main$"))
    
    # Обработчик текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("🚀 Бот запущен...")
    print(f"📊 Администратор: {ADMIN_ID}")
    print(f"💎 Название: {settings.bot_name}")
    print(f"👥 Пользователей: {db.global_stats['total_users']}")
    print(f"👤 Вывод на Telegram username")
    print(f"📋 Задания выдаются по одному")
    print(f"💰 Награда за задание: {settings.task_reward} {settings.currency_name}")
    print(f"🏅 Топ пользователей с призами")
    print(f"🎯 Конкурсы активны")
    print(f"🔔 Автоуведомления: {'Включены' if settings.auto_notify else 'Выключены'}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()