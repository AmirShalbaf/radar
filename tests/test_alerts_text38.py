"""
لایه هشدار سه‌سطحی — متن ۳۸، تصمیم کاربر ۳ و ۴ نوامبر ۲۰۲۶، ک۱۲۹.

- سه سطح: 🔴 اقدام با صدا، 🟠 نمودار را ببین، 🔵 بدان و بیاموز بی‌صدا.
- قالب «چه کنم، چرا، بعدش» با دکمه پیوندی؛ نشانه راست‌به‌چپ سر هر سطر.
- ساعت سکوت شب ۲۳:۰۰ تا ۷:۳۰ تهران: قرمز بی‌صدا و تکرار صبح با صدا، مگر انجام شده باشد.
- سقف روزانه نارنجی با صدا؛ بیشتر از آن بی‌صدا، نه حذف.
- مقدار متن ساده هر پیام همان پیشین است — آزمون‌های قدیمی پایشگر دست نخوردند.
- یک تعریف فاصله در پایشگر: افت لازم از قیمت — radar_brief.drop_pct.
بی شبکه.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import radar_alert as AL
import radar_telegram as TG
import radar_watch as W

UTC = timezone.utc
RLM = "\u200f"
DAY = datetime(2026, 11, 5, 8, 0, tzinfo=UTC)          # ۱۱:۳۰ تهران
NIGHT = datetime(2026, 11, 4, 21, 0, tzinfo=UTC)       # ۰۰:۳۰ تهران
ENV = {"GITHUB_REPOSITORY": "AmirShalbaf/radar", "RADAR_DESK_URL": "https://claude.ai/x"}


def _red(**kw):
    base = dict(title="ابطال هفتگی ETH", do="کل 0.148 ETH را بفروش",
                why="بسته 2300 زیر سطح 2380.56", nxt="رسید را ثبت کن",
                cmd="radar_positions.py exit --symbol ETH --price <قیمت اجرا>", symbol="ETH")
    base.update(kw)
    return AL.Alert("⛔ متن قدیمی پیام", "red", **base)


# ── شکل ──

def test_alert_keeps_old_plain_text_and_validates_level():
    a = _red()
    assert str(a) == "⛔ متن قدیمی پیام" and a.startswith("⛔") and a.level == "red"
    with pytest.raises(ValueError):
        AL.Alert("x", "green")
    b = AL.Alert(None, "blue", title="درس", do="هیچ", why="چون", nxt="بعد")
    assert str(b) == "🔵 بدان و بیاموز — درس\nچه کنم: هیچ\nچرا: چون\nبعدش: بعد"


def test_render_what_why_next_escaped_rtl_and_code():
    a = AL.prepare(_red(), {}, DAY, env=ENV)
    lines = a.html.split("\n")
    assert lines[0] == RLM + "🔴 <b>اقدام — ابطال هفتگی ETH</b>"
    assert lines[1].startswith(RLM + "<b>چه کنم:</b>")
    assert lines[2].startswith(RLM + "<b>چرا:</b>") and lines[3].startswith(RLM + "<b>بعدش:</b>")
    assert lines[4] == RLM + "<code>radar_positions.py exit --symbol ETH --price &lt;قیمت اجرا&gt;</code>"
    assert all(l.startswith(RLM) for l in lines)
    assert "<قیمت" not in a.html


def test_generic_alert_keeps_body_lines():
    a = AL.prepare(AL.Alert("⚠️ SOL — قیمت در دسترس نیست\nسطر دوم", "blue"), {}, DAY, env={})
    assert a.html.split("\n") == [RLM + "🔵 <b>بدان و بیاموز</b>", RLM + "⚠️ SOL — قیمت در دسترس نیست",
                                  RLM + "سطر دوم"]


def test_buttons_chart_desk_and_report():
    rows = AL.buttons_for(_red(), ENV)
    assert rows[0] == [("📈 نمودار ETH", "https://www.tradingview.com/chart/?symbol=OKX:ETHUSDT")]
    assert ("📋 میز تحلیلگر", "https://claude.ai/x") in rows[1]
    assert rows[1][-1][1] == "https://github.com/AmirShalbaf/radar/blob/main/reports/LATEST.md"
    assert AL.buttons_for(AL.Alert("x", "blue"), {"RADAR_DESK_URL": "http://bad"}) == []


# ── صدا، شب، سقف ──

@pytest.mark.parametrize("t,quiet", [((22, 59), False), ((23, 0), True), ((3, 30), True),
                                     ((7, 29), True), ((7, 30), False), ((12, 0), False)])
def test_quiet_hours_tehran(t, quiet):
    tehran = datetime(2026, 11, 5, t[0], t[1], tzinfo=timezone(timedelta(hours=3, minutes=30)))
    assert AL.is_quiet(tehran) is quiet


def test_levels_sound_by_day():
    assert AL.prepare(_red(), {}, DAY, env={}).silent is False
    assert AL.prepare(AL.Alert("x", "orange"), {}, DAY, env={}).silent is False
    assert AL.prepare(AL.Alert("x", "blue"), {}, DAY, env={}).silent is True


def test_red_at_night_silent_queued_and_repeated_at_0730():
    st: dict = {}
    a = AL.prepare(_red(check={"kind": "position_qty", "symbol": "ETH"}), st, NIGHT, env={})
    assert a.silent and AL.NOTE_NIGHT_RED in a.html
    AL.delivered(a, st, NIGHT)
    q = st[AL.BOX]["repeat"]
    assert len(q) == 1 and q[0]["due"] == "2026-11-05T04:00:00+00:00"    # ۷:۳۰ تهران
    assert AL.due_repeats(st, datetime(2026, 11, 5, 3, 59, tzinfo=UTC)) == []
    morning = datetime(2026, 11, 5, 4, 41, tzinfo=UTC)
    rep = AL.due_repeats(st, morning)
    assert len(rep) == 1 and str(rep[0]) == "⛔ متن قدیمی پیام" and rep[0].repeat_id
    r = AL.prepare(rep[0], st, morning, env={})
    assert r.silent is False and AL.NOTE_REPEAT in r.html and AL.NOTE_NIGHT_RED not in r.html
    AL.delivered(r, st, morning)
    assert st[AL.BOX]["repeat"] == []


def test_repeat_dropped_when_done_or_stale():
    st: dict = {}
    a = AL.prepare(_red(), st, NIGHT, env={})
    AL.delivered(a, st, NIGHT)
    assert AL.due_repeats(st, datetime(2026, 11, 5, 5, 0, tzinfo=UTC), lambda r: False) == []
    assert st[AL.BOX]["repeat"] == []
    AL.delivered(AL.prepare(_red(), st, NIGHT, env={}), st, NIGHT)
    assert AL.due_repeats(st, datetime(2026, 11, 5, 16, 1, tzinfo=UTC)) == []   # بیش از ۱۲ ساعت


def test_failed_send_queues_nothing_and_counts_nothing():
    st: dict = {}
    AL.prepare(_red(), st, NIGHT, env={})                  # prepare حالت را نمی‌نویسد
    assert st == {}


def test_orange_daily_sound_cap_then_silent_not_dropped():
    st: dict = {}
    for i in range(AL.ORANGE_SOUND_CAP):
        a = AL.prepare(AL.Alert(f"o{i}", "orange"), st, DAY, env={})
        assert a.silent is False
        AL.delivered(a, st, DAY)
    over = AL.prepare(AL.Alert("o-extra", "orange"), st, DAY, env={})
    assert over.silent is True and AL.NOTE_CAP in over.html
    AL.delivered(over, st, DAY)
    assert st[AL.BOX]["orange"]["n"] == AL.ORANGE_SOUND_CAP          # بی‌صدا شمرده نمی‌شود
    tomorrow = DAY + timedelta(days=1)
    assert AL.prepare(AL.Alert("o", "orange"), st, tomorrow, env={}).silent is False


def test_orange_at_night_silent_no_repeat():
    st: dict = {}
    a = AL.prepare(AL.Alert("o", "orange"), st, NIGHT, env={})
    assert a.silent and AL.NOTE_NIGHT in a.html
    AL.delivered(a, st, NIGHT)
    assert not st[AL.BOX].get("repeat")


# ── ارسال ──

class _Resp:
    def __init__(self, code=200, ok=True, desc=""):
        self.status_code, self._js = code, {"ok": ok, "description": desc}

    def json(self):
        return self._js


def test_send_rich_alert_html_silent_buttons(monkeypatch):
    monkeypatch.setenv(TG.TOKEN_ENV, "tok")
    monkeypatch.setenv(TG.CHAT_ENV, "chat")
    calls = []
    monkeypatch.setattr(TG.requests, "post", lambda url, data=None, timeout=None, files=None:
                        calls.append((url, data)) or _Resp())
    a = AL.prepare(_red(), {}, NIGHT, env=ENV)
    assert TG.send(a).ok
    url, data = calls[0]
    assert url.endswith("/sendMessage") and data["parse_mode"] == "HTML"
    assert data["text"] == a.html and data["disable_notification"] == "true"
    assert "tradingview.com" in data["reply_markup"]


def test_send_rich_falls_back_to_plain_with_rtl(monkeypatch):
    monkeypatch.setenv(TG.TOKEN_ENV, "tok")
    monkeypatch.setenv(TG.CHAT_ENV, "chat")
    calls = []

    def post(url, data=None, timeout=None, files=None):
        calls.append(data)
        return _Resp(400, False, "can't parse entities") if "parse_mode" in data else _Resp()
    monkeypatch.setattr(TG.requests, "post", post)
    res = TG.send(AL.prepare(_red(), {}, DAY, env={}))
    assert res.ok and calls[1]["text"] == RLM + "⛔ متن قدیمی پیام" and "parse_mode" not in calls[1]


def test_plain_string_send_unchanged(monkeypatch):
    monkeypatch.setenv(TG.TOKEN_ENV, "tok")
    monkeypatch.setenv(TG.CHAT_ENV, "chat")
    calls = []
    monkeypatch.setattr(TG.requests, "post", lambda url, data=None, timeout=None: calls.append(data) or _Resp())
    TG.send("سلام")
    assert calls[0] == {"chat_id": "chat", "text": "سلام"}


# ── پایشگر ──

MONDAY_NIGHT = datetime(2026, 10, 26, 0, 41, tzinfo=UTC)     # ۰۴:۱۱ تهران
CLOSE = "2026-10-26T00:00:00+00:00"


def _watch() -> dict:
    return {"version": 2, "updated": "2026-10-17T15:40:00+00:00", "exit_fraction": 1.0,
            "positions": [{"symbol": "ETH", "invalidation": 2380.56,
                           "invalidation_since": "2026-09-25T21:34:47+00:00"}], "items": []}


def _h(qty=0.148257, status="open") -> dict:
    return {"version": 2, "updated": "2026-10-17T20:42:00+00:00", "source": "آزمون",
            "frozen": {"date": "2026-09-25", "members": {"ETH": 0.148257}, "cash": []},
            "cash": [], "ledger": [],
            "positions": [{"symbol": "ETH", "book": "position", "status": status,
                           "invalidation": 2380.56,
                           "invalidation_since": "2026-09-25T21:34:47+00:00",
                           "lots": [{"qty": qty, "account": "LBank", "entry": None}]}]}


@pytest.fixture
def live(tmp_path, monkeypatch):
    """پایشگر با مسیر واقعی notify و فرستنده ساختگی — هشدار با html و صدایش."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(W, "stale_warning", lambda p: None)
    monkeypatch.setattr(W, "ticker", lambda s: None)
    wk = {"close": 2300.0, "closed_at": CLOSE, "venue": "okx", "week_open": "2026-10-19T00:00:00+00:00"}
    monkeypatch.setattr(W.P, "weekly_close", lambda s, now=None, get=None: (wk, []))
    sent = []
    monkeypatch.setattr(W.TG, "send", lambda m: sent.append(m) or TG.Sent(True, "کد 200"))
    W.SEND_FAILURES.clear()
    W.DIGEST_ERRORS.clear()
    return sent


