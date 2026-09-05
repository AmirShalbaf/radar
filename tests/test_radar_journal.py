#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
آزمون فیلدهای اجباری setup_name و decision_id در radar_journal.py

ادعا: کتابخانه ستاپ (references/setup-library.md) می‌گوید هر معامله باید
دقیقاً به یک ستاپ نام‌دار نسبت داده شود و به شناسه تصمیم گره بخورد.
پس ثبت معامله تازه بدون این دو فیلد نباید ممکن باشد. رکورد قدیمی
(پیش از این قاعده) هم باید با مقدار «نامشخص — پیش از کتابخانه ستاپ»
پر شود، نه خالی بماند — قانون سوگیری صفر.

اجرا:
    python tests/test_radar_journal.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import radar_journal as RJ

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    mark = "✅" if cond else "❌"
    print(f"{mark} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def test_add_requires_setup_and_decision() -> None:
    orig_argv, orig_db = sys.argv, RJ.DB
    with tempfile.TemporaryDirectory() as tmp:
        RJ.DB = os.path.join(tmp, "journal.json")
        try:
            sys.argv = ["radar_journal.py", "add", "--symbol", "TST",
                        "--side", "long", "--entry", "1", "--stop", "0.9",
                        "--size", "100"]
            try:
                RJ.main()
                ok = False
            except SystemExit as exc:
                ok = exc.code not in (0, None)
            check("بدون setup-name/decision-id ثبت رد می‌شود", ok)
        finally:
            sys.argv, RJ.DB = orig_argv, orig_db


def test_add_stores_setup_and_decision() -> None:
    orig_argv, orig_db = sys.argv, RJ.DB
    with tempfile.TemporaryDirectory() as tmp:
        RJ.DB = os.path.join(tmp, "journal.json")
        try:
            sys.argv = ["radar_journal.py", "add", "--symbol", "TST",
                        "--side", "long", "--entry", "1", "--stop", "0.9",
                        "--size", "100", "--setup-name", "الف۱",
                        "--decision-id", "D-2026-09-05-1"]
            RJ.main()
            d = RJ.load()
            t = d["trades"][0]
            check("نام ستاپ ثبت شد", t.get("setup_name") == "الف۱")
            check("شناسه تصمیم ثبت شد", t.get("decision_id") == "D-2026-09-05-1")
        finally:
            sys.argv, RJ.DB = orig_argv, orig_db


def test_existing_journal_backfilled() -> None:
    d = RJ.load()
    t = next((x for x in d["trades"] if x["id"] == 1 and x["symbol"] == "ZEC"), None)
    check("رکورد قدیمی زی‌کش پیدا شد", t is not None)
    if t is not None:
        expected = "نامشخص — پیش از کتابخانه ستاپ"
        check("نام ستاپ رکورد قدیمی پر شده", t.get("setup_name") == expected)
        check("شناسه تصمیم رکورد قدیمی پر شده", t.get("decision_id") == expected)


if __name__ == "__main__":
    test_add_requires_setup_and_decision()
    test_add_stores_setup_and_decision()
    test_existing_journal_backfilled()
    print()
    if FAILS:
        print(f"❌ {len(FAILS)} آزمون شکست: " + "، ".join(FAILS))
        sys.exit(1)
    print("✅ همه آزمون‌های radar_journal گذشتند.")
