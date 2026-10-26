#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_rebuy.py — بازخرید با انتخاب کیفی، بند ۳ متن ۱۸
=====================================================

تصمیم کاربر، ۲۵ اکتبر ۲۰۲۶: «مقدار از رژیم، انتخاب با کیفیت». جانشین «بازخرید فقط همان
ارزهای فروخته‌شده» در رویداد ۱۰۳. رادار فقط پیشنهاد می‌دهد؛ تصمیم با کاربر.

    بودجه    وقتی باند با هیسترزیس — سه روز پیاپی، ک۳۲ — به باندی با هدف ذخیره پایین‌تر
             رسید: ذخیره فعلی منهای هدف تازه × کل سرمایه. «رسید» یعنی آخرین تغییر سری
             trade_band در regime_history.json رو به هدف پایین‌تر بوده.
    سهمیه    برای هر پله rebuy هر نقشه، فعال و بایگانی: فروخته‌شده منهای بازخریده‌شده —
             radar_watch.rebuy_status، تنها تعریف. فروش نقشه بایگانی فقط تا زمان بستنش.
    نامزد    ارزهای دارای سهمیه باز، و فهرست پایش — radar_scan PRESETS["watch"]. BTC معیار
             قدرت نسبی است و نامزد نیست. کارت اسکنر پامپ نامزد نیست، تا بازبینی دوهفته‌ای
             اسکنر خلافش را نشان دهد.
    پذیرش    قیمت بالای سطح ابطال؛ نه زیر ناحیه ارزش ۱۵ روزه؛ قدرت نسبی ۳۰ روزه به BTC نه
             در یک‌سوم پایین فهرست پایش.
    رتبه     قدرت نسبی ۳۰ روزه — همان score_position سبد که ترتیب فروش بخش ۵ را می‌سازد.
             ارز بی‌سهمیه فقط با دست‌کم ۵ واحد درصد قدرت نسبی بیشتر جای ارز دارای سهمیه را
             می‌گیرد؛ فقط در هم‌ترازی، ترتیب عکس فروش: فروش تازه‌تر اول.
    مقدار    پرکردن بودجه به ترتیب رتبه؛ ارز دارای سهمیه تا سهمیه بازش.
    سقف      سقف تمرکز ۳۰٪ — بند ۴ متن ۱۸، P.CONCENTRATION_CAP_PCT. ارز در سقف یا بالای آن
             رد؛ سهمی که سقف جلویش را گرفت به نامزد پذیرفته‌شده بعدی؛ نماند، در ذخیره.

سطح ابطال نامزد، به ترتیب: سطح watch.json؛ کف پله rebuy نقشه — همان سطح ابطال روز فروش؛
یا سطح تازه با radar_levels.pick_invalidation، روش سطح‌های فعلی دفتر موقعیت. ناحیه ارزش
۱۵ روزه با radar_fetch3.volume_profile روی ۱۵ کندل روزانه بسته وقت جهانی.

بخش محض — evaluate، quota_table، band_release — بی‌شبکه است. gather کندل می‌خواند.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

# تنها منبع اصلی کمک‌تابع رقم فارسی — کپی محلی نگیر
from radar_text import fa
import radar_budget as BG
import radar_positions as P
import radar_watch as RW

UTC = timezone.utc
REPLACE_PP = 5.0          # جایگزینی ارز دارای سهمیه: دست‌کم ۵ واحد درصد قدرت نسبی بیشتر
VA_DAYS = 15              # ناحیه ارزش این معیار — تصمیم کاربر، متن ۱۸
BENCHMARK = "BTC"


def _at(raw) -> datetime:
    return RW._aware(raw, "زمان")


def _n(x: float) -> str:
    return f"{x:.10g}"


# ═══════════════════════ سهمیه ═══════════════════════

def plans(watch: dict) -> list[tuple[dict, datetime | None]]:
    """نقشه‌های بایگانی به ترتیب ساخت، سپس نقشه فعال. دومی زمان بستن یا None."""
    out = [(rp, _at(rp["closed"]["at"])) for rp in watch.get("reserve_archive") or []]
    out.sort(key=lambda x: _at(x[0]["created"]))
    if watch.get("reserve_plan"):
        out.append((watch["reserve_plan"], None))
    return out


