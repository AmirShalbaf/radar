# سنجش دسترسی منابع — 2026-10-08

`radar_probe.py` 1.0 — نشست ۱۰، ایستگاه ۱.

| مورد | مقدار |
|---|---|
| محیط | گیت‌هاب |
| کشور آی‌پی خروجی | CA |
| زمان | 2026-10-08 07:36 UTC |
| اجرای گردش‌کار | `37744407981` |
| تصویر اجراکننده | `ubuntu26` 20260927.149.1 |

۱۷ از ۲۱ منبع باز. «پاسخ بی‌نشانه» یعنی پاسخ آمد ولی نشانه محتوای درست در آن نبود — مثل پیام «کلید لازم است». ستون توضیح عنوان صفحه یا آغاز پاسخ است.

| دسته | منبع | شناسه مرورگر | کد | اندازه (بایت) | زمان (ثانیه) | داوری | توضیح |
|---|---|---|---|---|---|---|---|
| تقویم کلان | `fed-calendar-json` | bot | 200 | 544,133 | 0.1 | ✅ باز | — |
| تقویم کلان | `fed-fomc-page` | bot | 200 | 165,751 | 0.1 | ✅ باز | — |
| تقویم کلان | `fred-calendar-cpi` | bot | 200 | 67,056 | 1.4 | ✅ باز | — |
| تقویم کلان | `bea-ics` | bot | 200 | 42,706 | 0.3 | ✅ باز | — |
| تقویم کلان | `bea-ics-browser` | browser | 200 | 42,706 | 0.1 | ✅ باز | — |
| تقویم کلان | `bls-ics` | bot | 403 | 1,325 | 0.2 | ❌ بسته | Access Denied |
| تقویم کلان | `bls-ics-browser` | browser | 403 | 1,325 | 0.0 | ❌ بسته | Access Denied |
| آزادسازی و عرضه | `llama-emissions-api` | bot | 402 | 66 | 0.1 | ❌ بسته | Upgrade to the paid API plan at https://defillama.com/subscription |
| آزادسازی و عرضه | `llama-ds-list` | bot | 200 | 4,352 | 0.1 | ✅ باز | — |
| آزادسازی و عرضه | `llama-ds-protocol` | bot | 200 | 352,016 | 0.0 | ✅ باز | — |
| آزادسازی و عرضه | `llama-ds-index` | bot | 200 | 22,326,237 | 0.7 | ✅ باز | — |
| آزادسازی و عرضه | `coingecko-markets` | bot | 200 | 1,584 | 0.2 | ✅ باز | — |
| سه منبع تکرارگر | `farside-btc` | browser | 200 | 272,626 | 0.8 | ✅ باز | — |
| سه منبع تکرارگر | `farside-btc-bot` | bot | 200 | 272,626 | 0.4 | ✅ باز | — |
| سه منبع تکرارگر | `coinglass-api` | bot | 200 | 39 | 0.4 | ⚠️ پاسخ بی‌نشانه | {"code":"401","msg":"API key missing."} |
| سه منبع تکرارگر | `coinglass-site` | browser | 200 | 344,056 | 0.3 | ✅ باز | — |
| سه منبع تکرارگر | `ff-json` | bot | 200 | 11,199 | 0.3 | ✅ باز | — |
| سه منبع تکرارگر | `ff-xml` | bot | 200 | 28,585 | 0.0 | ✅ باز | — |
| سه منبع تکرارگر | `ff-site` | browser | 200 | 404,661 | 0.2 | ✅ باز | — |
| شاهد | `okx-candles` | bot | 200 | 262 | 0.3 | ✅ باز | — |
| شاهد | `fred-graph` | bot | 200 | 424,171 | 0.1 | ✅ باز | — |

نشانی‌ها:

- `fed-calendar-json`: https://www.federalreserve.gov/json/calendar.json
- `fed-fomc-page`: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
- `fred-calendar-cpi`: https://fred.stlouisfed.org/releases/calendar?rid=10&vs=2026-10-08&ve=2026-12-07
- `bea-ics`: https://www.bea.gov/news/schedule/ics/online-calendar-subscription.ics
- `bea-ics-browser`: https://www.bea.gov/news/schedule/ics/online-calendar-subscription.ics
- `bls-ics`: https://www.bls.gov/schedule/news_release/bls.ics
- `bls-ics-browser`: https://www.bls.gov/schedule/news_release/bls.ics
- `llama-emissions-api`: https://api.llama.fi/emissions
- `llama-ds-list`: https://defillama-datasets.llama.fi/emissionsProtocolsList
- `llama-ds-protocol`: https://defillama-datasets.llama.fi/emissions/layerzero
- `llama-ds-index`: https://defillama-datasets.llama.fi/emissionsIndex
- `coingecko-markets`: https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids=layerzero,sui
- `farside-btc`: https://farside.co.uk/btc/
- `farside-btc-bot`: https://farside.co.uk/btc/
- `coinglass-api`: https://open-api-v4.coinglass.com/api/futures/supported-coins
- `coinglass-site`: https://www.coinglass.com/LiquidationData
- `ff-json`: https://nfs.faireconomy.media/ff_calendar_thisweek.json
- `ff-xml`: https://nfs.faireconomy.media/ff_calendar_thisweek.xml
- `ff-site`: https://www.forexfactory.com/calendar
- `okx-candles`: https://www.okx.com/api/v5/market/history-candles?instId=BTC-USDT&bar=1H&limit=2
- `fred-graph`: https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFF
