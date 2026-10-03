"""
radar_history.py — کندل آزاد و وارسی سطح (snap). نشست ۷.

همه بی‌شبکه، با صرافی ساختگی و کندل مصنوعی. چهار قفل اصلی:
- واکشی: بازه صفحه‌به‌صفحه، ستون تأیید، «تاریخچه از فلان تاریخ» صریح، لنگر
  نادرست رد، اوکی‌اکس اول و گیت پشتیبان با نام صرافی، نهان‌گاه فقط کندل بسته.
- snap: سطح با سه برخورد تأیید؛ بی‌برخورد نه؛ برخورد پس از زمان ویدیو شمرده
  نمی‌شود؛ تاریخچه کوتاه «داده کافی نیست»؛ تعریف سطح همان radar_levels.
- «قوی» از شانس تصادفی همان پنجره می‌آید، نه عدد ثابت.
- کارت و گزارش: میدان snap کنار سطح، اعتبارسنج، و یک خط برای هر سطح.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_anchor as A
import radar_frames as F
import radar_history as H
import radar_levels as L
import radar_video as V

UTC = timezone.utc


@pytest.fixture(autouse=True)
def _no_pause(monkeypatch):
    monkeypatch.setattr(H, "PAUSE", 0)


# ═══════════════ داده مصنوعی ═══════════════

def zigzag(points, t0: datetime, tf: str = "1D", slope: float = 2.0) -> pd.DataFrame:
    """
    کندل از مسیر خطی میان نقطه‌های چرخش. سایه کندلی که به چرخش می‌رسد ۰.۲ و
    کندل بعدی ۰.۱ — پس سقف و کف هر چرخش یکتاست و نقطه چرخش ۳ و ۳ پیدا می‌شود.
    """
    mids = [float(points[0])]
    for a, b in zip(points, points[1:]):
        n = max(1, round(abs(b - a) / slope))
        mids += [a + (b - a) * k / n for k in range(1, n + 1)]
    step = timedelta(seconds=A.SECONDS[tf])
    rows = []
    for i in range(1, len(mids)):
        o, c = mids[i - 1], mids[i]
        rows.append({"ts": pd.Timestamp(t0 + step * (i - 1)),
                     "open": o, "close": c, "volume": 1.0, "confirm": 1,
                     "high": max(o, c) + (0.2 if c >= o else 0.1),
                     "low": min(o, c) - (0.2 if c <= o else 0.1)})
    return pd.DataFrame(rows)


T0 = datetime(2025, 1, 6, tzinfo=UTC)          # دوشنبه — برای هفتگی هم لنگر درست
THREE = [100, 130, 100, 110, 95, 125, 102, 110, 97, 140, 104, 110, 99, 135]
LATE = [100, 130, 100, 124, 98, 136, 96, 142, 101, 120, 105, 120, 104]
FAR = datetime(2030, 1, 1, tzinfo=UTC)


def peak_rows(df: pd.DataFrame, value: float) -> list[int]:
    """کندل‌هایی که به قله value می‌رسند و بعدشان پایین می‌رود — نه کندل گذری."""
    c = df["close"].values
    return [i for i in range(1, len(df) - 1)
            if abs(c[i] - value) < 1e-9 and c[i - 1] < value and c[i + 1] < value]


# ═══════════════ ۱ — لنگر 15m و 1h ═══════════════

def test_anchor_intraday_rules():
    assert A.anchor_ok(datetime(2023, 3, 13, 14, 15, tzinfo=UTC), "15m")
    assert not A.anchor_ok(datetime(2023, 3, 13, 14, 10, tzinfo=UTC), "15m")
    assert A.anchor_ok(datetime(2023, 3, 13, 14, 0, tzinfo=UTC), "1H")
    assert not A.anchor_ok(datetime(2023, 3, 13, 14, 30, tzinfo=UTC), "1H")
    assert "15m" in A.EXPECT and "1H" in A.EXPECT


def test_history_bar_table_extends_bar_without_touching_it():
    assert A.HISTORY_BAR["okx"] == {"15m": "15m", "1H": "1H", "4H": "4H", "1D": "1Dutc", "1W": "1Wutc"}
    assert A.HISTORY_BAR["gate"] == {"15m": "15m", "1H": "1h", "4H": "4h", "1D": "1d", "1W": "7d"}
    for v in ("okx", "gate"):
        assert set(A.BAR[v]) == {"1D", "4H", "1W"}            # جدول موتور دست نخورد
        assert all(A.HISTORY_BAR[v][k] == A.BAR[v][k] for k in A.BAR[v])
    assert A.SECONDS == {"15m": 900, "1H": 3600, "4H": 14400, "1D": 86400, "1W": 604800}


@pytest.mark.parametrize("raw,tf", [("15m", "15m"), ("1h", "1H"), ("1H", "1H"), ("4h", "4H"),
                                    ("1d", "1D"), ("1D", "1D"), ("1w", "1W"), ("1W", "1W")])
def test_norm_tf(raw, tf):
    assert H.norm_tf(raw) == tf


def test_norm_tf_unknown_is_error():
    with pytest.raises(ValueError):
        H.norm_tf("3h")


# ═══════════════ ۲ — صرافی ساختگی ═══════════════

class Resp:
    def __init__(self, js, status=200):
        self._js, self.status_code = js, status

    def json(self):
        return self._js


def candles_ms(t0: datetime, n: int, tf: str, open_last: bool = False, shift: timedelta = timedelta(0)):
    """[ts_ms, o, h, l, c, v, confirm] صعودی؛ اگر open_last آخری باز است."""
    step = A.SECONDS[tf]
    out = []
    for i in range(n):
        ts = int((t0 + shift + timedelta(seconds=step * i)).timestamp() * 1000)
        p = 100 + (i % 7)
        out.append([ts, p, p + 1, p - 1, p + 0.5, 10.0, 0 if (open_last and i == n - 1) else 1])
    return out


class FakeOKX:
    """history-candles: after یعنی کندل‌های کهنه‌تر از آن، جدید به قدیم، صفحه ۱۰۰تایی."""

    def __init__(self, rows, code="0", fail_on_call=None):
        self.rows = sorted(rows, key=lambda r: -r[0])
        self.code, self.fail_on_call, self.calls = code, fail_on_call, []

    def __call__(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        if self.fail_on_call and len(self.calls) == self.fail_on_call:
            raise requests.ConnectionError("قطع ساختگی")
        assert url == H.OKX_URL
        if self.code != "0":
            return Resp({"code": self.code, "msg": "Instrument ID does not exist", "data": []})
        after = int(params["after"])
        page = [r for r in self.rows if r[0] < after][:100]
        data = [[str(r[0]), str(r[1]), str(r[2]), str(r[3]), str(r[4]), str(r[5]), "0", "0", str(r[6])]
                for r in page]
        return Resp({"code": "0", "msg": "", "data": data})


class FakeGate:
    def __init__(self, rows):
        self.rows, self.calls = sorted(rows, key=lambda r: r[0]), []

    def __call__(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        assert url == H.GATE_URL
        f, t = int(params["from"]) * 1000, int(params["to"]) * 1000
        page = [r for r in self.rows if f <= r[0] <= t]
        assert len(page) <= H.GATE_PAGE
        return Resp([[str(r[0] // 1000), "0", str(r[4]), str(r[2]), str(r[3]), str(r[1]), str(r[5]),
                      "true" if r[6] else "false"] for r in page])


class Router:
    def __init__(self, okx=None, gate=None):
        self.okx, self.gate = okx, gate

    def __call__(self, url, params=None, timeout=None):
        if url == H.OKX_URL:
            if self.okx is None:
                raise requests.ConnectionError("اوکی‌اکس در دسترس نیست")
            return self.okx(url, params, timeout)
        return self.gate(url, params, timeout)


D0 = datetime(2018, 1, 11, tzinfo=UTC)
NOW = datetime(2026, 10, 3, 12, tzinfo=UTC)


# ═══════════════ ۳ — واکشی ═══════════════

def test_okx_range_paginates_and_sends_utc_bar(tmp_path):
    okx = FakeOKX(candles_ms(D0, 400, "1D"))
    s = H.history("BTC", "1d", datetime(2018, 2, 1, tzinfo=UTC), datetime(2018, 8, 31, tzinfo=UTC),
                  cache_dir=tmp_path, get=okx, now=NOW)
    assert s.venue == "okx"
    assert s.df["ts"].iloc[0] == pd.Timestamp("2018-02-01", tz="UTC")
    assert s.df["ts"].iloc[-1] == pd.Timestamp("2018-08-31", tz="UTC")
    assert len(s.df) == 212 and s.df["ts"].is_monotonic_increasing
    assert {p["bar"] for _, p in okx.calls} == {"1Dutc"}
    assert {p["instId"] for _, p in okx.calls} == {"BTC-USDT"}
    assert len(okx.calls) >= 3                                      # صفحه‌به‌صفحه
    assert list(s.df.columns) == ["ts", "open", "high", "low", "close", "volume", "confirm"]


@pytest.mark.parametrize("tf,bar", [("15m", "15m"), ("1h", "1H"), ("4h", "4H"), ("1w", "1Wutc")])
def test_okx_intraday_and_weekly_bar_names(tmp_path, tf, bar):
    t0 = datetime(2024, 1, 1, tzinfo=UTC)                          # دوشنبه
    okx = FakeOKX(candles_ms(t0, 150, H.norm_tf(tf)))
    s = H.history("BTC", tf, t0, t0 + timedelta(seconds=A.SECONDS[H.norm_tf(tf)] * 99),
                  cache_dir=tmp_path, get=okx, now=NOW)
    assert len(s.df) == 100
    assert {p["bar"] for _, p in okx.calls} == {bar}


def test_history_start_is_explicit_not_silent(tmp_path):
    okx = FakeOKX(candles_ms(D0, 100, "1D"))
    s = H.history("BTC", "1d", datetime(2017, 6, 1, tzinfo=UTC), datetime(2018, 3, 1, tzinfo=UTC),
                  cache_dir=tmp_path, get=okx, now=NOW)
    assert s.df["ts"].iloc[0] == pd.Timestamp(D0)
    assert any("تاریخچه okx از 2018-01-11" in n for n in s.notes)
    assert "تاریخچه okx از 2018-01-11" in H.render_md(s)


def test_confirm_column_is_the_venue_flag(tmp_path):
    t0 = datetime(2026, 9, 1, tzinfo=UTC)
    okx = FakeOKX(candles_ms(t0, 33, "1D", open_last=True))
    s = H.history("BTC", "1d", t0, NOW, cache_dir=tmp_path, get=okx, now=NOW)
    assert s.df["confirm"].iloc[-1] == 0 and (s.df["confirm"].iloc[:-1] == 1).all()
    assert "| تأیید |" in H.render_md(s)


def test_off_anchor_candle_is_rejected(tmp_path):
    okx = FakeOKX(candles_ms(D0, 50, "1D", shift=timedelta(hours=16)))    # لنگر هنگ‌کنگ
    with pytest.raises(H.HistoryError, match="لنگر"):
        H.history("BTC", "1d", D0, D0 + timedelta(days=40), venue="okx",
                  cache_dir=tmp_path, get=okx, now=NOW)


def test_mid_pagination_failure_is_loud(tmp_path):
    okx = FakeOKX(candles_ms(D0, 400, "1D"), fail_on_call=2)
    with pytest.raises(H.HistoryError, match="کندل"):
        H.history("BTC", "1d", D0, D0 + timedelta(days=350), venue="okx",
                  cache_dir=tmp_path, get=okx, now=NOW)


def test_okx_failure_falls_to_gate_with_name(tmp_path):
    rows = candles_ms(D0, 60, "1D")
    get = Router(okx=FakeOKX(rows, code="51001"), gate=FakeGate(rows))
    s = H.history("XYZ", "1d", D0, D0 + timedelta(days=59), cache_dir=tmp_path, get=get, now=NOW)
    assert s.venue == "gate" and len(s.df) == 60
    assert any("okx" in n and "51001" in n for n in s.notes)
    assert "| صرافی | gate |" in H.render_md(s)
    assert {p["interval"] for _, p in get.gate.calls} == {"1d"}
    assert {p["currency_pair"] for _, p in get.gate.calls} == {"XYZ_USDT"}


def test_partial_okx_history_does_not_mix_gate(tmp_path):
    get = Router(okx=FakeOKX(candles_ms(D0, 100, "1D")), gate=FakeGate(candles_ms(D0 - timedelta(days=300), 400, "1D")))
    s = H.history("BTC", "1d", datetime(2017, 6, 1, tzinfo=UTC), datetime(2018, 3, 1, tzinfo=UTC),
                  cache_dir=tmp_path, get=get, now=NOW)
    assert s.venue == "okx" and get.gate.calls == []


def test_both_venues_fail_is_error(tmp_path):
    get = Router(okx=None, gate=lambda *a, **k: Resp({"label": "INVALID_CURRENCY", "message": "x"}, 400))
    with pytest.raises(H.HistoryError, match="okx.*gate"):
        H.history("NOPE", "1d", D0, D0 + timedelta(days=5), cache_dir=tmp_path, get=get, now=NOW)


def test_gate_recent_limit_is_announced(tmp_path):
    t_now = datetime(2026, 10, 3, tzinfo=UTC)
    start = t_now - timedelta(minutes=15 * 12000)
    rows = candles_ms(t_now - timedelta(minutes=15 * 9999), 9999, "15m")
    get = Router(okx=FakeOKX([], code="51001"), gate=FakeGate(rows))
    s = H.history("BTC", "15m", start, t_now - timedelta(minutes=15), cache_dir=tmp_path, get=get, now=t_now)
    assert s.venue == "gate"
    assert any("گیت" in n and "۱۰۰۰۰" in n for n in s.notes)      # آستانه صرافی — رقم فارسی
    assert all(int(p["from"]) * 1000 >= rows[0][0] - 15 * 60 * 1000 for _, p in get.gate.calls)


def test_cache_serves_closed_candles_without_network(tmp_path):
    rows = candles_ms(D0, 200, "1D")
    first = FakeOKX(rows)
    a = H.history("BTC", "1d", D0, D0 + timedelta(days=150), cache_dir=tmp_path, get=first, now=NOW)
    second = FakeOKX(rows)
    b = H.history("BTC", "1d", D0, D0 + timedelta(days=150), cache_dir=tmp_path, get=second, now=NOW)
    assert second.calls == [] and b.cached == len(b.df) and b.fetched == 0
    pd.testing.assert_frame_equal(a.df, b.df)
    assert list((tmp_path / "okx").glob("BTC-1D.*"))


def test_cache_never_keeps_open_candle(tmp_path):
    t0 = datetime(2026, 9, 1, tzinfo=UTC)
    rows = candles_ms(t0, 33, "1D", open_last=True)
    H.history("BTC", "1d", t0, NOW, cache_dir=tmp_path, get=FakeOKX(rows), now=NOW)
    again = FakeOKX(rows)
    s = H.history("BTC", "1d", t0, NOW, cache_dir=tmp_path, get=again, now=NOW)
    assert again.calls                                              # کندل باز دوباره از صرافی
    assert s.df["confirm"].iloc[-1] == 0
    cached = (tmp_path / "okx" / "BTC-1D.csv").read_text(encoding="utf-8").strip().splitlines()
    assert len(cached) == 1 + 32                                     # سرخط و فقط بسته‌ها


def test_cache_extends_only_missing_part(tmp_path):
    rows = candles_ms(D0, 300, "1D")
    H.history("BTC", "1d", D0 + timedelta(days=100), D0 + timedelta(days=200), cache_dir=tmp_path,
              get=FakeOKX(rows), now=NOW)
    more = FakeOKX(rows)
    s = H.history("BTC", "1d", D0 + timedelta(days=50), D0 + timedelta(days=200), cache_dir=tmp_path,
                  get=more, now=NOW)
    assert len(s.df) == 151 and s.cached == 101 and s.fetched == 50
    assert all(int(p["after"]) <= int((D0 + timedelta(days=100)).timestamp() * 1000) for _, p in more.calls)


def test_gap_is_reported(tmp_path):
    rows = candles_ms(D0, 60, "1D")
    del rows[30:33]
    s = H.history("BTC", "1d", D0, D0 + timedelta(days=59), cache_dir=tmp_path, get=FakeOKX(rows), now=NOW)
    assert len(s.df) == 57
    assert any("شکاف" in n and "3" in n for n in s.notes)


def test_cli_out_is_a_file_and_csv_has_venue(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(H, "SESSION", type("S", (), {"get": staticmethod(FakeOKX(candles_ms(D0, 40, "1D")))})())
    out, csv = tmp_path / "btc.md", tmp_path / "btc.csv"
    rc = H.main(["--symbol", "BTC", "--tf", "1d", "--from", "2018-01-11", "--to", "2018-01-20",
                 "--cache", str(tmp_path / "c"), "--out", str(out), "--csv", str(csv)])
    assert rc == 0 and out.is_file()
    assert "BTC" in out.read_text(encoding="utf-8")
    head, *body = csv.read_text(encoding="utf-8").splitlines()
    assert head == "ts,open,high,low,close,volume,confirm,venue" and len(body) == 10
    assert body[0].endswith(",1,okx")


def test_cli_out_directory_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "SESSION", type("S", (), {"get": staticmethod(FakeOKX(candles_ms(D0, 40, "1D")))})())
    d = tmp_path / "zec.txt"
    d.mkdir()
    rc = H.main(["--symbol", "BTC", "--tf", "1d", "--from", "2018-01-11", "--to", "2018-01-20",
                 "--cache", str(tmp_path / "c"), "--out", str(d)])
    assert rc == 2 and list(d.iterdir()) == []                    # درس ک۱۴: هرگز فایل داخل پوشه


def test_date_only_to_includes_that_day():
    assert H.parse_time("2019-05-13", end=True) == datetime(2019, 5, 13, 23, 59, 59, 999000, tzinfo=UTC)
    assert H.parse_time("2023-03-13T16:30:01Z") == datetime(2023, 3, 13, 16, 30, 1, tzinfo=UTC)


# ═══════════════ ۴ — snap ═══════════════

def test_three_touch_level_is_confirmed():
    df = zigzag(THREE, T0)
    s = H.snap_frame(df, 110.2, "1D", FAR)
    assert s["verdict"] == "confirmed" and s["touches"] == 3
    assert s["class"] == "structural" and s["from"] == "candles"
    assert abs(s["nearest"] - 110.2) < 1e-6 and s["distance_atr"] < 0.25


def test_untouched_level_is_not_confirmed():
    df = zigzag(THREE, T0)
    s = H.snap_frame(df, 117.0, "1D", FAR)
    assert s["verdict"] == "not_near" and s["touches"] is None
    assert abs(s["nearest"] - 110.2) < 1e-6 and s["nearest_touches"] == 3
    assert s["distance_atr"] > 0.25


def test_touch_after_video_is_not_counted():
    df = zigzag(THREE, T0)
    third = peak_rows(df, 110)[2]
    cutoff = df["ts"].iloc[third].to_pydatetime()                  # کندل برخورد سوم هنوز بسته نشده
    assert H.snap_frame(df, 110.2, "1D", cutoff)["touches"] == 2
    assert H.snap_frame(df, 110.2, "1D", FAR)["touches"] == 3


def test_level_touched_only_after_video_is_not_confirmed():
    df = zigzag(LATE, T0)
    first = peak_rows(df, 120)[0]
    cutoff = df["ts"].iloc[first - 3].to_pydatetime()
    before = H.snap_frame(df, 120.2, "1D", cutoff)
    assert before["verdict"] == "not_near"
    assert before["last_bar"] < df["ts"].iloc[first].isoformat()
    assert H.snap_frame(df, 120.2, "1D", FAR)["verdict"] == "confirmed"


def test_short_history_is_no_data():
    df = zigzag([100, 130, 100, 115], T0)                          # کمتر از ۶۰ کندل
    assert len(df) < H.MIN_BARS
    s = H.snap_frame(df, 110.0, "1D", FAR)
    assert s["verdict"] == "no_data" and "60" in s["reason"].translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))


def test_snap_rejects_off_anchor_candles():
    df = zigzag(THREE, T0)
    df["ts"] = df["ts"] + pd.Timedelta(hours=16)
    with pytest.raises(H.HistoryError, match="لنگر"):
        H.snap_frame(df, 110.2, "1D", FAR)


def test_lookback_window_is_last_n_closed_candles():
    df = zigzag(THREE, T0)
    s = H.snap_frame(df, 110.2, "1D", FAR, lookback=60)
    assert s["bars"] == 60 and s["lookback"] == 60
    assert s["touches"] in (None, 1, 2)                            # برخوردهای کهنه بیرون از پنجره


def test_sub_daily_is_trigger_class():
    df = zigzag(THREE, T0, tf="4H")
    s = H.snap_frame(df, 110.2, "4H", FAR)
    assert s["verdict"] == "confirmed" and s["class"] == "trigger"


def test_one_level_definition(monkeypatch):
    """snap و assess هر دو از radar_levels.structural_levels می‌خوانند — یک تعریف."""
    calls = []
    real = L.structural_levels

    def spy(df, atr, tol_atr=1.0):
        calls.append(len(df))
        return real(df, atr, tol_atr)
    monkeypatch.setattr(L, "structural_levels", spy)
    df = zigzag(THREE, T0)
    H.snap_frame(df, 110.2, "1D", FAR)
    assert calls
    calls.clear()
    L.assess("X", df)
    assert calls


def test_structural_levels_matches_assess_rules():
    df = zigzag(THREE, T0)
    atr = float(L.atr_wilder(df).iloc[-1])
    res, sup = L.structural_levels(df, atr)
    assert {lv.kind for lv in res} <= {"مقاومت"} and {lv.kind for lv in sup} <= {"حمایت"}
    assert all(lv.touches >= 2 for lv in res + sup)
    assert any(abs(lv.price - 110.2) < 1e-6 and lv.touches == 3 for lv in res)


def test_strong_label_from_window_chance():
    s = H.snap_frame(zigzag(THREE, T0), 110.2, "1D", FAR)
    assert s["strength"] == "strong"
    assert s["chance_at_touches_pct"] <= 10 and s["strong_min_touches"] <= 3
    assert 0 < s["chance_pct"] < 100


def test_many_touches_can_still_be_weak():
    """دو سطح پرتکرار در پنجره باریک: خط تصادفی بیش از ۱۰٪ وقت به آن‌ها می‌رسد."""
    df = zigzag([100, 110] * 10, T0)
    s = H.snap_frame(df, 110.2, "1D", FAR)
    assert s["verdict"] == "confirmed" and s["touches"] >= 8
    assert s["strength"] == "weak" and s["chance_at_touches_pct"] > 10
    assert s["strong_min_touches"] is None


def test_snap_label_texts():
    df = zigzag(THREE, T0)
    assert H.snap_label(H.snap_frame(df, 110.2, "1D", FAR)) == "واقعی با 3 برخورد — قوی"
    assert H.snap_label(H.snap_frame(df, 117.0, "1D", FAR)).startswith("خط دلخواه")
    assert H.snap_label(H.snap_frame(df.head(30), 110.2, "1D", FAR)).startswith("داده کافی نیست")
    assert "ماشه" in H.snap_label(H.snap_frame(zigzag(THREE, T0, tf="4H"), 110.2, "4H", FAR))


# ═══════════════ ۵ — جمع‌بندی تحلیل‌گر ═══════════════

def fake_snap(verdict, chance, touches=None, price=1.0):
    return {"verdict": verdict, "chance_pct": chance, "touches": touches, "symbol": "BTC-USDT",
            "tf": "4H", "cutoff": "2026-01-01T00:00:00+00:00", "level": price, "strength": "weak"}


def test_summary_small_sample_gives_numbers_not_verdict():
    snaps = [fake_snap("confirmed", 30.0, 2, p) for p in range(5)]
    s = H.summarize(snaps)
    assert s["n"] == 5 and s["confirmed"] == 5 and s["verdict"] == "small"
    assert "نمونه کم" in "\n".join(H.summary_lines(s))


def test_summary_clearly_above_chance():
    snaps = ([fake_snap("confirmed", 30.0, 2, p) for p in range(20)]
             + [fake_snap("not_near", 30.0, None, 100 + p) for p in range(5)])
    s = H.summarize(snaps)
    assert s["verdict"] == "above" and s["p_value"] < 0.001
    assert abs(s["expected_pct"] - 30.0) < 1e-9


def test_summary_not_distinguishable_from_chance():
    snaps = ([fake_snap("confirmed", 30.0, 2, p) for p in range(8)]
             + [fake_snap("not_near", 30.0, None, 100 + p) for p in range(17)])
    assert H.summarize(snaps)["verdict"] == "chance"


def test_summary_dedupes_repeated_lines_and_skips_no_data():
    snaps = ([fake_snap("confirmed", 30.0, 2, 5.0)] * 4 + [fake_snap("no_data", None, None, 9.0)])
    s = H.summarize(snaps)
    assert s["n"] == 1 and s["no_data"] == 1


# ═══════════════ ۶ — کارت، اعتبارسنج، گزارش ═══════════════

def good_snap():
    return H.snap_frame(zigzag(THREE, T0), 110.2, "1D", FAR)


def card_with(level: dict) -> dict:
    return {"frame_id": "v_00m10.0s", "t": 10.0, "refs": [], "is_chart": True,
            "recorded_at": {"value": None, "confidence": None, "from": "image", "note": "ناخوانا"},
            "coin": {"value": "BTC", "confidence": "high", "from": "image"},
            "venue": {"value": None, "confidence": None, "from": "image", "note": "ناخوانا"},
            "timeframe": {"value": "1D", "confidence": "high", "from": "image"},
            "chart_type": {"value": "candles", "confidence": "high", "from": "image"},
            "scale": {"value": "linear", "confidence": "high", "from": "image"},
            "price_axis": {}, "levels": [level], "trendlines": [], "zones": [], "patterns": [],
            "indicators": [], "texts": [], "speech": "", "method_notes": []}


def level_obj(price=110.2):
    return {"price": {"value": price, "confidence": "high", "from": "image"}, "kind": "horizontal",
            "label": "خط سفید"}


def test_validator_accepts_snap_numbers_from_candles():
    lv = level_obj()
    lv["snap"] = good_snap()
    assert F.validate_card(card_with(lv)) == []


def test_validator_still_rejects_bare_numbers_elsewhere():
    lv = level_obj()
    lv["snap"] = good_snap()
    lv["width"] = 3.0
    assert any("عدد بی‌اطمینان" in e for e in F.validate_card(card_with(lv)))


@pytest.mark.parametrize("broken", [
    {"verdict": "maybe"}, {"from": "image"}, {"cutoff": "2026-01-01T00:00:00"},
    {"touches": float("nan")}, {"tool": None}])
def test_validator_rejects_bad_snap(broken):
    lv = level_obj()
    lv["snap"] = {**good_snap(), **broken}
    assert F.validate_card(card_with(lv))


def test_validator_checks_daily_column_too():
    lv = level_obj()
    lv["snap"] = {**H.snap_frame(zigzag(THREE, T0, tf="4H"), 110.2, "4H", FAR),
                  "daily": {**good_snap(), "verdict": "maybe"}}
    assert any("daily" in e for e in F.validate_card(card_with(lv)))


def write_card(tmp_path: Path, levels: list[dict], coin="BTC", tf="4h") -> Path:
    doc = tmp_path / "intake" / "src" / "doc.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("---\nمنبع: آزمون\nتاریخ انتشار: 2026-01-10T08:00:00+00:00\n---\n", encoding="utf-8")
    card = card_with(levels[0])
    card["levels"] = levels
    card["coin"]["value"], card["timeframe"]["value"] = coin, tf
    path = tmp_path / "intake" / "charts" / "src" / "vid.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schema": 1, "kind": "radar-chart-cards", "video_id": "vid",
                                "doc_id": "d", "doc": str(doc), "source": "src", "cards": [card]},
                               ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def fake_history_fn(calls):
    def fn(symbol, tf, start, end, **kw):
        calls.append((symbol, tf, end))
        t0 = datetime(2025, 6, 2, tzinfo=UTC) if tf != "1D" else datetime(2025, 6, 2, tzinfo=UTC)
        df = zigzag(THREE, t0, tf=tf)
        return H.Series(symbol=symbol, tf=tf, venue="okx", df=df, start=start, end=end, notes=[])
    return fn


def test_cards_command_writes_snap_and_daily_column(tmp_path):
    path = write_card(tmp_path, [level_obj(110.2), level_obj(117.0), level_obj(None)])
    path_json = json.loads(path.read_text(encoding="utf-8"))
    path_json["cards"][0]["levels"][2]["price"] = {"value": None, "confidence": None, "from": "image",
                                                   "note": "ناخوانا"}
    path.write_text(json.dumps(path_json, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    calls = []
    rc = H.cards_cmd([path], history_fn=fake_history_fn(calls))
    assert rc == 0
    lv = json.loads(path.read_text(encoding="utf-8"))["cards"][0]["levels"]
    assert lv[0]["snap"]["verdict"] == "confirmed" and lv[0]["snap"]["class"] == "trigger"
    assert lv[0]["snap"]["daily"]["tf"] == "1D"
    assert lv[1]["snap"]["verdict"] == "not_near"
    assert lv[2]["snap"]["verdict"] == "no_data" and "ناخوانا" in lv[2]["snap"]["reason"]
    cutoff = datetime(2026, 1, 10, 8, tzinfo=UTC)
    assert all(end == cutoff for _, _, end in calls)                 # برش همان زمان انتشار
    assert {tf for _, tf, _ in calls} == {"4H", "1D"}
    assert F.validate_cards(json.loads(path.read_text(encoding="utf-8"))) == []


def test_cards_command_index_symbol_is_no_data(tmp_path):
    path = write_card(tmp_path, [level_obj(59.2)], coin="BTC.D", tf="1h")
    calls = []
    assert H.cards_cmd([path], history_fn=fake_history_fn(calls)) == 0
    s = json.loads(path.read_text(encoding="utf-8"))["cards"][0]["levels"][0]["snap"]
    assert s["verdict"] == "no_data" and "شاخص" in s["reason"] and calls == []


def test_cards_dry_run_writes_nothing(tmp_path):
    path = write_card(tmp_path, [level_obj(110.2)])
    before = path.read_bytes()
    assert H.cards_cmd([path], history_fn=fake_history_fn([]), dry_run=True) == 0
    assert path.read_bytes() == before


@pytest.mark.parametrize("coin,sym", [("BTC", "BTC"), ("BTCUSD", "BTC"), ("BTCUSDT", "BTC"),
                                      ("ETH/USDT", "ETH"), ("BTC.D", None), ("TOTAL2", None),
                                      ("USDT.D", None)])
def test_exchange_symbol(coin, sym):
    assert H.exchange_symbol(coin) == sym


def test_video_report_has_one_line_per_level():
    lv1, lv2 = level_obj(110.2), level_obj(117.0)
    lv1["snap"] = good_snap()
    lv2["snap"] = H.snap_frame(zigzag(THREE, T0), 117.0, "1D", FAR)
    lv3 = level_obj(120.0)                                          # وارسی‌نشده
    card = card_with(lv1)
    card["levels"] = [lv1, lv2, lv3]
    cards = {"schema": 1, "video_id": "vid", "doc_id": "d", "source": "src", "title": "آزمون",
             "cards": [card]}
    md = V.render_report(cards, {})
    assert "واقعی با 3 برخورد — قوی" in md
    assert "خط دلخواه" in md
    assert "وارسی نشده" in md
    assert "## وارسی سطح با کندل" in md and "نمونه کم" in md
