from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import requests

from storage.db import get_conn
from storage.repository_wallet_watch import (
    get_last_signature,
    save_wallet_signature,
)

SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"
DEXSCREENER_TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens"

DHT8_MAIN_WALLET = "DHT8LqMZ4UcbgfL2ttXoUUXSnhmV9gNBYJcCZpP3NNY8"

WATCH_WALLETS: dict[str, str] = {
    "DHT8 Main": DHT8_MAIN_WALLET,

    # Main signer / known cluster
    "BJsbr Signer": "BJsbrDPdpxvzP35TYJ7gmrcumqxVSqwDeEb4Gg3aV4Ax",
    "Cluster 3oUE": "3oUEaNt7uL7pjZ6gdiAiEVRp9ZCcGRec7B5aSvXcjbWS",
    "Cluster Fnpc": "Fnpcmk5umHWXKfpjLcTSqVig7tg3aXgW2jF3f4kiGQRU",
    "Cluster 9ynT": "9ynTDJrA8EHqmSskLdooeptY7z4U4qrDUT1uQjEqKVJY",
    "Cluster EaE6": "EaE63hx1Fbw12kMUHPWGnG2dLThSxiz4MQJ7zPapz3Ws",
    "Cluster 1imt": "1imt7zeK3mE17dvdfztuEDhfoCUwnK8RVcjRzxnXLba",
    "Cluster AL3r": "AL3riiofreSvSCzoGgkpfLTa4QHe6SDK1NihXXrxZ21C",
    "Cluster Gjct": "GjctEPhWA9ArYKWqGznuhYMzjJKTJCWXbKpdvbYokdDt",

    # New wallets from Solscan activity
    "Cluster FdwJBf": "FdwJBfk3KXaQEcDcnnamKZX8p4F6SvUqndYpg34q7742",
    "Cluster 47ry": "47ryXZhowHBseGB4S6kVZAYZTH1wZohzUBsKtDw5xe2Q",
    "Cluster 4cAg": "4cAgMwv3MGMTNks68f6B8ZR2SRRuEgNeFgAG5pCmQqEF",
    "Cluster G2H3": "G2H36uTDdp1nn3pmoi4EThNjNVckNXHC61LfYsvDh1cv",
    "Cluster B6ut": "B6utNA4LPRVsHTX7odHwkjjPwPUr1Qyy1jsYcBWHz637",
    "Cluster Awao": "Awao8jtzXUWVvm22CPm2tqYLCi3LgBUeCvtYGZS3PAGz",
    "Cluster Ay2z": "Ay2z9CvwugMV7j3WSLgB9KW83QoV2QP1iFKJmKNsEhPv",
    "Cluster 7nwP": "7nwPXZNhBj88jcC22VNBQUYLohTsQWh5VGxWqnAAcvMf",
    "Cluster JD6r": "JD6rVaerbyz6wjQ433nrw6bFTgFrp46MiYmi8EtUAfsG",

    # Confirmed active wallets from SPCX / related activity
    "Cluster 2usC": "2usC51yJqENTS6U4bo19AmDspRF9UizrmkMQrB3Pxno3",
    "Cluster GAMq": "973vghafz4fQYB3MquWdLZd8dBMzJWcsTyBxH2GAMqcY",
}

TOKEN_ALIASES: dict[str, str] = {
    "D6uqF8hPTP62yN3M2NhJUn8NPR9zTcyQS5pFE2QKfXnm": "SpaceX",
    "21EsdVV4apT8dK9UtcuBZGNUS2P7PikL5iBf2SVYGSqg": "SPCX",
}

# Token family detector.
# Important: SPCX / SpaceX may keep the same name but use a new mint every time.
TOKEN_FAMILY_KEYWORDS: dict[str, list[str]] = {
    "SPCX / SpaceX Family": [
        "spcx",
        "spacex",
        "space x",
    ],
}

MIN_SOL_DELTA_TO_ALERT = Decimal("0.05")

# V4.2 thresholds
DHT8_BIG_BUY_SOL = Decimal("20")
CLUSTER_BIG_BUY_SOL = Decimal("5")
CLUSTER_BIG_SELL_SOL = Decimal("3")

# Distribution detector thresholds.
# This catches patterns like:
# Big BUY -> many token transfers OUT -> possible distribution / prep for exits.
CLUSTER_DISTRIBUTION_MIN_TOKEN_AMOUNT = Decimal("1000000")
SPCX_FAMILY_DISTRIBUTION_MIN_AMOUNT = Decimal("100000000")
CLUSTER_DISTRIBUTION_MAX_SOL_SPEND = Decimal("1")

# Temporary investigation mode for DHT8.
# Keep it ON while we study DHT8 behavior.
DHT8_TRACE_ALL = True
DHT8_TRACE_MAX_TXS_PER_CYCLE = 10

LIQUIDITY_RUG_USD = Decimal("1000")
LIQUIDITY_DROP_ALERT_PCT = Decimal("0.70")
PRICE_DUMP_FROM_PEAK_PCT = Decimal("0.35")
PRICE_DUMP_FROM_ENTRY_PCT = Decimal("0.25")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short(value: str | None, left: int = 6, right: int = 6) -> str:
    if not value:
        return "N/A"
    if len(value) <= left + right:
        return value
    return f"{value[:left]}...{value[-right:]}"


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


def _fmt_decimal(value: Decimal, places: int = 6) -> str:
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


