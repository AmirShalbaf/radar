"""
آزمون بلوغ میانگین دویست‌روزه — نشست ۱ نقشه رادار ۷، مورد ۱.

باگ: اسکن و چرخش ۶۰۰ کندل می‌خواستند. صرافی کندل باز امروز را هم
می‌فرستد و آن جدا می‌شود، پس ۵۹۹ کندل بسته می‌ماند. شرط بلوغ ۶۰۰ است.
نتیجه: از ۱۴ سپتامبر میانگین دویست‌روزه همه نمادها، حتی بیت‌کوین،
«نابالغ» گزارش می‌شد.

همین خطا در radar_fetch3.py برعکس بود: snapshot کندل باز را هم
می‌شمرد و با ۵۹۹ کندل بسته برچسب «بالغ» می‌زد. radar_book.py هم فقط
۲۶۰ کندل می‌گرفت و کندل باز را جدا نمی‌کرد.

ترفند آزمون: صرافی ساختگی **دقیقاً** به اندازه درخواست کندل می‌دهد و
آخرینش باز است — رفتار واقعی گیت و بایننس. پس تعداد درخواستی و آستانه
بلوغ به هم قفل می‌شوند: هر کدام بی دیگری عوض شود، آزمون قرمز می‌شود.

آستانه قاعده اینجا مستقل از ثابت کد نوشته شده — از CLAUDE.md، قاعده ۱.
اگر ثابت کد اشتباه عوض شود، آزمون رفتاری آن را می‌گیرد.
"""
import inspect
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_book as B
import radar_fetch3 as R
import radar_levels as L
import radar_rotate as RT
import radar_scan as S

COLS = ["ts", "open", "high", "low", "close", "vol"]

# قاعده بلوغ ۳n برای میانگین نمایی ۲۰۰ — عمداً عدد، نه ثابت کد
RULE_BARS = 3 * 200
# حالت عمیق تحلیل تک‌نماد: ۱۵۰۰ کندل بسته
RULE_BARS_DEEP = 1500


def _px(i: int) -> float:
    """قیمت مصنوعی با روند و نوسان — تا میانگین‌ها از هم جدا شوند."""
    return 100 + 0.05 * i + 5 * math.sin(i / 7)


def _frame(n: int, open_close: float | None = None) -> pd.DataFrame:
    """
    قاب روزانه مصنوعی با اندیکاتور، به قالب radar_fetch3.py.
    n سطر، که آخرینش کندل باز است.

    open_close پیش از محاسبه اندیکاتور جا می‌نشیند — سناریوی واقعی:
    enrich روی قاب کامل با کندل باز اجرا می‌شود.
    """
    open_ts = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=2)
    rows = []
    for i in range(n):
        ts = open_ts - pd.Timedelta(days=n - 1 - i)
        p = _px(i)
        rows.append([int(ts.timestamp() * 1000), p, p * 1.02, p * 0.98, p,
                     1000.0 + i])
    if open_close is not None:
        rows[-1][4] = open_close
        rows[-1][2] = max(rows[-1][2], open_close)
    return R.enrich(R._df(rows, COLS, bar="1D"))


# ═══════════════ ثابت‌های اصلی در radar_fetch3.py ═══════════════

def test_constants_follow_rule() -> None:
    """ثابت‌ها از قاعده ۳n می‌آیند، به‌علاوه یک کندل باز."""
    assert R.EMA200_MATURE_BARS == RULE_BARS
    assert R.DAILY_WANT == R.EMA200_MATURE_BARS + 1
    assert R.DAILY_WANT_DEEP - 1 >= RULE_BARS_DEEP


# ═══════════════ اسکن و چرخش با صرافی صادق ═══════════════

@pytest.fixture
def honest_venue(monkeypatch):
    """صرافی ساختگی: دقیقاً want کندل، آخرینش باز. تعداد درخواستی ضبط می‌شود."""
    asked: list[int] = []

    def fake(base, order, want, tests):
        asked.append(want)
        return {"1D": _frame(want)}, "okx", None

    monkeypatch.setattr(R, "candles_first_ok", fake)
    monkeypatch.setattr(R, "gather_venues", lambda *a, **k: ({}, {}, {}, {}))
    monkeypatch.setattr(R, "FAILURES", [])
    return asked


def test_scan_matures_with_honest_venue(honest_venue) -> None:
    """اسکن: پس از جداشدن کندل باز، هنوز ۶۰۰ کندل بسته بماند."""
    row = S.score_symbol("TEST", ["okx"], None)
    assert row is not None
    assert row["bars"] >= RULE_BARS
    assert row["ema200_mature"] is True
    assert "vs_ema200" in row


