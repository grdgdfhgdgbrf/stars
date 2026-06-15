import asyncio
import random
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, List
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

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = "8251949164:AAEUSmnhX_S4p-vWDD4fvC6mDclV0LvIFe0"
BOTOHUB_TOKEN = "3feed57e-9303-4343-8d87-ed8d9dd5650f"
BOTOHUB_API_URL = "https://botohub.me/get-tasks"
ADMIN_ID = 5356400377  # ID администратора

# Файлы для хранения данных
DATA_FILE = "bot_data.json"
SETTINGS_FILE = "settings.json"

# Состояния для ConversationHandler
SET_REWARD, SET_PRICE, SET_NAME, SET_DESCRIPTION, SET_WIN_CHANCE = range(5)

# ========== СТРУКТУРА ДАННЫХ ==========
# Будет храниться в памяти и периодически сохраняться в JSON
class BotData:
    def __init__(self):
        self.users: Dict[int, Dict] = {}  # user_id: {mcoin, tasks_completed, inventory, etc}
        self.cases: Dict[str, Dict] = {}  # case_name: {price, items: [{name, chance, reward}]}
        self.lottery: Dict = {
            "active": False,
            "tickets": {},
            "prize": 0,
            "end_time": None,
            "winner": None
        }
        self.settings: Dict = {
            "task_reward": 10,  # MCoin за выполнение задания
            "referral_reward": 5,  # MCoin за реферала
            "daily_reward": 15,  # MCoin за ежедневный бонус
            "last_daily": {},
            "min_withdraw": 50,
            "game_tax": 0.05,  # Налог на игры 5%
            "force_sub_channels": [],  # Обязательные каналы для подписки
            "force_sub_groups": [],    # Обязательные группы
            "welcome_message": "Добро пожаловать в бот!",
            "referral_program": True
        }
        self.pending_checks: Dict[int, Dict] = {}  # Ожидание проверки подписки

bot_data = BotData()

# ========== РАБОТА С ФАЙЛАМИ ==========
def save_data():
    """Сохраняет данные в JSON файл"""
    data_to_save = {
        "users": bot_data.users,
        "cases": bot_data.cases,
        "lottery": bot_data.lottery,
        "settings": bot_data.settings
    }
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=2)

def load_data():
    """Загружает данные из JSON файла"""
    global bot_data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                bot_data.users = {int(k): v for k, v in data.get("users", {}).items()}
                bot_data.cases = data.get("cases", {})
                bot_data.lottery = data.get("lottery", {})
                bot_data.settings = data.get("settings", {})
        except:
            pass