def _format_time(block_time: int | None) -> str:
    if not block_time:
        return "N/A"
    return datetime.fromtimestamp(block_time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _label_for_wallet(wallet_address: str) -> str:
    for label, address in WATCH_WALLETS.items():
        if address == wallet_address:
            return label
    return "Unknown Wallet"


def _is_watched_wallet(wallet_address: str) -> bool:
    return wallet_address in WATCH_WALLETS.values()


def _ensure_active_token_table() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS active_token_watch (
                mint TEXT PRIMARY KEY,
                symbol TEXT,
                name TEXT,
                source_label TEXT,
                source_wallet TEXT,
                buy_signature TEXT,
                entry_sol REAL,
                entry_amount REAL,
                entry_price_usd REAL,
                entry_liquidity_usd REAL,
                peak_price_usd REAL,
                last_price_usd REAL,
                last_liquidity_usd REAL,
                last_checked_at TEXT,
                status TEXT,
                last_alert TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.commit()


def get_active_token(mint: str) -> dict[str, Any] | None:
    _ensure_active_token_table()

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM active_token_watch
            WHERE mint = ?
            """,
            (mint,),
        ).fetchone()

        if not row:
            return None

        return dict(row)


def list_active_tokens() -> list[dict[str, Any]]:
    _ensure_active_token_table()

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM active_token_watch
            WHERE status = 'ACTIVE'
            ORDER BY updated_at DESC
            """
        ).fetchall()

        return [dict(row) for row in rows]


def save_active_token(
    mint: str,
    symbol: str | None,
    name: str | None,
    source_label: str,
    source_wallet: str,
    buy_signature: str,
    entry_sol: Decimal,
    entry_amount: Decimal,
    entry_price_usd: Decimal,
    entry_liquidity_usd: Decimal,
) -> None:
    _ensure_active_token_table()

    now = _now_iso()

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO active_token_watch (
                mint,
                symbol,
                name,
                source_label,
                source_wallet,
                buy_signature,
                entry_sol,
                entry_amount,
                entry_price_usd,
                entry_liquidity_usd,
                peak_price_usd,
                last_price_usd,
                last_liquidity_usd,
                last_checked_at,
                status,
                last_alert,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(mint)
            DO UPDATE SET
                symbol = excluded.symbol,
                name = excluded.name,
                source_label = excluded.source_label,
                source_wallet = excluded.source_wallet,
                buy_signature = excluded.buy_signature,
                entry_sol = excluded.entry_sol,
                entry_amount = excluded.entry_amount,
                entry_price_usd = excluded.entry_price_usd,
                entry_liquidity_usd = excluded.entry_liquidity_usd,
                peak_price_usd = MAX(active_token_watch.peak_price_usd, excluded.peak_price_usd),
                last_price_usd = excluded.last_price_usd,
                last_liquidity_usd = excluded.last_liquidity_usd,
                last_checked_at = excluded.last_checked_at,
                status = 'ACTIVE',
                last_alert = '',
                updated_at = excluded.updated_at
            """,
            (
                mint,
                symbol,
                name,
                source_label,
                source_wallet,
                buy_signature,
                _to_float(entry_sol),
                _to_float(entry_amount),
                _to_float(entry_price_usd),
                _to_float(entry_liquidity_usd),
                _to_float(entry_price_usd),
                _to_float(entry_price_usd),
                _to_float(entry_liquidity_usd),
                now,
                "ACTIVE",
                "",
                now,
                now,
            ),
        )
        conn.commit()


def update_active_token_market(
    mint: str,
    price_usd: Decimal,
    liquidity_usd: Decimal,
    alert_type: str | None = None,
    status: str | None = None,
) -> None:
    _ensure_active_token_table()

    existing = get_active_token(mint)
    old_peak = _to_decimal(existing.get("peak_price_usd") if existing else 0)
    new_peak = max(old_peak, price_usd)
    now = _now_iso()

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE active_token_watch
            SET
                peak_price_usd = ?,
                last_price_usd = ?,
                last_liquidity_usd = ?,
                last_checked_at = ?,
                last_alert = COALESCE(?, last_alert),
                status = COALESCE(?, status),
                updated_at = ?
            WHERE mint = ?
            """,
            (
                _to_float(new_peak),
                _to_float(price_usd),
                _to_float(liquidity_usd),
                now,
                alert_type,
                status,
                now,
                mint,
            ),
        )
        conn.commit()


def is_tracked_token(mint: str | None) -> bool:
    if not mint:
        return False

    if mint in TOKEN_ALIASES:
        return True

    active = get_active_token(mint)
    return bool(active and active.get("status") == "ACTIVE")


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
        "symbol": base.get("symbol") or TOKEN_ALIASES.get(mint),
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


def _token_family_from_text(symbol: str | None, name: str | None) -> str | None:
    combined = f"{symbol or ''} {name or ''}".lower()

    for family, keywords in TOKEN_FAMILY_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in combined:
                return family

    return None


def token_family_for_mint(mint: str | None) -> str | None:
    if not mint:
        return None

    alias = TOKEN_ALIASES.get(mint)
    if alias:
        family = _token_family_from_text(alias, alias)
        if family:
            return family

    active = get_active_token(mint)
    if active:
        family = _token_family_from_text(active.get("symbol"), active.get("name"))
        if family:
            return family

    dex_info = fetch_dex_token_info(mint)
    if dex_info:
        family = _token_family_from_text(dex_info.get("symbol"), dex_info.get("name"))
        if family:
            return family

    return None


def _is_spcx_family(mint: str | None) -> bool:
    family = token_family_for_mint(mint)
    return family == "SPCX / SpaceX Family"


def _token_label(mint: str | None) -> str:
    if not mint:
        return "N/A"

    name = TOKEN_ALIASES.get(mint)
    if name:
        return f"{name} ({_short(mint)})"

    active = get_active_token(mint)
    if active and active.get("symbol"):
        family = token_family_for_mint(mint)
        if family:
            return f"{active['symbol']} / {family} ({_short(mint)})"
        return f"{active['symbol']} ({_short(mint)})"

    dex_info = fetch_dex_token_info(mint)
    if dex_info and dex_info.get("symbol"):
        family = token_family_for_mint(mint)
        if family:
            return f"{dex_info['symbol']} / {family} ({_short(mint)})"
        return f"{dex_info['symbol']} ({_short(mint)})"

    return _short(mint)


def fetch_wallet_signatures(wallet_address: str, limit: int = 10) -> list[dict[str, Any]]:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [
            wallet_address,
            {"limit": limit},
        ],
    }

    try:
        response = requests.post(SOLANA_RPC_URL, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    result = data.get("result")
    if not isinstance(result, list):
        return []

    return result


def fetch_transaction_details(signature: str) -> dict[str, Any] | None:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [
            signature,
            {
                "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 0,
            },
        ],
    }

    try:
        response = requests.post(SOLANA_RPC_URL, json=payload, timeout=12)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None

    result = data.get("result")
    if not isinstance(result, dict):
        return None

    return result


