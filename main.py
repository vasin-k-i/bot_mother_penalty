import os
from dotenv import load_dotenv
load_dotenv()

import json
import datetime
import logging
import gspread
import openai  # исправлено здесь

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    filters,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from oauth2client.service_account import ServiceAccountCredentials

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Переменные окружения
TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
OPENAI_API_KEY = os.environ['OPENAI_API_KEY']
TARGET_CHAT_ID = int(os.environ['TARGET_CHAT_ID'])
GOOGLE_SHEET_ID = os.environ['GOOGLE_SHEET_ID']
GOOGLE_CREDENTIALS_JSON_PATH = os.environ['GOOGLE_CREDENTIALS_JSON_PATH']

openai.api_key = OPENAI_API_KEY  # исправлено здесь

# Авторизация в Google Sheets
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
with open(GOOGLE_CREDENTIALS_JSON_PATH) as f:
    creds_dict = json.load(f)
credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
gc = gspread.authorize(credentials)
sheet = gc.open_by_key(GOOGLE_SHEET_ID).sheet1

# Определение, является ли текст советом
async def is_advice(text: str) -> bool:
    prompt = (
        "посмотри на текущее сообщение и скажи - является ли оно советом. "
        "Если сомневаешься - дай оценку от 1 до 5 насколько это является советом и ответь Да, "
        "если это совет или если твоя оценка что это совет от 4 до 5 или ответь Нет, "
        "если это не совет или твоя оценка ниже 4.\n"
        f'Сообщение: "{text}"'
    )
    try:
        response = client.chat.completions.create(
    model="gpt-3.5-turbo",
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

# Подсчёт штрафов и советов за неделю
def get_week_stats(user_id):
    records = sheet.get_all_records()
    today = datetime.datetime.now()
    week_start = today - datetime.timedelta(days=today.weekday())
    penalties = 0
    advices = 0

    for row in records:
        row_user_id = int(row["user_id"])
        row_date = datetime.datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
        if row_user_id == user_id and row_date >= week_start:
            if int(row["penalty"]) > 0:
                penalties += 1
            else:
                advices += 1
    return penalties, advices

# Обработка входящих сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user = update.message.from_user
    text = update.message.text

    logger.info(f"Проверяем сообщение от {user.id}: {text}")

    if await is_advice(text):
        today = datetime.datetime.now().weekday()
        penalties, advices = get_week_stats(user.id)

        if today == 0:
            sheet.append_row([str(user.id), user.username, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), text, "0"])
            await update.message.reply_text(
                f"Сегодня понедельник, поэтому благодарим за совет. Это ваш {advices + 1}-й совет на этой неделе."
            )
        else:
            save_penalty(user.id, user.username, text)
            await update.message.reply_text(
                f"Сегодня не понедельник. А значит не День советов!\n"
                f"Получаете штрафной балл.\n"
                f"Текущее количество штрафных баллов на неделе: {penalties + 1}\n"
                f"Текущее количество советов за неделю: {advices}"
            )
    else:
        logger.info("Советом не признано")

# Еженедельный отчёт
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

# Запуск
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_weekly_report, 'cron', day_of_week='sun', hour=18, minute=0, args=[app.bot])
    scheduler.start()

    logger.info("Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
