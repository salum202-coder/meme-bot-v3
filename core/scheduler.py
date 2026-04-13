from __future__ import annotations

from datetime import datetime, timezone
from utils.http_client import HttpClient
from utils.logger import setup_logger
from storage.repository_tokens import token_exists, save_discovered_token, save_snapshot
from core.scanner import discover_tokens
from core.enricher import enrich_token
from core.filters import apply_initial_filters
from core.safety import evaluate_safety
from core.scoring import calculate_scores
from core.signals import classify_signal
from core.notifier import build_token_alert, build_position_open_alert
from core.paper_trader import maybe_open_paper_trade
from core.position_manager import evaluate_positions

logger = setup_logger("scheduler")
http = HttpClient()


def fetch_token_price(address: str) -> float | None:
    payload = http.get_json(f"https://api.dexscreener.com/latest/dex/tokens/{address}") or {}
    pairs = payload.get("pairs") or []
    sol_pairs = [p for p in pairs if p.get("chainId") == "solana"]
    if not sol_pairs:
        return None
    pair = max(sol_pairs, key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0), default=None)
    if not pair:
        return None
    return float(pair.get("priceUsd") or 0)


async def run_scan_cycle(context):
    chat_id = context.bot_data.get("chat_id") or context.application.bot_data.get("default_chat_id")
    if not chat_id:
        logger.info("No chat id available yet; skipping notifications")
    tokens = discover_tokens(http)
    logger.info("Discovered %s tokens", len(tokens))
    for raw_token in tokens:
        if token_exists(raw_token["address"]):
            continue

        token = enrich_token(http, raw_token)
        filter_result = apply_initial_filters(token)
        if not filter_result["passed"]:
            save_discovered_token(token, "IGNORE", 0)
            continue

        safety = evaluate_safety(token)
        scores = calculate_scores(token, safety)
        signal = classify_signal(token, safety, scores)

        save_discovered_token(token, signal["signal"], scores["total_score"])
        save_snapshot(
            {
                "address": token["address"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "price": token.get("price"),
                "liquidity": token.get("liquidity"),
                "volume_1h": token.get("volume_1h"),
                "buys_1h": token.get("buys_1h"),
                "sells_1h": token.get("sells_1h"),
                "market_cap": token.get("market_cap"),
                "total_score": scores["total_score"],
                "signal": signal["signal"],
            }
        )

        if chat_id and signal["signal"] in {"WATCH", "ALERT", "ENTRY_CANDIDATE"}:
            await context.bot.send_message(chat_id=chat_id, text=build_token_alert(token, safety, scores, signal))

        position = maybe_open_paper_trade(token, signal)
        if chat_id and position:
            await context.bot.send_message(chat_id=chat_id, text=build_position_open_alert(position))


async def run_position_cycle(context):
    chat_id = context.bot_data.get("chat_id") or context.application.bot_data.get("default_chat_id")
    if not chat_id:
        return
    evaluate_positions(
        fetch_price_func=fetch_token_price,
        notify_func=lambda text: context.application.create_task(context.bot.send_message(chat_id=chat_id, text=text)),
    )
