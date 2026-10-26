"""
لایه زمینه — بند ۲ متن ۲۰، ۲۷ اکتبر ۲۰۲۶. فقط نمایش.

برنت، بازده اوراق ۱۰ ساله آمریکا و شاخص دلار؛ هر کدام با مقدار، تغییر یک‌هفته‌ای و تاریخ
مشاهده، از همان FRED که رادار برای DGS10 و DTWEXBGS می‌خواند. تأخیر انتشار صریح. لایه
آزمون‌نشده است و به امتیاز رژیم یا قاعده‌ها راه ندارد — ورود فقط پس از ک۳۵.
"""
import ast
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_context as C
import radar_fetch3 as R

ROOT = Path(__file__).resolve().parent.parent
UTC = timezone.utc
NOW = datetime(2026, 10, 27, 6, 37, tzinfo=UTC)

CSV = {
    # برنت روزانه، ولی EIA هفتگی منتشر می‌کند — آخرین مشاهده ۲۰ اکتبر
    "DCOILBRENTEU": "observation_date,DCOILBRENTEU\n2026-10-12,66.10\n2026-10-13,.\n"
                    "2026-10-14,65.00\n2026-10-19,64.20\n2026-10-20,63.70\n",
    "DGS10": "observation_date,DGS10\n2026-10-16,4.05\n2026-10-19,4.10\n2026-10-20,4.12\n"
             "2026-10-23,4.18\n2026-10-26,4.21\n",
    "DTWEXBGS": "observation_date,DTWEXBGS\n2026-10-16,120.40\n2026-10-17,120.80\n"
                "2026-10-23,121.70\n",
}


def fake_http(missing=()):
    def http_text(url, params=None, timeout=25, retries=2, label=""):
        sid = url.split("id=")[-1]
        return None if sid in missing else CSV.get(sid)
    return http_text


def test_fred_rows_shared_parser() -> None:
    rows = R.fred_rows("DCOILBRENTEU", fake_http())
    assert rows == [("2026-10-12", 66.10), ("2026-10-14", 65.00), ("2026-10-19", 64.20),
                    ("2026-10-20", 63.70)]
    # همان تجزیه‌گر سری‌های رژیم — یک تعریف
    v, ts, prev = R.fred_series("DGS10", fake_http())
    assert v == 4.21 and ts == datetime(2026, 10, 26, tzinfo=UTC)
    assert R.fred_rows("DGS10", fake_http(missing=("DGS10",))) is None


def test_week_change_and_dates() -> None:
    rows = C.gather(NOW, fake_http())
    by = {r["sid"]: r for r in rows}
    b = by["DCOILBRENTEU"]
    assert b["value"] == 63.70 and b["date"] == "2026-10-20"
    # یک هفته پیش‌تر: آخرین مشاهده تا ۱۳ اکتبر — 66.10
    assert b["prev_date"] == "2026-10-12" and abs(b["chg"] - 100 * (63.70 / 66.10 - 1)) < 1e-9
    assert b["lag_days"] == 7
    y = by["DGS10"]
    # بازده با واحد درصد، نه درصد تغییر: 4.21 − 4.10
    assert y["date"] == "2026-10-26" and y["prev_date"] == "2026-10-19"
    assert abs(y["chg"] - 0.11) < 1e-9 and y["chg_unit"] == "pp"
    d = by["DTWEXBGS"]
    assert d["date"] == "2026-10-23" and d["prev_date"] == "2026-10-16"
    assert abs(d["chg"] - 100 * (121.70 / 120.40 - 1)) < 1e-9


def test_section_text_shows_dates_and_lag() -> None:
    rows = C.gather(NOW, fake_http())
    s = C.render_section(rows, NOW)
    assert s.startswith("## لایه زمینه — فقط نمایش")
    assert "نفت برنت" in s and "63.70" in s and "2026-10-20" in s
    assert "تأخیر انتشار ۷ روز" in s                     # برنت صریح
    assert "4.21" in s and "+0.11 واحد درصد" in s
    assert "121.70" in s and "+1.08٪" in s
    assert "آزمون‌نشده" in s and "ک۳۵" in s
    # سری تازه برچسب تأخیر نمی‌گیرد
    assert s.count("تأخیر انتشار") == 2                   # برنت ۷ روز، دلار ۴ روز
    line = C.render_line(rows)
    assert line.startswith("🌐 زمینه، فقط نمایش:") and "برنت 63.70" in line
    assert "2026-10-20" in line


def test_missing_series_is_said_not_hidden() -> None:
    rows = C.gather(NOW, fake_http(missing=("DCOILBRENTEU",)))
    s = C.render_section(rows, NOW)
    assert "نفت برنت" in s and "داده ندارم" in s
    assert "داده ندارم" in C.render_line(rows)


def test_one_row_series_has_no_change() -> None:
    def http(url, **k):
        return "observation_date,DGS10\n2026-10-26,4.21\n"
    r = C.series_row("DGS10", NOW, http)
    assert r["value"] == 4.21 and r["chg"] is None
    assert "تغییر هفته: —" in C.render_section([r], NOW)


def test_cli_writes_files_and_code(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(C, "_http", lambda: fake_http())
    sec, line = tmp_path / "s.md", tmp_path / "l.txt"
    assert C.main(["--section", str(sec), "--line", str(line)], now=NOW) == 0
    assert "لایه زمینه" in sec.read_text(encoding="utf-8")
    assert line.read_text(encoding="utf-8").startswith("🌐")
    monkeypatch.setattr(C, "_http", lambda: fake_http(missing=("DGS10",)))
    assert C.main(["--section", str(sec), "--line", str(line)], now=NOW) == 2
    assert "داده ندارم" in sec.read_text(encoding="utf-8")


def test_context_never_reaches_regime_score() -> None:
    """هیچ پرونده امتیاز یا قاعده‌ای radar_context را وارد نمی‌کند — ک۳۵ پیش از ورود."""
    for name in ("radar_regime.py", "radar_budget.py", "radar_book.py", "radar_watch.py",
                 "radar_positions.py", "radar_rebuy.py", "radar_scan.py", "radar_size.py"):
        tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
        mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        mods |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert "radar_context" not in mods, name
    import radar_regime as RG
    assert "DCOILBRENTEU" not in {s for v in RG.INPUT_SOURCES.values() for s in v}


def test_daily_workflow_wires_context_into_telegram_part() -> None:
    y = (ROOT / ".github" / "workflows" / "radar-daily.yml").read_text(encoding="utf-8")
    assert "python radar_context.py --section /tmp/context_section.md" in y
    head = y.index("# گزارش رادار — $D")
    cat = y.index("cat /tmp/context_section.md", head)
    assert cat < y.index('echo "<!-- رویداد-آغاز -->"')
