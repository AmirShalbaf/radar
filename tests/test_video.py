"""
آزمون radar_video.py — نشست ۶ب. بدون شبکه.

فراداده، زیرنویس و فریم تزریق می‌شوند؛ yt-dlp واقعی در این آزمون‌ها
صدا زده نمی‌شود و نگهبان پایین اگر شد قرمزش می‌کند. سند با سازنده واقعی
radar_intake.write_documents ساخته و با radar_frames.load_doc واقعی خوانده
می‌شود، تا ناسازگاری قالب اینجا قرمز شود نه در اجرای واقعی.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_frames as F
import radar_intake as I
import radar_video as V

ROOT = Path(__file__).resolve().parent.parent
VID = "abcDEF12_-z"
PL = "PLabcdefghij0123456789"
COURSE = "PLcourse000000000000"
COWEN = "UCRvqjQPSeaWn-uEx-w0XOIg"
STRANGER = "UCzzzzzzzzzzzzzzzzzzzzzz"
SECRET = "full transcript sentence that must stay local"

CONFIG = f"""sources:
  benjamin_cowen:
    name_fa: "بنجامین کوون"
    name_en: "Benjamin Cowen"
    role: "لنز تحلیل‌گر"
    kind: "youtube"
    channel_id: "{COWEN}"
    lang: ["en"]
    scores: true
  arshia_course:
    name_fa: "دوره ارشیا"
    role: "کتابخانه روش"
    kind: "playlist"
    playlist_id: "{COURSE}"
    lang: ["fa"]