def _is_success(tx: dict[str, Any]) -> bool:
    return tx.get("err") is None


def _get_account_keys(details: dict[str, Any]) -> list[str]:
    message = ((details.get("transaction") or {}).get("message") or {})
    account_keys = message.get("accountKeys") or []

    keys: list[str] = []
    for item in account_keys:
        if isinstance(item, dict):
            pubkey = item.get("pubkey")
        else:
            pubkey = str(item)

        if pubkey:
            keys.append(pubkey)

    return keys


def _get_signers(details: dict[str, Any]) -> list[str]:
    message = ((details.get("transaction") or {}).get("message") or {})
    account_keys = message.get("accountKeys") or []

    signers: list[str] = []

    for item in account_keys:
        if isinstance(item, dict):
            pubkey = item.get("pubkey")
            is_signer = bool(item.get("signer"))

            if pubkey and is_signer:
                signers.append(pubkey)

    return signers


def _wallet_role_in_tx(details: dict[str, Any], wallet_address: str) -> str:
    signers = _get_signers(details)

    if wallet_address in signers:
        return "SIGNER — DHT8 executed this transaction"

    account_keys = _get_account_keys(details)
    if wallet_address in account_keys:
        return "AFFECTED — DHT8 is inside the transaction, but not signer"

    meta = details.get("meta") or {}
    token_balances = (meta.get("preTokenBalances") or []) + (meta.get("postTokenBalances") or [])

    for item in token_balances:
        if item.get("owner") == wallet_address:
            return "TOKEN_OWNER — DHT8 token balance was affected"

    return "UNKNOWN — DHT8 relation not clear"


def _sol_delta_for_wallet(details: dict[str, Any], wallet_address: str) -> Decimal:
    meta = details.get("meta") or {}
    pre_balances = meta.get("preBalances") or []
    post_balances = meta.get("postBalances") or []
    account_keys = _get_account_keys(details)

    try:
        wallet_index = account_keys.index(wallet_address)
    except ValueError:
        return Decimal("0")

    if wallet_index >= len(pre_balances) or wallet_index >= len(post_balances):
        return Decimal("0")

    pre_lamports = Decimal(str(pre_balances[wallet_index]))
    post_lamports = Decimal(str(post_balances[wallet_index]))

    return (post_lamports - pre_lamports) / Decimal("1000000000")


def _token_amount_from_balance(item: dict[str, Any]) -> Decimal:
    ui_token_amount = item.get("uiTokenAmount") or {}
    raw_amount = ui_token_amount.get("amount")

    if raw_amount is None:
        ui_amount_string = ui_token_amount.get("uiAmountString")
        if ui_amount_string is None:
            return Decimal("0")
        return Decimal(str(ui_amount_string))

    decimals = int(ui_token_amount.get("decimals") or 0)
    return Decimal(str(raw_amount)) / (Decimal(10) ** decimals)


def _token_deltas_for_wallet(details: dict[str, Any], wallet_address: str) -> list[dict[str, Any]]:
    meta = details.get("meta") or {}
    pre_token_balances = meta.get("preTokenBalances") or []
    post_token_balances = meta.get("postTokenBalances") or []

    balances: dict[str, dict[str, Decimal]] = {}

    def add_side(items: list[dict[str, Any]], side: str) -> None:
        for item in items:
            owner = item.get("owner")
            mint = item.get("mint")

            if owner != wallet_address or not mint:
                continue

            if mint not in balances:
                balances[mint] = {"pre": Decimal("0"), "post": Decimal("0")}

            balances[mint][side] = _token_amount_from_balance(item)

    add_side(pre_token_balances, "pre")
    add_side(post_token_balances, "post")

    changes: list[dict[str, Any]] = []

    for mint, values in balances.items():
        pre = values["pre"]
        post = values["post"]
        delta = post - pre

        if delta == 0:
            continue

        changes.append(
            {
                "mint": mint,
                "pre": pre,
                "post": post,
                "delta": delta,
            }
        )

    changes.sort(key=lambda x: abs(x["delta"]), reverse=True)
    return changes


