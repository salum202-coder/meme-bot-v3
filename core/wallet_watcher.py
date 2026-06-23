from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import requests

from storage.db import get_conn
from storage.repository_wallet_watch import (
    get_last_signature,
    save_wallet_signature,
)
from core.solana_group_forensics import add_forensics_event
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

    # Confirmed active wallets from SPCX / SLX related activity
    "Cluster 2usC": "2usC51yJqENTS6U4bo19AmDspRF9UizrmkMQrB3Pxno3",
    "Cluster GAMq": "973vghafz4fQYB3MquWdLZd8dBMzJWcsTyBxH2GAMqcY",
    "Cluster G8R7 Buyer Distributor": "G8R73oApukNBHynSnmXWamhJuc1WWr7tBUAnra9wMdTt",
    "Candidate Cluster FLgc Distributor": "FLgcU5fu4n7s8P2c5uoe8jE4sgnVbH5MBszGqgrrETVU",
    "Cluster JBS2 Initial Buyer": "JBS2K42NigjzTd9sSc2qp8ySMyZL5t82UAGudgjhMXpY",
    "Cluster A4tT Initial Buyer": "A4tTYEDfscYjAEpTymoNAzTZ9FnXouxKhe3iuBTDuQXz",
    "Cluster 6g4v Initial Buyer": "BpkvZYRdDohvyL9gdC9hCadLnVeWFLoEjEmxz166g4vu2",
    "Cluster 5syp Initial Buyer": "NXGmCzx2qnnokMPdzUh336vRJWddRiBFZn6F85syp1Y",
}


TOKEN_ALIASES: dict[str, str] = {
    "D6uqF8hPTP62yN3M2NhJUn8NPR9zTcyQS5pFE2QKfXnm": "SpaceX",
    "21EsdVV4apT8dK9UtcuBZGNUS2P7PikL5iBf2SVYGSqg": "SPCX",
}


# Token family detector.
# Important:
# SPCX / SpaceX may keep the same name but use a new mint every time.
# SLX / Solstice also appears in the same cluster behavior.
TOKEN_FAMILY_KEYWORDS: dict[str, list[str]] = {
    "SPCX / SpaceX Family": [
        "spcx",
        "spacex",
        "space x",
    ],
    "SLX / Solstice Family": [
        "slx",
        "solstice",
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
DHT8_TRACE_ALL = False  # V4.23: reduce Telegram spam; keep only important paper alerts
DHT8_TRACE_MAX_TXS_PER_CYCLE = 10

LIQUIDITY_RUG_USD = Decimal("1000")
LIQUIDITY_DROP_ALERT_PCT = Decimal("0.70")
PRICE_DUMP_FROM_PEAK_PCT = Decimal("0.35")
PRICE_DUMP_FROM_ENTRY_PCT = Decimal("0.25")

# Paper Copy Mode V4.18
# Important: this is PAPER ONLY. No real buy/sell is executed here.
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

# Critical First Init Mode V4.18
# When a newly added high-value wallet has no saved last_signature yet,
# analyze its latest transaction if it is fresh, instead of silently skipping it.
CRITICAL_FIRST_INIT_ENABLED = True
CRITICAL_FIRST_INIT_WINDOW_SECONDS = 60 * 60

CRITICAL_FIRST_INIT_LABEL_KEYWORDS = (
    "GAMq",
    "G8R7 Buyer Distributor",
    "JBS2 Initial Buyer",
    "A4tT Initial Buyer",
    "6g4v Initial Buyer",
    "5syp Initial Buyer",
)

# New Mint Watch V4.18
# DHT8 Distribution IN is not an entry by itself.
# It only marks a new mint as WATCHING until an Initial Buyer / G8R7 BUY confirms it.
NEW_MINT_WATCH_ENABLED = True
NEW_MINT_WATCH_FAMILIES = PAPER_ALLOWED_FAMILIES

# New Mint Metrics Entry V4.18
# If DHT8 receives a new mint and the token quickly shows strong DexScreener metrics,
# open a PAPER trade even if the early buyer wallet is unknown.
NEW_MINT_METRICS_ENTRY_ENABLED = True
NEW_MINT_METRICS_MAX_AGE_SECONDS = 30 * 60
NEW_MINT_METRICS_MIN_LIQUIDITY_USD = Decimal("80000")
NEW_MINT_METRICS_MIN_VOLUME_H1_USD = Decimal("30000")
NEW_MINT_METRICS_MIN_BUYS_H1 = 20
NEW_MINT_METRICS_MIN_BUY_SELL_RATIO = Decimal("1.20")

# V4.18 Volume Dominance Entry
# Do not reject a DHT8 new mint just because sell count is higher.
# A token can have many tiny sells while buy volume in USD dominates.
# If buy/sell volume is available, use it. If not available, allow a strong
# positive h1 move + good liquidity/volume as a fallback momentum confirmation.
NEW_MINT_METRICS_VOLUME_DOMINANCE_ENABLED = True
NEW_MINT_METRICS_MIN_BUY_VOLUME_RATIO = Decimal("2.0")
NEW_MINT_METRICS_MIN_PRICE_CHANGE_H1_PCT = Decimal("10")

# Pending New Mint Recheck V4.27
# If DHT8 sees a mint before DexScreener data is ready, keep it WATCHING and recheck it.
NEW_MINT_RECHECK_ENABLED = True
NEW_MINT_RECHECK_MAX_AGE_SECONDS = 10 * 60
NEW_MINT_RECHECK_MIN_LIQUIDITY_USD = Decimal("30000")
NEW_MINT_RECHECK_MIN_VOLUME_H1_USD = Decimal("5000")

# Behavior-Based Detection V4.18
# Do not depend only on names like SPCX / SLX.
# If DHT8 receives a large allocation and Dex metrics are strong, treat it as a behavior rotation candidate.
BEHAVIOR_ROTATION_FAMILY = "DHT8 Rotation / Behavior"
BEHAVIOR_DHT8_MIN_TOKEN_AMOUNT = Decimal("700000000")
BEHAVIOR_MIN_LIQUIDITY_USD = Decimal("100000")
BEHAVIOR_MIN_VOLUME_H1_USD = Decimal("50000")
BEHAVIOR_MIN_BUYS_H1 = 20
BEHAVIOR_MIN_BUY_SELL_RATIO = Decimal("1.50")
BEHAVIOR_MIN_BUY_VOLUME_RATIO = Decimal("2.0")
BEHAVIOR_MIN_PRICE_CHANGE_H1_PCT = Decimal("10")

# Paper profit management V4.18
# This is Paper-only partial profit accounting. No real orders are sent.
# Paper profit management V4.19
# This is Paper-only partial profit accounting. No real orders are sent.
PAPER_TP1_PCT = Decimal("20")  # V4.25: first auto lock at +20%
PAPER_TP1_CLOSE_PERCENT = Decimal("50")
PAPER_AFTER_TP1_PROFIT_LOCK_PCT = Decimal("0.10")
PAPER_TRAILING_AFTER_TP1_DROP_PCT = Decimal("0.08")
PAPER_AFTER_TP1_FAST_LIQUIDITY_DROP_PCT = Decimal("0.20")

# V4.19 — Profit Protection
# After TP1, lock more profit instead of leaving 50% exposed until rug.
PAPER_TP2_PCT = Decimal("32")  # V4.25: second auto lock at +32%
PAPER_TP2_TOTAL_LOCKED_PERCENT = Decimal("75")

# If TP1 happened and the trade stays open too long while still profitable,
# close the remaining position before late-cycle rug risk.
PAPER_AFTER_TP1_TIME_PROTECTION_ENABLED = True
PAPER_AFTER_TP1_MAX_HOLD_HOURS = Decimal("3")
PAPER_AFTER_TP1_MIN_EXIT_PNL = Decimal("10")

DHT8_EXIT_SYNC_SIGNATURE_LIMIT = 60
TX_DETAILS_RETRY_ATTEMPTS = 4
TX_DETAILS_RETRY_DELAY_SECONDS = 0.75
PAPER_NO_TP1_MAX_HOLD_HOURS = Decimal("12")
PAPER_NO_TP1_MIN_EXIT_PNL = Decimal("5")

# Cluster-Only Kill Signal Exit V4.18
# User rule: exit decisions must be based on group/cluster behavior, not normal market noise.
# Therefore m5 sell pressure, ordinary buys/sells, price pullbacks, and fast liquidity moves
# are NOT treated as proactive kill signals anymore. They can still be observed,
# but the Paper Copy exit waits for DHT8 / GAMq / Cluster wallet movement on the same mint.
PAPER_MARKET_KILL_EXIT_ENABLED = False
PAPER_TIME_PROTECTION_ENABLED = False
PAPER_AFTER_TP1_KILL_DRAWDOWN_PCT = Decimal("0.08")
PAPER_BEFORE_TP1_KILL_DRAWDOWN_PCT = Decimal("0.12")
PAPER_KILL_SIGNAL_MIN_PROFIT_PCT = Decimal("5")
PAPER_FAST_LIQUIDITY_DROP_PCT = Decimal("0.12")
PAPER_PRE_TP1_FAST_LIQUIDITY_DROP_PCT = Decimal("0.15")
PAPER_M5_SELL_PRESSURE_MULTIPLIER = Decimal("2.0")
PAPER_M5_SELL_PRESSURE_MIN_SELLS = 5

# Paper Copy Wallet Accounting V4.18
# Separate from the original /wallet paper system.
# Each Paper Copy entry is counted as a fixed notional test trade.
PAPER_COPY_WALLET_STARTING_BALANCE_USD = Decimal("10.00")
PAPER_COPY_TRADE_SIZE_USD = Decimal("1.00")

# V4.32 — Paper statistics cleanup
# Abnormal meme-token results are kept in the trade log, but excluded from
# wallet balance, average PnL, and clean success-rate style summaries.
PAPER_STATS_MAX_REALISTIC_PNL_PCT = Decimal("1000")
PAPER_STATS_MIN_EXIT_LIQUIDITY_USD = Decimal("500")

# V4.32 — Group entry safety filter
# This protects broad V4.30 "first group wallet entry" from entering obvious
# bad/illiquid/too-large tokens such as Questium/NVDAx/SPCXxc edge cases.
GROUP_ENTRY_MAX_PRICE_USD = Decimal("10")
GROUP_ENTRY_MIN_LIQUIDITY_USD = Decimal("50000")
GROUP_ENTRY_MAX_LIQUIDITY_USD = Decimal("1000000")
GROUP_ENTRY_MIN_VOLUME_H1_USD = Decimal("20000")

# First Big Distribution Exit V4.18
# After a Paper Copy entry, any large Cluster Distribution IN/OUT on the same mint
# is treated as a final exit signal. This is intentionally aggressive because
# previous paper trades lost profit after early cluster distribution warnings.
FIRST_BIG_DISTRIBUTION_EXIT_ENABLED = False
FIRST_BIG_DISTRIBUTION_SIGNATURE_LIMIT = 20
FIRST_BIG_DISTRIBUTION_EXIT_LABEL_PREFIX = "Cluster "

# Pending TX Recheck V4.18
# If RPC cannot return details for a fresh transaction, keep the signature and
# re-check it in later cycles. This prevents missing DHT8 IN entries or DHT8 OUT exits.
PENDING_TX_RECHECK_ENABLED = True
PENDING_TX_RECHECK_MAX_ATTEMPTS = 8
PENDING_TX_RECHECK_WINDOW_SECONDS = 20 * 60
PENDING_TX_RECHECK_BATCH_LIMIT = 20

# Digest Entry Sync V4.18
# The 30m digest sometimes classifies transactions that were initially unavailable.
# Allow recent digest-discovered DHT8 IN to create New Mint Watch / Paper Entry.
DIGEST_ENTRY_SYNC_ENABLED = True
DIGEST_ENTRY_SYNC_MAX_AGE_SECONDS = 10 * 60

# V4.20 — Exit Intelligence Update
# Paper-only. No live trades are executed.
# Goal:
# 1) Keep V4.19 group-exit behavior.
# 2) Add Pattern Brain exit sync so stored OUT/SELL events can close open trades.
# 3) Detect first Armed Wallet OUT: wallet received the same mint after entry,
#    then later moved/sold it. This is the main signal we are testing.
# 4) Fast Kill is recorded/observed, but it does NOT block the next entry.
PAPER_V420_EXIT_INTELLIGENCE_ENABLED = True
PAPER_V420_PATTERN_EXIT_SYNC_ENABLED = False
PAPER_V420_ARMED_WALLET_OUT_EXIT_ENABLED = False
PAPER_V420_FAST_KILL_OBSERVE_ONLY = True

# V4.23 — Wallet OUT confirmation exit.
# Goal: do not close a Paper Copy trade just because the first wallet OUT appears.
# Close only when:
# 1) two unique wallet OUT/SELL/Distribution OUT events are seen after entry, or
# 2) one wallet OUT is confirmed by price dropping >= 15% from entry, or
# 3) one wallet OUT is confirmed by liquidity dropping >= 30% from entry.
PAPER_WALLET_OUT_EXIT_PRESSURE_ENABLED = True
PAPER_WALLET_OUT_MIN_EVENTS = 2
PAPER_WALLET_OUT_PRICE_DROP_CONFIRM_PCT = Decimal("15")
PAPER_WALLET_OUT_LIQUIDITY_DROP_CONFIRM_PCT = Decimal("30")

# V4.24 — Simple Exit Rules
# DHT8 OUT is an immediate exit.
# Non-DHT8 cluster OUT exits only after this many unique wallets.
PAPER_SIMPLE_EXIT_ENABLED = True
PAPER_SIMPLE_CLUSTER_OUT_MIN_WALLETS = 3



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
    """Format USD values with high precision for tiny meme-token prices.

    Liquidity/volume values still show as normal dollars, while token prices
    like 0.000004102 no longer appear as $0.00.
    """
    if value is None:
        return "N/A"

    try:
        amount = Decimal(str(value))
    except Exception:
        return "N/A"

    if amount == 0:
        return "$0"

    abs_amount = abs(amount)

    try:
        if abs_amount >= Decimal("1"):
            return f"${float(amount):,.2f}"

        if abs_amount >= Decimal("0.0001"):
            formatted = f"${float(amount):.8f}"
        else:
            formatted = f"${float(amount):.12f}"

        return formatted.rstrip("0").rstrip(".")
    except Exception:
        return f"${amount}"


def _fmt_price(value: Decimal | float | int | None) -> str:
    return _fmt_usd(value)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _age_text_from_iso(value: str | None) -> str:
    dt = _parse_iso_datetime(value)
    if not dt:
        return "N/A"

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    seconds = max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
    return _format_duration(seconds)


def _format_duration(seconds: int | float | None) -> str:
    if seconds is None:
        return "N/A"

    try:
        seconds = int(seconds)
    except Exception:
        return "N/A"

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


def _format_time(block_time: int | None) -> str:
    if not block_time:
        return "N/A"
    return datetime.fromtimestamp(block_time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _label_for_wallet(wallet_address: str) -> str:
    for label, address in get_all_watch_wallets().items():
        if address == wallet_address:
            return label
    return "Unknown Wallet"


def _is_watched_wallet(wallet_address: str) -> bool:
    return wallet_address in get_all_watch_wallets().values()


def _is_critical_first_init_wallet(label: str) -> bool:
    if not CRITICAL_FIRST_INIT_ENABLED:
        return False
    return any(keyword in label for keyword in CRITICAL_FIRST_INIT_LABEL_KEYWORDS)


def _is_recent_block_time(block_time: int | None, window_seconds: int) -> bool:
    if not block_time:
        return False

    now_ts = datetime.now(timezone.utc).timestamp()
    age_seconds = now_ts - float(block_time)

    return 0 <= age_seconds <= window_seconds


def _block_time_age_seconds(block_time: int | None) -> int | None:
    if not block_time:
        return None
    try:
        return int(datetime.now(timezone.utc).timestamp() - int(block_time))
    except Exception:
        return None


def _is_no_details_unknown(analysis: dict[str, Any]) -> bool:
    return (
        analysis.get("type") == "Unknown"
        and analysis.get("noise_reason") == "No transaction details"
    )


def _is_paper_relevant_analysis(analysis: dict[str, Any]) -> bool:
    analysis_type = analysis.get("type", "")
    if analysis.get("notify"):
        return True
    if "BUY" in analysis_type:
        return True
    if "SELL" in analysis_type:
        return True
    if "Distribution" in analysis_type:
        return True
    if "Transfer OUT" in analysis_type and "ignored" not in analysis_type:
        return True
    if "Transfer IN" in analysis_type and "ignored" not in analysis_type:
        return True
    return False


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
    txns_m5 = txns.get("m5") or {}
    txns_m15 = txns.get("m15") or {}
    txns_h1 = txns.get("h1") or {}

    # V4.18: DexScreener UI shows buy/sell volume, but not every API response
    # exposes it with the same key names. Keep this flexible and harmless.
    buy_volume = pair.get("buyVolume") or pair.get("buy_volume") or pair.get("buyVol") or pair.get("buy_vol") or {}
    sell_volume = pair.get("sellVolume") or pair.get("sell_volume") or pair.get("sellVol") or pair.get("sell_vol") or {}
    volume_buy = pair.get("volumeBuy") or pair.get("volume_buy") or {}
    volume_sell = pair.get("volumeSell") or pair.get("volume_sell") or {}

    def _period_volume(source: Any, period: str) -> Any:
        if isinstance(source, dict):
            return source.get(period) or source.get(period.upper())
        return source

    buy_volume_h1 = (
        _period_volume(buy_volume, "h1")
        or _period_volume(volume_buy, "h1")
        or txns_h1.get("buyVolume")
        or txns_h1.get("buy_volume")
        or txns_h1.get("buyVol")
    )
    sell_volume_h1 = (
        _period_volume(sell_volume, "h1")
        or _period_volume(volume_sell, "h1")
        or txns_h1.get("sellVolume")
        or txns_h1.get("sell_volume")
        or txns_h1.get("sellVol")
    )

    pair_created_at = pair.get("pairCreatedAt")
    pair_age_seconds = None
    try:
        if pair_created_at:
            pair_age_seconds = max(
                0,
                int(datetime.now(timezone.utc).timestamp() - (int(pair_created_at) / 1000)),
            )
    except Exception:
        pair_age_seconds = None

    return {
        "mint": mint,
        "symbol": base.get("symbol") or TOKEN_ALIASES.get(mint),
        "name": base.get("name"),
        "price_usd": _to_decimal(pair.get("priceUsd")),
        "liquidity_usd": _to_decimal(liquidity.get("usd")),
        "fdv": _to_decimal(pair.get("fdv")),
        "market_cap": _to_decimal(pair.get("marketCap")),
        "volume_m5": _to_decimal(volume.get("m5")),
        "volume_m15": _to_decimal(volume.get("m15")),
        "volume_h1": _to_decimal(volume.get("h1")),
        "price_change_m5": _to_decimal(price_change.get("m5")),
        "price_change_m15": _to_decimal(price_change.get("m15")),
        "price_change_h1": _to_decimal(price_change.get("h1")),
        "buys_m5": int(txns_m5.get("buys") or 0),
        "sells_m5": int(txns_m5.get("sells") or 0),
        "buys_m15": int(txns_m15.get("buys") or 0),
        "sells_m15": int(txns_m15.get("sells") or 0),
        "buys_h1": int(txns_h1.get("buys") or 0),
        "sells_h1": int(txns_h1.get("sells") or 0),
        "buy_volume_h1": _to_decimal(buy_volume_h1),
        "sell_volume_h1": _to_decimal(sell_volume_h1),
        "url": pair.get("url") or f"https://dexscreener.com/solana/{mint}",
        "pair_created_at": pair_created_at,
        "pair_age_seconds": pair_age_seconds,
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


def fetch_transaction_details(signature: str, attempts: int | None = None, retry_delay_seconds: float | None = None) -> dict[str, Any] | None:
    """Fetch parsed Solana transaction details with short retries.

    V4.18: public RPC can return None for a fresh transaction for a few seconds.
    Retrying here reduces false Unknown traces and helps DHT8 OUT / cluster exits
    trigger before a late liquidity-rug exit.
    """
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

    max_attempts = attempts if attempts is not None else TX_DETAILS_RETRY_ATTEMPTS
    delay = retry_delay_seconds if retry_delay_seconds is not None else TX_DETAILS_RETRY_DELAY_SECONDS

    for attempt in range(max(1, int(max_attempts))):
        try:
            response = requests.post(SOLANA_RPC_URL, json=payload, timeout=12)
            response.raise_for_status()
            data = response.json()
        except Exception:
            data = {}

        result = data.get("result") if isinstance(data, dict) else None
        if isinstance(result, dict):
            return result

        if attempt < max_attempts - 1:
            time.sleep(float(delay))

    return None

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



# ---------------------------------------------------------------------------
# Pending TX Recheck V4.18
# ---------------------------------------------------------------------------

def _ensure_pending_tx_table() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_unknown_transactions (
                signature TEXT PRIMARY KEY,
                label TEXT,
                wallet_address TEXT,
                block_time INTEGER,
                attempts INTEGER DEFAULT 0,
                status TEXT DEFAULT 'PENDING',
                first_seen_at TEXT,
                last_checked_at TEXT,
                resolved_at TEXT,
                resolved_type TEXT
            )
            """
        )
        conn.commit()


def save_pending_unknown_tx(
    label: str,
    wallet_address: str,
    signature: str,
    block_time: int | None,
) -> None:
    if not PENDING_TX_RECHECK_ENABLED or not signature:
        return

    _ensure_pending_tx_table()
    now = _now_iso()

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO pending_unknown_transactions (
                signature,
                label,
                wallet_address,
                block_time,
                attempts,
                status,
                first_seen_at,
                last_checked_at
            )
            VALUES (?, ?, ?, ?, 0, 'PENDING', ?, ?)
            ON CONFLICT(signature)
            DO UPDATE SET
                label = excluded.label,
                wallet_address = excluded.wallet_address,
                block_time = COALESCE(excluded.block_time, pending_unknown_transactions.block_time),
                last_checked_at = excluded.last_checked_at
            WHERE pending_unknown_transactions.status = 'PENDING'
            """,
            (signature, label, wallet_address, block_time, now, now),
        )
        conn.commit()


def list_pending_unknown_txs(limit: int = PENDING_TX_RECHECK_BATCH_LIMIT) -> list[dict[str, Any]]:
    _ensure_pending_tx_table()

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM pending_unknown_transactions
            WHERE status = 'PENDING'
            ORDER BY first_seen_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [dict(row) for row in rows]


def mark_pending_unknown_tx(
    signature: str,
    status: str,
    attempts: int,
    resolved_type: str | None = None,
) -> None:
    _ensure_pending_tx_table()
    now = _now_iso()

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE pending_unknown_transactions
            SET
                attempts = ?,
                status = ?,
                last_checked_at = ?,
                resolved_at = CASE WHEN ? != 'PENDING' THEN ? ELSE resolved_at END,
                resolved_type = COALESCE(?, resolved_type)
            WHERE signature = ?
            """,
            (attempts, status, now, status, now, resolved_type, signature),
        )
        conn.commit()


def build_pending_recheck_message(
    row: dict[str, Any],
    analysis: dict[str, Any],
) -> str:
    signature = row.get("signature") or ""
    label = row.get("label") or "Unknown"
    wallet_address = row.get("wallet_address") or ""
    token_changes = analysis.get("token_changes") or []
    token_text = "Token: N/A"

    if token_changes:
        item = token_changes[0]
        delta = item.get("delta", Decimal("0"))
        sign = "+" if delta > 0 else ""
        token_text = f"Token: {_token_label(item.get('mint'))} {sign}{_fmt_decimal(delta, 4)}"

    return "\n".join(
        [
            "🔁 Pending TX Recheck V4.18",
            "",
            f"Label: {label}",
            f"Wallet: {_short(wallet_address)}",
            f"Resolved as: {analysis.get('type', 'Unknown')}",
            f"Confidence: {analysis.get('confidence', 'low')}",
            token_text,
            f"Tx: https://solscan.io/tx/{signature}",
            "",
            "Action: Rechecked after RPC details were initially unavailable.",
        ]
    )


def process_pending_unknown_txs() -> list[str]:
    if not PENDING_TX_RECHECK_ENABLED:
        return []

    messages: list[str] = []

    for row in list_pending_unknown_txs():
        signature = row.get("signature") or ""
        label = row.get("label") or "Unknown"
        wallet_address = row.get("wallet_address") or ""
        block_time = row.get("block_time")
        attempts = int(row.get("attempts") or 0) + 1

        age_seconds = _block_time_age_seconds(block_time)
        if age_seconds is not None and age_seconds > PENDING_TX_RECHECK_WINDOW_SECONDS:
            mark_pending_unknown_tx(
                signature=signature,
                status="EXPIRED",
                attempts=attempts,
                resolved_type="expired",
            )
            continue

        analysis = analyze_transaction(signature, wallet_address)

        if _is_no_details_unknown(analysis):
            next_status = "PENDING" if attempts < PENDING_TX_RECHECK_MAX_ATTEMPTS else "FAILED"
            mark_pending_unknown_tx(
                signature=signature,
                status=next_status,
                attempts=attempts,
                resolved_type="no_details" if next_status == "FAILED" else None,
            )
            continue

        mark_pending_unknown_tx(
            signature=signature,
            status="RESOLVED",
            attempts=attempts,
            resolved_type=analysis.get("type", "Unknown"),
        )

        if not _is_paper_relevant_analysis(analysis):
            continue

        maybe_register_active_token(
            label=label,
            wallet_address=wallet_address,
            signature=signature,
            analysis=analysis,
        )

        paper_messages = maybe_handle_paper_copy_signal(
            label=label,
            wallet_address=wallet_address,
            signature=signature,
            analysis=analysis,
        )

        # V4.23: do not send standalone Pending TX Recheck spam.
        messages.extend(paper_messages)

    # If a pending DHT8 IN created a New Mint Watch, immediately evaluate metrics.
    messages.extend(monitor_new_mint_metric_entries())

    return messages


# ---------------------------------------------------------------------------
# New Mint Watch V4.18
# ---------------------------------------------------------------------------

def _ensure_new_mint_watch_table() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS new_mint_watch (
                mint TEXT PRIMARY KEY,
                symbol TEXT,
                name TEXT,
                token_family TEXT,
                source_label TEXT,
                source_wallet TEXT,
                source_signature TEXT,
                status TEXT,
                first_seen_at TEXT,
                last_checked_at TEXT,
                last_alert TEXT,
                updated_at TEXT
            )
            """
        )
        conn.commit()


def get_new_mint_watch(mint: str) -> dict[str, Any] | None:
    _ensure_new_mint_watch_table()

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM new_mint_watch
            WHERE mint = ?
            """,
            (mint,),
        ).fetchone()

        if not row:
            return None

        return dict(row)


def list_new_mint_watches(status: str = "WATCHING") -> list[dict[str, Any]]:
    _ensure_new_mint_watch_table()

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM new_mint_watch
            WHERE status = ?
            ORDER BY first_seen_at DESC
            """,
            (status,),
        ).fetchall()

        return [dict(row) for row in rows]


def update_new_mint_watch_status(
    mint: str,
    status: str,
    last_alert: str | None = None,
) -> None:
    _ensure_new_mint_watch_table()
    now = _now_iso()

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE new_mint_watch
            SET
                status = ?,
                last_checked_at = ?,
                last_alert = COALESCE(?, last_alert),
                updated_at = ?
            WHERE mint = ?
            """,
            (status, now, last_alert, now, mint),
        )
        conn.commit()


def update_new_mint_watch_checked(mint: str, last_alert: str | None = None) -> None:
    _ensure_new_mint_watch_table()
    now = _now_iso()

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE new_mint_watch
            SET
                last_checked_at = ?,
                last_alert = COALESCE(?, last_alert),
                updated_at = ?
            WHERE mint = ?
            """,
            (now, last_alert, now, mint),
        )
        conn.commit()


