"""
متن ۳۹ — تصمیم کاربر ۹ و ۱۰ نوامبر ۲۰۲۶، ساخته به دست Claude در محیط ابری، ۱۲ نوامبر.

الف) جداکننده زیرنویس آلبوم: «·» کنار رقم فارسی مثل صفر خوانده می‌شد.
ب) «مانده» در سطر ماشه با علامت گیج‌کننده بود: «+۱٫۰٪ مانده» برای ارزی که همین حالا زیر
   سطح ابطال است. حالا جای قیمت نسبت به سطح بی‌علامت گفته می‌شود — بالا یا زیر — و اگر شرط
   ماشه همین حالا برقرار است، صریح.
پ) هشدار کهنگی سطوح قالب «چه کنم، چرا، بعدش» می‌گیرد؛ متن ساده‌اش ثابت می‌ماند — قاعده ۹.
ت) واکنش ۳۰ دقیقه‌ای رویداد از watch_state.json به events_ledger.json می‌رود؛ نشان «فرستاده شد»
   همان‌جا می‌ماند. تنها نویسنده دفتر رویداد radar_events.py است.
ث) خوراک اطلاعیه‌های فدرال‌رزرو با قاعده ساده واژه — ک۸۹، بخش اول.
بی شبکه.
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import radar_alert as AL
import radar_brief_render as R
import radar_events as E
import radar_watch as W

UTC = timezone.utc


# ═══════════════ الف — جداکننده زیرنویس ═══════════════

def _cap_doc():
    return {"day": "۱۲ نوامبر", "verdict": {"headline": "امروز کاری نیست"}}


def test_caption_has_no_middle_dot_next_to_persian_digit() -> None:
    cap = R.caption(_cap_doc())
    assert not re.search(r"·\s*[۰-۹]|[۰-۹]\s*·", cap), cap
    assert "امروز" in cap and "سبد و ماشه‌ها" in cap and "نمودار و درس" in cap


# ═══════════════ ب — جای قیمت نسبت به سطح ═══════════════

def _trig(symbol, kind, level, price, judge="weekly"):
    return {"symbol": symbol, "kind": kind, "level": level, "judge": judge,
            "label": {"invalidation": "ابطال — فروش", "reentry": "ورود دوباره مجاز"}.get(kind, "هشدار"),
            "price": price, "move_pct": 100.0 * (level / price - 1.0)}


def _tdoc(*items):
    return {"sections": {"triggers": {"ok": True, "items": list(items), "total": len(items)}}}


def test_trigger_below_invalidation_says_below_and_condition_met() -> None:
    line = R._trigger_lines(_tdoc(_trig("LINK", "invalidation", 10.3366, 10.237)))[0]
    assert "مانده" not in line
    assert "زیر سطح" in line and "۱٫۰٪" in line
    assert "شرط همین حالا برقرار" in line and "بسته هفتگی" in line


def test_trigger_above_invalidation_says_drop_needed_without_alarm() -> None:
    line = R._trigger_lines(_tdoc(_trig("ONDO", "invalidation", 0.3478, 0.3654)))[0]
    assert "مانده" not in line
    assert "بالای سطح" in line and "۴٫۸٪" in line
    assert "شرط همین حالا برقرار" not in line


def test_trigger_reentry_below_level_is_not_met_and_above_is_met() -> None:
    below = R._trigger_lines(_tdoc(_trig("SOL", "reentry", 96.7108, 82.32)))[0]
    assert "زیر سطح" in below and "شرط همین حالا برقرار" not in below
    above = R._trigger_lines(_tdoc(_trig("SOL", "reentry", 96.7108, 99.0)))[0]
    assert "بالای سطح" in above and "شرط همین حالا برقرار" in above


def test_trigger_gap_uses_drop_from_price_definition() -> None:
    """فاصله تا سطح فقط تعریف radar_brief.drop_pct است: درصد از قیمت — قاعده ۹."""
    import radar_brief as BR
    x = _trig("ONDO", "invalidation", 0.3478, 0.3654)
    side, pct, met = R.trigger_gap(x)
    assert side == "above" and not met
    assert abs(pct - BR.drop_pct(0.3654, 0.3478)) < 1e-9


def test_trigger_image_has_no_signed_remaining() -> None:
    doc = _tdoc(_trig("LINK", "invalidation", 10.3366, 10.237),
                _trig("ONDO", "invalidation", 0.3478, 0.3654))
    doc["sections"]["positions"] = {"ok": False, "why": "آزمون"}
    doc["sections"]["trade"] = {"ok": False, "why": "آزمون"}
    doc["sections"]["scorecard"] = {"ok": False, "why": "آزمون"}
    html = R.card_book(doc)
    assert "چقدر مانده" not in html
    assert "زیر سطح" in html and "بالای سطح" in html


# ═══════════════ پ — هشدار کهنگی با قالب تازه ═══════════════

def _old_watch(tmp_path, days=20):
    p = tmp_path / "watch.json"
    upd = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    p.write_text(json.dumps({"version": 2, "updated": upd, "symbols": {}}), encoding="utf-8")
    return str(p)


def test_stale_alert_has_do_why_next_and_same_plain_text(tmp_path) -> None:
    p = _old_watch(tmp_path)
    a = W.stale_alert(p)
    assert isinstance(a, AL.Alert) and a.level == "orange"
    assert str(a) == W.stale_warning(p)                 # قاعده ۹: متن ساده ثابت
    assert a.do and a.why and a.nxt
    html = AL.render(a)
    for k in ("چه کنم", "چرا", "بعدش"):
        assert k in html
    assert "۲۰" in a.why                                # سن واقعی


def test_stale_alert_none_when_fresh(tmp_path) -> None:
    assert W.stale_alert(_old_watch(tmp_path, days=1)) is None


# ═══════════════ ت — واکنش رویداد در دفتر رویداد ═══════════════

def _ledger_ev(eid, kind, at):
    return {"id": eid, "kind": kind, "title": kind, "importance": "high", "at": at,
            "source": "آزمون", "prices": {"BTC": {"before": None, "h24": None, "d7": None}}}


STATE = {"event_result_cpi-2026-10": {
    "at": "2026-11-10T13:30:00+00:00", "kind": "cpi", "seen": "2026-11-10T14:18:18+00:00",
    "expected": "قدیم", "actual": None, "p0": 74404.8, "p30": 73748.6, "chg30_pct": -0.882,
    "lo": 73505.0, "hi": 74749.7, "venue": "okx"},
    "stale_2026-11-10": True}

CAL = {"version": 1, "events": [{"id": "cpi-2026-10", "at": "2026-11-10T13:30:00+00:00",
                                 "name": "تورم", "importance": "high", "expected": "انتظار ماهانه",
                                 "actual": "عدد واقعی", "lesson": "درس آزمون"}]}


def test_fill_reactions_copies_state_record_into_ledger() -> None:
    led = {"version": 1, "events": [_ledger_ev("cpi:2026-11-10", "cpi", "2026-11-10T13:30:00Z"),
                                     _ledger_ev("nfp:2026-12-04", "nfp", "2026-12-04T13:30:00Z")]}
    notes = E.fill_reactions(led, STATE, CAL)
    ev = led["events"][0]
    r = ev["reaction_30m"]
    assert r["p0"] == 74404.8 and r["chg30_pct"] == -0.882 and r["venue"] == "okx"
    assert r["calendar_id"] == "cpi-2026-10"
    assert ev["expected"] == "انتظار ماهانه" and ev["actual"] == "عدد واقعی"
    assert ev["lesson"] == "درس آزمون"
    assert "reaction_30m" not in led["events"][1]
    assert notes == []


def test_fill_reactions_is_idempotent_and_updates_calendar_fields() -> None:
    led = {"version": 1, "events": [_ledger_ev("cpi:2026-11-10", "cpi", "2026-11-10T13:30:00Z")]}
    E.fill_reactions(led, STATE, CAL)
    first = json.dumps(led, sort_keys=True)
    E.fill_reactions(led, STATE, CAL)
    assert json.dumps(led, sort_keys=True) == first
    cal2 = json.loads(json.dumps(CAL))
    cal2["events"][0]["actual"] = "اصلاح‌شده"
    E.fill_reactions(led, STATE, cal2)
    assert led["events"][0]["actual"] == "اصلاح‌شده"


def test_fill_reactions_unmatched_record_is_a_note_not_silence() -> None:
    led = {"version": 1, "events": []}
    notes = E.fill_reactions(led, STATE, CAL)
    assert notes and "cpi-2026-10" in notes[0]


def test_reaction_report_section_lists_reaction() -> None:
    led = {"version": 1, "events": [_ledger_ev("cpi:2026-11-10", "cpi", "2026-11-10T13:30:00Z")]}
    E.fill_reactions(led, STATE, CAL)
    sec = "\n".join(E.render_reactions(led, datetime(2026, 11, 12, tzinfo=UTC)))
    assert "-0.88" in sec and "عدد واقعی" in sec and "انتظار ماهانه" in sec


# ═══════════════ ث — خوراک اطلاعیه فدرال‌رزرو ═══════════════

RSS = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>Federal Reserve Board - All Press Releases</title>
<item><title>Federal Reserve issues FOMC statement</title>
<link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20261028a.htm</link>
<pubDate>Wed, 28 Oct 2026 18:00:00 GMT</pubDate><category>Monetary Policy</category></item>
<item><title>Minutes of the Federal Open Market Committee, October 27-28, 2026</title>
<link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20261118a.htm</link>
<pubDate>Wed, 18 Nov 2026 19:00:00 GMT</pubDate><category>Monetary Policy</category></item>
<item><title>Agencies issue joint statement on community bank leverage</title>
<link>https://www.federalreserve.gov/newsevents/pressreleases/bcreg20261117a.htm</link>
<pubDate>Tue, 17 Nov 2026 15:00:00 GMT</pubDate><category>Banking and Consumer Regulatory Policy</category></item>
</channel></rss>"""


