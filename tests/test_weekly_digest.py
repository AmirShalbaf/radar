"""
پیام بسته هفتگی — نشست ۱۱، مرحله ۲، تصمیم کاربر ۱۸ اکتبر ۲۰۲۶.

پیش از این پایشگر فقط هنگام نقض ابطال یا مهلت نقشه پیام می‌داد. هفته‌ای که همه
بالای سطح بستند هیچ پیامی نداشت، و نقشه ۸ اکتبر در مهلت اجرا نشد — رویداد ۱۰۱.

قرارداد:
- پیام‌های جدای نقض و مهلت می‌مانند؛ پیام هفتگی کنارشان، پس از آن‌ها.
- فقط آخرین هفته بسته‌شده، و فقط اگر بسته‌اش کمتر از ۷۲ ساعت پیش است؛ قدیمی‌تر
  یعنی کلید بی ارسال، با دلیل.
- کلید فقط پس از ارسال موفق؛ شکست یعنی تلاش در نبض بعد. دیرتر از ۱۲ ساعت یعنی «دیر».
- نقض ابطال بر پله نقشه مقدم است.
- رادار سفارش‌های ال‌بانک را نمی‌بیند — اقدام مهلت شرطی است.
- حکم مهلت از باند با هیسترزیس، trade_band، نه باند خام.
- بسته غایب یعنی «داده ندارم»، نه «بالای سطح». منبع و زمان بسته در پیام.

داده ساختگی همان عددهای مخزن ۱۸ اکتبر است: هفت نماد سبد، ETH 0.148257 با سطح
2380.5606، و نقشه ذخیره ۱۷ اکتبر با پله باز ETH 0.074 در 2490.
"""
import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_telegram as TG
import radar_watch as W

UTC = timezone.utc
CLOSE = datetime(2026, 10, 19, tzinfo=UTC)          # بسته هفته ۱۲ تا ۱۸ اکتبر
MONDAY = CLOSE + timedelta(hours=5, minutes=50)     # نخستین نبض معمول پس از بسته
SINCE = "2026-09-25T21:34:47+00:00"

# نماد، مقدار، سطح ابطال — holdings.json و watch.json امروز
POS = [("SOL", 5.63105369, 96.7108), ("ETH", 0.148257, 2380.5606),
       ("AAVE", 1.04895, 106.892), ("LINK", 11.09889, 10.3366),
       ("SUI", 81.6183, 0.6843), ("ONDO", 115.43866, 0.3478),
       ("TAO", 0.153892, 202.5065)]
CLOSES = {"SOL": 186.2, "ETH": 2500.0, "AAVE": 210.0, "LINK": 17.5, "SUI": 2.6,
          "ONDO": 0.72, "TAO": 330.0}

PLAN = {
    "title": "نقشه ذخیره ۱۷ اکتبر — پس از برداشت تتر",
    "created": "2026-10-17T15:32:00+00:00", "deadline": "2026-10-19T00:00:00+00:00",
    "account": "LBank",
    "on_deadline": {"cancel_if_band_at_least": "سازنده", "otherwise": "market"},
    "steps": [{"symbol": "BNB", "qty": 0.327, "price": None},
              {"symbol": "ETH", "qty": 0.074, "price": 2490}],
}
BNB_FILL = {"at": "2026-10-17T15:33:55+00:00", "action": "trim", "symbol": "BNB",
            "delta": -0.327, "price": 718.07, "reason": "reserve", "account": "LBank"}

DEADLINE_MARKET = ("اگر سفارش 2490 پر نشده: لغو کن و 0.074 را در بازار بفروش. "
                   "اگر پر شده: فقط رسیدش را ثبت کن.")


def _watch(plan=PLAN) -> dict:
    w = {"version": 2, "updated": "2026-10-17T15:40:00+00:00", "items": [],
         "exit_fraction": 1.0,
         "positions": [{"symbol": s, "invalidation": lvl, "invalidation_since": SINCE,
                        "warnings": []} for s, _, lvl in POS]}
    if plan is not None:
        w["reserve_plan"] = copy.deepcopy(plan)
    return w


def _h() -> dict:
    return {"version": 2, "updated": "2026-10-17T15:40:00+00:00", "source": "آزمون",
            "frozen": {"date": "2026-09-25",
                       "members": {**{s: q for s, q, _ in POS}, "BNB": 0.327}},
            "cash": [], "ledger": [dict(BNB_FILL)],
            "positions": [{"symbol": s, "book": "position", "status": "open",
                           "invalidation": lvl, "invalidation_since": SINCE,
                           "lots": [{"qty": q, "account": "LBank", "entry": None}]}
                          for s, q, lvl in POS]}


