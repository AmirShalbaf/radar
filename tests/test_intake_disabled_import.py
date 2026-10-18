"""
ورود پوشه انتظار با منبع خاموش — نشست ۱۱، مرحله ۴، ک۵۶، تصمیم کاربر ۱۸ اکتبر ۲۰۲۶.

باب الیوت خاموش شد: در دو هفته ۳ تا ۱۷ اکتبر ۱۴ سند، همه «متن ناقص» — رویداد ۱۰۱.
۶ سند او در پوشه انتظار مانده بود و `--pick` روال ویدیو واردشان می‌کرد.

قرارداد:
- سند منبع خاموش وارد intake/<منبع>/ نمی‌شود؛ فقط فهرستش — تاریخ، عنوان، پیوند —
  در .state.json و INDEX.md.
- متن ناقص در intake/_local/ می‌ماند، بیرون از مخزن؛ شناسنامه در
  intake/_local/_disabled/<منبع>/. هیچ فایلی پاک نمی‌شود.
- منبع روشن مثل پیش وارد می‌شود.
- هر سه راه ورود — radar_intake.py --import-pending و دو گام صفر radar_video.py —
  منابع خاموش را از analysts.yml می‌دهند.
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_intake as I

ROOT = Path(__file__).resolve().parent.parent
UTC = timezone.utc
NOW = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
STAMP = "20261016T223003Z"
SECRET = "full preview text that must stay local"
OFF = {"bob_elliott": "باب الیوت"}

CONFIG = """sources:
  tekrargar:
    name_fa: "تکرارگر"
    role: "دفتر ادعاها"
    kind: "youtube"
    channel_id: "UCtttttttttttttttttttttt"
    lang: ["fa"]
    watch: "full"
  bob_elliott:
    name_fa: "باب الیوت"
    kind: "rss"
    url: "https://bobeunlimited.substack.com/feed"
    enabled: false
    disabled_reason: "همه سندها متن ناقص"
    watch: "text"
