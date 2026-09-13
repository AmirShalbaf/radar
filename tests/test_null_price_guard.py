"""
آزمون نگهبان قیمت پوچ — رویداد ۲۱ در STATE.md.

باگ: نگهبان به شکل `live_close is None` نوشته شده بود. ولی عبارت
`float(nan)` مقدار `nan` می‌دهد نه `None`، پس `nan` از نگهبان رد می‌شد.

چرا بدتر از رد بی‌صدا است: با قیمت پوچ، کلید `vs_ema200` و `vs_ema50`
در دیکشنری **ساخته می‌شود** چون شرطشان فقط روی خود میانگین است، نه روی
قیمت. سنجه «موجود» شمرده می‌شود در حالی که محتوایش پوچ است — یعنی در
مخرج نرمال‌سازی می‌ماند. این نقض مستقیم قانون سوگیری صفر است، چون سنجه
غایب باید از مخرج کم شود.

سنجه چهارم (`atr_pct`) اتفاقی سالم مانده بود، چون شرطش `price > 0` دارد
و مقایسه `nan > 0` همیشه نادرست است. آن شرط عمداً دست‌نخورده ماند، ولی
تکیه‌گاه نیست — نگهبان واقعی بالادست است.
"""
import math
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_fetch3 as R
import radar_levels as L
import radar_rotate as RT
import radar_scan as S

COLS = ["ts", "open", "high", "low", "close", "vol"]


def _frame(n=700, last_close=None):
    """
    قاب روزانه مصنوعی با اندیکاتور. آخرین سطر کندل باز است.

    اگر last_close داده شود، بسته‌شدن سطر باز با آن جایگزین می‌شود —
    پس از محاسبه اندیکاتور، چون سناریوی واقعی همین است: صرافی برای
    کندل در حال شکل‌گیری مقدار پوچ برمی‌گرداند.
    """
    now = pd.Timestamp.now(tz="UTC")
    open_ts = now - pd.Timedelta(hours=2)          # سطر آخر هنوز باز است
    rows = []
    for i in range(n - 1, -1, -1):
        ts = open_ts - pd.Timedelta(days=i)
        px = 100 + (n - i) * 0.1                   # روند صعودی ملایم
        rows.append([int(ts.timestamp() * 1000), px, px * 1.02,
                     px * 0.98, px, 1000.0])
    df = R.enrich(R._df(rows, COLS, bar="1D"))
    if last_close is not None:
        df.loc[df.index[-1], "close"] = last_close
    return df


def _btc():
    return R._closed(_frame(400))


# ═══════════════ کمک‌تابع last_close ═══════════════

def test_last_close_healthy() -> None:
    """قاب سالم عدد می‌دهد."""
    df = _frame()
    v = R.last_close(df)
    assert v is not None and math.isfinite(v)


def test_last_close_reads_live_row_not_closed() -> None:
    """قیمت از سطر باز می‌آید، نه از آخرین سطر بسته."""
    df = _frame()
    df.loc[df.index[-1], "close"] = 777.0
    assert R.last_close(df) == 777.0
    assert float(R._closed(df)["close"].iloc[-1]) != 777.0


def test_last_close_nan_gives_none() -> None:
    """پوچ‌بودن باید None بدهد — همین نگهبان جا افتاده بود."""
    assert R.last_close(_frame(last_close=float("nan"))) is None


def test_last_close_inf_gives_none() -> None:
    """بی‌نهایت هم پوچ است. isfinite هر دو را می‌گیرد."""
    assert R.last_close(_frame(last_close=float("inf"))) is None
    assert R.last_close(_frame(last_close=float("-inf"))) is None


def test_last_close_empty_frame() -> None:
    """قاب تهی نباید بشکند."""
    assert R.last_close(pd.DataFrame(columns=COLS)) is None


def test_last_close_none_frame() -> None:
    """ورودی None نباید بشکند."""
    assert R.last_close(None) is None


def test_last_close_missing_column() -> None:
    """قاب بدون ستون بسته‌شدن نباید بشکند."""
    assert R.last_close(pd.DataFrame({"open": [1.0, 2.0]})) is None


def test_none_guard_alone_would_have_missed_it() -> None:
    """
    ثبت خود باگ: نگهبان قدیمی از کنار پوچ رد می‌شد. این آزمون توضیح
    می‌دهد چرا `is None` کافی نیست و نباید به آن بازگردیم.
    """
    old_style = float(_frame(last_close=float("nan"))["close"].iloc[-1])
    assert old_style is not None        # نگهبان قدیمی اینجا رد می‌شد
    assert math.isnan(old_style)        # در حالی که مقدار پوچ بود
    assert R.last_close(_frame(last_close=float("nan"))) is None


# ═══════════════ radar_scan.score_symbol ═══════════════

@pytest.fixture
def _stub(monkeypatch):
    """واکشی شبکه را با قاب مصنوعی جایگزین می‌کند."""
    def make(df):
        monkeypatch.setattr(R, "candles_first_ok",
                            lambda *a, **k: ({"1D": df}, "okx", None))
        monkeypatch.setattr(R, "gather_venues",
                            lambda *a, **k: ({}, {}, {}, {}))
        monkeypatch.setattr(R, "FAILURES", [])
    return make


