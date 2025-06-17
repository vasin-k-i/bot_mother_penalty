import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# Логгер
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Обработчик входящих сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user = update.message.from_user
    chat = update.message.chat

    logger.info(f"💬 Получено сообщение от пользователя:")
    logger.info(f"Имя: {user.first_name}")
    logger.info(f"Фамилия: {user.last_name}")
    logger.info(f"Username: {user.username}")
    logger.info(f"User ID: {user.id}")
    logger.info(f"Chat Title: {chat.title}")
    logger.info(f"Chat ID: {chat.id}")
    logger.info(f"Текст: {update.message.text}")

    await update.message.reply_text(
        f"Ваш user ID: {user.id}\nChat ID: {chat.id}"
    )

def main():
    import os

    TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    logger.info("Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
