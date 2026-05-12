@echo off
REM Storj Monitoring Stack - Start All Services
REM Adjust the paths below to match your installation.

set EXPORTERS_DIR=%~dp0..\exporters
set PROM_DIR=C:\Tools\prometheus
set AM_DIR=C:\Tools\alertmanager

echo Starting Storj Exporter...
cd /d "%EXPORTERS_DIR%"
start "" /B py storj-exporter.py

echo Starting STORJ Price Exporter...
start "" /B py storj-price-exporter.py

timeout /t 3 /nobreak >nul

echo Starting Prometheus...
cd /d "%PROM_DIR%"
start "" /B prometheus.exe --config.file=prometheus.yml --storage.tsdb.path=data --web.enable-lifecycle

timeout /t 3 /nobreak >nul

echo Starting Alertmanager...
cd /d "%AM_DIR%"
start "" /B alertmanager.exe --config.file=alertmanager.yml

echo.
echo ====================================
echo All services started!
echo ====================================
echo  Grafana Dashboard: http://localhost:3000/d/storj-multi-node
echo  Prometheus:        http://localhost:9090
echo  Alertmanager:      http://localhost:9093
echo  Storj Exporter:    http://localhost:9651/metrics
echo  STORJ Price:       http://localhost:9652/metrics
echo  Windows Exporter:  http://localhost:9182/metrics (service)
echo ====================================
echo.
pause