def test_parse_fed_press_and_keyword_rule() -> None:
    items = E.parse_fed_press(RSS)
    assert [i["title"][:24] for i in items] == ["Federal Reserve issues F", "Minutes of the Federal O",
                                                "Agencies issue joint sta"]
    assert items[0]["at"] == "2026-10-28T18:00:00Z"
    assert [i["important"] for i in items] == [True, True, False]


def test_press_section_and_line_only_recent_important() -> None:
    items = E.parse_fed_press(RSS)
    now = datetime(2026, 11, 18, 22, 0, tzinfo=UTC)
    sec = "\n".join(E.render_press(items, now))
    assert "Minutes of the Federal Open Market Committee" in sec
    assert "Agencies issue joint statement" in sec            # ۷ روز، همه با برچسب
    assert "FOMC statement" not in sec                        # بیرون از ۷ روز
    line = E.press_line(items, now)
    assert "Minutes" in line and "Agencies" not in line
    assert E.press_line(items, datetime(2026, 11, 25, tzinfo=UTC)) == ""


def test_parse_fed_press_bad_xml_is_empty_with_error() -> None:
    items, err = E.parse_fed_press("<rss><channel><item>", with_error=True)
    assert items == [] and err


# ── main: خوراک خبر نیامد، تقویم نمی‌شکند ──

