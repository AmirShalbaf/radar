#!/bin/bash
# راه‌اندازی مخزن — یک بار اجرا شود
set -e
git init
git add radar_fetch3.py requirements.txt README.md .gitignore radar_colab.ipynb
git commit -m "رادار ۵.۲ — واکشی چند-صرافی + ماکرو رسمی"
git branch -M main
echo ""
echo "حالا در github.com یک مخزن خصوصی به نام radar بساز، بعد:"
echo "  git remote add origin https://github.com/USERNAME/radar.git"
echo "  git push -u origin main"
echo ""
echo "از هر دستگاه دیگری:  git clone https://github.com/USERNAME/radar.git"
