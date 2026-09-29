"""
آزمون خرابی آشکار در جمع‌آوری — نشست ۴، بند ۳ و تصمیم ۵ کاربر، ۲۹ سپتامبر ۲۰۲۶.

یافته‌های ایستگاه ۱، بند «و»:
- شکست هر منبع — هندل ۴۰۴، صفحه منتقل‌شده، خوراک خالی — فقط یک خط لاگ بود؛
  نه در INDEX می‌آمد، نه در کد خروج. سه هندل ۴۰۴ و کایکو ماه‌ها پنهان ماندند.
- load_state فایل خراب را می‌بلعید: حافظه صفر، سپس بازنویسی همان فایل.
- rebuild_index سند ناخوانا را بی‌صدا از فهرست می‌انداخت.
- شکست trafilatura بی‌صدا به استخراج ساده می‌افتاد.
- خلاصه ۷۶ کلمه‌ای با «[…]» مثل مقاله کامل ثبت می‌شد.
حالا منبعی که شکست خورد بقیه را متوقف نمی‌کند، ولی با نام و دلیل در
خروجی و سرخط INDEX می‌آید و کد خروج ۳ می‌شود.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_intake as I

LONG = " ".join(["bitcoin will reach 62000 by the end of the month"] * 30)

CFG = """
sources:
  alpha:
    name_fa: "منبع الف"
    kind: "youtube"
    channel_id: "UCaaaaaaaaaaaaaaaaaaaaaa"
    lang: ["en"]
  beta:
    name_fa: "منبع ب"
    kind: "youtube"
    channel_id: "UCbbbbbbbbbbbbbbbbbbbbbb"
    lang: ["en"]
  gamma:
    name_fa: "منبع ج"
    kind: "rss"
    url: "https://example.com/feed"
  off:
    name_fa: "منبع خاموش"
    kind: "rss"
    url: "https://example.com/dead"
    enabled: false
    disabled_reason: "خوراک از فوریه مرده است"
