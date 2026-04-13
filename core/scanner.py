from __future__ import annotations

from datetime import datetime, timezone
from utils.http_client import HttpClient

DEX_BOOSTS_URL = "https://api.dexscreener.com/token-boosts/latest/v1"


def discover_tokens(http: HttpClient) -> list[dict]:
    payload = http.get_json(DEX_BOOSTS_URL) or []
    now_iso = datetime.now(timezone.utc).isoformat()
    discovered = []
    for item in payload:
        if item.get("chainId") != "solana":
            continue
        address = item.get("tokenAddress")
        if not address:
            continue
        discovered.append(
            {
                "address": address,
                "symbol": item.get("symbol") or "UNKNOWN",
                "name": item.get("description") or item.get("symbol") or "Unknown Token",
                "source": "dex_boosts",
                "discovered_at": now_iso,
            }
        )
    return discovered
