from __future__ import annotations

from typing import Any
from storage.db import get_conn


def open_position(position: dict[str, Any]) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO paper_positions(
                address, symbol, entry_price, quantity, allocated_capital,
                stop_loss, take_profit, trailing_stop_percent,
                highest_price, status, opened_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                position["address"],
                position.get("symbol"),
                position["entry_price"],
                position["quantity"],
                position["allocated_capital"],
                position["stop_loss"],
                position["take_profit"],
                position["trailing_stop_percent"],
                position["highest_price"],
                position["status"],
                position["opened_at"],
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_open_positions() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM paper_positions WHERE status = 'OPEN' ORDER BY id DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def count_open_positions() -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM paper_positions WHERE status = 'OPEN'"
        ).fetchone()
        return int(row["c"])


def has_open_position(address: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM paper_positions
            WHERE address = ? AND status = 'OPEN'
            LIMIT 1
            """,
            (address,),
        ).fetchone()
        return row is not None


def update_highest_price(position_id: int, highest_price: float) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE paper_positions SET highest_price = ? WHERE id = ?",
            (highest_price, position_id),
        )
        conn.commit()


def update_stop_loss(position_id: int, stop_loss: float) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE paper_positions SET stop_loss = ? WHERE id = ?",
            (stop_loss, position_id),
        )
        conn.commit()


def close_position(position_id: int, closed_at: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE paper_positions SET status = 'CLOSED', closed_at = ? WHERE id = ?",
            (closed_at, position_id),
        )
        conn.commit()