def save_new_mint_watch(
    mint: str,
    label: str,
    wallet_address: str,
    signature: str,
    token_family: str | None,
    dex_info: dict[str, Any] | None = None,
) -> bool:
    if not mint:
        return False

    existing = get_new_mint_watch(mint)
    if existing:
        return False

    if dex_info is None:
        dex_info = fetch_dex_token_info(mint) or {}

    now = _now_iso()
    symbol = dex_info.get("symbol") or TOKEN_ALIASES.get(mint)
    name = dex_info.get("name")

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO new_mint_watch (
                mint,
                symbol,
                name,
                token_family,
                source_label,
                source_wallet,
                source_signature,
                status,
                first_seen_at,
                last_checked_at,
                last_alert,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mint,
                symbol,
                name,
                token_family,
                label,
                wallet_address,
                signature,
                "WATCHING",
                now,
                now,
                "NEW_MINT_WATCH",
                now,
            ),
        )
        conn.commit()

    return True


def build_new_mint_watch_message(
    mint: str,
    label: str,
    wallet_address: str,
    signature: str,
    analysis: dict[str, Any],
    dex_info: dict[str, Any] | None = None,
) -> str:
    if dex_info is None:
        dex_info = fetch_dex_token_info(mint) or {}

    symbol = dex_info.get("symbol") or TOKEN_ALIASES.get(mint) or _token_label(mint)
    token_family = analysis.get("token_family") or token_family_for_mint(mint)
    price = dex_info.get("price_usd") or Decimal("0")
    liquidity = dex_info.get("liquidity_usd") or Decimal("0")
    volume_h1 = dex_info.get("volume_h1") or Decimal("0")
    buys_h1 = int(dex_info.get("buys_h1") or 0)
    sells_h1 = int(dex_info.get("sells_h1") or 0)

    return "\n".join(
        [
            "👀 NEW MINT WATCH",
            "",
            f"Token: {symbol}",
            f"Mint: {_short(mint)}",
            f"Family: {token_family or 'N/A'}",
            f"Source: {label}",
            "",
            f"Price: {_fmt_price(price)}",
            f"Liquidity: {_fmt_usd(liquidity)}",
            f"Volume 1H: {_fmt_usd(volume_h1)}",
            f"Buys/Sells: {buys_h1}/{sells_h1}",
            "",
            "DexScreener:",
            dex_info.get("url") or f"https://dexscreener.com/solana/{mint}",
        ]
    )


def maybe_handle_new_mint_watch_signal(
    label: str,
    wallet_address: str,
    signature: str,
    analysis: dict[str, Any],
) -> list[str]:
    if not NEW_MINT_WATCH_ENABLED:
        return []

    token_changes = analysis.get("token_changes") or []
    mint = analysis.get("active_mint") or _primary_token_mint(token_changes)
    if not mint:
        return []

    analysis_type = analysis.get("type", "")
    token_family = analysis.get("token_family") or token_family_for_mint(mint)

    if label != "DHT8 Main":
        return []

    if "Distribution IN" not in analysis_type:
        return []

    # V4.18: names can change. If token family is unknown but DHT8 received
    # a large allocation, treat it as a behavior-based rotation candidate.
    primary_amount = Decimal("0")
    positive_tokens = [x for x in token_changes if x.get("delta", Decimal("0")) > 0]
    if positive_tokens:
        primary_amount = positive_tokens[0].get("delta") or Decimal("0")

    is_known_family = token_family in NEW_MINT_WATCH_FAMILIES
    is_behavior_rotation = primary_amount >= BEHAVIOR_DHT8_MIN_TOKEN_AMOUNT

    if not is_known_family and not is_behavior_rotation:
        return []

    if not token_family and is_behavior_rotation:
        token_family = BEHAVIOR_ROTATION_FAMILY

    dex_info = fetch_dex_token_info(mint) or {}
    created = save_new_mint_watch(
        mint=mint,
        label=label,
        wallet_address=wallet_address,
        signature=signature,
        token_family=token_family,
        dex_info=dex_info,
    )

    if not created:
        return []

    return [
        build_new_mint_watch_message(
            mint=mint,
            label=label,
            wallet_address=wallet_address,
            signature=signature,
            analysis={**analysis, "token_family": token_family},
            dex_info=dex_info,
        )
    ]


# ---------------------------------------------------------------------------
# Paper Copy Mode V4.18
# ---------------------------------------------------------------------------

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

        # V4.18 migration columns for partial/manual close accounting.
        for column_name, column_type in [
            ("tp1_done", "INTEGER DEFAULT 0"),
            ("tp1_price_usd", "REAL DEFAULT 0"),
            ("tp1_pnl_pct", "REAL DEFAULT 0"),
            ("tp1_closed_pct", "REAL DEFAULT 0"),
            ("tp1_at", "TEXT DEFAULT ''"),
        ]:
            try:
                conn.execute(f"ALTER TABLE paper_copy_trades ADD COLUMN {column_name} {column_type}")
            except Exception:
                pass

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


def list_closed_paper_trades(limit: int = 10) -> list[dict[str, Any]]:
    _ensure_paper_copy_table()

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM paper_copy_trades
            WHERE status = 'CLOSED'
            ORDER BY closed_at DESC, updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [dict(row) for row in rows]


