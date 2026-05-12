@echo off
REM Silent autostart variant for Windows shell:startup
set EXPORTERS_DIR=%~dp0..\exporters
set PROM_DIR=C:\Tools\prometheus
set AM_DIR=C:\Tools\alertmanager

cd /d "%EXPORTERS_DIR%"
start "" /B py storj-exporter.py
start "" /B py storj-price-exporter.py
timeout /t 3 /nobreak >nul
cd /d "%PROM_DIR%"
start "" /B prometheus.exe --config.file=prometheus.yml --storage.tsdb.path=data --web.enable-lifecycle
timeout /t 3 /nobreak >nul
cd /d "%AM_DIR%"
start "" /B alertmanager.exe --config.file=alertmanager.yml
exit
