"""
نگهبان سراسری آزمون‌ها: هیچ آزمونی فایل داده واقعی مخزن را تغییر ندهد.

درس نشست ۳: آزمون‌های فرمان radar_positions.py مسیر --optcost نمی‌دادند،
پس پس از سیم‌کشی دفتر هزینه فرصت، هر اجرای کامل آزمون‌ها رکورد ساختگی در
radar_optcost.json واقعی می‌نوشت — ۱۵ رکورد پیش از آنکه دیده شود. آلودگی
داده کالیبراسیون از هر باگ کد بدتر است، چون بی‌صدا در حساب واقعی می‌نشیند.

درس رویداد ۶۱ و ک۶۴، نشست ۷: نگهبان پیشین پیش و پس از هر آزمون محتوای
فایل‌ها را می‌سنجید و تغییر را برمی‌گرداند. ولی نوشتن هم‌زمان جلسه دیگر را از
خرابی آزمون تشخیص نمی‌داد و پاکش می‌کرد — watch.json، ۳ اکتبر ۲۰۲۶.

قاعده تازه، دو لایه:
  ۱) رونوشت موقت. هر آزمون در پوشه موقتی اجرا می‌شود که رونوشت فایل‌های داده
     را دارد؛ مسیر پیش‌فرض نسبی به رونوشت می‌رسد. radar_journal.DB تنها مسیر
     مطلق است و به رونوشت وصل می‌شود.
  ۲) تله نوشتن. قلاب ممیزی پایتون فقط فراخوان‌های همین فرایند را می‌بیند. اگر
     خود آزمون فایل واقعی را برای نوشتن باز کند، جابه‌جا کند یا پاک کند، آزمون
     قرمز می‌شود. هیچ‌چیز برگردانده نمی‌شود؛ نوشتن فرایند بیرونی اصلاً به این
     قلاب نمی‌رسد، پس سالم می‌ماند.

محدودیت — ف۱۹: زیرفرایندی که خود آزمون بسازد و با مسیر مطلق بنویسد از قلاب
پنهان است. زیرفرایند پوشه کاری موقت را به ارث می‌برد، پس مسیر نسبی‌اش امن است.
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA_FILES = ("book_state.json", "holdings.json", "radar_journal.json",
              "radar_optcost.json", "regime.json", "regime_history.json",
              "snapshot.json", "watch.json", "watch_state.json",
              "events_ledger.json",                        # دفتر رویداد — نشست ۱۰
              "pump.json", "pump_ledger.json")             # اسکنر پامپ — نشست ۹
REAL = {os.path.normcase(str(ROOT / n)): n for n in DATA_FILES}

# شناسه آزمون در جریان و نوشتن‌های دیده‌شده — قلاب فقط در این بازه ثبت می‌کند
_CURRENT: dict = {"test": None, "hits": []}
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC


def _real_name(path) -> str | None:
    """نام فایل داده واقعی اگر این مسیر به آن برسد، وگرنه None."""
    if isinstance(path, int) or not isinstance(path, (str, bytes, os.PathLike)):
        return None
    try:
        full = os.path.normcase(os.path.abspath(os.fsdecode(path)))
    except (TypeError, ValueError):
        return None
    return REAL.get(full)


def _audit(event: str, args: tuple) -> None:
    if _CURRENT["test"] is None:
        return
    if event == "open":
        path, mode, flags = args
        writes = (any(c in mode for c in "wax+") if isinstance(mode, str)
                  else bool((flags or 0) & _WRITE_FLAGS))
        paths = [path] if writes else []
    elif event == "os.rename":                  # os.replace و shutil.move هم همین رویداد را دارند
        paths = list(args[:2])
    elif event in ("os.remove", "os.truncate"):
        paths = [args[0]]
    else:
        return
    for p in paths:
        name = _real_name(p)
        if name:
            _CURRENT["hits"].append(f"{event} {name}")


sys.addaudithook(_audit)


@pytest.fixture(autouse=True)
def _real_data_untouched(tmp_path_factory, monkeypatch):
    copy = tmp_path_factory.mktemp("data_copy")
    for n in DATA_FILES:
        if (ROOT / n).exists():
            (copy / n).write_bytes((ROOT / n).read_bytes())
    monkeypatch.chdir(copy)
    if (ROOT / "radar_journal.py").exists():
        import radar_journal
        monkeypatch.setattr(radar_journal, "DB", str(copy / os.path.basename(radar_journal.DB)))
    _CURRENT["test"], _CURRENT["hits"] = True, []
    yield
    hits = list(dict.fromkeys(_CURRENT["hits"]))
    _CURRENT["test"], _CURRENT["hits"] = None, []
    assert not hits, f"آزمون فایل داده واقعی را نوشت — برگردانده نشد، با git diff ببین: {hits}"


class NetworkInTest(RuntimeError):
    """آزمون به شبکه رفت — قاعده ثابت نشست‌ها: آزمون بدون شبکه."""


@pytest.fixture(autouse=True)
def _no_network(monkeypatch, request):
    """
    نگهبان دوم، نشست ۳: هر درخواست requests خطای صریح می‌دهد. پیش از این
    قاعده «آزمون بدون شبکه» فقط قرارداد بود؛ سیم‌کشی میانگین پنجاه‌هفته در
    main رژیم دو آزمون را بی‌صدا به OKX و Gate می‌برد. خطای شبکه عادی نیست،
    تا کدی که خطای شبکه را می‌گیرد آن را نبلعد.
    """
    try:
        import requests
    except ImportError:
        yield
        return

    def boom(self, method, url, *a, **k):
        raise NetworkInTest(f"{request.node.nodeid}: درخواست شبکه در آزمون — {method} {url}")
    monkeypatch.setattr(requests.sessions.Session, "request", boom)
    yield