def _regime(trade="محتاط", raw=None, gen="2026-10-18T11:05:00+00:00") -> dict:
    return {"generated_at": gen, "band": {"name": raw or trade},
            "trade_band": {"name": trade}}


def _weekly(closes=None, closed_at=CLOSE, missing=(), stale=(), venue="okx"):
    closes = dict(CLOSES, **(closes or {}))
    calls = []

    def f(sym):
        calls.append(sym)
        if sym in missing:
            return None, ["okx: خطای شبکه (ConnectionError)", "gate 7d: پاسخ نداد"]
        at = closed_at - timedelta(days=7) if sym in stale else closed_at
        return {"close": closes[sym], "week_open": (at - timedelta(days=7)).isoformat(),
                "closed_at": at.isoformat(), "venue": venue}, []
    f.calls = calls
    return f


def _digest(now=MONDAY, state=None, regime=None, plan=PLAN, **kw):
    state = {} if state is None else state
    key, text = W.weekly_digest(_watch(plan), _h(), state, now, weekly=_weekly(**kw),
                                regime=regime if regime is not None else _regime())
    return key, text, state


# ═══════════════ پیام و کلید ═══════════════

def test_monday_message_lists_every_symbol_with_source_and_close_time() -> None:
    key, text, _ = _digest()
    assert key == "weekly_digest_2026-10-19T00:00:00+00:00"
    assert text and text.startswith("📊 بسته هفتگی سبد")
    assert "2026-10-19 00:00 UTC" in text
    for s, _, _ in POS:
        assert f"— {s}: بسته" in text, s
    assert text.count("اوکی‌اکس") == len(POS)
    assert "✅ بالای سطح — ETH: بسته 2500، ابطال 2380.5606، فاصله 4.8٪، اوکی‌اکس" in text
    assert "دیر" not in text


def test_gate_venue_is_named() -> None:
    _, text, _ = _digest(venue="gate")
    assert text.count("گیت") == len(POS) and "اوکی‌اکس" not in text


def test_late_label_after_twelve_hours() -> None:
    assert "دیر" not in _digest(now=CLOSE + timedelta(hours=11, minutes=59))[1]
    _, text, _ = _digest(now=CLOSE + timedelta(hours=27))
    assert "⏱ دیر: 27 ساعت پس از بسته." in text


def test_only_within_72_hours() -> None:
    assert _digest(now=CLOSE + timedelta(hours=71, minutes=59))[1]
    key, text, state = _digest(now=CLOSE + timedelta(hours=72))
    assert text is None
    assert "۷۲" in state[key]["skipped"] and "فرستاده نشد" in state[key]["skipped"]


def test_sunday_push_never_sends_oct12_week() -> None:
    """کد یکشنبه ۱۸ اکتبر پوش می‌شود؛ نخستین نبض نباید پیام هفته ۱۲ اکتبر را بفرستد."""
    wk = _weekly()
    state: dict = {}
    key, text = W.weekly_digest(_watch(), _h(), state, datetime(2026, 10, 18, 5, tzinfo=UTC),
                                weekly=wk, regime=_regime())
    assert key == "weekly_digest_2026-10-12T00:00:00+00:00"
    assert text is None and state[key]["skipped"]
    assert wk.calls == []                     # بی واکشی


def test_existing_key_means_silent() -> None:
    state = {"weekly_digest_2026-10-19T00:00:00+00:00": {"sent": "x"}}
    assert _digest(state=state)[1] is None


def test_nothing_to_report_sets_no_key() -> None:
    state: dict = {}
    key, text = W.weekly_digest({"version": 2, "items": []}, _h(), state, MONDAY,
                                weekly=_weekly())
    assert text is None and key not in state


# ═══════════════ داده ندارم ═══════════════

def test_missing_close_is_no_data_not_above() -> None:
    _, text, _ = _digest(missing=("TAO",))
    assert "⚠️ داده ندارم — TAO: بسته هفتگی در دسترس نیست" in text
    assert "خطای شبکه" in text
    assert "✅ بالای سطح — TAO" not in text
    assert "همه بالای سطح" not in text
    assert "1 نماد داده ندارد" in text


