#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_state.py — به‌روزرسانی خودکار حافظه پروژه، رادار ۶.۱
============================================================

مسئله‌ای که حل می‌کند
---------------------
کلاود میان جلسه‌ها حافظه قابل‌اتکا ندارد. خلاصه‌های حافظه‌اش با تأخیر
به‌روز می‌شوند و ممکن است ناقص باشند. نتیجه: هر جلسه از نو شروع می‌شود
و تصمیم‌های قبلی فراموش می‌شوند.

راه‌حل: حافظه را از مدل بیرون بیاور و در مخزن بگذار.

    کامپیوتر ──> STATE.md ──git push──> گیت‌هاب ──> کلاود می‌خواند

این آزمون‌شده است: کلاود به رابط صرافی دسترسی ندارد (۴۰۳)، ولی
`raw.githubusercontent.com` را می‌خواند (۲۰۰).

این اسکریپت بخش‌های خودکار `STATE.md` را بازتولید می‌کند: فهرست
اسکریپت‌ها، وضعیت راه‌اندازی، تازگی گزارش‌ها، و آخرین کامیت.
بخش‌های دستی — دفترچه رویدادها و کارهای باز — دست‌نخورده می‌مانند.

اجرا
----
    python radar_state.py              # به‌روزرسانی بخش‌های خودکار
    python radar_state.py --snapshot   # به‌علاوه ساخت reports/LATEST.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

UTC = timezone.utc
VERSION = "6.1"
STATE = "STATE.md"

SCRIPTS = [
    "radar_fetch3.py", "radar_scan.py", "radar_rotate.py", "radar_levels.py",
    "radar_journal.py", "radar_intake.py", "radar_digest.py",
    "radar_size.py", "radar_book.py", "radar_optcost.py",
    "radar_watch.py", "radar_validate.py", "radar_state.py",
]

STATE_FILES = {
    "holdings.json": "سبد واقعی",
    "watch.json": "فهرست پایش زنده",
    "radar_journal.json": "دفترچه معاملات",
    "radar_optcost.json": "دفتر هزینه فرصت",
    "book_state.json": "تاریخچه ضربه‌ها",
}


def sh(cmd: str) -> str:
    try:
        # رمزگذاری صریح utf-8 — بدون آن، ویندوز از کدپیج محلی استفاده می‌کند
        # و پیام کامیت فارسی خراب می‌شود
        return subprocess.run(cmd, shell=True, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=15).stdout.strip()
    except Exception:
        return ""


def file_version(path: str) -> str:
    """نسخه را از متغیر VERSION داخل فایل می‌خواند."""
    if not os.path.exists(path):
        return "—"
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            head = f.read(4000)
        m = re.search(r'VERSION\s*=\s*["\']([\d.]+)["\']', head)
        return m.group(1) if m else "—"
    except Exception:
        return "—"


def age_days(path: str) -> float | None:
    if not os.path.exists(path):
        return None
    return (datetime.now().timestamp() - os.path.getmtime(path)) / 86400


def build_auto() -> str:
    o: list[str] = []
    W = o.append
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    W("<!-- شروع بخش خودکار — دستی ویرایش نکن -->")
    W("")
    W("## ۲ — نسخه و فایل‌ها")
    W("")
    W(f"تولید خودکار: {now}")
    W("")
    W("| مورد | مقدار |")
    W("|---|---|")
    W(f"| نسخه فعال | **رادار {VERSION}** |")
    last = sh("git log -1 --format=%h") or "—"
    msg = sh("git log -1 --format=%s") or "—"
    W(f"| آخرین کامیت | `{last}` — {msg} |")
    W(f"| شاخه | {sh('git rev-parse --abbrev-ref HEAD') or '—'} |")
    W("")
    W("| اسکریپت | نسخه | موجود |")
    W("|---|---|---|")
    for s in SCRIPTS:
        ok = "✅" if os.path.exists(s) else "❌"
        W(f"| `{s}` | {file_version(s)} | {ok} |")
    W("")

    W("## ۳ — وضعیت راه‌اندازی")
    W("")
    W("| مورد | وضعیت |")
    W("|---|---|")

    wf = os.path.isdir(".github/workflows")
    W(f"| گردش‌کار در `.github/workflows/` | {'✅ فایل هست' if wf else '❌ نیست'} |")

    reports = []
    if os.path.isdir("reports"):
        reports = [f for f in os.listdir("reports") if f.endswith(".md")]
    if reports:
        newest = max(reports, key=lambda f: os.path.getmtime(f"reports/{f}"))
        a = age_days(f"reports/{newest}") or 0
        tag = "✅ تازه" if a < 1.5 else f"⚠️ {a:.1f} روز کهنه"
        W(f"| پوشه `reports/` | {tag} — {len(reports)} فایل، آخری `{newest}` |")
    else:
        W("| پوشه `reports/` | ❌ **خالی — کلاود هیچ داده صرافی نمی‌بیند** |")

    for f, label in STATE_FILES.items():
        if os.path.exists(f):
            a = age_days(f) or 0
            W(f"| `{f}` ({label}) | ✅ {a:.1f} روز پیش |")
        else:
            W(f"| `{f}` ({label}) | ❌ ساخته نشده |")

    tg = "✅" if (os.getenv("TELEGRAM_BOT_TOKEN") and
                 os.getenv("TELEGRAM_CHAT_ID")) else "❌ تنظیم نشده"
    W(f"| کلید تلگرام | {tg} |")

    # شمارش رکوردها
    for f, key, label in (("radar_journal.json", "trades", "معامله ثبت‌شده"),
                          ("radar_optcost.json", "rejects", "رکورد هزینه فرصت")):
        n = 0
        if os.path.exists(f):
            try:
                with open(f, encoding="utf-8") as fh:
                    n = len(json.load(fh).get(key, []))
            except Exception:
                pass
        need = 20 if key == "trades" else 15
        flag = "✅" if n >= need else f"⚠️ حداقل لازم {need}"
        W(f"| تعداد {label} | {n} — {flag} |")

    W("")
    if not reports:
        W("**بزرگ‌ترین شکاف:** پوشه `reports/` خالی است.")
        W("تا وقتی خالی باشد، کلاود مجبور می‌شود از وب عدد بگیرد — که غلط است.")
        W("رفع: `python radar_watch.py --once` سپس کامیت و پوش.")
        W("")
    W("<!-- پایان بخش خودکار -->")
    return "\n".join(o)