def save_settings():
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(bot_data.settings, f, ensure_ascii=False, indent=2)

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Создает главную клавиатуру"""
    keyboard = [
        [KeyboardButton("💰 Баланс"), KeyboardButton("📋 Задания")],
        [KeyboardButton("🎲 Игры"), KeyboardButton("📦 Кейсы")],
        [KeyboardButton("🎰 Лотерея"), KeyboardButton("👥 Рефералы")],
        [KeyboardButton("🏆 Ежедневный бонус"), KeyboardButton("💸 Вывод средств")]
    ]
    
    if user_id == ADMIN_ID:
        keyboard.append([KeyboardButton("⚙️ Админ панель")])
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_user_data(user_id: int) -> Dict:
    """Получает данные пользователя, создает если нет"""
    if user_id not in bot_data.users:
        bot_data.users[user_id] = {
            "mcoin": 0,
            "tasks_completed": [],
            "inventory": [],
            "referrals": [],
            "referrer": None,
            "daily_last": None,
            "total_earned": 0,
            "join_date": datetime.now().isoformat(),
            "username": None
        }
        save_data()
    return bot_data.users[user_id]

def add_mcoins(user_id: int, amount: int, reason: str = ""):
    """Добавляет MCoin пользователю"""
    user = get_user_data(user_id)
    user["mcoin"] += amount
    user["total_earned"] += amount
    save_data()

def remove_mcoins(user_id: int, amount: int) -> bool:
    """Снимает MCoin, возвращает True если достаточно средств"""
    user = get_user_data(user_id)
    if user["mcoin"] >= amount:
        user["mcoin"] -= amount
        save_data()
        return True
    return False

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

    async with aiohttp.ClientSession() as session:
        async with session.post(BOTOHUB_API_URL, json=payload, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                return {"tasks": [], "completed": False, "skip": True}

# ========== КОМАНДЫ ИГР ==========
async def game_casino(update: Update, context: CallbackContext):
    """Игра Казино"""
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text("🎰 Использование: /casino <сумма>\nПример: /casino 50")
        return
    
    try:
        bet = int(args[0])
        if bet <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ Введите корректную сумму!")
        return
    
    if not remove_mcoins(user_id, bet):
        await update.message.reply_text(f"❌ Недостаточно MCoin! У вас {get_user_data(user_id)['mcoin']} MCoin")
        return
    
    # Логика казино
    win_chance = random.random()
    if win_chance < 0.4:  # 40% шанс выигрыша
        win_amount = int(bet * random.uniform(1.5, 3))
        add_mcoins(user_id, win_amount, "casino_win")
        await update.message.reply_text(
            f"🎉 **ПОБЕДА!** 🎉\n"
            f"Вы выиграли {win_amount} MCoin!\n"
            f"Ставка: {bet} MCoin\n"
            f"💰 Ваш баланс: {get_user_data(user_id)['mcoin']} MCoin"
        )
    else:
        await update.message.reply_text(
            f"😢 **ПРОИГРЫШ** 😢\n"
            f"Вы проиграли {bet} MCoin\n"
            f"💰 Ваш баланс: {get_user_data(user_id)['mcoin']} MCoin"
        )

async def game_dice(update: Update, context: CallbackContext):
    """Игра Кости"""
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text("🎲 Использование: /dice <сумма>\nПример: /dice 30")
        return
    
    try:
        bet = int(args[0])
        if bet <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ Введите корректную сумму!")
        return
    
    if not remove_mcoins(user_id, bet):
        await update.message.reply_text(f"❌ Недостаточно MCoin! У вас {get_user_data(user_id)['mcoin']} MCoin")
        return
    
    # Бросаем кости
    user_dice = random.randint(1, 6)
    bot_dice = random.randint(1, 6)
    
    if user_dice > bot_dice:
        win_amount = bet * 2
        add_mcoins(user_id, win_amount, "dice_win")
        await update.message.reply_text(
            f"🎲 **ВЫ ПОБЕДИЛИ!** 🎲\n"
            f"Ваш бросок: {user_dice}\n"
            f"Бросок бота: {bot_dice}\n"
            f"Вы выиграли {win_amount} MCoin!\n"
            f"💰 Баланс: {get_user_data(user_id)['mcoin']} MCoin"
        )
    elif user_dice < bot_dice:
        await update.message.reply_text(
            f"😢 **ВЫ ПРОИГРАЛИ** 😢\n"
            f"Ваш бросок: {user_dice}\n"
            f"Бросок бота: {bot_dice}\n"
            f"💰 Баланс: {get_user_data(user_id)['mcoin']} MCoin"
        )
    else:
        add_mcoins(user_id, bet, "dice_draw")
        await update.message.reply_text(
            f"🤝 **НИЧЬЯ** 🤝\n"
            f"Ваш бросок: {user_dice}\n"
            f"Бросок бота: {bot_dice}\n"
            f"Ставка возвращена!\n"
            f"💰 Баланс: {get_user_data(user_id)['mcoin']} MCoin"
        )

# ========== КЕЙСЫ ==========
async def cases_menu(update: Update, context: CallbackContext):
    """Меню кейсов"""
    keyboard = []
    for case_name, case_data in bot_data.cases.items():
        keyboard.append([InlineKeyboardButton(
            f"📦 {case_name} - {case_data['price']} MCoin", 
            callback_data=f"open_case_{case_name}"
        )])
    
    if not keyboard:
        await update.message.reply_text("📦 Кейсы временно недоступны!")
        return
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎁 **Магазин кейсов** 🎁\n\n"
        "Выберите кейс для открытия:",
        reply_markup=reply_markup
    )

async def open_case(update: Update, context: CallbackContext, case_name: str):
    """Открытие кейса"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if case_name not in bot_data.cases:
        await query.answer("Кейс не найден!")
        return
    
    case_data = bot_data.cases[case_name]
    price = case_data["price"]
    
    if not remove_mcoins(user_id, price):
        await query.answer("Недостаточно MCoin!", show_alert=True)
        return
    
    # Выбираем предмет из кейса
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
    
    # Выдаем награду
    reward = selected_item["reward"]
    add_mcoins(user_id, reward, f"case_{case_name}")
    
    await query.message.edit_text(
        f"🎉 **Вы открыли кейс '{case_name}'** 🎉\n\n"
        f"📦 Вам выпало: **{selected_item['name']}**\n"
        f"💰 Награда: {reward} MCoin\n\n"
        f"✨ Ваш баланс: {get_user_data(user_id)['mcoin']} MCoin"
    )

