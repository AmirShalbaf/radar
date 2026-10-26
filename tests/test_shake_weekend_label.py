"""
برچسب آخر هفته — بند ۶ متن ۲۰، ۲۷ اکتبر ۲۰۲۶. هشدار تکانی که شنبه یا یکشنبه UTC ساخته شود،
این برچسب را می‌گیرد: «حرکت آخر هفته — تا باز شدن بازار آمریکا تأییدنشده».
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_watch as W

UTC = timezone.utc
LABEL = "حرکت آخر هفته — تا باز شدن بازار آمریکا تأییدنشده"


def _bars(closes, end):
    last_open = end.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    return [{"open": last_open - timedelta(hours=len(closes) - 1 - i), "close": float(c),
             "low": float(c) * 0.999, "high": float(c) * 1.001} for i, c in enumerate(closes)]


def _alerts(now, regime=None, history=None):
    w = {"positions": [{"symbol": "SOL", "invalidation": 96.7108,
                        "invalidation_since": "2026-09-25T21:34:47+00:00"}]}
    h = {"positions": [{"symbol": "SOL", "book": "position", "status": "open",
                        "invalidation": 96.7108, "invalidation_since": "2026-09-25T21:34:47+00:00",
                        "lots": [{"qty": 5.0, "account": "LBank", "entry": None}]}],
         "ledger": [], "cash": []}
    feed = {"BTC": _bars([80000.0] * 26 + [81000, 82000, 83000, 84500.0], now),   # +5.6٪
            "SOL": _bars([99.0] * 29 + [97.9], now)}                             # نزدیک سطح
    return W.shake_alerts(w, h, {}, now, hourly=lambda s: (feed.get(s), []),
                          sigma=lambda s, hrs: (None, ["آزمون"]), regime=regime, history=history)


@pytest.mark.parametrize("now", [datetime(2026, 10, 31, 0, 41, tzinfo=UTC),     # شنبه
                                 datetime(2026, 11, 1, 23, 41, tzinfo=UTC)])    # یکشنبه
def test_weekend_alerts_labelled(now) -> None:
    msgs = _alerts(now)
    assert len(msgs) == 2
    assert all(m.startswith(LABEL) for m in msgs)


@pytest.mark.parametrize("now", [datetime(2026, 10, 30, 23, 41, tzinfo=UTC),    # جمعه
                                 datetime(2026, 11, 2, 0, 41, tzinfo=UTC)])     # دوشنبه
def test_weekday_alerts_unlabelled(now) -> None:
    msgs = _alerts(now)
    assert len(msgs) == 2 and not any(LABEL in m for m in msgs)


def test_regime_band_alert_on_weekend_labelled_too() -> None:
    now = datetime(2026, 10, 31, 6, 41, tzinfo=UTC)
    regime = {"generated_at": "2026-10-31T06:40:00+00:00", "score": -1.25,
              "band": {"name": "بحرانی"}, "trade_band": {"name": "انقباضی"}}
    history = {"days": {"2026-10-30": {"band": "انقباضی"}}}
    msgs = _alerts(now, regime, history)
    reg = [m for m in msgs if "باند خام رژیم" in m]
    assert len(reg) == 1 and reg[0].startswith(LABEL)
