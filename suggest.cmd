@echo off
pushd "%~dp0"
python radar_video.py --suggest %*
set RC=%ERRORLEVEL%
popd
exit /b %RC%