def test_rotate_matures_with_honest_venue(honest_venue) -> None:
    """چرخش: همان قفل."""
    row = RT.analyze("TEST", ["okx"], R._closed(_frame(400)))
    assert row is not None
    assert row["bars"] >= RULE_BARS
    assert row["e200_mature"] is True
    assert row["e200"] is not None


# ═══════════════ تحلیل تک‌نماد، عادی و عمیق ═══════════════

class _Stop(Exception):
    """توقف عمدی run3 پس از ضبط تعداد درخواستی — بدون شبکه."""


@pytest.mark.parametrize("deep, need", [(False, RULE_BARS),
                                        (True, RULE_BARS_DEEP)])
def test_single_symbol_requests_enough(monkeypatch, deep, need) -> None:
    """درخواست منهای کندل باز باید به آستانه برسد."""
    asked: list[int] = []

    def fake(base, order, want, tests):
        asked.append(want)
        raise _Stop

    monkeypatch.setattr(R, "probe_venues", lambda order: (list(order), []))
    monkeypatch.setattr(R, "candles_first_ok", fake)
    with pytest.raises(_Stop):
        R.run3("TEST", 0.0, "trade", None, deep, ["okx"])
    assert asked, "candles_first_ok صدا زده نشد"
    assert asked[0] - 1 >= need


# ═══════════════ snapshot در radar_fetch3.py ═══════════════

def _ema200_line(md: str) -> str:
    return next(l for l in md.splitlines() if l.startswith("| EMA ۲۰۰"))


def test_snapshot_599_closed_is_immature() -> None:
    """۶۰۰ سطر با یک باز یعنی ۵۹۹ بسته — نابالغ. کندل باز شمرده نشود."""
    md = R.snapshot(_frame(RULE_BARS), "روزانه")
    assert "نابالغ" in _ema200_line(md)
    assert "هشدار بلوغ" in md


def test_snapshot_600_closed_is_mature() -> None:
    """۶۰۱ سطر با یک باز یعنی ۶۰۰ بسته — بالغ."""
    md = R.snapshot(_frame(RULE_BARS + 1), "روزانه")
    assert "نابالغ" not in _ema200_line(md)
    assert "هشدار بلوغ" not in md


def test_snapshot_count_line_is_closed_count() -> None:
    """سطر «تعداد کندل» هم کندل بسته را بشمارد، هم‌سو با برچسب بلوغ."""
    md = R.snapshot(_frame(RULE_BARS + 1), "روزانه")
    assert f"تعداد کندل: {RULE_BARS}" in md


def test_snapshot_ema200_value_from_closed_frame() -> None:
    """
    قفل، نه قرمز: مقدار میانگین از سطر آخرِ **بسته** خوانده می‌شود.
    میانگین نمایی علّی است، پس مقدار آن سطر فقط از کندل‌های بسته می‌آید.
    کندل باز عمداً ده برابر است تا خواندن از قاب کامل دیده شود.
    """
    df = _frame(700, open_close=_px(699) * 10)
    closed = R._closed(df)
    want = R.fmt_num(float(R.ema(closed["close"], 200).iloc[-1]))
    full = R.fmt_num(float(R.ema(df["close"], 200).iloc[-1]))
    assert want != full, "آزمون تمایزدهنده نیست"
    assert f"| EMA ۲۰۰ | {want} |" in R.snapshot(df, "روزانه")


# ═══════════════ متن گزارش اسکن — تک‌منبع ═══════════════

def _imm_rows() -> list[dict]:
    return [{"symbol": "AAA", "score": 0.3, "covered": 5, "price": 1.0,
             "ema200_mature": False, "bars": 650, "date": "2026-09-23",
             "venue": "okx"}]


def test_scan_report_threshold_from_constant(monkeypatch) -> None:
    """
    عدد آستانه در متن هشدار از ثابت بیاید، نه دستی — درس رویداد ۲۲:
    متنی که در دو جا نوشته شود، دیر یا زود از هم جدا می‌افتد.
    """
    monkeypatch.setattr(R, "EMA200_MATURE_BARS", 700)
    rep = S.build_scan_report(_imm_rows(), {}, {}, ["okx"], 5, [])
    assert "کمتر از ۷۰۰ کندل" in rep
    assert "| AAA | 650 | ۷۰۰ |" in rep
    assert "۶۰۰" not in rep