def find_plan(watch: dict, created: str) -> tuple[dict, datetime | None] | None:
    want = _at(created)
    return next(((rp, until) for rp, until in plans(watch) if _at(rp["created"]) == want), None)


def quota_table(watch: dict, h: dict) -> list[dict]:
    """
    سهمیه بازخرید باز همه نقشه‌ها. نقشه بی بخش rebuy یک ردیف «بی تعهد بازخرید» می‌گیرد،
    تا گم نشود. last_sale زمان آخرین فروش پرشده همان نماد در همان نقشه است.
    """
    rows = []
    for rp, until in plans(watch):
        title = rp.get("title") or "نقشه ذخیره"
        if not rp.get("rebuy"):
            sold = {}
            for s in RW.reserve_progress(rp, _view(h, until)):
                if s["filled"]:
                    sold[s["symbol"]] = sold.get(s["symbol"], 0.0) + s["qty"]
            rows.append({"plan": title, "created": rp["created"], "closed": until,
                         "symbol": None, "sold_any": sold})
            continue
        prog = RW.reserve_progress(rp, _view(h, until))
        for r in RW.rebuy_status(rp, h, {}, until=until):
            fills = [s["fill_at"] for s in prog if s["filled"] and s["symbol"] == r["symbol"]
                     and s["fill_at"] is not None]
            rows.append({"plan": title, "created": rp["created"], "closed": until,
                         "symbol": r["symbol"], "qty": r["qty"], "sold": r["sold"],
                         "rebought": r["rebought"], "open": r["open"], "sale": r["sale"],
                         "floor": r["floor"], "last_sale": max(fills, default=None)})
    return rows


def _view(h: dict, until: datetime | None) -> dict:
    if until is None:
        return h
    return {**h, "ledger": [r for r in h.get("ledger", []) if _at(r["at"]) <= until]}


def open_quota(rows: list[dict]) -> dict[str, dict]:
    """جمع سهمیه باز هر نماد در همه نقشه‌ها، با آخرین فروش و کف نقشه تازه‌تر."""
    out: dict[str, dict] = {}
    for r in rows:
        if r.get("symbol") is None or r["open"] <= P.TOL:
            continue
        q = out.setdefault(r["symbol"], {"qty": 0.0, "last_sale": None, "floor": None,
                                         "plans": []})
        q["qty"] += r["open"]
        q["plans"].append(r["created"])
        if r["last_sale"] is not None and (q["last_sale"] is None or r["last_sale"] > q["last_sale"]):
            q["last_sale"], q["floor"] = r["last_sale"], r["floor"]
        elif q["floor"] is None:
            q["floor"] = r["floor"]
    return out


# ═══════════════════════ بودجه ═══════════════════════

def band_release(regime: dict | None, history: dict | None, now: datetime
                 ) -> tuple[dict | None, str | None]:
    """
    آخرین تغییر باند با هیسترزیس — trade_band روزهای regime_history.json و امروزِ
    regime.json. اگر رو به هدف ذخیره پایین‌تر بود: {from, to, day, target}. رژیم کهنه یا
    غایب یعنی None با دلیل؛ تغییر رو به پایین یا بی‌تغییر یعنی None بی‌دلیل.
    """
    warn = RW._regime_warn(regime, now)
    if warn:
        return None, warn
    tb = (regime.get("trade_band") or {}).get("name")
    if tb not in BG.BAND_ORDER:
        return None, "میدان trade_band در regime.json نیست یا نامعتبر است"
    today = f"{_at(regime['generated_at']).astimezone(UTC):%Y-%m-%d}"
    days = {d: rec.get("trade_band") for d, rec in ((history or {}).get("days") or {}).items()
            if rec.get("trade_band") in BG.BAND_ORDER and d < today}
    days[today] = tb
    seq = sorted(days.items())
    for i in range(len(seq) - 1, 0, -1):
        if seq[i][1] != seq[i - 1][1]:
            old, new = BG.band_by_name(seq[i - 1][1]), BG.band_by_name(seq[i][1])
            if new["stable"] < old["stable"]:
                return {"from": old["name"], "to": new["name"], "day": seq[i][0],
                        "target": new["stable"], "old_target": old["stable"]}, None
            return None, None
    return None, None


