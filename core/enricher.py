from __future__ import annotations

from utils.http_client import HttpClient


def enrich_token(http: HttpClient, token: dict) -> dict:
    address = token["address"]
    url = f"https://api.dexscreener.com/latest/dex/tokens/{address}"
    payload = http.get_json(url) or {}
    pairs = payload.get("pairs") or []

    sol_pairs = [p for p in pairs if p.get("chainId") == "solana"]
    pair = max(sol_pairs, key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0), default=None)
    if not pair:
        return {**token, "enrichment_ok": False}

    txns_h1 = (pair.get("txns") or {}).get("h1") or {}
    volume_h1 = (pair.get("volume") or {}).get("h1") or 0
    price_change_h1 = (pair.get("priceChange") or {}).get("h1") or 0
    socials = pair.get("info", {}).get("socials", []) or []
    websites = pair.get("info", {}).get("websites", []) or []

    return {
        **token,
        "enrichment_ok": True,
        "symbol": pair.get("baseToken", {}).get("symbol") or token.get("symbol"),
        "name": pair.get("baseToken", {}).get("name") or token.get("name"),
        "price": float(pair.get("priceUsd") or 0),
        "liquidity": float((pair.get("liquidity") or {}).get("usd") or 0),
        "volume_1h": float(volume_h1 or 0),
        "buys_1h": int(txns_h1.get("buys") or 0),
        "sells_1h": int(txns_h1.get("sells") or 0),
        "market_cap": float(pair.get("marketCap") or 0),
        "price_change_1h": float(price_change_h1 or 0),
        "pair_address": pair.get("pairAddress"),
        "pair_created_at": pair.get("pairCreatedAt"),
        "dex_url": pair.get("url") or f"https://dexscreener.com/solana/{address}",
        "websites_count": len(websites),
        "socials_count": len(socials),
    }
