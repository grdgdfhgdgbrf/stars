import asyncio
import random
import json
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from collections import defaultdict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    CallbackContext,
)
import aiohttp

# ==================================================
# ========== НАСТРАИВАЕМЫЕ КОНСТАНТЫ ==============
# ==================================================

# Токены
BOT_TOKEN = "8251949164:AAEUSmnhX_S4p-vWDD4fvC6mDclV0LvIFe0"
BOTOHUB_TOKEN = "3feed57e-9303-4343-8d87-ed8d9dd5650f"
BOTOHUB_API_URL = "https://botohub.me/get-tasks"

# ID администратора
ADMIN_ID = 5356400377

# Настройки валюты
CURRENCY_NAME = "MCoin"
START_BALANCE = 100
REFERRAL_REWARD = 50
DAILY_REWARD = 25

# Настройки заданий
TASK_REWARD = 50  # Награда за выполнение задания
TASK_HOLD_TIME = 180  # Время удержания подписки в секундах (3 минуты)

# Настройки лотереи
LOTTERY_TICKET_PRICE = 10
LOTTERY_DURATION_HOURS = 24
LOTTERY_MIN_PARTICIPANTS = 3

# Настройки кейсов
CASE_PRICES = {
    "common": 50,
    "rare": 150,
    "epic": 500,
    "legendary": 1500
}

CASE_REWARDS = {
    "common": [10, 20, 30, 40, 50],
    "rare": [50, 75, 100, 150, 200],
    "epic": [200, 300, 500, 750, 1000],
    "legendary": [1000, 1500, 2500, 5000, 10000]
}

# Обязательные подписки (ID каналов)
REQUIRED_SUBSCRIPTIONS = [
    {"id": "@example_channel", "name": "Example Channel"},
    # Добавьте другие каналы
]

# Игровые настройки
GAME_SLOT_COST = 10
GAME_SLOT_PRIZES = {
    "🍒🍒🍒": 100,
    "🍋🍋🍋": 50,
    "🍊🍊🍊": 75,
    "🔔🔔🔔": 200,
    "💎💎💎": 500
}

GAME_DICE_COST = 5
GAME_DICE_MULTIPLIER = 6

# Настройки реферальной системы
REFERRAL_BONUS = 25
REFERRAL_LEVELS = [10, 25, 50, 100, 200]

# ==================================================
# ========== СТРУКТУРЫ ДАННЫХ =====================
# ==================================================

# Хранилище данных (в памяти)
user_balances = defaultdict(int)  # Баланс пользователя
user_stats = defaultdict(lambda: {
    "tasks_completed": 0,
    "total_earned": 0,
    "referrals": [],
    "daily_claimed": None,
    "lottery_tickets": 0,
    "items": [],
    "last_slot": None
})
active_lottery = {
    "id": 0,
    "end_time": None,
    "participants": [],
    "prize_pool": 0,
    "active": False
}
user_flood = defaultdict(list)  # Антифлуд

# ==================================================
# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==============
# ==================================================

def check_flood(user_id: int) -> bool:
    """Проверка на флуд (не чаще 1 запроса в секунду)"""
    now = datetime.now()
    if user_id in user_flood:
        last_cmd = user_flood[user_id]
        if last_cmd and (now - last_cmd[-1]).seconds < 1:
            return False
    user_flood[user_id].append(now)
    if len(user_flood[user_id]) > 5:
        user_flood[user_id] = user_flood[user_id][-5:]
    return True

async def check_subscriptions(user_id: int, context: CallbackContext) -> bool:
    """Проверка обязательных подписок"""
    if not REQUIRED_SUBSCRIPTIONS:
        return True
    
    try:
        bot = context.bot
        for channel in REQUIRED_SUBSCRIPTIONS:
            try:
                chat_member = await bot.get_chat_member(chat_id=channel["id"], user_id=user_id)
                if chat_member.status in ["left", "kicked"]:
                    return False
            except:
                return False
        return True
    except:
        return False

