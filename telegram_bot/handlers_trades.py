from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes
from storage.repository_trades import recent_trades


def _short_address(address: str) -> str:
    if not address:
        return "N/A"
    if len(address) <= 12:
        return address
    return f"{address[:6]}...{address[-6:]}"


def _short_time(value: str | None) -> str:
    if not value:
        return "N/A"
    return value.replace("T", " ")[:19]


async def trades_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    trades = recent_trades(10)

    lines = [
        "📈 Last Paper Trades",
        "",
    ]

    if not trades:
        lines.append("No closed trades yet.")
        await update.message.reply_text("\n".join(lines))
        return

    for trade in trades:
        pnl_amount = float(trade.get("pnl_amount") or 0)
        pnl_percent = float(trade.get("pnl_percent") or 0)

        if pnl_amount > 0:
            emoji = "✅"
            result = "WIN"
        elif pnl_amount < 0:
            emoji = "❌"
            result = "LOSS"
        else:
            emoji = "➖"
            result = "BE"

        symbol = trade.get("symbol") or "UNKNOWN"
        entry = float(trade.get("entry_price") or 0)
        exit_price = float(trade.get("exit_price") or 0)
        reason = trade.get("exit_reason") or "N/A"
        closed_at = _short_time(trade.get("closed_at"))
        address = trade.get("address") or ""

        lines.extend(
            [
                f"{emoji} #{trade.get('id')} {symbol} — {result}",
                f"Entry: ${entry:.8f}",
                f"Exit: ${exit_price:.8f}",
                f"PnL: ${pnl_amount:.2f} ({pnl_percent:.2f}%)",
                f"Reason: {reason}",
                f"Closed: {closed_at}",
                f"Contract: {_short_address(address)}",
                "",
            ]
        )

    await update.message.reply_text("\n".join(lines))
