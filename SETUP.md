# راه‌اندازی رادار ۶.۱ — راهنمای گام‌به‌گام

هر گام یک بار انجام می‌شود مگر خلاف آن نوشته شده باشد.
ترتیب عمدی است: هر گام به گام قبلی وابسته است.

---

## مرحله ۰ — پیش‌نیازها (پنج دقیقه)

در پاورشل:

```powershell
python --version      # باید ۳.۱۰ یا بالاتر باشد
git --version
```

اگر پایتون نیست، از `python.org` نصب کن و گزینه «Add to PATH» را حتماً تیک بزن.

---

## مرحله ۱ — پاکسازی و به‌روزرسانی مخزن (ده دقیقه)

### ۱.۱ — گرفتن آخرین نسخه

```powershell
cd $HOME\Documents\radar
git pull
$env:PYTHONUTF8="1"
```

### ۱.۲ — حذف فایل‌های تکراری

این دو فایل کپی دقیق بایت‌به‌بایت هستند. تأیید شده با هش.

```powershell
git rm radar_fetch3-1.py radar_scan-1.py
git rm --cached -r __pycache__
Remove-Item -Recurse -Force __pycache__ -ErrorAction SilentlyContinue
Remove-Item out.txt -ErrorAction SilentlyContinue
```

### ۱.۳ — کپی فایل‌های جدید

از بسته `radar-6.0-repo.zip` این فایل‌ها را در ریشه مخزن بگذار:

| فایل | کار |
|---|---|
| `radar_size.py` | موتور اندازه مدرج |
| `radar_book.py` | بازبینی سبد و موتور خروج |
| `radar_optcost.py` | دفتر هزینه فرصت |
| `radar_watch.py` | پایشگر زنده سطوح |
| `radar_validate.py` | سنجش اعتبار موتور امتیازدهی |
| `.gitignore` | جلوگیری از کامیت فایل موقت |

و این دو در مسیر `.github/workflows/`:

```powershell
mkdir .github\workflows -Force
mkdir reports -Force
```

| فایل | زمان‌بندی |
|---|---|
| `radar-daily.yml` | هر روز ۰۶:۳۰ جهانی |
| `radar-weekly.yml` | یکشنبه ۰۷:۰۰ جهانی |

### ۱.۴ — نصب وابستگی‌ها

```powershell
pip install -r requirements.txt
pip install requests pandas numpy PyYAML
```

### ۱.۵ — کامیت

```powershell
git add .
git commit -m "رادار ۶.۱ — موتور مدرج، موتور خروج، پایشگر زنده، سنجش اعتبار"
git push
```

---

## مرحله ۲ — نصب اسکیل در کلاود (سه دقیقه)

| گام | کار |
|---|---|
| ۱ | فایل `radar-6.0-skill.zip` را دانلود کن |
| ۲ | در کلاود: تنظیمات ← Capabilities ← Skills |
| ۳ | اسکیل قدیمی `radar-5` را **حذف کن** — دو اسکیل هم‌زمان تداخل می‌سازند |
| ۴ | `radar-6.0-skill.zip` را بارگذاری کن |
| ۵ | آزمون: در گفتگوی تازه بنویس «رادار ۶ نصب شده؟ فهرست فایل‌های مرجعش را بگو» |

پاسخ درست باید ده فایل مرجع را نام ببرد، از جمله `risk-budget.md` و `exit-engine.md`.

---

## مرحله ۳ — اولین اجرا و مهم‌ترین عدد امروز (پانزده دقیقه)

### ۳.۱ — ساخت فایل سبد

```powershell
python radar_book.py --init
notepad holdings.json
```

برای هر پوزیشن پر کن:

```json
{
  "balance_total": 2500,
  "stable_usd": 0,
  "positions": [
    {"symbol":"SOL","size_usd":210,"invalidation":null,"side":"long","spot":true}
  ]
}
```

فعلاً `invalidation` را `null` بگذار. گام بعد پرش می‌کنیم.

### ۳.۲ — اجرای بازبینی سبد

```powershell
python radar_book.py --holdings holdings.json --regime -1.25
```

**این خروجی احتمالاً مهم‌ترین عدد امروز توست:** حرارت واقعی سبد.

در رادار ۵.۴ اسپات ریسک صفر داشت. در ۶.۰ پوزیشن اسپات بدون سطح ابطال، ریسکش ۱۰۰٪ همان پوزیشن شمرده می‌شود. عدد احتمالاً بزرگ خواهد بود.

