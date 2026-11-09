"""
متن سطح‌ها و تقویم — ۹ نوامبر ۲۰۲۶، رویداد ۱۳۵.

اسکرین‌شات موجودی و تاریخچه تتر LBank، ۹ نوامبر ۲۰۲۶ حدود 10:55 وقت جهانی: نُه کوین
بی‌تغییر و تتر 1135.61630829. سه برداشت شخصی تتر ۴ نوامبر — 2، 3 و 25 — و سود خودکار
۳ تا ۹ نوامبر. بازبینی هفتگی سطح‌ها — ک۴۱: سطوح و مهرها بی‌تغییر؛ سطحی که قیمت به آن
نزدیک است پایین برده نمی‌شود. تقویم: فدرال ۹ دسامبر و تورم ۱۰ دسامبر؛ انتظار تورم ۱۰
نوامبر و انتظار و عدد واقعی اشتغال ۶ نوامبر — ک۱۳۱.

الگوی «وضعیت فعلی منهای ردیف‌های پس از آن» — تا ثبت بعدی آزمون را نشکند.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_calendar as RC
import radar_positions as P
import radar_schedule as S

ROOT = Path(__file__).resolve().parent.parent
U = timezone.utc

SEEN_1109 = {"SOL": 0.00005369, "AAVE": 1.04895, "LINK": 11.09889, "SUI": 81.6183,
             "ONDO": 115.43866, "BNB": 0.0007579, "TRX": 0.6704, "ETH": 0.000057,
             "TAO": 0.000092}
USDT_1109 = 1135.61630829
AT_1109 = "2026-11-09T10:55:00+00:00"
WITHDRAWS = [("2026-11-04T14:22:01+00:00", 2.0), ("2026-11-04T14:34:01+00:00", 3.0),
             ("2026-11-04T14:38:02+00:00", 25.0)]
INCOME = ("2026-11-09T07:43:49+00:00", 1.0994648)
# هفت ردیف Earn تاریخچه تتر، ۳ تا ۹ نوامبر — رقم‌ها عیناً از اسکرین‌شات
EARN = [0.101414, 0.168907, 0.165812, 0.165812, 0.16583, 0.165847, 0.165864]
# بازبینی ۹ نوامبر — همان سطوح و مهرهای بازبینی ۱۷ اکتبر
LEVELS = {"AAVE": 106.892, "LINK": 10.3366, "SUI": 0.6843, "ONDO": 0.3478}
SINCE = "2026-09-26T05:04:16+00:00"


@pytest.fixture(scope="module")
def h() -> dict:
    return json.loads((ROOT / "holdings.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def w() -> dict:
    return json.loads((ROOT / "watch.json").read_text(encoding="utf-8"))


def _after(h, at: str) -> list[dict]:
    t0 = datetime.fromisoformat(at)
    return [r for r in h["ledger"] if datetime.fromisoformat(r["at"]) > t0]


def test_1109_matches_screenshot(h) -> None:
    pos = {p["symbol"]: p for p in h["positions"]}
    later = _after(h, AT_1109)
    extra = {s for s, p in pos.items() if p["status"] == "open"} - set(SEEN_1109)
    assert all(any(r["symbol"] == s for r in later) for s in extra), extra
    for sym, q in SEEN_1109.items():
        moved = sum(r["delta"] for r in later if r["symbol"] == sym)
        assert P.position_qty(pos[sym]) - moved == pytest.approx(q, abs=1e-12), sym
    cash = sum(r.get("net") or 0.0 for r in later if r["action"] in ("trim", "exit"))
    cash += sum(r["cash"]["qty"] for r in later if r["action"] == "income")
    cash -= sum(r["cash"]["qty"] for r in later if r["action"] == "withdraw")
    cash -= sum(r.get("cost") or 0.0 for r in later if r["action"] in ("reenter", "add"))
    assert [c["account"] for c in h["cash"]] == ["LBank"]
    assert h["cash"][0]["qty"] - cash == pytest.approx(USDT_1109, abs=1e-9)


def test_1109_withdraws_and_income(h) -> None:
    rows = [r for r in h["ledger"]
            if r["action"] == "withdraw" and r["at"].startswith("2026-11-04")]
    assert [(r["at"], r["cash"]["qty"]) for r in rows] == WITHDRAWS
    assert all(r["symbol"] == "USDT" and r["account"] == "LBank" for r in rows)
    assert all("پول خرج شخصی" in r["reason"] for r in rows)
    inc = [r for r in h["ledger"] if r["action"] == "income" and r["at"] == INCOME[0]]
    assert len(inc) == 1 and inc[0]["cash"]["qty"] == INCOME[1]
    # محاسبه‌شده: مانده ۲ نوامبر − برداشت‌ها + سود = مانده دیده‌شده ۹ نوامبر
    assert 1164.51684349 - 30 + INCOME[1] == pytest.approx(USDT_1109, abs=1e-9)
    # جمع هفت ردیف و اختلاف ناچیز ثبت‌شده در خود ردیف
    assert sum(EARN) == pytest.approx(1.099486, abs=1e-9)
    assert sum(EARN) - INCOME[1] == pytest.approx(0.0000212, abs=1e-9)


def test_1109_holdings_stamp(h) -> None:
    assert h["updated"] == AT_1109
    assert "۹ نوامبر ۲۰۲۶" in h["source"] and "1135.61630829" in h["source"]


def test_1109_weekly_review_levels_unchanged(h, w) -> None:
    """بازبینی ۹ نوامبر: سطحی که قیمت به آن نزدیک است پایین برده نمی‌شود."""
    assert w["updated"] == AT_1109
    assert w["_بازبینی"].startswith("بازبینی هفتگی ۹ نوامبر — ک۴۱، رویداد ۱۳۵")
    wl = {p["symbol"]: p["invalidation"] for p in w["positions"]}
    hl = {p["symbol"]: p["invalidation"] for p in h["positions"] if p.get("invalidation")}
    assert wl == LEVELS and hl == LEVELS
    assert all(p["invalidation_since"] == SINCE for p in w["positions"])
    assert P.level_mismatches(h, w) == []


def test_1109_calendar() -> None:
    cal = RC.load(str(ROOT / "events_calendar.json"))
    ev = {e["id"]: e for e in cal["events"]}
    assert ev["fomc-2026-12"]["at"] == "2026-12-09T19:00:00+00:00"
    assert ev["fomc-2026-12"]["press_at"] == "2026-12-09T19:30:00+00:00"
    assert ev["cpi-2026-11"]["at"] == "2026-12-10T13:30:00+00:00"
    assert all(ev[k]["importance"] == "high" for k in ("fomc-2026-12", "cpi-2026-11"))
    assert "3.9٪" in ev["cpi-2026-10"]["expected"] and "2.8٪" in ev["cpi-2026-10"]["expected"]
    assert "65 هزار" in ev["nfp-2026-10"]["expected"]
    assert "165 هزار" in ev["nfp-2026-10"]["actual"]


def test_1109_keeper_covers_december() -> None:
    """فدرال ۹ و تورم ۱۰ دسامبر پیاپی‌اند؛ نگهبان هر دو پنجره را با سقف نسل پوشش می‌دهد."""
    cal = RC.load(str(ROOT / "events_calendar.json"))
    ev = S.keeper_simulate(cal, datetime(2026, 12, 8, 13, 23, tzinfo=U))
    pulses = [t for t, wf in ev if wf == S.PULSE_WORKFLOW]
    gens = [wf for _, wf in ev if wf != S.PULSE_WORKFLOW]
    assert len(gens) < S.KEEPER_MAX_GEN
    windows = ((datetime(2026, 12, 9, 13, 0, tzinfo=U), datetime(2026, 12, 10, 1, 30, tzinfo=U)),
               (datetime(2026, 12, 10, 7, 30, tzinfo=U), datetime(2026, 12, 10, 19, 30, tzinfo=U)))
    for a, b in windows:
        x = [t for t in pulses if a <= t <= b]
        assert len(x) >= 12
        assert max((q - p).total_seconds() for p, q in zip(x, x[1:])) <= 60 * 60
