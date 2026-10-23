@echo off
rem Kraken Flow - public order-book viewer. Optional read-only position helper (needs Python).
rem Hidden launcher: kills old helpers, starts one hidden helper, opens the app, stops the helper when the window closes.
set "D=%~dp0"
if exist "%D%launcher.vbs" (start "" wscript.exe "%D%launcher.vbs" & exit /b)
start "" msedge --app="file:///%D:\=/%KrakenFlow.html" --window-position=4385,0 --window-size=1615,1392 --user-data-dir="%LOCALAPPDATA%\KrakenFlowProfile"
