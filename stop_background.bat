@echo off
REM stop_background.bat - Stops the SpectrumBot background process on Windows
echo Stopping SpectrumBot background monitor...

powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*main.py*--watch*' } | ForEach-Object { Write-Host 'Stopping PID:' $_.ProcessId; Stop-Process -Id $_.ProcessId -Force }"

echo ==========================================================
echo  SpectrumBot background service stopped!
echo ==========================================================
timeout /t 3 >nul
