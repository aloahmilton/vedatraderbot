import time
import schedule
from datetime import datetime
from veda_trader_bot import scan_markets, send_telegram

def scan_and_save():
    """Scan markets and send to Telegram"""
    print(f"[{datetime.now()}] Starting market scan...")
    try:
        scan_markets()
        print(f"[{datetime.now()}] Scan complete")
    except Exception as e:
        print(f"Scan error: {e}")

if __name__ == "__main__":
    print("=" * 50)
    print("VEDA TRADER BOT RUNNER - 24/7 MARKET SCANNER")
    print("=" * 50)

    # Run first scan immediately
    scan_and_save()

    # Schedule every 5 minutes
    schedule.every(5).minutes.do(scan_and_save)

    print("\nBot running. Scanning markets every 5 minutes...")

    while True:
        schedule.run_pending()
        time.sleep(30)