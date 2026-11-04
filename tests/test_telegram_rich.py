"""
ارسال قالب‌دار و تصویر تلگرام — متن ۳۷. همان قرارداد رسید: موفق فقط کد 200 و ok درست؛
توکن هرگز در متن رسید نیست؛ سقف‌ها پیش از ارسال سنجیده می‌شوند.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import radar_telegram as TG

TOK = "123456:AAFakeTokenForTestsOnlyDoNotUse"


class _Resp:
    def __init__(self, code=200, payload=None):
        self.status_code, self._p = code, payload if payload is not None else {"ok": True}

    def json(self):
        return self._p


def _setup(monkeypatch, resp=None):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOK)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    calls = []

    class _Req:
        @staticmethod
        def post(url, data=None, files=None, timeout=None):
            calls.append({"url": url, "data": data, "files": {k: v[0] for k, v in (files or {}).items()}})
            return resp or _Resp()
    monkeypatch.setattr(TG, "requests", _Req)
    return calls


def test_send_html_parse_mode_buttons_and_silent(monkeypatch):
    calls = _setup(monkeypatch)
    r = TG.send_html("<b>سلام</b>", buttons=[[("گزارش", "https://github.com/x"), ("بد", "http://x")]],
                     silent=True)
    assert r.ok and calls[0]["url"].endswith("/sendMessage")
    d = calls[0]["data"]
    assert d["parse_mode"] == "HTML" and d["disable_notification"] == "true" and d["chat_id"] == "999"
    kb = json.loads(d["reply_markup"])["inline_keyboard"]
    assert kb == [[{"text": "گزارش", "url": "https://github.com/x"}]]


def test_send_html_too_long_is_refused_before_network(monkeypatch):
    calls = _setup(monkeypatch)
    r = TG.send_html("ا" * (TG.HTML_MAX + 1))
    assert r.ok is False and calls == []


def test_single_photo_uses_send_photo(tmp_path, monkeypatch):
    calls = _setup(monkeypatch)
    p = tmp_path / "card1.png"
    p.write_bytes(b"png")
    r = TG.send_photos([str(p)], "<b>حکم</b>")
    assert r.ok and calls[0]["url"].endswith("/sendPhoto")
    assert calls[0]["files"] == {"photo": "card1.png"} and calls[0]["data"]["parse_mode"] == "HTML"


def test_album_uses_media_group_caption_on_first(tmp_path, monkeypatch):
    calls = _setup(monkeypatch)
    paths = []
    for i in range(3):
        p = tmp_path / f"card{i}.png"
        p.write_bytes(b"png")
        paths.append(str(p))
    r = TG.send_photos(paths, "زیرنویس")
    assert r.ok and calls[0]["url"].endswith("/sendMediaGroup")
    media = json.loads(calls[0]["data"]["media"])
    assert [m["media"] for m in media] == ["attach://p0", "attach://p1", "attach://p2"]
    assert media[0]["caption"] == "زیرنویس" and "caption" not in media[1]
    assert set(calls[0]["files"]) == {"p0", "p1", "p2"}


def test_caption_limit_and_missing_file(tmp_path, monkeypatch):
    calls = _setup(monkeypatch)
    p = tmp_path / "a.png"
    p.write_bytes(b"x")
    assert TG.send_photos([str(p)], "ا" * (TG.CAPTION_MAX + 1)).ok is False
    assert TG.send_photos([str(tmp_path / "نیست.png")], "x").ok is False
    assert calls == []


def test_failure_receipt_never_contains_token(monkeypatch):
    _setup(monkeypatch, _Resp(400, {"ok": False, "description": f"bad token {TOK}"}))
    r = TG.send_html("سلام")
    assert r.ok is False and TOK not in r.detail and "***" in r.detail and "400" in r.detail


def test_missing_keys_is_not_failure(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert TG.send_html("x").ok is None and TG.send_photos(["x"], "y").ok in (None, False)


def test_html_escape():
    assert TG.html_escape("a<b>&c") == "a&lt;b&gt;&amp;c"
