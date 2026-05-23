from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from core.wallet_digest import send_wallet_digest


async def digest_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    context.application.bot_data["chat_id"] = chat_id
    context.application.bot_data["default_chat_id"] = chat_id

    await update.message.reply_text("🧾 Building wallet cluster digest for the last 30 minutes...")
    await send_wallet_digest(context)
