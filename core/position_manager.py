from __future__ import annotations

from datetime import datetime, timezone
from storage.repository_positions import get_open_positions, update_highest_price, close_position
from storage.repository_trades import save_trade
from core.notifier import build_position_close_alert


def evaluate_positions(fetch_price_func, notify_func) -> None:
    positions = get_open_positions()

    for position in positions:
        current_price = fetch_price_func(position["address"])
        if not current_price or current_price <= 0:
            continue

        entry_price = position["entry_price"]

        # ======================
        # 🔄 تحديث أعلى سعر
        # ======================
        highest_price = max(position["highest_price"], current_price)
        if highest_price > position["highest_price"]:
            update_highest_price(position["id"], highest_price)

        # ======================
        # 🧠 BREAK EVEN LOGIC
        # ======================
        profit_percent = ((current_price / entry_price) - 1) * 100

        if profit_percent >= 5:
            # نحمي الصفقة (نرفع الستوب)
            position["stop_loss"] = max(position["stop_loss"], entry_price)

        # ======================
        # 🔥 TRAILING STOP
        # ======================
        trailing_stop = highest_price * (1 - position["trailing_stop_percent"] / 100)

        exit_reason = None

        # ======================
        # 🛑 شروط الخروج
        # ======================

        if current_price <= position["stop_loss"]:
            exit_reason = "Stop loss"

        elif current_price >= position["take_profit"]:
            exit_reason = "Take profit"

        elif current_price <= trailing_stop and highest_price > entry_price:
            exit_reason = "Trailing stop"

        if not exit_reason:
            continue

        # ======================
        # 📊 حساب الأرباح
        # ======================
        pnl_amount = (current_price - entry_price) * position["quantity"]
        pnl_percent = ((current_price / entry_price) - 1) * 100
        closed_at = datetime.now(timezone.utc).isoformat()

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
                exit_reason
            )
        )
