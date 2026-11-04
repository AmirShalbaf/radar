# قرارداد لایه پیام رادار — متن ۳۷

> این سند رابط پایدار میان «درون رادار» و «پیام تلگرام» است. هر بازبینی رادار — از
> جمله بازبینی کلی با Fable — می‌تواند درون رادار را عوض کند؛ این رابط فقط با نسخه
> تازه و آزمون سبز عوض می‌شود.

## سه طبقه

1. **سازنده‌ها** — `radar_scan.py`، `radar_book.py`، `radar_levels.py`، `radar_context.py` —
   گزارش مارک‌داونشان را مثل قبل می‌نویسند و با `--json` یک سند کناری هم در `reports/`
   می‌گذارند: `scan.json`، `book.json`، `levels.json`، `context.json`. ساخت سند با تابع خود
   سازنده است: `scan_doc`، `book_doc`، `levels_doc`، و همان ردیف‌های `gather` در زمینه.
   مقدار ساده یا تهی، با `radar_sidecar.py`؛ عدد پوچ کلیدش می‌ماند و تهی می‌شود.
2. **مترجم** — `radar_brief.py` — تنها فایلی که درون رادار را می‌شناسد. سندهای کناری و
   فایل‌های داده را می‌خواند و `reports/brief.json` را می‌سازد.
3. **نمایش و ارسال** — `radar_brief_render.py` و `radar_telegram.py` — فقط `brief.json` را
   می‌خوانند.

## قاعده‌ها

- **نمایش‌دهنده هیچ فایل دیگری از رادار را نمی‌خواند.** تنها استثنا تابع‌های بی‌وضعیت
  مترجم برای تاریخ و جدول باند `radar_budget.BANDS` است.
- **تغییر هر سازنده یا فایل داده فقط مترجم را عوض می‌کند.** آزمون‌های
  `tests/test_brief_contract.py` سند هر سازنده را با تابع خود سازنده می‌سازند و به مترجم
  می‌دهند؛ تغییر ناسازگار پیش از push قرمز می‌شود.
- **هر بخش جداست.** خطای یک بخش فقط همان را `ok: false` با `why` می‌کند. پیام می‌رود و
  فهرست بخش‌های افتاده در خود پیام می‌آید — «⚠️ داده ندارم».
- **سند کناری کهنه رد می‌شود.** بیش از `MAX_SIDECAR_AGE_H` ساعت یعنی سازنده امروز نیفتاده
  نوشته؛ «داده ندارم — کهنه»، نه عدد دیروز با برچسب امروز.
- **هیچ روزی بی پیام نیست.** تصویر نشد ← حکم در پیام HTML. HTML نشد ← متن ساده. هیچ‌کدام
  نشد ← کد ۴ و گام پشتیبان گردش‌کار، یعنی خلاصه قدیمی `LATEST.md`.
- **`reports/LATEST.md` دست نمی‌خورد.** تحلیلگر صبح و نگهبان تکرار روزانه آن را می‌خوانند.
- **یک تعریف فاصله:** افت لازم تا سطح = `100 × (قیمت − سطح) ÷ قیمت`؛ حرکت علامت‌دار تا
  ماشه = `100 × (سطح ÷ قیمت − 1)`. هر دو در `radar_brief.py`.

## شکل `brief.json` — نسخه ۱

```
schema: 1
generated, day, clock          — مهر جهانی؛ روز شمسی و ساعت تهران
verdict:  level green|red|unknown، headline، must، overdue، setups، windows
sections: هر بخش {ok: true, ...} یا {ok: false, why}
  capital    total، stable_usd، stable_pct، target_pct، assets، pos_risk_usd، pos_risk_pct
  positions  rows[symbol، value، price، invalidation، drop_pct، tier، week_chg_pct]، min_drop_pct
  regime     score، band، trade_band، cap_pct، mult، maxpos، stable_target، up، down، pillars
  winds      items[label، score، dir]، neg، neu، pos — ورودی‌های خود مدل رژیم
  market     btc{price، chg24، rsi، sma50w، above_sma_pct}، fear_greed، btc_dominance،
             stable_30d، crowd، crowd_flagged، crowd_n، funding_avg
  context    rows[short، value، unit، chg، chg_unit، lag_days]
  calendar   items[at، date، name، importance، window]، next_high_h
  triggers   items[symbol، kind، level، judge، label، price، move_pct]، total
  trade      risk_cap_usd، risk_used_usd، mult، maxpos، levels_candidates، pump_*، setups_ready
  scorecard  exits، forecasts_open، scored_n، brier_mean
  todo       items[level red|amber|info، text]
  health     count، max_gap_h، stale_hours، last_age_h، bad — از radar_schedule.health_stats
  lesson     id، title، points، practice — از references/lessons.json
  chart      series[symbol، points، levels، marks]
failed:   [{name، title، why}]
lesson_history: [{at، id}] — برای چرخش درس
```

## تغییر قرارداد

- **افزودن** کلید یا بخش: بی تغییر نسخه، با آزمون.
- **حذف یا تغییر معنی**: `SCHEMA` بالا می‌رود، نمایش‌دهنده هم‌زمان عوض می‌شود، و این سند
  به‌روز می‌شود.
- **درس تازه**: فقط `references/lessons.json`؛ شرط روی مسیر همین بخش‌ها.

## گام‌های بعد — ک۱۲۹

متن ۳۸ هشدارها، متن ۳۹ لایه خبر و درس، متن ۴۰ دوطرفه‌کردن. هر سه روی همین قرارداد.
