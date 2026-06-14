import asyncio
import random
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, List
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

# ========== КОНФИГУРАЦИЯ (ВСЕ НАСТРАИВАЕТСЯ ЗДЕСЬ) ==========
BOT_TOKEN = "8251949164:AAEUSmnhX_S4p-vWDD4fvC6mDclV0LvIFe0"
BOTOHUB_TOKEN = "3feed57e-9303-4343-8d87-ed8d9dd5650f"
BOTOHUB_API_URL = "https://botohub.me/get-tasks"
ADMIN_ID = 5356400377  # ID администратора

# Настройки валюты
START_MCOINS = 100
REWARD_FOR_TASK = 50  # Награда за выполнение задания
LOTTERY_TICKET_PRICE = 10
LOTTERY_DURATION_HOURS = 24

# Настройки кейсов
CASES = {
    "common": {
        "name": "📦 Обычный кейс",
        "price": 50,
        "items": [
            {"name": "10 MCoin", "reward": 10, "chance": 40},
            {"name": "20 MCoin", "reward": 20, "chance": 30},
            {"name": "50 MCoin", "reward": 50, "chance": 20},
            {"name": "100 MCoin", "reward": 100, "chance": 9},
            {"name": "500 MCoin (ДЖЕКПОТ!)", "reward": 500, "chance": 1}
        ]
    },
    "rare": {
        "name": "✨ Редкий кейс",
        "price": 200,
        "items": [
            {"name": "50 MCoin", "reward": 50, "chance": 35},
            {"name": "100 MCoin", "reward": 100, "chance": 30},
            {"name": "250 MCoin", "reward": 250, "chance": 20},
            {"name": "500 MCoin", "reward": 500, "chance": 10},
            {"name": "1000 MCoin (ДЖЕКПОТ!)", "reward": 1000, "chance": 5}
        ]
    },
    "legendary": {
        "name": "🔥 Легендарный кейс",
        "price": 500,
        "items": [
            {"name": "200 MCoin", "reward": 200, "chance": 30},
            {"name": "500 MCoin", "reward": 500, "chance": 25},
            {"name": "1000 MCoin", "reward": 1000, "chance": 20},
            {"name": "2500 MCoin", "reward": 2500, "chance": 15},
            {"name": "5000 MCoin (ДЖЕКПОТ!)", "reward": 5000, "chance": 10}
        ]
    }
}

# Настройки игр
GAMES = {
    "coinflip": {"name": "🪙 Орёл/Решка", "min_bet": 10, "max_bet": 1000},
    "dice": {"name": "🎲 Кость", "min_bet": 10, "max_bet": 1000},
    "slots": {"name": "🎰 Слоты", "min_bet": 25, "max_bet": 500}
}

# Обязательные подписки (каналы для проверки через Botohost)
REQUIRED_CHANNELS = [
    {"id": "@channel1", "url": "https://t.me/channel1"},
    {"id": "@channel2", "url": "https://t.me/channel2"}
]

# Структуры данных (хранятся в памяти)
user_balances: Dict[int, int] = {}  # баланс MCoin
user_stats: Dict[int, Dict] = defaultdict(lambda: {"tasks_completed": 0, "games_played": 0, "cases_opened": 0})
user_lottery_tickets: Dict[int, int] = defaultdict(int)
active_lottery: Dict = {"tickets": {}, "total_tickets": 0, "end_time": None, "prize_pool": 0}
daily_bonus: Dict[int, str] = {}  # последняя дата получения бонуса
referrals: Dict[int, List[int]] = defaultdict(list)
user_referrer: Dict[int, int] = {}
pending_tasks: Dict[int, Dict] = {}  # ожидающие проверки задания
banned_users: set = set()  # забаненные пользователи
admin_settings: Dict = {
    "task_reward": REWARD_FOR_TASK,
    "lottery_ticket_price": LOTTERY_TICKET_PRICE,
    "mining_rate": 1  # MCoin в час за майнинг
}

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def save_data():
    """Сохраняет данные в JSON файлы"""
    data = {
        "balances": user_balances,
        "stats": dict(user_stats),
        "lottery_tickets": dict(user_lottery_tickets),
        "referrals": dict(referrals),
        "user_referrer": user_referrer,
        "banned_users": list(banned_users),
        "admin_settings": admin_settings
    }
    with open("bot_data.json", "w") as f:
        json.dump(data, f)

