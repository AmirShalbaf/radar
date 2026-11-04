"""
رفع‌های کوچک پیش از دسامبر — متن ۳۸.

۱. سقف نسل نگهبان پنجره رویداد ۸ بود، حدود ۴۴ ساعت. شبیه‌سازی فدرال ۹ دسامبر و تورم ۱۰
   دسامبر در نسل ۸ بسته شد و پنجره تورم بی‌نگهبان ماند. حالا ۱۶.
۲. پیام خطای نقد و docstring تابع cash_expected درآمد و خرید رسیددار را نمی‌گفتند.
۳. برچسب «رادار ۶.۱» در سرصفحه گزارش سبد، پرسش گشایش و چند ابزار دیگر — همه از چارچوب ۷.
بی شبکه.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import radar_positions as P
import radar_schedule as S
from radar_text import fa

UTC = timezone.utc
FOMC = datetime(2026, 12, 9, 19, 0, tzinfo=UTC)
CPI = datetime(2026, 12, 10, 13, 30, tzinfo=UTC)


def _dec_cal() -> dict:
    return {"version": 1, "events": [
        {"id": "fomc-2026-12", "at": FOMC.isoformat(),
         "press_at": (FOMC + timedelta(minutes=30)).isoformat(),
         "name": "تصمیم نرخ فدرال‌رزرو", "importance": "high"},
        {"id": "cpi-2026-11", "at": CPI.isoformat(), "name": "تورم نوامبر", "importance": "high"}]}


def test_keeper_covers_two_consecutive_event_days():
    start = FOMC - timedelta(hours=6) - timedelta(hours=24)       # بیداری ۲۴ ساعت پیش از پنجره
    evs = S.keeper_simulate(_dec_cal(), start)
    pulses = [t for t, w in evs if w == S.PULSE_WORKFLOW]
    gens = [w for _, w in evs if w.startswith(S.KEEPER_WORKFLOW)]
    assert len(gens) < S.KEEPER_MAX_GEN                           # زنجیره به سقف نخورد
    cpi_end = CPI + timedelta(hours=6)
    assert pulses[-1] >= cpi_end - timedelta(minutes=60)          # تا پایان پنجره تورم
    for a, b in ((FOMC - timedelta(hours=6), FOMC + timedelta(hours=6, minutes=30)),
                 (CPI - timedelta(hours=6), cpi_end)):
        inside = [p for p in pulses if a <= p <= b]
        gaps = [(y - x).total_seconds() / 60 for x, y in zip(inside, inside[1:])]
        assert inside and max(gaps) <= 60


def test_old_cap_would_have_broken_the_chain(monkeypatch):
    monkeypatch.setattr(S, "KEEPER_MAX_GEN", 8)
    start = FOMC - timedelta(hours=30)
    pulses = [t for t, w in S.keeper_simulate(_dec_cal(), start) if w == S.PULSE_WORKFLOW]
    assert pulses[-1] < CPI + timedelta(hours=6) - timedelta(hours=2)


def test_cash_error_names_income_and_receipted_buys():
    h = {"frozen": {"cash": [{"asset": "USDT", "account": "LBank", "qty": 100.0}]},
         "cash": [{"asset": "USDT", "account": "LBank", "qty": 90.0}], "ledger": []}
    with pytest.raises(P.PositionsError) as e:
        P._check_cash(h)
    msg = str(e.value)
    assert "درآمد" in msg and "خریدهای رسیددار" in msg and "income" in msg and "رسید خرید" in msg
    doc = P.cash_expected.__doc__
    assert "reenter و add" in doc and "هزینه خریدهای رسیددار" in doc


@pytest.mark.parametrize("mod", ["radar_state", "radar_book", "radar_watch", "radar_optcost",
                                 "radar_size", "radar_validate"])
def test_version_labels_follow_framework(mod):
    import importlib
    import radar_fetch3 as R
    m = importlib.import_module(mod)
    assert fa(m.VERSION) == R.FRAMEWORK, f"{mod}.VERSION = {m.VERSION} ولی چارچوب {R.FRAMEWORK}"


def test_book_header_and_opening_say_framework():
    import radar_book as B
    import radar_state as ST
    import radar_fetch3 as R
    assert f"رادار {R.FRAMEWORK}" in ST.opening_questions()
    src = (ROOT / "radar_book.py").read_text(encoding="utf-8")
    assert "رادار ۶.۱" not in src and "رادار {fa(VERSION)}" in src and fa(B.VERSION) == R.FRAMEWORK