### ۳.۳ — نوشتن سطح ابطال برای هر پوزیشن

برای هر پوزیشن، چارت روزانه را باز کن و یک سطح ساختاری پیدا کن: حداقل دو نقطه برخورد واقعی، فقط روزانه یا بالاتر.

سپس در `holdings.json` بگذار و دوباره اجرا کن. عدد حرارت واقعی‌تر می‌شود.

**قانون سخت:** پوزیشنی که نتوانی برایش سطح ابطال بنویسی، تز ندارد و باید بسته شود.

---

## مرحله ۴ — داده زنده و هشدار (بیست دقیقه)

این مرحله برای تو مهم‌ترین است، چون گفتی داده لحظه‌ای برایت حیاتی است.

### ۴.۱ — ساخت ربات تلگرام

| گام | کار |
|---|---|
| ۱ | در تلگرام به `@BotFather` پیام بده |
| ۲ | `/newbot` بزن، نام و شناسه بده |
| ۳ | توکن را کپی کن |
| ۴ | به ربات خودت یک پیام بفرست (هر چیزی) |
| ۵ | در مرورگر باز کن: `api.telegram.org/bot<TOKEN>/getUpdates` |
| ۶ | عدد `chat.id` را بردار |

### ۴.۲ — تنظیم در سیستم

```powershell
$env:TELEGRAM_BOT_TOKEN="توکن"
$env:TELEGRAM_CHAT_ID="شناسه"
```

برای ماندگاری پس از بستن پاورشل:

```powershell
[Environment]::SetEnvironmentVariable("TELEGRAM_BOT_TOKEN","توکن","User")
[Environment]::SetEnvironmentVariable("TELEGRAM_CHAT_ID","شناسه","User")
```

### ۴.۳ — ساخت فهرست پایش

```powershell
python radar_watch.py --init
notepad watch.json
```

سطوح واقعی خودت را بگذار: سطح ابطال، پله‌های نردبان ورود، اهداف، هشدارهای قیمتی.

### ۴.۴ — اجرا

```powershell
python radar_watch.py --loop 300
```

هر پنج دقیقه می‌سنجد. سه چیز را زنده پایش می‌کند:

| رویداد | مبنای سنجش |
|---|---|
| نقض ابطال ساختاری | **بسته کندل روزانه** — سایه شکست نیست |
| پرشدن پله نردبان ورود | قیمت لحظه‌ای |
| رسیدن به هدف | قیمت لحظه‌ای |

### ۴.۵ — تنظیم کلیدها در گیت‌هاب

`Settings ← Secrets and variables ← Actions ← New repository secret`

| نام | ضروری؟ |
|---|---|
| `TELEGRAM_BOT_TOKEN` | برای هشدار |
| `TELEGRAM_CHAT_ID` | برای هشدار |
| `COINGECKO_API_KEY` | اختیاری — سقف نرخ بالاتر |
| `COINGLASS_API_KEY` | اختیاری — داده لیکوئیدیشن |

### ۴.۶ — فعال‌سازی گردش‌کار خودکار

در گیت‌هاب: تب `Actions` ← گردش‌کار «رادار — اسکن روزانه» ← `Run workflow`

اگر سبز شد، از فردا خودکار اجرا می‌شود و گزارش را در `reports/` کامیت می‌کند.

---

## مرحله ۵ — سنجش اعتبار (نیم ساعت، فقط یک بار)

**این مهم‌ترین مرحله کل راهنماست.**

```powershell
python radar_validate.py --symbols BTC,ETH,SOL,LINK,AAVE,SUI,ONDO,TAO,XRP,BNB --horizon 30 --out reports\validate.md
notepad reports\validate.md
```

خروجی به یکی از سه حکم می‌رسد:

| حکم | معنی | اقدام |
|---|---|---|
| برتری معنادار | امتیاز بالا با بازده بهتر همراه بوده | به آستانه‌های رده کیفیت اعتماد کن |
| برتری ضعیف | جهت درست، فاصله کوچک | آستانه‌ها محافظه‌کارانه بمانند |
| بدون برتری | امتیاز پیش‌بینی نکرده | **موتور امتیازدهی باید بازنویسی شود** |

نتیجه را در گفتگو بچسبان و بگو «نتیجه سنجش اعتبار را تفسیر کن».

---

## مرحله ۶ — دریافت محتوای تحلیل‌گران (بیست دقیقه)

### واقعیتی که باید بدانی

یوتیوب نشانی سرورهای ابری را مسدود می‌کند. یعنی نه کولب، نه گردش‌کار گیت‌هاب، هیچ‌کدام نمی‌توانند رونوشت ویدیو بگیرند.

