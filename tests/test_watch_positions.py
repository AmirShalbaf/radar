"""
پایشگر دفتر موقعیت — نشست ۳، مورد ۷-ج، تصمیم‌های کاربر ۲۵ و ۲۶ سپتامبر ۲۰۲۶.

- ابطال با بسته هفتگی وقت جهانی، یک بار برای هر هفته بسته‌شده — نخستین
  اجرای پس از دوشنبه ۰۰:۰۰. سهم خروج پارامتر watch.json است (پیش‌فرض ۱.۰):
  کمتر از یک یعنی آن سهم در بسته اول، باقی فقط اگر بسته بعدی هم زیر سطح بود.
- داده هفتگی نبود: «داده ندارم»، بلند، و اجرای بعد دوباره تلاش می‌کند.
- سطح هشدار فقط پیام است، خروج نمی‌سازد.
- ورود دوباره: بسته هفتگی بالای سطح، از سهمیه دفتر کل.
- هشدار بازار BTC: بسته هفتگی زیر میانگین ساده ۵۰ هفته.
- نقشه ذخیره: پله رسیده، و مهلت — پله پرنشده یعنی پله‌ای که کاهش reserve
  دفتر کل پوشش نداده.
- ONDO برچسب «سطح ضعیف» دارد.
"""
import copy
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_watch as W

UTC = timezone.utc
MON = datetime(2026, 9, 28, 4, 40, tzinfo=UTC)        # نخستین اجرای پس از دوشنبه
WEEK1 = "2026-09-28T00:00:00+00:00"
WEEK2 = "2026-10-05T00:00:00+00:00"


def _watch(**over) -> dict:
    w = {"version": 2, "updated": "2026-09-26", "exit_fraction": 1.0,
         "positions": [{"symbol": "SOL", "invalidation": 96.71, "touches": 4,
                        "warnings": [119.53]},
                       {"symbol": "ONDO", "invalidation": 0.4457, "touches": 3,
                        "label": "سطح ضعیف", "warnings": []}],
         "market": [{"symbol": "BTC", "weekly_close_below": 78822.35,
                     "label": "میانگین ساده ۵۰ هفته"}],
         "reserve_plan": {"created": "2026-09-25T16:00:00+00:00",
                          "deadline": "2026-10-05T00:00:00+00:00", "account": "LBank",
                          "steps": [{"symbol": "SOL", "qty": 0.749, "price": None},
                                    {"symbol": "SOL", "qty": 0.749, "price": 125.5},
                                    {"symbol": "SOL", "qty": 0.749, "price": 131.5}]},
         "items": []}
    w.update(over)
    return w


def _h(ledger=None, sol=6.0, sol_status="open") -> dict:
    return {"version": 2, "updated": "2026-09-25T05:15:00+00:00",
            "frozen": {"date": "2026-09-25", "members": {"SOL": 6.0, "ONDO": 100.0}},
            "cash": [], "ledger": ledger or [],
            "positions": [
                {"symbol": "SOL", "book": "position", "status": sol_status, "invalidation": 96.71,
                 "lots": [{"qty": sol, "account": "LBank", "entry": None}] if sol else []},
                {"symbol": "ONDO", "book": "position", "status": "open", "invalidation": 0.4457,
                 "lots": [{"qty": 100.0, "account": "LBank", "entry": None}]}]}


def _wk(closes: dict, closed_at=WEEK1):
    def f(sym):
        c = closes.get(sym)
        if c is None:
            return None, ["آزمون: داده نیست"]
        return {"close": c, "closed_at": closed_at, "venue": "okx"}, []
    return f


PX = {"SOL": 122.0, "ONDO": 0.55, "BTC": 84000.0}


def _run(watch, h, state, weekly, price=None, now=MON) -> list[str]:
    return W.check_positions(watch, h, state, now, weekly=weekly,
                             price=price or (lambda s: PX.get(s)))


