"""
آزمون پوشه انتظار جمع‌آوری شبانه — نشست ۷ب، کار شش. بدون شبکه.

تصمیم کاربر، ایستگاه ۱ — ۴ اکتبر ۲۰۲۶:
  - کار شبانه `radar_intake.py --pending` فقط در intake/_local/_pending/<زمان>/ می‌نویسد،
    بیرون از مخزن. هیچ فایل ردیابی‌شده‌ای دست نمی‌خورد: درخت تمیز می‌ماند و با جلسه
    در حال کار برخورد نمی‌کند. هیچ دستور گیتی در کار شبانه نیست.
  - اول در <زمان>.partial، در پایان یک جابه‌جایی؛ نیمه‌کاره هرگز وارد نمی‌شود.
  - شکست منبع کد ۳ و در run.json همان پوشه — نه بی‌صدا.
  - ورود در روال روزانه: سندها جابه‌جا، دیده‌شده‌ها ادغام، INDEX با کارنامه شب، و رکورد
    ورود در .state.json برای خلاصه روزانه. فایل هم‌نام با محتوای دیگر خطای بلند است.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_intake as I

ROOT = Path(__file__).resolve().parent.parent
UTC = timezone.utc
T1 = datetime(2026, 10, 3, 22, 30, tzinfo=UTC)
T2 = datetime(2026, 10, 4, 22, 30, tzinfo=UTC)
SECRET = "full transcript sentence that must stay local"

CONFIG = """sources:
  tekrargar:
    name_fa: "تکرارگر"
    role: "دفتر ادعاها"
    kind: "youtube"
    channel_id: "UCtttttttttttttttttttttt"
    lang: ["fa"]
    watch: "full"
  raoul_pal:
    name_fa: "رایول پال"
    role: "لنز تحلیل‌گر"
    kind: "youtube"
    channel_id: "UCrrrrrrrrrrrrrrrrrrrrrr"
    lang: ["en"]
    watch: "text"