def test_watcher_breach_at_night_is_red_silent_then_morning_repeat(live):
    st: dict = {}
    W.run_once(_watch(), st, quiet=True, h=_h(), now=MONDAY_NIGHT, regime_path=None)
    br = [m for m in live if m.startswith("⛔ ابطال هفتگی ETH")]
    assert br and br[0].level == "red" and br[0].silent and "<b>چه کنم:</b>" in br[0].html
    assert "کل باقی‌مانده" in br[0].html and "&lt;قیمت اجرا&gt;" in br[0].html
    dig = [m for m in live if m.startswith("📊")]
    assert dig and dig[0].level == "blue" and dig[0].silent
    assert len(st[AL.BOX]["repeat"]) == 1
    live.clear()
    W.run_once(_watch(), st, quiet=True, h=_h(), now=MONDAY_NIGHT + timedelta(hours=4),
               regime_path=None)
    rep = [m for m in live if m.startswith("⛔ ابطال هفتگی ETH")]
    assert len(rep) == 1 and rep[0].silent is False and AL.NOTE_REPEAT in rep[0].html
    assert st[AL.BOX]["repeat"] == []


def test_watcher_morning_repeat_skipped_when_sold(live):
    st: dict = {}
    W.run_once(_watch(), st, quiet=True, h=_h(), now=MONDAY_NIGHT, regime_path=None)
    live.clear()
    W.run_once(_watch(), st, quiet=True, h=_h(qty=0.00005), now=MONDAY_NIGHT + timedelta(hours=4),
               regime_path=None)
    assert not [m for m in live if m.startswith("⛔ ابطال هفتگی ETH")]
    assert st[AL.BOX]["repeat"] == []