async def call_botohub_api(chat_id: int, is_task: bool = False, skip: bool = False,
                            gender: str = None, age: str = None) -> dict:
    """Вызов API BotoHub."""
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
        async with session.post(BOTOHUB_API_URL, json=payload, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                error_text = await resp.text()
                raise Exception(f"API ошибка {resp.status}: {error_text}")

def get_main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Главное меню с кнопками"""
    keyboard = [
        [InlineKeyboardButton("💰 Баланс", callback_data="balance"),
         InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("🎮 Игры", callback_data="games_menu"),
         InlineKeyboardButton("🎁 Задания", callback_data="tasks_menu")],
        [InlineKeyboardButton("🎲 Лотерея", callback_data="lottery_menu"),
         InlineKeyboardButton("📦 Кейсы", callback_data="cases_menu")],
        [InlineKeyboardButton("👥 Рефералы", callback_data="referral_menu"),
         InlineKeyboardButton("⭐ Ежедневная награда", callback_data="daily")],
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("👑 Админ панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

# ==================================================
# ========== ОСНОВНЫЕ КОМАНДЫ =====================
# ==================================================

async def start(update: Update, context: CallbackContext):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    # Инициализация пользователя
    if user_balances[user_id] == 0:
        user_balances[user_id] = START_BALANCE
        user_stats[user_id]["total_earned"] = START_BALANCE
    
    # Проверка реферала
    if context.args and len(context.args) > 0:
        try:
            referrer_id = int(context.args[0])
            if referrer_id != user_id and user_stats[referrer_id]:
                user_stats[referrer_id]["referrals"].append(user_id)
                user_balances[referrer_id] += REFERRAL_BONUS
                user_stats[referrer_id]["total_earned"] += REFERRAL_BONUS
                await context.bot.send_message(
                    referrer_id,
                    f"🎉 Новый реферал! Вы получили {REFERRAL_BONUS} {CURRENCY_NAME}"
                )
        except:
            pass
    
    await update.message.reply_text(
        f"👋 Привет, {user_name}!\n\n"
        f"Добро пожаловать в игрового бота!\n"
        f"💰 Ваш баланс: {user_balances[user_id]} {CURRENCY_NAME}\n\n"
        f"Используйте кнопки ниже для навигации:",
        reply_markup=get_main_keyboard(user_id)
    )

async def balance(update: Update, context: CallbackContext):
    """Показать баланс"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    await query.edit_message_text(
        f"💰 **Ваш баланс:**\n"
        f"{user_balances[user_id]} {CURRENCY_NAME}\n\n"
        f"📊 **Всего заработано:** {user_stats[user_id]['total_earned']} {CURRENCY_NAME}\n"
        f"✅ **Выполнено заданий:** {user_stats[user_id]['tasks_completed']}",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(user_id)
    )

async def stats(update: Update, context: CallbackContext):
    """Показать статистику"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    await query.edit_message_text(
        f"📊 **Ваша статистика:**\n\n"
        f"💰 Баланс: {user_balances[user_id]} {CURRENCY_NAME}\n"
        f"✅ Выполнено заданий: {user_stats[user_id]['tasks_completed']}\n"
        f"👥 Приглашено рефералов: {len(user_stats[user_id]['referrals'])}\n"
        f"🎫 Лотерейных билетов: {user_stats[user_id]['lottery_tickets']}\n"
        f"💎 Предметов в инвентаре: {len(user_stats[user_id]['items'])}",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(user_id)
    )

async def daily_reward(update: Update, context: CallbackContext):
    """Ежедневная награда"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    now = datetime.now().date()
    last_claim = user_stats[user_id].get("daily_claimed")
    
    if last_claim == str(now):
        await query.edit_message_text(
            "❌ Вы уже получили ежедневную награду сегодня!\nВозвращайтесь завтра.",
            reply_markup=get_main_keyboard(user_id)
        )
        return
    
    user_balances[user_id] += DAILY_REWARD
    user_stats[user_id]["total_earned"] += DAILY_REWARD
    user_stats[user_id]["daily_claimed"] = str(now)
    
    await query.edit_message_text(
        f"⭐ **Ежедневная награда получена!**\n\n"
        f"+{DAILY_REWARD} {CURRENCY_NAME}\n"
        f"💰 Новый баланс: {user_balances[user_id]} {CURRENCY_NAME}",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(user_id)
    )