def list_all_paper_copy_trades() -> list[dict[str, Any]]:
    _ensure_paper_copy_table()

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM paper_copy_trades
            WHERE status IN ('OPEN', 'CLOSED')
            ORDER BY opened_at ASC
            """
        ).fetchall()

        return [dict(row) for row in rows]


def _is_abnormal_paper_copy_trade(trade: dict[str, Any]) -> bool:
    """Return True when a closed Paper Copy trade should not affect stats.

    The trade remains visible in history. Only wallet accounting and averages
    ignore it, so one impossible DexScreener print cannot inflate performance.
    """
    pnl_pct = _to_decimal(trade.get("pnl_pct"))
    exit_liquidity = _to_decimal(trade.get("last_liquidity_usd"))

    if pnl_pct > PAPER_STATS_MAX_REALISTIC_PNL_PCT:
        return True

    if exit_liquidity > 0 and exit_liquidity < PAPER_STATS_MIN_EXIT_LIQUIDITY_USD:
        return True

    return False


def _paper_copy_clean_closed_trades(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        trade for trade in trades
        if trade.get("status") == "CLOSED"
        and not _is_abnormal_paper_copy_trade(trade)
    ]


def paper_copy_summary_counts() -> dict[str, Any]:
    _ensure_paper_copy_table()

    with get_conn() as conn:
        total_open = conn.execute(
            "SELECT COUNT(*) AS c FROM paper_copy_trades WHERE status = 'OPEN'"
        ).fetchone()["c"]

        rows = conn.execute(
            "SELECT * FROM paper_copy_trades WHERE status = 'CLOSED'"
        ).fetchall()

    closed_trades = [dict(row) for row in rows]
    clean_closed = [
        trade for trade in closed_trades
        if not _is_abnormal_paper_copy_trade(trade)
    ]
    excluded_count = len(closed_trades) - len(clean_closed)

    wins = sum(1 for trade in clean_closed if _to_decimal(trade.get("pnl_pct")) > 0)
    losses = sum(1 for trade in clean_closed if _to_decimal(trade.get("pnl_pct")) < 0)

    avg_pnl = Decimal("0")
    if clean_closed:
        avg_pnl = sum(
            (_to_decimal(trade.get("pnl_pct")) for trade in clean_closed),
            Decimal("0"),
        ) / Decimal(len(clean_closed))

    return {
        "open": total_open or 0,
        "closed": len(closed_trades),
        "clean_closed": len(clean_closed),
        "excluded": excluded_count,
        "wins": wins,
        "losses": losses,
        "win_rate": (Decimal(wins) / Decimal(len(clean_closed)) * Decimal("100")) if clean_closed else Decimal("0"),
        "avg_pnl": avg_pnl,
    }


def _is_paper_entry_wallet(label: str) -> bool:
    return any(keyword in label for keyword in PAPER_ENTRY_LABEL_KEYWORDS)


def _is_paper_allowed_family(token_family: str | None) -> bool:
    return bool(token_family and token_family in PAPER_ALLOWED_FAMILIES)


def _is_behavior_rotation_family(token_family: str | None) -> bool:
    return token_family == BEHAVIOR_ROTATION_FAMILY


def _paper_buy_sell_ratio(dex_info: dict[str, Any]) -> Decimal:
    buys = Decimal(str(dex_info.get("buys_h1") or 0))
    sells = Decimal(str(dex_info.get("sells_h1") or 0))

    if sells <= 0:
        return buys if buys > 0 else Decimal("0")

    return buys / sells


def _paper_buy_sell_volume_ratio(dex_info: dict[str, Any]) -> Decimal:
    buy_volume = dex_info.get("buy_volume_h1") or Decimal("0")
    sell_volume = dex_info.get("sell_volume_h1") or Decimal("0")

    if sell_volume <= 0:
        return buy_volume if buy_volume > 0 else Decimal("0")

    return buy_volume / sell_volume


def _has_buy_volume_data(dex_info: dict[str, Any]) -> bool:
    return (dex_info.get("buy_volume_h1") or Decimal("0")) > 0 or (dex_info.get("sell_volume_h1") or Decimal("0")) > 0


def _is_volume_dominance_entry(
    dex_info: dict[str, Any],
    *,
    min_buy_volume_ratio: Decimal,
    min_price_change_h1_pct: Decimal,
) -> tuple[bool, str]:
    if not NEW_MINT_METRICS_VOLUME_DOMINANCE_ENABLED:
        return False, "Volume dominance disabled."

    price_change_h1 = dex_info.get("price_change_h1") or Decimal("0")
    volume_ratio = _paper_buy_sell_volume_ratio(dex_info)

    if _has_buy_volume_data(dex_info):
        if volume_ratio >= min_buy_volume_ratio:
            return True, f"Buy volume dominance passed ({_fmt_decimal(volume_ratio, 2)}x)."
        return False, f"Buy volume ratio below {_fmt_decimal(min_buy_volume_ratio, 2)}x."

    # Fallback when API does not expose buy/sell volume: use strong positive h1
    # momentum. This catches cases like many small sells but larger hidden buys.
    if price_change_h1 >= min_price_change_h1_pct:
        return True, f"Positive h1 momentum fallback passed ({_fmt_decimal(price_change_h1, 2)}%)."

    return False, f"Price change h1 below {_fmt_decimal(min_price_change_h1_pct, 2)}%."


def _paper_entry_quality(dex_info: dict[str, Any]) -> tuple[bool, str]:
    price = dex_info.get("price_usd") or Decimal("0")
    liquidity = dex_info.get("liquidity_usd") or Decimal("0")
    volume_h1 = dex_info.get("volume_h1") or Decimal("0")
    ratio = _paper_buy_sell_ratio(dex_info)

    if price <= 0:
        return False, "Price is not available."

    if liquidity < PAPER_MIN_LIQUIDITY_USD:
        return False, f"Liquidity below {_fmt_usd(PAPER_MIN_LIQUIDITY_USD)}."

    if volume_h1 < PAPER_MIN_VOLUME_H1_USD:
        return False, f"Volume 1H below {_fmt_usd(PAPER_MIN_VOLUME_H1_USD)}."

    print(
        f"[ENTRY_CHECK] "
        f"price={price} "
        f"liq={liquidity} "
        f"vol={volume_h1} "
        f"ratio={ratio}"
    )

    if ratio < PAPER_MIN_BUY_SELL_RATIO:
        return False, f"Buy/Sell ratio below {_fmt_decimal(PAPER_MIN_BUY_SELL_RATIO, 2)}x."

    return True, "Entry quality passed."



def _group_entry_quality_v432(dex_info: dict[str, Any]) -> tuple[bool, str]:
    """V4.32 safety filter for broad V4.30 group entries."""
    price = dex_info.get("price_usd") or Decimal("0")
    liquidity = dex_info.get("liquidity_usd") or Decimal("0")
    volume_h1 = dex_info.get("volume_h1") or Decimal("0")

    if price <= 0:
        return False, "Price is not available."

    if price > GROUP_ENTRY_MAX_PRICE_USD:
        return False, f"Price above {_fmt_usd(GROUP_ENTRY_MAX_PRICE_USD)}."

    if liquidity < GROUP_ENTRY_MIN_LIQUIDITY_USD:
        return False, f"Liquidity below {_fmt_usd(GROUP_ENTRY_MIN_LIQUIDITY_USD)}."

    if liquidity > GROUP_ENTRY_MAX_LIQUIDITY_USD:
        return False, f"Liquidity above {_fmt_usd(GROUP_ENTRY_MAX_LIQUIDITY_USD)}."

    if volume_h1 < GROUP_ENTRY_MIN_VOLUME_H1_USD:
        return False, f"Volume 1H below {_fmt_usd(GROUP_ENTRY_MIN_VOLUME_H1_USD)}."

    return True, "V4.32 group entry safety filter passed."
def open_paper_copy_trade(
    mint: str,
    label: str,
    wallet_address: str,
    signature: str,
    analysis: dict[str, Any],
    dex_info: dict[str, Any],
) -> str:
    _ensure_paper_copy_table()

    now = _now_iso()
    symbol = dex_info.get("symbol") or TOKEN_ALIASES.get(mint) or "UNKNOWN"
    name = dex_info.get("name")
    token_family = analysis.get("token_family") or token_family_for_mint(mint)
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
        conn.execute(
            """
            UPDATE paper_copy_trades
            SET
                tp1_done = 0,
                tp1_price_usd = 0,
                tp1_pnl_pct = 0,
                tp1_closed_pct = 0,
                tp1_at = ''
            WHERE mint = ?
            AND status = 'OPEN'
            """,
            (mint,),
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
            f"Wallet: {_short(wallet_address)}",
            f"Detected: {analysis.get('type', 'N/A')}",
            f"Reason: {analysis.get('paper_reason', 'Early known cluster buyer pattern.')}",
            "",
            f"Entry price: {_fmt_price(price)}",
            f"Liquidity: {_fmt_usd(liquidity)}",
            f"Volume 1H: {_fmt_usd(volume_h1)}",
            f"Buys/Sells 1H: {buys_h1}/{sells_h1}",
            f"Buy/Sell Count Ratio: {_fmt_decimal(_paper_buy_sell_ratio(dex_info), 2)}x",
            f"Buy/Sell Volume Ratio: {_fmt_decimal(_paper_buy_sell_volume_ratio(dex_info), 2)}x"
            if _has_buy_volume_data(dex_info) else
            f"H1 Momentum Fallback: {_fmt_decimal(dex_info.get('price_change_h1') or Decimal('0'), 2)}%",
            "",
            "DexScreener:",
            dex_info.get("url") or f"https://dexscreener.com/solana/{mint}",
            "",
            "Mode: Paper only. No real buy was executed.",
        ]
    )


def close_paper_copy_trade(
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

    remaining_pnl_pct = Decimal("0")
    if entry_price > 0:
        remaining_pnl_pct = ((exit_price - entry_price) / entry_price) * Decimal("100")

    tp1_done = bool(int(trade.get("tp1_done") or 0))
    tp1_closed_pct = _to_decimal(trade.get("tp1_closed_pct"))
    tp1_pnl_pct = _to_decimal(trade.get("tp1_pnl_pct"))

    effective_pnl_pct = remaining_pnl_pct
    if tp1_done and tp1_closed_pct > 0:
        closed_weight = tp1_closed_pct / Decimal("100")
        remaining_weight = Decimal("1") - closed_weight
        effective_pnl_pct = (tp1_pnl_pct * closed_weight) + (remaining_pnl_pct * remaining_weight)

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE paper_copy_trades
            SET
                status = 'CLOSED',
                exit_reason = ?,
                exit_signature = ?,
                exit_price_usd = ?,
                last_liquidity_usd = ?,
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
                _to_float(dex_info.get("liquidity_usd") or trade.get("last_liquidity_usd") or 0),
                _to_float(effective_pnl_pct),
                now,
                now,
                mint,
            ),
        )
        conn.commit()

    symbol = trade.get("symbol") or dex_info.get("symbol") or TOKEN_ALIASES.get(mint) or "UNKNOWN"

    lines = [
        "🚨 PAPER COPY EXIT",
        "",
        f"Token: {symbol}",
        f"Mint: {_short(mint)}",
        f"Reason: {reason}",
        "",
        f"Entry price: {_fmt_price(entry_price)}",
        f"Exit price: {_fmt_price(exit_price)}",
    ]

    if tp1_done and tp1_closed_pct > 0:
        lines.extend(
            [
                f"Locked before final: {_fmt_decimal(tp1_closed_pct, 2)}%",
                f"Avg locked PnL: {_fmt_decimal(tp1_pnl_pct, 2)}%",
                f"Remaining PnL: {_fmt_decimal(remaining_pnl_pct, 2)}%",
                f"Effective Paper PnL: {_fmt_decimal(effective_pnl_pct, 2)}%",
            ]
        )
    else:
        lines.append(f"Paper PnL: {_fmt_decimal(effective_pnl_pct, 2)}%")

    lines.extend(
        [
            "",
            "DexScreener:",
            dex_info.get("url") or f"https://dexscreener.com/solana/{mint}",
            "",
            "Mode: Paper only. No real sell was executed.",
        ]
    )

    return "\n".join(lines)



def _select_manual_close_trade(mint_arg: str | None = None) -> tuple[dict[str, Any] | None, str | None]:
    """Select one open paper copy trade for manual actions.

    If there is exactly one open trade, buttons/commands can work without args.
    If there are multiple, the user must pass a mint prefix/full mint to avoid closing
    the wrong trade.
    """
    open_trades = list_open_paper_trades()

    if not open_trades:
        return None, "No open paper copy positions."

    if mint_arg:
        needle = mint_arg.strip().lower()
        matches = [
            trade for trade in open_trades
            if str(trade.get("mint") or "").lower().startswith(needle)
            or needle in str(trade.get("mint") or "").lower()
        ]
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, "More than one open trade matched this mint prefix. Use a longer mint prefix."
        return None, f"No open paper copy position matched: {mint_arg}"

    if len(open_trades) == 1:
        return open_trades[0], None

    lines = [
        "There is more than one open Paper Copy position.",
        "Use one of these commands with a mint prefix:",
        "",
        "/copy_close_all <mint>",
        "/copy_close_50 <mint>",
        "/copy_close_25 <mint>",
        "",
        "Open positions:",
    ]
    for index, trade in enumerate(open_trades, start=1):
        lines.append(f"{index}) {trade.get('symbol') or 'UNKNOWN'} | {_short(trade.get('mint') or '')}")

    return None, "\n".join(lines)


def manual_close_paper_copy_trade(
    close_remaining_pct: Decimal,
    mint_arg: str | None = None,
) -> str:
    """Manual close for Paper Copy from Telegram buttons/commands.

    close_remaining_pct is a percentage of the CURRENT remaining position, not the
    original full position. Example: after TP1 closed 50%, /copy_close_50 closes
    half of the remaining 50%, leaving 25% of the original position open.
    """
    _ensure_paper_copy_table()

    if close_remaining_pct <= 0:
        return "Manual close percentage must be greater than 0."

    if close_remaining_pct > Decimal("100"):
        close_remaining_pct = Decimal("100")

    trade, error = _select_manual_close_trade(mint_arg)
    if error:
        return error
    if not trade:
        return "No open paper copy position found."

    mint = trade.get("mint") or ""
    dex_info = fetch_dex_token_info(mint) or {}

    if close_remaining_pct >= Decimal("99.999"):
        return close_paper_copy_trade(
            trade=trade,
            reason="Manual close from control panel.",
            signature=None,
            dex_info=dex_info,
        )

    entry_price = _to_decimal(trade.get("entry_price_usd"))
    current_price = dex_info.get("price_usd") or _to_decimal(trade.get("last_price_usd"))
    current_liquidity = dex_info.get("liquidity_usd") or _to_decimal(trade.get("last_liquidity_usd"))
    symbol = trade.get("symbol") or dex_info.get("symbol") or TOKEN_ALIASES.get(mint) or "UNKNOWN"

    current_pnl_pct = Decimal("0")
    if entry_price > 0:
        current_pnl_pct = ((current_price - entry_price) / entry_price) * Decimal("100")

    old_closed_pct = _to_decimal(trade.get("tp1_closed_pct"))
    if old_closed_pct < 0:
        old_closed_pct = Decimal("0")
    if old_closed_pct > Decimal("100"):
        old_closed_pct = Decimal("100")

    remaining_pct = Decimal("100") - old_closed_pct
    if remaining_pct <= Decimal("0.0001"):
        return close_paper_copy_trade(
            trade=trade,
            reason="Manual close from control panel; remaining allocation is already near zero.",
            signature=None,
            dex_info=dex_info,
        )

    close_pct_of_original = remaining_pct * (close_remaining_pct / Decimal("100"))
    if close_pct_of_original >= remaining_pct - Decimal("0.0001"):
        return close_paper_copy_trade(
            trade=trade,
            reason="Manual close from control panel.",
            signature=None,
            dex_info=dex_info,
        )

    old_avg_locked_pnl = _to_decimal(trade.get("tp1_pnl_pct"))
    new_closed_pct = old_closed_pct + close_pct_of_original
    new_avg_locked_pnl = current_pnl_pct
    if new_closed_pct > 0:
        new_avg_locked_pnl = (
            (old_avg_locked_pnl * old_closed_pct) + (current_pnl_pct * close_pct_of_original)
        ) / new_closed_pct

    now = _now_iso()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE paper_copy_trades
            SET
                tp1_done = 1,
                tp1_closed_pct = ?,
                tp1_pnl_pct = ?,
                tp1_price_usd = CASE WHEN COALESCE(tp1_price_usd, 0) > 0 THEN tp1_price_usd ELSE ? END,
                tp1_at = CASE WHEN COALESCE(tp1_at, '') <> '' THEN tp1_at ELSE ? END,
                last_price_usd = ?,
                last_liquidity_usd = ?,
                peak_price_usd = MAX(peak_price_usd, ?),
                updated_at = ?
            WHERE mint = ?
            AND status = 'OPEN'
            """,
            (
                _to_float(new_closed_pct),
                _to_float(new_avg_locked_pnl),
                _to_float(current_price),
                now,
                _to_float(current_price),
                _to_float(current_liquidity),
                _to_float(current_price),
                now,
                mint,
            ),
        )
        conn.commit()

    return "\n".join(
        [
            "🟡 PAPER COPY MANUAL PARTIAL CLOSE",
            "",
            f"Token: {symbol}",
            f"Mint: {_short(mint)}",
            "Action: Manual partial close from control panel.",
            "",
            f"Closed now: {_fmt_decimal(close_remaining_pct, 0)}% of remaining position",
            f"Closed from original: {_fmt_decimal(close_pct_of_original, 2)}%",
            f"Total locked: {_fmt_decimal(new_closed_pct, 2)}%",
            f"Remaining open: {_fmt_decimal(Decimal('100') - new_closed_pct, 2)}%",
            "",
            f"Entry price: {_fmt_price(entry_price)}",
            f"Close price: {_fmt_price(current_price)}",
            f"Close PnL: {_fmt_decimal(current_pnl_pct, 2)}%",
            f"Avg locked PnL: {_fmt_decimal(new_avg_locked_pnl, 2)}%",
            f"Liquidity: {_fmt_usd(current_liquidity)}",
            "",
            "DexScreener:",
            dex_info.get("url") or f"https://dexscreener.com/solana/{mint}",
            "",
            "Mode: Paper only. No real sell was executed.",
        ]
    )


def update_paper_copy_market(trade: dict[str, Any], dex_info: dict[str, Any]) -> None:
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



def mark_paper_copy_tp1(
    trade: dict[str, Any],
    dex_info: dict[str, Any],
) -> str:
    _ensure_paper_copy_table()

    mint = trade["mint"]
    now = _now_iso()
    symbol = trade.get("symbol") or dex_info.get("symbol") or TOKEN_ALIASES.get(mint) or "UNKNOWN"
    entry_price = _to_decimal(trade.get("entry_price_usd"))
    tp1_price = dex_info.get("price_usd") or _to_decimal(trade.get("last_price_usd"))
    liquidity = dex_info.get("liquidity_usd") or _to_decimal(trade.get("last_liquidity_usd"))

    tp1_pnl_pct = Decimal("0")
    if entry_price > 0:
        tp1_pnl_pct = ((tp1_price - entry_price) / entry_price) * Decimal("100")

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE paper_copy_trades
            SET
                tp1_done = 1,
                tp1_price_usd = ?,
                tp1_pnl_pct = ?,
                tp1_closed_pct = ?,
                tp1_at = ?,
                last_price_usd = ?,
                last_liquidity_usd = ?,
                peak_price_usd = MAX(peak_price_usd, ?),
                updated_at = ?
            WHERE mint = ?
            AND status = 'OPEN'
            AND COALESCE(tp1_done, 0) = 0
            """,
            (
                _to_float(tp1_price),
                _to_float(tp1_pnl_pct),
                _to_float(PAPER_TP1_CLOSE_PERCENT),
                now,
                _to_float(tp1_price),
                _to_float(liquidity),
                _to_float(tp1_price),
                now,
                mint,
            ),
        )
        conn.commit()

    return "\n".join(
        [
            "✅ PAPER COPY TP1",
            "",
            f"Token: {symbol}",
            f"Mint: {_short(mint)}",
            f"Action: Paper partial take profit.",
            "",
            f"TP1 close: {_fmt_decimal(PAPER_TP1_CLOSE_PERCENT, 0)}%",
            f"Entry price: {_fmt_price(entry_price)}",
            f"TP1 price: {_fmt_price(tp1_price)}",
            f"TP1 PnL: {_fmt_decimal(tp1_pnl_pct, 2)}%",
            f"Liquidity: {_fmt_usd(liquidity)}",
            "",
            "Remaining position protection:",
            f"Profit lock: +{_fmt_decimal(PAPER_AFTER_TP1_PROFIT_LOCK_PCT * Decimal('100'), 0)}% area",
            f"Trailing after TP1: {_fmt_decimal(PAPER_TRAILING_AFTER_TP1_DROP_PCT * Decimal('100'), 0)}% from peak",
            "",
            "DexScreener:",
            dex_info.get("url") or f"https://dexscreener.com/solana/{mint}",
            "",
            "Mode: Paper only. No real sell was executed.",
        ]
    )
def mark_paper_copy_tp2(
    trade: dict[str, Any],
    dex_info: dict[str, Any],
) -> str:
    _ensure_paper_copy_table()

    mint = trade["mint"]
    now = _now_iso()
    symbol = trade.get("symbol") or dex_info.get("symbol") or TOKEN_ALIASES.get(mint) or "UNKNOWN"
    entry_price = _to_decimal(trade.get("entry_price_usd"))
    tp2_price = dex_info.get("price_usd") or _to_decimal(trade.get("last_price_usd"))
    liquidity = dex_info.get("liquidity_usd") or _to_decimal(trade.get("last_liquidity_usd"))

    old_closed_pct = _to_decimal(trade.get("tp1_closed_pct"))
    old_avg_locked_pnl = _to_decimal(trade.get("tp1_pnl_pct"))

    if old_closed_pct >= PAPER_TP2_TOTAL_LOCKED_PERCENT:
        return ""

    tp2_pnl_pct = Decimal("0")
    if entry_price > 0:
        tp2_pnl_pct = ((tp2_price - entry_price) / entry_price) * Decimal("100")

    close_now_pct = PAPER_TP2_TOTAL_LOCKED_PERCENT - old_closed_pct
    if close_now_pct <= 0:
        return ""

    new_closed_pct = PAPER_TP2_TOTAL_LOCKED_PERCENT
    new_avg_locked_pnl = tp2_pnl_pct

    if new_closed_pct > 0:
        new_avg_locked_pnl = (
            (old_avg_locked_pnl * old_closed_pct) + (tp2_pnl_pct * close_now_pct)
        ) / new_closed_pct

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE paper_copy_trades
            SET
                tp1_done = 1,
                tp1_closed_pct = ?,
                tp1_pnl_pct = ?,
                tp1_price_usd = CASE WHEN COALESCE(tp1_price_usd, 0) > 0 THEN tp1_price_usd ELSE ? END,
                tp1_at = CASE WHEN COALESCE(tp1_at, '') <> '' THEN tp1_at ELSE ? END,
                last_price_usd = ?,
                last_liquidity_usd = ?,
                peak_price_usd = MAX(peak_price_usd, ?),
                updated_at = ?
            WHERE mint = ?
            AND status = 'OPEN'
            """,
            (
                _to_float(new_closed_pct),
                _to_float(new_avg_locked_pnl),
                _to_float(tp2_price),
                now,
                _to_float(tp2_price),
                _to_float(liquidity),
                _to_float(tp2_price),
                now,
                mint,
            ),
        )
        conn.commit()

    return "\n".join(
        [
            "✅ PAPER COPY TP2 V4.19",
            "",
            f"Token: {symbol}",
            f"Mint: {_short(mint)}",
            "Action: Paper second profit protection.",
            "",
            f"Closed now: {_fmt_decimal(close_now_pct, 2)}% from original position",
            f"Total locked: {_fmt_decimal(new_closed_pct, 2)}%",
            f"Remaining open: {_fmt_decimal(Decimal('100') - new_closed_pct, 2)}%",
            "",
            f"Entry price: {_fmt_price(entry_price)}",
            f"TP2 price: {_fmt_price(tp2_price)}",
            f"TP2 PnL: {_fmt_decimal(tp2_pnl_pct, 2)}%",
            f"Avg locked PnL: {_fmt_decimal(new_avg_locked_pnl, 2)}%",
            f"Liquidity: {_fmt_usd(liquidity)}",
            "",
            "Reason:",
            f"Price reached +{_fmt_decimal(PAPER_TP2_PCT, 0)}% area after TP1.",
            "V4.19 protects profit before late-cycle rug risk.",
            "",
            "DexScreener:",
            dex_info.get("url") or f"https://dexscreener.com/solana/{mint}",
            "",
            "Mode: Paper only. No real sell was executed.",
        ]
    )

def _is_tx_after_trade_open(tx: dict[str, Any], trade: dict[str, Any]) -> bool:
    block_time = tx.get("blockTime")
    opened = _parse_iso_datetime(trade.get("opened_at"))
    if not block_time or not opened:
        return True
    if opened.tzinfo is None:
        opened = opened.replace(tzinfo=timezone.utc)
    tx_time = datetime.fromtimestamp(block_time, tz=timezone.utc)
    return tx_time >= opened



def _trade_age_hours(trade: dict[str, Any]) -> Decimal:
    opened = _parse_iso_datetime(trade.get("opened_at"))
    if not opened:
        return Decimal("0")
    if opened.tzinfo is None:
        opened = opened.replace(tzinfo=timezone.utc)
    seconds = (datetime.now(timezone.utc) - opened).total_seconds()
    if seconds <= 0:
        return Decimal("0")
    return Decimal(str(seconds)) / Decimal("3600")


def _trade_tp1_age_hours(trade: dict[str, Any]) -> Decimal:
    tp1_at = trade.get("tp1_at") or ""
    started = _parse_iso_datetime(tp1_at)

    if not started:
        started = _parse_iso_datetime(trade.get("opened_at"))

    if not started:
        return Decimal("0")

    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)

    seconds = (datetime.now(timezone.utc) - started).total_seconds()
    if seconds <= 0:
        return Decimal("0")

    return Decimal(str(seconds)) / Decimal("3600")

def maybe_close_paper_copy_from_digest_event(
    label: str,
    wallet_address: str,
    tx: dict[str, Any],
    analysis: dict[str, Any],
) -> list[str]:
    """Close open Paper Copy trades when the digest successfully identifies an exit.

    V4.18: if the main wallet-watch cycle initially saw a fresh tx as Unknown
    because RPC details were not available, the 30m digest can later classify it
    as DHT8 OUT / GAMq exit / cluster distribution. This sync prevents waiting
    until a late liquidity-rug exit.
    """
    if not PAPER_COPY_ENABLED:
        return []

    signature = tx.get("signature") or ""
    if not signature:
        return []

    token_changes = analysis.get("token_changes") or []
    mint = analysis.get("active_mint") or _primary_token_mint(token_changes)
    if not mint:
        return []

    open_trade = get_open_paper_trade(mint)
    if not open_trade:
        return []

    if not _is_tx_after_trade_open(tx, open_trade):
        return []

    analysis_type = analysis.get("type", "")

    if label == "DHT8 Main" and "Distribution OUT" in analysis_type:
        return maybe_close_paper_copy_on_wallet_out_pressure(
            trade=open_trade,
            label=label,
            wallet_address=wallet_address,
            signature=signature,
            analysis=analysis,
            source="digest_dht8",
        )

    if "GAMq" in label and ("SELL" in analysis_type or "Distribution OUT" in analysis_type):
        return maybe_close_paper_copy_on_wallet_out_pressure(
            trade=open_trade,
            label=label,
            wallet_address=wallet_address,
            signature=signature,
            analysis=analysis,
            source="digest_gamq",
        )

    if _is_cluster_distribution_exit_label(label) and _is_big_distribution_signal_for_mint(analysis, mint):
        return maybe_close_paper_copy_on_wallet_out_pressure(
            trade=open_trade,
            label=label,
            wallet_address=wallet_address,
            signature=signature,
            analysis=analysis,
            source="digest_cluster",
        )

    return []

