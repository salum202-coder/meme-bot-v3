from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes
from storage.repository_tokens import recent_discoveries
from storage.repository_positions import count_open_positions
from storage.repository_trades import trade_stats


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Save chat_id so automatic alerts can be sent after deploy/restart
    chat_id = str(update.effective_chat.id)
    context.application.bot_data["chat_id"] = chat_id
    context.application.bot_data["default_chat_id"] = chat_id

    discoveries = recent_discoveries(5)
    stats = trade_stats()
    open_positions = count_open_positions()

    profit_factor = stats.get("profit_factor", 0)
    profit_factor_text = "∞" if profit_factor >= 999 else f"{profit_factor:.2f}"

    lines = [
        "📊 Status",
        "🔔 Auto alerts: ON",
        f"Open positions: {open_positions}",
        f"Closed trades: {stats['total']}",
        f"Wins/Losses/BE: {stats['wins']}/{stats['losses']}/{stats['breakeven']}",
        f"Win rate: {stats['win_rate']:.2f}%",
        f"PnL: ${stats['pnl']:.2f}",
        f"Profit factor: {profit_factor_text}",
        f"Avg win: {stats['avg_win_pct']:.2f}%",
        f"Avg loss: {stats['avg_loss_pct']:.2f}%",
        f"Best trade: {stats['best_trade_pct']:.2f}%",
        f"Worst trade: {stats['worst_trade_pct']:.2f}%",
        "",
        "Recent discoveries:",
    ]

    if discoveries:
        for item in discoveries:
            score = item.get("last_total_score")
            score_text = f"{float(score):.1f}" if score is not None else "0.0"
            lines.append(
                f"- {item.get('symbol') or 'UNKNOWN'} | {item.get('last_signal')} | {score_text}"
            )
    else:
        lines.append("- no discoveries yet")

    await update.message.reply_text("\n".join(lines))
