from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.bot_data["chat_id"] = str(update.effective_chat.id)
    await update.message.reply_text(
        "✅ Meme Bot V3 Starter is live.\n"
        "Commands: /status /wallet /positions"
    )