def budget(release: dict | None, val: dict) -> float | None:
    """بودجه آزادشده = ذخیره فعلی − هدف تازه × کل سرمایه. ارزش ناقص یعنی داده ندارم."""
    if release is None or val.get("incomplete"):
        return None
    return val["stable_usd"] - release["target"] / 100 * val["total"]


# ═══════════════════════ نامزد و رتبه ═══════════════════════

def watch_list() -> list[str]:
    """فهرست پایش — radar_scan PRESETS["watch"]؛ تنها منبع فهرست."""
    import radar_scan as RS                 # دیر: radar_fetch3 و pandas
    return list(RS.PRESETS["watch"])


def candidates(listed: list[str], quotas: dict) -> list[str]:
    syms = [s for s in list(quotas) + list(listed) if s != BENCHMARK]
    return list(dict.fromkeys(syms))


def evaluate(data: dict, listed: list[str], quotas: dict, amount: float | None,
             val: dict | None = None) -> dict:
    """
    پذیرش، رتبه و تقسیم بودجه — بی‌شبکه. data[نماد] = {price, level, level_src, va,
    rs30 به درصد}. listed فهرست پایش است — مرجع «یک‌سوم پایین». هر رد دلیل دارد.
    """
    ranked, rejected = [], []
    rs_list = sorted(d["rs30"] for s, d in data.items()
                     if s in listed and s != BENCHMARK and d.get("rs30") is not None)
    cut = rs_list[len(rs_list) // 3 - 1] if len(rs_list) >= 3 else None
    for sym, d in data.items():
        if sym == BENCHMARK:
            rejected.append({"symbol": sym, "why": "معیار قدرت نسبی — با خودش سنجیده نمی‌شود"})
            continue
        px, lvl, va, rs = d.get("price"), d.get("level"), d.get("va"), d.get("rs30")
        why = None
        if px is None:
            why = "قیمت: داده ندارم"
        elif lvl is None:
            why = f"سطح ابطال ساختاری ندارد — {d.get('level_why') or 'روش سطح‌ها نامزدی نداد'}"
        elif px <= lvl:
            why = f"زیر سطح ابطال {_n(lvl)} — قیمت {_n(px)}"
        elif not va:
            why = f"ناحیه ارزش {fa(VA_DAYS)} روزه: داده ندارم"
        elif px < va["val"]:
            why = (f"زیر ناحیه ارزش {fa(VA_DAYS)} روزه — قیمت {_n(px)}، کف ناحیه "
                   f"{_n(round(va['val'], 6))}")
        elif rs is None:
            why = "قدرت نسبی ۳۰ روزه: داده ندارم"
        elif cut is not None and sym in listed and rs <= cut:
            why = f"قدرت نسبی ۳۰ روزه {rs:+.1f}٪ در یک‌سوم پایین فهرست پایش"
        elif cut is not None and sym not in listed and rs <= cut:
            why = f"قدرت نسبی ۳۰ روزه {rs:+.1f}٪ هم‌تراز یک‌سوم پایین فهرست پایش"
        elif val is not None and P.cap_room(val, sym) <= 0.5:
            why = (f"بالای سقف تمرکز — سهم {P.share_pct(val, sym):.1f}٪، سقف "
                   f"{fa(P.CONCENTRATION_CAP_PCT)}٪؛ خرید تازه ممنوع")
        if why:
            rejected.append({"symbol": sym, "why": why})
            continue
        q = quotas.get(sym)
        ranked.append({"symbol": sym, "price": px, "rs30": rs, "level": lvl,
                       "level_src": d.get("level_src"), "quota": q["qty"] if q else 0.0,
                       "last_sale": q["last_sale"] if q else None, "usd": 0.0,
                       "replaces": None, "why": ""})

    def key(r):
        has = r["quota"] > P.TOL
        sale = r["last_sale"].timestamp() if r["last_sale"] else 0.0
        return (r["rs30"] if has else r["rs30"] - REPLACE_PP, 1 if not has else 0, sale)

    ranked.sort(key=key, reverse=True)
    for i, r in enumerate(ranked):
        if r["quota"] > P.TOL:
            r["why"] = (f"سهمیه باز {_n(round(r['quota'], 10))} — قدرت نسبی ۳۰ روزه "
                        f"{r['rs30']:+.1f}٪")
            continue
        below = [q for q in ranked[i + 1:] if q["quota"] > P.TOL]
        if below:
            q = below[0]
            r["replaces"] = q["symbol"]
            r["why"] = (f"جایگزین {q['symbol']} — قدرت نسبی ۳۰ روزه {r['rs30']:+.1f}٪ در برابر "
                        f"{q['rs30']:+.1f}٪، دست‌کم {fa(f'{REPLACE_PP:g}')} واحد درصد بهتر")
        else:
            r["why"] = f"قدرت نسبی ۳۰ روزه {r['rs30']:+.1f}٪"

    left = amount if amount is not None and amount > 0 else 0.0
    blocked = 0.0
    for r in ranked:
        quota = r["quota"] * r["price"] if r["quota"] > P.TOL else math.inf
        room = P.cap_room(val, r["symbol"]) if val is not None else math.inf
        take = min(left, quota, room)
        if room < min(left, quota):
            r["capped"] = min(left, quota) - room
            blocked += r["capped"]
            r["why"] += (f"؛ سقف تمرکز جلوی {r['capped']:,.0f} دلار را گرفت — به نامزد بعدی")
        if take > 0:
            r["usd"] = take
            left -= take
    return {"ranked": ranked, "rejected": rejected, "left": left, "blocked": blocked,
            "budget": amount, "rs_cut": cut}


# ═══════════════════════ داده — شبکه ═══════════════════════

def _level_for(sym: str, watch: dict, h: dict, quotas: dict, daily, now: datetime
               ) -> tuple[float | None, str, str]:
    pos = {p["symbol"]: p for p in h.get("positions", []) if p.get("book") == "position"}
    for it in watch.get("positions") or []:
        if it["symbol"].upper() == sym and sym in pos:
            return RW._position_level(it, pos[sym])[0], "watch.json", ""
    q = quotas.get(sym)
    if q and q.get("floor"):
        return float(q["floor"]), "کف پله بازخرید نقشه — سطح ابطال روز فروش", ""
    try:
        import radar_levels as L
        weekly = L.okx_candles(f"{sym}-USDT", "1W", 200)
    except Exception as exc:              # بلند، نه بلعیده: دلیل در ردیف رد می‌آید
        return None, "", f"کندل هفتگی نیامد ({type(exc).__name__})"
    if weekly is None or daily is None:
        return None, "", "کندل روزانه یا هفتگی نیامد"
    wk = weekly[weekly["confirm"] == 1].reset_index(drop=True)
    dl = daily.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "vol"})
    dl = dl[dl["confirm"] == 1].reset_index(drop=True)
    px = float(daily["c"].iloc[-1])
    res = L.pick_invalidation(dl, wk, px)
    if res.get("level") is None:
        return None, "", res.get("reason") or "سطحی نیامد"
    return float(res["level"]), "سطح تازه با روش سطح‌های دفتر موقعیت", ""


