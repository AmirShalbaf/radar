"""
پله نقشه ذخیره که با ابطال اجرا شد — بند ۲ متن ۱۹، ۲۶ اکتبر ۲۰۲۶.

بسته هفتگی ۲۶ اکتبر ETH زیر سطح بود؛ کاربر سفارش پله ۴ نقشه ۲۴ اکتبر — 0.0372 در 2430 —
را لغو و همان مقدار را در بازار با ابطال فروخت. فروش با ابطال فقط سهمیه ورود دوباره
ابطال می‌سازد، قاعده ت۲. اگر همان فروش پله ذخیره را هم «پر» کند، سهمیه بازخرید ذخیره هم
می‌سازد و یک فروش دو بار شمرده می‌شود. پس پله با executed و reason = invalidation بسته
می‌شود: نه مانده، نه پرشده، نه علامت بی‌پوشش، و بیرون از سهمیه بازخرید.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_book as B
import radar_positions as P
import radar_rebuy as RB
import radar_watch as W

CREATED = "2026-10-24T03:46:49+00:00"


def _row(action, sym, qty, price, at, reason, oid, level=None):
    r = {"at": at, "action": action, "symbol": sym, "delta": -qty, "price": price,
         "reason": reason, "account": "LBank", "order_id": oid,
         "gross": qty * price, "fee": 0.0, "net": qty * price}
    if level is not None:
        r["level"] = level
    return r


def _h():
    ledger = [_row("trim", "ETH", 0.037, 2381.81, "2026-10-24T03:48:34+00:00", "reserve", "a39"),
              _row("trim", "ETH", 0.0372, 2316.83, "2026-10-26T07:35:00+00:00", "invalidation",
                   "3eb", level=2380.5606)]
    return {"version": 2, "updated": "2026-10-26T07:35:00+00:00",
            "frozen": {"date": "2026-09-25", "members": {"ETH": 0.074257}, "cash": []},
            "cash": [], "ledger": ledger,
            "positions": [{"symbol": "ETH", "book": "position", "status": "open",
                           "invalidation": None,
                           "lots": [{"qty": 0.000057, "account": "LBank", "entry": None}]}]}


def _plan(mark=True):
    step4 = {"symbol": "ETH", "qty": 0.0372, "price": 2430}
    if mark:
        step4["executed"] = {"at": "2026-10-26T07:35:00+00:00", "order_id": "3eb",
                             "reason": "invalidation", "level": 2380.5606}
    return {"title": "نقشه ۲۴", "created": CREATED, "deadline": "2026-10-26T00:00:00+00:00",
            "account": "LBank",
            "steps": [{"symbol": "ETH", "qty": 0.037, "price": None,
                       "executed": {"at": "2026-10-24T03:48:34+00:00", "order_id": "a39"}},
                      step4],
            "rebuy": {"steps": [{"symbol": "ETH", "qty": 0.0742, "floor": 2380.56,
                                 "min_below_sale_pct": 5}]}}


def test_one_sale_one_quota() -> None:
    h, rp = _h(), _plan()
    W.validate_watch({"reserve_plan": rp})
    assert W.step_filled(rp, h) == [True, False]
    assert W.unfilled_steps(rp, h) == []                      # پله ۴ مانده نیست
    (st,) = W.rebuy_status(rp, h, {})
    assert st["sold"] == pytest.approx(0.037) and st["open"] == pytest.approx(0.037)
    re = P.reentry_state(h, "ETH")
    assert re["max_qty"] == pytest.approx(0.0372) and re["level"] == 2380.5606
    # جمع دو سهمیه برابر جمع فروش‌هاست، نه بیشتر
    assert st["open"] + re["max_qty"] == pytest.approx(0.037 + 0.0372)


def test_unmarked_step_stays_open_and_is_not_filled_by_invalidation() -> None:
    h, rp = _h(), _plan(mark=False)
    assert W.step_filled(rp, h) == [True, False]
    assert [s["qty"] for s in W.unfilled_steps(rp, h)] == [0.0372]


def test_no_stray_warning_for_invalidation_step() -> None:
    h, rp = _h(), _plan()
    msgs = W.check_positions({"reserve_plan": rp}, h, {}, W.datetime(2026, 10, 25, 12,
                                                                     tzinfo=W.UTC),
                             weekly=lambda s: (None, []), price=lambda s: None)
    assert not [m for m in msgs if "علامت اجراشده" in m]


def test_validation_of_reason() -> None:
    rp = _plan()
    rp["steps"][1]["executed"]["reason"] = "خرید"
    with pytest.raises(W.WatchError):
        W.validate_watch({"reserve_plan": rp})
    rp = _plan()
    del rp["steps"][1]["executed"]["level"]
    with pytest.raises(W.WatchError):
        W.validate_watch({"reserve_plan": rp})


def test_quota_table_and_book_show_it() -> None:
    h, rp = _h(), _plan()
    rows = RB.quota_table({"reserve_plan": rp}, h)
    assert rows[0]["sold"] == pytest.approx(0.037)
    val = {"rows": [], "total": 100.0, "stable_usd": 40.0}
    rv = B.reserve_view(rp, h, {"ETH": 2300.0}, val, W.datetime(2026, 10, 26, 8, tzinfo=W.UTC))
    assert rv["left"] == [] and rv["stray"] == []
    txt = "\n".join(B._reserve_lines(rv, None))
    assert "اجراشده با ابطال" in txt and "0.0372" in txt
