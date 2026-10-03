"""
آزمون radar_frames.py — نشست ۶. بدون شبکه، با داده ساختگی.

سند ورودی با همان سازنده واقعی radar_intake.build_documents ساخته می‌شود تا
هر تغییر قالب نامزد یا متن، اینجا قرمز شود نه در اجرای واقعی. فریم‌های
تحلیل آرایه ساختگی‌اند: «نمودار» یک خط شکسته روشن، و «دوربین چهره» نویز
در گوشه بالا چپ. دریافت و استخراج تزریق می‌شوند. فقط یک آزمون ffmpeg واقعی
را می‌خواهد و اگر نبود صریح رد می‌شود.
"""
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_frames as F
import radar_intake as I

ROOT = Path(__file__).resolve().parent.parent
H, W = F.ANALYSIS_H, F.ANALYSIS_W
NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
VID = "abcDEF12_-z"


# ═══════════════ سازنده‌های ساختگی ═══════════════

def view(seed: int) -> np.ndarray:
    """نمای نمودار: خط شکسته روشن روی زمینه تیره، متفاوت برای هر seed."""
    img = np.full((H, W), 20, np.uint8)
    rng = np.random.default_rng(seed)
    y = H // 2
    for x in range(110, W - 20):
        y = int(np.clip(y + rng.integers(-3, 4), 70, H - 10))
        img[y - 1:y + 2, x] = 200
    return img


