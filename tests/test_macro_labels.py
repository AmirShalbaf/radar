"""
آزمون خوانش انتظار مسیر نرخ — نشست ۱ نقشه رادار ۷، مورد ۴ الف.

باگ: بازده ۲ساله منهای سقف نرخ بهره «فاصله سیاست از خنثی» نام داشت و
مثبت‌بودنش «سیاست دیگر انقباضی نیست» خوانده می‌شد. ولی این عدد فاصله از
نرخ خنثی نیست؛ مسیری است که بازار برای نرخ انتظار دارد. مثبت یعنی بازار
افزایش بیشتر را قیمت کرده — باد مخالف دارایی ریسکی. در اسکن ۲۴ سپتامبر
۲۰۲۶ مقدار +0.710 بود و خوانش برعکس.

رفع: بازده ۲ساله با **کل** محدوده هدف فدرال سنجیده می‌شود، نه فقط سقف.
کف محدوده (DFEDTARL) از همان مسیر FRED می‌آید.
    بالای سقف       انتظار افزایش بیشتر
    زیر کف          انتظار کاهش نرخ
    داخل محدوده     تغییر روشنی قیمت نشده — مقدار صفر، مرزها هم داخل‌اند
عدد نمایش‌داده‌شده فاصله از نزدیک‌ترین مرز است. ورودی غایب یعنی
«داده ناکافی»، نه حدس.

این سنجه در هیچ امتیاز یا رأی ماکرویی به کار نرفته — فقط نمایشی است.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_fetch3 as R

LABEL = "انتظار بازار از مسیر نرخ"
UP = "انتظار افزایش بیشتر — باد مخالف دارایی ریسکی"
DOWN = "انتظار کاهش نرخ — بازار تسهیل را قیمت کرده"
FLAT = "بازار تغییر روشنی را قیمت نکرده"

HI, LO = 3.50, 3.25


def _fred(monkeypatch, **series: float) -> dict:
    """
    fetch_fred با http_text ساختگی: هر سری داده‌شده یک CSV کوچک برمی‌گرداند،
    بقیه هیچ — درست مثل وقتی FRED پاسخ نمی‌دهد. بدون شبکه.
    """
    monkeypatch.setattr(R.time, "sleep", lambda s: None)

    def http_text(url, label=None):
        sid = url.split("id=")[-1]
        if sid not in series:
            return None
        v = series[sid]
        return f"observation_date,{sid}\n2026-08-20,{v}\n2026-09-24,{v}\n"
    return R.fetch_fred(http_text)["derived"]["rate_path"]


def test_floor_series_is_fetched() -> None:
    assert "DFEDTARL" in R.FRED_SERIES


def test_above_ceiling(monkeypatch) -> None:
    d = _fred(monkeypatch, DGS2=3.90, DFEDTARU=HI, DFEDTARL=LO)
    assert d["label"] == LABEL
    assert d["read"] == UP
    assert d["value"] == pytest.approx(0.40)


def test_below_floor(monkeypatch) -> None:
    d = _fred(monkeypatch, DGS2=3.00, DFEDTARU=HI, DFEDTARL=LO)
    assert d["read"] == DOWN
    assert d["value"] == pytest.approx(-0.25)


def test_inside_range(monkeypatch) -> None:
    d = _fred(monkeypatch, DGS2=3.40, DFEDTARU=HI, DFEDTARL=LO)
    assert d["read"] == FLAT
    assert d["value"] == 0.0


@pytest.mark.parametrize("edge", [HI, LO])
def test_exactly_on_each_edge_is_inside(monkeypatch, edge) -> None:
    """مرز جزو محدوده است — نه افزایش، نه کاهش."""
    d = _fred(monkeypatch, DGS2=edge, DFEDTARU=HI, DFEDTARL=LO)
    assert d["read"] == FLAT
    assert d["value"] == 0.0


def test_missing_floor_is_not_guessed(monkeypatch) -> None:
    """کف نیامد یعنی «داده ناکافی» — حتی اگر ۲ساله بالای سقف باشد."""
    d = _fred(monkeypatch, DGS2=3.90, DFEDTARU=HI)
    assert "داده ناکافی" in d["read"]
    assert d["value"] is None


def test_missing_ceiling_is_not_guessed(monkeypatch) -> None:
    d = _fred(monkeypatch, DGS2=3.00, DFEDTARL=LO)
    assert "داده ناکافی" in d["read"]
    assert d["value"] is None


def test_old_wrong_reading_is_gone(monkeypatch) -> None:
    """ثبت خود باگ: خوانش «دیگر انقباضی نیست» نباید برگردد."""
    d = _fred(monkeypatch, DGS2=3.90, DFEDTARU=HI, DFEDTARL=LO)
    assert "انقباضی نیست" not in d["read"]
    assert "خنثی" not in d["label"]
