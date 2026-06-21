from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


FORENSICS_VERSION = "V4.35"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_forensics_report(limit: int = 30) -> str:
    lines = [
        f"🕵️ Solana Group Forensics {FORENSICS_VERSION}",
        "",
        "Mode: Passive surveillance only.",
        "No entry/exit decisions changed.",
        "",
        "Purpose:",
        "- Track group behavior from token birth to collapse.",
        "- Watch DHT8, GAMq, treasury wallets, and cluster wallets.",
        "- Record swaps, transfers, liquidity adds/removes, and SOL movements.",
        "",
        "Status:",
        "- Forensics module installed.",
        "- No live event storage added yet.",
        "",
        "Next step:",
        "- Add database table for forensic events.",
    ]

    return "\n".join(lines)