def _primary_token_mint(token_changes: list[dict[str, Any]]) -> str | None:
    if not token_changes:
        return None
    return token_changes[0].get("mint")


def _is_large_distribution_amount(mint: str | None, amount: Decimal) -> bool:
    amount_abs = abs(amount)

    if _is_spcx_family(mint):
        return amount_abs >= SPCX_FAMILY_DISTRIBUTION_MIN_AMOUNT

    return amount_abs >= CLUSTER_DISTRIBUTION_MIN_TOKEN_AMOUNT


def analyze_transaction(signature: str, wallet_address: str) -> dict[str, Any]:
    details = fetch_transaction_details(signature)

    if not details:
        return {
            "emoji": "❔",
            "type": "Unknown",
            "confidence": "low",
            "hints": ["transaction details unavailable"],
            "sol_delta": Decimal("0"),
            "token_changes": [],
            "notify": False,
            "register_active": False,
            "noise_reason": "No transaction details",
        }

    meta = details.get("meta") or {}
    err = meta.get("err")

    if err is not None:
        return {
            "emoji": "❌",
            "type": "Failed transaction",
            "confidence": "high",
            "hints": ["transaction failed"],
            "sol_delta": Decimal("0"),
            "token_changes": [],
            "notify": False,
            "register_active": False,
            "noise_reason": "Failed transaction ignored",
        }

    logs = "\n".join(meta.get("logMessages") or [])
    raw_text = json.dumps(details, ensure_ascii=False).lower()
    logs_text = logs.lower()

    sol_delta = _sol_delta_for_wallet(details, wallet_address)
    token_changes = _token_deltas_for_wallet(details, wallet_address)

    positive_tokens = [x for x in token_changes if x["delta"] > 0]
    negative_tokens = [x for x in token_changes if x["delta"] < 0]

    hints: list[str] = []

    if "placemarketorder" in raw_text or "place market order" in raw_text:
        hints.append("PlaceMarketOrder")
        if "phoenix" in raw_text or "phoenix" in logs_text:
            hints.append("Phoenix")

    dex_keywords = [
        "jupiter",
        "raydium",
        "orca",
        "meteora",
        "pump",
        "swap",
        "route",
        "market",
        "phoenix",
    ]

    matched_dex = [word for word in dex_keywords if word in raw_text or word in logs_text]
    for word in matched_dex[:5]:
        if word not in hints:
            hints.append(word)

    trade_like = bool(hints)
    transfer_hits = raw_text.count('"transfer"') + logs_text.count("instruction: transfer")

    # BUY:
    # DHT8 needs 20 SOL+
    # Any other cluster wallet needs 5 SOL+
    # Tracked tokens still notify even if below threshold.
    if positive_tokens and sol_delta < Decimal("-0.001"):
        spent_sol = abs(sol_delta)
        primary_mint = positive_tokens[0].get("mint")

        is_dht8_big_buy = (
            wallet_address == DHT8_MAIN_WALLET
            and spent_sol >= DHT8_BIG_BUY_SOL
        )

        is_cluster_big_buy = (
            wallet_address != DHT8_MAIN_WALLET
            and spent_sol >= CLUSTER_BIG_BUY_SOL
        )

        token_family = token_family_for_mint(primary_mint)

        if is_dht8_big_buy:
            return {
                "emoji": "🟢",
                "type": "DHT8 Big BUY",
                "confidence": "high",
                "hints": hints or ["DHT8 spent big SOL and received token"],
                "sol_delta": sol_delta,
                "token_changes": token_changes,
                "notify": True,
                "register_active": True,
                "active_mint": primary_mint,
                "token_family": token_family,
                "noise_reason": "",
            }

        if is_cluster_big_buy:
            return {
                "emoji": "🟢",
                "type": "Cluster Big BUY",
                "confidence": "high",
                "hints": hints or ["cluster wallet spent SOL and received token"],
                "sol_delta": sol_delta,
                "token_changes": token_changes,
                "notify": True,
                "register_active": True,
                "active_mint": primary_mint,
                "token_family": token_family,
                "noise_reason": "",
            }

        if is_tracked_token(primary_mint):
            return {
                "emoji": "🟢",
                "type": "Tracked Token BUY",
                "confidence": "medium",
                "hints": hints or ["token received, SOL spent"],
                "sol_delta": sol_delta,
                "token_changes": token_changes,
                "notify": True,
                "register_active": False,
                "active_mint": primary_mint,
                "token_family": token_family,
                "noise_reason": "",
            }

        return {
            "emoji": "🟢",
            "type": "Small / untracked BUY ignored",
            "confidence": "low",
            "hints": hints or ["untracked buy"],
            "sol_delta": sol_delta,
            "token_changes": token_changes,
            "notify": False,
            "register_active": False,
            "active_mint": primary_mint,
            "token_family": token_family,
            "noise_reason": "Buy was below cluster threshold and token is not tracked",
        }

    # SELL:
    # Notify if tracked token OR any cluster wallet receives 3 SOL+ from selling/spending token.
    if negative_tokens and sol_delta > Decimal("0.001"):
        primary_mint = negative_tokens[0].get("mint")
        is_big_cluster_sell = sol_delta >= CLUSTER_BIG_SELL_SOL
        token_family = token_family_for_mint(primary_mint)

        if is_tracked_token(primary_mint) or is_big_cluster_sell:
            return {
                "emoji": "🔴",
                "type": "Cluster SELL / Tracked Token Exit",
                "confidence": "medium-high",
                "hints": hints or ["token spent, SOL received"],
                "sol_delta": sol_delta,
                "token_changes": token_changes,
                "notify": True,
                "register_active": False,
                "active_mint": primary_mint,
                "token_family": token_family,
                "noise_reason": "",
            }

        return {
            "emoji": "🔴",
            "type": "Small / untracked SELL ignored",
            "confidence": "low",
            "hints": hints or ["untracked sell"],
            "sol_delta": sol_delta,
            "token_changes": token_changes,
            "notify": False,
            "register_active": False,
            "active_mint": primary_mint,
            "token_family": token_family,
            "noise_reason": "Sell was below cluster threshold and token is not tracked",
        }

    # DISTRIBUTION OUT:
    # Large token transfer out with no SOL received.
    # This is the pattern we discovered:
    # Big buy -> token distribution to many wallets -> possible later sell pressure.
    if negative_tokens and sol_delta <= Decimal("0") and abs(sol_delta) <= CLUSTER_DISTRIBUTION_MAX_SOL_SPEND:
        primary_mint = negative_tokens[0].get("mint")
        primary_delta = negative_tokens[0].get("delta") or Decimal("0")
        token_family = token_family_for_mint(primary_mint)

        if _is_large_distribution_amount(primary_mint, primary_delta):
            return {
                "emoji": "🟠",
                "type": "Cluster Distribution OUT / Possible Prep for Sell",
                "confidence": "medium-high",
                "hints": hints or [
                    "large token balance decreased",
                    f"transfer signals: {transfer_hits}",
                    "possible distribution to recipient wallets",
                ],
                "sol_delta": sol_delta,
                "token_changes": token_changes,
                "notify": True,
                "register_active": False,
                "active_mint": primary_mint,
                "token_family": token_family,
                "distribution_warning": True,
                "noise_reason": "",
            }

    # Transfer OUT:
    # Notify if token is tracked/active.
    if negative_tokens and sol_delta <= Decimal("0") and abs(sol_delta) <= CLUSTER_DISTRIBUTION_MAX_SOL_SPEND:
        primary_mint = negative_tokens[0].get("mint")
        token_family = token_family_for_mint(primary_mint)

        if is_tracked_token(primary_mint):
            return {
                "emoji": "🟠",
                "type": "Tracked Token Transfer OUT / Possible Distribution",
                "confidence": "high",
                "hints": hints or [f"tracked token balance decreased", f"transfer signals: {transfer_hits}"],
                "sol_delta": sol_delta,
                "token_changes": token_changes,
                "notify": True,
                "register_active": False,
                "active_mint": primary_mint,
                "token_family": token_family,
                "noise_reason": "",
            }

        return {
            "emoji": "🟠",
            "type": "Untracked Transfer OUT ignored",
            "confidence": "low",
            "hints": hints or ["untracked token balance decreased"],
            "sol_delta": sol_delta,
            "token_changes": token_changes,
            "notify": False,
            "register_active": False,
            "active_mint": primary_mint,
            "token_family": token_family,
            "noise_reason": "Transfer OUT was for untracked token",
        }

    # DISTRIBUTION IN:
    # Watched wallet received a large amount of token without spending SOL.
    if positive_tokens and abs(sol_delta) < Decimal("0.05"):
        primary_mint = positive_tokens[0].get("mint")
        primary_delta = positive_tokens[0].get("delta") or Decimal("0")
        token_family = token_family_for_mint(primary_mint)

        if _is_large_distribution_amount(primary_mint, primary_delta):
            return {
                "emoji": "📥",
                "type": "Cluster Distribution IN / Recipient Wallet",
                "confidence": "medium",
                "hints": hints or [
                    "large token balance increased",
                    f"transfer signals: {transfer_hits}",
                    "wallet may be a recipient in distribution pattern",
                ],
                "sol_delta": sol_delta,
                "token_changes": token_changes,
                "notify": True,
                "register_active": False,
                "active_mint": primary_mint,
                "token_family": token_family,
                "distribution_warning": True,
                "noise_reason": "",
            }

        if is_tracked_token(primary_mint):
            return {
                "emoji": "📥",
                "type": "Tracked Token Transfer IN / Cluster Receive",
                "confidence": "medium",
                "hints": hints or [f"tracked token balance increased", f"transfer signals: {transfer_hits}"],
                "sol_delta": sol_delta,
                "token_changes": token_changes,
                "notify": True,
                "register_active": False,
                "active_mint": primary_mint,
                "token_family": token_family,
                "noise_reason": "",
            }

        return {
            "emoji": "📥",
            "type": "Untracked Transfer IN ignored",
            "confidence": "low",
            "hints": hints or ["untracked token balance increased"],
            "sol_delta": sol_delta,
            "token_changes": token_changes,
            "notify": False,
            "register_active": False,
            "active_mint": primary_mint,
            "token_family": token_family,
            "noise_reason": "Transfer IN was for untracked token",
        }

    if trade_like and positive_tokens and negative_tokens:
        primary_mint = _primary_token_mint(token_changes)
        token_family = token_family_for_mint(primary_mint)

        if is_tracked_token(primary_mint):
            return {
                "emoji": "🚨",
                "type": "Possible TOKEN SWAP / Tracked Token",
                "confidence": "medium",
                "hints": hints,
                "sol_delta": sol_delta,
                "token_changes": token_changes,
                "notify": True,
                "register_active": False,
                "active_mint": primary_mint,
                "token_family": token_family,
                "noise_reason": "",
            }

    if trade_like and not token_changes and abs(sol_delta) < Decimal("0.001"):
        return {
            "emoji": "⚪",
            "type": "Trade order / no visible fill",
            "confidence": "medium",
            "hints": hints,
            "sol_delta": sol_delta,
            "token_changes": token_changes,
            "notify": False,
            "register_active": False,
            "noise_reason": "No token changes and only tiny SOL fee",
        }

    if trade_like and abs(sol_delta) >= MIN_SOL_DELTA_TO_ALERT:
        return {
            "emoji": "🚨",
            "type": "Possible Trade / Significant SOL Movement",
            "confidence": "medium",
            "hints": hints,
            "sol_delta": sol_delta,
            "token_changes": token_changes,
            "notify": False,
            "register_active": False,
            "noise_reason": "Trade-like movement ignored unless tracked or above Big BUY/SELL threshold",
        }

    return {
        "emoji": "👀",
        "type": "General Wallet Activity",
        "confidence": "low",
        "hints": ["no important pattern detected"],
        "sol_delta": sol_delta,
        "token_changes": token_changes,
        "notify": False,
        "register_active": False,
        "noise_reason": "Low-signal wallet activity ignored",
    }


