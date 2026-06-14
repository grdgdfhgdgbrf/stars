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

# ============================================
# ========== КОНСТАНТЫ ДЛЯ НАСТРОЙКИ ==========
# ============================================

# Токены
BOT_TOKEN = "8251949164:AAEUSmnhX_S4p-vWDD4fvC6mDclV0LvIFe0"
BOTOHUB_TOKEN = "3feed57e-9303-4343-8d87-ed8d9dd5650f"
ADMIN_IDS = [5356400377]  # ID администраторов

# Настройки бота
BOTOHUB_API_URL = "https://botohub.me/get-tasks"
CASINO_ENABLED = True  # Включить казино
LOTTERY_ENABLED = True  # Включить лотерею
CASES_ENABLED = True  # Включить кейсы

# Настройки валюты
START_MCOINS = 100  # Начальное количество MCoin
REWARD_PER_TASK = 50  # Награда за выполнение задания
LOTTERY_TICKET_PRICE = 10  # Цена билета лотереи
LOTTERY_WIN_MULTIPLIER = 10  # Множитель выигрыша в лотерее
CASINO_MIN_BET = 10  # Минимальная ставка в казино
CASINO_MAX_BET = 1000  # Максимальная ставка в казино

# Настройки кейсов
CASES = {
    "common": {
        "name": "📦 Обычный кейс",
        "price": 50,
        "rewards": [
            {"amount": 10, "chance": 30},
            {"amount": 25, "chance": 25},
            {"amount": 50, "chance": 20},
            {"amount": 100, "chance": 15},
            {"amount": 250, "chance": 7},
            {"amount": 500, "chance": 3},
        ]
    },
    "rare": {
        "name": "💎 Редкий кейс",
        "price": 200,
        "rewards": [
            {"amount": 50, "chance": 30},
            {"amount": 100, "chance": 25},
            {"amount": 250, "chance": 20},
            {"amount": 500, "chance": 15},
            {"amount": 1000, "chance": 7},
            {"amount": 2500, "chance": 3},
        ]
    },
    "legendary": {
        "name": "👑 Легендарный кейс",
        "price": 1000,
        "rewards": [
            {"amount": 500, "chance": 35},
            {"amount": 1000, "chance": 25},
            {"amount": 2500, "chance": 20},
            {"amount": 5000, "chance": 10},
            {"amount": 10000, "chance": 7},
            {"amount": 25000, "chance": 3},
        ]
    }
}

# Обязательные подписки (каналы для проверки через Botohost)
REQUIRED_SUBSCRIPTIONS = [
    {"chat_id": "-1001234567890", "name": "Основной канал", "reward": 100},
    {"chat_id": "-1009876543210", "name": "Новостной канал", "reward": 50},
]

# ============================================
# ========== СТРУКТУРЫ ДАННЫХ ==========
# ============================================

# Хранилище данных (в памяти)
user_mcoins = defaultdict(lambda: START_MCOINS)
user_tasks_completed = defaultdict(list)  # Выполненные задания BotoHub
user_subscriptions_check = defaultdict(lambda: {"checked": False, "claimed": False})
user_lottery_tickets = defaultdict(int)
active_lottery = {"active": False, "participants": [], "end_time": None, "prize_pool": 0}
user_daily_rewards = defaultdict(lambda: {"last_claim": None, "streak": 0})

# ============================================
# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
# ============================================

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

async def check_subscriptions(user_id: int, context: CallbackContext) -> bool:
    """Проверка обязательных подписок через Botohost (упрощенная версия)."""
    # Здесь должна быть реальная проверка через Botohost API
    # Сейчас возвращаем True для теста
    return True

async def add_mcoins(user_id: int, amount: int, context: CallbackContext, reason: str = ""):
    """Добавление MCoin пользователю."""
    user_mcoins[user_id] += amount
    try:
        await context.bot.send_message(
            user_id,
            f"💰 Вы получили {amount} MCoin! ({reason})\nБаланс: {user_mcoins[user_id]} MCoin"
        )
    except:
        pass

