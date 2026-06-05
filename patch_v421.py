from pathlib import Path

path = Path("core/wallet_watcher.py")
text = path.read_text(encoding="utf-8")

constants = '''
# V4.21 — Post-TP1 Profit Protection
# Protect the remaining position after TP1 from late-cycle rugs.
PAPER_V421_POST_TP1_PROTECTION_ENABLED = True
PAPER_V421_POST_TP1_CLUSTER_OUT_COUNT = 5
PAPER_V421_POST_TP1_GAMQ_COUNT = 2
PAPER_V421_POST_TP1_LIQUIDITY_DROP_PCT = Decimal("0.35")
'''

if "PAPER_V421_POST_TP1_PROTECTION_ENABLED" not in text:
    text = text.replace(
        'PAPER_AFTER_TP1_MIN_EXIT_PNL = Decimal("10")\n',
        'PAPER_AFTER_TP1_MIN_EXIT_PNL = Decimal("10")\n' + constants
    )

helper = '''
def _v421_tp1_start_iso_for_query(trade: dict[str, Any]) -> str:
    tp1_at = str(trade.get("tp1_at") or "").strip()
    if tp1_at:
        return tp1_at
    return _trade_opened_iso_for_query(trade)


def _v421_post_tp1_exit_counts(trade: dict[str, Any]) -> dict[str, int]:
    mint = trade.get("mint") or ""
    if not mint:
        return {"dht8_out": 0, "gamq_exit": 0, "cluster_exit": 0}

    try:
        _ensure_pattern_brain_tables()
        since_iso = _v421_tp1_start_iso_for_query(trade)

        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN event_kind = 'DHT8_OUT' THEN 1 ELSE 0 END) AS dht8_out,
                    SUM(CASE WHEN event_kind IN ('GAMQ_OUT', 'GAMQ_SELL') THEN 1 ELSE 0 END) AS gamq_exit,
                    SUM(CASE WHEN event_kind IN ('CLUSTER_OUT', 'CLUSTER_SELL') THEN 1 ELSE 0 END) AS cluster_exit
                FROM cluster_pattern_events
                WHERE mint = ?
                  AND event_at >= ?
                """,
                (mint, since_iso),
            ).fetchone()

        if not row:
            return {"dht8_out": 0, "gamq_exit": 0, "cluster_exit": 0}

        return {
            "dht8_out": int(row["dht8_out"] or 0),
            "gamq_exit": int(row["gamq_exit"] or 0),
            "cluster_exit": int(row["cluster_exit"] or 0),
        }
    except Exception:
        return {"dht8_out": 0, "gamq_exit": 0, "cluster_exit": 0}

'''

if "def _v421_post_tp1_exit_counts" not in text:
    text = text.replace(
        "def monitor_paper_copy_trades() -> list[str]:",
        helper + "\ndef monitor_paper_copy_trades() -> list[str]:"
    )

block = '''
        # V4.21 Post-TP1 Profit Protection:
        # After TP1, close the remaining position earlier if the group starts exiting
        # or liquidity weakens before a full rug.
        if PAPER_V421_POST_TP1_PROTECTION_ENABLED and tp1_done:
            v421_counts = _v421_post_tp1_exit_counts(trade)

            if v421_counts["dht8_out"] >= 1:
                messages.append(
                    close_paper_copy_trade(
                        trade=trade,
                        reason="V4.21 post-TP1 protection: DHT8 OUT after TP1.",
                        dex_info=dex_info,
                    )
                )
                continue

            if v421_counts["gamq_exit"] >= PAPER_V421_POST_TP1_GAMQ_COUNT:
                messages.append(
                    close_paper_copy_trade(
                        trade=trade,
                        reason=f"V4.21 post-TP1 protection: GAMq exit count reached {PAPER_V421_POST_TP1_GAMQ_COUNT}.",
                        dex_info=dex_info,
                    )
                )
                continue

            if v421_counts["cluster_exit"] >= PAPER_V421_POST_TP1_CLUSTER_OUT_COUNT:
                messages.append(
                    close_paper_copy_trade(
                        trade=trade,
                        reason=f"V4.21 post-TP1 protection: Cluster OUT/SELL count reached {PAPER_V421_POST_TP1_CLUSTER_OUT_COUNT}.",
                        dex_info=dex_info,
                    )
                )
                continue

            if entry_liquidity > 0 and liquidity <= entry_liquidity * (Decimal("1") - PAPER_V421_POST_TP1_LIQUIDITY_DROP_PCT):
                messages.append(
                    close_paper_copy_trade(
                        trade=trade,
                        reason=f"V4.21 post-TP1 protection: liquidity dropped more than {_fmt_decimal(PAPER_V421_POST_TP1_LIQUIDITY_DROP_PCT * Decimal('100'), 0)}% after TP1.",
                        dex_info=dex_info,
                    )
                )
                continue

'''

if "V4.21 Post-TP1 Profit Protection" not in text:
    text = text.replace(
        "        # Old no-TP1 time protection.\n",
        block + "\n        # Old no-TP1 time protection.\n"
    )

path.write_text(text, encoding="utf-8")
print("✅ V4.21 Post-TP1 Protection patch applied to core/wallet_watcher.py")
