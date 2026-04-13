from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes
from config import settings
from storage.repository_positions import get_open_positions
from storage.repository_trades import trade_stats


async def wallet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    open_positions = get_open_positions()
    allocated = sum(float(p["allocated_capital"]) for p in open_positions)
    stats = trade_stats()
    balance = settings.starting_balance + stats["pnl"]
    free_cash = balance - allocated
    await update.message.reply_text(
        "💼 Wallet\n"
        f"Starting Balance: ${settings.starting_balance:.2f}\n"
        f"Realized PnL: ${stats['pnl']:.2f}\n"
        f"Estimated Balance: ${balance:.2f}\n"
        f"Allocated: ${allocated:.2f}\n"
        f"Free Cash: ${free_cash:.2f}"
    )
