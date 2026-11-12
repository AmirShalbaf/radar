#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_brief_render.py — نمایش و ارسال پیام صبح رادار، متن ۳۷
================================================================

فقط reports/brief.json را می‌خواند — قرارداد references/brief-contract.md. هیچ فایل
دیگری از رادار را نمی‌شناسد؛ تغییر درون رادار اینجا را نمی‌شکند.

خروجی یک پیام صبح در تلگرام:
  ۱. آلبوم سه تصویر — امروز، سبد و ماشه‌ها، نمودار و درس — با زیرنویس کوتاه حکم.
  ۲. یک پیام HTML بی‌صدا با استنتاج‌ها، ماشه‌ها، کارهای باز، درس و سلامت سیستم،
     و دکمه‌های پیوندی.

زنجیره پشتیبان — هیچ روزی بی پیام:
  تصویر نشد ← حکم به سر پیام HTML می‌رود.  HTML نشد ← متن ساده همان پیام.
  هیچ‌کدام نشد ← کد ۴، و گام پشتیبان گردش‌کار خلاصه قدیمی را می‌فرستد.

اجرا:
    python radar_brief_render.py render --brief reports/brief.json --out /tmp/brief --png
    python radar_brief_render.py send --dir /tmp/brief
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

from radar_text import fa
import radar_telegram as TG

UTC = timezone.utc
TEHRAN = timezone(timedelta(hours=3, minutes=30))
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "assets", "fonts")
FONTS = ((400, "Vazirmatn-FD-Regular.woff2"), (500, "Vazirmatn-FD-Medium.woff2"),
         (700, "Vazirmatn-FD-Bold.woff2"), (900, "Vazirmatn-FD-Black.woff2"))
CARD_W = 1080
MAX_AGE_H = 6.0                 # پیام از سند کهنه‌تر ساخته نمی‌شود — گام پشتیبان می‌فرستد
RC_NOTHING = 4
LRM = "‎"                  # نشانه علامت‌دار در متن راست‌به‌چپ تلگرام جابه‌جا نشود
GMONTHS = ("ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن", "ژوئیه", "اوت",
           "سپتامبر", "اکتبر", "نوامبر", "دسامبر")
E = TG.html_escape


class RenderError(Exception):
    pass


# ═══════════════════════ عدد و زمان ═══════════════════════

def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def num(x, d: int = 0, sign: bool = False, pct: bool = False, usd: bool = False) -> str:
    """عدد فارسی با ٬ و ٫؛ تهی یعنی «—»."""
    if not _num(x):
        return "—"
    s = fa(f"{abs(x):,.{d}f}".replace(",", "٬").replace(".", "٫"))
    if pct:
        s += "٪"
    if usd:
        s += " دلار"
    if x < 0 and round(abs(x), d) > 0:
        s = "−" + s
    elif sign and x > 0 and round(x, d) > 0:
        s = "+" + s
    return s


def price(x) -> str:
    """رقم معنادار قیمت: ارز ارزان چهار رقم اعشار، گران بی‌اعشار."""
    if not _num(x):
        return "—"
    d = 0 if x >= 1000 else 2 if x >= 10 else 3 if x >= 1 else 4
    return num(x, d)


def tnum(x, d=0, sign=False, pct=False, usd=False) -> str:
    """عدد برای متن تلگرام — با نشانه چپ‌به‌راست تا علامت جابه‌جا نشود."""
    s = num(x, d, sign, pct, usd)
    return LRM + s if s[:1] in "+−" else s


def hnum(x, d=0, sign=False, pct=False, usd=False) -> str:
    """عدد برای تصویر — جزیره چپ‌به‌راست."""
    return f'<bdi class="n">{num(x, d, sign, pct, usd)}</bdi>'


def _ts(raw) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else None


def clock(t: datetime) -> str:
    return fa(t.astimezone(TEHRAN).strftime("%H:%M"))


def day_short(t: datetime) -> str:
    import radar_brief as BR            # تبدیل تاریخ تنها از مترجم — یک تعریف
    return BR.day_label(t)


def load(path: str, now: datetime | None = None) -> dict:
    import radar_brief as BR
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as exc:
        raise RenderError(f"{path} خوانا نیست — {type(exc).__name__}") from exc
    errs = BR.validate(doc)
    if errs:
        raise RenderError("سند با قرارداد نمی‌خواند: " + "؛ ".join(errs))
    gen = _ts(doc.get("generated"))
    age = ((now or datetime.now(UTC)) - gen).total_seconds() / 3600 if gen else None
    if age is None or age > MAX_AGE_H:
        raise RenderError(f"سند پیام صبح کهنه است — {fa(f'{age:.0f}') if age is not None else '؟'} ساعت")
    return doc


def S(doc: dict, name: str) -> dict:
    return (doc.get("sections") or {}).get(name) or {"ok": False, "why": "نیست"}


# ═══════════════════════ متن تلگرام ═══════════════════════

KIND_ARROW = {"invalidation": "⛔", "reentry": "🔁", "alert": "🔔", "ladder": "🎯", "target": "✅"}
JUDGE = {"weekly": "بسته هفتگی", "daily": "بسته روزانه", "live": "قیمت زنده"}


def window_text(w: dict) -> str:
    a, b = _ts(w["start"]), _ts(w["end"])
    when = f"{day_short(a)} {clock(a)} تا {clock(b)}"
    return f"{when} خرید تازه نه — {E(w['name'])}"


def caption(doc: dict) -> str:
    v = doc["verdict"]
    lines = [f"<b>☀️ رادار — صبح {E(doc['day'])}</b>", f"<b>{E(v['headline'])}</b>"]
    for t in v.get("must") or []:
        lines.append(f"🔴 {E(t)}")
    for t in (v.get("overdue") or [])[:2]:
        lines.append(f"🟠 {E(t)}")
    for w in v.get("windows") or []:
        lines.append(f"⏰ {window_text(w)}")
    # متن ۳۹: «·» کنار رقم فارسی مثل صفر خوانده می‌شد — شماره تصویر با حرف
    lines.append("<i>تصویر یک: امروز؛ تصویر دو: سبد و ماشه‌ها؛ تصویر سه: نمودار و درس</i>")
    # نشانه راست‌به‌چپ سر هر سطر — متن ۳۸؛ طول با نشانه سنجیده می‌شود
    out = TG.rtl("\n".join(lines))
    while len(out) > TG.CAPTION_MAX and len(lines) > 3:
        lines.pop(-2)
        out = TG.rtl("\n".join(lines))
    return out