def test_main_press_down_is_note_not_failure(tmp_path, monkeypatch) -> None:
    import test_radar_events as T
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    (tmp_path / "pump.json").write_text(json.dumps(
        {"generated": E.iso(T.NOW - timedelta(hours=3)), "candidates": []}), encoding="utf-8")
    monkeypatch.setattr(E, "portfolio_symbols", lambda path: ["SOL"])
    monkeypatch.setattr(E, "watchlist", lambda: ["BTC"])
    monkeypatch.setattr(E, "PAUSE_RETRY", 0.0)
    base = T._get()

    def get(url, **k):
        if "press_all.xml" in url:
            return SimpleNamespace(status_code=503, content=b"down", text="down", json=lambda: None)
        return base(url, **k)
    rc = E.main(["--out", "reports/events.md", "--line", "line.txt", "--ledger", "events_ledger.json",
                 "--pump", "pump.json", "--state", "none.json", "--calendar", "none.json"],
                get=get, now=T.NOW, history=T._Hist())
    assert rc == 0
    rep = (tmp_path / "reports" / "events.md").read_text(encoding="utf-8")
    assert "خوراک اطلاعیه فدرال‌رزرو نیامد" in rep


def test_main_writes_reaction_and_press(tmp_path, monkeypatch) -> None:
    import test_radar_events as T
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    (tmp_path / "pump.json").write_text(json.dumps(
        {"generated": E.iso(T.NOW - timedelta(hours=3)), "candidates": []}), encoding="utf-8")
    monkeypatch.setattr(E, "portfolio_symbols", lambda path: ["SOL"])
    monkeypatch.setattr(E, "watchlist", lambda: ["BTC"])
    monkeypatch.setattr(E, "PAUSE_RETRY", 0.0)
    st = {"event_result_cpi-2026-10": dict(STATE["event_result_cpi-2026-10"],
                                           at="2026-10-14T12:30:00+00:00")}
    (tmp_path / "watch_state.json").write_text(json.dumps(st), encoding="utf-8")
    cal = {"version": 1, "events": [dict(CAL["events"][0], at="2026-10-14T12:30:00+00:00")]}
    (tmp_path / "events_calendar.json").write_text(json.dumps(cal), encoding="utf-8")
    base = T._get()

    def get(url, **k):
        if "press_all.xml" in url:
            return SimpleNamespace(status_code=200, content=RSS.encode(), text=RSS, json=lambda: None)
        return base(url, **k)
    rc = E.main(["--out", "reports/events.md", "--line", "line.txt", "--ledger", "events_ledger.json",
                 "--pump", "pump.json"], get=get, now=T.NOW, history=T._Hist())
    assert rc == 0
    led = json.loads((tmp_path / "events_ledger.json").read_text(encoding="utf-8"))
    cpi = [e for e in led["events"] if e["id"] == "cpi:2026-10-14"][0]
    assert cpi["reaction_30m"]["chg30_pct"] == -0.882


