#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
آزمون لایه دفترچه معاملات — نام فایل و تفکیک فرضی از واقعی

ادعای یکم: نام فایل داده باید در هر مصرف‌کننده‌ای یکی باشد.
`radar_journal.py` در `journal.json` می‌نوشت، ولی `radar_state.py` و
گردش‌کار هفتگی دنبال `radar_journal.json` می‌گشتند. نتیجه بدترین شکل
خرابی بود: هیچ خطایی بالا نیامد، فقط شمارنده برای همیشه صفر ماند و
جدول وضعیت گفت «دفترچه ساخته نشده». آزمون زیر نام را در هر چهار جا به
هم قفل می‌کند — دو فایل پایتون، گردش‌کار، و استثنای `.gitignore`.

ادعای دوم: معامله فرضی و واقعی نباید با هم میانگین گرفته شوند. نتیجه
فرضی لغزش اجرا و فشار روانی و خروج زودهنگام را ندارد، پس سیستماتیک
خوش‌بینانه‌تر است. رکورد پیش از این میدان هم باید واقعی خوانده شود،
نه فرضی و نه خطا.

اجرا:
    python tests/test_journal_layer.py
"""

import io
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import radar_journal as RJ
import radar_state as RS

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    mark = "✅" if cond else "❌"
    print(f"{mark} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def read(path: str) -> str:
    with io.open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


def trade(tid: int, r: float, paper: bool | None) -> dict:
    """رکورد بسته کمینه. paper=None یعنی رکورد قدیمی، پیش از این میدان."""
    t = {
        "id": tid, "opened": "2026-09-01 00:00 UTC", "symbol": "TST",
        "side": "long", "entry": 100.0, "stop": 90.0, "target": 130.0,
        "size_usd": 100.0, "framework_verdict": "enter",
        "user_decision": "followed", "status": "closed",
        "exit_reason": "target", "r_realized": r,
    }
    if paper is not None:
        t["paper"] = paper
    return t


def write_db(path: str, trades: list[dict]) -> None:
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "trades": trades}, f, ensure_ascii=False)


# ═════════════ ۱ — نام فایل، قفل‌شده میان مصرف‌کننده‌ها ═════════════

def test_db_name_matches_everywhere() -> None:
    name = RJ.DB_NAME
    check("نام فایل در radar_journal و radar_state یکی است",
          name == RS.JOURNAL_DB, f"{name} در برابر {RS.JOURNAL_DB}")
    check("مسیر DB به همان نام ختم می‌شود",
          os.path.basename(RJ.DB) == name, os.path.basename(RJ.DB))
    check("نام در جدول فایل‌های وضعیت هست", name in RS.STATE_FILES)

    wf = read(".github/workflows/radar-weekly.yml")
    check("گردش‌کار هفتگی همان نام را نگهبانی می‌کند",
          f"[ -f {name} ]" in wf)

    gi = read(".gitignore")
    check("استثنای .gitignore روی همان نام است", f"!{name}" in gi)

    check("فایل داده واقعی با همین نام در مخزن هست",
          os.path.exists(os.path.join(ROOT, name)))

    # نام قدیمی نباید در هیچ کجای کد زنده مانده باشد
    for f in ("radar_journal.py", "radar_state.py"):
        src = read(f)
        check(f"نام قدیمی journal.json در {f} نمانده",
              '"journal.json"' not in src and "'journal.json'" not in src)


# ═════════════ ۲ — رکورد قدیمی بدون میدان paper ═════════════

def test_legacy_record_reads_as_real() -> None:
    orig = RJ.DB
    with tempfile.TemporaryDirectory() as tmp:
        RJ.DB = os.path.join(tmp, RJ.DB_NAME)
        try:
            write_db(RJ.DB, [trade(1, -1.0, None)])
            d = RJ.load()
            t = d["trades"][0]
            check("میدان paper برای رکورد قدیمی پر می‌شود", "paper" in t)
            check("رکورد قدیمی واقعی شمرده می‌شود", t.get("paper") is False,
                  repr(t.get("paper")))
            real, paper = RJ._split_paper(d["trades"])
            check("رکورد قدیمی در دسته واقعی می‌نشیند",
                  len(real) == 1 and len(paper) == 0)
        finally:
            RJ.DB = orig

    # فایل واقعی مخزن: همان یک معامله زی‌کش، بدون میدان paper نوشته شده
    d = RJ.load()
    t = next((x for x in d["trades"] if x["id"] == 1 and x["symbol"] == "ZEC"), None)
    check("رکورد زی‌کش مخزن خوانده شد", t is not None)
    if t is not None:
        check("رکورد زی‌کش واقعی است، نه فرضی", t.get("paper") is False)
        check("R محقق‌شده رکورد زی‌کش دست‌نخورده است", t.get("r_realized") == -1.0)


# ═════════════ ۳ — ثبت معامله فرضی ═════════════

def test_add_records_paper_flag() -> None:
    base = ["radar_journal.py", "add", "--symbol", "TST", "--side", "long",
            "--entry", "100", "--stop", "90", "--size", "100",
            "--setup-name", "الف۱", "--decision-id", "D-2026-09-16-1"]
    for flag, want, label in ((None, False, "بدون کلید، پیش‌فرض واقعی"),
                              ("--paper", True, "با کلید --paper، فرضی")):
        orig_argv, orig_db = sys.argv, RJ.DB
        with tempfile.TemporaryDirectory() as tmp:
            RJ.DB = os.path.join(tmp, RJ.DB_NAME)
            try:
                sys.argv = base + ([flag] if flag else [])
                RJ.main()
                t = RJ.load()["trades"][0]
                check(label, t.get("paper") is want, repr(t.get("paper")))
            finally:
                sys.argv, RJ.DB = orig_argv, orig_db


# ═════════════ ۴ — شمارش تفکیک‌شده، هر سه حالت ═════════════

CASES = (
    ("فقط واقعی", [trade(1, 1.0, False), trade(2, -1.0, False)], 2, 0),
    ("فقط فرضی", [trade(1, 2.0, True), trade(2, 3.0, True)], 0, 2),
    ("مخلوط", [trade(1, 1.0, False), trade(2, 2.0, True),
               trade(3, -1.0, None)], 2, 1),
)


def test_split_counts() -> None:
    for label, rows, want_real, want_paper in CASES:
        real, paper = RJ._split_paper(rows)
        check(f"تفکیک در حالت «{label}»",
              (len(real), len(paper)) == (want_real, want_paper),
              f"{len(real)} واقعی و {len(paper)} فرضی، انتظار "
              f"{want_real} و {want_paper}")


def test_report_shows_both_counters() -> None:
    """گزارش باید هر دو شمارنده را چاپ کند — دسته خالی هم حذف نمی‌شود."""
    import contextlib
    for label, rows, want_real, want_paper in CASES:
        orig = RJ.DB
        with tempfile.TemporaryDirectory() as tmp:
            RJ.DB = os.path.join(tmp, RJ.DB_NAME)
            try:
                write_db(RJ.DB, rows)
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    RJ.cmd_report(None)
                out = buf.getvalue()
            finally:
                RJ.DB = orig
        check(f"گزارش «{label}» شمارنده واقعی را دارد",
              f"| واقعی | {want_real} |" in out)
        check(f"گزارش «{label}» شمارنده فرضی را دارد",
              f"| فرضی | {want_paper} |" in out)
        check(f"گزارش «{label}» هر دو دسته را نشان می‌دهد",
              "## معاملات واقعی" in out and "## معاملات فرضی" in out)
        # مخلوط‌نشدن: میانگین دسته فرضی نباید در دسته واقعی ظاهر شود
        if label == "فقط فرضی":
            head = out.split("## معاملات فرضی")[0]
            check("دسته واقعی خالی، آمار فرضی را قرض نمی‌گیرد",
                  "هنوز معامله بسته‌ای در این دسته نیست." in head)


def test_state_counter_splits() -> None:
    """
    شمارنده STATE.md. این آزمون هم‌زمان نگهبان نام فایل است: فایل با
    نام **نویسنده** نوشته می‌شود (`RJ.DB_NAME`) و با چشم **خواننده**
    خوانده. اگر دو نام جدا بیفتند، هر سه حالت «0 واقعی + 0 فرضی»
    می‌دهند و آزمون قرمز می‌شود — همان خرابی بی‌صدای اصلی.
    """
    for label, rows, want_real, want_paper in CASES:
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                write_db(os.path.join(tmp, RJ.DB_NAME), rows)
                auto = RS.build_auto()
            finally:
                os.chdir(cwd)
        want = f"| تعداد معامله ثبت‌شده | {want_real} واقعی + {want_paper} فرضی"
        check(f"شمارنده وضعیت در حالت «{label}»", want in auto,
              next((l for l in auto.splitlines()
                    if "تعداد معامله ثبت‌شده" in l), "سطر پیدا نشد"))


def test_state_threshold_needs_real_trades() -> None:
    """آستانه بیست‌تایی کالیبراسیون فقط با معامله واقعی باز می‌شود."""
    cases = (
        ("بیست فرضی کافی نیست", [trade(i, 1.0, True) for i in range(1, 21)], False),
        ("بیست واقعی کافی است", [trade(i, 1.0, False) for i in range(1, 21)], True),
    )
    for label, rows, want_ok in cases:
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                write_db(os.path.join(tmp, RJ.DB_NAME), rows)
                auto = RS.build_auto()
            finally:
                os.chdir(cwd)
        line = next((l for l in auto.splitlines()
                     if "تعداد معامله ثبت‌شده" in l), "")
        check(label, ("✅" in line) is want_ok, line)


if __name__ == "__main__":
    test_db_name_matches_everywhere()
    test_legacy_record_reads_as_real()
    test_add_records_paper_flag()
    test_split_counts()
    test_report_shows_both_counters()
    test_state_counter_splits()
    test_state_threshold_needs_real_trades()
    print()
    if FAILS:
        print(f"❌ {len(FAILS)} آزمون شکست: " + "، ".join(FAILS))
        sys.exit(1)
    print("✅ همه آزمون‌های لایه دفترچه گذشتند.")
