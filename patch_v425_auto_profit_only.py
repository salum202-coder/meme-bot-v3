from pathlib import Path

wallet_path = Path("core/wallet_watcher.py")
wallet = wallet_path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# V4.25 — Auto Profit Lock Only
# ---------------------------------------------------------------------------
# Paper-only. No live trading added.
#
# This patch changes profit management only:
# - TP1 at +20% closes 50% of the position.
# - TP2 at +32% increases total locked to 75%.
#
# It does NOT change entry filters.
# It does NOT change DHT8 OUT / Cluster OUT exits.
# It does NOT change Post-TP1 Profit Lock.
# It does NOT change Liquidity Rug protection.

replacements = {
    'PAPER_TP1_PCT = Decimal("50")': 'PAPER_TP1_PCT = Decimal("20")  # V4.25: first auto lock at +20%',
    'PAPER_TP1_PCT = Decimal("20")  # V4.25: first auto lock at +20%': 'PAPER_TP1_PCT = Decimal("20")  # V4.25: first auto lock at +20%',
    'PAPER_TP2_PCT = Decimal("60")': 'PAPER_TP2_PCT = Decimal("32")  # V4.25: second auto lock at +32%',
    'PAPER_TP2_PCT = Decimal("32")  # V4.25: second auto lock at +32%': 'PAPER_TP2_PCT = Decimal("32")  # V4.25: second auto lock at +32%',
}

changed = False
for old, new in replacements.items():
    if old in wallet:
        wallet = wallet.replace(old, new)
        changed = True

if 'PAPER_TP1_PCT = Decimal("20")' not in wallet:
    raise SystemExit("Could not confirm PAPER_TP1_PCT = 20. Patch not applied.")

if 'PAPER_TP2_PCT = Decimal("32")' not in wallet:
    raise SystemExit("Could not confirm PAPER_TP2_PCT = 32. Patch not applied.")

wallet_path.write_text(wallet, encoding="utf-8")

print("✅ V4.25 Auto Profit Lock Only patch applied")
print("TP1: +20% closes 50%.")
print("TP2: +32% total locked becomes 75%.")
print("Entry filters unchanged.")
print("DHT8 OUT / Cluster OUT exits unchanged.")
print("Paper-only mode preserved. No live trading added.")
