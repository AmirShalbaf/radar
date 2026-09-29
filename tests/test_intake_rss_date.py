"""
آزمون تاریخ خوراک RSS — نشست ۴، یافته حین کار، ۲۹ سپتامبر ۲۰۲۶.

خوراک RSS تاریخ را به قالب «Tue, 29 Sep 2026 12:34:56 GMT» می‌دهد، ولی
همه مصرف‌کننده‌ها ده نویسه اول را تاریخ ISO فرض می‌کنند:
- نام فایل «Tue, 29 Se_…» می‌شد — با ویرگول و فاصله،
- ستون تاریخ INDEX و شناسه سند «Tue, 29 Se»،
- --since و --days در radar_digest مقایسه رشته‌ای غلط می‌کردند.
خوراک یوتیوب ISO است، پس تا وقتی فقط یوتیوب و دوره جمع می‌شد پنهان ماند.
باب الیوت نخستین منبع RSS روشن است. رفع در سرچشمه: تاریخ تجزیه‌شده
feedparser به ISO جهانی.
"""
import sys
import time
from pathlib import Path

from feedparser import FeedParserDict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_intake as I

RAW = "Tue, 29 Sep 2026 12:34:56 GMT"
PARSED = time.strptime("2026-09-29 12:34:56", "%Y-%m-%d %H:%M:%S")


class _FP:
    def __init__(self, entries):
        self.entries = entries

    def parse(self, url, **kw):
        return FeedParserDict(entries=self.entries, feed=FeedParserDict())


def _entry(**kw) -> FeedParserDict:
    base = {"link": "https://bobeunlimited.substack.com/p/rba", "title": "The RBA",
            "author": "Bob Elliott", "published": RAW, "published_parsed": PARSED}
    base.update(kw)
    return FeedParserDict(base)


def _src() -> I.Source:
    return I.Source(key="bob", name_fa="باب", kind="rss",
                    url="https://bobeunlimited.substack.com/feed")


def test_rss_date_is_iso(monkeypatch) -> None:
    monkeypatch.setattr(I, "feedparser", _FP([_entry()]))
    items = I.fetch_rss_items(_src(), session=None)
    assert items[0]["published"] == "2026-09-29T12:34:56Z"


def test_rss_updated_used_when_no_published(monkeypatch) -> None:
    e = _entry()
    del e["published"], e["published_parsed"]
    e["updated"], e["updated_parsed"] = RAW, PARSED
    monkeypatch.setattr(I, "feedparser", _FP([e]))
    assert I.fetch_rss_items(_src(), session=None)[0]["published"].startswith("2026-09-29")


def test_rss_unparsed_date_is_empty_not_garbage(monkeypatch) -> None:
    """بی‌تاریخ تجزیه‌شده: خالی، که در سند «—» می‌شود — نه ده نویسه دلبخواه."""
    e = _entry(published="sometime last week")
    del e["published_parsed"]
    monkeypatch.setattr(I, "feedparser", _FP([e]))
    assert I.fetch_rss_items(_src(), session=None)[0]["published"] == ""


def test_rss_file_name_and_index_date(tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "analysts.yml"
    cfg.write_text("sources:\n  bob:\n    name_fa: \"باب\"\n    kind: \"rss\"\n"
                   "    url: \"https://bobeunlimited.substack.com/feed\"\n", encoding="utf-8")
    out = tmp_path / "intake"
    monkeypatch.setattr(I, "_has_module", lambda m: True)
    monkeypatch.setattr(I, "make_session", lambda: object())
    monkeypatch.setattr(I, "feedparser", _FP([_entry()]))
    monkeypatch.setattr(I, "fetch_article_text",
                        lambda u, s: (" ".join(["word"] * 300), "trafilatura"))
    assert I.main(["--config", str(cfg), "--out", str(out), "--state",
                   str(out / ".state.json"), "--sleep", "0"]) == 0
    names = [p.name for p in (out / "bob").glob("*.md")]
    assert names and names[0].startswith("2026-09-29_")
    row = [l for l in (out / "INDEX.md").read_text(encoding="utf-8").splitlines()
           if "bob/" in l][0]
    assert row.startswith("| 2026-09-29 |")


def test_since_filters_rss_by_real_date(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(I, "feedparser", _FP([_entry()]))
    items = I.fetch_rss_items(_src(), session=None)
    assert items[0]["published"][:10] >= "2026-09-01"
    assert not items[0]["published"][:10] >= "2026-10-01"