def test_main_press_with_bom_parses_bytes_not_guessed_text(tmp_path, monkeypatch) -> None:
    """نخستین اجرای واقعی ۱۲ نوامبر: خوراک با نشانه ترتیب بایت می‌آید و requests متن را لاتین-۱ حدس می‌زند.

    خطای همان روز «invalid token: line 1, column 1» بود؛ پس خوراک باید از بایت خام خوانده شود.
    """
    import test_radar_events as T
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    (tmp_path / "pump.json").write_text(json.dumps(
        {"generated": E.iso(T.NOW - timedelta(hours=3)), "candidates": []}), encoding="utf-8")
    monkeypatch.setattr(E, "portfolio_symbols", lambda path: ["SOL"])
    monkeypatch.setattr(E, "watchlist", lambda: ["BTC"])
    monkeypatch.setattr(E, "PAUSE_RETRY", 0.0)
    base = T._get()
    raw = ("﻿" + RSS).encode("utf-8")

    def get(url, **k):
        if "press_all.xml" in url:
            return SimpleNamespace(status_code=200, content=raw, text=raw.decode("latin-1"),
                                   json=lambda: None)
        return base(url, **k)
    rc = E.main(["--out", "reports/events.md", "--line", "line.txt", "--ledger", "events_ledger.json",
                 "--pump", "pump.json", "--state", "none.json", "--calendar", "none.json"],
                get=get, now=T.NOW, history=T._Hist())
    assert rc == 0
    rep = (tmp_path / "reports" / "events.md").read_text(encoding="utf-8")
    assert "خوراک اطلاعیه فدرال‌رزرو نیامد" not in rep
    assert "XML نیست" not in rep
