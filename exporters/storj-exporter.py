#!/usr/bin/env python3
"""
Storj Multi-Node Prometheus Exporter
=====================================
Exposes Storj node metrics in Prometheus format.

Start:  py storj-exporter.py
Metrics: http://localhost:9651/metrics

Add to your Prometheus scrape config (prometheus.yml):
  - job_name: 'storj'
    scrape_interval: 60s
    static_configs:
      - targets: ['localhost:9651']
"""

import http.server
import socketserver
import urllib.request
import json
import sys
import time
from urllib.parse import urlparse
from datetime import datetime, timezone

# --- Configuration ---
LISTEN_PORT = 9651       # Port for Prometheus to scrape
LISTEN_HOST = "0.0.0.0"  # Listen on all interfaces
NODE_HOST = "127.0.0.1"
NODE_PORTS = [14002]  # Single consolidated Storj node (was 4, /24 limit makes more useless)
REQUEST_TIMEOUT = 5

# --- Helpers ---
def http_get_json(url, timeout=REQUEST_TIMEOUT):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def iso_to_epoch(iso_str):
    if not iso_str:
        return 0
    try:
        # Handle Z suffix and timezone-aware ISO strings
        s = iso_str.replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return 0


def fetch_node_metrics(port):
    """Fetch all metrics for a single node and return them as a dict."""
    base = f"http://{NODE_HOST}:{port}"
    metrics = {"port": port, "up": 0}

    try:
        dash = http_get_json(f"{base}/api/sno")
        metrics["up"] = 1
        metrics["node_id"] = dash.get("nodeID", "")
        metrics["wallet"] = dash.get("wallet", "")
        metrics["version"] = dash.get("version", "")
        metrics["up_to_date"] = 1 if dash.get("upToDate") else 0
        metrics["quic_ok"] = 1 if dash.get("quicStatus") == "OK" else 0
        metrics["started_at"] = iso_to_epoch(dash.get("startedAt", ""))
        metrics["last_pinged"] = iso_to_epoch(dash.get("lastPinged", ""))

        disk = dash.get("diskSpace", {}) or {}
        metrics["disk_used"] = disk.get("used", 0)
        metrics["disk_available"] = disk.get("available", 0)
        metrics["disk_trash"] = disk.get("trash", 0)
        metrics["disk_overused"] = disk.get("overused", 0)

        bw = dash.get("bandwidth", {}) or {}
        metrics["bw_used"] = bw.get("used", 0)
        metrics["bw_available"] = bw.get("available", 0)
    except Exception as e:
        metrics["error"] = str(e)
        return metrics

    # Satellites
    metrics["satellites"] = []
    try:
        sats_data = http_get_json(f"{base}/api/sno/satellites")
        for sat in (sats_data.get("audits") or []):
            metrics["satellites"].append({
                "id": sat.get("satelliteId", "unknown"),
                "url": sat.get("satelliteName", ""),
                "audit_score": sat.get("auditScore", 0) or 0,
                "suspension_score": sat.get("suspensionScore", 0) or 0,
                "online_score": sat.get("onlineScore", 0) or 0,
                "disqualified": 1 if sat.get("disqualified") else 0,
                "suspended": 1 if sat.get("suspended") else 0,
                "joined_at": iso_to_epoch(sat.get("joinedAt", "")),
                "ingress": sat.get("ingressSummary", 0) or 0,
                "egress": sat.get("egressSummary", 0) or 0,
            })
    except Exception:
        pass

    # Payout / earnings
    try:
        payout = http_get_json(f"{base}/api/sno/estimated-payout")
        cm = payout.get("currentMonth", {}) or {}
        pm = payout.get("previousMonth", {}) or {}
        metrics["payout_current_month"] = (cm.get("payout", 0) or 0) / 10000.0
        metrics["payout_current_held"] = (cm.get("held", 0) or 0) / 10000.0
        metrics["payout_previous_month"] = (pm.get("payout", 0) or 0) / 10000.0
        metrics["payout_previous_held"] = (pm.get("held", 0) or 0) / 10000.0
    except Exception:
        metrics["payout_current_month"] = 0
        metrics["payout_current_held"] = 0
        metrics["payout_previous_month"] = 0
        metrics["payout_previous_held"] = 0

    return metrics


