from __future__ import annotations

from datetime import datetime, timezone
from config import settings
from storage.repository_positions import count_open_positions, open_position


def maybe_open_paper_trade(token: dict, signal: dict) -> dict | None:
    if signal["signal"] != "ENTRY_CANDIDATE":
        return None
    if not settings.enable_auto_paper_entry:
        return None
    if count_open_positions() >= settings.max_open_positions:
        return None
    entry_price = float(token.get("price") or 0)
    if entry_price <= 0:
        return None

    capital = settings.starting_balance * settings.risk_per_trade
    quantity = capital / entry_price
    stop_loss = entry_price * (1 - settings.stop_loss_percent / 100)
    take_profit = entry_price * (1 + settings.take_profit_percent / 100)

    position = {
        "address": token["address"],
        "symbol": token.get("symbol"),
        "entry_price": entry_price,
        "quantity": quantity,
        "allocated_capital": capital,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "trailing_stop_percent": settings.trailing_stop_percent,
        "highest_price": entry_price,
        "status": "OPEN",
        "opened_at": datetime.now(timezone.utc).isoformat(),
    }
    position_id = open_position(position)
    position["id"] = position_id
    return position
