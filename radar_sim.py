#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_sim.py — شبیه‌ساز تصمیم، هسته موتور بک‌تست — ک۱۳۳
=========================================================

هر استراتژی را روی شمع‌های واقعی گذشته اجرا می‌کند و می‌گوید اگر همین قاعده را
اجرا کرده بودیم چه می‌شد. فقط سنجش است؛ هیچ قاعده زنده‌ای را عوض نمی‌کند — ابزار
سنجش از یخ‌بندان ک۱۲۰ معاف است، تصمیم کاربر ۹ نوامبر.

    python radar_sim.py run --strategy sma_cross --symbols BTC,ETH --tf 1d --from 2022-01-01 --to 2026-11-01
    گزینه‌ها: --fee-bps، --slip-bps، --risk-pct، --split 2025-01-01، --both-hit stop|target، --json FILE

قراردادها:
  - نگاه به آینده ممنوع. استراتژی در بسته شدن شمع i فقط شمع‌های ۰ تا i را می‌بیند؛
    سفارش از شمع i+1 به بعد اجرا می‌شود.
  - ورود بازاری در باز شدن شمع بعد، به‌علاوه لغزش. ورود توقفی وقتی سقف شمع به ماشه
    برسد؛ اگر شمع با شکاف از ماشه گذشت، در باز شدن همان شمع. ورود محدود برعکس.
  - خروج: حد ضرر، پله‌های سود، و خروج زمانی در بسته شدن شمع n‌ام. اگر در یک شمع هم
    حد ضرر و هم هدف لمس شد، پیش‌فرض محافظه‌کار است: اول حد ضرر — both_hit.
  - شکاف از حد ضرر: خروج در باز شدن همان شمع، نه روی خود حد ضرر. بدتر، ولی واقعی.
  - نتیجه هر معامله به واحد R: سود یا زیان تقسیم بر فاصله ورود واقعی تا حد ضرر،
    پس از کارمزد هر دو طرف. معامله بی حد ضرر، مثل سبک گرت، R ندارد و فقط درصد دارد.
  - کارمزد پیش‌فرض ۱۰ واحد پایه هر طرف و لغزش ۵ واحد پایه هر طرف.
  - یک پوزیشن هم‌زمان برای هر نماد. سفارش تازه تا بسته شدن پوزیشن نادیده می‌ماند.

آزمون: tests/test_sim.py، بی‌شبکه با شمع ساختگی. داده واقعی از radar_history.py،
فقط جایی که به صرافی راه دارد: لپ‌تاپ یا اجراکننده گیت‌هاب.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable

VERSION = "0.1"
UTC = timezone.utc
FEE_BPS = 10.0      # کارمزد هر طرف
SLIP_BPS = 5.0      # لغزش هر طرف
BOOT_N = 2000       # نمونه‌گیری دوباره برای بازه اطمینان امید
BOOT_SEED = 7


# ── داده ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Bar:
    t: str          # زمان باز شدن، ISO وقت جهانی
    o: float
    h: float
    l: float
    c: float
    v: float = 0.0


def bars_from_frame(df) -> list[Bar]:
    """از DataFrame خروجی radar_history: فقط شمع بسته، به ترتیب زمان."""
    out = []
    flag = "confirm" if "confirm" in df.columns else ("confirmed" if "confirmed" in df.columns else None)
    tcol = "ts" if "ts" in df.columns else ("time" if "time" in df.columns else None)
    for _, r in df.iterrows():
        if flag and not bool(int(r[flag])):
            continue
        t = r[tcol] if tcol else r.name
        t = t.isoformat() if hasattr(t, "isoformat") else str(t)
        out.append(Bar(t, float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]),
                       float(r.get("volume", 0.0) or 0.0)))
    return out


# ── سفارش و معامله ────────────────────────────────────────────────

@dataclass
class Order:
    side: str = "long"                 # long یا short
    kind: str = "market"               # market، stop یا limit
    price: float | None = None         # ماشه برای stop و limit
    stop: float | None = None          # حد ضرر؛ None یعنی بی حد ضرر
    targets: list = field(default_factory=list)   # [(قیمت، سهم)]، جمع سهم‌ها ≤ ۱
    time_stop: int | None = None       # خروج در بسته شدن شمع n‌ام پس از ورود
    expire: int = 1                    # سفارش stop یا limit تا چند شمع زنده است
    tag: str = ""


