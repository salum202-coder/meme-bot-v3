from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import requests

from storage.db import get_conn


DEXSCREENER_TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens"

PAPER_COPY_ENABLED = True

PAPER_ENTRY_LABEL_KEYWORDS = (
    "Initial Buyer",
    "G8R7 Buyer Distributor",
)

PAPER_ALLOWED_FAMILIES = (
    "SPCX / SpaceX Family",
    "SLX / Solstice Family",
)

PAPER_MIN_LIQUIDITY_USD = Decimal("80000")
PAPER_MIN_VOLUME_H1_USD = Decimal("10000")
PAPER_MIN_BUY_SELL_RATIO = Decimal("2.0")

PAPER_STOP_LOSS_PCT = Decimal("0.25")
PAPER_TRAILING_DROP_PCT = Decimal("0.30")
PAPER_LIQUIDITY_RUG_USD = Decimal("1000")
PAPER_LIQUIDITY_DROP_PCT = Decimal("0.70")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_decimal(value: Any, default: str = "0") -> Decimal:
    try:
        if value is None:
            return Decimal(default)
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _fmt_decimal(value: Decimal, places: int = 2) -> str:
    try:
        return f"{float(value):,.{places}f}"
    except Exception:
        return str(value)


def _fmt_usd(value: Decimal | float | int | None) -> str:
    if value is None:
        return "N/A"
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "N/A"


def _short(value: str | None, left: int = 6, right: int = 6) -> str:
    if not value:
        return "N/A"
    if len(value) <= left + right:
        return value
    return f"{value[:left]}...{value[-right:]}"


def _primary_token_mint(token_changes: list[dict[str, Any]]) -> str | None:
    if not token_changes:
        return None
    return token_changes[0].get("mint")


def fetch_dex_token_info(mint: str) -> dict[str, Any] | None:
    try:
        response = requests.get(f"{DEXSCREENER_TOKEN_URL}/{mint}", timeout=10)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return None

    pairs = payload.get("pairs") or []
    sol_pairs = [p for p in pairs if p.get("chainId") == "solana"]

    if not sol_pairs:
        return None

    pair = max(
        sol_pairs,
        key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0),
        default=None,
    )

    if not pair:
        return None

    base = pair.get("baseToken") or {}
    liquidity = pair.get("liquidity") or {}
    volume = pair.get("volume") or {}
    price_change = pair.get("priceChange") or {}
    txns = pair.get("txns") or {}
    txns_h1 = txns.get("h1") or {}

    return {
        "mint": mint,
        "symbol": base.get("symbol"),
        "name": base.get("name"),
        "price_usd": _to_decimal(pair.get("priceUsd")),
        "liquidity_usd": _to_decimal(liquidity.get("usd")),
        "fdv": _to_decimal(pair.get("fdv")),
        "market_cap": _to_decimal(pair.get("marketCap")),
        "volume_h1": _to_decimal(volume.get("h1")),
        "price_change_h1": _to_decimal(price_change.get("h1")),
        "buys_h1": int(txns_h1.get("buys") or 0),
        "sells_h1": int(txns_h1.get("sells") or 0),
        "url": pair.get("url") or f"https://dexscreener.com/solana/{mint}",
    }


def _ensure_paper_copy_table() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_copy_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mint TEXT UNIQUE,
                symbol TEXT,
                name TEXT,
                token_family TEXT,
                entry_label TEXT,
                entry_wallet TEXT,
                entry_signature TEXT,
                entry_price_usd REAL,
                entry_liquidity_usd REAL,
                entry_volume_h1 REAL,
                entry_buys_h1 INTEGER,
                entry_sells_h1 INTEGER,
                peak_price_usd REAL,
                last_price_usd REAL,
                last_liquidity_usd REAL,
                status TEXT,
                exit_reason TEXT,
                exit_signature TEXT,
                exit_price_usd REAL,
                pnl_pct REAL,
                opened_at TEXT,
                closed_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.commit()


