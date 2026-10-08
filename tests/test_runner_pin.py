"""
اجراکننده گیت‌هاب ثابت — نشست ۱۰، ۸ اکتبر ۲۰۲۶، رویداد ۹۰.

گیت‌هاب هشدار داد ubuntu-latest از ۱۹ اکتبر به Ubuntu 26.04 می‌رود. سنجش،
محاسبه‌شده از versions-manifest.json کنش setup-python: ساخته 3.11.15 تا 3.11.17
برای 26.04 هست؛ پس نصب پایتون نمی‌شکند. خطر مانده ابزار پایه پوسته است —
head -c، tail -c، paste، date — که Ubuntu از ۲۵.۱۰ با نسخه راستی عوض کرده؛ این
را فقط اجرای واقعی ثابت می‌کند.

قرارداد: هر چهار گردش‌کار روی ubuntu-24.04 ثابت؛ جابه‌جایی بی‌صدا نه. گردش‌کار
سنجش ورودی دستی runner دارد — پیش‌فرض 24.04، گزینه 26.04 — و پس از کامیت گزارش،
آزمون‌های مخزن را روی همان اجراکننده می‌زند. گزارش سنجش ImageOS و ImageVersion
را می‌نویسد.
"""
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_probe as PR

FLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
PIN = "ubuntu-24.04"


def _text(name: str) -> str:
    return (FLOWS / name).read_text(encoding="utf-8")


def test_no_floating_runner() -> None:
    for f in FLOWS.glob("*.yml"):
        assert "ubuntu-latest" not in f.read_text(encoding="utf-8"), f.name


def test_scheduled_flows_pinned() -> None:
    for name in ("radar-daily.yml", "radar-pulse.yml", "radar-weekly.yml"):
        runs = re.findall(r"runs-on:\s*(\S+)", _text(name))
        assert runs == [PIN], (name, runs)


def test_probe_runner_input_defaults_to_pin() -> None:
    t = _text("radar-probe.yml")
    assert "runner:" in t and "type: choice" in t
    assert f'default: "{PIN}"' in t and "ubuntu-26.04" in t
    assert re.search(r"runs-on:\s*\$\{\{\s*inputs\.runner\s*\|\|\s*'ubuntu-24\.04'\s*\}\}", t)


def test_probe_runs_tests_after_commit() -> None:
    t = _text("radar-probe.yml")
    i_commit = t.index("- name: کامیت گزارش")
    i_tests = t.index("python -m pytest -q tests")
    assert i_commit < i_tests
    assert "requirements-dev.txt" in t
    assert "|| true" not in t


def test_report_names_runner_image() -> None:
    now = datetime(2026, 10, 8, 9, 0, tzinfo=timezone.utc)
    rep = PR.render([], "گیت‌هاب", "US", now,
                    {"GITHUB_ACTIONS": "true", "ImageOS": "ubuntu24",
                     "ImageVersion": "20261005.1.0"})
    assert "ubuntu24" in rep and "20261005.1.0" in rep
    local = PR.render([], "محلی", "DE", now, {})
    assert "تصویر اجراکننده" not in local
