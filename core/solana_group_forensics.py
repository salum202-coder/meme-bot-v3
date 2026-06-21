from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


FORENSICS_VERSION = "V4.35"

FORENSICS_EVENTS: list[dict[str, Any]] = []


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short(value: str | None, left: int = 6, right: int = 6) -> str:
    if not value:
        return "N/A"
    if len(value) <= left + right:
        return value
    return f"{value[:left]}...{value[-right:]}"


def add_forensics_event(
    event_type: str,
    token: str = "",
    wallet: str = "",
    details: str = "",
) -> None:
    FORENSICS_EVENTS.append(
        {
            "time": _now_iso(),
            "event_type": event_type or "UNKNOWN",
            "token": token or "N/A",
            "wallet": wallet or "N/A",
            "details": details or "",
        }
    )

    if len(FORENSICS_EVENTS) > 1000:
        del FORENSICS_EVENTS[:100]


def build_forensics_report(limit: int = 30) -> str:
    lines = [
        f"🕵️ Solana Group Forensics {FORENSICS_VERSION}",
        "",
        "Mode: Passive surveillance only.",
        "No entry/exit decisions changed.",
        "",
        f"Events tracked: {len(FORENSICS_EVENTS)}",
        "",
    ]

    recent = FORENSICS_EVENTS[-limit:]

    if not recent:
        lines.extend(
            [
                "No forensic events recorded yet.",
                "",
                "Next step:",
                "- Connect this module to wallet/group events.",
                "- Then it will record DHT8, GAMq, treasury transfers, swaps, and exits.",
            ]
        )
        return "\n".join(lines)

    lines.append("Recent events:")
    lines.append("")

    for event in reversed(recent):
        lines.extend(
            [
                f"• {event.get('event_type') or 'UNKNOWN'}",
                f"  Token: {_short(str(event.get('token') or ''))}",
                f"  Wallet: {_short(str(event.get('wallet') or ''))}",
                f"  Time: {event.get('time') or 'N/A'}",
            ]
        )

        details = event.get("details") or ""
        if details:
            lines.append(f"  Details: {details}")

        lines.append("")

    return "\n".join(lines).strip()