### ۶.۱ — منابع نوشتاری (از کامپیوتر یا کولب)

```powershell
python radar_intake.py --source joseph_wang --limit 3
python radar_intake.py --source kaiko --limit 3
python radar_digest.py --all-roles
notepad intake\DIGEST.md
```

### ۶.۲ — منابع یوتیوبی (فقط از کامپیوتر خودت)

```powershell
python radar_intake.py --source arshia_course --limit 5
python radar_intake.py --source tradecity_pro --limit 5
```

اگر مسدود شد، از افزونه کلاود در کروم استفاده کن: ویدیو را باز کن، بخش رونوشت (Transcript) را باز کن، و در گفتگو بگو «این رونوشت را با قواعد کتابخانه روش استخراج کن».

### ۶.۳ — قانون ورود روش تازه به رادار

روش جدید تنها با یک شرط وارد چارچوب می‌شود:

> نتیجه آزمون خارج از نمونه، پس از کسر کارمزد و نرخ تأمین مالی، روی حداقل سه دارایی.

بدون این، روش در `method-library.md` ثبت می‌شود ولی حق امتیازدهی ندارد.

---

## مرحله ۷ — کلاود کد (پانزده دقیقه)

کلاود کد برای نگهداری مخزن است، نه برای تحلیل بازار.

```powershell
cd $HOME\Documents\radar
claude
```

### دستورهای مفید — کپی کن و بچسبان

**بررسی سلامت:**

```
مخزن را بررسی کن: خطای نحوی، وابستگی گمشده، فایل تکراری،
و ناسازگاری میان جدول رژیم در radar_size.py و radar_book.py.
گزارش بده، تغییری نده.
```

**افزودن آزمون:**

```
برای radar_size.py آزمون واحد بنویس با pytest.
حداقل این موارد: مرزهای پنج رژیم، چهار وتو، سقف رده D،
و اینکه هیچ ترکیبی ریسک منفی یا بالای ۲ درصد تولید نکند.
فایل tests/test_size.py.
```

**هم‌راستاسازی:**

```
جدول رژیم در radar_size.py و radar_book.py و references/risk-budget.md
باید دقیقاً یکی باشند. اختلاف را پیدا کن و به یک منبع واحد ارجاع بده.
```

---

## مرحله ۸ — روتین‌های تکرارشونده

### روزانه — ده دقیقه

```powershell
cd $HOME\Documents\radar; git pull; $env:PYTHONUTF8="1"
python radar_book.py --holdings holdings.json --regime <امتیاز>
python radar_optcost.py session --action --kind "..."
```

اگر گردش‌کار روزانه فعال باشد، فقط در گفتگو بگو: «فایل `reports/LATEST.md` را بخوان».

### هفتگی — نیم ساعت

```powershell
python radar_rotate.py --venues okx,gate --deep 8 --out rotate.txt
python radar_book.py --holdings holdings.json --regime <امتیاز> --candidates <پنج نامزد برتر>
python radar_journal.py report
python radar_optcost.py followup
python radar_optcost.py report
git add . ; git commit -m "weekly" ; git push
```

### ماهانه — بازنگری چارچوب

```powershell
python radar_optcost.py report
python radar_validate.py --out reports\validate.md
```

سپس جدول بازنگری اجباری `calibration.md` بخش ۶ را اعمال کن.

---

## چک‌لیست نهایی

| # | کار | انجام شد؟ |
|---|---|---|
| ۱ | فایل‌های تکراری حذف شدند | ☐ |
| ۲ | پنج اسکریپت جدید کپی شدند | ☐ |
| ۳ | دو گردش‌کار در `.github/workflows/` | ☐ |
| ۴ | اسکیل ۵ حذف و ۶ نصب شد | ☐ |
| ۵ | `holdings.json` با موجودی واقعی پر شد | ☐ |
| ۶ | برای هر پوزیشن سطح ابطال نوشته شد | ☐ |
| ۷ | ربات تلگرام ساخته و کلیدها تنظیم شد | ☐ |
| ۸ | `watch.json` با سطوح واقعی پر شد | ☐ |
| ۹ | گردش‌کار روزانه یک بار دستی اجرا و سبز شد | ☐ |
| ۱۰ | **سنجش اعتبار اجرا و نتیجه‌اش خوانده شد** | ☐ |

گام ۱۰ تعیین می‌کند به بقیه چقدر می‌شود اعتماد کرد.