def load_data():
    """Загружает данные из JSON файлов"""
    global user_balances, user_stats, user_lottery_tickets, referrals, user_referrer, banned_users, admin_settings
    if os.path.exists("bot_data.json"):
        with open("bot_data.json", "r") as f:
            data = json.load(f)
            user_balances = data.get("balances", {})
            user_stats = defaultdict(lambda: {"tasks_completed": 0, "games_played": 0, "cases_opened": 0}, data.get("stats", {}))
            user_lottery_tickets = defaultdict(int, data.get("lottery_tickets", {}))
            referrals = defaultdict(list, data.get("referrals", {}))
            user_referrer = data.get("user_referrer", {})
            banned_users = set(data.get("banned_users", []))
            admin_settings = data.get("admin_settings", admin_settings)

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

    headers = {"Content-Type": "application/json", "Auth": BOTOHUB_TOKEN}

    async with aiohttp.ClientSession() as session:
        async with session.post(BOTOHUB_API_URL, json=payload, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                error_text = await resp.text()
                raise Exception(f"API ошибка {resp.status}: {error_text}")

async def check_subscriptions(user_id: int) -> bool:
    """Проверяет, подписан ли пользователь на обязательные каналы"""
    # Здесь должна быть реальная проверка через Botostore API
    # Для примера возвращаем True
    return True

async def add_mcoins(user_id: int, amount: int, reason: str = ""):
    """Добавляет MCoin пользователю"""
    if user_id not in user_balances:
        user_balances[user_id] = START_MCOINS
    user_balances[user_id] += amount
    save_data()
    if reason:
        print(f"Добавлено {amount} MCoin пользователю {user_id} ({reason})")

async def remove_mcoins(user_id: int, amount: int) -> bool:
    """Снимает MCoin, возвращает True если достаточно средств"""
    if user_balances.get(user_id, 0) >= amount:
        user_balances[user_id] -= amount
        save_data()
        return True
    return False

# ========== ОСНОВНОЕ МЕНЮ ==========
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if user_id in banned_users:
        await update.message.reply_text("⛔ Вы забанены в боте!")
        return
    
    # Проверка подписок
    if not await check_subscriptions(user_id):
        keyboard = []
        for channel in REQUIRED_CHANNELS:
            keyboard.append([InlineKeyboardButton(f"📢 Подписаться на {channel['id']}", url=channel['url'])])
        keyboard.append([InlineKeyboardButton("✅ Проверить подписки", callback_data="check_subs")])
        await update.message.reply_text(
            "⚠️ Для использования бота необходимо подписаться на наши каналы!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Реферальная система
    if context.args and context.args[0].isdigit() and int(context.args[0]) != user_id:
        referrer_id = int(context.args[0])
        if referrer_id not in user_referrer and referrer_id not in referrals[user_id]:
            user_referrer[user_id] = referrer_id
            referrals[referrer_id].append(user_id)
            await add_mcoins(referrer_id, 50, f"реферал {user_id}")
            await add_mcoins(user_id, 25, "приветственный бонус за реферала")
    
    # Инициализация
    if user_id not in user_balances:
        user_balances[user_id] = START_MCOINS
        await add_mcoins(user_id, START_MCOINS, "приветственный бонус")
        save_data()
    
    keyboard = [
        [InlineKeyboardButton("💰 Профиль", callback_data="profile")],
        [InlineKeyboardButton("📋 Задания BotoHub", callback_data="tasks_menu")],
        [InlineKeyboardButton("🎮 Игры", callback_data="games_menu")],
        [InlineKeyboardButton("📦 Кейсы", callback_data="cases_menu")],
        [InlineKeyboardButton("🎲 Лотерея", callback_data="lottery")],
        [InlineKeyboardButton("⭐ Реферальная система", callback_data="referral")],
        [InlineKeyboardButton("⛏️ Майнинг", callback_data="mining")],
        [InlineKeyboardButton("🎁 Ежедневный бонус", callback_data="daily_bonus")]
    ]
    
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel")])
    
    await update.message.reply_text(
        f"👋 Добро пожаловать, {update.effective_user.first_name}!\n\n"
        f"💰 Баланс: {user_balances.get(user_id, 0)} MCoin\n\n"
        f"Выполняй задания, играй в игры и открывай кейсы, чтобы зарабатывать MCoin!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ========== ПРОФИЛЬ ==========
async def profile_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    
    stats = user_stats[user_id]
    text = (
        f"📊 **Ваш профиль**\n\n"
        f"💰 Баланс: {user_balances.get(user_id, 0)} MCoin\n"
        f"✅ Выполнено заданий: {stats['tasks_completed']}\n"
        f"🎮 Сыграно игр: {stats['games_played']}\n"
        f"📦 Открыто кейсов: {stats['cases_opened']}\n"
        f"🎫 Лотерейных билетов: {user_lottery_tickets[user_id]}\n"
    )
    
    if user_id in user_referrer:
        text += f"\n👤 Пригласил: @{user_referrer[user_id]}"
    
    await query.message.edit_text(text, parse_mode="Markdown")
    await query.answer()

# ========== ЗАДАНИЯ BOTOHUB ==========
async def tasks_menu_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    keyboard = [
        [InlineKeyboardButton("📋 Обычные задания", callback_data="regular_tasks")],
        [InlineKeyboardButton("⭐ Продвинутые задания", callback_data="advanced_tasks")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
    ]
    await query.message.edit_text(
        "📋 **Выберите тип заданий:**\n\n"
        "Обычные - получаете все задания сразу\n"
        "Продвинутые - задания по одному с проверкой",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    await query.answer()

async def regular_tasks(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.message.edit_text("🔄 Получаем список заданий...")
    
    try:
        result = await call_botohub_api(user_id, is_task=False)
        tasks = result.get("tasks", [])
        
        if not tasks:
            await query.message.edit_text("🎉 На данный момент нет активных заданий!")
            return
        
        for url in tasks:
            keyboard = [[InlineKeyboardButton("✅ Выполнено", callback_data=f"complete_task_{url}")]]
            await query.message.reply_text(
                f"📌 **Задание:**\n{url}\n\nНаграда: +{admin_settings['task_reward']} MCoin",
                reply_markup=InlineKeyboardMarkup(keyboard),
                disable_web_page_preview=True,
                parse_mode="Markdown"
            )
        
        await query.message.edit_text("✅ Задания отправлены!")
    except Exception as e:
        await query.message.edit_text(f"❌ Ошибка: {e}")
    
    await query.answer()

async def advanced_tasks(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.message.edit_text("🔄 Получаем задание...")
    
    try:
        result = await call_botohub_api(user_id, is_task=True)
        tasks = result.get("tasks", [])
        
        if not tasks:
            await query.message.edit_text("🎉 На данный момент нет заданий!")
            return
        
        task_url = tasks[0]
        pending_tasks[user_id] = {"url": task_url, "timestamp": datetime.now()}
        
        keyboard = [
            [InlineKeyboardButton("✅ Я выполнил", callback_data="check_advanced_task")],
            [InlineKeyboardButton("❌ Пропустить", callback_data="skip_advanced_task")]
        ]
        
        await query.message.edit_text(
            f"📢 **Продвинутое задание:**\n{task_url}\n\n"
            f"1. Перейдите по ссылке\n"
            f"2. Подпишитесь на канал\n"
            f"3. Нажмите «Я выполнил»\n\n"
            f"🏆 Награда: +{admin_settings['task_reward']} MCoin",
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True,
            parse_mode="Markdown"
        )
    except Exception as e:
        await query.message.edit_text(f"❌ Ошибка: {e}")
    
    await query.answer()

async def check_advanced_task(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in pending_tasks:
        await query.answer("Нет активных заданий!")
        return
    
    await query.message.edit_text("🔍 Проверяем выполнение...")
    
    try:
        result = await call_botohub_api(user_id, is_task=True)
        
        if result.get("prev_success", False):
            # Задание выполнено
            reward = admin_settings['task_reward']
            await add_mcoins(user_id, reward, "выполнение задания")
            user_stats[user_id]["tasks_completed"] += 1
            del pending_tasks[user_id]
            
            await query.message.edit_text(
                f"✅ **Задание выполнено!**\n\n"
                f"💰 Вы получили: +{reward} MCoin\n"
                f"📊 Новый баланс: {user_balances[user_id]} MCoin"
            )
        else:
            # Задание не выполнено
            await query.message.edit_text(
                f"❌ **Задание не выполнено!**\n\n"
                f"Пожалуйста, убедитесь что вы:\n"
                f"1. Подписались на канал\n"
                f"2. Подождали 3 минуты\n\n"
                f"После выполнения нажмите кнопку снова."
            )
    except Exception as e:
        await query.message.edit_text(f"❌ Ошибка: {e}")
    
    await query.answer()

async def skip_advanced_task(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id in pending_tasks:
        del pending_tasks[user_id]
    
    await query.message.edit_text("⏩ Задание пропущено! Начните новое командой /tasks")
    await query.answer()

async def complete_task_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    task_url = query.data.replace("complete_task_", "")
    
    await add_mcoins(user_id, admin_settings['task_reward'], "выполнение задания")
    user_stats[user_id]["tasks_completed"] += 1
    
    await query.message.edit_text(
        f"✅ **Задание выполнено!**\n\n"
        f"💰 Вы получили: +{admin_settings['task_reward']} MCoin\n"
        f"📊 Новый баланс: {user_balances[user_id]} MCoin"
    )
    await query.answer()

# ========== ИГРЫ ==========
async def games_menu_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    keyboard = []
    
    for game_id, game_info in GAMES.items():
        keyboard.append([InlineKeyboardButton(game_info['name'], callback_data=f"game_{game_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])
    
    await query.message.edit_text(
        "🎮 **Выберите игру:**\n\n"
        "Играйте и выигрывайте MCoin!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    await query.answer()

async def game_coinflip(update: Update, context: CallbackContext, bet: int):
    user_id = update.effective_user.id
    
    if bet < GAMES["coinflip"]["min_bet"] or bet > GAMES["coinflip"]["max_bet"]:
        return "❌ Неверная ставка!"
    
    if not await remove_mcoins(user_id, bet):
        return "❌ Недостаточно MCoin!"
    
    result = random.choice(["Орёл", "Решка"])
    user_choice = random.choice(["Орёл", "Решка"])
    
    if result == user_choice:
        win = bet * 2
        await add_mcoins(user_id, win, "выигрыш в Coinflip")
        user_stats[user_id]["games_played"] += 1
        return f"🪙 {result}! Вы угадали!\n💰 Выигрыш: +{win} MCoin"
    else:
        user_stats[user_id]["games_played"] += 1
        return f"🪙 {result}... Вы проиграли.\n💸 Потеряно: -{bet} MCoin"

async def game_dice(update: Update, context: CallbackContext, bet: int):
    user_id = update.effective_user.id
    
    if bet < GAMES["dice"]["min_bet"] or bet > GAMES["dice"]["max_bet"]:
        return "❌ Неверная ставка!"
    
    if not await remove_mcoins(user_id, bet):
        return "❌ Недостаточно MCoin!"
    
    player_roll = random.randint(1, 6)
    bot_roll = random.randint(1, 6)
    
    if player_roll > bot_roll:
        win = bet * 2
        await add_mcoins(user_id, win, "выигрыш в Dice")
        user_stats[user_id]["games_played"] += 1
        return f"🎲 Ваша кость: {player_roll}\n🤖 Кость бота: {bot_roll}\n✅ Вы победили!\n💰 Выигрыш: +{win} MCoin"
    elif player_roll < bot_roll:
        user_stats[user_id]["games_played"] += 1
        return f"🎲 Ваша кость: {player_roll}\n🤖 Кость бота: {bot_roll}\n❌ Вы проиграли!\n💸 Потеряно: -{bet} MCoin"
    else:
        await add_mcoins(user_id, bet, "ничья в Dice")
        return f"🎲 Ваша кость: {player_roll}\n🤖 Кость бота: {bot_roll}\n🤝 Ничья! Ставка возвращена."

async def game_slots(update: Update, context: CallbackContext, bet: int):
    user_id = update.effective_user.id
    
    if bet < GAMES["slots"]["min_bet"] or bet > GAMES["slots"]["max_bet"]:
        return "❌ Неверная ставка!"
    
    if not await remove_mcoins(user_id, bet):
        return "❌ Недостаточно MCoin!"
    
    slots = ["🍒", "🍋", "🍊", "7️⃣", "💎"]
    result = [random.choice(slots) for _ in range(3)]
    
    if result[0] == result[1] == result[2]:
        win = bet * 5
        await add_mcoins(user_id, win, "ДЖЕКПОТ в Слотах")
        user_stats[user_id]["games_played"] += 1
        return f"🎰 {' | '.join(result)}\n\n🎉 **ДЖЕКПОТ!**\n💰 Выигрыш: +{win} MCoin"
    elif result[0] == result[1] or result[1] == result[2]:
        win = bet * 2
        await add_mcoins(user_id, win, "выигрыш в Слотах")
        user_stats[user_id]["games_played"] += 1
        return f"🎰 {' | '.join(result)}\n\n✅ Выигрыш!\n💰 +{win} MCoin"
    else:
        user_stats[user_id]["games_played"] += 1
        return f"🎰 {' | '.join(result)}\n\n❌ Проигрыш!\n💸 -{bet} MCoin"

# ========== КЕЙСЫ ==========
async def cases_menu_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    keyboard = []
    
    for case_id, case_info in CASES.items():
        keyboard.append([InlineKeyboardButton(f"{case_info['name']} - {case_info['price']} MCoin", callback_data=f"open_case_{case_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])
    
    await query.message.edit_text(
        "📦 **Выберите кейс для открытия:**\n\n"
        "Каждый кейс содержит разные предметы и шансы!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    await query.answer()

async def open_case(update: Update, context: CallbackContext, case_id: str):
    query = update.callback_query
    user_id = query.from_user.id
    
    if case_id not in CASES:
        await query.answer("Кейс не найден!")
        return
    
    case = CASES[case_id]
    price = case["price"]
    
    if not await remove_mcoins(user_id, price):
        await query.answer("❌ Недостаточно MCoin!", show_alert=True)
        return
    
    # Выбор предмета с учетом шансов
    rand = random.randint(1, 100)
    cumulative = 0
    selected_item = None
    
    for item in case["items"]:
        cumulative += item["chance"]
        if rand <= cumulative:
            selected_item = item
            break
    
    reward = selected_item["reward"]
    await add_mcoins(user_id, reward, f"открытие кейса {case['name']}")
    user_stats[user_id]["cases_opened"] += 1
    
    await query.message.edit_text(
        f"🎉 **Вы открыли {case['name']}**\n\n"
        f"📦 Вам выпало: {selected_item['name']}\n"
        f"💰 Награда: +{reward} MCoin\n\n"
        f"📊 Новый баланс: {user_balances[user_id]} MCoin",
        parse_mode="Markdown"
    )
    await query.answer()

# ========== ЛОТЕРЕЯ ==========
async def lottery_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    
    if active_lottery["end_time"] is None or datetime.now() > active_lottery["end_time"]:
        # Создаем новую лотерею
        active_lottery["end_time"] = datetime.now() + timedelta(hours=LOTTERY_DURATION_HOURS)
        active_lottery["prize_pool"] = 1000  # Стартовый призовой фонд
        active_lottery["tickets"] = {}
        active_lottery["total_tickets"] = 0
    
    time_left = active_lottery["end_time"] - datetime.now()
    hours = time_left.seconds // 3600
    minutes = (time_left.seconds % 3600) // 60
    
    keyboard = [
        [InlineKeyboardButton(f"🎫 Купить билет ({admin_settings['lottery_ticket_price']} MCoin)", callback_data="buy_ticket")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
    ]
    
    await query.message.edit_text(
        f"🎲 **Лотерея**\n\n"
        f"💰 Призовой фонд: {active_lottery['prize_pool']} MCoin\n"
        f"🎫 Билетов продано: {active_lottery['total_tickets']}\n"
        f"⏰ До розыгрыша: {hours}ч {minutes}мин\n\n"
        f"Цена билета: {admin_settings['lottery_ticket_price']} MCoin\n"
        f"Победитель получит 70% призового фонда!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    await query.answer()

async def buy_ticket(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    
    price = admin_settings["lottery_ticket_price"]
    
    if not await remove_mcoins(user_id, price):
        await query.answer("❌ Недостаточно MCoin!", show_alert=True)
        return
    
    user_lottery_tickets[user_id] += 1
    active_lottery["tickets"][user_id] = active_lottery["tickets"].get(user_id, 0) + 1
    active_lottery["total_tickets"] += 1
    active_lottery["prize_pool"] += price
    
    await query.answer(f"✅ Билет куплен! У вас {user_lottery_tickets[user_id]} билетов", show_alert=True)
    await lottery_callback(update, context)

# ========== РЕФЕРАЛЫ ==========
async def referral_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    
    bot_username = context.bot.username
    referral_link = f"https://t.me/{bot_username}?start={user_id}"
    referrer_count = len(referrals[user_id])
    
    await query.message.edit_text(
        f"⭐ **Реферальная система**\n\n"
        f"👥 Приглашено друзей: {referrer_count}\n"
        f"💰 За каждого друга вы получаете: 50 MCoin\n"
        f"🎁 Друг получает: 25 MCoin\n\n"
        f"🔗 **Ваша реферальная ссылка:**\n"
        f"`{referral_link}`\n\n"
        f"Поделитесь ссылкой с друзьями и получайте бонусы!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]])
    )
    await query.answer()

# ========== МАЙНИНГ ==========
async def mining_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    
    keyboard = [
        [InlineKeyboardButton("⛏️ Начать майнинг (1 час)", callback_data="start_mining")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
    ]
    
    await query.message.edit_text(
        f"⛏️ **Майнинг MCoin**\n\n"
        f"💰 Скорость майнинга: {admin_settings['mining_rate']} MCoin/час\n"
        f"📊 Ваш баланс: {user_balances.get(user_id, 0)} MCoin\n\n"
        f"Нажмите «Начать майнинг» и получите награду через час!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    await query.answer()

async def start_mining(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    
    if "mining_end" in context.user_data and datetime.now() < context.user_data["mining_end"]:
        time_left = context.user_data["mining_end"] - datetime.now()
        minutes = time_left.seconds // 60
        await query.answer(f"Майнинг уже идет! Осталось {minutes} минут", show_alert=True)
        return
    
    context.user_data["mining_end"] = datetime.now() + timedelta(hours=1)
    
    await query.message.edit_text(
        f"⛏️ **Майнинг начат!**\n\n"
        f"Через 1 час вы получите {admin_settings['mining_rate']} MCoin.\n"
        f"Вернитесь в меню майнинга через час!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="mining")]])
    )
    await query.answer()

# ========== ЕЖЕДНЕВНЫЙ БОНУС ==========
async def daily_bonus_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    if daily_bonus.get(user_id) == today:
        await query.answer("Вы уже получали бонус сегодня!", show_alert=True)
        return
    
    bonus = random.randint(50, 200)
    await add_mcoins(user_id, bonus, "ежедневный бонус")
    daily_bonus[user_id] = today
    
    await query.message.edit_text(
        f"🎁 **Ежедневный бонус получен!**\n\n"
        f"💰 Вы получили: +{bonus} MCoin\n"
        f"📊 Новый баланс: {user_balances[user_id]} MCoin",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]])
    )
    await query.answer()

# ========== АДМИН-ПАНЕЛЬ ==========
async def admin_panel_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id != ADMIN_ID:
        await query.answer("⛔ Доступ запрещен!", show_alert=True)
        return
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("💰 Выдать MCoin", callback_data="admin_give")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="admin_settings_menu")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔨 Забанить/Разбанить", callback_data="admin_ban")],
        [InlineKeyboardButton("🎁 Создать промокод", callback_data="admin_promo")],
        [InlineKeyboardButton("👥 Список пользователей", callback_data="admin_users")],
        [InlineKeyboardButton("🎲 Завершить лотерею", callback_data="admin_end_lottery")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
    ]
    
    await query.message.edit_text(
        "👑 **Админ-панель**\n\n"
        "Выберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    await query.answer()

async def admin_stats(update: Update, context: CallbackContext):
    query = update.callback_query
    
    total_users = len(user_balances)
    total_mcoins = sum(user_balances.values())
    total_tasks = sum(stats["tasks_completed"] for stats in user_stats.values())
    total_games = sum(stats["games_played"] for stats in user_stats.values())
    
    await query.message.edit_text(
        f"📊 **Статистика бота**\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"💰 Всего MCoin: {total_mcoins}\n"
        f"✅ Выполнено заданий: {total_tasks}\n"
        f"🎮 Сыграно игр: {total_games}\n"
        f"🎫 Билетов в лотерее: {active_lottery['total_tickets']}\n"
        f"🏆 Призовой фонд: {active_lottery['prize_pool']} MCoin",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 В админ-панель", callback_data="admin_panel")]])
    )
    await query.answer()

async def admin_end_lottery(update: Update, context: CallbackContext):
    query = update.callback_query
    
    if active_lottery["total_tickets"] == 0:
        await query.answer("Нет билетов в лотерее!", show_alert=True)
        return
    
    winner_id = random.choices(
        list(active_lottery["tickets"].keys()),
        weights=list(active_lottery["tickets"].values())
    )[0]
    
    prize = int(active_lottery["prize_pool"] * 0.7)
    await add_mcoins(winner_id, prize, "победа в лотерее")
    
    await query.message.edit_text(
        f"🎲 **Лотерея завершена!**\n\n"
        f"🏆 Победитель: @{winner_id}\n"
        f"💰 Выигрыш: {prize} MCoin\n\n"
        f"Остальные билеты сгорают.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 В админ-панель", callback_data="admin_panel")]])
    )
    
    # Сброс лотереи
    active_lottery["end_time"] = None
    active_lottery["tickets"] = {}
    active_lottery["total_tickets"] = 0
    active_lottery["prize_pool"] = 1000
    user_lottery_tickets.clear()
    
    await query.answer()

# ========== ОБРАБОТЧИК КНОПОК ==========
async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data
    
    if data == "main_menu":
        await start(update, context)
    elif data == "profile":
        await profile_callback(update, context)
    elif data == "tasks_menu":
        await tasks_menu_callback(update, context)
    elif data == "regular_tasks":
        await regular_tasks(update, context)
    elif data == "advanced_tasks":
        await advanced_tasks(update, context)
    elif data == "check_advanced_task":
        await check_advanced_task(update, context)
    elif data == "skip_advanced_task":
        await skip_advanced_task(update, context)
    elif data == "games_menu":
        await games_menu_callback(update, context)
    elif data == "cases_menu":
        await cases_menu_callback(update, context)
    elif data.startswith("open_case_"):
        case_id = data.replace("open_case_", "")
        await open_case(update, context, case_id)
    elif data == "lottery":
        await lottery_callback(update, context)
    elif data == "buy_ticket":
        await buy_ticket(update, context)
    elif data == "referral":
        await referral_callback(update, context)
    elif data == "mining":
        await mining_callback(update, context)
    elif data == "start_mining":
        await start_mining(update, context)
    elif data == "daily_bonus":
        await daily_bonus_callback(update, context)
    elif data == "admin_panel":
        await admin_panel_callback(update, context)
    elif data == "admin_stats":
        await admin_stats(update, context)
    elif data == "admin_end_lottery":
        await admin_end_lottery(update, context)
    elif data.startswith("complete_task_"):
        await complete_task_callback(update, context)
    elif data.startswith("game_"):
        game_id = data.replace("game_", "")
        await query.message.reply_text(f"Введите ставку для игры {GAMES[game_id]['name']} (от {GAMES[game_id]['min_bet']} до {GAMES[game_id]['max_bet']}):")
        context.user_data["pending_game"] = game_id
        await query.answer()

# ========== ОБРАБОТЧИК СООБЩЕНИЙ ==========
async def handle_message(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if "pending_game" in context.user_data:
        try:
            bet = int(update.message.text)
            game_id = context.user_data["pending_game"]
            
            if game_id == "coinflip":
                result = await game_coinflip(update, context, bet)
            elif game_id == "dice":
                result = await game_dice(update, context, bet)
            elif game_id == "slots":
                result = await game_slots(update, context, bet)
            else:
                result = "❌ Игра не найдена!"
            
            await update.message.reply_text(result)
            del context.user_data["pending_game"]
        except ValueError:
            await update.message.reply_text("❌ Введите число!")

# ========== ЗАПУСК БОТА ==========
def main():
    load_data()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tasks", tasks_menu_callback))
    app.add_handler(CommandHandler("profile", profile_callback))
    app.add_handler(CommandHandler("balance", profile_callback))
    
    # Обработчики
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Бот запущен...")
    print(f"👑 Админ ID: {ADMIN_ID}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()