def with_mark(img: np.ndarray, area_px: int, x0: int = 150, y0: int = 120) -> np.ndarray:
    """لکه مستطیلی با مساحت تقریبی area_px — نقطه نشانگر یا برچسب، بسته به اندازه."""
    out = img.copy()
    w = 10
    h = max(1, area_px // w)
    out[y0:y0 + h, x0:x0 + w] = 255
    return out


def with_line(img: np.ndarray, length: int = 160, y: int = 100) -> np.ndarray:
    """خط افقی کشیده‌شده — دو پیکسل ضخامت."""
    out = img.copy()
    out[y:y + 2, 120:120 + length] = 240
    return out


def seq(parts, face_seed: int = 7) -> np.ndarray:
    """parts: [(تصویر، شمار نمونه)]. دوربین چهره هر نمونه نویز تازه است."""
    rng = np.random.default_rng(face_seed)
    frames = []
    for img, n in parts:
        for _ in range(n):
            f = img.copy()
            f[:50, :90] = rng.integers(0, 256, (50, 90), dtype=np.uint8)
            frames.append(f)
    return np.stack(frames)


def make_doc(tmp_path: Path, cands: list[tuple[str, list[str], int]], seconds: int = 120,
             url: str = f"https://www.youtube.com/watch?v={VID}") -> Path:
    """سند عمومی و محلی با سازنده واقعی radar_intake. برمی‌گرداند مسیر عمومی."""
    src = I.Source(key="alpha", name_fa="منبع الف", kind="youtube",
                   channel_id="UCaaaaaaaaaaaaaaaaaaaaaa")
    item = {"id": VID, "title": "عنوان آزمایشی", "url": url,
            "published": "2026-10-01", "author": "x"}
    segs = [{"text": f"line at {s} seconds", "start": float(s)} for s in range(0, seconds, 3)]
    cc = [I.ClaimCandidate(index=i + 1, timestamp=ts, text=f"claim {i + 1}",
                           categories=["سطح"], numbers=nums, strength=st)
          for i, (ts, nums, st) in enumerate(cands)]
    name = "2026-10-01_test_abcDEF12.md"
    public, full = I.build_documents(src, item, segs, "زیرنویس", cc,
                                     local_rel=f"{I.LOCAL_DIR}/alpha/{name}", duration="02:00")
    pub = tmp_path / "intake" / "alpha" / name
    loc = tmp_path / "intake" / I.LOCAL_DIR / "alpha" / name
    pub.parent.mkdir(parents=True)
    loc.parent.mkdir(parents=True)
    pub.write_text(public, encoding="utf-8")
    loc.write_text(full, encoding="utf-8")
    return pub


# ═══════════════ ۱ — خواندن سند ═══════════════

def test_parse_ts_ascii_only() -> None:
    assert F.parse_ts("06:45") == 405
    assert F.parse_ts("1:02:03") == 3723
    with pytest.raises(F.DocError):
        F.parse_ts("۰۶:۴۵")          # \d رقم فارسی را هم می‌گرفت


def test_year_only_candidates() -> None:
    def c(nums):
        return F.Candidate(1, "00:01", 1, 3, ["زمان"], nums, "x")
    assert c(["2018", "2022"]).year_only
    assert not c(["$6,000", "6,000", "2018"]).year_only
    assert not c([]).year_only
    assert not c(["۲۰۱۸"]).year_only
    assert not c(["40%", "2023"]).year_only


def test_year_range_is_2009_to_publish_year_plus_5() -> None:
    """
    تأیید کاربر، ایستگاه ۲: سال فقط ۲۰۰۹ تا سال انتشار به‌علاوه ۵. سال مرجع
    از تاریخ انتشار سند است، نه ساعت — وگرنه آزمون خودش بمب ساعتی می‌شد.
    """
    def c(nums, ref=2026):
        return F.Candidate(1, "00:01", 1, 3, ["زمان"], nums, "x", ref_year=ref)
    assert c(["2018", "2022"]).year_only
    assert c(["2009"]).year_only and c(["2031"]).year_only
    assert not c(["2090"]).year_only            # قیمت ARB 0.2090 — کریپتوسیتی ۲ اکتبر
    assert not c(["2008"]).year_only and not c(["2032"]).year_only
    assert c(["2035"], ref=2030).year_only
    # محدودیت ثبت‌شده در ک۵۵: قیمتی مثل ۲۰۲۰ برای اتر هنوز سال خوانده می‌شود؛
    # رفع کامل با بافت جمله در نشست ۵
    assert c(["2020"]).year_only


def test_load_doc_reference_year_is_publish_year(tmp_path) -> None:
    pub = make_doc(tmp_path, [("00:10", ["2031"], 3), ("00:20", ["2032"], 3)])
    d = F.load_doc(pub)                          # انتشار 2026-10-01
    assert [c.ref_year for c in d.candidates] == [2026, 2026]
    assert d.candidates[0].year_only and not d.candidates[1].year_only


def test_load_doc_reads_local_with_all_candidates(tmp_path) -> None:
    # ۱۲ نامزد: نسخه عمومی فقط ۱۰ تا دارد؛ فریم باید همه را ببیند
    cands = [(f"00:{10 + 5 * i:02d}", ["62000"], 3) for i in range(12)]
    pub = make_doc(tmp_path, cands)
    d = F.load_doc(pub)
    assert d.video_id == VID
    assert len(d.candidates) == 12
    assert d.candidates[0].seconds == 10 and d.candidates[0].numbers == ["62000"]
    assert d.source == "alpha"
    assert d.public_rel == "intake/alpha/2026-10-01_test_abcDEF12.md"
    assert d.transcript[0] == (0.0, "line at 0 seconds")
    # از مسیر محلی هم همان
    loc = tmp_path / "intake" / I.LOCAL_DIR / "alpha" / pub.name
    assert F.load_doc(loc).public_rel == d.public_rel


def test_load_doc_without_local_is_error(tmp_path) -> None:
    pub = make_doc(tmp_path, [("00:10", ["62000"], 3)])
    (tmp_path / "intake" / I.LOCAL_DIR / "alpha" / pub.name).unlink()
    with pytest.raises(F.DocError, match="متن محلی نیست"):
        F.load_doc(pub)


def test_load_doc_bad_url_is_error(tmp_path) -> None:
    pub = make_doc(tmp_path, [("00:10", ["62000"], 3)], url="https://example.com/x")
    with pytest.raises(F.DocError, match="شناسه"):
        F.load_doc(pub)


def test_local_dir_agrees_with_intake() -> None:
    assert F.LOCAL_DIR == I.LOCAL_DIR
    assert F.CANDIDATE_HEAD in I.build_documents(
        I.Source(key="a", name_fa="a"), {"id": "x", "title": "t", "url": "u"}, [], "m",
        [I.ClaimCandidate(1, "00:01", "t", ["سطح"], ["1"], 3)], local_rel="_local/a/x.md")[1]


# ═══════════════ ۲ — تحلیل ═══════════════

def test_auto_mask_takes_face_cam_not_chart() -> None:
    fr = seq([(view(1), 20), (view(2), 20)])
    keep, share = F.auto_mask(fr)
    assert not keep[:50, :90].any()                 # دوربین چهره ماسک شد
    assert keep[100:, 150:].all()                   # نمودار نه
    assert 0 < share < F.MASK_WARN
    assert not F.analyse(fr).mask_warning


def dense_view(seed: int) -> np.ndarray:
    """نمای پرشمع و پرحجم — هر جابه‌جایی بیشتر پیکسل‌های بلوک را عوض می‌کند."""
    img = np.full((H, W), 20, np.uint8)
    rng = np.random.default_rng(seed)
    img[60:, 100:] = np.where(rng.random((H - 60, W - 100)) < 0.3, 200, 20)
    return img


def test_frequent_chart_motion_does_not_mask_the_chart() -> None:
    """
    ایستگاه ۲ نشست ۶: در کریپتوسیتی خود نمودار در ۵.۵٪ گام‌ها عوض می‌شد و
    ماسک ۶۲.۸٪ قاب را گرفت. ماسک «گام آرام» — تأیید کاربر — بسامد را فقط در
    نیمه آرام‌تر گام‌ها می‌شمارد: دوربین چهره آنجا هم می‌جنبد، نمودار نه.
    """
    fr = seq([(dense_view(300 + k), 10) for k in range(20)])
    keep, share = F.auto_mask(fr)
    assert not keep[:50, :90].any()                 # دوربین چهره هنوز ماسک
    assert keep[100:, 150:].mean() > 0.95           # خود نمودار نه
    assert share < F.MASK_WARN
    an = F.analyse(fr)
    assert len(an.states) == 20                     # هر نما یک حالت ساکن


def test_mask_warning_when_most_of_frame_moves() -> None:
    rng = np.random.default_rng(3)
    fr = rng.integers(0, 256, (30, H, W), dtype=np.uint8)
    fr[:, :, 250:] = 20                              # فقط یک نوار ساکن
    an = F.analyse(fr)
    assert an.mask_share > F.MASK_WARN and an.mask_warning


def test_view_change_splits_states() -> None:
    an = F.analyse(seq([(view(1), 10), (view(2), 10)]))
    assert [(s.i0, s.i1) for s in an.states] == [(0, 9), (10, 19)]


def test_cursor_size_change_merges_but_drawing_does_not() -> None:
    base = view(1)
    dot = with_mark(base, 130)            # حدود ۰.۲۵٪ — بین STILL و MERGE_DIFF
    an = F.analyse(seq([(base, 10), (dot, 10)]))
    assert an.raw_states == 2 and len(an.states) == 1
    an = F.analyse(seq([(base, 10), (with_line(base), 10)]))
    assert len(an.states) == 2


def test_rep_takes_most_ink_and_never_a_motion_sample() -> None:
    base = view(1)
    pan = view(9)                        # یک نمونه جابه‌جایی وسط حالت
    marked = with_mark(base, 130)
    # ۱۰ نمونه هر سو: ماسک «گام آرام» فقط نیمه آرام گام‌ها را می‌شمارد و دوربین
    # چهره باید دست‌کم MASK_MIN_CHANGES بار در آن‌ها بجنبد. با ۵ نمونه، ۵.۵ ثانیه
    # ویدیو، چهره ماسک نمی‌شد — اندازه‌ای که ورودی واقعی هرگز ندارد: intake
    # ویدیوی ۳ دقیقه یا کمتر را رد می‌کند.
    an = F.analyse(seq([(base, 10), (pan, 1), (marked, 10)]))
    assert len(an.states) == 1
    rep = an.states[0].rep
    assert rep != 10 and rep >= 11       # نمونه جوهردار، نه نمونه حرکت


# ═══════════════ ۳ — انتخاب، سقف، حذف تکراری، نگاشت ═══════════════

def _doc(cands) -> F.VideoDoc:
    return F.VideoDoc(public_rel="intake/alpha/x.md", meta={}, doc_id="DOC1", source="alpha",
                      video_id=VID, url="u", title="t",
                      candidates=[F.Candidate(i + 1, F.fmt_t(s), s, st, ["سطح"], nums, "c")
                                  for i, (s, nums, st) in enumerate(cands)],
                      transcript=[(0.0, "x")])


def _many_views(n: int, each: int = 8) -> np.ndarray:
    return seq([(view(100 + k), each) for k in range(n)])


@pytest.mark.parametrize("cap", [1, 5, 25])
def test_max_frames_cap(cap) -> None:
    an = F.analyse(_many_views(40))
    sel = F.select_moments(an, _doc([(10.0, ["62000"], 3), (60.0, ["2018"], 3)]), cap)
    assert len(sel.moments) <= cap
    assert sel.dropped_by_cap > 0
    assert len({F.frame_id(VID, m.t) for m in sel.moments}) == len(sel.moments)


def test_tier1_capped_and_strongest_first() -> None:
    an = F.analyse(_many_views(40, each=6))
    cands = [(6.0 + 3 * i, ["62000"], 2 + (i % 3)) for i in range(20)]
    sel = F.select_moments(an, _doc(cands), 25)
    t1 = [m for m in sel.moments if m.tier == 1]
    assert 0 < len(t1) <= F.TIER1_CAP
    framed = {r.row for m in t1 for r in m.refs}
    strongest = {i + 1 for i, c in enumerate(cands) if c[2] == 4}
    assert strongest & framed                       # قوی‌ترها اول آمدند


def test_year_only_candidate_never_tier1() -> None:
    an = F.analyse(_many_views(10))
    sel = F.select_moments(an, _doc([(12.0, ["2018", "2022"], 3)]), 25)
    assert sel.tier1_candidates == 0 and sel.year_only_candidates == 1
    for m in sel.moments:
        if any(r.row == 1 for r in m.refs):
            assert m.tier == 2


def test_same_state_moments_share_one_frame() -> None:
    an = F.analyse(seq([(view(1), 20), (view(2), 20)]))
    sel = F.select_moments(an, _doc([(2.0, ["62000"], 3), (6.0, ["63000"], 3)]), 25)
    first = [m for m in sel.moments if m.state == 0]
    assert len(first) == 1
    assert {r.row for r in first[0].refs} == {1, 2}


def test_return_to_same_view_is_duplicate() -> None:
    a, b, c = view(1), view(2), view(3)
    an = F.analyse(seq([(a, 10), (b, 10), (a, 10)]))
    assert len(an.states) == 3
    sel = F.select_moments(an, _doc([]), 25)
    assert len(sel.moments) == 2 and sel.duplicates_merged >= 1
    an = F.analyse(seq([(a, 10), (b, 10), (c, 10)]))
    assert len(F.select_moments(an, _doc([]), 25).moments) == 3


def test_adjacent_drawing_is_not_deduplicated() -> None:
    base = view(1)
    an = F.analyse(seq([(base, 10), (with_line(base, 120), 10)]))
    assert len(an.states) == 2
    assert len(F.select_moments(an, _doc([]), 25).moments) == 2


def test_gap_filler_covers_long_silence() -> None:
    # ۳۰۰ ثانیه، یک نمای بلند در آغاز و نماهای کوتاه بعد؛ سقف ۲ تا گذر اولویت ۲ فقط آغاز را بگیرد
    parts = [(view(1), 120)] + [(view(10 + k), 4) for k in range(120)]
    an = F.analyse(seq(parts))
    sel = F.select_moments(an, _doc([]), 4)
    assert sel.gaps_filled >= 1
    assert any("gap_fill" in m.reasons for m in sel.moments)


def test_frame_maps_to_candidate_with_empty_claim_id() -> None:
    an = F.analyse(seq([(view(1), 10), (view(2), 10), (view(3), 10)]))
    sel = F.select_moments(an, _doc([(7.0, ["62000"], 3)]), 25)
    roles = {r.role: m for m in sel.moments for r in m.refs if r.row == 1}
    assert set(roles) == {"claim", "before", "after"}
    assert roles["before"].t < roles["claim"].t < roles["after"].t
    r = next(r for r in roles["claim"].refs if r.row == 1)
    assert r.to_json() == {"doc": "DOC1", "row": 1, "time": "00:07", "role": "claim",
                           "strength": 3, "year_only": False, "claim_id": None}
    assert F.frame_id(VID, roles["claim"].t) == f"{VID}_00m07.0s"
    assert F.frame_id(VID, 3723.25) == f"{VID}_1h02m03.2s"


def test_unframed_candidates_are_listed() -> None:
    an = F.analyse(_many_views(40))
    cands = [(5.0 + 8 * i, ["2019"], 3) for i in range(30)]
    sel = F.select_moments(an, _doc(cands), 3)
    framed = {r.row for m in sel.moments for r in m.refs}
    assert sel.unframed and set(sel.unframed).isdisjoint(framed)
    assert set(sel.unframed) | framed == set(range(1, 31))


# ═══════════════ ۴ — اجرا با دریافت و استخراج تزریقی ═══════════════

class FakeDL:
    def __init__(self, skip_first: bool = False):
        self.skip_first = skip_first
        self.calls = []

    def low(self, url, dest):
        self.calls.append(("low", url))
        p = dest / "low.mp4"
        p.write_bytes(b"x")
        return p

    def sections(self, url, starts, dest):
        self.calls.append(("sections", tuple(starts)))
        out = {}
        for k, s in enumerate(starts):
            if self.skip_first and k == 0:
                continue                 # یوتیوب یک تکه را نداد
            p = dest / f"sec_{s}.mp4"
            p.write_bytes(b"x")
            out[s] = p
        return out


def _fake_extract(section, offset, out):
    out.write_bytes(b"\xff\xd8\xff\xe0fakejpeg")


def _run(tmp_path, frames, cands, dl=None, cap=25):
    pub = make_doc(tmp_path, cands)
    doc = F.load_doc(pub)
    logs = []
    man, code = F.run(doc, tmp_path / "frames", cap, downloader=dl or FakeDL(),
                      decode=lambda p: frames, extract=_fake_extract,
                      height_of=lambda p: 1080, now=NOW, log=logs.append)
    return doc, man, code, logs


def test_run_output_structure(tmp_path) -> None:
    frames = seq([(view(k), 12) for k in range(1, 9)])          # ۴۸ ثانیه
    doc, man, code, _ = _run(tmp_path, frames, [("00:13", ["62000"], 3)])
    assert code == 0
    vdir = tmp_path / "frames" / VID
    assert json.loads((vdir / "frames.json").read_text(encoding="utf-8")) == man
    assert man["schema"] == 1 and man["video_id"] == VID and man["doc_id"] == doc.doc_id
    assert man["missing"] == [] and 0 < len(man["frames"]) <= 25
    md = (vdir / "FRAMES.md").read_text(encoding="utf-8")
    for f in man["frames"]:
        assert f["file"].endswith(".jpg")                       # JPEG، نه PNG
        assert (vdir / f["file"]).read_bytes().startswith(b"\xff\xd8")
        assert f"## {f['frame_id']}" in md and f"]({f['file']})" in md
    claim = next(f for f in man["frames"] if any(r["role"] == "claim" for r in f["refs"]))
    assert "[00:12] line at 12 seconds" in md                   # متن همان لحظه کنار فریم
    assert claim["refs"][0]["claim_id"] is None
    assert not (vdir / "_work").exists()                        # کار موقت پاک شد
    assert not list(vdir.glob("*.png"))


def test_run_missing_section_is_loud(tmp_path) -> None:
    frames = seq([(view(k), 12) for k in range(1, 5)])
    dl = FakeDL(skip_first=True)
    _, man, code, logs = _run(tmp_path, frames, [], dl=dl)
    assert code == 3
    assert man["missing"]
    md = (tmp_path / "frames" / VID / "FRAMES.md").read_text(encoding="utf-8")
    assert "فریم ناموجود" in md
    assert any("دریافت یا استخراج نشد" in x for x in logs)


def test_run_mask_warning_is_loud(tmp_path) -> None:
    rng = np.random.default_rng(3)
    frames = rng.integers(0, 256, (40, H, W), dtype=np.uint8)
    frames[:, :, 250:] = 20
    _, man, _, logs = _run(tmp_path, frames, [])
    assert man["analysis"]["mask_warning"] is True
    assert any("هشدار ماسک" in x for x in logs)
    assert "هشدار ماسک" in (tmp_path / "frames" / VID / "FRAMES.md").read_text(encoding="utf-8")


def test_run_removes_previous_frames(tmp_path) -> None:
    vdir = tmp_path / "frames" / VID
    vdir.mkdir(parents=True)
    (vdir / f"{VID}_99m00.0s.jpg").write_bytes(b"old")
    frames = seq([(view(k), 12) for k in range(1, 4)])
    _, man, _, logs = _run(tmp_path, frames, [])
    assert not (vdir / f"{VID}_99m00.0s.jpg").exists()
    assert len(list(vdir.glob("*.jpg"))) == len(man["frames"])
    assert any("اجرای پیشین" in x for x in logs)


def test_run_asks_only_selected_seconds_in_one_call(tmp_path) -> None:
    dl = FakeDL()
    frames = seq([(view(k), 12) for k in range(1, 6)])
    _, man, _, _ = _run(tmp_path, frames, [], dl=dl)
    sec_calls = [c for c in dl.calls if c[0] == "sections"]
    assert len(sec_calls) == 1
    assert set(sec_calls[0][1]) == {int(f["t"]) for f in man["frames"]}


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg نصب نیست — آزمون واقعی رد شد")
def test_real_ffmpeg_decode_and_extract(tmp_path) -> None:
    """ویدیوی ساختگی ۶ ثانیه: مستطیل روشن از ثانیه ۳. بدون شبکه."""
    vid = tmp_path / "s.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                    "-i", "color=c=0x141414:s=640x360:d=6:r=30",
                    "-vf", "drawbox=x=300:y=150:w=200:h=40:color=white:t=fill:enable='gte(t,3)'",
                    "-pix_fmt", "yuv420p", "-y", str(vid)], check=True)
    fr = F.decode_gray(vid)
    assert fr.shape[1:] == (H, W) and 11 <= len(fr) <= 13
    an = F.analyse(fr)
    assert len(an.states) == 2
    out = tmp_path / "f.jpg"
    F.extract_jpeg(vid, 4.0, out)
    assert out.read_bytes()[:2] == b"\xff\xd8"
    assert F.probe_height(vid) == 360


