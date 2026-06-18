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
BOT_TOKEN = "8251949164:AAHe6RTvf3OXniMVZd7_ICCH1BPtRNxHKFo"
BOTOHUB_TOKEN = "c72ddc9b-c2dc-4e3e-a985-7d51f0d77f58"
BOTOHUB_API_URL = "https://botohub.me/get-tasks"
ADMIN_ID = 5356400377

# Состояния для ConversationHandler
(SET_REWARD, SET_PRICE, SET_NAME, SET_DESCRIPTION, SET_WIN_CHANCE, 
 SET_ADMIN_ID, SET_CHANNEL, SET_PROMO, SET_WITHDRAW, SET_CHEQUE_AMOUNT,
 MAILING_TEXT, SET_TAX, SET_LIMIT, SET_REF_BONUS, EDIT_ITEM,
 AWAITING_WITHDRAW_AMOUNT, AWAITING_WITHDRAW_METHOD, AWAITING_CHEQUE_CODE,
 AWAITING_PROMO_CODE, AWAITING_PROMO_REWARD, AWAITING_PROMO_EXPIRY,
 AWAITING_BAN_USER, AWAITING_UNBAN_USER, AWAITING_ADD_MCOIN) = range(24)

# Файлы для хранения данных
DATA_FILE = "bot_data.json"
SETTINGS_FILE = "settings.json"

# ========== СТРУКТУРА ДАННЫХ ==========
class BotDatabase:
    def __init__(self):
        self.users: Dict[int, Dict] = {}
        self.promo_codes: Dict[str, Dict] = {}
        self.cheques: Dict[str, Dict] = {}
        self.withdraw_requests: Dict[int, Dict] = {}
        self.task_history: Dict[int, List[Dict]] = {}
        self.bans: Dict[int, Dict] = {}
        self.global_stats: Dict = {
            "total_users": 0,
            "total_mcoins_earned": 0,
            "total_withdrawn": 0,
            "total_tasks_completed": 0,
            "total_referrals": 0,
            "top_users": []
        }
        self.pending_checks: Dict[int, Dict] = {}
        
    def save(self):
        """Сохраняет все данные в файлы"""
        data = {
            "users": self.users,
            "promo_codes": self.promo_codes,
            "cheques": self.cheques,
            "withdraw_requests": self.withdraw_requests,
            "task_history": self.task_history,
            "bans": self.bans,
            "global_stats": self.global_stats,
            "pending_checks": self.pending_checks
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
                    self.promo_codes = data.get("promo_codes", {})
                    self.cheques = data.get("cheques", {})
                    self.withdraw_requests = {int(k): v for k, v in data.get("withdraw_requests", {}).items()}
                    self.task_history = {int(k): v for k, v in data.get("task_history", {}).items()}
                    self.bans = {int(k): v for k, v in data.get("bans", {}).items()}
                    self.global_stats = data.get("global_stats", self.global_stats)
                    self.pending_checks = {int(k): v for k, v in data.get("pending_checks", {}).items()}
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
        self.force_sub_channels = []
        self.force_sub_groups = []
        self.welcome_message = "Добро пожаловать в бот! 🎉"
        self.referral_program = True
        self.daily_limit = 1000
        self.ref_levels = [5, 10, 15, 20, 25]
        self.ref_multipliers = [1.0, 1.1, 1.2, 1.3, 1.5]
        self.admin_list = [ADMIN_ID]
        self.bot_name = "MCoin Bot"
        self.bot_description = "Зарабатывай MCoin выполняя задания!"
        self.currency_name = "MCoin"
        self.withdraw_methods = ["qiwi", "card", "crypto"]
        self.withdraw_commission = 0.05
        self.task_cooldown = 300
        self.max_daily_tasks = 20
        self.referral_levels = 3
        self.referral_bonuses = [5, 3, 1]
        self.auto_withdraw_enabled = False
        self.min_auto_withdraw = 100
        self.maintenance_mode = False
        self.bot_announcement = ""
        
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
    """Создает главную клавиатуру"""
    if user_id in db.bans:
        return ReplyKeyboardMarkup([["ℹ️ Я в бане"]], resize_keyboard=True)
    
    keyboard = [
        [KeyboardButton(f"💰 {settings.currency_name}"), KeyboardButton("📋 Задания")],
        [KeyboardButton("👥 Рефералы"), KeyboardButton("🏆 Ежедневный бонус")],
        [KeyboardButton("💸 Вывод средств"), KeyboardButton("🎫 Промокоды")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("❓ Помощь")]
    ]
    
    if user_id in settings.admin_list:
        keyboard.append([KeyboardButton("⚙️ Админ панель")])
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_user_data(user_id: int) -> Dict:
    """Получает данные пользователя, создает если нет"""
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
            "last_name": "",
            "level": 1,
            "experience": 0,
            "daily_streak": 0,
            "last_streak_date": None,
            "referral_earned": 0,
            "task_earned": 0,
            "referral_level": 1,
            "referral_count": 0,
            "bonus_claims": 0,
            "last_withdraw_date": None
        }
        db.global_stats["total_users"] += 1
        db.save()
    return db.users[user_id]

def add_mcoins(user_id: int, amount: int, reason: str = "", source: str = "other") -> bool:
    """Добавляет MCoin пользователю"""
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
        db.global_stats["total_referrals"] += 1
    elif source == "daily":
        pass
    elif source == "cheque":
        pass
    
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

def format_number(num: int) -> str:
    """Форматирует число"""
    return f"{num:,}".replace(",", ".")

def generate_cheque_code() -> str:
    """Генерирует уникальный код чека"""
    import string
    chars = string.ascii_uppercase + string.digits
    code = ''.join(random.choice(chars) for _ in range(12))
    while code in db.cheques:
        code = ''.join(random.choice(chars) for _ in range(12))
    return code

def get_referral_bonus(referral_count: int) -> float:
    """Возвращает множитель бонуса за рефералов"""
    for i, level in enumerate(settings.ref_levels):
        if referral_count >= level and i < len(settings.ref_multipliers):
            return settings.ref_multipliers[i]
    return 1.0

# ========== ПРОВЕРКА ПОДПИСОК ==========
async def check_force_subs(user_id: int, bot) -> Tuple[bool, List[str]]:
    """Проверяет обязательные подписки"""
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
    """Возвращает ссылки на обязательные подписки"""
    links = []
    for channel in settings.force_sub_channels:
        links.append(f"https://t.me/{channel}")
    for group in settings.force_sub_groups:
        links.append(f"https://t.me/{group}")
    return "\n".join(links)

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

# ========== РАБОТА С ЧЕКАМИ ==========
async def create_cheque(update: Update, context: CallbackContext):
    """Создание чека (только для админа)"""
    if update.effective_user.id not in settings.admin_list:
        await update.message.reply_text("⛔ Только для администратора!")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "📝 **Создание чека**\n\n"
            "Использование: /create_cheque <сумма> <количество>\n"
            "Пример: /create_cheque 100 5"
        )
        return
    
    try:
        amount = int(args[0])
        count = int(args[1])
        
        if amount <= 0 or count <= 0:
            raise ValueError
        
        created = []
        for i in range(count):
            code = generate_cheque_code()
            db.cheques[code] = {
                "amount": amount,
                "created_by": update.effective_user.id,
                "created_at": datetime.now().isoformat(),
                "used_by": None,
                "used_at": None,
                "active": True
            }
            created.append(code)
        
        db.save()
        
        cheques_text = "\n".join([f"`{code}` - {amount} {settings.currency_name}" for code in created])
        await update.message.reply_text(
            f"✅ **Создано {count} чеков**\n\n"
            f"💰 Сумма каждого: {amount} {settings.currency_name}\n\n"
            f"**Коды чеков:**\n{cheques_text}\n\n"
            f"Отправьте эти коды пользователям для активации.",
            parse_mode="Markdown"
        )
    except:
        await update.message.reply_text("❌ Ошибка! Используйте: /create_cheque <сумма> <количество>")

