"""
آزمون تفکیک «مسدود» از «زیرنویس ندارد» — نشست ۴، بند ۳، ایستگاه ۱ بند «و».

پیش از این شش `except Exception` پشت هم در fetch_transcript هر خطای واکشی را
می‌بلعید — مسدودی آی‌پی، خطای شبکه — و نتیجه «زیرنویس یافت نشد» بود. از
پشت وی‌پی‌ان، مسدودی یوتیوب دقیقاً شکل «این ویدیو زیرنویس ندارد» می‌گرفت.
حالا:
- نبود زیرنویس ویژگی ویدیو است: قطعات خالی با «زیرنویس ندارد».
- مسدودی خطای TranscriptBlocked است.
- هر خطای دیگر بالا می‌رود تا صدازننده با نوعش ثبتش کند.
استثناها همان کلاس‌های واقعی youtube-transcript-api اند، نه بدل.
"""
import sys
from pathlib import Path

import pytest
import youtube_transcript_api._errors as E

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_intake as I
import radar_one as ONE

VID = "dQw4w9WgXcQ"


class FakeT:
    def __init__(self, code, generated, *, fetch_exc=None, translate_exc=None,
                 text="bitcoin 62000"):
        self.language_code = code
        self.is_generated = generated
        self.is_translatable = translate_exc is None
        self._fetch_exc = fetch_exc
        self._translate_exc = translate_exc
        self._text = text

    def fetch(self):
        if self._fetch_exc is not None:
            raise self._fetch_exc
        return [{"text": self._text, "start": 1.0}]

    def translate(self, lang):
        if self._translate_exc is not None:
            raise self._translate_exc
        return FakeT(lang, True, fetch_exc=self._fetch_exc, text="translated")


class FakeListing:
    def __init__(self, ts):
        self.ts = ts

    def __iter__(self):
        return iter(self.ts)

    def _find(self, langs, generated):
        for t in self.ts:
            if t.is_generated == generated and t.language_code in langs:
                return t
        raise E.NoTranscriptFound(VID, langs, None)

    def find_manually_created_transcript(self, langs):
        return self._find(langs, False)

    def find_generated_transcript(self, langs):
        return self._find(langs, True)


@pytest.fixture
def listing(monkeypatch):
    box = {}

    def fake(video_id):
        if "exc" in box:
            raise box["exc"]
        return FakeListing(box["ts"])
    monkeypatch.setattr(I, "_get_transcript_list", fake)
    return box


# ═══════════════════ مسدود ═══════════════════

def test_blocked_at_listing_is_blocked(listing) -> None:
    listing["exc"] = E.IpBlocked(VID)
    with pytest.raises(I.TranscriptBlocked, match="IpBlocked"):
        I.fetch_transcript(VID, ["en"])


def test_blocked_at_fetch_is_not_no_transcript(listing) -> None:
    """همان مورد بلعیده‌شده: فهرست آمد، واکشی مسدود شد."""
    listing["ts"] = [FakeT("en", True, fetch_exc=E.RequestBlocked(VID))]
    with pytest.raises(I.TranscriptBlocked, match="RequestBlocked"):
        I.fetch_transcript(VID, ["en"])


def test_po_token_is_blocked(listing) -> None:
    listing["ts"] = [FakeT("en", False, fetch_exc=E.PoTokenRequired(VID))]
    with pytest.raises(I.TranscriptBlocked):
        I.fetch_transcript(VID, ["en"])


def test_blocked_in_translation_step_is_blocked(listing) -> None:
    listing["ts"] = [FakeT("de", True, fetch_exc=E.IpBlocked(VID))]
    with pytest.raises(I.TranscriptBlocked):
        I.fetch_transcript(VID, ["en"])


# ═══════════════════ خطای دیگر ═══════════════════

def test_other_fetch_error_propagates(listing) -> None:
    listing["ts"] = [FakeT("en", True, fetch_exc=ConnectionError("reset"))]
    with pytest.raises(ConnectionError):
        I.fetch_transcript(VID, ["en"])


def test_other_listing_error_propagates(listing) -> None:
    listing["exc"] = TimeoutError("slow")
    with pytest.raises(TimeoutError):
        I.fetch_transcript(VID, ["en"])


# ═══════════════════ ندارد — ویژگی ویدیو ═══════════════════

def test_empty_listing_is_no_transcript(listing) -> None:
    listing["ts"] = []
    segs, why = I.fetch_transcript(VID, ["en"])
    assert segs == [] and "زیرنویس ندارد" in why


def test_disabled_is_no_transcript(listing) -> None:
    listing["exc"] = E.TranscriptsDisabled(VID)
    segs, why = I.fetch_transcript(VID, ["en"])
    assert segs == [] and "زیرنویس ندارد" in why


def test_unavailable_video_says_so(listing) -> None:
    listing["exc"] = E.VideoUnavailable(VID)
    segs, why = I.fetch_transcript(VID, ["en"])
    assert segs == [] and "در دسترس نیست" in why


# ═══════════════════ ترتیب اولویت — رفتار پیشین ═══════════════════

def test_manual_before_generated(listing) -> None:
    listing["ts"] = [FakeT("en", True, text="auto"), FakeT("en", False, text="manual")]
    segs, why = I.fetch_transcript(VID, ["en"])
    assert segs[0]["text"] == "manual" and "دستی" in why


def test_generated_when_no_manual(listing) -> None:
    listing["ts"] = [FakeT("fa", True)]
    segs, why = I.fetch_transcript(VID, ["fa"])
    assert segs and "خودکار" in why


def test_translation_when_language_missing(listing) -> None:
    listing["ts"] = [FakeT("de", True)]
    segs, why = I.fetch_transcript(VID, ["en"])
    assert segs[0]["text"] == "translated" and "ترجمه" in why


def test_untranslatable_falls_to_any_language(listing) -> None:
    listing["ts"] = [FakeT("de", True, translate_exc=E.NotTranslatable(VID))]
    segs, why = I.fetch_transcript(VID, ["en"])
    assert segs and "زبان درخواستی نبود" in why


# ═══════════════════ radar_one — همان تابع ═══════════════════

def test_radar_one_reports_block_plainly(monkeypatch, capsys) -> None:
    def blocked(vid, langs):
        raise I.TranscriptBlocked("مسدود (IpBlocked)")
    monkeypatch.setattr(ONE, "fetch_transcript", blocked)
    assert ONE.main([VID]) == 3
    err = capsys.readouterr().err
    assert "مسدود" in err and "زیرنویس" in err