# ═══════════════ ۵ — کارت نمودار و اعتبارسنج ═══════════════

def num(v, conf="high", how=None):
    d = {"value": v, "confidence": conf, "from": "image"}
    if how:
        d["how"] = how
    return d


def unread():
    return {"value": None, "confidence": None, "from": "image", "note": "ناخوانا"}


def card(**over) -> dict:
    c = {
        "frame_id": f"{VID}_00m07.0s", "t": 7.0, "is_chart": True,
        "refs": [{"doc": "DOC1", "row": 1, "time": "00:07", "role": "claim",
                  "strength": 3, "year_only": False, "claim_id": None}],
        "recorded_at": {"value": "2026-09-28T04:19:04+00:00", "seen": "05:19:04 UTC+1",
                        "confidence": "medium", "from": "image"},
        "coin": {"value": "BTC", "seen": "BTCUSD", "confidence": "high", "from": "image"},
        "venue": num("TradingView INDEX"), "timeframe": num("1W"),
        "chart_type": num("candles"), "scale": num("log"),
        "price_axis": {"top": num(144000), "bottom": num(39050)},
        "levels": [{"price": num(82000, "medium", "درون‌یابی لگاریتمی"), "kind": "horizontal",
                    "drawn_at": "بدنه"}],
        "trendlines": [{"p1": {"time": num("2025-09", "low"), "price": num(123000, "low")},
                        "p2": {"time": num("2026-07", "low"), "price": unread()}}],
        "zones": [], "patterns": [{"name": num("سقف بالاتر", "medium")}],
        "indicators": [{"name": num("میانگین متحرک"), "settings": [{"label": "دوره", "value": None,
                                                                  "confidence": None, "from": "image",
                                                                  "note": "ناخوانا"}]}],
        "texts": [{"text": "Bitcoin Falls Amid Concerns", "confidence": "high"}],
        "speech": "سقف بالاتر و بسته هفتگی بالای سقف مه؛ ۸۲.۸ هزار از حرف",
        "method_notes": ["سطح روی بدنه، فلش روی سایه"],
    }
    c.update(over)
    return c


