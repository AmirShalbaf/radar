"""
نقشه ذخیره ۲۴ اکتبر ۲۰۲۶ — باند انقباضی، RD-20261024-01. متن ۱۶.

رژیم ‎-0.946 باند انقباضی در گزارش ۲۳ اکتبر، هدف ذخیره ۴۰٪. سه فروش در LBank —
TAO کامل، ETH نیمه بازار و SOL کم — و نیمه دوم ETH محدود در 2430. بازخرید با
قاعده ۵٪ رویداد ۹۸: سقف TAO 241.68، ETH 2262.72 زیر کف پس بسته، SOL 97.432.
سفارش بازخرید SOL در 97.60 بالای سقف است — سرپیچی آگاهانه ثبت‌شده در
RD-20261024-01؛ قاعده در کد شل نشد، پس rebuy_status آن را «بالای سقف» می‌خواند.

قفل داده: این آزمون فایل واقعی را می‌خواند و با هر بازبینی نقشه عوض می‌شود.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_positions as P
import radar_watch as W

ROOT = Path(__file__).resolve().parent.parent
CREATED = "2026-10-24T03:46:49+00:00"


@pytest.fixture(scope="module")
def files():
    w = json.loads((ROOT / "watch.json").read_text(encoding="utf-8"))
    h = json.loads((ROOT / "holdings.json").read_text(encoding="utf-8"))
    return w, h


def _plan(w: dict) -> dict:
    """نقشه ۲۴ اکتبر، فعال یا بایگانی — متن ۱۹ آن را بست."""
    plans = ([w["reserve_plan"]] if w.get("reserve_plan") else []) + w.get("reserve_archive", [])
    (rp,) = [p for p in plans if p["created"] == CREATED]
    return rp


def test_plan_shape(files) -> None:
    w, h = files
    W.validate_watch(w)
    assert P.level_mismatches(h, w) == [] and P.anchor_violations(w) == []
    rp = _plan(w)
    assert rp["title"] == "نقشه ذخیره ۲۴ اکتبر — باند انقباضی"
    assert (rp["created"], rp["deadline"], rp["account"]) == \
        (CREATED, "2026-10-26T00:00:00+00:00", "LBank")
    assert rp["on_deadline"] == {"cancel_if_band_at_least": "محتاط", "otherwise": "market"}
    assert [(s["symbol"], s["qty"], s["price"]) for s in rp["steps"]] == \
        [("TAO", 0.1538, 254.4), ("ETH", 0.037, None), ("SOL", 0.15, None),
         ("ETH", 0.0372, 2430)]
    assert [s["executed"]["order_id"] for s in rp["steps"][:3]] == [
        "4395c156-03ce-4604-83c3-ed74a5d55961", "a39a661a-34f9-4e1a-b9d6-7e244b797cca",
        "fe063a55-bd90-47aa-935d-c7817c807f3d"]
    # پله ۴ با ابطال اجرا شد — متن ۱۹، ۲۶ اکتبر؛ سهمیه بازخرید نمی‌سازد
    ex = rp["steps"][3]["executed"]
    assert (ex["reason"], ex["level"], ex["order_id"], ex["at"]) == (
        "invalidation", 2380.5606, "3eb65762-9c82-48cb-83ff-ec340c3ea623",
        "2026-10-26T07:35:00+00:00")
    assert [(s["symbol"], s["qty"], s["floor"], s["min_below_sale_pct"])
            for s in rp["rebuy"]["steps"]] == \
        [("TAO", 0.1538, 202.51, 5), ("ETH", 0.0742, 2380.56, 5), ("SOL", 0.15, 96.71, 5)]


def test_old_plan_archived(files) -> None:
    w, _ = files
    old = [p for p in w["reserve_archive"] if p["created"] == "2026-10-17T15:32:00+00:00"]
    assert len(old) == 1 and old[0]["closed"]["at"] == "2026-10-21T13:06:34+00:00"


def test_three_steps_filled_from_ledger(files) -> None:
    w, h = files
    prog = W.reserve_progress(_plan(w), h)
    assert [s["filled"] for s in prog] == [True, True, True, False]
    assert [s["fill_price"] for s in prog[:3]] == [254.4, 2381.81, 102.56]
    # پله ۴ با ابطال بسته شد — نه مانده، نه پرشده؛ فروش ابطال ۲۶ اکتبر پرش نمی‌کند
    assert prog[3]["by_invalidation"]
    assert W.unfilled_steps(_plan(w), h) == []


def test_rebuy_ceilings_and_sol_defiance_stays_outside_rule(files) -> None:
    w, h = files
    rb = {r["symbol"]: r for r in W.rebuy_status(_plan(w), h,
                                                  {"TAO": 233.0, "ETH": 2400.0, "SOL": 97.60})}
    assert rb["TAO"]["ceiling"] == pytest.approx(241.68) and rb["TAO"]["window"] == "open"
    assert rb["ETH"]["ceiling"] == pytest.approx(2262.7195) and rb["ETH"]["window"] == "no_gap"
    assert rb["ETH"]["sold"] == 0.037                    # پله ۴ پر نشده — تا مقدار پرشده
    assert rb["SOL"]["ceiling"] == pytest.approx(97.432)
    assert rb["SOL"]["window"] == "above"                 # 97.60 بالای سقف — قاعده شل نشد
    assert 100 * (1 - 97.60 / 102.56) == pytest.approx(4.836, abs=0.001)


def test_notes_carry_decision(files) -> None:
    rp = files[0]["reserve_plan"]
    for x in ("RD-20261024-01", "-0.946", "1625.64", "419.42", "561.88", "652.2",
              "15ad3c3b-f2aa-406c-ba81-5e43706fe87a", "2380.56", "exit",
              "e01c4e5c-d85c-41fc-aac4-805c985be802", "ب۱"):
        assert x in rp["note"], x
    for x in ("241.68", "2262.72", "97.432", "d320d08b-4974-4ce2-9bd5-ec6b472ec7c8",
              "c1d4c513-ec1d-4f36-a8ca-22bcac970294", "97.60", "سرپیچی آگاهانه",
              "RD-20261024-01", "۱۰۳"):
        assert x in rp["rebuy"]["note"], x


def test_tao_left_position_watch(files) -> None:
    w, _ = files
    assert "TAO" not in {p["symbol"] for p in w["positions"]}


def test_journal_decision(files) -> None:
    j = json.loads((ROOT / "radar_journal.json").read_text(encoding="utf-8"))
    d = [r for r in j["decisions"] if r["decision_id"] == "RD-20261024-01"]
    assert len(d) == 1
    r = d[0]
    assert (r["at"], r["human"], r["regime_band"], r["regime_score"]) == \
        (CREATED, "followed", "انقباضی", -0.946)
    assert r["symbols"] == ["TAO", "ETH", "SOL"]
    assert "سرپیچی کوچک" in r["note"] and "97.60" in r["note"] and "97.432" in r["note"]
