from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from core.wallet_watcher import WATCH_WALLETS
from storage.repository_wallet_watch import get_wallet_watch_states


def _short(value: str, left: int = 6, right: int = 6) -> str:
    if not value:
        return "N/A"
    if len(value) <= left + right:
        return value
    return f"{value[:left]}...{value[-right:]}"


async def cluster_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    context.application.bot_data["chat_id"] = chat_id
    context.application.bot_data["default_chat_id"] = chat_id

    states = get_wallet_watch_states()
    state_by_wallet = {item["wallet_address"]: item for item in states}

    lines = [
        "🕵️ Wallet Cluster Watch",
        "",
        f"Watched wallets: {len(WATCH_WALLETS)}",
        "Mode: Alerts only",
        "Auto entry: OFF",
        "",
    ]

    for label, wallet in WATCH_WALLETS.items():
        state = state_by_wallet.get(wallet)
        last_seen = state.get("last_seen_at") if state else "Not initialized yet"
        last_sig = state.get("last_signature") if state else None

        lines.extend(
            [
                f"• {label}",
                f"Wallet: {_short(wallet)}",
                f"Last seen: {last_seen or 'N/A'}",
                f"Last tx: {_short(last_sig) if last_sig else 'N/A'}",
                "",
            ]
        )

    await update.message.reply_text("\n".join(lines))