def test_scan_report_threshold_persian_digits() -> None:
    """قفل، نه قرمز: خروجی امروز همان بماند — آستانه با رقم فارسی."""
    rep = S.build_scan_report(_imm_rows(), {}, {}, ["okx"], 5, [])
    assert "کمتر از ۶۰۰ کندل" in rep
    assert "| AAA | 650 | ۶۰۰ |" in rep


# ═══════════════ radar_levels.py — استقلال با ثابت محلی ═══════════════

def test_levels_default_fetch_is_enough() -> None:
    """پیش‌فرض واکشی منهای کندل باز باید به آستانه برسد."""
    d = inspect.signature(L.okx_candles).parameters["want"].default
    assert d - 1 >= RULE_BARS


def test_levels_local_constant_matches_canonical() -> None:
    """ثابت محلی از ثابت اصلی جدا نیفتد — همان الگوی نگهبان پوچ."""
    assert L.DAILY_WANT == R.DAILY_WANT


# ═══════════════ radar_book.py — فقط بخش بلوغ ═══════════════

class _Resp:
    def __init__(self, payload, status: int = 200):
        self._p = payload
        self.status_code = status

    def json(self):
        return self._p


def _gate_rows(n: int, open_close: float | None = None) -> list:
    """قالب گیت: [زمان به ثانیه، حجم مظنه، بسته، بالا، پایین، باز، حجم پایه]."""
    open_ts = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=2)
    out = []
    for i in range(n):
        ts = open_ts - pd.Timedelta(days=n - 1 - i)
        p = _px(i)
        if i == n - 1 and open_close is not None:
            p = open_close
        out.append([str(int(ts.timestamp())), "1000", str(p), str(p * 1.02),
                    str(p * 0.98), str(p), "10"])
    return out


def _gate_requests(open_close: float | None = None):
    """گیت ساختگی: دقیقاً به اندازه limit کندل، آخرینش باز."""
    def get(url, params=None, timeout=None):
        return _Resp(_gate_rows(int(params["limit"]), open_close))
    return SimpleNamespace(get=get)


def _okx_requests(n_total: int):
    """اوکی‌اکس ساختگی: صفحه‌های ۱۰۰تایی، جدید به قدیم، پرچم تأیید در اندیس ۸."""
    open_ts = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=2)
    rows = []
    for i in range(n_total - 1, -1, -1):
        ts = open_ts - pd.Timedelta(days=n_total - 1 - i)
        p = _px(i)
        conf = "0" if i == n_total - 1 else "1"
        rows.append([str(int(ts.timestamp() * 1000)), str(p), str(p * 1.02),
                     str(p * 0.98), str(p), "10", "1000", "1000", conf])

    def get(url, params=None, timeout=None):
        page = rows
        if "after" in params:
            page = [r for r in rows if int(r[0]) < int(params["after"])]
        return _Resp({"code": "0", "data": page[:int(params["limit"])]})
    return SimpleNamespace(get=get)


def test_book_local_constant_matches_canonical() -> None:
    """ثابت محلی radar_book.py از ثابت اصلی جدا نیفتد."""
    assert B.DAILY_WANT == R.DAILY_WANT


@pytest.mark.parametrize("fn", ["candles", "okx_candles", "gate_candles"])
def test_book_default_fetch_is_enough(fn) -> None:
    """پیش‌فرض هر سه تابع واکشی منهای کندل باز باید به آستانه برسد."""
    d = inspect.signature(getattr(B, fn)).parameters["want"].default
    assert d - 1 >= RULE_BARS


def test_book_gate_path_matures(monkeypatch) -> None:
    """مسیر گیت: کندل باز از زمان تشخیص داده شود و بلوغ برسد."""
    monkeypatch.setattr(B, "requests", _gate_requests())
    df = B.gate_candles("TEST")
    assert int(df["confirm"].iloc[-1]) == 0
    assert (df["confirm"].iloc[:-1] == 1).all()
    sc = B.score_position(df, None)
    assert sc["bars"] >= RULE_BARS
    assert sc["mature"] is True


def test_book_okx_path_reads_flag(monkeypatch) -> None:
    """مسیر اوکی‌اکس: پرچم تأیید صرافی عددی شود و بلوغ برسد."""
    monkeypatch.setattr(B, "requests", _okx_requests(1000))
    df = B.okx_candles("TEST")
    assert int(df["confirm"].iloc[-1]) == 0
    assert (df["confirm"].iloc[:-1] == 1).all()
    sc = B.score_position(df, None)
    assert sc["bars"] >= RULE_BARS
    assert sc["mature"] is True