def well_known_sat_name(sat_id):
    """Map satellite IDs to friendly names."""
    known = {
        "12EayRS2V1kEsWESU9QMRseFhdxYxKicsiFmxrsLZHeLUtdps3S": "US1",
        "12L9nCYHy3iE3pj66YHcL8gkBhrybQYAEFC9SCMfXctzKKnvkjW": "EU1",
        "121RTSDpyNZVcEU84Ticf2L1ntiuUimbWgfATz21tuvgk3vzoA6": "AP1",
        "1wFTAgs9DP5RSnCqKV1eLf6N9wtk4EAtmN5DpSxcs8EjT69tGE": "SaltLake",
    }
    return known.get(sat_id, sat_id[:10] if sat_id else "unknown")


def render_prometheus(all_metrics):
    """Render metrics in Prometheus exposition format."""
    lines = []

    # HELP and TYPE blocks
    metric_defs = [
        ("storj_node_up", "gauge", "Whether the node API is reachable (1=up, 0=down)"),
        ("storj_node_info", "gauge", "Node info as labels (always 1)"),
        ("storj_node_up_to_date", "gauge", "Whether the node software is up to date"),
        ("storj_node_quic_ok", "gauge", "Whether QUIC is working (1=OK, 0=NOT OK)"),
        ("storj_node_started_timestamp", "gauge", "Unix timestamp when the node was started"),
        ("storj_node_last_pinged_timestamp", "gauge", "Unix timestamp when the node was last pinged"),
        ("storj_node_uptime_seconds", "gauge", "Seconds since the node was started"),

        ("storj_disk_used_bytes", "gauge", "Disk space used by the node"),
        ("storj_disk_available_bytes", "gauge", "Disk space still available"),
        ("storj_disk_trash_bytes", "gauge", "Disk space in trash"),
        ("storj_disk_overused_bytes", "gauge", "Disk space overused"),
        ("storj_disk_total_bytes", "gauge", "Total disk space allocated"),

        ("storj_bandwidth_used_bytes", "gauge", "Bandwidth used this month"),
        ("storj_bandwidth_available_bytes", "gauge", "Bandwidth still available this month"),

        ("storj_satellite_audit_score", "gauge", "Audit score for a satellite (0-1)"),
        ("storj_satellite_suspension_score", "gauge", "Suspension score for a satellite (0-1)"),
        ("storj_satellite_online_score", "gauge", "Online score for a satellite (0-1)"),
        ("storj_satellite_disqualified", "gauge", "Whether the node is disqualified from this satellite"),
        ("storj_satellite_suspended", "gauge", "Whether the node is suspended on this satellite"),
        ("storj_satellite_ingress_bytes", "counter", "Total ingress bytes from this satellite (this month)"),
        ("storj_satellite_egress_bytes", "counter", "Total egress bytes to this satellite (this month)"),

        ("storj_payout_current_month_usd", "gauge", "Estimated payout for current month in USD"),
        ("storj_payout_current_held_usd", "gauge", "Held amount for current month in USD"),
        ("storj_payout_previous_month_usd", "gauge", "Payout for previous month in USD"),
        ("storj_payout_previous_held_usd", "gauge", "Held amount for previous month in USD"),
    ]

    for name, mtype, helptxt in metric_defs:
        lines.append(f"# HELP {name} {helptxt}")
        lines.append(f"# TYPE {name} {mtype}")

    now = time.time()

    for m in all_metrics:
        port = m["port"]
        node_label = f'node="port_{port}"'

        # Up/down
        lines.append(f'storj_node_up{{{node_label}}} {m["up"]}')

        if not m["up"]:
            continue

        # Info as labels
        node_id = m.get("node_id", "")[:16] or "unknown"
        version = m.get("version", "")
        wallet = m.get("wallet", "")
        info_label = f'{node_label},node_id="{node_id}",version="{version}",wallet="{wallet}"'
        lines.append(f'storj_node_info{{{info_label}}} 1')

        lines.append(f'storj_node_up_to_date{{{node_label}}} {m.get("up_to_date", 0)}')
        lines.append(f'storj_node_quic_ok{{{node_label}}} {m.get("quic_ok", 0)}')

        started = m.get("started_at", 0)
        lines.append(f'storj_node_started_timestamp{{{node_label}}} {started}')
        lines.append(f'storj_node_last_pinged_timestamp{{{node_label}}} {m.get("last_pinged", 0)}')

        if started > 0:
            lines.append(f'storj_node_uptime_seconds{{{node_label}}} {now - started:.0f}')

        # Disk
        du = m.get("disk_used", 0)
        da = m.get("disk_available", 0)
        dt = m.get("disk_trash", 0)
        lines.append(f'storj_disk_used_bytes{{{node_label}}} {du}')
        lines.append(f'storj_disk_available_bytes{{{node_label}}} {da}')
        lines.append(f'storj_disk_trash_bytes{{{node_label}}} {dt}')
        lines.append(f'storj_disk_overused_bytes{{{node_label}}} {m.get("disk_overused", 0)}')
        lines.append(f'storj_disk_total_bytes{{{node_label}}} {du + da + dt}')

        # Bandwidth
        lines.append(f'storj_bandwidth_used_bytes{{{node_label}}} {m.get("bw_used", 0)}')
        lines.append(f'storj_bandwidth_available_bytes{{{node_label}}} {m.get("bw_available", 0)}')

        # Payout
        lines.append(f'storj_payout_current_month_usd{{{node_label}}} {m.get("payout_current_month", 0):.4f}')
        lines.append(f'storj_payout_current_held_usd{{{node_label}}} {m.get("payout_current_held", 0):.4f}')
        lines.append(f'storj_payout_previous_month_usd{{{node_label}}} {m.get("payout_previous_month", 0):.4f}')
        lines.append(f'storj_payout_previous_held_usd{{{node_label}}} {m.get("payout_previous_held", 0):.4f}')

        # Per-satellite metrics
        for sat in m.get("satellites", []):
            sat_name = well_known_sat_name(sat["id"])
            sat_label = f'{node_label},satellite="{sat_name}",satellite_id="{sat["id"][:16]}"'
            lines.append(f'storj_satellite_audit_score{{{sat_label}}} {sat["audit_score"]:.6f}')
            lines.append(f'storj_satellite_suspension_score{{{sat_label}}} {sat["suspension_score"]:.6f}')
            lines.append(f'storj_satellite_online_score{{{sat_label}}} {sat["online_score"]:.6f}')
            lines.append(f'storj_satellite_disqualified{{{sat_label}}} {sat["disqualified"]}')
            lines.append(f'storj_satellite_suspended{{{sat_label}}} {sat["suspended"]}')
            lines.append(f'storj_satellite_ingress_bytes{{{sat_label}}} {sat["ingress"]}')
            lines.append(f'storj_satellite_egress_bytes{{{sat_label}}} {sat["egress"]}')

    return "\n".join(lines) + "\n"


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Silent — only log errors
        try:
            line = fmt % args
            if " 200 " in line or " 404 " in line:
                return
        except Exception:
            pass
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/metrics":
            # Fetch metrics from all configured nodes
            all_metrics = [fetch_node_metrics(p) for p in NODE_PORTS]
            body = render_prometheus(all_metrics).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/" or path == "/index.html":
            body = (
                "Storj Multi-Node Prometheus Exporter\n"
                "=====================================\n\n"
                f"Configured ports: {NODE_PORTS}\n\n"
                "Endpoints:\n"
                "  /metrics  - Prometheus metrics\n"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not Found")


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    print()
    print("  ╔════════════════════════════════════════════╗")
    print("  ║  STORJ PROMETHEUS EXPORTER                 ║")
    print("  ╠════════════════════════════════════════════╣")
    print(f"  ║  Metrics: http://localhost:{LISTEN_PORT}/metrics   ║")
    print(f"  ║  Watching ports: {','.join(str(p) for p in NODE_PORTS):<24}  ║")
    print("  ║                                            ║")
    print("  ║  Stop with Ctrl+C                          ║")
    print("  ╚════════════════════════════════════════════╝")
    print()

    try:
        with ThreadingServer((LISTEN_HOST, LISTEN_PORT), Handler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
    except OSError as e:
        if getattr(e, "errno", None) in (98, 48, 10048):
            print(f"  Error: port {LISTEN_PORT} is already in use.")
        else:
            print(f"  Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
