#!/usr/bin/env python3
"""
Storj Identity Backup Reminder — Monthly on the 1st at 10:00
Reads webhook URL from STORJ_DISCORD_WEBHOOK env var or .env file.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path


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


def main():
    embed = {
        "title": "🔐 Storj Identity-Backup Erinnerung",
        "description": (
            "Hey! Es ist Zeit fuer ein **Backup deiner Storj-Identity-Dateien**.\n\n"
            "Ohne Backup verlierst du bei Disk-Crash ALLE Earnings und Node-Reputation — und kannst die Node nicht "
            "wiederherstellen.\n\n"
            "**Backup folgender Ordner:**\n"
            "• `C:\\Users\\<DU>\\AppData\\Roaming\\Storj\\Identity\\storagenode\\` (alle Nodes)\n"
            "• Optional: gesamtes Storj-Konfigurations-Verzeichnis pro Node\n\n"
            "**Empfehlung:** Kopie auf USB-Stick + verschluesseltes Cloud-Backup."
        ),
        "color": 0xffb84d,
        "footer": {"text": "Naechste Erinnerung in ~30 Tagen"},
        "timestamp": datetime.now().astimezone().isoformat(),
    }
    body = json.dumps({"embeds": [embed]}).encode("utf-8")
    req = urllib.request.Request(WEBHOOK_URL, data=body, headers={"Content-Type": "application/json", "User-Agent": "storj-identity/1.0"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        print(f"Posted: HTTP {resp.status}")


if __name__ == "__main__":
    main()
