from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from storage.db import get_conn


def get_last_signature(wallet_address: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT last_signature
            FROM wallet_watch_state
            WHERE wallet_address = ?
            """,
            (wallet_address,),
        ).fetchone()

        if not row:
            return None

        return row["last_signature"]


def save_wallet_signature(
    wallet_address: str,
    label: str,
    last_signature: str,
    last_seen_at: str | None = None,
) -> None:
    updated_at = datetime.now(timezone.utc).isoformat()

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO wallet_watch_state(
                wallet_address,
                label,
                last_signature,
                last_seen_at,
                updated_at
            )
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(wallet_address)
            DO UPDATE SET
                label = excluded.label,
                last_signature = excluded.last_signature,
                last_seen_at = excluded.last_seen_at,
                updated_at = excluded.updated_at
            """,
            (
                wallet_address,
                label,
                last_signature,
                last_seen_at,
                updated_at,
            ),
        )
        conn.commit()


def get_wallet_watch_states() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT wallet_address, label, last_signature, last_seen_at, updated_at
            FROM wallet_watch_state
            ORDER BY label ASC
            """
        ).fetchall()

        return [dict(row) for row in rows]
