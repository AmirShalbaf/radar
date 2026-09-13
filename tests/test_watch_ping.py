"""
آزمون کلید --ping در radar_watch.py.

هدف: پیام آزمایشی به تلگرام بدون منتظر ماندن برای فعال‌شدن هشدار،
با گزارش روشن موفق/ناموفق، و بدون هیچ نشتی از توکن در خروجی —
نه در پیام موفقیت، نه در پیام خطا، نه در خطای شبکه.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_watch as W

FAKE_TOKEN = "123456:AAFakeTokenForTestsOnlyDoNotUse"
FAKE_CHAT = "999999"


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"ok": True}

    def json(self):
        return self._payload


def _set_env(monkeypatch, tok=FAKE_TOKEN, chat=FAKE_CHAT):
    if tok is None:
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    else:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", tok)
    if chat is None:
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    else:
        monkeypatch.setenv("TELEGRAM_CHAT_ID", chat)


# ─────────────────────── حالت موفق ───────────────────────

def test_ping_success(monkeypatch, capsys) -> None:
    _set_env(monkeypatch)
    monkeypatch.setattr(W.requests, "post", lambda *a, **k: _Resp())
    assert W.ping_telegram() is True
    out = capsys.readouterr().out
    assert "✅" in out
    assert FAKE_TOKEN not in out


def test_ping_sends_to_correct_chat(monkeypatch) -> None:
    """داده ارسالی باید chat_id درست و متن آزمایشی داشته باشد."""
    _set_env(monkeypatch)
    captured = {}

    def fake_post(url, data=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        return _Resp()

    monkeypatch.setattr(W.requests, "post", fake_post)
    assert W.ping_telegram() is True
    assert captured["data"]["chat_id"] == FAKE_CHAT
    assert FAKE_TOKEN in captured["url"]          # توکن در URL درخواست هست...
    assert len(captured["data"]["text"]) > 0


def test_ping_api_rejects_returns_false(monkeypatch, capsys) -> None:
    """تلگرام کد ۲۰۰ ولی ok:false برگرداند — باید ناموفق گزارش شود."""
    _set_env(monkeypatch)
    monkeypatch.setattr(
        W.requests, "post",
        lambda *a, **k: _Resp(payload={"ok": False, "description": "chat not found"}))
    assert W.ping_telegram() is False
    out = capsys.readouterr().out
    assert "❌" in out
    assert FAKE_TOKEN not in out


def test_ping_http_error_status_returns_false(monkeypatch, capsys) -> None:
    _set_env(monkeypatch)
    monkeypatch.setattr(
        W.requests, "post",
        lambda *a, **k: _Resp(status_code=401,
                              payload={"ok": False, "description": "Unauthorized"}))
    assert W.ping_telegram() is False
    out = capsys.readouterr().out
    assert FAKE_TOKEN not in out


# ─────────────────────── متغیر محیطی غایب ───────────────────────

def test_ping_missing_both_vars(monkeypatch, capsys) -> None:
    _set_env(monkeypatch, tok=None, chat=None)
    called = []
    monkeypatch.setattr(W.requests, "post", lambda *a, **k: called.append(1))
    assert W.ping_telegram() is False
    out = capsys.readouterr().out
    assert "TELEGRAM_BOT_TOKEN" in out
    assert "TELEGRAM_CHAT_ID" in out
    assert not called                              # هرگز درخواست نزد


def test_ping_missing_token_only(monkeypatch, capsys) -> None:
    """پیام باید فقط متغیر غایب را نام ببرد، نه هر دو."""
    _set_env(monkeypatch, tok=None, chat=FAKE_CHAT)
    assert W.ping_telegram() is False
    out = capsys.readouterr().out
    assert "TELEGRAM_BOT_TOKEN" in out
    assert "TELEGRAM_CHAT_ID" not in out


def test_ping_missing_chat_only(monkeypatch, capsys) -> None:
    _set_env(monkeypatch, tok=FAKE_TOKEN, chat=None)
    assert W.ping_telegram() is False
    out = capsys.readouterr().out
    assert "TELEGRAM_CHAT_ID" in out
    assert "TELEGRAM_BOT_TOKEN" not in out


def test_ping_empty_string_env_counts_as_missing(monkeypatch, capsys) -> None:
    """رشته تهی هم غایب حساب می‌شود، نه یک توکن معتبر."""
    _set_env(monkeypatch, tok="", chat=FAKE_CHAT)
    assert W.ping_telegram() is False
    out = capsys.readouterr().out
    assert "TELEGRAM_BOT_TOKEN" in out


# ─────────────────────── خطای شبکه ───────────────────────

def test_ping_network_error_returns_false(monkeypatch, capsys) -> None:
    _set_env(monkeypatch)

    def raise_conn_error(*a, **k):
        raise ConnectionError(f"failed for url with token {FAKE_TOKEN}")

    monkeypatch.setattr(W.requests, "post", raise_conn_error)
    assert W.ping_telegram() is False
    out = capsys.readouterr().out
    assert "❌" in out
    assert "خطای شبکه" in out


def test_ping_network_error_never_leaks_token(monkeypatch, capsys) -> None:
    """
    هسته آزمون: استثنای requests گاهی نشانی کامل درخواست (با توکن) را
    در متن خودش دارد. باید فقط نوع استثنا گزارش شود، نه متنش.
    """
    _set_env(monkeypatch)

    def raise_with_token_in_message(*a, **k):
        raise TimeoutError(
            f"HTTPSConnectionPool: url /bot{FAKE_TOKEN}/sendMessage timed out")

    monkeypatch.setattr(W.requests, "post", raise_with_token_in_message)
    assert W.ping_telegram() is False
    out = capsys.readouterr().out
    assert FAKE_TOKEN not in out
    assert "TimeoutError" in out


def test_ping_malformed_json_response(monkeypatch, capsys) -> None:
    """پاسخ غیر JSON نباید بشکند."""
    _set_env(monkeypatch)

    class _BadResp:
        status_code = 200
        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(W.requests, "post", lambda *a, **k: _BadResp())
    assert W.ping_telegram() is False
    out = capsys.readouterr().out
    assert FAKE_TOKEN not in out


# ─────────────────────── notify() هم توکن را در خطا لو نمی‌دهد ───────────────────────

def test_notify_network_error_never_leaks_token(monkeypatch, capsys) -> None:
    """همان الگو در notify() — پیام هشدار عادی هم نباید توکن را لو بدهد."""
    _set_env(monkeypatch)

    def raise_with_token_in_message(*a, **k):
        raise ConnectionError(f"url contains {FAKE_TOKEN}")

    monkeypatch.setattr(W.requests, "post", raise_with_token_in_message)
    W.notify("پیام آزمایشی", quiet=False)
    out = capsys.readouterr().out
    assert FAKE_TOKEN not in out
    assert "ConnectionError" in out
