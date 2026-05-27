from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from core.wallet_watcher import (
    WATCH_WALLETS,
    analyze_transaction,
    fetch_wallet_signatures,
    maybe_close_paper_copy_from_digest_event,
    maybe_handle_digest_paper_sync,
    _fmt_decimal,
    _format_time,
    _is_success,
    _short,
    _token_label,
)


LOOKBACK_MINUTES = 30
MAX_TXS_TO_FETCH_PER_WALLET = 20
MAX_IMPORTANT_LINES_PER_MESSAGE = 8

NOISE_TYPES = {
    "Trade order / no visible fill",
    "Unknown",
    "General Wallet Activity",
}


def _digest_token_summary(token_changes: list[dict[str, Any]]) -> str:
    if not token_changes:
        return "Token: N/A"

    item = token_changes[0]
    mint = item.get("mint")
    delta = item.get("delta", Decimal("0"))
    sign = "+" if delta > 0 else ""

    return f"Token: {_token_label(mint)} {sign}{_fmt_decimal(delta, 4)}"


def _is_important_analysis(analysis: dict[str, Any]) -> bool:
    if analysis.get("notify"):
        return True

    analysis_type = analysis.get("type", "")
    if "BUY" in analysis_type:
        return True
    if "SELL" in analysis_type:
        return True
    if "Distribution" in analysis_type:
        return True
    if "Transfer OUT" in analysis_type and "ignored" not in analysis_type:
        return True
    if "Transfer IN" in analysis_type and "ignored" not in analysis_type:
        return True

    return False


