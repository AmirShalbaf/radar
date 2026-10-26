#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_context.py — لایه زمینه، بند ۲ متن ۲۰، ۲۷ اکتبر ۲۰۲۶ — فقط نمایش
=======================================================================

سه سری از همان FRED که رادار برای DGS10 و DTWEXBGS می‌خواند — مسیر بی‌کلید
fredgraph.csv و همان تجزیه‌گر radar_fetch3.fred_rows:

    نفت برنت                 DCOILBRENTEU   داده روزانه EIA، ولی هفتگی منتشر می‌شود
    بازده اوراق ۱۰ ساله آمریکا  DGS10         روزانه، یک روز کاری دیرتر
    شاخص دلار، سبد وسیع        DTWEXBGS      روزانه، هفتگی منتشر می‌شود

هر کدام با مقدار، تغییر یک‌هفته‌ای و تاریخ مشاهده. تغییر هفته: آخرین مشاهده در برابر
آخرین مشاهده تا هفت روز پیش از آن — بازده با واحد درصد، بقیه با درصد تغییر. سری‌ای که
آخرین مشاهده‌اش بیش از LAG_DAYS روز پیش است، تأخیر انتشارش را صریح می‌گیرد.

**آزمون‌نشده.** هیچ پرونده امتیاز یا قاعده‌ای این را وارد نمی‌کند؛ ورود به امتیاز رژیم
فقط پس از ک۳۵ — آزمون tests/test_context_layer.py قفلش می‌کند.

    python radar_context.py
    python radar_context.py --section /tmp/context_section.md --line /tmp/context_line.txt

کد ۲ یعنی سری‌ای نیامد؛ بخش و خط با «داده ندارم» همان سری نوشته می‌شوند.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

# تنها منبع اصلی کمک‌تابع رقم فارسی — کپی محلی نگیر
from radar_text import fa

UTC = timezone.utc
# (شناسه FRED، نام، نام کوتاه پیام، واحد مقدار، نوع تغییر: pct درصد تغییر، pp واحد درصد)
SERIES = (
    ("DCOILBRENTEU", "نفت برنت", "برنت", "دلار در بشکه", "pct"),
    ("DGS10", "بازده اوراق ۱۰ ساله آمریکا", "بازده ۱۰ ساله", "٪", "pp"),
    ("DTWEXBGS", "شاخص دلار، سبد وسیع", "شاخص دلار", "", "pct"),
)
WEEK = timedelta(days=7)
# بیش از این فاصله تا آخرین مشاهده یعنی تأخیر انتشار صریح — آخر هفته و تعطیلی یک‌روزه نه
LAG_DAYS = 3
UNTESTED = ("لایه زمینه آزمون‌نشده است؛ هیچ امتیاز رژیم یا قاعده‌ای از آن نمی‌خواند — "
            "ورود فقط پس از ک۳۵.")


def _http():
    """تابع دریافت متن — آزمون جایش داده ساختگی می‌گذارد."""
    import radar_fetch3 as R
    return R.http_text


def series_row(sid: str, now: datetime, http_text) -> dict:
    """یک سری: مقدار، تاریخ، مقدار هفته پیش و تغییر. نیامد یعنی value خالی با دلیل."""
    import radar_fetch3 as R
    meta = next(s for s in SERIES if s[0] == sid)
    row = {"sid": sid, "name": meta[1], "short": meta[2], "unit": meta[3], "chg_unit": meta[4],
           "value": None, "date": None, "prev": None, "prev_date": None, "chg": None,
           "lag_days": None, "why": None}
    rows = R.fred_rows(sid, http_text)
    if not rows:
        row["why"] = "FRED پاسخ نداد"
        return row
    d, v = rows[-1]
    day = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=UTC)
    row.update(value=v, date=d, lag_days=(now.astimezone(UTC).date() - day.date()).days)
    target = (day - WEEK).strftime("%Y-%m-%d")
    prev = [(dd, vv) for dd, vv in rows[:-1] if dd <= target]
    if prev:
        pd_, pv = prev[-1]
        row.update(prev=pv, prev_date=pd_)
        if meta[4] == "pp":
            row["chg"] = v - pv
        elif pv:
            row["chg"] = 100 * (v / pv - 1)
    return row


def gather(now: datetime, http_text=None) -> list[dict]:
    http_text = http_text or _http()
    return [series_row(s[0], now, http_text) for s in SERIES]


def _value(r: dict) -> str:
    return f"{r['value']:.2f}" + (f" {r['unit']}" if r["unit"] and r["unit"] != "٪" else
                                  r["unit"])


def _chg(r: dict) -> str:
    if r["chg"] is None:
        return "—"
    if r["chg_unit"] == "pp":
        return f"{r['chg']:+.2f} واحد درصد"
    return f"{r['chg']:+.2f}٪"


def render_section(rows: list[dict], now: datetime) -> str:
    o = ["## لایه زمینه — فقط نمایش", ""]
    for r in rows:
        head = f"- {r['name']} ({r['sid']}): "
        if r["value"] is None:
            o.append(head + f"داده ندارم — {r['why']}")
            continue
        line = (head + f"{_value(r)}؛ تغییر هفته: {_chg(r)}"
                + (f" از {r['prev_date']}" if r["prev_date"] else "")
                + f"؛ مشاهده {r['date']}")
        if r["lag_days"] is not None and r["lag_days"] > LAG_DAYS:
            line += f" — تأخیر انتشار {fa(r['lag_days'])} روز"
        o.append(line)
    o += ["", f"منبع: FRED، فدرال‌رزرو سنت‌لوئیس — {now.astimezone(UTC):%Y-%m-%d %H:%M} UTC. "
              + UNTESTED]
    return "\n".join(o)


def render_line(rows: list[dict]) -> str:
    """یک خط کوتاه — اگر بخش کامل از پیام بیفتد، همین بماند."""
    parts = []
    for r in rows:
        if r["value"] is None:
            parts.append(f"{r['short']} داده ندارم")
        else:
            parts.append(f"{r['short']} {r['value']:.2f} ({_chg(r)}، {r['date']})")
    return "🌐 زمینه، فقط نمایش: " + "؛ ".join(parts)


def main(argv: list[str] | None = None, now: datetime | None = None) -> int:
    ap = argparse.ArgumentParser(description="لایه زمینه — فقط نمایش، بند ۲ متن ۲۰")
    ap.add_argument("--section", default=None, help="بخش گزارش روزانه")
    ap.add_argument("--line", default=None, help="یک خط ساده")
    a = ap.parse_args(argv)
    now = now or datetime.now(UTC)
    rows = gather(now, _http())
    sec, line = render_section(rows, now), render_line(rows)
    for path, text in ((a.section, sec), (a.line, line)):
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text + "\n")
    if not a.section:
        print(sec)
    return 2 if any(r["value"] is None for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
