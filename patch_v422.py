from pathlib import Path

path = Path("core/wallet_watcher.py")
text = path.read_text(encoding="utf-8")

text = text.replace(
    "PAPER_V420_PATTERN_EXIT_SYNC_ENABLED = True",
    "PAPER_V420_PATTERN_EXIT_SYNC_ENABLED = False"
)

text = text.replace(
    "PAPER_V420_ARMED_WALLET_OUT_EXIT_ENABLED = True",
    "PAPER_V420_ARMED_WALLET_OUT_EXIT_ENABLED = False"
)

text = text.replace(
    "FIRST_BIG_DISTRIBUTION_EXIT_ENABLED = True",
    "FIRST_BIG_DISTRIBUTION_EXIT_ENABLED = False"
)

path.write_text(text, encoding="utf-8")

print("✅ V4.22 Exit Sensitivity Fix applied")
print("Disabled early V4.20 Pattern/Armed single OUT exits.")
print("DHT8 OUT and normal safety exits remain active.")