# ==================================================
# ========== ЗАДАНИЯ BOTOHUB =======================
# ==================================================

async def tasks_menu(update: Update, context: CallbackContext):
    """Меню заданий"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📋 Обычные задания", callback_data="regular_tasks")],
        [InlineKeyboardButton("🎯 Продвинутые задания", callback_data="advanced_tasks")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        "🎁 **Меню заданий**\n\n"
        "Выберите тип заданий:\n"
        "• Обычные - получаете все задания сразу\n"
        "• Продвинутые - по одному заданию с проверкой",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def regular_tasks(update: Update, context: CallbackContext):
    """Обычные задания BotoHub"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    await query.edit_message_text("🔄 Получаем список заданий...")
    
    try:
        result = await call_botohub_api(user_id, is_task=False)
        tasks = result.get("tasks", [])
        
        if not tasks:
            await query.edit_message_text(
                "🎉 На данный момент нет активных заданий.",
                reply_markup=get_main_keyboard(user_id)
            )
            return
        
        for url in tasks:
            await query.message.reply_text(
                f"📌 **Задание:**\n{url}\n\n"
                f"💰 Награда: {TASK_REWARD} {CURRENCY_NAME}\n"
                f"⏱ Время удержания: {TASK_HOLD_TIME//60} минут\n\n"
                f"После выполнения нажмите /check_task_{url.split('/')[-1]}",
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        
        # Сохраняем задания для проверки
        context.user_data["pending_tasks"] = tasks
        
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {e}")

async def advanced_tasks(update: Update, context: CallbackContext):
    """Продвинутые задания"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    await query.edit_message_text("🔄 Получаем задание...")
    
    try:
        result = await call_botohub_api(user_id, is_task=True)
        tasks = result.get("tasks", [])
        
        if not tasks:
            await query.edit_message_text(
                "🎉 Нет заданий для выполнения.",
                reply_markup=get_main_keyboard(user_id)
            )
            return
        
        task_url = tasks[0]
        context.user_data["current_task"] = task_url
        
        keyboard = [
            [InlineKeyboardButton("✅ Проверить выполнение", callback_data="check_advanced_task")],
            [InlineKeyboardButton("❌ Пропустить", callback_data="skip_advanced_task")],
            [InlineKeyboardButton("🔙 Назад", callback_data="tasks_menu")]
        ]
        
        await query.edit_message_text(
            f"🎯 **Продвинутое задание**\n\n"
            f"📢 Подпишитесь на канал:\n{task_url}\n\n"
            f"💰 Награда: {TASK_REWARD} {CURRENCY_NAME}\n"
            f"⏱ Время удержания: {TASK_HOLD_TIME//60} минут\n\n"
            f"После подписки нажмите «Проверить выполнение»",
            parse_mode="Markdown",
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {e}")

async def check_advanced_task(update: Update, context: CallbackContext):
    """Проверка выполнения продвинутого задания"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    await query.edit_message_text("🔍 Проверяем выполнение...")
    
    try:
        result = await call_botohub_api(user_id, is_task=True)
        prev_success = result.get("prev_success", False)
        
        if prev_success:
            # Задание выполнено
            reward = TASK_REWARD
            user_balances[user_id] += reward
            user_stats[user_id]["tasks_completed"] += 1
            user_stats[user_id]["total_earned"] += reward
            
            await query.edit_message_text(
                f"✅ **Задание выполнено!**\n\n"
                f"+{reward} {CURRENCY_NAME}\n"
                f"💰 Новый баланс: {user_balances[user_id]} {CURRENCY_NAME}",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard(user_id)
            )
        else:
            # Задание не выполнено
            task_url = context.user_data.get("current_task")
            await query.edit_message_text(
                f"❌ **Задание не выполнено**\n\n"
                f"Вы не подписаны на канал:\n{task_url}\n\n"
                f"Пожалуйста, подпишитесь и нажмите проверку снова.",
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
            
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {e}")

async def skip_advanced_task(update: Update, context: CallbackContext):
    """Пропуск задания"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    try:
        await call_botohub_api(user_id, is_task=True, skip=True)
        await query.edit_message_text(
            "⏩ Задание пропущено.\n\n"
            "Нажмите /start для продолжения",
            reply_markup=get_main_keyboard(user_id)
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {e}")

# ==================================================
# ========== ИГРЫ ==================================
# ==================================================

async def games_menu(update: Update, context: CallbackContext):
    """Меню игр"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🎰 Слоты", callback_data="game_slots"),
         InlineKeyboardButton("🎲 Кости", callback_data="game_dice")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        "🎮 **Выберите игру:**\n\n"
        f"🎰 Слоты - {GAME_SLOT_COST} {CURRENCY_NAME} за спин\n"
        f"🎲 Кости - {GAME_DICE_COST} {CURRENCY_NAME} за бросок",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def game_slots(update: Update, context: CallbackContext):
    """Игра в слоты"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    if user_balances[user_id] < GAME_SLOT_COST:
        await query.edit_message_text(
            f"❌ Недостаточно средств! Нужно {GAME_SLOT_COST} {CURRENCY_NAME}",
            reply_markup=get_main_keyboard(user_id)
        )
        return
    
    user_balances[user_id] -= GAME_SLOT_COST
    
    # Генерация результатов
    symbols = ["🍒", "🍋", "🍊", "🔔", "💎"]
    results = [random.choice(symbols) for _ in range(3)]
    result_str = "".join(results)
    
    prize = GAME_SLOT_PRIZES.get(result_str, 0)
    
    if prize > 0:
        user_balances[user_id] += prize
        user_stats[user_id]["total_earned"] += prize
        message = f"🎉 **ПОБЕДА!**\n{result_str}\n\nВы выиграли {prize} {CURRENCY_NAME}!"
    else:
        message = f"😢 **ПРОИГРЫШ**\n{result_str}\n\nПопробуйте еще раз!"
    
    await query.edit_message_text(
        f"{message}\n\n💰 Баланс: {user_balances[user_id]} {CURRENCY_NAME}\n"
        f"🎰 Ставка: {GAME_SLOT_COST} {CURRENCY_NAME}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎰 Еще раз", callback_data="game_slots")],
            [InlineKeyboardButton("🔙 В меню игр", callback_data="games_menu")]
        ])
    )

async def game_dice(update: Update, context: CallbackContext):
    """Игра в кости"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    if user_balances[user_id] < GAME_DICE_COST:
        await query.edit_message_text(
            f"❌ Недостаточно средств! Нужно {GAME_DICE_COST} {CURRENCY_NAME}",
            reply_markup=get_main_keyboard(user_id)
        )
        return
    
    user_balances[user_id] -= GAME_DICE_COST
    
    player_roll = random.randint(1, 6)
    bot_roll = random.randint(1, 6)
    
    if player_roll > bot_roll:
        win = GAME_DICE_COST * GAME_DICE_MULTIPLIER
        user_balances[user_id] += win
        user_stats[user_id]["total_earned"] += win
        message = f"🎉 **ВЫ ПОБЕДИЛИ!**\n\nВаш бросок: {player_roll}\nБот: {bot_roll}\nВы выиграли {win} {CURRENCY_NAME}!"
    elif player_roll < bot_roll:
        message = f"😢 **ВЫ ПРОИГРАЛИ**\n\nВаш бросок: {player_roll}\nБот: {bot_roll}\nПопробуйте еще раз!"
    else:
        user_balances[user_id] += GAME_DICE_COST
        message = f"🤝 **НИЧЬЯ!**\n\nВаш бросок: {player_roll}\nБот: {bot_roll}\nСтавка возвращена."
    
    await query.edit_message_text(
        f"{message}\n\n💰 Баланс: {user_balances[user_id]} {CURRENCY_NAME}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎲 Еще раз", callback_data="game_dice")],
            [InlineKeyboardButton("🔙 В меню игр", callback_data="games_menu")]
        ])
    )