def test_book_599_closed_is_immature(monkeypatch) -> None:
    """۶۰۰ سطر با یک باز یعنی ۵۹۹ بسته — نابالغ. کندل باز شمرده نشود."""
    monkeypatch.setattr(B, "requests", _gate_requests())
    sc = B.score_position(B.gate_candles("TEST", RULE_BARS), None)
    assert sc["mature"] is False


def test_book_price_live_structure_closed(monkeypatch) -> None:
    """
    قیمت از کندل زنده، ساختار از کندل بسته — قاعده radar_levels.py.
    کندل باز عمداً ده برابر است تا اندیکاتور آلوده دیده شود.
    """
    live = _px(699) * 10
    monkeypatch.setattr(B, "requests", _gate_requests(open_close=live))
    df = B.gate_candles("TEST", 700)
    closed_c = df.loc[df["confirm"] == 1, "c"].reset_index(drop=True)
    sc = B.score_position(df, None)
    assert sc["price"] == pytest.approx(live)
    assert sc["e20"] == pytest.approx(float(B.ema(closed_c, 20).iloc[-1]))
    assert sc["e50"] == pytest.approx(float(B.ema(closed_c, 50).iloc[-1]))
    assert sc["e200"] == pytest.approx(float(B.ema(closed_c, 200).iloc[-1]))
    assert sc["rsi"] == round(float(B.rsi_wilder(closed_c).iloc[-1]), 1)


def test_book_relative_strength_untouched(monkeypatch) -> None:
    """
    قفل، نه قرمز: قدرت نسبی در این مورد عمداً دست نمی‌خورد.
    همان فرمول قبلی روی قاب کامل — تغییرش مال نشست ۱۲ است.
    """
    monkeypatch.setattr(B, "requests", _gate_requests())
    df = B.gate_candles("TEST", 700)
    btc = B.gate_candles("BTC", 700)
    btc["c"] = btc["c"] * 0.9 + 3.0
    a0, a1 = float(df["c"].iloc[-31]), float(df["c"].iloc[-1])
    b0, b1 = float(btc["c"].iloc[-31]), float(btc["c"].iloc[-1])
    old = (a1 / a0 - 1) - (b1 / b0 - 1)
    sc = B.score_position(df, btc)
    assert sc["rs30"] == round(old, 4)


# ═══════════════ متن و منطق بلوغ در چرخش و سبد — تک‌منبع ═══════════════
#
# همان درس رویداد ۲۲: عدد «۶۰۰» در متن دستی نوشته شده بود. اگر آستانه
# عوض شود، متن دروغ می‌گوید. در چرخش منطق هم `3 * span` محلی بود؛ حالا
# متن و منطق هر دو از R.EMA200_MATURE_BARS می‌آیند.

def test_rotate_logic_and_text_follow_constant(monkeypatch) -> None:
    """آستانه ۷۰۰، قاب با ۶۵۰ کندل بسته: منطق نابالغ بگوید و متن ۷۰۰."""
    monkeypatch.setattr(R, "EMA200_MATURE_BARS", 700)
    monkeypatch.setattr(R, "candles_first_ok",
                        lambda *a, **k: ({"1D": _frame(651)}, "okx", None))
    monkeypatch.setattr(R, "FAILURES", [])
    row = RT.analyze("TEST", ["okx"], R._closed(_frame(400)))
    assert row["bars"] == 650
    assert row["e200_mature"] is False
    assert row["e200"] is None
    row["vol24"] = 1e7
    row["score"], row["cov"], row["flags"], row["raw"], row["norm"] = RT.score(row)
    rep = RT.build_report([row], 1, 1, ["okx"], 0, {})
    assert "کمتر از ۷۰۰ کندل" in rep
    assert "| TEST | 650 | ۷۰۰ |" in rep
    assert "۶۰۰" not in rep


def test_book_note_follows_constant(monkeypatch) -> None:
    """یادداشت بلوغ سبد از همان ثابتی بیاید که منطقش از آن می‌آید."""
    monkeypatch.setattr(B, "EMA200_MATURE_BARS", 700)
    monkeypatch.setattr(B, "requests", _gate_requests())
    sc = B.score_position(B.gate_candles("TEST", 651), None)
    assert sc["mature"] is False
    assert any("کمتر از ۷۰۰ کندل" in n for n in sc["notes"])
    assert not any("۶۰۰" in n for n in sc["notes"])
