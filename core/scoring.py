from __future__ import annotations


def calculate_scores(token: dict, safety: dict) -> dict:
    momentum = 0
    structure = 0
    hype = 0

    volume_1h = float(token.get("volume_1h", 0) or 0)
    buys = int(token.get("buys_1h", 0) or 0)
    sells = int(token.get("sells_1h", 0) or 0)
    price_change = float(token.get("price_change_1h", 0) or 0)
    liquidity = float(token.get("liquidity", 0) or 0)
    market_cap = float(token.get("market_cap", 0) or 0)

    total_txns = buys + sells
    buy_ratio = buys / total_txns if total_txns > 0 else 0
    volume_per_txn = volume_1h / total_txns if total_txns > 0 else 0

    # ======================
    # 🔥 MOMENTUM
    # ======================
    if volume_1h >= 250_000:
        momentum += 10
    elif volume_1h >= 120_000:
        momentum += 7
    elif volume_1h >= 60_000:
        momentum += 4
    elif volume_1h >= 20_000:
        momentum += 2

    if buy_ratio >= 0.60:
        momentum += 10
    elif buy_ratio >= 0.55:
        momentum += 7
    elif buy_ratio >= 0.50:
        momentum += 4

    if 5 <= price_change <= 25:
        momentum += 10
    elif 2 <= price_change < 5:
        momentum += 5
    elif 25 < price_change <= 60:
        momentum += 3
    elif price_change > 100:
        momentum -= 6

    if volume_per_txn >= 300:
        momentum += 4
    elif volume_per_txn >= 150:
        momentum += 2

    volume_spike = (
        volume_1h >= 180_000
        and total_txns >= 300
        and volume_per_txn >= 200
    )

    strong_volume_spike = (
        volume_1h >= 300_000
        and total_txns >= 500
        and volume_per_txn >= 250
        and buy_ratio >= 0.55
    )

    if volume_spike:
        momentum += 4

    if strong_volume_spike:
        momentum += 6

    # ======================
    # 🧱 STRUCTURE
    # ======================
    if liquidity >= 100_000:
        structure += 12
    elif liquidity >= 80_000:
        structure += 10
    elif liquidity >= 40_000:
        structure += 6
    elif liquidity >= 15_000:
        structure += 3

    if market_cap > 0 and liquidity > 0:
        ratio = liquidity / market_cap
        if 0.03 <= ratio <= 0.30:
            structure += 8
        else:
            structure += 3

    if token.get("price", 0):
        structure += 3

    # ======================
    # 📣 HYPE
    # ======================
    if int(token.get("socials_count", 0) or 0) > 0:
        hype += 4

    if int(token.get("websites_count", 0) or 0) > 0:
        hype += 2

    if token.get("source") == "dex_boosts":
        hype += 2

    # ======================
    # 🛡️ SAFETY
    # ======================
    safety_score = float(safety.get("safety_score", 0) or 0)

    total = max(0, min(100, safety_score + momentum + structure + hype))

    # ======================
    # 🧪 DEBUG TEMP
    # ======================
    print("=" * 50)
    print("TOKEN DEBUG")
    print("symbol:", token.get("symbol"))
    print("enrichment_ok:", token.get("enrichment_ok"))
    print("liquidity:", liquidity)
    print("volume_1h:", volume_1h)
    print("buys:", buys)
    print("sells:", sells)
    print("total_txns:", total_txns)
    print("buy_ratio:", round(buy_ratio, 3))
    print("volume_per_txn:", round(volume_per_txn, 2))
    print("market_cap:", market_cap)
    print("price_change:", price_change)
    print("socials:", token.get("socials_count"))
    print("websites:", token.get("websites_count"))
    print("safety:", safety_score)
    print("momentum:", momentum)
    print("structure:", structure)
    print("hype:", hype)
    print("TOTAL SCORE:", total)
    print("=" * 50)

    return {
        "total_score": total,
        "safety_score": safety_score,
        "momentum_score": max(0, min(momentum, 30)),
        "structure_score": max(0, min(structure, 20)),
        "hype_score": max(0, min(hype, 10)),
    }
