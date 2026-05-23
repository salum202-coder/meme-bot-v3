from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from utils.http_client import HttpClient

DEXSCREENER_TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens"


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _format_age(minutes: float | None) -> str:
    if minutes is None:
        return "N/A"

    if minutes < 60:
        return f"{int(minutes)}m"

    hours = int(minutes // 60)
    mins = int(minutes % 60)

    if hours < 24:
        return f"{hours}h {mins}m"

    days = hours // 24
    rem_hours = hours % 24
    return f"{days}d {rem_hours}h"


def _pair_age_minutes(pair_created_at: Any) -> float | None:
    if not pair_created_at:
        return None

    try:
        created_ms = int(pair_created_at)
        created_seconds = created_ms / 1000
        now_seconds = datetime.now(timezone.utc).timestamp()
        age_minutes = (now_seconds - created_seconds) / 60
        if age_minutes < 0:
            return None
        return age_minutes
    except Exception:
        return None


def _dex_id(pair: dict[str, Any] | None) -> str:
    if not pair:
        return "N/A"
    return str(pair.get("dexId") or "unknown")


def _is_raydium_pair(pair: dict[str, Any] | None) -> bool:
    dex_id = _dex_id(pair).lower()
    return "raydium" in dex_id


def _best_pair(pairs: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not pairs:
        return None

    return max(
        pairs,
        key=lambda p: _to_float((p.get("liquidity") or {}).get("usd")),
        default=None,
    )


def _best_raydium_pair(pairs: list[dict[str, Any]]) -> dict[str, Any] | None:
    raydium_pairs = [p for p in pairs if _is_raydium_pair(p)]
    return _best_pair(raydium_pairs)


def _age_class(age_minutes: float | None) -> str:
    if age_minutes is None:
        return "UNKNOWN"

    if age_minutes <= 60:
        return "VERY_EARLY"

    if age_minutes <= 180:
        return "EARLY"

    if age_minutes <= 360:
        return "FRESH"

    if age_minutes <= 720:
        return "MATURE"

    return "LATE"


def evaluate_raydium_intelligence(http: HttpClient, token: dict) -> dict:
    address = token.get("address")

    if not address:
        return {
            "raydium_quality": "UNKNOWN",
            "raydium_score": 0,
            "is_raydium": False,
            "dex_id": "N/A",
            "dex_status": "MISSING_ADDRESS",
            "pair_age_text": "N/A",
            "pair_age_minutes": None,
            "age_class": "UNKNOWN",
            "liquidity_usd": 0.0,
            "volume_h1": 0.0,
            "price_change_h1": 0.0,
            "buys_h1": 0,
            "sells_h1": 0,
            "buy_sell_ratio": 0.0,
            "volume_liquidity_ratio": 0.0,
            "pair_address": None,
            "url": "",
            "notes": ["Missing token address"],
        }

    payload = http.get_json(f"{DEXSCREENER_TOKEN_URL}/{address}") or {}
    pairs = payload.get("pairs") or []
    sol_pairs = [p for p in pairs if p.get("chainId") == "solana"]

    if not sol_pairs:
        return {
            "raydium_quality": "NO_PAIR",
            "raydium_score": 0,
            "is_raydium": False,
            "dex_id": "N/A",
            "dex_status": "NO_SOLANA_PAIR",
            "pair_age_text": "N/A",
            "pair_age_minutes": None,
            "age_class": "UNKNOWN",
            "liquidity_usd": 0.0,
            "volume_h1": 0.0,
            "price_change_h1": 0.0,
            "buys_h1": 0,
            "sells_h1": 0,
            "buy_sell_ratio": 0.0,
            "volume_liquidity_ratio": 0.0,
            "pair_address": None,
            "url": f"https://dexscreener.com/solana/{address}",
            "notes": ["No Solana pair found on DexScreener"],
        }

    raydium_pair = _best_raydium_pair(sol_pairs)
    selected_pair = raydium_pair or _best_pair(sol_pairs)
    is_raydium = _is_raydium_pair(selected_pair)
    dex_id = _dex_id(selected_pair)

    liquidity = selected_pair.get("liquidity") or {}
    volume = selected_pair.get("volume") or {}
    price_change = selected_pair.get("priceChange") or {}
    txns = selected_pair.get("txns") or {}
    txns_h1 = txns.get("h1") or {}

    liquidity_usd = _to_float(liquidity.get("usd"))
    volume_h1 = _to_float(volume.get("h1"))
    price_change_h1 = _to_float(price_change.get("h1"))
    buys_h1 = _to_int(txns_h1.get("buys"))
    sells_h1 = _to_int(txns_h1.get("sells"))

    buy_sell_ratio = 0.0
    if sells_h1 > 0:
        buy_sell_ratio = buys_h1 / sells_h1
    elif buys_h1 > 0:
        buy_sell_ratio = float(buys_h1)

    volume_liquidity_ratio = 0.0
    if liquidity_usd > 0:
        volume_liquidity_ratio = volume_h1 / liquidity_usd

    age_minutes = _pair_age_minutes(selected_pair.get("pairCreatedAt"))
    age_text = _format_age(age_minutes)
    age_class = _age_class(age_minutes)

    notes: list[str] = []
    score = 0

    if is_raydium:
        score += 25
        notes.append("Raydium pair detected")
    else:
        notes.append(f"Best pair is on {dex_id}, not Raydium")

    if liquidity_usd >= 100_000:
        score += 25
    elif liquidity_usd >= 30_000:
        score += 20
    elif liquidity_usd >= 10_000:
        score += 10
    elif liquidity_usd < 5_000:
        notes.append("Liquidity is very low")

    if age_minutes is not None:
        if age_minutes <= 180:
            score += 20
        elif age_minutes <= 360:
            score += 15
        elif age_minutes <= 720:
            score += 8
        else:
            notes.append("Pair is old; likely late entry")
    else:
        notes.append("Pair age unavailable")

    if 1.0 <= volume_liquidity_ratio <= 5.0:
        score += 15
    elif 0.5 <= volume_liquidity_ratio < 1.0:
        score += 8
    elif volume_liquidity_ratio > 10:
        notes.append("Volume/liquidity ratio is extremely high; possible churn")

    if buy_sell_ratio >= 1.5:
        score += 15
    elif buy_sell_ratio >= 1.1:
        score += 10
    elif sells_h1 > buys_h1:
        notes.append("Sells are higher than buys")

    if price_change_h1 >= 0:
        score += 10
    elif price_change_h1 > -20:
        score += 5
    elif price_change_h1 <= -40:
        notes.append("1H price change is deeply negative")

    danger = False

    if liquidity_usd < 5_000:
        danger = True

    if price_change_h1 <= -40:
        danger = True

    if sells_h1 >= 30 and buys_h1 > 0 and sells_h1 > buys_h1 * 2:
        danger = True
        notes.append("Strong sell pressure detected")

    if volume_liquidity_ratio > 10 and liquidity_usd < 30_000:
        danger = True

    if danger:
        quality = "DANGER"
    elif not is_raydium:
        quality = "OTHER_DEX"
    elif score >= 75:
        quality = "GOOD"
    elif score >= 55:
        quality = "WATCH"
    elif age_minutes is not None and age_minutes > 720:
        quality = "LATE"
    else:
        quality = "WEAK"

    if not notes:
        notes.append("Raydium checks completed")

    return {
        "raydium_quality": quality,
        "raydium_score": score,
        "is_raydium": is_raydium,
        "dex_id": dex_id,
        "dex_status": "RAYDIUM" if is_raydium else "OTHER_DEX",
        "pair_age_text": age_text,
        "pair_age_minutes": age_minutes,
        "age_class": age_class,
        "liquidity_usd": liquidity_usd,
        "volume_h1": volume_h1,
        "price_change_h1": price_change_h1,
        "buys_h1": buys_h1,
        "sells_h1": sells_h1,
        "buy_sell_ratio": buy_sell_ratio,
        "volume_liquidity_ratio": volume_liquidity_ratio,
        "pair_address": selected_pair.get("pairAddress"),
        "url": selected_pair.get("url") or f"https://dexscreener.com/solana/{address}",
        "notes": notes,
    }