def find_recent_dht8_out_for_trade(trade: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    mint = trade.get("mint")
    if not mint:
        return None

    for tx in fetch_wallet_signatures(DHT8_MAIN_WALLET, limit=DHT8_EXIT_SYNC_SIGNATURE_LIMIT):
        signature = tx.get("signature") or ""
        if not signature:
            continue
        if not _is_tx_after_trade_open(tx, trade):
            continue

        analysis = analyze_transaction(signature, DHT8_MAIN_WALLET)
        analysis_type = analysis.get("type", "")
        token_changes = analysis.get("token_changes") or []
        active_mint = analysis.get("active_mint") or _primary_token_mint(token_changes)

        if active_mint == mint and "Distribution OUT" in analysis_type:
            return signature, analysis

    return None


def _is_cluster_distribution_exit_label(label: str) -> bool:
    if not FIRST_BIG_DISTRIBUTION_EXIT_ENABLED:
        return False
    return label.startswith(FIRST_BIG_DISTRIBUTION_EXIT_LABEL_PREFIX)


def _is_big_distribution_signal_for_mint(analysis: dict[str, Any], mint: str) -> bool:
    analysis_type = analysis.get("type", "")
    if "Distribution" not in analysis_type:
        return False

    token_changes = analysis.get("token_changes") or []
    for change in token_changes:
        change_mint = change.get("mint")
        if change_mint != mint:
            continue

        amount = _to_decimal(change.get("delta"))
        if _is_large_distribution_amount(mint, amount):
            return True

    return False


def find_recent_cluster_distribution_for_trade(trade: dict[str, Any]) -> tuple[str, str, dict[str, Any]] | None:
    """Find the first recent Cluster Distribution IN/OUT on the same open mint after entry.

    V4.18 uses this as a defensive final-exit sync, because the cluster often
    distributes to wallets like B6ut/FdwJBf before the liquidity collapse.
    """
    if not FIRST_BIG_DISTRIBUTION_EXIT_ENABLED:
        return None

    mint = trade.get("mint")
    if not mint:
        return None

    for label, wallet_address in get_all_watch_wallets().items():
        if not _is_cluster_distribution_exit_label(label):
            continue

        for tx in fetch_wallet_signatures(wallet_address, limit=FIRST_BIG_DISTRIBUTION_SIGNATURE_LIMIT):
            signature = tx.get("signature") or ""
            if not signature:
                continue
            if not _is_tx_after_trade_open(tx, trade):
                continue

            analysis = analyze_transaction(signature, wallet_address)
            if _is_big_distribution_signal_for_mint(analysis, mint):
                return label, signature, analysis

    return None



def _is_v424_out_signal(analysis_type: str) -> bool:
    if "SELL" in analysis_type:
        return True
    if "Distribution OUT" in analysis_type:
        return True
    if "Transfer OUT" in analysis_type and "ignored" not in analysis_type:
        return True
    return False


def maybe_close_paper_copy_on_simple_cluster_out_count(
    *,
    trade: dict[str, Any],
    label: str,
    wallet_address: str,
    signature: str,
    analysis: dict[str, Any],
    source: str = "wallet_watch_cluster_v424",
) -> list[str]:
    # V4.24 simple cluster exit.
    # DHT8 is handled separately as immediate exit.
    # Non-DHT8 OUT/SELL events are counted.
    # Exit only when 3 unique wallets OUT after entry.
    if not PAPER_COPY_ENABLED or not PAPER_SIMPLE_EXIT_ENABLED:
        return []

    if label == "DHT8 Main":
        return []

    mint = trade.get("mint")
    if not mint:
        return []

    analysis_type = analysis.get("type") or "Wallet OUT"
    if not _is_v424_out_signal(analysis_type):
        return []

    record_paper_exit_pressure_event(
        mint=mint,
        label=label,
        wallet_address=wallet_address,
        signature=signature,
        event_kind=analysis_type,
        source=source,
    )

    out_wallets_count = count_unique_paper_exit_pressure_wallets(mint, trade.get("opened_at"))

    if out_wallets_count < PAPER_SIMPLE_CLUSTER_OUT_MIN_WALLETS:
        return []

    dex_info = fetch_dex_token_info(mint) or {}

    return [
        close_paper_copy_trade(
            trade=trade,
            reason=(
                f"V4.24 simple cluster exit: {out_wallets_count} unique non-DHT8 "
                f"wallet OUT/SELL events after entry. Latest signal: {label} / {analysis_type}."
            ),
            signature=signature,
            dex_info=dex_info,
        )
    ]


def maybe_handle_paper_copy_signal(
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
        return messages

    analysis_type = analysis.get("type", "")
    token_family = analysis.get("token_family") or token_family_for_mint(mint)

    # New Mint Watch: DHT8 Distribution IN is watch-only, not entry.
    messages.extend(
        maybe_handle_new_mint_watch_signal(
            label=label,
            wallet_address=wallet_address,
            signature=signature,
            analysis={**analysis, "token_family": token_family},
        )
    )

    open_trade = get_open_paper_trade(mint)

    # If a watched new mint is moved out by DHT8 or sold by GAMq, stop watching it for entries.
    if label == "DHT8 Main" and "Distribution OUT" in analysis_type:
        watched_for_exit = get_new_mint_watch(mint)
        if watched_for_exit:
            fast_kill_message = build_fast_kill_cycle_message(
                mint=mint,
                watched=watched_for_exit,
                signature=signature,
                analysis=analysis,
            )
            if fast_kill_message:
                messages.append(fast_kill_message)

            update_new_mint_watch_status(
                mint=mint,
                status="EXIT_RISK",
                last_alert="DHT8_DISTRIBUTION_OUT",
            )

    if "GAMq" in label and ("SELL" in analysis_type or "Distribution OUT" in analysis_type):
        if get_new_mint_watch(mint):
            update_new_mint_watch_status(
                mint=mint,
                status="GAMQ_EXIT",
                last_alert="GAMQ_EXIT_ACTIVITY",
            )

    # V4.24 Simple Exit rule 1:
    # DHT8 OUT / SELL / Transfer OUT = immediate Paper exit in all cases.
    if open_trade and label == "DHT8 Main" and _is_v424_out_signal(analysis_type):
        messages.append(
            close_paper_copy_trade(
                trade=open_trade,
                reason=f"V4.24 simple exit: DHT8 OUT detected. Signal: {analysis_type}.",
                signature=signature,
            )
        )
        return messages

    # V4.24 Simple Exit rule 2:
    # Any non-DHT8 cluster/GAMq/BJsbr OUT is counted.
    # Exit only after 3 unique non-DHT8 wallets OUT after entry.
    if open_trade and label != "DHT8 Main" and _is_v424_out_signal(analysis_type):
        exit_messages = maybe_close_paper_copy_on_simple_cluster_out_count(
            trade=open_trade,
            label=label,
            wallet_address=wallet_address,
            signature=signature,
            analysis=analysis,
            source="wallet_watch_cluster_v424",
        )
        if exit_messages:
            messages.extend(exit_messages)
            return messages

    if open_trade:
        return messages

    # Entry rule: only known early-buyer wallets / G8R7 for now.
    # Unknown early buyer discovery comes later with a scanner.
    if not _is_paper_entry_wallet(label):
        return messages

    if "BUY" not in analysis_type:
        return messages

    if not _is_paper_allowed_family(token_family):
        return messages

    dex_info = fetch_dex_token_info(mint)
    if not dex_info:
        return messages

    passed, _reason = _paper_entry_quality(dex_info)
    if not passed:
        return messages

    watched_mint = get_new_mint_watch(mint)
    paper_reason = "Early known cluster buyer pattern."
    if watched_mint:
        paper_reason = "DHT8 New Mint Watch confirmed by early buyer."

    messages.append(
        open_paper_copy_trade(
            mint=mint,
            label=label,
            wallet_address=wallet_address,
            signature=signature,
            analysis={**analysis, "token_family": token_family, "paper_reason": paper_reason},
            dex_info=dex_info,
        )
    )

    return messages


def _new_mint_metrics_entry_quality(dex_info: dict[str, Any]) -> tuple[bool, str]:
    price = dex_info.get("price_usd") or Decimal("0")
    liquidity = dex_info.get("liquidity_usd") or Decimal("0")
    volume_h1 = dex_info.get("volume_h1") or Decimal("0")
    buys_h1 = int(dex_info.get("buys_h1") or 0)
    ratio = _paper_buy_sell_ratio(dex_info)
    pair_age_seconds = dex_info.get("pair_age_seconds")

    if price <= 0:
        return False, "Price is not available."

    if pair_age_seconds is not None and pair_age_seconds > NEW_MINT_METRICS_MAX_AGE_SECONDS:
        return False, "Pair age is above the new-mint entry window."

    if liquidity < NEW_MINT_METRICS_MIN_LIQUIDITY_USD:
        return False, f"Liquidity below {_fmt_usd(NEW_MINT_METRICS_MIN_LIQUIDITY_USD)}."

    if volume_h1 < NEW_MINT_METRICS_MIN_VOLUME_H1_USD:
        return False, f"Volume 1H below {_fmt_usd(NEW_MINT_METRICS_MIN_VOLUME_H1_USD)}."

    if buys_h1 < NEW_MINT_METRICS_MIN_BUYS_H1:
        return False, f"Buys 1H below {NEW_MINT_METRICS_MIN_BUYS_H1}."

    if ratio < NEW_MINT_METRICS_MIN_BUY_SELL_RATIO:
        volume_passed, volume_reason = _is_volume_dominance_entry(
            dex_info,
            min_buy_volume_ratio=NEW_MINT_METRICS_MIN_BUY_VOLUME_RATIO,
            min_price_change_h1_pct=NEW_MINT_METRICS_MIN_PRICE_CHANGE_H1_PCT,
        )
        if not volume_passed:
            return False, (
                f"Buy/Sell count ratio below {_fmt_decimal(NEW_MINT_METRICS_MIN_BUY_SELL_RATIO, 2)}x "
                f"and volume dominance not confirmed: {volume_reason}"
            )
        return True, f"New mint volume dominance entry quality passed. {volume_reason}"

    return True, "New mint metrics entry quality passed."



def _behavior_rotation_metrics_entry_quality(dex_info: dict[str, Any]) -> tuple[bool, str]:
    price = dex_info.get("price_usd") or Decimal("0")
    liquidity = dex_info.get("liquidity_usd") or Decimal("0")
    volume_h1 = dex_info.get("volume_h1") or Decimal("0")
    buys_h1 = int(dex_info.get("buys_h1") or 0)
    ratio = _paper_buy_sell_ratio(dex_info)
    pair_age_seconds = dex_info.get("pair_age_seconds")

    if price <= 0:
        return False, "Price is not available."

    if pair_age_seconds is not None and pair_age_seconds > NEW_MINT_METRICS_MAX_AGE_SECONDS:
        return False, "Pair age is above the behavior entry window."

    if liquidity < BEHAVIOR_MIN_LIQUIDITY_USD:
        return False, f"Behavior liquidity below {_fmt_usd(BEHAVIOR_MIN_LIQUIDITY_USD)}."

    if volume_h1 < BEHAVIOR_MIN_VOLUME_H1_USD:
        return False, f"Behavior volume 1H below {_fmt_usd(BEHAVIOR_MIN_VOLUME_H1_USD)}."

    if buys_h1 < BEHAVIOR_MIN_BUYS_H1:
        return False, f"Behavior buys 1H below {BEHAVIOR_MIN_BUYS_H1}."

    if ratio < BEHAVIOR_MIN_BUY_SELL_RATIO:
        volume_passed, volume_reason = _is_volume_dominance_entry(
            dex_info,
            min_buy_volume_ratio=BEHAVIOR_MIN_BUY_VOLUME_RATIO,
            min_price_change_h1_pct=BEHAVIOR_MIN_PRICE_CHANGE_H1_PCT,
        )
        if not volume_passed:
            return False, (
                f"Behavior Buy/Sell count ratio below {_fmt_decimal(BEHAVIOR_MIN_BUY_SELL_RATIO, 2)}x "
                f"and volume dominance not confirmed: {volume_reason}"
            )
        return True, f"Behavior volume dominance entry quality passed. {volume_reason}"

    return True, "Behavior-based rotation metrics entry quality passed."



def maybe_handle_digest_paper_sync(
    label: str,
    wallet_address: str,
    signature: str,
    block_time: int | None,
    analysis: dict[str, Any],
) -> list[str]:
    """Allow the digest to sync missed paper entries/exits.

    V4.18: Some fresh DHT8 transactions arrive as RPC Unknown during live watch,
    then become readable in the digest. This wrapper lets the digest create New
    Mint Watch / Paper Entry or close open trades, while protecting against late entries.
    """
    if not PAPER_COPY_ENABLED or not DIGEST_ENTRY_SYNC_ENABLED:
        return []

    analysis_type = analysis.get("type", "")
    token_changes = analysis.get("token_changes") or []
    mint = analysis.get("active_mint") or _primary_token_mint(token_changes)

    if not mint:
        return []

    age_seconds = _block_time_age_seconds(block_time)
    is_recent = age_seconds is None or age_seconds <= DIGEST_ENTRY_SYNC_MAX_AGE_SECONDS

    # Exits must be processed even if the digest is a bit late.
    if get_open_paper_trade(mint):
        return maybe_handle_paper_copy_signal(
            label=label,
            wallet_address=wallet_address,
            signature=signature,
            analysis=analysis,
        )

    # Entries from digest are allowed only when fresh, to avoid chasing old mints.
    if not is_recent:
        return []

    if label == "DHT8 Main" and "Distribution IN" in analysis_type:
        messages = maybe_handle_paper_copy_signal(
            label=label,
            wallet_address=wallet_address,
            signature=signature,
            analysis=analysis,
        )
        messages.extend(monitor_new_mint_metric_entries())
        return messages

    return []


def monitor_new_mint_metric_entries() -> list[str]:
    if not PAPER_COPY_ENABLED or not NEW_MINT_METRICS_ENTRY_ENABLED:
        return []

    messages: list[str] = []

    for watched in list_new_mint_watches(status="WATCHING"):
        mint = watched.get("mint")
        if not mint:
            continue
        # Pending New Mint Recheck V4.27
        # Keep very-early DHT8 mints alive for a short window while DexScreener data appears.
        first_seen = _parse_iso_datetime(watched.get("first_seen_at") or "")
        if first_seen:
            if first_seen.tzinfo is None:
                first_seen = first_seen.replace(tzinfo=timezone.utc)

            age_seconds = (datetime.now(timezone.utc) - first_seen).total_seconds()

            if NEW_MINT_RECHECK_ENABLED and age_seconds > NEW_MINT_RECHECK_MAX_AGE_SECONDS:
                update_new_mint_watch_status(
                    mint=mint,
                    status="EXPIRED",
                    last_alert="PENDING_RECHECK_EXPIRED",
                )
                continue
        if get_open_paper_trade(mint):
            update_new_mint_watch_status(
                mint=mint,
                status="PAPER_OPEN",
                last_alert="PAPER_ALREADY_OPEN",
            )
            continue

        token_family = watched.get("token_family") or token_family_for_mint(mint)
        is_allowed_family = _is_paper_allowed_family(token_family)
        is_behavior_family = _is_behavior_rotation_family(token_family)
        if not is_allowed_family and not is_behavior_family:
            continue

        dex_info = fetch_dex_token_info(mint)
        if not dex_info:
            update_new_mint_watch_checked(mint)
            continue

        price = dex_info.get("price_usd") or Decimal("0")
        liquidity = dex_info.get("liquidity_usd") or Decimal("0")
        volume_h1 = dex_info.get("volume_h1") or Decimal("0")

        if NEW_MINT_RECHECK_ENABLED and (
            price <= 0
            or liquidity < NEW_MINT_RECHECK_MIN_LIQUIDITY_USD
            or volume_h1 < NEW_MINT_RECHECK_MIN_VOLUME_H1_USD
        ):
            update_new_mint_watch_checked(mint)
            continue

        if is_behavior_family and not is_allowed_family:
            passed, reason = _behavior_rotation_metrics_entry_quality(dex_info)
        else:
            passed, reason = _new_mint_metrics_entry_quality(dex_info)

        if not passed:
            update_new_mint_watch_checked(mint)
            continue

        ratio = _paper_buy_sell_ratio(dex_info)
        volume_ratio = _paper_buy_sell_volume_ratio(dex_info)
        if ratio < NEW_MINT_METRICS_MIN_BUY_SELL_RATIO and (volume_ratio > 0 or (dex_info.get("price_change_h1") or Decimal("0")) > 0):
            paper_reason = "DHT8 New Mint Watch + volume-dominance / momentum metrics; early buyers may be unknown."
        else:
            paper_reason = "DHT8 New Mint Watch + strong Dex metrics; early buyers may be unknown."
        if _is_behavior_rotation_family(token_family):
            paper_reason = "Behavior-based DHT8 rotation + strong Dex metrics; token name may be new/unknown."

        analysis = {
            "type": "New Mint Metrics Entry",
            "token_family": token_family,
            "paper_reason": paper_reason,
        }

        messages.append(
            open_paper_copy_trade(
                mint=mint,
                label="DHT8 New Mint Watch / Metrics",
                wallet_address=watched.get("source_wallet") or DHT8_MAIN_WALLET,
                signature=watched.get("source_signature") or "",
                analysis=analysis,
                dex_info=dex_info,
            )
        )

        update_new_mint_watch_status(
            mint=mint,
            status="PAPER_OPEN",
            last_alert="METRICS_PAPER_ENTRY",
        )

    return messages



def _calc_peak_drawdown_pct(price: Decimal, peak_price: Decimal) -> Decimal:
    if peak_price <= 0 or price <= 0:
        return Decimal("0")
    if price >= peak_price:
        return Decimal("0")
    return ((peak_price - price) / peak_price) * Decimal("100")


def _calc_liquidity_drop_pct(liquidity: Decimal, last_liquidity: Decimal) -> Decimal:
    if last_liquidity <= 0 or liquidity <= 0:
        return Decimal("0")
    if liquidity >= last_liquidity:
        return Decimal("0")
    return ((last_liquidity - liquidity) / last_liquidity) * Decimal("100")


def _has_m5_sell_pressure(dex_info: dict[str, Any]) -> bool:
    sells_m5 = int(dex_info.get("sells_m5") or 0)
    buys_m5 = int(dex_info.get("buys_m5") or 0)

    if sells_m5 < PAPER_M5_SELL_PRESSURE_MIN_SELLS:
        return False

    if buys_m5 <= 0:
        return True

    return Decimal(sells_m5) >= Decimal(buys_m5) * PAPER_M5_SELL_PRESSURE_MULTIPLIER


def _build_sell_pressure_text(dex_info: dict[str, Any]) -> str:
    return f"m5 sells/buys: {int(dex_info.get('sells_m5') or 0)}/{int(dex_info.get('buys_m5') or 0)}"

def _trade_opened_iso_for_query(trade: dict[str, Any]) -> str:
    opened = _parse_iso_datetime(trade.get("opened_at"))
    if not opened:
        return str(trade.get("opened_at") or "")
    if opened.tzinfo is None:
        opened = opened.replace(tzinfo=timezone.utc)
    return opened.isoformat()


def find_v420_first_armed_wallet_out_for_trade(trade: dict[str, Any]) -> dict[str, Any] | None:
    """Return first Armed Wallet OUT/SELL after entry for this mint.

    Armed Wallet OUT means:
    - the same wallet had CLUSTER_IN/GAMQ_IN on this mint after paper entry
    - then later had CLUSTER_OUT/CLUSTER_SELL/GAMQ_OUT/GAMQ_SELL on the same mint

    This is intentionally based on Pattern Brain memory, not just live alerts,
    so missed pending/digest events can still protect the open paper trade.
    """
    if not PAPER_V420_EXIT_INTELLIGENCE_ENABLED or not PAPER_V420_ARMED_WALLET_OUT_EXIT_ENABLED:
        return None

    mint = trade.get("mint") or ""
    if not mint:
        return None

    try:
        _ensure_pattern_brain_tables()
    except Exception:
        return None

    opened_iso = _trade_opened_iso_for_query(trade)

    try:
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT exit_event.*
                FROM cluster_pattern_events AS exit_event
                WHERE exit_event.mint = ?
                  AND exit_event.event_kind IN ('CLUSTER_OUT', 'CLUSTER_SELL', 'GAMQ_OUT', 'GAMQ_SELL')
                  AND exit_event.event_at >= ?
                  AND COALESCE(exit_event.wallet_address, '') <> ''
                  AND EXISTS (
                      SELECT 1
                      FROM cluster_pattern_events AS arm_event
                      WHERE arm_event.mint = exit_event.mint
                        AND arm_event.wallet_address = exit_event.wallet_address
                        AND arm_event.event_kind IN ('CLUSTER_IN', 'GAMQ_IN')
                        AND arm_event.event_at >= ?
                        AND arm_event.event_at <= exit_event.event_at
                  )
                ORDER BY exit_event.event_at ASC
                LIMIT 1
                """,
                (mint, opened_iso, opened_iso),
            ).fetchone()
    except Exception:
        return None

    return dict(row) if row else None


def find_v420_pattern_exit_for_trade(trade: dict[str, Any]) -> dict[str, Any] | None:
    """Return first Pattern Brain OUT/SELL event after entry for this mint.

    This is the V4.20 safety sync for cases where Pattern Brain already recorded
    Cluster OUT/SELL on an open mint, but the live wallet scan did not close the
    paper trade yet.
    """
    if not PAPER_V420_EXIT_INTELLIGENCE_ENABLED or not PAPER_V420_PATTERN_EXIT_SYNC_ENABLED:
        return None

    mint = trade.get("mint") or ""
    if not mint:
        return None

    try:
        _ensure_pattern_brain_tables()
    except Exception:
        return None

    opened_iso = _trade_opened_iso_for_query(trade)

    try:
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM cluster_pattern_events
                WHERE mint = ?
                  AND event_kind IN ('DHT8_OUT', 'CLUSTER_OUT', 'CLUSTER_SELL', 'GAMQ_OUT', 'GAMQ_SELL')
                  AND event_at >= ?
                ORDER BY event_at ASC
                LIMIT 1
                """,
                (mint, opened_iso),
            ).fetchone()
    except Exception:
        return None

    return dict(row) if row else None


def _v420_exit_signature(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    return str(row.get("signature") or "")


def _v420_exit_label(row: dict[str, Any] | None) -> str:
    if not row:
        return "Unknown"
    label = row.get("label") or "Unknown"
    kind = row.get("event_kind") or "UNKNOWN"
    return f"{label} / {kind}"


def _ensure_paper_exit_pressure_table() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_exit_pressure_events (
                mint TEXT NOT NULL,
                signature TEXT NOT NULL,
                label TEXT,
                wallet_address TEXT,
                event_kind TEXT,
                source TEXT,
                seen_at TEXT,
                PRIMARY KEY (mint, signature)
            )
            """
        )
        conn.commit()


def record_paper_exit_pressure_event(
    *,
    mint: str,
    label: str,
    wallet_address: str,
    signature: str,
    event_kind: str,
    source: str,
) -> None:
    if not mint or not signature:
        return

    _ensure_paper_exit_pressure_table()
    now = _now_iso()

    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO paper_exit_pressure_events (
                mint,
                signature,
                label,
                wallet_address,
                event_kind,
                source,
                seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (mint, signature, label, wallet_address, event_kind, source, now),
        )
        conn.commit()


def count_unique_paper_exit_pressure_wallets(mint: str, opened_at: str | None) -> int:
    if not mint:
        return 0

    _ensure_paper_exit_pressure_table()
    opened_iso = opened_at or ""

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT COALESCE(label, '') || ':' || COALESCE(wallet_address, '')) AS c
            FROM paper_exit_pressure_events
            WHERE mint = ?
              AND seen_at >= ?
            """,
            (mint, opened_iso),
        ).fetchone()

    return int(row["c"] or 0) if row else 0


def _calc_entry_price_drop_pct(current_price: Decimal, entry_price: Decimal) -> Decimal:
    if entry_price <= 0 or current_price <= 0:
        return Decimal("0")
    if current_price >= entry_price:
        return Decimal("0")
    return ((entry_price - current_price) / entry_price) * Decimal("100")


def _calc_entry_liquidity_drop_pct(current_liquidity: Decimal, entry_liquidity: Decimal) -> Decimal:
    if entry_liquidity <= 0 or current_liquidity <= 0:
        return Decimal("0")
    if current_liquidity >= entry_liquidity:
        return Decimal("0")
    return ((entry_liquidity - current_liquidity) / entry_liquidity) * Decimal("100")


def maybe_close_paper_copy_on_wallet_out_pressure(
    *,
    trade: dict[str, Any],
    label: str,
    wallet_address: str,
    signature: str,
    analysis: dict[str, Any],
    source: str = "wallet_watch",
) -> list[str]:
    """V4.23 confirmed wallet-OUT exit.

    Single wallet OUT is now observe-only.
    A close requires:
    - at least 2 unique wallet OUT/SELL events after entry, or
    - one wallet OUT + price drop confirmation, or
    - one wallet OUT + liquidity drop confirmation.
    """
    if not PAPER_COPY_ENABLED or not PAPER_WALLET_OUT_EXIT_PRESSURE_ENABLED:
        return []

    mint = trade.get("mint")
    if not mint:
        return []

    event_kind = analysis.get("type") or "Wallet OUT"
    record_paper_exit_pressure_event(
        mint=mint,
        label=label,
        wallet_address=wallet_address,
        signature=signature,
        event_kind=event_kind,
        source=source,
    )

    dex_info = fetch_dex_token_info(mint) or {}
    current_price = dex_info.get("price_usd") or _to_decimal(trade.get("last_price_usd"))
    current_liquidity = dex_info.get("liquidity_usd") or _to_decimal(trade.get("last_liquidity_usd"))
    entry_price = _to_decimal(trade.get("entry_price_usd"))
    entry_liquidity = _to_decimal(trade.get("entry_liquidity_usd"))

    price_drop_pct = _calc_entry_price_drop_pct(current_price, entry_price)
    liquidity_drop_pct = _calc_entry_liquidity_drop_pct(current_liquidity, entry_liquidity)
    out_wallets_count = count_unique_paper_exit_pressure_wallets(mint, trade.get("opened_at"))

    close_reason = ""

    if out_wallets_count >= PAPER_WALLET_OUT_MIN_EVENTS:
        close_reason = (
            f"V4.23 confirmed wallet OUT pressure: {out_wallets_count} unique wallet OUT events after entry."
        )
    elif price_drop_pct >= PAPER_WALLET_OUT_PRICE_DROP_CONFIRM_PCT:
        close_reason = (
            f"V4.23 wallet OUT + price confirmation: price dropped "
            f"{_fmt_decimal(price_drop_pct, 2)}% from entry."
        )
    elif liquidity_drop_pct >= PAPER_WALLET_OUT_LIQUIDITY_DROP_CONFIRM_PCT:
        close_reason = (
            f"V4.23 wallet OUT + liquidity confirmation: liquidity dropped "
            f"{_fmt_decimal(liquidity_drop_pct, 2)}% from entry."
        )

    if not close_reason:
        return []

    close_reason = (
        f"{close_reason} Signal: {label} / {event_kind}. "
        f"Single OUT alone is observe-only."
    )

    return [
        close_paper_copy_trade(
            trade=trade,
            reason=close_reason,
            signature=signature,
            dex_info=dex_info,
        )
    ]


def monitor_paper_copy_trades() -> list[str]:
    if not PAPER_COPY_ENABLED:
        return []

    messages: list[str] = []

    for trade in list_open_paper_trades():
        mint = trade["mint"]

        # V4.20 First Armed Wallet OUT Exit:
        # Main hypothesis under test: a wallet that received the open mint after entry
        # and later OUT/SELLs the same mint is often the earliest real distribution signal.
        v420_armed_exit = find_v420_first_armed_wallet_out_for_trade(trade)
        if v420_armed_exit:
            dex_info = fetch_dex_token_info(mint) or {}
            messages.append(
                close_paper_copy_trade(
                    trade=trade,
                    reason=f"V4.20 First Armed Wallet OUT exit: {_v420_exit_label(v420_armed_exit)}.",
                    signature=_v420_exit_signature(v420_armed_exit),
                    dex_info=dex_info,
                )
            )
            continue

        # V4.20 Pattern Brain Exit Sync:
        # If the memory table already recorded OUT/SELL after entry, close even if
        # the live scan missed it because of RPC delay or pending recheck timing.
        v420_pattern_exit = find_v420_pattern_exit_for_trade(trade)
        if v420_pattern_exit:
            dex_info = fetch_dex_token_info(mint) or {}
            messages.append(
                close_paper_copy_trade(
                    trade=trade,
                    reason=f"V4.20 Pattern Brain exit sync: {_v420_exit_label(v420_pattern_exit)}.",
                    signature=_v420_exit_signature(v420_pattern_exit),
                    dex_info=dex_info,
                )
            )
            continue

        # V4.23 Noise/False-Exit Fix:
        # Single Cluster OUT is observe-only now. Do not close just because one cluster wallet OUT/SELLs.
        # Strong exits below remain active: DHT8 OUT, liquidity rug/drop, stop loss, post-TP1 protection.
        recent_cluster_distribution = find_recent_cluster_distribution_for_trade(trade)
        if recent_cluster_distribution:
            pass

        # DHT8 OUT Sync:
        # Still important, but no longer the only exit signal because it can arrive late.
        recent_exit = find_recent_dht8_out_for_trade(trade)
        if recent_exit:
            signature, _analysis = recent_exit
            exit_messages = maybe_close_paper_copy_on_wallet_out_pressure(
                trade=trade,
                label="DHT8 Main",
                wallet_address=DHT8_MAIN_WALLET,
                signature=signature,
                analysis=_analysis,
                source="monitor_dht8_sync",
            )
            if exit_messages:
                messages.extend(exit_messages)
                continue

        dex_info = fetch_dex_token_info(mint)

        if not dex_info:
            continue

        price = dex_info.get("price_usd") or Decimal("0")
        liquidity = dex_info.get("liquidity_usd") or Decimal("0")
        entry_price = _to_decimal(trade.get("entry_price_usd"))
        entry_liquidity = _to_decimal(trade.get("entry_liquidity_usd"))
        last_liquidity = _to_decimal(trade.get("last_liquidity_usd"))
        peak_price = max(_to_decimal(trade.get("peak_price_usd")), price)

        update_paper_copy_market(trade, dex_info)

        pnl_pct = Decimal("0")
        if entry_price > 0:
            pnl_pct = ((price - entry_price) / entry_price) * Decimal("100")

        tp1_done = bool(int(trade.get("tp1_done") or 0))
        locked_pct = _to_decimal(trade.get("tp1_closed_pct"))
              

        # TP1: lock 50%.
        if not tp1_done and pnl_pct >= PAPER_TP1_PCT:
            messages.append(mark_paper_copy_tp1(trade, dex_info))
            refreshed_trade = get_open_paper_trade(mint)
            if refreshed_trade:
                trade = refreshed_trade
            tp1_done = True
            locked_pct = _to_decimal(trade.get("tp1_closed_pct"))
                    # V4.28 Post-TP1 liquidity protection
        if (
            tp1_done
            and last_liquidity > 0
            and liquidity <= last_liquidity * (Decimal("1") - PAPER_AFTER_TP1_FAST_LIQUIDITY_DROP_PCT)
        ):
            messages.append(
                close_paper_copy_trade(
                    trade=trade,
                    reason="V4.28 post-TP1 emergency: liquidity dropped fast after TP1.",
                    dex_info=dex_info,
                )
            )
            continue

        # V4.19 TP2: after TP1, lock total 75% when profit reaches +60%.
        if (
            tp1_done
            and locked_pct < PAPER_TP2_TOTAL_LOCKED_PERCENT
            and pnl_pct >= PAPER_TP2_PCT
        ):
            # V4.23: TP2 still updates locked profit internally, but no separate Telegram alert.
            mark_paper_copy_tp2(trade, dex_info)

            refreshed_trade = get_open_paper_trade(mint)
            if refreshed_trade:
                trade = refreshed_trade
            locked_pct = _to_decimal(trade.get("tp1_closed_pct"))

        # V4.32 Position-age final exit:
        # Use the age of this Paper position, not DexScreener pair age.
        # This prevents instant exits when the bot enters an already-older pair.
        position_age_hours = _trade_age_hours(trade)

        if (
            PAPER_AFTER_TP1_TIME_PROTECTION_ENABLED
            and position_age_hours >= PAPER_AFTER_TP1_MAX_HOLD_HOURS
            and pnl_pct > 0
        ):
            messages.append(
                close_paper_copy_trade(
                    trade=trade,
                    reason=(
                        f"V4.32 position-age profit exit: position age reached "
                        f"{_fmt_decimal(PAPER_AFTER_TP1_MAX_HOLD_HOURS, 0)}h "
                        f"and position is profitable."
                    ),
                    dex_info=dex_info,
                )
            )
            continue
        # Old no-TP1 time protection.
        if (
            PAPER_TIME_PROTECTION_ENABLED
            and not tp1_done
            and _trade_age_hours(trade) >= PAPER_NO_TP1_MAX_HOLD_HOURS
            and pnl_pct >= PAPER_NO_TP1_MIN_EXIT_PNL
        ):
            messages.append(
                close_paper_copy_trade(
                    trade=trade,
                    reason=f"Time protection: trade exceeded {_fmt_decimal(PAPER_NO_TP1_MAX_HOLD_HOURS, 0)}h without TP1 and is still positive.",
                    dex_info=dex_info,
                )
            )
            continue

        # Emergency exits below are last-resort damage control.

        if liquidity <= PAPER_LIQUIDITY_RUG_USD:
            messages.append(
                close_paper_copy_trade(
                    trade=trade,
                    reason="Liquidity Rug detected.",
                    dex_info=dex_info,
                )
            )
            continue

        if entry_liquidity > 0 and liquidity <= entry_liquidity * (Decimal("1") - PAPER_LIQUIDITY_DROP_PCT):
            messages.append(
                close_paper_copy_trade(
                    trade=trade,
                    reason="Liquidity dropped more than 70% from entry.",
                    dex_info=dex_info,
                )
            )
            continue

        if entry_price > 0 and price <= entry_price * (Decimal("1") - PAPER_STOP_LOSS_PCT):
            messages.append(
                close_paper_copy_trade(
                    trade=trade,
                    reason="Stop loss: price dropped 25% from entry.",
                    dex_info=dex_info,
                )
            )
            continue

        if tp1_done and entry_price > 0 and price <= entry_price * (Decimal("1") + PAPER_AFTER_TP1_PROFIT_LOCK_PCT):
            messages.append(
                close_paper_copy_trade(
                    trade=trade,
                    reason="Post-TP1 profit lock: remaining position fell back near protected profit area.",
                    dex_info=dex_info,
                )
            )
            continue

        trailing_drop = PAPER_TRAILING_AFTER_TP1_DROP_PCT if tp1_done else PAPER_TRAILING_DROP_PCT
        if peak_price > entry_price and price <= peak_price * (Decimal("1") - trailing_drop):
            messages.append(
                close_paper_copy_trade(
                    trade=trade,
                    reason=f"Trailing stop: price dropped more than {_fmt_decimal(trailing_drop * Decimal('100'), 0)}% from peak.",
                    dex_info=dex_info,
                )
            )
            continue

    return messages

def build_fast_kill_cycle_message(
    mint: str,
    watched: dict[str, Any] | None,
    signature: str | None = None,
    analysis: dict[str, Any] | None = None,
) -> str | None:
    if not watched:
        return None

    first_seen_at = watched.get("first_seen_at")
    first_seen = _parse_iso_datetime(first_seen_at)
    if not first_seen:
        return None

    if first_seen.tzinfo is None:
        first_seen = first_seen.replace(tzinfo=timezone.utc)

    seconds = int((datetime.now(timezone.utc) - first_seen).total_seconds())
    if seconds < 0 or seconds > 15 * 60:
        return None

    token_family = watched.get("token_family") or token_family_for_mint(mint)
    symbol = watched.get("symbol") or TOKEN_ALIASES.get(mint) or _token_label(mint)

    lines = [
        "⚡ FAST KILL CYCLE V4.18",
        "",
        f"Token: {symbol}",
        f"Mint: {_short(mint)}",
        f"Family: {token_family or 'N/A'}",
        "",
        f"DHT8 IN → OUT duration: {_format_duration(seconds)}",
        "Meaning: this mint was rotated out very quickly after DHT8 received it.",
        "Action: Do not enter late. Treat as failed/fast-kill cycle.",
    ]

    if signature:
        lines.extend(["", "Tx:", f"https://solscan.io/tx/{signature}"])

    return "\n".join(lines)


def _paper_trade_runtime_snapshot(trade: dict[str, Any]) -> dict[str, Any]:
    mint = trade.get("mint")
    dex_info = fetch_dex_token_info(mint) if mint else None
    dex_info = dex_info or {}

    current_price = dex_info.get("price_usd") or _to_decimal(trade.get("last_price_usd"))
    current_liquidity = dex_info.get("liquidity_usd") or _to_decimal(trade.get("last_liquidity_usd"))
    entry_price = _to_decimal(trade.get("entry_price_usd"))
    peak_price = max(_to_decimal(trade.get("peak_price_usd")), current_price)

    pnl_pct = Decimal("0")
    if entry_price > 0:
        pnl_pct = ((current_price - entry_price) / entry_price) * Decimal("100")

    return {
        "dex_info": dex_info,
        "current_price": current_price,
        "current_liquidity": current_liquidity,
        "entry_price": entry_price,
        "peak_price": peak_price,
        "pnl_pct": pnl_pct,
        "url": dex_info.get("url") or f"https://dexscreener.com/solana/{mint}",
    }


def build_copy_positions_message() -> str:
    trades = list_open_paper_trades()
    counts = paper_copy_summary_counts()

    if not trades:
        return "\n".join(
            [
                "📋 Paper Copy Positions",
                "",
                "No open paper copy positions.",
                "",
                f"Closed trades: {counts.get('closed', 0)}",
                f"Clean closed: {counts.get('clean_closed', 0)} | Excluded: {counts.get('excluded', 0)}",
                f"Clean average PnL: {_fmt_decimal(counts.get('avg_pnl') or Decimal('0'), 2)}%",
                "",
                "Mode: Paper only. No real positions.",
            ]
        )

    lines = [
        "📋 Paper Copy Positions",
        "",
        f"Open positions: {len(trades)}",
        "Mode: Paper only. No real positions.",
        "",
    ]

    for index, trade in enumerate(trades, start=1):
        snap = _paper_trade_runtime_snapshot(trade)
        symbol = trade.get("symbol") or (snap["dex_info"].get("symbol") if snap.get("dex_info") else None) or "UNKNOWN"
        mint = trade.get("mint")

        lines.extend(
            [
                f"{index}) {symbol} | {_short(mint)}",
                f"Family: {trade.get('token_family') or token_family_for_mint(mint) or 'N/A'}",
                f"Entry: {_fmt_price(snap['entry_price'])}",
                f"Now: {_fmt_price(snap['current_price'])}",
                f"Peak: {_fmt_price(snap['peak_price'])}",
                f"PnL: {_fmt_decimal(snap['pnl_pct'], 2)}%",
                f"Locked: {_fmt_decimal(_to_decimal(trade.get('tp1_closed_pct')), 2)}% @ {_fmt_decimal(_to_decimal(trade.get('tp1_pnl_pct')), 2)}% avg" if int(trade.get('tp1_done') or 0) else "Locked: 0%",
                f"Liquidity: {_fmt_usd(snap['current_liquidity'])}",
                f"Age: {_age_text_from_iso(trade.get('opened_at'))}",
                f"Reason: {trade.get('entry_label') or 'N/A'}",
                "DexScreener:",
                snap["url"],
                "",
            ]
        )

    return "\n".join(lines).strip()


def build_copy_trades_message(limit: int = 10) -> str:
    trades = list_closed_paper_trades(limit=limit)
    counts = paper_copy_summary_counts()

    if not trades:
        return "\n".join(
            [
                "📜 Paper Copy Trades",
                "",
                "No closed paper copy trades yet.",
                "",
                f"Open positions: {counts.get('open', 0)}",
                "Mode: Paper only.",
            ]
        )

    lines = [
        "📜 Paper Copy Trades",
        "",
        f"Closed trades shown: {len(trades)}",
        f"Total closed: {counts.get('closed', 0)}",
        f"Clean closed: {counts.get('clean_closed', 0)} | Excluded: {counts.get('excluded', 0)}",
        f"Clean average PnL: {_fmt_decimal(counts.get('avg_pnl') or Decimal('0'), 2)}%",
        f"Clean Win Rate: {_fmt_decimal(counts.get('win_rate') or Decimal('0'), 2)}%",
        "",
    ]

    for index, trade in enumerate(trades, start=1):
        symbol = trade.get("symbol") or "UNKNOWN"
        mint = trade.get("mint")
        pnl = _to_decimal(trade.get("pnl_pct"))
        abnormal_note = " | EXCLUDED FROM STATS" if _is_abnormal_paper_copy_trade(trade) else ""
        opened_at = trade.get("opened_at")
        closed_at = trade.get("closed_at")
        duration = "N/A"
        opened = _parse_iso_datetime(opened_at)
        closed = _parse_iso_datetime(closed_at)
        if opened and closed:
            if opened.tzinfo is None:
                opened = opened.replace(tzinfo=timezone.utc)
            if closed.tzinfo is None:
                closed = closed.replace(tzinfo=timezone.utc)
            duration = _format_duration(max(0, int((closed - opened).total_seconds())))

        lines.extend(
            [
                f"{index}) {symbol} | {_short(mint)}",
                f"Entry: {_fmt_price(_to_decimal(trade.get('entry_price_usd')))}",
                f"Exit: {_fmt_price(_to_decimal(trade.get('exit_price_usd')))}",
                f"PnL: {_fmt_decimal(pnl, 2)}%{abnormal_note}",
                f"Locked before final: {_fmt_decimal(_to_decimal(trade.get('tp1_closed_pct')), 2)}% @ {_fmt_decimal(_to_decimal(trade.get('tp1_pnl_pct')), 2)}% avg" if int(trade.get('tp1_done') or 0) else "Locked before final: No",
                f"Duration: {duration}",
                f"Reason: {trade.get('exit_reason') or 'N/A'}",
                "DexScreener:",
                f"https://dexscreener.com/solana/{mint}",
                "",
            ]
        )

    return "\n".join(lines).strip()



def _fmt_signed_usd(value: Decimal | float | int | None) -> str:
    amount = _to_decimal(value)
    sign = "+" if amount > 0 else ""
    return f"{sign}${float(amount):,.2f}"


def _paper_copy_wallet_open_components(trade: dict[str, Any]) -> dict[str, Any]:
    snap = _paper_trade_runtime_snapshot(trade)
    trade_size = PAPER_COPY_TRADE_SIZE_USD
    current_pnl_pct = snap["pnl_pct"]

    tp1_done = bool(int(trade.get("tp1_done") or 0))
    tp1_closed_pct = _to_decimal(trade.get("tp1_closed_pct"))
    tp1_pnl_pct = _to_decimal(trade.get("tp1_pnl_pct"))

    closed_weight = Decimal("0")
    if tp1_done and tp1_closed_pct > 0:
        closed_weight = tp1_closed_pct / Decimal("100")

    remaining_weight = max(Decimal("0"), Decimal("1") - closed_weight)

    tp1_realized_usd = trade_size * closed_weight * (tp1_pnl_pct / Decimal("100"))
    remaining_unrealized_usd = trade_size * remaining_weight * (current_pnl_pct / Decimal("100"))
    allocated_usd = trade_size * remaining_weight

    return {
        "snap": snap,
        "trade_size": trade_size,
        "tp1_realized_usd": tp1_realized_usd,
        "unrealized_usd": remaining_unrealized_usd,
        "allocated_usd": allocated_usd,
        "remaining_weight": remaining_weight,
        "current_pnl_pct": current_pnl_pct,
    }


def _paper_copy_wallet_closed_realized_usd(trade: dict[str, Any]) -> Decimal:
    # Closed pnl_pct is already effective if TP1 happened before final exit.
    pnl_pct = _to_decimal(trade.get("pnl_pct"))
    return PAPER_COPY_TRADE_SIZE_USD * (pnl_pct / Decimal("100"))


def build_copy_wallet_message() -> str:
    _ensure_paper_copy_table()

    trades = list_all_paper_copy_trades()
    open_trades = [trade for trade in trades if trade.get("status") == "OPEN"]
    closed_trades_all = [trade for trade in trades if trade.get("status") == "CLOSED"]
    excluded_closed_trades = [
        trade for trade in closed_trades_all
        if _is_abnormal_paper_copy_trade(trade)
    ]
    closed_trades = [
        trade for trade in closed_trades_all
        if not _is_abnormal_paper_copy_trade(trade)
    ]

    closed_realized_usd = sum(
        (_paper_copy_wallet_closed_realized_usd(trade) for trade in closed_trades),
        Decimal("0"),
    )

    open_tp1_realized_usd = Decimal("0")
    open_unrealized_usd = Decimal("0")
    allocated_usd = Decimal("0")
    open_lines: list[str] = []

    for index, trade in enumerate(open_trades, start=1):
        components = _paper_copy_wallet_open_components(trade)
        snap = components["snap"]
        open_tp1_realized_usd += components["tp1_realized_usd"]
        open_unrealized_usd += components["unrealized_usd"]
        allocated_usd += components["allocated_usd"]

        symbol = trade.get("symbol") or (snap.get("dex_info") or {}).get("symbol") or "UNKNOWN"
        mint = trade.get("mint")
        locked_pct = _to_decimal(trade.get("tp1_closed_pct"))
        locked_text = f"{_fmt_decimal(locked_pct, 2)}%" if int(trade.get("tp1_done") or 0) else "0%"

        open_lines.extend(
            [
                f"{index}) {symbol} | {_short(mint)}",
                f"Position size: {_fmt_usd(PAPER_COPY_TRADE_SIZE_USD)} paper",
                f"Remaining allocated: {_fmt_usd(components['allocated_usd'])}",
                f"Current PnL: {_fmt_decimal(components['current_pnl_pct'], 2)}%",
                f"Locked: {locked_text}",
                f"Realized locked: {_fmt_signed_usd(components['tp1_realized_usd'])}",
                f"Unrealized: {_fmt_signed_usd(components['unrealized_usd'])}",
                "",
            ]
        )

    realized_usd = closed_realized_usd + open_tp1_realized_usd
    estimated_balance = PAPER_COPY_WALLET_STARTING_BALANCE_USD + realized_usd + open_unrealized_usd
    free_cash = PAPER_COPY_WALLET_STARTING_BALANCE_USD + realized_usd - allocated_usd
    if free_cash < 0:
        free_cash = Decimal("0")

    total_pnl_usd = estimated_balance - PAPER_COPY_WALLET_STARTING_BALANCE_USD
    total_pnl_pct = Decimal("0")
    if PAPER_COPY_WALLET_STARTING_BALANCE_USD > 0:
        total_pnl_pct = (total_pnl_usd / PAPER_COPY_WALLET_STARTING_BALANCE_USD) * Decimal("100")

    lines = [
        "💼 Paper Copy Wallet V4.18",
        "",
        f"Starting Balance: {_fmt_usd(PAPER_COPY_WALLET_STARTING_BALANCE_USD)}",
        f"Paper Trade Size: {_fmt_usd(PAPER_COPY_TRADE_SIZE_USD)} each",
        f"Open Positions: {len(open_trades)}",
        f"Closed Trades: {len(closed_trades_all)}",
        f"Clean Closed Trades: {len(closed_trades)}",
        f"Excluded Abnormal Trades: {len(excluded_closed_trades)}",
        "",
        f"Realized PnL: {_fmt_signed_usd(realized_usd)}",
        f"Unrealized PnL: {_fmt_signed_usd(open_unrealized_usd)}",
        f"Total PnL: {_fmt_signed_usd(total_pnl_usd)} ({_fmt_decimal(total_pnl_pct, 2)}%)",
        "",
        f"Estimated Balance: {_fmt_usd(estimated_balance)}",
        f"Allocated: {_fmt_usd(allocated_usd)}",
        f"Free Cash: {_fmt_usd(free_cash)}",
        "",
        "Mode: Paper only. This is separate from the old /wallet system.",
    ]

    if open_lines:
        lines.extend(["", "Open position accounting:", ""])
        lines.extend(open_lines)

    return "\n".join(lines).strip()


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
        f"{analysis['emoji']} Wallet Watch V4.18",
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
            f"Price: {_fmt_price(price)}",
            f"Entry price: {_fmt_price(entry_price)}",
            f"Peak price: {_fmt_price(peak_price)}",
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

    for label, wallet_address in get_all_watch_wallets().items():
        await asyncio.sleep(0.35)

        signatures = fetch_wallet_signatures(wallet_address, limit=10)

        if not signatures:
            continue

        latest_signature = signatures[0].get("signature")
        latest_block_time = signatures[0].get("blockTime")

        if not latest_signature:
            continue

        last_seen = get_last_signature(wallet_address)

        # First initialization.
        # Normal wallets: save latest signature only and skip old history.
        # Critical wallets: if the latest tx is fresh, analyze it once so we do not miss
        # first BUY/SELL/Distribution after adding a new wallet.
        if not last_seen:
            if _is_critical_first_init_wallet(label) and _is_recent_block_time(
                latest_block_time,
                CRITICAL_FIRST_INIT_WINDOW_SECONDS,
            ):
                analysis = analyze_transaction(latest_signature, wallet_address)

                if _is_no_details_unknown(analysis):
                    save_pending_unknown_tx(label, wallet_address, latest_signature, latest_block_time)

                if analysis.get("notify") or _is_paper_relevant_analysis(analysis):
                    maybe_register_active_token(
                        label=label,
                        wallet_address=wallet_address,
                        signature=latest_signature,
                        analysis=analysis,
                    )

                    paper_messages = maybe_handle_paper_copy_signal(
                        label=label,
                        wallet_address=wallet_address,
                        signature=latest_signature,
                        analysis=analysis,
                    )

                    if chat_id:
                        for paper_message in paper_messages:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=paper_message,
                                disable_web_page_preview=True,
                            )

                        # V4.23: Wallet Activity Summary suppressed to reduce Telegram spam.

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

                if _is_no_details_unknown(analysis):
                    save_pending_unknown_tx(label, wallet_address, signature, tx.get("blockTime"))

                if analysis.get("notify") or _is_paper_relevant_analysis(analysis):
                    maybe_register_active_token(
                        label=label,
                        wallet_address=wallet_address,
                        signature=signature,
                        analysis=analysis,
                    )

                    paper_messages = maybe_handle_paper_copy_signal(
                        label=label,
                        wallet_address=wallet_address,
                        signature=signature,
                        analysis=analysis,
                    )

                    if chat_id:
                        for paper_message in paper_messages:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=paper_message,
                                disable_web_page_preview=True,
                            )

                        # V4.23: Wallet Activity Summary suppressed to reduce Telegram spam.
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

        important_items: list[tuple[dict[str, Any], dict[str, Any], int]] = []
        ignored_count = 0

        for tx in new_txs:
            signature = tx.get("signature") or ""
            if not signature:
                ignored_count += 1
                continue

            analysis = analyze_transaction(signature, wallet_address)

            if _is_no_details_unknown(analysis):
                save_pending_unknown_tx(label, wallet_address, signature, tx.get("blockTime"))

            if analysis.get("notify") or _is_paper_relevant_analysis(analysis):
                important_items.append((tx, analysis, ignored_count))
            else:
                ignored_count += 1

        for important_tx, important_analysis, item_ignored_count in important_items:
            important_signature = important_tx.get("signature") or ""

            maybe_register_active_token(
                label=label,
                wallet_address=wallet_address,
                signature=important_signature,
                analysis=important_analysis,
            )

            paper_messages = maybe_handle_paper_copy_signal(
                label=label,
                wallet_address=wallet_address,
                signature=important_signature,
                analysis=important_analysis,
            )

            if chat_id:
                for paper_message in paper_messages:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=paper_message,
                        disable_web_page_preview=True,
                    )

                # V4.23: Wallet Activity Summary suppressed to reduce Telegram spam.

        save_wallet_signature(
            wallet_address=wallet_address,
            label=label,
            last_signature=latest_signature,
            last_seen_at=_format_time(latest_block_time),
        )

    if chat_id:
        for paper_message in process_pending_unknown_txs():
            await context.bot.send_message(
                chat_id=chat_id,
                text=paper_message,
                disable_web_page_preview=True,
            )

        # V4.23: Active token alerts are suppressed to keep Telegram clean.
        # Keep only NEW MINT WATCH, PAPER ENTRY, TP1, PAPER EXIT, and requested STATUS.

        for paper_message in monitor_new_mint_metric_entries():
            await context.bot.send_message(
                chat_id=chat_id,
                text=paper_message,
                disable_web_page_preview=True,
            )

        for paper_message in monitor_paper_copy_trades():
            await context.bot.send_message(
                chat_id=chat_id,
                text=paper_message,
                disable_web_page_preview=True,
            )

