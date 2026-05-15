from __future__ import annotations

from typing import Any
from storage.db import get_conn


def save_trade(trade: dict[str, Any]) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO paper_trades(
                address, symbol, entry_price, exit_price, quantity, allocated_capital,
                pnl_amount, pnl_percent, entry_reason, exit_reason, opened_at, closed_at
            )
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


def has_traded_token(address: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM paper_trades
            WHERE address = ?
            LIMIT 1
            """,
            (address,),
        ).fetchone()
        return row is not None


def trade_stats() -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(pnl_amount), 0) AS pnl,
                COALESCE(SUM(CASE WHEN pnl_amount > 0 THEN 1 ELSE 0 END), 0) AS wins,
                COALESCE(SUM(CASE WHEN pnl_amount < 0 THEN 1 ELSE 0 END), 0) AS losses,
                COALESCE(SUM(CASE WHEN pnl_amount = 0 THEN 1 ELSE 0 END), 0) AS breakeven,
                COALESCE(SUM(CASE WHEN pnl_amount > 0 THEN pnl_amount ELSE 0 END), 0) AS gross_profit,
                COALESCE(ABS(SUM(CASE WHEN pnl_amount < 0 THEN pnl_amount ELSE 0 END)), 0) AS gross_loss,
                COALESCE(AVG(CASE WHEN pnl_amount > 0 THEN pnl_percent END), 0) AS avg_win_pct,
                COALESCE(AVG(CASE WHEN pnl_amount < 0 THEN pnl_percent END), 0) AS avg_loss_pct,
                COALESCE(MAX(pnl_percent), 0) AS best_trade_pct,
                COALESCE(MIN(pnl_percent), 0) AS worst_trade_pct
            FROM paper_trades
            """
        ).fetchone()

        total = int(row["total"])
        wins = int(row["wins"])
        losses = int(row["losses"])
        breakeven = int(row["breakeven"])

        gross_profit = float(row["gross_profit"])
        gross_loss = float(row["gross_loss"])

        if gross_loss > 0:
            profit_factor = gross_profit / gross_loss
        elif gross_profit > 0:
            profit_factor = 999.0
        else:
            profit_factor = 0.0

        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "breakeven": breakeven,
            "win_rate": (wins / total * 100) if total else 0.0,
            "pnl": float(row["pnl"]),
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "profit_factor": profit_factor,
            "avg_win_pct": float(row["avg_win_pct"]),
            "avg_loss_pct": float(row["avg_loss_pct"]),
            "best_trade_pct": float(row["best_trade_pct"]),
            "worst_trade_pct": float(row["worst_trade_pct"]),
        }
