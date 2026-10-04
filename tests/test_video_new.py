"""
آزمون radar_video.py --new — نشست ۷ب، کار دو. بدون شبکه.

خوراک، فراداده، زیرنویس و فریم تزریق می‌شوند. ساعت تزریق می‌شود — درس رویداد ۵۵:
آزمونی که داده‌اش ساعت ثابت دارد ولی کدش ساعت واقعی می‌خواند، بمب ساعتی است.

قواعد کاربر، ۳ و ۴ اکتبر ۲۰۲۶:
  - سقف روزی ۳ ویدیو، جزو آن پیشنهادها؛ مرز روز وقت جهانی.
  - ترتیب: اول صف پیشنهاد؛ بعد نوبت‌دهی — از هر منبع یکی، پیش از دومیِ هر منبع؛
    میان منابع تازه‌تر اول.
  - ویدیوی ۳ دقیقه یا کمتر کنار می‌رود و شمرده می‌شود — ف۸؛ سهمیه نمی‌گیرد.
  - ویدیوی منبع رصد بیش از ۷ روز پس از انتشار «کهنه» است، یک بار شمرده می‌شود؛
    پیشنهاد کاربر هرگز کهنه نمی‌شود.
  - دیده‌شده هرگز دوباره دیده نمی‌شود؛ بیش از سقف «ماند برای فردا»، نه رد بی‌صدا.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_frames as F
import radar_intake as I
import radar_video as V

UTC = timezone.utc
NOW = datetime(2026, 10, 4, 6, 0, tzinfo=UTC)
SECRET = "full transcript sentence that must stay local"

CID = {"cryptocity_pro": "UC" + "c" * 22, "tekrargar": "UC" + "t" * 22,
       "benjamin_cowen": "UC" + "b" * 22, "gareth_soloway": "UC" + "g" * 22,
       "raoul_pal": "UC" + "r" * 22}
STRANGER = "UC" + "z" * 22

CONFIG = f"""sources:
  cryptocity_pro:
    name_fa: "کریپتوسیتی پرو"
    role: "دفتر ادعاها"
    kind: "youtube"
    channel_id: "{CID['cryptocity_pro']}"
    lang: ["fa"]
    watch: "full"
  tekrargar:
    name_fa: "تکرارگر"
    role: "دفتر ادعاها"
    kind: "youtube"
    channel_id: "{CID['tekrargar']}"
    lang: ["fa"]
    watch: "full"
  benjamin_cowen:
    name_fa: "بنجامین کوون"
    role: "لنز تحلیل‌گر"
    kind: "youtube"
    channel_id: "{CID['benjamin_cowen']}"
    lang: ["en"]
    watch: "full"
  gareth_soloway:
    name_fa: "گرت سالووی"
    role: "لنز تحلیل‌گر"
    kind: "youtube"
    channel_id: "{CID['gareth_soloway']}"
    lang: ["en"]
    watch: "crypto_title"
    watch_keywords: [bitcoin, crypto]
  raoul_pal:
    name_fa: "رایول پال"
    role: "لنز تحلیل‌گر"
    kind: "youtube"
    channel_id: "{CID['raoul_pal']}"
    lang: ["en"]
    watch: "text"
