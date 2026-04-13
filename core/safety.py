from __future__ import annotations


def evaluate_safety(token: dict) -> dict:
    score = 0
    red_flags: list[str] = []
    green_flags: list[str] = []

    liquidity = token.get("liquidity", 0)
    if liquidity >= 100_000:
        score += 15
        green_flags.append("strong liquidity")
    elif liquidity >= 50_000:
        score += 10
        green_flags.append("acceptable liquidity")
    else:
        red_flags.append("borderline liquidity")

    if token.get("websites_count", 0) > 0:
        score += 8
        green_flags.append("website present")
    else:
        red_flags.append("no website")

    if token.get("socials_count", 0) > 0:
        score += 8
        green_flags.append("socials present")
    else:
        red_flags.append("no socials")

    if token.get("market_cap", 0) > 0:
        score += 5
    else:
        red_flags.append("no market cap data")

    price_change = abs(token.get("price_change_1h", 0))
    if price_change > 150:
        red_flags.append("overheated price action")
    else:
        score += 4

    risk_level = "high"
    if score >= 26:
        risk_level = "low"
    elif score >= 16:
        risk_level = "medium"

    return {
        "safety_score": min(score, 40),
        "risk_level": risk_level,
        "red_flags": red_flags,
        "green_flags": green_flags,
    }