@dataclass
class Trade:
    symbol: str
    side: str
    tag: str
    signal_t: str
    entry_t: str
    entry: float
    stop: float | None
    exit_t: str = ""
    exit: float = 0.0
    reason: str = ""
    bars: int = 0
    pct: float = 0.0          # بازده خالص درصدی، پس از کارمزد و لغزش
    r: float | None = None    # بازده به واحد R
    mae_pct: float = 0.0      # بدترین حرکت خلاف پس از ورود
    mfe_pct: float = 0.0      # بهترین حرکت موافق پس از ورود


def _adj(price: float, side: str, entering: bool, slip_bps: float) -> float:
    """لغزش همیشه به ضرر ما: خرید گران‌تر، فروش ارزان‌تر."""
    k = slip_bps / 1e4
    buy = (side == "long") == entering
    return price * (1 + k) if buy else price * (1 - k)


def _gross(side: str, entry: float, exit_: float) -> float:
    return (exit_ - entry) / entry if side == "long" else (entry - exit_) / entry


# ── موتور ─────────────────────────────────────────────────────────

Strategy = Callable[[list, int, dict], "Order | None"]


def run(bars: list[Bar], strategy: Strategy, *, symbol: str = "", params: dict | None = None,
        fee_bps: float = FEE_BPS, slip_bps: float = SLIP_BPS, both_hit: str = "stop") -> list[Trade]:
    """
    اجرای یک استراتژی روی یک نماد. strategy(bars, i, params) در بسته شدن شمع i صدا زده
    می‌شود و فقط bars[:i+1] را می‌بیند — یک کپی بریده می‌گیرد تا نگاه به آینده ناممکن باشد.
    """
    params = dict(params or {})
    trades: list[Trade] = []
    pending: tuple[Order, int, str] | None = None     # سفارش، شمع ثبت، زمان سیگنال
    pos: dict | None = None
    fee = fee_bps / 1e4

    for i in range(len(bars)):
        b = bars[i]

        # ۱) اجرای سفارش در انتظار روی همین شمع
        if pos is None and pending is not None:
            od, born, sig_t = pending
            fill = None
            if od.kind == "market":
                fill = b.o
            elif od.kind == "stop" and od.price is not None:
                if od.side == "long" and b.h >= od.price:
                    fill = max(b.o, od.price)
                elif od.side == "short" and b.l <= od.price:
                    fill = min(b.o, od.price)
            elif od.kind == "limit" and od.price is not None:
                if od.side == "long" and b.l <= od.price:
                    fill = min(b.o, od.price)
                elif od.side == "short" and b.h >= od.price:
                    fill = max(b.o, od.price)
            if fill is not None:
                px = _adj(fill, od.side, True, slip_bps)
                pos = {"od": od, "entry": px, "i0": i, "t0": b.t, "sig": sig_t, "left": 1.0,
                       "realized": 0.0, "lo": px, "hi": px, "tgt": sorted(
                           od.targets, key=lambda x: x[0], reverse=(od.side == "short"))}
                pending = None
                # ورود و خروج در همان شمع ورود هم ممکن است؛ پایین بررسی می‌شود
            elif i - born >= od.expire:
                pending = None

        # ۲) مدیریت پوزیشن باز روی همین شمع
        if pos is not None:
            od = pos["od"]
            side = od.side
            pos["lo"] = min(pos["lo"], b.l)
            pos["hi"] = max(pos["hi"], b.h)
            closed = False

            def close_part(price: float, frac: float, reason: str):
                nonlocal closed
                px = _adj(price, side, False, slip_bps)
                pos["realized"] += frac * (_gross(side, pos["entry"], px) - 2 * fee)
                pos["left"] -= frac
                pos["last"] = (b.t, px, reason)
                if pos["left"] <= 1e-9:
                    closed = True

            stop_hit = od.stop is not None and (b.l <= od.stop if side == "long" else b.h >= od.stop)
            tgt_hits = [(p, f) for p, f in pos["tgt"] if (b.h >= p if side == "long" else b.l <= p)]
            stop_first = both_hit == "stop" or not tgt_hits

            if stop_hit and stop_first:
                gap = (b.o < od.stop) if side == "long" else (b.o > od.stop)
                close_part(b.o if gap else od.stop, pos["left"], "stop")
            else:
                for p, f in list(tgt_hits):
                    if closed:
                        break
                    gap = (b.o > p) if side == "long" else (b.o < p)
                    close_part(b.o if gap else p, min(f, pos["left"]), "target")
                    pos["tgt"].remove((p, f))
                if not closed and stop_hit:
                    close_part(od.stop, pos["left"], "stop")
            if not closed and od.time_stop is not None and i - pos["i0"] + 1 >= od.time_stop:
                close_part(b.c, pos["left"], "time")
            if closed:
                trades.append(_finish(symbol, pos, i))
                pos = None

        # ۳) سیگنال تازه در بسته شدن شمع، فقط وقتی پوزیشن و سفارش باز نداریم
        if pos is None and pending is None and i < len(bars) - 1:
            od = strategy(bars[: i + 1], i, params)
            if od is not None:
                if od.stop is not None and od.kind != "market" and od.price is not None:
                    wrong = od.stop >= od.price if od.side == "long" else od.stop <= od.price
                    if wrong:
                        raise ValueError(f"حد ضرر در سوی نادرست ماشه: {od}")
                pending = (od, i, b.t)

    # پوزیشن باز در پایان داده: با بسته آخر، برچسب end
    if pos is not None:
        b = bars[-1]
        px = _adj(b.c, pos["od"].side, False, slip_bps)
        pos["realized"] += pos["left"] * (_gross(pos["od"].side, pos["entry"], px) - 2 * fee)
        pos["left"] = 0.0
        pos["last"] = (b.t, px, "end")
        trades.append(_finish(symbol, pos, len(bars) - 1))
    return trades


