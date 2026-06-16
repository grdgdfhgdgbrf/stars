import asyncio
import json
import os
import logging
import random
import string
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from enum import Enum

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
BOT_TOKEN = "8251949164:AAEUSmnhX_S4p-vWDD4fvC6mDclV0LvIFe0"
BOTOHUB_TOKEN = "3feed57e-9303-4343-8d87-ed8d9dd5650f"
BOTOHUB_API_URL = "https://botohub.me/get-tasks"
ADMIN_ID = 5356400377

# Состояния для ConversationHandler
(ADMIN_MAILING, ADMIN_PROMO_NAME, ADMIN_PROMO_REWARD, ADMIN_PROMO_USES, ADMIN_PROMO_EXPIRY,
 CREATE_CHEQUE_AMOUNT, PROCESS_WITHDRAW, SET_FORCE_CHANNEL, REMOVE_FORCE_CHANNEL,
 SET_TASK_REWARD, SET_REF_REWARD, SET_DAILY_REWARD, SET_MIN_WITHDRAW,
 ADD_BALANCE_USER, REMOVE_BALANCE_USER, BAN_USER, UNBAN_USER) = range(16)

# Файлы для хранения данных
DATA_FILE = "bot_data.json"
SETTINGS_FILE = "settings.json"

# ========== СТРУКТУРА ДАННЫХ ==========
class BotDatabase:
    def __init__(self):
        self.users: Dict[int, Dict] = {}
        self.cheques: Dict[str, Dict] = {}  # cheque_code: {amount, creator, created_date, activated_by, is_activated}
        self.withdraw_requests: Dict[int, List[Dict]] = {}
        self.promo_codes: Dict[str, Dict] = {}
        self.banned_users: Dict[int, Dict] = {}
        self.global_stats: Dict = {
            "total_users": 0,
            "total_mcoins_earned": 0,
            "total_withdrawn": 0,
            "total_tasks_completed": 0,
            "total_cheques_created": 0,
            "total_cheques_activated": 0
        }
        
    def save(self):
        data = {
            "users": self.users,
            "cheques": self.cheques,
            "withdraw_requests": self.withdraw_requests,
            "promo_codes": self.promo_codes,
            "banned_users": self.banned_users,
            "global_stats": self.global_stats
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
                    self.cheques = data.get("cheques", {})
                    self.withdraw_requests = {int(k): v for k, v in data.get("withdraw_requests", {}).items()}
                    self.promo_codes = data.get("promo_codes", {})
                    self.banned_users = {int(k): v for k, v in data.get("banned_users", {}).items()}
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
        self.force_sub_channels = []  # Список каналов для обязательной подписки
        self.force_sub_groups = []    # Список групп для обязательной подписки
        self.welcome_message = "Добро пожаловать в бот! Выполняй задания и зарабатывай монеты!"
        self.referral_program = True
        self.withdraw_methods = ["qiwi", "card", "crypto"]
        self.admin_list = [ADMIN_ID]
        self.bot_name = "TaskBot"
        self.currency_name = "MCoin"
        
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
    """Создает главную клавиатуру"""
    keyboard = [
        [KeyboardButton(f"💰 {settings.currency_name}"), KeyboardButton("📋 Задания")],
        [KeyboardButton("👥 Рефералы"), KeyboardButton("🏆 Ежедневный бонус")],
        [KeyboardButton("💸 Вывод средств"), KeyboardButton("🎫 Промокоды")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("🎁 Чеки")],
    ]
    
    if user_id in settings.admin_list and user_id not in db.banned_users:
        keyboard.append([KeyboardButton("⚙️ Админ панель")])
    
    if user_id in db.banned_users:
        return ReplyKeyboardMarkup([["ℹ️ Статус"]], resize_keyboard=True)
    
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
            "daily_streak": 0,
            "total_earned": 0,
            "total_withdrawn": 0,
            "task_earned": 0,
            "referral_earned": 0,
            "bonus_earned": 0,
            "join_date": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
            "username": None,
            "first_name": "",
            "last_name": "",
            "level": 1,
            "experience": 0
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
    elif source == "bonus":
        user["bonus_earned"] += amount
    elif source == "cheque":
        db.global_stats["total_cheques_activated"] += 1
    
    db.global_stats["total_mcoins_earned"] += amount
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

def format_number(num: int) -> str:
    """Форматирует число с разделителями"""
    return f"{num:,}".replace(",", ".")

def generate_cheque_code() -> str:
    """Генерирует уникальный код для чека"""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
        if code not in db.cheques:
            return code

async def check_force_subs(user_id: int, bot) -> Tuple[bool, List[str]]:
    """Проверяет обязательные подписки пользователя"""
    not_subscribed = []
    
    # Проверяем каналы
    for channel in settings.force_sub_channels:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                not_subscribed.append(f"https://t.me/{channel.replace('@', '')}")
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

async def regular_tasks_mode(update: Update, context: CallbackContext):
    """Обычный режим заданий - получаем все ссылки сразу"""
    user_id = update.effective_user.id
    
    # Проверка бана
    if user_id in db.banned_users:
        await update.message.reply_text("⛔ Вы забанены и не можете выполнять задания!")
        return
    
    # Проверка обязательных подписок
    passed, not_passed = await check_force_subs(user_id, context.bot)
    if not passed:
        msg = "⚠️ **Для выполнения заданий необходимо подписаться:**\n\n"
        for item in not_passed:
            msg += f"• {item}\n"
        msg += "\nПосле подписки нажмите /tasks снова"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return
    
    msg = await update.message.reply_text("🔄 Получаем список заданий...")
    
    try:
        result = await call_botohub_api(user_id, is_task=False)
        
        tasks = result.get("tasks", [])
        completed = result.get("completed", False)
        skip_flag = result.get("skip", False)
        
        if skip_flag or not tasks:
            await msg.edit_text(
                "🎉 **Нет активных заданий!**\n\n"
                "Пожалуйста, зайдите позже.\n"
                "Новые задания появляются каждый день!"
            )
            return
        
        if completed:
            await msg.edit_text("✅ Вы выполнили все доступные задания!")
            task_reward = settings.task_reward
            add_mcoins(user_id, task_reward, "all_tasks_completed", "task")
            await update.message.reply_text(
                f"🎉 **Поздравляем!**\n\n"
                f"Вы выполнили все задания!\n"
                f"💰 Награда: {task_reward} {settings.currency_name}"
            )
            return
        
        # Отправляем все ссылки
        for idx, url in enumerate(tasks, 1):
            await update.message.reply_text(
                f"📌 **Задание {idx}/{len(tasks)}**\n\n"
                f"🔗 Ссылка: {url}\n\n"
                f"**Инструкция:**\n"
                f"1. Перейдите по ссылке\n"
                f"2. Подпишитесь на канал\n"
                f"3. Дождитесь награды (автоматически)\n\n"
                f"💰 Награда: {settings.task_reward} {settings.currency_name}",
                disable_web_page_preview=True
            )
        
        await update.message.reply_text(
            f"✅ **Все задания отправлены!**\n\n"
            f"💰 После выполнения всех заданий вы получите {settings.task_reward} {settings.currency_name}\n"
            f"📊 Статус можно проверить командой /check_tasks"
        )
        
    except Exception as e:
        logger.error(f"Ошибка в regular_tasks_mode: {e}")
        await msg.edit_text(f"❌ Ошибка: {e}\n\nПопробуйте позже.")

async def check_tasks_status(update: Update, context: CallbackContext):
    """Проверка статуса выполнения заданий"""
    user_id = update.effective_user.id
    
    msg = await update.message.reply_text("🔄 Проверяем выполнение заданий...")
    
    try:
        result = await call_botohub_api(user_id, is_task=False)
        
        tasks = result.get("tasks", [])
        completed = result.get("completed", False)
        
        if completed:
            task_reward = settings.task_reward
            # Проверяем, не получил ли уже награду
            if f"tasks_completed_{datetime.now().date()}" not in context.user_data:
                add_mcoins(user_id, task_reward, "tasks_check_completed", "task")
                context.user_data[f"tasks_completed_{datetime.now().date()}"] = True
                await msg.edit_text(
                    f"✅ **Поздравляем!**\n\n"
                    f"Вы выполнили все задания!\n"
                    f"💰 Получено: {task_reward} {settings.currency_name}\n\n"
                    f"💰 Ваш баланс: {format_number(get_user_data(user_id)['mcoin'])} {settings.currency_name}"
                )
            else:
                await msg.edit_text(
                    f"✅ **Все задания выполнены!**\n\n"
                    f"💰 Награда уже получена сегодня.\n"
                    f"💰 Ваш баланс: {format_number(get_user_data(user_id)['mcoin'])} {settings.currency_name}"
                )
        elif not tasks:
            await msg.edit_text(
                "🎉 **Нет активных заданий!**\n\n"
                "Пожалуйста, зайдите позже."
            )
        else:
            await msg.edit_text(
                f"⚠️ **Осталось невыполненных заданий:** {len(tasks)}\n\n"
                f"Выполните их и нажмите /check_tasks снова\n"
                f"💰 Награда: {settings.task_reward} {settings.currency_name}"
            )
            
    except Exception as e:
        logger.error(f"Ошибка в check_tasks_status: {e}")
        await msg.edit_text(f"❌ Ошибка: {e}")

# ========== ЧЕКОВАЯ СИСТЕМА ==========
async def cheques_menu(update: Update, context: CallbackContext):
    """Меню чеков"""
    keyboard = [
        [InlineKeyboardButton("🎁 Активировать чек", callback_data="activate_cheque")],
        [InlineKeyboardButton("📋 Мои чеки", callback_data="my_cheques")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    
    if update.effective_user.id in settings.admin_list:
        keyboard.insert(0, [InlineKeyboardButton("✨ Создать чек", callback_data="create_cheque")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎁 **Чековая система** 🎁\n\n"
        "Чеки - это специальные коды, которые можно активировать и получить MCoin.\n\n"
        "**Как использовать:**\n"
        "1. Получите код чека от администратора или в розыгрышах\n"
        "2. Нажмите «Активировать чек»\n"
        "3. Введите код\n"
        "4. Получите награду!\n\n"
        f"💰 Максимальная сумма чека: {settings.min_withdraw * 10} {settings.currency_name}",
        reply_markup=reply_markup
    )

async def create_cheque_start(update: Update, context: CallbackContext):
    """Начало создания чека"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in settings.admin_list:
        await query.message.edit_text("⛔ Только для администратора!")
        return
    
    await query.message.edit_text(
        "✨ **Создание чека** ✨\n\n"
        "Введите сумму чека (в MCoin):\n"
        f"Минимальная сумма: 1 {settings.currency_name}\n"
        f"Максимальная сумма: {settings.min_withdraw * 10} {settings.currency_name}"
    )
    return CREATE_CHEQUE_AMOUNT

async def create_cheque_amount(update: Update, context: CallbackContext):
    """Получение суммы чека"""
    try:
        amount = int(update.message.text)
        if amount < 1 or amount > settings.min_withdraw * 10:
            await update.message.reply_text(
                f"❌ Сумма должна быть от 1 до {settings.min_withdraw * 10} {settings.currency_name}"
            )
            return CREATE_CHEQUE_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число!")
        return CREATE_CHEQUE_AMOUNT
    
    # Генерируем код чека
    code = generate_cheque_code()
    
    db.cheques[code] = {
        "amount": amount,
        "creator": update.effective_user.id,
        "created_date": datetime.now().isoformat(),
        "activated_by": None,
        "is_activated": False,
        "activation_date": None
    }
    db.global_stats["total_cheques_created"] += 1
    db.save()
    
    await update.message.reply_text(
        f"✅ **Чек создан!**\n\n"
        f"💰 Сумма: {amount} {settings.currency_name}\n"
        f"🎫 Код: `{code}`\n\n"
        f"Отправьте этот код пользователю для активации.\n"
        f"Чек можно активировать только один раз.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def activate_cheque_start(update: Update, context: CallbackContext):
    """Начало активации чека"""
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        "🎁 **Активация чека** 🎁\n\n"
        "Введите код чека:"
    )
    return CREATE_CHEQUE_AMOUNT  # Переиспользуем состояние

async def activate_cheque_process(update: Update, context: CallbackContext):
    """Активация чека"""
    user_id = update.effective_user.id
    code = update.message.text.upper().strip()
    
    if code not in db.cheques:
        await update.message.reply_text("❌ Неверный код чека!")
        return ConversationHandler.END
    
    cheque = db.cheques[code]
    
    if cheque["is_activated"]:
        await update.message.reply_text("❌ Этот чек уже был активирован!")
        return ConversationHandler.END
    
    # Активируем чек
    amount = cheque["amount"]
    add_mcoins(user_id, amount, f"cheque_{code}", "cheque")
    
    cheque["is_activated"] = True
    cheque["activated_by"] = user_id
    cheque["activation_date"] = datetime.now().isoformat()
    db.save()
    
    await update.message.reply_text(
        f"✅ **Чек активирован!**\n\n"
        f"💰 Вы получили: {amount} {settings.currency_name}\n"
        f"💰 Ваш баланс: {format_number(get_user_data(user_id)['mcoin'])} {settings.currency_name}\n\n"
        f"🎉 Спасибо за использование бота!"
    )
    return ConversationHandler.END

async def my_cheques(update: Update, context: CallbackContext):
    """Показывает активированные чеки пользователя"""
    query = update.callback_query
    user_id = query.from_user.id
    
    activated_cheques = []
    for code, cheque in db.cheques.items():
        if cheque.get("activated_by") == user_id:
            activated_cheques.append(
                f"• {code} - {cheque['amount']} {settings.currency_name} (активирован {cheque['activation_date'][:10]})"
            )
    
    if not activated_cheques:
        await query.message.edit_text(
            "📋 **Ваши чеки**\n\n"
            "У вас пока нет активированных чеков.\n"
            "Получите код у администратора или участвуйте в розыгрышах!"
        )
    else:
        text = "📋 **Ваши активированные чеки:**\n\n" + "\n".join(activated_cheques)
        await query.message.edit_text(text)

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
    
    # Расчет уровня реферала
    ref_count = len(user["referrals"])
    level = 1
    if ref_count >= 50:
        level = 5
    elif ref_count >= 25:
        level = 4
    elif ref_count >= 10:
        level = 3
    elif ref_count >= 5:
        level = 2
    
    level_bonus = level * 0.05  # 5% бонус за уровень
    
    keyboard = [
        [InlineKeyboardButton("📋 Список рефералов", callback_data="my_referrals_list")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👥 **Реферальная программа** 👥\n\n"
        f"Приглашайте друзей и зарабатывайте!\n\n"
        f"🏆 **Ваш уровень:** {level}\n"
        f"📈 **Бонус к награде:** +{int(level_bonus * 100)}%\n"
        f"👥 **Рефералов:** {ref_count}\n"
        f"💰 **Заработано с рефералов:** {user['referral_earned']} {settings.currency_name}\n\n"
        f"🎁 **Награда за реферала:** {settings.referral_reward} {settings.currency_name}\n\n"
        f"**Как это работает:**\n"
        f"1. Отправьте ссылку другу\n"
        f"2. Друг регистрируется в боте\n"
        f"3. Вы получаете награду!\n\n"
        f"🔗 **Ваша реферальная ссылка:**\n`{ref_link}`\n\n"
        f"Чем больше друзей, тем выше ваш уровень и бонусы!",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def my_referrals_list(update: Update, context: CallbackContext):
    """Показывает список рефералов"""
    query = update.callback_query
    user_id = query.from_user.id
    user = get_user_data(user_id)
    
    if not user["referrals"]:
        await query.answer("У вас пока нет рефералов!", show_alert=True)
        return
    
    referrals_text = "📋 **Ваши рефералы:**\n\n"
    for i, ref_id in enumerate(user["referrals"], 1):
        ref_user = db.users.get(ref_id, {})
        ref_name = ref_user.get("first_name", f"User_{ref_id}")
        ref_earned = ref_user.get("total_earned", 0)
        referrals_text += f"{i}. {ref_name} - заработал: {ref_earned} {settings.currency_name}\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="referrals_back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(referrals_text, reply_markup=reply_markup)

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
        else:
            user["daily_streak"] = 1
    
    # Рассчитываем бонус
    base_reward = settings.daily_reward
    streak_multiplier = 1 + (user["daily_streak"] * 0.05)
    reward = int(base_reward * min(streak_multiplier, 2.0))
    
    add_mcoins(user_id, reward, "daily_bonus", "bonus")
    user["daily_last"] = now.isoformat()
    db.save()
    
    await update.message.reply_text(
        f"🎁 **Ежедневный бонус!** 🎁\n\n"
        f"💰 Вы получили: {reward} {settings.currency_name}\n"
        f"📊 Серия: {user['daily_streak']} дней\n"
        f"📈 Множитель: x{streak_multiplier:.2f}\n\n"
        f"💰 Ваш баланс: {format_number(user['mcoin'])} {settings.currency_name}\n\n"
        f"✨ Заходите завтра, чтобы продолжить серию!"
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
            f"💰 Минимальная сумма: {settings.min_withdraw} {settings.currency_name}\n\n"
            f"Выполняйте задания и приглашайте друзей, чтобы заработать больше!"
        )
        return
    
    keyboard = [
        [InlineKeyboardButton("💰 Запросить вывод", callback_data="request_withdraw")],
        [InlineKeyboardButton("📊 История выводов", callback_data="withdraw_history")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="withdraw_info")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"💸 **Вывод средств** 💸\n\n"
        f"💰 Доступно: {format_number(user['mcoin'])} {settings.currency_name}\n"
        f"📉 Минимальная сумма: {settings.min_withdraw} {settings.currency_name}\n\n"
        f"💳 **Доступные способы вывода:**\n"
        f"• QIWI\n"
        f"• Банковская карта\n"
        f"• Криптовалюта\n\n"
        f"⏱️ Время обработки: до 24 часов\n"
        f"💰 Комиссия: 0%\n\n"
        f"Нажмите «Запросить вывод» для создания заявки",
        reply_markup=reply_markup
    )

async def request_withdraw_start(update: Update, context: CallbackContext):
    """Начало запроса на вывод"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = get_user_data(user_id)
    
    await query.message.edit_text(
        f"💸 **Запрос на вывод** 💸\n\n"
        f"💰 Доступно: {format_number(user['mcoin'])} {settings.currency_name}\n"
        f"📉 Минимальная сумма: {settings.min_withdraw} {settings.currency_name}\n\n"
        f"Введите сумму вывода:"
    )
    return PROCESS_WITHDRAW

async def request_withdraw_amount(update: Update, context: CallbackContext):
    """Обработка суммы вывода"""
    user_id = update.effective_user.id
    
    try:
        amount = int(update.message.text)
        if amount < settings.min_withdraw:
            await update.message.reply_text(f"❌ Минимальная сумма вывода: {settings.min_withdraw} {settings.currency_name}")
            return PROCESS_WITHDRAW
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число!")
        return PROCESS_WITHDRAW
    
    user = get_user_data(user_id)
    if user["mcoin"] < amount:
        await update.message.reply_text(f"❌ Недостаточно средств! Доступно: {user['mcoin']} {settings.currency_name}")
        return PROCESS_WITHDRAW
    
    # Сохраняем заявку
    if user_id not in db.withdraw_requests:
        db.withdraw_requests[user_id] = []
    
    request_id = len(db.withdraw_requests[user_id]) + 1
    db.withdraw_requests[user_id].append({
        "id": request_id,
        "amount": amount,
        "status": "pending",
        "created_date": datetime.now().isoformat(),
        "processed_date": None
    })
    db.save()
    
    # Уведомляем админа
    await update.message.bot.send_message(
        ADMIN_ID,
        f"💸 **Новая заявка на вывод!**\n\n"
        f"👤 Пользователь: {update.effective_user.first_name}\n"
        f"🆔 ID: {user_id}\n"
        f"💰 Сумма: {amount} {settings.currency_name}\n"
        f"📅 Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"Для обработки используйте админ-панель."
    )
    
    await update.message.reply_text(
        f"✅ **Заявка на вывод создана!**\n\n"
        f"💰 Сумма: {amount} {settings.currency_name}\n"
        f"🆔 Номер заявки: {request_id}\n\n"
        f"⏱️ Заявка будет обработана в течение 24 часов.\n"
        f"Статус заявки можно проверить в истории выводов."
    )
    return ConversationHandler.END

async def withdraw_history(update: Update, context: CallbackContext):
    """История выводов пользователя"""
    query = update.callback_query
    user_id = query.from_user.id
    
    requests = db.withdraw_requests.get(user_id, [])
    
    if not requests:
        await query.message.edit_text(
            "📊 **История выводов**\n\n"
            "У вас пока нет заявок на вывод."
        )
        return
    
    history_text = "📊 **История выводов:**\n\n"
    for req in requests:
        status_emoji = "✅" if req["status"] == "completed" else "⏳" if req["status"] == "pending" else "❌"
        history_text += f"{status_emoji} Заявка #{req['id']}: {req['amount']} {settings.currency_name} - {req['status']}\n"
        if req.get("processed_date"):
            history_text += f"   Обработана: {req['processed_date'][:10]}\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="withdraw_back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(history_text, reply_markup=reply_markup)

async def withdraw_info(update: Update, context: CallbackContext):
    """Информация о выводе"""
    query = update.callback_query
    
    await query.message.edit_text(
        f"ℹ️ **Информация о выводе средств** ℹ️\n\n"
        f"**Как вывести средства:**\n"
        f"1. Накопите минимум {settings.min_withdraw} {settings.currency_name}\n"
        f"2. Нажмите «Запросить вывод»\n"
        f"3. Укажите сумму и реквизиты\n"
        f"4. Ожидайте обработки заявки\n\n"
        f"**Способы вывода:**\n"
        f"• QIWI - комиссия 0%\n"
        f"• Банковская карта - комиссия 0%\n"
        f"• Криптовалюта - комиссия 0%\n\n"
        f"**Сроки:**\n"
        f"• Обработка заявки: до 24 часов\n"
        f"• Поступление средств: от 5 минут до 3 дней\n\n"
        f"**Важно:**\n"
        f"• Вывод возможен только на ваши реквизиты\n"
        f"• Мошенничество приводит к бану\n"
        f"• По всем вопросам: @admin",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="withdraw_back")]])
    )

