"""
یک تعریف میانگین ساده ۵۰ هفته در regime.json — نشست ۳ب، بند ۵.

تا نشست ۳ب دو تعریف بود: ورودی ma50w از کندل هفتگی candles_first_ok با لنگر
هنگ‌کنگ، و میدان btc_sma50w از radar_positions.sma_weekly با وقت جهانی و فقط
هفته‌های بسته‌شده. برای هفته بسته 2026-09-21 اولی 78822.00 داد و دومی
78822.346. حالا ورودی ma50w از همان sma_weekly می‌خواند — یک واکشی، یک عدد —
و آزمون برابری دو میدان را در سند regime.json قفل می‌کند.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_fetch3 as R
import radar_regime as G

UTC = timezone.utc
NOW = datetime(2026, 9, 29, 7, 0, tzinfo=UTC)
WEEK = "2026-09-28T00:00:00+00:00"
SMA = {"value": 80.0, "weeks": 50, "close": 90.0, "week_open": "2026-09-21T00:00:00+00:00",
       "week_closed_at": WEEK, "venue": "okx"}
COLS = ["ts", "open", "high", "low", "close", "vol"]


def _frame(n: int, bar: str, px) -> pd.DataFrame:
    step = pd.Timedelta(seconds=R.BAR_SECONDS[bar])
    last = pd.Timestamp(NOW).floor("D")
    rows = [[int((last - step * (n - 1 - i)).timestamp() * 1000), px(i), px(i), px(i),
             px(i), 1.0] for i in range(n)]
    df = R._df(rows, COLS)
    df["confirm"] = [1] * (n - 1) + [0]
    return R.enrich(df)


def _src(sma=SMA, why=None) -> dict:
    daily = _frame(700, "1D", lambda i: 110.0 if i == 699 else 105.0)
    # کندل هفتگی قدیمی با میانگین ۱۰۰ — نباید خوانده شود
    weekly = _frame(80, "1W", lambda i: 100.0)
    return {"fred": {"raw": {}, "derived": {}}, "macro": {},
            "btc": {"1D": daily, "1W": weekly}, "ethbtc": None,
            "sma50w": sma, "sma50w_why": why or []}


def test_ma50w_reads_sma_weekly() -> None:
    i = G.measure(_src(), {"version": 1, "days": {}}, NOW)["ma50w"]
    assert i.value == pytest.approx(100 * (110.0 / 80.0 - 1))       # نه 10٪ کندل هفتگی
    assert i.obs["btc_sma50w"] == 80.0
    assert i.ts == datetime.fromisoformat(WEEK)


def test_ma50w_absent_with_sma_reason() -> None:
    i = G.measure(_src(sma=None, why=["okx: نابالغ: 30 هفته بسته، ۵۰ لازم"]),
                  {"version": 1, "days": {}}, NOW)["ma50w"]
    assert i.score is None and "نابالغ" in i.reason


def test_ma50w_stale_week_is_absent() -> None:
    old = dict(SMA, week_closed_at="2026-09-07T00:00:00+00:00")
    i = G.measure(_src(sma=old), {"version": 1, "days": {}}, NOW)["ma50w"]
    assert i.score is None and "کهنه" in i.reason


def test_regime_json_two_fields_equal(tmp_path, monkeypatch) -> None:
    """قفل برابری در خود سند: میانگین ورودی ma50w همان btc_sma50w است."""
    monkeypatch.setattr(G, "gather", lambda order, now=None: _src())
    j = tmp_path / "regime.json"
    # ساعت تزریقی — نشست ۶. با ساعت واقعی، هفته بسته WEEK از 2026-10-12
    # کهنه می‌شد و main با پوشش صفر برمی‌گشت: بمب ساعتی، یافته اسکن ساعت جابه‌جا.
    assert G.main(["--json", str(j), "--history", str(tmp_path / "h.json"),
                   "--report", str(tmp_path / "r.md")], now=NOW) == 0
    doc = json.loads(j.read_text(encoding="utf-8"))
    ma = next(x for x in doc["inputs"] if x["key"] == "ma50w")
    assert ma["obs"]["btc_sma50w"] == doc["btc_sma50w"]["value"] == 80.0
    assert "هنگ‌کنگ" not in doc["btc_sma50w"]["definition"]


def test_gather_fetches_sma_once(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(R, "fetch_fred", lambda http_text: {"raw": {}, "derived": {}})
    monkeypatch.setattr(R, "fetch_macro", lambda out: None)
    monkeypatch.setattr(R, "probe_venues", lambda order: (list(order), []))
    monkeypatch.setattr(R, "candles_first_ok", lambda *a, **k: ({}, None, None))
    monkeypatch.setattr(G.P, "sma_weekly",
                        lambda *a, **k: calls.append(k.get("now")) or (SMA, []))
    src = G.gather(["okx"], NOW)
    assert src["sma50w"] == SMA and calls == [NOW]
