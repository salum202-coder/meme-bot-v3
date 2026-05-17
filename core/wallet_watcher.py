from __future__ import annotations

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


def _short(value: str, left: int = 6, right: int = 6) -> str:
    if not value:
        return "N/A"
    if len(value) <= left + right:
        return value
    return f"{value[:left]}...{value[-right:]}"


def _format_time(block_time: int | None) -> str:
    if not block_time:
        return "N/A"
    return datetime.fromtimestamp(block_time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def fetch_wallet_signatures(wallet_address: str, limit: int = 5) -> list[dict[str, Any]]:
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


def build_wallet_activity_alert(label: str, wallet_address: str, tx: dict[str, Any]) -> str:
    signature = tx.get("signature") or ""
    err = tx.get("err")
    status = "Success" if err is None else "Failed"
    block_time = tx.get("blockTime")

    return (
        "👀 Cluster Activity Detected\n\n"
        f"Label: {label}\n"
        f"Wallet: {_short(wallet_address)}\n"
        f"Status: {status}\n"
        f"Time: {_format_time(block_time)}\n\n"
        f"Tx:\n{signature}\n\n"
        f"Solscan:\nhttps://solscan.io/tx/{signature}\n\n"
        "Action: Review manually only. No auto entry."
    )


async def run_wallet_watch_cycle(context) -> None:
    chat_id = (
        context.application.bot_data.get("chat_id")
        or context.application.bot_data.get("default_chat_id")
    )

    for label, wallet_address in WATCH_WALLETS.items():
        signatures = fetch_wallet_signatures(wallet_address, limit=5)

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

        new_txs: list[dict[str, Any]] = []
        known_index = None

        for index, tx in enumerate(signatures):
            if tx.get("signature") == last_seen:
                known_index = index
                break

        if known_index is None:
            # Last seen not found in the latest batch. Alert latest only to avoid flooding.
            new_txs = [signatures[0]]
        else:
            new_txs = signatures[:known_index]

        # Oldest to newest, max 3 alerts per wallet per cycle.
        new_txs = list(reversed(new_txs))[-3:]

        if chat_id:
            for tx in new_txs:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=build_wallet_activity_alert(label, wallet_address, tx),
                    disable_web_page_preview=True,
                )

        save_wallet_signature(
            wallet_address=wallet_address,
            label=label,
            last_signature=latest_signature,
            last_seen_at=_format_time(latest_block_time),
        )