def cards_doc(*cs) -> dict:
    return {"schema": 1, "kind": "radar-chart-cards", "video_id": VID, "doc_id": "DOC1",
            "cards": list(cs) or [card()]}


def test_valid_card_passes() -> None:
    assert F.validate_cards(cards_doc()) == []


def test_number_without_confidence_rejected() -> None:
    c = card(price_axis={"top": {"value": 144000, "from": "image"}, "bottom": num(39050)})
    errs = F.validate_cards(cards_doc(c))
    assert any("اطمینان" in e for e in errs)


def test_bare_number_rejected() -> None:
    c = card(levels=[{"price": 82000, "kind": "horizontal"}])
    errs = F.validate_cards(cards_doc(c))
    assert any("عدد بی‌اطمینان" in e for e in errs)


def test_null_needs_unreadable_label_and_no_confidence() -> None:
    errs = F.validate_cards(cards_doc(card(scale={"value": None, "confidence": None, "from": "image"})))
    assert any("ناخوانا" in e for e in errs)
    errs = F.validate_cards(cards_doc(card(scale={**unread(), "confidence": "low"})))
    assert any("null با اطمینان" in e for e in errs)


def test_number_from_speech_rejected() -> None:
    c = card(levels=[{"price": {"value": 82800, "confidence": "high", "from": "speech"},
                      "kind": "horizontal"}])
    errs = F.validate_cards(cards_doc(c))
    assert any("from باید" in e for e in errs)