def _all_above():
    return _wk({"SOL": 120.0, "ONDO": 0.5, "BTC": 81000.0})


# ═══════════════ اعتبارسنجی watch.json ═══════════════

@pytest.mark.parametrize("f", [0, 1.5, "نصف", None])
def test_exit_fraction_must_be_in_range(f) -> None:
    with pytest.raises(W.WatchError):
        W.validate_watch(_watch(exit_fraction=f))


def test_default_exit_fraction_is_one() -> None:
    w = _watch()
    del w["exit_fraction"]
    W.validate_watch(w)
    assert W.exit_fraction(w) == 1.0


def test_deadline_needs_timezone() -> None:
    w = _watch()
    w["reserve_plan"]["deadline"] = "2026-10-05T00:00:00"
    with pytest.raises(W.WatchError):
        W.validate_watch(w)


def test_valid_watch_passes() -> None:
    W.validate_watch(_watch())


# ═══════════════ ابطال هفتگی ═══════════════

def test_breach_full_exit_once_per_week() -> None:
    st = {}
    msgs = _run(_watch(), _h(), st, _wk({"SOL": 95.0, "ONDO": 0.5, "BTC": 81000.0}))
    m = next(x for x in msgs if "SOL" in x and "ابطال هفتگی" in x)
    assert "خروج کامل" in m and "radar_positions.py exit" in m and "96.71" in m
    assert not [x for x in _run(_watch(), _h(), st, _wk({"SOL": 95.0, "ONDO": 0.5,
                                                          "BTC": 81000.0}))
                if "ابطال هفتگی" in x]


def test_no_breach_no_message() -> None:
    msgs = _run(_watch(), _h(), {}, _all_above())
    assert not [x for x in msgs if "ابطال" in x]


def test_half_exit_then_second_close_below() -> None:
    w, st = _watch(exit_fraction=0.5), {}
    m1 = [x for x in _run(w, _h(), st, _wk({"SOL": 95.0, "ONDO": 0.5, "BTC": 81000.0}))
          if "ابطال هفتگی" in x][0]
    assert "3" in m1 and "trim --reason invalidation" in m1 and "--level 96.71" in m1
    m2 = [x for x in _run(w, _h(sol=3.0, ledger=[{
        "at": WEEK1, "action": "trim", "symbol": "SOL", "delta": -3.0, "price": 95.0,
        "reason": "invalidation", "level": 96.71}]), st,
        _wk({"SOL": 94.0, "ONDO": 0.5, "BTC": 81000.0}, closed_at=WEEK2),
        now=MON + timedelta(days=7)) if "ابطال هفتگی" in x][0]
    assert "خروج کامل" in m2 and "دومین بسته" in m2


def test_half_exit_then_close_back_above_keeps_rest() -> None:
    w, st = _watch(exit_fraction=0.5), {}
    _run(w, _h(), st, _wk({"SOL": 95.0, "ONDO": 0.5, "BTC": 81000.0}))
    msgs = _run(w, _h(sol=3.0), st, _wk({"SOL": 99.0, "ONDO": 0.5, "BTC": 81000.0},
                                        closed_at=WEEK2), now=MON + timedelta(days=7))
    m = next(x for x in msgs if "SOL" in x and "نگه" in x)
    assert "باقی‌مانده" in m


def test_no_weekly_data_is_loud_and_retries() -> None:
    st = {}
    msgs = _run(_watch(), _h(), st, _wk({"ONDO": 0.5, "BTC": 81000.0}))
    assert any("SOL" in x and "داده ندارم" in x for x in msgs)
    again = _run(_watch(), _h(), st, _wk({"ONDO": 0.5, "BTC": 81000.0}))
    assert not any("SOL" in x and "داده ندارم" in x for x in again)     # یک بار در هفته
    later = _run(_watch(), _h(), st, _wk({"SOL": 95.0, "ONDO": 0.5, "BTC": 81000.0}))
    assert any("SOL" in x and "ابطال هفتگی" in x for x in later)         # دوباره تلاش کرد


