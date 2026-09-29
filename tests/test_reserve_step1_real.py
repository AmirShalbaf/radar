"""
پله اول نقشه ذخیره، دو فروش واقعی LBank — نشست ۳، ۲۶ سپتامبر ۲۰۲۶.

از رسیدها، زمان تهران به وقت جهانی برگردانده شد:
- SOL: بازار، 0.749 در 121.33، مجموع 90.87617، کارمزد 0.090876،
  2026-09-25T22:09:00Z، سفارش 6663fe17-13ce-44a7-927a-fee8784cd6c0
- ETH: بازار، 0.0472 در 2685.33، مجموع 126.747576، کارمزد 0.126748،
  2026-09-25T22:10:21Z، سفارش e6c70733-5c87-4de6-bad7-3166860aeb96
خالص پس از کارمزد، جمعاً 217.406122 تتر، به نقد LBank. قفل داده است.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_positions as P
import radar_watch as W

ROOT = Path(__file__).resolve().parent.parent
SALES = {
    "SOL": {"at": "2026-09-25T22:09:00+00:00", "qty": 0.749, "price": 121.33,
            "gross": 90.87617, "fee": 0.090876, "order_id": "6663fe17-13ce-44a7-927a-fee8784cd6c0"},
    "ETH": {"at": "2026-09-25T22:10:21+00:00", "qty": 0.0472, "price": 2685.33,
            "gross": 126.747576, "fee": 0.126748, "order_id": "e6c70733-5c87-4de6-bad7-3166860aeb96"},
}


def _load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_ledger_has_both_receipts() -> None:
    h = _load("holdings.json")
    rows = [r for r in h["ledger"] if r["action"] == "trim" and r["reason"] == "reserve"]
    assert [r["symbol"] for r in rows] == ["SOL", "ETH"]        # به ترتیب زمان رسید
    for r in rows:
        s = SALES[r["symbol"]]
        assert r["at"] == s["at"] and r["delta"] == -s["qty"] and r["price"] == s["price"]
        assert r["gross"] == s["gross"] and r["fee"] == s["fee"]
        assert r["order_id"] == s["order_id"] and r["account"] == "LBank"


def test_cash_and_quantities() -> None:
    h, j = P.load(str(ROOT / "holdings.json"), str(ROOT / "radar_journal.json"))
    cash = {c["account"]: c["qty"] for c in h["cash"]}
    assert cash["LBank"] == pytest.approx(0.1010102 + 217.406122, abs=1e-9)
    lots = {p["symbol"]: {l["account"]: l["qty"] for l in p["lots"]} for p in h["positions"]}
    assert lots["SOL"]["LBank"] == pytest.approx(6.38005369 - 0.749, abs=1e-12)
    assert lots["ETH"]["LBank"] == pytest.approx(0.242657 - 0.0472, abs=1e-12)
    # «صرافی دوم» ۲۹ سپتامبر با withdraw از رادار رفت — ETH رادار فقط LBank است
    assert "صرافی دوم" not in cash and "صرافی دوم" not in lots["ETH"]


def test_optcost_followup_from_sale_day() -> None:
    exits = {r["order_id"]: r for r in _load("radar_optcost.json")["exits"]}
    for sym, s in SALES.items():
        r = exits[s["order_id"]]
        assert r["symbol"] == sym and r["date"] == "2026-09-25" and r["at"] == s["at"]
        assert r["action"] == "trim" and r["reason"] == "reserve"


def test_watch_marks_and_no_market_reminder() -> None:
    w, h = _load("watch.json"), _load("holdings.json")
    W.validate_watch(w)
    steps = w["reserve_plan"]["steps"]
    marked = {s["symbol"]: s["executed"] for s in steps if s.get("executed")}
    assert {k: v["order_id"] for k, v in marked.items()} == \
        {k: v["order_id"] for k, v in SALES.items()}
    assert all(s["price"] is None for s in steps if s.get("executed"))
    assert W.unfilled_steps(w["reserve_plan"], h) == [
        {"symbol": "ETH", "qty": 0.0472, "price": 2755}, {"symbol": "ETH", "qty": 0.0472, "price": 2940},
        {"symbol": "SOL", "qty": 0.749, "price": 125.5}, {"symbol": "SOL", "qty": 0.749, "price": 131.5}]


def test_eth_step2_moved_below_utc_resistance() -> None:
    """
    نشست ۳ب، بند ۷: کاربر سفارش ETH 2790 را در LBank به 2755 برد — زیر مقاومت
    2760.76 با لنگر جهانی. مقاومت 131.81 که دلیل پله سوم SOL بود، با لنگر
    جهانی دیگر نیست. note نقشه هر دو را می‌گوید.
    """
    rp = _load("watch.json")["reserve_plan"]
    assert [s["price"] for s in rp["steps"] if s["symbol"] == "ETH"] == [None, 2755, 2940]
    assert "2760.76" in rp["note"] and "131.81" in rp["note"]
    assert "2790" in rp["note"]                      # جابه‌جایی ثبت شده، نه پاک
