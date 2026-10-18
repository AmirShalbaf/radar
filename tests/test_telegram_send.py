"""
تابع ارسال تلگرام با رسید — نشست ۱۱، مرحله ۱.

پیش از این notify در radar_watch.py پاسخ تلگرام را نمی‌خواند: کد 400 یا
"ok": false بی‌صدا می‌ماند و فقط استثنای شبکه چاپ می‌شد.

قرارداد:
- ارسال موفق فقط یعنی کد 200 و "ok": true در پاسخ.
- مخزن و لاگ گردش‌کار عمومی‌اند: توکن هرگز چاپ نمی‌شود. فقط کد وضعیت،
  description تلگرام و نوع استثنا.
- ارسال ناموفق بلند است: یک سطر خطا، و کد خروج ۴ پایشگر.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_telegram as TG
import radar_watch as W

FAKE_TOKEN = "123456:AAFakeTokenForTestsOnlyDoNotUse"
FAKE_CHAT = "999999"


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"ok": True}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _env(monkeypatch, tok=FAKE_TOKEN, chat=FAKE_CHAT):
    for name, v in (("TELEGRAM_BOT_TOKEN", tok), ("TELEGRAM_CHAT_ID", chat)):
        if v is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, v)


def _post(monkeypatch, resp=None, exc=None):
    calls = []

    def fake(url, data=None, timeout=None):
        calls.append({"url": url, "data": data})
        if exc is not None:
            raise exc
        return resp
    monkeypatch.setattr(TG.requests, "post", fake)
    return calls


# ─────────────────────── send ───────────────────────

def test_send_ok_needs_200_and_ok_true(monkeypatch) -> None:
    _env(monkeypatch)
    calls = _post(monkeypatch, _Resp(200, {"ok": True}))
    res = TG.send("سلام")
    assert res.ok is True
    assert calls[0]["data"] == {"chat_id": FAKE_CHAT, "text": "سلام"}


def test_send_200_but_ok_false_fails(monkeypatch) -> None:
    _env(monkeypatch)
    _post(monkeypatch, _Resp(200, {"ok": False, "description": "chat not found"}))
    res = TG.send("x")
    assert res.ok is False
    assert "200" in res.detail and "chat not found" in res.detail


def test_send_ok_must_be_true_not_truthy(monkeypatch) -> None:
    _env(monkeypatch)
    _post(monkeypatch, _Resp(200, {"ok": "yes"}))
    assert TG.send("x").ok is False


def test_send_400_reports_code_and_description(monkeypatch) -> None:
    _env(monkeypatch)
    _post(monkeypatch, _Resp(400, {"ok": False,
                                   "description": "Bad Request: message is too long"}))
    res = TG.send("x")
    assert res.ok is False
    assert "400" in res.detail and "message is too long" in res.detail
    assert FAKE_TOKEN not in res.detail


def test_send_description_never_carries_token(monkeypatch) -> None:
    _env(monkeypatch)
    _post(monkeypatch, _Resp(401, {"ok": False, "description": f"bad bot{FAKE_TOKEN}"}))
    res = TG.send("x")
    assert res.ok is False and FAKE_TOKEN not in res.detail and "401" in res.detail


def test_send_non_json_reply_fails(monkeypatch) -> None:
    _env(monkeypatch)
    _post(monkeypatch, _Resp(502, ValueError("not json")))
    res = TG.send("x")
    assert res.ok is False and "502" in res.detail


def test_send_network_error_type_only(monkeypatch) -> None:
    _env(monkeypatch)
    _post(monkeypatch, exc=TimeoutError(f"url /bot{FAKE_TOKEN}/sendMessage timed out"))
    res = TG.send("x")
    assert res.ok is False
    assert "TimeoutError" in res.detail and FAKE_TOKEN not in res.detail


def test_send_without_keys_is_none_and_never_posts(monkeypatch) -> None:
    _env(monkeypatch, tok=None, chat=None)
    calls = _post(monkeypatch, _Resp())
    res = TG.send("x")
    assert res.ok is None and not calls
    assert TG.missing() == ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]


def test_empty_key_counts_as_missing(monkeypatch) -> None:
    _env(monkeypatch, tok="", chat=FAKE_CHAT)
    calls = _post(monkeypatch, _Resp())
    assert TG.send("x").ok is None and not calls
    assert TG.missing() == ["TELEGRAM_BOT_TOKEN"]


# ─────────────────────── notify در پایشگر ───────────────────────

def test_notify_failure_is_loud(monkeypatch, capsys) -> None:
    _env(monkeypatch)
    W.SEND_FAILURES.clear()
    _post(monkeypatch, _Resp(400, {"ok": False, "description": "Bad Request: chat not found"}))
    res = W.notify("⛔ ابطال هفتگی ETH", quiet=True)
    out = capsys.readouterr().out
    assert res.ok is False
    assert "ناموفق" in out and "400" in out and "chat not found" in out
    assert FAKE_TOKEN not in out
    assert W.SEND_FAILURES == [res.detail]


def test_notify_success_is_quiet(monkeypatch, capsys) -> None:
    _env(monkeypatch)
    W.SEND_FAILURES.clear()
    _post(monkeypatch, _Resp())
    assert W.notify("پیام", quiet=True).ok is True
    assert "ناموفق" not in capsys.readouterr().out
    assert W.SEND_FAILURES == []


def test_notify_without_keys_is_not_a_failure(monkeypatch, capsys) -> None:
    _env(monkeypatch, tok=None, chat=None)
    W.SEND_FAILURES.clear()
    assert W.notify("پیام", quiet=True).ok is None
    assert W.SEND_FAILURES == [] and "ناموفق" not in capsys.readouterr().out


def _stale_watch(tmp_path) -> None:
    # updated کهنه یعنی هشدار کهنگی — یک notify واقعی در اجرای --once
    (tmp_path / "watch.json").write_text(
        json.dumps({"updated": "2026-01-01", "items": []}), encoding="utf-8")


def test_main_exit_code_4_when_send_fails(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    _stale_watch(tmp_path)
    _env(monkeypatch)
    _post(monkeypatch, _Resp(400, {"ok": False, "description": "Bad Request"}))
    assert W.main(["--once", "--watch", "watch.json"]) == 4
    assert FAKE_TOKEN not in capsys.readouterr().out
    # وضعیت با وجود شکست ارسال ثبت می‌شود
    assert (tmp_path / W.STATE_FILE).exists()


def test_main_exit_code_0_when_send_ok(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _stale_watch(tmp_path)
    _env(monkeypatch)
    _post(monkeypatch, _Resp())
    assert W.main(["--once", "--watch", "watch.json"]) == 0


def test_main_resets_failures_between_runs(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _stale_watch(tmp_path)
    _env(monkeypatch)
    _post(monkeypatch, _Resp(400, {"ok": False}))
    assert W.main(["--once", "--watch", "watch.json"]) == 4
    (tmp_path / W.STATE_FILE).unlink()
    _post(monkeypatch, _Resp())
    assert W.main(["--once", "--watch", "watch.json"]) == 0


def test_ping_uses_same_sender(monkeypatch, capsys) -> None:
    _env(monkeypatch)
    _post(monkeypatch, _Resp(200, {"ok": False, "description": "chat not found"}))
    assert W.ping_telegram() is False
    out = capsys.readouterr().out
    assert "chat not found" in out and FAKE_TOKEN not in out


def test_watch_has_no_direct_telegram_post() -> None:
    """تنها نقطه ارسال radar_telegram است — نشانی رابط در پایشگر تکرار نشود."""
    src = (Path(__file__).resolve().parent.parent / "radar_watch.py").read_text(encoding="utf-8")
    assert "api.telegram.org" not in src
