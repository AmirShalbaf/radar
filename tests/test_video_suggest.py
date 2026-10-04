"""
آزمون صف پیشنهاد radar_video.py --suggest — نشست ۷ب، کار سه. بدون شبکه.

تصمیم کاربر، ۳ و ۴ اکتبر ۲۰۲۶:
  - پیوند فوری در صف می‌رود؛ بی‌کار سنگین شبکه، بی‌مصرف سهمیه.
  - صف محلی و بیرون از مخزن — یادداشت کاربر به مخزن عمومی نمی‌رود.
  - یک فایل برای هر پیشنهاد، با ساخت انحصاری: دو نویسنده هم‌زمان هرگز نوشته هم را
    پاک نمی‌کنند و پیوند تکراری خودبه‌خود رد می‌شود — درس رویداد ۶۱.
  - پیوند تکراری یا ویدیوی دیده‌شده دوباره در صف نمی‌رود و پیام روشن می‌دهد.
  - کانالی که سه بار پیشنهاد شد، نامزد فهرست رصد است.
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_frames as F
import radar_intake as I
import radar_video as V

ROOT = Path(__file__).resolve().parent.parent
UTC = timezone.utc
NOW = datetime(2026, 10, 4, 6, 0, tzinfo=UTC)
VID = "abcDEF12_-z"
URL = f"https://www.youtube.com/watch?v={VID}"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("شبکه در --suggest صدا زده شد")
    monkeypatch.setattr(V.YtMeta, "_info", boom)
    monkeypatch.setattr(I, "fetch_youtube_items", boom)
    monkeypatch.setattr(I, "make_session", boom)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "intake").mkdir()
    return tmp_path


def suggest(link: str, note: str | None = None) -> int:
    argv = ["--suggest", link, "--intake", "intake"] + (["--note", note] if note is not None else [])
    return V.main(argv, now=NOW)


def qdir() -> Path:
    return Path("intake", I.LOCAL_DIR, V.SUGGEST_DIR)


def test_suggest_adds_one_file_without_network(env, capsys) -> None:
    assert suggest(URL, "حرفش درباره اتر جالب بود") == 0
    rec = json.loads((qdir() / f"{VID}.json").read_text(encoding="utf-8"))
    assert rec["video_id"] == VID and rec["url"] == URL
    assert rec["note"] == "حرفش درباره اتر جالب بود"
    assert rec["queued_at"] == "2026-10-04T06:00:00Z"
    assert "صف" in capsys.readouterr().out
    assert [c.video_id for c in V.read_queue(Path("intake"))] == [VID]     # همان قالب --new
    assert list(qdir().glob("*.tmp")) == []                                # فایل موقت نماند


def test_duplicate_in_queue_is_rejected_and_first_kept(env, capsys) -> None:
    assert suggest(URL, "اولی") == 0
    assert suggest(f"https://youtu.be/{VID}", "دومی") == 1
    assert "در صف هست" in capsys.readouterr().out
    rec = json.loads((qdir() / f"{VID}.json").read_text(encoding="utf-8"))
    assert rec["note"] == "اولی"


@pytest.mark.parametrize("status", ["seen", "ready", "short"])
def test_seen_video_is_rejected(env, capsys, status) -> None:
    Path("intake", V.VIDEO_STATE_NAME).write_text(json.dumps(
        {"videos": {VID: {"status": status, "source": "tekrargar"}}, "runs": {}}), encoding="utf-8")
    assert suggest(URL) == 1
    assert V.STATUS_FA[status] in capsys.readouterr().out
    assert not qdir().exists() or list(qdir().glob("*.json")) == []


@pytest.mark.parametrize("status", ["failed", "stale", "off_topic"])
def test_failed_stale_or_off_topic_can_be_suggested(env, status) -> None:
    """پیشنهاد کاربر درخواست صریح دیدن است — شکست، کهنه یا غیرکریپتویی را باز می‌کند."""
    Path("intake", V.VIDEO_STATE_NAME).write_text(json.dumps(
        {"videos": {VID: {"status": status, "source": "tekrargar"}}, "runs": {}}), encoding="utf-8")
    assert suggest(URL) == 0


def test_existing_cards_are_rejected(env, capsys) -> None:
    p = Path("intake", F.CHARTS_DIR.name, "tekrargar", f"{VID}.json")
    p.parent.mkdir(parents=True)
    p.write_text("{}", encoding="utf-8")
    assert suggest(URL) == 1
    assert "کارت" in capsys.readouterr().out


@pytest.mark.parametrize("outcome,rc", [("ready", 1), ("short", 1), ("پیشین — دیده‌شده", 1),
                                        ("failed", 0)])
def test_done_record_blocks_unless_failed(env, outcome, rc) -> None:
    d = qdir() / "done"
    d.mkdir(parents=True)
    (d / f"{VID}__20261003T200000Z.json").write_text(json.dumps(
        {"video_id": VID, "outcome": outcome}), encoding="utf-8")
    assert suggest(URL) == rc


@pytest.mark.parametrize("raw", ["https://www.youtube.com/playlist?list=PLabcdefghij0123456789",
                                 "https://www.youtube.com/@BenjaminCowen", "https://vimeo.com/1", ""])
def test_only_video_links(env, capsys, raw) -> None:
    assert suggest(raw) == 2
    assert not qdir().exists()


def test_note_needs_suggest(env) -> None:
    with pytest.raises(SystemExit):
        V.main(["--new", "--note", "x", "--intake", "intake"], now=NOW)


def test_corrupt_state_blocks_suggest_loudly(env, capsys) -> None:
    Path("intake", V.VIDEO_STATE_NAME).write_text("{bad", encoding="utf-8")
    assert suggest(URL) == 2
    assert not qdir().exists()


def test_queue_is_local_and_ignored_by_git() -> None:
    r = subprocess.run(["git", "check-ignore", "-q", f"intake/_local/{V.SUGGEST_DIR}/{VID}.json"],
                       cwd=ROOT)
    assert r.returncode == 0


# ─────────── دو نویسنده هم‌زمان ───────────

WRITER = r"""
import sys, time
from pathlib import Path
sys.path.insert(0, {root!r})
import radar_video as V
go = Path("go")
while not go.exists():
    time.sleep(0.01)
