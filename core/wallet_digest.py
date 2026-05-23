from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from core.wallet_watcher import (
    WATCH_WALLETS,
    analyze_transaction,
    fetch_wallet_signatures,
    _fmt_decimal,
    _format_time,
    _is_success,
    _short,
    _token_label,
)


LOOKBACK_MINUTES = 30
MAX_TXS_PER_WALLET_IN_DIGEST = 3
MAX_LINES_PER_MESSAGE = 10


def _digest_token_summary(token_changes: list[dict[str, Any]]) -> str:
    if not token_changes:
        return "Token: N/A"

    item = token_changes[0]
    mint = item.get("mint")
    delta = item.get("delta", Decimal("0"))
    sign = "+" if delta > 0 else ""

    return f"Token: {_token_label(mint)} {sign}{_fmt_decimal(delta, 4)}"


def _digest_line(
    label: str,
    wallet_address: str,
    tx: dict[str, Any],
    analysis: dict[str, Any],
) -> str:
    signature = tx.get("signature") or ""
    time_text = _format_time(tx.get("blockTime")).replace(" UTC", "")

    sol_delta = analysis.get("sol_delta", Decimal("0"))
    sol_sign = "+" if sol_delta > 0 else ""

    token_changes = analysis.get("token_changes") or []
    token_text = _digest_token_summary(token_changes)

    status = "✅" if _is_success(tx) else "❌"

    return (
        f"{status} {label} | {_short(wallet_address)}\n"
        f"Time: {time_text}\n"
        f"Type: {analysis.get('type', 'Unknown')}\n"
        f"SOL: {sol_sign}{_fmt_decimal(sol_delta, 6)}\n"
        f"{token_text}\n"
        f"Tx: https://solscan.io/tx/{signature}"
    )


def build_wallet_digest_report(
    activity_lines: list[str],
    inactive_wallets: list[str],
    total_txs: int,
    part_number: int = 1,
    total_parts: int = 1,
) -> str:
    header = [
        "🧾 Wallet Cluster 30m Digest",
        "",
        f"Period: last {LOOKBACK_MINUTES} minutes",
        f"Watched wallets: {len(WATCH_WALLETS)}",
        f"Total txs found: {total_txs}",
    ]

    if total_parts > 1:
        header.append(f"Part: {part_number}/{total_parts}")

    header.append("")

    if activity_lines:
        header.append("Recent activity:")
        body = "\n\n".join(activity_lines)
    else:
        header.append("No wallet activity found in this period.")
        body = ""

    footer: list[str] = []
    if inactive_wallets and part_number == 1:
        footer.extend(
            [
                "",
                f"No activity: {len(inactive_wallets)} wallets",
                ", ".join(inactive_wallets[:12]) + ("..." if len(inactive_wallets) > 12 else ""),
            ]
        )

    footer.extend(["", "Action: Digest only. No auto entry."])

    pieces = ["\n".join(header)]
    if body:
        pieces.append(body)
    pieces.append("\n".join(footer))

    return "\n\n".join(pieces)


def collect_wallet_digest() -> tuple[list[str], list[str], int]:
    now_ts = int(datetime.now(timezone.utc).timestamp())
    cutoff_ts = now_ts - (LOOKBACK_MINUTES * 60)

    activity_lines: list[str] = []
    inactive_wallets: list[str] = []
    total_txs = 0

    for label, wallet_address in WATCH_WALLETS.items():
        signatures = fetch_wallet_signatures(wallet_address, limit=15)

        recent_txs = [
            tx for tx in signatures
            if tx.get("blockTime") and int(tx.get("blockTime")) >= cutoff_ts
        ]

        if not recent_txs:
            inactive_wallets.append(label)
            continue

        total_txs += len(recent_txs)

        for tx in recent_txs[:MAX_TXS_PER_WALLET_IN_DIGEST]:
            signature = tx.get("signature") or ""
            if not signature:
                continue

            analysis = analyze_transaction(signature, wallet_address)
            activity_lines.append(_digest_line(label, wallet_address, tx, analysis))

    return activity_lines, inactive_wallets, total_txs


async def send_wallet_digest(context) -> None:
    chat_id = (
        context.application.bot_data.get("chat_id")
        or context.application.bot_data.get("default_chat_id")
    )

    if not chat_id:
        return

    activity_lines, inactive_wallets, total_txs = collect_wallet_digest()

    if not activity_lines:
        await context.bot.send_message(
            chat_id=chat_id,
            text=build_wallet_digest_report([], inactive_wallets, total_txs),
            disable_web_page_preview=True,
        )
        return

    chunks = [
        activity_lines[index:index + MAX_LINES_PER_MESSAGE]
        for index in range(0, len(activity_lines), MAX_LINES_PER_MESSAGE)
    ]

    total_parts = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        await context.bot.send_message(
            chat_id=chat_id,
            text=build_wallet_digest_report(
                activity_lines=chunk,
                inactive_wallets=inactive_wallets if index == 1 else [],
                total_txs=total_txs,
                part_number=index,
                total_parts=total_parts,
            ),
            disable_web_page_preview=True,
        )


async def run_wallet_digest_cycle(context) -> None:
    await send_wallet_digest(context)