async def remove_mcoins(user_id: int, amount: int, context: CallbackContext, reason: str = ""):
    """Списание MCoin."""
    if user_mcoins[user_id] >= amount:
        user_mcoins[user_id] -= amount
        return True
    return False

def get_main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Главная клавиатура."""
    keyboard = [
        [InlineKeyboardButton("💰 Баланс", callback_data="balance"),
         InlineKeyboardButton("📋 Задания BotoHub", callback_data="tasks_menu")],
        [InlineKeyboardButton("🎁 Ежедневная награда", callback_data="daily_reward"),
         InlineKeyboardButton("📢 Обязательные подписки", callback_data="check_subs")],
        [InlineKeyboardButton("🎰 Казино", callback_data="casino"),
         InlineKeyboardButton("🎲 Лотерея", callback_data="lottery")],
        [InlineKeyboardButton("📦 Кейсы", callback_data="cases"),
         InlineKeyboardButton("👤 Профиль", callback_data="profile")],
    ]
    if user_id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

# ============================================
# ========== ОСНОВНЫЕ КОМАНДЫ ==========
# ============================================

async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    if user_id not in user_mcoins:
        user_mcoins[user_id] = START_MCOINS
    
    await update.message.reply_text(
        f"🎉 Привет, {user_name}!\n\n"
        f"Добро пожаловать в бота с заданиями и играми!\n"
        f"💰 Твой баланс: {user_mcoins[user_id]} MCoin\n\n"
        f"Используй кнопки ниже для навигации:",
        reply_markup=get_main_keyboard(user_id)
    )

async def balance(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    await query.edit_message_text(
        f"💰 **Твой баланс:**\n"
        f"└ {user_mcoins[user_id]} MCoin\n\n"
        f"**Как заработать MCoin:**\n"
        f"• Выполнять задания BotoHub (+{REWARD_PER_TASK} MCoin)\n"
        f"• Ежедневная награда\n"
        f"• Обязательные подписки\n"
        f"• Выигрывать в лотерее\n"
        f"• Открывать кейсы",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")
        ]])
    )

# ============================================
# ========== ЗАДАНИЯ BOTOHUB ==========
# ============================================

async def tasks_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📋 Обычный режим", callback_data="regular_tasks")],
        [InlineKeyboardButton("🎯 Продвинутый режим", callback_data="adv_tasks")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]
    ]
    await query.edit_message_text(
        "📋 **Выбери режим заданий:**\n\n"
        "• Обычный - все задания сразу\n"
        "• Продвинутый - по одному заданию с проверкой",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def regular_tasks(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    msg = await query.edit_message_text("🔄 Получаем список заданий...")
    
    try:
        result = await call_botohub_api(user_id, is_task=False)
        
        tasks = result.get("tasks", [])
        completed = result.get("completed", False)
        skip_flag = result.get("skip", False)
        
        if skip_flag or not tasks:
            await msg.edit_text("🎉 На данный момент нет активных заданий. Попробуйте позже.")
            return
        
        if completed:
            await msg.edit_text("✅ Вы выполнили все доступные задания!")
            return
        
        for idx, url in enumerate(tasks, start=1):
            keyboard = [[InlineKeyboardButton("✅ Выполнено", callback_data=f"complete_task_{idx}_{url}")]]
            await context.bot.send_message(
                user_id,
                f"📌 Задание {idx}/{len(tasks)}:\n{url}\n\n"
                f"Подпишитесь на канал и нажмите «Выполнено»\n"
                f"Награда: +{REWARD_PER_TASK} MCoin",
                reply_markup=InlineKeyboardMarkup(keyboard),
                disable_web_page_preview=True
            )
        
        await msg.edit_text("✅ Задания отправлены!")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")

async def complete_task(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    task_id = query.data.split("_")[2]
    
    # Проверяем, не выполнено ли уже задание
    if task_id in user_tasks_completed[user_id]:
        await query.edit_text("❌ Это задание уже выполнено!")
        return
    
    # Добавляем награду
    user_tasks_completed[user_id].append(task_id)
    user_mcoins[user_id] += REWARD_PER_TASK
    
    await query.edit_text(
        f"✅ Задание выполнено!\n"
        f"💰 Награда: +{REWARD_PER_TASK} MCoin\n"
        f"💰 Твой баланс: {user_mcoins[user_id]} MCoin"
    )

# ============================================
# ========== КАЗИНО ==========
# ============================================

async def casino(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🎲 Играть (чёт/нечет)", callback_data="casino_even")],
        [InlineKeyboardButton("🎰 Слот-машина", callback_data="casino_slot")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]
    ]
    await query.edit_message_text(
        "🎰 **Казино MCoin**\n\n"
        f"Минимальная ставка: {CASINO_MIN_BET} MCoin\n"
        f"Максимальная ставка: {CASINO_MAX_BET} MCoin\n\n"
        "Выбери игру:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def casino_even(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    context.user_data["casino_type"] = "even"
    await query.edit_message_text(
        f"🎲 **Игра «Чёт/Нечет»**\n\n"
        f"Твой баланс: {user_mcoins[update.effective_user.id]} MCoin\n"
        f"Минимальная ставка: {CASINO_MIN_BET} MCoin\n\n"
        f"Введи сумму ставки (числом):",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Отмена", callback_data="casino")
        ]])
    )
    context.user_data["awaiting_bet"] = True

async def process_bet(update: Update, context: CallbackContext):
    if not context.user_data.get("awaiting_bet"):
        return
    
    try:
        bet = int(update.message.text)
        user_id = update.effective_user.id
        
        if bet < CASINO_MIN_BET or bet > CASINO_MAX_BET:
            await update.message.reply_text(f"❌ Ставка должна быть от {CASINO_MIN_BET} до {CASINO_MAX_BET} MCoin")
            return
        
        if user_mcoins[user_id] < bet:
            await update.message.reply_text(f"❌ Недостаточно средств! Баланс: {user_mcoins[user_id]} MCoin")
            return
        
        # Игра
        number = random.randint(1, 6)
        user_choice = random.choice(["чет", "нечет"])
        is_even = number % 2 == 0
        result = "чет" if is_even else "нечет"
        
        win = user_choice == result
        
        if win:
            win_amount = bet * 2
            user_mcoins[user_id] += win_amount - bet
            await update.message.reply_text(
                f"🎲 Выпало число: {number} ({result})\n"
                f"Ты выбрал: {user_choice}\n"
                f"✅ Ты выиграл! +{win_amount} MCoin\n"
                f"💰 Новый баланс: {user_mcoins[user_id]} MCoin"
            )
        else:
            user_mcoins[user_id] -= bet
            await update.message.reply_text(
                f"🎲 Выпало число: {number} ({result})\n"
                f"Ты выбрал: {user_choice}\n"
                f"❌ Ты проиграл! -{bet} MCoin\n"
                f"💰 Новый баланс: {user_mcoins[user_id]} MCoin"
            )
        
        context.user_data["awaiting_bet"] = False
        
    except ValueError:
        await update.message.reply_text("❌ Введи число!")

# ============================================
# ========== ЛОТЕРЕЯ ==========
# ============================================

async def lottery(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🎫 Купить билет", callback_data="buy_ticket")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="lottery_info")]
    ]
    
    if user_id in ADMIN_IDS and not active_lottery["active"]:
        keyboard.append([InlineKeyboardButton("🎲 Запустить розыгрыш", callback_data="start_draw")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")])
    
    info = f"🎲 **Лотерея**\n\n"
    if active_lottery["active"]:
        info += f"Статус: 🟢 Активна\n"
        info += f"Участников: {len(active_lottery['participants'])}\n"
        info += f"Призовой фонд: {active_lottery['prize_pool']} MCoin\n"
        info += f"Цена билета: {LOTTERY_TICKET_PRICE} MCoin\n"
        info += f"Твои билеты: {user_lottery_tickets[update.effective_user.id]}"
    else:
        info += "Статус: 🔴 Не активна\n"
        info += "Розыгрыш не запущен"
    
    await query.edit_message_text(info, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def buy_ticket(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    if not active_lottery["active"]:
        await query.edit_message_text("❌ Лотерея не активна!")
        return
    
    if user_mcoins[user_id] < LOTTERY_TICKET_PRICE:
        await query.edit_message_text(f"❌ Недостаточно MCoin! Нужно: {LOTTERY_TICKET_PRICE}")
        return
    
    user_mcoins[user_id] -= LOTTERY_TICKET_PRICE
    user_lottery_tickets[user_id] += 1
    active_lottery["participants"].append(user_id)
    active_lottery["prize_pool"] += LOTTERY_TICKET_PRICE
    
    await query.edit_message_text(
        f"✅ Билет куплен! -{LOTTERY_TICKET_PRICE} MCoin\n"
        f"🎫 Твои билеты: {user_lottery_tickets[user_id]}\n"
        f"💰 Призовой фонд: {active_lottery['prize_pool']} MCoin",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад", callback_data="lottery")
        ]])
    )

async def start_draw(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.edit_message_text("❌ Нет доступа!")
        return
    
    if active_lottery["active"]:
        await query.edit_message_text("❌ Лотерея уже активна!")
        return
    
    active_lottery["active"] = True
    active_lottery["participants"] = []
    active_lottery["prize_pool"] = 0
    
    await query.edit_message_text("✅ Лотерея запущена! Покупайте билеты!")

async def draw_winner(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.edit_message_text("❌ Нет доступа!")
        return
    
    if not active_lottery["active"]:
        await query.edit_message_text("❌ Лотерея не активна!")
        return
    
    if len(active_lottery["participants"]) == 0:
        await query.edit_message_text("❌ Нет участников!")
        return
    
    winner_id = random.choice(active_lottery["participants"])
    win_amount = active_lottery["prize_pool"]
    
    user_mcoins[winner_id] += win_amount
    
    await context.bot.send_message(
        winner_id,
        f"🎉 ПОЗДРАВЛЯЮ! Ты выиграл в лотерее!\n"
        f"💰 Приз: {win_amount} MCoin!"
    )
    
    await query.edit_message_text(
        f"🎉 Розыгрыш завершен!\n"
        f"👤 Победитель: ID {winner_id}\n"
        f"💰 Выигрыш: {win_amount} MCoin"
    )
    
    active_lottery["active"] = False
    user_lottery_tickets.clear()

# ============================================
# ========== КЕЙСЫ ==========
# ============================================

async def cases(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    text = "📦 **Магазин кейсов**\n\nТвой баланс: {}\n\n".format(user_mcoins[user_id])
    keyboard = []
    
    for case_id, case in CASES.items():
        text += f"{case['name']} - {case['price']} MCoin\n"
        keyboard.append([InlineKeyboardButton(f"{case['name']}", callback_data=f"open_case_{case_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")])
    
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def open_case(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    case_id = query.data.split("_")[2]
    case = CASES.get(case_id)
    
    if not case:
        await query.edit_message_text("❌ Кейс не найден!")
        return
    
    if user_mcoins[user_id] < case["price"]:
        await query.edit_message_text(f"❌ Недостаточно средств! Нужно: {case['price']} MCoin")
        return
    
    user_mcoins[user_id] -= case["price"]
    
    # Выбор награды
    random_num = random.randint(1, 100)
    cumulative = 0
    reward = None
    
    for rew in case["rewards"]:
        cumulative += rew["chance"]
        if random_num <= cumulative:
            reward = rew["amount"]
            break
    
    if reward is None:
        reward = case["rewards"][0]["amount"]
    
    user_mcoins[user_id] += reward
    
    await query.edit_message_text(
        f"📦 {case['name']}\n\n"
        f"💰 Ты получил: +{reward} MCoin\n"
        f"💰 Твой баланс: {user_mcoins[user_id]} MCoin",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 К кейсам", callback_data="cases")
        ]])
    )

# ============================================
# ========== АДМИН-ПАНЕЛЬ ==========
# ============================================

async def admin_panel(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.edit_message_text("❌ Нет доступа!")
        return
    
    keyboard = [
        [InlineKeyboardButton("💰 Выдать MCoin", callback_data="admin_give")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="admin_mailing")],
        [InlineKeyboardButton("🎲 Запустить лотерею", callback_data="start_draw_admin")],
        [InlineKeyboardButton("🎲 Провести розыгрыш", callback_data="draw_winner_admin")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]
    ]
    
    await query.edit_message_text(
        "⚙️ **Админ-панель**\n\n"
        f"Всего пользователей: {len(user_mcoins)}\n"
        f"Общий баланс: {sum(user_mcoins.values())} MCoin",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_give(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "💰 Введи ID пользователя и сумму через пробел:\n"
        "Пример: `5356400377 100`",
        parse_mode="Markdown"
    )
    context.user_data["admin_action"] = "give_mcoins"

async def admin_stats(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    total_users = len(user_mcoins)
    total_mcoins = sum(user_mcoins.values())
    avg_mcoins = total_mcoins / total_users if total_users > 0 else 0
    
    await query.edit_message_text(
        f"📊 **Статистика бота**\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"💰 Общий баланс: {total_mcoins} MCoin\n"
        f"📈 Средний баланс: {avg_mcoins:.2f} MCoin\n"
        f"🎫 Участников лотереи: {len(active_lottery['participants'])}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")
        ]])
    )

async def process_admin_command(update: Update, context: CallbackContext):
    if not context.user_data.get("admin_action"):
        return
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    
    action = context.user_data["admin_action"]
    
    if action == "give_mcoins":
        try:
            parts = update.message.text.split()
            target_id = int(parts[0])
            amount = int(parts[1])
            
            user_mcoins[target_id] += amount
            
            await update.message.reply_text(f"✅ Выдано {amount} MCoin пользователю {target_id}")
            await context.bot.send_message(target_id, f"💰 Администратор выдал тебе {amount} MCoin!")
            
        except:
            await update.message.reply_text("❌ Ошибка! Формат: ID Сумма")
        
        context.user_data["admin_action"] = None

# ============================================
# ========== ЗАПУСК БОТА ==========
# ============================================

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    
    # Callback'и
    app.add_handler(CallbackQueryHandler(balance, pattern="^balance$"))
    app.add_handler(CallbackQueryHandler(tasks_menu, pattern="^tasks_menu$"))
    app.add_handler(CallbackQueryHandler(regular_tasks, pattern="^regular_tasks$"))
    app.add_handler(CallbackQueryHandler(casino, pattern="^casino$"))
    app.add_handler(CallbackQueryHandler(casino_even, pattern="^casino_even$"))
    app.add_handler(CallbackQueryHandler(lottery, pattern="^lottery$"))
    app.add_handler(CallbackQueryHandler(buy_ticket, pattern="^buy_ticket$"))
    app.add_handler(CallbackQueryHandler(start_draw, pattern="^start_draw$"))
    app.add_handler(CallbackQueryHandler(draw_winner, pattern="^draw_winner$"))
    app.add_handler(CallbackQueryHandler(cases, pattern="^cases$"))
    app.add_handler(CallbackQueryHandler(open_case, pattern="^open_case_"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_give, pattern="^admin_give$"))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.edit_message_reply_markup(reply_markup=get_main_keyboard(u.effective_user.id)), pattern="^back_to_menu$"))
    
    # Обработчики сообщений
    app.add_handler(CallbackQueryHandler(complete_task, pattern="^complete_task_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_bet))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_command))
    
    # Запуск
    print("🚀 Бот запущен...")
    print(f"👑 Администраторы: {ADMIN_IDS}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()