def maybe_register_active_token(
    label: str,
    wallet_address: str,
    signature: str,
    analysis: dict[str, Any],
) -> None:
    if not analysis.get("register_active"):
        return

    token_changes = analysis.get("token_changes") or []
    positive_tokens = [x for x in token_changes if x["delta"] > 0]

    if not positive_tokens:
        return

    token = positive_tokens[0]
    mint = token.get("mint")
    amount = token.get("delta") or Decimal("0")

    if not mint:
        return

    dex_info = fetch_dex_token_info(mint) or {}
    symbol = dex_info.get("symbol") or TOKEN_ALIASES.get(mint)
    name = dex_info.get("name")
    entry_price_usd = dex_info.get("price_usd") or Decimal("0")
    entry_liquidity_usd = dex_info.get("liquidity_usd") or Decimal("0")

    save_active_token(
        mint=mint,
        symbol=symbol,
        name=name,
        source_label=label,
        source_wallet=wallet_address,
        buy_signature=signature,
        entry_sol=abs(analysis.get("sol_delta") or Decimal("0")),
        entry_amount=amount,
        entry_price_usd=entry_price_usd,
        entry_liquidity_usd=entry_liquidity_usd,
    )


def _format_token_changes(token_changes: list[dict[str, Any]]) -> list[str]:
    if not token_changes:
        return ["Token changes: N/A"]

    lines = ["Token changes:"]
    for item in token_changes[:3]:
        mint = item["mint"]
        delta = item["delta"]
        pre = item["pre"]
        post = item["post"]
        sign = "+" if delta > 0 else ""

        lines.append(f"- {_token_label(mint)}: {sign}{_fmt_decimal(delta, 4)}")
        lines.append(f"  Balance: {_fmt_decimal(pre, 4)} → {_fmt_decimal(post, 4)}")

    return lines


