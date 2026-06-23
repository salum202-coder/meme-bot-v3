from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from config import settings


FORENSICS_TIMELINE_VERSION = "V5.0"

# V5.0 is read-only. It does not change entry/exit decisions.
# It reconstructs a case timeline from existing forensics_events and paper_copy_trades.

DANGER_WALLET_KEYWORDS = (
    "DHT8",
    "GAMq",
    "B6ut",
    "FdwJBf",
    "47ry",
    "94hQ",
    "4hEf",
)

SYSTEM_MINTS = {
    "So11111111111111111111111111111111111111112",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
}


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

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


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _short(value: str | None, left: int = 6, right: int = 6) -> str:
    if not value:
        return "N/A"
    value = str(value)
    if len(value) <= left + right:
        return value
    return f"{value[:left]}...{value[-right:]}"


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _duration_text(start: str | None, end: str | None) -> str:
    a = _parse_iso(start)
    b = _parse_iso(end)
    if not a or not b:
        return "N/A"
    seconds = max(0, int((b - a).total_seconds()))
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    minutes = minutes % 60
    if hours < 24:
        return f"{hours}h {minutes}m"
    days = hours // 24
    hours = hours % 24
    return f"{days}d {hours}h"


def _to_decimal(value: Any, default: str = "0") -> Decimal:
    try:
        if value is None or value == "":
            return Decimal(default)
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def _fmt_decimal(value: Decimal | float | int | str | None, places: int = 2) -> str:
    try:
        return f"{float(_to_decimal(value)):,.{places}f}"
    except Exception:
        return str(value)


def _fmt_usd(value: Decimal | float | int | str | None) -> str:
    amount = _to_decimal(value)
    if amount == 0:
        return "$0"
    abs_amount = abs(amount)
    if abs_amount >= Decimal("1"):
        return f"${float(amount):,.2f}"
    if abs_amount >= Decimal("0.0001"):
        return f"${float(amount):.8f}".rstrip("0").rstrip(".")
    return f"${float(amount):.12f}".rstrip("0").rstrip(".")


def _extract_detail_number(details: str, key: str) -> Decimal:
    # Supports details like: price=0.001 liquidity=85000 volume=123000
    match = re.search(rf"{re.escape(key)}\s*=\s*([0-9.]+)", details or "", re.IGNORECASE)
    if not match:
        return Decimal("0")
    return _to_decimal(match.group(1))


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _resolve_mint(conn: sqlite3.Connection, mint_query: str | None = None) -> str | None:
    query = (mint_query or "").strip()

    if query:
        row = conn.execute(
            """
            SELECT mint
            FROM forensics_events
            WHERE mint = ? OR mint LIKE ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (query, f"{query}%"),
        ).fetchone()
        if row:
            return str(row["mint"])

        if _table_exists(conn, "paper_copy_trades"):
            row = conn.execute(
                """
                SELECT mint
                FROM paper_copy_trades
                WHERE mint = ? OR mint LIKE ? OR symbol LIKE ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (query, f"{query}%", f"%{query}%"),
            ).fetchone()
            if row:
                return str(row["mint"])

        return None

    row = conn.execute(
        """
        SELECT mint
        FROM forensics_events
        WHERE mint NOT IN ({})
        GROUP BY mint
        ORDER BY MAX(id) DESC
        LIMIT 1
        """.format(",".join("?" for _ in SYSTEM_MINTS)),
        tuple(SYSTEM_MINTS),
    ).fetchone()
    return str(row["mint"]) if row else None