def test_still_needed_rules():
    w = {"items": [{"symbol": "OP"}], "reserve_plan": None}
    assert W.still_needed({"check": {"kind": "item", "symbol": "OP"}}, w, _h()) is True
    assert W.still_needed({"check": {"kind": "item", "symbol": "NIGHT"}}, w, _h()) is False
    c = {"check": {"kind": "position_qty", "symbol": "ETH", "qty": 0.148257, "qty_after": 0.0}}
    assert W.still_needed(c, w, _h()) is True
    assert W.still_needed(c, w, _h(qty=0.001)) is False
    assert W.still_needed(c, w, _h(status="closed")) is False
    assert W.still_needed({"check": None}, w, None) is True


def test_one_distance_definition_in_watcher():
    src = (ROOT / "radar_watch.py").read_text(encoding="utf-8")
    assert "/ close * 100" not in src and "100 * (px / lvl - 1)" not in src
    assert src.count("drop_pct(") >= 4


def test_watcher_levels_are_set_everywhere():
    """هر پیام پایشگر سطح دارد — هیچ msgs.append رشته خام نیست."""
    import re
    src = (ROOT / "radar_watch.py").read_text(encoding="utf-8")
    raw = (re.findall(r"msgs\.append\(f[\"']", src) + re.findall(r"fired\.append\(\s*f[\"']", src)
           + re.findall(r"_once\(state, [^\n]+, msgs,\s+f?[\"']", src)
           + re.findall(r"notify\(f[\"']", src))
    assert raw == []
