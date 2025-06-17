import os
import json
import datetime
import logging
import openai
import gspread

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    filters,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from oauth2client.service_account import ServiceAccountCredentials

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Константы из переменных окружения
TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
OPENAI_API_KEY = os.environ['OPENAI_API_KEY']
TARGET_USERNAME = os.environ['TARGET_USERNAME']
TARGET_CHAT_ID = int(os.environ['TARGET_CHAT_ID'])
SHEET_NAME = os.environ['SHEET_NAME']
GOOGLE_CREDENTIALS_JSON = os.environ['GOOGLE_CREDENTIALS_JSON']

# Настройка OpenAI
openai.api_key = OPENAI_API_KEY

# Авторизация в Google Sheets
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
gc = gspread.authorize(credentials)
sheet = gc.open(SHEET_NAME).sheet1  # первая вкладка

# Проверка: является ли сообщение советом
async def is_advice(text: str) -> bool:
    prompt = f"""Определи, является ли следующее сообщение советом. Ответь "да" или "нет".
Сообщение: "{text}"
"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        result = response['choices'][0]['message']['content'].strip().lower()
        return 'да' in result
    except Exception as e:
        logger.error(f"Ошибка OpenAI: {e}")
        return False

# Сохранение штрафа в таблицу
def save_penalty(user_id, username, message):
    date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row([str(user_id), username, date, message, "1"])

# Обработка сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user = update.message.from_user
    text = update.message.text

    if user.username != TARGET_USERNAME:
        return

    logger.info(f"Проверяем сообщение от @{user.username}: {text}")

    if await is_advice(text):
        today = datetime.datetime.now().weekday()  # 0 = понедельник
        if today == 0:
            await update.message.reply_text("Сегодня понедельник. Совет принят.")
        else:
            save_penalty(user.id, user.username, text)
            await update.message.reply_text("Сегодня не понедельник. Совет не принят. Штрафной балл.")
    else:
        logger.info("Советом не признано")

# Отправка еженедельного отчёта
async def send_weekly_report(context: ContextTypes.DEFAULT_TYPE):
    try:
        records = sheet.get_all_records()
        summary = {}

        for row in records:
            username = row['username']
            summary[username] = summary.get(username, 0) + int(row['penalty'])

        if not summary:
            return

        lines = [f"📊 Еженедельный отчёт по штрафам:\n"]
        for user, count in summary.items():
            lines.append(f"@{user} — {count} штрафов")

        lines.append("\nСледите за языком. Следующий понедельник не за горами.")
        report = "\n".join(lines)

        await context.bot.send_message(chat_id=TARGET_CHAT_ID, text=report)

    except Exception as e:
        logger.error(f"Ошибка при отправке отчёта: {e}")

# Запуск бота
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Обработчик сообщений
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    # Планировщик отчёта
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_weekly_report, 'cron', day_of_week='sun', hour=18, minute=0, args=[app.bot])
    scheduler.start()

    logger.info("Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()

