from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import requests

from storage.repository_wallet_watch import (
    get_last_signature,
    save_wallet_signature,
)

SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"

WATCH_WALLETS: dict[str, str] = {
    "DHT8 Main": "DHT8LqMZ4UcbgfL2ttXoUUXSnhmV9gNBYJcCZpP3NNY8",
    "BJsbr Signer": "BJsbrDPdpxvzP35TYJ7gmrcumqxVSqwDeEb4Gg3aV4Ax",
    "Cluster 3oUE": "3oUEaNt7uL7pjZ6gdiAiEVRp9ZCcGRec7B5aSvXcjbWS",
    "Cluster Fnpc": "Fnpcmk5umHWXKfpjLcTSqVig7tg3aXgW2jF3f4kiGQRU",
    "Cluster 9ynT": "9ynTDJrA8EHqmSskLdooeptY7z4U4qrDUT1uQjEqKVJY",
    "Cluster EaE6": "EaE63hx1Fbw12kMUHPWGnG2dLThSxiz4MQJ7zPapz3Ws",
    "Cluster 1imt": "1imt7zeK3mE17dvdfztuEDhfoCUwnK8RVcjRzxnXLba",
    "Cluster AL3r": "AL3riiofreSvSCzoGgkpfLTa4QHe6SDK1NihXXrxZ21C",
    "Cluster Gjct": "GjctEPhWA9ArYKWqGznuhYMzjJKTJCWXbKpdvbYokdDt",
}


def _short(value: str | None, left: int = 6, right: int = 6) -> str:
    if not value:
        return "N/A"
    if len(value) <= left + right:
        return value
    return f"{value[:left]}...{value[-right:]}"


def _format_time(block_time: int | None) -> str:
    if not block_time:
        return "N/A"
    return datetime.fromtimestamp(block_time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def fetch_wallet_signatures(wallet_address: str, limit: int = 10) -> list[dict[str, Any]]:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [
            wallet_address,
            {
                "limit": limit,
            },
        ],
    }

    try:
        response = requests.post(SOLANA_RPC_URL, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    result = data.get("result")
    if not isinstance(result, list):
        return []

    return result


def fetch_transaction_details(signature: str) -> dict[str, Any] | None:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [
            signature,
            {
                "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 0,
            },
        ],
    }

    try:
        response = requests.post(SOLANA_RPC_URL, json=payload, timeout=12)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None

    result = data.get("result")
    if not isinstance(result, dict):
        return None

    return result


def _is_success(tx: dict[str, Any]) -> bool:
    return tx.get("err") is None


def classify_transaction(signature: str) -> dict[str, Any]:
    details = fetch_transaction_details(signature)

    if not details:
        return {
            "emoji": "❔",
            "type": "Unknown",
            "confidence": "low",
            "hints": ["transaction details unavailable"],
        }

    meta = details.get("meta") or {}
    err = meta.get("err")

    if err is not None:
        return {
            "emoji": "❌",
            "type": "Failed transaction",
            "confidence": "high",
            "hints": ["transaction failed"],
        }

    logs = "\n".join(meta.get("logMessages") or [])
    raw_text = json.dumps(details, ensure_ascii=False).lower()
    logs_text = logs.lower()

    hints: list[str] = []

    # Strong trade signals
    if "placemarketorder" in raw_text or "place market order" in raw_text:
        hints.append("PlaceMarketOrder")
        if "phoenix" in raw_text or "phoenix" in logs_text:
            hints.append("Phoenix")
        return {
            "emoji": "🚨",
            "type": "Possible Trade / Market Order",
            "confidence": "medium-high",
            "hints": hints,
        }

    # Common DEX / routing hints
    dex_keywords = [
        "jupiter",
        "raydium",
        "orca",
        "meteora",
        "pump",
        "swap",
        "route",
        "market",
    ]

    matched_dex = [word for word in dex_keywords if word in raw_text or word in logs_text]

    if matched_dex:
        return {
            "emoji": "🚨",
            "type": "Possible Swap / Trade",
            "confidence": "medium",
            "hints": matched_dex[:5],
        }

    # Distribution / many transfers
    transfer_hits = raw_text.count('"transfer"') + logs_text.count("instruction: transfer")
    if transfer_hits >= 5:
        return {
            "emoji": "💸",
            "type": "Possible Distribution / Many Transfers",
            "confidence": "medium",
            "hints": [f"transfer signals: {transfer_hits}"],
        }

    # Token account creation
    if "associated token program" in raw_text or "createassociatedtokenaccount" in raw_text or "createidempotent" in raw_text:
        return {
            "emoji": "🧾",
            "type": "Create Token Account",
            "confidence": "medium",
            "hints": ["associated token account activity"],
        }

    # Normal transfer
    if transfer_hits > 0:
        return {
            "emoji": "↔️",
            "type": "Transfer",
            "confidence": "medium",
            "hints": [f"transfer signals: {transfer_hits}"],
        }

    return {
        "emoji": "👀",
        "type": "General Wallet Activity",
        "confidence": "low",
        "hints": ["no clear trade/transfer pattern detected"],
    }


