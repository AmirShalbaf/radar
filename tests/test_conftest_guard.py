"""
نگهبان tests/conftest.py و فرایند بیرونی — ک۶۴، نشست ۷.

درس رویداد ۶۱: نگهبان پیشین فایل داده تغییرکرده حین آزمون را برمی‌گرداند و
نوشتن هم‌زمان جلسه دیگر را پاک می‌کرد. قاعده تازه: آزمون‌ها روی رونوشت موقت
کار می‌کنند، و نگهبان فقط نوشتن خود فرایند آزمون روی فایل واقعی را قرمز
می‌کند — هرگز چیزی را برنمی‌گرداند.

روش: رونوشت عین conftest.py واقعی در مخزنی ساختگی، و یک اجرای درونی pytest
در زیرفرایند. ROOT نگهبان از جای خود فایل ساخته می‌شود، پس رونوشت همان مخزن
ساختگی را می‌پاید و فایل داده واقعی این مخزن هرگز لمس نمی‌شود.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

REAL_CONFTEST = Path(__file__).resolve().parent / "conftest.py"
ORIG = '{"orig": true}'


def fake_repo(tmp_path: Path, test_body: str, journal: bool = False) -> Path:
    root = tmp_path / "fake"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "conftest.py").write_bytes(REAL_CONFTEST.read_bytes())
    (root / "watch.json").write_text(ORIG, encoding="utf-8")
    (root / "radar_journal.json").write_text(ORIG, encoding="utf-8")
    if journal:
        # هم‌الگوی radar_journal.py واقعی: مسیر مطلق از جای خود فایل
        (root / "radar_journal.py").write_text(textwrap.dedent("""
            import os
            HERE = os.path.dirname(os.path.abspath(__file__))
            DB = os.path.join(HERE, "radar_journal.json")
            def save(text):
                with open(DB, "w", encoding="utf-8") as f:
                    f.write(text)
        """), encoding="utf-8")
    (root / "tests" / "test_inner.py").write_text(
        "import subprocess, sys\nfrom pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parent.parent\n\n" + textwrap.dedent(test_body),
        encoding="utf-8")
    return root


def run_inner(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
                          cwd=root, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120)


def test_external_process_write_survives(tmp_path):
    """فرایند بیرونی حین آزمون watch.json را می‌نویسد — نوشته‌اش سالم می‌ماند."""
    root = fake_repo(tmp_path, """
        def test_peer_writes_meanwhile():
            code = "open(r'%s', 'w', encoding='utf-8').write('external')" % (ROOT / "watch.json")
            subprocess.run([sys.executable, "-c", code], check=True)
    """)
    r = run_inner(root)
    assert (root / "watch.json").read_text(encoding="utf-8") == "external", r.stdout
    assert r.returncode == 0, r.stdout       # نوشتن فرایند دیگر خطای آزمون نیست


def test_in_process_write_is_red_and_not_reverted(tmp_path):
    """نوشتن خود آزمون روی فایل واقعی قرمز می‌شود، و برگردانده نمی‌شود."""
    root = fake_repo(tmp_path, """
        def test_bad():
            (ROOT / "watch.json").write_text("test wrote", encoding="utf-8")
    """)
    r = run_inner(root)
    assert r.returncode != 0, r.stdout
    assert "watch.json" in r.stdout
    assert (root / "watch.json").read_text(encoding="utf-8") == "test wrote"


def test_relative_default_path_writes_temp_copy(tmp_path):
    """مسیر پیش‌فرض نسبی به رونوشت موقت می‌رسد، نه به فایل واقعی."""
    root = fake_repo(tmp_path, """
        def test_default_path():
            p = Path("watch.json")
            assert p.read_text(encoding="utf-8") == '{"orig": true}'    # رونوشت
            p.write_text("copy only", encoding="utf-8")
            assert Path.cwd().resolve() != ROOT
    """)
    r = run_inner(root)
    assert r.returncode == 0, r.stdout
    assert (root / "watch.json").read_text(encoding="utf-8") == ORIG


def test_journal_absolute_default_goes_to_copy(tmp_path):
    """radar_journal.DB مسیر مطلق است — نگهبان آن را هم به رونوشت می‌برد."""
    root = fake_repo(tmp_path, """
        import radar_journal
        def test_journal_save():
            radar_journal.save("copy only")
            assert Path(radar_journal.DB).resolve() != (ROOT / "radar_journal.json").resolve()
    """, journal=True)
    r = run_inner(root)
    assert r.returncode == 0, r.stdout
    assert (root / "radar_journal.json").read_text(encoding="utf-8") == ORIG
