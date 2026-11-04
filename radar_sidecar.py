#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_sidecar.py — سند ماشین‌خوان کنار گزارش‌های رادار، متن ۳۷
================================================================

هر سازنده — اسکن، سبد، سطوح، زمینه — گزارش مارک‌داونش را مثل قبل می‌نویسد و با
کلید `--json` یک سند JSON هم کنارش می‌گذارد. لایه پیام فقط همین سندها و
فایل‌های داده را می‌خواند، هرگز مارک‌داون را. قرارداد: references/brief-contract.md.

دو قاعده:
- مقدار ساده یا تهی. عدد پوچ یا بی‌نهایت، شیء ناشناخته و تاریخ بی‌منطقه تهی
  می‌شوند — «داده ندارم»، نه صفر و نه رشته ساختگی.
- نوشتن اتمی. سند نیمه‌نوشته هرگز جای سند سالم را نمی‌گیرد.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timezone

UTC = timezone.utc


def plain(v):
    """مقدار ساده JSON، یا None برای هر چیز دیگر — بی‌صدا ساخته نمی‌شود."""
    if v is None or isinstance(v, (bool, str)):
        return v
    if isinstance(v, int):
        return int(v)
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    try:                                     # نوع numpy — بی وابستگی مستقیم
        import numbers
        if isinstance(v, numbers.Integral):
            return int(v)
        if isinstance(v, numbers.Real):
            f = float(v)
            return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None
    if isinstance(v, datetime):
        return v.astimezone(UTC).isoformat() if v.tzinfo else None
    return None


def plain_dict(d: dict) -> dict:
    """
    فقط کلیدهای ساده یک ردیف. عدد پوچ با کلیدش می‌ماند و تهی می‌شود — «داده ندارم»
    دیده شود؛ مقدار پیچیده یا ناشناخته کنار می‌رود، نه خراب.
    """
    import numbers
    out = {}
    for k, v in (d or {}).items():
        if isinstance(v, (dict, list, tuple)):
            continue
        p = plain(v)
        if p is not None or v is None or isinstance(v, numbers.Real):
            out[str(k)] = p
    return out


def stamp(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).astimezone(UTC).isoformat(timespec="seconds")


def write_json(path: str, doc: dict) -> None:
    """نوشتن اتمی در همان پوشه، سپس جایگزینی."""
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1, allow_nan=False)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