# ─────────────────────────────────────────────
# V4.18 — Final Safety Layer
# Cluster Discovery + Armed Cluster Exit + Manual Controls
# Key rule:
#   Cluster IN = ARMED / danger watch only.
#   Final exit = DHT8 OUT, GAMq OUT/SELL, or OUT/SELL from a cluster recipient
#   that was armed on the same mint after entry.
# This avoids early exits caused by normal retail noise or simple internal receipt.
# ─────────────────────────────────────────────

CLUSTER_DISCOVERY_MIN_AMOUNT = Decimal("650000000")
CLUSTER_DYNAMIC_WATCH_LIMIT = 45
CLUSTER_ARMED_STATUS = "ARMED_RECIPIENT"


def _ensure_cluster_discovery_tables() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cluster_discovered_wallets (
                wallet_address TEXT PRIMARY KEY,
                label TEXT,
                first_seen_at TEXT,
                last_seen_at TEXT,
                first_mint TEXT,
                last_mint TEXT,
                events_count INTEGER DEFAULT 0,
                in_count INTEGER DEFAULT 0,
                out_count INTEGER DEFAULT 0,
                sell_count INTEGER DEFAULT 0,
                buy_count INTEGER DEFAULT 0,
                confidence TEXT DEFAULT 'low',
                role TEXT DEFAULT 'candidate',
                source TEXT,
                notes TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cluster_mint_recipients (
                mint TEXT NOT NULL,
                wallet_address TEXT NOT NULL,
                label TEXT,
                first_seen_at TEXT,
                last_seen_at TEXT,
                in_count INTEGER DEFAULT 0,
                out_count INTEGER DEFAULT 0,
                sell_count INTEGER DEFAULT 0,
                amount_in TEXT DEFAULT '0',
                amount_out TEXT DEFAULT '0',
                status TEXT DEFAULT 'WATCH',
                last_signature TEXT,
                PRIMARY KEY (mint, wallet_address)
            )
            """
        )
        conn.commit()


def _static_label_for_wallet(wallet_address: str) -> str | None:
    for label, address in dict(WATCH_WALLETS).items():
        if address == wallet_address:
            return label
    return None


def _candidate_label(wallet_address: str) -> str:
    known = _static_label_for_wallet(wallet_address)
    if known:
        return known
    return f"Candidate Cluster {_short(wallet_address, 4, 4)}"


def _cluster_confidence(events_count: int, in_count: int, out_count: int, sell_count: int, buy_count: int) -> str:
    if out_count > 0 or sell_count > 0:
        return "high"
    if events_count >= 2 or in_count >= 2 or buy_count > 0:
        return "medium"
    return "low"


def _cluster_role(confidence: str, in_count: int, out_count: int, sell_count: int, buy_count: int) -> str:
    if out_count > 0 or sell_count > 0:
        return "exit / distribution"
    if buy_count > 0:
        return "early buyer"
    if in_count > 0:
        return "recipient / distribution"
    if confidence == "high":
        return "confirmed cluster"
    return "candidate"


def _cluster_event_kind(analysis: dict[str, Any]) -> str:
    analysis_type = analysis.get("type", "")
    if "SELL" in analysis_type:
        return "SELL"
    if "BUY" in analysis_type:
        return "BUY"
    if "Distribution OUT" in analysis_type or "Transfer OUT" in analysis_type:
        return "OUT"
    if "Distribution IN" in analysis_type or "Transfer IN" in analysis_type:
        return "IN"
    return "OTHER"


def _large_token_amount_for_mint(analysis: dict[str, Any], mint: str) -> Decimal:
    best = Decimal("0")
    for change in analysis.get("token_changes") or []:
        if change.get("mint") != mint:
            continue
        amount = abs(_to_decimal(change.get("delta")))
        if amount > best:
            best = amount
    return best


def record_cluster_wallet_event(
    *,
    label: str,
    wallet_address: str,
    mint: str,
    analysis: dict[str, Any],
    signature: str = "",
    source: str = "wallet_watch",
) -> None:
    if not wallet_address or not mint:
        return

    _ensure_cluster_discovery_tables()
    now = _now_iso()
    event_kind = _cluster_event_kind(analysis)
    amount = _large_token_amount_for_mint(analysis, mint)

    known_label = _candidate_label(wallet_address)

    in_inc = 1 if event_kind == "IN" else 0
    out_inc = 1 if event_kind == "OUT" else 0
    sell_inc = 1 if event_kind == "SELL" else 0
    buy_inc = 1 if event_kind == "BUY" else 0

    with get_conn() as conn:
        current = conn.execute(
            "SELECT * FROM cluster_discovered_wallets WHERE wallet_address = ?",
            (wallet_address,),
        ).fetchone()

        if current:
            events_count = int(current["events_count"] or 0) + 1
            in_count = int(current["in_count"] or 0) + in_inc
            out_count = int(current["out_count"] or 0) + out_inc
            sell_count = int(current["sell_count"] or 0) + sell_inc
            buy_count = int(current["buy_count"] or 0) + buy_inc
            confidence = _cluster_confidence(events_count, in_count, out_count, sell_count, buy_count)
            role = _cluster_role(confidence, in_count, out_count, sell_count, buy_count)

            conn.execute(
                """
                UPDATE cluster_discovered_wallets
                SET label = ?, last_seen_at = ?, last_mint = ?, events_count = ?,
                    in_count = ?, out_count = ?, sell_count = ?, buy_count = ?,
                    confidence = ?, role = ?, source = ?
                WHERE wallet_address = ?
                """,
                (
                    known_label,
                    now,
                    mint,
                    events_count,
                    in_count,
                    out_count,
                    sell_count,
                    buy_count,
                    confidence,
                    role,
                    source,
                    wallet_address,
                ),
            )
        else:
            events_count = 1
            confidence = _cluster_confidence(events_count, in_inc, out_inc, sell_inc, buy_inc)
            role = _cluster_role(confidence, in_inc, out_inc, sell_inc, buy_inc)
            conn.execute(
                """
                INSERT INTO cluster_discovered_wallets (
                    wallet_address, label, first_seen_at, last_seen_at, first_mint, last_mint,
                    events_count, in_count, out_count, sell_count, buy_count,
                    confidence, role, source, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    wallet_address,
                    known_label,
                    now,
                    now,
                    mint,
                    mint,
                    events_count,
                    in_inc,
                    out_inc,
                    sell_inc,
                    buy_inc,
                    confidence,
                    role,
                    source,
                    "auto-discovered from cluster behavior",
                ),
            )

        if event_kind in {"IN", "OUT", "SELL"}:
            row = conn.execute(
                "SELECT * FROM cluster_mint_recipients WHERE mint = ? AND wallet_address = ?",
                (mint, wallet_address),
            ).fetchone()

            if row:
                new_in_count = int(row["in_count"] or 0) + in_inc
                new_out_count = int(row["out_count"] or 0) + out_inc
                new_sell_count = int(row["sell_count"] or 0) + sell_inc
                current_in = _to_decimal(row["amount_in"] or "0")
                current_out = _to_decimal(row["amount_out"] or "0")
                status = row["status"] or "WATCH"
                if event_kind == "IN":
                    status = CLUSTER_ARMED_STATUS
                if event_kind in {"OUT", "SELL"}:
                    status = "EXIT_SIGNAL"

                conn.execute(
                    """
                    UPDATE cluster_mint_recipients
                    SET label = ?, last_seen_at = ?, in_count = ?, out_count = ?, sell_count = ?,
                        amount_in = ?, amount_out = ?, status = ?, last_signature = ?
                    WHERE mint = ? AND wallet_address = ?
                    """,
                    (
                        known_label,
                        now,
                        new_in_count,
                        new_out_count,
                        new_sell_count,
                        str(current_in + amount if event_kind == "IN" else current_in),
                        str(current_out + amount if event_kind in {"OUT", "SELL"} else current_out),
                        status,
                        signature,
                        mint,
                        wallet_address,
                    ),
                )
            else:
                status = CLUSTER_ARMED_STATUS if event_kind == "IN" else "EXIT_SIGNAL"
                conn.execute(
                    """
                    INSERT INTO cluster_mint_recipients (
                        mint, wallet_address, label, first_seen_at, last_seen_at,
                        in_count, out_count, sell_count, amount_in, amount_out,
                        status, last_signature
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mint,
                        wallet_address,
                        known_label,
                        now,
                        now,
                        in_inc,
                        out_inc,
                        sell_inc,
                        str(amount if event_kind == "IN" else Decimal("0")),
                        str(amount if event_kind in {"OUT", "SELL"} else Decimal("0")),
                        status,
                        signature,
                    ),
                )

        conn.commit()


def _token_owner_deltas_for_mint(details: dict[str, Any], mint: str) -> dict[str, Decimal]:
    meta = details.get("meta") or {}
    pre = meta.get("preTokenBalances") or []
    post = meta.get("postTokenBalances") or []

    balances: dict[str, Decimal] = {}

    def key(item: dict[str, Any]) -> tuple[str, str] | None:
        if item.get("mint") != mint:
            return None
        owner = item.get("owner")
        if not owner:
            return None
        return owner, str(item.get("accountIndex"))

    pre_map: dict[tuple[str, str], Decimal] = {}
    post_map: dict[tuple[str, str], Decimal] = {}
    for item in pre:
        k = key(item)
        if k:
            pre_map[k] = _token_amount_from_balance(item)
    for item in post:
        k = key(item)
        if k:
            post_map[k] = _token_amount_from_balance(item)

    for k in set(pre_map.keys()) | set(post_map.keys()):
        owner, _idx = k
        delta = post_map.get(k, Decimal("0")) - pre_map.get(k, Decimal("0"))
        balances[owner] = balances.get(owner, Decimal("0")) + delta

    return balances


def discover_related_wallets_from_tx(signature: str, mint: str, source_label: str, source_event: str) -> None:
    if not signature or not mint:
        return

    details = fetch_transaction_details(signature, attempts=2, retry_delay_seconds=0.25)
    if not details:
        return

    owner_deltas = _token_owner_deltas_for_mint(details, mint)
    
    record_wallet_link_events_from_deltas(
        mint=mint,
        signature=signature,
        owner_deltas=owner_deltas,
        source_label=source_label,
        source_event=source_event,
    )
    for owner, delta in owner_deltas.items():
        if not owner:
            continue
        if owner == DHT8_MAIN_WALLET:
            continue
        if abs(delta) < CLUSTER_DISCOVERY_MIN_AMOUNT:
            continue

        fake_analysis = {
            "type": "Cluster Distribution IN / Recipient Wallet" if delta > 0 else "Cluster Distribution OUT / Possible Prep for Sell",
            "token_changes": [{"mint": mint, "delta": delta}],
        }
        record_cluster_wallet_event(
            label=_candidate_label(owner),
            wallet_address=owner,
            mint=mint,
            analysis=fake_analysis,
            signature=signature,
            source=f"tx_discovery:{source_label}:{source_event}",
        )

# V4.33 — Passive Wallet Link Graph
def _ensure_wallet_link_tables() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS wallet_link_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                detected_at TEXT NOT NULL,
                signature TEXT NOT NULL,
                mint TEXT NOT NULL,
                from_wallet TEXT NOT NULL,
                to_wallet TEXT NOT NULL,
                amount TEXT NOT NULL,
                source_label TEXT,
                source_event TEXT,
                UNIQUE(signature, mint, from_wallet, to_wallet)
            )
            """
        )
        conn.commit()


