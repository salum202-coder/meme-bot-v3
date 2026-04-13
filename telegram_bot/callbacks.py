from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes


async def generic_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(f"Callback received: {query.data}")
