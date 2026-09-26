"""
قاعده لنگر سطح ابطال — نشست ۳، ایستگاه آخر، بند ۲، تصمیم کاربر ۲۶ سپتامبر ۲۰۲۶.

اشکال: سطح‌های ایستگاه دو نسبت به قیمت زنده وسط یک هفته صعودی انتخاب شدند،
ولی با بسته هفتگی داوری می‌شوند. بسته هفتگی ONDO تا 2026-09-21 برابر 0.4326
بود و سطحش 0.4457 — سطح از روز اول بالای آخرین بسته بود.

قاعده: سطح ابطال دست‌کم ۱ ATR هفتگی زیر min(قیمت فعلی، آخرین بسته هفتگی
بسته‌شده). دقیقاً ۱ ATR پذیرفته است.
- radar_positions: تنها منبع قاعده، کتابخانه استاندارد.
- radar_levels.pick_invalidation: هنگام انتخاب.
- پایشگر و سبد: هنگام بارگذاری، از لنگر ثبت‌شده در watch.json، هشدار صریح.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_levels as L
import radar_positions as P
import radar_watch as W

UTC = timezone.utc


# ═══════════════ قاعده، تنها منبع ═══════════════

def test_anchor_is_min_of_price_and_weekly_close() -> None:
    assert P.invalidation_anchor(0.5495, 0.4326) == 0.4326
    assert P.invalidation_anchor(100.0, 103.0) == 100.0


@pytest.mark.parametrize("level, ok", [
    (90.0, True),               # دقیقاً ۱ ATR: پذیرفته
    (90.000001, False),         # یک مو کمتر از ۱ ATR: رد
    (85.0, True),
])
def test_anchor_ok_boundary(level, ok) -> None:
    assert P.anchor_ok(level, 100.0, 10.0) is ok


def test_anchor_ok_exact_boundary_survives_float_error() -> None:
    """0.5 − 0.45 در ممیز شناور 0.04999999999999999 است — باز هم دقیقاً ۱ ATR."""
    assert 0.5 - 0.45 < 0.05
    assert P.anchor_ok(0.45, 0.5, 0.05) is True


def test_ondo_level_fails_the_rule() -> None:
    assert P.anchor_ok(0.4457, P.invalidation_anchor(0.5495, 0.4326), 0.05) is False


# ═══════════════ radar_levels — هنگام انتخاب ═══════════════

def _daily(n: int = 200) -> pd.DataFrame:
    """کف روزانه 99؛ دو برخورد در 88 و دو برخورد در 80. ATR روزانه حدود 2."""
    t0 = pd.Timestamp("2026-01-01", tz="UTC")
    lows = [99.0] * n
    for i in (50, 120):
        lows[i] = 88.0
    for i in (70, 150):
        lows[i] = 80.0
    return pd.DataFrame({"ts": [t0 + pd.Timedelta(days=i) for i in range(n)],
                         "open": 100.0, "high": 101.0, "low": lows, "close": 100.0,
                         "confirm": 1})


def _weekly(n: int = 40) -> pd.DataFrame:
    """دامنه هفتگی ثابت 10 — ATR هفتگی دقیقاً 10؛ کف‌ها برابرند، پس نقطه چرخش نیست."""
    t0 = pd.Timestamp("2025-06-02", tz="UTC")
    return pd.DataFrame({"ts": [t0 + pd.Timedelta(weeks=i) for i in range(n)],
                         "open": 100.0, "high": 105.0, "low": 95.0, "close": 100.0,
                         "confirm": 1})


def _pick(price, week_close):
    wc = _weekly()
    wc.loc[wc.index[-1], "close"] = week_close
    return L.pick_invalidation(_daily(), wc, price)


def test_pick_uses_price_when_lower_anchor_is_price() -> None:
    lv = _pick(100.0, 100.0)
    assert lv["level"] == pytest.approx(88.0)
    assert lv["anchor"] == 100.0


def test_pick_uses_weekly_close_when_lower() -> None:
    """قیمت 100 ولی بسته هفتگی 97: 88 فقط 0.9 ATR زیر 97 است — رد؛ 80 انتخاب."""
    lv = _pick(100.0, 97.0)
    assert lv["level"] == pytest.approx(80.0)
    assert lv["anchor"] == 97.0


def test_pick_exactly_one_atr_accepted() -> None:
    lv = _pick(100.0, 98.0)                     # 98 − 88 = 10 = دقیقاً ۱ ATR
    assert lv["level"] == pytest.approx(88.0)


def test_pick_none_when_no_valid_level() -> None:
    lv = _pick(100.0, 89.9)                     # 80 فقط 0.99 ATR زیر لنگر
    assert lv["level"] is None and "معتبر" in lv["reason"]


# ═══════════════ پایشگر و سبد — هنگام بارگذاری ═══════════════

STAMP = "2026-09-25T21:34:47+00:00"


def _watch(**anchor) -> dict:
    it = {"symbol": "ONDO", "invalidation": 0.4457, "invalidation_since": STAMP,
          "touches": 3, "warnings": []}
    it.update(anchor)
    return {"version": 2, "updated": STAMP, "positions": [it], "items": []}


def test_violation_reported() -> None:
    w = _watch(anchor=0.4326, anchor_atr_w=0.05, anchor_price=0.5495,
               anchor_week_close=0.4326)
    bad = P.anchor_violations(w)
    assert len(bad) == 1 and "ONDO" in bad[0] and "ATR" in bad[0]


def test_exactly_one_atr_not_reported() -> None:
    w = _watch(invalidation=0.45, anchor=0.5, anchor_atr_w=0.05)
    w["positions"][0]["invalidation"] = 0.45
    assert P.anchor_violations(w) == []


def test_missing_anchor_reported() -> None:
    bad = P.anchor_violations(_watch())
    assert len(bad) == 1 and "لنگر" in bad[0] and "ثبت نشده" in bad[0]


def test_watcher_warns_on_violation() -> None:
    w = _watch(anchor=0.4326, anchor_atr_w=0.05)
    h = {"version": 2, "frozen": {"date": "2026-09-25", "members": {"ONDO": 1.0}},
         "positions": [{"symbol": "ONDO", "book": "position", "status": "open",
                        "invalidation": 0.4457, "invalidation_since": STAMP,
                        "lots": [{"qty": 1.0, "account": "A", "entry": None}]}],
         "ledger": []}
    msgs = W.check_positions(w, h, {}, datetime(2026, 9, 26, tzinfo=UTC),
                             weekly=lambda s: (None, ["آزمون"]), price=lambda s: None)
    assert any("قاعده لنگر" in m and "ONDO" in m for m in msgs)


def test_book_level_check_warns_on_violation(tmp_path) -> None:
    import json
    import radar_book as B
    p = tmp_path / "watch.json"
    p.write_text(json.dumps(_watch(anchor=0.4326, anchor_atr_w=0.05), ensure_ascii=False),
                 encoding="utf-8")
    h = {"version": 2, "positions": [{"symbol": "ONDO", "book": "position", "status": "open",
                                      "invalidation": 0.4457, "invalidation_since": STAMP,
                                      "lots": []}], "ledger": []}
    notes, error = B.level_check(h, str(p))
    assert any("قاعده لنگر" in n and "ONDO" in n for n in notes)
    assert error is False                      # هشدار صریح، نه خطا
