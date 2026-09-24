"""
آزمون جدول بودجه رژیم — نشست ۲ نقشه رادار ۷، مورد م۱.

دو باگ:
۱) جدول در دو نسخه بود — radar_book.py و radar_size.py — و radar_regime.py
   سومی می‌شد. متنی که در چند جا نوشته شود، دیر یا زود از هم جدا می‌افتد
   (رویداد ۲۲). حالا تنها منبع radar_budget.py است، فقط کتابخانه استاندارد،
   تا استقلال سبد و اندازه نشکند.
۲) روی مرز دقیق باند **بالاتر** انتخاب می‌شد (`>=`). قاعده تازه
   محافظه‌کارانه است: روی مرز، باند پایین‌تر.

ورودی پوچ یا بی‌نهایت خطای صریح می‌دهد. پیش از این `--regime nan` بی‌صدا
«بحرانی» می‌شد — کار باز ک۲۶.
"""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_book as B
import radar_budget as BG
import radar_size as Z

ROOT = Path(__file__).resolve().parent.parent

# جدول بودجه از دستور نشست ۲ — عمداً عدد، نه ثابت کد
TABLE = {
    "انبساطی": (8.0, 1.00, 5),
    "سازنده": (6.0, 0.75, 4),
    "محتاط": (4.0, 0.50, 3),
    "انقباضی": (2.5, 0.30, 2),
    "بحرانی": (1.5, 0.20, 1),
}


@pytest.mark.parametrize("score, name", [
    (5.0, "انبساطی"),
    (0.5000001, "انبساطی"),
    (0.50, "سازنده"),          # مرز دقیق: باند پایین‌تر
    (1e-9, "سازنده"),
    (0.0, "محتاط"),            # مرز دقیق
    (-0.4999999, "محتاط"),
    (-0.50, "انقباضی"),        # مرز دقیق
    (-1.1999999, "انقباضی"),
    (-1.20, "بحرانی"),         # مرز دقیق
    (-5.0, "بحرانی"),
])
def test_band_and_exact_boundary_goes_lower(score, name) -> None:
    assert BG.regime_band(score)["name"] == name


@pytest.mark.parametrize("name", list(TABLE))
def test_budget_values_match_the_table(name) -> None:
    rows = {r["name"]: r for r in (BG.regime_band(s)
                                   for s in (1.0, 0.25, -0.25, -1.0, -2.0))}
    r = rows[name]
    assert (r["cap"], r["mult"], r["maxpos"]) == TABLE[name]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_score_is_an_error(bad) -> None:
    with pytest.raises(ValueError):
        BG.regime_band(bad)


def test_book_and_size_use_the_single_source() -> None:
    """سبد و اندازه همان تابع را صدا می‌زنند، نه کپی."""
    assert B.regime_row is BG.regime_band
    assert Z.regime_row is BG.regime_band
    assert not hasattr(B, "REGIMES")
    assert not hasattr(Z, "REGIMES")


def test_book_boundary_follows_new_rule() -> None:
    """رفتار سبد روی مرز دقیق هم عوض شد — از همان منبع."""
    assert B.regime_row(0.50)["name"] == "سازنده"


def test_no_other_copy_of_the_table() -> None:
    """هیچ فایل پایتون دیگری جدول نام باندها را تعریف نکند."""
    owners = []
    for p in sorted(ROOT.glob("*.py")):
        text = p.read_text(encoding="utf-8")
        if '"انبساطی", 8.0' in text or "'انبساطی', 8.0" in text:
            owners.append(p.name)
    assert owners == ["radar_budget.py"]


def test_budget_is_stdlib_only() -> None:
    """استقلال سبد و اندازه: این ماژول نباید pandas یا لایه صرافی بیاورد."""
    src = (ROOT / "radar_budget.py").read_text(encoding="utf-8")
    for heavy in ("pandas", "numpy", "requests", "radar_fetch3"):
        assert f"import {heavy}" not in src


# هدف ذخیره استیبل هر باند. منشأ: کامیت f714c33 (رادار ۶.۱، ۲۲ اوت
# ۲۰۲۶)، هم‌زمان در radar_book.py و radar_size.py. کامنت آن به
# risk-budget.md ارجاع می‌داد که در مخزن نیست — پس دلیل عدد ثبت نشده.
# از نشست ۲ فقط در radar_budget.py است. این آزمون قفل است، نه قرمز.
STABLE = {"انبساطی": 10, "سازنده": 15, "محتاط": 25, "انقباضی": 40, "بحرانی": 55}


@pytest.mark.parametrize("name", list(STABLE))
def test_stable_reserve_target_is_locked(name) -> None:
    rows = {r["name"]: r for r in (BG.regime_band(s)
                                   for s in (1.0, 0.25, -0.25, -1.0, -2.0))}
    assert rows[name]["stable"] == STABLE[name]