def get_open_paper_trade(mint: str) -> dict[str, Any] | None:
    _ensure_paper_copy_table()

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM paper_copy_trades
            WHERE mint = ?
            AND status = 'OPEN'
            """,
            (mint,),
        ).fetchone()

        if not row:
            return None

        return dict(row)


def list_open_paper_trades() -> list[dict[str, Any]]:
    _ensure_paper_copy_table()

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM paper_copy_trades
            WHERE status = 'OPEN'
            ORDER BY opened_at DESC
            """
        ).fetchall()

        return [dict(row) for row in rows]


def _is_entry_wallet(label: str) -> bool:
    return any(keyword in label for keyword in PAPER_ENTRY_LABEL_KEYWORDS)


def _is_allowed_family(token_family: str | None) -> bool:
    return bool(token_family and token_family in PAPER_ALLOWED_FAMILIES)


def _buy_sell_ratio(dex_info: dict[str, Any]) -> Decimal:
    buys = Decimal(str(dex_info.get("buys_h1") or 0))
    sells = Decimal(str(dex_info.get("sells_h1") or 0))

    if sells <= 0:
        return buys if buys > 0 else Decimal("0")

    return buys / sells


def _passes_entry_quality(dex_info: dict[str, Any]) -> tuple[bool, str]:
    price = dex_info.get("price_usd") or Decimal("0")
    liquidity = dex_info.get("liquidity_usd") or Decimal("0")
    volume_h1 = dex_info.get("volume_h1") or Decimal("0")
    ratio = _buy_sell_ratio(dex_info)

    if price <= 0:
        return False, "Price is not available."

    if liquidity < PAPER_MIN_LIQUIDITY_USD:
        return False, f"Liquidity below {_fmt_usd(PAPER_MIN_LIQUIDITY_USD)}."

    if volume_h1 < PAPER_MIN_VOLUME_H1_USD:
        return False, f"Volume 1H below {_fmt_usd(PAPER_MIN_VOLUME_H1_USD)}."

    if ratio < PAPER_MIN_BUY_SELL_RATIO:
        return False, f"Buy/Sell ratio below {_fmt_decimal(PAPER_MIN_BUY_SELL_RATIO, 2)}x."

    return True, "Entry quality passed."


