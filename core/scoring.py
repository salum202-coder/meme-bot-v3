from __future__ import annotations


def calculate_scores(token: dict, safety: dict) -> dict:
    momentum = 0
    structure = 0
    hype = 0

    volume_1h = token.get("volume_1h", 0)
    if volume_1h >= 250_000:
        momentum += 12
    elif volume_1h >= 100_000:
        momentum += 8
    elif volume_1h >= 50_000:
        momentum += 5

    buys = token.get("buys_1h", 0)
    sells = token.get("sells_1h", 0)
    if buys > sells:
        momentum += 8
    elif buys == sells and buys > 0:
        momentum += 4

    price_change = token.get("price_change_1h", 0)
    if 5 <= price_change <= 80:
        momentum += 10
    elif 0 < price_change < 5:
        momentum += 5
    elif price_change > 120:
        momentum -= 5

    liquidity = token.get("liquidity", 0)
    market_cap = token.get("market_cap", 0)
    if liquidity >= 50_000:
        structure += 8
    elif liquidity >= 20_000:
        structure += 5

    if market_cap > 0 and liquidity > 0:
        ratio = liquidity / market_cap if market_cap else 0
        if 0.02 <= ratio <= 0.35:
            structure += 8
        else:
            structure += 3

    if token.get("price", 0) > 0:
        structure += 4

    if token.get("socials_count", 0) > 0:
        hype += 5
    if token.get("websites_count", 0) > 0:
        hype += 3
    if token.get("source") == "dex_boosts":
        hype += 2

    safety_score = safety["safety_score"]
    total = max(0, min(100, safety_score + momentum + structure + hype))
    return {
        "total_score": total,
        "safety_score": safety_score,
        "momentum_score": max(0, min(momentum, 30)),
        "structure_score": max(0, min(structure, 20)),
        "hype_score": max(0, min(hype, 10)),
    }
