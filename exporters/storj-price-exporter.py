#!/usr/bin/env python3
"""
Storj Token Price Exporter
===========================
Fetches STORJ token price from CoinGecko (USD/EUR) and exposes as Prometheus metrics.
Cached 5 minutes to respect free-tier rate limits.

Start:   py storj-price-exporter.py
Metrics: http://localhost:9652/metrics
"""

import http.server
import socketserver
import urllib.request
import json
import sys
import time

LISTEN_PORT = 9652
LISTEN_HOST = "0.0.0.0"
CACHE_TTL = 300  # 5 minutes
API_URL = "https://api.coingecko.com/api/v3/simple/price?ids=storj&vs_currencies=usd,eur&include_24hr_change=true"

_cache = {"data": None, "fetched_at": 0}


def fetch_price():
    now = time.time()
    if _cache["data"] and (now - _cache["fetched_at"]) < CACHE_TTL:
        return _cache["data"]
    try:
        req = urllib.request.Request(API_URL, headers={"User-Agent": "storj-price-exporter/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        storj = data.get("storj", {})
        result = {
            "usd": float(storj.get("usd", 0) or 0),
            "eur": float(storj.get("eur", 0) or 0),
            "usd_24h_change": float(storj.get("usd_24h_change", 0) or 0),
            "eur_24h_change": float(storj.get("eur_24h_change", 0) or 0),
        }
        _cache["data"] = result
        _cache["fetched_at"] = now
        return result
    except Exception as e:
        sys.stderr.write(f"[price-exporter] fetch failed: {e}\n")
        return _cache["data"] or {"usd": 0, "eur": 0, "usd_24h_change": 0, "eur_24h_change": 0}


def render():
    p = fetch_price()
    lines = [
        "# HELP storj_token_price_usd Current STORJ token price in USD (CoinGecko)",
        "# TYPE storj_token_price_usd gauge",
        f"storj_token_price_usd {p['usd']}",
        "# HELP storj_token_price_eur Current STORJ token price in EUR (CoinGecko)",
        "# TYPE storj_token_price_eur gauge",
        f"storj_token_price_eur {p['eur']}",
        "# HELP storj_token_price_24h_change_percent 24h price change in percent",
        "# TYPE storj_token_price_24h_change_percent gauge",
        f'storj_token_price_24h_change_percent{{currency="usd"}} {p["usd_24h_change"]}',
        f'storj_token_price_24h_change_percent{{currency="eur"}} {p["eur_24h_change"]}',
        "",
    ]
    return "\n".join(lines)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path == "/metrics":
            body = render().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    print(f"Storj Token Price Exporter — http://localhost:{LISTEN_PORT}/metrics")
    try:
        with ThreadingServer((LISTEN_HOST, LISTEN_PORT), Handler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    except OSError as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
