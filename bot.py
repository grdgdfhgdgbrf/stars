import asyncio
import random
import json
import os
import logging
import re
import string
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
BOTOHUB_TOKEN = "c72ddc9b-c2dc-4e3e-a985-7d51f0d77f58"
BOTOHUB_API_URL = "https://botohub.me/get-tasks"
ADMIN_ID = 5356400377

# Состояния для ConversationHandler
(MAIN_MENU, SETTINGS_MENU, TASK_SETTINGS, REFERRAL_SETTINGS, 
 WITHDRAW_SETTINGS, PROMO_SETTINGS, CHEQUE_SETTINGS, USER_MANAGEMENT,
 AWAITING_WITHDRAW_AMOUNT, AWAITING_WITHDRAW_METHOD, AWAITING_PROMO_CODE,
 AWAITING_PROMO_REWARD, AWAITING_PROMO_EXPIRY, AWAITING_CHEQUE_AMOUNT,
 AWAITING_CHEQUE_COUNT, AWAITING_BAN_USER, AWAITING_UNBAN_USER,
 AWAITING_ADD_MCOIN, AWAITING_MAILING_TEXT, AWAITING_SETTING_VALUE,
 AWAITING_FORCE_SUB_INPUT, AWAITING_REWARD_INPUT) = range(23)

