from __future__ import annotations

from decimal import Decimal

from telegram import Update
from telegram.ext import ContextTypes

from core.wallet_watcher import (
    WATCH_WALLETS,
    build_copy_positions_message,
    build_copy_trades_message,
    build_copy_wallet_message,
    manual_close_paper_copy_trade,
    build_cluster_discovery_message,
)
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

    await update.message.reply_text("\n".join(lines), disable_web_page_preview=True)


async def copy_positions_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    context.application.bot_data["chat_id"] = chat_id
    context.application.bot_data["default_chat_id"] = chat_id

    await update.message.reply_text(
        build_copy_positions_message(),
        disable_web_page_preview=True,
    )


async def copy_trades_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    context.application.bot_data["chat_id"] = chat_id
    context.application.bot_data["default_chat_id"] = chat_id

    await update.message.reply_text(
        build_copy_trades_message(limit=10),
        disable_web_page_preview=True,
    )


async def copy_wallet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    context.application.bot_data["chat_id"] = chat_id
    context.application.bot_data["default_chat_id"] = chat_id

    await update.message.reply_text(
        build_copy_wallet_message(),
        disable_web_page_preview=True,
    )


def _first_arg(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    args = getattr(context, "args", None) or []
    return args[0] if args else None


async def copy_close_all_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    context.application.bot_data["chat_id"] = chat_id
    context.application.bot_data["default_chat_id"] = chat_id

    await update.message.reply_text(
        manual_close_paper_copy_trade(Decimal("100"), mint_arg=_first_arg(context)),
        disable_web_page_preview=True,
    )


async def copy_close_50_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    context.application.bot_data["chat_id"] = chat_id
    context.application.bot_data["default_chat_id"] = chat_id

    await update.message.reply_text(
        manual_close_paper_copy_trade(Decimal("50"), mint_arg=_first_arg(context)),
        disable_web_page_preview=True,
    )


async def copy_close_25_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    context.application.bot_data["chat_id"] = chat_id
    context.application.bot_data["default_chat_id"] = chat_id

    await update.message.reply_text(
        manual_close_paper_copy_trade(Decimal("25"), mint_arg=_first_arg(context)),
        disable_web_page_preview=True,
    )


async def cluster_map_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    context.application.bot_data["chat_id"] = chat_id
    context.application.bot_data["default_chat_id"] = chat_id

    await update.message.reply_text(
        build_cluster_discovery_message(),
        disable_web_page_preview=True,
    )
