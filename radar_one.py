#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_one.py — گرفتن متن یک ویدئو یا شورت مشخص

وقتی نشانی یک ویدئو را داری و نمی‌خواهی کل کانال را جمع کنی.
شورت‌ها معمولاً در خوراک کانال نمی‌آیند، پس این تنها راه گرفتنشان است.

اجرا:
    python radar_one.py https://youtube.com/shorts/XXXX
    python radar_one.py XXXX --lang fa --out one.md
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass

sys.path.insert(0, ".")
try:
    from radar_intake import (extract_claim_candidates, fetch_transcript,
                              fmt_ts, is_boilerplate)
except ImportError:
    print("radar_intake.py باید کنار این فایل باشد.", file=sys.stderr)
    raise


def video_id(raw: str) -> str:
    """شناسه را از هر شکل نشانی یوتیوب بیرون می‌کشد — شورت، watch، یا خام."""
    for pat in (r"/shorts/([\w-]{11})",
                r"[?&]v=([\w-]{11})",
                r"youtu\.be/([\w-]{11})",
                r"/embed/([\w-]{11})",
                r"/live/([\w-]{11})"):
        m = re.search(pat, raw or "")
        if m:
            return m.group(1)
    raw = (raw or "").strip()
    return raw if re.fullmatch(r"[\w-]{11}", raw) else ""


def main() -> int:
    ap = argparse.ArgumentParser(description="متن یک ویدئو یا شورت مشخص")
    ap.add_argument("url", help="نشانی کامل یا شناسه ۱۱ کاراکتری")
    ap.add_argument("--lang", default="fa,en", help="ترتیب زبان، جدا با کاما")
    ap.add_argument("--out", help="ذخیره در فایل به‌جای چاپ")
    ap.add_argument("--min-strength", type=int, default=2, dest="min_strength")
    args = ap.parse_args()

    vid = video_id(args.url)
    if not vid:
        print("شناسه ویدئو پیدا نشد. نشانی را کامل بده.", file=sys.stderr)
        return 1

    langs = [x.strip() for x in args.lang.split(",") if x.strip()]
    print(f"شناسه: {vid} | زبان: {langs}", file=sys.stderr)

    segs, method = fetch_transcript(vid, langs)
    if not segs:
        print(f"متن گرفته نشد: {method}", file=sys.stderr)
        return 2

    cands = extract_claim_candidates(segs, min_strength=args.min_strength)
    body = []
    for s in segs:
        t = (s.get("text") or "").strip()
        if not t:
            continue
        st = s.get("start")
        body.append(f"[{fmt_ts(st)}] {t}" if st is not None else t)

    head = [
        "---",
        f"شناسه ویدئو: {vid}",
        f"نشانی: https://www.youtube.com/watch?v={vid}",
        f"روش استخراج: {method}",
        f"تاریخ جمع‌آوری: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"تعداد کلمه: {sum(len(b.split()) for b in body)}",
        f"نامزد ادعا: {len(cands)}",
        "برچسب معرفتی: نقل‌شده (Reported)",
        "---",
        "",
        "> این متن **داده** نیست. هیچ عددی از آن وارد امتیازدهی نمی‌شود.",
        "> رونویسی خودکار خطا دارد — هر عدد کلیدی باید در ویدئو تأیید شود.",
        "",
        "## نامزدهای ادعا (خودکار — تأییدنشده)",
        "",
    ]
    if cands:
        head += ["| # | زمان | قدرت | دسته | اعداد | متن |",
                 "|---|---|---|---|---|---|"]
        head += [c.to_row() for c in cands]
    else:
        head += ["نامزدی پیدا نشد — یعنی ادعای عددی و تاریخ‌دار داده نشده."]
    head += ["", "---", "", "## متن کامل", ""]

    out = "\n".join(head) + "\n" + "\n".join(body) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"✅ {args.out} — {method} — {len(cands)} نامزد", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