def test_speech_must_be_plain_short_text() -> None:
    errs = F.validate_cards(cards_doc(card(speech={"value": 82800, "confidence": "high",
                                                   "from": "image"})))
    assert any("speech" in e for e in errs)
    errs = F.validate_cards(cards_doc(card(speech="x" * (F.SPEECH_MAX + 1))))
    assert any("سقف" in e for e in errs)
    errs = F.validate_cards(cards_doc(card(method_notes="یک یادداشت")))
    assert any("method_notes" in e for e in errs)


def test_recorded_at_needs_timezone() -> None:
    errs = F.validate_cards(cards_doc(card(recorded_at={
        "value": "2026-09-28T04:19:04", "confidence": "medium", "from": "image"})))
    assert any("بی‌منطقه" in e for e in errs)


def test_texts_need_confidence_and_cap() -> None:
    errs = F.validate_cards(cards_doc(card(texts=[{"text": "x" * (F.TEXT_MAX + 1)}])))
    assert any("سقف" in e for e in errs) and any("اطمینان" in e for e in errs)


def test_missing_field_rejected_and_not_chart_card_is_lighter() -> None:
    c = card()
    del c["scale"]
    assert any("scale" in e for e in F.validate_cards(cards_doc(c)))
    nc = {"frame_id": f"{VID}_00m07.0s", "t": 7.0, "is_chart": False, "refs": [],
          "texts": [], "speech": "فقط چهره گوینده", "method_notes": []}
    assert F.validate_cards(cards_doc(nc)) == []