def open_paper_trade(
    mint: str,
    label: str,
    wallet_address: str,
    signature: str,
    analysis: dict[str, Any],
    dex_info: dict[str, Any],
) -> str:
    _ensure_paper_copy_table()

    now = _now_iso()
    symbol = dex_info.get("symbol") or "UNKNOWN"
    name = dex_info.get("name")
    token_family = analysis.get("token_family")
    price = dex_info.get("price_usd") or Decimal("0")
    liquidity = dex_info.get("liquidity_usd") or Decimal("0")
    volume_h1 = dex_info.get("volume_h1") or Decimal("0")
    buys_h1 = int(dex_info.get("buys_h1") or 0)
    sells_h1 = int(dex_info.get("sells_h1") or 0)

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO paper_copy_trades (
                mint,
                symbol,
                name,
                token_family,
                entry_label,
                entry_wallet,
                entry_signature,
                entry_price_usd,
                entry_liquidity_usd,
                entry_volume_h1,
                entry_buys_h1,
                entry_sells_h1,
                peak_price_usd,
                last_price_usd,
                last_liquidity_usd,
                status,
                exit_reason,
                exit_signature,
                exit_price_usd,
                pnl_pct,
                opened_at,
                closed_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(mint)
            DO UPDATE SET
                symbol = excluded.symbol,
                name = excluded.name,
                token_family = excluded.token_family,
                entry_label = excluded.entry_label,
                entry_wallet = excluded.entry_wallet,
                entry_signature = excluded.entry_signature,
                entry_price_usd = excluded.entry_price_usd,
                entry_liquidity_usd = excluded.entry_liquidity_usd,
                entry_volume_h1 = excluded.entry_volume_h1,
                entry_buys_h1 = excluded.entry_buys_h1,
                entry_sells_h1 = excluded.entry_sells_h1,
                peak_price_usd = excluded.peak_price_usd,
                last_price_usd = excluded.last_price_usd,
                last_liquidity_usd = excluded.last_liquidity_usd,
                status = 'OPEN',
                exit_reason = '',
                exit_signature = '',
                exit_price_usd = 0,
                pnl_pct = 0,
                opened_at = excluded.opened_at,
                closed_at = '',
                updated_at = excluded.updated_at
            """,
            (
                mint,
                symbol,
                name,
                token_family,
                label,
                wallet_address,
                signature,
                _to_float(price),
                _to_float(liquidity),
                _to_float(volume_h1),
                buys_h1,
                sells_h1,
                _to_float(price),
                _to_float(price),
                _to_float(liquidity),
                "OPEN",
                "",
                "",
                0,
                0,
                now,
                "",
                now,
            ),
        )
        conn.commit()

    return "\n".join(
        [
            "🟢 PAPER COPY ENTRY",
            "",
            f"Token: {symbol}",
            f"Mint: {_short(mint)}",
            f"Family: {token_family or 'N/A'}",
            "",
            f"Entry wallet: {label}",
            f"Detected: {analysis.get('type', 'N/A')}",
            f"Reason: Early known cluster buyer pattern.",
            "",
            f"Entry price: {_fmt_usd(price)}",
            f"Liquidity: {_fmt_usd(liquidity)}",
            f"Volume 1H: {_fmt_usd(volume_h1)}",
            f"Buys/Sells 1H: {buys_h1}/{sells_h1}",
            f"Buy/Sell Ratio: {_fmt_decimal(_buy_sell_ratio(dex_info), 2)}x",
            "",
            "DexScreener:",
            dex_info.get("url") or f"https://dexscreener.com/solana/{mint}",
            "",
            "Mode: Paper only. No real buy was executed.",
        ]
    )


def close_paper_trade(
    trade: dict[str, Any],
    reason: str,
    signature: str | None = None,
    dex_info: dict[str, Any] | None = None,
) -> str:
    _ensure_paper_copy_table()

    mint = trade["mint"]
    now = _now_iso()

    if dex_info is None:
        dex_info = fetch_dex_token_info(mint) or {}

    exit_price = dex_info.get("price_usd") or _to_decimal(trade.get("last_price_usd"))
    entry_price = _to_decimal(trade.get("entry_price_usd"))

    pnl_pct = Decimal("0")
    if entry_price > 0:
        pnl_pct = ((exit_price - entry_price) / entry_price) * Decimal("100")

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE paper_copy_trades
            SET
                status = 'CLOSED',
                exit_reason = ?,
                exit_signature = ?,
                exit_price_usd = ?,
                pnl_pct = ?,
                closed_at = ?,
                updated_at = ?
            WHERE mint = ?
            AND status = 'OPEN'
            """,
            (
                reason,
                signature or "",
                _to_float(exit_price),
                _to_float(pnl_pct),
                now,
                now,
                mint,
            ),
        )
        conn.commit()

    symbol = trade.get("symbol") or dex_info.get("symbol") or "UNKNOWN"

    return "\n".join(
        [
            "🚨 PAPER COPY EXIT",
            "",
            f"Token: {symbol}",
            f"Mint: {_short(mint)}",
            f"Reason: {reason}",
            "",
            f"Entry price: {_fmt_usd(entry_price)}",
            f"Exit price: {_fmt_usd(exit_price)}",
            f"Paper PnL: {_fmt_decimal(pnl_pct, 2)}%",
            "",
            "DexScreener:",
            dex_info.get("url") or f"https://dexscreener.com/solana/{mint}",
            "",
            "Mode: Paper only. No real sell was executed.",
        ]
    )