def value_area(daily) -> dict | None:
    """ناحیه ارزش ۱۵ کندل روزانه بسته — radar_fetch3.volume_profile، تنها تعریف."""
    import radar_fetch3 as R
    dl = daily.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "vol"})
    dl = dl[dl["confirm"] == 1].reset_index(drop=True)
    if len(dl) < VA_DAYS:
        return None
    seg = dl.iloc[-VA_DAYS:].reset_index(drop=True)
    return R.volume_profile(seg, 0, VA_DAYS - 1)


def gather(symbols: list[str], watch: dict, h: dict, quotas: dict,
           frames: dict | None = None, btc=None, now: datetime | None = None) -> dict:
    """داده هر نامزد: قیمت زنده، قدرت نسبی ۳۰ روزه، ناحیه ارزش ۱۵ روزه و سطح ابطال."""
    import radar_book as B
    now = now or datetime.now(UTC)
    frames = dict(frames or {})
    btc = btc if btc is not None else B.candles(BENCHMARK)
    out = {}
    for sym in symbols:
        df = frames.get(sym)
        if df is None:
            df = B.candles(sym)
        if df is None:
            out[sym] = {"price": None}
            continue
        sc = B.score_position(df, btc)
        lvl, src, why = _level_for(sym, watch, h, quotas, df, now)
        out[sym] = {"price": B._last_close(df),
                    "rs30": None if not sc or sc["rs30"] is None else 100 * sc["rs30"],
                    "va": value_area(df), "level": lvl, "level_src": src, "level_why": why}
    return out


