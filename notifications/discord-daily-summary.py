#!/usr/bin/env python3
"""
Storj Discord Daily Summary
============================
Sends a daily status summary to a Discord webhook.

Reads webhook URL from environment variable STORJ_DISCORD_WEBHOOK
(or from a .env file next to this script).

Schedule via Windows Task Scheduler, e.g. daily at 09:00:
    py discord-daily-summary.py
"""

import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime
from pathlib import Path

PROM_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090/api/v1/query")


def load_env():
    """Load KEY=VALUE pairs from .env file next to this script (simple loader)."""
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
    sys.stderr.write("ERROR: STORJ_DISCORD_WEBHOOK is not set. See .env.example.\n")
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


def per_node(results):
    out = {}
    for r in results:
        node = r["metric"].get("node", "?")
        try:
            out[node] = float(r["value"][1])
        except Exception:
            out[node] = 0
    return out


def fmt_bytes(b):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(b) < 1024:
            return f"{b:.2f} {unit}"
        b /= 1024
    return f"{b:.2f} PB"


def main():
    nodes_up = scalar(q("sum(storj_node_up)"))
    nodes_total = scalar(q("count(storj_node_up)"))
    total_used = scalar(q("sum(storj_disk_used_bytes)"))
    total_free = scalar(q("sum(storj_disk_available_bytes)"))
    total_bw = scalar(q("sum(storj_bandwidth_used_bytes)"))
    total_earn = scalar(q("sum(storj_payout_current_month_usd)"))
    total_held = scalar(q("sum(storj_payout_current_held_usd)"))
    storj_eur = scalar(q("storj_token_price_eur"))
    storj_usd = scalar(q("storj_token_price_usd"))

    uptime_24h = per_node(q("storj:uptime_24h_percent"))
    forecast_days = per_node(q("storj:disk_full_in_days"))
    min_audit = per_node(q("min by (node) (storj_satellite_audit_score)"))

    if nodes_up == nodes_total:
        status_icon, status_text, color = "🟢", "Alles laeuft", 0x00d4aa
    elif nodes_up >= nodes_total / 2:
        status_icon, status_text, color = "🟡", "Teilweise offline", 0xffb84d
    else:
        status_icon, status_text, color = "🔴", "PROBLEM", 0xff5577

    eur_value = total_earn * (storj_eur / storj_usd) if storj_usd else 0

    today = datetime.now().strftime("%d.%m.%Y")
    fields = [
        {"name": "Nodes", "value": f"{int(nodes_up)}/{int(nodes_total)} online", "inline": True},
        {"name": "Disk belegt", "value": fmt_bytes(total_used), "inline": True},
        {"name": "Frei", "value": fmt_bytes(total_free), "inline": True},
        {"name": "Bandbreite (Monat)", "value": fmt_bytes(total_bw), "inline": True},
        {"name": "Einnahmen (Monat)", "value": f"${total_earn:.2f}" + (f" (~€{eur_value:.2f})" if eur_value else ""), "inline": True},
        {"name": "Held", "value": f"${total_held:.2f}", "inline": True},
    ]
    if storj_usd:
        fields.append({"name": "STORJ-Preis", "value": f"${storj_usd:.4f} / €{storj_eur:.4f}", "inline": True})

    node_lines = []
    for node in sorted(set(list(uptime_24h.keys()) + list(forecast_days.keys()) + list(min_audit.keys()))):
        up_pct = uptime_24h.get(node, 0)
        fc = forecast_days.get(node, 0)
        au = min_audit.get(node, 1) * 100
        fc_text = f"voll in {fc:.0f}d" if 0 < fc < 365 else "OK"
        node_lines.append(f"`{node}`: Up24h {up_pct:.1f}% | Audit min {au:.2f}% | {fc_text}")
    if node_lines:
        fields.append({"name": "Pro Node", "value": "\n".join(node_lines), "inline": False})

    embed = {
        "title": f"{status_icon} Storj Tagesreport — {today}",
        "description": status_text,
        "color": color,
        "fields": fields,
        "footer": {"text": "Storj Multi-Node Monitor"},
        "timestamp": datetime.now().astimezone().isoformat(),
    }
    body = json.dumps({"embeds": [embed]}).encode("utf-8")
    req = urllib.request.Request(WEBHOOK_URL, data=body, headers={"Content-Type": "application/json", "User-Agent": "storj-daily-summary/1.0"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"Posted to Discord: HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        print(f"Discord error {e.code}: {e.read().decode()}")
        sys.exit(1)


if __name__ == "__main__":
    main()
