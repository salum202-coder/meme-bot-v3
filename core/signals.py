from __future__ import annotations

from config import settings


def classify_signal(token: dict, safety: dict, scores: dict) -> dict:
    total = float(scores.get("total_score", 0))

    risk_level = safety.get("risk_level", "medium")
    red_flags = safety.get("red_flags", [])

    price_change_1h = float(token.get("price_change_1h") or 0)
    liquidity = float(token.get("liquidity") or 0)
    volume_1h = float(token.get("volume_1h") or 0)
    buys_1h = int(token.get("buys_1h") or 0)
    sells_1h = int(token.get("sells_1h") or 0)

    total_txns = buys_1h + sells_1h
    buy_ratio = buys_1h / total_txns if total_txns > 0 else 0.0

    if not token.get("enrichment_ok"):
        return {"signal": "IGNORE", "reason": "No pair data"}

    # hard risk only
    if "critical contract risk" in red_flags:
        return {"signal": "IGNORE", "reason": "Critical contract risk"}

    if price_change_1h <= -60:
        return {"signal": "IGNORE", "reason": "Heavy dump"}

    if liquidity < 10_000:
        return {"signal": "IGNORE", "reason": "Very low liquidity"}

    if volume_1h < 3_000:
        return {"signal": "IGNORE", "reason": "Very low volume"}

    if total_txns < 15:
        return {"signal": "IGNORE", "reason": "Very low activity"}

    # ENTRY
    if (
        total >= 70
        and risk_level in ("low", "medium")
        and liquidity >= 50_000
        and volume_1h >= 40_000
        and buys_1h > sells_1h
        and 0 <= price_change_1h <= 60
    ):
        return {"signal": "ENTRY_CANDIDATE", "reason": "Strong score with healthy buy pressure"}

    # ALERT
    if (
        total >= 55
        and liquidity >= 30_000
        and volume_1h >= 20_000
        and buy_ratio >= 0.50
    ):
        return {"signal": "ALERT", "reason": "Good momentum candidate"}

    # WATCH
    if total >= 35:
        return {"signal": "WATCH", "reason": "Watchlist candidate"}

    return {"signal": "IGNORE", "reason": "Below threshold"}
