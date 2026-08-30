# خطای اسکن — 2026-08-30

اسکن با خطا افتاد. ته گزارش خطا:

```
  File "/home/runner/work/radar/radar/radar_scan.py", line 476
    f"| {f"{r['vs_poc']:+.1f}%" if r.get('vs_poc') is not None else '—'} |")
                          ^
SyntaxError: invalid decimal literal
```
