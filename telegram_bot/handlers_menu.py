from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from telegram_bot.handlers_status import status_handler
from telegram_bot.handlers_wallet_watch import (
    cluster_handler,
    copy_positions_handler,
    copy_trades_handler,
    copy_wallet_handler,
    copy_close_all_handler,
    copy_close_50_handler,
    copy_close_25_handler,
    cluster_map_handler,
    pattern_brain_handler,
)
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

    if text == "📋 Copy Positions":
        await copy_positions_handler(update, context)
        return

    if text == "🧠 Cluster Map":
        await cluster_map_handler(update, context)
        return

    if text == "🧠 Pattern Brain":
        await pattern_brain_handler(update, context)
        return

    if text == "📜 Copy Trades":
        await copy_trades_handler(update, context)
        return

    if text == "💼 Copy Wallet":
        await copy_wallet_handler(update, context)
        return

    if text == "🔴 Close Copy All":
        await copy_close_all_handler(update, context)
        return

    if text == "🟡 Close Copy 50%":
        await copy_close_50_handler(update, context)
        return

    if text == "🟠 Close Copy 25%":
        await copy_close_25_handler(update, context)
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
