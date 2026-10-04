"""
آزمون فهرست رصد — نشست ۷ب، کار یک، تصمیم‌های کاربر ۳ و ۴ اکتبر ۲۰۲۶.

میدان watch در analysts.yml برای هر منبع صریح است:
  full          دیدن کامل — کریپتوسیتی، تکرارگر، کوون
  crypto_title  دیدن کامل فقط وقتی عنوان درباره کریپتوست — سالووی، با فهرست کلیدواژه
  text          فقط متن — بقیه
مقدار ناشناخته، میدان غایب، یا منبع خاموش در فهرست رصد خطای بلند است، نه پیش‌فرض بی‌صدا.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import radar_intake as I
import radar_video as V

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "analysts.yml"

SOLOWAY_KEYWORDS = [
    "bitcoin", "btc", "crypto", "cryptocurrency", "cryptocurrencies", "ethereum", "eth", "ether",
    "xrp", "ripple", "solana", "altcoin", "altseason", "blockchain", "coinbase", "microstrategy",
    "mstr", "saylor", "stablecoin", "dogecoin", "doge", "cardano", "chainlink", "binance", "halving",
    "ibit", "defi",
]


def _src(key="x", **kw) -> I.Source:
    d = {"name_fa": key, "kind": "youtube", "channel_id": "UC" + "a" * 22, "enabled": True}
    d.update(kw)
    return I.Source.from_dict(key, d)


# ─────────── analysts.yml واقعی ───────────

def test_real_config_watch_modes() -> None:
    s = {x.key: x.watch for x in I.load_sources(CFG)}
    assert s == {
        "joseph_wang": "text", "kaiko": "text", "bob_elliott": "text", "ray_dalio": "text",
        "tradecity_pro": "text", "no_bs_crypto": "text", "cryptocity_pro": "full",
        "tekrargar": "full", "benjamin_cowen": "full", "gareth_soloway": "crypto_title",
        "raoul_pal": "text", "virtualbacon": "text", "arshia_course": "text",
    }


def test_real_config_has_no_watch_errors() -> None:
    assert V.watch_errors(I.load_sources(CFG)) == []


def test_real_config_soloway_keywords_are_the_approved_list() -> None:
    s = {x.key: x for x in I.load_sources(CFG)}
    assert s["gareth_soloway"].watch_keywords == SOLOWAY_KEYWORDS


def test_watch_list_returns_the_four_watched_sources() -> None:
    assert [s.key for s in V.watch_list(CFG)] == [
        "cryptocity_pro", "tekrargar", "benjamin_cowen", "gareth_soloway"]


# ─────────── خطای بلند ───────────

def test_unknown_value_is_loud() -> None:
    errs = V.watch_errors([_src("a", watch="maybe")])
    assert len(errs) == 1 and "a" in errs[0] and "maybe" in errs[0]


def test_missing_field_is_loud() -> None:
    errs = V.watch_errors([_src("a")])
    assert len(errs) == 1 and "a" in errs[0] and "watch" in errs[0]


@pytest.mark.parametrize("mode", ["full", "crypto_title"])
def test_disabled_source_in_watch_list_is_loud(mode) -> None:
    kw = {"watch_keywords": ["bitcoin"]} if mode == "crypto_title" else {}
    errs = V.watch_errors([_src("a", watch=mode, enabled=False, disabled_reason="x", **kw)])
    assert len(errs) == 1 and "خاموش" in errs[0]


def test_disabled_text_source_is_fine() -> None:
    assert V.watch_errors([_src("a", watch="text", enabled=False, disabled_reason="x")]) == []


@pytest.mark.parametrize("kind", ["rss", "index", "playlist"])
def test_non_youtube_full_view_is_loud(kind) -> None:
    errs = V.watch_errors([_src("a", watch="full", kind=kind)])
    assert len(errs) == 1 and "youtube" in errs[0]


def test_crypto_title_without_keywords_is_loud() -> None:
    assert V.watch_errors([_src("a", watch="crypto_title")])


def test_keywords_outside_crypto_title_are_loud() -> None:
    assert V.watch_errors([_src("a", watch="full", watch_keywords=["bitcoin"])])
    assert V.watch_errors([_src("b", watch="text", watch_keywords=["bitcoin"])])


@pytest.mark.parametrize("bad", ["بیت‌کوین", "bit coin", "btc.*", "", "BTC", 7])
def test_keyword_must_be_lowercase_ascii_word(bad) -> None:
    assert V.watch_errors([_src("a", watch="crypto_title", watch_keywords=["bitcoin", bad])])


def test_watch_list_raises_on_bad_config(tmp_path) -> None:
    cfg = tmp_path / "analysts.yml"
    cfg.write_text("sources:\n  a:\n    name_fa: a\n    kind: youtube\n    watch: maybe\n",
                   encoding="utf-8")
    with pytest.raises(V.WatchConfigError, match="maybe"):
        V.watch_list(cfg)


# ─────────── عنوان کریپتویی ───────────

@pytest.mark.parametrize("title", [
    "Bitcoin Breakout Imminent?", "BTC & ETH: Next Move", "Is the Altseason Over?",
    "Why Crypto Will Explode", "$XRP to $5?", "Bitcoins vs Gold", "MicroStrategy's Big Bet",
    "ETH/BTC ratio", "BITCOIN CRASH", "S&P 500 and Bitcoin", "Altcoins Are Breaking Out",
    "Dogecoin Pumps",
])
def test_crypto_titles_match(title) -> None:
    assert V.title_matches(title, SOLOWAY_KEYWORDS)


@pytest.mark.parametrize("title", [
    "Stock Market Crash Coming!", "Gold Hits All Time High", "NVIDIA Earnings Preview",
    "Solar Stocks Soar", "Ethics in Trading", "Bitcoinization of Nothing", "The Cryptoverse",
    "Silver Breakout", "",
])
def test_non_crypto_titles_do_not_match(title) -> None:
    assert not V.title_matches(title, SOLOWAY_KEYWORDS)


def test_wants_full_view() -> None:
    full = _src("a", watch="full")
    title = _src("b", watch="crypto_title", watch_keywords=["bitcoin"])
    text = _src("c", watch="text")
    assert V.wants_full_view(full, "Gold only")
    assert V.wants_full_view(title, "Bitcoin now") and not V.wants_full_view(title, "Gold only")
    assert not V.wants_full_view(text, "Bitcoin now")
