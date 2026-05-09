from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)

    # Save chat_id in both places so scheduler can always access it
    context.bot_data["chat_id"] = chat_id
    context.application.bot_data["default_chat_id"] = chat_id

    await update.message.reply_text(
        "✅ Meme Bot V3 Starter is live.\n"
        "📡 Auto alerts are enabled.\n"
        "Commands: /status /wallet /positions"
    )