def test_weak_level_label() -> None:
    msgs = _run(_watch(), _h(), {}, _wk({"SOL": 120.0, "ONDO": 0.40, "BTC": 81000.0}))
    m = next(x for x in msgs if "ONDO" in x and "ابطال هفتگی" in x)
    assert "سطح ضعیف" in m


def test_exited_position_not_checked_for_invalidation() -> None:
    ledger = [{"at": WEEK1, "action": "exit", "symbol": "SOL", "delta": -6.0,
               "price": 95.0, "level": 96.71, "reason": "invalidation"}]
    msgs = _run(_watch(), _h(ledger=ledger, sol=0.0, sol_status="exited"), {},
                _wk({"SOL": 90.0, "ONDO": 0.5, "BTC": 81000.0}))
    assert not [x for x in msgs if "SOL" in x and "ابطال هفتگی" in x]


# ═══════════════ ورود دوباره ═══════════════

def test_reentry_allowed_on_weekly_close_above_level() -> None:
    ledger = [{"at": WEEK1, "action": "exit", "symbol": "SOL", "delta": -6.0,
               "price": 95.0, "level": 96.71, "reason": "invalidation"}]
    msgs = _run(_watch(), _h(ledger=ledger, sol=0.0, sol_status="exited"), {},
                _wk({"SOL": 99.0, "ONDO": 0.5, "BTC": 81000.0}, closed_at=WEEK2))
    m = next(x for x in msgs if "ورود دوباره" in x)
    assert "SOL" in m and "96.71" in m and "reenter" in m


# ═══════════════ سطح هشدار ═══════════════

def test_warning_level_message_only_once_and_rearms() -> None:
    st, wk = {}, _all_above()
    msgs = _run(_watch(), _h(), st, wk, price=lambda s: {"SOL": 118.0}.get(s, PX.get(s)))
    m = next(x for x in msgs if "هشدار" in x and "119.53" in x)
    assert "فقط پیام" in m and "exit" not in m
    assert not [x for x in _run(_watch(), _h(), st, wk,
                                price=lambda s: {"SOL": 117.0}.get(s, PX.get(s)))
                if "119.53" in x]
    _run(_watch(), _h(), st, wk, price=lambda s: {"SOL": 122.0}.get(s, PX.get(s)))
    assert [x for x in _run(_watch(), _h(), st, wk,
                            price=lambda s: {"SOL": 118.0}.get(s, PX.get(s)))
            if "119.53" in x]


# ═══════════════ هشدار بازار ═══════════════

def test_btc_weekly_close_below_sma_is_market_alert_once() -> None:
    st = {}
    wk = _wk({"SOL": 120.0, "ONDO": 0.5, "BTC": 77000.0})
    m = next(x for x in _run(_watch(), _h(), st, wk) if "BTC" in x)
    assert "هشدار بازار" in m and "میانگین ساده ۵۰ هفته" in m and "78822.35" in m
    assert not [x for x in _run(_watch(), _h(), st, wk) if "BTC" in x]


# ═══════════════ نقشه ذخیره ═══════════════

def test_reserve_step_reached_message() -> None:
    msgs = _run(_watch(), _h(), {}, _all_above(),
                price=lambda s: {"SOL": 126.0}.get(s, PX.get(s)))
    assert any("پله ذخیره" in x and "125.5" in x and "0.749" in x for x in msgs)
    assert not any("پله ذخیره" in x and "131.5" in x for x in msgs)


def test_filled_steps_come_from_reserve_trims() -> None:
    ledger = [{"at": "2026-09-26T10:00:00+00:00", "action": "trim", "symbol": "SOL",
               "delta": -1.498, "price": 126.0, "reason": "reserve"}]
    assert W.unfilled_steps(_watch()["reserve_plan"], _h(ledger=ledger, sol=4.502)) == [
        {"symbol": "SOL", "qty": 0.749, "price": 131.5}]