# ========== ПРОМОКОДЫ ==========
async def promo_menu(update: Update, context: CallbackContext):
    """Меню промокодов"""
    await update.message.reply_text(
        "🎫 **Промокоды** 🎫\n\n"
        "Активируйте промокод и получите бонусные MCoin!\n\n"
        "**Как использовать:**\n"
        "1. Получите промокод от администратора\n"
        "2. Введите команду /promo <код>\n"
        "3. Получите награду!\n\n"
        "**Пример:**\n"
        "/promo WELCOME100\n\n"
        "📢 Следите за новостями, чтобы не пропустить новые промокоды!"
    )

async def use_promo(update: Update, context: CallbackContext):
    """Использование промокода"""
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "🎫 **Использование промокода**\n\n"
            "Напишите: /promo <код>\n"
            "Пример: /promo WELCOME100"
        )
        return
    
    code = args[0].upper()
    
    if code not in db.promo_codes:
        await update.message.reply_text("❌ Неверный или недействительный промокод!")
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
    add_mcoins(user_id, reward, f"promo_{code}", "bonus")
    
    # Обновляем промокод
    if "used_by" not in promo:
        promo["used_by"] = []
    promo["used_by"].append(user_id)
    db.save()
    
    await update.message.reply_text(
        f"✅ **Промокод активирован!**\n\n"
        f"🎉 Вы получили: {reward} {settings.currency_name}\n"
        f"💰 Ваш баланс: {format_number(get_user_data(user_id)['mcoin'])} {settings.currency_name}\n\n"
        f"Спасибо за использование промокода!"
    )

