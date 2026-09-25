"""
آزمون سطوح ساختاری سبد در گردش‌کار روزانه — نشست ۳، مورد ۷.

- radar_positions.py symbols: نمادهای پوزیشن باز هر دو دفتر، جدا با کاما،
  به ترتیب فایل. خارج‌شده نیست. فهرست از همان‌جا می‌آید، نه از متن گردش‌کار.
- گام «سطوح ساختاری سبد» پس از سبد و پیش از خلاصه امروز، با خروجی تاریخ‌دار
  reports/levels-$D.md. خطا با ::error:: و فایل خطا، بدون `|| true`.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_positions as P

ROOT = Path(__file__).resolve().parent.parent
DAILY = ROOT / ".github" / "workflows" / "radar-daily.yml"
STEP = "سطوح ساختاری سبد"


def _step(name: str) -> str:
    text = DAILY.read_text(encoding="utf-8")
    start = text.index(f"- name: {name}\n")
    nxt = text.find("\n      - name:", start + 1)
    return text[start:nxt if nxt != -1 else len(text)]


def test_symbols_lists_open_positions(tmp_path, capsys) -> None:
    now = datetime.now(timezone.utc).isoformat()
    h = {"version": 2, "updated": now, "source": "آزمون",
         "frozen": {"date": "2026-09-25", "members": {"SOL": 6.0, "ETH": 0.5, "BNB": 1.0}},
         "cash": [], "ledger": [{"at": now, "action": "exit", "symbol": "BNB", "delta": -1.0,
                                 "price": 700.0, "level": 702.0, "reason": "invalidation"}],
         "positions": [
             {"symbol": "SOL", "book": "position", "status": "open", "invalidation": None,
              "lots": [{"qty": 6.0, "account": "A", "entry": None}]},
             {"symbol": "BNB", "book": "position", "status": "exited", "invalidation": 702.0,
              "lots": []},
             {"symbol": "ETH", "book": "position", "status": "open", "invalidation": None,
              "lots": [{"qty": 0.5, "account": "A", "entry": None}]}]}
    hp, jp = tmp_path / "h.json", tmp_path / "j.json"
    hp.write_text(json.dumps(h, ensure_ascii=False), encoding="utf-8")
    jp.write_text(json.dumps({"version": 1, "trades": []}), encoding="utf-8")
    assert P.main(["--holdings", str(hp), "--journal", str(jp), "symbols"]) == 0
    assert capsys.readouterr().out.strip() == "SOL,ETH"


def test_daily_has_levels_step_between_book_and_summary() -> None:
    text = DAILY.read_text(encoding="utf-8")
    i = text.index(f"- name: {STEP}\n")
    assert text.index("- name: بازبینی سبد و موتور خروج\n") < i
    assert i < text.index("- name: ساخت خلاصه امروز\n")


def test_levels_step_dated_output_from_holdings_symbols() -> None:
    step = _step(STEP)
    assert "python radar_positions.py" in step and "symbols" in step
    assert "python radar_levels.py" in step and "--watchlist" in step
    assert 'reports/levels-$D.md' in step


def test_levels_step_fails_loudly_but_does_not_stop() -> None:
    step = _step(STEP)
    assert "::error::" in step and "levels-error-" in step
    assert "|| true" not in step
    assert "if ! python radar_levels.py" in step or "if python radar_levels.py" in step