def test_optional_claims_and_speech_vs_screen() -> None:
    """
    نشست ۶ب — گزارش ویدیو ادعا و ناهمخوانی حرف و صفحه را از کارت می‌خواند،
    نه از متن آزاد method_notes. هر دو اختیاری‌اند: کارت‌های نشست ۶ بی‌آن‌ها معتبرند.
    """
    ok = card(claims=["لانگ پس از شکست 2.474 — به گفته او"],
              speech_vs_screen={"agree": False, "note": "حرف از AVAX، صفحه MORPHO — د۱۳"})
    assert F.validate_cards(cards_doc(ok)) == []
    assert F.validate_cards(cards_doc(card(speech_vs_screen={"agree": None, "note": ""}))) == []
    assert F.validate_cards(cards_doc(card())) == []
    bad = [
        (card(claims="یک ادعا"), "claims"),
        (card(claims=["x" * (F.TEXT_MAX + 1)]), "claims"),
        (card(claims=[num(2.474)]), "claims"),
        (card(speech_vs_screen={"agree": 1, "note": ""}), "agree"),
        (card(speech_vs_screen={"agree": True}), "speech_vs_screen"),
        (card(speech_vs_screen={"agree": False, "note": "x" * (F.TEXT_MAX + 1)}), "note"),
    ]
    for c, word in bad:
        errs = F.validate_cards(cards_doc(c))
        assert any(word in e for e in errs), (word, errs)


