from __future__ import annotations

from config import settings


def apply_initial_filters(token: dict) -> dict:
    if not token.get("enrichment_ok"):
        return {"passed": False, "reason": "No pair data"}
    if token.get("liquidity", 0) < settings.min_liquidity:
        return {"passed": False, "reason": "Low liquidity"}
    if token.get("volume_1h", 0) < settings.min_volume_1h:
        return {"passed": False, "reason": "Low volume"}
    txns = token.get("buys_1h", 0) + token.get("sells_1h", 0)
    if txns < settings.min_txns_1h:
        return {"passed": False, "reason": "Low transactions"}
    return {"passed": True, "reason": "Passed"}
