from __future__ import annotations

from datetime import datetime, timezone
from storage.repository_positions import get_open_positions, update_highest_price, close_position
from storage.repository_trades import save_trade
from core.notifier import build_position_close_alert


def evaluate_positions(fetch_price_func, notify_func) -> None:
    positions = get_open_positions()

    for position in positions:
        current_price = fetch_price_func(position["address"])
        entry_price = float(position["entry_price"])
        closed_at = datetime.now(timezone.utc).isoformat()

        # If token price disappeared, close it as dead/no price instead of keeping it open forever.
        if not current_price or current_price <= 0:
            current_price = 0.0
            exit_reason = "No price data / dead token"

            pnl_amount = -float(position["allocated_capital"])
            pnl_percent = -100.0

            save_trade(
                {
                    "address": position["address"],
                    "symbol": position.get("symbol"),
                    "entry_price": entry_price,
                    "exit_price": current_price,
                    "quantity": position["quantity"],
                    "allocated_capital": position["allocated_capital"],
                    "pnl_amount": pnl_amount,
                    "pnl_percent": pnl_percent,
                    "entry_reason": "ENTRY_CANDIDATE",
                    "exit_reason": exit_reason,
                    "opened_at": position["opened_at"],
                    "closed_at": closed_at,
                }
            )

            close_position(position["id"], closed_at)

            notify_func(
                build_position_close_alert(
                    position,
                    current_price,
                    pnl_amount,
                    pnl_percent,
                    exit_reason,
                )
            )
            continue

        current_price = float(current_price)

        highest_price = max(float(position["highest_price"]), current_price)
        if highest_price > float(position["highest_price"]):
            update_highest_price(position["id"], highest_price)

        profit_percent = ((current_price / entry_price) - 1) * 100

        stop_loss = float(position["stop_loss"])
        if profit_percent >= 5:
            stop_loss = max(stop_loss, entry_price)

        trailing_stop = highest_price * (1 - float(position["trailing_stop_percent"]) / 100)

        exit_reason = None

        if current_price <= stop_loss:
            exit_reason = "Stop loss"
        elif current_price >= float(position["take_profit"]):
            exit_reason = "Take profit"
        elif current_price <= trailing_stop and highest_price > entry_price:
            exit_reason = "Trailing stop"

        if not exit_reason:
            continue

        pnl_amount = (current_price - entry_price) * float(position["quantity"])
        pnl_percent = ((current_price / entry_price) - 1) * 100

        save_trade(
            {
                "address": position["address"],
                "symbol": position.get("symbol"),
                "entry_price": entry_price,
                "exit_price": current_price,
                "quantity": position["quantity"],
                "allocated_capital": position["allocated_capital"],
                "pnl_amount": pnl_amount,
                "pnl_percent": pnl_percent,
                "entry_reason": "ENTRY_CANDIDATE",
                "exit_reason": exit_reason,
                "opened_at": position["opened_at"],
                "closed_at": closed_at,
            }
        )

        close_position(position["id"], closed_at)

        notify_func(
            build_position_close_alert(
                position,
                current_price,
                pnl_amount,
                pnl_percent,
                exit_reason,
            )
        )
