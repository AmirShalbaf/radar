"""
آزمون ستون تأیید کندل — ردیف ۱۵ و ۱۸ در STATE.md.

باگ اصلی: تابع _df در radar_fetch3.py ستون تأیید را برای همه سطرها یک
می‌گذاشت. نتیجه: صافی کندل بسته در radar_scan.py و radar_rotate.py و خود
radar_fetch3.py بی‌اثر بود و کندل باز وارد اندیکاتور می‌شد.

خطر هنگام رفع: اگر کندل باز حذف شود، قیمت تا یک روز کهنه می‌شود — همان
باگ ۸. پس قاعده این است: قیمت از کندل زنده، ساختار از کندل بسته. آزمون‌های
زیر هر دو طرف را قفل می‌کنند.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_fetch3 as R


def _rows(n, bar_seconds, last_open_offset):
    """
    n سطر کندل می‌سازد. آخرین سطر با فاصله last_open_offset ثانیه از اکنون
    باز شده است. اگر این فاصله کمتر از طول کندل باشد، آن سطر باز است.
    """
    now = pd.Timestamp.now(tz="UTC")
    last_open = now - pd.Timedelta(seconds=last_open_offset)
    out = []
    for i in range(n - 1, -1, -1):
        ts = last_open - pd.Timedelta(seconds=bar_seconds * i)
        out.append([int(ts.timestamp() * 1000), 100, 110, 90, 105, 1000])
    return out


COLS = ["ts", "open", "high", "low", "close", "vol"]


# ─────────────────────── محاسبه تأیید از مهر زمانی ───────────────────────

def test_daily_open_candle_marked_zero() -> None:
    """کندل باز روزانه باید تأیید صفر بگیرد."""
    # آخرین کندل ۲ ساعت پیش باز شده — هنوز بسته نشده
    df = R._df(_rows(10, 86_400, 2 * 3600), COLS, bar="1D")
    assert df["confirm"].iloc[-1] == 0
    assert (df["confirm"].iloc[:-1] == 1).all()


def test_daily_closed_candle_marked_one() -> None:
    """کندل بسته روزانه باید تأیید یک بگیرد."""
    # آخرین کندل ۳۰ ساعت پیش باز شده — قطعاً بسته است
    df = R._df(_rows(10, 86_400, 30 * 3600), COLS, bar="1D")
    assert (df["confirm"] == 1).all()


def test_four_hour_open_candle() -> None:
    """کندل باز چهارساعته."""
    df = R._df(_rows(10, 14_400, 600), COLS, bar="4H")
    assert df["confirm"].iloc[-1] == 0


def test_weekly_open_candle() -> None:
    """کندل باز هفتگی."""
    df = R._df(_rows(10, 604_800, 3 * 86_400), COLS, bar="1W")
    assert df["confirm"].iloc[-1] == 0


def test_confirm_is_anchor_agnostic() -> None:
    """
    مبنا زمان باز شدن خود کندل است، نه نیمه‌شب جهانی. پس چه صرافی روز را
    از ساعت صفر ببندد چه از ساعت هشت، نتیجه یکی است.
    """
    a = R._df(_rows(5, 86_400, 30 * 3600), COLS, bar="1D")
    b = R._df(_rows(5, 86_400, 30 * 3600 + 8 * 3600), COLS, bar="1D")
    assert (a["confirm"] == 1).all() and (b["confirm"] == 1).all()


# ─────────────────────── پرچم صریح صرافی ───────────────────────

def test_explicit_flag_beats_computation() -> None:
    """پرچم صریح صرافی بر محاسبه زمانی مقدم است."""
    rows = _rows(5, 86_400, 30 * 3600)      # از نظر زمانی همه بسته‌اند
    df = R._df(rows, COLS, bar="1D", confirm=[1, 1, 1, 1, 0])
    assert df["confirm"].iloc[-1] == 0      # پرچم صرافی برنده شد


def test_okx_string_flag_becomes_int() -> None:
    """پرچم رشته‌ای اوکی‌اکس باید عددی شود."""
    rows = _rows(3, 86_400, 30 * 3600)
    df = R._df(rows, COLS, bar="1D", confirm=["1", "1", "0"])
    assert df["confirm"].tolist() == [1, 1, 0]
    assert df["confirm"].dtype.kind in "iu"


def test_invalid_flag_falls_to_zero() -> None:
    """در شک، کندل نابسته فرض می‌شود. محافظه‌کارانه‌تر است."""
    rows = _rows(3, 86_400, 30 * 3600)
    df = R._df(rows, COLS, bar="1D", confirm=["1", None, "خراب"])
    assert df["confirm"].tolist() == [1, 0, 0]


# ─────────────────────── سازگاری عقب‌رو ───────────────────────

def test_backward_compatible_without_bar() -> None:
    """بدون تایم‌فریم، رفتار قدیمی حفظ می‌شود."""
    df = R._df(_rows(5, 86_400, 600), COLS)
    assert (df["confirm"] == 1).all()


def test_confirm_column_always_present() -> None:
    """ستون تأیید همیشه ساخته می‌شود."""
    for bar in ["1D", "4H", "1W", None]:
        df = R._df(_rows(5, 86_400, 600), COLS, bar=bar)
        assert "confirm" in df.columns


# ─────────────────────── سطر باز حذف نمی‌شود ───────────────────────

def test_open_candle_labelled_not_dropped() -> None:
    """
    حذف سطر باز قیمت را کهنه می‌کند — باگ ۸. تعداد سطرها باید دست‌نخورده
    بماند تا قیمت زنده در دسترس باشد.
    """
    df = R._df(_rows(10, 86_400, 2 * 3600), COLS, bar="1D")
    assert len(df) == 10


def test_live_price_comes_from_open_row() -> None:
    """قیمت زنده از سطر باز، ساختار از سطر بسته."""
    rows = _rows(10, 86_400, 2 * 3600)
    rows[-1][4] = 777.0                      # بسته‌شدن کندل باز
    df = R._df(rows, COLS, bar="1D")
    assert float(df["close"].iloc[-1]) == 777.0        # زنده
    assert float(R._closed(df)["close"].iloc[-1]) != 777.0   # ساختار


# ─────────────────────── کمک‌تابع _closed ───────────────────────

def test_closed_returns_only_confirmed() -> None:
    """کمک‌تابع فقط کندل بسته می‌دهد."""
    df = R._df(_rows(10, 86_400, 2 * 3600), COLS, bar="1D")
    assert len(R._closed(df)) == 9


def test_closed_handles_empty_input() -> None:
    """با ورودی تهی نباید بشکند."""
    assert R._closed(None) is None
    empty = pd.DataFrame(columns=COLS)
    assert len(R._closed(empty)) == 0


def test_closed_passthrough_without_column() -> None:
    """بدون ستون تأیید، قاب دست‌نخورده برمی‌گردد."""
    df = pd.DataFrame({"close": [1, 2, 3]})
    assert len(R._closed(df)) == 3


def test_closed_resets_index() -> None:
    """اندیس پس از صافی بازنشانی می‌شود."""
    df = R._df(_rows(10, 86_400, 2 * 3600), COLS, bar="1D")
    assert list(R._closed(df).index) == list(range(9))


# ─────────────────────── ترتیب و یکتایی ───────────────────────

def test_sorted_ascending_and_deduped() -> None:
    """ترتیب صعودی و حذف تکرار حفظ می‌شود."""
    rows = _rows(10, 86_400, 30 * 3600)
    rows = rows + [rows[0]]                  # یک سطر تکراری
    df = R._df(rows, COLS, bar="1D")
    assert len(df) == 10
    assert df["ts"].is_monotonic_increasing


# ─────────────────────── اندیکاتور علّی است ───────────────────────

def test_indicator_unaffected_by_open_candle() -> None:
    """
    میانگین نمایی علّی است: مقدار هر سطر فقط به سطرهای پیش از خودش وابسته
    است. پس محاسبه روی قاب کامل و سپس صافی‌کردن، با محاسبه روی قاب صاف‌شده
    یکی است. این چیزی است که اجازه می‌دهد ترتیب فعلی درست بماند.
    """
    rows = _rows(60, 86_400, 2 * 3600)
    full = R._df(rows, COLS, bar="1D")
    full = full.copy()
    full["ema"] = full["close"].ewm(span=10, adjust=False).mean()

    closed_first = R._closed(R._df(rows, COLS, bar="1D")).copy()
    closed_first["ema"] = closed_first["close"].ewm(span=10, adjust=False).mean()

    assert R._closed(full)["ema"].iloc[-1] == pytest.approx(
        closed_first["ema"].iloc[-1])