def test_old_week_close_is_no_data() -> None:
    _, text, _ = _digest(stale=("SUI",))
    assert "⚠️ داده ندارم — SUI: بسته هفته 2026-10-19 00:00 UTC هنوز نیامده" in text
    assert "2026-10-12 00:00 UTC" in text and "✅ بالای سطح — SUI" not in text


def test_all_above_says_so() -> None:
    _, text, _ = _digest(now=datetime(2026, 10, 26, 5, 50, tzinfo=UTC),
                         closed_at=datetime(2026, 10, 26, tzinfo=UTC),
                         plan=dict(PLAN, deadline="2026-11-02T00:00:00+00:00"))
    assert "هیچ — همه بالای سطح ابطال." in text


def test_level_set_after_close_is_not_judged() -> None:
    w, h = _watch(), _h()
    for x in (w["positions"][0], h["positions"][0]):
        x["invalidation_since"] = "2026-10-19T03:00:00+00:00"
    _, text = W.weekly_digest(w, h, {}, MONDAY, weekly=_weekly(), regime=_regime())
    assert "ℹ️ داوری نمی‌شود — SOL" in text and "همه بالای سطح" not in text


# ═══════════════ نقض ابطال مقدم بر پله ═══════════════

def test_eth_breach_overrides_open_plan_step() -> None:
    _, text, _ = _digest(closes={"ETH": 2375.0})
    assert "⛔ زیر سطح — ETH: بسته 2375، ابطال 2380.5606" in text
    assert "اول سفارش 2490 را لغو کن، کل 0.148257 را بفروش — در بازار." in text
    assert "اگر سفارش 2490 پر نشده" not in text
    assert "پله ETH" not in text


def test_breach_without_plan_step_sells_all() -> None:
    _, text, _ = _digest(closes={"SOL": 90.0})
    assert "⛔ ابطال SOL: کل 5.63105369 را بفروش — در بازار." in text
    # پله باز ETH همچنان اقدام مهلت خودش را دارد
    assert DEADLINE_MARKET in text


def test_partial_exit_fraction_follows_breach_state() -> None:
    w = _watch()
    w["exit_fraction"] = 0.5
    state = {"breach_SOL": CLOSE.isoformat()}          # بخش ۱: نخستین بسته زیر سطح
    _, text = W.weekly_digest(w, _h(), state, MONDAY, weekly=_weekly(closes={"SOL": 90.0}),
                              regime=_regime())
    assert "سهم 0.5، یعنی 2.815526845 را بفروش" in text
    assert "باقی فقط اگر بسته هفتگی بعد هم زیر سطح بود" in text


# ═══════════════ مهلت نقشه ═══════════════

def test_deadline_action_is_conditional() -> None:
    _, text, _ = _digest()
    assert DEADLINE_MARKET in text
    assert "⏰ مهلت نقشه ذخیره ۱۷ اکتبر — پس از برداشت تتر گذشت (2026-10-19 00:00 UTC)" in text
    assert "BNB" not in text                            # پله بازار BNB از دفتر کل پر است


def test_deadline_uses_hysteresis_band_not_raw() -> None:
    _, text, _ = _digest(regime=_regime(trade="محتاط", raw="سازنده"))
    assert DEADLINE_MARKET in text and "باند با هیسترزیس محتاط" in text
    _, text, _ = _digest(regime=_regime(trade="سازنده", raw="محتاط"))
    assert "🟢 شرط لغو" in text
    assert "اگر سفارش 2490 پر نشده: لغو کن. اگر پر شده: فقط رسیدش را ثبت کن." in text
    assert "در بازار بفروش" not in text


def test_deadline_unknown_band_asks() -> None:
    _, text = W.weekly_digest(_watch(), _h(), {}, MONDAY, weekly=_weekly(), regime=None)
    assert "نامعلوم" in text and "تصمیم با تو" in text
    assert DEADLINE_MARKET not in text


def test_before_deadline_plan_is_info_only() -> None:
    _, text, _ = _digest(plan=dict(PLAN, deadline="2026-10-26T00:00:00+00:00"))
    assert "🗓 مهلت نقشه ذخیره ۱۷ اکتبر — پس از برداشت تتر: 2026-10-26 00:00 UTC" in text
    assert "پله ETH: سفارش 0.074 در 2490" in text
    assert "بفروش" not in text and "هیچ — همه بالای سطح ابطال." in text


