"""
لنگر کندل وقت جهانی — نشست ۳ب، بند ۱.

یافته نشست ۳ (رویداد ۳۵): اوکی‌اکس با 1D و 1W پیش‌فرض بر پایه وقت هنگ‌کنگ
می‌بندد — روزانه 16:00 UTC، هفتگی یکشنبه 16:00 UTC — و گیت با 1d و 7d بر
پایه وقت جهانی. پس «بسته روزانه» در مخزن یک لحظه نبود. سنجش زنده ایستگاه ۱
نشست ۳ب: 1Dutc و 1Wutc روی هر دو نقطه دسترسی اوکی‌اکس ۰۰:۰۰ UTC و دوشنبه‌اند؛
بایننس و بای‌بیت هم؛ کوکوین هفتگی پنجشنبه است.

دو قفل برای هر مسیر:
- درخواستی که واقعاً به صرافی می‌رود با جایگزین مصنوعی http گرفته و bar آن
  سنجیده می‌شود. متن فایل برای "1D" گشته نمی‌شود: "1D" نام داخلی تایم‌فریم
  در همه جای مخزن است و چنین آزمونی شکننده است.
- کندل مصنوعی با شروع 16:00 UTC رد و اعلام می‌شود؛ هرگز بازگشت بی‌صدا به
  لنگر هنگ‌کنگ.

چهارساعته عوض نمی‌شود: ۸ ساعت مضرب ۴ است و مرز در هر دو لنگر یکی است — سنجش
زنده ۱۲:۰۰، ۱۶:۰۰، ۲۰:۰۰ در هر چهار صرافی. فقط قفل می‌شود.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_anchor as A
import radar_book as B
import radar_fetch3 as R
import radar_journal as RJ
import radar_levels as L
import radar_optcost as RO
import radar_positions as P
import radar_validate as V
import radar_watch as W

UTC = timezone.utc
NOW = datetime.now(UTC)
DAY0 = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
STEP = {"1D": timedelta(days=1), "4H": timedelta(hours=4), "1W": timedelta(weeks=1)}
HK = timedelta(hours=8)                    # لنگر هنگ‌کنگ: ۸ ساعت زودتر از مرز جهانی


def _last_open(bar: str) -> datetime:
    if bar == "1D":
        return DAY0
    if bar == "4H":
        return DAY0 + timedelta(hours=NOW.hour - NOW.hour % 4)
    return DAY0 - timedelta(days=DAY0.weekday())


def _opens(n: int, bar: str, shift: timedelta = timedelta(0)) -> list[datetime]:
    """زمان باز شدن n کندل، قدیم به جدید؛ آخری کندل جاری است."""
    last = _last_open(bar) - shift
    return [last - STEP[bar] * (n - 1 - i) for i in range(n)]


def _ms(t: datetime) -> str:
    return str(int(t.timestamp() * 1000))


# ═══════════════ صرافی‌های ساختگی — هر درخواست ثبت می‌شود ═══════════════

class _Resp:
    def __init__(self, js, code: int = 200):
        self._js, self.status_code = js, code

    def json(self):
        return self._js


class Okx:
    """
    اوکی‌اکس ساختگی: جدید به قدیم، پرچم تأیید در اندیس ۸؛ after یعنی قدیمی‌تر.
    هر bar درخواستی همان ردیف‌ها را می‌گیرد — آزمون نام bar را از seen می‌خواند.
    """

    def __init__(self, n: int = 120, bar: str = "1D", shift: timedelta = timedelta(0)):
        ops = _opens(n, bar, shift)
        self.rows = []
        for i, op in enumerate(ops):
            p = 100.0 + i
            self.rows.append([_ms(op), str(p), str(p * 1.01), str(p * 0.99), str(p),
                              "1", "1", "1", "0" if i == n - 1 else "1"])
        self.rows.reverse()
        self.seen: list[tuple[str, dict]] = []

    def page(self, url: str, params: dict) -> dict:
        path = url.split("okx.com", 1)[1]
        self.seen.append((path, dict(params)))
        rows = self.rows
        if "after" in params:
            rows = [r for r in rows if int(r[0]) < int(params["after"])]
        return {"code": "0", "data": rows[: int(params.get("limit", 100))]}

    def http(self, url, params=None, label="", **k):          # radar_fetch3.http_get
        return self.page(url, params or {})

    def get(self, url, params=None, timeout=None, **k):        # requests.get
        return _Resp(self.page(url, params or {}))

    def bars(self) -> set:
        return {p["bar"] for _, p in self.seen}


class Gate:
    """قالب گیت: [زمان به ثانیه، حجم مظنه، بسته، بالا، پایین، باز، حجم پایه، بسته‌شده]."""

    def __init__(self, n: int = 120, bar: str = "1D", shift: timedelta = timedelta(0)):
        ops = _opens(n, bar, shift)
        self.rows = [[str(int(op.timestamp())), "1000", str(100.0 + i), str(101.0 + i),
                      str(99.0 + i), str(100.0 + i), "10", "false" if i == n - 1 else "true"]
                     for i, op in enumerate(ops)]
        self.seen: list[dict] = []

    def http(self, url, params=None, label="", **k):
        self.seen.append(dict(params or {}))
        return self.rows[-int((params or {}).get("limit", 1000)):]

    def get(self, url, params=None, timeout=None, **k):
        return _Resp(self.http(url, params))


def _binance(n=120, bar="1D", shift=timedelta(0)):
    rows = [[int(op.timestamp() * 1000), "100", "101", "99", str(100.0 + i), "10"]
            for i, op in enumerate(_opens(n, bar, shift))]
    return lambda url, params=None, label="", **k: rows[-int(params["limit"]):]


def _bybit(n=120, bar="1D", shift=timedelta(0)):
    rows = [[_ms(op), "100", "101", "99", str(100.0 + i), "10", "1000"]
            for i, op in enumerate(_opens(n, bar, shift))]
    rows.reverse()
    return lambda url, params=None, label="", **k: {"retCode": 0, "result": {"list": rows}}


def _fake_requests(srv) -> SimpleNamespace:
    return SimpleNamespace(get=srv.get, RequestException=requests.RequestException)


def _route(okx: Okx, gate: Gate):
    """http_get ساختگی radar_fetch3 که هر دامنه را به صرافی خودش می‌برد."""
    def http(url, params=None, label="", **k):
        if "okx.com" in url:
            return okx.http(url, params, label)
        if "gateio" in url:
            return gate.http(url, params, label)
        return None
    return http


@pytest.fixture
def failures(monkeypatch):
    f: list[str] = []
    monkeypatch.setattr(R, "FAILURES", f)
    return f


# ═══════════════ radar_anchor — تنها منبع ═══════════════

def test_anchor_rules() -> None:
    assert A.anchor_ok(datetime(2026, 9, 26, 0, tzinfo=UTC), "1D")
    assert not A.anchor_ok(datetime(2026, 9, 25, 16, tzinfo=UTC), "1D")
    assert A.anchor_ok(datetime(2026, 9, 21, 0, tzinfo=UTC), "1W")          # دوشنبه
    assert not A.anchor_ok(datetime(2026, 9, 20, 16, tzinfo=UTC), "1W")     # یکشنبه هنگ‌کنگ
    assert not A.anchor_ok(datetime(2026, 9, 24, 0, tzinfo=UTC), "1W")      # پنجشنبه کوکوین
    assert A.anchor_ok(datetime(2026, 9, 26, 16, tzinfo=UTC), "4H")
    assert not A.anchor_ok(datetime(2026, 9, 26, 2, tzinfo=UTC), "4H")
    assert A.anchor_ok(int(datetime(2026, 9, 26, tzinfo=UTC).timestamp() * 1000), "1D")


def test_naive_time_is_error() -> None:
    with pytest.raises(ValueError):
        A.anchor_ok(datetime(2026, 9, 26), "1D")


def test_bar_table_single_source() -> None:
    assert A.BAR["okx"] == {"1D": "1Dutc", "4H": "4H", "1W": "1Wutc"}
    assert A.BAR["gate"] == {"1D": "1d", "4H": "4h", "1W": "7d"}
    assert "kucoin" not in A.BAR                    # کلاس نداشت؛ هفتگی‌اش پنجشنبه است
    assert R.BAR is A.BAR


def test_positions_shares_guard() -> None:
    assert P.OKX_WEEK_BAR == A.BAR["okx"]["1W"]
    assert P.GATE_WEEK_INTERVAL == A.BAR["gate"]["1W"]
    assert P._is_monday_utc(datetime(2026, 9, 21, tzinfo=UTC))
    assert not P._is_monday_utc(datetime(2026, 9, 20, 16, tzinfo=UTC))


def test_dead_okx_path_removed() -> None:
    """okx_candles و BAR_MAP در radar_fetch3.py صدازننده‌ای نداشتند."""
    assert not hasattr(R, "okx_candles")
    assert not hasattr(R, "BAR_MAP")


# ═══════════════ radar_fetch3 — آداپتورهای صرافی ═══════════════

@pytest.mark.parametrize("bar,sent", [("1D", "1Dutc"), ("1W", "1Wutc"), ("4H", "4H")])
def test_fetch3_okx_sends_utc_bar(bar, sent, failures) -> None:
    srv = Okx(bar=bar)
    df = R.VENUES["okx"].candles("BTC", bar, 5, srv.http)
    assert df is not None, failures
    assert srv.bars() == {sent}


@pytest.mark.parametrize("bar", ["1D", "1W"])
def test_fetch3_okx_rejects_hk_anchor(bar, failures) -> None:
    srv = Okx(bar=bar, shift=HK)
    assert R.VENUES["okx"].candles("BTC", bar, 5, srv.http) is None
    assert any("لنگر" in f for f in failures)


@pytest.mark.parametrize("venue,make", [("gate", lambda **k: Gate(**k).http),
                                        ("binance", _binance), ("bybit", _bybit)])
def test_fetch3_other_venues_reject_hk_anchor(venue, make, failures) -> None:
    assert R.VENUES[venue].candles("BTC", "1D", 100, make()) is not None, failures
    assert R.VENUES[venue].candles("BTC", "1D", 100, make(shift=HK)) is None
    assert any("لنگر" in f and venue in f for f in failures)


def test_fetch3_gate_sends_utc_intervals(failures) -> None:
    for bar, sent in (("1D", "1d"), ("1W", "7d"), ("4H", "4h")):
        g = Gate(bar=bar)
        assert R.VENUES["gate"].candles("BTC", bar, 100, g.http) is not None, failures
        assert g.seen[-1]["interval"] == sent


def test_fetch3_4h_same_boundary_both_anchors(failures) -> None:
    """قفل، نه قرمز: مرز چهارساعته در دو لنگر یکی است؛ ۰۲:۰۰ لنگر نیست."""
    assert R.VENUES["okx"].candles("BTC", "4H", 5, Okx(bar="4H", shift=HK).http) is not None
    assert R.VENUES["okx"].candles("BTC", "4H", 5,
                                   Okx(bar="4H", shift=timedelta(hours=2)).http) is None


def test_candles_first_ok_falls_to_utc_venue(monkeypatch, failures) -> None:
    """اوکی‌اکس با لنگر هنگ‌کنگ رد می‌شود و گیت وقت جهانی جایش می‌نشیند — اعلام‌شده."""
    monkeypatch.setattr(R, "http_get", _route(Okx(shift=HK), Gate()))
    got, vn, _ = R.candles_first_ok("BTC", ["okx", "gate"], 100, [])
    assert vn == "gate"
    assert any("okx" in f and "لنگر" in f for f in failures)


def test_candles_first_ok_no_utc_is_no_data(monkeypatch, failures) -> None:
    monkeypatch.setattr(R, "http_get", _route(Okx(shift=HK), Gate(shift=HK)))
    got, vn, _ = R.candles_first_ok("BTC", ["okx", "gate"], 100, [])
    assert got == {} and vn is None


def test_candles_first_ok_pair_is_utc(monkeypatch, failures) -> None:
    okx = Okx(n=500)
    monkeypatch.setattr(R, "http_get", _route(okx, Gate()))
    _, vn, pair = R.candles_first_ok("ETH", ["okx"], 100, [])
    assert vn == "okx" and pair is not None
    sent = {p["bar"] for _, p in okx.seen if p["instId"] == "ETH-BTC"}
    assert sent == {"1Dutc"}


# ═══════════════ radar_levels ═══════════════

def test_levels_sends_utc_bar(monkeypatch) -> None:
    srv = Okx()
    monkeypatch.setattr(L, "requests", _fake_requests(srv))
    assert L.okx_candles("BTC-USDT", "1D", 50) is not None
    assert srv.bars() == {"1Dutc"}
    srv4 = Okx(bar="4H")
    monkeypatch.setattr(L, "requests", _fake_requests(srv4))
    assert L.okx_candles("BTC-USDT", "4H", 50) is not None
    assert srv4.bars() == {"4H"}


def test_levels_rejects_hk_anchor(monkeypatch) -> None:
    monkeypatch.setattr(L, "requests", _fake_requests(Okx(shift=HK)))
    with pytest.raises(L.CandleError, match="لنگر"):
        L.okx_candles("BTC-USDT", "1D", 50)


def test_levels_report_announces_rejection(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(L, "requests", _fake_requests(Okx(shift=HK)))
    out = tmp_path / "levels.md"
    monkeypatch.setattr(sys, "argv", ["radar_levels.py", "--watchlist", "BTC", "--out", str(out)])
    assert L.main() == 0
    txt = out.read_text(encoding="utf-8")
    assert "BTC" in txt and "داده ندارم" in txt and "لنگر" in txt


# ═══════════════ radar_book ═══════════════

@pytest.fixture
def book_notes(monkeypatch):
    n: list[str] = []
    monkeypatch.setattr(B, "CANDLE_NOTES", n)
    return n


def test_book_sends_utc_bar(monkeypatch, book_notes) -> None:
    srv = Okx(n=700)
    monkeypatch.setattr(B, "requests", _fake_requests(srv))
    assert B.okx_candles("BTC") is not None
    assert srv.bars() == {"1Dutc"}


def test_book_hk_okx_falls_to_gate_announced(monkeypatch, book_notes) -> None:
    okx, gate = Okx(n=700, shift=HK), Gate(n=700)

    def get(url, params=None, timeout=None, **k):
        return okx.get(url, params) if "okx.com" in url else gate.get(url, params)
    monkeypatch.setattr(B, "requests", SimpleNamespace(get=get,
                                                       RequestException=requests.RequestException))
    df = B.candles("BTC")
    assert df is not None and len(df) == B.DAILY_WANT
    assert gate.seen and gate.seen[-1]["interval"] == "1d"
    assert any("لنگر" in n and "BTC" in n for n in book_notes)


def test_book_no_utc_is_no_data(monkeypatch, book_notes) -> None:
    okx, gate = Okx(n=700, shift=HK), Gate(n=700, shift=HK)

    def get(url, params=None, timeout=None, **k):
        return okx.get(url, params) if "okx.com" in url else gate.get(url, params)
    monkeypatch.setattr(B, "requests", SimpleNamespace(get=get,
                                                       RequestException=requests.RequestException))
    assert B.candles("BTC") is None
    assert sum("لنگر" in n for n in book_notes) == 2


def test_book_report_shows_candle_notes() -> None:
    h = {"positions": [], "updated": NOW.isoformat(), "source": "آزمون"}
    txt = B.build_report(h, [], None, [], candle_notes=["⚠️ BTC: آزمون لنگر"])
    assert "آزمون لنگر" in txt
    assert "1Dutc" in txt


def test_reports_carry_anchor_line() -> None:
    """قفل، نه قرمز: گزارش روزانه می‌گوید با کدام لنگر ساخته شده — یک متن."""
    import radar_regime as G
    assert A.ANCHOR_LINE in L.report([], 2.0)
    inp = {k: G.Input(key=k, column=c, label=lb, weight=G.weights()[k], score=0.1)
           for k, (c, lb) in G.INPUTS.items()}
    doc = G.build_doc(G.aggregate(inp), inp, NOW)
    assert A.ANCHOR_LINE in G.render_md(doc)


# ═══════════════ radar_watch ═══════════════

def test_watch_daily_close_sends_utc_bar(monkeypatch) -> None:
    srv = Okx(n=3)
    monkeypatch.setattr(W, "requests", _fake_requests(srv))
    close, day = W.last_closed_daily("BTC")
    assert srv.bars() == {"1Dutc"}
    assert day == (DAY0 - timedelta(days=1)).strftime("%Y-%m-%d")


def test_watch_daily_close_rejects_hk(monkeypatch, capsys) -> None:
    monkeypatch.setattr(W, "requests", _fake_requests(Okx(n=3, shift=HK)))
    assert W.last_closed_daily("BTC") is None
    assert "لنگر" in capsys.readouterr().err


# ═══════════════ radar_validate، radar_optcost، radar_journal ═══════════════

def test_validate_sends_utc_bar(monkeypatch) -> None:
    srv = Okx(n=400)
    monkeypatch.setattr(V, "requests", _fake_requests(srv))
    assert V.candles("BTC", want=300) is not None
    assert srv.bars() == {"1Dutc"}


def test_validate_rejects_hk(monkeypatch, capsys) -> None:
    monkeypatch.setattr(V, "requests", _fake_requests(Okx(n=400, shift=HK)))
    assert V.candles("BTC", want=300) is None
    assert "لنگر" in capsys.readouterr().err


def test_optcost_sends_utc_bar(monkeypatch) -> None:
    srv = Okx(n=40)
    monkeypatch.setattr(RO, "requests", _fake_requests(srv))
    assert RO.candles_since("BTC", 10)
    assert srv.bars() == {"1Dutc"}


def test_optcost_rejects_hk(monkeypatch, capsys) -> None:
    monkeypatch.setattr(RO, "requests", _fake_requests(Okx(n=40, shift=HK)))
    assert RO.candles_since("BTC", 10) is None
    assert "لنگر" in capsys.readouterr().err


def test_journal_sends_utc_bar(monkeypatch) -> None:
    srv = Okx(n=3)
    monkeypatch.setattr(R, "http_get", srv.http)
    close, day = RJ.daily_close("BTC")
    assert srv.bars() == {"1Dutc"}
    assert day == (DAY0 - timedelta(days=1)).strftime("%Y-%m-%d")


def test_journal_rejects_hk(monkeypatch, capsys) -> None:
    monkeypatch.setattr(R, "http_get", Okx(n=3, shift=HK).http)
    assert RJ.daily_close("BTC") is None
    assert "لنگر" in capsys.readouterr().err
