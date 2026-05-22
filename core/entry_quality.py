from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


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


def get_token_age_minutes(pair_created_at: Any) -> int | None:
    if not pair_created_at:
        return None

    try:
        timestamp = float(pair_created_at)

        # DexScreener usually returns milliseconds.
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000

        created_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        now = datetime.now(timezone.utc)

        age_seconds = max(0, int((now - created_at).total_seconds()))
        return age_seconds // 60

    except Exception:
        return None


def format_token_age(pair_created_at: Any) -> str:
    age_minutes = get_token_age_minutes(pair_created_at)

    if age_minutes is None:
        return "N/A"

    if age_minutes < 1:
        return "<1m"

    if age_minutes < 60:
        return f"{age_minutes}m"

    age_hours = age_minutes // 60
    remaining_minutes = age_minutes % 60

    if age_hours < 24:
        return f"{age_hours}h {remaining_minutes}m"

    age_days = age_hours // 24
    remaining_hours = age_hours % 24

    return f"{age_days}d {remaining_hours}h"


def classify_age(age_minutes: int | None) -> str:
    if age_minutes is None:
        return "UNKNOWN"

    if age_minutes < 5:
        return "TOO_NEW"

    if age_minutes <= 180:
        return "EARLY"

    if age_minutes <= 360:
        return "FRESH"

    if age_minutes <= 1440:
        return "MATURE"

    return "LATE"


def calculate_entry_quality(token: dict, safety: dict, scores: dict, signal: dict) -> dict:
    signal_name = signal.get("signal", "UNKNOWN")
    total_score = _to_float(scores.get("total_score"))

    risk = str(safety.get("risk_level", "unknown")).lower()

    age_minutes = get_token_age_minutes(token.get("pair_created_at"))
    age_text = format_token_age(token.get("pair_created_at"))
    age_class = classify_age(age_minutes)

    liquidity = _to_float(token.get("liquidity"))
    volume_1h = _to_float(token.get("volume_1h"))
    price_change_1h = _to_float(token.get("price_change_1h"))
    buys_1h = _to_int(token.get("buys_1h"))
    sells_1h = _to_int(token.get("sells_1h"))

    buy_sell_ratio = 0.0
    if sells_1h > 0:
        buy_sell_ratio = buys_1h / sells_1h
    elif buys_1h > 0:
        buy_sell_ratio = 99.0

    volume_liquidity_ratio = 0.0
    if liquidity > 0:
        volume_liquidity_ratio = volume_1h / liquidity

    reasons: list[str] = []

    if signal_name != "ENTRY_CANDIDATE":
        return {
            "quality": "NO_ENTRY_SIGNAL",
            "can_paper_trade": False,
            "age_minutes": age_minutes,
            "age_text": age_text,
            "age_class": age_class,
            "buy_sell_ratio": buy_sell_ratio,
            "volume_liquidity_ratio": volume_liquidity_ratio,
            "reasons": ["Signal is not ENTRY_CANDIDATE"],
        }

    if age_minutes is None:
        return {
            "quality": "UNKNOWN_AGE",
            "can_paper_trade": False,
            "age_minutes": age_minutes,
            "age_text": age_text,
            "age_class": age_class,
            "buy_sell_ratio": buy_sell_ratio,
            "volume_liquidity_ratio": volume_liquidity_ratio,
            "reasons": ["Token age is unknown"],
        }

    if age_minutes < 5:
        return {
            "quality": "TOO_NEW / HIGH RISK",
            "can_paper_trade": False,
            "age_minutes": age_minutes,
            "age_text": age_text,
            "age_class": age_class,
            "buy_sell_ratio": buy_sell_ratio,
            "volume_liquidity_ratio": volume_liquidity_ratio,
            "reasons": ["Token is too new; wait for liquidity and trading to stabilize"],
        }

    if age_minutes > 360:
        return {
            "quality": "LATE / WATCH ONLY",
            "can_paper_trade": False,
            "age_minutes": age_minutes,
            "age_text": age_text,
            "age_class": age_class,
            "buy_sell_ratio": buy_sell_ratio,
            "volume_liquidity_ratio": volume_liquidity_ratio,
            "reasons": ["Token is older than 6 hours; likely not an early entry"],
        }

    # ELITE conditions:
    # We want fresh tokens with strong score, healthy liquidity, strong volume,
    # buy pressure, and controlled price movement.
    elite_checks = {
        "score": total_score >= 90,
        "risk": risk == "low",
        "age": 5 <= age_minutes <= 180,
        "liquidity": liquidity >= 50_000,
        "volume": volume_1h >= max(50_000, liquidity * 0.75),
        "buy_pressure": buys_1h >= max(50, sells_1h * 1.15),
        "price_change": 5 <= price_change_1h <= 80,
    }

    if all(elite_checks.values()):
        return {
            "quality": "ELITE",
            "can_paper_trade": True,
            "age_minutes": age_minutes,
            "age_text": age_text,
            "age_class": age_class,
            "buy_sell_ratio": buy_sell_ratio,
            "volume_liquidity_ratio": volume_liquidity_ratio,
            "reasons": [
                "Fresh token with strong score, healthy liquidity, strong volume, and buy pressure"
            ],
        }

    # Strong but not perfect. Good for manual watch, not auto paper entry.
    strong_checks = {
        "score": total_score >= 85,
        "risk": risk in {"low", "medium-low"},
        "age": 5 <= age_minutes <= 360,
        "liquidity": liquidity >= 40_000,
        "volume": volume_1h >= 40_000,
        "buy_pressure": buys_1h > sells_1h,
        "price_change": 0 <= price_change_1h <= 120,
    }

    if all(strong_checks.values()):
        missing = [name for name, ok in elite_checks.items() if not ok]
        if missing:
            reasons.append(f"Not ELITE because: {', '.join(missing)}")

        return {
            "quality": "STRONG WATCH",
            "can_paper_trade": False,
            "age_minutes": age_minutes,
            "age_text": age_text,
            "age_class": age_class,
            "buy_sell_ratio": buy_sell_ratio,
            "volume_liquidity_ratio": volume_liquidity_ratio,
            "reasons": reasons or ["Strong token, but not enough for auto entry"],
        }

    missing = [name for name, ok in strong_checks.items() if not ok]

    return {
        "quality": "AVOID / WEAK SETUP",
        "can_paper_trade": False,
        "age_minutes": age_minutes,
        "age_text": age_text,
        "age_class": age_class,
        "buy_sell_ratio": buy_sell_ratio,
        "volume_liquidity_ratio": volume_liquidity_ratio,
        "reasons": [f"Weak setup because: {', '.join(missing)}"] if missing else ["Weak setup"],
    }
