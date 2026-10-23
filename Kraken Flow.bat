@echo off
rem Kraken Flow - public order-book viewer. Optional read-only position helper (needs Python).
set "D=%~dp0"
set "F=%D%KrakenFlow.html"
where python >nul 2>nul
if not errorlevel 1 if exist "%D%position_server.py" start "Kraken Flow position helper (read-only)" /min python "%D%position_server.py"
start "" msedge --app="file:///%F:\=/%" --window-size=3440,1400 --user-data-dir="%LOCALAPPDATA%\KrakenFlowProfile"
if errorlevel 1 start "" "%F%"