"""


def _item(i: str, title: str = "") -> dict:
    return {"id": f"vid{i}xxxxxxx"[:11], "title": title or f"ویدیو {i}",
            "url": f"https://www.youtube.com/watch?v=vid{i}", "published": "2026-09-29",
            "author": "x"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    cfg = tmp_path / "analysts.yml"
    cfg.write_text(CFG, encoding="utf-8")
    out = tmp_path / "intake"
    monkeypatch.setattr(I, "_has_module", lambda m: True)
    monkeypatch.setattr(I, "make_session", lambda: object())
    monkeypatch.setattr(I, "video_duration", lambda vid, s: (600, "آزمون"))
    feeds: dict = {}

    def yt(src, session):
        v = feeds[src.key]
        if isinstance(v, Exception):
            raise v
        return v
    monkeypatch.setattr(I, "fetch_youtube_items", yt)
    monkeypatch.setattr(I, "fetch_rss_items", yt)
    monkeypatch.setattr(I, "fetch_transcript",
                        lambda vid, langs: ([{"text": LONG, "start": 3.0}], "زیرنویس خودکار [en]"))
    monkeypatch.setattr(I, "fetch_article_text", lambda url, s: (LONG, "trafilatura"))

    def run(*extra):
        return I.main(["--config", str(cfg), "--out", str(out),
                       "--state", str(out / ".state.json"), "--sleep", "0", *extra])
    return {"out": out, "feeds": feeds, "run": run, "tmp": tmp_path}


def _index(env) -> str:
    return (env["out"] / "INDEX.md").read_text(encoding="utf-8")


# ═══════════════════ شکست منبع ═══════════════════

def test_failed_source_does_not_stop_others(env, capsys) -> None:
    env["feeds"].update(alpha=I.SourceFailure("صفحه کانال ۴۰۴"),
                        beta=[_item("1")], gamma=[_item("2")])
    assert env["run"]() == 3
    idx = _index(env)
    assert "منابع ناموفق" in idx
    assert "منبع الف" in idx and "صفحه کانال ۴۰۴" in idx
    assert list((env["out"] / "beta").glob("*.md"))
    assert list((env["out"] / "gamma").glob("*.md"))
    out = capsys.readouterr().out
    assert "منبع الف" in out and "صفحه کانال ۴۰۴" in out


def test_all_healthy_exits_zero(env) -> None:
    env["feeds"].update(alpha=[_item("1")], beta=[_item("2")], gamma=[_item("3")])
    assert env["run"]() == 0
    assert "هیچ منبعی شکست نخورد" in _index(env)


def test_unexpected_error_is_recorded_with_type(env) -> None:
    env["feeds"].update(alpha=ValueError("feed parse"), beta=[], gamma=[])
    assert env["run"]() == 3
    assert "ValueError" in _index(env)


def test_blocked_stops_that_source_and_fails(env, monkeypatch) -> None:
    calls = []

    def blocked(vid, langs):
        calls.append(vid)
        raise I.TranscriptBlocked("مسدود (IpBlocked)")
    monkeypatch.setattr(I, "fetch_transcript", blocked)
    env["feeds"].update(alpha=[_item("1"), _item("2")], beta=[], gamma=[])
    assert env["run"]("--source", "alpha") == 3
    assert len(calls) == 1
    assert "مسدود" in _index(env)


def test_item_error_is_failure_with_type(env, monkeypatch) -> None:
    def broken(vid, langs):
        raise ConnectionError("reset by peer")
    monkeypatch.setattr(I, "fetch_transcript", broken)
    env["feeds"].update(alpha=[_item("1")])
    assert env["run"]("--source", "alpha") == 3
    assert "ConnectionError" in _index(env)


def test_no_transcript_is_reported_not_failure(env, monkeypatch) -> None:
    """«اگر منبعی زیرنویس نداشت فقط گزارش کن» — ویژگی ویدیو، نه شکست."""
    monkeypatch.setattr(I, "fetch_transcript", lambda vid, langs: ([], "زیرنویس ندارد"))
    env["feeds"].update(alpha=[_item("1", "بی‌متن")])
    assert env["run"]("--source", "alpha") == 0
    idx = _index(env)
    assert "بی‌متن" in idx and "زیرنویس ندارد" in idx


def test_disabled_sources_listed_with_reason(env) -> None:
    env["feeds"].update(alpha=[], beta=[], gamma=[])
    env["run"]()
    idx = _index(env)
    assert "منابع خاموش" in idx and "خوراک از فوریه مرده است" in idx


def test_dry_run_reports_failure_and_writes_nothing(env) -> None:
    env["feeds"].update(alpha=I.SourceFailure("خوراک خالی"), beta=[_item("1")], gamma=[])
    assert env["run"]("--dry-run") == 3
    assert not (env["out"] / "INDEX.md").exists()
    assert not (env["out"] / ".state.json").exists()


# ═══════════════════ حافظه خراب ═══════════════════

def test_corrupt_state_stops_and_is_not_overwritten(env, capsys) -> None:
    env["out"].mkdir()
    st = env["out"] / ".state.json"
    st.write_text("{not json", encoding="utf-8")
    env["feeds"].update(alpha=[_item("1")], beta=[], gamma=[])
    assert env["run"]() == 2
    assert st.read_text(encoding="utf-8") == "{not json"
    assert not (env["out"] / "INDEX.md").exists()
    assert ".state.json" in capsys.readouterr().out


def test_load_state_raises_on_corrupt(tmp_path) -> None:
    p = tmp_path / ".state.json"
    p.write_text("[1, 2", encoding="utf-8")
    with pytest.raises(I.IntakeError):
        I.load_state(p)


def test_load_state_missing_is_empty(tmp_path) -> None:
    assert I.load_state(tmp_path / "none.json") == {"seen": {}}


# ═══════════════════ INDEX ═══════════════════

def _doc(title: str) -> str:
    return ("---\nمنبع: الف\nجایگاه در رادار: لنز\nعنوان: " + title +
            "\nتاریخ انتشار: 2026-09-29\nنامزد ادعا: 2\n---\n\nمتن\n")


def test_unreadable_doc_is_listed_not_dropped(tmp_path) -> None:
    out = tmp_path / "intake"
    (out / "a").mkdir(parents=True)
    (out / "a" / "good.md").write_text(_doc("خوب"), encoding="utf-8")
    (out / "a" / "bad.md").write_bytes(b"---\n\xff\xfe\xfa broken\n---\n")
    problems = I.rebuild_index(out)
    idx = (out / "INDEX.md").read_text(encoding="utf-8")
    assert problems and "a/bad.md" in problems[0]
    assert "a/bad.md" in idx and "ناخوانا" in idx
    assert "تعداد سند: 2" in idx


def test_unreadable_doc_makes_run_fail(env) -> None:
    env["feeds"].update(alpha=[], beta=[], gamma=[])
    (env["out"] / "a").mkdir(parents=True)
    (env["out"] / "a" / "bad.md").write_bytes(b"\xff\xfe")
    assert env["run"]() == 3


def test_digest_is_not_a_document(tmp_path) -> None:
    out = tmp_path / "intake"
    out.mkdir()
    (out / "DIGEST.md").write_text("# چکیده\n", encoding="utf-8")
    I.rebuild_index(out)
    assert "تعداد سند: 0" in (out / "INDEX.md").read_text(encoding="utf-8")


def test_pipe_in_title_does_not_break_the_table(tmp_path) -> None:
    """عنوان «پارت 7 | هر چی از ساختار...» جدول INDEX موجود را شکسته بود."""
    out = tmp_path / "intake"
    (out / "a").mkdir(parents=True)
    (out / "a" / "x.md").write_text(_doc("پارت 7 | هر چی"), encoding="utf-8")
    I.rebuild_index(out)
    rows = [l for l in (out / "INDEX.md").read_text(encoding="utf-8").splitlines()
            if "a/x.md" in l]
    head = [l for l in (out / "INDEX.md").read_text(encoding="utf-8").splitlines()
            if l.startswith("| تاریخ")]
    assert rows[0].count("|") == head[0].count("|")


# ═══════════════════ متن مقاله ═══════════════════

class _Resp:
    text = "<html><body><p>" + LONG + "</p></body></html>"

    def raise_for_status(self):
        return None


class _Session:
    def get(self, url, timeout=0):
        return _Resp()


def test_trafilatura_failure_is_labelled(monkeypatch) -> None:
    class Boom:
        @staticmethod
        def fetch_url(url):
            raise RuntimeError("tls")
    monkeypatch.setattr(I, "trafilatura", Boom)
    txt, method = I.fetch_article_text("https://example.com/a", _Session())
    assert txt
    assert "trafilatura" in method and "RuntimeError" in method


def test_trafilatura_empty_is_labelled(monkeypatch) -> None:
    class Empty:
        @staticmethod
        def fetch_url(url):
            return None
    monkeypatch.setattr(I, "trafilatura", Empty)
    txt, method = I.fetch_article_text("https://example.com/a", _Session())
    assert "trafilatura" in method and "استخراج ساده" in method


def test_text_gap_rules() -> None:
    wang = " ".join(["word"] * 70) + " under the impression of […]"
    assert "…" in I.text_gap(wang)
    elliott = " ".join(["word"] * 200) + " l… Continue reading this post for free, courtesy of Bob Elliott."
    assert "Continue reading" in I.text_gap(elliott)
    js = " ".join(["word"] * 200) + " This site requires JavaScript to run correctly."
    assert I.text_gap(js)
    assert I.text_gap(" ".join(["word"] * 80)).startswith("کوتاه")
    assert I.text_gap(LONG) is None


def test_incomplete_article_is_labelled_everywhere(env, monkeypatch) -> None:
    stub = " ".join(["word"] * 70) + " rallied under the impression of […]"
    monkeypatch.setattr(I, "fetch_article_text", lambda url, s: (stub, "trafilatura"))
    env["feeds"].update(gamma=[_item("9", "War and Policy")])
    assert env["run"]("--source", "gamma") == 0
    docs = list((env["out"] / "gamma").glob("*.md"))
    assert "متن: ناقص" in docs[0].read_text(encoding="utf-8")
    row = [l for l in _index(env).splitlines() if "War and Policy" in l][0]
    assert "ناقص" in row
