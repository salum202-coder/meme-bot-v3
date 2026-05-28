from __future__ import annotations

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes


MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["📊 Status", "🧾 30m Digest"],
        ["🕵️ Cluster", "🧠 Cluster Map"],
        ["🧠 Pattern Brain"],
        ["📋 Copy Positions", "📜 Copy Trades"],
        ["💼 Copy Wallet"],
        ["🔴 Close Copy All"],
        ["🟡 Close Copy 50%", "🟠 Close Copy 25%"],
        ["📈 Trades", "📌 Positions"],
        ["💼 Wallet"],
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
        "📋 Paper Copy tracking is enabled.\n"
        "🧯 Manual Paper Copy close controls are enabled.\n\n"
        "Use the fixed control panel below, or commands:\n"
        "/status - Bot status and performance\n"
        "/cluster - Wallet cluster watch\n"
        "/digest - Last 30m wallet digest\n"
        "/copy_positions - Open Paper Copy positions\n"
        "/copy_trades - Closed Paper Copy trades\n"
        "/copy_wallet - Paper Copy wallet accounting\n"
        "/copy_close_all - Manual close full Paper Copy position\n"
        "/copy_close_50 - Manual close 50% of remaining Paper Copy position\n"
        "/copy_close_25 - Manual close 25% of remaining Paper Copy position\n"
        "/positions - Open original paper trades\n"
        "/trades - Last original closed trades\n"
        "/wallet - Paper wallet summary"
    )

    await update.message.reply_text(text, reply_markup=MAIN_KEYBOARD)