def _infer_lines(doc: dict) -> list[str]:
    out = []
    w = S(doc, "winds")
    if w["ok"]:
        worst = w["items"][0] if w["items"] and w["items"][0]["dir"] < 0 else None
        s = f"• <b>بادها:</b> {fa(w['neg'])} مخالف، {fa(w['neu'])} خنثی، {fa(w['pos'])} موافق"
        if worst:
            s += f" — قوی‌ترین مخالف: {E(worst['label'])}"
        out.append(s)
    m = S(doc, "market")
    if m["ok"] and m.get("crowd_n"):
        top = m["crowd"][0]
        out.append(f"• <b>جمعیت در برابر نهنگ:</b> در {fa(m['crowd_flagged'])} از {fa(m['crowd_n'])} ارز "
                   f"حساب‌های کوچک لانگ‌ترند و معامله‌گران بزرگ نه. بیشترین {E(top['symbol'])}: "
                   f"{tnum(top['crowd'], 1)} در برابر {tnum(top['whale'], 1)}")
    t = S(doc, "trade")
    if t["ok"]:
        if t.get("levels_candidates"):
            out.append("• <b>اسکنر سطح:</b> نامزد نزدیک حمایت: " + "، ".join(E(s) for s in t["levels_candidates"]))
        elif t.get("levels_known"):
            out.append("• <b>اسکنر سطح:</b> هیچ ارزی نزدیک حمایت با نسبت سود به ضرر کافی نیست؛ "
                       "امروز ورود لازم نیست")
        if t.get("pump_cards") is not None:
            # کارت آزمون‌نشده با نماد و جهت، نه «آماده» — متن ۳۸
            cl = t.get("pump_card_list") or []
            names = "، ".join(f"{E(c['symbol'])} {E(c.get('side_label') or '')}".strip()
                              for c in cl[:4])
            out.append(f"• <b>اسکنر پامپ:</b> کارت آزمون‌نشده {fa(t['pump_cards'])}"
                       + (f" — {names}" if names else "") + " — مجوز ورود نیست، اول تحلیلگر صبح؛ "
                       f"نامزد شورت {fa(t['pump_short'])}؛ پس از پامپ {fa(t['pump_after'])}")
    c = S(doc, "context")
    if c["ok"]:
        parts = []
        for r in c["rows"]:
            if not _num(r.get("value")):
                continue
            chg = ""
            if _num(r.get("chg")):
                chg = f"، هفته {tnum(r['chg'], 1 if r.get('chg_unit') == 'pct' else 2, sign=True, pct=r.get('chg_unit') == 'pct')}"
            lag = f"، داده {fa(r['lag_days'])} روز پیش" if _num(r.get("lag_days")) and r["lag_days"] > 3 else ""
            parts.append(f"{E(r['short'])} {num(r['value'], 2)}{chg}{lag}")
        if parts:
            out.append("• <b>زمینه، فقط نمایش:</b> " + "؛ ".join(parts))
    return out


# شرط ماشه وقتی قیمت در این سمت سطح است برقرار است — invalidation بسته زیر، reentry بسته بالا
MET_SIDE = {"invalidation": "below", "reentry": "above"}


def trigger_gap(x: dict) -> tuple[str, float, bool]:
    """
    (سمت قیمت نسبت به سطح، فاصله درصد بی‌علامت، شرط همین حالا برقرار؟) — متن ۳۹.

    فاصله همان تعریف radar_brief.drop_pct است، درصد از قیمت — قاعده ۹. از move_pct خود سند
    ساخته می‌شود: drop_pct = −move_pct، چون (قیمت − سطح) / قیمت = ۱ − سطح / قیمت.
    «مانده» با علامت حذف شد: «+۱٫۰٪ مانده» برای ارزی که همین حالا زیر ابطال بود غلط خوانده می‌شد.
    """
    d = -float(x["move_pct"])
    side = "above" if d > 0 else "below" if d < 0 else "at"
    met = MET_SIDE.get(x.get("kind")) == side
    return side, abs(d), met


def gap_text(x: dict, num_fn=None) -> str:
    """«قیمت ۴٫۸٪ بالای سطح» یا «قیمت ۱٫۰٪ زیر سطح» — بی‌علامت، یک‌جهته."""
    num_fn = num_fn or tnum
    side, pct, _ = trigger_gap(x)
    if side == "at":
        return "قیمت روی سطح"
    return f"قیمت {num_fn(pct, 1, pct=True)} {'بالای' if side == 'above' else 'زیر'} سطح"


def _trigger_lines(doc: dict, k: int = 4) -> list[str]:
    t = S(doc, "triggers")
    if not t["ok"]:
        return []
    out = []
    for x in t["items"][:k]:
        judge = JUDGE.get(x["judge"], x["judge"])
        line = (f"{KIND_ARROW.get(x['kind'], '•')} <b>{E(x['symbol'])}</b> {E(x['label'])} در "
                f"{price(x['level'])} — {gap_text(x)}، داوری {judge}")
        if trigger_gap(x)[2]:
            line += f" — ⚠️ شرط همین حالا برقرار است؛ حکم فقط با {judge}"
        out.append(line)
    return out


def message(doc: dict, with_head: bool = False) -> str:
    parts = []
    if with_head:                       # تصویر نرسید: حکم همین‌جا
        parts.append(caption(doc).rsplit("\n", 1)[0])
        parts.append("")
    inf = _infer_lines(doc)
    if inf:
        parts += ["<b>🧠 استنتاج رادار امروز</b>",
                  "<blockquote expandable>" + "\n".join(inf) + "</blockquote>"]
    tr = _trigger_lines(doc)
    if tr:
        parts += ["<b>🎯 نزدیک‌ترین ماشه‌ها</b>", "<blockquote>" + "\n".join(tr) + "</blockquote>"]
    todo = S(doc, "todo")
    if todo["ok"] and todo["items"]:
        icon = {"red": "🔴", "amber": "🟠", "info": "🗓"}
        parts += ["<b>📌 کارهای باز</b>"] + [f"{icon.get(i['level'], '•')} {E(i['text'])}"
                                            for i in todo["items"]]
    les = S(doc, "lesson")
    if les["ok"]:
        body = "\n".join(f"{fa(i + 1)}) {E(p)}" for i, p in enumerate(les.get("points") or []))
        if les.get("practice"):
            body += f"\n🔎 تمرین: {E(les['practice'])}"
        parts += [f"<b>📚 درس امروز: {E(les['title'])}</b>",
                  "<blockquote expandable>" + body + "</blockquote>"]
    parts.append(health_line(doc))
    out = "\n".join(parts)
    if len(TG.rtl(out)) > TG.HTML_MAX:             # بلندترین بخش جمع‌شدنی کوتاه می‌شود
        out = out.replace("<blockquote expandable>" + "\n".join(inf) + "</blockquote>",
                          "<blockquote expandable>" + "\n".join(inf[:2]) + "</blockquote>")
    out = TG.rtl(out)                              # نشانه راست‌به‌چپ سر هر سطر — متن ۳۸
    return out[:TG.HTML_MAX] if len(out) <= TG.HTML_MAX else _plain_cut(out)