# ==================================================
# ========== ЛОТЕРЕЯ ===============================
# ==================================================

async def lottery_menu(update: Update, context: CallbackContext):
    """Меню лотереи"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    if not active_lottery["active"]:
        await query.edit_message_text(
            "🎲 **Лотерея не активна**\n\n"
            f"Создайте новую лотерею с помощью команды /create_lottery (только для админа)",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(user_id)
        )
        return
    
    remaining = active_lottery["end_time"] - datetime.now()
    hours = remaining.seconds // 3600
    minutes = (remaining.seconds % 3600) // 60
    
    keyboard = [
        [InlineKeyboardButton(f"🎫 Купить билет ({LOTTERY_TICKET_PRICE} {CURRENCY_NAME})", 
                            callback_data="buy_ticket")],
        [InlineKeyboardButton("📊 Информация", callback_data="lottery_info")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        f"🎲 **Текущая лотерея**\n\n"
        f"💰 Призовой фонд: {active_lottery['prize_pool']} {CURRENCY_NAME}\n"
        f"👥 Участников: {len(active_lottery['participants'])}\n"
        f"⏱ Осталось времени: {hours}ч {minutes}мин\n"
        f"🎫 Ваши билеты: {user_stats[user_id]['lottery_tickets']}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def buy_ticket(update: Update, context: CallbackContext):
    """Покупка лотерейного билета"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    if not active_lottery["active"]:
        await query.edit_message_text("❌ Лотерея не активна!", reply_markup=get_main_keyboard(user_id))
        return
    
    if user_balances[user_id] < LOTTERY_TICKET_PRICE:
        await query.edit_message_text(
            f"❌ Недостаточно средств! Нужно {LOTTERY_TICKET_PRICE} {CURRENCY_NAME}",
            reply_markup=get_main_keyboard(user_id)
        )
        return
    
    user_balances[user_id] -= LOTTERY_TICKET_PRICE
    user_stats[user_id]["lottery_tickets"] += 1
    active_lottery["prize_pool"] += LOTTERY_TICKET_PRICE
    active_lottery["participants"].append(user_id)
    
    await query.edit_message_text(
        f"✅ **Билет куплен!**\n\n"
        f"💰 Ваш баланс: {user_balances[user_id]} {CURRENCY_NAME}\n"
        f"🎫 Билетов: {user_stats[user_id]['lottery_tickets']}\n"
        f"🎲 Общий призовой фонд: {active_lottery['prize_pool']} {CURRENCY_NAME}",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(user_id)
    )

