#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_sim.py — شبیه‌ساز تصمیم، هسته موتور بک‌تست — ک۱۳۳
=========================================================

هر استراتژی را روی شمع‌های واقعی گذشته اجرا می‌کند و می‌گوید اگر همین قاعده را
اجرا کرده بودیم چه می‌شد. فقط سنجش است؛ هیچ قاعده زنده‌ای را عوض نمی‌کند — ابزار
سنجش از یخ‌بندان ک۱۲۰ معاف است، تصمیم کاربر ۹ نوامبر.

    python radar_sim.py run --strategy sma_cross --symbols BTC,ETH --tf 1d --from 2022-01-01 --to 2026-11-01
    گزینه‌ها: --fee-bps، --slip-bps، --risk-pct، --split 2025-01-01، --both-hit stop|target،
    --cluster week|day|none، --json FILE

قراردادها — نسخه ۰.۲ پس از بازبینی مستقل ۱۲ نوامبر، رویداد ۱۴۰:
  - نگاه به آینده ممنوع. استراتژی در بسته شدن شمع i یک نمای فقط‌خواندنی از شمع ۰ تا i
    می‌گیرد؛ هر دسترسی به شمع بعدی IndexError است. نما کپی نمی‌سازد، پس موتور خطی است.
  - سفارش از شمع i+1 به بعد اجرا می‌شود. بازاری در باز شدن شمع بعد. توقفی وقتی سقف یا
    کف به ماشه برسد، و با شکاف در باز شدن. محدود برعکس. لغزش همیشه به ضرر ما.
  - اندازه پوزیشن در لحظه سفارش ثابت می‌شود. پس R = سود یا زیان تقسیم بر ریسک
    برنامه‌ریزی‌شده: فاصله ماشه تا حد ضرر، و برای بازاری فاصله بسته شمع سیگنال تا حد ضرر.
    شکاف از حد ضرر پس بیش از یک R زیان می‌دهد، و شکاف نزدیک حد ضرر R را منفجر نمی‌کند.
  - سفارشی که پر شدنش از حد ضرر یا از هدف رد شده باشد اجرا نمی‌شود و در skipped می‌آید.
  - ترتیب درون شمع:
      • باز شدن اولین قیمت است: اگر از حد ضرر رد شده، خروج در باز شدن، هر فرضی باشد؛
        اگر از هدف رد شده، همان هدف در باز شدن.
      • اگر پس از آن هم حد ضرر و هم هدف لمس شد، ترتیب نامعلوم است: پیش‌فرض محافظه‌کار
        اول حد ضرر — both_hit — و معامله برچسب ambiguous می‌گیرد.
      • شمع ورود سفارش محدود: سقف شاید پیش از پر شدن آمده، پس هدف آن شمع شمرده نمی‌شود.
        شمع ورود سفارش توقفی: کف شاید پیش از پر شدن آمده، پس لمس حد ضرر بدبینانه شمرده
        می‌شود. هر دو ambiguous. در شمع ورودی که با باز شدن پر نشده، خروج در باز شدن نیست.
  - خروج زمانی time_stop=n: بسته شدن شمع n‌ام، خود شمع ورود یکم؛ n کمتر از یک رد است.
  - کارمزد هر طرف روی ارزش همان طرف؛ پیش‌فرض ۱۰ واحد پایه کارمزد و ۵ واحد پایه لغزش.
  - یک پوزیشن هم‌زمان برای هر نماد. سفارش تازه تا بسته شدن پوزیشن ساخته نمی‌شود.
  - سنجه‌ها: منحنی و افت به ترتیب زمان خروج. بازه ۹۰٪ امید با نمونه‌گیری دوباره خوشه‌ای
    به هفته ورود، چون معامله‌های هم‌زمان چند نماد مستقل نیستند. زیر ۳۰ معامله برچسب کم‌نمونه.

محدودیت‌های شناخته — خوش‌بینانه یا ناقص، آگاهانه:
  - سفارش محدود و هدف با لمس دقیق پر می‌شوند؛ در واقعیت شاید صف پر نشود.
  - فاندینگ فیوچرز حساب نمی‌شود. افت سرمایه فقط از معامله بسته است، نه شناور، و حرارت
    چند پوزیشن هم‌زمان را نمی‌سنجد.
  - بیشترین حرکت خلاف و موافق در شمع خروج فراتر از نقطه خروج را هم می‌بیند.
  - خوشه هفته ورود، نگه‌داری چندهفته‌ای هم‌پوشان را جدا می‌شمرد؛ بازه هنوز شاید تنگ باشد.
  - سفارش ماندگار که با شکاف از هدف یا حد ضرر پر می‌شد در واقعیت تقریباً فوراً با زیان
    کارمزد بسته می‌شد؛ اینجا skipped است و صفر شمرده می‌شود. شمارش آن در گزارش هست.