def _plain_cut(html: str) -> str:
    """آخرین چاره: بی تگ، بریده — HTML نیمه هرگز فرستاده نمی‌شود."""
    import re
    txt = re.sub(r"<[^>]+>", "", html).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return E(TG.clip(txt, TG.HTML_MAX - 200))


def health_line(doc: dict) -> str:
    h = S(doc, "health")
    if h["ok"]:
        s = f"⚙️ سیستم: {fa(h['count'])} نبض در ۲۴ ساعت"
        if _num(h.get("max_gap_h")):
            s += f"، بیشترین فاصله {num(h['max_gap_h'], 1)} ساعت"
            if _num(h.get("stale_hours")) and h["max_gap_h"] > h["stale_hours"]:
                s += " ⚠️"
    else:
        s = f"⚙️ سیستم: سلامت نبض سنجیده نشد — {E(h.get('why'))}"
    failed = [f for f in doc.get("failed") or [] if f["name"] not in ("lesson",)]
    if failed:
        s += "\n⚠️ داده ندارم: " + "؛ ".join(f"{E(f['title'])} — {E(f['why'])}" for f in failed)
    return s


def plain(doc: dict) -> str:
    """متن ساده پشتیبان — همان محتوا، بی تگ."""
    import re
    html = message(doc, with_head=True)
    txt = re.sub(r"<[^>]+>", "", html)
    return txt.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def buttons(env=os.environ) -> list:
    rows, first = [], []
    desk = env.get("RADAR_DESK_URL", "")
    if desk.startswith("https://"):
        first.append(("📋 میز تحلیلگر", desk))
    repo = env.get("GITHUB_REPOSITORY", "")
    if repo:
        base = f"https://github.com/{repo}/blob/main/reports"
        first.append(("📄 گزارش کامل", f"{base}/LATEST.md"))
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        rows.append([("💼 گزارش سبد", f"{base}/book-{day}.md"), ("📈 اسکن", f"{base}/scan-{day}.md")])
    return ([first] if first else []) + rows


# ═══════════════════════ تصویر ═══════════════════════

def _css() -> str:
    faces = "".join(
        f"@font-face{{font-family:V;src:url('file://{os.path.join(FONT_DIR, f)}');font-weight:{w}}}"
        for w, f in FONTS)
    return faces + """
:root{--bg:#0d141c;--p:#16212c;--p2:#1c2a37;--line:#26384a;--t:#e8eef4;--m:#8fa1b3;
--g:#3ccf7a;--a:#f2b33d;--r:#ff6b5e;--b:#5aa9ff}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:V,sans-serif;background:var(--bg);color:var(--t);direction:rtl;width:1080px}
bdi.n{direction:ltr;unicode-bidi:isolate}
.card{width:1080px;padding:42px 52px 34px;display:flex;flex-direction:column;gap:20px;
background:radial-gradient(1200px 500px at 85% -10%,#173049 0%,transparent 60%),var(--bg)}
.hd{display:flex;justify-content:space-between;align-items:flex-end}
.brand{font-size:44px;font-weight:900}.brand small{font-size:26px;font-weight:500;color:var(--m);margin-right:12px}
.when{text-align:left;color:var(--m);font-size:24px;line-height:1.5}.when b{color:var(--t);font-weight:700}
.sec{font-size:28px;font-weight:900;margin-bottom:12px}.sec span{font-size:22px;font-weight:500;color:var(--m)}
.box{background:var(--p);border:1px solid var(--line);border-radius:26px;padding:22px 28px}
.v-green{background:linear-gradient(135deg,#12392a,#14261f);border-color:#1f6b45}.v-green h1{color:#7ff0ac}
.v-red{background:linear-gradient(135deg,#3d1714,#26120f);border-color:#7a2a24}.v-red h1{color:#ffb3ab}
.v-unknown{background:linear-gradient(135deg,#3a3014,#241e10);border-color:#6b5a2a}.v-unknown h1{color:#ffd27a}
.verdict h1{font-size:40px;font-weight:900;margin-bottom:10px}
.li{display:flex;gap:14px;align-items:flex-start;font-size:25px;line-height:1.55;padding:4px 0}
.li i{font-style:normal;width:34px;flex:none;text-align:center}.li em{font-style:normal;color:var(--m)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.tile{background:var(--p);border:1px solid var(--line);border-radius:24px;padding:18px 24px}
.k{color:var(--m);font-size:22px;font-weight:500}.v{font-size:50px;font-weight:900;line-height:1.15;margin:4px 0}
.s{font-size:21px;color:var(--m);line-height:1.5}
.up{color:var(--g)}.dn{color:var(--r)}.am{color:var(--a)}
.na{color:var(--m);font-size:21px;line-height:1.5}
.chips{display:flex;flex-wrap:wrap;gap:10px}
.chip{font-size:21px;padding:8px 16px;border-radius:999px;background:var(--p2);border:1px solid var(--line)}
.chip.dn{border-color:#6b2c28;background:#2a1715;color:#ffb3ab}.chip.up{border-color:#1f6b45;background:#12261c;color:#9df0bf}
.chip.ne{color:var(--m)}
.row{display:flex;align-items:center;gap:16px;font-size:24px;padding:11px 0;border-bottom:1px solid var(--line)}
.row:last-child{border-bottom:0}
.pill{flex:none;min-width:200px;font-size:21px;font-weight:700;padding:6px 14px;border-radius:12px;background:var(--p2);text-align:center}
.pill.hot{background:#3a2a10;color:#ffd27a}
.tag{margin-right:auto;font-size:19px;padding:4px 12px;border-radius:10px}
.t-high{background:#2a1715;color:#ffb3ab}.t-medium{background:#2b2612;color:#f5d27a}.t-low{background:var(--p2);color:var(--m)}
.foot{font-size:20px;color:var(--m);display:flex;justify-content:space-between}
.sym{direction:ltr;text-align:right;font-weight:900}
"""