async def activate_cheque(update: Update, context: CallbackContext):
    """Активация чека пользователем"""
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "🎫 **Активация чека**\n\n"
            "Использование: /cheque <код>\n"
            "Пример: /cheque ABCD1234EFGH"
        )
        return
    
    code = args[0].upper()
    
    if code not in db.cheques:
        await update.message.reply_text("❌ Неверный код чека!")
        return
    
    cheque = db.cheques[code]
    
    if not cheque["active"]:
        await update.message.reply_text("❌ Этот чек уже был использован!")
        return
    
    if cheque["used_by"]:
        await update.message.reply_text("❌ Этот чек уже активирован другим пользователем!")
        return
    
    # Активируем чек
    amount = cheque["amount"]
    add_mcoins(user_id, amount, f"cheque_{code}", "cheque")
    
    cheque["used_by"] = user_id
    cheque["used_at"] = datetime.now().isoformat()
    cheque["active"] = False
    
    db.save()
    
    await update.message.reply_text(
        f"✅ **Чек активирован!** 🎉\n\n"
        f"💰 Вы получили: {amount} {settings.currency_name}\n"
        f"💳 Ваш баланс: {format_number(get_user_data(user_id)['mcoin'])} {settings.currency_name}\n\n"
        f"✨ Спасибо за использование бота!"
    )

async def list_cheques(update: Update, context: CallbackContext):
    """Список всех чеков (только для админа)"""
    if update.effective_user.id not in settings.admin_list:
        await update.message.reply_text("⛔ Только для администратора!")
        return
    
    if not db.cheques:
        await update.message.reply_text("📭 Нет созданных чеков.")
        return
    
    active = []
    used = []
    
    for code, cheque in db.cheques.items():
        info = f"`{code}` - {cheque['amount']} {settings.currency_name}"
        if cheque["active"] and not cheque["used_by"]:
            active.append(info)
        else:
            user = get_user_data(cheque["used_by"]) if cheque["used_by"] else None
            user_info = f"@{user['username']}" if user and user.get("username") else f"ID:{cheque['used_by']}" if cheque["used_by"] else "Не использован"
            used.append(f"{info} - Использован: {user_info}")
    
    text = "📊 **Список чеков**\n\n"
    if active:
        text += f"🟢 **Активные ({len(active)}):**\n" + "\n".join(active[:20]) + "\n\n"
    if used:
        text += f"🔴 **Использованные ({len(used)}):**\n" + "\n".join(used[:20])
    
    if len(active) > 20 or len(used) > 20:
        text += f"\n\n📌 Всего: {len(active)} активных, {len(used)} использованных"
    
    await update.message.reply_text(text, parse_mode="Markdown")

# ========== ВЫВОД СРЕДСТВ ==========
async def withdraw_menu(update: Update, context: CallbackContext):
    """Меню вывода средств"""
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    if settings.maintenance_mode:
        await update.message.reply_text("🔧 Бот на техническом обслуживании. Вывод временно недоступен.")
        return
    
    if user["mcoin"] < settings.min_withdraw:
        await update.message.reply_text(
            f"❌ **Недостаточно средств для вывода**\n\n"
            f"💰 Ваш баланс: {format_number(user['mcoin'])} {settings.currency_name}\n"
            f"💰 Минимальная сумма: {settings.min_withdraw} {settings.currency_name}\n\n"
            f"Выполняйте задания, чтобы заработать больше!"
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
        f"💰 Доступно: {format_number(user['mcoin'])} {settings.currency_name}\n"
        f"📉 Минимальная сумма: {settings.min_withdraw} {settings.currency_name}\n"
        f"📈 Максимальная сумма: {settings.max_withdraw} {settings.currency_name}\n"
        f"💳 Комиссия: {settings.withdraw_commission * 100}%\n\n"
        f"💳 **Доступные способы:**\n"
        f"• QIWI\n"
        f"• Банковская карта\n"
        f"• Криптовалюта\n\n"
        f"⏱️ Время обработки: до 24 часов\n"
        f"{pending_text}\n\n"
        f"Нажмите «Запросить вывод» для создания заявки",
        reply_markup=reply_markup
    )

async def request_withdraw_callback(update: Update, context: CallbackContext):
    """Запрос на вывод средств"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if settings.maintenance_mode:
        await query.message.edit_text("🔧 Бот на техническом обслуживании. Вывод временно недоступен.")
        return
    
    user = get_user_data(user_id)
    
    if user_id in db.withdraw_requests and db.withdraw_requests[user_id].get("status") == "pending":
        await query.message.edit_text(
            "⚠️ **У вас уже есть активная заявка на вывод!**\n\n"
            "Дождитесь обработки текущей заявки."
        )
        return
    
    if user["mcoin"] < settings.min_withdraw:
        await query.message.edit_text(
            f"❌ **Недостаточно средств!**\n\n"
            f"Доступно: {format_number(user['mcoin'])} {settings.currency_name}\n"
            f"Минимальная сумма: {settings.min_withdraw} {settings.currency_name}"
        )
        return
    
    # Запрашиваем сумму
    context.user_data["withdraw_step"] = "amount"
    keyboard = [
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_withdraw")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"💸 **Запрос вывода**\n\n"
        f"💰 Доступно: {format_number(user['mcoin'])} {settings.currency_name}\n"
        f"📉 Минимальная сумма: {settings.min_withdraw} {settings.currency_name}\n"
        f"📈 Максимальная сумма: {min(user['mcoin'], settings.max_withdraw)} {settings.currency_name}\n\n"
        f"Введите сумму вывода:",
        reply_markup=reply_markup
    )

async def withdraw_amount_input(update: Update, context: CallbackContext):
    """Обработка ввода суммы вывода"""
    user_id = update.effective_user.id
    text = update.message.text
    
    try:
        amount = int(text)
        user = get_user_data(user_id)
        
        if amount < settings.min_withdraw:
            await update.message.reply_text(
                f"❌ Минимальная сумма: {settings.min_withdraw} {settings.currency_name}\n"
                f"Введите корректную сумму или /cancel"
            )
            return
        
        if amount > user["mcoin"]:
            await update.message.reply_text(
                f"❌ Недостаточно средств! Доступно: {format_number(user['mcoin'])} {settings.currency_name}\n"
                f"Введите меньшую сумму или /cancel"
            )
            return
        
        if amount > settings.max_withdraw:
            await update.message.reply_text(
                f"❌ Максимальная сумма: {settings.max_withdraw} {settings.currency_name}\n"
                f"Введите меньшую сумму или /cancel"
            )
            return
        
        context.user_data["withdraw_amount"] = amount
        
        # Запрашиваем метод вывода
        keyboard = []
        for method in settings.withdraw_methods:
            keyboard.append([InlineKeyboardButton(
                f"💳 {method.upper()}", 
                callback_data=f"withdraw_method_{method}"
            )])
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_withdraw")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"💰 Сумма: {amount} {settings.currency_name}\n\n"
            f"Выберите способ вывода:",
            reply_markup=reply_markup
        )
        
        context.user_data["withdraw_step"] = "method"
        
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число или /cancel")

async def withdraw_method_callback(update: Update, context: CallbackContext):
    """Выбор метода вывода"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    method = query.data.replace("withdraw_method_", "")
    amount = context.user_data.get("withdraw_amount", 0)
    
    if not amount:
        await query.message.edit_text("❌ Ошибка! Попробуйте снова /withdraw")
        return
    
    # Создаем заявку на вывод
    commission = int(amount * settings.withdraw_commission)
    final_amount = amount - commission
    
    db.withdraw_requests[user_id] = {
        "user_id": user_id,
        "amount": amount,
        "commission": commission,
        "final_amount": final_amount,
        "method": method,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "user_data": {
            "username": update.effective_user.username,
            "first_name": update.effective_user.first_name
        }
    }
    
    # Снимаем деньги
    remove_mcoins(user_id, amount, f"withdraw_request_{method}")
    
    db.save()
    
    await query.message.edit_text(
        f"✅ **Заявка на вывод создана!**\n\n"
        f"💰 Сумма: {amount} {settings.currency_name}\n"
        f"💳 Комиссия: {commission} {settings.currency_name}\n"
        f"💳 К получению: {final_amount} {settings.currency_name}\n"
        f"💳 Способ: {method.upper()}\n\n"
        f"⏱️ Время обработки: до 24 часов\n"
        f"📊 Статус: Ожидает обработки\n\n"
        f"✨ Вы получите уведомление после обработки заявки!"
    )
    
    # Уведомляем админа
    for admin_id in settings.admin_list:
        try:
            await context.bot.send_message(
                admin_id,
                f"💸 **Новая заявка на вывод!**\n\n"
                f"👤 Пользователь: {update.effective_user.first_name}\n"
                f"🆔 ID: {user_id}\n"
                f"💰 Сумма: {amount} {settings.currency_name}\n"
                f"💳 К получению: {final_amount} {settings.currency_name}\n"
                f"💳 Способ: {method.upper()}\n"
                f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                f"Обработайте заявку в админ-панели!"
            )
        except:
            pass
    
    # Очищаем данные
    context.user_data.pop("withdraw_amount", None)
    context.user_data.pop("withdraw_step", None)

