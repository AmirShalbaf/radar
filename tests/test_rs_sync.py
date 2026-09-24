"""
آزمون هم‌زمانی قدرت نسبی — نشست ۱ نقشه رادار ۷، مورد ۲.

باگ اسکن: در score_symbol بازده کوین از قیمت زنده حساب می‌شد و بازده
بیت‌کوین از آخرین کندل بسته. نشانه عینی: قدرت نسبی بیت‌کوین به خودش در
اسکن ۲۴ سپتامبر در هر دو پنجره ‎-0.8% بود. یک عدد در هر دو پنجره یعنی
خطا از نقطه پایانی است، نه از طول پنجره.
رفع: هر دو طرف از کندل بسته، در همان تاریخ.

باگ چرخش: rel24 کوین از تیکر زنده غلتان ۲۴ساعته بود و مبنای بیت‌کوین
از تغییر آخرین روز بسته. چون rel24 فقط برای مرتب‌سازی است و کم‌کردن
عدد ثابت ترتیب را عوض نمی‌کند، این خطا امروز در خروجی دیده نمی‌شد —
ولی عددی که ذخیره می‌شد غلط بود.
رفع: هر دو طرف زنده، از یک پاسخ تیکر. اگر بیت‌کوین در پاسخ نبود:
ترتیب با تغییر خام، rel24 خالی نه صفر، و هشدار صریح بالای گزارش.
"""
import math
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_fetch3 as R
import radar_rotate as RT
import radar_scan as S

COLS = ["ts", "open", "high", "low", "close", "vol"]


def _frame(n: int, px, open_close: float | None = None) -> pd.DataFrame:
    """
    قاب روزانه مصنوعی با اندیکاتور، n سطر که آخرینش کندل باز است.
    px تابع قیمت بر حسب شماره سطر است.
    """
    open_ts = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=2)
    rows = []
    for i in range(n):
        ts = open_ts - pd.Timedelta(days=n - 1 - i)
        p = px(i)
        if i == n - 1 and open_close is not None:
            p = open_close
        rows.append([int(ts.timestamp() * 1000), p, p * 1.02, p * 0.98, p,
                     1000.0])
    return R.enrich(R._df(rows, COLS, bar="1D"))


def _btc_px(i: int) -> float:
    return 60000 + 40 * i + 1500 * math.sin(i / 9)


def _coin_px(i: int) -> float:
    return 20 + 0.03 * i + 2 * math.cos(i / 5)


def _close_at(df: pd.DataFrame, ts) -> float:
    return float(df.loc[df["ts"] <= ts, "close"].iloc[-1])


@pytest.fixture
def venue(monkeypatch):
    """صرافی ساختگی: همان قابی را برمی‌گرداند که آزمون تعیین می‌کند."""
    def make(df):
        monkeypatch.setattr(R, "candles_first_ok",
                            lambda *a, **k: ({"1D": df}, "okx", None))
        monkeypatch.setattr(R, "gather_venues",
                            lambda *a, **k: ({}, {}, {}, {}))
        monkeypatch.setattr(R, "FAILURES", [])
    return make


# ═══════════════ اسکن — هر دو طرف از کندل بسته ═══════════════

def test_scan_btc_rs_to_itself_is_zero(venue) -> None:
    """
    قدرت نسبی بیت‌کوین به خودش باید **دقیقاً** صفر باشد.
    کندل باز عمداً ۳٪ بالاتر است تا ناهم‌زمانی دیده شود.
    """
    closed_last = _btc_px(698)
    df = _frame(700, _btc_px, open_close=closed_last * 1.03)
    venue(df)
    row = S.score_symbol("BTC", ["okx"], R._closed(df))
    assert row["rs_btc_30d"] == 0.0
    assert row["rs_btc_7d"] == 0.0


def test_scan_rs_uses_closed_basis_for_both(venue) -> None:
    """قدرت نسبی = بازده بسته کوین منهای بازده بسته بیت‌کوین، در همان تاریخ."""
    coin = _frame(700, _coin_px, open_close=_coin_px(698) * 1.05)
    btc = R._closed(_frame(700, _btc_px))
    venue(coin)
    row = S.score_symbol("TEST", ["okx"], btc)

    cc = R._closed(coin)
    now_ts = cc["ts"].iloc[-1]
    for days, tag in [(30, "30d"), (7, "7d")]:
        back = now_ts - pd.Timedelta(days=days)
        cw = 100 * (_close_at(cc, now_ts) / _close_at(cc, back) - 1)
        bw = 100 * (_close_at(btc, now_ts) / _close_at(btc, back) - 1)
        assert row[f"rs_btc_{tag}"] == pytest.approx(cw - bw)
        assert row[f"chg_{tag}"] == pytest.approx(cw)


def test_scan_price_stays_live(venue) -> None:
    """قفل، نه قرمز: قیمت ردیف همچنان از کندل زنده می‌آید."""
    live = _coin_px(698) * 1.05
    venue(_frame(700, _coin_px, open_close=live))
    row = S.score_symbol("TEST", ["okx"], R._closed(_frame(700, _btc_px)))
    assert row["price"] == pytest.approx(live)


# ═══════════════ چرخش — هر دو طرف زنده از یک پاسخ تیکر ═══════════════

def _ticker(inst: str, last: float, o24: float, vol: float = 5e7) -> dict:
    return {"instId": inst, "last": str(last), "open24h": str(o24),
            "volCcy24h": str(vol)}