def _page(body: str) -> str:
    return f"<!doctype html><html lang=fa><meta charset=utf-8><style>{_css()}</style><body>{body}</body></html>"


def _na(s: dict) -> str:
    return f'<div class="na">داده ندارم — {E(s.get("why"))}</div>'


def _gauge(v: float) -> str:
    cx, cy, r = 115, 108, 86
    segs = ((0, 25, "#ff6b5e"), (25, 45, "#f2913d"), (45, 55, "#c9c9c9"), (55, 75, "#9ad66f"), (75, 100, "#3ccf7a"))
    out = []
    for a, b, c in segs:
        t1, t2 = math.pi * (1 - a / 100), math.pi * (1 - b / 100)
        out.append(f'<path d="M{cx + r * math.cos(t1):.1f},{cy - r * math.sin(t1):.1f} A{r},{r} 0 0 1 '
                   f'{cx + r * math.cos(t2):.1f},{cy - r * math.sin(t2):.1f}" stroke="{c}" stroke-width="18" fill="none"/>')
    t = math.pi * (1 - max(0, min(100, v)) / 100)
    out.append(f'<line x1="{cx}" y1="{cy}" x2="{cx + (r - 6) * math.cos(t):.1f}" y2="{cy - (r - 6) * math.sin(t):.1f}" '
               'stroke="#e8eef4" stroke-width="6" stroke-linecap="round"/>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="9" fill="#e8eef4"/>')
    return f'<svg width="230" height="118" viewBox="0 0 230 118" style="direction:ltr">{"".join(out)}</svg>'


def _regime_bar(score: float) -> str:
    import radar_budget as BG             # جدول باند از خود رادار — تنها منبع
    lo, hi, W = -2.0, 1.5, 440
    x = lambda s: W - (min(max(s, lo), hi) - lo) / (hi - lo) * W     # راست‌به‌چپ: بحرانی راست
    cols = ["#145a3a", "#1f4a33", "#4a4a1c", "#5a3a14", "#5a1f1b"]
    floors = [b[0] for b in BG.BANDS]
    parts, top = [], hi
    for i, f in enumerate(floors):
        bottom = lo if f is None else f
        parts.append(f'<rect x="{x(top):.1f}" y="18" width="{x(bottom) - x(top):.1f}" height="26" '
                     f'fill="{cols[min(i, len(cols) - 1)]}"/>')
        top = bottom
    m = x(score)
    parts.append(f'<polygon points="{m - 11:.1f},6 {m + 11:.1f},6 {m:.1f},22" fill="#f2b33d"/>'
                 f'<rect x="{m - 2:.1f}" y="18" width="4" height="26" fill="#f2b33d"/>')
    return f'<svg width="{W}" height="50" viewBox="0 0 {W} 50" style="direction:ltr">{"".join(parts)}</svg>'