async def lottery_info(update: Update, context: CallbackContext):
    """Информация о лотерее"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        f"📊 **Детали лотереи**\n\n"
        f"💰 Призовой фонд: {active_lottery['prize_pool']} {CURRENCY_NAME}\n"
        f"👥 Участников: {len(active_lottery['participants'])}\n"
        f"🎫 Цена билета: {LOTTERY_TICKET_PRICE} {CURRENCY_NAME}\n"
        f"🏆 Минимальное количество участников: {LOTTERY_MIN_PARTICIPANTS}\n\n"
        f"Победитель получит 100% призового фонда!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад", callback_data="lottery_menu")
        ]])
    )

# ==================================================
# ========== КЕЙСЫ =================================
# ==================================================

async def cases_menu(update: Update, context: CallbackContext):
    """Меню кейсов"""
    query = update.callback_query
    await query.answer()
    
    keyboard = []
    for case_type, price in CASE_PRICES.items():
        keyboard.append([InlineKeyboardButton(
            f"📦 {case_type.upper()} кейс - {price} {CURRENCY_NAME}", 
            callback_data=f"open_case_{case_type}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
    
    await query.edit_message_text(
        f"🎁 **Открытие кейсов**\n\n"
        f"Выберите тип кейса:\n"
        f"• Common - шанс получить 10-50 {CURRENCY_NAME}\n"
        f"• Rare - шанс получить 50-200 {CURRENCY_NAME}\n"
        f"• Epic - шанс получить 200-1000 {CURRENCY_NAME}\n"
        f"• Legendary - шанс получить 1000-10000 {CURRENCY_NAME}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def open_case(update: Update, context: CallbackContext, case_type: str):
    """Открытие кейса"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    price = CASE_PRICES.get(case_type)
    if not price:
        await query.edit_message_text("❌ Неверный тип кейса!")
        return
    
    if user_balances[user_id] < price:
        await query.edit_message_text(
            f"❌ Недостаточно средств! Нужно {price} {CURRENCY_NAME}",
            reply_markup=get_main_keyboard(user_id)
        )
        return
    
    user_balances[user_id] -= price
    
    rewards = CASE_REWARDS[case_type]
    reward = random.choice(rewards)
    user_balances[user_id] += reward
    user_stats[user_id]["total_earned"] += reward
    
    await query.edit_message_text(
        f"🎉 **Вы открыли {case_type.upper()} кейс!**\n\n"
        f"💰 Вы получили: +{reward} {CURRENCY_NAME}\n"
        f"💎 Новый баланс: {user_balances[user_id]} {CURRENCY_NAME}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📦 Открыть еще", callback_data="cases_menu"),
            InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")
        ]])
    )