def test_unfilled_market_step_is_conditional() -> None:
    h = _h()
    h["ledger"] = []
    _, text = W.weekly_digest(_watch(), h, {}, MONDAY, weekly=_weekly(), regime=_regime())
    assert ("پله BNB: اگر 0.327 هنوز فروخته نشده: در بازار بفروش. اگر فروخته شده: "
            "فقط رسیدش را ثبت کن.") in text


# ═══════════════ اجرا در run_once ═══════════════

@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "regime.json").write_text(json.dumps(_regime()), encoding="utf-8")
    monkeypatch.setattr(W, "stale_warning", lambda p: None)
    monkeypatch.setattr(W, "ticker", lambda s: None)
    sent: list[str] = []
    replies: list[bool] = []

    def fake_send(text):
        sent.append(text)
        ok = replies.pop(0) if replies else True
        return TG.Sent(ok, "کد 200" if ok else "کد 400: Bad Request")
    monkeypatch.setattr(W.TG, "send", fake_send)

    def go(now=MONDAY, closes=None, state=None):
        wk = _weekly(closes=closes)
        monkeypatch.setattr(W.P, "weekly_close", lambda s, now=None, get=None: wk(s))
        st = {} if state is None else state
        W.SEND_FAILURES.clear()
        W.DIGEST_ERRORS.clear()
        W.run_once(_watch(), st, quiet=True, h=_h(), now=now, regime_path="regime.json")
        return st, json.loads((tmp_path / W.STATE_FILE).read_text(encoding="utf-8"))
    go.sent, go.replies = sent, replies
    return go


KEY = "weekly_digest_2026-10-19T00:00:00+00:00"


def test_run_sends_digest_after_breach_and_deadline(run) -> None:
    state, saved = run(closes={"ETH": 2375.0})
    breach = [i for i, m in enumerate(run.sent) if m.startswith("⛔ ابطال هفتگی ETH")]
    digest = [i for i, m in enumerate(run.sent) if m.startswith("📊 بسته هفتگی سبد")]
    assert breach and len(digest) == 1 and breach[0] < digest[0]
    assert saved[KEY]["sent"]
    # پیام‌های جدای نقض و مهلت دست‌نخورده
    assert any("خروج کامل باقی‌مانده: 0.148257 ETH" in m for m in run.sent)


def test_second_pulse_same_week_is_silent(run) -> None:
    state, _ = run()
    run.sent.clear()
    run(now=MONDAY + timedelta(hours=4), state=state)
    assert not any(m.startswith("📊") for m in run.sent)


def test_send_failure_retries_next_pulse(run) -> None:
    run.replies.extend([False] * 20)
    state, saved = run()
    assert KEY not in saved and W.SEND_FAILURES
    run.replies.clear()
    run.sent.clear()
    state, saved = run(now=MONDAY + timedelta(hours=4), state=state)
    assert [m for m in run.sent if m.startswith("📊")] and saved[KEY]["sent"]


def test_digest_crash_is_loud_after_other_messages(run, monkeypatch) -> None:
    def boom(*a, **k):
        raise RuntimeError("آزمون خرابی")
    monkeypatch.setattr(W, "weekly_digest", boom)
    state, saved = run(closes={"ETH": 2375.0})
    i_breach = next(i for i, m in enumerate(run.sent) if m.startswith("⛔ ابطال هفتگی ETH"))
    i_err = next(i for i, m in enumerate(run.sent) if "پیام بسته هفتگی ساخته نشد" in m)
    assert i_breach < i_err and "RuntimeError" in run.sent[i_err]
    assert any(m.startswith("⏰ مهلت") for m in run.sent[:i_err])
    # بقیه وضعیت ثبت شد
    assert saved.get(f"wk_ETH_{CLOSE.isoformat()}") is True
    assert W.DIGEST_ERRORS and KEY not in saved


def test_main_exit_code_5_on_digest_crash(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "watch.json").write_text(json.dumps({"updated": "2026-10-17", "items": []}),
                                         encoding="utf-8")
    monkeypatch.setattr(W, "run_once", lambda *a, **k: W.DIGEST_ERRORS.append("x"))
    assert W.main(["--once", "--watch", "watch.json"]) == 5


def test_no_holdings_means_no_digest(run, monkeypatch, tmp_path) -> None:
    W.run_once({"version": 2, "items": [], "positions": []}, {}, quiet=True, h=None,
               now=MONDAY, regime_path=None)
    assert not any(m.startswith("📊") for m in run.sent)