def card_today(doc: dict) -> str:
    v = doc["verdict"]
    items = []
    for t in v.get("must") or []:
        items.append(f'<div class="li"><i>🔴</i><span>{E(t)}</span></div>')
    for t in (v.get("overdue") or [])[:2]:
        items.append(f'<div class="li"><i>🟠</i><span>{E(t)}</span></div>')
    if v.get("setups") is not None:
        # نامزد آزمون‌نشده، نه مجوز — متن ۳۸؛ اول تحلیلگر صبح
        if v["setups"]:
            cs = v.get("candidates")
            st = ("، ".join(f'<bdi class="n"><b>{E(c["symbol"])}</b></bdi> {E(c.get("side_label") or "")}'
                           f' <em>{E(c.get("source_label") or "")}</em>' for c in cs)
                  if cs else "، ".join(E(s) for s in v["setups"]))
            items.append(f'<div class="li"><i>🧪</i><span>نامزد آزمون‌نشده: {st} '
                         f'<em>— مجوز ورود نیست؛ اول تحلیلگر صبح</em></span></div>')
        else:
            items.append('<div class="li"><i>🚫</i><span>نامزد تازه: <b>هیچ</b> '
                         '<em>— «امروز هیچ» هم تصمیم درست است</em></span></div>')
    for w in v.get("windows") or []:
        items.append(f'<div class="li"><i>⏰</i><span>{window_text(w)}</span></div>')
    m, r, w = S(doc, "market"), S(doc, "regime"), S(doc, "winds")
    if m["ok"] and _num(m["btc"]["price"]):
        b = m["btc"]
        sub = []
        if _num(b.get("chg24")):
            # پایه تغییر — متن ۳۸: نبض کهنه یعنی از بسته روزانه ۳:۳۰ تهران، نه ۲۴ ساعت
            span = "از بسته روزانه ۳:۳۰" if b.get("chg24_basis") == "daily_close" else "در ۲۴ ساعت"
            sub.append(f'<span class="{"dn" if b["chg24"] < 0 else "up"}">{hnum(b["chg24"], 1, True, True)}</span> {span}')
        if _num(b.get("rsi")):
            sub.append(f"قدرت نسبی RSI {hnum(b['rsi'])}")
        line2 = ""
        if _num(b.get("above_sma_pct")):
            word = "بالای" if b["above_sma_pct"] >= 0 else "زیر"
            line2 = (f'<br><b class="am">{hnum(abs(b["above_sma_pct"]), 1, pct=True)}</b> {word} '
                     f'میانگین ۵۰ هفته — خط چرخه')
        btc = (f'<div class="k">بیت‌کوین</div><div class="v">{hnum(b["price"])}<span style="font-size:26px"> $</span></div>'
               f'<div class="s">{" · ".join(sub)}{line2}</div>')
    else:
        btc = '<div class="k">بیت‌کوین</div>' + _na(m)
    if m["ok"] and _num(m.get("fear_greed")):
        fgv = m["fear_greed"]
        word = ("ترس شدید" if fgv < 25 else "ترس" if fgv < 45 else "خنثی" if fgv <= 55
                else "طمع" if fgv <= 75 else "طمع شدید")
        cls = "dn" if fgv < 45 else "up" if fgv > 55 else ""
        fg = (f'<div style="display:flex;align-items:center;gap:8px"><div style="flex:1"><div class="k">ترس و طمع</div>'
              f'<div class="v {cls}">{hnum(fgv)}</div><div class="s">{word} — به‌تنهایی سیگنال نیست</div></div>'
              f'{_gauge(fgv)}</div>')
    else:
        fg = '<div class="k">ترس و طمع</div>' + _na(m)
    if r["ok"]:
        gaps = []
        if r.get("up"):
            gaps.append(f"تا «{E(r['up']['name'])}» {hnum(r['up']['gap'], 2)}")
        if r.get("down"):
            gaps.append(f"تا «{E(r['down']['name'])}» {hnum(r['down']['gap'], 2)}")
        pil = "".join(f'<div class="li" style="font-size:21px;padding:1px 0"><span style="flex:1">{E(p["label"])}</span>'
                      f'{hnum(p["score"], 2)}</div>' for p in r.get("pillars") or [] if _num(p.get("score")))
        reg = (f'<div class="k">رژیم رادار</div><div class="v am" style="font-size:42px">{hnum(r["score"], 2)} '
               f'<span style="font-size:28px">{E(r["band"])}</span></div>{_regime_bar(r["score"])}'
               f'<div style="display:flex;justify-content:space-between;width:440px;font-size:17px;color:var(--m)">'
               f'<span>بحرانی</span><span>انبساطی</span></div><div class="s">{" · ".join(gaps)}</div>{pil}')
    else:
        reg = '<div class="k">رژیم رادار</div>' + _na(r)
    if m["ok"] and (_num(m.get("btc_dominance")) or _num(m.get("stable_30d"))):
        place = '<div class="k">جای پول در بازار</div>'
        if _num(m.get("btc_dominance")):
            place += (f'<div class="v" style="font-size:42px">{hnum(m["btc_dominance"], 1, pct=True)} '
                      f'<span style="font-size:23px;color:var(--m)">تسلط بیت‌کوین</span></div>'
                      f'<div class="s">بالای ۵۸٪ یعنی آلت‌کوین‌ها معمولاً عقب‌ترند</div>')
        if _num(m.get("stable_30d")):
            c = "dn" if m["stable_30d"] < 0 else "up"
            place += (f'<div class="v {c}" style="font-size:38px;margin-top:8px">{hnum(m["stable_30d"], 1, True, True)} '
                      f'<span style="font-size:23px;color:var(--m)">استیبل‌کوین ۳۰ روز</span></div>'
                      f'<div class="s">{"پول نقد کریپتو کم شده — سوخت خرید کمتر" if m["stable_30d"] < 0 else "پول نقد تازه وارد شده"}</div>')
    else:
        place = '<div class="k">جای پول در بازار</div>' + _na(m)
    if w["ok"]:
        chips = "".join(
            f'<div class="chip {"dn" if x["dir"] < 0 else "up" if x["dir"] > 0 else "ne"}">'
            f'{"⬇" if x["dir"] < 0 else "⬆" if x["dir"] > 0 else "➖"} {E(x["label"])}</div>' for x in w["items"])
        winds = (f'<div class="box"><div class="sec">🧭 بادها <span>— {fa(w["neg"])} مخالف · {fa(w["neu"])} خنثی · '
                 f'{fa(w["pos"])} موافق، از ورودی‌های مدل رژیم</span></div><div class="chips">{chips}</div></div>')
    else:
        winds = f'<div class="box"><div class="sec">🧭 بادها</div>{_na(w)}</div>'
    cal = S(doc, "calendar")
    if cal["ok"] and cal["items"]:
        imp = {"high": "اثر بالا", "medium": "اثر میانه", "low": "اثر کم"}
        rows = []
        today = datetime.now(UTC).astimezone(TEHRAN).date()
        for e in cal["items"]:
            at = _ts(e["at"]) if e.get("at") else None
            if at:
                when = f"{day_short(at)} · {clock(at)}"
                hot = at.astimezone(TEHRAN).date() <= today + timedelta(days=3)
            else:
                d = datetime.fromisoformat(e["date"] + "T12:00:00+00:00")
                when = "امروز" if d.astimezone(TEHRAN).date() == today else day_short(d)
                hot = d.astimezone(TEHRAN).date() <= today + timedelta(days=3)
            rows.append(f'<div class="row"><div class="pill{" hot" if hot else ""}">{when}</div><span>{E(e["name"])}</span>'
                        f'<span class="tag t-{E(e.get("importance") or "low")}">{imp.get(e.get("importance"), "")}</span></div>')
        calbox = f'<div class="box" style="padding:12px 26px">{"".join(rows)}</div>'
    else:
        calbox = f'<div class="box">⏰ تقویم {_na(cal) if not cal["ok"] else "<div class=na>رویداد مهمی در ۱۰ روز آینده ثبت نشده</div>"}</div>'
    h = S(doc, "health")
    sysline = (f"⚙️ سیستم: {fa(h['count'])} نبض در ۲۴ ساعت" + (" ⚠️" if _num(h.get("max_gap_h")) and _num(h.get("stale_hours")) and h["max_gap_h"] > h["stale_hours"] else "")
               if h["ok"] else "⚙️ سلامت سیستم سنجیده نشد")
    return _page(f"""<div class="card">
 <div class="hd"><div class="brand">🛡️ رادار<small>گزارش صبح</small></div>
  <div class="when"><b>{E(doc['day'])}</b><br>{E(doc['clock'])} تهران</div></div>
 <div class="box verdict v-{v['level']}"><h1>{E(v['headline'])}</h1>{''.join(items)}</div>
 <div><div class="sec">🌡 هوای بازار</div>
  <div class="grid"><div class="tile">{btc}</div><div class="tile">{fg}</div>
   <div class="tile">{reg}</div><div class="tile">{place}</div></div></div>
 {winds}
 {calbox}
 <div class="foot"><span>۱ از ۳</span><span>{sysline}</span></div>
</div>""")