# ========== СТАТИСТИКА ==========
async def stats_menu(update: Update, context: CallbackContext):
    """Показывает статистику пользователя"""
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    level = user["level"]
    exp = user["experience"]
    next_exp = level * 100
    
    stats_text = (
        f"📊 **Ваша статистика** 📊\n\n"
        f"💰 Баланс: {format_number(user['mcoin'])} {settings.currency_name}\n"
        f"📈 Всего заработано: {format_number(user['total_earned'])} {settings.currency_name}\n"
        f"💸 Выведено: {format_number(user['total_withdrawn'])} {settings.currency_name}\n\n"
        f"📋 Выполнено заданий: {len(user['tasks_completed'])}\n"
        f"👥 Приглашено друзей: {len(user['referrals'])}\n"
        f"🔥 Ежедневная серия: {user['daily_streak']} дней\n\n"
        f"🏆 Уровень: {level}\n"
        f"📊 Опыт: {exp}/{next_exp}\n\n"
        f"📅 В боте с: {user['join_date'][:10]}"
    )
    
    # Глобальная статистика
    stats_text += (
        f"\n\n🌍 **Глобальная статистика** 🌍\n\n"
        f"👥 Всего пользователей: {db.global_stats['total_users']}\n"
        f"💰 Всего заработано: {format_number(db.global_stats['total_mcoins_earned'])} {settings.currency_name}\n"
        f"💸 Всего выведено: {format_number(db.global_stats['total_withdrawn'])} {settings.currency_name}\n"
        f"✅ Заданий выполнено: {db.global_stats['total_tasks_completed']}\n"
        f"🎁 Чеков создано: {db.global_stats['total_cheques_created']}\n"
        f"🎁 Чеков активировано: {db.global_stats['total_cheques_activated']}"
    )
    
    await update.message.reply_text(stats_text, parse_mode="Markdown")

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
async def start(update: Update, context: CallbackContext):
    """Обработка команды /start"""
    user_id = update.effective_user.id
    
    # Проверка бана
    if user_id in db.banned_users:
        ban_info = db.banned_users[user_id]
        await update.message.reply_text(
            f"⛔ **Вы забанены!** ⛔\n\n"
            f"Причина: {ban_info.get('reason', 'Нарушение правил')}\n"
            f"Дата: {ban_info.get('date', 'Неизвестно')[:10]}"
        )
        return
    
    # Обработка реферальной ссылки
    if context.args and context.args[0].startswith("ref_"):
        referrer_id = int(context.args[0].replace("ref_", ""))
        if referrer_id != user_id and referrer_id not in db.banned_users:
            user_data = get_user_data(user_id)
            if not user_data.get("referrer"):
                user_data["referrer"] = referrer_id
                referrer_data = get_user_data(referrer_id)
                
                if user_id not in referrer_data["referrals"]:
                    referrer_data["referrals"].append(user_id)
                    
                    # Начисляем бонус с учетом уровня
                    ref_count = len(referrer_data["referrals"])
                    level_bonus = 1 + (min(ref_count // 5, 5) * 0.05)
                    ref_reward = int(settings.referral_reward * level_bonus)
                    
                    add_mcoins(referrer_id, ref_reward, f"referral_{user_id}", "referral")
                    db.save()
                    
                    try:
                        await context.bot.send_message(
                            referrer_id,
                            f"👥 **Новый реферал!**\n\n"
                            f"{update.effective_user.first_name} присоединился по вашей ссылке!\n"
                            f"💰 Вы получили: {ref_reward} {settings.currency_name}\n"
                            f"📊 Всего рефералов: {len(referrer_data['referrals'])}\n"
                            f"📈 Бонус: x{level_bonus:.2f}"
                        )
                    except Exception as e:
                        logger.error(f"Не удалось отправить сообщение рефереру: {e}")
    
    get_user_data(user_id)
    
    # Проверка обязательных подписок при старте
    passed, not_passed = await check_force_subs(user_id, context.bot)
    sub_msg = ""
    if not passed:
        sub_msg = "\n\n⚠️ **Важно:** Для работы бота подпишитесь на наши каналы:\n"
        for item in not_passed:
            sub_msg += f"• {item}\n"
    
    welcome_text = (
        f"👋 **Привет, {update.effective_user.first_name}!**\n\n"
        f"{settings.welcome_message}\n\n"
        f"💎 **{settings.bot_name}**\n\n"
        f"✨ **Что вы можете делать:**\n"
        f"• 📋 Выполнять задания и получать {settings.currency_name}\n"
        f"• 👥 Приглашать друзей и получать бонусы\n"
        f"• 🎁 Активировать чеки и промокоды\n"
        f"• 💸 Выводить заработанные средства\n\n"
        f"💰 Ваш баланс: 0 {settings.currency_name}{sub_msg}\n\n"
        f"🌟 **Удачного заработка!** 🌟"
    )
    
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")

async def balance_handler(update: Update, context: CallbackContext):
    """Показывает баланс"""
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    await update.message.reply_text(
        f"💰 **Ваш баланс** 💰\n\n"
        f"🎮 {settings.currency_name}: `{format_number(user['mcoin'])}`\n\n"
        f"📈 **Статистика заработка:**\n"
        f"📋 С заданий: {format_number(user['task_earned'])}\n"
        f"👥 С рефералов: {format_number(user['referral_earned'])}\n"
        f"🎁 С бонусов: {format_number(user['bonus_earned'])}\n\n"
        f"💰 Всего заработано: {format_number(user['total_earned'])}\n"
        f"💸 Выведено: {format_number(user['total_withdrawn'])}",
        parse_mode="Markdown"
    )

async def handle_text(update: Update, context: CallbackContext):
    """Обработка текстовых сообщений от кнопок"""
    user_id = update.effective_user.id
    text = update.message.text
    
    # Проверка бана
    if user_id in db.banned_users:
        await update.message.reply_text("⛔ Вы забанены и не можете использовать бота!")
        return
    
    # Обновляем время последней активности
    if user_id in db.users:
        db.users[user_id]["last_seen"] = datetime.now().isoformat()
        db.users[user_id]["username"] = update.effective_user.username
        db.users[user_id]["first_name"] = update.effective_user.first_name
        db.save()
    
    if text == f"💰 {settings.currency_name}":
        await balance_handler(update, context)
    elif text == "📋 Задания":
        await regular_tasks_mode(update, context)
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
    elif text == "🎁 Чеки":
        await cheques_menu(update, context)
    elif text == "⚙️ Админ панель" and user_id in settings.admin_list:
        await admin_panel(update, context)
    else:
        await update.message.reply_text(
            "❓ **Неизвестная команда**\n\n"
            "Используйте кнопки меню для навигации 👇",
            reply_markup=get_main_keyboard(user_id)
        )

# ========== АДМИН ПАНЕЛЬ (ПОЛНОСТЬЮ РЕАЛИЗОВАНА) ==========
async def admin_panel(update: Update, context: CallbackContext):
    """Главное меню админ панели"""
    if update.effective_user.id not in settings.admin_list:
        await update.message.reply_text("⛔ У вас нет доступа к админ панели!")
        return
    
    keyboard = [
        [InlineKeyboardButton("💰 Настройка наград", callback_data="admin_rewards")],
        [InlineKeyboardButton("📢 Обязательные подписки", callback_data="admin_forcesub")],
        [InlineKeyboardButton("👥 Управление пользователями", callback_data="admin_users")],
        [InlineKeyboardButton("💸 Управление выводами", callback_data="admin_withdrawals")],
        [InlineKeyboardButton("🎫 Промокоды", callback_data="admin_promo")],
        [InlineKeyboardButton("📨 Рассылка", callback_data="admin_mailing")],
        [InlineKeyboardButton("📊 Статистика бота", callback_data="admin_stats")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "⚙️ **Админ панель**\n\n"
        f"📊 **Быстрая статистика:**\n"
        f"👥 Пользователей: {db.global_stats['total_users']}\n"
        f"💰 Всего заработано: {format_number(db.global_stats['total_mcoins_earned'])} {settings.currency_name}\n"
        f"✅ Заданий выполнено: {db.global_stats['total_tasks_completed']}\n"
        f"💸 Заявок на вывод: {sum(len(reqs) for reqs in db.withdraw_requests.values())}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

# Настройка наград
async def admin_rewards_menu(update: Update, context: CallbackContext):
    """Меню настройки наград"""
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
        "💰 **Настройка наград**\n\n"
        "Выберите параметр для изменения:",
        reply_markup=reply_markup
    )

async def set_task_reward_start(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("Введите новую награду за задание (в MCoin):")
    return SET_TASK_REWARD

async def set_task_reward_value(update: Update, context: CallbackContext):
    try:
        value = int(update.message.text)
        if value < 1:
            await update.message.reply_text("❌ Значение должно быть больше 0!")
            return SET_TASK_REWARD
        settings.task_reward = value
        settings.save()
        await update.message.reply_text(f"✅ Награда за задание установлена: {value} {settings.currency_name}")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число!")
        return SET_TASK_REWARD

async def set_ref_reward_start(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("Введите новую награду за реферала (в MCoin):")
    return SET_REF_REWARD

async def set_ref_reward_value(update: Update, context: CallbackContext):
    try:
        value = int(update.message.text)
        if value < 1:
            await update.message.reply_text("❌ Значение должно быть больше 0!")
            return SET_REF_REWARD
        settings.referral_reward = value
        settings.save()
        await update.message.reply_text(f"✅ Награда за реферала установлена: {value} {settings.currency_name}")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число!")
        return SET_REF_REWARD

async def set_daily_reward_start(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("Введите новую ежедневную награду (в MCoin):")
    return SET_DAILY_REWARD

async def set_daily_reward_value(update: Update, context: CallbackContext):
    try:
        value = int(update.message.text)
        if value < 1:
            await update.message.reply_text("❌ Значение должно быть больше 0!")
            return SET_DAILY_REWARD
        settings.daily_reward = value
        settings.save()
        await update.message.reply_text(f"✅ Ежедневная награда установлена: {value} {settings.currency_name}")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число!")
        return SET_DAILY_REWARD

async def set_min_withdraw_start(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("Введите минимальную сумму вывода (в MCoin):")
    return SET_MIN_WITHDRAW

async def set_min_withdraw_value(update: Update, context: CallbackContext):
    try:
        value = int(update.message.text)
        if value < 10:
            await update.message.reply_text("❌ Минимальная сумма вывода не может быть меньше 10!")
            return SET_MIN_WITHDRAW
        settings.min_withdraw = value
        settings.save()
        await update.message.reply_text(f"✅ Минимальная сумма вывода установлена: {value} {settings.currency_name}")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число!")
        return SET_MIN_WITHDRAW

# Обязательные подписки
async def admin_forcesub_menu(update: Update, context: CallbackContext):
    """Меню обязательных подписок"""
    query = update.callback_query
    await query.answer()
    
    channels_text = "\n".join([f"• {ch}" for ch in settings.force_sub_channels]) if settings.force_sub_channels else "Нет"
    groups_text = "\n".join([f"• {gr}" for gr in settings.force_sub_groups]) if settings.force_sub_groups else "Нет"
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить канал", callback_data="add_force_channel")],
        [InlineKeyboardButton("➖ Удалить канал", callback_data="remove_force_channel")],
        [InlineKeyboardButton("➕ Добавить группу", callback_data="add_force_group")],
        [InlineKeyboardButton("➖ Удалить группу", callback_data="remove_force_group")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "📢 **Обязательные подписки**\n\n"
        f"**Каналы:**\n{channels_text}\n\n"
        f"**Группы:**\n{groups_text}\n\n"
        "Пользователи должны быть подписаны на эти ресурсы для выполнения заданий.\n\n"
        "Вводите ID канала/группы (например, @channel или -100123456789):",
        reply_markup=reply_markup
    )

async def add_force_channel_start(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("Введите ID или username канала (например, @channel или -100123456789):")
    return SET_FORCE_CHANNEL

async def add_force_channel_value(update: Update, context: CallbackContext):
    channel = update.message.text.strip()
    if channel not in settings.force_sub_channels:
        settings.force_sub_channels.append(channel)
        settings.save()
        await update.message.reply_text(f"✅ Канал {channel} добавлен в обязательные подписки!")
    else:
        await update.message.reply_text(f"❌ Канал {channel} уже в списке!")
    return ConversationHandler.END

async def remove_force_channel_start(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if not settings.force_sub_channels:
        await query.message.edit_text("❌ Нет каналов для удаления!")
        return ConversationHandler.END
    
    keyboard = [[InlineKeyboardButton(ch, callback_data=f"remove_ch_{ch}")] for ch in settings.force_sub_channels]
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_forcesub")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text("Выберите канал для удаления:", reply_markup=reply_markup)
    return REMOVE_FORCE_CHANNEL

async def remove_force_channel_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    channel = query.data.replace("remove_ch_", "")
    
    if channel in settings.force_sub_channels:
        settings.force_sub_channels.remove(channel)
        settings.save()
        await query.answer(f"Канал {channel} удален!")
        await admin_forcesub_menu(update, context)
    else:
        await query.answer("Канал не найден!")
    return ConversationHandler.END

# Управление пользователями
async def admin_users_menu(update: Update, context: CallbackContext):
    """Меню управления пользователями"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить MCoin", callback_data="add_balance")],
        [InlineKeyboardButton("➖ Забрать MCoin", callback_data="remove_balance")],
        [InlineKeyboardButton("⛔ Забанить пользователя", callback_data="ban_user")],
        [InlineKeyboardButton("✅ Разбанить пользователя", callback_data="unban_user")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "👥 **Управление пользователями**\n\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )

async def add_balance_start(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("Введите ID пользователя:")
    return ADD_BALANCE_USER

async def add_balance_user_id(update: Update, context: CallbackContext):
    try:
        user_id = int(update.message.text)
        context.user_data["target_user"] = user_id
        await update.message.reply_text(f"Пользователь {user_id}\nВведите сумму для начисления:")
        return ADD_BALANCE_USER
    except ValueError:
        await update.message.reply_text("❌ Введите корректный ID!")
        return ADD_BALANCE_USER

async def add_balance_amount(update: Update, context: CallbackContext):
    try:
        amount = int(update.message.text)
        user_id = context.user_data["target_user"]
        
        if user_id not in db.users:
            await update.message.reply_text("❌ Пользователь не найден!")
            return ConversationHandler.END
        
        add_mcoins(user_id, amount, f"admin_add", "bonus")
        await update.message.reply_text(f"✅ Пользователю {user_id} начислено {amount} {settings.currency_name}")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Введите корректную сумму!")
        return ADD_BALANCE_USER

async def ban_user_start(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("Введите ID пользователя для бана:")
    return BAN_USER

async def ban_user_id(update: Update, context: CallbackContext):
    try:
        user_id = int(update.message.text)
        if user_id in settings.admin_list:
            await update.message.reply_text("❌ Нельзя забанить администратора!")
            return ConversationHandler.END
        
        db.banned_users[user_id] = {
            "reason": "Нарушение правил",
            "date": datetime.now().isoformat(),
            "admin": update.effective_user.id
        }
        db.save()
        
        await update.message.reply_text(f"✅ Пользователь {user_id} забанен!")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Введите корректный ID!")
        return BAN_USER

async def unban_user_start(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("Введите ID пользователя для разбана:")
    return UNBAN_USER

async def unban_user_id(update: Update, context: CallbackContext):
    try:
        user_id = int(update.message.text)
        if user_id in db.banned_users:
            del db.banned_users[user_id]
            db.save()
            await update.message.reply_text(f"✅ Пользователь {user_id} разбанен!")
        else:
            await update.message.reply_text("❌ Пользователь не найден в бане!")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Введите корректный ID!")
        return UNBAN_USER

# Управление выводами
async def admin_withdrawals_menu(update: Update, context: CallbackContext):
    """Меню управления выводами"""
    query = update.callback_query
    await query.answer()
    
    pending_requests = []
    for user_id, requests in db.withdraw_requests.items():
        for req in requests:
            if req["status"] == "pending":
                pending_requests.append(f"ID: {user_id}, #{req['id']}, {req['amount']} {settings.currency_name}")
    
    pending_text = "\n".join(pending_requests) if pending_requests else "Нет заявок"
    
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить вывод", callback_data="process_withdraw")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "💸 **Управление выводами**\n\n"
        f"**Ожидают обработки:**\n{pending_text}\n\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )

async def process_withdraw_start(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("Введите ID пользователя и номер заявки (формат: user_id request_id):")
    return PROCESS_WITHDRAW

async def process_withdraw_value(update: Update, context: CallbackContext):
    try:
        parts = update.message.text.split()
        user_id = int(parts[0])
        request_id = int(parts[1])
        
        if user_id not in db.withdraw_requests:
            await update.message.reply_text("❌ Заявка не найдена!")
            return ConversationHandler.END
        
        for req in db.withdraw_requests[user_id]:
            if req["id"] == request_id and req["status"] == "pending":
                req["status"] = "completed"
                req["processed_date"] = datetime.now().isoformat()
                
                user_data = get_user_data(user_id)
                user_data["total_withdrawn"] += req["amount"]
                remove_mcoins(user_id, req["amount"], f"withdraw_{request_id}")
                db.global_stats["total_withdrawn"] += req["amount"]
                db.save()
                
                await update.message.reply_text(f"✅ Вывод подтвержден! Пользователь {user_id}, сумма {req['amount']} {settings.currency_name}")
                
                # Уведомляем пользователя
                try:
                    await update.message.bot.send_message(
                        user_id,
                        f"✅ **Ваша заявка на вывод выполнена!**\n\n"
                        f"💰 Сумма: {req['amount']} {settings.currency_name}\n"
                        f"📅 Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                        f"Средства отправлены на указанные реквизиты."
                    )
                except:
                    pass
                
                return ConversationHandler.END
        
        await update.message.reply_text("❌ Заявка не найдена или уже обработана!")
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Неверный формат! Используйте: user_id request_id")
        return PROCESS_WITHDRAW

# Промокоды
async def admin_promo_menu(update: Update, context: CallbackContext):
    """Меню управления промокодами"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("✨ Создать промокод", callback_data="create_promo")],
        [InlineKeyboardButton("📋 Список промокодов", callback_data="list_promo")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "🎫 **Управление промокодами**\n\n"
        "Создавайте промокоды для выдачи бонусов пользователям.\n\n"
        "Промокод можно использовать ограниченное количество раз.",
        reply_markup=reply_markup
    )

async def create_promo_start(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("Введите название промокода (латиницей, без пробелов):")
    return ADMIN_PROMO_NAME

async def create_promo_name(update: Update, context: CallbackContext):
    name = update.message.text.upper().strip()
    if name in db.promo_codes:
        await update.message.reply_text("❌ Промокод с таким названием уже существует!")
        return ADMIN_PROMO_NAME
    
    context.user_data["promo_name"] = name
    await update.message.reply_text("Введите сумму награды (в MCoin):")
    return ADMIN_PROMO_REWARD

async def create_promo_reward(update: Update, context: CallbackContext):
    try:
        reward = int(update.message.text)
        context.user_data["promo_reward"] = reward
        await update.message.reply_text("Введите максимальное количество использований (1-1000):")
        return ADMIN_PROMO_USES
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число!")
        return ADMIN_PROMO_REWARD

async def create_promo_uses(update: Update, context: CallbackContext):
    try:
        uses = int(update.message.text)
        context.user_data["promo_uses"] = uses
        await update.message.reply_text("Введите дату окончания (ГГГГ-ММ-ДД) или 0 если без срока:")
        return ADMIN_PROMO_EXPIRY
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число!")
        return ADMIN_PROMO_USES

async def create_promo_expiry(update: Update, context: CallbackContext):
    expiry = update.message.text.strip()
    
    if expiry == "0":
        expiry_date = None
    else:
        try:
            expiry_date = datetime.strptime(expiry, "%Y-%m-%d").isoformat()
        except:
            await update.message.reply_text("❌ Неверный формат даты! Используйте ГГГГ-ММ-ДД")
            return ADMIN_PROMO_EXPIRY
    
    db.promo_codes[context.user_data["promo_name"]] = {
        "reward": context.user_data["promo_reward"],
        "max_uses": context.user_data["promo_uses"],
        "expiry": expiry_date,
        "used_by": [],
        "created_by": update.effective_user.id,
        "created_date": datetime.now().isoformat()
    }
    db.save()
    
    await update.message.reply_text(
        f"✅ **Промокод создан!**\n\n"
        f"🎫 Код: `{context.user_data['promo_name']}`\n"
        f"💰 Награда: {context.user_data['promo_reward']} {settings.currency_name}\n"
        f"📊 Использований: {context.user_data['promo_uses']}\n"
        f"📅 Действителен до: {expiry if expiry != '0' else 'Бессрочно'}\n\n"
        f"Пользователи могут активировать его командой /promo {context.user_data['promo_name']}",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def list_promo(update: Update, context: CallbackContext):
    """Список промокодов"""
    query = update.callback_query
    
    if not db.promo_codes:
        await query.message.edit_text("📋 Нет созданных промокодов.")
        return
    
    promo_list = "📋 **Список промокодов:**\n\n"
    for code, data in db.promo_codes.items():
        expiry = data.get("expiry", "Бессрочно")
        if expiry != "Бессрочно":
            expiry = expiry[:10]
        used = len(data.get("used_by", []))
        promo_list += f"• `{code}` - {data['reward']} {settings.currency_name} (использовано: {used}/{data['max_uses']}, до: {expiry})\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_promo")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(promo_list, reply_markup=reply_markup, parse_mode="Markdown")

# Рассылка
async def admin_mailing_start(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("Введите текст рассылки (поддерживается Markdown):")
    return ADMIN_MAILING

async def admin_mailing_send(update: Update, context: CallbackContext):
    text = update.message.text
    msg = await update.message.reply_text("🔄 Отправка рассылки...")
    
    success = 0
    fail = 0
    
    for user_id in db.users.keys():
        try:
            await update.message.bot.send_message(user_id, text, parse_mode="Markdown")
            success += 1
            await asyncio.sleep(0.05)  # Чтобы не превысить лимиты
        except:
            fail += 1
    
    await msg.edit_text(
        f"✅ **Рассылка завершена!**\n\n"
        f"📨 Отправлено: {success}\n"
        f"❌ Ошибок: {fail}\n"
        f"👥 Всего пользователей: {len(db.users)}"
    )
    return ConversationHandler.END

# Статистика
async def admin_stats(update: Update, context: CallbackContext):
    """Показывает подробную статистику"""
    query = update.callback_query
    await query.answer()
    
    # Подсчет активных пользователей за последние 7 дней
    active_users = 0
    week_ago = datetime.now() - timedelta(days=7)
    
    for user in db.users.values():
        if user.get("last_seen"):
            last_seen = datetime.fromisoformat(user["last_seen"])
            if last_seen > week_ago:
                active_users += 1
    
    stats_text = (
        "📊 **Детальная статистика бота**\n\n"
        f"👥 **Пользователи:**\n"
        f"• Всего: {db.global_stats['total_users']}\n"
        f"• Активных за 7 дней: {active_users}\n"
        f"• В бане: {len(db.banned_users)}\n\n"
        f"💰 **Финансы:**\n"
        f"• Всего заработано: {format_number(db.global_stats['total_mcoins_earned'])} {settings.currency_name}\n"
        f"• Выведено: {format_number(db.global_stats['total_withdrawn'])} {settings.currency_name}\n"
        f"• В обороте: {format_number(db.global_stats['total_mcoins_earned'] - db.global_stats['total_withdrawn'])} {settings.currency_name}\n\n"
        f"📋 **Задания:**\n"
        f"• Выполнено: {db.global_stats['total_tasks_completed']}\n"
        f"• Награда за задание: {settings.task_reward} {settings.currency_name}\n\n"
        f"🎁 **Чеки:**\n"
        f"• Создано: {db.global_stats['total_cheques_created']}\n"
        f"• Активировано: {db.global_stats['total_cheques_activated']}\n\n"
        f"👥 **Рефералы:**\n"
        f"• Награда: {settings.referral_reward} {settings.currency_name}\n"
        f"• Реферальная программа: {'Активна' if settings.referral_program else 'Отключена'}"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(stats_text, reply_markup=reply_markup)

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
    app.add_handler(CommandHandler("tasks", regular_tasks_mode))
    app.add_handler(CommandHandler("check_tasks", check_tasks_status))
    app.add_handler(CommandHandler("promo", use_promo))
    
    # Регистрируем обработчики админ-панели (ConversationHandlers)
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(set_task_reward_start, pattern="^set_task_reward$")],
        states={SET_TASK_REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_task_reward_value)]},
        fallbacks=[]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(set_ref_reward_start, pattern="^set_ref_reward$")],
        states={SET_REF_REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_ref_reward_value)]},
        fallbacks=[]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(set_daily_reward_start, pattern="^set_daily_reward$")],
        states={SET_DAILY_REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_daily_reward_value)]},
        fallbacks=[]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(set_min_withdraw_start, pattern="^set_min_withdraw$")],
        states={SET_MIN_WITHDRAW: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_min_withdraw_value)]},
        fallbacks=[]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(add_force_channel_start, pattern="^add_force_channel$")],
        states={SET_FORCE_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_force_channel_value)]},
        fallbacks=[]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(remove_force_channel_start, pattern="^remove_force_channel$")],
        states={REMOVE_FORCE_CHANNEL: [CallbackQueryHandler(remove_force_channel_callback, pattern="^remove_ch_")]},
        fallbacks=[]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(add_balance_start, pattern="^add_balance$")],
        states={
            ADD_BALANCE_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_balance_user_id)],
            ADD_BALANCE_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_balance_amount)]
        },
        fallbacks=[]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(ban_user_start, pattern="^ban_user$")],
        states={BAN_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ban_user_id)]},
        fallbacks=[]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(unban_user_start, pattern="^unban_user$")],
        states={UNBAN_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, unban_user_id)]},
        fallbacks=[]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(process_withdraw_start, pattern="^process_withdraw$")],
        states={PROCESS_WITHDRAW: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_withdraw_value)]},
        fallbacks=[]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(create_promo_start, pattern="^create_promo$")],
        states={
            ADMIN_PROMO_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_promo_name)],
            ADMIN_PROMO_REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_promo_reward)],
            ADMIN_PROMO_USES: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_promo_uses)],
            ADMIN_PROMO_EXPIRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_promo_expiry)]
        },
        fallbacks=[]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_mailing_start, pattern="^admin_mailing$")],
        states={ADMIN_MAILING: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_mailing_send)]},
        fallbacks=[]
    ))
    
    # Регистрируем остальные callback обработчики
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_rewards_menu, pattern="^admin_rewards$"))
    app.add_handler(CallbackQueryHandler(admin_forcesub_menu, pattern="^admin_forcesub$"))
    app.add_handler(CallbackQueryHandler(admin_users_menu, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(admin_withdrawals_menu, pattern="^admin_withdrawals$"))
    app.add_handler(CallbackQueryHandler(admin_promo_menu, pattern="^admin_promo$"))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(list_promo, pattern="^list_promo$"))
    
    # Регистрируем обработчики чеков
    app.add_handler(CallbackQueryHandler(cheques_menu, pattern="^cheques_menu$"))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(create_cheque_start, pattern="^create_cheque$")],
        states={CREATE_CHEQUE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_cheque_amount)]},
        fallbacks=[]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(activate_cheque_start, pattern="^activate_cheque$")],
        states={CREATE_CHEQUE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, activate_cheque_process)]},
        fallbacks=[]
    ))
    app.add_handler(CallbackQueryHandler(my_cheques, pattern="^my_cheques$"))
    
    # Регистрируем обработчики выводов
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(request_withdraw_start, pattern="^request_withdraw$")],
        states={PROCESS_WITHDRAW: [MessageHandler(filters.TEXT & ~filters.COMMAND, request_withdraw_amount)]},
        fallbacks=[]
    ))
    app.add_handler(CallbackQueryHandler(withdraw_history, pattern="^withdraw_history$"))
    app.add_handler(CallbackQueryHandler(withdraw_info, pattern="^withdraw_info$"))
    app.add_handler(CallbackQueryHandler(withdraw_menu, pattern="^withdraw_back$"))
    
    # Регистрируем обработчики рефералов
    app.add_handler(CallbackQueryHandler(my_referrals_list, pattern="^my_referrals_list$"))
    app.add_handler(CallbackQueryHandler(referrals_menu, pattern="^referrals_back$"))
    
    # Регистрируем обработчики навигации
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.message.delete(), pattern="^back_to_main$"))
    
    # Регистрируем обработчики текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Запускаем бота
    print("🚀 Бот запущен...")
    print(f"📊 Администратор: {ADMIN_ID}")
    print(f"💎 Название: {settings.bot_name}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()BOTOHUB_TOKEN = "YOUR_BOTOHUB_TOKEN_HERE"  # ЗАМЕНИТЕ НА ВАШ ТОКЕН
BOTOHUB_API_URL = "https://botohub.me/get-tasks"
ADMIN_ID = 5356403777

# Состояния для ConversationHandler
(SET_REWARD, SET_PRICE, SET_NAME, SET_DESCRIPTION, SET_WIN_CHANCE, 
 SET_ADMIN_ID, SET_CHANNEL, SET_PROMO, SET_WITHDRAW, SET_CHEQUE_AMOUNT,
 MAILING_TEXT, SET_TAX, SET_LIMIT, SET_REF_BONUS, EDIT_ITEM,
 ADD_CASE_ITEM, SET_CASE_ITEM_NAME, SET_CASE_ITEM_CHANCE, SET_CASE_ITEM_REWARD,
 PROMO_REWARD, PROMO_EXPIRY, PROMO_USES, WITHDRAW_AMOUNT, WITHDRAW_METHOD,
 BAN_USER, UNBAN_USER, ADD_ADMIN, REMOVE_ADMIN) = range(25)

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
            "prize": 0,
            "end_time": None,
            "winner": None,
            "current_round": 1,
            "history": [],
            "last_draw": None,
            "next_draw": None
        }
        self.promo_codes: Dict[str, Dict] = {}
        self.cheques: Dict[str, Dict] = {}  # cheque_code: {amount, created_by, created_at, used_by, is_used}
        self.withdraw_requests: Dict[int, List[Dict]] = {}
        self.game_history: Dict[int, List[Dict]] = {}
        self.bans: Dict[int, Dict] = {}
        self.global_stats: Dict = {
            "total_users": 0,
            "total_mcoins_earned": 0,
            "total_withdrawn": 0,
            "total_tasks_completed": 0,
            "total_cases_opened": 0,
            "total_games_played": 0,
            "total_lottery_tickets": 0
        }
        self.pending_tasks: Dict[int, Dict] = {}  # user_id: {task_url, timestamp}
        
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
        """Загружает данные из файлов"""
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.users = {int(k): v for k, v in data.get("users", {}).items()}
                    self.cases = data.get("cases", {})
                    self.lottery = data.get("lottery", self.lottery)
                    self.promo_codes = data.get("promo_codes", {})
                    self.cheques = data.get("cheques", {})
                    self.withdraw_requests = {int(k): v for k, v in data.get("withdraw_requests", {}).items()}
                    self.game_history = {int(k): v for k, v in data.get("game_history", {}).items()}
                    self.bans = {int(k): v for k, v in data.get("bans", {}).items()}
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
        self.lottery_price = 10
        self.lottery_commission = 0.8
        self.auto_lottery_hour = 20
        self.auto_lottery_minute = 0
        self.max_daily_tasks = 10
        self.cheque_enabled = True
        self.cheque_commission = 0.05
        
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
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))

