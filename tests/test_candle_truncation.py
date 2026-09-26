"""
کوتاه‌شدن بی‌صدای کندل — نشست ۳ب، بند ۴.

یافته‌های ایستگاه ۱، محاسبه‌شده:
- مسیر زنده OKX.candles سقف ۱۵ صفحه داشت: حالت عمیق 1501 خواست، 1500 گرفت.
- نقطه دسترسی /market/candles در صفحه‌بندی در 1440 کندل می‌ایستد؛ radar_book و
  radar_validate فقط همین را می‌زدند.
- بای‌بیت یک درخواست ۱۰۰۰تایی بی‌صفحه‌بندی بود؛ گیت هم — ک۲۲.
- okx_candles در radar_levels.py خطا را با except Exception: break می‌بلعید و
  سقف ۲۰ صفحه داشت؛ ticker و last_closed_daily در radar_watch.py هم می‌بلعیدند.

قاعده: کوتاه‌شدن به دست ما — خطای میانه صفحه‌بندی، سقف صفحه، سقف یک درخواست —
خطای صریح با شمار واقعی است. گیت صفحه‌بندی ندارد؛ اعلام شمار کافی است. تمام
شدن تاریخچه خود صرافی خطا نیست: کوین تازه «نابالغ» است، نه «داده ندارم» —
قاعده ۱ این دو را جدا می‌خواهد. بایننس همان الگوی بلعیدن را داشت و همین‌جا
درست شد.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_book as B
import radar_fetch3 as R
import radar_levels as L
import radar_validate as V
import radar_watch as W

UTC = timezone.utc
DAY0 = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


class _Resp:
    def __init__(self, js, code: int = 200):
        self._js, self.status_code = js, code

    def json(self):
        return self._js


class Okx:
    """
    اوکی‌اکس ساختگی با n کندل روزانه وقت جهانی، جدید به قدیم.
    fail_page: از این صفحه به بعد code خطا؛ raise_page: از این صفحه استثنای شبکه.
    candles_cap: سقف واقعی /market/candles — سنجش زنده ۲۶ سپتامبر، 1440.
    """

    def __init__(self, n=2000, fail_page=None, raise_page=None, candles_cap=1440):
        self.rows = []
        for i in range(n):
            op = DAY0 - timedelta(days=i)
            self.rows.append([str(int(op.timestamp() * 1000)), "100", "101", "99", "100",
                              "1", "1", "1", "0" if i == 0 else "1"])
        self.fail_page, self.raise_page, self.cap = fail_page, raise_page, candles_cap
        self.paths: list[str] = []

    def page(self, url, params):
        path = url.split("okx.com", 1)[1]
        self.paths.append(path)
        k = len(self.paths)
        if self.raise_page and k >= self.raise_page:
            raise requests.ConnectionError("آزمون: شبکه قطع شد")
        if self.fail_page and k >= self.fail_page:
            return {"code": "50011", "msg": "آزمون: سقف نرخ", "data": []}
        rows = self.rows[: self.cap] if path.endswith("/market/candles") else self.rows
        if "after" in params:
            rows = [r for r in rows if int(r[0]) < int(params["after"])]
        return {"code": "0", "data": rows[: int(params.get("limit", 100))]}

    def http(self, url, params=None, label="", **k):
        try:
            return self.page(url, params or {})
        except requests.RequestException:
            return None                         # همان رفتار http_get: None پس از تلاش

    def get(self, url, params=None, timeout=None, **k):
        return _Resp(self.page(url, params or {}))


def _req(get) -> SimpleNamespace:
    return SimpleNamespace(get=get, RequestException=requests.RequestException)


@pytest.fixture
def failures(monkeypatch):
    f: list[str] = []
    monkeypatch.setattr(R, "FAILURES", f)
    return f


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """مکث میان صفحه‌ها برای احترام به سقف نرخ صرافی است، نه برای آزمون."""
    import time
    monkeypatch.setattr(time, "sleep", lambda s: None)


# ═══════════════ radar_fetch3 — OKX.candles ═══════════════

def test_okx_deep_gets_full_1501(failures) -> None:
    df = R.VENUES["okx"].candles("BTC", "1D", R.DAILY_WANT_DEEP, Okx().http)
    assert len(df) >= R.DAILY_WANT_DEEP, failures


def test_okx_error_midway_is_loud(failures) -> None:
    df = R.VENUES["okx"].candles("BTC", "1D", 601, Okx(fail_page=3).http)
    assert df is None
    msg = next(f for f in failures if "قطع" in f)
    assert "200" in msg and "601" in msg


def test_okx_short_history_is_not_error(failures) -> None:
    """قفل: تاریخچه کوتاه خود صرافی خطا نیست — کوین تازه نابالغ است."""
    df = R.VENUES["okx"].candles("NEW", "1D", 601, Okx(n=300).http)
    assert len(df) == 300
    assert not [f for f in failures if "قطع" in f]


# ═══════════════ گیت، بای‌بیت، بایننس ═══════════════

def _gate(n):
    rows = [[str(int((DAY0 - timedelta(days=n - 1 - i)).timestamp())), "1", "100", "101",
             "99", "100", "10", "true"] for i in range(n)]
    return lambda url, params=None, label="", **k: rows[-int(params["limit"]):]


def test_gate_over_1000_declares_count(failures) -> None:
    """ک۲۲: گیت صفحه‌بندی ندارد؛ کمتر گرفتن اعلام می‌شود، نه بی‌صدا."""
    df = R.VENUES["gate"].candles("BTC", "1D", 1501, _gate(3000))
    assert len(df) == 1000
    assert any("1000" in f and "1501" in f for f in failures)


def test_gate_within_limit_is_silent(failures) -> None:
    assert len(R.VENUES["gate"].candles("BTC", "1D", 601, _gate(3000))) == 601
    assert not failures


def _bybit(n):
    rows = [[str(int((DAY0 - timedelta(days=i)).timestamp() * 1000)), "100", "101", "99",
             "100", "10", "1"] for i in range(n)]
    return lambda url, params=None, label="", **k: {
        "retCode": 0, "result": {"list": rows[: int(params["limit"])]}}


def test_bybit_over_limit_is_error(failures) -> None:
    assert R.VENUES["bybit"].candles("BTC", "1D", 1501, _bybit(3000)) is None
    assert any("1000" in f and "1501" in f for f in failures)


def test_bybit_within_limit_ok(failures) -> None:
    assert R.VENUES["bybit"].candles("BTC", "1D", 601, _bybit(3000)) is not None


def test_binance_error_midway_is_loud(failures) -> None:
    rows = [[int((DAY0 - timedelta(days=i)).timestamp() * 1000), "100", "101", "99", "100",
             "10"] for i in range(3000)][::-1]
    calls = {"n": 0}

    def http(url, params=None, label="", **k):
        calls["n"] += 1
        if calls["n"] >= 2:
            return None
        end = params.get("endTime")
        page = [r for r in rows if end is None or r[0] <= end]
        return page[-int(params["limit"]):]
    assert R.VENUES["binance"].candles("BTC", "1D", 1501, http) is None
    assert any("قطع" in f and "1501" in f for f in failures)


# ═══════════════ radar_levels ═══════════════

def test_levels_error_midway_is_loud(monkeypatch) -> None:
    monkeypatch.setattr(L, "requests", _req(Okx(fail_page=3).get))
    with pytest.raises(L.CandleError, match="200"):
        L.okx_candles("BTC-USDT", "1D", 700)


def test_levels_network_error_is_loud(monkeypatch) -> None:
    monkeypatch.setattr(L, "requests", _req(Okx(raise_page=2).get))
    with pytest.raises(L.CandleError, match="ConnectionError"):
        L.okx_candles("BTC-USDT", "1D", 700)


def test_levels_no_page_cap_below_want(monkeypatch) -> None:
    """سقف ۲۰ صفحه یعنی 2000 کندل؛ درخواست بیشتر بی‌صدا کوتاه می‌شد."""
    monkeypatch.setattr(L, "requests", _req(Okx(n=3000).get))
    assert len(L.okx_candles("BTC-USDT", "1D", 2500)) >= 2500


def test_levels_report_shows_candle_count() -> None:
    a = L.Assessment(symbol="GOOD", price=100.0, atr=2.0, trend="صعودی",
                     verdict="نزدیک سطح", dist_sup_atr=1.0, rr=2.5, n_bars=699)
    a.support = L.Level(price=98.0, touches=3, last_idx=50, kind="حمایت")
    a.resistance = L.Level(price=105.0, touches=2, last_idx=40, kind="مقاومت")
    b = L.Assessment(symbol="YOUNG", verdict="بدون حمایت شناسایی‌شده", n_bars=120)
    txt = L.report([a, b], 2.0)
    assert "| کندل |" in txt
    assert "| 699 |" in txt and "| 120 |" in txt


# ═══════════════ radar_book و radar_validate — history-candles ═══════════════

def test_book_pages_through_history(monkeypatch) -> None:
    srv = Okx()
    monkeypatch.setattr(B, "requests", _req(srv.get))
    monkeypatch.setattr(B, "CANDLE_NOTES", [])
    df = B.okx_candles("BTC", want=1500)
    assert len(df) >= 1500
    assert srv.paths[0].endswith("/market/candles")
    assert all(p.endswith("/market/history-candles") for p in srv.paths[1:])


def test_book_error_midway_is_announced(monkeypatch) -> None:
    notes: list[str] = []
    monkeypatch.setattr(B, "CANDLE_NOTES", notes)
    monkeypatch.setattr(B, "requests", _req(Okx(fail_page=3).get))
    assert B.okx_candles("BTC") is None
    assert any("200" in n and "601" in n for n in notes)


def test_book_network_error_is_announced(monkeypatch) -> None:
    notes: list[str] = []
    monkeypatch.setattr(B, "CANDLE_NOTES", notes)
    monkeypatch.setattr(B, "requests", _req(Okx(raise_page=1).get))
    assert B.okx_candles("BTC") is None
    assert any("ConnectionError" in n for n in notes)


def test_validate_pages_through_history(monkeypatch) -> None:
    srv = Okx()
    monkeypatch.setattr(V, "requests", _req(srv.get))
    df = V.candles("BTC", want=1600)
    assert len(df) >= 1600
    assert all(p.endswith("/market/history-candles") for p in srv.paths[1:])


def test_validate_error_is_loud(monkeypatch, capsys) -> None:
    monkeypatch.setattr(V, "requests", _req(Okx(fail_page=3).get))
    assert V.candles("BTC", want=900) is None
    err = capsys.readouterr().err
    assert "200" in err and "900" in err


# ═══════════════ radar_watch ═══════════════

def test_watch_ticker_error_is_loud(monkeypatch, capsys) -> None:
    def get(url, params=None, timeout=None, **k):
        raise requests.ConnectionError("آزمون")
    monkeypatch.setattr(W, "requests", _req(get))
    assert W.ticker("BTC") is None
    assert "ConnectionError" in capsys.readouterr().err


def test_watch_daily_close_error_is_loud(monkeypatch, capsys) -> None:
    monkeypatch.setattr(W, "requests", _req(Okx(fail_page=1).get))
    assert W.last_closed_daily("BTC") is None
    assert "50011" in capsys.readouterr().err


def test_watch_item_says_close_missing(monkeypatch) -> None:
    """پیش از این: بسته روزانه نیامد یعنی ابطال مورد بی‌صدا سنجیده نمی‌شد."""
    monkeypatch.setattr(W, "ticker", lambda s: 100.0)
    monkeypatch.setattr(W, "last_closed_daily", lambda s: None)
    fired = W.check_item({"symbol": "BTC", "invalidation": 90.0}, {})
    assert any("بسته روزانه" in f for f in fired)