def card_book(doc: dict) -> str:
    c, p, t, tr, sc = (S(doc, n) for n in ("capital", "positions", "trade", "triggers", "scorecard"))
    if c["ok"]:
        palette = ["#2fc7b5", "#8a7dff", "#5aa9ff", "#4fd1ff", "#b07cff", "#f29ad8", "#9ad66f", "#f2b33d"]
        seg = "".join(f'<div style="width:{a["pct"]:.2f}%;background:{palette[i % len(palette)]};height:100%"></div>'
                      for i, a in enumerate(c["assets"]))
        leg = "".join(f'<span style="display:inline-flex;align-items:center;gap:8px;margin-left:20px">'
                      f'<i style="width:16px;height:16px;border-radius:5px;background:{palette[i % len(palette)]};display:inline-block"></i>'
                      f'{"تتر" if a["symbol"] == "USDT" else E(a["symbol"])} {hnum(a["pct"], 1, pct=True)}</span>'
                      for i, a in enumerate(c["assets"]))
        tgt = c.get("target_pct")
        marker = (f'<div style="position:relative;height:30px"><div style="position:absolute;right:{tgt}%;top:-44px;height:50px;'
                  f'border-right:3px dashed #ffd27a"></div><div style="position:absolute;right:calc({tgt}% - 160px);top:6px;'
                  f'width:320px;text-align:center;font-size:19px;color:#ffd27a">هدف ذخیره رژیم: دست‌کم {hnum(tgt)}٪</div></div>'
                  if _num(tgt) else "")
        capbox = (f'<div class="box"><div style="height:40px;border-radius:12px;overflow:hidden;display:flex">{seg}</div>'
                  f'{marker}<div style="font-size:21px;color:var(--m);margin-top:6px">{leg}</div></div>')
        head = (f'<b>کل سرمایه {hnum(c["total"])} دلار</b><br>ریسک تا ابطال {hnum(c.get("pos_risk_usd"))} دلار — '
                f'{hnum(c.get("pos_risk_pct"), 1, pct=True)} سرمایه')
    else:
        capbox, head = f'<div class="box">{_na(c)}</div>', "سرمایه — داده ندارم"
    if p["ok"] and p["rows"]:
        col = {"red": "var(--r)", "amber": "var(--a)", "green": "var(--g)", "none": "var(--m)"}
        rows = []
        for r in p["rows"]:
            d = r.get("drop_pct")
            bar = (f'<div style="flex:1;height:22px;background:var(--p2);border-radius:11px;overflow:hidden">'
                   f'<div style="width:{min(max(d, 0) / 25, 1) * 100:.1f}%;height:100%;background:{col[r["tier"]]};border-radius:11px"></div></div>'
                   f'<b style="width:110px;color:{col[r["tier"]]}">{hnum(-d, 1, pct=True)}</b>' if _num(d)
                   else '<span class="na" style="flex:1">سطح ابطال ندارد</span>')
            wk = r.get("week_chg_pct")
            rows.append(f'<div class="row"><span class="sym" style="width:110px;font-size:28px">{E(r["symbol"])}</span>'
                        f'<span style="width:110px">{hnum(r.get("value"))}$</span>'
                        f'<span style="width:120px" class="{"dn" if _num(wk) and wk < 0 else "up"}">{hnum(wk, 1, True, True)}</span>'
                        f'<div style="flex:1;display:flex;align-items:center;gap:14px">{bar}</div></div>')
        posbox = (f'<div class="box"><div class="sec">🛡 هر ارز تا سطح ابطال <span>— افت لازم تا فروش</span></div>'
                  f'<div class="row" style="font-size:19px;color:var(--m);padding:4px 0"><span style="width:110px">ارز</span>'
                  f'<span style="width:110px">ارزش</span><span style="width:120px">این هفته</span><span style="flex:1">فاصله تا ابطال</span></div>'
                  f'{"".join(rows)}<div style="font-size:20px;color:var(--m);margin-top:8px">🟢 بیش از ۱۰٪ · 🟠 ۳ تا ۱۰٪ · 🔴 زیر ۳٪ — '
                  f'حکم فقط با {E(p.get("judge"))}</div></div>')
    else:
        posbox = f'<div class="box"><div class="sec">🛡 سبد</div>{_na(p) if not p["ok"] else "<div class=na>موقعیت بازی نیست</div>"}</div>'
    if tr["ok"]:
        lines = []
        span = max(10.0, max(abs(x["move_pct"]) for x in tr["items"]))
        for x in tr["items"]:
            # متن ۳۹: میله جای قیمت است — راست یعنی بالای سطح، چپ یعنی زیر آن؛ رنگ فقط وقتی
            # شرط ماشه همین حالا برقرار است، وگرنه خاکستری
            side, gp, met = trigger_gap(x)
            colr = ("var(--r)" if x.get("kind") == "invalidation" else "var(--g)") if met else "var(--m)"
            w = gp / span * 50
            barpos = "left:50%" if side == "above" else "right:50%"
            lines.append(f'<div style="display:flex;align-items:center;gap:16px;padding:8px 0;font-size:23px">'
                         f'<span class="sym" style="width:80px">{E(x["symbol"])}</span>'
                         f'<span style="width:430px">{E(x["label"])} در {price(x["level"])}<br>'
                         f'<em style="font-style:normal;color:var(--m);font-size:19px">داوری: {JUDGE.get(x["judge"], x["judge"])}</em></span>'
                         f'<div style="flex:1;position:relative;height:26px;direction:ltr;border-left:2px solid transparent">'
                         f'<div style="position:absolute;left:50%;top:-6px;bottom:-6px;border-left:2px solid #44566a"></div>'
                         f'<div style="position:absolute;top:0;bottom:0;{barpos};width:{w:.1f}%;background:{colr};border-radius:8px;opacity:.85"></div></div>'
                         f'<b style="width:170px;color:{colr}">{"روی سطح" if side == "at" else hnum(gp, 1, False, True) + (" بالای سطح" if side == "above" else " زیر سطح")}</b></div>')
        trbox = f'<div class="box"><div class="sec">🎯 نقشه ماشه‌ها <span>— قیمت کجای سطح است</span></div>{"".join(lines)}</div>'
    else:
        trbox = f'<div class="box"><div class="sec">🎯 ماشه‌ها</div>{_na(tr)}</div>'
    if t["ok"]:
        used = t.get("risk_used_usd")
        tradetile = (f'<div class="tile"><div class="k">💵 دفتر معامله امروز</div>'
                     f'<div class="v" style="font-size:36px">مصرف {hnum(used)} از {hnum(t.get("risk_cap_usd"))}$</div>'
                     f'<div class="s">اندازه {hnum(t.get("mult"), 2)} برابر · حداکثر {hnum(t.get("maxpos"))} معامله هم‌جهت<br>'
                     f'نامزد آزمون‌نشده: {hnum(t.get("setups_ready"))} — اول تحلیلگر</div></div>')
    else:
        tradetile = f'<div class="tile"><div class="k">💵 دفتر معامله</div>{_na(t)}</div>'
    if sc["ok"]:
        lines = []
        for e in sc["exits"][:2]:
            if _num(e.get("now")) and _num(e.get("saved_usd")):
                good = e["saved_usd"] >= 0
                lines.append(f'فروش {E(e["symbol"])} در {price(e["price"])} ← الان {price(e["now"])}<br>'
                             f'<b class="{"up" if good else "dn"}">{"تا اینجا درست" if good else "تا اینجا زود بود"} · '
                             f'حدود {hnum(abs(e["saved_usd"]))}$ {"جلو" if good else "عقب"}</b>')
        for f in sc["forecasts_open"][:1]:
            if f.get("top"):
                lines.append(f'<span style="color:var(--m)">پیش‌بینی باز {E(f["symbol"])}: «{E(f["top"]["name"])}» '
                             f'{hnum((f["top"].get("p") or 0) * 100)}٪</span>')
        if _num(sc.get("brier_mean")):
            lines.append(f'<span style="color:var(--m)">نمره پیش‌بینی‌ها: {hnum(sc["scored_n"])} مورد، Brier {hnum(sc["brier_mean"], 2)}</span>')
        body = "<br>".join(lines) if lines else "تصمیم تازه‌ای برای داوری نیست"
        sctile = f'<div class="tile"><div class="k">🧾 کارنامه تصمیم</div><div class="s" style="color:var(--t);font-size:22px;line-height:1.6">{body}</div></div>'
    else:
        sctile = f'<div class="tile"><div class="k">🧾 کارنامه</div>{_na(sc)}</div>'
    at = _ts(c.get("prices_at")) if c["ok"] else None
    return _page(f"""<div class="card">
 <div class="hd"><div class="brand">💼 سبد و ماشه‌ها</div><div class="when">{head}</div></div>
 {capbox}{posbox}{trbox}
 <div class="grid">{tradetile}{sctile}</div>
 <div class="foot"><span>۲ از ۳</span><span>قیمت‌ها: {clock(at) + " تهران" if at else "—"}</span></div>
</div>""")


