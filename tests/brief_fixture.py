"""
سازنده سندهای کناری برای آزمون لایه پیام — متن ۳۷.

هر سند با **تابع خود سازنده** ساخته می‌شود — scan_doc، book_doc، levels_doc و همان
شکل radar_context — نه با دیکشنری دست‌نویس. پس اگر بازبینی بعدی شکل خروجی یک سازنده
را عوض کند، آزمون قرارداد همان‌جا قرمز می‌شود، پیش از push، نه بی‌صدا در تلگرام.

بی شبکه: قیمت و بسته هفتگی تزریق می‌شوند؛ دفتر کل و سطح‌ها از فایل‌های داده همان
پوشه کاری آزمون — رونوشت conftest.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import radar_book as B
import radar_levels as LV
import radar_positions as P
import radar_scan as SN
import radar_sidecar as SC
from radar_fetch3 import Field

UTC = timezone.utc

PRICES = {"BTC": 76590.4, "ETH": 2247.13, "SOL": 91.74, "BNB": 691.69, "AAVE": 125.52,
          "LINK": 11.078, "SUI": 0.8612, "ONDO": 0.3814, "TAO": 221.26, "TRX": 0.3207}
WEEKLY = {"AAVE": 134.6, "LINK": 11.393, "SUI": 0.9007, "ONDO": 0.4047, "SOL": 94.53,
          "ETH": 2275.21}
CROWD = {"BTC": (2.51, 0.62), "SOL": (3.29, 0.63), "LINK": (1.79, 1.14), "AAVE": (1.61, 1.06),
         "ETH": (2.33, 0.54), "SUI": (2.82, 0.83), "ONDO": (2.50, 0.86)}


def scan(now: datetime, prices: dict = PRICES) -> dict:
    rows = []
    for s, px in prices.items():
        r = {"symbol": s, "price": px, "score": -0.3, "covered": 6, "rsi": 34.9 if s == "BTC" else 38.0,
             "funding_8h": 0.01, "vs_ema200": float("nan"), "ema200_mature": s != "TAO"}
        if s in CROWD:
            r["ls_crowd"], r["ls_whale"] = CROWD[s]
            r["crowd_vs_whale"] = CROWD[s][0] / CROWD[s][1]
        rows.append(r)
    macro = {"fear_greed": Field(26, "alternative.me", now), "btc_dominance": Field(59.24, "cg", now),
             "btc_dom_ex_stable": Field(66.95, "cg", now), "stable_change_30d": Field(-3.6, "llama", now)}
    fred = {"derived": {"real_10y": {"label": "بازده واقعی", "value": 2.65, "read": "مثبت"}}}
    return SN.scan_doc(rows, macro, fred, ["okx", "gate"], now)


def book(now: datetime, prices: dict = PRICES, weekly: dict = WEEKLY,
         holdings: str = "holdings.json", regime_score: float = -0.816,
         actions: list | None = None) -> dict:
    h, _ = P.load(holdings, None)
    val = P.value(h, prices)
    vrow = {r["symbol"]: r for r in val["rows"] if r["book"] == "position"}
    rows = []
    for p in h["positions"]:
        if p["book"] != "position" or p["status"] != "open":
            continue
        v = vrow.get(p["symbol"], {})
        wk = ({"close": weekly[p["symbol"]], "closed_at": "2026-11-02T00:00:00+00:00"}
              if p["symbol"] in weekly and p.get("invalidation") is not None else None)
        rows.append({"pos": p, "qty": P.position_qty(p), "price": prices.get(p["symbol"]),
                     "value": v.get("value"), "dust": v.get("dust", False), "weekly": wk,
                     "rsi": 38.0, "rs30": -10.0})
    reentry = []
    for p in h["positions"]:
        if p["book"] == "position":
            st = P.reentry_state(h, p["symbol"])
            if st is None or st["used"] >= st["max_qty"] - P.TOL:
                continue
            wk = {"close": weekly.get(p["symbol"]), "closed_at": "2026-11-02T00:00:00+00:00"}
            reentry.append({"symbol": p["symbol"], "state": st, "weekly": wk, "why": []})
    reg = B.regime_row(regime_score)
    info = B.RegimeInfo(regime_score, "regime.json", [])
    heat = P.trade_heat(h, reg, val["total"])
    pos_risk = 0.0
    for r in rows:
        if r.get("dust") or r.get("value") is None:
            continue
        inv = r["pos"].get("invalidation")
        pos_risk += r["value"] if inv is None else r["qty"] * max(r["price"] - inv, 0.0)
    summary = {"actions": list(actions or []), "pos_risk": pos_risk}
    return B.book_doc(rows, reentry, val, reg, reg, info, heat, summary, [], now)


def levels(now: datetime, prices: dict = PRICES, candidate: str | None = None) -> dict:
    rows = []
    for s in ("AAVE", "LINK", "SUI", "ONDO"):
        a = LV.Assessment(symbol=s, price=prices[s], atr=prices[s] * 0.05, trend="بی‌ساختار",
                          rr=1.2, rr_tactical=0.6, verdict="روی سطح")
        if s == candidate:
            a.trend, a.rr = "صعودی", 2.4
        rows.append(a)
    return LV.levels_doc(rows, 2.0, now)


def context(now: datetime) -> dict:
    rows = [{"sid": "DCOILBRENTEU", "name": "نفت برنت", "short": "برنت", "unit": "دلار در بشکه",
             "chg_unit": "pct", "value": 123.10, "date": "2026-10-27", "prev": 115.2,
             "prev_date": "2026-10-20", "chg": 6.84, "lag_days": 7, "why": None},
            {"sid": "DGS10", "name": "بازده ۱۰ ساله", "short": "بازده ۱۰ ساله", "unit": "٪",
             "chg_unit": "pp", "value": 4.94, "date": "2026-10-30", "prev": 4.9,
             "prev_date": "2026-10-23", "chg": 0.04, "lag_days": 4, "why": None}]
    return {"version": 1, "generated": SC.stamp(now), "rows": [SC.plain_dict(r) for r in rows]}


def write_all(root: str, now: datetime | None = None, **kw) -> dict:
    """هر چهار سند کناری را در root/reports می‌نویسد؛ مسیرها را برمی‌گرداند."""
    now = now or datetime.now(UTC)
    os.makedirs(os.path.join(root, "reports"), exist_ok=True)
    docs = {"scan": scan(now), "book": book(now, **kw), "levels": levels(now), "context": context(now)}
    paths = {}
    for k, d in docs.items():
        p = os.path.join(root, "reports", f"{k}.json")
        SC.write_json(p, d)
        paths[k] = p
    return paths


def fake_fetch(days: int = 90):
    """کندل ساختگی بی شبکه — نمودار آزمون."""
    def fetch(sym: str):
        base = PRICES.get(sym, 100.0)
        t0 = datetime(2026, 8, 5, tzinfo=UTC).timestamp()
        return [[datetime.fromtimestamp(t0 + i * 86400, UTC).isoformat(),
                 base * (1 + 0.1 * ((i % 20) - 10) / 10)] for i in range(days)]
    return fetch