"""


# ═══════════════ سازنده‌های ساختگی ═══════════════

@pytest.fixture(autouse=True)
def _no_real_ytdlp(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("yt-dlp واقعی در آزمون صدا زده شد")
    monkeypatch.setattr(V.YtMeta, "_info", boom)


def info(vid: str, *, cid: str = STRANGER, dur=900, title: str | None = None) -> dict:
    return {"id": vid, "title": title or f"عنوان {vid}", "timestamp": 1759300000,
            "duration": dur, "channel": "Stranger Charts", "channel_id": cid,
            "uploader_id": "@stranger", "language": "en"}


class FakeMeta:
    def __init__(self, videos=None, playlists=None, blocked=()):
        self.videos = videos or {}
        self.playlists = playlists or {}
        self.blocked = set(blocked)
        self.calls = []

    def video(self, vid):
        self.calls.append(("video", vid))
        if vid in self.blocked:
            raise V.MetaError("yt-dlp: Sign in to confirm you're not a bot", blocked=True)
        return self.videos[vid]

    def playlist(self, pid):
        self.calls.append(("playlist", pid))
        return self.playlists[pid]


class Calls:
    def __init__(self):
        self.transcript = []
        self.frames = []

    def fake_transcript(self, vid, langs):
        self.transcript.append((vid, list(langs)))
        return ([{"text": SECRET, "start": 0.0},
                 {"text": "bitcoin to 62000 by december", "start": 30.0}], "زیرنویس خودکار [en]")

    def fake_frames(self, doc_path, out_root, max_frames):
        self.frames.append((Path(doc_path).as_posix(), max_frames))
        doc = F.load_doc(doc_path)                       # خواننده واقعی radar_frames
        vdir = Path(out_root) / doc.video_id
        vdir.mkdir(parents=True, exist_ok=True)
        fid = F.frame_id(doc.video_id, 30.0)
        man = {"schema": 1, "radar_frames": F.VERSION, "video_id": doc.video_id,
               "doc_id": doc.doc_id, "doc": doc.public_rel, "source": doc.source, "url": doc.url,
               "title": doc.title, "analysis": {"mask_warning": False},
               "selection": {"unframed_candidates": []}, "missing": [],
               "frames": [{"frame_id": fid, "t": 30.0, "file": fid + ".jpg", "refs": []}]}
        (vdir / "frames.json").write_text(json.dumps(man, ensure_ascii=False), encoding="utf-8")
        (vdir / "FRAMES.md").write_text(f"# {SECRET}\n", encoding="utf-8")
        return man, 0


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "analysts.yml").write_text(CONFIG, encoding="utf-8")
    (tmp_path / "intake").mkdir()
    return tmp_path


def run(argv, meta, calls=None, whisper=None):
    calls = calls or Calls()
    deps = V.Deps(meta=meta, transcript=calls.fake_transcript, frames=calls.fake_frames,
                  whisper=whisper, missing=lambda *a: [])
    rc = V.main(argv + ["--config", "analysts.yml", "--intake", "intake", "--frames", "frames"],
                deps=deps)
    return rc, calls


def make_done(vid: str, key: str = V.SINGLE_PREFIX + STRANGER, frames: bool = True) -> Path:
    """قسمت پیشین: سند عمومی و محلی، و اگر خواستی فهرست فریم."""
    src = I.Source(key=key, name_fa="x", kind="youtube")
    item = V.item_from_info(info(vid))
    fname, _, _ = I.write_documents(src, item, Calls().fake_transcript(vid, ["en"])[0], "زیرنویس",
                                    Path("intake"), duration="15:00")
    if frames:
        (Path("frames") / vid).mkdir(parents=True)
        (Path("frames") / vid / "frames.json").write_text('{"frames": [{}, {}]}', encoding="utf-8")
    return Path("intake") / key / fname


def front(path: Path) -> dict:
    return I._front_matter(path.read_text(encoding="utf-8"))


# ═══════════════ ۱ — پیوند، بی‌شبکه ═══════════════

@pytest.mark.parametrize("raw", [
    f"https://www.youtube.com/watch?v={VID}",
    f"https://youtube.com/watch?v={VID}&t=120s",
    f"https://m.youtube.com/watch?v={VID}",
    f"https://youtu.be/{VID}?si=xyz",
    f"youtu.be/{VID}",
    f"https://www.youtube.com/shorts/{VID}",
    f"https://www.youtube.com/live/{VID}",
    f"https://www.youtube.com/embed/{VID}",
    f"  {VID}  ",
])
def test_video_links(raw) -> None:
    link = V.parse_link(raw)
    assert (link.kind, link.video_id, link.playlist_id, link.note) == ("video", VID, "", "")


@pytest.mark.parametrize("raw", [
    f"https://www.youtube.com/playlist?list={PL}",
    f"https://youtube.com/playlist?list={PL}&si=abc",
    f"www.youtube.com/playlist/?list={PL}",
    PL,
])
def test_playlist_links(raw) -> None:
    link = V.parse_link(raw)
    assert (link.kind, link.playlist_id) == ("playlist", PL)
    assert link.url == f"https://www.youtube.com/playlist?list={PL}"


def test_video_inside_playlist_is_the_video_with_a_note() -> None:
    """کاربر روی همان قسمت بود؛ کل پلی‌لیست فقط با پیوند خود پلی‌لیست."""
    link = V.parse_link(f"https://www.youtube.com/watch?v={VID}&list={PL}&index=3")
    assert link.kind == "video" and link.video_id == VID
    assert f"playlist?list={PL}" in link.note
    assert link.playlist_id == PL           # منبع پلی‌لیست شناخته‌شده از همین می‌آید


def test_auto_mix_is_never_a_playlist() -> None:
    link = V.parse_link(f"https://www.youtube.com/watch?v={VID}&list=RD{VID}")
    assert link.kind == "video" and link.note == ""
    with pytest.raises(V.LinkError):
        V.parse_link("https://www.youtube.com/playlist?list=RDabc123def")


@pytest.mark.parametrize("raw", [
    "https://www.youtube.com/@BenjaminCowen",
    f"https://www.youtube.com/channel/{COWEN}",
    "https://vimeo.com/123456789",
    "https://www.youtube.com/playlist",
    "۱۲۳۴۵۶۷۸۹۰۱",                      # ۱۱ رقم فارسی — تله \d
    "سلام دنیا!!",
    "",
])
def test_rejected_links(raw) -> None:
    with pytest.raises(V.LinkError):
        V.parse_link(raw)


def test_bad_link_exit_2(env, capsys) -> None:
    rc, calls = run(["https://www.youtube.com/@BenjaminCowen"], FakeMeta())
    assert rc == 2 and "کانال" in capsys.readouterr().err
    assert calls.transcript == [] and calls.frames == []


# ═══════════════ ۲ — پلی‌لیست ═══════════════

def _playlist(*specs) -> dict:
    """specs: (شناسه، مدت). ترتیب همان ترتیب پلی‌لیست است."""
    return {"title": "دوره آزمایشی", "channel": "Stranger Charts",
            "entries": [{"id": v, "title": f"قسمت {v}", "duration": d} for v, d in specs]}


def test_playlist_without_limit_lists_in_order_and_stops(env, capsys) -> None:
    ids = ["aaaaaaaaaa1", "bbbbbbbbbb2", "cccccccccc3", "dddddddddd4"]
    make_done(ids[3])
    before = sorted(p.as_posix() for p in Path(".").rglob("*"))
    meta = FakeMeta(playlists={PL: _playlist((ids[0], 900), (ids[1], 60), (ids[2], None),
                                             (ids[3], 1200))})
    rc, calls = run([f"https://www.youtube.com/playlist?list={PL}"], meta)
    out = capsys.readouterr().out
    assert rc == 0
    assert meta.calls == [("playlist", PL)]                 # هیچ فراداده ویدیو
    assert calls.transcript == [] and calls.frames == []
    assert sorted(p.as_posix() for p in Path(".").rglob("*")) == before   # هیچ فایلی
    rows = [l for l in out.splitlines() if l.startswith("| 0")]
    assert [r.split("|")[1].strip() for r in rows] == ["01", "02", "03", "04"]
    assert ids[0] in rows[0] and "تازه" in rows[0]
    assert "کوتاه" in rows[1] and "مدت نامعلوم" in rows[2] and "پیشین" in rows[3]
    assert "هیچ فایلی نوشته نشد" in out and "## برآورد" in out
    assert "| قسمت تازه | 2 |" in out                       # تازه و مدت نامعلوم
    assert "| مدت کل قسمت‌های تازه با مدت معلوم | 15:00 |" in out
    assert "حدود 4 دقیقه" in out                             # ۰.۲۲ × ۹۰۰ + ۱۵ = ۲۱۳ ثانیه
    assert "--limit N" in out


def test_playlist_limit_takes_new_episodes_in_order(env) -> None:
    ids = ["aaaaaaaaaa1", "bbbbbbbbbb2", "cccccccccc3", "dddddddddd4", "eeeeeeeeee5"]
    make_done(ids[1])
    meta = FakeMeta(videos={v: info(v) for v in ids},
                    playlists={PL: _playlist((ids[0], 900), (ids[1], 900), (ids[2], 90),
                                             (ids[3], 900), (ids[4], 900))})
    rc, calls = run([PL, "--limit", "2"], meta)
    assert rc == 0
    assert [c for c in meta.calls if c[0] == "video"] == [("video", ids[0]), ("video", ids[3])]
    titles = sorted(front(p)["عنوان"] for p in Path("intake").glob("single_*/*.md"))
    assert [x for x in titles if x.startswith("[")] == [f"[01] عنوان {ids[0]}",
                                                        f"[04] عنوان {ids[3]}"]
    assert len(calls.frames) == 2


def test_playlist_source_from_analysts_wins(env) -> None:
    meta = FakeMeta(videos={"aaaaaaaaaa1": info("aaaaaaaaaa1")},
                    playlists={COURSE: _playlist(("aaaaaaaaaa1", 900))})
    rc, _ = run([f"https://www.youtube.com/playlist?list={COURSE}", "--limit", "1"], meta)
    assert rc == 0
    docs = list(Path("intake/arshia_course").glob("*.md"))
    assert len(docs) == 1 and front(docs[0])["جایگاه در رادار"] == "کتابخانه روش"


def test_video_link_of_known_playlist_takes_its_source_and_position(env) -> None:
    """
    نشست ۶ب، پیوند آزمایشی کاربر: ویدیوی دوره با &list= منبع arshia_course و شماره
    قسمتش را می‌گیرد — «پارت ۳» بدون شماره در فهرست گم می‌شود.
    """
    other = "aaaaaaaaaa1"
    meta = FakeMeta(videos={VID: info(VID)},
                    playlists={COURSE: _playlist((other, 900), (VID, 900))})
    rc, _ = run([f"https://www.youtube.com/watch?v={VID}&list={COURSE}"], meta)
    assert rc == 0
    docs = list(Path("intake/arshia_course").glob("*.md"))
    assert len(docs) == 1 and front(docs[0])["عنوان"] == f"[02] عنوان {VID}"
    assert ("video", other) not in meta.calls


def test_video_link_of_unknown_playlist_resolves_by_channel(env) -> None:
    meta = FakeMeta(videos={VID: info(VID)})
    rc, _ = run([f"https://www.youtube.com/watch?v={VID}&list={PL}"], meta)
    assert rc == 0 and meta.calls == [("video", VID)]          # پلی‌لیست ناشناخته خوانده نشد
    assert list(Path("intake", V.SINGLE_PREFIX + STRANGER).glob("*.md"))


def test_video_not_in_the_named_playlist_is_loud(env, capsys) -> None:
    meta = FakeMeta(videos={VID: info(VID)},
                    playlists={COURSE: _playlist(("aaaaaaaaaa1", 900))})
    rc, _ = run([f"https://www.youtube.com/watch?v={VID}&list={COURSE}"], meta)
    assert rc == 0 and "در پلی‌لیست" in capsys.readouterr().out
    assert not list(Path("intake").glob("arshia_course/*.md"))   # منبع از کانال، نه دوره


def legacy_doc(vid: str, n: int) -> Path:
    """سند دوره پیش از نشست ۴: متن کامل در خود سند عمومی، بی‌نسخه محلی."""
    p = Path("intake/arshia_course") / f"2026-08-09_{n:02d}-قسمت_{vid[:6]}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nعنوان: [{n:02d}] قسمت\nنشانی: https://www.youtube.com/watch?v={vid}\n"
                 f"ساخته‌شده با: radar_intake 1.3\n---\n\n## متن کامل\n\n[00:01] {SECRET}\n",
                 encoding="utf-8")
    return p


def test_legacy_full_doc_is_never_refetched_or_duplicated(env, capsys) -> None:
    """۹ فایل دوره ارشیا متن کامل را در خود دارند. پیش از رفع، نبود نسخه محلی
    «دوباره گرفته می‌شود» می‌خواند و سند دوم با نام دیگر می‌ساخت."""
    old = legacy_doc(VID, 1)
    before = old.read_bytes()
    rc, calls = run([VID], FakeMeta({VID: info(VID)}))
    out = capsys.readouterr().out
    assert calls.transcript == [] and calls.frames == []
    assert old.read_bytes() == before
    assert sorted(Path("intake").rglob("*.md")) == [old]          # هیچ سند دومی
    assert "سند قدیمی" in out and rc == 0


def test_legacy_episodes_count_as_done_in_playlist(env, capsys) -> None:
    ids = ["aaaaaaaaaa1", "bbbbbbbbbb2", "cccccccccc3"]
    legacy_doc(ids[0], 1)
    legacy_doc(ids[1], 2)
    meta = FakeMeta(videos={v: info(v) for v in ids},
                    playlists={COURSE: _playlist(*((v, 900) for v in ids))})
    rc, _ = run([COURSE], meta)
    rows = [l for l in capsys.readouterr().out.splitlines() if l.startswith("| 0")]
    assert "پیشین" in rows[0] and "پیشین" in rows[1] and "تازه" in rows[2]
    rc, calls = run([COURSE, "--limit", "1"], meta)
    assert rc == 0 and [c for c in meta.calls if c[0] == "video"] == [("video", ids[2])]
    assert len(calls.frames) == 1


def test_block_stops_the_playlist_loudly(env, capsys) -> None:
    ids = ["aaaaaaaaaa1", "bbbbbbbbbb2", "cccccccccc3"]
    meta = FakeMeta(videos={v: info(v) for v in ids}, blocked={ids[1]},
                    playlists={PL: _playlist(*((v, 900) for v in ids))})
    rc, calls = run([PL, "--limit", "3"], meta)
    out = capsys.readouterr().out
    assert rc == 3
    assert ("video", ids[2]) not in meta.calls
    assert "مسدود" in out and "امتحان نشد" in out and "03" in out
    assert len(calls.frames) == 1                           # قسمت ۱ دیده شد


# ═══════════════ ۳ — منبع ═══════════════

def test_unknown_channel_is_single_video_without_vote(env, capsys) -> None:
    cfg = (env / "analysts.yml").read_bytes()
    rc, calls = run([f"https://youtu.be/{VID}", "--max-frames", "7"], FakeMeta({VID: info(VID)}))
    out = capsys.readouterr().out
    assert rc == 0
    pub = next(Path("intake", V.SINGLE_PREFIX + STRANGER).glob("*.md"))
    meta = front(pub)
    assert meta["جایگاه در رادار"] == V.SINGLE_ROLE
    assert meta["حق امتیازدهی"].startswith("ندارد")
    assert (env / "analysts.yml").read_bytes() == cfg       # analysts.yml فقط با تأیید کاربر
    assert "کانال ناشناخته — پیشنهاد، نه ثبت" in out and f'channel_id: "{STRANGER}"' in out
    assert calls.frames == [(pub.as_posix(), 7)]
    state = json.loads(Path("intake/.state.json").read_text(encoding="utf-8"))
    assert VID in state["seen"][V.SINGLE_PREFIX + STRANGER]
    assert pub.name in Path("intake/INDEX.md").read_text(encoding="utf-8")


def test_known_channel_uses_its_analysts_source(env, capsys) -> None:
    rc, calls = run([VID], FakeMeta({VID: info(VID, cid=COWEN)}))
    out = capsys.readouterr().out
    assert rc == 0
    pub = next(Path("intake/benjamin_cowen").glob("*.md"))
    assert front(pub)["جایگاه در رادار"] == "لنز تحلیل‌گر"
    assert calls.transcript == [(VID, ["en"])]
    assert "پیشنهاد" not in out


def test_full_text_and_frames_stay_local(env) -> None:
    run([VID], FakeMeta({VID: info(VID)}))
    pub = next(Path("intake", V.SINGLE_PREFIX + STRANGER).glob("*.md"))
    local = Path("intake", I.LOCAL_DIR) / pub.relative_to("intake")
    assert SECRET not in pub.read_text(encoding="utf-8")
    assert SECRET in local.read_text(encoding="utf-8")
    tpl = json.loads(Path("frames", VID, "card_template.json").read_text(encoding="utf-8"))
    assert tpl["frames_tool"] == f"radar_frames {F.VERSION}"
    assert tpl["cards"][0]["claims"] == []


@pytest.mark.parametrize("path, ignored", [
    ("intake/_local/single_UCx/x.md", True),
    ("frames/abc/card_template.json", True),
    ("intake/reports/single_UCx/abc.md", False),
    ("intake/single_UCx/x.md", False),
])
def test_what_is_public(path, ignored) -> None:
    r = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT)
    assert (r.returncode == 0) is ignored, path


# ═══════════════ ۴ — بازاستفاده، هیچ‌چیز بی‌صدا بازنویسی نمی‌شود ═══════════════

def test_existing_doc_is_reused(env) -> None:
    pub = make_done(VID, frames=False)
    rc, calls = run([VID], FakeMeta({VID: info(VID)}))
    assert rc == 0 and calls.transcript == []
    assert calls.frames == [(pub.as_posix(), F.DEFAULT_MAX_FRAMES)]


def test_existing_frames_need_force(env, capsys) -> None:
    make_done(VID)
    rc, calls = run([VID], FakeMeta({VID: info(VID)}))
    assert rc == 0 and calls.frames == []
    assert "پیشین — فریم هست" in capsys.readouterr().out
    rc, calls = run([VID, "--force"], FakeMeta({VID: info(VID)}))
    assert rc == 0 and len(calls.frames) == 1


def test_cards_block_frames_even_with_force(env, capsys) -> None:
    """درس رویداد ۵۹: فریم تازه شناسه‌های کارت را از فهرست جدا می‌کند."""
    pub = make_done(VID)
    cards = Path("intake", F.CHARTS_DIR.name, pub.parent.name, f"{VID}.json")
    cards.parent.mkdir(parents=True)
    cards.write_text("{}", encoding="utf-8")
    rc, calls = run([VID, "--force"], FakeMeta({VID: info(VID)}))
    assert rc == 0 and calls.frames == []
    assert "پیشین — کارت هست" in capsys.readouterr().out


def test_short_video_is_rejected_not_failed(env, capsys) -> None:
    rc, calls = run([VID], FakeMeta({VID: info(VID, dur=150)}))
    assert rc == 0 and calls.transcript == [] and calls.frames == []
    assert "رد شد — کوتاه" in capsys.readouterr().out
    assert not list(Path("intake").glob("single_*"))


def test_no_transcript_fails_loudly_unless_whisper(env, capsys) -> None:
    calls = Calls()
    calls.fake_transcript = lambda vid, langs: ([], "زیرنویس ندارد")
    rc, _ = run([VID], FakeMeta({VID: info(VID)}), calls)
    assert rc == 3 and "بی‌زیرنویس" in capsys.readouterr().out
    assert calls.frames == []
    whisper = lambda url: ([{"text": "spoken words", "start": 1.0}], "رونویسی ویسپر [en]")
    rc, _ = run([VID], FakeMeta({VID: info(VID)}), calls, whisper=whisper)
    assert rc == 0 and len(calls.frames) == 1


def test_transcript_block_is_exit_3(env, capsys) -> None:
    calls = Calls()

    def blocked(vid, langs):
        raise I.TranscriptBlocked("مسدود (RequestBlocked)")
    calls.fake_transcript = blocked
    rc, _ = run([VID], FakeMeta({VID: info(VID)}), calls)
    assert rc == 3 and "مسدود" in capsys.readouterr().out


# ═══════════════ ۵ — گزارش ویدیو ═══════════════

def num(v, conf="high"):
    return {"value": v, "confidence": conf, "from": "image"}


def unread():
    return {"value": None, "confidence": None, "from": "image", "note": "ناخوانا"}


def chart(t, **over) -> dict:
    c = {"frame_id": F.frame_id(VID, t), "t": t, "is_chart": True,
         "refs": [{"doc": "D", "row": 5, "time": F.fmt_t(t), "role": "claim", "strength": 3,
                   "year_only": False, "claim_id": None}],
         "recorded_at": {"value": "2026-10-01T08:00:00+00:00", "confidence": "medium", "from": "image"},
         "coin": num("BTC"), "venue": unread(), "timeframe": num("1W"), "chart_type": num("candles"),
         "scale": num("log"), "price_axis": {"top": num(144000), "bottom": num(39050)},
         "levels": [{"price": num(82111.82), "kind": "horizontal", "label": "خط آبی",
                     "drawn_at": num("بدنه", "medium")}],
         "trendlines": [{"p1": {"time": num("2025-09", "low"), "price": num(123000, "low")},
                         "p2": {"time": num("2026-07", "low"), "price": unread()},
                         "kind": "projection"}],
         "zones": [{"low": num(2.566), "high": num(2.665), "label": "ابزار موقعیت"}],
         "patterns": [{"name": num("سقف بالاتر", "medium")}], "indicators": [{"name": num("RSI")}],
         "texts": [], "speech": SECRET, "method_notes": ["سطح را از بدنه کشید"],
         "claims": ["لانگ پس از بسته هفتگی بالای 82,111 — به گفته او"],
         "speech_vs_screen": {"agree": True, "note": ""}}
    c.update(over)
    return c


def report_cards() -> dict:
    c2 = chart(75.0, levels=[{"price": num(82111.82), "kind": "horizontal", "label": "خط آبی",
                              "drawn_at": num("بدنه", "medium")},
                             {"price": num(59.61, "medium"), "kind": "horizontal", "unit": "%"}],
               trendlines=[], zones=[], claims=[],
               speech_vs_screen={"agree": False, "note": "حرف از AVAX، صفحه MORPHO — د۱۳"})
    c3 = {"frame_id": F.frame_id(VID, 90.0), "t": 90.0, "is_chart": False, "refs": [],
          "texts": [], "speech": SECRET, "method_notes": []}
    c4 = chart(120.0, coin=num("ARB"), timeframe=num("1h"), levels=[{"price": num(0.209),
               "kind": "horizontal"}], trendlines=[], zones=[], claims=[],
               speech_vs_screen={"agree": None, "note": "نماد حرف روی صفحه نبود"})
    return {"schema": 1, "kind": "radar-chart-cards", "video_id": VID, "doc_id": "D",
            "doc": "intake/single_UCx/doc.md", "source": "single_UCx", "url": f"https://youtu.be/{VID}",
            "title": "عنوان ویدیو", "read_by": "مدل", "read_at": "2026-10-03",
            "frames_tool": "radar_frames 1.1", "cards": [chart(69.0), c2, c3, c4]}


def test_report_format() -> None:
    cards = report_cards()
    assert F.validate_cards(cards) == []
    meta = {"منبع": "Stranger Charts", "جایگاه در رادار": V.SINGLE_ROLE,
            "تاریخ انتشار": "2026-10-01T08:00:00Z", "مدت": "15:00"}
    rep = V.render_report(cards, meta)
    heads = [l for l in rep.splitlines() if l.startswith("#")]
    assert heads == ["# گزارش ویدیو — عنوان ویدیو", "## نمودارها",
                     "## سطح‌ها و خط‌ها — هر عدد از تصویر", "## روش",
                     "## ادعاها — به بیان ما، نه نقل", "## حرف و صفحه"]
    assert SECRET not in rep                                # حرف گوینده نقل نمی‌شود
    assert "تک‌ویدیو — بدون حق رأی" in rep
    assert "| 2026-10-01 |" in rep and "| 15:00 |" in rep
    assert "| 01:09 تا 01:15 | BTC | 1W | log | 2 |" in rep  # دو کارت پیاپی یک نما
    assert "| 02:00 | ARB | 1h | log | 1 |" in rep
    assert "فریم غیرنمودار: 1 — 01:30" in rep
    assert "| 01:09 (×2) | BTC | سطح افقی | 82,111.82 | بالا | خط آبی، روی بدنه |" in rep
    assert "| 01:15 | BTC | سطح افقی | 59.61% | متوسط |" in rep
    assert "| 02:00 | ARB | سطح افقی | 0.209 | بالا |" in rep
    assert "| ناحیه | 2.566 تا 2.665 | بالا | ابزار موقعیت |" in rep
    assert "| مسیر پیش‌بینی | 123,000 تا ناخوانا | پایین |" in rep
    assert "- اندیکاتورها: RSI" in rep and "- الگوهای نام‌برده: سقف بالاتر" in rep
    assert rep.count("- سطح را از بدنه کشید") == 1          # تکراری یک بار
    assert "| 01:09 | BTC | 5 | لانگ پس از بسته هفتگی بالای 82,111 — به گفته او |" in rep
    assert "| 1 | 1 | 1 |" in rep
    assert "- 01:15 — صفحه BTC: حرف از AVAX، صفحه MORPHO — د۱۳" in rep


def test_report_of_session6_cards_says_fields_missing() -> None:
    """کارت‌های نشست ۶ claims و speech_vs_screen ندارند — گزارش صریح می‌گوید، نه خالی."""
    cards = report_cards()
    for c in cards["cards"]:
        c.pop("claims", None)
        c.pop("speech_vs_screen", None)
    rep = V.render_report(cards, {})
    assert "میدان `claims` ندارند" in rep and "میدان `speech_vs_screen` ندارند" in rep


def test_report_cli_writes_public_report_only_from_valid_cards(env, capsys) -> None:
    cards = report_cards()
    p = Path("intake/charts/single_UCx") / f"{VID}.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
    assert V.main(["--report", p.as_posix(), "--intake", "intake", "--frames", "frames"]) == 0
    out = Path("intake", I.REPORTS_DIR, "single_UCx", f"{VID}.md")
    assert out.read_text(encoding="utf-8").startswith("# گزارش ویدیو — عنوان ویدیو")
    cards["cards"][0]["levels"] = [{"price": 82111.82, "kind": "horizontal"}]   # عدد بی‌اطمینان
    p.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
    out.unlink()
    assert V.main(["--report", p.as_posix(), "--intake", "intake", "--frames", "frames"]) == 2
    assert not out.exists() and "کارت نامعتبر" in capsys.readouterr().err
