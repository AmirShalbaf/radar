"""
آزمون radar_probe.py و گردش‌کار radar-probe.yml — نشست ۱۰، ایستگاه ۱.

سنجش دسترسی منابع تقویم رویداد و آزادسازی، و سه منبع تکرارگر، از همان
محیطی که اجرا می‌شود: لپ‌تاپ یا اجراکننده گیت‌هاب. فقط وضعیت، اندازه، زمان و
نشانه محتوا — هیچ داده‌ای ذخیره نمی‌شود. منبع بسته داده سنجش است، نه خطای
اسکریپت؛ پس اجرا با کد ۰ تمام می‌شود و گزارش همه سطرها را دارد.
گردش‌کار فقط دستی است — بی‌زمان‌بندی — و فقط گزارش خودش را کامیت می‌کند.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_probe as PR

ROOT = Path(__file__).resolve().parent.parent
FLOW = ROOT / ".github" / "workflows" / "radar-probe.yml"
NOW = datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc)


class _R:
    def __init__(self, status: int, body: bytes, headers: dict | None = None):
        self.status_code, self.content, self.headers = status, body, headers or {}


def _t(marker: str = "FOMC") -> PR.Target:
    return PR.Target("x", "آزمون", "https://example.test/x", "bot", marker)


# ═══════════════ داوری ═══════════════

def test_classify() -> None:
    assert PR.classify(200, True) == "open"
    assert PR.classify(200, False) == "no_marker"
    assert PR.classify(403, False) == "closed"
    assert PR.classify(402, False) == "closed"
    assert PR.classify(None, False) == "error"


def test_probe_open() -> None:
    row = PR.probe(_t(), lambda url, **k: _R(200, b'{"type": "FOMC"}'), pause=0)
    assert row["verdict"] == "open" and row["status"] == 200 and row["bytes"] == 16


def test_probe_closed_keeps_page_title() -> None:
    html = b"<html><head><title>Just a moment...</title></head><body>cf</body></html>"
    row = PR.probe(_t(), lambda url, **k: _R(403, html), pause=0)
    assert row["verdict"] == "closed"
    assert "Just a moment..." in row["why"]


def test_probe_no_marker_keeps_body_snippet() -> None:
    """کوین‌گلس بی‌کلید ۲۰۰ می‌دهد ولی با پیام خطا — باید دیده شود."""
    row = PR.probe(_t('"data"'), lambda url, **k: _R(200, b'{"code":"401","msg":"API key missing."}'),
                   pause=0)
    assert row["verdict"] == "no_marker"
    assert "API key missing." in row["why"]


def test_probe_error_does_not_raise() -> None:
    def boom(url, **k):
        raise TimeoutError("slow")
    row = PR.probe(_t(), boom, pause=0)
    assert row["verdict"] == "error" and row["status"] is None
    assert "TimeoutError" in row["why"]


def test_snippet_is_table_safe() -> None:
    s = PR.snippet(b"a|b\nc\r\n" + b"x" * 500)
    assert "|" not in s and "\n" not in s and len(s) <= PR.REASON_MAX


def test_user_agents() -> None:
    seen = {}

    def get(url, headers=None, **k):
        seen[url] = headers["User-Agent"]
        return _R(200, b"FOMC")
    PR.probe(PR.Target("a", "g", "https://a.test", "bot", "FOMC"), get, pause=0)
    PR.probe(PR.Target("b", "g", "https://b.test", "browser", "FOMC"), get, pause=0)
    assert seen["https://a.test"] == PR.UA["bot"]
    assert seen["https://b.test"] == PR.UA["browser"] and "Mozilla" in PR.UA["browser"]


# ═══════════════ فهرست منابع ═══════════════

NEEDED = {"fed-calendar-json", "fed-fomc-page", "fred-calendar-cpi", "bea-ics", "bls-ics",
          "bls-ics-browser", "llama-emissions-api", "llama-ds-list", "llama-ds-protocol",
          "llama-ds-index", "coingecko-markets", "farside-btc", "farside-btc-bot",
          "coinglass-api", "coinglass-site", "ff-json", "ff-xml", "okx-candles", "fred-graph"}


def test_targets_cover_session_decisions() -> None:
    keys = [t.key for t in PR.targets(NOW)]
    assert NEEDED <= set(keys)
    assert len(keys) == len(set(keys))
    for t in PR.targets(NOW):
        assert t.ua in PR.UA and t.marker and t.url.startswith("https://")


def test_fred_window_moves_with_now() -> None:
    t = {x.key: x for x in PR.targets(NOW)}["fred-calendar-cpi"]
    assert "rid=10" in t.url and "vs=2026-10-06" in t.url and "ve=2026-12-05" in t.url


# ═══════════════ main ═══════════════

def test_main_writes_report_on_github(tmp_path) -> None:
    out = tmp_path / "probe.md"

    def get(url, **k):
        if "ipinfo" in url:
            return _R(200, b"US\n")
        if "farside" in url:
            return _R(403, b"<title>Just a moment...</title>")
        return _R(200, b"FOMC Consumer Price Index BEGIN:VCALENDAR sui-foundation unlockEvents "
                       b"protocolSlug circulating_supply IBIT Liquidation \"title\" <weeklyevents "
                       b"\"code\":\"0\" DFF \"data\" Meetings")
    rc = PR.main(["--out", str(out)], get=get, env={"GITHUB_ACTIONS": "true"}, now=NOW, pause=0)
    assert rc == 0
    rep = out.read_text(encoding="utf-8")
    assert "گیت‌هاب" in rep and "US" in rep and "2026-10-06 09:00 UTC" in rep
    for k in NEEDED:
        assert f"`{k}`" in rep, k
    farside = [l for l in rep.splitlines() if "`farside-btc`" in l][0]
    assert "403" in farside and "❌ بسته" in farside and "Just a moment..." in farside


def test_main_survives_total_network_failure(tmp_path) -> None:
    out = tmp_path / "probe.md"

    def get(url, **k):
        raise ConnectionError("down")
    assert PR.main(["--out", str(out)], get=get, env={}, now=NOW, pause=0) == 0
    rep = out.read_text(encoding="utf-8")
    assert "محلی" in rep and "نامعلوم" in rep
    assert rep.count("❌ خطا") == len(PR.targets(NOW))


def test_main_only_filters(tmp_path) -> None:
    out = tmp_path / "probe.md"
    PR.main(["--out", str(out), "--only", "ff-json,bls-ics"],
            get=lambda url, **k: _R(200, b"x"), env={}, now=NOW, pause=0)
    rep = out.read_text(encoding="utf-8")
    assert "`ff-json`" in rep and "`bls-ics`" in rep and "`farside-btc`" not in rep


def test_main_rejects_unknown_only(tmp_path) -> None:
    with pytest.raises(SystemExit):
        PR.main(["--out", str(tmp_path / "p.md"), "--only", "nope"],
                get=lambda url, **k: _R(200, b"x"), env={}, now=NOW, pause=0)


# ═══════════════ گردش‌کار ═══════════════

def test_workflow_is_manual_and_commits_only_its_report() -> None:
    text = FLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch" in text
    assert "schedule" not in text and "cron" not in text
    assert "python radar_probe.py" in text and 'reports/probe-sources-$D.md' in text
    assert "|| true" not in text
    adds = [l.strip() for l in text.splitlines() if l.strip().startswith("git add")]
    assert adds == ['git add "reports/probe-sources-$D.md"']
    assert "contents: write" in text
    assert 'python-version: "3.11"' in text
