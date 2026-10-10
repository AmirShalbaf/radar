# -*- coding: utf-8 -*-
"""
اتصال اسکنر پامپ — نشست ۹، ایستگاه ۲ب. بی‌شبکه.

بخش pulse در pump.json (سقف ۵، انقضای ۳ روز، تمدید)، نبض با بخش جدای «نامزد اسکنر»،
radar_events نامزد را از pump.json تازه‌تر از ۳۶ ساعت می‌خواند، گروه «اسکنر پامپ» در
radar_probe، و گام اسکنر در گردش‌کار روزانه پیش از گام رویداد.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import radar_events as E
import radar_probe as PR
import radar_pump as P
import radar_snapshot as S

UTC = timezone.utc
NOW = datetime(2026, 10, 10, 7, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parent.parent
DAILY = ROOT / ".github" / "workflows" / "radar-daily.yml"


def _e(sym, side="long", card=False, name="الف‌۳"):
    return {"symbol": sym, "side": side, "setup": {"name": name, "state": "pre"},
            "card": {"ok": card}}


# ═══════════════ بخش pulse ═══════════════

def test_pulse_cap_expiry_and_refresh():
    old = P.iso(NOW - timedelta(days=2))
    prev = [
        {"symbol": "A", "side": "long", "setup": "الف‌۳", "added": old, "last_seen": old,
         "expires": P.iso(NOW + timedelta(days=1))},
        {"symbol": "B", "side": "long", "setup": "الف‌۱", "added": old, "last_seen": old,
         "expires": P.iso(NOW - timedelta(minutes=1))},                 # منقضی
        {"symbol": "C", "side": "short", "setup": "ج‌۱", "added": old, "last_seen": old,
         "expires": P.iso(NOW + timedelta(hours=5))},
    ]
    sec = {"long": [_e("D"), _e("A")], "short": [_e("E", "short", card=True, name="ج‌۱")]}
    out = P.pulse_merge(prev, P.pulse_picks(sec), NOW)
    assert [p["symbol"] for p in out] == ["E", "D", "A", "C"]          # کارت‌دار اول
    a = next(p for p in out if p["symbol"] == "A")
    assert a["added"] == old and a["expires"] == P.iso(NOW + timedelta(days=3))   # تمدید
    assert next(p for p in out if p["symbol"] == "C")["expires"] == prev[2]["expires"]
    many = {"long": [_e(f"S{i}") for i in range(8)], "short": []}
    assert len(P.pulse_merge(prev, P.pulse_picks(many), NOW)) == P.PULSE_MAX == 5


def test_telegram_line_counts_and_card_names():
    sec = {"long": [_e("OP", card=True), _e("LTC")], "short": [_e("ADA", "short")],
           "afterpump": [_e("KAIA")], "late": [], "nolevel": [], "veto": [_e("ZK")]}
    line = P.telegram_line(sec)
    assert line.startswith("اسکنر پامپ") and "آزمون‌نشده" in line
    assert "1 کارت: OP" in line and "لانگ 2" in line and "شورت 1" in line
    assert "پس از پامپ 1" in line and "وتو 1" in line
    none = P.telegram_line({k: [] for k in P.SECTIONS})
    assert "0 کارت" in none and ":" not in none.split("کارت")[1][:2]


# ═══════════════ نبض ═══════════════

def test_snapshot_reads_only_live_pulse_items(tmp_path):
    f = tmp_path / "pump.json"
    f.write_text(json.dumps({"pulse": {"items": [
        {"symbol": "op", "side": "long", "setup": "الف‌۳", "expires": P.iso(NOW + timedelta(days=1))},
        {"symbol": "OLD", "side": "long", "setup": "الف‌۱", "expires": P.iso(NOW - timedelta(hours=1))},
        {"symbol": "ریال", "side": "long", "setup": "الف‌۱", "expires": P.iso(NOW + timedelta(days=1))},
    ]}}, ensure_ascii=False), encoding="utf-8")
    items = S.pulse_items(str(f), NOW)
    assert [i["symbol"] for i in items] == ["OP"]
    assert S.pulse_items(str(tmp_path / "missing.json"), NOW) == []


def test_snapshot_scanner_section_is_separate():
    rows = [{"symbol": "BTC", "price": 80000.0, "chg24": 1.0, "funding": 0.01, "oi_usd": 1e9,
             "src": "okx"},
            {"symbol": "OP", "price": 0.14, "chg24": 3.0, "funding": 0.01, "oi_usd": 4e7,
             "src": "okx"}]
    scanner = {"OP": {"symbol": "OP", "side": "long", "setup": "الف‌۳",
                      "expires": "2026-10-13T05:26:00Z"}}
    md, js = S.build(rows, {}, [], scanner=scanner)
    assert "## نامزد اسکنر — آزمون‌نشده" in md
    main, extra = md.split("## نامزد اسکنر — آزمون‌نشده")
    assert "| OP |" not in main and "| OP |" in extra and "| BTC |" in main
    assert "OP" not in js["symbols"] and js["scanner"]["OP"]["setup"] == "الف‌۳"
    md2, js2 = S.build(rows[:1], {}, [])
    assert "نامزد اسکنر" not in md2 and js2.get("scanner") == {}


# ═══════════════ رویداد ═══════════════

def _pump(tmp_path, hours_old: float, cands=("ZRO", "WLD")):
    f = tmp_path / "pump.json"
    f.write_text(json.dumps({"generated": P.iso(NOW - timedelta(hours=hours_old)),
                             "candidates": list(cands)}), encoding="utf-8")
    return f


def test_events_reads_fresh_pump_candidates(tmp_path):
    syms, src, note = E.pump_candidates(_pump(tmp_path, 20), NOW)
    assert syms == ["ZRO", "WLD"] and "pump.json" in src and note is None


def test_events_ignores_stale_or_missing_pump(tmp_path):
    syms, src, note = E.pump_candidates(_pump(tmp_path, 37), NOW)
    assert syms == [] and src is None and "کهنه" in note
    syms, src, note = E.pump_candidates(tmp_path / "nope.json", NOW)
    assert syms == [] and src is None and "pump.json" in note


# ═══════════════ سنجش منابع ═══════════════

def test_probe_has_pump_scanner_group():
    ts = [t for t in PR.targets(NOW) if t.group == "اسکنر پامپ"]
    keys = {t.key for t in ts}
    assert {"okx-tickers-spot", "okx-instruments-spot", "okx-funding-all", "okx-oi-history",
            "okx-candles-4h", "gate-tickers-spot", "gate-currency-pairs", "gate-contracts",
            "gate-candles-1h", "gate-contract-stats", "lbank-pairs"} <= keys
    assert all(t.marker for t in ts)
    lb = next(t for t in ts if t.key == "lbank-pairs")
    assert "api.lbkex.com" in lb.url and lb.marker == "_usdt"


# ═══════════════ گردش‌کار روزانه ═══════════════

def _step(name: str) -> str:
    text = DAILY.read_text(encoding="utf-8")
    start = text.index(f"- name: {name}\n")
    nxt = text.find("\n      - name:", start + 1)
    return text[start:nxt if nxt != -1 else len(text)]


def test_daily_pump_step_before_events_soft_and_loud():
    text = DAILY.read_text(encoding="utf-8")
    i = text.index("- name: اسکنر پامپ\n")
    assert text.index("- name: ساخت رژیم\n") < i < text.index("- name: تقویم رویداد و آزادسازی\n")
    s = _step("اسکنر پامپ")
    assert "timeout-minutes: 12" in s and "continue-on-error: true" in s
    assert "python radar_pump.py" in s and "--line /tmp/pump_line.txt" in s
    assert "|| true" not in s and "::error::" in s and 'reports/pump-error-$D.md' in s
    assert "timeout-minutes: 40" in text


def test_daily_commits_pump_files_and_summary_has_line():
    c = _step("کامیت گزارش‌ها")
    for f in ("pump.json", "pump_ledger.json", "reports/PUMP.md"):
        assert f in c
    s = _step("ساخت خلاصه امروز")
    assert "pump_line" in s and s.index("pump_line") < s.index("staleness.md\n            echo")
