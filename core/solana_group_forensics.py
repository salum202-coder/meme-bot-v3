from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

from config import settings


FORENSICS_VERSION = "V4.36"
SYSTEM_MINTS = {
    "So11111111111111111111111111111111111111112",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short(value: str | None, left: int = 6, right: int = 6) -> str:
    if not value:
        return "N/A"
    if len(value) <= left + right:
        return value
    return f"{value[:left]}...{value[-right:]}"


def _db_path() -> str:
    path = settings.database_path
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_tables() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS forensics_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                detected_at TEXT NOT NULL,
                mint TEXT NOT NULL,
                wallet TEXT,
                label TEXT,
                event_type TEXT NOT NULL,
                event_category TEXT NOT NULL,
                signature TEXT,
                source TEXT,
                details TEXT
            )
            """
        )
        conn.commit()


def _extract(pattern: str, text: str) -> str:
    match = re.search(pattern, text or "")
    return match.group(1).strip() if match else ""


def _infer_category(event_type: str, label: str, source: str, details: str) -> str:
    text = f"{event_type} {label} {source} {details}".upper()

    if "DHT8" in text and "OUT" in text:
        return "DHT8_OUT"
    if "DHT8" in text and "IN" in text:
        return "DHT8_IN"

    if "GAMQ" in text and "OUT" in text:
        return "GAMQ_OUT"
    if "GAMQ" in text and "SELL" in text:
        return "GAMQ_SELL"
    if "GAMQ" in text and "IN" in text:
        return "GAMQ_IN"
    if "GAMQ" in text:
        return "GAMQ_EVENT"

    if "DISTRIBUTION OUT" in text or "POSSIBLE PREP FOR SELL" in text:
        return "DISTRIBUTION_OUT"
    if "DISTRIBUTION IN" in text:
        return "DISTRIBUTION_IN"

    if "SELL" in text:
        return "SELL"
    if "BUY" in text:
        return "BUY"
    if "OUT" in text:
        return "OUT"
    if "IN" in text:
        return "IN"

    return "PATTERN_EVENT"


def add_forensics_event(
    event_type: str,
    token: str = "",
    wallet: str = "",
    details: str = "",
) -> None:
    mint = token or ""

    if not mint or mint in SYSTEM_MINTS:
        return

    label = _extract(r"label=(.*?)\s+source=", details)
    source = _extract(r"source=(.*?)\s+signature=", details)
    signature = _extract(r"signature=([A-Za-z0-9]+)", details)

    category = _infer_category(event_type, label, source, details)

    try:
        _ensure_tables()
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO forensics_events (
                    detected_at, mint, wallet, label, event_type,
                    event_category, signature, source, details
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    mint,
                    wallet or "",
                    label or "",
                    event_type or "PATTERN_EVENT",
                    category,
                    signature or "",
                    source or "",
                    details or "",
                ),
            )
            conn.commit()
    except Exception:
        return


def build_forensics_report(limit: int = 30) -> str:
    _ensure_tables()

    with _connect() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM forensics_events"
        ).fetchone()["c"]

        mint_rows = conn.execute(
            """
            SELECT
                mint,
                COUNT(*) AS events,
                SUM(CASE WHEN event_category LIKE 'GAMQ%' THEN 1 ELSE 0 END) AS gamq_events,
                SUM(CASE WHEN event_category = 'DISTRIBUTION_OUT' THEN 1 ELSE 0 END) AS distribution_out,
                SUM(CASE WHEN event_category = 'DHT8_OUT' THEN 1 ELSE 0 END) AS dht8_out,
                COUNT(DISTINCT CASE WHEN event_category = 'DISTRIBUTION_OUT' THEN wallet END) AS unique_out_wallets,
                MAX(detected_at) AS last_seen
            FROM forensics_events
            GROUP BY mint
            ORDER BY MAX(id) DESC
            LIMIT 5
            """
        ).fetchall()

        recent = conn.execute(
            """
            SELECT *
            FROM forensics_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    lines = [
        f"🕵️ Solana Group Forensics {FORENSICS_VERSION}",
        "",
        "Mode: Passive surveillance only.",
        "No entry/exit decisions changed.",
        "",
        f"Events tracked: {total}",
        "",
    ]

    if mint_rows:
        lines.append("Mint summaries:")
        lines.append("")

        for row in mint_rows:
            lines.extend(
                [
                    f"• {_short(row['mint'])}",
                    f"  Events: {row['events']} | GAMq: {row['gamq_events']} | Dist OUT: {row['distribution_out']} | Unique OUT wallets: {row['unique_out_wallets']} | DHT8 OUT: {row['dht8_out']}",
                    f"  Last seen: {row['last_seen']}",
                    "",
                ]
            )

    if not recent:
        lines.extend(
            [
                "No forensic events recorded yet.",
                "",
                "Waiting for new wallet/group events.",
            ]
        )
        return "\n".join(lines)

    lines.append("Recent events:")
    lines.append("")

    for row in recent:
        lines.extend(
            [
                f"• {row['event_category']}",
                f"  Token: {_short(row['mint'])}",
                f"  Wallet: {row['label'] or _short(row['wallet'])}",
                f"  Time: {row['detected_at']}",
            ]
        )

        if row["source"]:
            lines.append(f"  Source: {row['source']}")

        if row["signature"]:
            lines.append(f"  Sig: {_short(row['signature'])}")

        lines.append("")

    return "\n".join(lines).strip()
