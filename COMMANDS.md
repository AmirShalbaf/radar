# برگه دستورهای رادار — مرجع سریع

> این فایل را باز نگه دار. همه دستورها اینجاست.

---

## ۰ — همیشه اول (هر بار پاورشل تازه)

```
cd $HOME\Documents\radar; git pull; $env:PYTHONUTF8="1"
```

---

## ۱ — تحلیل عمیق یک کوین

```
python radar_fetch3.py ZEC --balance 800 --profile position --venues okx,gate --deep --out zec.txt
```

```
python radar_fetch3.py BTC --balance 800 --profile trade --venues okx,gate --deep --out btc.txt
```

| کلید | مقدارها |
|---|---|
| `--profile` | `position` برای اسپات و نگهداری، `trade` برای معامله کوتاه |
| `--balance` | موجودی حساب به دلار |
| `--venues` | `okx,gate` — بایننس و بای‌بیت مسدودند |
| `--deep` | تحلیل کامل‌تر |

بعد: `notepad zec.txt` و کپی در گفتگو.

---

## ۲ — اسکن واچ‌لیست

```
python radar_scan.py --preset all --venues okx,gate --top 5 --out scan.txt
```

```
python radar_scan.py --watchlist BTC,ETH,ZEC,HYPE --venues okx,gate --out scan.txt
```

| پریست | کوین‌ها |
|---|---|
| `main` | BTC، ETH، SOL |
| `watch` | BTC، ETH، SOL، TAO، HYPE، ONDO، LINK، AAVE، SUI |
| `all` | هر ۱۳ کوین |

---

## ۳ — چرخش و کوین پامپی

```
python radar_rotate.py --venues okx,gate --min-vol 5000000 --top 40 --deep 8 --out rotate.txt
```

| کلید | معنی |
|---|---|
| `--min-vol` | حداقل حجم روزانه دلاری |
| `--top` | چند نماد وارد بررسی کندل شود |
| `--deep` | برای چند نامزد، **آزمون پامپ کاذب** اجرا شود |
| `--exclude` | نمادهای حذفی، جدا با کاما |

---

## ۴ — نظر تحلیل‌گران

```
python radar_intake.py --limit 5 --since 2026-08-01
python radar_digest.py --all-roles
notepad intake\DIGEST.md
```

فقط یک منبع:

```
python radar_intake.py --source joseph_wang --limit 3
python radar_intake.py --source arshia_course --limit 15
```

نام منابع: `joseph_wang` `kaiko` `ray_dalio` `tradecity_pro` `no_bs_crypto` `cryptocity_pro` `tekrargar` `benjamin_cowen` `gareth_soloway` `raoul_pal` `virtualbacon` `arshia_course`

فقط یک گزارش:

```
python radar_digest.py --report watchlist
python radar_digest.py --report rules --all-roles
python radar_digest.py --report overlap
```

> منابع یوتیوبی فقط از کامپیوتر خانگی کار می‌کنند. از کولب مسدودند.

---

## ۵ — ژورنال

**ثبت معامله:**

```
python radar_journal.py add --symbol ZEC --side long --entry 515.79 --stop 480 --target 575 --invalidation 480.43 --size 200 --verdict "بدون ورود" --decision "ورود" --rr 1.7 --regime -1.25 --note "..."
```

**بقیه:**

```
python radar_journal.py list
python radar_journal.py check
python radar_journal.py update --id 1 --stop 500
python radar_journal.py close --id 1 --exit 560 --reason "..." --lesson "..."
python radar_journal.py report
```

---

## ۶ — ذخیره در گیت‌هاب

```
git add . ; git commit -m "update" ; git push
```

بررسی وضعیت:

```
git status
```

---

## روتین روزانه — ده دقیقه

```
cd $HOME\Documents\radar; git pull; $env:PYTHONUTF8="1"
python radar_journal.py check
python radar_scan.py --preset watch --venues okx,gate --out scan.txt
notepad scan.txt
```

**سؤال پیش از هر تصمیم:** آیا امروز اصلاً نیاز به ورود هست؟ اگر نه، ببند و برو.

---

## روتین هفتگی — نیم ساعت

```
python radar_rotate.py --venues okx,gate --deep 8 --out rotate.txt
python radar_intake.py --limit 5 --since 2026-08-01
python radar_digest.py --all-roles
python radar_journal.py report
git add . ; git commit -m "weekly" ; git push
```

---

## جمله‌هایی که در گفتگو می‌گویی

| موقعیت | جمله |
|---|---|
| بعد از تحلیل کوین | «با رادار ۵.۳ تحلیل کن. پروفایل موقعیت.» |
| بعد از اسکن | «اسکن امروز را بررسی کن.» |
| بعد از چرخش | «چرخش هفته را بررسی کن. کدام نامزد واقعی است؟» |
| بعد از چکیده | «گزارش تحلیل‌گران را بخوان.» |
| اگر push کرده‌ای | «فایل `intake/DIGEST.md` را از گیت‌هاب بخوان.» |

---

## پنج خطای رایج

| نشانه | راه‌حل |
|---|---|
| خطای `cp1256` یا `UnicodeEncodeError` | `$env:PYTHONUTF8="1"` را فراموش کرده‌ای |
| کد قدیمی اجرا می‌شود | `git pull` نکرده‌ای |
| سیستم دیگر قدیمی است | `git push` نکرده‌ای |
| `0 مورد ساخته می‌شد` | قبلاً گرفته شده. `--force` اضافه کن |
| یوتیوب مسدود | روی کولب اجرا کرده‌ای. فقط کامپیوتر خانگی |

---

## قانون داده-اول

هیچ تحلیلی بدون داده شروع نمی‌شود. اگر بدون خروجی اسکریپت بپرسی، اول فهرست داده لازم خواسته می‌شود.

استثنا: «با داده موجود ادامه بده» یا درخواست تحلیل ماکرو.

---

*آخرین به‌روزرسانی: ۹ اوت ۲۰۲۶*
