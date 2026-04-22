import time
import schedule
import requests
from datetime import datetime, timezone
from src.config import (
    pairs_for_session, current_session, session_label, 
    TELEGRAM_TOKEN, ALL_PAIRS, GOLD_CHAT_ID, PREMIUM_ENABLED
)
from src.engine import analyze_pair, evaluate_pending_signals
from src.notifier import (
    send_telegram, fmt_signal, fmt_gold_signal, fmt_session_announcement, 
    fmt_watchlist, fmt_session_report, handle_telegram_command
)
from src.database import save_signal_to_db, record_signal_state

# Premium system initialized from config

# Global State
session_signals = []
last_session_alerted = ""
last_update_id = 0

def scan_markets():
    global session_signals, last_session_alerted
    
    now = datetime.now(timezone.utc)
    sess = current_session()
    
    # 1. Evaluate Outcomes
    evaluate_pending_signals(session_signals)
    
    # 2. Session Announcements
    if sess != last_session_alerted:
        send_telegram(fmt_session_announcement(sess), pin=True)
        pairs = pairs_for_session(sess)
        send_telegram(fmt_watchlist(sess, pairs))
        last_session_alerted = sess
        
    # 3. Scan Pairs
    pairs = pairs_for_session(sess)
    print(f"[{now.strftime('%H:%M:%S')}] Scanning {len(pairs)} pairs ({sess})")
    
    for p in pairs:
        sig = analyze_pair(p)
        if sig:
            sig["no"] = len(session_signals) + 1
            sig["timestamp"] = datetime.now(timezone.utc)
            sig["direction"] = sig["type"] # consistency
            
            if send_telegram(fmt_signal(sig, sig["no"])):
                session_signals.append(sig)
                save_signal_to_db(sig)
                record_signal_state(sig["pair"], sig["type"])
                print(f"  [SIGNAL] {sig['pair']} {sig['type']} sent (Score: {sig['score']}).")
                
                # Handle Gold Signal
                if sig.get("is_gold") and PREMIUM_ENABLED:
                    send_telegram(fmt_gold_signal(sig, sig["no"]), chat_id=GOLD_CHAT_ID)
                    print(f"  [GOLD] Sent to premium channel.")
        time.sleep(0.5)

    # 4. Session Report
    h, m = now.hour, now.minute
    if (h, m) in [(6, 55), (15, 55), (20, 55)]:
        date_str = now.strftime("%d %b").upper()
        send_telegram(fmt_session_report(session_signals, date_str))
        session_signals = []

def poll_commands():
    global last_update_id
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        params = {"offset": last_update_id + 1, "timeout": 1}
        r = requests.get(url, params=params, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if data.get("ok") and data.get("result"):
                for update in data["result"]:
                    last_update_id = max(last_update_id, update["update_id"])
                    try:
                        handle_telegram_command(update, send_telegram, PREMIUM_ENABLED)
                    except Exception as cmd_e:
                        print(f"[COMMAND ERROR] {cmd_e}")
    except: pass

def main():
    print("Veda Trader Bot v5 Online & Scanning...")
    send_telegram("🚀 <b>VEDA TRADER v5 ONLINE</b>\nModular structure active.")
    
    scan_markets()
    schedule.every(5).minutes.do(scan_markets)
    
    while True:
        schedule.run_pending()
        poll_commands()
        time.sleep(10)

if __name__ == "__main__":
    main()