"""


class Net:
    """شبکه ساختگی: خوراک هر منبع و ثبت زیرنویس‌های گرفته‌شده."""

    def __init__(self):
        self.feeds: dict[str, list | Exception] = {}
        self.transcripts: list[str] = []
        self.unreachable: list[str] = []      # دلیل هر پیش‌سنجی ناموفق، به ترتیب
        self.probes: list[str] = []
        self.waits: list[float] = []

    def item(self, src, vid, day="2026-10-03"):
        self.feeds.setdefault(src, []).append(
            {"id": vid, "title": f"title {vid}", "url": f"https://www.youtube.com/watch?v={vid}",
             "published": f"{day}T10:00:00+00:00", "author": "x"})

    def install(self, mp):
        def fetch_items(src, session):
            f = self.feeds.get(src.key, [])
            if isinstance(f, Exception):
                raise f
            return list(f)

        def transcript(vid, langs):
            self.transcripts.append(vid)
            return [{"text": SECRET, "start": 0.0}, {"text": "bitcoin to 90000 by december", "start": 5.0}], "زیرنویس"

        def reachable(src, session):
            self.probes.append(src.key)
            return self.unreachable.pop(0) if self.unreachable else ""

        mp.setattr(I, "fetch_items", fetch_items)
        mp.setattr(I, "video_duration", lambda vid, s: (900, "itemprop"))
        mp.setattr(I, "fetch_transcript", transcript)
        mp.setattr(I, "make_session", lambda: object())
        mp.setattr(I, "missing_deps", lambda whisper: [])
        mp.setattr(I, "youtube_reachable", reachable)
        mp.setattr(I, "_wait", lambda s: self.waits.append(s))     # بی خواب واقعی


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "analysts.yml").write_text(CONFIG, encoding="utf-8")
    (tmp_path / "intake").mkdir()
    net = Net()
    net.install(monkeypatch)
    return net


def nightly(now=T1, extra=()) -> int:
    return I.main(["--pending", "--sleep", "0", *extra], now=now)


def pending() -> Path:
    return Path("intake", I.LOCAL_DIR, I.PENDING_DIR)


def snapshot() -> dict:
    """هر فایل بیرون از _local — همان چیزی که گیت می‌بیند."""
    return {p.as_posix(): p.read_bytes() for p in Path("intake").rglob("*")
            if p.is_file() and I.LOCAL_DIR not in p.parts}


# ═══════════════ کار شبانه ═══════════════

def test_nightly_touches_nothing_tracked(env) -> None:
    Path("intake", "INDEX.md").write_text("# پیشین\n", encoding="utf-8")
    Path("intake", ".state.json").write_text('{"seen": {}}', encoding="utf-8")
    before = snapshot()
    env.item("tekrargar", "tk00000001a")
    env.item("raoul_pal", "rp00000001a")
    assert nightly() == 0
    assert snapshot() == before                                  # درخت تمیز
    (d,) = pending().iterdir()
    assert d.name == "20261003T223000Z"
    assert len(list((d / "tekrargar").glob("*.md"))) == 1
    assert len(list((d / I.LOCAL_DIR / "raoul_pal").glob("*.md"))) == 1
    st = json.loads((d / ".state.json").read_text(encoding="utf-8"))
    assert set(st["seen"]) == {"tekrargar", "raoul_pal"}
    run = json.loads((d / I.RUN_FILE).read_text(encoding="utf-8"))
    assert run["exit_code"] == 0 and run["started"] == "2026-10-03 22:30 UTC"
    assert not list(pending().glob("*" + I.PARTIAL_SUFFIX))


def test_nightly_skips_what_main_and_earlier_pending_saw(env) -> None:
    Path("intake", ".state.json").write_text(json.dumps(
        {"seen": {"tekrargar": {"tk00000001a": {"title": "x"}}}}), encoding="utf-8")
    env.item("tekrargar", "tk00000001a")
    env.item("tekrargar", "tk00000002a")
    assert nightly(T1) == 0
    assert env.transcripts == ["tk00000002a"]
    env.item("tekrargar", "tk00000003a")
    assert nightly(T2) == 0                                       # پوشه شب قبل هنوز وارد نشده
    assert env.transcripts == ["tk00000002a", "tk00000003a"]


def test_nightly_source_failure_is_exit_3_and_recorded(env) -> None:
    env.feeds["tekrargar"] = I.SourceFailure("خوراک کانال خالی — وضعیت 404")
    env.item("raoul_pal", "rp00000001a")
    assert nightly() == 3
    (d,) = pending().iterdir()
    run = json.loads((d / I.RUN_FILE).read_text(encoding="utf-8"))
    assert run["exit_code"] == 3
    assert any("404" in s["failure"] for s in run["report"]["sources"])
    assert "404" in (d / "RUN.md").read_text(encoding="utf-8")


# ─────────── یوتیوب در دسترس نیست — تصمیم کاربر، ایستگاه ۲ ───────────
# مثلاً فیلترشکن هنوز وصل نشده: تا ۳ بار با فاصله ۲۰ دقیقه دوباره، بعد کد ۳ ثبت‌شده.

def test_unreachable_youtube_retries_three_times_then_exit_3(env) -> None:
    env.unreachable = ["ConnectTimeout"] * 4
    env.item("tekrargar", "tk00000001a")
    assert nightly() == 3
    assert len(env.probes) == 4 and env.waits == [1200, 1200, 1200]
    assert env.transcripts == []                                  # منبعی امتحان نشد
    (d,) = pending().iterdir()
    run = json.loads((d / I.RUN_FILE).read_text(encoding="utf-8"))
    assert run["exit_code"] == 3 and run["probe"]["attempts"] == 4
    fails = [s["failure"] for s in run["report"]["sources"] if s["failure"]]
    assert len(fails) == 1 and "یوتیوب" in fails[0] and "ConnectTimeout" in fails[0]
    res = I.import_pending(Path("intake"), Path("intake/.state.json"), now=T2)
    assert any("یوتیوب" in f for f in res.imported[0]["failures"])  # در خلاصه روزانه هم


def test_youtube_back_on_second_try_runs_normally(env) -> None:
    env.unreachable = ["ConnectionError"]
    env.item("tekrargar", "tk00000001a")
    assert nightly() == 0
    assert env.waits == [1200] and env.transcripts == ["tk00000001a"]
    (d,) = pending().iterdir()
    run = json.loads((d / I.RUN_FILE).read_text(encoding="utf-8"))
    assert run["probe"] == {"attempts": 2, "reasons": ["ConnectionError"]}


def test_reachable_first_time_waits_nothing(env) -> None:
    env.item("tekrargar", "tk00000001a")
    assert nightly() == 0
    assert env.probes == ["tekrargar"] and env.waits == []


def test_no_youtube_source_no_probe(env) -> None:
    Path("analysts.yml").write_text(CONFIG + """  bob_elliott:
    name_fa: "باب الیوت"
    kind: "rss"
    url: "https://example.com/feed"
    watch: "text"
