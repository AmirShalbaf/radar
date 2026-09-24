"""
آزمون مهر زمان و افزودنی‌های داده radar_fetch3.py — نشست ۲ نقشه رادار ۷، م۲.

radar_regime.py داده را از توابع موجود می‌گیرد و قاعده تازگی را روی هر
ورودی اجرا می‌کند. سه چیز کم بود:

۱) سنجه‌های مشتق FRED مهر زمان نداشتند. حالا هر کدام فهرست سری‌های
   منبع (sources) و قدیمی‌ترین تاریخ مشاهده (ts) را دارد — تا بشود مهلت
   تازگی را برای هر سری جدا، بر اساس آهنگ انتشارش، سنجید.
۲) مشتق‌های fetch_macro — مثل تسلط تتر و تسلط بدون استیبل — به‌جای
   زمان مشاهده `datetime.now` می‌گرفتند. یعنی ادعای تازگی داشتند که
   نداشتند. حالا قدیمی‌ترین مهر اجزایشان را می‌گیرند.
۳) روند ۳۰ روزه نقدینگی خالص فقط دلار داشت، نه درصد؛ و شاخص دلار روند
   ۳۰ روزه نداشت.

به‌علاوه برچسب واحد WTREGEN: «میلیارد» نوشته شده بود ولی عدد میلیون است.
محاسبه نقدینگی خالص از قبل درست تقسیم می‌کرد — فقط برچسب غلط بود.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_fetch3 as R

UTC = timezone.utc


def _day(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)


# هر سری: (مقدار ۳۰ روز قبل، تاریخ آخر، مقدار آخر)
SERIES = {
    "DGS2": (4.60, "2026-09-23", 4.85),
    "DGS10": (4.90, "2026-09-23", 5.11),
    "DGS30": (5.20, "2026-09-23", 5.40),
    "T10YIE": (2.30, "2026-09-24", 2.33),
    "DFEDTARU": (4.00, "2026-09-24", 4.00),
    "DFEDTARL": (3.75, "2026-09-24", 3.75),
    "DTWEXBGS": (118.00, "2026-09-18", 119.18),    # هفتگی، با تأخیر
    "WALCL": (6_800_000.0, "2026-09-17", 6_750_000.0),   # میلیون دلار
    "RRPONTSYD": (1.0, "2026-09-24", 0.63),              # میلیارد دلار
    "WTREGEN": (900_000.0, "2026-09-17", 977_084.0),     # میلیون دلار
}


@pytest.fixture
def fred(monkeypatch) -> dict:
    """fetch_fred با CSV مصنوعی — بدون شبکه."""
    monkeypatch.setattr(R.time, "sleep", lambda s: None)

    def http_text(url, label=None):
        sid = url.split("id=")[-1]
        if sid not in SERIES:
            return None
        prev, last_d, last_v = SERIES[sid]
        return (f"observation_date,{sid}\n2026-08-01,{prev}\n"
                f"{last_d},{last_v}\n")
    return R.fetch_fred(http_text)


# ═══════════════ FRED — منبع و مهر زمان مشتق‌ها ═══════════════

@pytest.mark.parametrize("key, sources, oldest", [
    ("rate_path", ["DGS2", "DFEDTARU", "DFEDTARL"], "2026-09-23"),
    ("curve_30_2", ["DGS30", "DGS2"], "2026-09-23"),
    ("real_10y", ["DGS10", "T10YIE"], "2026-09-23"),
    ("net_liquidity", ["WALCL", "RRPONTSYD", "WTREGEN"], "2026-09-17"),
    ("net_liq_trend", ["WALCL", "RRPONTSYD", "WTREGEN"], "2026-09-17"),
    ("dollar_30d", ["DTWEXBGS"], "2026-09-18"),
])
def test_derived_has_sources_and_oldest_ts(fred, key, sources, oldest) -> None:
    d = fred["derived"][key]
    assert sorted(d["sources"]) == sorted(sources)
    assert d["ts"] == _day(oldest)


def test_net_liq_trend_has_percent(fred) -> None:
    now = 6_750_000 / 1000 - 0.63 - 977_084 / 1000
    prev = 6_800_000 / 1000 - 1.0 - 900_000 / 1000
    d = fred["derived"]["net_liq_trend"]
    assert d["value"] == pytest.approx(now - prev)
    assert d["pct"] == pytest.approx(100 * (now - prev) / prev)


def test_dollar_30d_percent(fred) -> None:
    d = fred["derived"]["dollar_30d"]
    assert d["value"] == pytest.approx(100 * (119.18 / 118.00 - 1))
    assert "دلار" in d["label"]


def test_wtregen_unit_label_is_millions() -> None:
    assert R.FRED_SERIES["WTREGEN"][1] == "میلیون دلار"


# ═══════════════ fetch_macro — زمان مشاهده، نه زمان واکشی ═══════════════

T_GLOBAL = datetime(2026, 9, 24, 20, 0, tzinfo=UTC)
T_LLAMA = datetime(2026, 9, 24, 0, 0, tzinfo=UTC)
T_TETHER = datetime(2026, 9, 24, 19, 30, tzinfo=UTC)
T_USDC = datetime(2026, 9, 24, 18, 45, tzinfo=UTC)


def _llama() -> list:
    base = int(T_LLAMA.timestamp())
    return [{"date": str(base - (40 - i) * 86400),
             "totalCirculatingUSD": {"peggedUSD": 2.5e11 + i * 1e9}}
            for i in range(41)]


@pytest.fixture
def macro(monkeypatch) -> dict:
    """fetch_macro با پاسخ‌های مصنوعی — بدون شبکه."""
    def http_get(url, params=None, timeout=20, retries=3, label=""):
        if url.endswith("/global"):
            return {"data": {"updated_at": int(T_GLOBAL.timestamp()),
                             "market_cap_percentage": {"btc": 57.0, "eth": 12.0},
                             "total_market_cap": {"usd": 3.0e12},
                             "market_cap_change_percentage_24h_usd": 1.2}}
        if "alternative.me" in url:
            return None
        if "stablecoincharts" in url:
            return _llama()
        if url.endswith("/coins/markets"):
            return [{"id": "tether", "market_cap": 1.6e11,
                     "last_updated": T_TETHER.strftime("%Y-%m-%dT%H:%M:%S.000Z")},
                    {"id": "usd-coin", "market_cap": 6.0e10,
                     "last_updated": T_USDC.strftime("%Y-%m-%dT%H:%M:%S.000Z")}]
        return None
    monkeypatch.setattr(R, "http_get", http_get)
    out: dict = {}
    R.fetch_macro(out)
    return out


@pytest.mark.parametrize("key, oldest", [
    ("btc_dom_ex_stable", T_LLAMA),
    ("stable_dominance", T_LLAMA),
    ("usdt_dominance", T_TETHER),
    ("usdt_mcap", T_TETHER),
    ("usdc_dominance", T_USDC),
    ("total2", T_GLOBAL),
    ("total3", T_GLOBAL),
    ("total3_ex_stable", T_LLAMA),
])
def test_macro_derived_ts_is_oldest_component(macro, key, oldest) -> None:
    """مهر زمان مشتق = قدیمی‌ترین جزء، نه لحظه واکشی."""
    assert macro[key].ts == oldest


def test_macro_tether_without_timestamp_has_unknown_age(monkeypatch) -> None:
    """بدون مهر منبع، عمر نامعلوم است — None، نه «همین حالا»."""
    def http_get(url, params=None, timeout=20, retries=3, label=""):
        if url.endswith("/global"):
            return {"data": {"updated_at": int(T_GLOBAL.timestamp()),
                             "market_cap_percentage": {"btc": 57.0},
                             "total_market_cap": {"usd": 3.0e12}}}
        if url.endswith("/coins/markets"):
            return [{"id": "tether", "market_cap": 1.6e11}]
        return None
    monkeypatch.setattr(R, "http_get", http_get)
    out: dict = {}
    R.fetch_macro(out)
    assert out["usdt_dominance"].ts is None