def _load_forensics_events(conn: sqlite3.Connection, mint: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM forensics_events
        WHERE mint = ?
        ORDER BY detected_at ASC, id ASC
        """,
        (mint,),
    ).fetchall()
    return [dict(row) for row in rows]


def _load_paper_trade(conn: sqlite3.Connection, mint: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "paper_copy_trades"):
        return None

    row = conn.execute(
        """
        SELECT *
        FROM paper_copy_trades
        WHERE mint = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (mint,),
    ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Timeline intelligence
# ---------------------------------------------------------------------------

def _event_label(event: dict[str, Any]) -> str:
    return str(event.get("label") or event.get("wallet") or "Unknown")


def _event_category(event: dict[str, Any]) -> str:
    return str(event.get("event_category") or event.get("event_type") or "PATTERN_EVENT")


def _event_source(event: dict[str, Any]) -> str:
    return str(event.get("source") or "")


def _is_danger_wallet(label: str) -> bool:
    return any(keyword.lower() in label.lower() for keyword in DANGER_WALLET_KEYWORDS)


def _classify_timeline_event(event: dict[str, Any]) -> str:
    category = _event_category(event)
    source = _event_source(event)
    label = _event_label(event)
    text = f"{category} {source} {label}".upper()

    if "PAPER_COPY_ENTRY" in source.upper() or category == "BUY":
        return "BOT / PAPER ENTRY"
    if "PAPER_COPY_EXIT" in source.upper():
        return "BOT / PAPER EXIT"
    if "DHT8" in text and "OUT" in text:
        return "DHT8 EXIT SIGNAL"
    if "DHT8" in text and "IN" in text:
        return "DHT8 IN"
    if "GAMQ" in text and ("OUT" in text or "SELL" in text):
        return "GAMq EXIT SIGNAL"
    if "GAMQ" in text and "IN" in text:
        return "GAMq IN"
    if "DISTRIBUTION_OUT" in category or "DISTRIBUTION OUT" in text:
        return "DISTRIBUTION OUT"
    if "DISTRIBUTION_IN" in category or "DISTRIBUTION IN" in text:
        return "DISTRIBUTION IN"
    if "SELL" in text:
        return "SELL"
    if "BUY" in text:
        return "BUY"
    if "OUT" in text:
        return "OUT"
    if "IN" in text:
        return "IN"
    return "PATTERN EVENT"


def _first_event(events: list[dict[str, Any]], predicate) -> dict[str, Any] | None:
    for event in events:
        try:
            if predicate(event):
                return event
        except Exception:
            continue
    return None


def _unique_wallet_order(events: list[dict[str, Any]], max_items: int = 12) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []

    for event in events:
        label = _event_label(event)
        if not label or label == "Unknown":
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(label)
        if len(ordered) >= max_items:
            break

    return ordered


def _market_points(events: list[dict[str, Any]]) -> dict[str, Decimal]:
    prices: list[Decimal] = []
    liquidities: list[Decimal] = []

    for event in events:
        details = str(event.get("details") or "")
        price = _extract_detail_number(details, "price") or _extract_detail_number(details, "price_usd")
        liquidity = _extract_detail_number(details, "liquidity") or _extract_detail_number(details, "liquidity_usd")
        if price > 0:
            prices.append(price)
        if liquidity > 0:
            liquidities.append(liquidity)

    return {
        "first_price": prices[0] if prices else Decimal("0"),
        "peak_price": max(prices) if prices else Decimal("0"),
        "last_price": prices[-1] if prices else Decimal("0"),
        "first_liquidity": liquidities[0] if liquidities else Decimal("0"),
        "peak_liquidity": max(liquidities) if liquidities else Decimal("0"),
        "last_liquidity": liquidities[-1] if liquidities else Decimal("0"),
    }


def _exit_verdict(events: list[dict[str, Any]], trade: dict[str, Any] | None) -> tuple[str, str]:
    if not trade:
        return "UNKNOWN", "No paper trade found for this mint."

    status = str(trade.get("status") or "")
    exit_reason = str(trade.get("exit_reason") or "")
    closed_at = str(trade.get("closed_at") or "")

    if status != "CLOSED" or not closed_at:
        return "OPEN / UNKNOWN", "Trade is still open or exit time is missing."

    exit_dt = _parse_iso(closed_at)
    if not exit_dt:
        return "UNKNOWN", "Exit time could not be parsed."

    first_danger = _first_event(
        events,
        lambda e: _is_danger_wallet(_event_label(e)) and _parse_iso(e.get("detected_at")) is not None,
    )

    first_out = _first_event(
        events,
        lambda e: "OUT" in _event_category(e).upper() or "SELL" in _event_category(e).upper(),
    )

    first_risk = first_out or first_danger
    if not first_risk:
        if "liquidity" in exit_reason.lower() or "rug" in exit_reason.lower():
            return "CORRECT EXIT", "Exit was caused by liquidity/rug protection."
        return "UNKNOWN", "No danger wallet or OUT/SELL event was recorded before exit."

    risk_dt = _parse_iso(first_risk.get("detected_at"))
    if not risk_dt:
        return "UNKNOWN", "Risk event time could not be parsed."

    delta_seconds = int((exit_dt - risk_dt).total_seconds())
    if delta_seconds < -120:
        return "EARLY EXIT", "Bot exited before the main recorded risk signal."
    if delta_seconds <= 900:
        return "CORRECT EXIT", "Bot exited close to the recorded risk signal."
    return "LATE EXIT", "Bot exited long after the first recorded risk signal."


def _build_case_summary(mint: str, events: list[dict[str, Any]], trade: dict[str, Any] | None) -> list[str]:
    if not events and not trade:
        return ["No events found for this mint."]

    first = events[0] if events else None
    last = events[-1] if events else None
    first_wallets = _unique_wallet_order(events, max_items=8)

    first_dht8 = _first_event(events, lambda e: "DHT8" in _event_label(e).upper())
    first_gamq = _first_event(events, lambda e: "GAMQ" in _event_label(e).upper())
    first_dist_out = _first_event(events, lambda e: "OUT" in _event_category(e).upper())
    danger_seen = [_event_label(e) for e in events if _is_danger_wallet(_event_label(e))]
    danger_seen_unique = []
    for label in danger_seen:
        if label not in danger_seen_unique:
            danger_seen_unique.append(label)

    market = _market_points(events)
    verdict, verdict_reason = _exit_verdict(events, trade)

    lines = [
        "🧬 Token Case File",
        "",
        f"Mint: {_short(mint)}",
        f"Full Mint: {mint}",
        "",
        "Birth / First Seen:",
        f"- First event: {first.get('detected_at') if first else 'N/A'}",
        f"- First wallet: {_event_label(first) if first else 'N/A'}",
        f"- Last seen: {last.get('detected_at') if last else 'N/A'}",
        f"- Case duration: {_duration_text(first.get('detected_at') if first else None, last.get('detected_at') if last else None)}",
        "",
        "Early Wallet Order:",
    ]

    if first_wallets:
        for index, label in enumerate(first_wallets, start=1):
            lines.append(f"{index}) {label}")
    else:
        lines.append("N/A")

    lines.extend([
        "",
        "Danger Wallets:",
        f"- DHT8 first seen: {first_dht8.get('detected_at') if first_dht8 else 'No'}",
        f"- GAMq first seen: {first_gamq.get('detected_at') if first_gamq else 'No'}",
        f"- First OUT/SELL: {first_dist_out.get('detected_at') if first_dist_out else 'No'}",
        f"- Danger wallets seen: {', '.join(danger_seen_unique) if danger_seen_unique else 'No'}",
        "",
        "Market Snapshot From Stored Details:",
        f"- First price: {_fmt_usd(market['first_price'])}",
        f"- Peak price: {_fmt_usd(market['peak_price'])}",
        f"- Last price: {_fmt_usd(market['last_price'])}",
        f"- First liquidity: {_fmt_usd(market['first_liquidity'])}",
        f"- Peak liquidity: {_fmt_usd(market['peak_liquidity'])}",
        f"- Last liquidity: {_fmt_usd(market['last_liquidity'])}",
        "",
        "Bot Trade:",
    ])

    if trade:
        opened_at = trade.get("opened_at") or ""
        closed_at = trade.get("closed_at") or ""
        lines.extend([
            f"- Status: {trade.get('status') or 'N/A'}",
            f"- Entry: {opened_at or 'N/A'} @ {_fmt_usd(trade.get('entry_price_usd'))}",
            f"- Exit: {closed_at or 'N/A'} @ {_fmt_usd(trade.get('exit_price_usd'))}",
            f"- Duration: {_duration_text(opened_at, closed_at)}",
            f"- PnL: {_fmt_decimal(trade.get('pnl_pct'), 2)}%",
            f"- Reason: {trade.get('exit_reason') or 'N/A'}",
        ])
    else:
        lines.append("- No paper trade found.")

    lines.extend([
        "",
        "Verdict:",
        f"- {verdict}",
        f"- {verdict_reason}",
    ])

    return lines


def _build_timeline_lines(events: list[dict[str, Any]], max_events: int = 80) -> list[str]:
    lines = ["", "Timeline:", ""]

    if not events:
        lines.append("No timeline events found.")
        return lines

    first_time = events[0].get("detected_at")

    for index, event in enumerate(events[:max_events], start=1):
        detected_at = str(event.get("detected_at") or "")
        age = _duration_text(first_time, detected_at)
        title = _classify_timeline_event(event)
        label = _event_label(event)
        category = _event_category(event)
        source = _event_source(event)
        signature = str(event.get("signature") or "")

        lines.extend([
            f"{index}) +{age} | {title}",
            f"   Time: {detected_at}",
            f"   Wallet: {label}",
            f"   Category: {category}",
        ])

        if source:
            lines.append(f"   Source: {source}")
        if signature:
            lines.append(f"   Sig: {_short(signature)}")

        details = str(event.get("details") or "").strip()
        price = _extract_detail_number(details, "price") or _extract_detail_number(details, "price_usd")
        liquidity = _extract_detail_number(details, "liquidity") or _extract_detail_number(details, "liquidity_usd")
        if price > 0 or liquidity > 0:
            lines.append(f"   Market: price={_fmt_usd(price)} | liquidity={_fmt_usd(liquidity)}")

        lines.append("")

    if len(events) > max_events:
        lines.append(f"... {len(events) - max_events} more events hidden by limit.")

    return lines


# ---------------------------------------------------------------------------
# Public report function
# ---------------------------------------------------------------------------

def build_forensics_timeline_report(mint_query: str = "", limit: int = 80) -> str:
    """Build a full investigation-style timeline for one mint.

    mint_query can be:
    - empty: latest mint in forensics_events
    - full mint
    - mint prefix
    - symbol if a matching paper_copy_trades row exists
    """
    with _connect() as conn:
        if not _table_exists(conn, "forensics_events"):
            return "Forensics table not found yet. Waiting for events."

        mint = _resolve_mint(conn, mint_query)
        if not mint:
            return f"No mint found for query: {mint_query or 'latest'}"

        events = _load_forensics_events(conn, mint)
        trade = _load_paper_trade(conn, mint)

    lines = [
        f"🕵️ Forensics Timeline {FORENSICS_TIMELINE_VERSION}",
        "",
        "Mode: Passive investigation only.",
        "No entry/exit decisions changed.",
        "",
    ]

    lines.extend(_build_case_summary(mint, events, trade))
    lines.extend(_build_timeline_lines(events, max_events=limit))

    lines.extend([
        "Investigation Notes:",
        "- This report reconstructs what happened from stored bot/forensics events.",
        "- Market snapshots depend on whether price/liquidity were stored in event details.",
        "- Future V5.1 can enrich events with more market data at recording time.",
    ])

    return "\n".join(lines).strip()
