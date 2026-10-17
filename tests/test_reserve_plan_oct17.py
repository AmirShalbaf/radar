"""
نقشه ذخیره ۱۷ اکتبر ۲۰۲۶ — پس از برداشت تتر. مرور هفتگی، RD-20261017-01.

نقشه ۸ اکتبر — رویداد ۸۹ — در مهلت ۱۵ اکتبر اجرا نشد؛ کاربر دور بود. ۱۷ اکتبر دو
سفارش محدودش لغو شد و کاربر ۳۳۴.۸ دلار تتر را برای خرج شخصی برداشت. ذخیره
0.42 دلار ماند، رژیم محتاط ‎-0.426 و هدف ۲۵٪. ترتیب بخش ۵: BNB سپس ETH.

قرارداد:
- BNB 0.327 در بازار فروخته شد — پله بازار با price برابر null و executed، همان
  قالب پله‌های بازار نقشه رویداد ۳۶. پرشدنش از دفتر کل است، نه از executed.
- ETH 0.074 با سفارش محدود در 2490؛ مهلت 2026-10-19 00:00 UTC، شرط مهلت مثل قبل.
- بازخرید: کف همان سطح ابطال، ۵٪ زیر فروش واقعی. محاسبه‌شده: هیچ‌کدام پنجره
  نزدیک ابطال ندارند — BNB 718.07 × 0.95 = 682.1665 و ETH 2490 × 0.95 = 2365.5،
  هر دو زیر کف.
- BNB مانده ناچیز است و از پایش موقعیت بیرون رفت؛ بازبینی هفتگی ۱۷ اکتبر.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_positions as P
import radar_watch as W

ROOT = Path(__file__).resolve().parent.parent
CREATED = "2026-10-17T15:32:00+00:00"


@pytest.fixture(scope="module")
def files():
    w = json.loads((ROOT / "watch.json").read_text(encoding="utf-8"))
    h = json.loads((ROOT / "holdings.json").read_text(encoding="utf-8"))
    return w, h


def test_plan_shape(files) -> None:
    w, _ = files
    W.validate_watch(w)
    rp = w["reserve_plan"]
    assert rp["title"] == "نقشه ذخیره ۱۷ اکتبر — پس از برداشت تتر"
    assert rp["created"] == CREATED and rp["deadline"] == "2026-10-19T00:00:00+00:00"
    assert rp["account"] == "LBank"
    assert rp["on_deadline"] == {"cancel_if_band_at_least": "سازنده", "otherwise": "market"}
    assert [(s["symbol"], s["qty"], s["price"]) for s in rp["steps"]] == \
        [("BNB", 0.327, None), ("ETH", 0.074, 2490)]
    ex = rp["steps"][0]["executed"]
    assert ex == {"at": "2026-10-17T15:33:55+00:00",
                  "order_id": "8c103fa9-64c1-493e-9f3d-1f3c3ae36102",
                  "avg_price": 718.07, "gross": 234.80889, "fee": 0.234809}
    assert "executed" not in rp["steps"][1] and "cancelled" not in rp["steps"][1]
    assert [(s["symbol"], s["qty"], s["floor"], s["min_below_sale_pct"])
            for s in rp["rebuy"]["steps"]] == \
        [("BNB", 0.327, 702.39, 5), ("ETH", 0.074, 2380.56, 5)]


def test_plan_note_carries_decision(files) -> None:
    rp = files[0]["reserve_plan"]
    for x in ("-0.426", "۲۵٪", "1,648", "0.42", "-9.2٪", "-7.1٪", "بازار",
              "7e76721a-0cc5-408a-b3a0-e07b135189bd", "15:35:50 UTC", "2380.56", "exit",
              "RD-20261017-01"):
        assert x in rp["note"], x
    for x in ("682.17", "2365.5", "محاسبه‌شده"):
        assert x in rp["rebuy"]["note"], x


def test_bnb_step_filled_from_ledger(files) -> None:
    w, h = files
    prog = W.reserve_progress(w["reserve_plan"], h)
    assert [s["filled"] for s in prog] == [True, False]
    assert prog[0]["fill_price"] == 718.07
    assert prog[0]["fill_at"].isoformat() == "2026-10-17T15:33:55+00:00"
    assert W.unfilled_steps(w["reserve_plan"], h) == [
        {"symbol": "ETH", "qty": 0.074, "price": 2490}]


def test_rebuy_has_no_near_invalidation_window(files) -> None:
    w, h = files
    rb = {r["symbol"]: r for r in W.rebuy_status(w["reserve_plan"], h,
                                                  {"BNB": 690.0, "ETH": 2400.0})}
    assert rb["BNB"]["sale"] == 718.07 and rb["BNB"]["window"] == "no_gap"
    assert rb["BNB"]["ceiling"] == pytest.approx(682.1665)
    assert rb["ETH"]["window"] == "unsold"
    # اگر ETH در 2490 پر شود، سقف زیر کف است — پنجره‌ای نیست
    assert 2490 * 0.95 == pytest.approx(2365.5) and 2365.5 < 2380.56


def test_bnb_left_position_watch(files) -> None:
    w, h = files
    assert "BNB" not in {p["symbol"] for p in w["positions"]}
    assert P.level_mismatches(h, w) == []


def test_weekly_review_stamp(files) -> None:
    w, _ = files
    assert w["updated"] == "2026-10-17T15:40:00+00:00"
    assert w["_بازبینی"] == ("بازبینی هفتگی ۱۷ اکتبر با تحلیل‌گر — هیچ ابطالی با بسته "
                            "هفتگی ۱۲ اکتبر نقض نشده؛ سطوح بی‌تغییر")