def _finish(symbol: str, pos: dict, i: int) -> Trade:
    od = pos["od"]
    e = pos["entry"]
    t, px, reason = pos["last"]
    risk = abs(e - od.stop) / e if od.stop is not None else None
    pct = pos["realized"]
    if od.side == "long":
        mae, mfe = (pos["lo"] - e) / e, (pos["hi"] - e) / e
    else:
        mae, mfe = (e - pos["hi"]) / e, (e - pos["lo"]) / e
    return Trade(symbol, od.side, od.tag, pos["sig"], pos["t0"], round(e, 10), od.stop,
                 t, round(px, 10), reason, i - pos["i0"] + 1, round(100 * pct, 4),
                 round(pct / risk, 4) if risk else None, round(100 * mae, 4), round(100 * mfe, 4))


# ── سنجه‌ها ────────────────────────────────────────────────────────

def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def _boot_ci(xs: list[float], n: int = BOOT_N, seed: int = BOOT_SEED) -> tuple[float, float] | None:
    """بازه ۹۰٪ میانگین با نمونه‌گیری دوباره — آیا امید از صفر جداست یا شانس است؟"""
    if len(xs) < 10:
        return None
    rnd = random.Random(seed)
    k = len(xs)
    ms = sorted(sum(xs[rnd.randrange(k)] for _ in range(k)) / k for _ in range(n))
    return ms[int(0.05 * n)], ms[int(0.95 * n) - 1]


def _max_dd(curve: list[float]) -> float:
    peak, dd = curve[0] if curve else 0.0, 0.0
    for x in curve:
        peak = max(peak, x)
        dd = min(dd, x - peak)
    return dd


