"""
نمایش و ارسال پیام صبح — متن ۳۷. فقط brief.json خوانده می‌شود؛ سقف‌های تلگرام، تگ مجاز،
گریز متن پویا، زنجیره پشتیبان و تصویر.
"""
import json
import os
import re
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
import radar_sidecar as SC
import radar_telegram as TG

UTC = timezone.utc
ALLOWED = {"b", "/b", "i", "/i", "blockquote", "blockquote expandable", "/blockquote"}


def _doc(**kw):
    now = datetime.now(UTC)
    F.write_all(".", now, **kw)
    src = BR.Sources(".", now, files={"lessons": str(ROOT / "references" / "lessons.json")})
    return BR.collect(src, fetch=F.fake_fetch())


def _tags(html):
    return set(re.findall(r"<([^>]+)>", html))


def test_caption_and_message_fit_telegram_and_use_only_allowed_tags():
    doc = _doc()
    cap, msg, head = R.caption(doc), R.message(doc), R.message(doc, with_head=True)
    assert len(cap) <= TG.CAPTION_MAX and len(msg) <= TG.HTML_MAX and len(head) <= TG.HTML_MAX
    for t in (cap, msg, head):
        assert _tags(t) <= ALLOWED, _tags(t) - ALLOWED
        assert "**" not in t and "##" not in t and "|---" not in t
    assert doc["verdict"]["headline"] in cap and doc["verdict"]["headline"] in head
    assert "نزدیک‌ترین ماشه‌ها" in msg and "درس امروز" in msg and "⚙️ سیستم" in msg


def test_dynamic_text_is_escaped():
    doc = _doc()
    doc["verdict"]["must"] = ["فروش <b>همه</b> & فرار"]
    cap = R.caption(doc)
    assert "&lt;b&gt;همه&lt;/b&gt; &amp; فرار" in cap


def test_long_caption_is_trimmed_not_rejected():
    doc = _doc()
    doc["verdict"]["overdue"] = ["الف" * 600, "ب" * 600]
    assert len(R.caption(doc)) <= TG.CAPTION_MAX


def test_failed_section_shows_no_data_with_reason():
    now = datetime.now(UTC)
    F.write_all(".", now)
    os.remove("reports/scan.json")
    doc = BR.collect(BR.Sources(".", now), fetch=None)
    html = R.card_today(doc)
    assert "داده ندارم" in html and "scan.json" in html
    assert "⚠️ داده ندارم" in R.message(doc)
    names = [n for n, _ in R.cards(doc)]
    assert names[:2] == ["card1", "card2"]


def test_load_rejects_stale_or_broken_document(tmp_path):
    doc = _doc()
    p = tmp_path / "b.json"
    SC.write_json(str(p), doc)
    assert R.load(str(p))["schema"] == BR.SCHEMA
    with pytest.raises(R.RenderError, match="کهنه"):
        R.load(str(p), now=datetime.now(UTC) + timedelta(hours=R.MAX_AGE_H + 1))
    bad = dict(doc, schema=99)
    SC.write_json(str(p), bad)
    with pytest.raises(R.RenderError, match="قرارداد"):
        R.load(str(p))


def test_plain_fallback_has_no_tags():
    txt = R.plain(_doc())
    assert "<" not in txt.replace("&lt;", "") and "امروز" in txt


def test_buttons_https_only_and_desk_optional():
    assert R.buttons({}) == []
    b = R.buttons({"GITHUB_REPOSITORY": "x/radar", "RADAR_DESK_URL": "http://bad"})
    flat = [u for row in b for _, u in row]
    assert flat and all(u.startswith("https://github.com/x/radar/") for u in flat)
    b = R.buttons({"GITHUB_REPOSITORY": "x/radar", "RADAR_DESK_URL": "https://claude.ai/a"})
    assert b[0][0] == ("📋 میز تحلیلگر", "https://claude.ai/a")


def test_number_format_persian_with_sign():
    assert R.num(-6.71, 1, pct=True) == "−۶٫۷٪"
    assert R.num(5.4, 1, sign=True, pct=True) == "+۵٫۴٪"
    assert R.num(1534.3) == "۱٬۵۳۴" and R.num(None) == "—"
    assert R.tnum(-1.0, 1).startswith(R.LRM)
    assert R.price(0.3478) == "۰٫۳۴۷۸" and R.price(76590.4) == "۷۶٬۵۹۰"


def _render(tmp_path, doc):
    p = tmp_path / "brief.json"
    SC.write_json(str(p), doc)
    out = tmp_path / "out"
    assert R.render(str(p), str(out), png=False) == 0
    return out


def _fake(monkeypatch, photos, html, plain):
    calls = []
    monkeypatch.setattr(TG, "send_photos", lambda paths, cap, silent=False: calls.append(("photos", len(paths))) or photos)
    monkeypatch.setattr(TG, "send_html", lambda text, buttons=None, silent=False: calls.append(("html", silent, text)) or html)
    monkeypatch.setattr(TG, "send", lambda text: calls.append(("plain",)) or plain)
    return calls


def test_send_chain_photos_then_silent_html(tmp_path, monkeypatch):
    out = _render(tmp_path, _doc())
    (out / "card1.png").write_bytes(b"x")
    calls = _fake(monkeypatch, TG.Sent(True, "ok"), TG.Sent(True, "ok"), TG.Sent(True, "ok"))
    assert R.send(str(out)) == 0
    assert calls[0] == ("photos", 1) and calls[1][0] == "html" and calls[1][1] is True
    assert "استنتاج" in calls[1][2] and "☀️" not in calls[1][2]


def test_send_without_photos_puts_verdict_in_html(tmp_path, monkeypatch):
    out = _render(tmp_path, _doc())
    calls = _fake(monkeypatch, TG.Sent(False, "x"), TG.Sent(True, "ok"), TG.Sent(True, "ok"))
    assert R.send(str(out)) == 0
    html = [c for c in calls if c[0] == "html"][0]
    assert html[1] is False and "☀️ رادار" in html[2]


def test_send_falls_back_to_plain_then_fails_loud(tmp_path, monkeypatch):
    out = _render(tmp_path, _doc())
    calls = _fake(monkeypatch, TG.Sent(False, "x"), TG.Sent(False, "x"), TG.Sent(True, "ok"))
    assert R.send(str(out)) == 0 and calls[-1] == ("plain",)
    _fake(monkeypatch, TG.Sent(False, "x"), TG.Sent(False, "x"), TG.Sent(False, "x"))
    assert R.send(str(out)) == R.RC_NOTHING


def test_send_without_keys_is_not_failure(tmp_path, monkeypatch):
    out = _render(tmp_path, _doc())
    (out / "card1.png").write_bytes(b"x")
    _fake(monkeypatch, TG.Sent(None, "بی‌کلید"), TG.Sent(True, "ok"), TG.Sent(True, "ok"))
    assert R.send(str(out)) == 0


def test_png_rendering_when_browser_available(tmp_path):
    pytest.importorskip("playwright")
    out = _render(tmp_path, _doc())
    htmls = sorted(str(p) for p in out.glob("card*.html"))
    try:
        got = R.to_png(htmls, [h[:-5] + ".png" for h in htmls])
    except R.RenderError as exc:
        pytest.skip(f"مرورگر در دسترس نیست — {exc}")
    assert len(got) == len(htmls) and all(os.path.getsize(p) > 20000 for p in got)
