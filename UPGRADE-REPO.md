# ارتقای مخزن `AmirShalbaf/radar` به رادار ۶.۰

راهنمای دقیق: چه فایلی اضافه شود، چه فایلی عوض شود، چه فایلی دست‌نخورده بماند.

---

## ۱. وضعیت فعلی مخزن — ممیزی

| فایل | وضعیت | اقدام |
|---|---|---|
| `radar_fetch3.py` (۹۷ کیلوبایت، نسخه ۳.۶) | سالم و کامل | **دست‌نخورده** |
| `radar_scan.py` | سالم | **دست‌نخورده** |
| `radar_rotate.py` | سالم | **دست‌نخورده** |
| `radar_levels.py` (نسخه ۱.۱) | ✅ چهار افزوده ۵.۴ را **دارد** | **دست‌نخورده** |
| `radar_journal.py` | سالم | **دست‌نخورده** |
| `radar_intake.py` (نسخه ۱.۴) | سالم | **دست‌نخورده** |
| `radar_digest.py` (نسخه ۱.۱) | سالم | **دست‌نخورده** |
| `radar_fetch3-1.py` | **کپی تکراری بایت‌به‌بایت** `radar_fetch3.py` | **حذف** |
| `radar_scan-1.py` | **کپی تکراری بایت‌به‌بایت** `radar_scan.py` | **حذف** |
| `out.txt`، `zec.txt/` | فایل موقت | **حذف یا انتقال به `reports/`** |
| `__pycache__/` | باید در `.gitignore` باشد | **حذف + gitignore** |
| `.github/workflows/` | **وجود ندارد** — علت خطای ۴۰۴ | **افزودن** |

**تصحیح یک برداشت قبلی:** `radar_levels.py` نسخه ۱.۱ در واقع **هر چهار افزوده ۵.۴** را پیاده کرده — پرسش دروازه‌ای، حالت بی‌ساختار، تفکیک سطح ساختاری، و اصل فاصله ورود تا ابطال. شکاف کد و مشخصات که قبلاً ثبت شده بود، دیگر وجود ندارد.

---

## ۲. فایل‌های جدید — اضافه شوند

```
radar/
├── radar_size.py                      ← جدید، موتور اندازه مدرج
├── radar_book.py                      ← جدید، بازبینی سبد و موتور خروج
├── radar_optcost.py                   ← جدید، دفتر هزینه فرصت
├── holdings.json                      ← جدید، ساخته می‌شود با: python radar_book.py --init
├── .gitignore                         ← جدید
├── reports/                           ← جدید، خروجی خودکار
└── .github/
    └── workflows/
        ├── radar-daily.yml            ← جدید، رفع خطای ۴۰۴
        └── radar-weekly.yml           ← جدید، رفع خطای ۴۰۴
```

---

## ۳. دستورهای اجرا

```bash
cd $HOME/Documents/radar
git pull

# پاکسازی
git rm --cached -r __pycache__ 2>/dev/null
rm -rf __pycache__ out.txt
git rm radar_fetch3-1.py radar_scan-1.py

# فایل‌های جدید را از بسته رادار ۶.۰ اینجا کپی کن
mkdir -p .github/workflows reports

# ساخت فایل سبد
python radar_book.py --init
# سپس holdings.json را با موجودی واقعی پر کن

git add .
git commit -m "رادار ۶.۰ — موتور تصمیم مدرج، موتور خروج، دفتر هزینه فرصت، خودکارسازی"
git push
```

---

## ۴. محتوای `.gitignore`

```
__pycache__/
*.pyc
.env
*.tmp
out.txt
scan.txt
rotate.txt
btc.txt
```

**نگهداری عمدی در مخزن:** `radar_journal.json`، `radar_optcost.json` و `book_state.json` باید **کامیت شوند**. این‌ها داده کالیبراسیون‌اند، نه فایل موقت. بدون تاریخچه‌شان، نرخ اقدام و هزینه فرصت قابل محاسبه نیست.

---

## ۵. به‌روزرسانی `requirements.txt`

```
requests
pandas
numpy
PyYAML
```

`radar_size.py` هیچ وابستگی بیرونی ندارد — فقط کتابخانه استاندارد. عمدی است تا از هر جایی قابل اجرا باشد.

---

## ۶. کلیدهای مخزن

`Settings > Secrets and variables > Actions > New repository secret`

| نام | ضروری؟ | کار |
|---|---|---|
| `COINGECKO_API_KEY` | خیر | سقف نرخ ۱۵ ← ۳۰ در دقیقه |
| `COINGLASS_API_KEY` | خیر | داده لیکوئیدیشن |
| `TELEGRAM_BOT_TOKEN` | خیر | اعلان |
| `TELEGRAM_CHAT_ID` | خیر | مقصد اعلان |

**هرگز کلید را داخل کد ننویس. مخزن عمومی است.**

---

## ۷. آزمون پس از ارتقا

```bash
# ۱ — موتور اندازه، بدون شبکه کار می‌کند
python radar_size.py --balance 2500 --regime -1.25 --score 1.25 \
  --entry 515.79 --stop 478 --target 575 --invalidation 480.43 \
  --win-prob 0.45 --coverage 78 --flow 3 --structural \
  --ladder-near 515 --ladder-poc 500 --ladder-far 487

# انتظار: رده A، ریسک ۰.۶۸٪، ورود مؤثر ۴۹۳.۷، نسبت ۵.۱۸

# ۲ — بازبینی سبد
python radar_book.py --holdings holdings.json --regime -1.25

# ۳ — دفتر هزینه فرصت
python radar_optcost.py session --no-action
python radar_optcost.py report

# ۴ — گردش‌کار
# در گیت‌هاب: تب Actions > رادار — اسکن روزانه > Run workflow
```

---

## ۸. ترتیب پیشنهادی اجرا

| اولویت | کار | چرا اول |
|---|---|---|
| ۱ | `holdings.json` را با موجودی واقعی پر کن و `radar_book.py` را اجرا کن | حرارت واقعی سبد را نشان می‌دهد. احتمالاً بزرگ‌ترین یافته امروز همین است |
| ۲ | برای هر پوزیشن اسپات یک سطح ابطال ساختاری بنویس | پوزیشن بدون ابطال با ریسک ۱۰۰٪ شمرده می‌شود |
| ۳ | گردش‌کار روزانه را فعال کن | بدون جلسات منظم، نرخ اقدام قابل محاسبه نیست |
| ۴ | ثبت در دفتر هزینه فرصت را شروع کن | تنها راه فهمیدن اینکه چارچوب سخت‌گیر است یا شل |
| ۵ | ربات تلگرام | راحتی، نه ضرورت |