def test_scan_healthy_still_works(_stub) -> None:
    """قاب سالم مثل قبل کار می‌کند — سنجه ساخته می‌شود."""
    _stub(_frame())
    row = S.score_symbol("TEST", ["okx"], _btc())
    assert row is not None
    assert "vs_ema200" in row
    assert math.isfinite(row["vs_ema200"])
    assert math.isfinite(row["price"])


def test_scan_null_price_rejects_symbol(_stub) -> None:
    """قیمت پوچ یعنی نماد رد می‌شود."""
    _stub(_frame(last_close=float("nan")))
    assert S.score_symbol("TEST", ["okx"], _btc()) is None


def test_scan_null_price_never_creates_ema_keys(_stub) -> None:
    """
    هسته باگ: کلید سنجه نباید با مقدار پوچ ساخته شود. اگر ساخته شود،
    در مخرج نرمال‌سازی می‌ماند و امتیاز را می‌آلاید — نقض قانون سوگیری صفر.
    """
    _stub(_frame(last_close=float("nan")))
    row = S.score_symbol("TEST", ["okx"], _btc())
    # نماد کلاً رد شد، پس هیچ کلیدی وجود ندارد
    assert row is None
    # و اگر روزی رفتار به «سطر ناقص» تغییر کرد، این شرط باید نگه دارد:
    if row is not None:
        assert "vs_ema200" not in row
        assert "vs_ema50" not in row


def test_scan_null_price_is_labelled_not_silent(_stub) -> None:
    """رد باید برچسب «داده ندارم» بگیرد، نه حذف بی‌صدا — درس رویداد ۱۴."""
    _stub(_frame(last_close=float("nan")))
    S.score_symbol("TEST", ["okx"], _btc())
    assert any("TEST" in f for f in R.FAILURES)


def test_scan_empty_frame_does_not_crash(_stub) -> None:
    """قاب تهی نباید بشکند."""
    _stub(pd.DataFrame(columns=COLS + ["confirm"]))
    assert S.score_symbol("TEST", ["okx"], _btc()) is None


# ═══════════════ radar_rotate.analyze ═══════════════

def test_rotate_healthy_still_works(_stub) -> None:
    """قاب سالم مثل قبل کار می‌کند."""
    _stub(_frame())
    row = RT.analyze("TEST", ["okx"], _btc())
    assert row is not None
    assert math.isfinite(row["price"])
    assert row["e200"] is not None


def test_rotate_null_price_rejects_symbol(_stub) -> None:
    """قیمت پوچ یعنی نماد رد می‌شود."""
    _stub(_frame(last_close=float("nan")))
    assert RT.analyze("TEST", ["okx"], _btc()) is None


def test_rotate_null_price_is_labelled(_stub) -> None:
    """رد برچسب می‌گیرد."""
    _stub(_frame(last_close=float("nan")))
    RT.analyze("TEST", ["okx"], _btc())
    assert any("TEST" in f for f in R.FAILURES)


def test_rotate_empty_frame_does_not_crash(_stub) -> None:
    """قاب تهی نباید بشکند."""
    _stub(pd.DataFrame(columns=COLS + ["confirm"]))
    assert RT.analyze("TEST", ["okx"], _btc()) is None


# ═══════════════ radar_levels.assess ═══════════════
#
# این فایل عمداً مستقل است و واکشی خودش را دارد، پس نسخه محلی نگهبان
# دارد. آزمون هر دو نسخه را کنار هم نگه می‌دارد تا از هم دور نیفتند.

def test_levels_healthy_still_works() -> None:
    """قاب سالم مثل قبل کار می‌کند."""
    a = L.assess("TEST", _frame())
    assert a.verdict != "داده ندارم"
    assert math.isfinite(a.price)


def test_levels_null_price_verdict() -> None:
    """قیمت پوچ یعنی برچسب «داده ندارم»، نه سقوط و نه حذف بی‌صدا."""
    a = L.assess("TEST", _frame(last_close=float("nan")))
    assert a.verdict == "داده ندارم"


def test_levels_empty_frame_does_not_crash() -> None:
    """قاب تهی نباید بشکند."""
    a = L.assess("TEST", pd.DataFrame(columns=COLS))
    assert a.verdict in ("داده کم", "داده ندارم")


def test_levels_guard_matches_canonical() -> None:
    """
    نسخه محلی و نسخه اصلی باید یک رفتار بدهند. اگر روزی یکی عوض شد و
    دیگری نه، این آزمون قرمز می‌شود.
    """
    for lc in [float("nan"), float("inf"), None]:
        df = _frame(last_close=lc) if lc is not None else _frame()
        assert L._last_close(df) == R.last_close(df) or (
            L._last_close(df) is None and R.last_close(df) is None)
    assert L._last_close(None) is None
    assert L._last_close(pd.DataFrame(columns=COLS)) is None
