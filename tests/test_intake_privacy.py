"""
آزمون چیدمان «متن کامل فقط محلی» — نشست ۴، بند «ز»، تصمیم ۶ و ۷ کاربر.

مخزن عمومی است. متن کامل مقاله و زیرنویس منابع دیگر — وانگ، کایکو،
یوتیوبرها — نباید در آن برود. قاعده، یکی برای همه منابع، دوره ارشیا هم:
- عمومی: intake/<src>/<name>.md — شناسنامه، پیوند، حداکثر ۱۰ خط نامزد
  ادعا، هر خط حداکثر ۲۰۰ نویسه، با زمان ویدیو.
- محلی: intake/_local/<src>/<name>.md — سند کامل؛ در .gitignore.
- ۹ فایل موجود دوره ارشیا دست نمی‌خورند — دوره رایگان است.
- radar_digest متن محلی را جفت می‌کند، سند بی‌متن را نمی‌شمارد و شمارش را
  صریح می‌گوید. سند ناخوانا را هم دیگر بی‌صدا نمی‌اندازد — خط ۲۱۲ پیشین.
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_digest as DG
import radar_intake as I

ROOT = Path(__file__).resolve().parent.parent
SECRET = "the full transcript sentence nobody else may publish"


def _src() -> I.Source:
    return I.Source(key="alpha", name_fa="منبع الف", kind="youtube",
                    channel_id="UCaaaaaaaaaaaaaaaaaaaaaa")


def _item() -> dict:
    return {"id": "abcdefghijk", "title": "عنوان", "url": "https://www.youtube.com/watch?v=abcdefghijk",
            "published": "2026-09-29", "author": "x"}


def _cands(n: int, text_len: int = 300) -> list:
    return [I.ClaimCandidate(index=i + 1, timestamp=f"00:{i:02d}", text=("x" * text_len),
                             categories=["سطح"], numbers=["62000"], strength=(i % 5) + 1)
            for i in range(n)]


def _table_rows(doc: str) -> list[str]:
    return [l for l in doc.splitlines() if l.startswith("| ") and not l.startswith("| #")]


# ═══════════════════ سند عمومی و محلی ═══════════════════

def test_public_has_no_full_text() -> None:
    segs = [{"text": SECRET, "start": 5.0}]
    pub, full = I.build_documents(_src(), _item(), segs, "زیرنویس خودکار [en]", [],
                                  local_rel="_local/alpha/x.md")
    assert SECRET not in pub and "## متن کامل" not in pub
    assert SECRET in full and "## متن کامل" in full
    assert "_local/alpha/x.md" in pub


def test_public_caps_rows_and_chars() -> None:
    pub, full = I.build_documents(_src(), _item(), [{"text": "t", "start": 1.0}], "m",
                                  _cands(15), local_rel="_local/alpha/x.md")
    rows = _table_rows(pub)
    assert len(rows) == I.PUBLIC_MAX_CANDIDATES == 10
    for r in rows:
        assert len(r.split("|")[-2].strip()) <= I.PUBLIC_MAX_CHARS == 200
    assert len(_table_rows(full)) == 15


def test_public_keeps_the_strongest() -> None:
    pub, _ = I.build_documents(_src(), _item(), [{"text": "t", "start": 1.0}], "m",
                               _cands(15), local_rel="_local/alpha/x.md")
    stars = [r.split("|")[3].strip().count("★") for r in _table_rows(pub)]
    # قدرت ۱ تا ۵ هر کدام سه بار: ده‌تای برتر = سه ۵، سه ۴، سه ۳، و نخستین ۲
    assert sorted(stars, reverse=True) == [5, 5, 5, 4, 4, 4, 3, 3, 3, 2]


def test_public_still_has_timestamps_and_front_matter() -> None:
    pub, _ = I.build_documents(_src(), _item(), [{"text": "t", "start": 1.0}], "m",
                               _cands(3), local_rel="_local/alpha/x.md")
    meta = I._front_matter(pub)
    assert meta["نشانی"].startswith("https://www.youtube.com/")
    assert meta["نامزد ادعا"] == "3"
    assert "00:0" in pub


# ═══════════════════ اجرای کامل ═══════════════════

@pytest.fixture
def env(tmp_path, monkeypatch):
    cfg = tmp_path / "analysts.yml"
    cfg.write_text("sources:\n  alpha:\n    name_fa: \"منبع الف\"\n    kind: \"youtube\"\n"
                   "    channel_id: \"UCaaaaaaaaaaaaaaaaaaaaaa\"\n", encoding="utf-8")
    out = tmp_path / "intake"
    monkeypatch.setattr(I, "_has_module", lambda m: True)
    monkeypatch.setattr(I, "make_session", lambda: object())
    monkeypatch.setattr(I, "video_duration", lambda vid, s: (600, "آزمون"))
    monkeypatch.setattr(I, "fetch_youtube_items", lambda s, ss: [_item()])
    # جمله محرمانه نامزد ادعا نیست؛ نامزد — با سقف — عمداً در سند عمومی می‌آید
    segs = [{"text": SECRET, "start": 5.0},
            {"text": "hello there friends", "start": 9.0},
            {"text": "good morning everyone", "start": 12.0},
            {"text": "thanks for watching today", "start": 15.0},
            {"text": "bitcoin will hit 62000 by next week", "start": 60.0}]
    monkeypatch.setattr(I, "fetch_transcript", lambda v, l: (segs, "زیرنویس خودکار [en]"))
    rc = I.main(["--config", str(cfg), "--out", str(out), "--state",
                 str(out / ".state.json"), "--sleep", "0"])
    return {"out": out, "rc": rc}


def test_run_writes_public_and_local_pair(env) -> None:
    assert env["rc"] == 0
    pub = list((env["out"] / "alpha").glob("*.md"))
    loc = list((env["out"] / I.LOCAL_DIR / "alpha").glob("*.md"))
    assert len(pub) == len(loc) == 1 and pub[0].name == loc[0].name
    public = pub[0].read_text(encoding="utf-8")
    assert SECRET not in public and "hello there" not in public
    # نامزد با زمان ویدیو — زمان آغاز پنجره لغزان سه‌قطعه‌ای، یعنی 00:12
    assert "62000" in public and "| 00:12 |" in public
    assert SECRET in loc[0].read_text(encoding="utf-8")


def test_index_does_not_list_local_copies(env) -> None:
    idx = (env["out"] / "INDEX.md").read_text(encoding="utf-8")
    assert "تعداد سند: 1" in idx
    assert "_local" not in idx.split("## اسناد")[1]


def test_local_dir_is_gitignored() -> None:
    def ignored(p: str) -> bool:
        r = subprocess.run(["git", "check-ignore", "-q", p], cwd=ROOT)
        assert r.returncode in (0, 1), r
        return r.returncode == 0
    assert ignored("intake/_local/alpha/2026-09-29_x_abcdef.md")
    assert not ignored("intake/alpha/2026-09-29_x_abcdef.md")
    assert not ignored("intake/INDEX.md")


def test_existing_arshia_files_stay_full() -> None:
    """۹ فایل موجود دوره دست نمی‌خورند — تصمیم پیشین کاربر."""
    files = sorted((ROOT / "intake" / "arshia_course").glob("*.md"))
    assert len(files) == 9
    for f in files:
        assert "## متن کامل" in f.read_text(encoding="utf-8"), f.name


def test_write_documents_is_the_single_writer(tmp_path) -> None:
    """
    نشست ۶ب: radar_video هم سند می‌سازد. نام فایل و چیدمان عمومی و محلی فقط در
    write_documents است — متنی که در دو جا نوشته شود، از هم جدا می‌افتد (رویداد ۲۲).
    """
    item = {**_item(), "published": "2026-09-29T05:23:15+00:00"}
    segs = [{"text": SECRET, "start": 5.0}, {"text": "bitcoin to 62000 by december", "start": 9.0}]
    fname, n, date = I.write_documents(_src(), item, segs, "زیرنویس", tmp_path, duration="12:00")
    assert date == "2026-09-29" and fname == "2026-09-29_عنوان_abcdef.md"
    public = (tmp_path / "alpha" / fname).read_text(encoding="utf-8")
    local = (tmp_path / I.LOCAL_DIR / "alpha" / fname).read_text(encoding="utf-8")
    assert SECRET not in public and SECRET in local
    assert "مدت: 12:00" in public and f"نامزد ادعا: {n}" in public


# ═══════════════════ radar_digest ═══════════════════

def test_digest_and_intake_agree_on_local_dir() -> None:
    """radar_digest بی‌وابستگی به radar_intake هم باید اجرا شود؛ پس نام تکرار شده."""
    assert DG.LOCAL_DIR == I.LOCAL_DIR


def test_digest_and_intake_agree_on_reports_dir() -> None:
    assert DG.REPORTS_DIR == I.REPORTS_DIR == "reports"


def test_digest_skips_video_reports(tmp_path) -> None:
    """نشست ۶ب: گزارش ویدیو سند نیست؛ «بی‌متن محلی» هم شمرده نمی‌شود."""
    (tmp_path / "reports" / "a").mkdir(parents=True)
    (tmp_path / "reports" / "a" / "v.md").write_text("# گزارش ویدیو\n", encoding="utf-8")
    docs, rep = DG.load_docs(tmp_path, None)
    assert docs == [] and rep.no_local == [] and rep.unreadable == []

def _stub(title: str) -> str:
    return (f"---\nمنبع: الف\nجایگاه در رادار: کتابخانه روش\nعنوان: {title}\n"
            f"تاریخ انتشار: 2026-09-29\n---\n\n## نامزدهای ادعا\n\n"
            f"| 1 | 00:05 | ★★ | جهت | — | solana bullish in table |\n")


def _full(body: str) -> str:
    return _stub("x") + "\n---\n\n## متن کامل\n\n" + body + "\n"


def test_digest_reads_local_text_for_stub(tmp_path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / I.LOCAL_DIR / "a").mkdir(parents=True)
    (tmp_path / "a" / "x.md").write_text(_stub("x"), encoding="utf-8")
    (tmp_path / I.LOCAL_DIR / "a" / "x.md").write_text(_full("[00:05] bitcoin is bullish"),
                                                       encoding="utf-8")
    docs, rep = DG.load_docs(tmp_path, None)
    assert len(docs) == 1 and "bitcoin is bullish" in docs[0].body
    assert "solana" not in docs[0].body
    assert rep.no_local == [] and rep.unreadable == []


def test_digest_does_not_count_stub_without_local_text(tmp_path) -> None:
    """پیش از این جدول نامزدها جای متن خوانده می‌شد و گزارش بی‌صدا عوض می‌شد."""
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.md").write_text(_stub("x"), encoding="utf-8")
    docs, rep = DG.load_docs(tmp_path, None)
    assert docs == []
    assert rep.no_local == ["a/x.md"]


def test_digest_legacy_full_doc_still_counts(tmp_path) -> None:
    (tmp_path / "arshia_course").mkdir()
    (tmp_path / "arshia_course" / "p1.md").write_text(_full("[00:01] اگر بیت کوین 124 هزار بشکند"),
                                                      encoding="utf-8")
    docs, rep = DG.load_docs(tmp_path, None)
    assert len(docs) == 1 and "124" in docs[0].body


def test_digest_does_not_double_count_local(tmp_path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / I.LOCAL_DIR / "a").mkdir(parents=True)
    (tmp_path / "a" / "x.md").write_text(_stub("x"), encoding="utf-8")
    (tmp_path / I.LOCAL_DIR / "a" / "x.md").write_text(_full("body"), encoding="utf-8")
    docs, _ = DG.load_docs(tmp_path, None)
    assert len(docs) == 1


def test_digest_unreadable_doc_is_reported(tmp_path) -> None:
    """خط ۲۱۲ پیشین: except Exception: continue — سند بی‌صدا می‌افتاد."""
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "bad.md").write_bytes(b"\xff\xfe\xfa")
    docs, rep = DG.load_docs(tmp_path, None)
    assert docs == [] and rep.unreadable and "a/bad.md" in rep.unreadable[0]


def test_digest_main_states_counts_and_fails_on_unreadable(tmp_path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / I.LOCAL_DIR / "a").mkdir(parents=True)
    (tmp_path / "a" / "x.md").write_text(_stub("x"), encoding="utf-8")
    (tmp_path / I.LOCAL_DIR / "a" / "x.md").write_text(_full("bitcoin bullish"), encoding="utf-8")
    (tmp_path / "a" / "y.md").write_text(_stub("y"), encoding="utf-8")
    (tmp_path / "a" / "bad.md").write_bytes(b"\xff\xfe")
    out = tmp_path / "DIGEST.md"
    rc = DG.main(["--intake", str(tmp_path), "--out", str(out)])
    text = out.read_text(encoding="utf-8")
    assert rc == 3
    assert "بی‌متن محلی" in text and "a/y.md" in text
    assert "ناخوانا" in text and "a/bad.md" in text