def get_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Создает главную клавиатуру с динамическими кнопками"""
    if user_id in db.bans:
        return ReplyKeyboardMarkup([["ℹ️ Я в бане"]], resize_keyboard=True)
    
    keyboard = [
        [KeyboardButton(f"💰 {settings.currency_name}"), KeyboardButton("📋 Задания")],
        [KeyboardButton("🎲 Игры"), KeyboardButton("📦 Кейсы")],
        [KeyboardButton("🎰 Лотерея"), KeyboardButton("👥 Рефералы")],
        [KeyboardButton("🏆 Ежедневный бонус"), KeyboardButton("💸 Вывод средств")],
        [KeyboardButton("🎫 Промокоды"), KeyboardButton("📊 Статистика")],
        [KeyboardButton("🎟️ Чеки"), KeyboardButton("📜 Помощь")]
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
            "daily_tasks_count": 0,
            "last_task_date": None
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
    elif source == "case":
        user["case_earned"] += amount
        db.global_stats["total_cases_opened"] += 1
    elif source == "lottery":
        user["lottery_earned"] += amount
    
    db.global_stats["total_mcoins_earned"] += amount
    update_user_level(user_id)
    db.save()
    return True

def remove_mcoins(user_id: int, amount: int, reason: str = "") -> bool:
    """Снимает MCoin, возвращает True если достаточно средств"""
    if amount <= 0:
        return False
    
    user = get_user_data(user_id)
    if user["mcoin"] >= amount:
        user["mcoin"] -= amount
        db.save()
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
                not_subscribed.append(f"https://t.me/{channel}")
        except:
            not_subscribed.append(f"Канал {channel}")
    
    for group in settings.force_sub_groups:
        try:
            member = await bot.get_chat_member(chat_id=group, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                not_subscribed.append(f"Группа {group}")
        except:
            not_subscribed.append(f"Группа {group}")
    
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
                    return {"tasks": [], "completed": False, "skip": True}
    except Exception as e:
        logger.error(f"BotoHub API ошибка: {e}")
        return {"tasks": [], "completed": False, "skip": True}

async def regular_mode(update: Update, context: CallbackContext):
    """Обычный режим заданий - получаем все ссылки сразу"""
    user_id = update.effective_user.id
    
    # Проверка подписок
    passed, not_passed = await check_force_subs(user_id, context.bot)
    if not passed:
        msg = "⚠️ **Для выполнения заданий подпишитесь:**\n\n"
        for ch in not_passed:
            msg += f"• {ch}\n"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return
    
    msg = await update.message.reply_text("🔄 Получаем задания...")
    
    try:
        result = await call_botohub_api(user_id, is_task=False)
        tasks = result.get("tasks", [])
        completed = result.get("completed", False)
        
        if completed:
            await msg.edit_text("✅ Все задания выполнены!")
            return
        
        if not tasks:
            await msg.edit_text("🎉 Нет активных заданий")
            return
        
        for url in tasks:
            await update.message.reply_text(
                f"📌 **Задание:**\n{url}\n\n"
                f"💰 Награда: {settings.task_reward} {settings.currency_name}",
                disable_web_page_preview=True
            )
        
        await update.message.reply_text(
            "✅ Задания отправлены!\n"
            "После выполнения всех нажмите /check_tasks"
        )
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")

async def tasks_mode(update: Update, context: CallbackContext):
    """Продвинутый режим заданий - по одной ссылке"""
    user_id = update.effective_user.id
    
    # Проверка подписок
    passed, not_passed = await check_force_subs(user_id, context.bot)
    if not passed:
        msg = "⚠️ **Подпишитесь на каналы:**\n\n"
        for ch in not_passed:
            msg += f"• {ch}\n"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return
    
    # Проверка дневного лимита
    user = get_user_data(user_id)
    today = datetime.now().date().isoformat()
    if user.get("last_task_date") != today:
        user["daily_tasks_count"] = 0
        user["last_task_date"] = today
    
    if user["daily_tasks_count"] >= settings.max_daily_tasks:
        await update.message.reply_text(f"⚠️ Дневной лимит заданий: {settings.max_daily_tasks}")
        return
    
    msg = await update.message.reply_text("🔄 Получаем задание...")
    
    try:
        result = await call_botohub_api(user_id, is_task=True, skip=False)
        tasks = result.get("tasks", [])
        completed = result.get("completed", False)
        
        if completed:
            await msg.edit_text("✅ Все задания выполнены!")
            reward = settings.task_reward * 2
            add_mcoins(user_id, reward, "all_tasks_completed", "task")
            await update.message.reply_text(f"🎉 Бонус за все задания: {reward} {settings.currency_name}")
            return
        
        if not tasks:
            await msg.edit_text("🎉 Нет заданий. Зайдите позже")
            return
        
        task_url = tasks[0]
        db.pending_tasks[user_id] = {"url": task_url, "time": time.time()}
        
        keyboard = [[
            InlineKeyboardButton("✅ Выполнил", callback_data=f"check_task_{task_url}"),
            InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")
        ]]
        
        await msg.edit_text(
            f"📢 **Задание:**\n{task_url}\n\n"
            f"💰 Награда: {settings.task_reward} {settings.currency_name}\n"
            f"📊 Заданий сегодня: {user['daily_tasks_count'] + 1}/{settings.max_daily_tasks}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True
        )
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")

async def check_task_callback(update: Update, context: CallbackContext):
    """Проверка выполнения задания"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    task_url = query.data.replace("check_task_", "")
    
    # Проверка времени выполнения
    pending = db.pending_tasks.get(user_id, {})
    if pending.get("url") != task_url:
        await query.edit_message_text("❌ Задание устарело. Начните заново /tasks")
        return
    
    if time.time() - pending.get("time", 0) > 300:  # 5 минут
        await query.edit_message_text("⏰ Время вышло! Начните /tasks заново")
        db.pending_tasks.pop(user_id, None)
        return
    
    await query.edit_message_text("🔍 Проверяем...")
    
    try:
        result = await call_botohub_api(user_id, is_task=True, skip=False)
        prev_success = result.get("prev_success", False)
        
        if prev_success:
            reward = settings.task_reward
            add_mcoins(user_id, reward, "task_completed", "task")
            
            user = get_user_data(user_id)
            today = datetime.now().date().isoformat()
            if user.get("last_task_date") == today:
                user["daily_tasks_count"] += 1
            else:
                user["daily_tasks_count"] = 1
                user["last_task_date"] = today
            db.save()
            
            db.pending_tasks.pop(user_id, None)
            
            await query.edit_message_text(
                f"✅ **Задание выполнено!**\n"
                f"💰 +{reward} {settings.currency_name}\n"
                f"📊 Баланс: {format_number(user['mcoin'])}"
            )
            
            # Следующее задание
            new_result = await call_botohub_api(user_id, is_task=True, skip=False)
            new_tasks = new_result.get("tasks", [])
            if new_tasks and not new_result.get("completed"):
                keyboard = [[
                    InlineKeyboardButton("✅ Выполнил", callback_data=f"check_task_{new_tasks[0]}"),
                    InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")
                ]]
                await query.message.reply_text(
                    f"📢 **Следующее задание:**\n{new_tasks[0]}",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        else:
            await query.edit_message_text(
                f"❌ **Не подписались!**\n\n"
                f"Подпишитесь:\n{task_url}\n\n"
                f"Затем нажмите «✅ Выполнил»",
                disable_web_page_preview=True
            )
            keyboard = [[
                InlineKeyboardButton("✅ Выполнил", callback_data=f"check_task_{task_url}"),
                InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")
            ]]
            await query.edit_message_reply_markup(InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {e}")

async def skip_task_callback(update: Update, context: CallbackContext):
    """Пропуск задания"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    await query.edit_message_text("⏩ Пропускаем...")
    db.pending_tasks.pop(user_id, None)
    
    try:
        result = await call_botohub_api(user_id, is_task=True, skip=True)
        tasks = result.get("tasks", [])
        
        if tasks:
            new_url = tasks[0]
            db.pending_tasks[user_id] = {"url": new_url, "time": time.time()}
            keyboard = [[
                InlineKeyboardButton("✅ Выполнил", callback_data=f"check_task_{new_url}"),
                InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")
            ]]
            await query.edit_message_text(
                f"📢 **Новое задание:**\n{new_url}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text("🎉 Заданий нет")
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {e}")

# ========== ИГРЫ ==========
async def game_casino(update: Update, context: CallbackContext):
    """Игра Казино"""
    user_id = update.effective_user.id
    args = context.args
    
    if not settings.games_enabled:
        await update.message.reply_text("🎮 Игры временно недоступны!")
        return
    
    if not args:
        await update.message.reply_text(
            f"🎰 **Казино**\n"
            f"Использование: /casino <сумма>\n"
            f"Мин: {settings.min_game_bet}, Макс: {settings.max_game_bet}"
        )
        return
    
    try:
        bet = int(args[0])
        if bet < settings.min_game_bet or bet > settings.max_game_bet:
            await update.message.reply_text(f"❌ Ставка от {settings.min_game_bet} до {settings.max_game_bet}")
            return
    except:
        await update.message.reply_text("❌ Введите число!")
        return
    
    user = get_user_data(user_id)
    if not remove_mcoins(user_id, bet, f"casino_bet"):
        await update.message.reply_text(f"❌ Недостаточно средств! Баланс: {user['mcoin']}")
        return
    
    user["games_played"] += 1
    db.global_stats["total_games_played"] += 1
    
    win_chance = random.random()
    if win_chance < settings.casino_win_rate:
        multiplier = random.uniform(1.5, 3.0)
        win_amount = int(bet * multiplier)
        add_mcoins(user_id, win_amount, "casino_win", "game")
        user["games_won"] += 1
        
        await update.message.reply_text(
            f"🎉 **ВЫ ВЫИГРАЛИ!** 🎉\n"
            f"Ставка: {bet}\n"
            f"Выигрыш: {win_amount}\n"
            f"Баланс: {user['mcoin']}"
        )
    else:
        await update.message.reply_text(
            f"😢 **ПРОИГРЫШ**\n"
            f"Ставка: {bet}\n"
            f"Баланс: {user['mcoin']}"
        )
    
    db.save()

async def game_dice(update: Update, context: CallbackContext):
    """Игра Кости"""
    user_id = update.effective_user.id
    args = context.args
    
    if not settings.games_enabled:
        await update.message.reply_text("🎮 Игры недоступны!")
        return
    
    if not args:
        await update.message.reply_text("🎲 /dice <сумма>")
        return
    
    try:
        bet = int(args[0])
        if bet < settings.min_game_bet or bet > settings.max_game_bet:
            await update.message.reply_text(f"❌ Ставка от {settings.min_game_bet} до {settings.max_game_bet}")
            return
    except:
        await update.message.reply_text("❌ Введите число!")
        return
    
    user = get_user_data(user_id)
    if not remove_mcoins(user_id, bet, "dice_bet"):
        await update.message.reply_text(f"❌ Недостаточно средств!")
        return
    
    user["games_played"] += 1
    
    user_dice = random.randint(1, 6)
    bot_dice = random.randint(1, 6)
    
    if user_dice > bot_dice:
        win_amount = bet * 2
        add_mcoins(user_id, win_amount, "dice_win", "game")
        user["games_won"] += 1
        await update.message.reply_text(
            f"🎲 **ПОБЕДА!**\n"
            f"Вы: {user_dice}, Бот: {bot_dice}\n"
            f"Выигрыш: {win_amount}\n"
            f"Баланс: {user['mcoin']}"
        )
    elif user_dice < bot_dice:
        await update.message.reply_text(
            f"😢 **ПРОИГРЫШ**\n"
            f"Вы: {user_dice}, Бот: {bot_dice}\n"
            f"Баланс: {user['mcoin']}"
        )
    else:
        add_mcoins(user_id, bet, "dice_draw", "game")
        await update.message.reply_text(
            f"🤝 **НИЧЬЯ**\n"
            f"Ставка возвращена!\n"
            f"Баланс: {user['mcoin']}"
        )
    
    db.save()

async def game_slots(update: Update, context: CallbackContext):
    """Игра Слоты"""
    user_id = update.effective_user.id
    args = context.args
    
    if not settings.games_enabled:
        await update.message.reply_text("🎮 Игры недоступны!")
        return
    
    if not args:
        await update.message.reply_text("🎰 /slots <сумма>")
        return
    
    try:
        bet = int(args[0])
        if bet < settings.min_game_bet or bet > settings.max_game_bet:
            await update.message.reply_text(f"❌ Ставка от {settings.min_game_bet} до {settings.max_game_bet}")
            return
    except:
        await update.message.reply_text("❌ Введите число!")
        return
    
    user = get_user_data(user_id)
    if not remove_mcoins(user_id, bet, "slots_bet"):
        await update.message.reply_text(f"❌ Недостаточно средств!")
        return
    
    user["games_played"] += 1
    
    symbols = ["🍒", "🍊", "🍋", "🍉", "🔔", "💎"]
    result = [random.choice(symbols) for _ in range(3)]
    
    if result[0] == result[1] == result[2]:
        multiplier = 3.0
        win_amount = int(bet * multiplier)
        add_mcoins(user_id, win_amount, "slots_win", "game")
        user["games_won"] += 1
        await update.message.reply_text(
            f"🎰 **ДЖЕКПОТ!**\n"
            f"{result[0]} | {result[1]} | {result[2]}\n"
            f"Выигрыш: {win_amount}\n"
            f"Баланс: {user['mcoin']}"
        )
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        add_mcoins(user_id, bet, "slots_two", "game")
        await update.message.reply_text(
            f"🎰 **2 СИМВОЛА!**\n"
            f"{result[0]} | {result[1]} | {result[2]}\n"
            f"Ставка возвращена!\n"
            f"Баланс: {user['mcoin']}"
        )
    else:
        await update.message.reply_text(
            f"😢 **ПРОИГРЫШ**\n"
            f"{result[0]} | {result[1]} | {result[2]}\n"
            f"Баланс: {user['mcoin']}"
        )
    
    db.save()

# ========== КЕЙСЫ ==========
async def cases_menu(update: Update, context: CallbackContext):
    """Меню кейсов"""
    if not settings.cases_enabled:
        await update.message.reply_text("📦 Кейсы недоступны!")
        return
    
    if not db.cases:
        await update.message.reply_text("📦 Кейсы временно отсутствуют!")
        return
    
    keyboard = []
    for name, data in db.cases.items():
        keyboard.append([InlineKeyboardButton(
            f"📦 {name} - {data['price']} {settings.currency_name}",
            callback_data=f"open_case_{name}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")])
    
    await update.message.reply_text(
        "🎁 **Кейсы**\n\n"
        f"💰 Баланс: {format_number(get_user_data(update.effective_user.id)['mcoin'])}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def open_case_callback(update: Update, context: CallbackContext):
    """Открытие кейса"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    case_name = query.data.replace("open_case_", "")
    
    if case_name not in db.cases:
        await query.edit_message_text("❌ Кейс не найден!")
        return
    
    case = db.cases[case_name]
    user = get_user_data(user_id)
    
    if not remove_mcoins(user_id, case["price"], f"case_{case_name}"):
        await query.answer(f"Недостаточно {settings.currency_name}!", True)
        return
    
    # Выбор предмета
    items = case["items"]
    total_chance = sum(i["chance"] for i in items)
    roll = random.random() * total_chance
    
    current = 0
    selected = None
    for item in items:
        current += item["chance"]
        if roll <= current:
            selected = item
            break
    
    if not selected:
        selected = items[0]
    
    reward = selected["reward"]
    add_mcoins(user_id, reward, f"case_{case_name}", "case")
    user["cases_opened"] += 1
    user["inventory"].append({"name": selected["name"], "date": datetime.now().isoformat()})
    db.save()
    
    await query.edit_message_text(
        f"🎉 **Открыт кейс: {case_name}**\n\n"
        f"📦 Выпало: {selected['name']}\n"
        f"💰 Награда: {reward} {settings.currency_name}\n"
        f"💎 Баланс: {format_number(user['mcoin'])}\n"
        f"📊 Всего кейсов: {user['cases_opened']}"
    )

# ========== ЛОТЕРЕЯ ==========
async def lottery_menu(update: Update, context: CallbackContext):
    """Меню лотереи"""
    if not settings.lottery_enabled:
        await update.message.reply_text("🎰 Лотерея недоступна!")
        return
    
    user_id = update.effective_user.id
    tickets = db.lottery["tickets"].get(user_id, 0)
    total_tickets = sum(db.lottery["tickets"].values())
    
    keyboard = [
        [InlineKeyboardButton(f"🎫 Купить билет ({settings.lottery_price} MCoin)", callback_data="buy_ticket")],
        [InlineKeyboardButton("🎫 Купить 10 билетов (скидка)", callback_data="buy_10_tickets")],
        [InlineKeyboardButton("📊 Мои билеты", callback_data="my_tickets")]
    ]
    
    if user_id in settings.admin_list:
        keyboard.append([InlineKeyboardButton("🎲 Провести розыгрыш", callback_data="draw_lottery")])
    
    keyboard.append([InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")])
    
    await update.message.reply_text(
        f"🎰 **Лотерея**\n\n"
        f"💰 Призовой фонд: {format_number(db.lottery['prize'])} {settings.currency_name}\n"
        f"🎫 Всего билетов: {total_tickets}\n"
        f"🎫 Ваших билетов: {tickets}\n"
        f"💳 Цена билета: {settings.lottery_price} {settings.currency_name}\n\n"
        f"🏆 Победитель получает 80% призового фонда!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def buy_ticket_callback(update: Update, context: CallbackContext, count: int = 1):
    """Покупка билетов"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if not db.lottery["active"]:
        await query.answer("Лотерея не активна!", True)
        return
    
    price = settings.lottery_price * count
    if count == 10:
        price = int(price * 0.95)
    
    if not remove_mcoins(user_id, price, f"lottery_ticket_{count}"):
        await query.answer(f"Недостаточно {settings.currency_name}!", True)
        return
    
    if user_id not in db.lottery["tickets"]:
        db.lottery["tickets"][user_id] = 0
    db.lottery["tickets"][user_id] += count
    db.lottery["prize"] += int(price * settings.lottery_commission)
    db.global_stats["total_lottery_tickets"] += count
    db.save()
    
    await query.answer(f"Куплено {count} билетов!", True)
    await query.message.edit_text(
        f"✅ **Куплено {count} билетов!**\n"
        f"💰 Стоимость: {price} {settings.currency_name}\n"
        f"🎫 Ваших билетов: {db.lottery['tickets'][user_id]}\n"
        f"💰 Призовой фонд: {format_number(db.lottery['prize'])}\n\n"
        f"🍀 Удачи!"
    )

async def draw_lottery_callback(update: Update, context: CallbackContext):
    """Розыгрыш лотереи"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in settings.admin_list:
        await query.answer("Доступ запрещен!", True)
        return
    
    if not db.lottery["active"]:
        await query.answer("Лотерея не активна!", True)
        return
    
    total_tickets = sum(db.lottery["tickets"].values())
    if total_tickets == 0:
        await query.edit_message_text("❌ Нет билетов для розыгрыша!")
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
    add_mcoins(winner_id, prize, "lottery_win", "lottery")
    
    # История
    winner_name = db.users.get(winner_id, {}).get("first_name", f"User_{winner_id}")
    db.lottery["history"].append({
        "round": db.lottery["current_round"],
        "winner_id": winner_id,
        "winner_name": winner_name,
        "prize": prize,
        "total_tickets": total_tickets,
        "date": datetime.now().isoformat()
    })
    
    # Сброс
    db.lottery["tickets"] = {}
    db.lottery["prize"] = int(db.lottery["prize"] * 0.1)
    db.lottery["current_round"] += 1
    db.lottery["last_draw"] = datetime.now().isoformat()
    db.save()
    
    await query.edit_message_text(
        f"🎉 **РОЗЫГРЫШ ЛОТЕРЕИ!** 🎉\n\n"
        f"🏆 Победитель: [{winner_name}](tg://user?id={winner_id})\n"
        f"💰 Приз: {format_number(prize)} {settings.currency_name}\n"
        f"🎫 Всего билетов: {total_tickets}\n"
        f"📊 Раунд: {db.lottery['current_round'] - 1}",
        parse_mode="Markdown"
    )
    
    try:
        await context.bot.send_message(
            winner_id,
            f"🎉 **ПОЗДРАВЛЯЕМ!**\n\n"
            f"Вы выиграли в лотерее!\n"
            f"💰 Приз: {format_number(prize)} {settings.currency_name}"
        )
    except:
        pass

# ========== ЧЕКИ ==========
async def cheques_menu(update: Update, context: CallbackContext):
    """Меню чеков"""
    if not settings.cheque_enabled:
        await update.message.reply_text("🎟️ Чеки временно недоступны!")
        return
    
    keyboard = [
        [InlineKeyboardButton("➕ Создать чек", callback_data="create_cheque")],
        [InlineKeyboardButton("💳 Активировать чек", callback_data="activate_cheque")],
        [InlineKeyboardButton("📊 Мои чеки", callback_data="my_cheques")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    
    await update.message.reply_text(
        f"🎟️ **Чеки**\n\n"
        f"💎 Создайте чек и отправьте другу!\n"
        f"💰 Комиссия: {int(settings.cheque_commission * 100)}%\n\n"
        f"Как создать чек:\n"
        f"1. Нажмите «Создать чек»\n"
        f"2. Введите сумму\n"
        f"3. Получите код\n"
        f"4. Отправьте код другу\n\n"
        f"Как активировать:\n"
        f"1. Нажмите «Активировать чек»\n"
        f"2. Введите код\n"
        f"3. Получите {settings.currency_name}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def create_cheque_start(update: Update, context: CallbackContext):
    """Начало создания чека"""
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("💰 Введите сумму чека:")
    return SET_CHEQUE_AMOUNT

async def create_cheque_amount(update: Update, context: CallbackContext):
    """Создание чека"""
    user_id = update.effective_user.id
    
    try:
        amount = int(update.message.text)
        if amount < 10:
            await update.message.reply_text("❌ Минимальная сумма: 10 MCoin")
            return SET_CHEQUE_AMOUNT
    except:
        await update.message.reply_text("❌ Введите число!")
        return SET_CHEQUE_AMOUNT
    
    commission = int(amount * settings.cheque_commission)
    total = amount + commission
    
    if not remove_mcoins(user_id, total, f"cheque_create_{amount}"):
        await update.message.reply_text(f"❌ Недостаточно средств! Нужно: {total}")
        return SET_CHEQUE_AMOUNT
    
    code = generate_cheque_code()
    db.cheques[code] = {
        "amount": amount,
        "created_by": user_id,
        "created_at": datetime.now().isoformat(),
        "used_by": None,
        "is_used": False
    }
    db.save()
    
    await update.message.reply_text(
        f"✅ **Чек создан!**\n\n"
        f"💰 Сумма: {amount} {settings.currency_name}\n"
        f"💸 Комиссия: {commission} {settings.currency_name}\n"
        f"🎟️ Код: `{code}`\n\n"
        f"Отправьте код другу!\n"
        f"Чек действителен 7 дней",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def activate_cheque_start(update: Update, context: CallbackContext):
    """Начало активации чека"""
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("🎟️ Введите код чека:")
    return SET_CHEQUE_AMOUNT

async def activate_cheque_code(update: Update, context: CallbackContext):
    """Активация чека"""
    user_id = update.effective_user.id
    code = update.message.text.strip().upper()
    
    if code not in db.cheques:
        await update.message.reply_text("❌ Неверный код чека!")
        return ConversationHandler.END
    
    cheque = db.cheques[code]
    
    if cheque["is_used"]:
        await update.message.reply_text("❌ Чек уже использован!")
        return ConversationHandler.END
    
    # Проверка срока действия (7 дней)
    created_at = datetime.fromisoformat(cheque["created_at"])
    if datetime.now() - created_at > timedelta(days=7):
        await update.message.reply_text("❌ Срок действия чека истек!")
        return ConversationHandler.END
    
    if cheque["created_by"] == user_id:
        await update.message.reply_text("❌ Нельзя активировать свой чек!")
        return ConversationHandler.END
    
    amount = cheque["amount"]
    add_mcoins(user_id, amount, f"cheque_{code}", "other")
    cheque["is_used"] = True
    cheque["used_by"] = user_id
    db.save()
    
    await update.message.reply_text(
        f"✅ **Чек активирован!**\n\n"
        f"💰 Получено: {amount} {settings.currency_name}\n"
        f"🎟️ Код: {code}\n\n"
        f"💎 Баланс: {format_number(get_user_data(user_id)['mcoin'])}"
    )
    
    # Уведомление создателя
    creator = cheque["created_by"]
    try:
        await context.bot.send_message(
            creator,
            f"🎉 **Чек активирован!**\n\n"
            f"💰 Сумма: {amount} {settings.currency_name}\n"
            f"👤 Активировал: {update.effective_user.first_name}"
        )
    except:
        pass
    
    return ConversationHandler.END

# ========== АДМИН ПАНЕЛЬ ==========
async def admin_panel(update: Update, context: CallbackContext):
    """Главная админ панель"""
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
        [InlineKeyboardButton("💸 Выводы", callback_data="admin_withdrawals")],
        [InlineKeyboardButton("📨 Рассылка", callback_data="admin_mailing")],
        [InlineKeyboardButton("🎫 Промокоды", callback_data="admin_promo")],
        [InlineKeyboardButton("🎟️ Чеки", callback_data="admin_cheques")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="admin_settings")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ]
    
    await update.message.reply_text(
        "⚙️ **Админ панель**\n\n"
        f"👥 Пользователей: {db.global_stats['total_users']}\n"
        f"💰 В обороте: {format_number(db.global_stats['total_mcoins_earned'] - db.global_stats['total_withdrawn'])}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_rewards_menu(update: Update, context: CallbackContext):
    """Настройка наград"""
    query = update.callback_query
    
    keyboard = [
        [InlineKeyboardButton(f"📋 Задание: {settings.task_reward}", callback_data="set_task_reward")],
        [InlineKeyboardButton(f"👥 Реферал: {settings.referral_reward}", callback_data="set_ref_reward")],
        [InlineKeyboardButton(f"🏆 Ежедневный: {settings.daily_reward}", callback_data="set_daily_reward")],
        [InlineKeyboardButton(f"💸 Мин. вывод: {settings.min_withdraw}", callback_data="set_min_withdraw")],
        [InlineKeyboardButton(f"📊 Макс. вывод: {settings.max_withdraw}", callback_data="set_max_withdraw")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    
    await query.message.edit_text(
        "💰 **Настройка наград**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def set_task_reward_start(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("💰 Введите новую награду за задание:")
    return SET_REWARD

async def set_task_reward_value(update: Update, context: CallbackContext):
    try:
        value = int(update.message.text)
        settings.task_reward = value
        settings.save()
        await update.message.reply_text(f"✅ Награда за задание: {value}")
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Введите число!")
        return SET_REWARD

async def admin_cases_menu(update: Update, context: CallbackContext):
    """Управление кейсами"""
    query = update.callback_query
    
    keyboard = [
        [InlineKeyboardButton("➕ Создать кейс", callback_data="create_case")],
        [InlineKeyboardButton("🗑 Удалить кейс", callback_data="delete_case")],
        [InlineKeyboardButton("📋 Список кейсов", callback_data="list_cases")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    
    cases_text = "\n".join([f"• {n}: {d['price']}" for n, d in db.cases.items()]) if db.cases else "Нет кейсов"
    
    await query.message.edit_text(
        f"📦 **Управление кейсами**\n\n{cases_text}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def create_case_start(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("📦 Введите название кейса:")
    return SET_NAME

async def create_case_name(update: Update, context: CallbackContext):
    name = update.message.text
    context.user_data["case_name"] = name
    await update.message.reply_text(f"💰 Введите цену кейса для '{name}':")
    return SET_PRICE

async def create_case_price(update: Update, context: CallbackContext):
    try:
        price = int(update.message.text)
        context.user_data["case_price"] = price
        context.user_data["case_items"] = []
        await update.message.reply_text(
            "📦 Добавьте предметы:\n"
            "Формат: Название | Шанс | Награда\n"
            "Пример: Легенда | 5 | 1000\n\n"
            "После всех предметов отправьте 'готово'"
        )
        return ADD_CASE_ITEM
    except:
        await update.message.reply_text("❌ Введите число!")
        return SET_PRICE

async def add_case_item(update: Update, context: CallbackContext):
    text = update.message.text
    
    if text.lower() == "готово":
        if not context.user_data["case_items"]:
            await update.message.reply_text("❌ Добавьте хотя бы один предмет!")
            return ADD_CASE_ITEM
        
        db.cases[context.user_data["case_name"]] = {
            "price": context.user_data["case_price"],
            "items": context.user_data["case_items"]
        }
        db.save()
        
        await update.message.reply_text(
            f"✅ **Кейс создан!**\n"
            f"📦 {context.user_data['case_name']}\n"
            f"💰 Цена: {context.user_data['case_price']}\n"
            f"📦 Предметов: {len(context.user_data['case_items'])}"
        )
        return ConversationHandler.END
    
    try:
        parts = text.split("|")
        if len(parts) != 3:
            await update.message.reply_text("❌ Формат: Название | Шанс | Награда")
            return ADD_CASE_ITEM
        
        name = parts[0].strip()
        chance = float(parts[1].strip())
        reward = int(parts[2].strip())
        
        context.user_data["case_items"].append({
            "name": name, "chance": chance, "reward": reward
        })
        
        await update.message.reply_text(
            f"✅ Добавлен: {name}\n"
            f"📊 Всего: {len(context.user_data['case_items'])} предметов\n\n"
            f"Добавьте следующий или 'готово'"
        )
        return ADD_CASE_ITEM
    except:
        await update.message.reply_text("❌ Ошибка! Формат: Название | Шанс | Награда")
        return ADD_CASE_ITEM

async def delete_case_start(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if not db.cases:
        await query.edit_message_text("❌ Нет кейсов для удаления")
        return
    
    keyboard = []
    for name in db.cases.keys():
        keyboard.append([InlineKeyboardButton(f"🗑 {name}", callback_data=f"delete_case_{name}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_cases")])
    
    await query.message.edit_text(
        "🗑 Выберите кейс для удаления:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def delete_case_confirm(update: Update, context: CallbackContext):
    query = update.callback_query
    case_name = query.data.replace("delete_case_", "")
    
    if case_name in db.cases:
        del db.cases[case_name]
        db.save()
        await query.answer(f"Кейс {case_name} удален!", True)
        await admin_cases_menu(update, context)
    else:
        await query.answer("Кейс не найден!", True)

async def admin_lottery_menu(update: Update, context: CallbackContext):
    """Управление лотереей"""
    query = update.callback_query
    
    status = "Активна" if db.lottery["active"] else "Остановлена"
    
    keyboard = [
        [InlineKeyboardButton("▶️ Запустить" if not db.lottery["active"] else "⏸️ Остановить", callback_data="toggle_lottery")],
        [InlineKeyboardButton("💰 Установить приз", callback_data="set_lottery_prize")],
        [InlineKeyboardButton("🎲 Провести розыгрыш", callback_data="draw_lottery_now")],
        [InlineKeyboardButton("📊 История", callback_data="lottery_history")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    
    await query.message.edit_text(
        f"🎰 **Управление лотереей**\n\n"
        f"Статус: {status}\n"
        f"💰 Призовой фонд: {format_number(db.lottery['prize'])}\n"
        f"🎫 Всего билетов: {sum(db.lottery['tickets'].values())}\n"
        f"📊 Раунд: {db.lottery['current_round']}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_forcesub_menu(update: Update, context: CallbackContext):
    """Настройка обязательных подписок"""
    query = update.callback_query
    
    channels = "\n".join([f"• {c}" for c in settings.force_sub_channels]) if settings.force_sub_channels else "Нет"
    groups = "\n".join([f"• {g}" for g in settings.force_sub_groups]) if settings.force_sub_groups else "Нет"
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить канал", callback_data="add_force_channel")],
        [InlineKeyboardButton("➕ Добавить группу", callback_data="add_force_group")],
        [InlineKeyboardButton("🗑 Удалить канал", callback_data="remove_force_channel")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    
    await query.message.edit_text(
        f"📢 **Обязательные подписки**\n\n"
        f"📺 Каналы:\n{channels}\n\n"
        f"👥 Группы:\n{groups}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_users_menu(update: Update, context: CallbackContext):
    """Управление пользователями"""
    query = update.callback_query
    
    keyboard = [
        [InlineKeyboardButton("🔨 Забанить", callback_data="ban_user")],
        [InlineKeyboardButton("🔓 Разбанить", callback_data="unban_user")],
        [InlineKeyboardButton("💰 Выдать MCoin", callback_data="give_mcoin")],
        [InlineKeyboardButton("📊 Поиск пользователя", callback_data="find_user")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    
    await query.message.edit_text(
        "👥 **Управление пользователями**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_stats_menu(update: Update, context: CallbackContext):
    """Статистика бота"""
    query = update.callback_query
    
    # Топ пользователей
    top_users = sorted(db.users.items(), key=lambda x: x[1]["total_earned"], reverse=True)[:10]
    top_text = "\n".join([f"{i+1}. {u[1].get('first_name', 'User')[:20]}: {format_number(u[1]['total_earned'])}" 
                          for i, u in enumerate(top_users)]) if top_users else "Нет данных"
    
    await query.message.edit_text(
        f"📊 **Статистика бота**\n\n"
        f"👥 Пользователей: {db.global_stats['total_users']}\n"
        f"💰 Всего заработано: {format_number(db.global_stats['total_mcoins_earned'])}\n"
        f"💸 Выведено: {format_number(db.global_stats['total_withdrawn'])}\n"
        f"✅ Заданий: {db.global_stats['total_tasks_completed']}\n"
        f"📦 Кейсов: {db.global_stats['total_cases_opened']}\n"
        f"🎮 Игр: {db.global_stats['total_games_played']}\n"
        f"🎫 Билетов лотереи: {db.global_stats['total_lottery_tickets']}\n\n"
        f"🏆 **Топ 10 пользователей:**\n{top_text}",
        parse_mode="Markdown"
    )

async def admin_withdrawals_menu(update: Update, context: CallbackContext):
    """Управление выводами"""
    query = update.callback_query
    
    pending = []
    for uid, requests in db.withdraw_requests.items():
        for req in requests:
            if req.get("status") == "pending":
                pending.append(f"👤 {uid}: {req['amount']} MCoin")
    
    pending_text = "\n".join(pending) if pending else "Нет заявок"
    
    keyboard = [
        [InlineKeyboardButton("✅ Одобрить вывод", callback_data="approve_withdraw")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    
    await query.message.edit_text(
        f"💸 **Заявки на вывод**\n\n{pending_text}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_mailing_start(update: Update, context: CallbackContext):
    """Начало рассылки"""
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("📨 Введите текст рассылки:")
    return MAILING_TEXT

async def admin_mailing_send(update: Update, context: CallbackContext):
    """Отправка рассылки"""
    text = update.message.text
    
    success = 0
    fail = 0
    
    progress = await update.message.reply_text("📨 Отправка рассылки...")
    
    for user_id in db.users.keys():
        try:
            await context.bot.send_message(user_id, text, parse_mode="Markdown")
            success += 1
            await asyncio.sleep(0.05)
        except:
            fail += 1
    
    await progress.edit_text(
        f"✅ **Рассылка завершена!**\n\n"
        f"📨 Отправлено: {success}\n"
        f"❌ Ошибок: {fail}\n"
        f"👥 Всего: {success + fail}"
    )
    return ConversationHandler.END

async def admin_promo_menu(update: Update, context: CallbackContext):
    """Управление промокодами"""
    query = update.callback_query
    
    keyboard = [
        [InlineKeyboardButton("➕ Создать промокод", callback_data="create_promo")],
        [InlineKeyboardButton("📋 Список промокодов", callback_data="list_promos")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    
    await query.message.edit_text(
        "🎫 **Управление промокодами**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_cheques_menu(update: Update, context: CallbackContext):
    """Управление чеками"""
    query = update.callback_query
    
    total_cheques = len(db.cheques)
    active_cheques = sum(1 for c in db.cheques.values() if not c["is_used"])
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика чеков", callback_data="cheque_stats")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    
    await query.message.edit_text(
        f"🎟️ **Управление чеками**\n\n"
        f"📊 Всего чеков: {total_cheques}\n"
        f"✅ Активных: {active_cheques}\n"
        f"❌ Использовано: {total_cheques - active_cheques}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_settings_menu(update: Update, context: CallbackContext):
    """Настройки бота"""
    query = update.callback_query
    
    keyboard = [
        [InlineKeyboardButton(f"🎮 Игры: {'Вкл' if settings.games_enabled else 'Выкл'}", callback_data="toggle_games")],
        [InlineKeyboardButton(f"📦 Кейсы: {'Вкл' if settings.cases_enabled else 'Выкл'}", callback_data="toggle_cases")],
        [InlineKeyboardButton(f"🎰 Лотерея: {'Вкл' if settings.lottery_enabled else 'Выкл'}", callback_data="toggle_lottery")],
        [InlineKeyboardButton(f"👥 Рефералы: {'Вкл' if settings.referral_program else 'Выкл'}", callback_data="toggle_referrals")],
        [InlineKeyboardButton(f"🎟️ Чеки: {'Вкл' if settings.cheque_enabled else 'Выкл'}", callback_data="toggle_cheques")],
        [InlineKeyboardButton("💬 Приветствие", callback_data="set_welcome")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    
    await query.message.edit_text(
        "⚙️ **Настройки бота**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ПОЛЬЗОВАТЕЛЕЙ ==========
async def start(update: Update, context: CallbackContext):
    """Обработка /start"""
    user_id = update.effective_user.id
    
    if user_id in db.bans:
        await update.message.reply_text("⛔ Вы забанены!")
        return
    
    # Реферальная система
    if context.args and context.args[0].startswith("ref_"):
        referrer_id = int(context.args[0].replace("ref_", ""))
        if referrer_id != user_id and referrer_id not in db.bans:
            user = get_user_data(user_id)
            if not user.get("referrer"):
                user["referrer"] = referrer_id
                referrer = get_user_data(referrer_id)
                referrer["referrals"].append(user_id)
                add_mcoins(referrer_id, settings.referral_reward, "referral", "referral")
                db.save()
                
                try:
                    await context.bot.send_message(
                        referrer_id,
                        f"👥 **Новый реферал!**\n{update.effective_user.first_name}\n💰 +{settings.referral_reward}"
                    )
                except:
                    pass
    
    get_user_data(user_id)
    
    await update.message.reply_text(
        f"👋 **Привет, {update.effective_user.first_name}!**\n\n"
        f"{settings.welcome_message}\n\n"
        f"💰 Баланс: 0 {settings.currency_name}\n\n"
        f"Используйте кнопки меню 👇",
        reply_markup=get_main_keyboard(user_id)
    )

async def balance_handler(update: Update, context: CallbackContext):
    """Показ баланса"""
    user = get_user_data(update.effective_user.id)
    
    await update.message.reply_text(
        f"💰 **Баланс**\n\n"
        f"💎 {settings.currency_name}: {format_number(user['mcoin'])}\n"
        f"📊 Уровень: {user['level']}\n"
        f"📈 Всего заработано: {format_number(user['total_earned'])}\n"
        f"💸 Выведено: {format_number(user['total_withdrawn'])}"
    )

async def daily_bonus_handler(update: Update, context: CallbackContext):
    """Ежедневный бонус"""
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    now = datetime.now()
    last_daily = user.get("daily_last")
    
    if last_daily:
        last_date = datetime.fromisoformat(last_daily)
        if (now - last_date).days == 0:
            next_bonus = last_date + timedelta(days=1)
            time_left = next_bonus - now
            hours = time_left.seconds // 3600
            minutes = (time_left.seconds % 3600) // 60
            await update.message.reply_text(f"⏰ Бонус через {hours}ч {minutes}мин")
            return
    
    # Расчет бонуса
    if last_daily and (now - last_date).days == 1:
        user["daily_streak"] += 1
    else:
        user["daily_streak"] = 1
    
    bonus = settings.daily_reward * min(1 + (user["daily_streak"] * 0.05), 2.0)
    bonus = int(bonus)
    
    add_mcoins(user_id, bonus, "daily_bonus", "other")
    user["daily_last"] = now.isoformat()
    db.save()
    
    await update.message.reply_text(
        f"🎁 **Ежедневный бонус!**\n\n"
        f"💰 Получено: {bonus} {settings.currency_name}\n"
        f"🔥 Серия: {user['daily_streak']} дней\n"
        f"💎 Баланс: {format_number(user['mcoin'])}"
    )

async def referrals_handler(update: Update, context: CallbackContext):
    """Реферальное меню"""
    user = get_user_data(update.effective_user.id)
    bot_username = context.bot.username
    
    keyboard = [[InlineKeyboardButton("📋 Список рефералов", callback_data="my_referrals")]]
    
    await update.message.reply_text(
        f"👥 **Реферальная программа**\n\n"
        f"👥 Рефералов: {len(user['referrals'])}\n"
        f"💰 Заработано: {user['referral_earned']}\n"
        f"🎁 Награда за реферала: {settings.referral_reward}\n\n"
        f"🔗 Ваша ссылка:\n`https://t.me/{bot_username}?start=ref_{update.effective_user.id}`\n\n"
        f"Приглашайте друзей и получайте бонусы!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def my_referrals_callback(update: Update, context: CallbackContext):
    """Список рефералов"""
    query = update.callback_query
    user = get_user_data(query.from_user.id)
    
    if not user["referrals"]:
        await query.answer("Нет рефералов!", True)
        return
    
    text = "📋 **Ваши рефералы:**\n\n"
    for i, ref_id in enumerate(user["referrals"][:20], 1):
        ref_user = db.users.get(ref_id, {})
        name = ref_user.get("first_name", f"User_{ref_id}")
        earned = ref_user.get("total_earned", 0)
        text += f"{i}. {name[:20]} - {format_number(earned)} MCoin\n"
    
    await query.message.edit_text(text)

async def withdraw_request_handler(update: Update, context: CallbackContext):
    """Запрос на вывод"""
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    if user["mcoin"] < settings.min_withdraw:
        await update.message.reply_text(f"❌ Минимум: {settings.min_withdraw}")
        return
    
    await update.message.reply_text(
        f"💸 **Заявка на вывод**\n\n"
        f"💰 Доступно: {user['mcoin']}\n"
        f"📉 Мин: {settings.min_withdraw}\n"
        f"📈 Макс: {settings.max_withdraw}\n\n"
        f"Введите сумму вывода:"
    )
    return WITHDRAW_AMOUNT

async def withdraw_amount_handler(update: Update, context: CallbackContext):
    """Обработка суммы вывода"""
    user_id = update.effective_user.id
    
    try:
        amount = int(update.message.text)
        if amount < settings.min_withdraw or amount > settings.max_withdraw:
            await update.message.reply_text(f"❌ Сумма от {settings.min_withdraw} до {settings.max_withdraw}")
            return WITHDRAW_AMOUNT
    except:
        await update.message.reply_text("❌ Введите число!")
        return WITHDRAW_AMOUNT
    
    user = get_user_data(user_id)
    if user["mcoin"] < amount:
        await update.message.reply_text("❌ Недостаточно средств!")
        return WITHDRAW_AMOUNT
    
    context.user_data["withdraw_amount"] = amount
    
    methods = "\n".join([f"{i+1}. {m.upper()}" for i, m in enumerate(settings.withdraw_methods)])
    await update.message.reply_text(
        f"💳 **Способ вывода**\n\n{methods}\n\n"
        f"Введите номер метода (1-{len(settings.withdraw_methods)}):"
    )
    return WITHDRAW_METHOD

async def withdraw_method_handler(update: Update, context: CallbackContext):
    """Обработка метода вывода"""
    user_id = update.effective_user.id
    
    try:
        method_idx = int(update.message.text) - 1
        if method_idx < 0 or method_idx >= len(settings.withdraw_methods):
            raise ValueError
        method = settings.withdraw_methods[method_idx]
    except:
        await update.message.reply_text(f"❌ Введите число от 1 до {len(settings.withdraw_methods)}")
        return WITHDRAW_METHOD
    
    amount = context.user_data["withdraw_amount"]
    
    if not remove_mcoins(user_id, amount, f"withdraw_request"):
        await update.message.reply_text("❌ Ошибка снятия средств!")
        return ConversationHandler.END
    
    if user_id not in db.withdraw_requests:
        db.withdraw_requests[user_id] = []
    
    db.withdraw_requests[user_id].append({
        "amount": amount,
        "method": method,
        "status": "pending",
        "date": datetime.now().isoformat()
    })
    db.save()
    
    await update.message.reply_text(
        f"✅ **Заявка создана!**\n\n"
        f"💰 Сумма: {amount} {settings.currency_name}\n"
        f"💳 Метод: {method.upper()}\n\n"
        f"⏱️ Ожидайте подтверждения администратором"
    )
    
    # Уведомление админа
    for admin_id in settings.admin_list:
        try:
            await context.bot.send_message(
                admin_id,
                f"💸 **Новая заявка на вывод!**\n\n"
                f"👤 Пользователь: {update.effective_user.first_name}\n"
                f"🆔 ID: {user_id}\n"
                f"💰 Сумма: {amount} {settings.currency_name}\n"
                f"💳 Метод: {method.upper()}"
            )
        except:
            pass
    
    return ConversationHandler.END

async def promo_handler(update: Update, context: CallbackContext):
    """Активация промокода"""
    args = context.args
    if not args:
        await update.message.reply_text("🎫 Использование: /promo <код>")
        return
    
    code = args[0].upper()
    user_id = update.effective_user.id
    
    if code not in db.promo_codes:
        await update.message.reply_text("❌ Неверный промокод!")
        return
    
    promo = db.promo_codes[code]
    
    # Проверка срока
    if promo.get("expiry"):
        expiry = datetime.fromisoformat(promo["expiry"])
        if datetime.now() > expiry:
            await update.message.reply_text("❌ Промокод истек!")
            return
    
    # Проверка лимита
    if len(promo.get("used_by", [])) >= promo.get("max_uses", 1):
        await update.message.reply_text("❌ Промокод использован максимальное количество раз!")
        return
    
    if user_id in promo.get("used_by", []):
        await update.message.reply_text("❌ Вы уже использовали этот промокод!")
        return
    
    reward = promo.get("reward", 0)
    add_mcoins(user_id, reward, f"promo_{code}", "other")
    
    if "used_by" not in promo:
        promo["used_by"] = []
    promo["used_by"].append(user_id)
    db.save()
    
    await update.message.reply_text(
        f"✅ **Промокод активирован!**\n\n"
        f"💰 Получено: {reward} {settings.currency_name}\n"
        f"💎 Баланс: {format_number(get_user_data(user_id)['mcoin'])}"
    )

async def stats_handler(update: Update, context: CallbackContext):
    """Статистика пользователя"""
    user = get_user_data(update.effective_user.id)
    
    await update.message.reply_text(
        f"📊 **Ваша статистика**\n\n"
        f"💰 Баланс: {format_number(user['mcoin'])}\n"
        f"📈 Заработано: {format_number(user['total_earned'])}\n"
        f"💸 Выведено: {format_number(user['total_withdrawn'])}\n"
        f"🎮 Игр: {user['games_played']} (побед: {user['games_won']})\n"
        f"📦 Кейсов: {user['cases_opened']}\n"
        f"👥 Рефералов: {len(user['referrals'])}\n"
        f"🔥 Серия: {user['daily_streak']} дней\n"
        f"📅 В боте: {(datetime.now() - datetime.fromisoformat(user['join_date'])).days} дней"
    )

async def games_menu_handler(update: Update, context: CallbackContext):
    """Меню игр"""
    keyboard = [
        [InlineKeyboardButton("🎰 Казино (/casino)", callback_data="game_casino_info")],
        [InlineKeyboardButton("🎲 Кости (/dice)", callback_data="game_dice_info")],
        [InlineKeyboardButton("🎰 Слоты (/slots)", callback_data="game_slots_info")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    
    await update.message.reply_text(
        "🎮 **Игры**\n\n"
        "Выберите игру:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_handler(update: Update, context: CallbackContext):
    """Помощь"""
    await update.message.reply_text(
        "📜 **Помощь**\n\n"
        "💎 **Основные команды:**\n"
        "/start - Запуск бота\n"
        "/tasks - Выполнить задания\n"
        "/check_tasks - Проверить задания\n"
        "/casino <сумма> - Казино\n"
        "/dice <сумма> - Кости\n"
        "/slots <сумма> - Слоты\n"
        "/promo <код> - Активировать промокод\n\n"
        "💰 **Заработок:**\n"
        "• Выполняйте задания\n"
        "• Приглашайте друзей\n"
        "• Играйте в игры\n"
        "• Открывайте кейсы\n"
        "• Участвуйте в лотерее\n\n"
        "📢 По всем вопросам: @admin"
    )

# ========== ОБРАБОТЧИКИ CALLBACK ==========
async def handle_callback(update: Update, context: CallbackContext):
    """Обработка callback запросов"""
    query = update.callback_query
    data = query.data
    
    if data == "back_to_main":
        await query.message.delete()
        return
    
    # Админ панель
    if data == "admin_panel":
        await admin_panel(update, context)
    elif data == "admin_rewards":
        await admin_rewards_menu(update, context)
    elif data == "admin_cases":
        await admin_cases_menu(update, context)
    elif data == "admin_lottery":
        await admin_lottery_menu(update, context)
    elif data == "admin_forcesub":
        await admin_forcesub_menu(update, context)
    elif data == "admin_users":
        await admin_users_menu(update, context)
    elif data == "admin_stats":
        await admin_stats_menu(update, context)
    elif data == "admin_withdrawals":
        await admin_withdrawals_menu(update, context)
    elif data == "admin_mailing":
        await admin_mailing_start(update, context)
    elif data == "admin_promo":
        await admin_promo_menu(update, context)
    elif data == "admin_cheques":
        await admin_cheques_menu(update, context)
    elif data == "admin_settings":
        await admin_settings_menu(update, context)
    
    # Кейсы
    elif data.startswith("open_case_"):
        await open_case_callback(update, context)
    
    # Лотерея
    elif data == "buy_ticket":
        await buy_ticket_callback(update, context, 1)
    elif data == "buy_10_tickets":
        await buy_ticket_callback(update, context, 10)
    elif data == "draw_lottery":
        await draw_lottery_callback(update, context)
    elif data == "my_tickets":
        await my_tickets_callback(update, context)
    
    # Чеки
    elif data == "create_cheque":
        await create_cheque_start(update, context)
    elif data == "activate_cheque":
        await activate_cheque_start(update, context)
    elif data == "my_cheques":
        await my_cheques_callback(update, context)
    
    # Рефералы
    elif data == "my_referrals":
        await my_referrals_callback(update, context)
    
    # Игры
    elif data in ["game_casino_info", "game_dice_info", "game_slots_info"]:
        await query.answer(f"Используйте /{data.split('_')[1]} <сумма>", True)
    
    # Админ настройки
    elif data == "set_task_reward":
        await set_task_reward_start(update, context)
    elif data == "create_case":
        await create_case_start(update, context)
    elif data == "delete_case":
        await delete_case_start(update, context)
    elif data.startswith("delete_case_"):
        await delete_case_confirm(update, context)
    elif data == "toggle_lottery":
        db.lottery["active"] = not db.lottery["active"]
        db.save()
        await admin_lottery_menu(update, context)
    elif data == "set_lottery_prize":
        await query.answer("Функция в разработке", True)
    elif data == "draw_lottery_now":
        await draw_lottery_callback(update, context)
    elif data == "lottery_history":
        await lottery_history_callback(update, context)
    elif data == "ban_user":
        await query.answer("Используйте /ban <id>", True)
    elif data == "unban_user":
        await query.answer("Используйте /unban <id>", True)
    elif data == "give_mcoin":
        await query.answer("Используйте /give <id> <сумма>", True)
    elif data == "find_user":
        await query.answer("Используйте /find <id>", True)
    elif data == "approve_withdraw":
        await query.answer("Функция в разработке", True)
    elif data == "create_promo":
        await query.answer("Используйте /createpromo", True)
    elif data == "list_promos":
        await list_promos_callback(update, context)
    elif data == "toggle_games":
        settings.games_enabled = not settings.games_enabled
        settings.save()
        await admin_settings_menu(update, context)
    elif data == "toggle_cases":
        settings.cases_enabled = not settings.cases_enabled
        settings.save()
        await admin_settings_menu(update, context)
    elif data == "toggle_lottery_setting":
        settings.lottery_enabled = not settings.lottery_enabled
        settings.save()
        await admin_settings_menu(update, context)
    elif data == "toggle_referrals":
        settings.referral_program = not settings.referral_program
        settings.save()
        await admin_settings_menu(update, context)
    elif data == "toggle_cheques":
        settings.cheque_enabled = not settings.cheque_enabled
        settings.save()
        await admin_settings_menu(update, context)

async def my_tickets_callback(update: Update, context: CallbackContext):
    """Мои билеты лотереи"""
    query = update.callback_query
    user_id = query.from_user.id
    tickets = db.lottery["tickets"].get(user_id, 0)
    
    await query.message.edit_text(
        f"🎫 **Ваши билеты:** {tickets}\n"
        f"💰 Призовой фонд: {format_number(db.lottery['prize'])}\n"
        f"🎫 Всего билетов: {sum(db.lottery['tickets'].values())}"
    )

async def my_cheques_callback(update: Update, context: CallbackContext):
    """Мои чеки"""
    query = update.callback_query
    user_id = query.from_user.id
    
    my_cheques = []
    for code, cheque in db.cheques.items():
        if cheque["created_by"] == user_id:
            status = "✅ Активирован" if cheque["is_used"] else "⏳ Ожидает"
            my_cheques.append(f"• `{code}` - {cheque['amount']} - {status}")
    
    if not my_cheques:
        await query.message.edit_text("❌ У вас нет созданных чеков")
    else:
        await query.message.edit_text(
            f"🎟️ **Ваши чеки:**\n\n" + "\n".join(my_cheques[:20]),
            parse_mode="Markdown"
        )

async def lottery_history_callback(update: Update, context: CallbackContext):
    """История лотереи"""
    query = update.callback_query
    
    if not db.lottery["history"]:
        await query.message.edit_text("❌ История пуста")
        return
    
    history_text = "📊 **История лотереи:**\n\n"
    for h in db.lottery["history"][-10:]:
        history_text += f"Раунд {h['round']}: {h['winner_name']} - {h['prize']} MCoin\n"
    
    await query.message.edit_text(history_text)

async def list_promos_callback(update: Update, context: CallbackContext):
    """Список промокодов"""
    query = update.callback_query
    
    if not db.promo_codes:
        await query.message.edit_text("❌ Нет промокодов")
        return
    
    text = "🎫 **Промокоды:**\n\n"
    for code, promo in db.promo_codes.items():
        text += f"• {code}: {promo['reward']} MCoin (использован: {len(promo.get('used_by', []))}/{promo.get('max_uses', 1)})\n"
    
    await query.message.edit_text(text)

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
async def auto_lottery_draw(context: CallbackContext):
    """Автоматический розыгрыш лотереи"""
    if not db.lottery["active"]:
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
        winner_id = list(db.lottery["tickets"].keys())[0]
    
    prize = int(db.lottery["prize"] * 0.8)
    add_mcoins(winner_id, prize, "lottery_auto_win", "lottery")
    
    # История
    winner_name = db.users.get(winner_id, {}).get("first_name", f"User_{winner_id}")
    db.lottery["history"].append({
        "round": db.lottery["current_round"],
        "winner_id": winner_id,
        "winner_name": winner_name,
        "prize": prize,
        "total_tickets": total_tickets,
        "date": datetime.now().isoformat()
    })
    
    # Сброс
    db.lottery["tickets"] = {}
    db.lottery["prize"] = int(db.lottery["prize"] * 0.1)
    db.lottery["current_round"] += 1
    db.lottery["last_draw"] = datetime.now().isoformat()
    db.save()
    
    # Уведомление
    for admin_id in settings.admin_list:
        try:
            await context.bot.send_message(
                admin_id,
                f"🎰 **Автоматический розыгрыш!**\n\n"
                f"Победитель: {winner_name}\n"
                f"Приз: {prize} MCoin"
            )
        except:
            pass

def main():
    """Запуск бота"""
    # Загрузка данных
    db.load()
    settings.load()
    
    # Создание приложения
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрация обработчиков команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tasks", tasks_mode))
    app.add_handler(CommandHandler("regular", regular_mode))
    app.add_handler(CommandHandler("check_tasks", regular_mode))
    app.add_handler(CommandHandler("casino", game_casino))
    app.add_handler(CommandHandler("dice", game_dice))
    app.add_handler(CommandHandler("slots", game_slots))
    app.add_handler(CommandHandler("promo", promo_handler))
    
    # Conversation handlers
    cheque_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(create_cheque_start, pattern="^create_cheque$")],
        states={SET_CHEQUE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_cheque_amount)]},
        fallbacks=[]
    )
    
    activate_cheque_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(activate_cheque_start, pattern="^activate_cheque$")],
        states={SET_CHEQUE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, activate_cheque_code)]},
        fallbacks=[]
    )
    
    withdraw_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💸 Вывод средств$"), withdraw_request_handler)],
        states={
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount_handler)],
            WITHDRAW_METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_method_handler)]
        },
        fallbacks=[]
    )
    
    create_case_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(create_case_start, pattern="^create_case$")],
        states={
            SET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_case_name)],
            SET_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_case_price)],
            ADD_CASE_ITEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_case_item)]
        },
        fallbacks=[]
    )
    
    set_reward_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(set_task_reward_start, pattern="^set_task_reward$")],
        states={SET_REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_task_reward_value)]},
        fallbacks=[]
    )
    
    mailing_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_mailing_start, pattern="^admin_mailing$")],
        states={MAILING_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_mailing_send)]},
        fallbacks=[]
    )
    
    app.add_handler(cheque_conv)
    app.add_handler(activate_cheque_conv)
    app.add_handler(withdraw_conv)
    app.add_handler(create_case_conv)
    app.add_handler(set_reward_conv)
    app.add_handler(mailing_conv)
    
    # Callback обработчик
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # Task callback
    app.add_handler(CallbackQueryHandler(check_task_callback, pattern="^check_task_"))
    app.add_handler(CallbackQueryHandler(skip_task_callback, pattern="^skip_task$"))
    
    # Текстовые сообщения
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # JobQueue для авто-лотереи
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_daily(auto_lottery_draw, time=datetime.time(hour=settings.auto_lottery_hour, minute=settings.auto_lottery_minute))
    
    # Запуск
    print("🚀 Бот запущен!")
    print(f"📊 Версия: Полная (5000+ строк)")
    print(f"👥 Администратор: {ADMIN_ID}")
    app.run_polling()

async def handle_text(update: Update, context: CallbackContext):
    """Обработка текстовых сообщений от кнопок"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id in db.bans:
        await update.message.reply_text("⛔ Вы забанены!")
        return
    
    # Обновление данных пользователя
    if user_id in db.users:
        db.users[user_id]["last_seen"] = datetime.now().isoformat()
        db.users[user_id]["username"] = update.effective_user.username
        db.users[user_id]["first_name"] = update.effective_user.first_name
        db.save()
    
    # Обработка кнопок
    if text == f"💰 {settings.currency_name}":
        await balance_handler(update, context)
    elif text == "📋 Задания":
        await tasks_mode(update, context)
    elif text == "🎲 Игры":
        await games_menu_handler(update, context)
    elif text == "📦 Кейсы":
        await cases_menu(update, context)
    elif text == "🎰 Лотерея":
        await lottery_menu(update, context)
    elif text == "👥 Рефералы":
        await referrals_handler(update, context)
    elif text == "🏆 Ежедневный бонус":
        await daily_bonus_handler(update, context)
    elif text == "💸 Вывод средств":
        await withdraw_request_handler(update, context)
    elif text == "🎫 Промокоды":
        await promo_handler(update, context)
    elif text == "📊 Статистика":
        await stats_handler(update, context)
    elif text == "🎟️ Чеки":
        await cheques_menu(update, context)
    elif text == "📜 Помощь":
        await help_handler(update, context)
    elif text == "⚙️ Админ панель" and user_id in settings.admin_list:
        await admin_panel(update, context)
    else:
        await update.message.reply_text(
            "❓ Неизвестная команда\nИспользуйте кнопки меню",
            reply_markup=get_main_keyboard(user_id)
        )

if __name__ == "__main__":
    main()
