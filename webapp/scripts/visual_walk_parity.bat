@echo off
cd /d "%~dp0\.."
node scripts\visual_walk_parity.mjs %*
echo.
echo Open latest compare.html in webapp\parity_out\
pause