"""


def _doc(src: str, title: str, day: str, url: str) -> str:
    return (f"---\nمنبع: {src}\nعنوان: {title}\nنشانی: {url}\n"
            f"تاریخ انتشار: {day}T10:56:28Z\nمتن: ناقص — «Continue reading» — پیش‌نمایش\n---\n\n"
            "## نامزدهای ادعا\n")


def _pending(root: Path, stamp: str = STAMP, elliott=(("The Coastal Blindspot", "2026-10-16",
                                                      "the-coastal-blindspot"),)) -> Path:
    d = root / I.LOCAL_DIR / I.PENDING_DIR / stamp
    for title, day, slug in elliott:
        name = f"{day}_{slug}.md"
        (d / "bob_elliott").mkdir(parents=True, exist_ok=True)
        (d / "bob_elliott" / name).write_text(
            _doc("باب الیوت", title, day, f"https://bobeunlimited.substack.com/p/{slug}"),
            encoding="utf-8")
        (d / I.LOCAL_DIR / "bob_elliott").mkdir(parents=True, exist_ok=True)
        (d / I.LOCAL_DIR / "bob_elliott" / name).write_text(SECRET, encoding="utf-8")
    (d / "tekrargar").mkdir(parents=True, exist_ok=True)
    (d / "tekrargar" / "2026-10-16_tk.md").write_text(
        _doc("تکرارگر", "ویدیو", "2026-10-16", "https://www.youtube.com/watch?v=tk00000001a"),
        encoding="utf-8")
    (d / I.LOCAL_DIR / "tekrargar").mkdir(parents=True, exist_ok=True)
    (d / I.LOCAL_DIR / "tekrargar" / "2026-10-16_tk.md").write_text("local", encoding="utf-8")
    (d / ".state.json").write_text(json.dumps(
        {"seen": {"bob_elliott": {"fc402cd9": {"title": "The Coastal Blindspot"}}}}),
        encoding="utf-8")
    (d / I.RUN_FILE).write_text(json.dumps({"started": "2026-10-16 22:30 UTC", "exit_code": 0}),
                                encoding="utf-8")
    return d


@pytest.fixture
def intake(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "intake"
    root.mkdir()
    return root


def _import(root: Path, disabled=OFF):
    return I.import_pending(root, root / ".state.json", now=NOW, disabled=disabled)


ELLIOTT = "bob_elliott/2026-10-16_the-coastal-blindspot.md"


def test_disabled_doc_is_listed_not_imported(intake) -> None:
    d = _pending(intake)
    res = _import(intake)
    assert not (intake / "bob_elliott").exists()
    assert (intake / I.LOCAL_DIR / ELLIOTT).read_text(encoding="utf-8") == SECRET
    assert (intake / I.LOCAL_DIR / I.DISABLED_DIR / ELLIOTT).exists()
    assert (intake / "tekrargar" / "2026-10-16_tk.md").exists()        # منبع روشن مثل پیش
    want = {"source": "bob_elliott", "name_fa": "باب الیوت", "date": "2026-10-16",
            "title": "The Coastal Blindspot",
            "url": "https://bobeunlimited.substack.com/p/the-coastal-blindspot",
            "file": ELLIOTT, "stamp": STAMP}
    assert res.disabled == [want]
    st = json.loads((intake / ".state.json").read_text(encoding="utf-8"))
    assert st["disabled_docs"] == [want]
    (rec,) = st["imports"]
    assert rec["disabled_docs"] == [want]
    assert rec["docs"] == ["tekrargar/2026-10-16_tk.md"]
    assert "fc402cd9" in st["seen"]["bob_elliott"]                   # دوباره گرفته نمی‌شود
    assert not d.exists()                                           # پوشه انتظار خالی و برداشته


def test_index_lists_disabled_docs_without_a_doc_row(intake) -> None:
    _pending(intake)
    _import(intake)
    index = (intake / "INDEX.md").read_text(encoding="utf-8")
    assert "## سند منبع خاموش — وارد نشد" in index
    assert ("| 2026-10-16 | باب الیوت | The Coastal Blindspot | "
            "https://bobeunlimited.substack.com/p/the-coastal-blindspot |") in index
    assert "intake/_local/" in index
    assert f"`{ELLIOTT}`" not in index                               # ردیف سند نیست


def test_list_survives_later_index_rebuild(intake) -> None:
    _pending(intake)
    _import(intake)
    I.rebuild_index(intake)
    assert "The Coastal Blindspot" in (intake / "INDEX.md").read_text(encoding="utf-8")


def test_same_doc_twice_is_listed_once(intake) -> None:
    _pending(intake)
    _import(intake)
    _pending(intake, stamp="20261017T223003Z")
    # شناسنامه همان بایت‌ها — هم‌نام یکسان کنار می‌رود
    _import(intake)
    st = json.loads((intake / ".state.json").read_text(encoding="utf-8"))
    assert [x["file"] for x in st["disabled_docs"]] == [ELLIOTT]


def test_six_waiting_docs_all_listed(intake) -> None:
    docs = [(f"Post {i}", f"2026-10-1{i}", f"post-{i}") for i in range(1, 7)]
    _pending(intake, elliott=docs)
    res = _import(intake)
    assert len(res.disabled) == 6 and not (intake / "bob_elliott").exists()


def test_without_disabled_old_behaviour(intake) -> None:
    _pending(intake)
    res = I.import_pending(intake, intake / ".state.json", now=NOW)
    assert (intake / ELLIOTT).exists() and res.disabled == []


def test_disabled_shell_conflict_is_loud(intake) -> None:
    d = _pending(intake)
    clash = intake / I.LOCAL_DIR / I.DISABLED_DIR / ELLIOTT
    clash.parent.mkdir(parents=True)
    clash.write_text("نسخه دیگر", encoding="utf-8")
    with pytest.raises(I.ImportConflict):
        _import(intake)
    assert (d / ELLIOTT).exists()


def test_render_import_names_disabled_docs(intake) -> None:
    _pending(intake)
    lines = I.render_import(_import(intake))
    assert any("منبع خاموش" in x and "باب الیوت" in x and "The Coastal Blindspot" in x
               for x in lines)


def test_disabled_sources_from_config(tmp_path) -> None:
    cfg = tmp_path / "analysts.yml"
    cfg.write_text(CONFIG, encoding="utf-8")
    assert I.disabled_sources(I.load_sources(cfg)) == OFF


def test_main_import_pending_skips_disabled(intake) -> None:
    Path("analysts.yml").write_text(CONFIG, encoding="utf-8")
    _pending(intake)
    assert I.main(["--import-pending"], now=NOW) == 0
    assert not (intake / "bob_elliott").exists()
    assert (intake / "tekrargar" / "2026-10-16_tk.md").exists()


def test_video_import_calls_pass_disabled_sources() -> None:
    """هر دو گام صفر radar_video.py — --new و --pick — منابع خاموش را می‌دهند."""
    src = (ROOT / "radar_video.py").read_text(encoding="utf-8")
    calls = re.findall(r"I\.import_pending\([^)]*\)", src)
    assert len(calls) == 2
    assert all("disabled=" in c for c in calls)


def test_real_config_elliott_is_off() -> None:
    off = I.disabled_sources(I.load_sources(ROOT / "analysts.yml"))
    assert off["bob_elliott"] == "باب الیوت"