# ==================================================
# ========== РЕФЕРАЛЬНАЯ СИСТЕМА ===================
# ==================================================

async def referral_menu(update: Update, context: CallbackContext):
    """Реферальное меню"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={user_id}"
    
    referral_count = len(user_stats[user_id]["referrals"])
    next_bonus = next((level for level in REFERRAL_LEVELS if level > referral_count), None)
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        f"👥 **Реферальная система**\n\n"
        f"Приглашайте друзей и получайте бонусы!\n\n"
        f"💰 За каждого реферала: +{REFERRAL_BONUS} {CURRENCY_NAME}\n"
        f"👥 Ваших рефералов: {referral_count}\n\n"
        f"🏆 Следующая награда: {next_bonus} рефералов\n\n"
        f"🔗 **Ваша реферальная ссылка:**\n"
        f"`{referral_link}`\n\n"
        f"Поделитесь ссылкой с друзьями!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True
    )

# ==================================================
# ========== АДМИН ПАНЕЛЬ ==========================
# ==================================================

async def admin_panel(update: Update, context: CallbackContext):
    """Админ панель"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await query.edit_message_text("❌ У вас нет доступа к админ панели!")
        return
    
    keyboard = [
        [InlineKeyboardButton("💰 Выдать валюту", callback_data="admin_give")],
        [InlineKeyboardButton("📊 Статистика бота", callback_data="admin_stats")],
        [InlineKeyboardButton("🎲 Создать лотерею", callback_data="admin_create_lottery")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="admin_settings")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        "👑 **Админ панель**\n\n"
        "Выберите действие:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_give(update: Update, context: CallbackContext):
    """Выдача валюты (админ)"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "💰 **Выдача валюты**\n\n"
        "Используйте команду:\n"
        `/give <user_id> <amount>\n\n`
        f"Пример: `/give 123456789 100`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")
        ]])
    )

async def admin_create_lottery(update: Update, context: CallbackContext):
    """Создание лотереи (админ)"""
    query = update.callback_query
    await query.answer()
    
    active_lottery["active"] = True
    active_lottery["id"] += 1
    active_lottery["end_time"] = datetime.now() + timedelta(hours=LOTTERY_DURATION_HOURS)
    active_lottery["participants"] = []
    active_lottery["prize_pool"] = 0
    
    await query.edit_message_text(
        f"✅ **Лотерея создана!**\n\n"
        f"Длительность: {LOTTERY_DURATION_HOURS} часов\n"
        f"Минимальное количество участников: {LOTTERY_MIN_PARTICIPANTS}\n"
        f"Цена билета: {LOTTERY_TICKET_PRICE} {CURRENCY_NAME}\n\n"
        f"Лотерея автоматически завершится через {LOTTERY_DURATION_HOURS} часов.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")
        ]])
    )

async def admin_stats(update: Update, context: CallbackContext):
    """Статистика бота"""
    query = update.callback_query
    await query.answer()
    
    total_users = len(user_balances)
    total_currency = sum(user_balances.values())
    total_tasks = sum(stats["tasks_completed"] for stats in user_stats.values())
    
    await query.edit_message_text(
        f"📊 **Статистика бота**\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"💰 Всего в обращении: {total_currency} {CURRENCY_NAME}\n"
        f"✅ Выполнено заданий: {total_tasks}\n"
        f"🎲 Активная лотерея: {'Да' if active_lottery['active'] else 'Нет'}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")
        ]])
    )

# ==================================================
# ========== ОБРАБОТЧИКИ НАВИГАЦИИ =================
# ==================================================

async def back_to_main(update: Update, context: CallbackContext):
    """Возврат в главное меню"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    await query.edit_message_text(
        f"👋 Главное меню\n\n💰 Баланс: {user_balances[user_id]} {CURRENCY_NAME}",
        reply_markup=get_main_keyboard(user_id)
    )