def build_wallet_activity_summary(
    label: str,
    wallet_address: str,
    new_txs: list[dict[str, Any]],
    important_tx: dict[str, Any],
    analysis: dict[str, Any],
    ignored_count: int,
) -> str:
    total = len(new_txs)
    success_count = sum(1 for tx in new_txs if _is_success(tx))
    failed_count = total - success_count

    important_signature = important_tx.get("signature") or ""
    important_time = _format_time(important_tx.get("blockTime"))

    hints = analysis.get("hints") or []
    hints_text = ", ".join(hints[:5]) if hints else "N/A"

    sol_delta = analysis.get("sol_delta", Decimal("0"))
    sol_sign = "+" if sol_delta > 0 else ""

    token_changes = analysis.get("token_changes") or []
    primary_mint = _primary_token_mint(token_changes)
    token_family = analysis.get("token_family") or token_family_for_mint(primary_mint)

    lines = [
        f"{analysis['emoji']} Wallet Watch V4.2",
        "",
        f"Label: {label}",
        f"Wallet: {_short(wallet_address)}",
        f"Detected: {analysis['type']}",
        f"Confidence: {analysis['confidence']}",
        f"Hints: {hints_text}",
        f"SOL delta: {sol_sign}{_fmt_decimal(sol_delta, 6)} SOL",
    ]

    if token_family:
        lines.append(f"Token Family: {token_family}")

    lines.append("")
    lines.extend(_format_token_changes(token_changes))

    if analysis.get("distribution_warning"):
        lines.extend(
            [
                "",
                "⚠️ Cluster Pattern Detector:",
                "Large token distribution detected.",
                "Meaning: possible distribution after buy / prep for sell pressure.",
                "Action: Do not enter late. Watch exits and recipient wallets.",
            ]
        )

    if analysis.get("register_active") and primary_mint:
        lines.extend(
            [
                "",
                "🧠 Active Token Tracker: ON",
                "This token will be monitored for dump/liquidity risk.",
            ]
        )

    if primary_mint:
        lines.extend(
            [
                "",
                "DexScreener:",
                f"https://dexscreener.com/solana/{primary_mint}",
            ]
        )

    lines.extend(
        [
            "",
            f"New txs checked: {total}",
            f"Ignored noise before alert: {ignored_count}",
            f"Success: {success_count}",
            f"Failed: {failed_count}",
            f"Important activity: {important_time}",
            "",
            "Important tx:",
            f"https://solscan.io/tx/{important_signature}",
            "",
            "Recent txs:",
        ]
    )

    for tx in new_txs[:3]:
        signature = tx.get("signature") or ""
        status = "✅" if _is_success(tx) else "❌"
        lines.append(f"{status} {_short(signature, 8, 8)}")

    lines.extend(
        [
            "",
            "Action: Review manually only. No auto entry.",
        ]
    )

    return "\n".join(lines)


