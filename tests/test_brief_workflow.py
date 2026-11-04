"""
سیم‌کشی گردش‌کار روزانه برای پیام صبح — متن ۳۷، و یک منبع عددهای سلامت نبض.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import radar_schedule as RS

UTC = timezone.utc
WF = ROOT / ".github" / "workflows" / "radar-daily.yml"


def _steps():
    d = yaml.safe_load(WF.read_text(encoding="utf-8"))
    return d["jobs"]["scan"]["steps"]


def _step(name):
    return next(s for s in _steps() if s.get("name") == name)


def test_producers_write_sidecars():
    for name, flag in (("اسکن واچ‌لیست", "--json reports/scan.json"),
                       ("بازبینی سبد و موتور خروج", "--json reports/book.json"),
                       ("سطوح ساختاری سبد", "--json reports/levels.json"),
                       ("لایه زمینه", "--json reports/context.json")):
        assert flag in _step(name)["run"], name


def test_brief_order_collect_commit_send_fallback():
    names = [s.get("name") for s in _steps()]
    i = {n: names.index(n) for n in ("ساخت خلاصه امروز", "گردآوری پیام صبح", "کامیت گزارش‌ها",
                                    "پیام صبح رادار", "اعلان تلگرام")}
    assert i["ساخت خلاصه امروز"] < i["گردآوری پیام صبح"] < i["کامیت گزارش‌ها"] < i["پیام صبح رادار"] < i["اعلان تلگرام"]
    c = _step("گردآوری پیام صبح")
    assert c["continue-on-error"] is True and "radar_brief.py collect --out reports/brief.json" in c["run"]
    b = _step("پیام صبح رادار")
    assert b["id"] == "brief" and b["continue-on-error"] is True
    assert '"playwright==1.63.0"' in b["run"] and "--png" in b["run"] and "send --dir /tmp/brief" in b["run"]
    assert b["env"]["RADAR_DESK_URL"] == "${{ secrets.RADAR_DESK_URL }}"
    assert b["env"]["TELEGRAM_BOT_TOKEN"] == "${{ secrets.TELEGRAM_BOT_TOKEN }}"
    f = _step("اعلان تلگرام")
    assert f["if"] == "success() && steps.brief.outcome != 'success'"
    assert "python radar_telegram.py --file /tmp/telegram_daily.txt" in f["run"]


def test_latest_header_unchanged_for_daily_guard():
    assert 'echo "# گزارش رادار — $D"' in _step("ساخت خلاصه امروز")["run"]


def test_health_stats_single_source_for_line():
    now = datetime(2026, 11, 3, 7, 16, tzinfo=UTC)
    runs = [now - timedelta(hours=h) for h in (30, 20, 9.4, 5.5)]
    log = {"runs": [{"at": t.isoformat(), "snapshot_rc": 0, "watch_rc": 0} for t in runs]}
    st = RS.health_stats(log, now)
    assert st["count"] == 3 and abs(st["max_gap_h"] - 10.6) < 1e-9
    assert abs(st["last_age_h"] - 5.5) < 1e-9 and st["bad"] == 0
    line = RS.health_line(log, now)
    assert "۳ نبض" in line and "10.6 ساعت" in line
    assert RS.health_line({"runs": []}, now).endswith("دفتر نبض هنوز ردیفی ندارد")
