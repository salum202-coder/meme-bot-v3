from __future__ import annotations

from datetime import datetime, timezone
from storage.repository_positions import (
    get_open_positions,
    update_highest_price,
    update_stop_loss,
    close_position,
)
from storage.repository_trades import save_trade
from core.notifier import build_position_close_alert


# In-memory protection against temporary API price failures.
# If price disappears once, we do not immediately close as -100%.
_MISSING_PRICE_COUNTS: dict[int, int] = {}
MAX_MISSING_PRICE_CHECKS = 3


def evaluate_positions(fetch_price_func, notify_func) -> None:
    positions = get_open_positions()

    for position in positions:
        position_id = int(position["id"])
        current_price = fetch_price_func(position["address"])
        entry_price = float(position["entry_price"])
        closed_at = datetime.now(timezone.utc).isoformat()

        # Handle missing price data safely
        if not current_price or current_price <= 0:
            _MISSING_PRICE_COUNTS[position_id] = _MISSING_PRICE_COUNTS.get(position_id, 0) + 1

            if _MISSING_PRICE_COUNTS[position_id] < MAX_MISSING_PRICE_CHECKS:
                continue

            current_price = 0.0
            exit_reason = f"No price data / dead token after {MAX_MISSING_PRICE_CHECKS} checks"

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

            close_position(position_id, closed_at)
            _MISSING_PRICE_COUNTS.pop(position_id, None)

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

        _MISSING_PRICE_COUNTS.pop(position_id, None)

        current_price = float(current_price)

        highest_price = max(float(position["highest_price"]), current_price)
        if highest_price > float(position["highest_price"]):
            update_highest_price(position_id, highest_price)

        profit_percent = ((current_price / entry_price) - 1) * 100

        stop_loss = float(position["stop_loss"])

        # Break even protection:
        # If trade reaches +5%, move SL to entry and persist it in DB.
        if profit_percent >= 5 and stop_loss < entry_price:
            stop_loss = entry_price
            update_stop_loss(position_id, stop_loss)

        trailing_stop = highest_price * (1 - float(position["trailing_stop_percent"]) / 100)

        exit_reason = None

        if current_price <= stop_loss:
            exit_reason = "Stop loss / Break even"
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

        close_position(position_id, closed_at)
        _MISSING_PRICE_COUNTS.pop(position_id, None)

        notify_func(
            build_position_close_alert(
                position,
                current_price,
                pnl_amount,
                pnl_percent,
                exit_reason,
            )
        )
