"""
تصمیم سهم خروج با ابطال — نشست ۳، تصمیم کاربر ۲۶ سپتامبر ۲۰۲۶.

exit_fraction روی 1.0 می‌ماند، یعنی گزینه الف. دلیل در ف۳ ثبت است: ابطال
برای دم توزیع ساخته شده. برتری «خروج نصف» در حالت معمول، با ۲۳ رویداد و
نمونه‌ای که فقط سکه‌های بازمانده را دارد، در حد نویز است. ولی هزینه‌اش در
دم سازوکاری است: SOL، نوامبر ۲۰۲۲، −27.7٪ در برابر −8.9٪.

شرط بازنگری: دست‌کم ۲۰ رویداد ابطال واقعی در دفتر، یا نمونه‌ای که سکه‌های
مرده و حذف‌شده را هم دارد. این آزمون قفل است — عوض‌کردن عدد بدون عوض‌کردن
ف۳ می‌شکندش.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_watch as W

ROOT = Path(__file__).resolve().parent.parent


def _f3() -> str:
    text = (ROOT / "STATE.md").read_text(encoding="utf-8")
    return next(l for l in text.splitlines() if l.startswith("| ف۳ |"))


def test_watch_exit_fraction_is_option_a() -> None:
    w = json.loads((ROOT / "watch.json").read_text(encoding="utf-8"))
    assert w["exit_fraction"] == 1.0
    assert W.DEFAULT_EXIT_FRACTION == 1.0


def test_f3_records_reason_and_review_condition() -> None:
    row = _f3()
    assert "دم توزیع" in row
    assert "−27.7" in row and "−8.9" in row
    assert "۲۰ رویداد ابطال واقعی" in row
    assert "سکه‌های مرده" in row