def test_old_trims_before_plan_do_not_count() -> None:
    ledger = [{"at": "2026-09-20T10:00:00+00:00", "action": "trim", "symbol": "SOL",
               "delta": -0.749, "price": 126.0, "reason": "reserve"}]
    assert len(W.unfilled_steps(_watch()["reserve_plan"], _h(ledger=ledger, sol=5.251))) == 3


def test_deadline_alert_once_with_unfilled_steps() -> None:
    st, now = {}, datetime(2026, 10, 5, 4, 40, tzinfo=UTC)
    msgs = _run(_watch(), _h(), st, _all_above(), now=now)
    m = next(x for x in msgs if "مهلت" in x)
    assert "قیمت بازار" in m and "131.5" in m
    assert not [x for x in _run(_watch(), _h(), st, _all_above(), now=now) if "مهلت" in x]


def test_market_steps_reminder_before_deadline() -> None:
    msgs = _run(_watch(), _h(), {}, _all_above())
    assert any("پله بازار" in x and "SOL" in x for x in msgs)


# ═══════════════ هم‌خوانی با holdings.json ═══════════════

def test_invalidation_mismatch_with_holdings_is_loud() -> None:
    h = _h()
    h["positions"][0]["invalidation"] = 90.0
    msgs = _run(_watch(), h, {}, _all_above())
    assert any("ناهمخوانی" in x and "SOL" in x for x in msgs)


def test_run_once_does_not_mutate_inputs() -> None:
    w, h = _watch(), _h()
    w0, h0 = copy.deepcopy(w), copy.deepcopy(h)
    _run(w, h, {}, _wk({"SOL": 95.0, "ONDO": 0.4, "BTC": 70000.0}))
    assert w == w0 and h == h0


# ═══════════════ یکپارچه: main ═══════════════

def _write(tmp_path, watch, h) -> None:
    import json
    (tmp_path / "watch.json").write_text(json.dumps(watch, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "holdings.json").write_text(json.dumps(h, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "radar_journal.json").write_text('{"version": 1, "trades": []}',
                                                 encoding="utf-8")


def _valid_h() -> dict:
    h = _h()
    h["source"] = "آزمون"
    return h


def test_main_runs_position_checks(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, _watch(), _valid_h())
    sent: list[str] = []
    monkeypatch.setattr(W, "notify", lambda m, quiet=False: sent.append(m))
    monkeypatch.setattr(W.P, "weekly_close", lambda s, now=None, get=None: (
        {"close": {"SOL": 95.0}.get(s, 1e9), "closed_at": WEEK1, "venue": "okx"}, []))
    monkeypatch.setattr(W, "ticker", lambda s: PX.get(s))
    assert W.main(["--once", "--watch", "watch.json", "--holdings", "holdings.json"]) == 0
    assert any("SOL" in m and "ابطال هفتگی" in m for m in sent)


def test_main_invalid_watch_v2_is_loud(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, _watch(exit_fraction=2), _valid_h())
    sent: list[str] = []
    monkeypatch.setattr(W, "notify", lambda m, quiet=False: sent.append(m))
    assert W.main(["--once", "--watch", "watch.json"]) == 2
    assert any("exit_fraction" in m for m in sent)


def test_main_invalid_holdings_is_loud(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    h = _valid_h()
    h["frozen"]["members"]["SOL"] = 5.0                 # ناوردا شکسته
    _write(tmp_path, _watch(), h)
    sent: list[str] = []
    monkeypatch.setattr(W, "notify", lambda m, quiet=False: sent.append(m))
    monkeypatch.setattr(W.P, "weekly_close", lambda s, now=None, get=None: (None, ["آزمون"]))
    monkeypatch.setattr(W, "ticker", lambda s: PX.get(s))
    assert W.main(["--once", "--watch", "watch.json", "--holdings", "holdings.json"]) == 2
    assert any("holdings.json" in m and "نامعتبر" in m for m in sent)
