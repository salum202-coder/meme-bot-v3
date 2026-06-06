from pathlib import Path

wallet_path = Path("core/wallet_watcher.py")
wallet = wallet_path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# V4.24 Simple Exit Rules
# ---------------------------------------------------------------------------
# Paper-only. No live trading added.
#
# Rules:
# 1) DHT8 Main OUT / SELL / Transfer OUT = immediate Paper exit in all cases.
# 2) Non-DHT8 cluster OUT / SELL / Transfer OUT is counted.
# 3) If 3 unique non-DHT8 wallets OUT after entry = Paper exit in all cases.
# 4) TP1 / TP2 / normal emergency protection remain unchanged.

# Add simple exit constants after existing V4.23 wallet-out constants.
anchor = 'PAPER_WALLET_OUT_LIQUIDITY_DROP_CONFIRM_PCT = Decimal("30")'
insert = """PAPER_WALLET_OUT_LIQUIDITY_DROP_CONFIRM_PCT = Decimal("30")

# V4.24 — Simple Exit Rules
# DHT8 OUT is an immediate exit.
# Non-DHT8 cluster OUT exits only after this many unique wallets.
PAPER_SIMPLE_EXIT_ENABLED = True
PAPER_SIMPLE_CLUSTER_OUT_MIN_WALLETS = 3"""
if "PAPER_SIMPLE_EXIT_ENABLED" not in wallet:
    if anchor not in wallet:
        raise SystemExit("Could not find V4.23 constants anchor. Patch not applied.")
    wallet = wallet.replace(anchor, insert)

# Add helper before maybe_handle_paper_copy_signal.
helper_anchor = "def maybe_handle_paper_copy_signal("
helper = r"""
def _is_v424_out_signal(analysis_type: str) -> bool:
    if "SELL" in analysis_type:
        return True
    if "Distribution OUT" in analysis_type:
        return True
    if "Transfer OUT" in analysis_type and "ignored" not in analysis_type:
        return True
    return False


def maybe_close_paper_copy_on_simple_cluster_out_count(
    *,
    trade: dict[str, Any],
    label: str,
    wallet_address: str,
    signature: str,
    analysis: dict[str, Any],
    source: str = "wallet_watch_cluster_v424",
) -> list[str]:
    \"\"\"V4.24 simple cluster exit.

    DHT8 is handled separately as immediate exit.
    Non-DHT8 OUT/SELL events are counted.
    Exit only when 3 unique wallets OUT after entry.
    \"\"\"
    if not PAPER_COPY_ENABLED or not PAPER_SIMPLE_EXIT_ENABLED:
        return []

    if label == "DHT8 Main":
        return []

    mint = trade.get("mint")
    if not mint:
        return []

    analysis_type = analysis.get("type") or "Wallet OUT"
    if not _is_v424_out_signal(analysis_type):
        return []

    record_paper_exit_pressure_event(
        mint=mint,
        label=label,
        wallet_address=wallet_address,
        signature=signature,
        event_kind=analysis_type,
        source=source,
    )

    out_wallets_count = count_unique_paper_exit_pressure_wallets(mint, trade.get("opened_at"))

    if out_wallets_count < PAPER_SIMPLE_CLUSTER_OUT_MIN_WALLETS:
        return []

    dex_info = fetch_dex_token_info(mint) or {}

    return [
        close_paper_copy_trade(
            trade=trade,
            reason=(
                f"V4.24 simple cluster exit: {out_wallets_count} unique non-DHT8 "
                f"wallet OUT/SELL events after entry. Latest signal: {label} / {analysis_type}."
            ),
            signature=signature,
            dex_info=dex_info,
        )
    ]

"""
if "def maybe_close_paper_copy_on_simple_cluster_out_count(" not in wallet:
    pos = wallet.find(helper_anchor)
    if pos == -1:
        raise SystemExit("Could not find maybe_handle_paper_copy_signal anchor. Patch not applied.")
    wallet = wallet[:pos] + helper + "\n" + wallet[pos:]

# Replace V4.23 DHT8 block with immediate DHT8 exit.
old_dht8 = """    # V4.23 Exit rule 1:
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
new_dht8 = """    # V4.24 Simple Exit rule 1:
    # DHT8 OUT / SELL / Transfer OUT = immediate Paper exit in all cases.
    if open_trade and label == "DHT8 Main" and _is_v424_out_signal(analysis_type):
        messages.append(
            close_paper_copy_trade(
                trade=open_trade,
                reason=f"V4.24 simple exit: DHT8 OUT detected. Signal: {analysis_type}.",
                signature=signature,
            )
        )
        return messages
"""
if old_dht8 not in wallet:
    raise SystemExit("Could not find V4.23 DHT8 exit block. Patch not applied.")
wallet = wallet.replace(old_dht8, new_dht8)

# Replace V4.23 GAMq + Cluster blocks with one simple cluster count block.
old_cluster = """    # V4.23 Exit rule 2:
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

    # V4.23 Exit rule 3:
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
new_cluster = """    # V4.24 Simple Exit rule 2:
    # Any non-DHT8 cluster/GAMq/BJsbr OUT is counted.
    # Exit only after 3 unique non-DHT8 wallets OUT after entry.
    if open_trade and label != "DHT8 Main" and _is_v424_out_signal(analysis_type):
        exit_messages = maybe_close_paper_copy_on_simple_cluster_out_count(
            trade=open_trade,
            label=label,
            wallet_address=wallet_address,
            signature=signature,
            analysis=analysis,
            source="wallet_watch_cluster_v424",
        )
        if exit_messages:
            messages.extend(exit_messages)
            return messages
"""
if old_cluster not in wallet:
    raise SystemExit("Could not find V4.23 GAMq/Cluster exit blocks. Patch not applied.")
wallet = wallet.replace(old_cluster, new_cluster)

wallet_path.write_text(wallet, encoding="utf-8")

print("✅ V4.24 Simple Exit patch applied")
print("DHT8 OUT / SELL / Transfer OUT = immediate Paper exit.")
print("Non-DHT8 cluster OUT count >= 3 = Paper exit.")
print("TP1 / TP2 remain unchanged.")
print("Paper-only mode preserved. No live trading added.")
