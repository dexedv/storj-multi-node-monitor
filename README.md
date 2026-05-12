# Storj Multi-Node Monitor

**🇩🇪 Deutsch** · [🇬🇧 English](README.en.md)

Komplettes Monitoring-Stack für mehrere Storj-Nodes auf einem Windows-Host. Liefert vier Grafana-Dashboards (Master, Per-Node Drilldown, Mobile, TV), Discord-Alerts, tägliche/wöchentliche Discord-Reports und Host-Metriken.

## Komponenten

```
Storj Nodes (14002, 14003, …)
        │
        ▼
storj-exporter  ──┐
storj-price-     ─┼─►  Prometheus  ──►  Alertmanager  ──► Discord
exporter          │   (Port 9090)     (Port 9093)
windows_exporter ─┘
                                    └─►  Grafana
                                         (Port 3000)
```

| Service           | Port  | Quelle                                          |
| ----------------- | ----- | ----------------------------------------------- |
| Storj Exporter    | 9651  | dieses Repo (`exporters/storj-exporter.py`)     |
| STORJ Price       | 9652  | dieses Repo (`exporters/storj-price-exporter.py`) |
| Windows Exporter  | 9182  | https://github.com/prometheus-community/windows_exporter |
| Prometheus        | 9090  | https://prometheus.io/download/                 |
| Alertmanager      | 9093  | https://prometheus.io/download/                 |
| Grafana           | 3000  | https://grafana.com/grafana/download            |

## Features

- 📊 **4 Grafana-Dashboards** — Master, Drilldown pro Node, Mobile, TV-Wand
- 🚨 **35 Alert/Recording-Regeln** — Disk-Forecast, Audit/Suspension Scores, STORJ-Preis-Bewegung, Host-Metriken
- 💬 **Discord-Integration** — Alerts in Echtzeit, täglicher + wöchentlicher Report + Identity-Backup-Reminder
- 💰 **Earnings-Forecast** in USD + EUR mit aktuellem STORJ-Token-Preis (CoinGecko)
- 🖥 **Host-Monitoring** — CPU/RAM/Disk via windows_exporter
- 🟢 **Status-Banner** — Fleet-Health auf einen Blick

---

## Installation (Windows)

### Voraussetzungen

- Windows 10/11
- Python 3.10+ (`py --version`)
- Mehrere Storj-Nodes auf demselben Host (Standard-Ports 14002, 14003, …)
- Admin-Rechte für Service-Installation

### 1. Repo klonen + .env vorbereiten

```powershell
git clone https://github.com/<USER>/<REPO>.git
cd <REPO>
copy .env.example .env
# .env mit Notepad öffnen, STORJ_DISCORD_WEBHOOK setzen
```

Discord-Webhook erstellen: Server-Einstellungen → Integrationen → Webhooks → Neuer Webhook → URL kopieren.

### 2. Storj-Ports anpassen

In `exporters/storj-exporter.py` Zeile `NODE_PORTS` an deine Nodes anpassen:

```python
NODE_PORTS = [14002, 14003, 14004, 14005]
```

### 3. Prometheus installieren

```powershell
# Download https://prometheus.io/download/ → Windows AMD64
# Entpacken nach C:\Tools\prometheus\
copy prometheus\prometheus.yml C:\Tools\prometheus\
copy prometheus\alert_rules.yml C:\Tools\prometheus\
copy prometheus\recording_rules.yml C:\Tools\prometheus\
```

### 4. Alertmanager installieren

```powershell
# Download von https://prometheus.io/download/
# Entpacken nach C:\Tools\alertmanager\
copy alertmanager\alertmanager.yml C:\Tools\alertmanager\
# alertmanager.yml öffnen → YOUR_DISCORD_WEBHOOK_URL durch echte URL ersetzen
```

### 5. Windows Exporter installieren

```powershell
# MSI von https://github.com/prometheus-community/windows_exporter/releases
# Installer ausführen (Admin nötig)
# Empfohlene Collectors:
msiexec /i windows_exporter-VERSION-amd64.msi /qn ^
  ENABLED_COLLECTORS=cpu,logical_disk,net,os,memory,system,tcp,physical_disk ^
  LISTEN_PORT=9182
```

Falls der Service nicht startet ("Unzulässige Funktion"): die `config.yaml` unter `C:\Program Files\windows_exporter\` darf nicht leer sein — eine Zeile reicht:
```yaml
collectors:
  enabled: cpu,logical_disk,net,os,memory,system,tcp,physical_disk
