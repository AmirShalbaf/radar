"""
سه رفع پیام صبح — متن ۳۸، یافته‌های نخستین پیام واقعی ۴ نوامبر ۲۰۲۶.

الف) تلگرام سطری را که با نماد لاتین آغاز شود چپ‌به‌راست می‌چیند — سطرهای ماشه به هم
     می‌ریخت. هر سطر زیرنویس و پیام نشانه راست‌به‌چپ RLM می‌گیرد؛ در نقل‌قول، پس از تگ.
ب) «ستاپ واجد شرایط: ۱ کارت اسکنر» مثل مجوز خوانده می‌شد. حالا «نامزد آزمون‌نشده» با نماد
   و جهت، و «مجوز ورود نیست؛ اول تحلیلگر صبح».
پ) نبض کهنه یعنی تغییر بیت‌کوین تهی بود. حالا از بسته روزانه دیروز تا قیمت اسکن، با
   برچسب «از بسته روزانه» — نه «۲۴ ساعت».
بی شبکه.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import brief_fixture as F
import radar_brief as BR
import radar_brief_render as R
import radar_telegram as TG

UTC = timezone.utc
RLM = "\u200f"
NOW = datetime(2026, 11, 4, 10, 5, tzinfo=UTC)


def _fetch_with_yesterday(close_y: float = 75000.0):
    """کندل روزانه تا امروز؛ بسته دیروز ۳ نوامبر = close_y."""
    def fetch(sym):
        out = []
        for i in range(60, -1, -1):
            t = datetime(2026, 11, 4, tzinfo=UTC) - timedelta(days=i)
            v = close_y if t.day == 3 and t.month == 11 else F.PRICES.get(sym, 100.0)
            out.append([t.isoformat(), v])
        return out
    return fetch


def _pump(tmp=".", cards=(("NIGHT", "long", "B"), ("DGAI", "short", "C"))):
    secs = {"long": [], "short": [], "afterpump": [], "late": [], "nolevel": [], "veto": []}
    for sym, side, grade in cards:
        secs[side].append({"symbol": sym, "side": side, "setup": {"name": "الف‌۱"},
                           "card": {"ok": True, "grade": grade}})
    secs["long"].append({"symbol": "BAD", "side": "long", "setup": {}, "card": {"ok": False}})
    doc = {"generated": NOW.isoformat(), "cards_n": len(cards), "sections": secs}
    Path(tmp, "pump.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def _doc(snapshot_age_h=None, fetch=None, cards=True):
    F.write_all(".", NOW)
    if cards:
        _pump()
    else:
        Path("pump.json").write_text(json.dumps({"cards_n": 0, "sections": {}}), encoding="utf-8")
    snap = {"generated_utc": (NOW - timedelta(hours=snapshot_age_h or 30)).strftime("%Y-%m-%d %H:%M UTC"),
            "symbols": {"BTC": {"price": 76500.0, "chg24_pct": -1.25}}}
    Path("snapshot.json").write_text(json.dumps(snap), encoding="utf-8")
    src = BR.Sources(".", NOW, files={"lessons": str(ROOT / "references" / "lessons.json")})
    return BR.collect(src, fetch=fetch)


def _lines_ok(html: str) -> list[str]:
    """سطرهایی که نشانه راست‌به‌چپ ندارند — باید تهی باشد."""
    bad = []
    for line in html.split("\n"):
        body = line.split(">", 1)[1] if line.startswith("<blockquote") else line
        if not body.startswith(RLM):
            bad.append(line)
    return bad


# ── الف — نشانه راست‌به‌چپ ──

def test_rtl_every_line_once_and_after_quote_tag():
    s = "⛔ <b>SOL</b> ابطال\n<blockquote expandable>• یک\nدو</blockquote>\n"
    out = TG.rtl(s)
    assert out.split("\n")[0] == RLM + "⛔ <b>SOL</b> ابطال"
    assert out.split("\n")[1] == "<blockquote expandable>" + RLM + "• یک"
    assert TG.rtl(out) == out                         # دوباره نمی‌گیرد
    assert not _lines_ok(out)


def test_caption_and_message_lines_start_rtl():
    doc = _doc(fetch=F.fake_fetch())
    for html in (R.caption(doc), R.message(doc), R.message(doc, with_head=True)):
        assert not _lines_ok(html), _lines_ok(html)[:3]
        assert RLM + RLM not in html                  # سطر سر کپشن در پیام دوباره نگرفت
    trig = [l for l in R.message(doc).split("\n") if "<b>" in l and "مانده" in l]
    assert trig and all(RLM in l[:30] for l in trig)


def test_plain_fallback_keeps_rtl_mark():
    doc = _doc(fetch=F.fake_fetch())
    assert all(l.startswith(RLM) or not l for l in R.plain(doc).split("\n"))


# ── ب — نامزد آزمون‌نشده، نه مجوز ──

def test_scanner_cards_are_untested_candidates_with_symbol_and_side():
    doc = _doc(fetch=F.fake_fetch())
    v = doc["verdict"]
    assert v["setups"] == ["NIGHT لانگ — کارت اسکنر پامپ", "DGAI شورت — کارت اسکنر پامپ"]
    assert [c["symbol"] for c in v["candidates"]] == ["NIGHT", "DGAI"]
    assert v["candidates"][1]["side_label"] == "شورت" and v["candidates"][0]["grade"] == "B"
    t = doc["sections"]["trade"]
    assert [c["symbol"] for c in t["pump_card_list"]] == ["NIGHT", "DGAI"]   # کارت ناسالم نه
    html = R.card_today(doc)
    assert "ستاپ واجد شرایط" not in html and "کارت اسکنر" in html
    assert "نامزد آزمون‌نشده" in html and "مجوز ورود نیست" in html and "اول تحلیلگر" in html
    assert "NIGHT" in html and "لانگ" in html and "DGAI" in html and "شورت" in html
    msg = R.message(doc)
    assert "کارت آماده" not in msg and "کارت آزمون‌نشده" in msg and "NIGHT لانگ" in msg
    assert "ستاپ آماده" not in R.card_book(doc)


def test_no_candidate_day_says_none_is_fine():
    doc = _doc(fetch=F.fake_fetch(), cards=False)
    assert doc["verdict"]["setups"] == [] and doc["verdict"]["candidates"] == []
    assert "«امروز هیچ» هم تصمیم درست است" in R.card_today(doc)


def test_document_still_valid_with_new_keys():
    assert BR.validate(_doc(fetch=F.fake_fetch())) == []


# ── پ — تغییر بیت‌کوین از بسته روزانه ──

def test_btc_change_from_daily_close_when_pulse_stale():
    doc = _doc(snapshot_age_h=30, fetch=_fetch_with_yesterday(75000.0))
    b = doc["sections"]["market"]["btc"]
    assert b["chg24_basis"] == "daily_close" and b["prev_daily_close"] == 75000.0
    assert b["chg24"] == pytest.approx(100 * (b["price"] / 75000.0 - 1))
    html = R.card_today(doc)
    assert "</span> از بسته روزانه ۳:۳۰" in html and "</span> در ۲۴ ساعت" not in html


def test_btc_change_from_fresh_pulse_keeps_24h_label():
    doc = _doc(snapshot_age_h=2, fetch=_fetch_with_yesterday())
    b = doc["sections"]["market"]["btc"]
    assert b["chg24"] == -1.25 and b["chg24_basis"] == "pulse_24h"
    assert "</span> در ۲۴ ساعت" in R.card_today(doc)


def test_btc_change_missing_candle_gives_reason_not_crash():
    doc = _doc(snapshot_age_h=30, fetch=F.fake_fetch())       # کندل ساختگی تا ۲ نوامبر
    b = doc["sections"]["market"]["btc"]
    assert b["chg24"] is None and "دیروز" in b["chg24_why"]
    assert doc["sections"]["market"]["ok"]


def test_prev_daily_close_utc_day():
    pts = [["2026-11-02T00:00:00+00:00", 1.0], ["2026-11-03T00:00:00+00:00", 2.0],
           ["2026-11-04T00:00:00+00:00", 3.0]]
    assert BR.prev_daily_close(pts, datetime(2026, 11, 4, 0, 1, tzinfo=UTC)) == 2.0
    assert BR.prev_daily_close(pts, datetime(2026, 11, 3, 23, 59, tzinfo=UTC)) == 1.0