def update_paper_trade_market(trade: dict[str, Any], dex_info: dict[str, Any]) -> None:
    mint = trade["mint"]
    price = dex_info.get("price_usd") or Decimal("0")
    liquidity = dex_info.get("liquidity_usd") or Decimal("0")
    old_peak = _to_decimal(trade.get("peak_price_usd"))
    new_peak = max(old_peak, price)
    now = _now_iso()

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE paper_copy_trades
            SET
                peak_price_usd = ?,
                last_price_usd = ?,
                last_liquidity_usd = ?,
                updated_at = ?
            WHERE mint = ?
            AND status = 'OPEN'
            """,
            (
                _to_float(new_peak),
                _to_float(price),
                _to_float(liquidity),
                now,
                mint,
            ),
        )
        conn.commit()


def maybe_open_or_close_paper_trade_from_signal(
    label: str,
    wallet_address: str,
    signature: str,
    analysis: dict[str, Any],
) -> list[str]:
    if not PAPER_COPY_ENABLED:
        return []

    messages: list[str] = []

    token_changes = analysis.get("token_changes") or []
    mint = analysis.get("active_mint") or _primary_token_mint(token_changes)

    if not mint:
        return []

    analysis_type = analysis.get("type", "")
    token_family = analysis.get("token_family")
    open_trade = get_open_paper_trade(mint)

    # Exit rule 1:
    # DHT8 transferred the same token out.
    if open_trade and label == "DHT8 Main" and "Distribution OUT" in analysis_type:
        messages.append(
            close_paper_trade(
                trade=open_trade,
                reason="DHT8 transferred this token out. Possible DHT8 → GAMq exit route.",
                signature=signature,
            )
        )
        return messages

    # Exit rule 2:
    # GAMq sold or moved the same token.
    if open_trade and "GAMq" in label and ("SELL" in analysis_type or "Distribution OUT" in analysis_type):
        messages.append(
            close_paper_trade(
                trade=open_trade,
                reason="GAMq exit activity detected.",
                signature=signature,
            )
        )
        return messages

    # Entry rule:
    # Known initial buyer / G8R7 big buy.
    if open_trade:
        return messages

    if not _is_entry_wallet(label):
        return messages

    if "BUY" not in analysis_type:
        return messages

    if not _is_allowed_family(token_family):
        return messages

    dex_info = fetch_dex_token_info(mint)
    if not dex_info:
        return messages

    passed, reason = _passes_entry_quality(dex_info)
    if not passed:
        return messages

    messages.append(
        open_paper_trade(
            mint=mint,
            label=label,
            wallet_address=wallet_address,
            signature=signature,
            analysis=analysis,
            dex_info=dex_info,
        )
    )

    return messages


def monitor_paper_copy_trades() -> list[str]:
    if not PAPER_COPY_ENABLED:
        return []

    messages: list[str] = []

    for trade in list_open_paper_trades():
        mint = trade["mint"]
        dex_info = fetch_dex_token_info(mint)

        if not dex_info:
            continue

        price = dex_info.get("price_usd") or Decimal("0")
        liquidity = dex_info.get("liquidity_usd") or Decimal("0")
        entry_price = _to_decimal(trade.get("entry_price_usd"))
        entry_liquidity = _to_decimal(trade.get("entry_liquidity_usd"))
        peak_price = max(_to_decimal(trade.get("peak_price_usd")), price)

        update_paper_trade_market(trade, dex_info)

        if liquidity <= PAPER_LIQUIDITY_RUG_USD:
            messages.append(
                close_paper_trade(
                    trade=trade,
                    reason="Liquidity Rug detected.",
                    dex_info=dex_info,
                )
            )
            continue

        if entry_liquidity > 0 and liquidity <= entry_liquidity * (Decimal("1") - PAPER_LIQUIDITY_DROP_PCT):
            messages.append(
                close_paper_trade(
                    trade=trade,
                    reason="Liquidity dropped more than 70% from entry.",
                    dex_info=dex_info,
                )
            )
            continue

        if entry_price > 0 and price <= entry_price * (Decimal("1") - PAPER_STOP_LOSS_PCT):
            messages.append(
                close_paper_trade(
                    trade=trade,
                    reason="Stop loss: price dropped 25% from entry.",
                    dex_info=dex_info,
                )
            )
            continue

        if peak_price > entry_price and price <= peak_price * (Decimal("1") - PAPER_TRAILING_DROP_PCT):
            messages.append(
                close_paper_trade(
                    trade=trade,
                    reason="Trailing stop: price dropped 30% from peak.",
                    dex_info=dex_info,
                )
            )
            continue

    return messages