def _important_line(
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
    token_family = analysis.get("token_family")

    lines = [
        f"{status} {label} | {_short(wallet_address)}",
        f"Time: {time_text}",
        f"Type: {analysis.get('type', 'Unknown')}",
        f"SOL: {sol_sign}{_fmt_decimal(sol_delta, 6)}",
    ]

    if token_family:
        lines.append(f"Family: {token_family}")

    lines.extend(
        [
            token_text,
            f"Tx: https://solscan.io/tx/{signature}",
        ]
    )

    return "\n".join(lines)


def _wallet_summary_line(
    label: str,
    wallet_address: str,
    total: int,
    type_counter: Counter,
    important_count: int,
) -> str:
    top_types = []
    for type_name, count in type_counter.most_common(4):
        top_types.append(f"{count} {type_name}")

    top_text = " | ".join(top_types) if top_types else "No classified activity"

    if important_count > 0:
        prefix = "🔥"
        note = f"{important_count} important"
    else:
        prefix = "⚪"
        note = "No BUY / SELL / Distribution detected"

    return (
        f"{prefix} {label} | {_short(wallet_address)}\n"
        f"Txs: {total} | {note}\n"
        f"Types: {top_text}"
    )


def collect_wallet_digest() -> tuple[list[str], list[str], list[str], int, list[str], list[str]]:
    now_ts = int(datetime.now(timezone.utc).timestamp())
    cutoff_ts = now_ts - (LOOKBACK_MINUTES * 60)

    wallet_summaries: list[str] = []
    important_lines: list[str] = []
    inactive_wallets: list[str] = []
    paper_exit_messages: list[str] = []
    paper_sync_messages: list[str] = []
    total_txs = 0

    for label, wallet_address in WATCH_WALLETS.items():
        signatures = fetch_wallet_signatures(wallet_address, limit=MAX_TXS_TO_FETCH_PER_WALLET)

        recent_txs = [
            tx for tx in signatures
            if tx.get("blockTime") and int(tx.get("blockTime")) >= cutoff_ts
        ]

        if not recent_txs:
            inactive_wallets.append(label)
            continue

        total_txs += len(recent_txs)

        type_counter: Counter = Counter()
        important_count = 0

        for tx in recent_txs:
            signature = tx.get("signature") or ""
            if not signature:
                continue

            analysis = analyze_transaction(signature, wallet_address)
            analysis_type = analysis.get("type", "Unknown")
            type_counter[analysis_type] += 1

            if _is_important_analysis(analysis):
                important_count += 1
                important_lines.append(_important_line(label, wallet_address, tx, analysis))

                # V4.13 Digest Entry/Exit Sync:
                # If the live watcher missed a fresh DHT8 IN because transaction
                # details were unavailable, the digest can still create the watch/entry.
                paper_sync_messages.extend(
                    maybe_handle_digest_paper_sync(
                        label=label,
                        wallet_address=wallet_address,
                        signature=signature,
                        block_time=tx.get("blockTime"),
                        analysis=analysis,
                    )
                )

                # V4.13 Digest Exit Sync:
                # If the digest successfully classifies a DHT8/cluster exit after the
                # main watcher initially saw it as Unknown, close the matching open
                # Paper Copy trade immediately from this digest pass.
                paper_exit_messages.extend(
                    maybe_close_paper_copy_from_digest_event(
                        label=label,
                        wallet_address=wallet_address,
                        tx=tx,
                        analysis=analysis,
                    )
                )

        wallet_summaries.append(
            _wallet_summary_line(
                label=label,
                wallet_address=wallet_address,
                total=len(recent_txs),
                type_counter=type_counter,
                important_count=important_count,
            )
        )

    return wallet_summaries, important_lines, inactive_wallets, total_txs, paper_exit_messages, paper_sync_messages


def build_wallet_digest_report(
    wallet_summaries: list[str],
    important_lines: list[str],
    inactive_wallets: list[str],
    total_txs: int,
    part_number: int = 1,
    total_parts: int = 1,
) -> str:
    lines = [
        "🧾 Wallet Cluster 30m Digest",
        "",
        f"Period: last {LOOKBACK_MINUTES} minutes",
        f"Watched wallets: {len(WATCH_WALLETS)}",
        f"Total txs found: {total_txs}",
    ]

    if total_parts > 1:
        lines.append(f"Part: {part_number}/{total_parts}")

    lines.append("")

    if important_lines:
        lines.append("🔥 Important activity:")
        lines.append("")
        lines.extend(important_lines)
        lines.append("")

    if wallet_summaries and part_number == 1:
        lines.append("Wallet summary:")
        lines.append("")
        lines.extend(wallet_summaries)
    elif not important_lines and not wallet_summaries:
        lines.append("No wallet activity found in this period.")

    if inactive_wallets and part_number == 1:
        lines.extend(
            [
                "",
                f"No activity: {len(inactive_wallets)} wallets",
                ", ".join(inactive_wallets[:12]) + ("..." if len(inactive_wallets) > 12 else ""),
            ]
        )

    lines.extend(
        [
            "",
            "Action: Digest only. No auto entry.",
        ]
    )

    return "\n\n".join(lines)


async def send_wallet_digest(context) -> None:
    chat_id = (
        context.application.bot_data.get("chat_id")
        or context.application.bot_data.get("default_chat_id")
    )

    if not chat_id:
        return

    wallet_summaries, important_lines, inactive_wallets, total_txs, paper_exit_messages, paper_sync_messages = collect_wallet_digest()

    for paper_message in paper_exit_messages:
        await context.bot.send_message(
            chat_id=chat_id,
            text=paper_message,
            disable_web_page_preview=True,
        )

    if not important_lines:
        await context.bot.send_message(
            chat_id=chat_id,
            text=build_wallet_digest_report(
                wallet_summaries=wallet_summaries,
                important_lines=[],
                inactive_wallets=inactive_wallets,
                total_txs=total_txs,
            ),
            disable_web_page_preview=True,
        )
        for paper_message in paper_sync_messages:
            await context.bot.send_message(
                chat_id=chat_id,
                text=paper_message,
                disable_web_page_preview=True,
            )
        return

    chunks = [
        important_lines[index:index + MAX_IMPORTANT_LINES_PER_MESSAGE]
        for index in range(0, len(important_lines), MAX_IMPORTANT_LINES_PER_MESSAGE)
    ]

    total_parts = len(chunks)

    for index, chunk in enumerate(chunks, start=1):
        await context.bot.send_message(
            chat_id=chat_id,
            text=build_wallet_digest_report(
                wallet_summaries=wallet_summaries if index == 1 else [],
                important_lines=chunk,
                inactive_wallets=inactive_wallets if index == 1 else [],
                total_txs=total_txs,
                part_number=index,
                total_parts=total_parts,
            ),
            disable_web_page_preview=True,
        )

    for paper_message in paper_sync_messages:
        await context.bot.send_message(
            chat_id=chat_id,
            text=paper_message,
            disable_web_page_preview=True,
        )


async def run_wallet_digest_cycle(context) -> None:
    await send_wallet_digest(context)
