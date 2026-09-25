"""
نگهبان سراسری آزمون‌ها: هیچ آزمونی فایل داده واقعی مخزن را تغییر ندهد.

درس نشست ۳: آزمون‌های فرمان radar_positions.py مسیر --optcost نمی‌دادند،
پس پس از سیم‌کشی دفتر هزینه فرصت، هر اجرای کامل آزمون‌ها رکورد ساختگی در
radar_optcost.json واقعی می‌نوشت — ۱۵ رکورد پیش از آنکه دیده شود. آلودگی
داده کالیبراسیون از هر باگ کد بدتر است، چون بی‌صدا در حساب واقعی می‌نشیند.

پیش از هر آزمون محتوای فایل‌های داده خوانده می‌شود. اگر پس از آن فرق کرد،
محتوای اصلی برگردانده و آزمون قرمز می‌شود — پس مخزن حتی وقتی آزمونی
خطا دارد تمیز می‌ماند.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA_FILES = ("book_state.json", "holdings.json", "radar_journal.json",
              "radar_optcost.json", "regime.json", "regime_history.json",
              "snapshot.json", "watch.json", "watch_state.json")


def _snapshot() -> dict:
    return {n: (ROOT / n).read_bytes() if (ROOT / n).exists() else None
            for n in DATA_FILES}


@pytest.fixture(autouse=True)
def _real_data_untouched():
    before = _snapshot()
    yield
    after = _snapshot()
    changed = [n for n in DATA_FILES if before[n] != after[n]]
    for n in changed:
        p = ROOT / n
        if before[n] is None:
            p.unlink()
        else:
            p.write_bytes(before[n])
    assert not changed, f"آزمون فایل داده واقعی را تغییر داد — برگردانده شد: {changed}"