async def withdraw_history_callback(update: Update, context: CallbackContext):
    """История выводов пользователя"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
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
            f"{i}. {status_emoji} {req['amount']} {settings.currency_name} -> {req['method'].upper()}\n"
            f"   Статус: {req['status']}\n"
            f"   Дата: {req['created_at'][:10]}\n\n"
        )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="withdraw_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(history_text, reply_markup=reply_markup)

async def withdraw_info_callback(update: Update, context: CallbackContext):
    """Информация о выводе"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="withdraw_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"ℹ️ **Информация о выводе**\n\n"
        f"💳 **Способы вывода:**\n"
        f"• QIWI - Кошелек QIWI\n"
        f"• Card - Банковская карта\n"
        f"• Crypto - Криптовалюта\n\n"
        f"💰 **Комиссия:** {settings.withdraw_commission * 100}%\n"
        f"📉 **Минимальная сумма:** {settings.min_withdraw} {settings.currency_name}\n"
        f"📈 **Максимальная сумма:** {settings.max_withdraw} {settings.currency_name}\n\n"
        f"⏱️ **Время обработки:** до 24 часов\n\n"
        f"📌 **Важно:**\n"
        f"• Вывод доступен только после выполнения заданий\n"
        f"• Мошеннические действия будут заблокированы\n"
        f"• Вопросы по выводу - администратору",
        reply_markup=reply_markup
    )

async def cancel_withdraw(update: Update, context: CallbackContext):
    """Отмена вывода"""
    query = update.callback_query
    await query.answer()
    
    context.user_data.pop("withdraw_amount", None)
    context.user_data.pop("withdraw_step", None)
    
    await query.message.edit_text("❌ Вывод отменен.")

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
    
    # Расчет уровня реферала
    level = 1
    for i, lvl in enumerate(settings.ref_levels, 1):
        if ref_count >= lvl:
            level = i + 1
    
    bonus_multiplier = get_referral_bonus(ref_count)
    
    keyboard = [
        [InlineKeyboardButton("📋 Список рефералов", callback_data="my_referrals")],
        [InlineKeyboardButton("📊 Статистика", callback_data="ref_stats")]
    ]
    
    if user_id in settings.admin_list:
        keyboard.append([InlineKeyboardButton("⚙️ Управление реферальной системой", callback_data="admin_ref_system")])
    
    keyboard.append([InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👥 **Реферальная программа** 👥\n\n"
        f"🏆 **Ваш уровень:** {level}\n"
        f"📈 **Бонусный множитель:** x{bonus_multiplier:.2f}\n"
        f"👥 **Рефералов:** {ref_count}\n"
        f"💰 **Заработано:** {user['referral_earned']} {settings.currency_name}\n\n"
        f"🎁 **Награда за реферала:** {settings.referral_reward} {settings.currency_name}\n\n"
        f"📊 **Следующие уровни:**\n"
        f"{chr(10).join([f'• {lvl} рефералов - x{settings.ref_multipliers[i]}' for i, lvl in enumerate(settings.ref_levels)])}\n\n"
        f"🔗 **Ваша реферальная ссылка:**\n`{ref_link}`\n\n"
        f"Отправьте её друзьям и получайте бонусы!",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def my_referrals_callback(update: Update, context: CallbackContext):
    """Показывает список рефералов"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user_data(user_id)
    
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
        ref_earned = ref_user.get("total_earned", 0)
        ref_join = ref_user.get("join_date", "Unknown")[:10]
        active = ref_user.get("last_seen", "")
        is_active = "🟢" if active and (datetime.now() - datetime.fromisoformat(active)).days < 7 else "🔴"
        
        referrals_list.append(f"{i}. {is_active} {ref_name} - Заработал: {ref_earned} {settings.currency_name} (с {ref_join})")
    
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
    """Статистика рефералов"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user_data(user_id)
    
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
        f"💰 Заработано рефералами: {format_number(total_earned)} {settings.currency_name}\n"
        f"🏆 Ваш доход: {user['referral_earned']} {settings.currency_name}\n\n"
        f"📈 Средний доход на реферала: {format_number(total_earned // len(user['referrals']) if user['referrals'] else 0)} {settings.currency_name}"
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
                f"🎁 Следующий бонус через: {hours}ч {minutes}мин\n"
                f"📊 Текущая серия: {user['daily_streak']} дней\n\n"
                f"Не пропустите завтрашний бонус, чтобы увеличить серию!"
            )
            return
        elif days_diff == 1:
            user["daily_streak"] += 1
        elif days_diff > 1:
            user["daily_streak"] = 1
    
    # Рассчитываем бонус
    base_reward = settings.daily_reward
    streak_multiplier = 1 + (user["daily_streak"] * 0.05)
    reward = int(base_reward * min(streak_multiplier, 3.0))
    
    add_mcoins(user_id, reward, "daily_bonus", "daily")
    user["daily_last"] = now.isoformat()
    user["last_streak_date"] = now.isoformat()
    user["bonus_claims"] += 1
    
    # Бонусы за достижения
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
        f"💰 Вы получили: {reward} {settings.currency_name}{extra_text}\n"
        f"📊 Серия: {user['daily_streak']} дней\n"
        f"📈 Множитель: x{streak_multiplier:.2f}\n"
        f"💰 Ваш баланс: {format_number(user['mcoin'])} {settings.currency_name}\n\n"
        f"✨ Заходите завтра, чтобы продолжить серию!"
    )