def splice(text: str, auto: str) -> str:
    """بخش خودکار را جایگزین می‌کند و بخش‌های دستی را دست نمی‌زند."""
    start = "<!-- شروع بخش خودکار — دستی ویرایش نکن -->"
    end = "<!-- پایان بخش خودکار -->"
    if start in text and end in text:
        pre = text.split(start)[0]
        post = text.split(end, 1)[1]
        return pre + auto + post
    # نخستین اجرا: پیش از بخش ۴ درج کن
    marker = "## ۴ — یافته‌های اثبات‌شده"
    if marker in text:
        pre, post = text.split(marker, 1)
        # بخش‌های ۲ و ۳ قدیمی را بردار
        pre = re.split(r"## ۲ — نسخه و فایل‌ها", pre)[0]
        return pre + auto + "\n\n" + marker + post
    return text + "\n\n" + auto


def snapshot() -> None:
    """یک عکس فوری از داده زنده می‌سازد تا کلاود چیزی برای خواندن داشته باشد."""
    os.makedirs("reports", exist_ok=True)
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# آخرین وضعیت — {now}", "",
             "تولیدشده روی کامپیوتر کاربر، از رابط صرافی.",
             "**این داده معتبر است. جست‌وجوی وب برای عدد ممنوع.**", ""]
    try:
        import requests
        syms = ["BTC", "ETH", "ZEC", "SOL", "HYPE", "BNB", "SUI", "ONDO", "TAO", "XRP", "AAVE", "LINK"]
        lines += ["## قیمت لحظه‌ای — اوکی‌اکس", "",
                  "| نماد | قیمت | تغییر ۲۴ ساعته |", "|---|---|---|"]
        for s in syms:
            try:
                j = requests.get("https://www.okx.com/api/v5/market/ticker",
                                 params={"instId": f"{s}-USDT"}, timeout=12).json()
                if j.get("code") == "0" and j.get("data"):
                    d = j["data"][0]
                    px, op = float(d["last"]), float(d["open24h"])
                    ch = (px / op - 1) * 100 if op else 0
                    lines.append(f"| {s} | {px:,.4f} | {ch:+.2f}٪ |")
                else:
                    lines.append(f"| {s} | داده ندارم | — |")
            except Exception:
                lines.append(f"| {s} | داده ندارم | — |")
    except ImportError:
        lines.append("کتابخانه requests نصب نیست.")

    lines += ["", "## پرسش گشایش رادار ۶.۱", "",
              "۱. رژیم امروز کدام است و بودجه ریسکش چقدر؟",
              "۲. از بودجه چقدر مصرف شده؟",
              "۳. **کوچک‌ترین اقدام درست امروز چیست؟**", "",
              "پاسخ سوم هرگز «هیچ کاری» نیست."]

    with open("reports/LATEST.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("ساخته شد: reports/LATEST.md")


def main() -> int:
    ap = argparse.ArgumentParser(description=f"به‌روزرسانی حافظه پروژه — رادار {VERSION}")
    ap.add_argument("--snapshot", action="store_true",
                    help="به‌علاوه ساخت reports/LATEST.md از رابط صرافی")
    a = ap.parse_args()

    if a.snapshot:
        snapshot()

    if not os.path.exists(STATE):
        print(f"{STATE} پیدا نشد. اول آن را از بسته رادار کپی کن.")
        return 1

    with open(STATE, encoding="utf-8") as f:
        text = f.read()
    out = splice(text, build_auto())
    with open(STATE, "w", encoding="utf-8") as f:
        f.write(out)

    print("STATE.md به‌روز شد.")
    print("\nحالا این را بزن تا کلاود ببیندش:")
    print('  git add . ; git commit -m "state" ; git push')
    print("\nسپس در گفتگو فقط بگو: «STATE.md را از مخزن بخوان».")
    return 0


if __name__ == "__main__":
    sys.exit(main())
