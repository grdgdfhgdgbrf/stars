import asyncio
from typing import Dict, Optional

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

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = "8251949164:AAEUSmnhX_S4p-vWDD4fvC6mDclV0LvIFe0"
BOTOHUB_TOKEN = "3feed57e-9303-4343-8d87-ed8d9dd5650f"  # Токен из кабинета BotoHub
BOTOHUB_API_URL = "https://botohub.me/get-tasks"

# Структура user_data:
# user_data[user_id] = {
#     "mode": "tasks" | "regular",       # режим: задания (продвинутый) или обычный
#     "current_task_url": str,           # текущая невыполненная ссылка (для режима заданий)
#     "waiting_for_join": bool,          # ожидание проверки вступления
#     "completed_all": bool,             # все задания выполнены
#     "age": str,                        # возрастная категория (если задана)
#     "gender": str                      # пол (если задан)
# }

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
async def call_botohub_api(chat_id: int, is_task: bool = False, skip: bool = False,
                            gender: str = None, age: str = None) -> dict:
    """
    Вызов API BotoHub.
    Возвращает словарь с полями: tasks, completed, skip, prev_success, prev_outdated.
    """
    payload = {
        "chat_id": chat_id,
    }
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

async def send_task_message(update: Update, context: CallbackContext, task_url: str):
    """Отправляет сообщение с заданием (ссылкой) и кнопкой проверки."""
    keyboard = [
        [InlineKeyboardButton("✅ Я вступил", callback_data="check_sub")],
        [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"📢 **Выполните задание:**\nПерейдите по ссылке и подпишитесь (на 3 минуты):\n{task_url}\n\n"
        f"После подписки нажмите «Я вступил».",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# ========== ОБРАБОТЧИКИ КОМАНД ==========
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    # Инициализируем данные пользователя в памяти
    context.user_data.clear()  # сброс для чистоты
    context.user_data["mode"] = "regular"
    context.user_data["waiting_for_join"] = False
    context.user_data["completed_all"] = False
    context.user_data["current_task_url"] = None
    context.user_data["age"] = None
    context.user_data["gender"] = None

    await update.message.reply_text(
        "👋 Привет! Я бот для выполнения заданий от BotoHub.\n\n"
        "Доступные режимы:\n"
        "/regular — обычный режим (получить все ссылки сразу)\n"
        "/tasks — продвинутый режим (по одной ссылке, с отслеживанием)\n\n"
        "Также можно задать демографические параметры:\n"
        "/set_gender male|female\n"
        "/set_age 25   или   /set_age c2 (категория c1-c6)\n\n"
        "Нажмите /regular или /tasks для начала."
    )

async def set_gender(update: Update, context: CallbackContext):
    if not context.args or context.args[0] not in ["male", "female"]:
        await update.message.reply_text("Использование: /set_gender male|female")
        return
    context.user_data["gender"] = context.args[0]
    await update.message.reply_text(f"✅ Пол установлен: {context.user_data['gender']}")

async def set_age(update: Update, context: CallbackContext):
    if not context.args:
        await update.message.reply_text("Использование: /set_age 25  или /set_age c2")
        return
    age_value = context.args[0]
    context.user_data["age"] = age_value
    await update.message.reply_text(f"✅ Возраст/категория установлен: {age_value}")

async def regular_mode(update: Update, context: CallbackContext):
    """Обычный режим: получаем список всех невыполненных ссылок и показываем."""
    user_id = update.effective_user.id
    context.user_data["mode"] = "regular"
    context.user_data["waiting_for_join"] = False
    context.user_data["current_task_url"] = None

    # Показываем, что начали
    msg = await update.message.reply_text("🔄 Получаем список заданий...")

    try:
        gender = context.user_data.get("gender")
        age = context.user_data.get("age")
        result = await call_botohub_api(user_id, is_task=False, gender=gender, age=age)

        tasks = result.get("tasks", [])
        completed = result.get("completed", False)
        skip_flag = result.get("skip", False)

        if skip_flag or not tasks:
            await msg.edit_text("🎉 На данный момент нет активных заданий. Попробуйте позже.")
            return

        if completed:
            await msg.edit_text("✅ Вы выполнили все доступные задания! Спасибо!")
            context.user_data["completed_all"] = True
            return

        # Отправляем каждую ссылку отдельно для удобства
        for idx, url in enumerate(tasks, start=1):
            await update.message.reply_text(
                f"📌 Задание {idx}/{len(tasks)}:\n{url}\n\n"
                f"Перейдите и подпишитесь (удерживайте подписку минимум 3 минуты).",
                disable_web_page_preview=True
            )
        await update.message.reply_text("✅ Все ссылки отправлены. После выполнения всех заданий нажмите /check_regular.")

    except Exception as e:
        await msg.edit_text(f"❌ Ошибка при получении заданий: {e}")

async def check_regular(update: Update, context: CallbackContext):
    """Проверка выполнения в обычном режиме — просто повторный запрос к API."""
    user_id = update.effective_user.id
    msg = await update.message.reply_text("🔄 Проверяем выполнение...")
    try:
        gender = context.user_data.get("gender")
        age = context.user_data.get("age")
        result = await call_botohub_api(user_id, is_task=False, gender=gender, age=age)
        tasks = result.get("tasks", [])
        completed = result.get("completed", False)

        if completed:
            await msg.edit_text("✅ Поздравляю! Вы выполнили все задания.")
        elif not tasks:
            await msg.edit_text("🎉 Нет новых заданий. Вы всё сделали!")
        else:
            await msg.edit_text(f"⚠️ Ещё остались невыполненные задания. Получите их заново командой /regular")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")

async def tasks_mode(update: Update, context: CallbackContext):
    """Продвинутый режим: получаем одно задание, отслеживаем выполнение через API."""
    user_id = update.effective_user.id
    context.user_data["mode"] = "tasks"
    context.user_data["waiting_for_join"] = False
    context.user_data["completed_all"] = False

    msg = await update.message.reply_text("🔄 Запрашиваем задание...")
    try:
        gender = context.user_data.get("gender")
        age = context.user_data.get("age")
        result = await call_botohub_api(user_id, is_task=True, skip=False, gender=gender, age=age)

        tasks = result.get("tasks", [])
        completed = result.get("completed", False)
        skip_flag = result.get("skip", False)
        prev_success = result.get("prev_success", False)
        prev_outdated = result.get("prev_outdated", False)

        # Логика состояния для пользователя
        if completed:
            await msg.edit_text("✅ Вы выполнили все задания! Спасибо за работу!")
            context.user_data["completed_all"] = True
            return

        if skip_flag or not tasks:
            await msg.edit_text("🎉 На данный момент нет заданий для показа.")
            return

        task_url = tasks[0]
        context.user_data["current_task_url"] = task_url
        context.user_data["waiting_for_join"] = True

        # Отправляем задание с кнопками
        keyboard = [
            [InlineKeyboardButton("✅ Я вступил", callback_data="check_sub")],
            [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await msg.edit_text(
            f"📢 **Продвинутое задание:**\nПерейдите и подпишитесь:\n{task_url}\n\n"
            f"После подписки нажмите «Я вступил» для проверки.",
            reply_markup=reply_markup,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")

# ========== ОБРАБОТЧИКИ КНОПОК ==========
async def check_subscription(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if context.user_data.get("mode") != "tasks" or not context.user_data.get("waiting_for_join"):
        await query.edit_message_text("⚠️ Сейчас нет активного задания для проверки. Начните заново через /tasks")
        return

    # Отправляем запрос к API с is_task=true (без skip) — BotoHub сам определит, выполнено ли задание
    await query.edit_message_text("🔍 Проверяем выполнение задания...")
    try:
        gender = context.user_data.get("gender")
        age = context.user_data.get("age")
        result = await call_botohub_api(user_id, is_task=True, skip=False, gender=gender, age=age)

        tasks = result.get("tasks", [])
        completed = result.get("completed", False)
        skip_flag = result.get("skip", False)
        prev_success = result.get("prev_success", False)

        if completed:
            await query.edit_message_text("🎉 Поздравляю! Вы выполнили все задания!")
            context.user_data["completed_all"] = True
            context.user_data["waiting_for_join"] = False
            return

        if prev_success:
            # Предыдущее задание выполнено, и API выдало новое
            if tasks:
                new_url = tasks[0]
                context.user_data["current_task_url"] = new_url
                context.user_data["waiting_for_join"] = True

                keyboard = [
                    [InlineKeyboardButton("✅ Я вступил", callback_data="check_sub")],
                    [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    f"✅ Предыдущее задание выполнено!\n\n📢 **Новое задание:**\n{new_url}\n\n"
                    f"Подпишитесь и нажмите «Я вступил».",
                    reply_markup=reply_markup,
                    parse_mode="Markdown",
                    disable_web_page_preview=True
                )
            else:
                await query.edit_message_text("✅ Задание выполнено, но новых заданий пока нет. Попробуйте позже.")
                context.user_data["waiting_for_join"] = False
        else:
            # prev_success == False — задание не выполнено
            current_url = context.user_data.get("current_task_url")
            await query.edit_message_text(
                f"❌ Вы всё ещё не подписаны на канал.\n\n"
                f"Пожалуйста, подпишитесь:\n{current_url}\n\n"
                f"После подписки нажмите «Я вступил» снова.",
                disable_web_page_preview=True
            )
            # Возвращаем кнопки
            keyboard = [
                [InlineKeyboardButton("✅ Я вступил", callback_data="check_sub")],
                [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_reply_markup(reply_markup)

    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка при проверке: {e}")

async def skip_task(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if context.user_data.get("mode") != "tasks" or not context.user_data.get("waiting_for_join"):
        await query.edit_message_text("⚠️ Нет активного задания для пропуска.")
        return

    await query.edit_message_text("⏩ Пропускаем задание...")
    try:
        gender = context.user_data.get("gender")
        age = context.user_data.get("age")
        # Отправляем skip=true
        result = await call_botohub_api(user_id, is_task=True, skip=True, gender=gender, age=age)

        tasks = result.get("tasks", [])
        completed = result.get("completed", False)
        skip_flag = result.get("skip", False)

        if completed:
            await query.edit_message_text("✅ Все задания выполнены! Вы великолепны!")
            context.user_data["completed_all"] = True
            context.user_data["waiting_for_join"] = False
            return

        if skip_flag or not tasks:
            await query.edit_message_text("🎉 Нет заданий для показа. Возможно, все выполнены.")
            context.user_data["waiting_for_join"] = False
            return

        # Получили новое задание после пропуска
        new_url = tasks[0]
        context.user_data["current_task_url"] = new_url
        context.user_data["waiting_for_join"] = True

        keyboard = [
            [InlineKeyboardButton("✅ Я вступил", callback_data="check_sub")],
            [InlineKeyboardButton("❌ Пропустить", callback_data="skip_task")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"⏩ Задание пропущено.\n\n📢 **Новое задание:**\n{new_url}\n\n"
            f"Подпишитесь и нажмите «Я вступил».",
            reply_markup=reply_markup,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка при пропуске: {e}")

# ========== ЗАПУСК БОТА ==========
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("regular", regular_mode))
    app.add_handler(CommandHandler("check_regular", check_regular))
    app.add_handler(CommandHandler("tasks", tasks_mode))
    app.add_handler(CommandHandler("set_gender", set_gender))
    app.add_handler(CommandHandler("set_age", set_age))

    # Callback'и кнопок
    app.add_handler(CallbackQueryHandler(check_subscription, pattern="^check_sub$"))
    app.add_handler(CallbackQueryHandler(skip_task, pattern="^skip_task$"))

    # Запуск
    print("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()