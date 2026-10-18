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
"""

from __future__ import annotations

import os
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