def _chart_svg(s: dict, w: int = 976, h: int = 330, color: str = "#f2913d") -> str:
    pts = [(_ts(t), v) for t, v in s.get("points") or [] if _num(v)]
    pts = [(t, v) for t, v in pts if t is not None]
    if len(pts) < 10:
        return '<div class="na">داده نمودار کافی نیست</div>'
    lvls = [l for l in s.get("levels") or [] if _num(l.get("value"))]
    vals = [v for _, v in pts] + [l["value"] for l in lvls]
    lo, hi = min(vals) * 0.985, max(vals) * 1.01
    t0, t1 = pts[0][0], pts[-1][0]
    span = (t1 - t0).total_seconds() or 1
    X = lambda t: 70 + (t - t0).total_seconds() / span * (w - 90)
    Y = lambda v: 20 + (hi - v) / (hi - lo) * (h - 60)
    d = "M" + " L".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in pts)
    area = d + f" L{X(t1):.1f},{h - 40} L{X(t0):.1f},{h - 40} Z"
    g, top = [], []
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        lab = fa(f"{v / 1000:.0f}k") if hi >= 10000 else fa(f"{v:.0f}") if hi >= 10 else fa(f"{v:.3f}")
        g.append(f'<line x1="70" x2="{w - 20}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#22303e"/>'
                 f'<text x="62" y="{Y(v) + 6:.1f}" fill="#7d8b99" font-size="17" text-anchor="end">{lab}</text>')
    m = datetime(t0.year, t0.month, 1, tzinfo=UTC)
    while m <= t1:
        if m >= t0:
            g.append(f'<text x="{X(m):.1f}" y="{h - 12}" fill="#7d8b99" font-size="17" text-anchor="middle">'
                     f'۱ {GMONTHS[m.month - 1]}</text>')
        m = datetime(m.year + (m.month == 12), m.month % 12 + 1, 1, tzinfo=UTC)
    colors = {"sma": "#ffd27a", "invalidation": "#ff6b5e", "reentry": "#5aa9ff", "alert": "#3ccf7a",
              "ladder": "#4fd1ff", "target": "#3ccf7a"}
    lvls_sorted = sorted(lvls, key=lambda l: -l["value"])
    for i, l in enumerate(lvls_sorted):
        c = colors.get(l.get("kind"), "#ffd27a")
        dy = -11 if i % 2 == 0 else 26
        top.append(f'<line x1="70" x2="{w - 20}" y1="{Y(l["value"]):.1f}" y2="{Y(l["value"]):.1f}" stroke="{c}" '
                   f'stroke-width="2.5" stroke-dasharray="10 7"/><text x="{w * 0.56:.0f}" y="{Y(l["value"]) + dy:.1f}" '
                   f'fill="{c}" font-size="21" font-weight="700" text-anchor="middle" paint-order="stroke" '
                   f'stroke="#16212c" stroke-width="8">{E(l["label"])} · {price(l["value"])}</text>')
    for mk in s.get("marks") or []:
        t = _ts(mk.get("at"))
        if t and t0 <= t <= t1 and _num(mk.get("value")):
            top.append(f'<circle cx="{X(t):.1f}" cy="{Y(mk["value"]):.1f}" r="9" fill="#ffd27a" stroke="#0d141c" stroke-width="3"/>'
                       f'<text x="{X(t) - 16:.1f}" y="{Y(mk["value"]) + 36:.1f}" fill="#ffd27a" font-size="20" font-weight="700" '
                       f'text-anchor="end" paint-order="stroke" stroke="#16212c" stroke-width="8">{E(mk.get("label") or "")} {price(mk["value"])}</text>')
    top.append(f'<circle cx="{X(t1):.1f}" cy="{Y(pts[-1][1]):.1f}" r="7" fill="{color}"/>')
    gid = "g" + color[1:]
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="direction:ltr;font-family:V">'
            f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{color}" stop-opacity=".28"/>'
            f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>{"".join(g)}'
            f'<path d="{area}" fill="url(#{gid})"/><path d="{d}" fill="none" stroke="{color}" stroke-width="3.5" '
            f'stroke-linejoin="round"/>{"".join(top)}</svg>')