def build_dht8_trace_message(
    tx: dict[str, Any],
    analysis: dict[str, Any],
    wallet_address: str,
) -> str:
    signature = tx.get("signature") or ""
    details = fetch_transaction_details(signature)

    role = "UNKNOWN"
    signers_text = "N/A"

    if details:
        role = _wallet_role_in_tx(details, wallet_address)
        signers = _get_signers(details)
        signers_text = ", ".join(_short(s) for s in signers[:5]) if signers else "N/A"

    sol_delta = analysis.get("sol_delta", Decimal("0"))
    sol_sign = "+" if sol_delta > 0 else ""

    hints = analysis.get("hints") or []
    hints_text = ", ".join(hints[:6]) if hints else "N/A"

    noise_reason = analysis.get("noise_reason") or "N/A"
    token_changes = analysis.get("token_changes") or []
    primary_mint = _primary_token_mint(token_changes)
    token_family = analysis.get("token_family") or token_family_for_mint(primary_mint)

    lines = [
        "🕵️ DHT8 Full Trace",
        "",
        f"Wallet: {_short(wallet_address)}",
        f"Role: {role}",
        f"Signers: {signers_text}",
        "",
        f"Detected: {analysis.get('type', 'Unknown')}",
        f"Confidence: {analysis.get('confidence', 'N/A')}",
        f"Hints: {hints_text}",
        f"Noise reason: {noise_reason}",
        "",
        f"SOL delta: {sol_sign}{_fmt_decimal(sol_delta, 6)} SOL",
    ]

    if token_family:
        lines.append(f"Token Family: {token_family}")

    lines.append("")
    lines.extend(_format_token_changes(token_changes))

    if primary_mint:
        lines.extend(
            [
                "",
                "DexScreener:",
                f"https://dexscreener.com/solana/{primary_mint}",
            ]
        )

    lines.extend(
        [
            "",
            f"Time: {_format_time(tx.get('blockTime'))}",
            "",
            "Tx:",
            f"https://solscan.io/tx/{signature}",
            "",
            "Action: Trace only. No auto entry.",
        ]
    )

    return "\n".join(lines)


def build_active_token_alert(token: dict[str, Any], dex_info: dict[str, Any], alert_type: str, reason: str) -> str:
    mint = token["mint"]
    symbol = dex_info.get("symbol") or token.get("symbol") or TOKEN_ALIASES.get(mint) or _short(mint)

    price = dex_info.get("price_usd") or Decimal("0")
    liquidity = dex_info.get("liquidity_usd") or Decimal("0")
    entry_price = _to_decimal(token.get("entry_price_usd"))
    peak_price = _to_decimal(token.get("peak_price_usd"))
    entry_liq = _to_decimal(token.get("entry_liquidity_usd"))

    price_from_entry = Decimal("0")
    price_from_peak = Decimal("0")
    liquidity_from_entry = Decimal("0")

    if entry_price > 0:
        price_from_entry = ((price - entry_price) / entry_price) * Decimal("100")

    if peak_price > 0:
        price_from_peak = ((price - peak_price) / peak_price) * Decimal("100")

    if entry_liq > 0:
        liquidity_from_entry = ((liquidity - entry_liq) / entry_liq) * Decimal("100")

    token_family = token_family_for_mint(mint)

    lines = [
        f"⚠️ Active Token Alert — {alert_type}",
        "",
        f"Token: {symbol}",
        f"Mint: {_short(mint)}",
    ]

    if token_family:
        lines.append(f"Token Family: {token_family}")

    lines.extend(
        [
            f"Reason: {reason}",
            "",
            f"Price: {_fmt_usd(price)}",
            f"Entry price: {_fmt_usd(entry_price)}",
            f"Peak price: {_fmt_usd(peak_price)}",
            f"From entry: {_fmt_decimal(price_from_entry, 2)}%",
            f"From peak: {_fmt_decimal(price_from_peak, 2)}%",
            "",
            f"Liquidity: {_fmt_usd(liquidity)}",
            f"Entry liquidity: {_fmt_usd(entry_liq)}",
            f"Liquidity change: {_fmt_decimal(liquidity_from_entry, 2)}%",
            "",
            f"Volume 1H: {_fmt_usd(dex_info.get('volume_h1') or Decimal('0'))}",
            f"1H change: {_fmt_decimal(dex_info.get('price_change_h1') or Decimal('0'), 2)}%",
            f"1H buys/sells: {dex_info.get('buys_h1') or 0}/{dex_info.get('sells_h1') or 0}",
            "",
            "DexScreener:",
            dex_info.get("url") or f"https://dexscreener.com/solana/{mint}",
            "",
            "Action: Watch only. No auto entry.",
        ]
    )

    return "\n".join(lines)


