from __future__ import annotations

from pathlib import Path
import re


WALLET_PATH = Path("core/wallet_watcher.py")
BOT_PATH = Path("telegram_bot/bot.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 occurrence, found {count}")
    return text.replace(old, new, 1)


def patch_wallet_watcher() -> None:
    text = WALLET_PATH.read_text(encoding="utf-8")

    # V4.23 — Alert cleanup flags.
    text = text.replace(
        "DHT8_TRACE_ALL = True",
        "DHT8_TRACE_ALL = False  # V4.23: reduce Telegram spam; keep only important paper alerts"
    )

    constants_anchor = "PAPER_V420_FAST_KILL_OBSERVE_ONLY = True\n"
    constants_insert = """PAPER_V420_FAST_KILL_OBSERVE_ONLY = True

# V4.23 — Wallet OUT confirmation exit.
# Goal: do not close a Paper Copy trade just because the first wallet OUT appears.
# Close only when:
# 1) two unique wallet OUT/SELL/Distribution OUT events are seen after entry, or
# 2) one wallet OUT is confirmed by price dropping >= 15% from entry, or
# 3) one wallet OUT is confirmed by liquidity dropping >= 30% from entry.
PAPER_WALLET_OUT_EXIT_PRESSURE_ENABLED = True
PAPER_WALLET_OUT_MIN_EVENTS = 2
PAPER_WALLET_OUT_PRICE_DROP_CONFIRM_PCT = Decimal("15")
PAPER_WALLET_OUT_LIQUIDITY_DROP_CONFIRM_PCT = Decimal("30")
"""
    if "PAPER_WALLET_OUT_EXIT_PRESSURE_ENABLED" not in text:
        text = replace_once(text, constants_anchor, constants_insert, "insert V4.23 exit constants")

    # Short NEW MINT WATCH message.
    old_new_mint_return = """    return "\\n".join(
        [
            "👀 NEW MINT WATCH V4.18",
            "",
            f"Token: {symbol}",
            f"Mint: {_short(mint)}",
            f"Family: {token_family or 'N/A'}",
            "",
            f"Source: {label}",
            f"Wallet: {_short(wallet_address)}",
            f"Detected: {analysis.get('type', 'N/A')}",
            "Reason: DHT8 received a new mint allocation. This is WATCH only, not entry.",
            "",
            f"Price: {_fmt_price(price)}",
            f"Liquidity: {_fmt_usd(liquidity)}",
            f"Volume 1H: {_fmt_usd(volume_h1)}",
            f"Buys/Sells 1H: {buys_h1}/{sells_h1}",
            "",
            "Next trigger needed for Paper Entry:",
            "Known buyer Big BUY OR strong Dex metrics on this watched mint.",
            "",
            "Exit danger:",
            "DHT8 → GAMq or GAMq SELL.",
            "",
            "DexScreener:",
            dex_info.get("url") or f"https://dexscreener.com/solana/{mint}",
            "",
            f"Tx: https://solscan.io/tx/{signature}",
            "",
            "Mode: Watch only. No Paper entry yet. No real buy.",
        ]
    )
"""
    new_new_mint_return = """    return "\\n".join(
        [
            "👀 NEW MINT WATCH",
            "",
            f"Token: {symbol}",
            f"Mint: {_short(mint)}",
            f"Family: {token_family or 'N/A'}",
            f"Source: {label}",
            "",
            f"Price: {_fmt_price(price)}",
            f"Liquidity: {_fmt_usd(liquidity)}",
            f"Volume 1H: {_fmt_usd(volume_h1)}",
            f"Buys/Sells: {buys_h1}/{sells_h1}",
            "",
            "DexScreener:",
            dex_info.get("url") or f"https://dexscreener.com/solana/{mint}",
        ]
    )
"""
    if old_new_mint_return in text:
        text = replace_once(text, old_new_mint_return, new_new_mint_return, "short NEW MINT WATCH")
    else:
        print("⚠️ NEW MINT WATCH block was not replaced; it may already be changed.")

    # V4.23.1: FAST KILL is preserved as an important warning alert.
    # It stays watch-only and does not close Paper trades by itself.

    # Add Wallet OUT pressure helpers before monitor_paper_copy_trades.
    helper_anchor = "def monitor_paper_copy_trades() -> list[str]:\n"
    helper_code = '''def _ensure_paper_exit_pressure_table() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_exit_pressure_events (
                mint TEXT NOT NULL,
                signature TEXT NOT NULL,
                label TEXT,
                wallet_address TEXT,
                event_kind TEXT,
                source TEXT,
                seen_at TEXT,
                PRIMARY KEY (mint, signature)
            )
            """
        )
        conn.commit()


def record_paper_exit_pressure_event(
    *,
    mint: str,
    label: str,
    wallet_address: str,
    signature: str,
    event_kind: str,
    source: str,
) -> None:
    if not mint or not signature:
        return

    _ensure_paper_exit_pressure_table()
    now = _now_iso()

    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO paper_exit_pressure_events (
                mint,
                signature,
                label,
                wallet_address,
                event_kind,
                source,
                seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (mint, signature, label, wallet_address, event_kind, source, now),
        )
        conn.commit()


def count_unique_paper_exit_pressure_wallets(mint: str, opened_at: str | None) -> int:
    if not mint:
        return 0

    _ensure_paper_exit_pressure_table()
    opened_iso = opened_at or ""

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT COALESCE(label, '') || ':' || COALESCE(wallet_address, '')) AS c
            FROM paper_exit_pressure_events
            WHERE mint = ?
              AND seen_at >= ?
            """,
            (mint, opened_iso),
        ).fetchone()

    return int(row["c"] or 0) if row else 0


def _calc_entry_price_drop_pct(current_price: Decimal, entry_price: Decimal) -> Decimal:
    if entry_price <= 0 or current_price <= 0:
        return Decimal("0")
    if current_price >= entry_price:
        return Decimal("0")
    return ((entry_price - current_price) / entry_price) * Decimal("100")


def _calc_entry_liquidity_drop_pct(current_liquidity: Decimal, entry_liquidity: Decimal) -> Decimal:
    if entry_liquidity <= 0 or current_liquidity <= 0:
        return Decimal("0")
    if current_liquidity >= entry_liquidity:
        return Decimal("0")
    return ((entry_liquidity - current_liquidity) / entry_liquidity) * Decimal("100")


def maybe_close_paper_copy_on_wallet_out_pressure(
    *,
    trade: dict[str, Any],
    label: str,
    wallet_address: str,
    signature: str,
    analysis: dict[str, Any],
    source: str = "wallet_watch",
) -> list[str]:
    """V4.23 confirmed wallet-OUT exit.

    Single wallet OUT is now observe-only.
    A close requires:
    - at least 2 unique wallet OUT/SELL events after entry, or
    - one wallet OUT + price drop confirmation, or
    - one wallet OUT + liquidity drop confirmation.
    """
    if not PAPER_COPY_ENABLED or not PAPER_WALLET_OUT_EXIT_PRESSURE_ENABLED:
        return []

    mint = trade.get("mint")
    if not mint:
        return []

    event_kind = analysis.get("type") or "Wallet OUT"
    record_paper_exit_pressure_event(
        mint=mint,
        label=label,
        wallet_address=wallet_address,
        signature=signature,
        event_kind=event_kind,
        source=source,
    )

    dex_info = fetch_dex_token_info(mint) or {}
    current_price = dex_info.get("price_usd") or _to_decimal(trade.get("last_price_usd"))
    current_liquidity = dex_info.get("liquidity_usd") or _to_decimal(trade.get("last_liquidity_usd"))
    entry_price = _to_decimal(trade.get("entry_price_usd"))
    entry_liquidity = _to_decimal(trade.get("entry_liquidity_usd"))

    price_drop_pct = _calc_entry_price_drop_pct(current_price, entry_price)
    liquidity_drop_pct = _calc_entry_liquidity_drop_pct(current_liquidity, entry_liquidity)
    out_wallets_count = count_unique_paper_exit_pressure_wallets(mint, trade.get("opened_at"))

    close_reason = ""

    if out_wallets_count >= PAPER_WALLET_OUT_MIN_EVENTS:
        close_reason = (
            f"V4.23 confirmed wallet OUT pressure: {out_wallets_count} unique wallet OUT events after entry."
        )
    elif price_drop_pct >= PAPER_WALLET_OUT_PRICE_DROP_CONFIRM_PCT:
        close_reason = (
            f"V4.23 wallet OUT + price confirmation: price dropped "
            f"{_fmt_decimal(price_drop_pct, 2)}% from entry."
        )
    elif liquidity_drop_pct >= PAPER_WALLET_OUT_LIQUIDITY_DROP_CONFIRM_PCT:
        close_reason = (
            f"V4.23 wallet OUT + liquidity confirmation: liquidity dropped "
            f"{_fmt_decimal(liquidity_drop_pct, 2)}% from entry."
        )

    if not close_reason:
        return []

    close_reason = (
        f"{close_reason} Signal: {label} / {event_kind}. "
        f"Single OUT alone is observe-only."
    )

    return [
        close_paper_copy_trade(
            trade=trade,
            reason=close_reason,
            signature=signature,
            dex_info=dex_info,
        )
    ]


'''
    if "def _ensure_paper_exit_pressure_table" not in text:
        text = replace_once(text, helper_anchor, helper_code + helper_anchor, "insert V4.23 helper functions")

    # Replace direct DHT8/GAMq/Cluster exits inside maybe_handle_paper_copy_signal.
    old_dht8_exit = """    # Exit rule 1: DHT8 transferred the same token out.
    # This is the strongest pre-exit signal we discovered before GAMq sells.
    if open_trade and label == "DHT8 Main" and "Distribution OUT" in analysis_type:
        messages.append(
            close_paper_copy_trade(
                trade=open_trade,
                reason="DHT8 transferred this token out. Possible DHT8 → GAMq exit route.",
                signature=signature,
            )
        )
        return messages
"""
    new_dht8_exit = """    # V4.23 Exit rule 1:
    # DHT8 OUT is important, but one OUT alone is observe-only.
    # Close only after 2 wallet OUT events, or OUT + price/liquidity confirmation.
    if open_trade and label == "DHT8 Main" and "Distribution OUT" in analysis_type:
        exit_messages = maybe_close_paper_copy_on_wallet_out_pressure(
            trade=open_trade,
            label=label,
            wallet_address=wallet_address,
            signature=signature,
            analysis=analysis,
            source="wallet_watch_dht8",
        )
        if exit_messages:
            messages.extend(exit_messages)
            return messages
"""
    if old_dht8_exit in text:
        text = replace_once(text, old_dht8_exit, new_dht8_exit, "guard DHT8 direct exit")

    old_gamq_exit = """    # Exit rule 2: GAMq sells or moves the same token.
    if open_trade and "GAMq" in label and ("SELL" in analysis_type or "Distribution OUT" in analysis_type):
        messages.append(
            close_paper_copy_trade(
                trade=open_trade,
                reason="GAMq exit activity detected.",
                signature=signature,
            )
        )
        return messages
"""
    new_gamq_exit = """    # V4.23 Exit rule 2:
    # GAMq OUT/SELL is also confirmed through the same pressure gate.
    if open_trade and "GAMq" in label and ("SELL" in analysis_type or "Distribution OUT" in analysis_type):
        exit_messages = maybe_close_paper_copy_on_wallet_out_pressure(
            trade=open_trade,
            label=label,
            wallet_address=wallet_address,
            signature=signature,
            analysis=analysis,
            source="wallet_watch_gamq",
        )
        if exit_messages:
            messages.extend(exit_messages)
            return messages
"""
    if old_gamq_exit in text:
        text = replace_once(text, old_gamq_exit, new_gamq_exit, "guard GAMq direct exit")

    old_cluster_exit = """    # V4.18 Exit rule 3:
    # Any first large cluster distribution on the same open mint after entry is final exit.
    # This protects profit/capital before waiting for liquidity-rug confirmation.
    if open_trade and _is_cluster_distribution_exit_label(label) and _is_big_distribution_signal_for_mint(analysis, mint):
        messages.append(
            close_paper_copy_trade(
                trade=open_trade,
                reason=f"First big cluster distribution detected after entry: {label} / {analysis_type}.",
                signature=signature,
            )
        )
        return messages
"""
    new_cluster_exit = """    # V4.23 Exit rule 3:
    # First Cluster OUT is observe-only. It becomes an exit only with confirmation.
    if open_trade and _is_cluster_distribution_exit_label(label) and _is_big_distribution_signal_for_mint(analysis, mint):
        exit_messages = maybe_close_paper_copy_on_wallet_out_pressure(
            trade=open_trade,
            label=label,
            wallet_address=wallet_address,
            signature=signature,
            analysis=analysis,
            source="wallet_watch_cluster",
        )
        if exit_messages:
            messages.extend(exit_messages)
            return messages
"""
    if old_cluster_exit in text:
        text = replace_once(text, old_cluster_exit, new_cluster_exit, "guard cluster direct exit")

    # Replace digest direct exits with V4.23 confirmed exits.
    text = text.replace(
        """    if label == "DHT8 Main" and "Distribution OUT" in analysis_type:
        return [
            close_paper_copy_trade(
                trade=open_trade,
                reason="Digest exit sync: DHT8 OUT detected on open mint.",
                signature=signature,
            )
        ]
""",
        """    if label == "DHT8 Main" and "Distribution OUT" in analysis_type:
        return maybe_close_paper_copy_on_wallet_out_pressure(
            trade=open_trade,
            label=label,
            wallet_address=wallet_address,
            signature=signature,
            analysis=analysis,
            source="digest_dht8",
        )
"""
    )

    text = text.replace(
        """    if "GAMq" in label and ("SELL" in analysis_type or "Distribution OUT" in analysis_type):
        return [
            close_paper_copy_trade(
                trade=open_trade,
                reason="Digest exit sync: GAMq exit activity detected on open mint.",
                signature=signature,
            )
        ]
""",
        """    if "GAMq" in label and ("SELL" in analysis_type or "Distribution OUT" in analysis_type):
        return maybe_close_paper_copy_on_wallet_out_pressure(
            trade=open_trade,
            label=label,
            wallet_address=wallet_address,
            signature=signature,
            analysis=analysis,
            source="digest_gamq",
        )
"""
    )

    text = text.replace(
        """    if _is_cluster_distribution_exit_label(label) and _is_big_distribution_signal_for_mint(analysis, mint):
        return [
            close_paper_copy_trade(
                trade=open_trade,
                reason=f"Digest exit sync: first big cluster distribution detected on open mint: {label}.",
                signature=signature,
            )
        ]
""",
        """    if _is_cluster_distribution_exit_label(label) and _is_big_distribution_signal_for_mint(analysis, mint):
        return maybe_close_paper_copy_on_wallet_out_pressure(
            trade=open_trade,
            label=label,
            wallet_address=wallet_address,
            signature=signature,
            analysis=analysis,
            source="digest_cluster",
        )
"""
    )

    # Replace DHT8 OUT sync direct close inside monitor_paper_copy_trades.
    old_dht8_sync = """        recent_exit = find_recent_dht8_out_for_trade(trade)
        if recent_exit:
            signature, _analysis = recent_exit
            dex_info = fetch_dex_token_info(mint) or {}
            messages.append(
                close_paper_copy_trade(
                    trade=trade,
                    reason="DHT8 OUT sync detected. Closing remaining position.",
                    signature=signature,
                    dex_info=dex_info,
                )
            )
            continue
"""
    new_dht8_sync = """        recent_exit = find_recent_dht8_out_for_trade(trade)
        if recent_exit:
            signature, _analysis = recent_exit
            exit_messages = maybe_close_paper_copy_on_wallet_out_pressure(
                trade=trade,
                label="DHT8 Main",
                wallet_address=DHT8_MAIN_WALLET,
                signature=signature,
                analysis=_analysis,
                source="monitor_dht8_sync",
            )
            if exit_messages:
                messages.extend(exit_messages)
                continue
"""
    if old_dht8_sync in text:
        text = replace_once(text, old_dht8_sync, new_dht8_sync, "guard DHT8 sync exit")

    # Silence Pending TX resolved messages; keep only paper entry/exit messages.
    text = text.replace(
        "        messages.append(build_pending_recheck_message(row=row, analysis=analysis))\n        messages.extend(paper_messages)\n",
        "        # V4.23: do not send standalone Pending TX Recheck spam.\n        messages.extend(paper_messages)\n"
    )

    # Keep TP2 accounting, but suppress TP2 Telegram alert.
    text = text.replace(
        """            tp2_message = mark_paper_copy_tp2(trade, dex_info)
            if tp2_message:
                messages.append(tp2_message)
""",
        """            # V4.23: TP2 still updates locked profit internally, but no separate Telegram alert.
            mark_paper_copy_tp2(trade, dex_info)
"""
    )

    # Remove Wallet Activity Summary Telegram blocks.
    summary_pattern = re.compile(
        r"\n(?P<indent>[ \t]+)await context\.bot\.send_message\(\n"
        r"(?P=indent)[ \t]+chat_id=chat_id,\n"
        r"(?P=indent)[ \t]+text=build_wallet_activity_summary\([\s\S]*?\n"
        r"(?P=indent)[ \t]+disable_web_page_preview=True,\n"
        r"(?P=indent)\)",
        re.MULTILINE,
    )
    text, summary_removed = summary_pattern.subn(
        "\n\\g<indent># V4.23: Wallet Activity Summary suppressed to reduce Telegram spam.",
        text,
    )
    print(f"Wallet Activity Summary blocks removed: {summary_removed}")

    # Disable active-token monitor alerts from Telegram cycle.
    old_active_monitor_block = """        for alert in monitor_active_tokens():
            await context.bot.send_message(
                chat_id=chat_id,
                text=alert,
                disable_web_page_preview=True,
            )

"""
    new_active_monitor_block = """        # V4.23: Active token alerts are suppressed to keep Telegram clean.
        # Keep only NEW MINT WATCH, PAPER ENTRY, TP1, PAPER EXIT, and requested STATUS.

"""
    if old_active_monitor_block in text:
        text = replace_once(text, old_active_monitor_block, new_active_monitor_block, "disable active token alert sending")

    WALLET_PATH.write_text(text, encoding="utf-8")


