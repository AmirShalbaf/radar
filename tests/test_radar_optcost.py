#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
آزمون باگ شماره ۹ — شرط تهی در بخش ۳ گزارش radar_optcost.py

ادعا: وقتی R ازدست‌رفته یک شرط مسدودکننده هنوز محاسبه نشده (تهی است)،
گزارش نباید بنویسد «R متوسطش منفی است». تهی یعنی «داده ندارم» —
قانون مادر داده. سه حالت باید سه پیام جدا بگیرند:

    تهی        → داده ندارم، قضاوت ممنوع
    مثبت       → شرط گران است
    صفر یا منفی → شرط محافظت کرده

اجرا:
    python tests/test_radar_optcost.py
"""

import json
import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import radar_optcost as RO

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    mark = "✅" if cond else "❌"
    print(f"{mark} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def make_reject(rid: int, blocker: str, r_lost) -> dict:
    return {"id": rid, "date": "2026-08-01", "symbol": f"T{rid}",
            "price": 100.0, "blocker": blocker, "grade": "F", "score": 0.5,
            "regime": -0.6, "side": "long", "entry": 100.0, "stop": 95.0,
            "target": 115.0, "note": "", "p14": None, "p30": None,
            "r_lost": r_lost, "r_note": None}


def run_report(rejects: list[dict]) -> str:
    """گزارش را در پوشه موقت با دفتر ساختگی اجرا می‌کند و متن را برمی‌گرداند."""
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            with open(RO.FILE, "w", encoding="utf-8") as f:
                json.dump({"rejects": rejects, "sessions": []}, f)
            out = os.path.join(tmp, "rep.md")
            RO.cmd_report(SimpleNamespace(out=out))
            with open(out, encoding="utf-8") as f:
                return f.read()
        finally:
            os.chdir(cwd)


def test_none_is_not_negative() -> None:
    # سه رد با یک شرط (تمرکز ۱۰۰٪ > آستانه ۴۰٪) و R ازدست‌رفته همگی تهی
    txt = run_report([make_reject(i, "رده کیفیت F", None) for i in (1, 2, 3)])
    check("تهی: ادعای «منفی» نمی‌کند", "R متوسطش منفی است" not in txt)
    check("تهی: صریح می‌گوید داده ندارم", "هنوز محاسبه نشده" in txt)


def test_negative_still_reported_protective() -> None:
    txt = run_report([make_reject(i, "رده کیفیت F", -1.0) for i in (1, 2, 3)])
    check("منفی: پیام محافظت هست", "محافظت کرده" in txt)


def test_positive_still_reported_expensive() -> None:
    txt = run_report([make_reject(i, "رده کیفیت F", 2.0) for i in (1, 2, 3)])
    check("مثبت: پیام گرانی هست", "گران است" in txt)


if __name__ == "__main__":
    test_none_is_not_negative()
    test_negative_still_reported_protective()
    test_positive_still_reported_expensive()
    print()
    if FAILS:
        print(f"❌ {len(FAILS)} آزمون شکست: " + "، ".join(FAILS))
        sys.exit(1)
    print("✅ همه آزمون‌های radar_optcost گذشتند.")
