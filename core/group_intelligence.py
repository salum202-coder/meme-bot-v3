from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from storage.db import get_conn

GROUP_INTELLIGENCE_VERSION = "V5.1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_decimal(value: Any, default: str = "0") -> Decimal:
    try:
        if value is None or value == "":
            return Decimal(default)
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _short(value: str | None, left: int = 6, right: int = 6) -> str:
    if not value:
        return "N/A"
    value = str(value)
    if len(value) <= left + right:
        return value
    return f"{value[:left]}...{value[-right:]}"


def _fmt_decimal(value: Any, places: int = 2) -> str:
    try:
        return f"{float(_to_decimal(value)):,.{places}f}"
    except Exception:
        return str(value)


def _fmt_usd(value: Any) -> str:
    amount = _to_decimal(value)
    if amount == 0:
        return "$0"
    if abs(amount) >= Decimal("1"):
        return f"${float(amount):,.2f}"
    if abs(amount) >= Decimal("0.0001"):
        return f"${float(amount):.8f}".rstrip("0").rstrip(".")
    return f"${float(amount):.12f}".rstrip("0").rstrip(".")


def ensure_group_intelligence_tables() -> None:
    """Create passive Group Intelligence tables. No entry/exit decisions changed."""
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS group_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                detected_at TEXT NOT NULL,
                mint TEXT NOT NULL,
                label TEXT,
                wallet_address TEXT,
                role TEXT,
                event_type TEXT,
                analysis_type TEXT,
                signature TEXT,
                source TEXT,
                price_usd REAL DEFAULT 0,
                liquidity_usd REAL DEFAULT 0,
                volume_h1_usd REAL DEFAULT 0,
                token_delta TEXT DEFAULT '0',
                sol_delta TEXT DEFAULT '0',
                notes TEXT,
                UNIQUE(mint, signature, wallet_address, event_type)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS wallet_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                detected_at TEXT NOT NULL,
                mint TEXT NOT NULL,
                from_wallet TEXT NOT NULL,
                to_wallet TEXT NOT NULL,
                amount TEXT DEFAULT '0',
                asset TEXT DEFAULT 'TOKEN',
                signature TEXT,
                source TEXT,
                notes TEXT,
                UNIQUE(mint, signature, from_wallet, to_wallet, asset)
            )
            """
        )
        conn.commit()


def infer_group_role(label: str = "", event_type: str = "", token_delta: Any = None, sol_delta: Any = None) -> str:
    text = f"{label} {event_type}".upper()
    token_change = _to_decimal(token_delta)
    sol_change = _to_decimal(sol_delta)

    if "TREASURY" in text or "VAULT" in text:
        return "TREASURY"
    if "DHT8" in text and ("OUT" in text or "SELL" in text):
        return "EXIT_WALLET"
    if "GAMQ" in text and ("OUT" in text or "SELL" in text):
        return "EXIT_WALLET"
    if "OUT" in text or "SELL" in text or token_change < 0:
        return "DISTRIBUTION_OR_EXIT"
    if "DHT8" in text and ("IN" in text or token_change > 0):
        return "GROUP_RECIPIENT"
    if "BUY" in text or sol_change < 0:
        return "INITIAL_BUYER"
    if "IN" in text or token_change > 0:
        return "RECIPIENT"
    return "OBSERVED"


def record_group_event(
    *,
    mint: str,
    label: str = "",
    wallet_address: str = "",
    event_type: str = "",
    analysis_type: str = "",
    signature: str = "",
    source: str = "",
    price_usd: Any = 0,
    liquidity_usd: Any = 0,
    volume_h1_usd: Any = 0,
    token_delta: Any = 0,
    sol_delta: Any = 0,
    role: str = "",
    notes: str = "",
) -> None:
    if not mint:
        return

    ensure_group_intelligence_tables()
    if not role:
        role = infer_group_role(label, event_type or analysis_type, token_delta, sol_delta)

    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO group_events (
                detected_at, mint, label, wallet_address, role,
                event_type, analysis_type, signature, source,
                price_usd, liquidity_usd, volume_h1_usd,
                token_delta, sol_delta, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _now_iso(), mint, label, wallet_address, role,
                event_type or analysis_type or "GROUP_EVENT",
                analysis_type or event_type or "GROUP_EVENT",
                signature, source,
                _to_float(price_usd), _to_float(liquidity_usd), _to_float(volume_h1_usd),
                str(_to_decimal(token_delta)), str(_to_decimal(sol_delta)), notes,
            ),
        )
        conn.commit()


def record_wallet_link(
    *,
    mint: str,
    from_wallet: str,
    to_wallet: str,
    amount: Any,
    asset: str = "TOKEN",
    signature: str = "",
    source: str = "",
    notes: str = "",
) -> None:
    if not mint or not from_wallet or not to_wallet or from_wallet == to_wallet:
        return

    ensure_group_intelligence_tables()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO wallet_links (
                detected_at, mint, from_wallet, to_wallet,
                amount, asset, signature, source, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (_now_iso(), mint, from_wallet, to_wallet, str(_to_decimal(amount)), asset or "TOKEN", signature, source, notes),
        )
        conn.commit()


def record_wallet_links_from_owner_deltas(
    *,
    mint: str,
    signature: str,
    owner_deltas: dict[str, Decimal],
    min_amount: Decimal = Decimal("1000000"),
    source: str = "owner_delta",
) -> None:
    if not mint or not signature or not owner_deltas:
        return

    negatives = [
        (wallet, abs(_to_decimal(delta)))
        for wallet, delta in owner_deltas.items()
        if _to_decimal(delta) < 0 and abs(_to_decimal(delta)) >= min_amount
    ]
    positives = [
        (wallet, _to_decimal(delta))
        for wallet, delta in owner_deltas.items()
        if _to_decimal(delta) > 0 and _to_decimal(delta) >= min_amount
    ]

    for from_wallet, out_amount in negatives:
        for to_wallet, in_amount in positives:
            record_wallet_link(
                mint=mint,
                from_wallet=from_wallet,
                to_wallet=to_wallet,
                amount=min(out_amount, in_amount),
                asset="TOKEN",
                signature=signature,
                source=source,
            )


def list_group_events_for_mint(mint: str, limit: int = 80) -> list[dict[str, Any]]:
    ensure_group_intelligence_tables()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM group_events
            WHERE mint = ?
            ORDER BY detected_at ASC, id ASC
            LIMIT ?
            """,
            (mint, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def list_wallet_links_for_mint(mint: str, limit: int = 80) -> list[dict[str, Any]]:
    ensure_group_intelligence_tables()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM wallet_links
            WHERE mint = ?
            ORDER BY detected_at ASC, id ASC
            LIMIT ?
            """,
            (mint, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def _latest_paper_mint() -> str | None:
    with get_conn() as conn:
        try:
            row = conn.execute(
                """
                SELECT mint
                FROM paper_copy_trades
                WHERE mint IS NOT NULL AND mint <> ''
                ORDER BY
                    CASE WHEN status = 'OPEN' THEN 0 ELSE 1 END,
                    COALESCE(updated_at, opened_at, closed_at, '') DESC,
                    id DESC
                LIMIT 1
                """
            ).fetchone()
        except Exception:
            return None
    return str(row["mint"]) if row else None


def build_group_intelligence_report(mint: str | None = None, limit: int = 60) -> str:
    ensure_group_intelligence_tables()
    selected_mint = (mint or "").strip() or _latest_paper_mint()

    if not selected_mint:
        return "\n".join([
            f"🧠 Group Intelligence {GROUP_INTELLIGENCE_VERSION}",
            "",
            "No Paper trade mint found yet.",
            "Waiting for group events.",
        ])

    events = list_group_events_for_mint(selected_mint, limit=limit)
    links = list_wallet_links_for_mint(selected_mint, limit=limit)

    roles: dict[str, int] = {}
    for event in events:
        role = event.get("role") or "OBSERVED"
        roles[role] = roles.get(role, 0) + 1

    lines = [
        f"🧠 Group Intelligence {GROUP_INTELLIGENCE_VERSION}",
        "",
        "Mode: Passive group investigation only.",
        "No entry/exit decisions changed.",
        "",
        f"Mint: {_short(selected_mint)}",
        f"Full Mint: {selected_mint}",
        "",
        "Group Summary:",
        f"- Group events: {len(events)}",
        f"- Wallet links: {len(links)}",
    ]

    if roles:
        lines.append("- Roles seen: " + ", ".join(f"{k}={v}" for k, v in sorted(roles.items())))
    else:
        lines.append("- Roles seen: No group events recorded yet.")

    lines.extend(["", "Recent Group Events:"])

    if not events:
        lines.append("- No group events recorded yet for this mint.")
    else:
        for index, event in enumerate(events[-20:], start=1):
            lines.extend([
                f"{index}) {event.get('detected_at')}",
                f"   Wallet: {event.get('label') or _short(event.get('wallet_address'))}",
                f"   Role: {event.get('role') or 'OBSERVED'}",
                f"   Event: {event.get('event_type') or event.get('analysis_type')}",
                f"   Token delta: {_fmt_decimal(event.get('token_delta'), 4)} | SOL delta: {_fmt_decimal(event.get('sol_delta'), 6)}",
                f"   Market: price={_fmt_usd(event.get('price_usd'))} | liq={_fmt_usd(event.get('liquidity_usd'))} | vol1h={_fmt_usd(event.get('volume_h1_usd'))}",
            ])
            if event.get("signature"):
                lines.append(f"   Sig: {_short(event.get('signature'))}")
            lines.append("")

    lines.extend(["Wallet Links / Money Flow:"])

    if not links:
        lines.append("- No wallet links recorded yet for this mint.")
    else:
        for index, link in enumerate(links[-20:], start=1):
            lines.extend([
                f"{index}) {_short(link.get('from_wallet'))} → {_short(link.get('to_wallet'))}",
                f"   Amount: {_fmt_decimal(link.get('amount'), 4)} {link.get('asset') or 'TOKEN'}",
                f"   Source: {link.get('source') or 'N/A'}",
            ])
            if link.get("signature"):
                lines.append(f"   Sig: {_short(link.get('signature'))}")
            lines.append("")

    lines.extend([
        "How to use:",
        "- Watch role changes from RECIPIENT into DISTRIBUTION_OR_EXIT.",
        "- Repeated wallet links reveal group structure.",
        "- This is the data layer for future /case reports.",
    ])

    return "\n".join(lines).strip()