""", encoding="utf-8")
    assert I.main(["--pending", "--sleep", "0", "--source", "bob_elliott"], now=T1) == 0
    assert env.probes == []


def test_pending_with_dry_run_is_refused(env) -> None:
    assert I.main(["--pending", "--dry-run"], now=T1) == 2
    assert not pending().exists()


# ═══════════════ ورود در روال روزانه ═══════════════

def test_import_moves_merges_rebuilds_and_records(env) -> None:
    env.item("tekrargar", "tk00000001a")
    env.feeds["raoul_pal"] = I.SourceFailure("یوتیوب مسدود کرد")
    assert nightly() == 3
    res = I.import_pending(Path("intake"), Path("intake/.state.json"), now=T2)
    assert [x["stamp"] for x in res.imported] == ["20261003T223000Z"]
    (doc,) = Path("intake", "tekrargar").glob("*.md")
    assert Path("intake", I.LOCAL_DIR, "tekrargar", doc.name).exists()
    assert SECRET not in doc.read_text(encoding="utf-8")
    st = json.loads(Path("intake/.state.json").read_text(encoding="utf-8"))
    assert "tk00000001a" in st["seen"]["tekrargar"]
    (rec,) = st["imports"]
    assert rec["at"] == "2026-10-04T22:30:00Z" and rec["exit_code"] == 3
    assert rec["docs"] == [doc.relative_to("intake").as_posix()]
    assert any("مسدود" in f for f in rec["failures"])
    index = Path("intake", "INDEX.md").read_text(encoding="utf-8")
    assert doc.name in index and "2026-10-03 22:30 UTC" in index and "مسدود" in index
    assert not any(pending().iterdir())                           # وارد و برداشته شد


def test_import_conflict_is_loud_and_keeps_everything(env) -> None:
    env.item("tekrargar", "tk00000001a")
    nightly()
    (d,) = pending().iterdir()
    (pdoc,) = (d / "tekrargar").glob("*.md")
    clash = Path("intake", "tekrargar", pdoc.name)
    clash.parent.mkdir(parents=True)
    clash.write_text("نسخه دیگر", encoding="utf-8")
    with pytest.raises(I.ImportConflict, match=pdoc.name):
        I.import_pending(Path("intake"), Path("intake/.state.json"), now=T2)
    assert clash.read_text(encoding="utf-8") == "نسخه دیگر"
    assert pdoc.exists()
    assert not Path("intake/.state.json").exists()


def test_import_identical_file_is_fine(env) -> None:
    env.item("tekrargar", "tk00000001a")
    nightly()
    (d,) = pending().iterdir()
    (pdoc,) = (d / "tekrargar").glob("*.md")
    same = Path("intake", "tekrargar", pdoc.name)
    same.parent.mkdir(parents=True)
    same.write_bytes(pdoc.read_bytes())
    res = I.import_pending(Path("intake"), Path("intake/.state.json"), now=T2)
    assert len(res.imported) == 1 and res.imported[0]["docs"] == []


def test_partial_is_never_imported_and_is_reported(env) -> None:
    part = pending() / ("20261003T223000Z" + I.PARTIAL_SUFFIX)
    (part / "tekrargar").mkdir(parents=True)
    (part / "tekrargar" / "x.md").write_text("نیمه", encoding="utf-8")
    res = I.import_pending(Path("intake"), Path("intake/.state.json"), now=T2)
    assert res.imported == [] and res.partial == [part.name]
    assert not Path("intake", "tekrargar").exists() and part.exists()


def test_import_cli(env, capsys) -> None:
    env.item("tekrargar", "tk00000001a")
    nightly()
    assert I.main(["--import-pending"], now=T2) == 0
    assert "20261003T223000Z" in capsys.readouterr().out


def test_nightly_cmd_is_ascii_and_runs_pending() -> None:
    raw = (ROOT / "radar_nightly.cmd").read_bytes()
    assert raw.isascii()                    # cmd فایل دسته‌ای UTF-8 را درست نمی‌خواند — کار سه
    txt = raw.decode("ascii")
    assert "radar_intake.py --pending" in txt and "pushd" in txt and "ERRORLEVEL" in txt
    assert "git" not in txt.lower()         # کار شبانه هیچ دستور گیتی ندارد
