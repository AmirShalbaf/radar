@echo off
pushd "%~dp0"
set PYTHONUTF8=1
if not exist "intake\_local\_pending" mkdir "intake\_local\_pending"
echo ===== %DATE% %TIME% >> "intake\_local\_pending\nightly.log"
python radar_intake.py --pending >> "intake\_local\_pending\nightly.log" 2>&1
set RC=%ERRORLEVEL%
echo ===== exit %RC% >> "intake\_local\_pending\nightly.log"
popd
exit /b %RC%
