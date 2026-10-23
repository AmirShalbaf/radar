"""
کلید پیام نقض ابطال فقط پس از ارسال موفق — بازبینی عمیق ۲۳ اکتبر ۲۰۲۶.

پیش از این check_positions کلید wk_<نماد>_<بسته> را پیش از ارسال می‌گذاشت. اگر
تلگرام پیام خروج را نمی‌رساند، کلید ثبت شده بود و هیچ اجرایی دوباره نمی‌فرستاد؛
فقط پیام هفتگی، اگر خودش می‌رسید، ردیف نقض را داشت. یافته از «کم» به «مهم» رفت —
تصمیم کاربر، ۲۳ اکتبر.

قرارداد — مثل پیام هفتگی:
- کلید هفته و وضعیت سهم خروج — breach_<نماد> — فقط پس از رسید موفق ثبت می‌شوند.
- ارسال ناموفق: یک سطر صریح در خروجی، که به reports/WATCH.md می‌رود، کد خروج ۴
  و ::error:: گام نبض؛ اجرای بعد دوباره می‌فرستد.
- ارسال ناموفق سهم خروج جزئی را جابه‌جا نمی‌کند: اجرای بعد هنوز «نخستین بسته»
  است، نه «دومین»؛ پیام هفتگی همان اجرا هم همان سهم را می‌گوید.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_telegram as TG
import radar_watch as W

UTC = timezone.utc
ROOT = Path(__file__).resolve().parent.parent
MONDAY = datetime(2026, 10, 26, 5, 0, tzinfo=UTC)
CLOSE = "2026-10-26T00:00:00+00:00"
WK = f"wk_ETH_{CLOSE}"


def _watch(fraction=1.0) -> dict:
    return {"version": 2, "updated": "2026-10-17T15:40:00+00:00", "exit_fraction": fraction,
            "positions": [{"symbol": "ETH", "invalidation": 2380.56,
                           "invalidation_since": "2026-09-25T21:34:47+00:00"}],
            "items": []}


def _h() -> dict:
    return {"version": 2, "updated": "2026-10-17T20:42:00+00:00", "source": "آزمون",
            "frozen": {"date": "2026-09-25", "members": {"ETH": 0.148257}, "cash": []},
            "cash": [], "ledger": [],
            "positions": [{"symbol": "ETH", "book": "position", "status": "open",
                           "invalidation": 2380.56,
                           "invalidation_since": "2026-09-25T21:34:47+00:00",
                           "lots": [{"qty": 0.148257, "account": "LBank", "entry": None}]}]}


@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(W, "stale_warning", lambda p: None)
    monkeypatch.setattr(W, "ticker", lambda s: None)
    sent: list[str] = []
    fail: list[str] = []          # پیشوند پیام‌هایی که این اجرا نمی‌رسند

    def fake_send(text):
        sent.append(text)
        ok = not any(text.startswith(p) for p in fail)
        return TG.Sent(ok, "کد 200" if ok else "کد 502: Bad Gateway")
    monkeypatch.setattr(W.TG, "send", fake_send)

    def go(close=2300.0, now=MONDAY, state=None, fraction=1.0, closed_at=CLOSE):
        wk = {"close": close, "closed_at": closed_at, "venue": "okx",
              "week_open": (datetime.fromisoformat(closed_at) - timedelta(days=7)).isoformat()}
        monkeypatch.setattr(W.P, "weekly_close", lambda s, now=None, get=None: (wk, []))
        st = {} if state is None else state
        W.SEND_FAILURES.clear()
        W.DIGEST_ERRORS.clear()
        W.run_once(_watch(fraction), st, quiet=True, h=_h(), now=now, regime_path=None)
        return st, json.loads((tmp_path / W.STATE_FILE).read_text(encoding="utf-8"))
    go.sent, go.fail = sent, fail
    return go


def _breach(sent) -> list[str]:
    return [m for m in sent if m.startswith("⛔ ابطال هفتگی ETH")]


def test_successful_send_sets_week_key(run) -> None:
    state, saved = run()
    assert _breach(run.sent) and saved[WK] is True
    run.sent.clear()
    run(now=MONDAY + timedelta(hours=4), state=state)
    assert not _breach(run.sent)                                   # یک بار در هفته


def test_failed_send_keeps_key_unset_and_retries(run) -> None:
    run.fail.append("⛔ ابطال هفتگی")
    state, saved = run()
    assert _breach(run.sent) and WK not in saved and W.SEND_FAILURES
    run.fail.clear()
    run.sent.clear()
    state, saved = run(now=MONDAY + timedelta(hours=4), state=state)
    assert len(_breach(run.sent)) == 1 and saved[WK] is True       # اجرای بعد دوباره فرستاد


def test_failed_send_is_loud_in_watch_report(run, capsys) -> None:
    run.fail.append("⛔ ابطال هفتگی")
    run()
    out = capsys.readouterr().out
    assert "پیام ابطال ETH فرستاده نشد" in out and "اجرای بعد دوباره" in out


def test_failed_partial_send_stays_first_close(run) -> None:
    """ارسال ناموفق نیمه اول نباید اجرای بعد را «دومین بسته» و خروج کامل کند."""
    run.fail.append("⛔ ابطال هفتگی")
    state, saved = run(fraction=0.5)
    assert "breach_ETH" not in saved
    run.fail.clear()
    run.sent.clear()
    state, saved = run(fraction=0.5, now=MONDAY + timedelta(hours=4), state=state)
    m = _breach(run.sent)[0]
    assert "فروش سهم 0.5" in m and "دومین" not in m
    assert saved["breach_ETH"] == CLOSE


def test_digest_tells_same_fraction_when_breach_send_failed(run) -> None:
    run.fail.append("⛔ ابطال هفتگی")
    run(fraction=0.5)
    digest = [m for m in run.sent if m.startswith("📊 بسته هفتگی سبد")][0]
    assert "سهم 0.5" in digest and "کل 0.148257" not in digest


def test_exit_code_4_when_breach_send_fails(run) -> None:
    """کد خروج ۴ از همان SEND_FAILURES — main آن را برمی‌گرداند، tests/test_telegram_send."""
    run.fail.append("⛔ ابطال هفتگی")
    run()
    assert W._run_rc() == W.RC_SEND_FAILED


def test_pulse_step_marks_nonzero_exit_as_error() -> None:
    """گام نبض با هر کد جز صفر ::error:: می‌دهد و کد را در WATCH.md می‌نویسد."""
    wf = (ROOT / ".github" / "workflows" / "radar-pulse.yml").read_text(encoding="utf-8")
    assert 'echo "::error::پایشگر خطا داد — کد $rc' in wf
    assert 'echo "⛔ پایشگر با خطا تمام شد — کد $rc"' in wf
