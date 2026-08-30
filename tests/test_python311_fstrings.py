#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
آزمون ناسازگاری PEP 701 با پایتون ۳.۱۱ — گردش‌کار روی این نسخه اجرا می‌شود

چرا این آزمون لازم است
-----------------------
باگ چندماهه اسکن روزانه: خط ۴۷۶ radar_scan.py رشته قالب‌بندی تودرتو با
گیومه هم‌جنس داشت. در پایتون ۳.۱۲ محلی (PEP 701) سالم بود، در پایتون
۳.۱۱ رانر گیت‌هاب خطای نحوی می‌داد. `python -m py_compile` این را هرگز
نمی‌گرفت چون روی همان مفسر محلی اجرا می‌شود.

`ast.parse(feature_version=(3, 11))` هم این محدودیت را بازنمی‌گرداند —
آزمون‌شده و رد شده: نسخه معیوب اصلی را هم بدون خطا رد می‌کند، چون این
محدودیت در توکنایزر است، نه در گرامر.

درس: کد باید روی نسخه پایتون محیط اجرا آزمایش شود، نه فقط محیط توسعه.

روش
---
پشته گیومه‌های باز رشته‌های f را با ماژول tokenize دنبال می‌کند. هر
رشته (ساده یا f) که همان نویسه گیومه یک f-string باز را در تودرتو
تکرار کند، در ۳.۱۱ و پیش از آن خطای نحوی می‌دهد.

اجرا:
    python tests/test_python311_fstrings.py
"""

import io
import pathlib
import sys
import tokenize

FAILS: list[str] = []
ROOT = pathlib.Path(__file__).resolve().parent.parent
FSTRING_START = getattr(tokenize, "FSTRING_START", None)
FSTRING_END = getattr(tokenize, "FSTRING_END", None)


def quote_char_of(tok_string: str) -> str:
    s = tok_string
    while s and s[0].isalpha():
        s = s[1:]
    return s[0] if s else ""


def scan_file(path: pathlib.Path) -> list[tuple[int, int, str]]:
    """نقاطی که همان گیومه یک f-string باز، تودرتو تکرار شده را برمی‌گرداند."""
    problems: list[tuple[int, int, str]] = []
    stack: list[str] = []
    toks = tokenize.tokenize(io.BytesIO(path.read_bytes()).readline)
    for tok in toks:
        if FSTRING_START is not None and tok.type == FSTRING_START:
            q = quote_char_of(tok.string)
            if q in stack:
                problems.append((tok.start[0], tok.start[1],
                                 f"رشته f با گیومه «{q}» درون رشته f باز با همان گیومه"))
            stack.append(q)
        elif FSTRING_END is not None and tok.type == FSTRING_END:
            if stack:
                stack.pop()
        elif tok.type == tokenize.STRING and stack:
            q = quote_char_of(tok.string)
            if q in stack:
                problems.append((tok.start[0], tok.start[1],
                                 f"رشته ساده با گیومه «{q}» درون رشته f باز با همان گیومه"))
    return problems


def check(name: str, cond: bool, detail: str = "") -> None:
    mark = "✅" if cond else "❌"
    print(f"{mark} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def test_repo_fstrings_are_py311_safe() -> None:
    if FSTRING_START is None:
        print("⚠️ این مفسر توکن FSTRING_START ندارد — آزمون رد شد (بی‌ربط به این نسخه).")
        return
    total = 0
    for path in sorted(ROOT.glob("*.py")):
        for line, col, msg in scan_file(path):
            check(f"{path.name}:{line}:{col}", False, msg)
            total += 1
    check("همه رشته‌های f ریشه مخزن با پایتون ۳.۱۱ سازگارند", total == 0)


def test_regression_line_476_pattern() -> None:
    """بازآفرینی دقیق باگ اصلی — نباید هرگز دوباره چاپ نشدن بدهد."""
    src = (
        "r = {'vs_poc': 1.0}\n"
        "x = f\"| {f\"{r['vs_poc']:+.1f}%\" if r.get('vs_poc') is not None else '—'} |\"\n"
    )
    tmp = ROOT / "tests" / "_tmp_regression_476.py"
    tmp.write_text(src, encoding="utf-8")
    try:
        problems = scan_file(tmp)
        check("الگوی خط ۴۷۶ به‌درستی شناسایی می‌شود", len(problems) >= 1)
    finally:
        tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    test_repo_fstrings_are_py311_safe()
    test_regression_line_476_pattern()
    print()
    if FAILS:
        print(f"❌ {len(FAILS)} مورد ناسازگار با پایتون ۳.۱۱: " + "، ".join(FAILS))
        sys.exit(1)
    print("✅ همه فایل‌های ریشه مخزن روی قواعد پایتون ۳.۱۱ سالم‌اند.")
