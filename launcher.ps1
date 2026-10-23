# Kraken Flow launcher (runs hidden). One helper per session; helper stops when the app window closes.
$ErrorActionPreference = 'SilentlyContinue'
$D = $PSScriptRoot
$F = Join-Path $D 'KrakenFlow.html'
$Prof = Join-Path $env:LOCALAPPDATA 'KrakenFlowProfile'
# 1) clean up old helpers + old watchers (matched by command line only)
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'KrakenFlow\\launcher\.ps1' -and $_.ProcessId -ne $PID } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -match 'position_server\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
# 2) start exactly one hidden helper (pythonw = no console)
$helper = $null
$pyw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
if ($pyw -and (Test-Path (Join-Path $D 'position_server.py'))) {
  $helper = Start-Process -FilePath $pyw -ArgumentList ('"' + (Join-Path $D 'position_server.py') + '"') -WorkingDirectory $D -WindowStyle Hidden -PassThru
}
# 3) open the app window
$url = 'file:///' + ($F -replace '\\','/')
Start-Process msedge -ArgumentList "--app=`"$url`"","--window-position=4385,0","--window-size=1615,1392","--user-data-dir=`"$Prof`""
if (-not $helper) { exit }
# 4) wait until every Edge process using the Kraken Flow profile is gone, then stop the helper
$pat = [regex]::Escape($Prof)
Start-Sleep -Seconds 8
while ($true) {
  if ($helper.HasExited) { exit }
  $alive = Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" | Where-Object { $_.CommandLine -match $pat }
  if (-not $alive) { break }
  Start-Sleep -Seconds 3
}
Stop-Process -Id $helper.Id -Force
