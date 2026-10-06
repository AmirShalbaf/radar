"""
آزمون ترتیب فروش دفتر موقعیت در radar_book.py — نشست ۳، مورد ۷.

قاعده کاربر (۲۵ سپتامبر ۲۰۲۶): اول پوزیشن بی‌ابطال، سپس ضعیف‌ترین قدرت
نسبی ۳۰ روزه. پیش از این بخش ۵ اول بر اساس سه‌ضربه و امتیاز مرتب می‌کرد و
قدرت نسبی را آخر می‌آورد. امتیاز حالا فقط در ستون دلیل می‌آید؛ ضربه از ۶
اکتبر فقط اطلاعی است و نه دلیل است نه اقدام — ک۸۵. قدرت نسبی نامعلوم آخر می‌آید،
با یادداشت — ضعفی که اندازه‌گیری نشده ادعا نمی‌شود.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_book as B


def _r(sym, rs30, inv=None, score=0.0, strikes=0, value=100.0) -> dict:
    return {"pos": {"symbol": sym, "invalidation": inv}, "rs30": rs30,
            "score": score, "strikes": strikes, "value": value}


def _syms(rows) -> list[str]:
    return [r["pos"]["symbol"] for r in B.sell_order(rows)]


def test_no_invalidation_first_then_weakest_rs() -> None:
    rows = [_r("ONDO", 0.36, inv=0.44), _r("ETH", 0.026, inv=2380.0),
            _r("SUI", 0.264), _r("AAVE", 0.086, inv=117.0), _r("BNB", 0.044)]
    assert _syms(rows) == ["BNB", "SUI", "ETH", "AAVE", "ONDO"]


def test_score_and_strikes_do_not_reorder() -> None:
    """امتیاز بد و سه ضربه جای قدرت نسبی را نمی‌گیرند."""
    rows = [_r("A", 0.10, inv=1.0, score=-1.5, strikes=3),
            _r("B", -0.05, inv=1.0, score=1.2, strikes=0)]
    assert _syms(rows) == ["B", "A"]


def test_unknown_rs_goes_last_within_its_group() -> None:
    rows = [_r("X", None, inv=1.0), _r("Y", 0.30, inv=1.0), _r("Z", None),
            _r("W", 0.50)]
    assert _syms(rows) == ["W", "Z", "Y", "X"]


def test_report_notes_unknown_rs(tmp_path) -> None:
    h = {"version": 2, "updated": "2026-09-25T00:00:00+00:00", "source": "آزمون",
         "frozen": {"date": "2026-09-25", "members": {}}, "cash": [], "positions": [],
         "ledger": []}
    rows = []
    for sym, rs in (("AAA", None), ("BBB", -0.02)):
        pos = {"symbol": sym, "book": "position", "status": "open", "invalidation": 1.0,
               "lots": [{"qty": 1.0, "account": "A", "entry": None}]}
        rows.append({"pos": pos, "qty": 1.0, "price": 500.0, "value": 500.0,
                     "dust": False, "avg_entry": None, "score": 0.1, "rsi": None,
                     "rs30": rs, "strikes": 0, "weekly": None, "weekly_why": [],
                     "swap_edge": None, "swap_to": None})
    rep = B.build_report(h, rows, None, [], "آزمون")
    sell = rep.split("## ۵")[1].split("## ۶")[0]
    lines = [l for l in sell.splitlines() if l.startswith("| ") and l[2].isdigit()]
    assert "BBB" in lines[0] and "AAA" in lines[1]
    assert "قدرت نسبی نامعلوم" in lines[1]
    assert "ضعیف‌ترین قدرت نسبی" in sell


def test_fmt_zero_decimals_keeps_integer_zeros() -> None:
    """پیش از این 500 با صفر رقم اعشار «5» می‌شد و 1000 «1,» — rstrip صفر عدد صحیح را هم می‌برید."""
    assert B.fmt(500.0, 0) == "500"
    assert B.fmt(1000.0, 0) == "1,000"
    assert B.fmt(2.50, 4) == "2.5"
    assert B.fmt(3.0) == "3"