# ========== ЗАДАНИЯ BOTOHUB ==========
async def tasks_mode(update: Update, context: CallbackContext):
    """Режим заданий с полной интеграцией BotoHub"""
    user_id = update.effective_user.id
    
    if settings.maintenance_mode:
        await update.message.reply_text("🔧 Бот на техническом обслуживании. Задания временно недоступны.")
        return
    
    # Проверяем обязательные подписки
    passed, not_passed = await check_force_subs(user_id, context.bot)
    if not passed:
        msg = "⚠️ **Для выполнения заданий необходимо подписаться:**\n\n"
        for channel in not_passed:
            msg += f"• {channel}\n"
        msg += f"\n🔗 Ссылки для подписки:\n{get_subscription_links()}\n\n"
        msg += "После подписки нажмите /tasks снова"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return
    
    # Проверяем дневной лимит заданий
    user = get_user_data(user_id)
    today = datetime.now().date().isoformat()
    
    if user.get("last_task_date") != today:
        user["tasks_today"] = 0
        user["last_task_date"] = today
    
    if user["tasks_today"] >= settings.max_daily_tasks:
        await update.message.reply_text(
            f"⏰ **Дневной лимит заданий исчерпан!**\n\n"
            f"Вы выполнили {settings.max_daily_tasks} заданий сегодня.\n"
            f"Лимит обновится завтра.\n\n"
            f"Тем временем:\n"
            f"• Приглашайте друзей 👥\n"
            f"• Получайте ежедневный бонус 🏆\n"
            f"• Активируйте промокоды 🎫"
        )
        return
    
    msg = await update.message.reply_text("🔄 Получаем задание...")
    
    try:
        result = await call_botohub_api(user_id, is_task=True, skip=False)
        
        tasks = result.get("tasks", [])
        completed = result.get("completed", False)
        skip_flag = result.get("skip", False)
        
        if completed:
            # Все задания выполнены - даем бонус
            task_reward = settings.task_reward
            add_mcoins(user_id, task_reward, "all_tasks_completed", "task")
            user["tasks_today"] += 1
            db.save()
            
            await msg.edit_text(
                f"✅ **Все задания выполнены!** 🎉\n\n"
                f"💰 Вы получили: {task_reward} {settings.currency_name}\n\n"
                f"📊 Сегодня выполнено: {user['tasks_today']}/{settings.max_daily_tasks}\n"
                f"💰 Ваш баланс: {format_number(user['mcoin'])} {settings.currency_name}\n\n"
                f"✨ Новые задания появятся позже!"
            )
            return
        
        if skip_flag or not tasks:
            await msg.edit_text(
                "🎉 **Нет активных заданий!**\n\n"
                "Пожалуйста, зайдите позже.\n"
                "В это время вы можете:\n"
                "• Приглашать друзей 👥\n"
                "• Получать ежедневный бонус 🏆\n"
                "• Активировать промокоды 🎫"
            )
            return
        
        task_url = tasks[0]
        context.user_data["current_task_url"] = task_url
        
        keyboard = [
            [InlineKeyboardButton("✅ Я выполнил", callback_data=f"check_task_{task_url}")],
            [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await msg.edit_text(
            f"📢 **Новое задание!** 📢\n\n"
            f"🔗 **Ссылка:** {task_url}\n\n"
            f"💰 **Награда:** {settings.task_reward} {settings.currency_name}\n"
            f"📊 **Сегодня выполнено:** {user['tasks_today']}/{settings.max_daily_tasks}\n\n"
            f"**Как выполнить:**\n"
            f"1️⃣ Перейдите по ссылке\n"
            f"2️⃣ Подпишитесь на канал\n"
            f"3️⃣ Вернитесь и нажмите «✅ Я выполнил»\n\n"
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
    
    user = get_user_data(user_id)
    
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
            user["tasks_today"] += 1
            user["tasks_completed"].append({
                "url": task_url,
                "completed_at": datetime.now().isoformat()
            })
            db.save()
            
            if completed:
                # Все задания выполнены
                await query.edit_message_text(
                    f"✅ **Задание выполнено!** ✅\n\n"
                    f"💰 Вы получили: {task_reward} {settings.currency_name}\n"
                    f"🎉 **Поздравляем! Вы выполнили все задания!**\n\n"
                    f"📊 Сегодня выполнено: {user['tasks_today']}/{settings.max_daily_tasks}\n"
                    f"💰 Ваш баланс: {format_number(user['mcoin'])} {settings.currency_name}\n\n"
                    f"✨ Отличная работа!"
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
                    f"💰 Вы получили: {task_reward} {settings.currency_name}\n"
                    f"📊 Сегодня выполнено: {user['tasks_today']}/{settings.max_daily_tasks}\n\n"
                    f"📢 **Следующее задание:**\n{new_url}\n\n"
                    f"💰 **Награда:** {settings.task_reward} {settings.currency_name}\n\n"
                    f"Нажмите «✅ Я выполнил» после подписки",
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
            else:
                await query.edit_message_text(
                    f"✅ **Задание выполнено!** ✅\n\n"
                    f"💰 Вы получили: {task_reward} {settings.currency_name}\n"
                    f"📊 Сегодня выполнено: {user['tasks_today']}/{settings.max_daily_tasks}\n"
                    f"💰 Ваш баланс: {format_number(user['mcoin'])} {settings.currency_name}"
                )
        else:
            # Задание не выполнено
            await query.edit_message_text(
                f"❌ **Вы ещё не подписались!** ❌\n\n"
                f"🔗 Пожалуйста, подпишитесь:\n{task_url}\n\n"
                f"**Инструкция:**\n"
                f"1️⃣ Нажмите на ссылку выше\n"
                f"2️⃣ Нажмите «Подписаться» или «Join»\n"
                f"3️⃣ Вернитесь и нажмите «✅ Я выполнил»\n\n"
                f"⏱️ У вас есть 3 минуты на выполнение",
                disable_web_page_preview=True
            )
            
            keyboard = [
                [InlineKeyboardButton("✅ Я выполнил", callback_data=f"check_task_{task_url}")],
                [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_reply_markup(reply_markup)
            
    except Exception as e:
        logger.error(f"Ошибка в check_task_callback: {e}")
        await query.edit_message_text(f"❌ Ошибка при проверке: {e}\n\nПопробуйте еще раз.")

async def skip_task_callback(update: Update, context: CallbackContext):
    """Пропуск задания"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    await query.edit_message_text("⏩ **Пропускаем задание...**")
    
    try:
        result = await call_botohub_api(user_id, is_task=True, skip=True)
        
        tasks = result.get("tasks", [])
        completed = result.get("completed", False)
        
        if completed:
            await query.edit_message_text("✅ **Все задания выполнены!** 🎉")
            return
        
        if tasks:
            new_url = tasks[0]
            context.user_data["current_task_url"] = new_url
            
            keyboard = [
                [InlineKeyboardButton("✅ Я выполнил", callback_data=f"check_task_{new_url}")],
                [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"⏩ **Задание пропущено!**\n\n"
                f"📢 **Новое задание:**\n{new_url}\n\n"
                f"💰 **Награда:** {settings.task_reward} {settings.currency_name}\n\n"
                f"Нажмите «✅ Я выполнил» после подписки",
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
        else:
            await query.edit_message_text("🎉 **Нет доступных заданий!**")
            
    except Exception as e:
        logger.error(f"Ошибка в skip_task_callback: {e}")
        await query.edit_message_text(f"❌ Ошибка: {e}")

# ========== ПРОМОКОДЫ ==========
async def promo_menu(update: Update, context: CallbackContext):
    """Меню промокодов"""
    user_id = update.effective_user.id
    
    keyboard = [
        [InlineKeyboardButton("🎫 Активировать промокод", callback_data="activate_promo")],
        [InlineKeyboardButton("📋 Список активных", callback_data="active_promos")]
    ]
    
    if user_id in settings.admin_list:
        keyboard.append([InlineKeyboardButton("⚙️ Создать промокод", callback_data="admin_promo")])
    
    keyboard.append([InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎫 **Промокоды** 🎫\n\n"
        "Промокоды дают бонусные MCoin!\n\n"
        "**Как использовать:**\n"
        "1. Получите промокод\n"
        "2. Нажмите «Активировать промокод»\n"
        "3. Введите код\n\n"
        "📌 Промокоды можно получить в наших соцсетях!\n"
        "Следите за обновлениями!",
        reply_markup=reply_markup
    )

async def activate_promo_callback(update: Update, context: CallbackContext):
    """Активация промокода"""
    query = update.callback_query
    await query.answer()
    
    context.user_data["promo_step"] = "code"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_promo")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "🎫 **Введите промокод:**\n\n"
        "Введите код в сообщении",
        reply_markup=reply_markup
    )

async def promo_code_input(update: Update, context: CallbackContext):
    """Обработка ввода промокода"""
    user_id = update.effective_user.id
    code = update.message.text.upper()
    
    if code not in db.promo_codes:
        await update.message.reply_text("❌ Неверный промокод!")
        context.user_data.pop("promo_step", None)
        return
    
    promo = db.promo_codes[code]
    
    # Проверяем срок действия
    if promo.get("expiry"):
        expiry_date = datetime.fromisoformat(promo["expiry"])
        if datetime.now() > expiry_date:
            await update.message.reply_text("❌ Срок действия промокода истек!")
            context.user_data.pop("promo_step", None)
            return
    
    # Проверяем лимит использований
    if len(promo.get("used_by", [])) >= promo.get("max_uses", 1):
        await update.message.reply_text("❌ Промокод уже использован максимальное количество раз!")
        context.user_data.pop("promo_step", None)
        return
    
    # Проверяем использовал ли пользователь
    if user_id in promo.get("used_by", []):
        await update.message.reply_text("❌ Вы уже использовали этот промокод!")
        context.user_data.pop("promo_step", None)
        return
    
    # Начисляем награду
    reward = promo.get("reward", 0)
    add_mcoins(user_id, reward, f"promo_{code}", "other")
    
    if "used_by" not in promo:
        promo["used_by"] = []
    promo["used_by"].append(user_id)
    
    db.save()
    
    await update.message.reply_text(
        f"✅ **Промокод активирован!** 🎉\n\n"
        f"🎁 Вы получили: {reward} {settings.currency_name}\n"
        f"💰 Ваш баланс: {format_number(get_user_data(user_id)['mcoin'])} {settings.currency_name}\n\n"
        f"✨ Спасибо за использование бота!"
    )
    
    context.user_data.pop("promo_step", None)

async def active_promos_callback(update: Update, context: CallbackContext):
    """Показывает активные промокоды"""
    query = update.callback_query
    await query.answer()
    
    active = []
    for code, promo in db.promo_codes.items():
        if promo.get("active", True):
            expiry = promo.get("expiry", "Бессрочно")
            if expiry != "Бессрочно":
                try:
                    expiry_date = datetime.fromisoformat(expiry)
                    if datetime.now() > expiry_date:
                        continue
                except:
                    pass
            active.append(f"🎫 {code} - {promo['reward']} {settings.currency_name} (до {expiry})")
    
    if not active:
        await query.message.edit_text("📭 Нет активных промокодов.\n\nСледите за новостями!")
        return
    
    text = "📋 **Активные промокоды:**\n\n" + "\n".join(active)
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="promo_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, reply_markup=reply_markup)

# ========== СТАТИСТИКА ==========
async def stats_menu(update: Update, context: CallbackContext):
    """Показывает статистику пользователя и глобальную"""
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    level, exp_needed, current_exp = get_level_info(user_id)
    
    # Прогресс-бар
    progress = int((current_exp / exp_needed) * 20) if exp_needed > 0 else 0
    progress_bar = "█" * progress + "░" * (20 - progress)
    
    keyboard = [
        [InlineKeyboardButton("📊 Детальная статистика", callback_data="detailed_stats")],
        [InlineKeyboardButton("🏆 Топ пользователей", callback_data="top_users")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📊 **Ваша статистика** 📊\n\n"
        f"💰 {settings.currency_name}: {format_number(user['mcoin'])}\n"
        f"📈 Всего заработано: {format_number(user['total_earned'])}\n"
        f"💸 Выведено: {format_number(user['total_withdrawn'])}\n\n"
        f"🏅 **Уровень:** {level}\n"
        f"📈 **Прогресс:** {progress_bar} {format_number(current_exp)}/{format_number(exp_needed)}\n\n"
        f"✅ Выполнено заданий: {len(user['tasks_completed'])}\n"
        f"📊 Заданий сегодня: {user['tasks_today']}/{settings.max_daily_tasks}\n"
        f"👥 Рефералов: {len(user['referrals'])}\n"
        f"🔥 Серия: {user['daily_streak']} дней\n"
        f"📅 В боте: {(datetime.now() - datetime.fromisoformat(user['join_date'])).days} дней",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def detailed_stats_callback(update: Update, context: CallbackContext):
    """Детальная статистика"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user_data(user_id)
    
    completed_withdrawals = len([r for r in db.withdraw_requests.values() if r.get("status") == "completed" and r.get("user_id") == user_id])
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="stats_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"📊 **Детальная статистика** 📊\n\n"
        f"💰 **Заработано:**\n"
        f"• С заданий: {user['task_earned']} {settings.currency_name}\n"
        f"• С рефералов: {user['referral_earned']} {settings.currency_name}\n"
        f"• С бонусов: {user['bonus_claims']} раз\n\n"
        f"📊 **Активность:**\n"
        f"• Заданий выполнено: {len(user['tasks_completed'])}\n"
        f"• Рефералов приглашено: {len(user['referrals'])}\n"
        f"• Выводов: {completed_withdrawals}\n\n"
        f"📅 **Даты:**\n"
        f"• В боте с: {user['join_date'][:10]}\n"
        f"• Последний визит: {user['last_seen'][:10] if user.get('last_seen') else 'Неизвестно'}\n"
        f"• Последний бонус: {user['daily_last'][:10] if user.get('daily_last') else 'Не получал'}",
        reply_markup=reply_markup
    )

async def top_users_callback(update: Update, context: CallbackContext):
    """Топ пользователей"""
    query = update.callback_query
    await query.answer()
    
    # Сортируем пользователей по балансу
    sorted_users = sorted(db.users.items(), key=lambda x: x[1].get("mcoin", 0), reverse=True)[:10]
    
    top_text = "🏆 **Топ пользователей** 🏆\n\n"
    for i, (uid, data) in enumerate(sorted_users, 1):
        name = data.get("first_name", f"User_{uid}")
        if len(name) > 15:
            name = name[:15] + "..."
        top_text += f"{'🥇' if i == 1 else '🥈' if i == 2 else '🥉' if i == 3 else f'{i}.'} {name} - {data.get('mcoin', 0)} {settings.currency_name}\n"
    
    if not sorted_users:
        top_text = "📭 Нет пользователей"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="stats_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(top_text, reply_markup=reply_markup)

# ========== ПОМОЩЬ ==========
async def help_menu(update: Update, context: CallbackContext):
    """Меню помощи"""
    keyboard = [
        [InlineKeyboardButton("📋 Как выполнять задания", callback_data="help_tasks")],
        [InlineKeyboardButton("👥 Реферальная система", callback_data="help_referral")],
        [InlineKeyboardButton("💸 Вывод средств", callback_data="help_withdraw")],
        [InlineKeyboardButton("🎫 Промокоды", callback_data="help_promo")],
        [InlineKeyboardButton("❓ Частые вопросы", callback_data="help_faq")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    help_text = (
        "❓ **Помощь** ❓\n\n"
        "**📋 Задания:**\n"
        "Нажмите кнопку «Задания» или /tasks\n"
        "Выполняйте задания и получайте MCoin!\n\n"
        "**👥 Рефералы:**\n"
        "Приглашайте друзей по ссылке\n"
        "Получайте бонусы за каждого реферала!\n\n"
        "**💸 Вывод средств:**\n"
        "Накопите достаточно MCoin\n"
        "Создайте заявку на вывод\n\n"
        "**🎫 Промокоды:**\n"
        "Активируйте промокоды для получения бонусов!\n\n"
        "**🏆 Ежедневный бонус:**\n"
        "Заходите каждый день\n"
        "Увеличивайте серию и бонусы!\n\n"
        "По всем вопросам обращайтесь к администратору."
    )
    
    await update.message.reply_text(help_text, reply_markup=reply_markup)

# ========== АДМИН ПАНЕЛЬ ==========
async def admin_panel(update: Update, context: CallbackContext):
    """Главное меню админ панели"""
    if update.effective_user.id not in settings.admin_list:
        await update.message.reply_text("⛔ У вас нет доступа к админ панели!")
        return
    
    keyboard = [
        [InlineKeyboardButton("💰 Настройка наград", callback_data="admin_rewards")],
        [InlineKeyboardButton("📢 Обязательные подписки", callback_data="admin_forcesub")],
        [InlineKeyboardButton("👥 Управление пользователями", callback_data="admin_users")],
        [InlineKeyboardButton("📊 Статистика бота", callback_data="admin_stats")],
        [InlineKeyboardButton("💸 Управление выводами", callback_data="admin_withdrawals")],
        [InlineKeyboardButton("📨 Рассылка", callback_data="admin_mailing")],
        [InlineKeyboardButton("🎫 Промокоды", callback_data="admin_promo")],
        [InlineKeyboardButton("📦 Чековая система", callback_data="admin_cheques")],
        [InlineKeyboardButton("⚙️ Настройки бота", callback_data="admin_settings")],
        [InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    pending_withdrawals = len([r for r in db.withdraw_requests.values() if r.get("status") == "pending"])
    total_users = db.global_stats["total_users"]
    
    await update.message.reply_text(
        f"⚙️ **Админ панель** ⚙️\n\n"
        f"📊 **Быстрая статистика:**\n"
        f"👥 Пользователей: {total_users}\n"
        f"💰 Всего заработано: {format_number(db.global_stats['total_mcoins_earned'])} {settings.currency_name}\n"
        f"✅ Заданий выполнено: {db.global_stats['total_tasks_completed']}\n"
        f"💸 Ожидают вывода: {pending_withdrawals}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

# ========== АДМИН: НАСТРОЙКА НАГРАД ==========
async def admin_rewards_menu(update: Update, context: CallbackContext):
    """Меню настройки наград"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton(f"💰 За задание: {settings.task_reward}", callback_data="set_task_reward")],
        [InlineKeyboardButton(f"👥 За реферала: {settings.referral_reward}", callback_data="set_ref_reward")],
        [InlineKeyboardButton(f"🏆 Ежедневный: {settings.daily_reward}", callback_data="set_daily_reward")],
        [InlineKeyboardButton(f"💸 Мин. вывод: {settings.min_withdraw}", callback_data="set_min_withdraw")],
        [InlineKeyboardButton(f"📊 Лимит заданий: {settings.max_daily_tasks}", callback_data="set_max_tasks")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "💰 **Настройка наград** 💰\n\n"
        "Выберите параметр для изменения:",
        reply_markup=reply_markup
    )

async def set_reward_value(update: Update, context: CallbackContext):
    """Установка значения награды"""
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
    """Обработка ввода значения награды"""
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
        
        # Обновляем настройку
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
        await update.message.reply_text("❌ Введите корректное число!")

# ========== АДМИН: ОБЯЗАТЕЛЬНЫЕ ПОДПИСКИ ==========
async def admin_forcesub_menu(update: Update, context: CallbackContext):
    """Меню управления обязательными подписками"""
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
    """Добавление обязательной подписки через callback"""
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
    """Обработка ввода названия подписки"""
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
    """Удаление обязательной подписки"""
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
    """Подтверждение удаления подписки"""
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
    """Меню управления пользователями"""
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
    """Запрос ID пользователя для бана"""
    query = update.callback_query
    await query.answer()
    
    context.user_data["admin_action"] = "ban"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "⛔ **Бан пользователя**\n\n"
        "Введите ID пользователя для бана:",
        reply_markup=reply_markup
    )

async def unban_user_callback(update: Update, context: CallbackContext):
    """Запрос ID пользователя для разбана"""
    query = update.callback_query
    await query.answer()
    
    context.user_data["admin_action"] = "unban"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "✅ **Разбан пользователя**\n\n"
        "Введите ID пользователя для разбана:",
        reply_markup=reply_markup
    )

async def add_mcoin_callback(update: Update, context: CallbackContext):
    """Запрос данных для добавления MCoin"""
    query = update.callback_query
    await query.answer()
    
    context.user_data["admin_action"] = "add_mcoin"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "💰 **Добавление MCoin**\n\n"
        "Введите ID пользователя и сумму через пробел:\n"
        "Пример: 123456789 100",
        reply_markup=reply_markup
    )

async def admin_action_input(update: Update, context: CallbackContext):
    """Обработка действий админа с пользователями"""
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
            target_id = int(text)
            if target_id in db.bans:
                await update.message.reply_text("❌ Пользователь уже забанен!")
                return
            
            db.bans[target_id] = {
                "reason": "Нарушение правил",
                "date": datetime.now().isoformat(),
                "banned_by": user_id
            }
            db.save()
            
            await update.message.reply_text(f"⛔ Пользователь {target_id} забанен!")
            
        except ValueError:
            await update.message.reply_text("❌ Введите корректный ID!")
            
    elif action == "unban":
        try:
            target_id = int(text)
            if target_id not in db.bans:
                await update.message.reply_text("❌ Пользователь не забанен!")
                return
            
            del db.bans[target_id]
            db.save()
            
            await update.message.reply_text(f"✅ Пользователь {target_id} разбанен!")
            
        except ValueError:
            await update.message.reply_text("❌ Введите корректный ID!")
            
    elif action == "add_mcoin":
        try:
            parts = text.split()
            if len(parts) != 2:
                await update.message.reply_text("❌ Используйте: ID Сумма")
                return
            
            target_id = int(parts[0])
            amount = int(parts[1])
            
            if amount <= 0:
                await update.message.reply_text("❌ Сумма должна быть положительной!")
                return
            
            add_mcoins(target_id, amount, f"admin_add_{amount}", "other")
            
            await update.message.reply_text(
                f"✅ Добавлено {amount} {settings.currency_name} пользователю {target_id}!"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Введите корректные данные!")
    
    context.user_data.pop("admin_action", None)

async def list_users_callback(update: Update, context: CallbackContext):
    """Список всех пользователей"""
    query = update.callback_query
    await query.answer()
    
    if not db.users:
        await query.message.edit_text("📭 Нет пользователей!")
        return
    
    users_list = []
    for uid, data in sorted(db.users.items(), key=lambda x: x[1].get("mcoin", 0), reverse=True)[:20]:
        name = data.get("first_name", f"User_{uid}")
        users_list.append(f"{uid} | {name} | {data.get('mcoin', 0)} {settings.currency_name}")
    
    text = "📊 **Список пользователей (топ 20):**\n\n" + "\n".join(users_list)
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_users")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, reply_markup=reply_markup)

# ========== АДМИН: СТАТИСТИКА ==========
async def admin_stats_callback(update: Update, context: CallbackContext):
    """Полная статистика бота для админа"""
    query = update.callback_query
    await query.answer()
    
    total_users = db.global_stats["total_users"]
    total_earned = db.global_stats["total_mcoins_earned"]
    total_withdrawn = db.global_stats["total_withdrawn"]
    total_tasks = db.global_stats["total_tasks_completed"]
    
    pending_withdrawals = len([r for r in db.withdraw_requests.values() if r.get("status") == "pending"])
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
        f"• Всего заработано: {format_number(total_earned)} {settings.currency_name}\n"
        f"• Выведено: {format_number(total_withdrawn)} {settings.currency_name}\n"
        f"• В системе: {format_number(total_earned - total_withdrawn)} {settings.currency_name}\n\n"
        f"📋 **Заявки на вывод:**\n"
        f"• Ожидают: {pending_withdrawals}\n"
        f"• Всего: {total_withdraw_requests}\n\n"
        f"✅ **Задания:**\n"
        f"• Выполнено: {total_tasks}\n"
        f"• В среднем на пользователя: {total_tasks // total_users if total_users > 0 else 0}",
        reply_markup=reply_markup
    )

# ========== АДМИН: УПРАВЛЕНИЕ ВЫВОДАМИ ==========
async def admin_withdrawals_callback(update: Update, context: CallbackContext):
    """Управление заявками на вывод"""
    query = update.callback_query
    await query.answer()
    
    pending = []
    for uid, req in db.withdraw_requests.items():
        if req.get("status") == "pending":
            user = db.users.get(uid, {})
            name = user.get("first_name", f"User_{uid}")
            pending.append(f"{uid} | {name} | {req['amount']} {settings.currency_name} | {req['method']}")
    
    if not pending:
        await query.message.edit_text("📭 Нет заявок на вывод!")
        return
    
    text = "💸 **Заявки на вывод:**\n\n" + "\n".join(pending[:10])
    if len(pending) > 10:
        text += f"\n\n... и еще {len(pending) - 10}"
    
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить вывод", callback_data="confirm_withdraw")],
        [InlineKeyboardButton("❌ Отклонить вывод", callback_data="reject_withdraw")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, reply_markup=reply_markup)

async def confirm_withdraw_callback(update: Update, context: CallbackContext):
    """Подтверждение вывода"""
    query = update.callback_query
    await query.answer()
    
    context.user_data["admin_action"] = "confirm_withdraw"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "✅ **Подтверждение вывода**\n\n"
        "Введите ID пользователя для подтверждения вывода:",
        reply_markup=reply_markup
    )

async def reject_withdraw_callback(update: Update, context: CallbackContext):
    """Отклонение вывода"""
    query = update.callback_query
    await query.answer()
    
    context.user_data["admin_action"] = "reject_withdraw"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "❌ **Отклонение вывода**\n\n"
        "Введите ID пользователя для отклонения вывода:",
        reply_markup=reply_markup
    )

async def admin_withdraw_action(update: Update, context: CallbackContext):
    """Обработка действий с выводами"""
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    action = context.user_data.get("admin_action")
    if action not in ["confirm_withdraw", "reject_withdraw"]:
        return
    
    try:
        target_id = int(update.message.text)
        
        if target_id not in db.withdraw_requests:
            await update.message.reply_text("❌ Заявка не найдена!")
            return
        
        request = db.withdraw_requests[target_id]
        if request.get("status") != "pending":
            await update.message.reply_text("❌ Заявка уже обработана!")
            return
        
        if action == "confirm_withdraw":
            request["status"] = "completed"
            request["completed_at"] = datetime.now().isoformat()
            
            db.global_stats["total_withdrawn"] += request["final_amount"]
            
            await update.message.reply_text(
                f"✅ Вывод подтвержден!\n"
                f"Пользователь: {target_id}\n"
                f"Сумма: {request['amount']} {settings.currency_name}\n"
                f"К получению: {request['final_amount']} {settings.currency_name}"
            )
            
            # Уведомляем пользователя
            try:
                await context.bot.send_message(
                    target_id,
                    f"✅ **Ваша заявка на вывод подтверждена!**\n\n"
                    f"💰 Сумма: {request['amount']} {settings.currency_name}\n"
                    f"💳 К получению: {request['final_amount']} {settings.currency_name}\n"
                    f"💳 Способ: {request['method'].upper()}\n\n"
                    f"Средства будут отправлены в ближайшее время!"
                )
            except:
                pass
                
        else:  # reject
            request["status"] = "rejected"
            request["rejected_at"] = datetime.now().isoformat()
            
            # Возвращаем деньги
            add_mcoins(target_id, request["amount"], "withdraw_rejected", "other")
            
            await update.message.reply_text(
                f"❌ Вывод отклонен!\n"
                f"Пользователь: {target_id}\n"
                f"Сумма возвращена на баланс."
            )
            
            # Уведомляем пользователя
            try:
                await context.bot.send_message(
                    target_id,
                    f"❌ **Ваша заявка на вывод отклонена!**\n\n"
                    f"💰 Сумма: {request['amount']} {settings.currency_name}\n"
                    f"💳 Способ: {request['method'].upper()}\n\n"
                    f"Средства возвращены на ваш баланс.\n"
                    f"По вопросам обратитесь к администратору."
                )
            except:
                pass
        
        db.save()
        
    except ValueError:
        await update.message.reply_text("❌ Введите корректный ID!")
    
    context.user_data.pop("admin_action", None)

# ========== АДМИН: РАССЫЛКА ==========
async def admin_mailing_callback(update: Update, context: CallbackContext):
    """Создание рассылки"""
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
    """Обработка текста рассылки"""
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
    """Отправка рассылки"""
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

# ========== АДМИН: ПРОМОКОДЫ ==========
async def admin_promo_callback(update: Update, context: CallbackContext):
    """Управление промокодами"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("➕ Создать промокод", callback_data="create_promo_code")],
        [InlineKeyboardButton("📋 Список промокодов", callback_data="list_promo_codes")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "🎫 **Управление промокодами** 🎫\n\n"
        f"Всего промокодов: {len(db.promo_codes)}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

async def create_promo_code_callback(update: Update, context: CallbackContext):
    """Создание промокода"""
    query = update.callback_query
    await query.answer()
    
    context.user_data["promo_create_step"] = "code"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_promo_create")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "🎫 **Создание промокода**\n\n"
        "Введите код промокода (латиница, цифры, без пробелов):",
        reply_markup=reply_markup
    )

async def promo_code_create_input(update: Update, context: CallbackContext):
    """Обработка создания промокода"""
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    step = context.user_data.get("promo_create_step")
    
    if step == "code":
        code = update.message.text.upper()
        
        if len(code) < 3:
            await update.message.reply_text("❌ Код должен содержать минимум 3 символа!")
            return
        
        if code in db.promo_codes:
            await update.message.reply_text("❌ Такой промокод уже существует!")
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
                f"💰 Награда: {reward} {settings.currency_name}\n\n"
                "Введите срок действия (в днях) или 0 для бессрочного:"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Введите корректное число!")
            
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
                f"💰 Награда: {reward} {settings.currency_name}\n"
                f"⏱️ Срок: {expiry_text}\n\n"
                f"Отправьте код пользователям!"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Введите корректное число дней!")

async def list_promo_codes_callback(update: Update, context: CallbackContext):
    """Список промокодов"""
    query = update.callback_query
    await query.answer()
    
    if not db.promo_codes:
        await query.message.edit_text("📭 Нет созданных промокодов.")
        return
    
    text = "📋 **Список промокодов:**\n\n"
    for code, promo in db.promo_codes.items():
        status = "🟢 Активен" if promo.get("active") else "🔴 Неактивен"
        uses = len(promo.get("used_by", []))
        expiry = promo.get("expiry", "Бессрочно")
        if expiry != "Бессрочно":
            try:
                expiry_date = datetime.fromisoformat(expiry)
                if datetime.now() > expiry_date:
                    status = "🔴 Истек"
            except:
                pass
        
        text += f"🎫 {code}\n"
        text += f"   💰 {promo['reward']} {settings.currency_name}\n"
        text += f"   📊 Использован: {uses} раз\n"
        text += f"   📅 Срок: {expiry[:10] if expiry != 'Бессрочно' else expiry}\n"
        text += f"   📌 {status}\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_promo")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, reply_markup=reply_markup)

# ========== АДМИН: ЧЕКИ ==========
async def admin_cheques_callback(update: Update, context: CallbackContext):
    """Управление чеками"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📝 Создать чек", callback_data="create_cheque_menu")],
        [InlineKeyboardButton("📋 Список чеков", callback_data="list_cheques_admin")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    total_cheques = len(db.cheques)
    active_cheques = len([c for c in db.cheques.values() if c.get("active")])
    
    await query.message.edit_text(
        f"📦 **Чековая система** 📦\n\n"
        f"📊 Всего чеков: {total_cheques}\n"
        f"🟢 Активных: {active_cheques}\n"
        f"🔴 Использовано: {total_cheques - active_cheques}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

async def create_cheque_menu_callback(update: Update, context: CallbackContext):
    """Создание чека через админку"""
    query = update.callback_query
    await query.answer()
    
    context.user_data["cheque_step"] = "amount"
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_cheque")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "📝 **Создание чека**\n\n"
        "Введите сумму чека:",
        reply_markup=reply_markup
    )

async def cheque_amount_input(update: Update, context: CallbackContext):
    """Ввод суммы чека"""
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    try:
        amount = int(update.message.text)
        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть положительной!")
            return
        
        context.user_data["cheque_amount"] = amount
        context.user_data["cheque_step"] = "count"
        
        await update.message.reply_text(
            f"💰 Сумма: {amount} {settings.currency_name}\n\n"
            "Введите количество чеков:"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число!")

async def cheque_count_input(update: Update, context: CallbackContext):
    """Ввод количества чеков"""
    user_id = update.effective_user.id
    if user_id not in settings.admin_list:
        return
    
    try:
        count = int(update.message.text)
        if count <= 0 or count > 100:
            await update.message.reply_text("❌ Количество должно быть от 1 до 100!")
            return
        
        amount = context.user_data["cheque_amount"]
        
        created = []
        for i in range(count):
            code = generate_cheque_code()
            db.cheques[code] = {
                "amount": amount,
                "created_by": user_id,
                "created_at": datetime.now().isoformat(),
                "used_by": None,
                "used_at": None,
                "active": True
            }
            created.append(code)
        
        db.save()
        
        context.user_data.pop("cheque_amount", None)
        context.user_data.pop("cheque_step", None)
        
        cheques_text = "\n".join([f"`{code}` - {amount} {settings.currency_name}" for code in created])
        await update.message.reply_text(
            f"✅ **Создано {count} чеков**\n\n"
            f"💰 Сумма каждого: {amount} {settings.currency_name}\n\n"
            f"**Коды чеков:**\n{cheques_text}\n\n"
            f"Отправьте эти коды пользователям для активации.",
            parse_mode="Markdown"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число!")

async def list_cheques_admin_callback(update: Update, context: CallbackContext):
    """Список чеков для админа"""
    query = update.callback_query
    await query.answer()
    
    if not db.cheques:
        await query.message.edit_text("📭 Нет созданных чеков.")
        return
    
    active = []
    used = []
    
    for code, cheque in db.cheques.items():
        info = f"`{code}` - {cheque['amount']} {settings.currency_name}"
        if cheque["active"] and not cheque["used_by"]:
            active.append(info)
        else:
            user = get_user_data(cheque["used_by"]) if cheque["used_by"] else None
            user_info = f"@{user['username']}" if user and user.get("username") else f"ID:{cheque['used_by']}" if cheque["used_by"] else "Не использован"
            used.append(f"{info} - Использован: {user_info}")
    
    text = "📊 **Список чеков**\n\n"
    if active:
        text += f"🟢 **Активные ({len(active)}):**\n" + "\n".join(active[:20]) + "\n\n"
    if used:
        text += f"🔴 **Использованные ({len(used)}):**\n" + "\n".join(used[:20])
    
    if len(active) > 20 or len(used) > 20:
        text += f"\n\n📌 Всего: {len(active)} активных, {len(used)} использованных"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_cheques")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")

# ========== АДМИН: НАСТРОЙКИ БОТА ==========
async def admin_settings_callback(update: Update, context: CallbackContext):
    """Настройки бота"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton(f"🔄 Режим обслуживания: {settings.maintenance_mode}", callback_data="toggle_maintenance")],
        [InlineKeyboardButton(f"💱 Курс валюты: {settings.currency_name}", callback_data="set_currency")],
        [InlineKeyboardButton(f"📊 Лимит задач: {settings.max_daily_tasks}", callback_data="set_max_tasks")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "⚙️ **Настройки бота** ⚙️\n\n"
        f"🔄 Режим обслуживания: {'Включен' if settings.maintenance_mode else 'Выключен'}\n"
        f"💱 Валюта: {settings.currency_name}\n"
        f"📊 Лимит задач в день: {settings.max_daily_tasks}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

async def toggle_maintenance_callback(update: Update, context: CallbackContext):
    """Переключение режима обслуживания"""
    query = update.callback_query
    await query.answer()
    
    settings.maintenance_mode = not settings.maintenance_mode
    settings.save()
    
    status = "включен" if settings.maintenance_mode else "выключен"
    await query.message.edit_text(f"🔄 Режим обслуживания {status}!")

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
async def start(update: Update, context: CallbackContext):
    """Обработка команды /start"""
    user_id = update.effective_user.id
    
    # Проверка бана
    if user_id in db.bans:
        await update.message.reply_text(
            "⛔ **Вы забанены!** ⛔\n\n"
            f"Причина: {db.bans[user_id].get('reason', 'Не указана')}\n"
            f"Дата: {db.bans[user_id].get('date', 'Неизвестно')}"
        )
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
                referrer_data["referral_count"] += 1
                
                # Начисляем бонус
                ref_reward = int(settings.referral_reward * get_referral_bonus(len(referrer_data["referrals"])))
                add_mcoins(referrer_id, ref_reward, "referral_bonus", "referral")
                db.save()
                
                try:
                    await context.bot.send_message(
                        referrer_id,
                        f"👥 **Новый реферал!** 👥\n\n"
                        f"{update.effective_user.first_name} присоединился по вашей ссылке!\n"
                        f"💰 Вы получили: {ref_reward} {settings.currency_name}\n"
                        f"📊 Всего рефералов: {len(referrer_data['referrals'])}\n"
                        f"📈 Бонусный множитель: x{get_referral_bonus(len(referrer_data['referrals'])):.2f}"
                    )
                except Exception as e:
                    logger.error(f"Не удалось отправить сообщение рефереру: {e}")
    
    get_user_data(user_id)
    
    # Проверка обязательных подписок при старте
    passed, not_passed = await check_force_subs(user_id, context.bot)
    sub_text = ""
    if not passed:
        sub_text = (
            f"\n\n⚠️ **Важно:** Для работы с ботом необходимо подписаться на:\n"
            f"{get_subscription_links()}\n\n"
            f"После подписки обновите бота командой /start"
        )
    
    welcome_text = (
        f"👋 **Привет, {update.effective_user.first_name}!**\n\n"
        f"{settings.welcome_message}\n\n"
        f"💎 **{settings.bot_name}**\n"
        f"{settings.bot_description}\n\n"
        f"✨ **Что вы можете делать:**\n"
        f"• 📋 Выполнять задания и получать {settings.currency_name}\n"
        f"• 👥 Приглашать друзей и получать бонусы\n"
        f"• 🏆 Получать ежедневные бонусы\n"
        f"• 💸 Выводить заработанные средства\n"
        f"• 🎫 Активировать промокоды\n\n"
        f"💰 Ваш баланс: 0 {settings.currency_name}"
        f"{sub_text}"
    )
    
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard(user_id))

async def balance_handler(update: Update, context: CallbackContext):
    """Показывает баланс"""
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    level, exp_needed, current_exp = get_level_info(user_id)
    progress = int((current_exp / exp_needed) * 20) if exp_needed > 0 else 0
    progress_bar = "█" * progress + "░" * (20 - progress)
    
    await update.message.reply_text(
        f"💰 **Ваш баланс** 💰\n\n"
        f"🎮 {settings.currency_name}: `{format_number(user['mcoin'])}`\n\n"
        f"📊 **Прогресс:**\n"
        f"🏅 Уровень: {level}\n"
        f"📈 Опыт: {progress_bar} {format_number(current_exp)}/{format_number(exp_needed)}\n\n"
        f"📊 **Статистика:**\n"
        f"💰 Всего заработано: {format_number(user['total_earned'])}\n"
        f"💸 Выведено: {format_number(user['total_withdrawn'])}\n"
        f"✅ С заданий: {format_number(user['task_earned'])}\n"
        f"👥 С рефералов: {format_number(user['referral_earned'])}\n"
        f"📅 В боте: {(datetime.now() - datetime.fromisoformat(user['join_date'])).days} дней\n"
        f"🔥 Серия: {user['daily_streak']} дней",
        parse_mode="Markdown"
    )

async def handle_text(update: Update, context: CallbackContext):
    """Обработка текстовых сообщений"""
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
        return
    
    if context.user_data.get("promo_create_step"):
        await promo_code_create_input(update, context)
        return
    
    if context.user_data.get("cheque_step") == "count":
        await cheque_count_input(update, context)
        return
    
    if context.user_data.get("cheque_step") == "amount":
        await cheque_amount_input(update, context)
        return
    
    if context.user_data.get("sub_type"):
        await add_force_sub_input(update, context)
        return
    
    # Обработка команд с кнопок
    if text == f"💰 {settings.currency_name}":
        await balance_handler(update, context)
    elif text == "📋 Задания":
        await tasks_mode(update, context)
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

# ========== ОБРАБОТЧИК ОТМЕНЫ ==========
async def cancel_action_callback(update: Update, context: CallbackContext):
    """Отмена действия админа"""
    query = update.callback_query
    await query.answer()
    
    context.user_data.pop("admin_action", None)
    await query.message.edit_text("✅ Действие отменено.")

async def cancel_setting_callback(update: Update, context: CallbackContext):
    """Отмена настройки"""
    query = update.callback_query
    await query.answer()
    
    context.user_data.pop("setting_to_change", None)
    await query.message.edit_text("✅ Отменено.")

async def cancel_mailing_callback(update: Update, context: CallbackContext):
    """Отмена рассылки"""
    query = update.callback_query
    await query.answer()
    
    context.user_data.pop("mailing_message", None)
    context.user_data.pop("mailing_step", None)
    await query.message.edit_text("✅ Рассылка отменена.")

async def cancel_promo_create_callback(update: Update, context: CallbackContext):
    """Отмена создания промокода"""
    query = update.callback_query
    await query.answer()
    
    context.user_data.pop("promo_create_code", None)
    context.user_data.pop("promo_create_reward", None)
    context.user_data.pop("promo_create_step", None)
    await query.message.edit_text("✅ Создание промокода отменено.")

async def cancel_promo_callback(update: Update, context: CallbackContext):
    """Отмена активации промокода"""
    query = update.callback_query
    await query.answer()
    
    context.user_data.pop("promo_step", None)
    await query.message.edit_text("✅ Активация промокода отменена.")

async def cancel_cheque_callback(update: Update, context: CallbackContext):
    """Отмена создания чека"""
    query = update.callback_query
    await query.answer()
    
    context.user_data.pop("cheque_amount", None)
    context.user_data.pop("cheque_step", None)
    await query.message.edit_text("✅ Создание чека отменено.")

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
    app.add_handler(CommandHandler("tasks", tasks_mode))
    app.add_handler(CommandHandler("cheque", activate_cheque))
    app.add_handler(CommandHandler("create_cheque", create_cheque))
    app.add_handler(CommandHandler("list_cheques", list_cheques))
    
    # Регистрируем callback обработчики
    app.add_handler(CallbackQueryHandler(check_task_callback, pattern="^check_task_"))
    app.add_handler(CallbackQueryHandler(skip_task_callback, pattern="^skip_task$"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_rewards_menu, pattern="^admin_rewards$"))
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
    app.add_handler(CallbackQueryHandler(confirm_withdraw_callback, pattern="^confirm_withdraw$"))
    app.add_handler(CallbackQueryHandler(reject_withdraw_callback, pattern="^reject_withdraw$"))
    app.add_handler(CallbackQueryHandler(admin_mailing_callback, pattern="^admin_mailing$"))
    app.add_handler(CallbackQueryHandler(send_mailing_callback, pattern="^send_mailing$"))
    app.add_handler(CallbackQueryHandler(admin_promo_callback, pattern="^admin_promo$"))
    app.add_handler(CallbackQueryHandler(create_promo_code_callback, pattern="^create_promo_code$"))
    app.add_handler(CallbackQueryHandler(list_promo_codes_callback, pattern="^list_promo_codes$"))
    app.add_handler(CallbackQueryHandler(admin_cheques_callback, pattern="^admin_cheques$"))
    app.add_handler(CallbackQueryHandler(create_cheque_menu_callback, pattern="^create_cheque_menu$"))
    app.add_handler(CallbackQueryHandler(list_cheques_admin_callback, pattern="^list_cheques_admin$"))
    app.add_handler(CallbackQueryHandler(admin_settings_callback, pattern="^admin_settings$"))
    app.add_handler(CallbackQueryHandler(toggle_maintenance_callback, pattern="^toggle_maintenance$"))
    
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
    
    app.add_handler(CallbackQueryHandler(cancel_action_callback, pattern="^cancel_action$"))
    app.add_handler(CallbackQueryHandler(cancel_setting_callback, pattern="^cancel_setting$"))
    app.add_handler(CallbackQueryHandler(cancel_mailing_callback, pattern="^cancel_mailing$"))
    app.add_handler(CallbackQueryHandler(cancel_promo_create_callback, pattern="^cancel_promo_create$"))
    app.add_handler(CallbackQueryHandler(cancel_promo_callback, pattern="^cancel_promo$"))
    app.add_handler(CallbackQueryHandler(cancel_cheque_callback, pattern="^cancel_cheque$"))
    app.add_handler(CallbackQueryHandler(cancel_withdraw, pattern="^cancel_withdraw$"))
    
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.message.delete(), pattern="^back_to_main$"))
    
    # Обработчик текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Запускаем бота
    print("🚀 Бот запущен...")
    print(f"📊 Администратор: {ADMIN_ID}")
    print(f"💎 Название: {settings.bot_name}")
    print(f"👥 Пользователей: {db.global_stats['total_users']}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()