```

### 6. Grafana installieren

1. `.msi` von https://grafana.com/grafana/download?platform=windows herunterladen
2. Installieren (läuft danach als Windows-Service auf Port 3000)
3. `http://localhost:3000` → Login `admin/admin`, Passwort neu setzen
4. **Datasource** anlegen: ⚙ → Data Sources → Add → Prometheus → URL `http://localhost:9090` → Save & Test
5. **Dashboards importieren** (für alle 4 JSONs aus `grafana/`):
   - ➕ → Import → Upload JSON → Prometheus-Datasource wählen → Import

### 7. Services starten

```powershell
.\scripts\start-all.bat
```

Browser:
- Master: http://localhost:3000/d/storj-multi-node
- Drilldown: http://localhost:3000/d/storj-drilldown
- Mobile: http://localhost:3000/d/storj-mobile
- TV (kiosk): http://localhost:3000/d/storj-tv?kiosk

### 8. Scheduled Tasks (Discord-Reports)

```powershell
schtasks /Create /TN "Storj Daily Summary" /XML "scripts\scheduled-tasks\storj-daily-task.xml" /F
schtasks /Create /TN "Storj Weekly Summary" /XML "scripts\scheduled-tasks\storj-weekly-task.xml" /F
schtasks /Create /TN "Storj Identity Reminder" /XML "scripts\scheduled-tasks\storj-identity-task.xml" /F
```

Vor dem Import in den XML-Dateien den `<Arguments>`-Pfad anpassen, falls dein Repo woanders liegt.

### 9. Autostart bei Reboot (optional)

`Win+R` → `shell:startup` → Verknüpfung zu `scripts\autostart-silent.bat` reinziehen.

---

## Konfiguration

### Discord-Webhook

In `.env`:
```
STORJ_DISCORD_WEBHOOK=https://discord.com/api/webhooks/.../...
```
Die Python-Scripts laden das automatisch. Alertmanager braucht die URL zusätzlich in `alertmanager.yml`.

### Andere Node-Ports

Edit `exporters/storj-exporter.py` → `NODE_PORTS`.

### Alert-Schwellen

Edit `prometheus/alert_rules.yml`. Typische Anpassungen:
- `for: 5m` → wie lange muss der Zustand bestehen?
- `severity: warning/critical/info` → routing in alertmanager
- Schwellwerte in `expr:`

---

## Architektur-Details

### Metriken-Namespace

| Präfix | Quelle |
|---|---|
| `storj_node_*`, `storj_disk_*`, `storj_bandwidth_*` | Storj-Node API via `storj-exporter.py` |
| `storj_satellite_*` | Per-Satellit Audit/Suspension/Online Scores |
| `storj_payout_*` | Earnings & Held aus Storj-Node API |
| `storj_token_price_*` | CoinGecko via `storj-price-exporter.py` |
| `storj:*` | Recording-Rules (abgeleitete Werte) |
| `windows_*` | windows_exporter |

### Recording-Rules

Definiert in `prometheus/recording_rules.yml`. Wichtige:
- `storj:disk_used_percent` — Auslastung in %
- `storj:disk_full_in_days` — Forecast wann Disk voll
- `storj:uptime_24h_percent`, `storj:uptime_7d_percent`, `storj:uptime_30d_percent`
- `storj:earnings_forecast_month_usd` — Linear-Forecast Monatsende
- `storj:fleet_min_status` — 0=down, 1=warning, 2=ok (für Status-Banner)

### Dashboard-Variablen

- `$node` — Multi-Select Node-Filter (alle Dashboards außer TV)

---

## Bekannte Eigenheiten

- **windows_exporter Service startet nicht?** Standard-MSI fügt `--collectors.enabled` zum binPath hinzu mit veralteten Collector-Namen (z.B. `cs`, `thermalzone`). Setze den binPath manuell auf nur die exe + `--config.file` und stelle sicher dass `config.yaml` nicht leer ist.
- **Datasource UID** in den Dashboard-JSONs ist hardcoded auf den UID einer spezifischen Installation. Beim Grafana-Import sollte Grafana den UID-Mismatch erkennen und nach der Datasource fragen.
- **STORJ-Token-Preis** wird alle 5 Minuten von CoinGecko gecached, um Rate-Limits zu schonen.

---

## Lizenz

MIT — siehe `LICENSE`.

## Credits

- [Storj Labs](https://storj.io) — die Tech
- [Prometheus](https://prometheus.io), [Grafana](https://grafana.com), [Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/)
- [windows_exporter](https://github.com/prometheus-community/windows_exporter)
- [CoinGecko API](https://www.coingecko.com/api) — STORJ-Preis