# ==================================================
# ========== ОБРАБОТЧИК КОМАНДЫ GIVE ===============
# ==================================================

async def give_command(update: Update, context: CallbackContext):
    """Команда для выдачи валюты"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет прав для этой команды!")
        return
    
    if len(context.args) != 2:
        await update.message.reply_text("Использование: /give <user_id> <amount>")
        return
    
    try:
        user_id = int(context.args[0])
        amount = int(context.args[1])
        
        user_balances[user_id] += amount
        user_stats[user_id]["total_earned"] += amount
        
        await update.message.reply_text(
            f"✅ Выдано {amount} {CURRENCY_NAME} пользователю {user_id}\n"
            f"💰 Новый баланс: {user_balances[user_id]} {CURRENCY_NAME}"
        )
        
        await context.bot.send_message(
            user_id,
            f"🎉 Вам начислено {amount} {CURRENCY_NAME} от администрации!\n"
            f"💰 Баланс: {user_balances[user_id]} {CURRENCY_NAME}"
        )
    except:
        await update.message.reply_text("❌ Неверный формат! Используйте /give <user_id> <amount>")

async def check_subscriptions_command(update: Update, context: CallbackContext):
    """Проверка обязательных подписок"""
    user_id = update.effective_user.id
    
    if not REQUIRED_SUBSCRIPTIONS:
        await update.message.reply_text("✅ Нет обязательных подписок!")
        return
    
    subscribed = await check_subscriptions(user_id, context)
    
    if subscribed:
        await update.message.reply_text(
            "✅ Все подписки активны!\n"
            "Вы можете пользоваться ботом в полном объеме."
        )
    else:
        keyboard = []
        for channel in REQUIRED_SUBSCRIPTIONS:
            keyboard.append([InlineKeyboardButton(
                f"📢 Подписаться на {channel['name']}", 
                url=f"https://t.me/{channel['id'].replace('@', '')}"
            )])
        keyboard.append([InlineKeyboardButton("🔄 Проверить", callback_data="check_subs")])
        
        await update.message.reply_text(
            "⚠️ **Для использования бота необходимо подписаться на каналы:**\n\n"
            "Подпишитесь на все каналы ниже и нажмите «Проверить»",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def force_check_subs(update: Update, context: CallbackContext):
    """Принудительная проверка подписок"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    subscribed = await check_subscriptions(user_id, context)
    
    if subscribed:
        await query.edit_message_text(
            "✅ Спасибо за подписку! Теперь вы можете пользоваться ботом.",
            reply_markup=get_main_keyboard(user_id)
        )
    else:
        await query.edit_message_text(
            "❌ Вы всё ещё не подписаны на все каналы.\n"
            "Пожалуйста, подпишитесь и попробуйте снова."
        )

