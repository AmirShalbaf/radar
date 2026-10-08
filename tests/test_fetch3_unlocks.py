"""
ک۸۷ — شرط آزادسازی radar_fetch3 از منبع تازه، نشست ۱۰.

fetch_unlocks نشانی api.llama.fi/emissions را می‌خواند که پولی شد — کد ۴۰۲؛ هر ۱۱
گزارش تحلیل کامل از ۹ اوت «آزادسازی بعدی: داده ندارم» نوشتند. حالا همان حکم
radar_events.symbol_unlock — داده عمومی DefiLlama و عرضه در گردش CoinGecko، با
وتوی ف۳۱. نامعلوم با دلیل در خانه گزارش و در FAILURES؛ خطا هم در FAILURES.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_events as EV
import radar_fetch3 as R

ROOT = Path(__file__).resolve().parent.parent


def _v(status, cliffs=(), why=""):
    return {"symbol": "ZRO", "status": status, "why": why, "single_max": 5.92 if cliffs else 0.0,
            "total": 5.92 if cliffs else 0.0, "emission": 0.0, "cliffs": list(cliffs),
            "cover_end": None, "slug": "layerzero"}


CLIFF = {"day": "2026-10-20", "at": "2026-10-20T05:33:00Z", "tokens": 23625000.0, "pct": 5.92,
         "cats": ["insiders"]}


def _run(monkeypatch, ret=None, exc=None) -> dict:
    def fake(sym, get=None, now=None):
        if exc:
            raise exc
        return ret
    monkeypatch.setattr(EV, "symbol_unlock", fake)
    monkeypatch.setattr(R, "FAILURES", [])
    out: dict = {}
    R.fetch_unlocks("ZRO", out)
    return out


def test_veto_shows_cliff(monkeypatch) -> None:
    out = _run(monkeypatch, _v("veto", [CLIFF], "بزرگ‌ترین پله 5.92٪"))
    v = out["next_unlock"].value
    assert "2026-10-20" in v and "5.92" in v and "وتو" in v
    assert out["next_unlock"].source.startswith("DefiLlama")
    assert R.FAILURES == []


def test_pass_without_cliff(monkeypatch) -> None:
    out = _run(monkeypatch, _v("pass", why="بی پله"))
    assert "عبور" in out["next_unlock"].value


def test_unknown_is_loud(monkeypatch) -> None:
    out = _run(monkeypatch, _v("unknown", why="پوشش DefiLlama تا 2026-06-19"))
    assert "نامعلوم" in out["next_unlock"].value and "2026-06-19" in out["next_unlock"].value
    assert any("نامعلوم" in f for f in R.FAILURES)


def test_error_is_loud(monkeypatch) -> None:
    out = _run(monkeypatch, exc=RuntimeError("boom"))
    assert "next_unlock" not in out
    assert any("boom" in f for f in R.FAILURES)


def test_paid_endpoint_gone() -> None:
    assert "api.llama.fi/emissions" not in (ROOT / "radar_fetch3.py").read_text(encoding="utf-8")
