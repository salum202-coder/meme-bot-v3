from __future__ import annotations

from config import settings


def classify_signal(token: dict, safety: dict, scores: dict) -> dict:
    total = scores["total_score"]

    risk_level = safety.get("risk_level", "medium")
    red_flags = safety.get("red_flags", [])

    price_change_1h = float(token.get("price_change_1h") or 0)
    liquidity = float(token.get("liquidity") or 0)
    volume_1h = float(token.get("volume_1h") or 0)
    buys_1h = int(token.get("buys_1h") or 0)
    sells_1h = int(token.get("sells_1h") or 0)

    total_txns = buys_1h + sells_1h
    buy_ratio = buys_1h / total_txns if total_txns > 0 else 0.0

    if "overheated price action" in red_flags:
        return {"signal": "IGNORE", "reason": "Overheated token"}

    if "critical contract risk" in red_flags:
        return {"signal": "IGNORE", "reason": "Critical contract risk"}

    if risk_level == "high" and total < settings.alert_score_threshold:
        return {"signal": "IGNORE", "reason": "High risk and weak score"}

    if price_change_1h <= -50:
        return {"signal": "IGNORE", "reason": "Heavy dump in 1h"}

    if price_change_1h >= 80:
        return {"signal": "IGNORE", "reason": "Overextended pump in 1h"}

    if liquidity < settings.min_liquidity:
        return {"signal": "IGNORE", "reason": "Low liquidity"}

    if volume_1h < settings.min_volume_1h:
        return {"signal": "IGNORE", "reason": "Low volume"}

    if total_txns < settings.min_txns_1h:
        return {"signal": "IGNORE", "reason": "Low transaction activity"}

    strong_entry_conditions = all(
        [
            total >= settings.entry_score_threshold,
            risk_level in ("low", "medium"),
            price_change_1h >= 5,
            price_change_1h <= 35,
            buy_ratio >= 0.52,
            buys_1h >= sells_1h,
        ]
    )

    if strong_entry_conditions:
        return {"signal": "ENTRY_CANDIDATE", "reason": "High score with healthy momentum"}

    if total >= settings.alert_score_threshold:
        return {"signal": "ALERT", "reason": "Strong watch"}

    if total >= settings.watch_score_threshold:
        return {"signal": "WATCH", "reason": "Watchlist candidate"}

    return {"signal": "IGNORE", "reason": "Below threshold"}