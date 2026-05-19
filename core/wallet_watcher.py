from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
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

TOKEN_ALIASES: dict[str, str] = {
    "D6uqF8hPTP62yN3M2NhJUn8NPR9zTcyQS5pFE2QKfXnm": "SpaceX",
}

MIN_SOL_DELTA_TO_ALERT = Decimal("0.05")


def _short(value: str | None, left: int = 6, right: int = 6) -> str:
    if not value:
        return "N/A"
    if len(value) <= left + right:
        return value
    return f"{value[:left]}...{value[-right:]}"


def _token_label(mint: str | None) -> str:
    if not mint:
        return "N/A"

    name = TOKEN_ALIASES.get(mint)
    if name:
        return f"{name} ({_short(mint)})"

    return _short(mint)


def _format_time(block_time: int | None) -> str:
    if not block_time:
        return "N/A"
    return datetime.fromtimestamp(block_time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _fmt_decimal(value: Decimal, places: int = 6) -> str:
    try:
        return f"{float(value):,.{places}f}"
    except Exception:
        return str(value)


def fetch_wallet_signatures(wallet_address: str, limit: int = 10) -> list[dict[str, Any]]:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [
            wallet_address,
            {"limit": limit},
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


def _get_account_keys(details: dict[str, Any]) -> list[str]:
    message = ((details.get("transaction") or {}).get("message") or {})
    account_keys = message.get("accountKeys") or []

    keys: list[str] = []
    for item in account_keys:
        if isinstance(item, dict):
            pubkey = item.get("pubkey")
        else:
            pubkey = str(item)

        if pubkey:
            keys.append(pubkey)

    return keys


def _sol_delta_for_wallet(details: dict[str, Any], wallet_address: str) -> Decimal:
    meta = details.get("meta") or {}
    pre_balances = meta.get("preBalances") or []
    post_balances = meta.get("postBalances") or []
    account_keys = _get_account_keys(details)

    try:
        wallet_index = account_keys.index(wallet_address)
    except ValueError:
        return Decimal("0")

    if wallet_index >= len(pre_balances) or wallet_index >= len(post_balances):
        return Decimal("0")

    pre_lamports = Decimal(str(pre_balances[wallet_index]))
    post_lamports = Decimal(str(post_balances[wallet_index]))

    return (post_lamports - pre_lamports) / Decimal("1000000000")


def _token_amount_from_balance(item: dict[str, Any]) -> Decimal:
    ui_token_amount = item.get("uiTokenAmount") or {}
    raw_amount = ui_token_amount.get("amount")

    if raw_amount is None:
        ui_amount_string = ui_token_amount.get("uiAmountString")
        if ui_amount_string is None:
            return Decimal("0")
        return Decimal(str(ui_amount_string))

    decimals = int(ui_token_amount.get("decimals") or 0)
    return Decimal(str(raw_amount)) / (Decimal(10) ** decimals)


def _token_deltas_for_wallet(details: dict[str, Any], wallet_address: str) -> list[dict[str, Any]]:
    meta = details.get("meta") or {}
    pre_token_balances = meta.get("preTokenBalances") or []
    post_token_balances = meta.get("postTokenBalances") or []

    balances: dict[str, dict[str, Decimal]] = {}

    def add_side(items: list[dict[str, Any]], side: str) -> None:
        for item in items:
            owner = item.get("owner")
            mint = item.get("mint")

            if owner != wallet_address or not mint:
                continue

            if mint not in balances:
                balances[mint] = {"pre": Decimal("0"), "post": Decimal("0")}

            balances[mint][side] = _token_amount_from_balance(item)

    add_side(pre_token_balances, "pre")
    add_side(post_token_balances, "post")

    changes: list[dict[str, Any]] = []

    for mint, values in balances.items():
        pre = values["pre"]
        post = values["post"]
        delta = post - pre

        if delta == 0:
            continue

        changes.append(
            {
                "mint": mint,
                "pre": pre,
                "post": post,
                "delta": delta,
            }
        )

    changes.sort(key=lambda x: abs(x["delta"]), reverse=True)
    return changes


def _primary_token_mint(token_changes: list[dict[str, Any]]) -> str | None:
    if not token_changes:
        return None
    return token_changes[0].get("mint")


def analyze_transaction(signature: str, wallet_address: str) -> dict[str, Any]:
    details = fetch_transaction_details(signature)

    if not details:
        return {
            "emoji": "❔",
            "type": "Unknown",
            "confidence": "low",
            "hints": ["transaction details unavailable"],
            "sol_delta": Decimal("0"),
            "token_changes": [],
            "notify": False,
            "noise_reason": "No transaction details",
        }

    meta = details.get("meta") or {}
    err = meta.get("err")

    if err is not None:
        return {
            "emoji": "❌",
            "type": "Failed transaction",
            "confidence": "high",
            "hints": ["transaction failed"],
            "sol_delta": Decimal("0"),
            "token_changes": [],
            "notify": False,
            "noise_reason": "Failed transaction ignored",
        }

    logs = "\n".join(meta.get("logMessages") or [])
    raw_text = json.dumps(details, ensure_ascii=False).lower()
    logs_text = logs.lower()

    sol_delta = _sol_delta_for_wallet(details, wallet_address)
    token_changes = _token_deltas_for_wallet(details, wallet_address)

    positive_tokens = [x for x in token_changes if x["delta"] > 0]
    negative_tokens = [x for x in token_changes if x["delta"] < 0]

    hints: list[str] = []

    if "placemarketorder" in raw_text or "place market order" in raw_text:
        hints.append("PlaceMarketOrder")
        if "phoenix" in raw_text or "phoenix" in logs_text:
            hints.append("Phoenix")

    dex_keywords = [
        "jupiter",
        "raydium",
        "orca",
        "meteora",
        "pump",
        "swap",
        "route",
        "market",
        "phoenix",
    ]

    matched_dex = [word for word in dex_keywords if word in raw_text or word in logs_text]
    for word in matched_dex[:5]:
        if word not in hints:
            hints.append(word)

    trade_like = bool(hints)
    transfer_hits = raw_text.count('"transfer"') + logs_text.count("instruction: transfer")

    # BUY: wallet spends SOL and receives token.
    if positive_tokens and sol_delta < Decimal("-0.001"):
        return {
            "emoji": "🟢",
            "type": "Possible BUY",
            "confidence": "medium",
            "hints": hints or ["token received, SOL spent"],
            "sol_delta": sol_delta,
            "token_changes": token_changes,
            "notify": True,
            "noise_reason": "",
        }

    # SELL: wallet loses token and receives SOL.
    if negative_tokens and sol_delta > Decimal("0.001"):
        return {
            "emoji": "🔴",
            "type": "Possible SELL",
            "confidence": "medium",
            "hints": hints or ["token spent, SOL received"],
            "sol_delta": sol_delta,
            "token_changes": token_changes,
            "notify": True,
            "noise_reason": "",
        }

    # New V3 rule:
    # Token leaves watched wallet without clear SOL received.
    # This can mean distribution to other wallets before selling.
    if negative_tokens and abs(sol_delta) < Decimal("0.05"):
        return {
            "emoji": "🟠",
            "type": "Token Transfer OUT / Possible Distribution",
            "confidence": "medium-high",
            "hints": hints or [f"token balance decreased", f"transfer signals: {transfer_hits}"],
            "sol_delta": sol_delta,
            "token_changes": token_changes,
            "notify": True,
            "noise_reason": "",
        }

    # New V3 rule:
    # Token enters watched wallet without clear SOL spent.
    # Useful for catching receiving wallets in the cluster.
    if positive_tokens and abs(sol_delta) < Decimal("0.05"):
        return {
            "emoji": "📥",
            "type": "Token Transfer IN / Cluster Receive",
            "confidence": "medium",
            "hints": hints or [f"token balance increased", f"transfer signals: {transfer_hits}"],
            "sol_delta": sol_delta,
            "token_changes": token_changes,
            "notify": True,
            "noise_reason": "",
        }

    if trade_like and positive_tokens and negative_tokens:
        return {
            "emoji": "🚨",
            "type": "Possible TOKEN SWAP",
            "confidence": "medium",
            "hints": hints,
            "sol_delta": sol_delta,
            "token_changes": token_changes,
            "notify": True,
            "noise_reason": "",
        }

    if trade_like and not token_changes and abs(sol_delta) < Decimal("0.001"):
        return {
            "emoji": "⚪",
            "type": "Trade order / no visible fill",
            "confidence": "medium",
            "hints": hints,
            "sol_delta": sol_delta,
            "token_changes": token_changes,
            "notify": False,
            "noise_reason": "No token changes and only tiny SOL fee",
        }

    if trade_like and abs(sol_delta) >= MIN_SOL_DELTA_TO_ALERT:
        return {
            "emoji": "🚨",
            "type": "Possible Trade / Significant SOL Movement",
            "confidence": "medium",
            "hints": hints,
            "sol_delta": sol_delta,
            "token_changes": token_changes,
            "notify": True,
            "noise_reason": "",
        }

    if transfer_hits >= 5:
        return {
            "emoji": "💸",
            "type": "Possible Distribution / Many Transfers",
            "confidence": "medium",
            "hints": [f"transfer signals: {transfer_hits}"],
            "sol_delta": sol_delta,
            "token_changes": token_changes,
            "notify": True,
            "noise_reason": "",
        }

    if "associated token program" in raw_text or "createassociatedtokenaccount" in raw_text or "createidempotent" in raw_text:
        return {
            "emoji": "🧾",
            "type": "Create Token Account",
            "confidence": "medium",
            "hints": ["associated token account activity"],
            "sol_delta": sol_delta,
            "token_changes": token_changes,
            "notify": False,
            "noise_reason": "Token account creation ignored",
        }

    if transfer_hits > 0 and abs(sol_delta) >= MIN_SOL_DELTA_TO_ALERT:
        return {
            "emoji": "↔️",
            "type": "Large Transfer",
            "confidence": "medium",
            "hints": [f"transfer signals: {transfer_hits}"],
            "sol_delta": sol_delta,
            "token_changes": token_changes,
            "notify": True,
            "noise_reason": "",
        }

    return {
        "emoji": "👀",
        "type": "General Wallet Activity",
        "confidence": "low",
        "hints": ["no important pattern detected"],
        "sol_delta": sol_delta,
        "token_changes": token_changes,
        "notify": False,
        "noise_reason": "Low-signal wallet activity ignored",
    }


def _format_token_changes(token_changes: list[dict[str, Any]]) -> list[str]:
    if not token_changes:
        return ["Token changes: N/A"]

    lines = ["Token changes:"]
    for item in token_changes[:3]:
        mint = item["mint"]
        delta = item["delta"]
        pre = item["pre"]
        post = item["post"]
        sign = "+" if delta > 0 else ""

        lines.append(
            f"- {_token_label(mint)}: {sign}{_fmt_decimal(delta, 4)}"
        )
        lines.append(
            f"  Balance: {_fmt_decimal(pre, 4)} → {_fmt_decimal(post, 4)}"
        )

    return lines


def build_wallet_activity_summary(
    label: str,
    wallet_address: str,
    new_txs: list[dict[str, Any]],
    important_tx: dict[str, Any],
    analysis: dict[str, Any],
    ignored_count: int,
) -> str:
    total = len(new_txs)
    success_count = sum(1 for tx in new_txs if _is_success(tx))
    failed_count = total - success_count

    important_signature = important_tx.get("signature") or ""
    important_time = _format_time(important_tx.get("blockTime"))

    hints = analysis.get("hints") or []
    hints_text = ", ".join(hints[:5]) if hints else "N/A"

    sol_delta = analysis.get("sol_delta", Decimal("0"))
    sol_sign = "+" if sol_delta > 0 else ""

    token_changes = analysis.get("token_changes") or []
    primary_mint = _primary_token_mint(token_changes)

    lines = [
        f"{analysis['emoji']} Wallet Watch V3",
        "",
        f"Label: {label}",
        f"Wallet: {_short(wallet_address)}",
        f"Detected: {analysis['type']}",
        f"Confidence: {analysis['confidence']}",
        f"Hints: {hints_text}",
        f"SOL delta: {sol_sign}{_fmt_decimal(sol_delta, 6)} SOL",
        "",
    ]

    lines.extend(_format_token_changes(token_changes))

    if primary_mint:
        lines.extend(
            [
                "",
                "DexScreener:",
                f"https://dexscreener.com/solana/{primary_mint}",
            ]
        )

    lines.extend(
        [
            "",
            f"New txs checked: {total}",
            f"Ignored noise before alert: {ignored_count}",
            f"Success: {success_count}",
            f"Failed: {failed_count}",
            f"Important activity: {important_time}",
            "",
            "Important tx:",
            f"https://solscan.io/tx/{important_signature}",
            "",
            "Recent txs:",
        ]
    )

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

        important_analysis = None
        important_tx = None
        ignored_count = 0

        for tx in new_txs:
            signature = tx.get("signature") or ""
            if not signature:
                ignored_count += 1
                continue

            analysis = analyze_transaction(signature, wallet_address)

            if analysis.get("notify"):
                important_analysis = analysis
                important_tx = tx
                break

            ignored_count += 1

        if chat_id and important_analysis and important_tx:
            await context.bot.send_message(
                chat_id=chat_id,
                text=build_wallet_activity_summary(
                    label=label,
                    wallet_address=wallet_address,
                    new_txs=new_txs,
                    important_tx=important_tx,
                    analysis=important_analysis,
                    ignored_count=ignored_count,
                ),
                disable_web_page_preview=True,
            )

        save_wallet_signature(
            wallet_address=wallet_address,
            label=label,
            last_signature=latest_signature,
            last_seen_at=_format_time(latest_block_time),
        )