# ═══════════════════════ متن ═══════════════════════

def lines(release: dict, amount: float | None, ev: dict | None, val: dict,
          plain: bool = False) -> list[str]:
    """متن مشترک پیام پایشگر و ردیف اقدام سبد. plain یعنی بی قالب مارک‌داون."""
    b = (lambda s: s) if plain else (lambda s: f"**{s}**")
    head = (f"🟢 {b('بودجه آزادشده')} — باند با هیسترزیس از {release['from']} به "
            f"{release['to']}، {release['day']}؛ هدف ذخیره {fa(release['old_target'])}٪ به "
            f"{fa(release['target'])}٪.")
    if amount is None:
        return [head, "بودجه: داده ندارم — ارزش سبد ناقص است."]
    if amount <= 0:
        return [head, f"بودجه: هیچ — ذخیره {val['stable_usd']:,.0f} دلار زیر یا برابر هدف "
                      f"{fa(release['target'])}٪ از {val['total']:,.0f} دلار است."]
    out = [head, f"بودجه: ذخیره {val['stable_usd']:,.0f} منهای {fa(release['target'])}٪ از "
                 f"{val['total']:,.0f} = {amount:,.0f} دلار. رادار فقط پیشنهاد می‌دهد؛ تصمیم با تو."]
    if ev is None:
        return out + ["فهرست نامزدها ساخته نشد — داده کندل نیامد."]
    got = [r for r in ev["ranked"] if r["usd"] > 0]
    if got:
        out.append("فهرست رتبه‌دار:")
        for i, r in enumerate(got, 1):
            tail = "" if r["quota"] > P.TOL else ("؛ ثبت موقعیت تازه با سطح ابطال فرمان ندارد — "
                                                   "فقط پیشنهاد")
            out.append(f"{fa(i)}. {r['symbol']} — {r['usd']:,.0f} دلار، قیمت مرجع "
                       f"{_n(r['price'])}؛ {r['why']}{tail}")
    rest = [r for r in ev["ranked"] if r["usd"] <= 0]
    if rest:
        out.append("پذیرفته، بی‌بودجه: " + "، ".join(r["symbol"] for r in rest))
    if ev["rejected"]:
        out.append("رد:")
        out += [f"- {r['symbol']} — {r['why']}" for r in ev["rejected"]]
    if ev["left"] > 0.5:
        cap = (" سقف تمرکز جلوی بخشی را گرفت و" if ev.get("blocked", 0) > 0.5 or any(
            "سقف تمرکز" in r["why"] for r in ev["rejected"]) else "")
        out.append(f"در ذخیره می‌ماند: {ev['left']:,.0f} دلار —{cap} نامزد پذیرفته‌شده دیگری "
                   "نیست.")
    out.append("ثبت بازخرید همان ارز: radar_positions.py reenter --reserve-plan <created نقشه> "
               f"--symbol <نماد> --qty <مقدار> --price <قیمت> --account <حساب> {P.RECEIPT_ARGS}")
    return out
