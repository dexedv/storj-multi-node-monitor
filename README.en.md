# Storj Multi-Node Monitor

[🇩🇪 Deutsch](README.md) · **🇬🇧 English**

Complete monitoring stack for multiple Storj nodes on a single Windows host. Ships four Grafana dashboards (master, per-node drilldown, mobile, TV), Discord alerts, daily/weekly Discord reports, and host-level metrics.

## Components

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

| Service           | Port  | Source                                          |
| ----------------- | ----- | ----------------------------------------------- |
| Storj Exporter    | 9651  | this repo (`exporters/storj-exporter.py`)       |
| STORJ Price       | 9652  | this repo (`exporters/storj-price-exporter.py`) |
| Windows Exporter  | 9182  | https://github.com/prometheus-community/windows_exporter |
| Prometheus        | 9090  | https://prometheus.io/download/                 |
| Alertmanager      | 9093  | https://prometheus.io/download/                 |
| Grafana           | 3000  | https://grafana.com/grafana/download            |

## Features

- 📊 **4 Grafana dashboards** — master, per-node drilldown, mobile, TV-wall
- 🚨 **35 alert/recording rules** — disk forecast, audit/suspension scores, STORJ price movement, host metrics
- 💬 **Discord integration** — real-time alerts, daily + weekly reports, monthly identity-backup reminder
- 💰 **Earnings forecast** in USD + EUR using live STORJ-token price (CoinGecko)
- 🖥 **Host monitoring** — CPU/RAM/disk via windows_exporter
- 🟢 **Status banner** — fleet health at a glance

---

## Installation (Windows)

### Prerequisites

- Windows 10/11
- Python 3.10+ (`py --version`)
- Multiple Storj nodes on the same host (default ports 14002, 14003, …)
- Admin rights for service installation

### 1. Clone repo + prepare .env

```powershell
git clone https://github.com/<USER>/<REPO>.git
cd <REPO>
copy .env.example .env
# Open .env in Notepad and set STORJ_DISCORD_WEBHOOK
```

Create a Discord webhook: Server settings → Integrations → Webhooks → New webhook → copy URL.

### 2. Adjust Storj ports

In `exporters/storj-exporter.py`, edit the `NODE_PORTS` line to match your nodes:

```python
NODE_PORTS = [14002, 14003, 14004, 14005]
```

### 3. Install Prometheus

```powershell
# Download https://prometheus.io/download/ → Windows AMD64
# Extract to C:\Tools\prometheus\
copy prometheus\prometheus.yml C:\Tools\prometheus\
copy prometheus\alert_rules.yml C:\Tools\prometheus\
copy prometheus\recording_rules.yml C:\Tools\prometheus\
```

### 4. Install Alertmanager

```powershell
# Download from https://prometheus.io/download/
# Extract to C:\Tools\alertmanager\
copy alertmanager\alertmanager.yml C:\Tools\alertmanager\
# Open alertmanager.yml → replace YOUR_DISCORD_WEBHOOK_URL with your real webhook
```

### 5. Install Windows Exporter

```powershell
# MSI from https://github.com/prometheus-community/windows_exporter/releases
# Run installer (admin required)
# Recommended collectors:
msiexec /i windows_exporter-VERSION-amd64.msi /qn ^
  ENABLED_COLLECTORS=cpu,logical_disk,net,os,memory,system,tcp,physical_disk ^
  LISTEN_PORT=9182
```

If the service fails to start ("Incorrect function"): the `config.yaml` under `C:\Program Files\windows_exporter\` must not be empty — one line is enough:
```yaml
collectors:
  enabled: cpu,logical_disk,net,os,memory,system,tcp,physical_disk
```

### 6. Install Grafana

1. Download the `.msi` from https://grafana.com/grafana/download?platform=windows
2. Install (runs as Windows service on port 3000 afterwards)
3. `http://localhost:3000` → login `admin/admin`, set a new password
4. **Add datasource**: ⚙ → Data Sources → Add → Prometheus → URL `http://localhost:9090` → Save & Test
5. **Import dashboards** (all 4 JSONs from `grafana/`):
   - ➕ → Import → Upload JSON → pick the Prometheus datasource → Import

