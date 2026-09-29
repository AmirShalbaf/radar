"""
آزمون ترتیب و بازسازی INDEX — نشست ۴، ایستگاه ۲، تصمیم کاربر ۲۹ سپتامبر ۲۰۲۶.

یافته ایستگاه ۲: ۹ سند دوره ارشیا تاریخ انتشار ندارند و خانه تاریخشان «—»
است. مرتب‌سازی نزولی رشته‌ای «—» را بالای رقم‌ها می‌گذاشت، پس سندهای
بی‌تاریخ بالای سندهای تازه می‌نشستند. حالا سند بی‌تاریخ پایین فهرست است.

بازسازی INDEX بدون اجرا — مثلاً پس از همین رفع — کارنامه آخرین اجرا را
پاک نمی‌کند؛ از INDEX موجود نگهش می‌دارد.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_intake as I


def _doc(title: str, date: str | None) -> str:
    d = f"تاریخ انتشار: {date}\n" if date else "تاریخ انتشار: \n"
    return f"---\nمنبع: الف\nجایگاه در رادار: لنز\nعنوان: {title}\n{d}نامزد ادعا: 1\n---\n\nمتن\n"


def _doc_rows(out: Path) -> list[str]:
    body = (out / "INDEX.md").read_text(encoding="utf-8").split("## اسناد", 1)[1]
    return [l for l in body.splitlines() if l.startswith("| ") and not l.startswith("| تاریخ")]


def test_undated_docs_sort_last(tmp_path) -> None:
    out = tmp_path / "intake"
    (out / "a").mkdir(parents=True)
    (out / "a" / "old.md").write_text(_doc("قدیمی", "2026-09-10"), encoding="utf-8")
    (out / "a" / "nodate2.md").write_text(_doc("[02] بی‌تاریخ", None), encoding="utf-8")
    (out / "a" / "nodate1.md").write_text(_doc("[01] بی‌تاریخ", None), encoding="utf-8")
    (out / "a" / "new.md").write_text(_doc("تازه", "2026-09-29"), encoding="utf-8")
    I.rebuild_index(out)
    rows = _doc_rows(out)
    assert [r.split("|")[1].strip() for r in rows] == ["2026-09-29", "2026-09-10", "—", "—"]
    # بی‌تاریخ‌ها به ترتیب نام فایل — ترتیب قسمت‌های دوره
    assert "nodate1.md" in rows[2] and "nodate2.md" in rows[3]


def test_unreadable_doc_also_sorts_last(tmp_path) -> None:
    out = tmp_path / "intake"
    (out / "a").mkdir(parents=True)
    (out / "a" / "bad.md").write_bytes(b"\xff\xfe")
    (out / "a" / "new.md").write_text(_doc("تازه", "2026-09-29"), encoding="utf-8")
    I.rebuild_index(out)
    rows = _doc_rows(out)
    assert "new.md" in rows[0] and "bad.md" in rows[1]


def test_reindex_keeps_last_run_section(tmp_path) -> None:
    out = tmp_path / "intake"
    (out / "a").mkdir(parents=True)
    (out / "a" / "x.md").write_text(_doc("یک", "2026-09-29"), encoding="utf-8")
    run = I.RunReport(started="2026-09-29 21:16 UTC",
                      sources=[I.SourceRun("a", "منبع الف", made=3, short=14)])
    I.rebuild_index(out, run)
    (out / "a" / "y.md").write_text(_doc("دو", "2026-09-28"), encoding="utf-8")
    I.rebuild_index(out)
    idx = (out / "INDEX.md").read_text(encoding="utf-8")
    assert "## آخرین اجرا — 2026-09-29 21:16 UTC" in idx
    assert "| منبع الف | 3 | 14 |" in idx
    assert "تعداد سند: 2" in idx
    assert idx.count("## آخرین اجرا") == 1


def test_fresh_reindex_has_no_run_section(tmp_path) -> None:
    out = tmp_path / "intake"
    (out / "a").mkdir(parents=True)
    (out / "a" / "x.md").write_text(_doc("یک", "2026-09-29"), encoding="utf-8")
    I.rebuild_index(out)
    assert "## آخرین اجرا" not in (out / "INDEX.md").read_text(encoding="utf-8")


def test_new_run_replaces_old_section(tmp_path) -> None:
    out = tmp_path / "intake"
    out.mkdir()
    I.rebuild_index(out, I.RunReport(started="2026-09-28 10:00 UTC"))
    I.rebuild_index(out, I.RunReport(started="2026-09-29 21:16 UTC"))
    idx = (out / "INDEX.md").read_text(encoding="utf-8")
    assert "2026-09-28 10:00" not in idx and "2026-09-29 21:16" in idx