def card_chart(doc: dict) -> str | None:
    ch, les = S(doc, "chart"), S(doc, "lesson")
    if not ch["ok"] and not les["ok"]:
        return None
    boxes = []
    if ch["ok"]:
        cols = ["#f2913d", "#b07cff"]
        for i, s in enumerate(ch["series"][:2]):
            last = s["points"][-1][1] if s.get("points") else None
            boxes.append(f'<div class="box" style="padding:18px 22px"><div class="sec" style="margin-bottom:4px">'
                         f'<span class="sym" style="font-size:28px;color:var(--t)">{E(s["symbol"])}</span> '
                         f'<span>— الان {price(last)}</span></div>{_chart_svg(s, color=cols[i % 2])}</div>')
    else:
        boxes.append(f'<div class="box"><div class="sec">📈 نمودار</div>{_na(ch)}</div>')
    if les["ok"]:
        pts = "".join(f'<div class="li" style="font-size:24px"><i>{"①②③④⑤"[i]}</i><span>{E(p)}</span></div>'
                      for i, p in enumerate((les.get("points") or [])[:5]))
        pr = (f'<div class="li" style="font-size:22px;color:var(--m)"><i>🔎</i><span>تمرین: {E(les["practice"])}</span></div>'
              if les.get("practice") else "")
        boxes.append(f'<div class="box" style="background:linear-gradient(135deg,#1b2440,#161f33);border-color:#33407a">'
                     f'<div class="sec">📚 درس امروز: {E(les["title"])}</div>{pts}{pr}</div>')
    return _page(f"""<div class="card" style="gap:18px">
 <div class="hd"><div class="brand">📈 نمودار و درس روز</div><div class="when"><b>{fa(ch.get('days', 90))} روز اخیر</b><br>بسته روزانه وقت جهانی</div></div>
 {''.join(boxes)}
 <div class="foot"><span>۳ از ۳</span><span>نمودار: اوکی‌اکس، سپس گیت</span></div>
</div>""")


def cards(doc: dict) -> list[tuple[str, str]]:
    out = [("card1", card_today(doc)), ("card2", card_book(doc))]
    c3 = card_chart(doc)
    if c3:
        out.append(("card3", c3))
    return out


def to_png(html_paths: list[str], png_paths: list[str]) -> list[str]:
    """کروم نصب‌شده رانر اول، سپس کرومیوم خود playwright. هر شکست صریح."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RenderError("playwright نصب نیست") from exc
    done, errs = [], []
    with sync_playwright() as p:
        browser = None
        for kw in ({"channel": "chrome"}, {}):
            try:
                browser = p.chromium.launch(**kw)
                break
            except Exception as exc:
                errs.append(f"{kw or 'chromium'}: {type(exc).__name__}")
        if browser is None:
            raise RenderError("مرورگر بالا نیامد — " + "؛ ".join(errs))
        try:
            page = browser.new_page(viewport={"width": CARD_W, "height": 900}, device_scale_factor=1)
            for h, o in zip(html_paths, png_paths):
                page.goto("file://" + os.path.abspath(h))
                page.evaluate("document.fonts.ready.then(() => true)")
                page.wait_for_timeout(150)
                page.screenshot(path=o, full_page=True)
                done.append(o)
        finally:
            browser.close()
    return done


# ═══════════════════════ خط فرمان ═══════════════════════

def render(brief: str, out: str, png: bool, now: datetime | None = None) -> int:
    doc = load(brief, now)
    os.makedirs(out, exist_ok=True)
    files = {"caption.html": caption(doc), "message.html": message(doc),
             "message_head.html": message(doc, with_head=True), "plain.txt": plain(doc),
             "buttons.json": json.dumps(buttons(), ensure_ascii=False)}
    for name, text in files.items():
        with open(os.path.join(out, name), "w", encoding="utf-8") as f:
            f.write(text)
    htmls = []
    for name, html in cards(doc):
        p = os.path.join(out, f"{name}.html")
        with open(p, "w", encoding="utf-8") as f:
            f.write(html)
        htmls.append(p)
    print(f"✅ متن و {fa(len(htmls))} کارت HTML در {out}")
    if png:
        try:
            got = to_png(htmls, [h[:-5] + ".png" for h in htmls])
            print(f"✅ {fa(len(got))} تصویر ساخته شد")
        except Exception as exc:                 # بی تصویر هم پیام می‌رود — بلند، نه بلعیده
            print(f"⚠️ تصویر ساخته نشد — {type(exc).__name__}: {str(exc)[:200]}")
    return 0


def send(out: str) -> int:
    def read(name):
        with open(os.path.join(out, name), encoding="utf-8") as f:
            return f.read()
    try:
        cap, msg, head, txt = (read(n) for n in ("caption.html", "message.html", "message_head.html", "plain.txt"))
        btn = json.loads(read("buttons.json"))
    except (OSError, ValueError) as exc:
        print(f"⛔ پوشه پیام خوانا نیست — {type(exc).__name__}")
        return RC_NOTHING
    pngs = sorted(os.path.join(out, f) for f in os.listdir(out) if f.startswith("card") and f.endswith(".png"))
    photos = TG.send_photos(pngs, cap) if pngs else TG.Sent(False, "تصویری ساخته نشد")
    if photos.ok is None:
        print(f"ℹ️ ارسالی نبود — {photos.detail}")
        return 0
    print(("✅ آلبوم تصویر رسید — " if photos.ok else "⚠️ آلبوم تصویر نرسید — ") + photos.detail)
    body = msg if photos.ok else head
    res = TG.send_html(body, buttons=btn, silent=bool(photos.ok))
    if res.ok:
        print(f"✅ پیام HTML رسید — {res.detail}")
        return 0
    print(f"⚠️ پیام HTML نرسید — {res.detail}")
    fb = TG.send(TG.clip(txt))
    if fb.ok:
        print(f"✅ متن ساده پشتیبان رسید — {fb.detail}")
        return 0
    print(f"⛔ متن ساده هم نرسید — {fb.detail}")
    return 0 if photos.ok else RC_NOTHING


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="نمایش و ارسال پیام صبح رادار — متن ۳۷")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("render")
    p.add_argument("--brief", default="reports/brief.json")
    p.add_argument("--out", default="/tmp/brief")
    p.add_argument("--png", action="store_true")
    p = sp.add_parser("send")
    p.add_argument("--dir", default="/tmp/brief", dest="out")
    a = ap.parse_args(argv)
    try:
        return render(a.brief, a.out, a.png) if a.cmd == "render" else send(a.out)
    except RenderError as exc:
        print(f"⛔ {exc}")
        return RC_NOTHING


if __name__ == "__main__":
    sys.exit(main())
