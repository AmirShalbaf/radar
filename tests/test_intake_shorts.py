"""
آزمون رد ویدیوی کوتاه — نشست ۴، تصمیم ۱ کاربر، ۲۹ سپتامبر ۲۰۲۶.

یافته ایستگاه ۱: ۱۱ از ۱۵ آیتم خوراک رایول پال ویدیوی کوتاه بود، دو نمونه
حدود ۲۷ ثانیه. قاعده، در همه منابع یوتیوب:
- ویدیوی ۳ دقیقه یا کمتر رد می‌شود — نه بی‌صدا: شمارش در خروجی و INDEX.
- مدت نامعلوم یعنی «رد نشد»، با برچسب «مدت نامعلوم».
- ردشده سهم --limit را نمی‌خورد.
روش سنجش: فراداده خود صفحه ویدیو — `itemprop="duration"`، سپس
`lengthSeconds` داخل بلوک `videoDetails` همان ویدیو. نه نخستین
`lengthSeconds` صفحه: همان درس resolve_channel_id، «اولین تطبیق انتخاب
دلبخواه است، نه استخراج».
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_intake as I

VID = "abcdefghijk"


class _Resp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class _Session:
    def __init__(self, text=None, exc=None):
        self.text, self.exc = text, exc

    def get(self, url, timeout=0):
        if self.exc:
            raise self.exc
        return _Resp(self.text)


# ═══════════════════ خواندن مدت ═══════════════════

def test_duration_from_meta() -> None:
    html = '<meta itemprop="duration" content="PT2M59S">'
    assert I.video_duration(VID, _Session(html))[0] == 179


def test_duration_with_hours() -> None:
    html = '<meta itemprop="duration" content="PT1H2M3S">'
    assert I.video_duration(VID, _Session(html))[0] == 3723


def test_duration_real_youtube_shape_over_an_hour() -> None:
    """یوتیوب ساعت را در دقیقه می‌ریزد: 5914 ثانیه = PT98M34S — سنجش ۲۹ سپتامبر."""
    html = '<meta itemprop="duration" content="PT98M34S">'
    assert I.video_duration(VID, _Session(html))[0] == 5914


def test_duration_from_own_video_details_not_first_match() -> None:
    html = ('"lengthSeconds":"30" related... '
            '"videoDetails":{"videoId":"' + VID + '","title":"x","lengthSeconds":"900"}')
    assert I.video_duration(VID, _Session(html))[0] == 900


def test_duration_unknown_when_absent() -> None:
    dur, why = I.video_duration(VID, _Session("<html>consent</html>"))
    assert dur is None and why


def test_duration_unknown_on_error_with_type() -> None:
    dur, why = I.video_duration(VID, _Session(exc=ConnectionError("reset")))
    assert dur is None and "ConnectionError" in why


# ═══════════════════ اجرا ═══════════════════

def _item(vid: str) -> dict:
    return {"id": vid, "title": f"ویدیو {vid}", "url": f"https://www.youtube.com/watch?v={vid}",
            "published": "2026-09-29", "author": "x"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    cfg = tmp_path / "analysts.yml"
    cfg.write_text("sources:\n"
                   "  alpha:\n    name_fa: \"منبع الف\"\n    kind: \"youtube\"\n"
                   "    channel_id: \"UCaaaaaaaaaaaaaaaaaaaaaa\"\n"
                   "  gamma:\n    name_fa: \"منبع ج\"\n    kind: \"rss\"\n"
                   "    url: \"https://example.com/feed\"\n", encoding="utf-8")
    out = tmp_path / "intake"
    durs: dict = {}
    calls: list = []
    items: dict = {"alpha": [], "gamma": []}

    def dur(vid, session):
        calls.append(vid)
        v = durs[vid]
        return (v, "آزمون") if v is not None else (None, "فراداده مدت در صفحه نبود")

    monkeypatch.setattr(I, "_has_module", lambda m: True)
    monkeypatch.setattr(I, "make_session", lambda: object())
    monkeypatch.setattr(I, "video_duration", dur)
    monkeypatch.setattr(I, "fetch_youtube_items", lambda s, ss: items[s.key])
    monkeypatch.setattr(I, "fetch_rss_items", lambda s, ss: items[s.key])
    monkeypatch.setattr(I, "fetch_transcript",
                        lambda v, l: ([{"text": "bitcoin 62000 next week", "start": 1.0}], "خودکار"))
    monkeypatch.setattr(I, "fetch_article_text",
                        lambda u, s: (" ".join(["word"] * 300), "trafilatura"))

    def run(*extra):
        return I.main(["--config", str(cfg), "--out", str(out), "--state",
                       str(out / ".state.json"), "--sleep", "0", *extra])
    return {"out": out, "durs": durs, "calls": calls, "items": items, "run": run}


def _idx(env) -> str:
    return (env["out"] / "INDEX.md").read_text(encoding="utf-8")


def test_short_rejected_counted_unknown_kept(env, capsys) -> None:
    env["durs"].update({"short000001": 27, "edge0000180": 180, "long0000181": 181,
                        "unknown0001": None})
    env["items"]["alpha"] = [_item(v) for v in env["durs"]]
    assert env["run"]("--source", "alpha") == 0          # رد کوتاه شکست نیست
    docs = sorted((env["out"] / "alpha").glob("*.md"))
    assert len(docs) == 2
    unknown = [d for d in docs if "unknown" in d.name][0].read_text(encoding="utf-8")
    assert "مدت: نامعلوم" in unknown
    idx = _idx(env)
    row = [l for l in idx.splitlines() if l.startswith("| منبع الف")][0]
    cells = [c.strip() for c in row.split("|")[1:-1]]
    head = [c.strip() for c in [l for l in idx.splitlines() if l.startswith("| منبع |")][0].split("|")[1:-1]]
    assert cells[head.index("کوتاه ردشده")] == "2"
    assert cells[head.index("مدت نامعلوم")] == "1"
    assert "مدت نامعلوم" in [l for l in idx.splitlines() if "unknown" in l][0]
    out = capsys.readouterr().out
    assert "کوتاه" in out


def test_shorts_do_not_eat_the_limit(env) -> None:
    env["durs"].update({"short000001": 20, "short000002": 25, "long0000001": 1200})
    env["items"]["alpha"] = [_item(v) for v in env["durs"]]
    env["run"]("--source", "alpha", "--limit", "1")
    assert len(list((env["out"] / "alpha").glob("*.md"))) == 1


def test_rejected_short_is_remembered(env) -> None:
    env["durs"].update({"short000001": 20})
    env["items"]["alpha"] = [_item("short000001")]
    env["run"]("--source", "alpha")
    state = json.loads((env["out"] / ".state.json").read_text(encoding="utf-8"))
    assert state["seen"]["alpha"]["short000001"]["rejected"] == "کوتاه"
    env["calls"].clear()
    env["run"]("--source", "alpha")
    assert env["calls"] == []


def test_dry_run_also_filters(env, capsys) -> None:
    env["durs"].update({"short000001": 20, "long0000001": 1200})
    env["items"]["alpha"] = [_item(v) for v in env["durs"]]
    env["run"]("--source", "alpha", "--dry-run")
    out = capsys.readouterr().out
    row = [l for l in out.splitlines() if l.startswith("| منبع الف")][0]
    assert row.split("|")[2].strip() == "1"               # سند تازه
    assert not (env["out"] / ".state.json").exists()


def test_articles_are_not_timed(env) -> None:
    env["items"]["gamma"] = [{"id": "art1", "title": "مقاله", "url": "https://example.com/a",
                              "published": "2026-09-29", "author": "x"}]
    assert env["run"]("--source", "gamma") == 0
    assert env["calls"] == []