def build_wallet_activity_summary(
    label: str,
    wallet_address: str,
    new_txs: list[dict[str, Any]],
) -> str:
    total = len(new_txs)
    success_count = sum(1 for tx in new_txs if _is_success(tx))
    failed_count = total - success_count

    latest_tx = new_txs[0] if new_txs else {}
    latest_signature = latest_tx.get("signature") or ""
    latest_time = _format_time(latest_tx.get("blockTime"))

    classification = classify_transaction(latest_signature) if latest_signature else {
        "emoji": "❔",
        "type": "Unknown",
        "confidence": "low",
        "hints": [],
    }

    hints = classification.get("hints") or []
    hints_text = ", ".join(hints[:5]) if hints else "N/A"

    lines = [
        f"{classification['emoji']} Wallet Watch V2",
        "",
        f"Label: {label}",
        f"Wallet: {_short(wallet_address)}",
        f"Detected: {classification['type']}",
        f"Confidence: {classification['confidence']}",
        f"Hints: {hints_text}",
        "",
        f"New txs: {total}",
        f"Success: {success_count}",
        f"Failed: {failed_count}",
        f"Latest activity: {latest_time}",
        "",
        "Latest tx:",
        f"https://solscan.io/tx/{latest_signature}",
        "",
        "Recent txs:",
    ]

    for tx in new_txs[:3]:
        signature = tx.get("signature") or ""
        status = "✅" if _is_success(tx) else "❌"
        lines.append(f"{status} {_short(signature, 8, 8)}")

    lines.extend(
        [
            "",
            "Action: Review manually only. No auto entry.",
        ]
    )

    return "\n".join(lines)


async def run_wallet_watch_cycle(context) -> None:
    chat_id = (
        context.application.bot_data.get("chat_id")
        or context.application.bot_data.get("default_chat_id")
    )

    for label, wallet_address in WATCH_WALLETS.items():
        signatures = fetch_wallet_signatures(wallet_address, limit=10)

        if not signatures:
            continue

        latest_signature = signatures[0].get("signature")
        latest_block_time = signatures[0].get("blockTime")

        if not latest_signature:
            continue

        last_seen = get_last_signature(wallet_address)

        # First run: create baseline silently to avoid spam.
        if not last_seen:
            save_wallet_signature(
                wallet_address=wallet_address,
                label=label,
                last_signature=latest_signature,
                last_seen_at=_format_time(latest_block_time),
            )
            continue

        if latest_signature == last_seen:
            continue

        known_index = None

        for index, tx in enumerate(signatures):
            if tx.get("signature") == last_seen:
                known_index = index
                break

        if known_index is None:
            new_txs = [signatures[0]]
        else:
            new_txs = signatures[:known_index]

        new_txs = new_txs[:10]

        if chat_id and new_txs:
            await context.bot.send_message(
                chat_id=chat_id,
                text=build_wallet_activity_summary(label, wallet_address, new_txs),
                disable_web_page_preview=True,
            )

        save_wallet_signature(
            wallet_address=wallet_address,
            label=label,
            last_signature=latest_signature,
            last_seen_at=_format_time(latest_block_time),
        )