def monitor_active_tokens() -> list[str]:
    alerts: list[str] = []

    for token in list_active_tokens():
        mint = token["mint"]
        dex_info = fetch_dex_token_info(mint)

        if not dex_info:
            continue

        price = dex_info.get("price_usd") or Decimal("0")
        liquidity = dex_info.get("liquidity_usd") or Decimal("0")

        entry_price = _to_decimal(token.get("entry_price_usd"))
        entry_liquidity = _to_decimal(token.get("entry_liquidity_usd"))
        peak_price = max(_to_decimal(token.get("peak_price_usd")), price)
        last_alert = token.get("last_alert") or ""

        alert_type = None
        reason = None
        new_status = None

        if liquidity <= LIQUIDITY_RUG_USD:
            alert_type = "LIQUIDITY_RUG"
            reason = "Liquidity is extremely low."
            new_status = "DANGER"

        elif entry_liquidity > 0 and liquidity <= entry_liquidity * (Decimal("1") - LIQUIDITY_DROP_ALERT_PCT):
            alert_type = "LIQUIDITY_DROP"
            reason = "Liquidity dropped more than 70% from entry."

        elif peak_price > 0 and price <= peak_price * (Decimal("1") - PRICE_DUMP_FROM_PEAK_PCT):
            alert_type = "PRICE_DUMP_FROM_PEAK"
            reason = "Price dumped more than 35% from peak."

        elif entry_price > 0 and price <= entry_price * (Decimal("1") - PRICE_DUMP_FROM_ENTRY_PCT):
            alert_type = "PRICE_DUMP_FROM_ENTRY"
            reason = "Price dropped more than 25% below entry."

        elif (dex_info.get("sells_h1") or 0) >= 50 and (dex_info.get("sells_h1") or 0) > (dex_info.get("buys_h1") or 0) * 2:
            alert_type = "SELL_PRESSURE"
            reason = "1H sells are more than double buys."

        update_active_token_market(
            mint=mint,
            price_usd=price,
            liquidity_usd=liquidity,
            alert_type=alert_type if alert_type else None,
            status=new_status,
        )

        if alert_type and alert_type != last_alert:
            alerts.append(build_active_token_alert(token, dex_info, alert_type, reason or "Risk detected."))

    return alerts


async def run_wallet_watch_cycle(context) -> None:
    chat_id = (
        context.application.bot_data.get("chat_id")
        or context.application.bot_data.get("default_chat_id")
    )

    for label, wallet_address in WATCH_WALLETS.items():
        await asyncio.sleep(0.35)
        signatures = fetch_wallet_signatures(wallet_address, limit=10)

        if not signatures:
            continue

        latest_signature = signatures[0].get("signature")
        latest_block_time = signatures[0].get("blockTime")

        if not latest_signature:
            continue

        last_seen = get_last_signature(wallet_address)

        # First initialization only. Do not send old historical txs.
        if not last_seen:
            save_wallet_signature(
                wallet_address=wallet_address,
                label=label,
                last_signature=latest_signature,
                last_seen_at=_format_time(latest_block_time),
            )
            continue

        if latest_signature == last_seen:
            continue

        known_index = None

        for index, tx in enumerate(signatures):
            if tx.get("signature") == last_seen:
                known_index = index
                break

        if known_index is None:
            new_txs = [signatures[0]]
        else:
            new_txs = signatures[:known_index]

        new_txs = new_txs[:10]

        # Special DHT8 investigation mode:
        # Send every new DHT8 tx, even if normal filter would ignore it.
        if wallet_address == DHT8_MAIN_WALLET and DHT8_TRACE_ALL:
            txs_to_trace = new_txs[:DHT8_TRACE_MAX_TXS_PER_CYCLE]

            for tx in txs_to_trace:
                signature = tx.get("signature") or ""
                if not signature:
                    continue

                analysis = analyze_transaction(signature, wallet_address)

                if analysis.get("notify"):
                    maybe_register_active_token(
                        label=label,
                        wallet_address=wallet_address,
                        signature=signature,
                        analysis=analysis,
                    )

                    if chat_id:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=build_wallet_activity_summary(
                                label=label,
                                wallet_address=wallet_address,
                                new_txs=[tx],
                                important_tx=tx,
                                analysis=analysis,
                                ignored_count=0,
                            ),
                            disable_web_page_preview=True,
                        )
                else:
                    if chat_id:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=build_dht8_trace_message(
                                tx=tx,
                                analysis=analysis,
                                wallet_address=wallet_address,
                            ),
                            disable_web_page_preview=True,
                        )

            save_wallet_signature(
                wallet_address=wallet_address,
                label=label,
                last_signature=latest_signature,
                last_seen_at=_format_time(latest_block_time),
            )
            continue

        important_analysis = None
        important_tx = None
        ignored_count = 0

        for tx in new_txs:
            signature = tx.get("signature") or ""
            if not signature:
                ignored_count += 1
                continue

            analysis = analyze_transaction(signature, wallet_address)

            if analysis.get("notify"):
                important_analysis = analysis
                important_tx = tx
                break

            ignored_count += 1

        if important_analysis and important_tx:
            important_signature = important_tx.get("signature") or ""

            maybe_register_active_token(
                label=label,
                wallet_address=wallet_address,
                signature=important_signature,
                analysis=important_analysis,
            )

            if chat_id:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=build_wallet_activity_summary(
                        label=label,
                        wallet_address=wallet_address,
                        new_txs=new_txs,
                        important_tx=important_tx,
                        analysis=important_analysis,
                        ignored_count=ignored_count,
                    ),
                    disable_web_page_preview=True,
                )

        save_wallet_signature(
            wallet_address=wallet_address,
            label=label,
            last_signature=latest_signature,
            last_seen_at=_format_time(latest_block_time),
        )

    if chat_id:
        for alert in monitor_active_tokens():
            await context.bot.send_message(
                chat_id=chat_id,
                text=alert,
                disable_web_page_preview=True,
            )
