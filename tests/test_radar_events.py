"""
آزمون radar_events.py — نشست ۱۰ رادار ۷: تقویم رویداد، آزادسازی و دفتر رویداد.

تصمیم‌های ایستگاه ۱، رویداد ۸۷:
- جلسه فدرال‌رزرو از calendar.json رسمی، به وقت شرقی آمریکا؛ تورم، اشتغال و شاخص
  قیمت تولیدکننده از FRED، به وقت مرکزی آمریکا؛ PCE با ICS رسمی BEA وارسی متقاطع —
  ف۳۲. اهمیت بالا: تصمیم فدرال‌رزرو، تورم مصرف‌کننده، اشتغال؛ میانه: صورت‌جلسه،
  PCE، شاخص قیمت تولیدکننده.
- آزادسازی از DefiLlama عمومی، مخرج عرضه در گردش CoinGecko — ف۳۳. وتو: تک‌پله
  دست‌کم ۱٪ یا جمع دست‌کم ۲٪ در ۳۰ روز؛ پاداش استیکینگ و استخراج شمرده نمی‌شود؛
  «داده ناقص» یعنی «نامعلوم»، نه رد خودکار و نه عبور — ف۳۱. «بی‌زمان‌بندی» ثابت
  فقط BNB.
- دفتر رویداد: قیمت پیش، ۲۴ ساعت و ۷ روز از کندل ۱ ساعته بسته؛ فقط پس از سررسید؛
  شکست با دلیل، هرگز تخمین.
- خروجی: گزارش کامل، بخش ۱۴ روزه برای LATEST.md، یک خط ساده تلگرام بی‌قالب‌بندی.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_events as E

UTC = timezone.utc
ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)
DAY = 86_400


def _ts(d: datetime) -> int:
    return int(d.timestamp())


# ═══════════════ تقویم فدرال‌رزرو ═══════════════

FED = {"events": [
    {"title": "FOMC Meeting", "time": "2:00 p.m.", "month": "2026-10", "days": "28", "type": "FOMC",
     "description": "&lt;p&gt;Two-day meeting, October 27 - 28&lt;/p&gt;"},
    {"title": "FOMC Meeting", "time": "2:00 p.m.", "month": "2026-10", "days": "28", "type": "FOMC"},
    {"title": "FOMC Press Conference", "time": "2:30 p.m.", "month": "2026-10", "days": "28",
     "type": "FOMC"},
    {"title": " FOMC Minutes", "time": "2:00 p.m.", "month": "2026-10", "days": "7", "type": "FOMC"},
    {"title": "FOMC Meeting", "time": "2:00 p.m.", "month": "2026-12", "days": "9", "type": "FOMC"},
    {"title": "FOMC Meeting", "time": "2:00 p.m.", "month": "", "days": "1", "type": "events"},
    {"title": "Speech - Governor X", "time": "4:30 a.m.", "month": "2026-10", "days": "8",
     "type": "Speeches"},
]}


def test_fed_meetings_and_minutes_in_utc() -> None:
    ev = {e["id"]: e for e in E.parse_fed_calendar(FED)}
    assert set(ev) == {"fomc:2026-10-28", "fomc_minutes:2026-10-07", "fomc:2026-12-09"}
    # ساعت تابستانی آمریکا ۱ نوامبر ۲۰۲۶ تمام می‌شود
    assert ev["fomc:2026-10-28"]["at"] == "2026-10-28T18:00:00Z"
    assert ev["fomc:2026-12-09"]["at"] == "2026-12-09T19:00:00Z"
    assert ev["fomc_minutes:2026-10-07"]["at"] == "2026-10-07T18:00:00Z"
    assert ev["fomc:2026-10-28"]["importance"] == "high"
    assert ev["fomc_minutes:2026-10-07"]["importance"] == "medium"
    assert "federalreserve.gov" in ev["fomc:2026-10-28"]["source"]


def test_fed_bad_time_is_skipped_not_guessed() -> None:
    doc = {"events": [{"title": "FOMC Meeting", "time": "TBD", "month": "2026-10", "days": "28",
                       "type": "FOMC"}]}
    assert E.parse_fed_calendar(doc) == []


# ═══════════════ FRED ═══════════════

def _fred(rows: list[tuple[str, str, int, str]]) -> str:
    """ساختار جدول تقویم FRED — روز، ساعت، پیوند انتشار."""
    out = ["<table>"]
    for day, tm, rid, name in rows:
        out.append(f'<tr class="day"><td>{day}</td></tr>')
        out.append(f'<tr><td>{tm} </td><td><a href="/release?rid={rid}">{name}</a></td></tr>')
    return "\n".join(out + ["</table>All times are US Central Time."])


def test_fred_rows_central_to_utc() -> None:
    html = _fred([("Wednesday October 14, 2026", "7:30 am", 10, "Consumer Price Index"),
                  ("Thursday December 10, 2026", "7:30 am", 10, "Consumer Price Index")])
    ev = E.parse_fred_calendar(html, "cpi")
    assert [e["at"] for e in ev] == ["2026-10-14T12:30:00Z", "2026-12-10T13:30:00Z"]
    assert ev[0]["id"] == "cpi:2026-10-14" and ev[0]["importance"] == "high"
    assert "rid=10" in ev[0]["source"]


def test_fred_ignores_other_releases() -> None:
    html = _fred([("Friday November 06, 2026", "7:30 am", 50, "Employment Situation"),
                  ("Friday November 06, 2026", "9:00 am", 999, "Something Else")])
    ev = E.parse_fred_calendar(html, "nfp")
    assert [(e["id"], e["at"]) for e in ev] == [("nfp:2026-11-06", "2026-11-06T13:30:00Z")]


def test_kinds_and_importance() -> None:
    assert E.KINDS["cpi"][1] == E.KINDS["nfp"][1] == E.KINDS["fomc"][1] == "high"
    assert E.KINDS["pce"][1] == E.KINDS["ppi"][1] == E.KINDS["fomc_minutes"][1] == "medium"
    assert E.FRED_RIDS == {"cpi": 10, "nfp": 50, "pce": 54, "ppi": 46}


# ═══════════════ وارسی متقاطع PCE با BEA ═══════════════

BEA = "\r\n".join([
    "BEGIN:VCALENDAR", "BEGIN:VEVENT", "DTSTART:20261029T123000Z",
    "SUMMARY:Personal Income and Outlays\\, September 2026", "END:VEVENT",
    "BEGIN:VEVENT", "DTSTART:20261029T123000Z",
    "SUMMARY:GDP (Advance Estimate)\\, 3rd Quarter 2026", "END:VEVENT", "END:VCALENDAR"])


def test_bea_pce_times() -> None:
    assert E.parse_bea_ics(BEA) == {"2026-10-29": "2026-10-29T12:30:00Z"}


def test_pce_cross_check() -> None:
    ok = [{"id": "pce:2026-10-29", "kind": "pce", "at": "2026-10-29T12:30:00Z"}]
    assert E.pce_conflicts(ok, E.parse_bea_ics(BEA)) == []
    bad = [{"id": "pce:2026-10-29", "kind": "pce", "at": "2026-10-29T13:30:00Z"}]
    c = E.pce_conflicts(bad, E.parse_bea_ics(BEA))
    assert len(c) == 1 and "13:30" in c[0] and "12:30" in c[0]
    missing = [{"id": "pce:2026-10-30", "kind": "pce", "at": "2026-10-30T12:30:00Z"}]
    assert "BEA" in E.pce_conflicts(missing, E.parse_bea_ics(BEA))[0]


# ═══════════════ آزادسازی ═══════════════

def _doc(cliff_day=5, cliff=1000.0, linear_per_day=0.0, reward_per_day=10.0, cover_days=400,
         cliff_cat="insiders") -> dict:
    """پرونده ساختگی DefiLlama: یک پله، یک خطی، یک پاداش؛ سری روزانه تجمعی."""
    t0 = _ts(NOW) - 10 * DAY
    team, vest, rew = [], [], []
    for i in range(cover_days):
        t = t0 + i * DAY
        team.append({"timestamp": t, "unlocked": cliff if t >= _ts(NOW) + cliff_day * DAY else 0.0})
        vest.append({"timestamp": t, "unlocked": linear_per_day * i})
        rew.append({"timestamp": t, "unlocked": reward_per_day * i})
    return {
        "categories": {cliff_cat: ["Team"], "privateSale": ["Investors"], "staking": ["Rewards"]},
        "documentedData": {"data": [{"label": "Team", "data": team},
                                    {"label": "Investors", "data": vest},
                                    {"label": "Rewards", "data": rew}]},
        "metadata": {"unlockEvents": [
            {"timestamp": _ts(NOW) + cliff_day * DAY,
             "cliffAllocations": [{"recipient": "Team", "category": cliff_cat, "amount": cliff}]}]},
        "gecko_id": "x"}


def _entry(locked=0.0, slug="x-proto") -> dict:
    return {"protocolSlug": slug, "gecko_id": "x", "totalLocked": locked}


def test_window_unlocks_by_category_and_cliffs() -> None:
    w = E.window_unlocks(_doc(linear_per_day=5.0), NOW, 30)
    assert w["by_cat"]["insiders"] == pytest.approx(1000.0)
    assert w["by_cat"]["privateSale"] == pytest.approx(150.0)
    assert w["by_cat"]["staking"] == pytest.approx(300.0)
    assert [(c["day"], c["tokens"]) for c in w["cliffs"]] == [("2026-10-13", 1000.0)]
    assert w["cover_end"] > NOW + timedelta(days=30)


def test_cliff_time_floored_to_hour() -> None:
    """
    زمان پله DefiLlama ثانیه‌دار و تقریبی است — 02:15:55. لرزش چندثانیه‌ای فردا نباید
    «بازنگری» بسازد و قیمت‌ها را صفر کند؛ قیمت از کندل ساعتی است، پس گرد به ساعت
    سنجش را عوض نمی‌کند — یافته اجرای واقعی ۸ اکتبر.
    """
    d = _doc(cliff=1000.0, reward_per_day=0)
    u = d["metadata"]["unlockEvents"][0]
    u["timestamp"] += 2 * 3600 + 15 * 60 + 55
    w = E.window_unlocks(d, NOW, 30)
    assert w["cliffs"][0]["at"] == "2026-10-13T11:00:00Z"
    u["timestamp"] += 3
    assert E.window_unlocks(d, NOW, 30)["cliffs"][0]["at"] == "2026-10-13T11:00:00Z"


def test_single_cliff_vetoes() -> None:
    v = E.unlock_verdict("ZRO", _entry(), _doc(cliff=1000.0, reward_per_day=0), 100_000.0, NOW)
    assert v["status"] == "veto" and v["single_max"] == pytest.approx(1.0)
    assert v["cliffs"][0]["pct"] == pytest.approx(1.0)


def test_below_single_threshold_passes() -> None:
    v = E.unlock_verdict("X", _entry(), _doc(cliff=999.0, reward_per_day=0), 100_000.0, NOW)
    assert v["status"] == "pass"


def test_linear_total_vetoes() -> None:
    """جمع خطی ۲٪ در ۳۰ روز بی پله بزرگ — مثل WLD."""
    v = E.unlock_verdict("WLD", _entry(), _doc(cliff=0.0, linear_per_day=2000 / 30,
                                              reward_per_day=0), 100_000.0, NOW)
    assert v["status"] == "veto" and v["total"] == pytest.approx(2.0)


def test_emission_does_not_veto() -> None:
    """پاداش استیکینگ ۵٪ — وتو نمی‌سازد، ولی دیده می‌شود."""
    v = E.unlock_verdict("TAO", _entry(), _doc(cliff=0.0, reward_per_day=5000 / 30),
                         100_000.0, NOW)
    assert v["status"] == "pass" and v["emission"] == pytest.approx(5.0)
    v = E.unlock_verdict("X", _entry(), _doc(cliff=5000.0, cliff_cat="farming",
                                            reward_per_day=0), 100_000.0, NOW)
    assert v["status"] == "pass"


def test_short_cover_with_big_lock_is_unknown() -> None:
    """مثل HYPE: سری تا فردا، قفل بی‌زمان‌بندی بزرگ — نه عبور، نه وتو."""
    v = E.unlock_verdict("HYPE", _entry(locked=5000.0), _doc(cliff=0.0, cover_days=12,
                                                            reward_per_day=0), 100_000.0, NOW)
    assert v["status"] == "unknown" and "5.0٪" in v["why"]


def test_short_cover_with_tiny_lock_passes() -> None:
    v = E.unlock_verdict("ETH", _entry(locked=0.0), _doc(cliff=0.0, cover_days=12,
                                                        reward_per_day=0), 100_000.0, NOW)
    assert v["status"] == "pass"


def test_short_cover_known_veto_still_vetoes() -> None:
    v = E.unlock_verdict("X", _entry(locked=50_000.0), _doc(cliff=3000.0, cliff_day=1,
                                                           cover_days=13, reward_per_day=0),
                         100_000.0, NOW)
    assert v["status"] == "veto"


def test_missing_circ_or_doc_is_unknown() -> None:
    assert E.unlock_verdict("X", _entry(), _doc(), None, NOW)["status"] == "unknown"
    assert E.unlock_verdict("X", _entry(), None, 1.0, NOW)["status"] == "unknown"
    assert E.unlock_verdict("X", None, None, None, NOW)["status"] == "unknown"


def test_bnb_fixed_no_schedule() -> None:
    v = E.unlock_verdict("BNB", None, None, None, NOW)
    assert v["status"] == "pass" and "سوزانده" in v["why"]
    assert set(E.NO_SCHEDULE) == {"BNB"}


def test_thresholds_are_decisions() -> None:
    assert (E.VETO_SINGLE_PCT, E.VETO_TOTAL_PCT, E.HORIZON_DAYS) == (1.0, 2.0, 30)
    assert E.EMISSION_CATEGORIES == {"staking", "farming"}


# ═══════════════ نگاشت نماد ═══════════════

INDEX = {"data": [
    {"protocolSlug": "layerzero", "gecko_id": "layerzero", "tokenPrice": [{"symbol": "ZRO"}]},
    {"protocolSlug": "ethereum", "gecko_id": None, "tokenPrice": [{"symbol": "ETH"}]},
    {"protocolSlug": "a1", "gecko_id": "foo", "tokenPrice": [{"symbol": "DUP"}]},
    {"protocolSlug": "a2", "gecko_id": "bar", "tokenPrice": [{"symbol": "DUP"}]},
    {"gecko_id": "noslug", "tokenPrice": [{"symbol": "NOS"}]},
]}


def test_index_mapping() -> None:
    m = E.index_by_symbol(INDEX)
    e, why = E.pick_entry("ZRO", m, {})
    assert e["protocolSlug"] == "layerzero" and why is None
    e, why = E.pick_entry("SAND", m, {})
    assert e is None and "DefiLlama" in why
    e, why = E.pick_entry("DUP", m, {})
    assert e is None and "مبهم" in why
    e, why = E.pick_entry("DUP", m, {"DUP": "bar"})
    assert e["protocolSlug"] == "a2"
    assert "NOS" not in m


# ═══════════════ نامزدهای اسکنر ═══════════════

ROT = "\n".join(["# چرخش", "", "| # | نماد | قیمت |", "|---|---|---|",
                 "| 1 | **WLD** | 0.58 |", "| 2 | **SUI** | 1.18 |", "| 3 | **STRK** | 0.05 |", ""])


def test_rotate_candidates_dir_form(tmp_path) -> None:
    (tmp_path / "rotate-2026-09-27.md").write_text(ROT.replace("WLD", "OLD"), encoding="utf-8")
    d = tmp_path / "rotate-2026-10-04.md"
    d.mkdir()
    (d / "ROTATE_20261004_1258.md").write_text(ROT, encoding="utf-8")
    syms, src = E.rotate_candidates(tmp_path)
    assert syms == ["WLD", "SUI", "STRK"] and "2026-10-04" in src


def test_rotate_candidates_file_form(tmp_path) -> None:
    (tmp_path / "rotate-2026-10-11.md").write_text(ROT, encoding="utf-8")
    assert E.rotate_candidates(tmp_path)[0] == ["WLD", "SUI", "STRK"]


def test_rotate_candidates_none(tmp_path) -> None:
    assert E.rotate_candidates(tmp_path) == ([], None)


# ═══════════════ دفتر رویداد ═══════════════

def _macro(kind="cpi", at="2026-10-14T12:30:00Z") -> dict:
    d = at[:10]
    return {"id": f"{kind}:{d}", "kind": kind, "title": E.KINDS[kind][0],
            "importance": E.KINDS[kind][1], "at": at, "source": "آزمون"}


def test_upsert_new_and_revised() -> None:
    led = {"version": 1, "events": []}
    E.upsert(led, [_macro()], NOW, macro_symbols=["BTC", "SOL"])
    e = led["events"][0]
    assert e["first_seen"] == "2026-10-08T09:00:00Z"
    assert set(e["prices"]) == {"BTC", "SOL"}
    assert e["prices"]["BTC"] == {"before": None, "h24": None, "d7": None}
    E.upsert(led, [_macro(at="2026-10-14T13:30:00Z")], NOW + timedelta(days=1), macro_symbols=["BTC"])
    e = led["events"][0]
    assert e["at"] == "2026-10-14T13:30:00Z"
    assert e["revised"] == [{"from": "2026-10-14T12:30:00Z", "seen": "2026-10-09T09:00:00Z"}]
    assert set(e["prices"]) == {"BTC", "SOL"}          # نمادهای روز نخست می‌مانند
    E.upsert(led, [_macro(at="2026-10-14T13:30:00Z")], NOW, macro_symbols=["BTC"])
    assert len(led["events"]) == 1 and len(led["events"][0]["revised"]) == 1


def test_upsert_unlock_measures_symbol_and_btc() -> None:
    led = {"version": 1, "events": []}
    u = {"id": "unlock:ZRO:2026-10-20", "kind": "unlock", "title": "آزادسازی ZRO",
         "importance": "high", "at": "2026-10-20T05:33:00Z", "symbol": "ZRO", "tokens": 1.0,
         "pct_circ": 5.92, "categories": ["insiders"], "source": "آزمون"}
    E.upsert(led, [u], NOW, macro_symbols=["BTC", "SOL"])
    assert set(led["events"][0]["prices"]) == {"ZRO", "BTC"}


class _Hist:
    """جانشین radar_history.history: کندل ۱ ساعته با بسته = ساعت باز شدن."""

    def __init__(self, fail=()):
        self.calls, self.fail = [], set(fail)

    def __call__(self, sym, tf, start, end, **k):
        self.calls.append((sym, tf, start, end))
        if sym in self.fail:
            raise RuntimeError(f"no {sym}")
        rows = [{"ts": pd.Timestamp(start), "open": 1.0, "high": 1.0, "low": 1.0,
                 "close": float(start.hour) + 100 * start.day, "volume": 1.0, "confirm": 1}]
        return SimpleNamespace(df=pd.DataFrame(rows), venue="okx", notes=[])


def test_fill_only_due_points_from_closed_candle() -> None:
    led = {"version": 1, "events": []}
    E.upsert(led, [_macro(at="2026-10-07T12:30:00Z")], NOW, macro_symbols=["BTC"])
    h = _Hist()
    notes = E.fill_prices(led, NOW, h)
    p = led["events"][0]["prices"]["BTC"]
    # پیش: کندل 11:00 تا 12:00 روز ۷ — بسته. ۲۴ ساعت: کندل 11:00 تا 12:00 روز ۸ —
    # ساعت 09:00 روز ۸ هنوز بسته نیست
    assert p["before"]["close"] == 11 + 700 and p["before"]["candle_open"] == "2026-10-07T11:00:00Z"
    assert p["h24"] is None and p["d7"] is None
    assert all(c[1] == "1h" for c in h.calls) and notes == []
    E.fill_prices(led, NOW + timedelta(hours=4), h)
    assert p["h24"]["close"] == 11 + 800 and p["d7"] is None


def test_fill_failure_recorded_never_estimated() -> None:
    led = {"version": 1, "events": []}
    E.upsert(led, [_macro(at="2026-10-07T12:30:00Z")], NOW, macro_symbols=["BTC", "ZZZ"])
    notes = E.fill_prices(led, NOW, _Hist(fail={"ZZZ"}))
    z = led["events"][0]["prices"]["ZZZ"]["before"]
    assert "close" not in z and "no ZZZ" in z["error"] and z["tried_at"] == "2026-10-08T09:00:00Z"
    assert notes and "ZZZ" in notes[0]
    # اجرای بعد دوباره امتحان می‌کند
    E.fill_prices(led, NOW + timedelta(hours=1), _Hist())
    assert "close" in led["events"][0]["prices"]["ZZZ"]["before"]


def test_future_event_not_filled() -> None:
    led = {"version": 1, "events": []}
    E.upsert(led, [_macro(at="2026-10-14T12:30:00Z")], NOW, macro_symbols=["BTC"])
    h = _Hist()
    E.fill_prices(led, NOW, h)
    assert h.calls == [] and led["events"][0]["prices"]["BTC"]["before"] is None


# ═══════════════ خروجی ═══════════════

def _verdicts():
    def v(sym, status, single=None, total=None, day=None, why=""):
        cl = [{"day": day, "at": f"{day}T05:33:00Z", "tokens": 1.0, "pct": single,
               "cats": ["insiders"]}] if day else []
        return {"symbol": sym, "status": status, "why": why, "single_max": single,
                "total": total, "emission": 0.0, "cliffs": cl, "cover_end": None}
    return {"SOL": v("SOL", "pass", total=0.0), "LINK": v("LINK", "unknown", why="پوشش تا 2026-06-19"),
            "ZRO": v("ZRO", "veto", 5.92, 5.92, "2026-10-20"),
            "STRK": v("STRK", "veto", 3.05, 3.05, "2026-10-14")}


GROUPS = {"SOL": ["سبد"], "LINK": ["سبد", "واچ‌لیست"], "ZRO": ["نامزد اسکنر"],
          "STRK": ["نامزد اسکنر"]}
MACRO = [_macro(at="2026-10-14T12:30:00Z"), _macro("fomc", "2026-10-28T18:00:00Z"),
         _macro("ppi", "2026-10-15T12:30:00Z"), _macro("nfp", "2026-11-06T13:30:00Z")]


def test_telegram_line_is_plain() -> None:
    line = E.telegram_line(MACRO, _verdicts(), GROUPS, NOW)
    assert "\n" not in line
    for ch in "*_`[":
        assert ch not in line
    assert "2026-10-14 12:30 UTC" in line            # تورم در ۱۴ روز
    assert "2026-10-28" not in line                  # فدرال‌رزرو بیرون از ۱۴ روز
    assert "2026-10-15" not in line                  # اهمیت میانه در خط نیست
    assert "ZRO" in line and "STRK" in line and "LINK" in line
    assert "۱۴" in line


def test_section_14_days() -> None:
    s = E.render_section(MACRO, _verdicts(), GROUPS, NOW, "reports/events-2026-10-08.md")
    assert s.startswith("## رویدادهای ۱۴ روز آینده")
    assert "2026-10-14 12:30" in s and "2026-10-15 12:30" in s
    assert "2026-10-28" not in s and "2026-11-06" not in s
    assert "SOL" in s and "LINK" in s and "نامعلوم" in s
    assert "ZRO" not in s.split("### آزادسازی نمادهای سبد")[1]
    assert "reports/events-2026-10-08.md" in s


def test_report_has_rules_and_all_groups() -> None:
    r = E.render_report(MACRO, _verdicts(), GROUPS, NOW, sources=[("FRED", "✅ 200")],
                        ledger={"version": 1, "events": []}, notes=["⛔ آزمون"])
    for x in ("۱٪", "۲٪", "۳۰ روز", "ف۳۱", "ZRO", "5.92", "STRK", "2026-10-28 18:00",
              "2026-11-06 13:30", "⛔ آزمون", "FRED"):
        assert x in r, x


# ═══════════════ main بی‌شبکه ═══════════════

def _protocol() -> dict:
    d = _doc(cliff=23_625_000.0, cliff_day=12, reward_per_day=0)
    return d


def _get(fail=()):
    fail = set(fail)

    def get(url, params=None, **k):
        def r(status, body):
            data = body if isinstance(body, (bytes, str)) else json.dumps(body)
            return SimpleNamespace(status_code=status, content=data.encode() if isinstance(data, str) else data,
                                   text=data if isinstance(data, str) else data.decode(),
                                   json=lambda: json.loads(data))
        for key in fail:
            if key in url:
                return r(503, "down")
        if "calendar.json" in url:
            return r(200, FED)
        if "fred.stlouisfed.org" in url:
            rid = int(url.split("rid=")[1].split("&")[0])
            kind = {v: k for k, v in E.FRED_RIDS.items()}[rid]
            day = {"cpi": "Wednesday October 14, 2026", "nfp": "Friday November 06, 2026",
                   "pce": "Thursday October 29, 2026", "ppi": "Thursday October 15, 2026"}[kind]
            return r(200, _fred([(day, "7:30 am", rid, E.FRED_NAMES[kind])]))
        if "bea.gov" in url:
            return r(200, BEA)
        if url.endswith("emissionsIndex"):
            return r(200, {"data": [{"protocolSlug": "layerzero", "gecko_id": "layerzero",
                                     "totalLocked": 0.0, "tokenPrice": [{"symbol": "ZRO"}]}]})
        if "emissions/layerzero" in url:
            return r(200, _protocol())
        if "coingecko" in url:
            return r(200, [{"id": "layerzero", "circulating_supply": 399_061_089.0}])
        raise AssertionError(url)
    return get


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "rotate-2026-10-04.md").write_text(
        ROT.replace("WLD", "ZRO").replace("SUI", "ZRO2").replace("STRK", "ZRO3"), encoding="utf-8")
    monkeypatch.setattr(E, "portfolio_symbols", lambda path: ["SOL"])
    monkeypatch.setattr(E, "watchlist", lambda: ["BTC"])
    monkeypatch.setattr(E, "PAUSE_RETRY", 0.0)
    return tmp_path


def _run(world, get, extra=()):
    argv = ["--out", "reports/events.md", "--section", "sec.md", "--line", "line.txt",
            "--ledger", "events_ledger.json", "--reports-dir", "reports", *extra]
    return E.main(argv, get=get, now=NOW, history=_Hist())


def test_main_writes_everything(world) -> None:
    rc = _run(world, _get())
    assert rc == 0
    rep = (world / "reports" / "events.md").read_text(encoding="utf-8")
    assert "ZRO" in rep and "وتو" in rep and "2026-10-28 18:00" in rep
    assert (world / "sec.md").read_text(encoding="utf-8").startswith("## رویدادهای ۱۴ روز آینده")
    assert "ZRO" in (world / "line.txt").read_text(encoding="utf-8")
    led = json.loads((world / "events_ledger.json").read_text(encoding="utf-8"))
    ids = {e["id"] for e in led["events"]}
    assert {"fomc:2026-10-28", "cpi:2026-10-14", "pce:2026-10-29"} <= ids
    assert "unlock:ZRO:2026-10-20" in ids


def test_main_source_failure_is_loud_and_keeps_ledger(world) -> None:
    assert _run(world, _get()) == 0
    rc = _run(world, _get(fail={"calendar.json"}))
    assert rc == 2
    rep = (world / "reports" / "events.md").read_text(encoding="utf-8")
    assert "federalreserve.gov" in rep and "نیامد" in rep
    # رویداد فدرال‌رزرو از دفتر، با برچسب واکشی پیشین
    assert "2026-10-28 18:00" in rep and "از دفتر" in rep
    line = (world / "line.txt").read_text(encoding="utf-8")
    assert "خطا" in line or "نیامد" in line


def test_main_unlock_source_failure_is_unknown(world) -> None:
    rc = _run(world, _get(fail={"emissionsIndex"}))
    assert rc == 2
    rep = (world / "reports" / "events.md").read_text(encoding="utf-8")
    assert "نامعلوم" in rep and "DefiLlama" in rep


def test_main_pce_conflict_is_loud(world, monkeypatch) -> None:
    bad = BEA.replace("20261029T123000Z", "20261029T133000Z")
    get = _get()

    def g(url, **k):
        if "bea.gov" in url:
            return SimpleNamespace(status_code=200, content=bad.encode(), text=bad,
                                   json=lambda: None)
        return get(url, **k)
    assert _run(world, g) == 2
    assert "BEA" in (world / "reports" / "events.md").read_text(encoding="utf-8")


# ═══════════════ پاسخ JSON با BOM ═══════════════

def test_json_with_bom() -> None:
    """
    calendar.json فدرال‌رزرو با BOM آغاز می‌شود و r.json() آن را نمی‌خواند — یافته
    وارسی فقط‌خواندنی پیش از ایستگاه ۲، ۸ اکتبر.
    """
    body = "﻿" + json.dumps(FED)

    def get(url, **k):
        def bad():
            raise ValueError("Unexpected UTF-8 BOM")
        return SimpleNamespace(status_code=200, content=body.encode("utf-8"), text=body,
                               json=bad)
    doc, err = E._json(get, E.FED_CALENDAR, "fed")
    assert err is None and doc == FED


# ═══════════════ یک نماد — برای radar_fetch3، ک۸۷ ═══════════════

def test_symbol_unlock_one_symbol(monkeypatch) -> None:
    monkeypatch.setattr(E, "_cg_ids", lambda: {})
    v = E.symbol_unlock("ZRO", get=_get(), now=NOW)
    assert v["status"] == "veto" and v["cliffs"][0]["day"] == "2026-10-20"
    v = E.symbol_unlock("SAND", get=_get(), now=NOW)
    assert v["status"] == "unknown" and "DefiLlama" in v["why"]


def test_symbol_unlock_index_down(monkeypatch) -> None:
    monkeypatch.setattr(E, "_cg_ids", lambda: {})
    monkeypatch.setattr(E, "PAUSE_RETRY", 0.0)
    v = E.symbol_unlock("ZRO", get=_get(fail={"emissionsIndex"}), now=NOW)
    assert v["status"] == "unknown" and "شاخص" in v["why"]


# ═══════════════ گردش‌کار روزانه ═══════════════

DAILY = ROOT / ".github" / "workflows" / "radar-daily.yml"
STEP = "تقویم رویداد و آزادسازی"


def _step(name: str) -> str:
    text = DAILY.read_text(encoding="utf-8")
    start = text.index(f"- name: {name}\n")
    nxt = text.find("\n      - name:", start + 1)
    return text[start:nxt if nxt != -1 else len(text)]


def test_daily_events_step_is_loud() -> None:
    text = DAILY.read_text(encoding="utf-8")
    i = text.index(f"- name: {STEP}\n")
    assert text.index("- name: سطوح ساختاری سبد\n") < i < text.index("- name: ساخت خلاصه امروز\n")
    s = _step(STEP)
    assert "python radar_events.py" in s and 'reports/events-$D.md' in s
    assert "|| true" not in s and "::error::" in s and 'reports/events-error-$D.md' in s


def test_summary_has_line_and_marked_section() -> None:
    s = _step("ساخت خلاصه امروز")
    assert "events_line" in s and "events_section" in s
    assert "<!-- رویداد-آغاز -->" in s and "<!-- رویداد-پایان -->" in s
    # خط ساده پیش از تازگی داده‌ها، تا در ۳۵۰۰ نویسه نخست تلگرام باشد
    assert s.index("events_line") < s.index("staleness.md\n            echo")


def test_telegram_drops_section_keeps_line() -> None:
    s = _step("اعلان تلگرام")
    assert "رویداد-آغاز" in s and "رویداد-پایان" in s and "sed" in s


def test_ledger_committed_without_swallow() -> None:
    s = _step("کامیت گزارش‌ها")
    loop = [l for l in s.splitlines() if l.strip().startswith("for f in")]
    assert loop and "events_ledger.json" in loop[0]
