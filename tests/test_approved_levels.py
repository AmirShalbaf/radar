"""
سطح‌های تأییدشده پس از قاعده لنگر — نشست ۳، تصمیم کاربر ۲۶ سپتامبر ۲۰۲۶.

AAVE، LINK، SUI، ONDO و TAO سطح تازه گرفتند؛ SOL، ETH و BNB بدون تغییر.
لنگر هر هشت سکه در watch.json. مهر تازه invalidation_since فقط برای پنج
سکه عوض‌شده؛ همان سطح و مهر در holdings.json. برچسب «سطح ضعیف» ONDO
برداشته شد: هر دو دلیلش — سه برخورد در ۱۶ روز با پهنای 0.6٪، و سطح بالای
آخرین بسته هفتگی — درباره سطح تازه صدق نمی‌کند.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_positions as P
import radar_watch as W

ROOT = Path(__file__).resolve().parent.parent
OLD = "2026-09-25T21:34:47+00:00"
APPROVED = {"SOL": 96.7108, "ETH": 2380.5606, "BNB": 702.3872, "AAVE": 106.8920,
            "LINK": 10.3366, "SUI": 0.6843, "ONDO": 0.3478, "TAO": 202.5065}
CHANGED = {"AAVE", "LINK", "SUI", "ONDO", "TAO"}


def _files():
    w = json.loads((ROOT / "watch.json").read_text(encoding="utf-8"))
    h = json.loads((ROOT / "holdings.json").read_text(encoding="utf-8"))
    return w, h


def test_levels_are_the_approved_ones() -> None:
    w, _ = _files()
    assert {it["symbol"]: it["invalidation"] for it in w["positions"]} == APPROVED


def test_anchor_rule_holds_for_all_eight() -> None:
    w, h = _files()
    W.validate_watch(w)
    assert P.anchor_violations(w) == []
    assert P.level_mismatches(h, w) == []
    for it in w["positions"]:
        assert it["anchor"] == it["anchor_week_close"] <= it["anchor_price"]


def test_new_stamp_only_for_changed_coins() -> None:
    w, _ = _files()
    since = {it["symbol"]: it["invalidation_since"] for it in w["positions"]}
    new = {since[s] for s in CHANGED}
    assert len(new) == 1
    assert datetime.fromisoformat(new.pop()) > datetime.fromisoformat(OLD)
    assert all(since[s] == OLD for s in set(APPROVED) - CHANGED)


def test_ondo_weak_label_removed() -> None:
    w, _ = _files()
    ondo = next(it for it in w["positions"] if it["symbol"] == "ONDO")
    assert ondo.get("label") != "سطح ضعیف"