def patch_bot() -> None:
    text = BOT_PATH.read_text(encoding="utf-8")

    old_digest_job = """    # Wallet Cluster Digest - summary report every 30 minutes.
    app.job_queue.run_repeating(run_wallet_digest_cycle, interval=1800, first=180)
"""
    new_digest_job = """    # V4.23: Wallet Cluster Digest auto-job disabled to remove 30m Telegram spam.
    # Manual /digest command remains available if you need it.
"""
    if old_digest_job in text:
        text = replace_once(text, old_digest_job, new_digest_job, "disable 30m digest job")
    else:
        print("⚠️ Digest job block was not replaced; it may already be disabled.")

    BOT_PATH.write_text(text, encoding="utf-8")


def main() -> None:
    if not WALLET_PATH.exists():
        raise FileNotFoundError(f"Missing file: {WALLET_PATH}")
    if not BOT_PATH.exists():
        raise FileNotFoundError(f"Missing file: {BOT_PATH}")

    patch_wallet_watcher()
    patch_bot()

    print("✅ V4.23 Clean Exit + Alert Cleanup patch applied.")
    print("Changes:")
    print("- Single Wallet OUT is observe-only.")
    print("- Exit requires 2 wallet OUT events OR OUT + price drop >= 15% OR OUT + liquidity drop >= 30%.")
    print("- 30m Digest auto-job disabled.")
    print("- NEW MINT WATCH shortened.")
    print("- Wallet Activity Summary / Pending Recheck / Active Token spam reduced.")
    print("- FAST KILL alert is preserved as watch-only warning.")
    print("- TP2 accounting remains, but TP2 alert is suppressed.")
    print("- Paper-only mode preserved. No Live trading added.")


if __name__ == "__main__":
    main()
