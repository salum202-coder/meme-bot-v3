from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    context.application.bot_data["chat_id"] = chat_id
    context.application.bot_data["default_chat_id"] = chat_id

    text = (
        "✅ Meme Bot V3 Starter is live.\n"
        "📡 Auto alerts are enabled.\n\n"
        "Commands:\n"
        "/status - Bot status and performance\n"
        "/positions - Open paper trades\n"
        "/trades - Last closed trades\n"
        "/wallet - Paper wallet summary"
    )

    await update.message.reply_text(text)