def record_wallet_link_events_from_deltas(
    *,
    mint: str,
    signature: str,
    owner_deltas: dict[str, Decimal],
    source_label: str = "",
    source_event: str = "",
) -> None:
    if not mint or not signature or not owner_deltas:
        return

    negatives = [
        (w, abs(d))
        for w, d in owner_deltas.items()
        if d < 0 and abs(d) >= CLUSTER_DISCOVERY_MIN_AMOUNT
    ]
    positives = [
        (w, d)
        for w, d in owner_deltas.items()
        if d > 0 and d >= CLUSTER_DISCOVERY_MIN_AMOUNT
    ]

    if not negatives or not positives:
        return

    _ensure_wallet_link_tables()
    now = _now_iso()

    with get_conn() as conn:
        for from_wallet, out_amount in negatives:
            for to_wallet, in_amount in positives:
                if from_wallet == to_wallet:
                    continue

                amount = min(out_amount, in_amount)

                conn.execute(
                    """
                    INSERT OR IGNORE INTO wallet_link_events (
                        detected_at, signature, mint, from_wallet, to_wallet,
                        amount, source_label, source_event
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now,
                        signature,
                        mint,
                        from_wallet,
                        to_wallet,
                        str(amount),
                        source_label,
                        source_event,
                    ),
                )

        conn.commit()


def build_wallet_links_report(limit: int = 25) -> str:
    _ensure_wallet_link_tables()

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                from_wallet,
                to_wallet,
                COUNT(*) AS links,
                COUNT(DISTINCT mint) AS mints,
                MAX(detected_at) AS last_seen,
                MAX(mint) AS last_mint,
                MAX(amount) AS max_amount
            FROM wallet_link_events
            GROUP BY from_wallet, to_wallet
            ORDER BY links DESC, mints DESC, last_seen DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    lines = [
        "🔗 Wallet Links V4.33",
        "",
        "Mode: Passive learning only. No entry/exit decisions changed.",
        "Inferred from token owner balance deltas inside the same transaction.",
        "",
    ]

    if not rows:
        lines.append("No wallet links recorded yet.")
        return "\n".join(lines)

    for i, row in enumerate(rows, 1):
        r = dict(row)
        lines.extend(
            [
                f"{i}) {_short(r.get('from_wallet'))} → {_short(r.get('to_wallet'))}",
                f"   Links: {r.get('links') or 0} | Mints: {r.get('mints') or 0}",
                f"   Last mint: {_short(r.get('last_mint'))}",
                f"   Max amount: {r.get('max_amount')}",
                "",
            ]
        )

    lines.extend(
        [
            "How to use:",
            "- Repeated links reveal wallet relationships.",
            "- Example: DHT8 → GAMq means DHT8 likely routes tokens to GAMq.",
            "- This is analysis only.",
        ]
    )

    return "\n".join(lines)
    return "\n".join(lines)


def build_entry_debug_report(limit: int = 20) -> str:
    lines = [
        "🧪 Entry Debug V4.34",
        "",
        "Purpose: Show why recent group activity did not become Paper Entry.",
        "",
        "Current likely blockers:",
        "- No group entry signal",
        "- Mint already had a previous Paper trade",
        "- DexScreener price unavailable",
        "- Missed older tx when last_signature is not found",
        "",
        "Next step: add persistent blocked-entry logging.",
    ]
    return "\n".join(lines)


def list_discovered_cluster_wallets(limit: int = 80) -> list[dict[str, Any]]:
    _ensure_cluster_discovery_tables()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM cluster_discovered_wallets
            ORDER BY
                CASE confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                events_count DESC,
                last_seen_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_watch_wallets() -> dict[str, str]:
    """Known wallets + discovered medium/high confidence cluster wallets.

    Dynamic wallets are intentionally capped to reduce RPC pressure.
    """
    wallets = dict(WATCH_WALLETS)
    try:
        discovered = list_discovered_cluster_wallets(limit=CLUSTER_DYNAMIC_WATCH_LIMIT)
    except Exception:
        return wallets

    for row in discovered:
        address = row.get("wallet_address") or ""
        if not address or address in wallets.values():
            continue
        confidence = row.get("confidence") or "low"
        if confidence not in {"medium", "high"}:
            continue
        label = row.get("label") or _candidate_label(address)
        if not label.startswith("Candidate") and not label.startswith("Cluster"):
            label = f"Candidate {label}"
        wallets[label] = address

    return wallets


def build_cluster_discovery_message() -> str:
    known_count = len(WATCH_WALLETS)
    all_wallets = get_all_watch_wallets()
    discovered = list_discovered_cluster_wallets(limit=60)

    lines = [
        "🧠 Cluster Discovery V4.18",
        "",
        f"Known wallets: {known_count}",
        f"Watched including discovered: {len(all_wallets)}",
        "",
        "Legend:",
        "HIGH = exit/sell/out behavior seen",
        "MEDIUM = repeated recipient/buyer behavior",
        "LOW = one-time candidate only",
        "",
        "Known wallets:",
    ]

    for label, address in list(WATCH_WALLETS.items())[:35]:
        lines.append(f"• {label} | {_short(address)}")

    if discovered:
        lines.extend(["", "Discovered / candidate wallets:"])
        for row in discovered[:40]:
            lines.extend(
                [
                    f"• {row.get('label') or _short(row.get('wallet_address'))}",
                    f"  Wallet: {_short(row.get('wallet_address'))}",
                    f"  Confidence: {(row.get('confidence') or 'low').upper()} | Role: {row.get('role') or 'candidate'}",
                    f"  Events: {row.get('events_count') or 0} | IN: {row.get('in_count') or 0} | OUT: {row.get('out_count') or 0} | SELL: {row.get('sell_count') or 0}",
                    f"  Last mint: {_short(row.get('last_mint'))}",
                    "",
                ]
            )
    else:
        lines.extend(["", "No discovered wallets yet."])

    lines.extend([
        "Action:",
        "The bot monitors known wallets and medium/high discovered wallets.",
        "Cluster IN = armed watch. Cluster OUT/SELL after IN = emergency exit.",
    ])

    return "\n".join(lines)


def _is_cluster_like_label(label: str) -> bool:
    return label.startswith("Cluster ") or label.startswith("Candidate Cluster") or label.startswith("Candidate ")


def _is_group_exit_signal_for_mint(label: str, analysis: dict[str, Any], mint: str) -> bool:
    analysis_type = analysis.get("type", "")
    if label == "DHT8 Main" and "Distribution OUT" in analysis_type:
        return True
    if "GAMq" in label and ("SELL" in analysis_type or "Distribution OUT" in analysis_type):
        return True
    if _is_cluster_like_label(label) and ("SELL" in analysis_type or "Distribution OUT" in analysis_type or "Transfer OUT" in analysis_type):
        return _large_token_amount_for_mint(analysis, mint) >= CLUSTER_DISCOVERY_MIN_AMOUNT
    return False


def _is_group_arm_signal_for_mint(label: str, analysis: dict[str, Any], mint: str) -> bool:
    analysis_type = analysis.get("type", "")
    if not _is_cluster_like_label(label):
        return False
    if "Distribution IN" not in analysis_type and "Transfer IN" not in analysis_type:
        return False
    return _large_token_amount_for_mint(analysis, mint) >= CLUSTER_DISCOVERY_MIN_AMOUNT

def _has_first_cluster_in_alert_been_sent(mint: str) -> bool:
    try:
        _ensure_pattern_brain_tables()
        with get_conn() as conn:
            row = conn.execute(
                "SELECT first_cluster_in_at FROM cluster_mint_memory WHERE mint = ?",
                (mint,),
            ).fetchone()
            return bool(row and row["first_cluster_in_at"])
    except Exception:
        return True


def build_first_cluster_in_alert(label: str, wallet_address: str, mint: str, signature: str, analysis: dict[str, Any]) -> str:
    amount = _large_token_amount_for_mint(analysis, mint)
    return "\n".join(
        [
            "🟡 FIRST CLUSTER IN ALERT",
            "",
            f"Mint: {_short(mint)}",
            f"Full Mint: {mint}",
            f"Wallet label: {label}",
            f"Wallet: {_short(wallet_address)}",
            f"Detected: First group IN on this mint",
            f"Amount: {_fmt_decimal(amount, 4)}",
            "",
            "Meaning:",
            "This is the first detected group entry on this token.",
            "Alert only. No paper entry and no real trade was executed.",
            "",
            "DexScreener:",
            f"https://dexscreener.com/solana/{mint}",
            "",
            f"Tx: https://solscan.io/tx/{signature}",
        ]
    )
def build_cluster_armed_message(label: str, wallet_address: str, mint: str, signature: str, analysis: dict[str, Any]) -> str:
    amount = _large_token_amount_for_mint(analysis, mint)
    return "\n".join(
        [
            "🟡 CLUSTER ARMED WATCH V4.18",
            "",
            f"Mint: {_short(mint)}",
            f"Cluster wallet: {label}",
            f"Wallet: {_short(wallet_address)}",
            "Detected: Cluster Distribution IN after Paper entry",
            f"Amount: {_fmt_decimal(amount, 4)}",
            "",
            "Meaning:",
            "This is NOT final exit by itself.",
            "The wallet is now marked as an armed recipient for this mint.",
            "",
            "Final exit trigger:",
            "If this wallet, DHT8, GAMq, or another cluster wallet starts OUT/SELL on the same mint, close immediately.",
            "",
            f"Tx: https://solscan.io/tx/{signature}",
        ]
    )


# Override: Cluster IN arms the trade; Cluster OUT/SELL exits.
def _has_any_paper_copy_trade_for_mint(mint: str) -> bool:
    """Return True if this mint was already opened before.

    This prevents repeated Paper entries on the same token, even if the trade is
    already closed. The user rule is: first group entry only, one Paper trade per
    mint.
    """
    if not mint:
        return False

    _ensure_paper_copy_table()
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM paper_copy_trades
            WHERE mint = ?
            LIMIT 1
            """,
            (mint,),
        ).fetchone()

    return bool(row)