def _tickers(with_btc: bool = True) -> list[dict]:
    t = [_ticker("XYZ-USDT", 51, 50),          # همان نسبت بیت‌کوین: ‎+2%
         _ticker("ABC-USDT", 11, 10),          # ‎+10%
         _ticker("DEF-USDT", 9.7, 10),         # ‎-3%
         _ticker("USDC-USDT", 1, 1)]           # استیبل — بیرون
    if with_btc:
        t.append(_ticker("BTC-USDT", 102, 100))
    return t


def test_universe_reports_btc_from_same_snapshot(monkeypatch) -> None:
    """تغییر ۲۴ساعته بیت‌کوین از همان پاسخ تیکر؛ خود بیت‌کوین نامزد نیست."""
    monkeypatch.setattr(R, "okx_get", lambda *a, **k: _tickers())
    uni, b24 = RT.universe_okx(0)
    assert b24 == pytest.approx(2.0)
    syms = {u["symbol"] for u in uni}
    assert "BTC" not in syms and "USDC" not in syms
    assert syms == {"XYZ", "ABC", "DEF"}


def test_universe_without_btc_gives_none(monkeypatch) -> None:
    """بیت‌کوین در پاسخ نبود یعنی مبنا خالی، نه صفر."""
    monkeypatch.setattr(R, "okx_get", lambda *a, **k: _tickers(with_btc=False))
    uni, b24 = RT.universe_okx(0)
    assert b24 is None
    assert len(uni) == 3


def test_pre_rank_btc_twin_is_exactly_zero(monkeypatch) -> None:
    """کوینی با همان نسبت ۲۴ساعته بیت‌کوین، rel24 دقیقاً صفر."""
    monkeypatch.setattr(R, "okx_get", lambda *a, **k: _tickers())
    uni, b24 = RT.universe_okx(0)
    pool = RT.pre_rank(uni, b24, 10)
    rel = {u["symbol"]: u["rel24"] for u in pool}
    assert rel["XYZ"] == 0.0
    assert rel["ABC"] == pytest.approx(8.0)
    assert rel["DEF"] == pytest.approx(-5.0)


def test_pre_rank_without_btc_keeps_order_and_empties_rel(monkeypatch) -> None:
    """بدون مبنا: ترتیب همان، rel24 خالی — نه صفر."""
    monkeypatch.setattr(R, "okx_get", lambda *a, **k: _tickers())
    uni, b24 = RT.universe_okx(0)
    with_b = [u["symbol"] for u in RT.pre_rank([dict(u) for u in uni], b24, 10)]
    no_b = RT.pre_rank([dict(u) for u in uni], None, 10)
    assert [u["symbol"] for u in no_b] == with_b == ["ABC", "XYZ", "DEF"]
    assert all(u["rel24"] is None for u in no_b)


def test_pre_rank_cuts_to_top(monkeypatch) -> None:
    """برش به top همان رفتار قبلی است."""
    monkeypatch.setattr(R, "okx_get", lambda *a, **k: _tickers())
    uni, b24 = RT.universe_okx(0)
    assert [u["symbol"] for u in RT.pre_rank(uni, b24, 2)] == ["ABC", "XYZ"]


# ═══════════════ چرخش — main بدون شبکه ═══════════════

def _btc_down_5() -> pd.DataFrame:
    """کندل بیت‌کوین که آخرین روز بسته‌اش ‎-5% است — مبنای غلط قدیمی."""
    def px(i: int) -> float:
        return 60000.0 * (0.95 if i >= 398 else 1.0)
    return _frame(400, px)


@pytest.fixture
def rotate_main(monkeypatch, capsys):
    """
    main را بدون شبکه اجرا می‌کند و مبنای ارسالی به pre_rank را ضبط می‌کند.
    analyze ساختگی None می‌دهد تا فقط مسیر پیش‌رتبه‌بندی آزموده شود.
    """
    def run(with_btc: bool):
        seen: list = []
        real = RT.pre_rank

        def spy(uni, btc_chg24, top):
            seen.append(btc_chg24)
            return real(uni, btc_chg24, top)

        monkeypatch.setattr(RT, "pre_rank", spy)
        monkeypatch.setattr(R, "probe_venues", lambda order: (list(order), []))
        monkeypatch.setattr(R, "okx_get",
                            lambda *a, **k: _tickers(with_btc=with_btc))
        monkeypatch.setattr(R, "candles_first_ok",
                            lambda *a, **k: ({"1D": _btc_down_5()}, "okx", None))
        monkeypatch.setattr(RT, "analyze", lambda *a, **k: None)
        monkeypatch.setattr(R, "FAILURES", [])
        monkeypatch.setattr(sys, "argv", ["radar_rotate.py", "--stdout",
                                          "--deep", "0", "--min-vol", "0"])
        rc = RT.main()
        return rc, seen, capsys.readouterr().out
    return run


def test_rotate_main_uses_ticker_btc(rotate_main) -> None:
    """مبنای پیش‌رتبه‌بندی ‎+2% تیکر است، نه ‎-5% کندل بسته."""
    rc, seen, out = rotate_main(with_btc=True)
    assert rc == 0
    assert seen == [pytest.approx(2.0)]
    assert "تیکر بیت‌کوین در پاسخ نبود" not in out


def test_rotate_main_without_btc_ticker_warns_and_continues(rotate_main) -> None:
    """بی‌صدا نه، ولی توقف هم نه: اجرا ادامه می‌یابد و گزارش هشدار دارد."""
    rc, seen, out = rotate_main(with_btc=False)
    assert rc == 0
    assert seen == [None]
    assert "تیکر بیت‌کوین در پاسخ نبود" in out
    # هشدار بالای گزارش است، پیش از جدول‌ها
    assert out.index("تیکر بیت‌کوین در پاسخ نبود") < out.index("جهان بازار")