# ========== ЛОТЕРЕЯ ==========
async def lottery_menu(update: Update, context: CallbackContext):
    """Меню лотереи"""
    keyboard = [
        [InlineKeyboardButton("🎫 Купить билет (10 MCoin)", callback_data="buy_ticket")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="lottery_info")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    prize_info = f"Призовой фонд: {bot_data.lottery['prize']} MCoin" if bot_data.lottery['active'] else "Лотерея не активна"
    
    await update.message.reply_text(
        f"🎰 **Лотерея** 🎰\n\n"
        f"{prize_info}\n"
        f"Цена билета: 10 MCoin\n\n"
        f"Каждый билет увеличивает шанс на победу!\n"
        f"Победитель получает 80% призового фонда",
        reply_markup=reply_markup
    )

async def buy_ticket(update: Update, context: CallbackContext):
    """Покупка лотерейного билета"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if not bot_data.lottery.get("active", False):
        await query.answer("Лотерея не активна!", show_alert=True)
        return
    
    if not remove_mcoins(user_id, 10):
        await query.answer("Недостаточно MCoin!", show_alert=True)
        return
    
    # Добавляем билет
    if user_id not in bot_data.lottery["tickets"]:
        bot_data.lottery["tickets"][user_id] = 0
    bot_data.lottery["tickets"][user_id] += 1
    bot_data.lottery["prize"] += 8  # 80% от цены билета идет в призовой фонд
    
    save_data()
    
    total_tickets = sum(bot_data.lottery["tickets"].values())
    await query.answer("Билет куплен! Удачи!", show_alert=True)
    await query.message.edit_text(
        f"✅ **Билет куплен!**\n\n"
        f"Ваших билетов: {bot_data.lottery['tickets'][user_id]}\n"
        f"Всего билетов: {total_tickets}\n"
        f"Призовой фонд: {bot_data.lottery['prize']} MCoin"
    )

# ========== АДМИН ПАНЕЛЬ ==========
async def admin_panel(update: Update, context: CallbackContext):
    """Главное меню админ панели"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет доступа к админ панели!")
        return
    
    keyboard = [
        [InlineKeyboardButton("💰 Настройка наград", callback_data="admin_rewards")],
        [InlineKeyboardButton("📦 Управление кейсами", callback_data="admin_cases")],
        [InlineKeyboardButton("🎰 Управление лотереей", callback_data="admin_lottery")],
        [InlineKeyboardButton("📢 Обязательные подписки", callback_data="admin_forcesub")],
        [InlineKeyboardButton("👥 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("💸 Выплаты", callback_data="admin_withdraw")],
        [InlineKeyboardButton("📨 Рассылка", callback_data="admin_mailing")],
        [InlineKeyboardButton("🔙 Выход", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "⚙️ **Админ панель** ⚙️\n\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )

async def admin_rewards_menu(update: Update, context: CallbackContext):
    """Меню настройки наград"""
    query = update.callback_query
    
    keyboard = [
        [InlineKeyboardButton(f"💰 За задание: {bot_data.settings['task_reward']}", callback_data="set_task_reward")],
        [InlineKeyboardButton(f"👥 За реферала: {bot_data.settings['referral_reward']}", callback_data="set_ref_reward")],
        [InlineKeyboardButton(f"🏆 Ежедневный: {bot_data.settings['daily_reward']}", callback_data="set_daily_reward")],
        [InlineKeyboardButton(f"💸 Мин. вывод: {bot_data.settings['min_withdraw']}", callback_data="set_min_withdraw")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "💰 **Настройка наград** 💰\n\n"
        "Выберите параметр для изменения:",
        reply_markup=reply_markup
    )

async def admin_cases_menu(update: Update, context: CallbackContext):
    """Меню управления кейсами"""
    query = update.callback_query
    
    keyboard = [
        [InlineKeyboardButton("📦 Создать кейс", callback_data="create_case")],
        [InlineKeyboardButton("🗑 Удалить кейс", callback_data="delete_case")],
        [InlineKeyboardButton("📋 Список кейсов", callback_data="list_cases")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    cases_list = "\n".join([f"• {name}: {data['price']} MCoin" for name, data in bot_data.cases.items()])
    cases_text = f"\n\n📦 **Существующие кейсы:**\n{cases_list}" if cases_list else "\n\n📦 Кейсы отсутствуют"
    
    await query.message.edit_text(
        f"📦 **Управление кейсами** 📦{cases_text}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

async def create_case_start(update: Update, context: CallbackContext):
    """Начало создания кейса"""
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        "📦 **Создание нового кейса**\n\n"
        "Введите название кейса:"
    )
    return SET_NAME

async def create_case_name(update: Update, context: CallbackContext):
    """Получение названия кейса"""
    case_name = update.message.text
    context.user_data['case_name'] = case_name
    
    await update.message.reply_text(
        f"📦 Кейс '{case_name}'\n\n"
        "Введите цену кейса (в MCoin):"
    )
    return SET_PRICE

async def create_case_price(update: Update, context: CallbackContext):
    """Получение цены кейса"""
    try:
        price = int(update.message.text)
        context.user_data['case_price'] = price
        
        await update.message.reply_text(
            f"💰 Цена: {price} MCoin\n\n"
            "Введите предметы в формате:\n"
            "Название | шанс | награда\n"
            "Пример: Легендарный предмет | 10 | 500\n\n"
            "Каждый предмет с новой строки. Для завершения отправьте 'готово':"
        )
        context.user_data['case_items'] = []
        return SET_DESCRIPTION
    except:
        await update.message.reply_text("❌ Введите корректное число!")
        return SET_PRICE

async def create_case_items(update: Update, context: CallbackContext):
    """Добавление предметов в кейс"""
    text = update.message.text
    
    if text.lower() == 'готово':
        if len(context.user_data['case_items']) == 0:
            await update.message.reply_text("❌ Добавьте хотя бы один предмет!")
            return SET_DESCRIPTION
        
        # Сохраняем кейс
        bot_data.cases[context.user_data['case_name']] = {
            "price": context.user_data['case_price'],
            "items": context.user_data['case_items']
        }
        save_data()
        
        await update.message.reply_text(
            f"✅ **Кейс '{context.user_data['case_name']}' создан!**\n\n"
            f"💰 Цена: {context.user_data['case_price']} MCoin\n"
            f"📦 Предметов: {len(context.user_data['case_items'])}"
        )
        return ConversationHandler.END
    
    try:
        parts = text.split('|')
        if len(parts) != 3:
            await update.message.reply_text("❌ Неверный формат! Пример: Название | 10 | 500")
            return SET_DESCRIPTION
        
        name = parts[0].strip()
        chance = float(parts[1].strip())
        reward = int(parts[2].strip())
        
        context.user_data['case_items'].append({
            "name": name,
            "chance": chance,
            "reward": reward
        })
        
        await update.message.reply_text(
            f"✅ Добавлен предмет: {name}\n"
            f"Шанс: {chance}%, Награда: {reward} MCoin\n\n"
            f"Всего предметов: {len(context.user_data['case_items'])}\n"
            f"Добавьте следующий предмет или отправьте 'готово':"
        )
        return SET_DESCRIPTION
    except:
        await update.message.reply_text("❌ Ошибка! Пример: Название | 10 | 500")
        return SET_DESCRIPTION

# ========== ОСНОВНЫЕ ФУНКЦИИ БОТА ==========
async def check_force_subs(user_id: int) -> tuple:
    """Проверяет обязательные подписки"""
    # Здесь можно реализовать проверку через bot.get_chat_member
    # Для упрощения возвращаем True
    return True, []

async def handle_balance(update: Update, context: CallbackContext):
    """Показывает баланс"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    await update.message.reply_text(
        f"💰 **Ваш баланс** 💰\n\n"
        f"🎮 MCoin: {user_data['mcoin']}\n"
        f"📊 Всего заработано: {user_data['total_earned']}\n"
        f"👥 Рефералов: {len(user_data['referrals'])}\n"
        f"📅 В боте с: {user_data['join_date'][:10]}",
        parse_mode="Markdown"
    )

async def handle_tasks(update: Update, context: CallbackContext):
    """Обработка заданий"""
    user_id = update.effective_user.id
    
    # Проверяем обязательные подписки
    passed, not_passed = await check_force_subs(user_id)
    if not passed:
        msg = "⚠️ **Для выполнения заданий необходимо подписаться:**\n\n"
        for channel in not_passed:
            msg += f"• {channel}\n"
        await update.message.reply_text(msg)
        return
    
    await tasks_mode(update, context)

async def handle_games(update: Update, context: CallbackContext):
    """Меню игр"""
    keyboard = [
        [InlineKeyboardButton("🎰 Казино (/casino)", callback_data="game_casino")],
        [InlineKeyboardButton("🎲 Кости (/dice)", callback_data="game_dice")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎮 **Игровой центр** 🎮\n\n"
        "Выберите игру:",
        reply_markup=reply_markup
    )

async def handle_daily(update: Update, context: CallbackContext):
    """Ежедневный бонус"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    last_daily = user_data.get("daily_last")
    if last_daily:
        last_date = datetime.fromisoformat(last_daily)
        if datetime.now() - last_date < timedelta(days=1):
            hours_left = 24 - (datetime.now() - last_date).seconds // 3600
            await update.message.reply_text(
                f"⏰ Вы уже получали бонус сегодня!\n"
                f"Следующий бонус через {hours_left} часов."
            )
            return
    
    reward = bot_data.settings["daily_reward"]
    add_mcoins(user_id, reward, "daily_bonus")
    user_data["daily_last"] = datetime.now().isoformat()
    save_data()
    
    await update.message.reply_text(
        f"🎁 **Ежедневный бонус!** 🎁\n\n"
        f"Вы получили {reward} MCoin!\n"
        f"💰 Баланс: {user_data['mcoin']} MCoin"
    )

async def handle_withdraw(update: Update, context: CallbackContext):
    """Вывод средств"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    min_withdraw = bot_data.settings["min_withdraw"]
    
    if user_data["mcoin"] < min_withdraw:
        await update.message.reply_text(
            f"❌ Минимальная сумма вывода: {min_withdraw} MCoin\n"
            f"💰 Ваш баланс: {user_data['mcoin']} MCoin"
        )
        return
    
    # Здесь нужно добавить реальную систему вывода
    await update.message.reply_text(
        "💸 **Вывод средств** 💸\n\n"
        "Для вывода средств обратитесь к администратору.\n"
        f"Запрос на вывод: {user_data['mcoin']} MCoin\n\n"
        f"ID: {user_id}\n"
        f"Username: @{update.effective_user.username}"
    )

async def handle_referrals(update: Update, context: CallbackContext):
    """Реферальная система"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    if not bot_data.settings["referral_program"]:
        await update.message.reply_text("❌ Реферальная программа временно отключена!")
        return
    
    # Генерация реферальной ссылки
    bot_username = context.bot.username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    await update.message.reply_text(
        f"👥 **Реферальная программа** 👥\n\n"
        f"Приглашайте друзей и получайте бонусы!\n"
        f"Награда за реферала: {bot_data.settings['referral_reward']} MCoin\n\n"
        f"📊 Ваша статистика:\n"
        f"Приглашено: {len(user_data['referrals'])}\n"
        f"Заработано: {len(user_data['referrals']) * bot_data.settings['referral_reward']} MCoin\n\n"
        f"🔗 Ваша ссылка:\n`{ref_link}`\n\n"
        f"Отправьте её друзьям!",
        parse_mode="Markdown"
    )

# ========== ОБРАБОТКА ЗАДАНИЙ BOTOHUB ==========
async def tasks_mode(update: Update, context: CallbackContext):
    """Продвинутый режим заданий"""
    user_id = update.effective_user.id
    
    # Проверяем обязательные подписки
    passed, not_passed = await check_force_subs(user_id)
    if not passed:
        msg = "⚠️ **Для выполнения заданий необходимо подписаться:**\n\n"
        for channel in not_passed:
            msg += f"• {channel}\n"
        await update.message.reply_text(msg)
        return
    
    msg = await update.message.reply_text("🔄 Получаем задание...")
    
    try:
        result = await call_botohub_api(user_id, is_task=True, skip=False)
        
        tasks = result.get("tasks", [])
        completed = result.get("completed", False)
        skip_flag = result.get("skip", False)
        
        if completed:
            await msg.edit_text("✅ Вы выполнили все задания! Получите награду!")
            task_reward = bot_data.settings["task_reward"]
            add_mcoins(user_id, task_reward, "tasks_completed")
            await update.message.reply_text(f"🎉 Вы получили {task_reward} MCoin за выполнение всех заданий!")
            return
        
        if skip_flag or not tasks:
            await msg.edit_text("🎉 На данный момент нет заданий. Попробуйте позже.")
            return
        
        task_url = tasks[0]
        
        keyboard = [
            [InlineKeyboardButton("✅ Я выполнил", callback_data=f"check_task_{task_url}")],
            [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await msg.edit_text(
            f"📢 **Новое задание!**\n\n"
            f"Подпишитесь на канал:\n{task_url}\n\n"
            f"После подписки нажмите «Я выполнил»\n"
            f"💰 Награда: {bot_data.settings['task_reward']} MCoin",
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")

async def check_task(update: Update, context: CallbackContext):
    """Проверка выполнения задания"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    task_url = query.data.replace("check_task_", "")
    
    await query.edit_message_text("🔍 Проверяем выполнение...")
    
    try:
        result = await call_botohub_api(user_id, is_task=True, skip=False)
        
        if result.get("prev_success", False):
            # Задание выполнено
            task_reward = bot_data.settings["task_reward"]
            add_mcoins(user_id, task_reward, "task_completed")
            
            if result.get("completed", False):
                await query.edit_message_text(
                    f"✅ Задание выполнено!\n"
                    f"💰 Вы получили {task_reward} MCoin\n"
                    f"🎉 Вы выполнили все задания!"
                )
            else:
                # Пытаемся получить следующее задание
                new_tasks = result.get("tasks", [])
                if new_tasks:
                    new_url = new_tasks[0]
                    keyboard = [
                        [InlineKeyboardButton("✅ Я выполнил", callback_data=f"check_task_{new_url}")],
                        [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await query.edit_message_text(
                        f"✅ Задание выполнено! Получено {task_reward} MCoin\n\n"
                        f"📢 **Следующее задание:**\n{new_url}\n\n"
                        f"Подпишитесь и нажмите «Я выполнил»",
                        reply_markup=reply_markup,
                        disable_web_page_preview=True
                    )
                else:
                    await query.edit_message_text(f"✅ Задание выполнено! Получено {task_reward} MCoin")
        else:
            await query.edit_message_text(
                f"❌ Вы ещё не подписались!\n\n"
                f"Пожалуйста, подпишитесь:\n{task_url}\n\n"
                f"После подписки нажмите «Я выполнил» снова",
                disable_web_page_preview=True
            )
            # Возвращаем кнопки
            keyboard = [
                [InlineKeyboardButton("✅ Я выполнил", callback_data=f"check_task_{task_url}")],
                [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_reply_markup(reply_markup)
            
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка при проверке: {e}")

async def skip_task(update: Update, context: CallbackContext):
    """Пропуск задания"""
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
                f"📢 **Новое задание:**\n{new_url}\n\n"
                f"Подпишитесь и нажмите «Я выполнил»",
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
        else:
            await query.edit_message_text("🎉 Нет доступных заданий!")
            
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {e}")

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
async def start(update: Update, context: CallbackContext):
    """Обработка команды /start"""
    user_id = update.effective_user.id
    
    # Проверяем реферальную ссылку
    if context.args and context.args[0].startswith("ref_"):
        referrer_id = int(context.args[0].replace("ref_", ""))
        if referrer_id != user_id:
            user_data = get_user_data(user_id)
            if not user_data.get("referrer"):
                user_data["referrer"] = referrer_id
                referrer_data = get_user_data(referrer_id)
                referrer_data["referrals"].append(user_id)
                ref_reward = bot_data.settings["referral_reward"]
                add_mcoins(referrer_id, ref_reward, "referral")
                save_data()
                
                try:
                    await context.bot.send_message(
                        referrer_id,
                        f"👥 По вашей реферальной ссылке присоединился {update.effective_user.first_name}!\n"
                        f"💰 Вы получили {ref_reward} MCoin!"
                    )
                except:
                    pass
    
    get_user_data(user_id)
    
    welcome_msg = f"👋 Привет, {update.effective_user.first_name}!\n\n{bot_data.settings['welcome_message']}"
    
    await update.message.reply_text(
        welcome_msg,
        reply_markup=get_main_keyboard(user_id)
    )

async def handle_text(update: Update, context: CallbackContext):
    """Обработка текстовых сообщений"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if text == "💰 Баланс":
        await handle_balance(update, context)
    elif text == "📋 Задания":
        await handle_tasks(update, context)
    elif text == "🎲 Игры":
        await handle_games(update, context)
    elif text == "📦 Кейсы":
        await cases_menu(update, context)
    elif text == "🎰 Лотерея":
        await lottery_menu(update, context)
    elif text == "👥 Рефералы":
        await handle_referrals(update, context)
    elif text == "🏆 Ежедневный бонус":
        await handle_daily(update, context)
    elif text == "💸 Вывод средств":
        await handle_withdraw(update, context)
    elif text == "⚙️ Админ панель" and user_id == ADMIN_ID:
        await admin_panel(update, context)
    else:
        await update.message.reply_text(
            "Используйте кнопки меню 👇",
            reply_markup=get_main_keyboard(user_id)
        )

# ========== ЗАПУСК БОТА ==========
def main():
    # Загружаем данные
    load_data()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Создаем ConversationHandler для создания кейсов
    case_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(create_case_start, pattern="^create_case$")],
        states={
            SET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_case_name)],
            SET_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_case_price)],
            SET_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_case_items)],
        },
        fallbacks=[],
    )
    
    # Основные обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("casino", game_casino))
    app.add_handler(CommandHandler("dice", game_dice))
    
    # Conversation handlers
    app.add_handler(case_conv)
    
    # Callback handlers
    app.add_handler(CallbackQueryHandler(check_task, pattern="^check_task_"))
    app.add_handler(CallbackQueryHandler(skip_task, pattern="^skip_task$"))
    app.add_handler(CallbackQueryHandler(admin_rewards_menu, pattern="^admin_rewards$"))
    app.add_handler(CallbackQueryHandler(admin_cases_menu, pattern="^admin_cases$"))
    app.add_handler(CallbackQueryHandler(create_case_start, pattern="^create_case$"))
    app.add_handler(CallbackQueryHandler(buy_ticket, pattern="^buy_ticket$"))
    app.add_handler(CallbackQueryHandler(open_case, pattern="^open_case_"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.message.delete(), pattern="^back_to_main$"))
    
    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Запуск
    print("🚀 Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()