### 7. Start services

```powershell
.\scripts\start-all.bat
```

Browser:
- Master: http://localhost:3000/d/storj-multi-node
- Drilldown: http://localhost:3000/d/storj-drilldown
- Mobile: http://localhost:3000/d/storj-mobile
- TV (kiosk): http://localhost:3000/d/storj-tv?kiosk

### 8. Scheduled tasks (Discord reports)

```powershell
schtasks /Create /TN "Storj Daily Summary" /XML "scripts\scheduled-tasks\storj-daily-task.xml" /F
schtasks /Create /TN "Storj Weekly Summary" /XML "scripts\scheduled-tasks\storj-weekly-task.xml" /F
schtasks /Create /TN "Storj Identity Reminder" /XML "scripts\scheduled-tasks\storj-identity-task.xml" /F
```

Before importing, adjust the `<Arguments>` path inside the XML files if your repo lives elsewhere.

### 9. Auto-start on reboot (optional)

`Win+R` → `shell:startup` → drop a shortcut to `scripts\autostart-silent.bat` into that folder.

---

## Configuration

### Discord webhook

In `.env`:
```
STORJ_DISCORD_WEBHOOK=https://discord.com/api/webhooks/.../...
```
The Python scripts load this automatically. Alertmanager additionally needs the URL set in `alertmanager.yml`.

### Different node ports

Edit `exporters/storj-exporter.py` → `NODE_PORTS`.

### Alert thresholds

Edit `prometheus/alert_rules.yml`. Common tweaks:
- `for: 5m` → how long must the condition hold before firing?
- `severity: warning/critical/info` → routing in alertmanager
- threshold values in `expr:`

---

## Architecture

### Metric namespaces

| Prefix | Source |
|---|---|
| `storj_node_*`, `storj_disk_*`, `storj_bandwidth_*` | Storj node API via `storj-exporter.py` |
| `storj_satellite_*` | per-satellite audit/suspension/online scores |
| `storj_payout_*` | earnings & held from Storj node API |
| `storj_token_price_*` | CoinGecko via `storj-price-exporter.py` |
| `storj:*` | recording rules (derived values) |
| `windows_*` | windows_exporter |

### Recording rules

Defined in `prometheus/recording_rules.yml`. Notable ones:
- `storj:disk_used_percent` — usage in %
- `storj:disk_full_in_days` — forecast when disk runs full
- `storj:uptime_24h_percent`, `storj:uptime_7d_percent`, `storj:uptime_30d_percent`
- `storj:earnings_forecast_month_usd` — linear forecast for end of month
- `storj:fleet_min_status` — 0=down, 1=warning, 2=ok (used by the status banner)

### Dashboard variables

- `$node` — multi-select node filter (all dashboards except TV)

---

## Known quirks

- **windows_exporter service won't start?** The default MSI appends `--collectors.enabled` to the binPath with collector names that may no longer exist in the installed version (e.g. `cs`, `thermalzone`). Set the binPath manually to just the exe + `--config.file`, and make sure `config.yaml` is not empty.
- **Datasource UID** in the dashboard JSONs is hardcoded to one specific installation. On Grafana import, Grafana should detect the UID mismatch and ask you to pick the datasource.
- **STORJ token price** is cached for 5 minutes per CoinGecko fetch to respect free-tier rate limits.

---

## License

MIT — see `LICENSE`.

## Credits

- [Storj Labs](https://storj.io) — the tech
- [Prometheus](https://prometheus.io), [Grafana](https://grafana.com), [Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/)
- [windows_exporter](https://github.com/prometheus-community/windows_exporter)
- [CoinGecko API](https://www.coingecko.com/api) — STORJ price feed
