from __future__ import annotations

from typing import Any
from storage.db import get_conn


def save_trade(trade: dict[str, Any]) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO paper_trades(address, symbol, entry_price, exit_price, quantity, allocated_capital,
            pnl_amount, pnl_percent, entry_reason, exit_reason, opened_at, closed_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade["address"],
                trade.get("symbol"),
                trade["entry_price"],
                trade["exit_price"],
                trade["quantity"],
                trade["allocated_capital"],
                trade["pnl_amount"],
                trade["pnl_percent"],
                trade.get("entry_reason"),
                trade.get("exit_reason"),
                trade["opened_at"],
                trade["closed_at"],
            ),
        )
        conn.commit()


def trade_stats() -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(pnl_amount), 0) AS pnl,
                   COALESCE(SUM(CASE WHEN pnl_amount > 0 THEN 1 ELSE 0 END), 0) AS wins
            FROM paper_trades
            """
        ).fetchone()
        total = int(row["total"])
        wins = int(row["wins"])
        return {
            "total": total,
            "wins": wins,
            "losses": total - wins,
            "win_rate": (wins / total * 100) if total else 0.0,
            "pnl": float(row["pnl"]),
        }
