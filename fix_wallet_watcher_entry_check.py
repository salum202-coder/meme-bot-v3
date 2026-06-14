from __future__ import annotations

from pathlib import Path
import ast
import shutil
from datetime import datetime

TARGET = Path("core/wallet_watcher.py")

OLD_BLOCK = def _paper_entry_quality(dex_info: dict[str, Any]) -> tuple[bool, str]:
    price = dex_info.get("price_usd") or Decimal("0")
    liquidity = dex_info.get("liquidity_usd") or Decimal("0")
    volume_h1 = dex_info.get("volume_h1") or Decimal("0")
    ratio = _paper_buy_sell_ratio(dex_info)

    if price <= 0:
        return False, "Price is not available."

    if liquidity < PAPER_MIN_LIQUIDITY_USD:
        return False, f"Liquidity below {_fmt_usd(PAPER_MIN_LIQUIDITY_USD)}."

    if volume_h1 < PAPER_MIN_VOLUME_H1_USD:
        return False, f"Volume 1H below {_fmt_usd(PAPER_MIN_VOLUME_H1_USD)}."

    if ratio < PAPER_MIN_BUY_SELL_RATIO:
        return False, f"Buy/Sell ratio below {_fmt_decimal(PAPER_MIN_BUY_SELL_RATIO, 2)}x."
        print(
        f"[ENTRY_CHECK] "
        f"price={price} "
        f"liq={liquidity} "
        f"vol={volume_h1} "
        f"ratio={ratio}"
    )
    return True, "Entry quality passed."


NEW_BLOCK = def _paper_entry_quality(dex_info: dict[str, Any]) -> tuple[bool, str]:
    price = dex_info.get("price_usd") or Decimal("0")
    liquidity = dex_info.get("liquidity_usd") or Decimal("0")
    volume_h1 = dex_info.get("volume_h1") or Decimal("0")
    ratio = _paper_buy_sell_ratio(dex_info)

    print(
        f"[ENTRY_CHECK] "
        f"price={price} "
        f"liq={liquidity} "
        f"vol={volume_h1} "
        f"ratio={ratio}"
    )

    if price <= 0:
        return False, "Price is not available."

    if liquidity < PAPER_MIN_LIQUIDITY_USD:
        return False, f"Liquidity below {_fmt_usd(PAPER_MIN_LIQUIDITY_USD)}."

    if volume_h1 < PAPER_MIN_VOLUME_H1_USD:
        return False, f"Volume 1H below {_fmt_usd(PAPER_MIN_VOLUME_H1_USD)}."

    if ratio < PAPER_MIN_BUY_SELL_RATIO:
        return False, f"Buy/Sell ratio below {_fmt_decimal(PAPER_MIN_BUY_SELL_RATIO, 2)}x."

    return True, "Entry quality passed."



def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"❌ لم أجد الملف: {TARGET}")

    text = TARGET.read_text(encoding="utf-8")

    if NEW_BLOCK in text:
        print("✅ التعديل موجود مسبقاً. لا يوجد شيء للتغيير.")
        ast.parse(text)
        print("✅ Syntax OK")
        return

    if OLD_BLOCK not in text:
        raise SystemExit(
            "❌ لم أجد البلوك القديم كما هو. لا تطبق التعديل.
"
            "ارسل لي الملف الحالي أو آخر نسخة من wallet_watcher.py للمراجعة."
        )

    backup = TARGET.with_suffix(
        TARGET.suffix + f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    shutil.copy2(TARGET, backup)

    updated = text.replace(OLD_BLOCK, NEW_BLOCK, 1)

    try:
        ast.parse(updated)
    except SyntaxError as e:
        print(f"❌ Syntax Error بعد التعديل: {e}")
        print(f"✅ لم يتم حفظ التعديل. النسخة الأصلية محفوظة في: {backup}")
        raise SystemExit(1)

    TARGET.write_text(updated, encoding="utf-8")

    print("✅ تم إصلاح ENTRY_CHECK بنجاح.")
    print(f"✅ Backup created: {backup}")
    print("✅ Syntax OK")
    print("ملاحظة: لم يتم تغيير منطق الدخول أو الخروج، فقط نقل print قبل شروط return.")


if __name__ == "__main__":
    main()