"""


def vid(tag: str) -> str:
    """شناسه ۱۱ نویسه‌ای اسکی."""
    return (tag + "_" * 11)[:11]


def ago(hours: float) -> datetime:
    return NOW - timedelta(hours=hours)


# ═══════════════ ساختگی‌ها ═══════════════

@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("شبکه واقعی در آزمون صدا زده شد")
    monkeypatch.setattr(V.YtMeta, "_info", boom)
    monkeypatch.setattr(I, "fetch_youtube_items", boom)


class World:
    """یک جهان ساختگی: خوراک هر منبع، فراداده هر ویدیو، و ثبت فراخوان‌ها."""

    def __init__(self):
        self.feeds: dict[str, list | Exception] = {}
        self.videos: dict[str, dict] = {}
        self.blocked: set[str] = set()
        self.frames: list[str] = []
        self.meta_calls: list[str] = []

    def add(self, source: str | None, tag: str, published: datetime, *, dur=900,
            title: str | None = None, cid: str | None = None, in_feed: bool = True) -> str:
        v = vid(tag)
        cid = cid or (CID[source] if source else STRANGER)
        title = title or f"title {tag}"
        self.videos[v] = {"id": v, "title": title, "timestamp": int(published.timestamp()),
                          "duration": dur, "channel": "chan " + cid[-1], "channel_id": cid,
                          "uploader_id": "@x", "language": "en"}
        if source and in_feed:
            self.feeds.setdefault(source, []).append(
                {"id": v, "title": title, "url": f"https://www.youtube.com/watch?v={v}",
                 "published": published.isoformat(), "author": "x"})
        return v

    # Deps
    def feed(self, src):
        f = self.feeds.get(src.key, [])
        if isinstance(f, Exception):
            raise f
        return sorted(f, key=lambda i: i["published"], reverse=True)   # خوراک یوتیوب: تازه‌ترین اول

    def meta_video(self, v):
        self.meta_calls.append(v)
        if v in self.blocked:
            raise V.MetaError("yt-dlp: Sign in to confirm you're not a bot", blocked=True)
        return self.videos[v]

    def transcript(self, v, langs):
        return ([{"text": SECRET, "start": 0.0},
                 {"text": "bitcoin to 62000 by december", "start": 30.0}], "زیرنویس خودکار [en]")

    def make_frames(self, doc_path, out_root, max_frames):
        doc = F.load_doc(doc_path)
        self.frames.append(doc.video_id)
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

    def deps(self) -> V.Deps:
        meta = type("M", (), {"video": lambda _s, v: self.meta_video(v),
                              "playlist": lambda _s, p: {}})()
        return V.Deps(meta=meta, transcript=self.transcript, frames=self.make_frames,
                      missing=lambda *a: [], feed=self.feed)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "analysts.yml").write_text(CONFIG, encoding="utf-8")
    (tmp_path / "intake").mkdir()
    return tmp_path


def run_new(world: World, now: datetime = NOW, extra=()) -> int:
    return V.main(["--new", "--config", "analysts.yml", "--intake", "intake", "--frames", "frames",
                   *extra], deps=world.deps(), now=now)


def state() -> dict:
    return json.loads(Path("intake", V.VIDEO_STATE_NAME).read_text(encoding="utf-8"))


def suggest_file(v: str, queued_at: str, note: str = "") -> Path:
    """صف پیشنهاد — یک فایل برای هر ویدیو؛ نوشتنش کار --suggest است، کار سه."""
    d = Path("intake", I.LOCAL_DIR, V.SUGGEST_DIR)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{v}.json"
    p.write_text(json.dumps({"video_id": v, "url": f"https://www.youtube.com/watch?v={v}",
                             "queued_at": queued_at, "note": note}, ensure_ascii=False),
                 encoding="utf-8")
    return p


# ═══════════════ سقف و ترتیب ═══════════════

def test_cap_three_and_the_rest_wait_for_tomorrow(env, capsys) -> None:
    w = World()
    made = [w.add(s, f"{s[:2]}{i}", ago(10 * i + j)) for j, s in
            enumerate(["cryptocity_pro", "tekrargar", "benjamin_cowen"]) for i in (1, 2)]
    assert run_new(w) == 0
    assert len(w.frames) == 3
    out = capsys.readouterr().out
    assert "ماند برای فردا" in out
    st = state()
    assert sorted(v for v, e in st["videos"].items() if e["status"] == "ready") == sorted(w.frames)
    run = st["runs"][NOW.strftime("%Y-%m-%d")][-1]
    assert sorted(d["video_id"] for d in run["deferred"]) == sorted(set(made) - set(w.frames))
    for d in run["deferred"]:
        assert d["video_id"] in out


def test_round_robin_one_per_source_newest_source_first(env) -> None:
    w = World()
    c1 = w.add("cryptocity_pro", "c1", ago(1))
    w.add("cryptocity_pro", "c2", ago(2))
    w.add("cryptocity_pro", "c3", ago(3))
    t1 = w.add("tekrargar", "t1", ago(20))
    b1 = w.add("benjamin_cowen", "b1", ago(30))
    assert run_new(w) == 0
    assert w.frames == [c1, t1, b1]          # نه c2 پیش از دومیِ منابع دیگر


def test_second_round_is_newest_first_too(env) -> None:
    w = World()
    a1 = w.add("cryptocity_pro", "a1", ago(1))
    w.add("cryptocity_pro", "a2", ago(40))
    b1 = w.add("tekrargar", "b1", ago(2))
    b2 = w.add("tekrargar", "b2", ago(5))
    assert run_new(w) == 0
    assert w.frames == [a1, b1, b2]          # دور دوم: b2 تازه‌تر از a2


def test_cap_counts_across_runs_of_the_same_utc_day(env) -> None:
    w = World()
    for i in range(5):
        w.add("cryptocity_pro", f"c{i}", ago(i + 1))
    assert run_new(w) == 0 and len(w.frames) == 3
    assert run_new(w, NOW + timedelta(hours=3)) == 0 and len(w.frames) == 3     # همان روز
    assert run_new(w, NOW + timedelta(days=1)) == 0 and len(w.frames) == 5      # فردا


# ═══════════════ صف پیشنهاد ═══════════════

def test_queue_comes_first_and_is_labelled(env, capsys) -> None:
    w = World()
    for s in ("cryptocity_pro", "tekrargar", "benjamin_cowen"):
        w.add(s, s[:2], ago(1))
    q = w.add(None, "q1", ago(5))
    qf = suggest_file(q, "2026-10-03T20:00:00Z", note="یادداشت خصوصی")
    assert run_new(w) == 0
    assert w.frames[0] == q and len(w.frames) == 3
    out = capsys.readouterr().out
    assert "پیشنهاد امیر" in out
    assert "یادداشت خصوصی" not in json.dumps(state(), ensure_ascii=False)   # یادداشت عمومی نمی‌شود
    e = state()["videos"][q]
    assert e["suggested"] is True and e["status"] == "ready"
    assert not qf.exists()                                       # از صف رفت، نه پاک بی‌رد
    done = list(Path("intake", I.LOCAL_DIR, V.SUGGEST_DIR, "done").glob(f"{q}__*.json"))
    assert len(done) == 1
    rec = json.loads(done[0].read_text(encoding="utf-8"))
    assert rec["note"] == "یادداشت خصوصی" and rec["outcome"] == "ready"


def test_queue_is_fifo_and_counts_in_the_cap(env) -> None:
    w = World()
    w.add("cryptocity_pro", "c1", ago(1))
    qs = [w.add(None, f"q{i}", ago(5)) for i in range(4)]
    for i, q in enumerate(reversed(qs)):                         # q3 اول در صف
        suggest_file(q, f"2026-10-03T2{i}:00:00Z")
    assert run_new(w) == 0
    assert w.frames == [qs[3], qs[2], qs[1]]
    left = sorted(p.stem for p in Path("intake", I.LOCAL_DIR, V.SUGGEST_DIR).glob("*.json"))
    assert left == [qs[0]]                                       # در صف ماند، نه رد


def test_suggestion_is_never_stale(env) -> None:
    w = World()
    q = w.add(None, "old", NOW - timedelta(days=30))
    suggest_file(q, "2026-10-03T20:00:00Z")
    assert run_new(w) == 0
    assert w.frames == [q]


def test_watch_video_older_than_seven_days_is_stale_once(env, capsys) -> None:
    w = World()
    old = w.add("cryptocity_pro", "old", NOW - timedelta(days=7, hours=1))
    fresh = w.add("cryptocity_pro", "new", NOW - timedelta(days=6, hours=23))
    assert run_new(w) == 0
    assert w.frames == [fresh]
    out = capsys.readouterr().out
    assert "کهنه" in out and old in out
    assert state()["videos"][old]["status"] == "stale"
    assert run_new(w, NOW + timedelta(days=1)) == 0
    assert old not in capsys.readouterr().out                    # یک بار شمرده می‌شود
    assert w.frames == [fresh]


# ═══════════════ کوتاه، دیده‌شده، عنوان ═══════════════

def test_short_is_counted_and_takes_no_slot(env, capsys) -> None:
    w = World()
    s1 = w.add("cryptocity_pro", "s1", ago(1), dur=120)
    others = [w.add("cryptocity_pro", f"c{i}", ago(i + 2)) for i in range(3)]
    assert run_new(w) == 0
    assert w.frames == others
    assert state()["videos"][s1]["status"] == "short"
    assert state()["runs"][NOW.strftime("%Y-%m-%d")][-1]["short"] == [s1]
    assert "کوتاه" in capsys.readouterr().out


def test_short_known_from_intake_state_needs_no_metadata(env) -> None:
    w = World()
    s1 = w.add("tekrargar", "s1", ago(1), dur=120)
    Path("intake", ".state.json").write_text(json.dumps(
        {"seen": {"tekrargar": {s1: {"title": "x", "rejected": "کوتاه", "seconds": 120}}}}),
        encoding="utf-8")
    assert run_new(w) == 0
    assert s1 not in w.meta_calls
    assert state()["videos"][s1]["status"] == "short"


def test_seen_is_never_seen_again(env, capsys) -> None:
    w = World()
    a = w.add("cryptocity_pro", "a", ago(1))
    assert run_new(w) == 0 and w.frames == [a]
    capsys.readouterr()
    assert run_new(w, NOW + timedelta(days=1)) == 0
    assert w.frames == [a]                                       # دوباره ساخته نشد
    out = capsys.readouterr().out
    assert "آماده از پیش" in out and a in out                    # هنوز منتظر خواندن
    st = state()
    st["videos"][a]["status"] = "seen"
    Path("intake", V.VIDEO_STATE_NAME).write_text(json.dumps(st), encoding="utf-8")
    assert run_new(w, NOW + timedelta(days=2)) == 0
    assert w.frames == [a] and a not in capsys.readouterr().out


def test_existing_cards_block_without_state(env) -> None:
    """ویدیوی دیده‌شده پیش از ۷ب — کارتش هست، در فایل وضعیت نیست."""
    w = World()
    a = w.add("tekrargar", "a", ago(1))
    p = Path("intake", F.CHARTS_DIR.name, "tekrargar", f"{a}.json")
    p.parent.mkdir(parents=True)
    p.write_text("{}", encoding="utf-8")
    assert run_new(w) == 0
    assert w.frames == []


def test_crypto_title_filter_counts_off_topic_once(env, capsys) -> None:
    w = World()
    g = w.add("gareth_soloway", "g1", ago(1), title="Gold Rally Continues")
    b = w.add("gareth_soloway", "b1", ago(2), title="Bitcoin Breakout Now")
    assert run_new(w) == 0
    assert w.frames == [b]
    assert state()["videos"][g]["status"] == "off_topic"
    assert g in capsys.readouterr().out
    assert run_new(w, NOW + timedelta(days=1)) == 0
    assert g not in capsys.readouterr().out


def test_text_sources_are_never_fully_seen(env) -> None:
    w = World()
    w.add("raoul_pal", "r1", ago(1))
    assert run_new(w) == 0
    assert w.frames == []


# ═══════════════ خطای بلند ═══════════════

def test_feed_failure_is_loud_exit_3(env, capsys) -> None:
    w = World()
    w.feeds["tekrargar"] = I.SourceFailure("خوراک کانال خالی — وضعیت 404")
    a = w.add("cryptocity_pro", "a", ago(1))
    assert run_new(w) == 3
    assert w.frames == [a]
    out = capsys.readouterr().out
    assert "tekrargar" in out and "404" in out


def test_block_stops_and_lists_untried(env, capsys) -> None:
    w = World()
    q = w.add(None, "q", ago(1))
    qf = suggest_file(q, "2026-10-03T20:00:00Z")
    a = w.add("cryptocity_pro", "a", ago(1))
    w.blocked.add(q)
    assert run_new(w) == 3
    assert w.frames == [] and a not in w.meta_calls
    out = capsys.readouterr().out
    assert "مسدود" in out and a in out
    assert qf.exists()                                           # فردا دوباره
    assert q not in state()["videos"]


def test_corrupt_state_is_loud_and_kept(env, capsys) -> None:
    p = Path("intake", V.VIDEO_STATE_NAME)
    p.write_text("{garbage", encoding="utf-8")
    assert run_new(World()) == 2
    assert p.read_text(encoding="utf-8") == "{garbage"
    assert V.VIDEO_STATE_NAME in capsys.readouterr().err


def test_bad_watch_config_is_exit_2(env, capsys) -> None:
    Path("analysts.yml").write_text(CONFIG.replace('watch: "text"', 'watch: "maybe"'), encoding="utf-8")
    assert run_new(World()) == 2
    assert "maybe" in capsys.readouterr().err


def test_output_points_the_model_to_frames(env, capsys) -> None:
    w = World()
    a = w.add("benjamin_cowen", "a", ago(1))
    assert run_new(w) == 0
    out = capsys.readouterr().out
    assert f"frames/{a}/FRAMES.md" in out
    assert f"intake/charts/benjamin_cowen/{a}.json" in out
    assert "radar_history.py cards" in out and "--report" in out


def test_state_is_public_safe(env) -> None:
    w = World()
    w.add("cryptocity_pro", "a", ago(1))
    run_new(w)
    assert SECRET not in Path("intake", V.VIDEO_STATE_NAME).read_text(encoding="utf-8")


# ═══════════════ --report وضعیت را «دیده‌شده» می‌کند ═══════════════

def test_mark_seen_updates_or_creates_entry(env) -> None:
    p = Path("intake", V.VIDEO_STATE_NAME)
    cards = {"video_id": vid("a"), "source": "tekrargar", "title": "t"}
    V.mark_seen(p, cards, Path("intake/reports/tekrargar/a.md"), NOW)
    e = state()["videos"][vid("a")]
    assert (e["status"], e["seen_at"][:10], e["source"]) == ("seen", "2026-10-04", "tekrargar")
    st = state()
    st["videos"][vid("a")].update({"status": "ready", "suggested": True})
    p.write_text(json.dumps(st), encoding="utf-8")
    V.mark_seen(p, cards, Path("intake/reports/tekrargar/a.md"), NOW)
    e = state()["videos"][vid("a")]
    assert e["status"] == "seen" and e["suggested"] is True
