from __future__ import annotations

from typing import Any
from storage.db import get_conn


def token_exists(address: str) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM discovered_tokens WHERE address = ?", (address,)).fetchone()
        return row is not None


def save_discovered_token(token: dict[str, Any], signal: str, total_score: float) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO discovered_tokens(address, symbol, name, source, discovered_at, last_signal, last_total_score)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                token.get("address"),
                token.get("symbol"),
                token.get("name"),
                token.get("source"),
                token.get("discovered_at"),
                signal,
                total_score,
            ),
        )
        conn.commit()


def save_snapshot(snapshot: dict[str, Any]) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO token_snapshots(address, timestamp, price, liquidity, volume_1h, buys_1h, sells_1h, market_cap, total_score, signal)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.get("address"),
                snapshot.get("timestamp"),
                snapshot.get("price"),
                snapshot.get("liquidity"),
                snapshot.get("volume_1h"),
                snapshot.get("buys_1h"),
                snapshot.get("sells_1h"),
                snapshot.get("market_cap"),
                snapshot.get("total_score"),
                snapshot.get("signal"),
            ),
        )
        conn.commit()


def recent_discoveries(limit: int = 10) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT address, symbol, name, last_signal, last_total_score, discovered_at FROM discovered_tokens ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