def test_manifest_cross_check() -> None:
    man = {"frames": [{"frame_id": f"{VID}_00m07.0s", "t": 7.0},
                      {"frame_id": f"{VID}_00m20.0s", "t": 20.0}], "missing": []}
    errs = F.validate_cards(cards_doc(), man)
    assert any("فریم بی‌کارت" in e for e in errs)
    errs = F.validate_cards(cards_doc(card(frame_id=f"{VID}_09m09.0s")), man)
    assert any("در فهرست فریم‌ها نیست" in e for e in errs)
    errs = F.validate_cards(cards_doc(card(t=8.0)), {"frames": [{"frame_id": f"{VID}_00m07.0s",
                                                               "t": 7.0}], "missing": []})
    assert any("نمی‌خواند" in e for e in errs)


def test_template_is_rejected_until_filled(tmp_path) -> None:
    frames = seq([(view(k), 12) for k in range(1, 4)])
    _, man, _, _ = _run(tmp_path, frames, [])
    tpl = F.card_template(man)
    errs = F.validate_cards(tpl, man)
    assert any("template" in e for e in errs)
    assert len(tpl["cards"]) == len(man["frames"])
    for c in tpl["cards"]:          # نشست ۶ب — خواننده یادش بماند
        assert c["claims"] == [] and c["speech_vs_screen"] == {"agree": None, "note": ""}


def test_validate_cli(tmp_path) -> None:
    good = tmp_path / "good.json"
    good.write_text(json.dumps(cards_doc(), ensure_ascii=False), encoding="utf-8")
    assert F.main(["--validate", str(good), "--out", str(tmp_path / "frames")]) == 0
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(cards_doc(card(levels=[{"price": 1}])), ensure_ascii=False),
                   encoding="utf-8")
    assert F.main(["--validate", str(bad), "--out", str(tmp_path / "frames")]) == 2