sys.exit(V.main(["--suggest", sys.argv[1], "--note", sys.argv[2], "--intake", "intake"]))
"""


def test_concurrent_writers_never_lose_or_duplicate(env) -> None:
    code = WRITER.format(root=str(ROOT))
    distinct = [f"https://youtu.be/w{i:02d}" + "_" * 8 for i in range(8)]
    same = [URL] * 6
    procs = [subprocess.Popen([sys.executable, "-c", code, link, f"note {i}"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
             for i, link in enumerate(distinct + same)]
    time.sleep(3)                     # همه فرایندها بالا آمده و منتظر علامت‌اند
    Path("go").write_text("1")
    rcs = [p.wait(timeout=120) for p in procs]
    errs = [p.stderr.read().decode("utf-8", "replace") for p in procs]
    assert rcs[:8] == [0] * 8, errs
    assert sorted(rcs[8:]) == [0, 1, 1, 1, 1, 1], errs
    files = sorted(p.stem for p in qdir().glob("*.json"))
    assert files == sorted([V.parse_link(x).video_id for x in distinct] + [VID])
    for f in qdir().glob("*.json"):
        json.loads(f.read_text(encoding="utf-8"))               # هیچ فایل نیمه‌نوشته‌ای نیست
    assert list(qdir().glob("*.tmp")) == []


# ─────────── نامزد فهرست رصد ───────────

def test_channel_suggested_three_times_is_a_candidate() -> None:
    def e(cid, name="Chan", src=None, sug=True, status="seen"):
        return {"source": src or V.SINGLE_PREFIX + cid, "channel_id": cid, "channel": name,
                "suggested": sug, "status": status}
    a, b, k = "UC" + "a" * 22, "UC" + "b" * 22, "UC" + "k" * 22
    vs = {"videos": {
        "v1_________": e(a, "Alpha"), "v2_________": e(a, "Alpha", status="short"),
        "v3_________": e(a, "Alpha", status="ready"),
        "v4_________": e(b), "v5_________": e(b),
        "v6_________": e(b, sug=False),                                   # از خوراک، نه پیشنهاد
        "v7_________": e(k, src="tekrargar"), "v8_________": e(k, src="tekrargar"),
        "v9_________": e(k, src="tekrargar"),                             # منبع شناخته — نامزد نیست
    }}
    got = V.channel_candidates(vs)
    assert [(c["channel_id"], c["channel"], c["count"]) for c in got] == [(a, "Alpha", 3)]


def test_suggest_cmd_wraps_the_command() -> None:
    raw = (ROOT / "suggest.cmd").read_bytes()
    # cmd فایل دسته‌ای UTF-8 را درست نمی‌خواند: سطر توضیح فارسی در اجرای واقعی ایستگاه
    # کار سه به «'�' is not recognized» شکست. پس فقط اسکی؛ توضیح در CLAUDE.md و radar_video.
    assert raw.isascii()
    txt = raw.decode("ascii")
    assert "radar_video.py --suggest %*" in txt
    assert "pushd" in txt and "popd" in txt and "ERRORLEVEL" in txt
