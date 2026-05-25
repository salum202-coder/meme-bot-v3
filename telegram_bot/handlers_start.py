from __future__ import annotations

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes


MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["📊 Status", "🧾 30m Digest"],
        ["🕵️ Cluster", "📋 Copy Positions"],
        ["📜 Copy Trades", "📈 Trades"],
        ["📌 Positions", "💼 Wallet"],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
    is_persistent=True,
)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    context.application.bot_data["chat_id"] = chat_id
    context.application.bot_data["default_chat_id"] = chat_id

    text = (
        "✅ Meme Bot V3 is live.\n"
        "📡 Auto alerts are enabled.\n"
        "🧾 Wallet digest runs every 30 minutes.\n"
        "📋 Paper Copy tracking is enabled.\n\n"
        "Use the fixed control panel below, or commands:\n"
        "/status - Bot status and performance\n"
        "/cluster - Wallet cluster watch\n"
        "/digest - Last 30m wallet digest\n"
        "/copy_positions - Open Paper Copy positions\n"
        "/copy_trades - Closed Paper Copy trades\n"
        "/positions - Open original paper trades\n"
        "/trades - Last original closed trades\n"
        "/wallet - Paper wallet summary"
    )

    await update.message.reply_text(text, reply_markup=MAIN_KEYBOARD)
