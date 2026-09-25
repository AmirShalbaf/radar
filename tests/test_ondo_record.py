"""
اصلاح ک۱۰ — نشست ۳، تصمیم کاربر ۲۶ سپتامبر ۲۰۲۶.

ک۱۰ غلط نبود، ناقص بود. ONDO در دو صرافی بود. در ۱۳ سپتامبر ۲۰۲۶ ONDO صرافی
دیگر به خاطر نیاز به نقدینگی فروخته شد، نه به خاطر سیگنال رادار. ONDO داخل
LBank باقی است و در دفتر موقعیت می‌ماند. ردیف ک۱۰ حذف نمی‌شود.

آمار نتیجه‌ها: فروش برای نقدینگی خروج رادار نیست. اگر در دفتر هزینه فرصت یا
دفترچه ثبت شده باشد، دلیلش باید «نیاز به نقدینگی» باشد.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _k10() -> str:
    text = (ROOT / "STATE.md").read_text(encoding="utf-8")
    return next(l for l in text.splitlines() if l.startswith("| ک۱۰ |"))


def test_k10_row_kept_and_completed() -> None:
    row = _k10()
    assert "نیاز به نقدینگی" in row and "نه به خاطر سیگنال" in row
    assert "LBank" in row and "دفتر موقعیت" in row


def _records(obj):
    """هر دیکشنری تودرتو — دفترها ساختار یکسان ندارند."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _records(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _records(v)


def test_no_ondo_sale_counted_as_radar_exit() -> None:
    for name in ("radar_optcost.json", "radar_journal.json"):
        data = json.loads((ROOT / name).read_text(encoding="utf-8"))
        for r in _records(data):
            day = str(r.get("date") or r.get("at") or r.get("closed") or "")
            if r.get("symbol") == "ONDO" and day.startswith("2026-09-13"):
                assert r.get("reason") == "نیاز به نقدینگی", (name, r)


def test_ondo_lbank_lot_stays_in_position_book() -> None:
    h = json.loads((ROOT / "holdings.json").read_text(encoding="utf-8"))
    p = next(x for x in h["positions"] if x["symbol"] == "ONDO")
    assert p["book"] == "position" and p["status"] == "open"
    assert [(l["account"], l["qty"]) for l in p["lots"]] == [("LBank", 115.43866)]
