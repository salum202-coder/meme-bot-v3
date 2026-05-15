from __future__ import annotations

from datetime import datetime, timezone
from utils.http_client import HttpClient
from utils.logger import setup_logger
from storage.repository_tokens import (
    get_discovered_token,
    save_discovered_token,
    save_snapshot,
)
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

    pair = max(
        sol_pairs,
        key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0),
        default=None,
    )

    if not pair:
        return None

    return float(pair.get("priceUsd") or 0)


def _save_token_snapshot(token: dict, total_score: float, signal: str) -> None:
    save_snapshot(
        {
            "address": token.get("address"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "price": token.get("price"),
            "liquidity": token.get("liquidity"),
            "volume_1h": token.get("volume_1h"),
            "buys_1h": token.get("buys_1h"),
            "sells_1h": token.get("sells_1h"),
            "market_cap": token.get("market_cap"),
            "total_score": total_score,
            "signal": signal,
        }
    )


async def run_scan_cycle(context):
    chat_id = context.bot_data.get("chat_id") or context.application.bot_data.get("default_chat_id")

    if not chat_id:
        logger.info("No chat id available yet; skipping notifications")

    tokens = discover_tokens(http)
    logger.info("Discovered %s tokens", len(tokens))

    for raw_token in tokens:
        existing = get_discovered_token(raw_token["address"])
        previous_signal = existing.get("last_signal") if existing else None

        token = enrich_token(http, raw_token)

        filter_result = apply_initial_filters(token)

        if not filter_result["passed"]:
            save_discovered_token(token, "IGNORE", 0)
            _save_token_snapshot(token, 0, "IGNORE")
            continue

        safety = evaluate_safety(token)
        scores = calculate_scores(token, safety)
        signal = classify_signal(token, safety, scores)

        current_signal = signal["signal"]
        total_score = scores["total_score"]

        save_discovered_token(token, current_signal, total_score)
        _save_token_snapshot(token, total_score, current_signal)

        should_send_alert = (
            chat_id
            and current_signal in {"WATCH", "ALERT", "ENTRY_CANDIDATE"}
            and current_signal != previous_signal
        )

        if should_send_alert:
            await context.bot.send_message(
                chat_id=chat_id,
                text=build_token_alert(token, safety, scores, signal),
                disable_web_page_preview=True,
            )

        position = maybe_open_paper_trade(token, signal)

        if chat_id and position:
            await context.bot.send_message(
                chat_id=chat_id,
                text=build_position_open_alert(position),
                disable_web_page_preview=True,
            )


async def run_position_cycle(context):
    chat_id = context.bot_data.get("chat_id") or context.application.bot_data.get("default_chat_id")

    if not chat_id:
        return

    evaluate_positions(
        fetch_price_func=fetch_token_price,
        notify_func=lambda text: context.application.create_task(
            context.bot.send_message(
                chat_id=chat_id,
                text=text,
                disable_web_page_preview=True,
            )
        ),
    )
