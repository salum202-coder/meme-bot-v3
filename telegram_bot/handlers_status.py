from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes
from storage.repository_tokens import recent_discoveries
from storage.repository_positions import count_open_positions
from storage.repository_trades import trade_stats


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    discoveries = recent_discoveries(5)
    stats = trade_stats()
    open_positions = count_open_positions()
    lines = [
        "📊 Status",
        f"Open positions: {open_positions}",
        f"Closed trades: {stats['total']}",
        f"Win rate: {stats['win_rate']:.2f}%",
        f"PnL: ${stats['pnl']:.2f}",
        "",
        "Recent discoveries:",
    ]
    if discoveries:
        for item in discoveries:
            lines.append(f"- {item.get('symbol') or 'UNKNOWN'} | {item.get('last_signal')} | {item.get('last_total_score')}")
    else:
        lines.append("- no discoveries yet")
    await update.message.reply_text("\n".join(lines))