def test_cli_rejects_zero_max_frames() -> None:
    with pytest.raises(SystemExit) as e:
        F.main(["x.md", "--max-frames", "0"])
    assert e.value.code == 2


# ═══════════════ ۶ — بهداشت مخزن ═══════════════

@pytest.mark.parametrize("path", ["frames/abc/x.jpg", "frames/abc/FRAMES.md", "FRAMES.md",
                                  "intake/benjamin_cowen/FRAMES.md"])
def test_frames_output_is_gitignored(path) -> None:
    r = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT)
    assert r.returncode == 0, f"{path} در .gitignore نیست"


def test_cards_are_not_gitignored() -> None:
    r = subprocess.run(["git", "check-ignore", "-q", "intake/charts/benjamin_cowen/x.json"], cwd=ROOT)
    assert r.returncode == 1


def test_no_ocr_and_no_pillow_in_code() -> None:
    """هیچ نویسه‌خوانی در کد — خواندن کار مدل است. Pillow هم لازم نشد — تأیید کاربر."""
    src = (ROOT / "radar_frames.py").read_text(encoding="utf-8")
    for bad in ("pytesseract", "easyocr", "paddleocr", "tesserocr", "import PIL",
                "from PIL", "import cv2", "imagehash"):
        assert bad not in src, bad


# ═══════════════ ۷ — نسخه، نشست ۶ب ═══════════════

# ثابت‌هایی که انتخاب لحظه را می‌سازند. تغییر هر کدام یعنی شناسه فریم دیگر
# بازتولید نمی‌شود، پس نسخه باید بالا برود — همین‌جا با هم ویرایش شوند.
SELECTION_VERSION = "1.1"
SELECTION = {
    "ANALYSIS_W": 320, "ANALYSIS_H": 180, "SAMPLE_FPS": 2, "PIX_DELTA": 25,
    "MASK_BLOCK": 10, "MASK_FREQ": 0.02, "MASK_MIN_CHANGES": 5, "QUIET_Q": 50,
    "MASK_WARN": 0.30, "STILL": 0.002, "MIN_STILL_SAMPLES": 3, "MERGE_DIFF": 0.003,
    "THUMB_W": 64, "THUMB_H": 36, "THUMB_DELTA": 12, "DUP_FRAC": 0.005,
    "SNAP_WINDOW": 3.0, "NEIGHBOR_WINDOW": 10.0, "TIER1_CAP": 12, "GAP_MAX": 120.0,
    "GAP_CAP": 3, "DEFAULT_MAX_FRAMES": 25, "SECTION_LEN": 2,
    "YEAR_MIN": 2009, "YEAR_AHEAD": 5,
}


def test_selection_constants_locked_to_version() -> None:
    """
    ماسک گام آرام (01197ac) انتخاب لحظه را عوض کرد ولی VERSION همان 1.0 ماند،
    پس هر دو فایل کارت «radar_frames 1.0» می‌گویند و مرز ماسک از برچسب پیدا
    نیست — رویداد ۵۹. حالا هر تغییر ثابت انتخاب بی‌بالا رفتن نسخه قرمز است.
    """
    assert F.VERSION == SELECTION_VERSION
    assert {k: getattr(F, k) for k in SELECTION} == SELECTION


def test_new_card_frames_tool_is_version(tmp_path) -> None:
    frames = seq([(view(k), 12) for k in range(1, 4)])
    _, man, _, _ = _run(tmp_path, frames, [])
    assert man["radar_frames"] == F.VERSION
    assert F.card_template(man)["frames_tool"] == f"radar_frames {F.VERSION}"
    md = (tmp_path / "frames" / VID / "FRAMES.md").read_text(encoding="utf-8")
    assert f"radar_frames {F.VERSION}" in md


@pytest.mark.parametrize("rel", ["benjamin_cowen/2C70_Ms3V9A.json",
                                 "cryptocity_pro/zN1RocH5VoU.json"])
def test_session6_cards_keep_their_tool_version(rel) -> None:
    """کارت‌های نشست ۶ با 1.0 ساخته شدند. برچسبشان تاریخ است، نه خطا — دست نمی‌خورد."""
    d = json.loads((ROOT / "intake" / "charts" / rel).read_text(encoding="utf-8"))
    assert d["frames_tool"] == "radar_frames 1.0"