# ==================================================
# ========== ЗАПУСК БОТА ===========================
# ==================================================

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("give", give_command))
    app.add_handler(CommandHandler("checksubs", check_subscriptions_command))
    
    # Callback обработчики
    app.add_handler(CallbackQueryHandler(balance, pattern="^balance$"))
    app.add_handler(CallbackQueryHandler(stats, pattern="^stats$"))
    app.add_handler(CallbackQueryHandler(daily_reward, pattern="^daily$"))
    app.add_handler(CallbackQueryHandler(tasks_menu, pattern="^tasks_menu$"))
    app.add_handler(CallbackQueryHandler(regular_tasks, pattern="^regular_tasks$"))
    app.add_handler(CallbackQueryHandler(advanced_tasks, pattern="^advanced_tasks$"))
    app.add_handler(CallbackQueryHandler(check_advanced_task, pattern="^check_advanced_task$"))
    app.add_handler(CallbackQueryHandler(skip_advanced_task, pattern="^skip_advanced_task$"))
    app.add_handler(CallbackQueryHandler(games_menu, pattern="^games_menu$"))
    app.add_handler(CallbackQueryHandler(game_slots, pattern="^game_slots$"))
    app.add_handler(CallbackQueryHandler(game_dice, pattern="^game_dice$"))
    app.add_handler(CallbackQueryHandler(lottery_menu, pattern="^lottery_menu$"))
    app.add_handler(CallbackQueryHandler(buy_ticket, pattern="^buy_ticket$"))
    app.add_handler(CallbackQueryHandler(lottery_info, pattern="^lottery_info$"))
    app.add_handler(CallbackQueryHandler(cases_menu, pattern="^cases_menu$"))
    app.add_handler(CallbackQueryHandler(referral_menu, pattern="^referral_menu$"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_give, pattern="^admin_give$"))
    app.add_handler(CallbackQueryHandler(admin_create_lottery, pattern="^admin_create_lottery$"))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(back_to_main, pattern="^back_to_main$"))
    app.add_handler(CallbackQueryHandler(force_check_subs, pattern="^check_subs$"))
    
    # Обработчики для кейсов
    for case_type in CASE_PRICES.keys():
        app.add_handler(CallbackQueryHandler(
            lambda update, context, ct=case_type: open_case(update, context, ct),
            pattern=f"^open_case_{case_type}$"
        ))
    
    print("🚀 Бот запущен с игровой системой!")
    print(f"👑 Администратор: {ADMIN_ID}")
    print(f"💰 Валюта: {CURRENCY_NAME}")
    
    # Запуск проверки лотереи
    async def check_lottery():
        while True:
            if active_lottery["active"] and active_lottery["end_time"] and datetime.now() >= active_lottery["end_time"]:
                if len(active_lottery["participants"]) >= LOTTERY_MIN_PARTICIPANTS:
                    winner = random.choice(active_lottery["participants"])
                    prize = active_lottery["prize_pool"]
                    user_balances[winner] += prize
                    user_stats[winner]["total_earned"] += prize
                    
                    for user_id in active_lottery["participants"]:
                        await app.bot.send_message(
                            user_id,
                            f"🎲 **Лотерея завершена!**\n\n"
                            f"🏆 Победитель: пользователь {winner}\n"
                            f"💰 Выигрыш: {prize} {CURRENCY_NAME}\n\n"
                            f"Спасибо за участие!"
                        )
                
                active_lottery["active"] = False
                active_lottery["participants"] = []
                active_lottery["prize_pool"] = 0
            
            await asyncio.sleep(60)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(check_lottery())
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()