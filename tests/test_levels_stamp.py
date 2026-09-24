"""
آزمون مهر زمان گزارش سطوح — نشست ۱ نقشه رادار ۷، مورد ۴ ب.

باگ: خروجی radar_levels.py هیچ سطر «تولید: تاریخ و ساعت» نداشت. پس قانون
تازگی رویش اجراشدنی نبود — خواننده نمی‌دانست عدد مال کی است.

رفع: سطر `تولید: **YYYY-MM-DD HH:MM UTC**` زیر عنوان، هم‌قالب اسکن و
چرخش و نبض. زمان به report تزریق‌پذیر است تا آزمون به ساعت سیستم
وابسته نباشد.

الگو عمداً `[0-9]` است نه `\\d` — در پایتون `\\d` رقم فارسی را هم می‌گیرد.
"""
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_levels as L

UTC = timezone.utc
STAMP = re.compile(r"^تولید: \*\*[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2} UTC\*\*")


def test_injected_time_is_printed_near_top() -> None:
    now = datetime(2026, 9, 25, 6, 30, tzinfo=UTC)
    head = L.report([], 2.0, now=now).splitlines()[:3]
    assert "تولید: **2026-09-25 06:30 UTC**" in head


def test_other_timezone_is_converted_to_utc() -> None:
    """ساعت محلی تهران به وقت جهانی برگردد، نه همان‌طور چاپ شود."""
    tehran = timezone(timedelta(hours=3, minutes=30))
    now = datetime(2026, 9, 25, 10, 0, tzinfo=tehran)
    assert "تولید: **2026-09-25 06:30 UTC**" in L.report([], 2.0, now=now)


def test_default_stamp_has_the_shared_format() -> None:
    """بدون تزریق هم سطر هست — فقط قالب سنجیده می‌شود، نه خود ساعت."""
    head = L.report([], 2.0).splitlines()[:3]
    assert any(STAMP.match(l) for l in head)
