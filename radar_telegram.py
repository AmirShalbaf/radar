#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_telegram.py — تنها تابع ارسال تلگرام رادار، نشست ۱۱
==========================================================

پیش از این پایشگر پاسخ تلگرام را نمی‌خواند: کد 400 یا "ok": false بی‌صدا
می‌ماند و فقط استثنای شبکه چاپ می‌شد. حالا هر ارسال رسید دارد.

قرارداد:
- ارسال موفق فقط یعنی کد 200 و "ok": true در پاسخ.
- مخزن عمومی است و لاگ گردش‌کار هم. توکن هرگز چاپ نمی‌شود: فقط کد وضعیت،
  description تلگرام و نوع استثنا. متن استثنای requests گاهی نشانی کامل
  درخواست را دارد و توکن بخشی از همان نشانی است.
- کلید غایب «ارسال ناموفق» نیست؛ یعنی ارسالی نبود — اجرای محلی بی‌کلید.

فقط کتابخانه استاندارد و requests.

خط فرمان — بازبینی ۲۳ اکتبر ۲۰۲۶، یافته م۴: گام تلگرام روزانه و هفتگی هم از همین
تابع می‌فرستند، نه curl بی‌رسید.

    python radar_telegram.py --file /tmp/telegram_daily.txt
    python radar_telegram.py --text "گزارش هفتگی آماده شد"

کد خروج: ۰ موفق یا کلید تنظیم‌نشده، ۴ ناموفق — مثل پایشگر — و ۲ فایل غایب.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import NamedTuple

try:
    import requests
except ImportError:          # بی requests هر ارسال ناموفق است، نه بی‌صدا
    requests = None

TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
CHAT_ENV = "TELEGRAM_CHAT_ID"
API = "https://api.telegram.org/bot{tok}/sendMessage"
TIMEOUT = 15
DESC_MAX = 200               # سقف description در لاگ — پاسخ تلگرام کوتاه است
# سقف متن به نویسه، زیر سقف ۴۰۹۶ تلگرام. پیش از این head -c 3500 به بایت می‌برید و
# حرف فارسی دوبایتی را نصف می‌کرد
MAX_CHARS = 3500
RC_FAILED = 4


class Sent(NamedTuple):
    ok: bool | None          # None یعنی کلید تنظیم نشده و ارسالی نبود
    detail: str              # کد و توضیح، بی توکن


def missing() -> list[str]:
    """نام متغیرهای غایب؛ رشته تهی هم غایب است."""
    return [n for n in (TOKEN_ENV, CHAT_ENV) if not os.getenv(n)]


def send(text: str) -> Sent:
    """یک پیام متن ساده. رسید: موفق، ناموفق با کد، یا بی‌کلید."""
    tok, chat = os.getenv(TOKEN_ENV), os.getenv(CHAT_ENV)
    if not (tok and chat):
        return Sent(None, f"کلید تلگرام تنظیم نشده: {', '.join(missing())}")
    if requests is None:
        return Sent(False, "requests نصب نیست")
    try:
        r = requests.post(API.format(tok=tok), data={"chat_id": chat, "text": text},
                          timeout=TIMEOUT)
    except Exception as exc:          # فقط نوع — متن استثنا ممکن است نشانی با توکن باشد
        return Sent(False, f"خطای شبکه: {type(exc).__name__}")
    try:
        js = r.json()
    except ValueError:
        js = {}
    if not isinstance(js, dict):
        js = {}
    if r.status_code == 200 and js.get("ok") is True:
        return Sent(True, "کد 200")
    desc = str(js.get("description") or "بی‌توضیح").replace(tok, "***")[:DESC_MAX]
    return Sent(False, f"کد {r.status_code}: {desc}")


def clip(text: str, limit: int = MAX_CHARS) -> str:
    """بریدن به نویسه، با نشانه «…» — هرگز وسط حرف."""
    return text if len(text) <= limit else text[:limit - 1] + "…"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ارسال تلگرام با رسید — رادار")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="متن پیام از این فایل، UTF-8")
    src.add_argument("--text", help="متن پیام")
    a = ap.parse_args(argv)
    if a.file is not None:
        try:
            with open(a.file, encoding="utf-8") as f:
                text = f.read()
        except OSError as exc:
            print(f"⛔ فایل پیام خوانا نیست: {a.file} ({type(exc).__name__})")
            return 2
    else:
        text = a.text
    res = send(clip(text))
    if res.ok:
        print(f"✅ تلگرام ارسال شد — {res.detail}")
        return 0
    if res.ok is None:
        print(f"ℹ️ ارسالی نبود — {res.detail}")
        return 0
    print(f"⛔ ارسال تلگرام ناموفق — {res.detail}")
    return RC_FAILED


if __name__ == "__main__":
    sys.exit(main())
