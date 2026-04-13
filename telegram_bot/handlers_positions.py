from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes
from storage.repository_positions import get_open_positions


async def positions_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    positions = get_open_positions()
    if not positions:
        await update.message.reply_text("No open paper positions.")
        return
    lines = ["📌 Open Positions"]
    for p in positions[:10]:
        lines.append(
            f"- #{p['id']} {p.get('symbol') or 'UNKNOWN'} | entry ${p['entry_price']:.8f} | capital ${p['allocated_capital']:.2f}"
        )
    await update.message.reply_text("\n".join(lines))
