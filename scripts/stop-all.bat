@echo off
echo Stopping Storj monitoring stack...
taskkill /F /IM prometheus.exe 2>nul
taskkill /F /IM alertmanager.exe 2>nul
powershell -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='py.exe'\" | Where-Object { $_.CommandLine -like '*storj-exporter*' -or $_.CommandLine -like '*storj-price-exporter*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Done. (Grafana service still running — stop with: Stop-Service Grafana)
pause