آزمون: tests/test_sim.py، بی‌شبکه با شمع ساختگی. داده واقعی از radar_history.py،
فقط جایی که به صرافی راه دارد: لپ‌تاپ یا اجراکننده گیت‌هاب.
"""
from __future__ import annotations

import argparse
import json
import math
import operator
import random
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable

VERSION = "0.2"
UTC = timezone.utc
FEE_BPS = 10.0      # کارمزد هر طرف
SLIP_BPS = 5.0      # لغزش هر طرف
BOOT_N = 2000       # نمونه‌گیری دوباره برای بازه اطمینان امید
BOOT_SEED = 7
SMALL_N = 30       # زیر این، بازه اطمینان کم‌نمونه است


# ── داده ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Bar:
    t: str          # زمان باز شدن، ISO وقت جهانی
    o: float
    h: float
    l: float
    c: float
    v: float = 0.0


def _when(raw) -> datetime | None:
    """زمان ISO به وقت جهانی؛ بی‌منطقه یعنی وقت جهانی. نامعتبر: None."""
    try:
        d = datetime.fromisoformat(str(raw).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.replace(tzinfo=UTC) if d.tzinfo is None else d.astimezone(UTC)


def _tkey(raw):
    """کلید مرتب‌سازی زمان: زمان واقعی اگر خوانا بود، وگرنه خود رشته."""
    d = _when(raw)
    return (0, d, "") if d is not None else (1, None, str(raw))


def bars_from_frame(df) -> list[Bar]:
    """
    از DataFrame خروجی radar_history: فقط شمع بسته، به ترتیب زمان، بی تکرار.
    بی ستون confirm خطاست — شمع باز را نمی‌شود جدا کرد. confirm نامعلوم یعنی باز.
    زمان باید datetime باشد؛ عدد خام میلی‌ثانیه تقسیم درون و بیرون‌نمونه را خراب می‌کند.
    """
    flag = "confirm" if "confirm" in df.columns else ("confirmed" if "confirmed" in df.columns else None)
    tcol = "ts" if "ts" in df.columns else ("time" if "time" in df.columns else None)
    if flag is None:
        raise ValueError("ستون confirm نیست؛ شمع باز از بسته جدا نمی‌شود")
    seen: dict[str, Bar] = {}
    for _, r in df.iterrows():
        c = r[flag]
        try:
            c = float(c)
        except (TypeError, ValueError):
            continue
        if math.isnan(c) or c == 0:
            continue
        t = r[tcol] if tcol else r.name
        if not hasattr(t, "isoformat"):
            raise ValueError(f"زمان شمع datetime نیست: {t!r}")
        t = t.isoformat()
        o, h, lo, cl = (float(r[k]) for k in ("open", "high", "low", "close"))
        if not all(math.isfinite(x) for x in (o, h, lo, cl)):
            raise ValueError(f"قیمت نامعتبر در شمع بسته {t}")
        seen[t] = Bar(t, o, h, lo, cl, float(r.get("volume", 0.0) or 0.0))
    return sorted(seen.values(), key=lambda b: _tkey(b.t))


# ── سفارش و معامله ────────────────────────────────────────────────

@dataclass
class Order:
    side: str = "long"                 # long یا short
    kind: str = "market"               # market، stop یا limit
    price: float | None = None         # ماشه برای stop و limit
    stop: float | None = None          # حد ضرر؛ None یعنی بی حد ضرر
    targets: list = field(default_factory=list)   # [(قیمت، سهم)]، جمع سهم‌ها ≤ ۱
    time_stop: int | None = None       # خروج در بسته شدن شمع n‌ام؛ خود شمع ورود یکم
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
    pct: float = 0.0          # بازده خالص درصدی روی ارزش ورود، پس از کارمزد و لغزش
    r: float | None = None    # بازده به واحد ریسک برنامه‌ریزی‌شده
    mae_pct: float = 0.0      # بدترین حرکت خلاف پس از ورود
    mfe_pct: float = 0.0      # بهترین حرکت موافق پس از ورود
    ambiguous: bool = False   # نتیجه به فرض ترتیب درون شمع وابسته بود
    risk_pct: float | None = None   # ریسک برنامه‌ریزی‌شده، درصد ارزش ورود


class Run(list):
    """فهرست معامله‌ها؛ skipped سفارش‌هایی است که پر شدند ولی اجرا نشدند."""

    def __init__(self, *a):
        super().__init__(*a)
        self.skipped: list[dict] = []


class Past:
    """
    نمای فقط‌خواندنی شمع ۰ تا n-۱، بی کپی. اندیس منفی از آخرین شمع بسته؛ هر اندیس
    بیرون از گذشته IndexError است. برش فقط درون گذشته می‌ماند.
    """
    __slots__ = ("_b", "_n")

    def __init__(self, bars: list, n: int):
        self._b, self._n = bars, n

    def __len__(self):
        return self._n

    def __getitem__(self, k):
        if isinstance(k, slice):
            return [self._b[j] for j in range(*k.indices(self._n))]
        k = operator.index(k)
        if k < 0:
            k += self._n
        if not 0 <= k < self._n:
            raise IndexError("شمع آینده یا بیرون از گذشته")
        return self._b[k]

    def __iter__(self):
        b = self._b
        for j in range(self._n):
            yield b[j]


def _adj(price: float, side: str, entering: bool, slip_bps: float) -> float:
    """لغزش همیشه به ضرر ما: خرید گران‌تر، فروش ارزان‌تر."""
    k = slip_bps / 1e4
    buy = (side == "long") == entering
    return price * (1 + k) if buy else price * (1 - k)


def _gross(side: str, entry: float, exit_: float) -> float:
    return (exit_ - entry) / entry if side == "long" else (entry - exit_) / entry


def _validate(od: Order, ref: float) -> None:
    """سفارش ناسازگار خطای استراتژی است، نه معامله؛ پیش از ثبت رد می‌شود."""
    if od.side not in ("long", "short") or od.kind not in ("market", "stop", "limit"):
        raise ValueError(f"سو یا نوع سفارش نامعتبر: {od}")
    if od.kind != "market" and od.price is None:
        raise ValueError(f"سفارش {od.kind} بی ماشه: {od}")
    if od.time_stop is not None and od.time_stop < 1:
        raise ValueError(f"خروج زمانی کمتر از یک شمع: {od}")
    if od.expire < 1:
        raise ValueError(f"عمر سفارش کمتر از یک شمع: {od}")
    nums = [x for x in (od.price, od.stop) if x is not None] + [v for t in od.targets for v in t]
    if any(not math.isfinite(float(x)) for x in nums) or any(len(t) != 2 for t in od.targets):
        raise ValueError(f"عدد نامعتبر یا هدف بدشکل در سفارش: {od}")
    fr = [f for _, f in od.targets]
    if any(f <= 0 for f in fr) or sum(fr) > 1 + 1e-9:
        raise ValueError(f"سهم هدف‌ها باید مثبت و جمعشان حداکثر یک باشد: {od}")
    long = od.side == "long"
    if od.stop is not None and (od.stop >= ref if long else od.stop <= ref):
        raise ValueError(f"حد ضرر در سوی نادرست ماشه: {od}")
    for p, _ in od.targets:
        if p <= ref if long else p >= ref:
            raise ValueError(f"هدف در سوی نادرست ماشه: {od}")


def _fill(od: Order, b: Bar) -> float | None:
    if od.kind == "market":
        return b.o
    long = od.side == "long"
    if od.kind == "stop":
        if long and b.h >= od.price:
            return max(b.o, od.price)
        if not long and b.l <= od.price:
            return min(b.o, od.price)
    else:
        if long and b.l <= od.price:
            return min(b.o, od.price)
        if not long and b.h >= od.price:
            return max(b.o, od.price)
    return None


def _skip_reason(od: Order, px: float) -> str | None:
    """
    پر شدنی که از حد ضرر یا هدف گذشته معامله نیست؛ معامله‌گر واقعی واردش نمی‌شد.
    px قیمت خام بازار است، پیش از لغزش: لغزش نباید باز شدن زیر حد ضرر را پنهان کند.
    """
    long = od.side == "long"
    if od.stop is not None and (px <= od.stop if long else px >= od.stop):
        return "through_stop"
    if any(p <= px if long else p >= px for p, _ in od.targets):
        return "past_target"
    return None


# ── موتور ─────────────────────────────────────────────────────────

Strategy = Callable[[Past, int, dict], "Order | None"]


def run(bars: list[Bar], strategy: Strategy, *, symbol: str = "", params: dict | None = None,
        fee_bps: float = FEE_BPS, slip_bps: float = SLIP_BPS, both_hit: str = "stop") -> Run:
    """
    اجرای یک استراتژی روی یک نماد. strategy(past, i, params) در بسته شدن شمع i صدا زده
    می‌شود و فقط شمع ۰ تا i را می‌بیند. خروجی Run: فهرست Trade به‌علاوه skipped.
    """
    if both_hit not in ("stop", "target"):
        raise ValueError(f"both_hit فقط stop یا target: {both_hit!r}")
    params = dict(params or {})
    out = Run()
    pending: tuple | None = None      # سفارش، شمع ثبت، زمان سیگنال، قیمت مرجع ریسک
    pos: dict | None = None
    fee = fee_bps / 1e4
    last = len(bars) - 1

    for i, b in enumerate(bars):
        # ۱) اجرای سفارش در انتظار روی همین شمع
        if pos is None and pending is not None:
            od, born, sig_t, ref = pending
            fill = _fill(od, b)
            if fill is not None:
                pending = None
                px = _adj(fill, od.side, True, slip_bps)
                why = _skip_reason(od, fill)
                if why:
                    out.skipped.append({"symbol": symbol, "tag": od.tag, "signal_t": sig_t, "t": b.t,
                                        "reason": why})
                else:
                    long = od.side == "long"
                    pos = {"od": od, "entry": px, "ref": ref, "i0": i, "t0": b.t, "sig": sig_t,
                           "left": 1.0, "realized": 0.0, "lo": px, "hi": px, "amb": False,
                           "at_open": fill == b.o,
                           "tgt": sorted(((float(p), float(f)) for p, f in od.targets),
                                         key=lambda x: x[0], reverse=not long)}
            elif i - born >= od.expire:
                pending = None

        # ۲) مدیریت پوزیشن باز روی همین شمع، ورود همین شمع هم
        if pos is not None and _manage(pos, b, i, both_hit, slip_bps, fee):
            out.append(_finish(symbol, pos, i))
            pos = None

        # ۳) سیگنال تازه در بسته شدن شمع، فقط وقتی پوزیشن و سفارش باز نداریم
        if pos is None and pending is None and i < last:
            od = strategy(Past(bars, i + 1), i, params)
            if od is not None:
                ref = b.c if od.kind == "market" else od.price
                _validate(od, ref)
                pending = (od, i, b.t, ref)

    # پوزیشن باز در پایان داده: با بسته آخر، برچسب end
    if pos is not None:
        b = bars[-1]
        _close(pos, b, b.c, pos["left"], "end", slip_bps, fee)
        out.append(_finish(symbol, pos, last))
    return out


def _close(pos: dict, b: Bar, price: float, frac: float, reason: str, slip_bps: float, fee: float) -> bool:
    side, e = pos["od"].side, pos["entry"]
    px = _adj(price, side, False, slip_bps)
    # کارمزد ورود روی ارزش ورود، کارمزد خروج روی ارزش خروج
    pos["realized"] += frac * (_gross(side, e, px) - fee - fee * px / e)
    pos["left"] -= frac
    pos["last"] = (b.t, px, reason)
    if pos["left"] <= 1e-9:
        pos["left"] = 0.0
        return True
    return False


def _manage(pos: dict, b: Bar, i: int, both_hit: str, slip_bps: float, fee: float) -> bool:
    """یک شمع از عمر پوزیشن. True یعنی کامل بسته شد."""
    od = pos["od"]
    long = od.side == "long"
    entry_bar = i == pos["i0"]
    known = not entry_bar or pos["at_open"]      # کل شمع پس از ورود است؟
    stop = od.stop

    # حرکت خلاف و موافق: در شمع ورودِ میانه‌شمع فقط سویی که حتماً پس از پر شدن آمده
    if known or (od.kind == "limit") == long:
        pos["lo"] = min(pos["lo"], b.l)
    if known or (od.kind == "limit") != long:
        pos["hi"] = max(pos["hi"], b.h)

    def close(price, frac, reason):
        return _close(pos, b, price, frac, reason, slip_bps, fee)

    if known:
        # باز شدن اولین قیمت شمع است: ترتیبش معلوم
        if stop is not None and (b.o <= stop if long else b.o >= stop):
            return close(b.o, pos["left"], "stop")
        while pos["tgt"]:
            p, f = pos["tgt"][0]
            if not (b.o >= p if long else b.o <= p):
                break
            pos["tgt"].pop(0)
            if close(b.o, min(f, pos["left"]), "target"):
                return True

    stop_hit = stop is not None and (b.l <= stop if long else b.h >= stop)
    touched = [(p, f) for p, f in pos["tgt"] if (b.h >= p if long else b.l <= p)]
    if not known and od.kind == "limit":
        # بسته شدن پس از پر شدن است: هدفی که بسته از آن گذشته حتماً خورده شد. هدفی که فقط
        # سقف لمسش کرده شاید پیش از پر شدن بوده؛ شمرده نمی‌شود
        sure = [(p, f) for p, f in touched if (b.c >= p if long else b.c <= p)]
        if len(sure) < len(touched):
            pos["amb"] = True
        touched = sure
    if not known and od.kind == "stop" and stop_hit and (b.c > stop if long else b.c < stop):
        pos["amb"] = True              # کف شاید پیش از پر شدن بود؛ بدبینانه حد ضرر
    if stop_hit and touched:
        pos["amb"] = True

    if stop_hit and (not touched or both_hit == "stop"):
        return close(stop, pos["left"], "stop")
    for p, f in touched:
        pos["tgt"].remove((p, f))
        if close(p, min(f, pos["left"]), "target"):
            return True
    if stop_hit:
        return close(stop, pos["left"], "stop")
    if od.time_stop is not None and i - pos["i0"] + 1 >= od.time_stop:
        return close(b.c, pos["left"], "time")
    return False


def _finish(symbol: str, pos: dict, i: int) -> Trade:
    od = pos["od"]
    e = pos["entry"]
    t, px, reason = pos["last"]
    # ریسک برنامه‌ریزی‌شده به نسبت ارزش ورود واقعی: R = سود دلاری ÷ ریسک دلاری
    risk = abs(pos["ref"] - od.stop) / e if od.stop is not None else None
    pct = pos["realized"]
    if od.side == "long":
        mae, mfe = (pos["lo"] - e) / e, (pos["hi"] - e) / e
    else:
        mae, mfe = (e - pos["hi"]) / e, (e - pos["lo"]) / e
    return Trade(symbol, od.side, od.tag, pos["sig"], pos["t0"], round(e, 10), od.stop,
                 t, round(px, 10), reason, i - pos["i0"] + 1, round(100 * pct, 4),
                 round(pct / risk, 4) if risk else None, round(100 * mae, 4), round(100 * mfe, 4),
                 pos["amb"], round(100 * risk, 4) if risk else None)


# ── سنجه‌ها ────────────────────────────────────────────────────────

def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def _median(xs):
    s = sorted(xs)
    n = len(s)
    return None if not n else (s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2)


def _cluster_key(t: Trade, cluster: str, idx: int):
    """خوشه بازه اطمینان: هفته یا روز ورود. none یا زمان ناخوانا: هر معامله تنها."""
    d = _when(t.entry_t) if cluster != "none" else None
    if d is None:
        return ("one", idx)
    if cluster == "day":
        return ("day", d.date().isoformat())
    y, w, _ = d.isocalendar()
    return ("week", f"{y}-W{w:02d}")


def _boot_ci(xs: list[float], keys: list | None = None, n: int = BOOT_N,
             seed: int = BOOT_SEED) -> tuple[float, float, int] | None:
    """
    بازه ۹۰٪ میانگین با نمونه‌گیری دوباره خوشه‌ای: معامله‌های یک خوشه با هم برمی‌گردند،
    چون ریزش یک هفته همه نمادها را با هم می‌زند. کمتر از ۱۰ معامله یا خوشه: None.
    """
    keys = keys if keys is not None else list(range(len(xs)))
    groups: dict = {}
    for k, x in zip(keys, xs):
        g = groups.setdefault(k, [0.0, 0])
        g[0] += x
        g[1] += 1
    G = list(groups.values())
    k = len(G)
    if len(xs) < 10 or k < 10:
        return None
    rnd = random.Random(seed)
    ms = []
    for _ in range(n):
        tot = cnt = 0
        for _ in range(k):
            s, c = G[rnd.randrange(k)]
            tot += s
            cnt += c
        ms.append(tot / cnt)
    ms.sort()
    return ms[int(0.05 * n)], ms[int(0.95 * n) - 1], k


def _max_dd(curve: list[float]) -> float:
    peak, dd = curve[0] if curve else 0.0, 0.0
    for x in curve:
        peak = max(peak, x)
        dd = min(dd, x - peak)
    return dd


def metrics(trades: list[Trade], risk_pct: float = 1.0, cluster: str = "week",
            skipped: list[dict] | None = None) -> dict:
    """
    سنجه‌ها. درصدی روی همه معامله‌ها؛ R روی معامله‌های دارای حد ضرر، با شمارش r_n.
    منحنی R و سرمایه با ریسک ثابت هر معامله به ترتیب زمان خروج؛ سرمایه از صفر پایین‌تر
    نمی‌رود و ruined می‌شود. cluster: week، day یا none برای بازه اطمینان.
    """
    if cluster not in ("week", "day", "none"):
        raise ValueError(f"cluster فقط week، day یا none: {cluster!r}")
    n = len(trades)
    out: dict = {"n": n}
    if skipped is not None:
        out["skipped"] = {r: sum(s.get("reason") == r for s in skipped)
                          for r in sorted({s.get("reason") for s in skipped})}
    if not n:
        return out
    pcts = [t.pct for t in trades]
    out.update({
        "win_rate": round(100 * sum(p > 0 for p in pcts) / n, 2),
        "avg_pct": round(_mean(pcts), 4),
        "median_bars": _median([t.bars for t in trades]),
        "worst_mae_pct": round(min(t.mae_pct for t in trades), 4),
        "reasons": {r: sum(t.reason == r for t in trades) for r in sorted({t.reason for t in trades})},
        "ambiguous_n": sum(bool(getattr(t, "ambiguous", False)) for t in trades),
    })
    tr = sorted((t for t in trades if t.r is not None), key=lambda t: (_tkey(t.exit_t), _tkey(t.entry_t)))
    out["r_n"] = len(tr)
    if not tr:
        return out
    rs = [t.r for t in tr]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    ci = _boot_ci(rs, [_cluster_key(t, cluster, j) for j, t in enumerate(tr)])
    curve, eq, streak, worst, ruined = [0.0], 1.0, 0, 0, False
    eqc = [1.0]
    for r in rs:
        curve.append(curve[-1] + r)
        if not ruined:
            eq = max(0.0, eq * (1 + r * risk_pct / 100))
            ruined = eq <= 0.0
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
        "expectancy_r": round(_mean(rs), 4),
        "expectancy_ci90": [round(ci[0], 4), round(ci[1], 4)] if ci else None,
        "ci_clusters": ci[2] if ci else None,
        "ci_cluster": cluster,
        "small_sample": len(rs) < SMALL_N or not ci or ci[2] < SMALL_N,
        "profit_factor": round(sum(wins) / -sum(losses), 4) if losses and sum(losses) < 0 else None,
        "max_dd_r": round(_max_dd(curve), 4),
        "max_dd_pct_at_risk": round(100 * dd, 2),
        "risk_pct": risk_pct,
        "ruined": ruined,
        "longest_loss_streak": worst,
    })
    return out


def split_metrics(trades: list[Trade], split: str, risk_pct: float = 1.0, cluster: str = "week") -> dict:
    """درون‌نمونه و بیرون‌نمونه با زمان واقعی ورود — قاعده‌ای که فقط روی گذشته‌ای که دیده کار کند، حفظی است."""
    cut = _when(split)
    if cut is None:
        raise ValueError(f"زمان برش نامعتبر: {split!r}")
    def side(t):
        d = _when(t.entry_t)
        if d is None:
            raise ValueError(f"زمان ورود نامعتبر: {t.entry_t!r}")
        return d < cut
    a = [t for t in trades if side(t)]
    b = [t for t in trades if not side(t)]
    return {"split": split, "in_sample": metrics(a, risk_pct, cluster), "out_of_sample": metrics(b, risk_pct, cluster)}


# ── استراتژی‌ها ────────────────────────────────────────────────────
# هر استراتژی تابعی است (past, i, params) -> Order | None. past نمای گذشته است، نه فهرست:
# با اندیس منفی و برش کوتاه بخوان، نه با پیمایش همه گذشته در هر شمع، تا اجرا خطی بماند.

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
    cs = [b.c for b in bars[-(slow + 1):]]       # فقط پنجره لازم
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

def run_many(series: dict[str, list[Bar]], strategy: Strategy, **kw) -> Run:
    out = Run()
    for sym, bars in series.items():
        r = run(bars, strategy, symbol=sym, **kw)
        out.extend(r)
        out.skipped += r.skipped
    out.sort(key=lambda t: (_tkey(t.entry_t), t.symbol))
    return out


def render_md(name: str, m: dict, by_symbol: dict, meta: dict) -> str:
    L = [f"# شبیه‌ساز — {name}", "",
         f"نسخه {VERSION}؛ {meta.get('tf', '')}؛ {meta.get('from', '')} تا {meta.get('to', '')}؛ "
         f"کارمزد {meta.get('fee_bps')} و لغزش {meta.get('slip_bps')} واحد پایه هر طرف؛ "
         f"هر دو لمس در یک شمع: {meta.get('both_hit')}؛ خوشه بازه اطمینان: {meta.get('cluster')}. "
         f"آزمون‌نشده تا داوری کاربر.", ""]
    sk = m.get("skipped") or {}
    if sk:
        L.append("سفارش پرشده ولی اجرانشده: " + "، ".join(f"{k} {v}" for k, v in sk.items()))
        L.append("")
    if not m.get("n"):
        L.append("هیچ معامله‌ای نشد.")
        return "\n".join(L)
    ci = m.get("expectancy_ci90")
    rows = [("تعداد معامله", m["n"]), ("معامله دارای حد ضرر", m.get("r_n")), ("درصد برد", m.get("win_rate")),
            ("میانگین بازده درصدی", m.get("avg_pct")), ("میانگین سود R", m.get("avg_win_r")),
            ("میانگین ضرر R", m.get("avg_loss_r")), ("امید هر معامله R", m.get("expectancy_r")),
            ("بازه ۹۰٪ امید", f"{ci} — {m.get('ci_clusters')} خوشه" if ci else None),
            ("ضریب سود", m.get("profit_factor")),
            ("بیشترین افت R", m.get("max_dd_r")), ("بیشترین افت سرمایه با ریسک ثابت", m.get("max_dd_pct_at_risk")),
            ("طولانی‌ترین باخت پیاپی", m.get("longest_loss_streak")), ("میانه شمع نگه‌داری", m.get("median_bars"))]
    L += ["| سنجه | مقدار |", "|---|---|"] + [f"| {k} | {'—' if v is None else v} |" for k, v in rows]
    L += ["", f"معامله وابسته به فرض ترتیب درون شمع: {m.get('ambiguous_n', 0)} از {m['n']}. "
              "اگر زیاد است، با --both-hit target هم اجرا کن و فاصله دو نتیجه را ببین."]
    if m.get("small_sample"):
        L.append(f"کم‌نمونه: زیر {SMALL_N} معامله؛ بازه اطمینان قابل اتکا نیست.")
    if m.get("ruined"):
        L.append("سرمایه با این ریسک ثابت به صفر رسید.")
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
    r.add_argument("--cluster", choices=["week", "day", "none"], default="week")
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
    m = metrics(trades, a.risk_pct, a.cluster, skipped=trades.skipped)
    by = {s: metrics([t for t in trades if t.symbol == s], a.risk_pct, a.cluster,
                     skipped=[x for x in trades.skipped if x["symbol"] == s]) for s in series}
    meta = {"tf": a.tf, "from": a.start, "to": a.end, "fee_bps": a.fee_bps, "slip_bps": a.slip_bps,
            "both_hit": a.both_hit, "cluster": a.cluster}
    print(render_md(a.strategy, m, by, meta))
    sp = split_metrics(trades, a.split, a.risk_pct, a.cluster) if a.split else None
    if sp:
        print("\n" + json.dumps(sp, ensure_ascii=False))
    if a.json:
        doc = {"version": VERSION, "strategy": a.strategy, "meta": meta, "metrics": m, "by_symbol": by,
               "split": sp, "skipped": trades.skipped, "trades": [asdict(t) for t in trades]}
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
