@echo off
rem Kraken Flow - public order-book viewer (read-only, no keys)
set "F=%~dp0KrakenFlow.html"
start "" msedge --app="file:///%F:\=/%" --window-size=3440,1400 --user-data-dir="%LOCALAPPDATA%\KrakenFlowProfile"
if errorlevel 1 start "" "%F%"
