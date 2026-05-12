#!/usr/bin/env python3
"""
Storj Discord Weekly Summary — Mondays 09:30
Reads webhook URL from STORJ_DISCORD_WEBHOOK env var or .env file.
"""

import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

PROM_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090/api/v1/query")


def load_env():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


load_env()
WEBHOOK_URL = os.environ.get("STORJ_DISCORD_WEBHOOK", "").strip()
if not WEBHOOK_URL:
    sys.stderr.write("ERROR: STORJ_DISCORD_WEBHOOK is not set.\n")
    sys.exit(2)


def q(promql):
    try:
        url = f"{PROM_URL}?query={urllib.parse.quote(promql)}"
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read().decode())
        return data.get("data", {}).get("result", [])
    except Exception as e:
        sys.stderr.write(f"Query failed [{promql}]: {e}\n")
        return []


def scalar(results, default=0.0):
    if not results:
        return default
    try:
        return float(results[0]["value"][1])
    except Exception:
        return default


def fmt_bytes(b):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(b) < 1024:
            return f"{b:.2f} {unit}"
        b /= 1024
    return f"{b:.2f} PB"


def main():
    nodes_total = scalar(q("count(storj_node_up)"))
    total_used = scalar(q("sum(storj_disk_used_bytes)"))
    total_used_week_ago = scalar(q("sum(storj_disk_used_bytes offset 7d)"))
    growth = total_used - total_used_week_ago

    avg_uptime_7d = scalar(q("avg(storj:uptime_7d_percent)"))
    total_earn = scalar(q("sum(storj_payout_current_month_usd)"))
    forecast_usd = scalar(q("storj:earnings_forecast_total_usd"))
    storj_usd = scalar(q("storj_token_price_usd"))
    storj_eur = scalar(q("storj_token_price_eur"))
    forecast_eur = forecast_usd * (storj_eur / storj_usd) if storj_usd else 0

    avg_egress_5m = scalar(q("avg_over_time(sum(storj:egress_rate_5m_bps)[7d:5m])"))
    avg_ingress_5m = scalar(q("avg_over_time(sum(storj:ingress_rate_5m_bps)[7d:5m])"))

    week_end = datetime.now()
    week_start = week_end - timedelta(days=7)

    fields = [
        {"name": "Zeitraum", "value": f"{week_start.strftime('%d.%m.')} – {week_end.strftime('%d.%m.%Y')}", "inline": False},
        {"name": "Avg Uptime", "value": f"{avg_uptime_7d:.2f}%", "inline": True},
        {"name": "Disk-Wachstum", "value": fmt_bytes(growth) if growth > 0 else f"-{fmt_bytes(abs(growth))}", "inline": True},
        {"name": "Ø Egress", "value": f"{fmt_bytes(avg_egress_5m)}/s", "inline": True},
        {"name": "Ø Ingress", "value": f"{fmt_bytes(avg_ingress_5m)}/s", "inline": True},
        {"name": "Einnahmen bisher", "value": f"${total_earn:.2f}", "inline": True},
        {"name": "Forecast Monatsende", "value": f"${forecast_usd:.2f}" + (f" (~€{forecast_eur:.2f})" if forecast_eur else ""), "inline": True},
        {"name": "STORJ-Preis", "value": f"${storj_usd:.4f} / €{storj_eur:.4f}", "inline": True},
        {"name": "Nodes", "value": f"{int(nodes_total)} aktiv", "inline": True},
    ]
    embed = {
        "title": f"📈 Storj Wochenreport — KW {week_end.isocalendar()[1]}",
        "color": 0x00d4aa,
        "fields": fields,
        "footer": {"text": "Storj Multi-Node Monitor"},
        "timestamp": datetime.now().astimezone().isoformat(),
    }
    body = json.dumps({"embeds": [embed]}).encode("utf-8")
    req = urllib.request.Request(WEBHOOK_URL, data=body, headers={"Content-Type": "application/json", "User-Agent": "storj-weekly/1.0"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        print(f"Posted: HTTP {resp.status}")


if __name__ == "__main__":
    main()
