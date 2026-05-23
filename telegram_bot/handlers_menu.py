from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from telegram_bot.handlers_status import status_handler
from telegram_bot.handlers_wallet_watch import cluster_handler
from telegram_bot.handlers_trades import trades_handler
from telegram_bot.handlers_positions import positions_handler
from telegram_bot.handlers_wallet import wallet_handler
from telegram_bot.handlers_digest import digest_handler


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()

    if text == "📊 Status":
        await status_handler(update, context)
        return

    if text == "🧾 30m Digest":
        await digest_handler(update, context)
        return

    if text == "🕵️ Cluster":
        await cluster_handler(update, context)
        return

    if text == "📈 Trades":
        await trades_handler(update, context)
        return

    if text == "📌 Positions":
        await positions_handler(update, context)
        return

    if text == "💼 Wallet":
        await wallet_handler(update, context)
        return

    await update.message.reply_text(
        "Choose from the control panel below or use /start to show it again."
    )
