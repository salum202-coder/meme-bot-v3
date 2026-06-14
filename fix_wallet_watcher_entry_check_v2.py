from __future__ import annotations

from pathlib import Path
import ast
import shutil
from datetime import datetime

TARGET = Path("core/wallet_watcher.py")

OLD_TEXT = '    if ratio < PAPER_MIN_BUY_SELL_RATIO:\n        return False, f"Buy/Sell ratio below {_fmt_decimal(PAPER_MIN_BUY_SELL_RATIO, 2)}x."\n        print(\n        f"[ENTRY_CHECK] "\n        f"price={price} "\n        f"liq={liquidity} "\n        f"vol={volume_h1} "\n        f"ratio={ratio}"\n    )\n    return True, "Entry quality passed."\n'

NEW_TEXT = '    print(\n        f"[ENTRY_CHECK] "\n        f"price={price} "\n        f"liq={liquidity} "\n        f"vol={volume_h1} "\n        f"ratio={ratio}"\n    )\n\n    if ratio < PAPER_MIN_BUY_SELL_RATIO:\n        return False, f"Buy/Sell ratio below {_fmt_decimal(PAPER_MIN_BUY_SELL_RATIO, 2)}x."\n\n    return True, "Entry quality passed."\n'


def main() -> None:
    if not TARGET.exists():
        raise SystemExit("ERROR: core/wallet_watcher.py not found. Run this file from project root.")

    original = TARGET.read_text(encoding="utf-8")

    if NEW_TEXT in original:
        ast.parse(original)
        print("OK: ENTRY_CHECK fix already exists.")
        print("OK: Syntax OK")
        return

    if OLD_TEXT not in original:
        raise SystemExit(
            "ERROR: Expected old ENTRY_CHECK block was not found. "
            "Do not continue. Send the current wallet_watcher.py for review."
        )

    backup = TARGET.with_suffix(
        TARGET.suffix + ".backup_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    shutil.copy2(TARGET, backup)

    updated = original.replace(OLD_TEXT, NEW_TEXT, 1)

    try:
        ast.parse(updated)
    except SyntaxError as exc:
        print("ERROR: Syntax error after patch.")
        print(exc)
        print("No changes were saved.")
        print("Backup:", backup)
        raise SystemExit(1)

    TARGET.write_text(updated, encoding="utf-8")

    print("OK: ENTRY_CHECK fixed successfully.")
    print("OK: Backup created:", backup)
    print("OK: Syntax OK")
    print("NOTE: Entry/exit logic was not changed. Only ENTRY_CHECK logging was moved before return.")


if __name__ == "__main__":
    main()
