"""
مسیر گزارش چرخش — بند ۵ متن ۱۸، ک۱۴ و ک۲۴. گردش‌کار هفتگی --out reports/rotate-DATE.md
می‌دهد ولی radar_rotate همیشه پوشه می‌ساخت؛ پس گزارش ۲۵ اکتبر در reports/rotate-2026-10-25.md/
نشست و grep نامزدهای بازبینی هفتگی سبد هر بار خالی برگشت.
"""
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_rotate as RT

UTC = timezone.utc
NOW = datetime(2026, 11, 1, 9, 13, tzinfo=UTC)
ROOT = Path(__file__).resolve().parent.parent


def test_md_suffix_is_a_file(tmp_path) -> None:
    out = str(tmp_path / "reports" / "rotate-2026-11-01.md")
    assert RT.out_path(out, NOW) == out


def test_folder_keeps_old_behaviour(tmp_path) -> None:
    assert RT.out_path(str(tmp_path / "out"), NOW) == str(tmp_path / "out" / "ROTATE_20261101_0913.md")


def test_existing_folder_with_md_name_is_an_error(tmp_path) -> None:
    d = tmp_path / "rotate-2026-10-25.md"
    d.mkdir()
    with pytest.raises(RT.OutPathError):
        RT.out_path(str(d), NOW)


def test_write_report_creates_parent_and_file(tmp_path) -> None:
    out = tmp_path / "reports" / "rotate-2026-11-01.md"
    fn = RT.write_report("| SOL | 1 |\n", str(out), NOW)
    assert fn == str(out) and out.is_file()
    assert out.read_text(encoding="utf-8") == "| SOL | 1 |\n"


def _row(sym, score, rs30, rs7):
    return {"symbol": sym, "price": 10.0, "score": score, "rs30": rs30, "rs7": rs7, "rs3": 1.0,
            "e200": 5.0, "e50": 3.0, "rsi": 55.0, "zone": "داخل", "vs_poc": 1.0,
            "atr_pct": 4.0, "flags": [], "pegged": False, "e200_mature": True, "bars": 700}


def test_weekly_candidates_come_from_ranked_rows(tmp_path) -> None:
    """
    نامزدهای بازبینی هفتگی سبد از جدول‌های رتبه‌دار — «| ۱ | **نماد** |». الگوی پیشین
    grep سطر «| نماد |» را می‌جست و فقط جدول میخکوب و نابالغ را می‌گرفت؛ تا ک۱۴ پوشه بود و
    هیچ‌چیز نمی‌گرفت.
    """
    wf = (ROOT / ".github" / "workflows" / "radar-weekly.yml").read_text(encoding="utf-8")
    assert '--out "reports/rotate-$(date -u +%Y-%m-%d).md"' in wf
    assert RT.CANDIDATE_SED in wf
    rows = [_row("HYPE", 1.8, 12.0, 5.0), _row("SOL", 1.5, 3.0, 2.0),
            _row("AAVE", 0.7, -4.0, 2.0),
            dict(_row("USDG", 1.0, 1.0, 1.0), pegged=True, atr_pct=0.02),
            dict(_row("NEWC", 1.2, 2.0, 1.0), e200_mature=False, bars=120)]
    rep = RT.build_report(rows, 300, 40, ["okx"], 5e6, {})
    out = tmp_path / "rotate.md"
    RT.write_report(rep, str(out), NOW)
    assert RT.candidates(out.read_text(encoding="utf-8")) == ["HYPE", "SOL", "NEWC", "AAVE"]


def test_old_report_folders_moved_to_files() -> None:
    folders = [p for p in (ROOT / "reports").glob("rotate-*.md") if p.is_dir()]
    assert folders == []
