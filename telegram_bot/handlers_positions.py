from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes
from storage.repository_positions import get_open_positions
from utils.http_client import HttpClient

http = HttpClient()


def fetch_current_price(address: str) -> float | None:
    payload = http.get_json(f"https://api.dexscreener.com/latest/dex/tokens/{address}") or {}
    pairs = payload.get("pairs") or []
    sol_pairs = [p for p in pairs if p.get("chainId") == "solana"]

    if not sol_pairs:
        return None

    pair = max(
        sol_pairs,
        key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0),
        default=None,
    )

    if not pair:
        return None

    price = pair.get("priceUsd")
    return float(price) if price else None


def _fmt_price(value) -> str:
    try:
        return f"${float(value):.8f}"
    except Exception:
        return "N/A"


def _fmt_money(value) -> str:
    try:
        return f"${float(value):.2f}"
    except Exception:
        return "$0.00"


def _fmt_pct(value) -> str:
    try:
        sign = "+" if float(value) > 0 else ""
        return f"{sign}{float(value):.2f}%"
    except Exception:
        return "N/A"


async def positions_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Save chat_id so auto alerts keep working after restart/deploy
    chat_id = str(update.effective_chat.id)
    context.application.bot_data["chat_id"] = chat_id
    context.application.bot_data["default_chat_id"] = chat_id

    positions = get_open_positions()

    if not positions:
        await update.message.reply_text("No open paper positions.")
        return

    lines = [
        "📌 Open Positions",
        "",
    ]

    for p in positions[:10]:
        position_id = p.get("id")
        symbol = p.get("symbol") or "UNKNOWN"
        address = p.get("address") or ""

        entry_price = float(p.get("entry_price") or 0)
        capital = float(p.get("allocated_capital") or 0)
        stop_loss = float(p.get("stop_loss") or 0)
        take_profit = float(p.get("take_profit") or 0)
        highest_price = float(p.get("highest_price") or entry_price)
        trailing_stop_percent = float(p.get("trailing_stop_percent") or 0)

        current_price = fetch_current_price(address)

        if current_price and entry_price > 0:
            pnl_percent = ((current_price / entry_price) - 1) * 100
            pnl_amount = capital * (pnl_percent / 100)

            distance_to_sl = ((current_price / stop_loss) - 1) * 100 if stop_loss > 0 else 0
            distance_to_tp = ((take_profit / current_price) - 1) * 100 if current_price > 0 else 0

            status_emoji = "🟢" if pnl_percent > 0 else "🔴" if pnl_percent < 0 else "⚪"

            lines.extend(
                [
                    f"{status_emoji} #{position_id} {symbol}",
                    f"Entry: {_fmt_price(entry_price)}",
                    f"Current: {_fmt_price(current_price)}",
                    f"PnL: {_fmt_money(pnl_amount)} ({_fmt_pct(pnl_percent)})",
                    f"Capital: {_fmt_money(capital)}",
                    f"SL: {_fmt_price(stop_loss)}",
                    f"TP: {_fmt_price(take_profit)}",
                    f"Highest: {_fmt_price(highest_price)}",
                    f"Trailing: {trailing_stop_percent:.2f}%",
                    f"Distance to SL: {_fmt_pct(distance_to_sl)}",
                    f"Distance to TP: {_fmt_pct(distance_to_tp)}",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    f"⚠️ #{position_id} {symbol}",
                    f"Entry: {_fmt_price(entry_price)}",
                    "Current: N/A",
                    "PnL: N/A",
                    f"Capital: {_fmt_money(capital)}",
                    f"SL: {_fmt_price(stop_loss)}",
                    f"TP: {_fmt_price(take_profit)}",
                    f"Highest: {_fmt_price(highest_price)}",
                    f"Trailing: {trailing_stop_percent:.2f}%",
                    "",
                ]
            )

    await update.message.reply_text("\n".join(lines))
