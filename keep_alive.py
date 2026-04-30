"""
VEDA TRADER - Keep Alive Ping Script
pings your Render app URL to prevent it from sleeping.

Run: python keep_alive.py
Or set up as a cron/scheduled task.

Runs every 5 minutes to keep the app awake without triggering restarts.
"""

import os
import sys
import time
import requests
from datetime import datetime

# Your Render app URL - UPDATE THIS
RENDER_URL = os.getenv("KEEP_ALIVE_URL", "https://vedatraderbot.onrender.com")

# Default ping interval (5 minutes = 300 seconds)
PING_INTERVAL = int(os.getenv("PING_INTERVAL", "300"))

def ping_app():
    """Ping the Render app."""
    try:
        r = requests.get(f"{RENDER_URL}/health", timeout=10)
        if r.status_code == 200:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✓ Ping OK")
            return True
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✗ Ping failed: {r.status_code}")
            return False
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✗ Ping error: {e}")
        return False

def main():
    # Check for aggressive mode
    aggressive = "--every-second" in sys.argv
    
    if aggressive:
        print(f"[KEEP ALIVE] Aggressive mode - pinging EVERY SECOND")
        print(f"[KEEP ALIVE] Target: {RENDER_URL}")
        print(f"[KEEP ALIVE] Press Ctrl+C to stop\n")
        while True:
            ping_app()
            time.sleep(1)  # Every second
    else:
        print(f"[KEEP ALIVE] Pinging every {PING_INTERVAL} seconds")
        print(f"[KEEP ALIVE] Target: {RENDER_URL}")
        print(f"[KEEP ALIVE] Press Ctrl+C to stop\n")
        while True:
            ping_app()
            time.sleep(PING_INTERVAL)

if __name__ == "__main__":
    main()
