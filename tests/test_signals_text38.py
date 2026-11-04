"""
هشدارهای تازه متن ۳۸ — اهرم داغ، بسته هفتگی بیت‌کوین در برابر میانگین ۵۰ هفته، دو ساعت
پیش از رویداد مهم و نتیجه رویداد. همه فقط اطلاع؛ هیچ حکم خرید و فروشی نمی‌سازند.
داده ساختگی، بی شبکه.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import radar_calendar as RC
import radar_signals as SG
import radar_watch as W

UTC = timezone.utc
NOW = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)


def _hourly(closes, end=NOW, lo=None, hi=None):
    """شمع بسته ساعتی تا end — هر ردیف open، close، low، high."""
    rows, t = [], end - timedelta(hours=len(closes))
    for c in closes:
        rows.append({"open": t, "close": c, "low": lo or c * 0.99, "high": hi or c * 1.01})
        t += timedelta(hours=1)
    return rows


def _snap(fund, now=NOW, sym="BTC", price=80000.0):
    return {"generated_utc": (now - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M UTC"),
            "symbols": {sym: {"price": price, "funding_8h_pct": fund}}}


def _oi(pct, n=30, end=NOW):
    t1 = int(end.replace(minute=0).timestamp() * 1000)
    pts = [(t1 - (n - 1 - i) * 3_600_000, 1000.0) for i in range(n)]
    pts[-1] = (pts[-1][0], 1000.0 * (1 + pct / 100))
    return lambda s: (pts, None)


def _heat(fund=0.035, oi_pct=12.0, closes=None, state=None, **kw):
    closes = closes or [80000.0] * 30
    return SG.leverage_heat(["BTC"], {} if state is None else state, NOW,
                            hourly=lambda s: (_hourly(closes), []), snapshot=_snap(fund),
                            oi=_oi(oi_pct), pause=0, **kw)


# ── اهرم داغ ──

def test_heat_fires_when_funding_hot_oi_up_price_flat():
    out = _heat()
    assert len(out) == 1
    a = out[0]
    assert a.level == "orange" and a.symbol == "BTC" and "اهرم داغ BTC" in a.title
    assert "+12.0٪" in a.why and "+0.0350٪" in a.why and "فرضیه آزمون‌نشده" in a.nxt
    assert a.startswith("🔥") and "چه کنم:" in a
    key = f"lev_heat_BTC_{NOW:%Y-%m-%d}"
    assert key in a.sets and a.sets[key]["side"] == "long"


@pytest.mark.parametrize("kw", [dict(fund=0.02), dict(oi_pct=9.0),
                                dict(closes=[80000.0] * 5 + [78000.0] + [80000.0] * 24)])
def test_heat_quiet_when_any_condition_fails(kw):
    assert _heat(**kw) == []


def test_heat_short_side_and_once_per_day():
    out = _heat(fund=-0.012)
    assert out and out[0].sets[f"lev_heat_BTC_{NOW:%Y-%m-%d}"]["side"] == "short"
    assert "شورت‌ها" in out[0].title
    st: dict = {}
    out[0].commit(st)
    assert _heat(fund=-0.012, state=st) == []


def test_heat_no_oi_fetch_when_funding_normal():
    asked = []
    SG.leverage_heat(["BTC"], {}, NOW, hourly=lambda s: (_hourly([80000.0] * 30), []),
                     snapshot=_snap(0.01), oi=lambda s: asked.append(s) or ([], None), pause=0)
    assert asked == []


def test_heat_stale_snapshot_or_network_error_is_no_data(capsys):
    old = _snap(0.05, now=NOW - timedelta(hours=6))
    assert SG.leverage_heat(["BTC"], {}, NOW, snapshot=old, pause=0) == []
    assert "کهنه" in capsys.readouterr().out

    def boom(s):
        raise RuntimeError("شبکه")
    assert SG.leverage_heat(["BTC"], {}, NOW, hourly=boom, snapshot=_snap(0.05), pause=0) == []
    assert "RuntimeError" in capsys.readouterr().out


def test_heat_dust_position_skipped():
    h = {"positions": [{"symbol": "TRX", "book": "position", "status": "open",
                        "lots": [{"qty": 0.67, "account": "LBank", "entry": None}]}]}
    snap = _snap(-0.02, sym="TRX", price=0.32)
    out = SG.leverage_heat(["TRX"], {}, NOW, hourly=lambda s: (_hourly([0.32] * 30), []),
                           snapshot=snap, oi=_oi(20.0), h=h, pause=0)
    assert out == []


# ── بسته هفتگی بیت‌کوین در برابر میانگین ۵۰ هفته ──

CLOSE = "2026-11-02T00:00:00+00:00"


def _regime(value, closed_at=CLOSE):
    gen = datetime.fromisoformat(closed_at) + timedelta(hours=9)
    return {"generated_at": gen.isoformat(), "score": -0.5,
            "btc_sma50w": {"value": value, "weeks": 50, "close": 78342.5,
                           "week_closed_at": closed_at}}


def _mkt(state, value, close=78342.5, closed_at=CLOSE):
    w = {"market": [{"symbol": "BTC", "label": "میانگین ساده ۵۰ هفته"}], "updated": "2026-11-01"}
    wk = lambda s: ({"close": close, "closed_at": closed_at, "venue": "okx"}, [])
    now = datetime.fromisoformat(closed_at) + timedelta(hours=10)
    return W.check_positions(w, {"positions": [], "ledger": []}, state, now, weekly=wk,
                             price=lambda s: None, regime=_regime(value, closed_at))


def test_btc_above_sma_is_blue_and_cross_is_orange():
    st: dict = {}
    m = _mkt(st, 75775.434)
    assert len(m) == 1 and m[0].level == "blue" and m[0].startswith("📈 بسته هفتگی BTC")
    assert "هشدار بازار" not in m[0] and "3.4٪ بالای" in m[0].why
    nxt = "2026-11-09T00:00:00+00:00"
    m2 = _mkt(st, 79000.0, close=77000.0, closed_at=nxt)
    assert m2[0].level == "orange" and m2[0].startswith("📉 هشدار بازار") and "زیر" in m2[0].title
    assert "رفت" in m2[0].title
    m3 = _mkt(st, 79000.0, close=76000.0, closed_at="2026-11-16T00:00:00+00:00")
    assert m3[0].level == "blue"                                  # ماندن زیر خط
    m4 = _mkt(st, 75000.0, close=80000.0, closed_at="2026-11-23T00:00:00+00:00")
    assert m4[0].level == "orange" and "برگشت" in m4[0].title


def test_btc_first_judgement_below_is_orange():
    m = _mkt({}, 80000.0)
    assert m[0].level == "orange" and "هشدار بازار" in m[0]


# ── دو ساعت پیش و روز پیش رویداد ──

EV = datetime(2026, 11, 6, 13, 30, tzinfo=UTC)


def _cal(**extra):
    e = {"id": "nfp-2026-10", "at": EV.isoformat(), "name": "گزارش اشتغال (NFP)",
         "importance": "high"}
    e.update(extra)
    return {"version": 1, "events": [e]}


def test_reminder_parts_near_is_orange_day_is_blue():
    near = RC.reminder_parts(_cal(expected="+120K"), "event_near_nfp-2026-10",
                             EV - timedelta(minutes=90))
    assert near["level"] == "orange" and "۹۰ دقیقه دیگر" in near["title"]
    assert "خرید تازه نه" in near["do"] and "+120K" in near["why"] and near["symbol"] == "BTC"
    day = RC.reminder_parts(_cal(), "event_day_nfp-2026-10", EV - timedelta(hours=20))
    assert day["level"] == "blue" and "دو ساعت پیش" in day["nxt"]
    assert RC.reminder_parts(_cal(), "event_near_gone", EV)["level"] == "orange"


def test_calendar_result_fields_validated():
    RC.validate(_cal(expected="+120K", actual="+95K", lesson="درس"))
    with pytest.raises(RC.CalendarError):
        RC.validate(_cal(actual=95))
    with pytest.raises(RC.CalendarError):
        RC.validate(_cal(expected="  "))


def test_watcher_sends_reminder_as_leveled_alert(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "cal.json").write_text(json.dumps(_cal(), ensure_ascii=False), encoding="utf-8")
    sent = []
    monkeypatch.setattr(W, "notify", lambda m, quiet=False: sent.append(m) or W.TG.Sent(True, "200"))
    monkeypatch.setattr(W, "stale_warning", lambda p: None)
    st: dict = {}
    W.run_once({"items": []}, st, quiet=True, now=EV - timedelta(minutes=100),
               regime_path=None, events_path="cal.json")
    assert len(sent) == 1 and sent[0].level == "orange" and sent[0].startswith("⏰")
    assert st.get("event_near_nfp-2026-10") is True


# ── نتیجه رویداد ──

class _S:
    def __init__(self, df, venue="okx"):
        self.df, self.venue = df, venue


def _hist15(p0=80000.0, p15=80300.0, p30=79800.0, confirm=(1, 1), at=EV):
    def history(sym, tf, a, b, cache_dir=None, now=None):
        assert sym == "BTC" and tf == "15m" and a == at and b == at + timedelta(minutes=15)
        df = pd.DataFrame({"ts": [pd.Timestamp(at), pd.Timestamp(at + timedelta(minutes=15))],
                           "open": [p0, p15], "high": [80500.0, 80400.0],
                           "low": [79900.0, 79700.0], "close": [p15, p30],
                           "confirm": list(confirm)})
        return _S(df)
    return history


def _ledger():
    return {"version": 1, "events": [
        {"id": "nfp:2026-10-02", "kind": "nfp", "at": "2026-10-02T12:30:00Z", "importance": "high",
         "title": "گزارش اشتغال", "prices": {"BTC": {"before": {"close": 86418.2},
                                                     "h24": {"close": 84676.2}}}},
        {"id": "nfp:2026-11-06", "kind": "nfp", "at": "2026-11-06T13:30:00Z", "importance": "high",
         "title": "گزارش اشتغال", "prices": {"BTC": {"before": None, "h24": None}}},
        {"id": "unlock:SUI:2026-11-06", "kind": "unlock", "at": "2026-11-06T13:30:00Z",
         "importance": "high", "title": "آزادسازی", "prices": {}}]}


def test_event_result_blue_with_reaction_and_lesson():
    now = EV + timedelta(minutes=41)
    out = SG.event_results(_cal(expected="+120K", actual="+95K"), _ledger(), {}, now,
                           history=_hist15())
    assert len(out) == 1
    a = out[0]
    assert a.level == "blue" and a.title == "نتیجه گزارش اشتغال (NFP)"
    assert "عدد واقعی +95K، انتظار بازار +120K" in a.why
    assert "-0.25٪" in a.why and "80000" in a.why and "79800" in a.why
    assert "10-02 -2.0٪" in a.nxt and "دفتر" in a.nxt
    rec = a.sets["event_result_nfp-2026-10"]
    assert rec["kind"] == "nfp" and rec["chg30_pct"] == pytest.approx(-0.25)
    assert "خرید تازه نه" in a.do                              # پنجره تا ۱ ساعت پس از انتشار


def test_event_result_timing_and_once():
    assert SG.event_results(_cal(), _ledger(), {}, EV + timedelta(minutes=29),
                            history=_hist15()) == []
    assert SG.event_results(_cal(), _ledger(), {}, EV + timedelta(hours=13),
                            history=_hist15()) == []
    st = {"event_result_nfp-2026-10": {"at": "x"}}
    assert SG.event_results(_cal(), _ledger(), st, EV + timedelta(hours=1), history=_hist15()) == []


def test_event_result_from_ledger_only_and_no_unlock():
    out = SG.event_results(None, _ledger(), {}, EV + timedelta(hours=1), history=_hist15())
    assert [a.title for a in out] == ["نتیجه گزارش اشتغال"]
    assert "ثبت نشده" in out[0].why


def test_event_result_missing_candle_retries_then_sends_without_reaction(capsys):
    h = _hist15(confirm=(1, 0))
    assert SG.event_results(_cal(), _ledger(), {}, EV + timedelta(hours=1), history=h) == []
    assert "اجرای بعد" in capsys.readouterr().out
    out = SG.event_results(_cal(), _ledger(), {}, EV + timedelta(hours=4), history=h)
    assert out and "داده ندارم" in out[0].why and "p0" not in out[0].sets["event_result_nfp-2026-10"]


def test_event_lesson_from_calendar_wins():
    out = SG.event_results(_cal(lesson="اشتغال ضعیف یعنی کاهش نرخ زودتر"), _ledger(), {},
                           EV + timedelta(hours=1), history=_hist15())
    assert out[0].nxt == "درس: اشتغال ضعیف یعنی کاهش نرخ زودتر"