# ========== КЛАССЫ ДЛЯ ХРАНЕНИЯ ДАННЫХ ==========
class BotDatabase:
    def __init__(self):
        self.users: Dict[int, Dict] = {}
        self.promo_codes: Dict[str, Dict] = {}
        self.cheques: Dict[str, Dict] = {}
        self.withdraw_requests: Dict[int, Dict] = {}
        self.bans: Dict[int, Dict] = {}
        self.global_stats: Dict = {
            "total_users": 0,
            "total_earned": 0,
            "total_withdrawn": 0,
            "total_tasks": 0,
            "total_referrals": 0
        }
        
    def save(self):
        try:
            data = {
                "users": self.users,
                "promo_codes": self.promo_codes,
                "cheques": self.cheques,
                "withdraw_requests": self.withdraw_requests,
                "bans": self.bans,
                "global_stats": self.global_stats
            }
            with open("bot_data.json", 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения: {e}")
    
    def load(self):
        try:
            if os.path.exists("bot_data.json"):
                with open("bot_data.json", 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.users = {int(k): v for k, v in data.get("users", {}).items()}
                    self.promo_codes = data.get("promo_codes", {})
                    self.cheques = data.get("cheques", {})
                    self.withdraw_requests = {int(k): v for k, v in data.get("withdraw_requests", {}).items()}
                    self.bans = {int(k): v for k, v in data.get("bans", {}).items()}
                    self.global_stats = data.get("global_stats", self.global_stats)
        except Exception as e:
            logger.error(f"Ошибка загрузки: {e}")

class BotSettings:
    def __init__(self):
        self.task_reward = 10
        self.referral_reward = 5
        self.daily_reward = 15
        self.min_withdraw = 50
        self.max_withdraw = 10000
        self.withdraw_commission = 0.05
        self.max_daily_tasks = 20
        self.force_sub_channels = []
        self.force_sub_groups = []
        self.welcome_message = "Добро пожаловать в бот! 🎉"
        self.maintenance_mode = False
        self.bot_name = "MCoin Bot"
        self.currency = "MCoin"
        self.admin_list = [ADMIN_ID]
        self.ref_levels = [5, 10, 15, 20, 25]
        self.ref_multipliers = [1.0, 1.1, 1.2, 1.3, 1.5]
        self.withdraw_methods = ["qiwi", "card", "crypto"]
        
    def save(self):
        try:
            with open("settings.json", 'w', encoding='utf-8') as f:
                json.dump(self.__dict__, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения настроек: {e}")
    
    def load(self):
        try:
            if os.path.exists("settings.json"):
                with open("settings.json", 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, value in data.items():
                        setattr(self, key, value)
        except Exception as e:
            logger.error(f"Ошибка загрузки настроек: {e}")

# ========== ИНИЦИАЛИЗАЦИЯ ==========
db = BotDatabase()
settings = BotSettings()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    if user_id in db.bans:
        return ReplyKeyboardMarkup([["ℹ️ Я в бане"]], resize_keyboard=True)
    
    keyboard = [
        [KeyboardButton(f"💰 {settings.currency}"), KeyboardButton("📋 Задания")],
        [KeyboardButton("👥 Рефералы"), KeyboardButton("🏆 Ежедневный бонус")],
        [KeyboardButton("💸 Вывод"), KeyboardButton("🎫 Промокоды")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("❓ Помощь")]
    ]
    
    if user_id in settings.admin_list:
        keyboard.append([KeyboardButton("⚙️ Админ панель")])
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_user_data(user_id: int) -> Dict:
    if user_id not in db.users:
        db.users[user_id] = {
            "balance": 0,
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
            "level": 1,
            "daily_streak": 0,
            "referral_earned": 0,
            "task_earned": 0,
            "bonus_claims": 0
        }
        db.global_stats["total_users"] += 1
        db.save()
    return db.users[user_id]

def add_balance(user_id: int, amount: int, reason: str = "", source: str = "other") -> bool:
    if amount <= 0:
        return False
    
    user = get_user_data(user_id)
    user["balance"] += amount
    user["total_earned"] += amount
    
    if source == "task":
        user["task_earned"] += amount
        db.global_stats["total_tasks"] += 1
    elif source == "referral":
        user["referral_earned"] += amount
        db.global_stats["total_referrals"] += 1
    
    db.global_stats["total_earned"] += amount
    update_user_level(user_id)
    db.save()
    return True

def remove_balance(user_id: int, amount: int, reason: str = "") -> bool:
    if amount <= 0:
        return False
    
    user = get_user_data(user_id)
    if user["balance"] >= amount:
        user["balance"] -= amount
        db.save()
        return True
    return False

def update_user_level(user_id: int) -> bool:
    user = get_user_data(user_id)
    total = user["total_earned"]
    
    if total >= 100:
        level = 1
        exp_needed = 100
        exp = total
        
        while exp >= exp_needed and level < 100:
            exp -= exp_needed
            level += 1
            exp_needed = int(exp_needed * 1.5)
        
        if level > user["level"]:
            user["level"] = level
            return True
    return False

def get_level_info(user_id: int) -> Tuple[int, int, int]:
    user = get_user_data(user_id)
    total = user["total_earned"]
    
    level = 1
    exp_needed = 100
    exp = total
    
    while exp >= exp_needed and level < 100:
        exp -= exp_needed
        level += 1
        exp_needed = int(exp_needed * 1.5)
    
    return level, exp_needed, exp

def format_number(num: int) -> str:
    return f"{num:,}".replace(",", ".")

def generate_cheque_code() -> str:
    chars = string.ascii_uppercase + string.digits
    code = ''.join(random.choice(chars) for _ in range(12))
    while code in db.cheques:
        code = ''.join(random.choice(chars) for _ in range(12))
    return code

def get_referral_multiplier(count: int) -> float:
    for i, level in enumerate(settings.ref_levels):
        if count >= level and i < len(settings.ref_multipliers):
            return settings.ref_multipliers[i]
    return 1.0

def get_subscription_links() -> str:
    links = []
    for channel in settings.force_sub_channels:
        links.append(f"https://t.me/{channel}")
    for group in settings.force_sub_groups:
        links.append(f"https://t.me/{group}")
    return "\n".join(links)

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
        except:
            not_subscribed.append(channel)
    
    for group in settings.force_sub_groups:
        try:
            member = await bot.get_chat_member(chat_id=group, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                not_subscribed.append(group)
        except:
            not_subscribed.append(group)
    
    return len(not_subscribed) == 0, not_subscribed

# ========== API BOTOHUB ==========
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
                    return {"tasks": [], "completed": False, "skip": True}
    except:
        return {"tasks": [], "completed": False, "skip": True}

# ========== ЗАДАНИЯ ==========
async def tasks_mode(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if settings.maintenance_mode:
        await update.message.reply_text("🔧 Бот на обслуживании. Задания недоступны.")
        return
    
    passed, not_passed = await check_force_subs(user_id, context.bot)
    if not passed:
        msg = "⚠️ **Подпишитесь на каналы:**\n\n"
        for channel in not_passed:
            msg += f"• {channel}\n"
        msg += f"\n🔗 Ссылки:\n{get_subscription_links()}\n\nПосле подписки нажмите /tasks"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return
    
    user = get_user_data(user_id)
    today = datetime.now().date().isoformat()
    
    if user.get("last_task_date") != today:
        user["tasks_today"] = 0
        user["last_task_date"] = today
    
    if user["tasks_today"] >= settings.max_daily_tasks:
        await update.message.reply_text(
            f"⏰ **Лимит заданий исчерпан!**\n\n"
            f"Выполнено: {settings.max_daily_tasks} сегодня\n"
            f"Лимит обновится завтра."
        )
        return
    
    msg = await update.message.reply_text("🔄 Получаем задание...")
    
    try:
        result = await call_botohub_api(user_id, is_task=True, skip=False)
        
        tasks = result.get("tasks", [])
        completed = result.get("completed", False)
        skip_flag = result.get("skip", False)
        
        if completed:
            reward = settings.task_reward
            add_balance(user_id, reward, "all_tasks_completed", "task")
            user["tasks_today"] += 1
            db.save()
            
            await msg.edit_text(
                f"✅ **Все задания выполнены!**\n\n"
                f"💰 Награда: {reward} {settings.currency}\n"
                f"📊 Сегодня: {user['tasks_today']}/{settings.max_daily_tasks}"
            )
            return
        
        if skip_flag or not tasks:
            await msg.edit_text("🎉 Нет активных заданий. Зайдите позже.")
            return
        
        task_url = tasks[0]
        context.user_data["current_task_url"] = task_url
        
        keyboard = [
            [InlineKeyboardButton("✅ Выполнил", callback_data=f"check_task_{task_url}")],
            [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await msg.edit_text(
            f"📢 **Задание**\n\n"
            f"🔗 {task_url}\n\n"
            f"💰 Награда: {settings.task_reward} {settings.currency}\n"
            f"📊 Сегодня: {user['tasks_today']}/{settings.max_daily_tasks}\n\n"
            f"1️⃣ Перейдите по ссылке\n"
            f"2️⃣ Подпишитесь\n"
            f"3️⃣ Нажмите «Выполнил»",
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")

async def check_task_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    task_url = query.data.replace("check_task_", "")
    
    user = get_user_data(user_id)
    
    await query.edit_message_text("🔍 Проверяем...")
    
    try:
        result = await call_botohub_api(user_id, is_task=True, skip=False)
        
        prev_success = result.get("prev_success", False)
        completed = result.get("completed", False)
        tasks = result.get("tasks", [])
        
        if prev_success:
            reward = settings.task_reward
            add_balance(user_id, reward, "task_completed", "task")
            user["tasks_today"] += 1
            user["tasks_completed"].append({
                "url": task_url,
                "date": datetime.now().isoformat()
            })
            db.save()
            
            if completed:
                await query.edit_message_text(
                    f"✅ **Задание выполнено!**\n\n"
                    f"💰 +{reward} {settings.currency}\n"
                    f"📊 Сегодня: {user['tasks_today']}/{settings.max_daily_tasks}"
                )
            elif tasks:
                new_url = tasks[0]
                context.user_data["current_task_url"] = new_url
                
                keyboard = [
                    [InlineKeyboardButton("✅ Выполнил", callback_data=f"check_task_{new_url}")],
                    [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"✅ **Задание выполнено!**\n\n"
                    f"💰 +{reward} {settings.currency}\n\n"
                    f"📢 **Следующее задание:**\n{new_url}",
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
            else:
                await query.edit_message_text(
                    f"✅ **Задание выполнено!**\n\n"
                    f"💰 +{reward} {settings.currency}"
                )
        else:
            await query.edit_message_text(
                f"❌ **Вы не подписались!**\n\n"
                f"🔗 {task_url}\n\n"
                f"Подпишитесь и нажмите «Выполнил»",
                disable_web_page_preview=True
            )
            
            keyboard = [
                [InlineKeyboardButton("✅ Выполнил", callback_data=f"check_task_{task_url}")],
                [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_reply_markup(reply_markup)
            
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {e}")

async def skip_task_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    await query.edit_message_text("⏩ Пропускаем...")
    
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
                [InlineKeyboardButton("✅ Выполнил", callback_data=f"check_task_{new_url}")],
                [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"⏩ **Пропущено!**\n\n"
                f"📢 **Новое задание:**\n{new_url}",
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
        else:
            await query.edit_message_text("🎉 Нет доступных заданий!")
            
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {e}")

# ========== ЕЖЕДНЕВНЫЙ БОНУС ==========
async def daily_bonus(update: Update, context: CallbackContext):
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
                f"⏰ **Бонус уже получен!**\n\n"
                f"Следующий через: {hours}ч {minutes}мин\n"
                f"Серия: {user['daily_streak']} дней"
            )
            return
        elif days_diff == 1:
            user["daily_streak"] += 1
        else:
            user["daily_streak"] = 1
    
    base_reward = settings.daily_reward
    multiplier = 1 + (user["daily_streak"] * 0.05)
    reward = int(base_reward * min(multiplier, 3.0))
    
    add_balance(user_id, reward, "daily_bonus", "daily")
    user["daily_last"] = now.isoformat()
    user["bonus_claims"] += 1
    
    extra_bonus = 0
    achievements = []
    
    if user["daily_streak"] == 7:
        extra_bonus = 50
        achievements.append("7 дней - +50")
    elif user["daily_streak"] == 30:
        extra_bonus = 250
        achievements.append("30 дней - +250")
    elif user["daily_streak"] == 100:
        extra_bonus = 1000
        achievements.append("100 дней - +1000")
    
    if extra_bonus > 0:
        add_balance(user_id, extra_bonus, "streak_bonus", "daily")
    
    db.save()
    
    extra_text = f"\n🏆 {', '.join(achievements)}" if achievements else ""
    
    await update.message.reply_text(
        f"🎁 **Ежедневный бонус!**\n\n"
        f"💰 +{reward} {settings.currency}{extra_text}\n"
        f"📊 Серия: {user['daily_streak']} дней\n"
        f"📈 Множитель: x{multiplier:.2f}\n"
        f"💰 Баланс: {format_number(user['balance'])} {settings.currency}"
    )

# ========== РЕФЕРАЛЬНАЯ СИСТЕМА ==========
async def referrals_menu(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    bot_username = context.bot.username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    ref_count = len(user["referrals"])
    multiplier = get_referral_multiplier(ref_count)
    
    level = 1
    for i, lvl in enumerate(settings.ref_levels, 1):
        if ref_count >= lvl:
            level = i + 1
    
    keyboard = [
        [InlineKeyboardButton("📋 Список рефералов", callback_data="my_referrals")],
        [InlineKeyboardButton("📊 Статистика", callback_data="ref_stats")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👥 **Реферальная программа**\n\n"
        f"🏆 Уровень: {level}\n"
        f"📈 Множитель: x{multiplier:.2f}\n"
        f"👥 Рефералов: {ref_count}\n"
        f"💰 Заработано: {user['referral_earned']} {settings.currency}\n\n"
        f"🎁 Награда: {settings.referral_reward} {settings.currency}\n\n"
        f"🔗 Ссылка:\n`{ref_link}`",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def my_referrals_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user_data(user_id)
    
    if not user["referrals"]:
        await query.message.edit_text("👥 У вас пока нет рефералов.")
        return
    
    page = context.user_data.get("ref_page", 0)
    per_page = 10
    total = len(user["referrals"])
    total_pages = (total + per_page - 1) // per_page
    
    start = page * per_page
    end = min(start + per_page, total)
    
    text = "📋 **Ваши рефералы:**\n\n"
    for i, ref_id in enumerate(user["referrals"][start:end], start + 1):
        ref_user = db.users.get(ref_id, {})
        name = ref_user.get("first_name", f"User_{ref_id}")
        earned = ref_user.get("total_earned", 0)
        text += f"{i}. {name} - Заработал: {earned} {settings.currency}\n"
    
    text += f"\n📊 Страница {page + 1}/{total_pages}"
    
    keyboard = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data="ref_page_prev"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data="ref_page_next"))
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="referrals_menu")])
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def ref_stats_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user_data(user_id)
    
    active = 0
    total_earned = 0
    
    for ref_id in user["referrals"]:
        ref_user = db.users.get(ref_id, {})
        if ref_user.get("last_seen"):
            try:
                if (datetime.now() - datetime.fromisoformat(ref_user["last_seen"])).days < 7:
                    active += 1
            except:
                pass
        total_earned += ref_user.get("total_earned", 0)
    
    await query.message.edit_text(
        f"📊 **Статистика рефералов**\n\n"
        f"👥 Всего: {len(user['referrals'])}\n"
        f"🟢 Активных: {active}\n"
        f"💰 Заработано: {format_number(total_earned)} {settings.currency}\n"
        f"🏆 Ваш доход: {user['referral_earned']} {settings.currency}"
    )

# ========== ВЫВОД СРЕДСТВ ==========
async def withdraw_menu(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    if settings.maintenance_mode:
        await update.message.reply_text("🔧 Вывод временно недоступен.")
        return
    
    if user["balance"] < settings.min_withdraw:
        await update.message.reply_text(
            f"❌ **Недостаточно средств**\n\n"
            f"💰 Баланс: {format_number(user['balance'])} {settings.currency}\n"
            f"📉 Минимум: {settings.min_withdraw} {settings.currency}"
        )
        return
    
    keyboard = [
        [InlineKeyboardButton("💰 Запросить вывод", callback_data="request_withdraw")],
        [InlineKeyboardButton("📊 История", callback_data="withdraw_history")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="withdraw_info")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    pending = db.withdraw_requests.get(user_id, {}).get("status") == "pending"
    pending_text = "\n⚠️ Есть активная заявка!" if pending else ""
    
    await update.message.reply_text(
        f"💸 **Вывод средств**\n\n"
        f"💰 Доступно: {format_number(user['balance'])} {settings.currency}\n"
        f"📉 Минимум: {settings.min_withdraw} {settings.currency}\n"
        f"💳 Комиссия: {settings.withdraw_commission * 100}%\n\n"
        f"💳 Способы:\n"
        f"• QIWI\n"
        f"• Банковская карта\n"
        f"• Криптовалюта\n\n"
        f"⏱️ Обработка: до 24 часов"
        f"{pending_text}",
        reply_markup=reply_markup
    )

async def request_withdraw_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if settings.maintenance_mode:
        await query.message.edit_text("🔧 Вывод временно недоступен.")
        return
    
    user = get_user_data(user_id)
    
    if user_id in db.withdraw_requests and db.withdraw_requests[user_id].get("status") == "pending":
        await query.message.edit_text("⚠️ У вас уже есть активная заявка!")
        return
    
    if user["balance"] < settings.min_withdraw:
        await query.message.edit_text(
            f"❌ Недостаточно средств!\n"
            f"Доступно: {format_number(user['balance'])} {settings.currency}"
        )
        return
    
    context.user_data["withdraw_step"] = "amount"
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_withdraw")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"💸 **Введите сумму:**\n\n"
        f"💰 Доступно: {format_number(user['balance'])} {settings.currency}\n"
        f"📉 Минимум: {settings.min_withdraw} {settings.currency}",
        reply_markup=reply_markup
    )

async def withdraw_amount_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    try:
        amount = int(update.message.text)
        user = get_user_data(user_id)
        
        if amount < settings.min_withdraw:
            await update.message.reply_text(
                f"❌ Минимум: {settings.min_withdraw} {settings.currency}"
            )
            return
        
        if amount > user["balance"]:
            await update.message.reply_text(
                f"❌ Недостаточно! Доступно: {format_number(user['balance'])} {settings.currency}"
            )
            return
        
        if amount > settings.max_withdraw:
            await update.message.reply_text(
                f"❌ Максимум: {settings.max_withdraw} {settings.currency}"
            )
            return
        
        context.user_data["withdraw_amount"] = amount
        
        keyboard = []
        for method in settings.withdraw_methods:
            keyboard.append([InlineKeyboardButton(
                f"💳 {method.upper()}",
                callback_data=f"withdraw_method_{method}"
            )])
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_withdraw")])
        
        await update.message.reply_text(
            f"💰 Сумма: {amount} {settings.currency}\n\n"
            f"Выберите способ:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        context.user_data["withdraw_step"] = "method"
        
    except ValueError:
        await update.message.reply_text("❌ Введите число!")

async def withdraw_method_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    method = query.data.replace("withdraw_method_", "")
    amount = context.user_data.get("withdraw_amount", 0)
    
    if not amount:
        await query.message.edit_text("❌ Ошибка! Попробуйте снова.")
        return
    
    commission = int(amount * settings.withdraw_commission)
    final = amount - commission
    
    db.withdraw_requests[user_id] = {
        "user_id": user_id,
        "amount": amount,
        "commission": commission,
        "final": final,
        "method": method,
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }
    
    remove_balance(user_id, amount, f"withdraw_{method}")
    db.save()
    
    await query.message.edit_text(
        f"✅ **Заявка создана!**\n\n"
        f"💰 Сумма: {amount} {settings.currency}\n"
        f"💳 Комиссия: {commission} {settings.currency}\n"
        f"💳 К получению: {final} {settings.currency}\n"
        f"💳 Способ: {method.upper()}\n\n"
        f"⏱️ Ожидайте обработки."
    )
    
    for admin_id in settings.admin_list:
        try:
            await context.bot.send_message(
                admin_id,
                f"💸 **Новая заявка на вывод!**\n\n"
                f"👤 ID: {user_id}\n"
                f"💰 Сумма: {amount} {settings.currency}\n"
                f"💳 К получению: {final} {settings.currency}\n"
                f"💳 Способ: {method.upper()}"
            )
        except:
            pass
    
    context.user_data.pop("withdraw_amount", None)
    context.user_data.pop("withdraw_step", None)

async def withdraw_history_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    requests = [req for uid, req in db.withdraw_requests.items() if uid == user_id]
    
    if not requests:
        await query.message.edit_text("📭 Нет истории выводов.")
        return
    
    text = "📊 **История выводов**\n\n"
    for i, req in enumerate(reversed(requests[-10:]), 1):
        status = "✅" if req["status"] == "completed" else "⏳" if req["status"] == "pending" else "❌"
        text += f"{i}. {status} {req['amount']} {settings.currency} -> {req['method'].upper()}\n"
        text += f"   Статус: {req['status']}\n"
        text += f"   Дата: {req['created_at'][:10]}\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="withdraw_menu")]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def withdraw_info_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="withdraw_menu")]]
    
    await query.message.edit_text(
        f"ℹ️ **Информация**\n\n"
        f"💳 Способы:\n"
        f"• QIWI\n"
        f"• Банковская карта\n"
        f"• Криптовалюта\n\n"
        f"💰 Комиссия: {settings.withdraw_commission * 100}%\n"
        f"📉 Минимум: {settings.min_withdraw} {settings.currency}\n"
        f"📈 Максимум: {settings.max_withdraw} {settings.currency}\n\n"
        f"⏱️ Обработка: до 24 часов",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def cancel_withdraw(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("withdraw_amount", None)
    context.user_data.pop("withdraw_step", None)
    await query.message.edit_text("❌ Вывод отменен.")

# ========== ПРОМОКОДЫ ==========
async def promo_menu(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    keyboard = [
        [InlineKeyboardButton("🎫 Активировать", callback_data="activate_promo")],
        [InlineKeyboardButton("📋 Активные", callback_data="active_promos")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎫 **Промокоды**\n\n"
        "Получайте бонусные MCoin!\n\n"
        "1️⃣ Получите промокод\n"
        "2️⃣ Нажмите «Активировать»\n"
        "3️⃣ Введите код",
        reply_markup=reply_markup
    )

async def activate_promo_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["promo_step"] = "code"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_promo")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "🎫 **Введите промокод:**",
        reply_markup=reply_markup
    )

async def promo_code_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    code = update.message.text.upper()
    
    if code not in db.promo_codes:
        await update.message.reply_text("❌ Неверный промокод!")
        context.user_data.pop("promo_step", None)
        return
    
    promo = db.promo_codes[code]
    
    if promo.get("expiry"):
        try:
            if datetime.now() > datetime.fromisoformat(promo["expiry"]):
                await update.message.reply_text("❌ Промокод истек!")
                context.user_data.pop("promo_step", None)
                return
        except:
            pass
    
    if len(promo.get("used_by", [])) >= promo.get("max_uses", 1):
        await update.message.reply_text("❌ Промокод использован максимальное число раз!")
        context.user_data.pop("promo_step", None)
        return
    
    if user_id in promo.get("used_by", []):
        await update.message.reply_text("❌ Вы уже использовали этот промокод!")
        context.user_data.pop("promo_step", None)
        return
    
    reward = promo.get("reward", 0)
    add_balance(user_id, reward, f"promo_{code}", "other")
    
    if "used_by" not in promo:
        promo["used_by"] = []
    promo["used_by"].append(user_id)
    
    db.save()
    
    await update.message.reply_text(
        f"✅ **Промокод активирован!**\n\n"
        f"🎁 +{reward} {settings.currency}\n"
        f"💰 Баланс: {format_number(get_user_data(user_id)['balance'])} {settings.currency}"
    )
    
    context.user_data.pop("promo_step", None)

async def active_promos_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    active = []
    for code, promo in db.promo_codes.items():
        if promo.get("active", True):
            expiry = promo.get("expiry", "Бессрочно")
            if expiry != "Бессрочно":
                try:
                    if datetime.now() > datetime.fromisoformat(expiry):
                        continue
                except:
                    pass
            active.append(f"🎫 {code} - {promo['reward']} {settings.currency} (до {expiry})")
    
    if not active:
        await query.message.edit_text("📭 Нет активных промокодов.")
        return
    
    text = "📋 **Активные промокоды:**\n\n" + "\n".join(active)
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="promo_menu")]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ========== ЧЕКИ ==========
async def create_cheque(update: Update, context: CallbackContext):
    if update.effective_user.id not in settings.admin_list:
        await update.message.reply_text("⛔ Только для админа!")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "📝 **Создание чека**\n"
            "Использование: /create_cheque <сумма> <количество>"
        )
        return
    
    try:
        amount = int(args[0])
        count = int(args[1])
        
        if amount <= 0 or count <= 0:
            raise ValueError
        
        created = []
        for _ in range(count):
            code = generate_cheque_code()
            db.cheques[code] = {
                "amount": amount,
                "created_by": update.effective_user.id,
                "created_at": datetime.now().isoformat(),
                "used_by": None,
                "active": True
            }
            created.append(code)
        
        db.save()
        
        codes_text = "\n".join([f"`{code}` - {amount} {settings.currency}" for code in created])
        await update.message.reply_text(
            f"✅ **Создано {count} чеков**\n\n"
            f"{codes_text}",
            parse_mode="Markdown"
        )
    except:
        await update.message.reply_text("❌ Ошибка! Используйте: /create_cheque <сумма> <количество>")

async def activate_cheque(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "🎫 **Активация чека**\n"
            "Использование: /cheque <код>"
        )
        return
    
    code = args[0].upper()
    
    if code not in db.cheques:
        await update.message.reply_text("❌ Неверный код!")
        return
    
    cheque = db.cheques[code]
    
    if not cheque["active"] or cheque["used_by"]:
        await update.message.reply_text("❌ Чек уже использован!")
        return
    
    amount = cheque["amount"]
    add_balance(user_id, amount, f"cheque_{code}", "cheque")
    
    cheque["used_by"] = user_id
    cheque["used_at"] = datetime.now().isoformat()
    cheque["active"] = False
    
    db.save()
    
    await update.message.reply_text(
        f"✅ **Чек активирован!**\n\n"
        f"💰 +{amount} {settings.currency}\n"
        f"💳 Баланс: {format_number(get_user_data(user_id)['balance'])} {settings.currency}"
    )

# ========== СТАТИСТИКА ==========
async def stats_menu(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    level, exp_needed, current_exp = get_level_info(user_id)
    progress = int((current_exp / exp_needed) * 20) if exp_needed > 0 else 0
    progress_bar = "█" * progress + "░" * (20 - progress)
    
    keyboard = [
        [InlineKeyboardButton("📊 Детальная статистика", callback_data="detailed_stats")],
        [InlineKeyboardButton("🏆 Топ пользователей", callback_data="top_users")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📊 **Ваша статистика**\n\n"
        f"💰 Баланс: {format_number(user['balance'])} {settings.currency}\n"
        f"📈 Всего заработано: {format_number(user['total_earned'])}\n"
        f"💸 Выведено: {format_number(user['total_withdrawn'])}\n\n"
        f"🏅 Уровень: {level}\n"
        f"📈 Прогресс: {progress_bar} {format_number(current_exp)}/{format_number(exp_needed)}\n\n"
        f"✅ Заданий: {len(user['tasks_completed'])}\n"
        f"📊 Сегодня: {user['tasks_today']}/{settings.max_daily_tasks}\n"
        f"👥 Рефералов: {len(user['referrals'])}\n"
        f"🔥 Серия: {user['daily_streak']} дней",
        reply_markup=reply_markup
    )

async def detailed_stats_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user_data(user_id)
    
    completed_withdrawals = len([
        r for r in db.withdraw_requests.values() 
        if r.get("user_id") == user_id and r.get("status") == "completed"
    ])
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="stats_menu")]]
    
    await query.message.edit_text(
        f"📊 **Детальная статистика**\n\n"
        f"💰 **Заработано:**\n"
        f"• С заданий: {user['task_earned']} {settings.currency}\n"
        f"• С рефералов: {user['referral_earned']} {settings.currency}\n"
        f"• С бонусов: {user['bonus_claims']} раз\n\n"
        f"📊 **Активность:**\n"
        f"• Заданий: {len(user['tasks_completed'])}\n"
        f"• Рефералов: {len(user['referrals'])}\n"
        f"• Выводов: {completed_withdrawals}\n\n"
        f"📅 В боте: {(datetime.now() - datetime.fromisoformat(user['join_date'])).days} дней",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def top_users_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    sorted_users = sorted(db.users.items(), key=lambda x: x[1].get("balance", 0), reverse=True)[:10]
    
    text = "🏆 **Топ пользователей**\n\n"
    for i, (uid, data) in enumerate(sorted_users, 1):
        name = data.get("first_name", f"User_{uid}")
        if len(name) > 15:
            name = name[:15] + "..."
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        text += f"{medal} {name} - {data.get('balance', 0)} {settings.currency}\n"
    
    if not sorted_users:
        text = "📭 Нет пользователей"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="stats_menu")]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ========== ПОМОЩЬ ==========
async def help_menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("📋 Задания", callback_data="help_tasks")],
        [InlineKeyboardButton("👥 Рефералы", callback_data="help_referral")],
        [InlineKeyboardButton("💸 Вывод", callback_data="help_withdraw")],
        [InlineKeyboardButton("🎫 Промокоды", callback_data="help_promo")],
        [InlineKeyboardButton("❓ FAQ", callback_data="help_faq")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "❓ **Помощь**\n\n"
        "Выберите тему:",
        reply_markup=reply_markup
    )

# ========== АДМИН ПАНЕЛЬ ==========
async def admin_panel(update: Update, context: CallbackContext):
    if update.effective_user.id not in settings.admin_list:
        await update.message.reply_text("⛔ Доступ запрещен!")
        return
    
    keyboard = [
        [InlineKeyboardButton("💰 Настройки наград", callback_data="admin_rewards")],
        [InlineKeyboardButton("📢 Обязательные подписки", callback_data="admin_forcesub")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("💸 Заявки на вывод", callback_data="admin_withdrawals")],
        [InlineKeyboardButton("📨 Рассылка", callback_data="admin_mailing")],
        [InlineKeyboardButton("🎫 Промокоды", callback_data="admin_promo")],
        [InlineKeyboardButton("📦 Чеки", callback_data="admin_cheques")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="admin_settings")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    pending = len([r for r in db.withdraw_requests.values() if r.get("status") == "pending"])
    
    await update.message.reply_text(
        f"⚙️ **Админ панель**\n\n"
        f"👥 Пользователей: {db.global_stats['total_users']}\n"
        f"💰 Всего заработано: {format_number(db.global_stats['total_earned'])} {settings.currency}\n"
        f"💸 Ожидают вывода: {pending}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

# ========== АДМИН: НАСТРОЙКИ НАГРАД ==========
async def admin_rewards(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton(f"💰 За задание: {settings.task_reward}", callback_data="set_task_reward")],
        [InlineKeyboardButton(f"👥 За реферала: {settings.referral_reward}", callback_data="set_ref_reward")],
        [InlineKeyboardButton(f"🏆 Ежедневный: {settings.daily_reward}", callback_data="set_daily_reward")],
        [InlineKeyboardButton(f"💸 Мин. вывод: {settings.min_withdraw}", callback_data="set_min_withdraw")],
        [InlineKeyboardButton(f"📊 Лимит задач: {settings.max_daily_tasks}", callback_data="set_max_tasks")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "💰 **Настройка наград**\n\n"
        "Выберите параметр:",
        reply_markup=reply_markup
    )

async def set_reward_value(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    setting = query.data.replace("set_", "")
    context.user_data["setting_to_change"] = setting
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_setting")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"📝 Введите новое значение для '{setting}':",
        reply_markup=reply_markup
    )

async def reward_value_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    setting = context.user_data.get("setting_to_change")
    if not setting:
        await update.message.reply_text("❌ Ошибка!")
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
        elif setting == "daily_reward":
            settings.daily_reward = value
        elif setting == "min_withdraw":
            settings.min_withdraw = value
        elif setting == "max_tasks":
            settings.max_daily_tasks = value
        
        settings.save()
        context.user_data.pop("setting_to_change", None)
        
        await update.message.reply_text(
            f"✅ Настройка '{setting}' обновлена!\n"
            f"Новое значение: {value}"
        )
    except ValueError:
        await update.message.reply_text("❌ Введите число!")

# ========== АДМИН: ОБЯЗАТЕЛЬНЫЕ ПОДПИСКИ ==========
async def admin_forcesub(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    channels = "\n".join([f"• {ch}" for ch in settings.force_sub_channels]) or "Нет каналов"
    groups = "\n".join([f"• {gr}" for gr in settings.force_sub_groups]) or "Нет групп"
    
    keyboard = [
        [InlineKeyboardButton("➕ Канал", callback_data="add_channel")],
        [InlineKeyboardButton("➕ Группа", callback_data="add_group")],
        [InlineKeyboardButton("🗑 Удалить канал", callback_data="remove_channel")],
        [InlineKeyboardButton("🗑 Удалить группу", callback_data="remove_group")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"📢 **Обязательные подписки**\n\n"
        f"📺 Каналы:\n{channels}\n\n"
        f"👥 Группы:\n{groups}",
        reply_markup=reply_markup
    )

async def add_force_sub(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    sub_type = "channel" if query.data == "add_channel" else "group"
    context.user_data["sub_type"] = sub_type
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_setting")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"📝 Введите название {sub_type}а:\n"
        f"Пример: @channel_name",
        reply_markup=reply_markup
    )

async def add_force_sub_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    sub_type = context.user_data.get("sub_type")
    if not sub_type:
        await update.message.reply_text("❌ Ошибка!")
        return
    
    name = update.message.text.strip()
    if name.startswith("@"):
        name = name[1:]
    
    if sub_type == "channel":
        if name in settings.force_sub_channels:
            await update.message.reply_text("❌ Канал уже добавлен!")
            return
        settings.force_sub_channels.append(name)
    else:
        if name in settings.force_sub_groups:
            await update.message.reply_text("❌ Группа уже добавлена!")
            return
        settings.force_sub_groups.append(name)
    
    settings.save()
    context.user_data.pop("sub_type", None)
    
    await update.message.reply_text(f"✅ {sub_type.capitalize()} '{name}' добавлен!")

async def remove_force_sub(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    sub_type = "channel" if query.data == "remove_channel" else "group"
    
    items = settings.force_sub_channels if sub_type == "channel" else settings.force_sub_groups
    if not items:
        await query.message.edit_text(f"❌ Нет {sub_type}ов для удаления!")
        return
    
    keyboard = []
    for item in items:
        keyboard.append([InlineKeyboardButton(f"🗑 {item}", callback_data=f"remove_{sub_type}_{item}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_forcesub")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"📝 Выберите {sub_type} для удаления:",
        reply_markup=reply_markup
    )

async def remove_sub_confirmation(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    data = query.data.replace("remove_", "")
    parts = data.split("_")
    sub_type = parts[0]
    name = "_".join(parts[1:])
    
    if sub_type == "channel":
        if name in settings.force_sub_channels:
            settings.force_sub_channels.remove(name)
            await query.message.edit_text(f"✅ Канал '{name}' удален!")
        else:
            await query.message.edit_text(f"❌ Канал '{name}' не найден!")
    else:
        if name in settings.force_sub_groups:
            settings.force_sub_groups.remove(name)
            await query.message.edit_text(f"✅ Группа '{name}' удалена!")
        else:
            await query.message.edit_text(f"❌ Группа '{name}' не найдена!")
    
    settings.save()

# ========== АДМИН: УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ ==========
async def admin_users(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("⛔ Забанить", callback_data="ban_user")],
        [InlineKeyboardButton("✅ Разбанить", callback_data="unban_user")],
        [InlineKeyboardButton("💰 Добавить MCoin", callback_data="add_mcoin")],
        [InlineKeyboardButton("📊 Список пользователей", callback_data="list_users")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"👥 **Управление пользователями**\n\n"
        f"Всего: {db.global_stats['total_users']}\n"
        f"Забанено: {len(db.bans)}",
        reply_markup=reply_markup
    )

async def ban_user(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["admin_action"] = "ban"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "⛔ **Бан пользователя**\n\n"
        "Введите ID пользователя:",
        reply_markup=reply_markup
    )

async def unban_user(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["admin_action"] = "unban"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "✅ **Разбан пользователя**\n\n"
        "Введите ID пользователя:",
        reply_markup=reply_markup
    )

async def add_mcoin_admin(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["admin_action"] = "add_mcoin"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "💰 **Добавление MCoin**\n\n"
        "Введите ID и сумму через пробел:\n"
        "Пример: 123456789 100",
        reply_markup=reply_markup
    )

async def admin_action_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    action = context.user_data.get("admin_action")
    if not action:
        return
    
    text = update.message.text
    
    if action == "ban":
        try:
            target = int(text)
            if target in db.bans:
                await update.message.reply_text("❌ Пользователь уже забанен!")
                return
            
            db.bans[target] = {
                "reason": "Нарушение правил",
                "date": datetime.now().isoformat(),
                "banned_by": user_id
            }
            db.save()
            
            await update.message.reply_text(f"⛔ Пользователь {target} забанен!")
            
        except ValueError:
            await update.message.reply_text("❌ Введите корректный ID!")
            
    elif action == "unban":
        try:
            target = int(text)
            if target not in db.bans:
                await update.message.reply_text("❌ Пользователь не забанен!")
                return
            
            del db.bans[target]
            db.save()
            
            await update.message.reply_text(f"✅ Пользователь {target} разбанен!")
            
        except ValueError:
            await update.message.reply_text("❌ Введите корректный ID!")
            
    elif action == "add_mcoin":
        try:
            parts = text.split()
            if len(parts) != 2:
                await update.message.reply_text("❌ Используйте: ID Сумма")
                return
            
            target = int(parts[0])
            amount = int(parts[1])
            
            if amount <= 0:
                await update.message.reply_text("❌ Сумма должна быть положительной!")
                return
            
            add_balance(target, amount, f"admin_add_{amount}", "other")
            
            await update.message.reply_text(
                f"✅ Добавлено {amount} {settings.currency} пользователю {target}!"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Введите корректные данные!")
    
    context.user_data.pop("admin_action", None)

async def list_users_admin(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if not db.users:
        await query.message.edit_text("📭 Нет пользователей!")
        return
    
    users_list = []
    for uid, data in sorted(db.users.items(), key=lambda x: x[1].get("balance", 0), reverse=True)[:20]:
        name = data.get("first_name", f"User_{uid}")
        users_list.append(f"{uid} | {name} | {data.get('balance', 0)} {settings.currency}")
    
    text = "📊 **Список пользователей (топ 20)**\n\n" + "\n".join(users_list)
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_users")]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ========== АДМИН: СТАТИСТИКА ==========
async def admin_stats(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    total = db.global_stats["total_users"]
    earned = db.global_stats["total_earned"]
    withdrawn = db.global_stats["total_withdrawn"]
    tasks = db.global_stats["total_tasks"]
    
    pending = len([r for r in db.withdraw_requests.values() if r.get("status") == "pending"])
    
    active = 0
    for user in db.users.values():
        if user.get("last_seen"):
            try:
                if (datetime.now() - datetime.fromisoformat(user["last_seen"])).days < 7:
                    active += 1
            except:
                pass
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"📊 **Статистика бота**\n\n"
        f"👥 **Пользователи:**\n"
        f"• Всего: {total}\n"
        f"• Активных: {active}\n"
        f"• Забанено: {len(db.bans)}\n\n"
        f"💰 **Финансы:**\n"
        f"• Всего заработано: {format_number(earned)} {settings.currency}\n"
        f"• Выведено: {format_number(withdrawn)} {settings.currency}\n"
        f"• В системе: {format_number(earned - withdrawn)} {settings.currency}\n\n"
        f"📋 **Заявки:**\n"
        f"• Ожидают: {pending}\n"
        f"• Всего: {len(db.withdraw_requests)}\n\n"
        f"✅ **Задания:**\n"
        f"• Выполнено: {tasks}",
        reply_markup=reply_markup
    )

# ========== АДМИН: УПРАВЛЕНИЕ ВЫВОДАМИ ==========
async def admin_withdrawals(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    pending = []
    for uid, req in db.withdraw_requests.items():
        if req.get("status") == "pending":
            user = db.users.get(uid, {})
            name = user.get("first_name", f"User_{uid}")
            pending.append(f"{uid} | {name} | {req['amount']} {settings.currency} | {req['method']}")
    
    if not pending:
        await query.message.edit_text("📭 Нет заявок на вывод!")
        return
    
    text = "💸 **Заявки на вывод:**\n\n" + "\n".join(pending[:10])
    if len(pending) > 10:
        text += f"\n\n... и еще {len(pending) - 10}"
    
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_withdraw")],
        [InlineKeyboardButton("❌ Отклонить", callback_data="reject_withdraw")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, reply_markup=reply_markup)

async def confirm_withdraw(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["admin_action"] = "confirm_withdraw"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "✅ **Подтверждение вывода**\n\n"
        "Введите ID пользователя:",
        reply_markup=reply_markup
    )

async def reject_withdraw(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["admin_action"] = "reject_withdraw"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "❌ **Отклонение вывода**\n\n"
        "Введите ID пользователя:",
        reply_markup=reply_markup
    )

async def admin_withdraw_action(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    action = context.user_data.get("admin_action")
    if action not in ["confirm_withdraw", "reject_withdraw"]:
        return
    
    try:
        target = int(update.message.text)
        
        if target not in db.withdraw_requests:
            await update.message.reply_text("❌ Заявка не найдена!")
            return
        
        request = db.withdraw_requests[target]
        if request.get("status") != "pending":
            await update.message.reply_text("❌ Заявка уже обработана!")
            return
        
        if action == "confirm_withdraw":
            request["status"] = "completed"
            request["completed_at"] = datetime.now().isoformat()
            db.global_stats["total_withdrawn"] += request["final"]
            
            await update.message.reply_text(
                f"✅ Вывод подтвержден!\n"
                f"Пользователь: {target}\n"
                f"Сумма: {request['amount']} {settings.currency}"
            )
            
            try:
                await context.bot.send_message(
                    target,
                    f"✅ **Вывод подтвержден!**\n\n"
                    f"💰 Сумма: {request['amount']} {settings.currency}\n"
                    f"💳 К получению: {request['final']} {settings.currency}\n"
                    f"💳 Способ: {request['method'].upper()}"
                )
            except:
                pass
                
        else:
            request["status"] = "rejected"
            request["rejected_at"] = datetime.now().isoformat()
            add_balance(target, request["amount"], "withdraw_rejected", "other")
            
            await update.message.reply_text(
                f"❌ Вывод отклонен!\n"
                f"Пользователь: {target}\n"
                f"Сумма возвращена."
            )
            
            try:
                await context.bot.send_message(
                    target,
                    f"❌ **Вывод отклонен!**\n\n"
                    f"💰 Сумма: {request['amount']} {settings.currency}\n"
                    f"Средства возвращены на баланс."
                )
            except:
                pass
        
        db.save()
        
    except ValueError:
        await update.message.reply_text("❌ Введите корректный ID!")
    
    context.user_data.pop("admin_action", None)

# ========== АДМИН: РАССЫЛКА ==========
async def admin_mailing(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["mailing_step"] = "message"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_mailing")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "📨 **Создание рассылки**\n\n"
        "Введите текст сообщения (поддерживается Markdown):",
        reply_markup=reply_markup
    )

async def mailing_message_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    text = update.message.text
    context.user_data["mailing_message"] = text
    context.user_data["mailing_step"] = "confirm"
    
    keyboard = [
        [InlineKeyboardButton("✅ Отправить", callback_data="send_mailing")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_mailing")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📨 **Подтверждение**\n\n"
        f"Текст:\n{text}\n\n"
        f"Получателей: {db.global_stats['total_users']}\n\n"
        f"Отправить?",
        reply_markup=reply_markup
    )

async def send_mailing(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if user_id not in settings.admin_list:
        return
    
    text = context.user_data.get("mailing_message")
    if not text:
        await query.message.edit_text("❌ Ошибка!")
        return
    
    await query.message.edit_text("📨 Отправка...")
    
    sent = 0
    failed = 0
    
    for uid in db.users.keys():
        try:
            await context.bot.send_message(uid, text, parse_mode="Markdown")
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

# ========== АДМИН: ПРОМОКОДЫ ==========
async def admin_promo(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("➕ Создать", callback_data="create_promo")],
        [InlineKeyboardButton("📋 Список", callback_data="list_promo")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"🎫 **Управление промокодами**\n\n"
        f"Всего: {len(db.promo_codes)}",
        reply_markup=reply_markup
    )

async def create_promo(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["promo_create_step"] = "code"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_promo_create")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "🎫 **Создание промокода**\n\n"
        "Введите код (латиница, цифры):",
        reply_markup=reply_markup
    )

async def promo_create_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    step = context.user_data.get("promo_create_step")
    
    if step == "code":
        code = update.message.text.upper()
        
        if len(code) < 3:
            await update.message.reply_text("❌ Минимум 3 символа!")
            return
        
        if code in db.promo_codes:
            await update.message.reply_text("❌ Такой код уже существует!")
            return
        
        context.user_data["promo_create_code"] = code
        context.user_data["promo_create_step"] = "reward"
        
        await update.message.reply_text(
            f"📝 Код: {code}\n\n"
            "Введите сумму награды:"
        )
        
    elif step == "reward":
        try:
            reward = int(update.message.text)
            if reward <= 0:
                await update.message.reply_text("❌ Сумма должна быть положительной!")
                return
            
            context.user_data["promo_create_reward"] = reward
            context.user_data["promo_create_step"] = "expiry"
            
            await update.message.reply_text(
                f"📝 Код: {context.user_data['promo_create_code']}\n"
                f"💰 Награда: {reward} {settings.currency}\n\n"
                "Введите срок в днях (0 - бессрочно):"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Введите число!")
            
    elif step == "expiry":
        try:
            days = int(update.message.text)
            
            code = context.user_data["promo_create_code"]
            reward = context.user_data["promo_create_reward"]
            
            expiry = None
            if days > 0:
                expiry = (datetime.now() + timedelta(days=days)).isoformat()
            
            db.promo_codes[code] = {
                "reward": reward,
                "max_uses": 1,
                "expiry": expiry,
                "active": True,
                "used_by": [],
                "created_by": user_id,
                "created_at": datetime.now().isoformat()
            }
            
            db.save()
            
            context.user_data.pop("promo_create_code", None)
            context.user_data.pop("promo_create_reward", None)
            context.user_data.pop("promo_create_step", None)
            
            expiry_text = f"до {expiry[:10]}" if expiry else "бессрочно"
            
            await update.message.reply_text(
                f"✅ **Промокод создан!**\n\n"
                f"🎫 Код: {code}\n"
                f"💰 Награда: {reward} {settings.currency}\n"
                f"⏱️ Срок: {expiry_text}"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Введите число дней!")

async def list_promo(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if not db.promo_codes:
        await query.message.edit_text("📭 Нет промокодов.")
        return
    
    text = "📋 **Промокоды:**\n\n"
    for code, promo in db.promo_codes.items():
        status = "🟢 Активен" if promo.get("active") else "🔴 Неактивен"
        uses = len(promo.get("used_by", []))
        expiry = promo.get("expiry", "Бессрочно")
        
        text += f"🎫 {code}\n"
        text += f"   💰 {promo['reward']} {settings.currency}\n"
        text += f"   📊 Использован: {uses} раз\n"
        text += f"   📅 Срок: {expiry[:10] if expiry != 'Бессрочно' else expiry}\n"
        text += f"   📌 {status}\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_promo")]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ========== АДМИН: ЧЕКИ ==========
async def admin_cheques(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    total = len(db.cheques)
    active = len([c for c in db.cheques.values() if c.get("active")])
    
    keyboard = [
        [InlineKeyboardButton("📝 Создать", callback_data="create_cheque_admin")],
        [InlineKeyboardButton("📋 Список", callback_data="list_cheques_admin")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"📦 **Чековая система**\n\n"
        f"📊 Всего: {total}\n"
        f"🟢 Активных: {active}\n"
        f"🔴 Использовано: {total - active}",
        reply_markup=reply_markup
    )

async def create_cheque_admin(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["cheque_step"] = "amount"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_cheque")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "📝 **Создание чека**\n\n"
        "Введите сумму:",
        reply_markup=reply_markup
    )

async def cheque_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    step = context.user_data.get("cheque_step")
    
    if step == "amount":
        try:
            amount = int(update.message.text)
            if amount <= 0:
                await update.message.reply_text("❌ Сумма должна быть положительной!")
                return
            
            context.user_data["cheque_amount"] = amount
            context.user_data["cheque_step"] = "count"
            
            await update.message.reply_text(
                f"💰 Сумма: {amount} {settings.currency}\n\n"
                "Введите количество:"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Введите число!")
            
    elif step == "count":
        try:
            count = int(update.message.text)
            if count <= 0 or count > 100:
                await update.message.reply_text("❌ От 1 до 100!")
                return
            
            amount = context.user_data["cheque_amount"]
            
            created = []
            for _ in range(count):
                code = generate_cheque_code()
                db.cheques[code] = {
                    "amount": amount,
                    "created_by": user_id,
                    "created_at": datetime.now().isoformat(),
                    "used_by": None,
                    "active": True
                }
                created.append(code)
            
            db.save()
            
            context.user_data.pop("cheque_amount", None)
            context.user_data.pop("cheque_step", None)
            
            codes = "\n".join([f"`{code}` - {amount} {settings.currency}" for code in created])
            await update.message.reply_text(
                f"✅ **Создано {count} чеков**\n\n"
                f"{codes}",
                parse_mode="Markdown"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Введите число!")

async def list_cheques_admin(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if not db.cheques:
        await query.message.edit_text("📭 Нет чеков.")
        return
    
    active = []
    used = []
    
    for code, cheque in db.cheques.items():
        info = f"`{code}` - {cheque['amount']} {settings.currency}"
        if cheque.get("active") and not cheque.get("used_by"):
            active.append(info)
        else:
            user = get_user_data(cheque["used_by"]) if cheque.get("used_by") else None
            user_info = f"@{user['username']}" if user and user.get("username") else f"ID:{cheque['used_by']}" if cheque.get("used_by") else "Не использован"
            used.append(f"{info} - Использован: {user_info}")
    
    text = "📊 **Список чеков**\n\n"
    if active:
        text += f"🟢 **Активные ({len(active)}):**\n" + "\n".join(active[:20]) + "\n\n"
    if used:
        text += f"🔴 **Использованные ({len(used)}):**\n" + "\n".join(used[:20])
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_cheques")]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ========== АДМИН: НАСТРОЙКИ ==========
async def admin_settings(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    status = "Включен" if settings.maintenance_mode else "Выключен"
    
    keyboard = [
        [InlineKeyboardButton(f"🔄 Режим обслуживания: {status}", callback_data="toggle_maintenance")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"⚙️ **Настройки**\n\n"
        f"🔄 Режим обслуживания: {status}",
        reply_markup=reply_markup
    )

async def toggle_maintenance(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    settings.maintenance_mode = not settings.maintenance_mode
    settings.save()
    
    status = "включен" if settings.maintenance_mode else "выключен"
    await query.message.edit_text(f"🔄 Режим обслуживания {status}!")

# ========== ОТМЕНА ДЕЙСТВИЙ ==========
async def cancel_action(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("admin_action", None)
    await query.message.edit_text("✅ Действие отменено.")

async def cancel_setting(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("setting_to_change", None)
    await query.message.edit_text("✅ Отменено.")

async def cancel_mailing(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("mailing_message", None)
    context.user_data.pop("mailing_step", None)
    await query.message.edit_text("✅ Рассылка отменена.")

async def cancel_promo_create(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("promo_create_code", None)
    context.user_data.pop("promo_create_reward", None)
    context.user_data.pop("promo_create_step", None)
    await query.message.edit_text("✅ Создание промокода отменено.")

async def cancel_promo(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("promo_step", None)
    await query.message.edit_text("✅ Активация промокода отменена.")

async def cancel_cheque(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("cheque_amount", None)
    context.user_data.pop("cheque_step", None)
    await query.message.edit_text("✅ Создание чека отменено.")

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if user_id in db.bans:
        await update.message.reply_text(
            f"⛔ **Вы забанены!**\n\n"
            f"Причина: {db.bans[user_id].get('reason', 'Не указана')}"
        )
        return
    
    if context.args and context.args[0].startswith("ref_"):
        referrer_id = int(context.args[0].replace("ref_", ""))
        if referrer_id != user_id and referrer_id not in db.bans:
            user_data = get_user_data(user_id)
            if not user_data.get("referrer"):
                user_data["referrer"] = referrer_id
                referrer_data = get_user_data(referrer_id)
                referrer_data["referrals"].append(user_id)
                
                bonus = int(settings.referral_reward * get_referral_multiplier(len(referrer_data["referrals"])))
                add_balance(referrer_id, bonus, "referral_bonus", "referral")
                db.save()
                
                try:
                    await context.bot.send_message(
                        referrer_id,
                        f"👥 **Новый реферал!**\n\n"
                        f"{update.effective_user.first_name} присоединился!\n"
                        f"💰 +{bonus} {settings.currency}"
                    )
                except:
                    pass
    
    get_user_data(user_id)
    
    passed, not_passed = await check_force_subs(user_id, context.bot)
    sub_text = ""
    if not passed:
        sub_text = (
            f"\n\n⚠️ **Подпишитесь на каналы:**\n"
            f"{get_subscription_links()}\n\n"
            f"После подписки нажмите /start"
        )
    
    welcome = (
        f"👋 **Привет, {update.effective_user.first_name}!**\n\n"
        f"{settings.welcome_message}\n\n"
        f"💎 Зарабатывайте MCoin выполняя задания!\n\n"
        f"📋 Выполняйте задания\n"
        f"👥 Приглашайте друзей\n"
        f"🏆 Получайте бонусы\n"
        f"💸 Выводите средства"
        f"{sub_text}"
    )
    
    await update.message.reply_text(welcome, reply_markup=get_main_keyboard(user_id))

async def balance_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    level, exp_needed, current_exp = get_level_info(user_id)
    progress = int((current_exp / exp_needed) * 20) if exp_needed > 0 else 0
    progress_bar = "█" * progress + "░" * (20 - progress)
    
    await update.message.reply_text(
        f"💰 **Баланс**\n\n"
        f"🎮 {settings.currency}: `{format_number(user['balance'])}`\n\n"
        f"🏅 Уровень: {level}\n"
        f"📈 Опыт: {progress_bar} {format_number(current_exp)}/{format_number(exp_needed)}\n\n"
        f"📊 Всего заработано: {format_number(user['total_earned'])}\n"
        f"💸 Выведено: {format_number(user['total_withdrawn'])}\n"
        f"✅ Заданий: {len(user['tasks_completed'])}\n"
        f"👥 Рефералов: {len(user['referrals'])}",
        parse_mode="Markdown"
    )

async def handle_text(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id in db.bans:
        await update.message.reply_text("⛔ Вы забанены!")
        return
    
    if user_id in db.users:
        db.users[user_id]["last_seen"] = datetime.now().isoformat()
        db.users[user_id]["username"] = update.effective_user.username
        db.users[user_id]["first_name"] = update.effective_user.first_name
        db.save()
    
    # Проверка шагов
    if context.user_data.get("withdraw_step") == "amount":
        await withdraw_amount_input(update, context)
        return
    
    if context.user_data.get("promo_step") == "code":
        await promo_code_input(update, context)
        return
    
    if context.user_data.get("mailing_step") == "message":
        await mailing_message_input(update, context)
        return
    
    if context.user_data.get("admin_action") in ["ban", "unban", "add_mcoin", "confirm_withdraw", "reject_withdraw"]:
        await admin_action_input(update, context)
        await admin_withdraw_action(update, context)
        return
    
    if context.user_data.get("promo_create_step"):
        await promo_create_input(update, context)
        return
    
    if context.user_data.get("cheque_step"):
        await cheque_input(update, context)
        return
    
    if context.user_data.get("sub_type"):
        await add_force_sub_input(update, context)
        return
    
    if context.user_data.get("setting_to_change"):
        await reward_value_input(update, context)
        return
    
    # Обработка кнопок
    if text == f"💰 {settings.currency}":
        await balance_handler(update, context)
    elif text == "📋 Задания":
        await tasks_mode(update, context)
    elif text == "👥 Рефералы":
        await referrals_menu(update, context)
    elif text == "🏆 Ежедневный бонус":
        await daily_bonus(update, context)
    elif text == "💸 Вывод":
        await withdraw_menu(update, context)
    elif text == "🎫 Промокоды":
        await promo_menu(update, context)
    elif text == "📊 Статистика":
        await stats_menu(update, context)
    elif text == "❓ Помощь":
        await help_menu(update, context)
    elif text == "⚙️ Админ панель" and user_id in settings.admin_list:
        await admin_panel(update, context)
    else:
        await update.message.reply_text(
            "❓ Используйте кнопки меню 👇",
            reply_markup=get_main_keyboard(user_id)
        )

# ========== ЗАПУСК БОТА ==========
def main():
    db.load()
    settings.load()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tasks", tasks_mode))
    app.add_handler(CommandHandler("cheque", activate_cheque))
    app.add_handler(CommandHandler("create_cheque", create_cheque))
    
    # Callback обработчики
    app.add_handler(CallbackQueryHandler(check_task_callback, pattern="^check_task_"))
    app.add_handler(CallbackQueryHandler(skip_task_callback, pattern="^skip_task$"))
    
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_rewards, pattern="^admin_rewards$"))
    app.add_handler(CallbackQueryHandler(set_reward_value, pattern="^set_"))
    app.add_handler(CallbackQueryHandler(admin_forcesub, pattern="^admin_forcesub$"))
    app.add_handler(CallbackQueryHandler(add_force_sub, pattern="^add_(channel|group)$"))
    app.add_handler(CallbackQueryHandler(remove_force_sub, pattern="^remove_(channel|group)$"))
    app.add_handler(CallbackQueryHandler(remove_sub_confirmation, pattern="^remove_"))
    app.add_handler(CallbackQueryHandler(admin_users, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(ban_user, pattern="^ban_user$"))
    app.add_handler(CallbackQueryHandler(unban_user, pattern="^unban_user$"))
    app.add_handler(CallbackQueryHandler(add_mcoin_admin, pattern="^add_mcoin$"))
    app.add_handler(CallbackQueryHandler(list_users_admin, pattern="^list_users$"))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_withdrawals, pattern="^admin_withdrawals$"))
    app.add_handler(CallbackQueryHandler(confirm_withdraw, pattern="^confirm_withdraw$"))
    app.add_handler(CallbackQueryHandler(reject_withdraw, pattern="^reject_withdraw$"))
    app.add_handler(CallbackQueryHandler(admin_mailing, pattern="^admin_mailing$"))
    app.add_handler(CallbackQueryHandler(send_mailing, pattern="^send_mailing$"))
    app.add_handler(CallbackQueryHandler(admin_promo, pattern="^admin_promo$"))
    app.add_handler(CallbackQueryHandler(create_promo, pattern="^create_promo$"))
    app.add_handler(CallbackQueryHandler(list_promo, pattern="^list_promo$"))
    app.add_handler(CallbackQueryHandler(admin_cheques, pattern="^admin_cheques$"))
    app.add_handler(CallbackQueryHandler(create_cheque_admin, pattern="^create_cheque_admin$"))
    app.add_handler(CallbackQueryHandler(list_cheques_admin, pattern="^list_cheques_admin$"))
    app.add_handler(CallbackQueryHandler(admin_settings, pattern="^admin_settings$"))
    app.add_handler(CallbackQueryHandler(toggle_maintenance, pattern="^toggle_maintenance$"))
    
    app.add_handler(CallbackQueryHandler(referrals_menu, pattern="^referrals_menu$"))
    app.add_handler(CallbackQueryHandler(my_referrals_callback, pattern="^my_referrals$"))
    app.add_handler(CallbackQueryHandler(ref_stats_callback, pattern="^ref_stats$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.message.delete(), pattern="^ref_page_"))
    
    app.add_handler(CallbackQueryHandler(withdraw_menu, pattern="^withdraw_menu$"))
    app.add_handler(CallbackQueryHandler(request_withdraw_callback, pattern="^request_withdraw$"))
    app.add_handler(CallbackQueryHandler(withdraw_history_callback, pattern="^withdraw_history$"))
    app.add_handler(CallbackQueryHandler(withdraw_info_callback, pattern="^withdraw_info$"))
    app.add_handler(CallbackQueryHandler(withdraw_method_callback, pattern="^withdraw_method_"))
    
    app.add_handler(CallbackQueryHandler(promo_menu, pattern="^promo_menu$"))
    app.add_handler(CallbackQueryHandler(activate_promo_callback, pattern="^activate_promo$"))
    app.add_handler(CallbackQueryHandler(active_promos_callback, pattern="^active_promos$"))
    
    app.add_handler(CallbackQueryHandler(stats_menu, pattern="^stats_menu$"))
    app.add_handler(CallbackQueryHandler(detailed_stats_callback, pattern="^detailed_stats$"))
    app.add_handler(CallbackQueryHandler(top_users_callback, pattern="^top_users$"))
    
    app.add_handler(CallbackQueryHandler(help_menu, pattern="^help_menu$"))
    
    app.add_handler(CallbackQueryHandler(cancel_action, pattern="^cancel_action$"))
    app.add_handler(CallbackQueryHandler(cancel_setting, pattern="^cancel_setting$"))
    app.add_handler(CallbackQueryHandler(cancel_mailing, pattern="^cancel_mailing$"))
    app.add_handler(CallbackQueryHandler(cancel_promo_create, pattern="^cancel_promo_create$"))
    app.add_handler(CallbackQueryHandler(cancel_promo, pattern="^cancel_promo$"))
    app.add_handler(CallbackQueryHandler(cancel_cheque, pattern="^cancel_cheque$"))
    app.add_handler(CallbackQueryHandler(cancel_withdraw, pattern="^cancel_withdraw$"))
    
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.message.delete(), pattern="^back_to_main$"))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("🚀 Бот запущен...")
    print(f"📊 Администратор: {ADMIN_ID}")
    print(f"👥 Пользователей: {db.global_stats['total_users']}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()