def _is_group_entry_signal_for_mint(
    label: str,
    wallet_address: str,
    analysis: dict[str, Any],
    mint: str,
) -> bool:
    """V4.30: any watched group wallet entering a new mint is a Paper entry.

    No symbol/family filter.
    No liquidity/volume/buy-sell-ratio filter.
    The only requirements are:
    - the signal came from a watched/group wallet,
    - this wallet gained this mint,
    - the event looks like BUY / IN / receive / swap.
    """
    if not mint:
        return False

    try:
        watched_wallets = set(get_all_watch_wallets().values())
    except Exception:
        watched_wallets = set(WATCH_WALLETS.values())

    is_group_wallet = (
        wallet_address in watched_wallets
        or label == "DHT8 Main"
        or "GAMq" in label
        or "BJsbr" in label
        or _is_cluster_like_label(label)
    )
    if not is_group_wallet:
        return False

    has_positive_mint = False
    for change in analysis.get("token_changes") or []:
        if change.get("mint") != mint:
            continue
        if _to_decimal(change.get("delta")) > 0:
            has_positive_mint = True
            break

    if not has_positive_mint:
        return False

    analysis_type = analysis.get("type", "")
    entry_keywords = (
        "BUY",
        "Distribution IN",
        "Transfer IN",
        "Cluster Receive",
        "TOKEN SWAP",
    )

    return any(keyword in analysis_type for keyword in entry_keywords)