def metrics(trades: list[Trade], risk_pct: float = 1.0) -> dict:
    """
    سنجه‌ها به واحد R وقتی همه حد ضرر دارند، وگرنه فقط درصد. risk_pct برای منحنی سرمایه
    با ریسک ثابت هر معامله — بیشترین افت سرمایه، نه فقط افت R.
    """
    n = len(trades)
    out = {"n": n}
    if not n:
        return out
    pcts = [t.pct for t in trades]
    out.update({
        "win_rate": round(100 * sum(p > 0 for p in pcts) / n, 2),
        "avg_pct": round(_mean(pcts), 4),
        "median_bars": sorted(t.bars for t in trades)[n // 2],
        "worst_mae_pct": round(min(t.mae_pct for t in trades), 4),
        "reasons": {r: sum(t.reason == r for t in trades) for r in sorted({t.reason for t in trades})},
    })
    rs = [t.r for t in trades if t.r is not None]
    if len(rs) == n:
        wins = [r for r in rs if r > 0]
        losses = [r for r in rs if r <= 0]
        exp = _mean(rs)
        ci = _boot_ci(rs)
        curve, eq, streak, worst = [0.0], 1.0, 0, 0
        eqc = [1.0]
        for r in rs:
            curve.append(curve[-1] + r)
            eq *= 1 + r * risk_pct / 100
            eqc.append(eq)
            streak = streak + 1 if r <= 0 else 0
            worst = max(worst, streak)
        peak, dd = 1.0, 0.0
        for x in eqc:
            peak = max(peak, x)
            dd = min(dd, x / peak - 1)
        out.update({
            "avg_win_r": round(_mean(wins), 4) if wins else None,
            "avg_loss_r": round(_mean(losses), 4) if losses else None,
            "expectancy_r": round(exp, 4),
            "expectancy_ci90": [round(ci[0], 4), round(ci[1], 4)] if ci else None,
            "profit_factor": round(sum(wins) / -sum(losses), 4) if losses and sum(losses) < 0 else None,
            "max_dd_r": round(_max_dd(curve), 4),
            "max_dd_pct_at_risk": round(100 * dd, 2),
            "risk_pct": risk_pct,
            "longest_loss_streak": worst,
        })
    return out


def split_metrics(trades: list[Trade], split: str, risk_pct: float = 1.0) -> dict:
    """درون‌نمونه و بیرون‌نمونه با تاریخ ورود — قاعده‌ای که فقط روی گذشته‌ای که دیده کار کند، حفظی است."""
    a = [t for t in trades if t.entry_t < split]
    b = [t for t in trades if t.entry_t >= split]
    return {"split": split, "in_sample": metrics(a, risk_pct), "out_of_sample": metrics(b, risk_pct)}


# ── استراتژی‌ها ────────────────────────────────────────────────────
# هر استراتژی تابعی است (bars, i, params) -> Order | None. فقط bars را می‌بیند.

def _sma(xs: list[float], n: int) -> float | None:
    return sum(xs[-n:]) / n if len(xs) >= n else None


def sma_cross(bars, i, p) -> Order | None:
    """
    نمونه آزمون لوله‌کشی، نه پیشنهاد: میانگین کوتاه از بلند رد شد ← خرید بازاری،
    حد ضرر زیر کف n شمع، هدف k برابر ریسک. آزمون‌نشده.
    """
    fast, slow, look, k = int(p.get("fast", 10)), int(p.get("slow", 30)), int(p.get("look", 10)), float(p.get("rr", 2))
    if i < slow + 1:
        return None
    cs = [b.c for b in bars]
    f0, s0 = _sma(cs[:-1], fast), _sma(cs[:-1], slow)
    f1, s1 = _sma(cs, fast), _sma(cs, slow)
    if f0 <= s0 and f1 > s1:
        stop = min(b.l for b in bars[-look:])
        e = bars[-1].c
        if stop >= e:
            return None
        return Order("long", "market", stop=stop, targets=[(e + k * (e - stop), 1.0)],
                     time_stop=int(p.get("hold", 60)), tag="sma_cross")
    return None


STRATEGIES: dict[str, Strategy] = {"sma_cross": sma_cross}


# ── اجرای چندنمادی و خط فرمان ─────────────────────────────────────

def run_many(series: dict[str, list[Bar]], strategy: Strategy, **kw) -> list[Trade]:
    out = []
    for sym, bars in series.items():
        out += run(bars, strategy, symbol=sym, **kw)
    return sorted(out, key=lambda t: (t.entry_t, t.symbol))


def render_md(name: str, m: dict, by_symbol: dict, meta: dict) -> str:
    L = [f"# شبیه‌ساز — {name}", "",
         f"نسخه {VERSION}؛ {meta.get('tf', '')}؛ {meta.get('from', '')} تا {meta.get('to', '')}؛ "
         f"کارمزد {meta.get('fee_bps')} و لغزش {meta.get('slip_bps')} واحد پایه هر طرف؛ "
         f"هر دو لمس در یک شمع: {meta.get('both_hit')}. آزمون‌نشده تا داوری کاربر.", ""]
    if not m.get("n"):
        L.append("هیچ معامله‌ای نشد.")
        return "\n".join(L)
    rows = [("تعداد معامله", m["n"]), ("درصد برد", m.get("win_rate")),
            ("میانگین بازده درصدی", m.get("avg_pct")), ("میانگین سود R", m.get("avg_win_r")),
            ("میانگین ضرر R", m.get("avg_loss_r")), ("امید هر معامله R", m.get("expectancy_r")),
            ("بازه ۹۰٪ امید", m.get("expectancy_ci90")), ("ضریب سود", m.get("profit_factor")),
            ("بیشترین افت R", m.get("max_dd_r")), ("بیشترین افت سرمایه با ریسک ثابت", m.get("max_dd_pct_at_risk")),
            ("طولانی‌ترین باخت پیاپی", m.get("longest_loss_streak")), ("میانه شمع نگه‌داری", m.get("median_bars"))]
    L += ["| سنجه | مقدار |", "|---|---|"] + [f"| {k} | {'—' if v is None else v} |" for k, v in rows]
    L += ["", "| نماد | تعداد | درصد برد | امید R |", "|---|---|---|---|"]
    for s, sm in sorted(by_symbol.items()):
        L.append(f"| {s} | {sm.get('n', 0)} | {sm.get('win_rate', '—')} | {sm.get('expectancy_r', '—')} |")
    return "\n".join(L)


def main(argv=None, history_fn=None) -> int:
    ap = argparse.ArgumentParser(description="شبیه‌ساز تصمیم رادار — هسته بک‌تست")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--strategy", required=True, choices=sorted(STRATEGIES))
    r.add_argument("--symbols", required=True)
    r.add_argument("--tf", default="1d")
    r.add_argument("--from", dest="start", required=True)
    r.add_argument("--to", dest="end", required=True)
    r.add_argument("--venue", default="auto")
    r.add_argument("--params", default="{}", help="JSON")
    r.add_argument("--fee-bps", type=float, default=FEE_BPS)
    r.add_argument("--slip-bps", type=float, default=SLIP_BPS)
    r.add_argument("--risk-pct", type=float, default=1.0)
    r.add_argument("--both-hit", choices=["stop", "target"], default="stop")
    r.add_argument("--split", default=None)
    r.add_argument("--json", default=None, help="مسیر فایل خروجی ماشین‌خوان")
    a = ap.parse_args(argv)

    if history_fn is None:
        import radar_history as H
        def history_fn(sym, tf, s, e, venue):
            return H.history(sym, tf, H.parse_time(s), H.parse_time(e, end=True), venue=venue).df
    series = {}
    for sym in [x.strip().upper() for x in a.symbols.split(",") if x.strip()]:
        series[sym] = bars_from_frame(history_fn(sym, a.tf, a.start, a.end, a.venue))
    strat = STRATEGIES[a.strategy]
    kw = dict(params=json.loads(a.params), fee_bps=a.fee_bps, slip_bps=a.slip_bps, both_hit=a.both_hit)
    trades = run_many(series, strat, **kw)
    m = metrics(trades, a.risk_pct)
    by = {s: metrics([t for t in trades if t.symbol == s], a.risk_pct) for s in series}
    meta = {"tf": a.tf, "from": a.start, "to": a.end, "fee_bps": a.fee_bps, "slip_bps": a.slip_bps,
            "both_hit": a.both_hit}
    print(render_md(a.strategy, m, by, meta))
    if a.split:
        print("\n" + json.dumps(split_metrics(trades, a.split, a.risk_pct), ensure_ascii=False))
    if a.json:
        doc = {"version": VERSION, "strategy": a.strategy, "meta": meta, "metrics": m, "by_symbol": by,
               "trades": [asdict(t) for t in trades]}
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