# Override V4.30: any watched group wallet entering a new mint opens one Paper entry.
def maybe_handle_paper_copy_signal(
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
        return messages

    analysis_type = analysis.get("type", "")
    token_family = analysis.get("token_family") or token_family_for_mint(mint)

    # Record and discover cluster behavior whenever a meaningful group event appears.
    if "Distribution" in analysis_type or "Transfer" in analysis_type or "SELL" in analysis_type or "BUY" in analysis_type:
        if (
            _large_token_amount_for_mint(analysis, mint) >= CLUSTER_DISCOVERY_MIN_AMOUNT
            or _is_cluster_like_label(label)
            or label == "DHT8 Main"
            or "GAMq" in label
            or "BJsbr" in label
        ):
            record_cluster_wallet_event(
                label=label,
                wallet_address=wallet_address,
                mint=mint,
                analysis=analysis,
                signature=signature,
                source="wallet_watch_v4_30",
            )
            discover_related_wallets_from_tx(signature, mint, label, analysis_type)

    # DHT8 Distribution IN remains a watch alert, but entry is no longer limited to DHT8/SPCX/SLX.
    messages.extend(
        maybe_handle_new_mint_watch_signal(
            label=label,
            wallet_address=wallet_address,
            signature=signature,
            analysis={**analysis, "token_family": token_family},
        )
    )

    open_trade = get_open_paper_trade(mint)

    # Mark watched mint as risky when DHT8/GAMq exits before entry.
    if label == "DHT8 Main" and "Distribution OUT" in analysis_type:
        watched_for_exit = get_new_mint_watch(mint)
        if watched_for_exit:
            fast_kill_message = build_fast_kill_cycle_message(
                mint=mint,
                watched=watched_for_exit,
                signature=signature,
                analysis=analysis,
            )
            if fast_kill_message:
                messages.append(fast_kill_message)
            update_new_mint_watch_status(
                mint=mint,
                status="EXIT_RISK",
                last_alert="DHT8_DISTRIBUTION_OUT",
            )

    if "GAMq" in label and ("SELL" in analysis_type or "Distribution OUT" in analysis_type):
        if get_new_mint_watch(mint):
            update_new_mint_watch_status(
                mint=mint,
                status="GAMQ_EXIT",
                last_alert="GAMQ_EXIT_ACTIVITY",
            )

    # Exit logic is preserved: group OUT/SELL is pressure-based, not entry-related.
    if open_trade and _is_group_exit_signal_for_mint(label, analysis, mint):
        exit_messages = maybe_close_paper_copy_on_wallet_out_pressure(
            trade=open_trade,
            label=label,
            wallet_address=wallet_address,
            signature=signature,
            analysis=analysis,
            source="group_exit_signal_v4_30",
        )
        if exit_messages:
            messages.extend(exit_messages)
            return messages

    # Cluster IN after an existing entry arms the wallet only; no duplicate entry.
    if open_trade and _is_group_arm_signal_for_mint(label, analysis, mint):
        record_cluster_wallet_event(
            label=label,
            wallet_address=wallet_address,
            mint=mint,
            analysis=analysis,
            signature=signature,
            source="armed_recipient_after_entry_v4_30",
        )
        messages.append(build_cluster_armed_message(label, wallet_address, mint, signature, analysis))
        return messages

    if open_trade:
        return messages

    # V4.30 entry rule:
    # Any watched/group wallet entering a new mint opens exactly one Paper trade.
    # No SPCX/SLX filter. No Initial Buyer/G8R7 filter. No liquidity/volume/ratio filter.
    if not _is_group_entry_signal_for_mint(label, wallet_address, analysis, mint):
        return messages

    # Do not re-enter the same mint after a prior open/closed Paper trade.
    if _has_any_paper_copy_trade_for_mint(mint):
        return messages

    dex_info = fetch_dex_token_info(mint) or {}

    passed, block_reason = _group_entry_quality_v432(dex_info)
    if not passed:
        return messages

    entry_price = dex_info.get("price_usd") or Decimal("0")
    if entry_price <= 0:
        return messages

    paper_reason = (
        "V4.32 first group wallet entry on a new mint. "
        "Passed price/liquidity/volume safety filter."
    )

    messages.append(
        open_paper_copy_trade(
            mint=mint,
            label=label,
            wallet_address=wallet_address,
            signature=signature,
            analysis={
                **analysis,
                "token_family": token_family,
                "paper_reason": paper_reason,
            },
            dex_info=dex_info,
        )
    )
    return messages

def maybe_close_paper_copy_from_digest_event(
    label: str,
    wallet_address: str,
    tx: dict[str, Any],
    analysis: dict[str, Any],
) -> list[str]:
    if not PAPER_COPY_ENABLED:
        return []
    signature = tx.get("signature") or ""
    if not signature:
        return []

    token_changes = analysis.get("token_changes") or []
    mint = analysis.get("active_mint") or _primary_token_mint(token_changes)
    if not mint:
        return []

    # Always discover cluster participants from digest too.
    if "Distribution" in analysis.get("type", "") or "SELL" in analysis.get("type", ""):
        record_cluster_wallet_event(label=label, wallet_address=wallet_address, mint=mint, analysis=analysis, signature=signature, source="digest_v4_17")
        discover_related_wallets_from_tx(signature, mint, label, analysis.get("type", ""))

    open_trade = get_open_paper_trade(mint)
    if not open_trade or not _is_tx_after_trade_open(tx, open_trade):
        return []

    if _is_group_exit_signal_for_mint(label, analysis, mint):
        return [
            close_paper_copy_trade(
                trade=open_trade,
                reason=f"Digest group-exit sync on open mint: {label} / {analysis.get('type', '')}.",
                signature=signature,
            )
        ]

    if _is_group_arm_signal_for_mint(label, analysis, mint):
        record_cluster_wallet_event(label=label, wallet_address=wallet_address, mint=mint, analysis=analysis, signature=signature, source="digest_armed_v4_17")
        return [build_cluster_armed_message(label, wallet_address, mint, signature, analysis)]

    return []


def find_recent_cluster_distribution_for_trade(trade: dict[str, Any]) -> tuple[str, str, dict[str, Any]] | None:
    """Find recent group OUT/SELL signals only.

    V4.18: Cluster IN arms the trade; it is not final exit. OUT/SELL from
    any known or discovered cluster wallet on the same mint is final exit.
    """
    mint = trade.get("mint")
    if not mint:
        return None

    for label, wallet_address in get_all_watch_wallets().items():
        if label == "DHT8 Main":
            continue
        if not _is_cluster_like_label(label) and "GAMq" not in label:
            continue

        for tx in fetch_wallet_signatures(wallet_address, limit=FIRST_BIG_DISTRIBUTION_SIGNATURE_LIMIT):
            signature = tx.get("signature") or ""
            if not signature or not _is_tx_after_trade_open(tx, trade):
                continue
            analysis = analyze_transaction(signature, wallet_address)

            # Discover and arm on IN, but do not return exit.
            if _is_group_arm_signal_for_mint(label, analysis, mint):
                record_cluster_wallet_event(label=label, wallet_address=wallet_address, mint=mint, analysis=analysis, signature=signature, source="sync_armed_v4_17")
                continue

            if _is_group_exit_signal_for_mint(label, analysis, mint):
                return label, signature, analysis

    return None

# ─────────────────────────────────────────────
# V4.18 — Cluster Pattern Brain / Passive Learning
# This layer DOES NOT change entry or exit decisions.
# It records event timelines and builds wallet danger scores so we can learn
# how the group behaves across mints before using the scores in a future version.
# ─────────────────────────────────────────────

PATTERN_BRAIN_MAX_RECENT_MINTS = 10
PATTERN_BRAIN_MAX_WALLETS = 12


def _ensure_pattern_brain_tables() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cluster_pattern_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mint TEXT NOT NULL,
                event_at TEXT NOT NULL,
                label TEXT,
                wallet_address TEXT,
                event_kind TEXT,
                analysis_type TEXT,
                amount TEXT DEFAULT '0',
                signature TEXT,
                source TEXT,
                price_usd TEXT DEFAULT '0',
                liquidity_usd TEXT DEFAULT '0',
                notes TEXT,
                UNIQUE(signature, mint, wallet_address, event_kind)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cluster_mint_memory (
                mint TEXT PRIMARY KEY,
                first_seen_at TEXT,
                last_event_at TEXT,
                dht8_in_at TEXT DEFAULT '',
                dht8_out_at TEXT DEFAULT '',
                first_cluster_in_at TEXT DEFAULT '',
                first_cluster_out_at TEXT DEFAULT '',
                first_gamq_at TEXT DEFAULT '',
                first_paper_entry_at TEXT DEFAULT '',
                first_paper_exit_at TEXT DEFAULT '',
                cluster_in_count INTEGER DEFAULT 0,
                cluster_out_count INTEGER DEFAULT 0,
                gamq_event_count INTEGER DEFAULT 0,
                paper_entry_count INTEGER DEFAULT 0,
                paper_exit_count INTEGER DEFAULT 0,
                last_event_kind TEXT DEFAULT '',
                last_event_label TEXT DEFAULT '',
                last_signature TEXT DEFAULT '',
                last_price_usd TEXT DEFAULT '0',
                last_liquidity_usd TEXT DEFAULT '0',
                final_pnl_pct TEXT DEFAULT '',
                final_exit_reason TEXT DEFAULT ''
            )
            """
        )
        conn.commit()


def _pattern_event_kind(label: str, analysis: dict[str, Any] | None, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    analysis = analysis or {}
    base = _cluster_event_kind(analysis)
    if label == "DHT8 Main" and base == "IN":
        return "DHT8_IN"
    if label == "DHT8 Main" and base == "OUT":
        return "DHT8_OUT"
    if "GAMq" in label and base in {"IN", "OUT", "SELL"}:
        return f"GAMQ_{base}"
    if base in {"IN", "OUT", "SELL", "BUY"}:
        return f"CLUSTER_{base}"
    return base or "OTHER"


def _pattern_price_liquidity(mint: str) -> tuple[Decimal, Decimal]:
    # Best-effort only. We avoid making this critical to bot decisions.
    try:
        info = fetch_dex_token_info(mint) or {}
        return _to_decimal(info.get("price_usd")), _to_decimal(info.get("liquidity_usd"))
    except Exception:
        return Decimal("0"), Decimal("0")


def record_pattern_brain_event(
    *,
    mint: str,
    label: str,
    wallet_address: str = "",
    event_kind: str | None = None,
    analysis: dict[str, Any] | None = None,
    signature: str = "",
    source: str = "wallet_watch",
    notes: str = "",
    price_usd: Decimal | None = None,
    liquidity_usd: Decimal | None = None,
    pnl_pct: Decimal | None = None,
    exit_reason: str = "",
) -> None:
    if not mint:
        return

    _ensure_pattern_brain_tables()
    now = _now_iso()
    try:
        add_forensics_event(
            event_type=event_kind or "PATTERN_EVENT",
            token=mint,
            wallet=wallet_address or label,
            details=f"label={label} source={source} signature={signature} notes={notes}",
        )
    except Exception:
        pass
    analysis = analysis or {}
    kind = _pattern_event_kind(label, analysis, event_kind)
    analysis_type = analysis.get("type") or kind
    amount = _large_token_amount_for_mint(analysis, mint) if analysis else Decimal("0")

    if price_usd is None or liquidity_usd is None:
        # For trade events we usually pass price/liquidity. For cluster events this is best-effort.
        fetched_price, fetched_liq = _pattern_price_liquidity(mint)
        if price_usd is None:
            price_usd = fetched_price
        if liquidity_usd is None:
            liquidity_usd = fetched_liq

    is_cluster_in = kind in {"CLUSTER_IN", "GAMQ_IN"}
    is_cluster_out = kind in {"CLUSTER_OUT", "CLUSTER_SELL", "GAMQ_OUT", "GAMQ_SELL"}
    is_gamq = kind.startswith("GAMQ_")

    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO cluster_pattern_events (
                mint, event_at, label, wallet_address, event_kind, analysis_type,
                amount, signature, source, price_usd, liquidity_usd, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mint,
                now,
                label,
                wallet_address,
                kind,
                analysis_type,
                str(amount),
                signature or f"{source}:{now}:{kind}",
                source,
                str(price_usd or Decimal("0")),
                str(liquidity_usd or Decimal("0")),
                notes,
            ),
        )

        row = conn.execute("SELECT * FROM cluster_mint_memory WHERE mint = ?", (mint,)).fetchone()
        if row:
            cluster_in_count = int(row["cluster_in_count"] or 0) + (1 if is_cluster_in else 0)
            cluster_out_count = int(row["cluster_out_count"] or 0) + (1 if is_cluster_out else 0)
            gamq_count = int(row["gamq_event_count"] or 0) + (1 if is_gamq else 0)
            paper_entry_count = int(row["paper_entry_count"] or 0) + (1 if kind == "PAPER_ENTRY" else 0)
            paper_exit_count = int(row["paper_exit_count"] or 0) + (1 if kind == "PAPER_EXIT" else 0)

            dht8_in_at = row["dht8_in_at"] or (now if kind == "DHT8_IN" else "")
            dht8_out_at = row["dht8_out_at"] or (now if kind == "DHT8_OUT" else "")
            first_cluster_in_at = row["first_cluster_in_at"] or (now if is_cluster_in else "")
            first_cluster_out_at = row["first_cluster_out_at"] or (now if is_cluster_out else "")
            first_gamq_at = row["first_gamq_at"] or (now if is_gamq else "")
            first_paper_entry_at = row["first_paper_entry_at"] or (now if kind == "PAPER_ENTRY" else "")
            first_paper_exit_at = row["first_paper_exit_at"] or (now if kind == "PAPER_EXIT" else "")

            final_pnl = row["final_pnl_pct"] or ""
            final_reason = row["final_exit_reason"] or ""
            if kind == "PAPER_EXIT":
                final_pnl = str(pnl_pct) if pnl_pct is not None else final_pnl
                final_reason = exit_reason or final_reason

            conn.execute(
                """
                UPDATE cluster_mint_memory
                SET last_event_at = ?, dht8_in_at = ?, dht8_out_at = ?,
                    first_cluster_in_at = ?, first_cluster_out_at = ?, first_gamq_at = ?,
                    first_paper_entry_at = ?, first_paper_exit_at = ?,
                    cluster_in_count = ?, cluster_out_count = ?, gamq_event_count = ?,
                    paper_entry_count = ?, paper_exit_count = ?,
                    last_event_kind = ?, last_event_label = ?, last_signature = ?,
                    last_price_usd = ?, last_liquidity_usd = ?,
                    final_pnl_pct = ?, final_exit_reason = ?
                WHERE mint = ?
                """,
                (
                    now,
                    dht8_in_at,
                    dht8_out_at,
                    first_cluster_in_at,
                    first_cluster_out_at,
                    first_gamq_at,
                    first_paper_entry_at,
                    first_paper_exit_at,
                    cluster_in_count,
                    cluster_out_count,
                    gamq_count,
                    paper_entry_count,
                    paper_exit_count,
                    kind,
                    label,
                    signature,
                    str(price_usd or Decimal("0")),
                    str(liquidity_usd or Decimal("0")),
                    final_pnl,
                    final_reason,
                    mint,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO cluster_mint_memory (
                    mint, first_seen_at, last_event_at, dht8_in_at, dht8_out_at,
                    first_cluster_in_at, first_cluster_out_at, first_gamq_at,
                    first_paper_entry_at, first_paper_exit_at,
                    cluster_in_count, cluster_out_count, gamq_event_count,
                    paper_entry_count, paper_exit_count,
                    last_event_kind, last_event_label, last_signature,
                    last_price_usd, last_liquidity_usd, final_pnl_pct, final_exit_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mint,
                    now,
                    now,
                    now if kind == "DHT8_IN" else "",
                    now if kind == "DHT8_OUT" else "",
                    now if is_cluster_in else "",
                    now if is_cluster_out else "",
                    now if is_gamq else "",
                    now if kind == "PAPER_ENTRY" else "",
                    now if kind == "PAPER_EXIT" else "",
                    1 if is_cluster_in else 0,
                    1 if is_cluster_out else 0,
                    1 if is_gamq else 0,
                    1 if kind == "PAPER_ENTRY" else 0,
                    1 if kind == "PAPER_EXIT" else 0,
                    kind,
                    label,
                    signature,
                    str(price_usd or Decimal("0")),
                    str(liquidity_usd or Decimal("0")),
                    str(pnl_pct) if (kind == "PAPER_EXIT" and pnl_pct is not None) else "",
                    exit_reason if kind == "PAPER_EXIT" else "",
                ),
            )
        conn.commit()


# Wrap V4.16 discovery to add passive pattern memory without changing trading decisions.
_record_cluster_wallet_event_v416 = record_cluster_wallet_event


def record_cluster_wallet_event(
    *,
    label: str,
    wallet_address: str,
    mint: str,
    analysis: dict[str, Any],
    signature: str = "",
    source: str = "wallet_watch",
) -> None:
    _record_cluster_wallet_event_v416(
        label=label,
        wallet_address=wallet_address,
        mint=mint,
        analysis=analysis,
        signature=signature,
        source=source,
    )
    try:
        record_pattern_brain_event(
            mint=mint,
            label=label,
            wallet_address=wallet_address,
            analysis=analysis,
            signature=signature,
            source=source,
        )
    except Exception:
        # Pattern Brain is passive only. It must never break alerts or exits.
        return


_open_paper_copy_trade_v416 = open_paper_copy_trade


def open_paper_copy_trade(
    mint: str,
    label: str,
    wallet_address: str,
    signature: str,
    analysis: dict[str, Any],
    dex_info: dict[str, Any],
) -> str:
    message = _open_paper_copy_trade_v416(
        mint=mint,
        label=label,
        wallet_address=wallet_address,
        signature=signature,
        analysis=analysis,
        dex_info=dex_info,
    )
    try:
        record_pattern_brain_event(
            mint=mint,
            label=label,
            wallet_address=wallet_address,
            event_kind="PAPER_ENTRY",
            analysis=analysis,
            signature=signature,
            source="paper_copy_entry_v4_17",
            price_usd=_to_decimal(dex_info.get("price_usd")),
            liquidity_usd=_to_decimal(dex_info.get("liquidity_usd")),
            notes=analysis.get("paper_reason", ""),
        )
    except Exception:
        pass
    return message


_close_paper_copy_trade_v416 = close_paper_copy_trade


def close_paper_copy_trade(
    trade: dict[str, Any],
    reason: str,
    signature: str | None = None,
    dex_info: dict[str, Any] | None = None,
) -> str:
    mint = trade.get("mint") or ""
    if dex_info is None:
        dex_info = fetch_dex_token_info(mint) or {}

    entry_price = _to_decimal(trade.get("entry_price_usd"))
    exit_price = _to_decimal(dex_info.get("price_usd") or trade.get("last_price_usd"))
    remaining_pnl_pct = Decimal("0")
    if entry_price > 0:
        remaining_pnl_pct = ((exit_price - entry_price) / entry_price) * Decimal("100")
    tp1_done = bool(int(trade.get("tp1_done") or 0))
    tp1_closed_pct = _to_decimal(trade.get("tp1_closed_pct"))
    tp1_pnl_pct = _to_decimal(trade.get("tp1_pnl_pct"))
    effective_pnl_pct = remaining_pnl_pct
    if tp1_done and tp1_closed_pct > 0:
        closed_weight = tp1_closed_pct / Decimal("100")
        remaining_weight = Decimal("1") - closed_weight
        effective_pnl_pct = (tp1_pnl_pct * closed_weight) + (remaining_pnl_pct * remaining_weight)

    message = _close_paper_copy_trade_v416(trade=trade, reason=reason, signature=signature, dex_info=dex_info)
    try:
        record_pattern_brain_event(
            mint=mint,
            label=trade.get("entry_label") or "Paper Copy",
            wallet_address=trade.get("entry_wallet") or "",
            event_kind="PAPER_EXIT",
            analysis={"type": "Paper Copy Exit", "token_changes": []},
            signature=signature or trade.get("exit_signature") or "",
            source="paper_copy_exit_v4_17",
            price_usd=exit_price,
            liquidity_usd=_to_decimal(dex_info.get("liquidity_usd") or trade.get("last_liquidity_usd")),
            pnl_pct=effective_pnl_pct,
            exit_reason=reason,
        )
    except Exception:
        pass
    return message


def _danger_score_for_wallet(row: dict[str, Any]) -> int:
    events = int(row.get("events") or 0)
    in_count = int(row.get("in_count") or 0)
    out_count = int(row.get("out_count") or 0)
    sell_count = int(row.get("sell_count") or 0)
    gamq_count = int(row.get("gamq_count") or 0)
    label = str(row.get("label") or "")

    score = 0
    score += min(30, events * 3)
    score += min(25, in_count * 4)
    score += min(45, (out_count + sell_count) * 18)
    score += min(15, gamq_count * 8)
    if "G8R7" in label or "GAMq" in label:
        score += 10
    if out_count == 0 and sell_count == 0 and in_count > 0:
        score = min(score, 45)
    return max(0, min(99, score))
def build_exit_ranking_message() -> str:
    """V4.26 Exit Wallet Ranking - passive/read-only."""
    _ensure_pattern_brain_tables()

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                COALESCE(e.label, 'Unknown') AS label,
                COALESCE(e.wallet_address, '') AS wallet_address,
                COUNT(*) AS out_events,
                COUNT(DISTINCT e.mint) AS mints_seen,
                SUM(CASE WHEN CAST(m.final_pnl_pct AS REAL) < 0 THEN 1 ELSE 0 END) AS losing_mints,
                SUM(CASE WHEN CAST(m.final_pnl_pct AS REAL) <= -10 THEN 1 ELSE 0 END) AS bad_mints,
                AVG(CAST(m.final_pnl_pct AS REAL)) AS avg_final_pnl,
                MIN(CAST(m.final_pnl_pct AS REAL)) AS worst_final_pnl,
                MAX(CAST(m.final_pnl_pct AS REAL)) AS best_final_pnl
            FROM cluster_pattern_events e
            JOIN cluster_mint_memory m ON m.mint = e.mint
            WHERE e.event_kind IN ('DHT8_OUT','CLUSTER_OUT','CLUSTER_SELL','GAMQ_OUT','GAMQ_SELL')
              AND COALESCE(m.final_pnl_pct, '') <> ''
            GROUP BY e.wallet_address, e.label
            ORDER BY
                bad_mints DESC,
                losing_mints DESC,
                avg_final_pnl ASC,
                out_events DESC
            LIMIT 20
            """
        ).fetchall()

    lines = [
        "🏆 Exit Wallet Ranking V4.26",
        "",
        "Mode: Passive analysis only. No entry/exit decisions changed.",
        "Ranks wallets by closed mint results after OUT/SELL.",
        "",
    ]

    if not rows:
        lines.append("No enough closed OUT/SELL data yet.")
        return "\n".join(lines)

    for i, row in enumerate(rows, start=1):
        d = dict(row)

        out_events = int(d.get("out_events") or 0)
        losing_mints = int(d.get("losing_mints") or 0)
        bad_mints = int(d.get("bad_mints") or 0)

        avg_pnl = _to_decimal(d.get("avg_final_pnl"))
        worst_pnl = _to_decimal(d.get("worst_final_pnl"))
        best_pnl = _to_decimal(d.get("best_final_pnl"))

        danger_score = 0
        danger_score += min(35, bad_mints * 12)
        danger_score += min(25, losing_mints * 7)
        danger_score += min(20, out_events * 2)

        if avg_pnl < Decimal("0"):
            danger_score += min(20, abs(int(avg_pnl)))

        danger_score = max(0, min(99, danger_score))

        lines.extend([
            f"{i}) {d.get('label') or 'Unknown'} | Danger: {danger_score}/100",
            f"   Wallet: {_short(d.get('wallet_address'))}",
            f"   OUT/SELL events: {out_events} | Mints: {int(d.get('mints_seen') or 0)}",
            f"   Losing mints: {losing_mints} | Bad <= -10%: {bad_mints}",
            f"   Avg final PnL: {_fmt_decimal(avg_pnl, 2)}%",
            f"   Worst/Best: {_fmt_decimal(worst_pnl, 2)}% / {_fmt_decimal(best_pnl, 2)}%",
            "",
        ])

    lines.extend([
        "How to use:",
        "- High danger means this wallet's OUT/SELL often appears on bad closed mints.",
        "- For now this is analysis only, not an auto-exit rule.",
    ])

    return "\n".join(lines)
def _fmt_pattern_age(first_seen_at: str | None, event_at: str | None) -> str:
    if not first_seen_at or not event_at:
        return "-"
    try:
        start = datetime.fromisoformat(str(first_seen_at).replace("Z", "+00:00"))
        event = datetime.fromisoformat(str(event_at).replace("Z", "+00:00"))
        minutes = int((event - start).total_seconds() // 60)
        if minutes < 0:
            return "-"
        if minutes >= 60:
            return f"{minutes // 60}h {minutes % 60}m"
        return f"{minutes}m"
    except Exception:
        return "-"
def build_pattern_brain_message() -> str:
    _ensure_pattern_brain_tables()
    with get_conn() as conn:
        total_events = conn.execute("SELECT COUNT(*) AS c FROM cluster_pattern_events").fetchone()["c"]
        total_mints = conn.execute("SELECT COUNT(*) AS c FROM cluster_mint_memory").fetchone()["c"]
        wallet_rows = conn.execute(
            """
            SELECT
                COALESCE(label, 'Unknown') AS label,
                wallet_address,
                COUNT(*) AS events,
                SUM(CASE WHEN event_kind IN ('CLUSTER_IN','GAMQ_IN','DHT8_IN') THEN 1 ELSE 0 END) AS in_count,
                SUM(CASE WHEN event_kind IN ('CLUSTER_OUT','GAMQ_OUT','DHT8_OUT') THEN 1 ELSE 0 END) AS out_count,
                SUM(CASE WHEN event_kind IN ('CLUSTER_SELL','GAMQ_SELL') THEN 1 ELSE 0 END) AS sell_count,
                SUM(CASE WHEN event_kind LIKE 'GAMQ_%' THEN 1 ELSE 0 END) AS gamq_count,
                MAX(event_at) AS last_seen,
                MAX(mint) AS last_mint
            FROM cluster_pattern_events
            WHERE event_kind NOT IN ('PAPER_ENTRY','PAPER_EXIT')
            GROUP BY wallet_address, label
            ORDER BY (out_count + sell_count) DESC, events DESC, last_seen DESC
            LIMIT ?
            """,
            (PATTERN_BRAIN_MAX_WALLETS,),
        ).fetchall()
        mint_rows = conn.execute(
            """
            SELECT * FROM cluster_mint_memory
            ORDER BY last_event_at DESC
            LIMIT ?
            """,
            (PATTERN_BRAIN_MAX_RECENT_MINTS,),
        ).fetchall()

    lines = [
        "🧠 Cluster Pattern Brain V4.18",
        "",
        "Mode: Passive learning only. No entry/exit decisions changed.",
        f"Pattern events recorded: {total_events}",
        f"Mints tracked: {total_mints}",
        "",
        "Top wallet danger signals:",
    ]

    if wallet_rows:
        for row in wallet_rows:
            d = dict(row)
            score = _danger_score_for_wallet(d)
            lines.extend(
                [
                    f"• {d.get('label') or _short(d.get('wallet_address'))} | Score: {score}/100",
                    f"  Wallet: {_short(d.get('wallet_address'))}",
                    f"  Events: {d.get('events') or 0} | IN: {d.get('in_count') or 0} | OUT: {d.get('out_count') or 0} | SELL: {d.get('sell_count') or 0} | GAMq: {d.get('gamq_count') or 0}",
                    f"  Last mint: {_short(d.get('last_mint'))}",
                    "",
                ]
            )
    else:
        lines.append("No pattern events recorded yet.")
        lines.append("")

    lines.append("Recent mint timelines:")
    if mint_rows:
        for row in mint_rows:
            r = dict(row)
            final_pnl = r.get("final_pnl_pct") or ""
            pnl_text = f" | Final PnL: {Decimal(str(final_pnl)):.2f}%" if final_pnl not in {"", None} else ""
            lines.extend(
                [
                    f"• {_short(r.get('mint'))}",
                    f"  Full Mint: {r.get('mint')}",
                    f"  DHT8 IN: {'yes' if r.get('dht8_in_at') else 'no'} | DHT8 OUT: {'yes' if r.get('dht8_out_at') else 'no'} | GAMq: {r.get('gamq_event_count') or 0}",
                    f"  Cluster IN: {r.get('cluster_in_count') or 0} | Cluster OUT/SELL: {r.get('cluster_out_count') or 0}",
                    f"  Paper Entry: {r.get('paper_entry_count') or 0} | Paper Exit: {r.get('paper_exit_count') or 0}{pnl_text}",
                    f"  Last: {r.get('last_event_kind') or 'N/A'} / {r.get('last_event_label') or 'N/A'}",
                    f"  Timing: DHT8 IN {_fmt_pattern_age(r.get('first_seen_at'), r.get('dht8_in_at'))} | DHT8 OUT {_fmt_pattern_age(r.get('first_seen_at'), r.get('dht8_out_at'))} | First OUT {_fmt_pattern_age(r.get('first_seen_at'), r.get('first_cluster_out_at'))} | GAMq {_fmt_pattern_age(r.get('first_seen_at'), r.get('first_gamq_at'))} | Entry {_fmt_pattern_age(r.get('first_seen_at'), r.get('first_paper_entry_at'))} | Exit {_fmt_pattern_age(r.get('first_seen_at'), r.get('first_paper_exit_at'))}",
                    "",
                ]
            )
    else:
        lines.append("No mint timelines yet.")
        lines.append("")

    lines.extend(
        [
            "How to use:",
            "- High score OUT/SELL wallets are likely exit/risk wallets.",
            "- IN-only wallets are usually armed watch, not automatic exit.",
            "- V4.18 only observes. V4.18 can use these scores after enough data.",
        ]
    )
    return "\n".join(lines)
