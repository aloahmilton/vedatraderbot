import time
import schedule
import requests
from datetime import datetime, timezone
from src.config import (
    pairs_for_session, current_session, session_label, 
    TELEGRAM_TOKEN, ALL_PAIRS, validate_runtime_config
)
from src.engine import analyze_pair, evaluate_pending_signals
from src.notifier import (
    send_telegram, fmt_signal, fmt_gold_signal, fmt_session_announcement,
    fmt_watchlist, fmt_session_report, handle_telegram_command, setup_bot_profile
)
from src.database import save_signal_to_db, record_signal_state
from src.database import upsert_bot_status, log_scan_error

# Premium system - integrated modularly
try:
    from src import premium
    PREMIUM_CHANNEL_ID = premium.PREMIUM_CHANNEL_ID
    PREMIUM_ENABLED = premium.PREMIUM_ENABLED
except ImportError:
    PREMIUM_CHANNEL_ID = None
    PREMIUM_ENABLED = False


# Global State
session_signals = []
last_session_alerted = ""
last_update_id = 0

def _deliver_signal(sig: dict) -> bool:
    """Route by tier and return public delivery status."""
    if sig["tier"] == "public":
        # FREE channel: Forex signals only
        return send_telegram(fmt_signal(sig, sig["no"]))

    # PREMIUM channel: All premium signals (Stocks, Indices, Commodities, Crypto)
    if PREMIUM_ENABLED and PREMIUM_CHANNEL_ID:
        if sig.get("is_gold"):
            # Gold signals get special formatting
            delivered = send_telegram(fmt_gold_signal(sig, sig["no"]), chat_id=PREMIUM_CHANNEL_ID)
            print("  [GOLD] Sent premium gold signal to private channel." if delivered else "  [GOLD] Failed to send premium gold signal.")
            return delivered
        else:
            # Regular premium signals
            delivered = send_telegram(fmt_signal(sig, sig["no"]), chat_id=PREMIUM_CHANNEL_ID)
            print("  [PREMIUM] Sent premium signal to private channel." if delivered else "  [PREMIUM] Failed to send premium signal.")
            return delivered

    # No premium channel configured or disabled
    return False

def _store_signal(sig: dict, delivered: bool):
    sig["telegram_ok"] = bool(delivered) if sig["tier"] == "public" else None
    save_signal_to_db(sig)
    record_signal_state(sig["pair"], sig["type"])

def scan_markets():
    global session_signals, last_session_alerted
    
    now = datetime.now(timezone.utc)
    sess = current_session()
    sent_ok = 0
    sent_fail = 0
    scanned = 0
    generated = 0
    
    # 1. Evaluate Outcomes
    try:
        evaluate_pending_signals(session_signals)
    except Exception as e:
        print(f"[EVALUATION ERROR] {e}")
        log_scan_error("evaluate_pending_signals", str(e))
    
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
        scanned += 1
        try:
            sig = analyze_pair(p)
        except Exception as e:
            print(f"  [SCAN ERROR] {p.get('name', 'unknown')}: {e}")
            log_scan_error("analyze_pair", f"{p.get('name', 'unknown')}: {e}")
            continue
        if sig:
            generated += 1
            sig["no"] = len(session_signals) + 1
            sig["timestamp"] = datetime.now(timezone.utc)
            sig["direction"] = sig["type"] 

            delivered = _deliver_signal(sig)
            _store_signal(sig, delivered)
            session_signals.append(sig)

            if sig["tier"] == "public":
                if delivered:
                    sent_ok += 1
                    print(f"  [PUBLIC SIGNAL] {sig['pair']} {sig['type']} sent (Score: {sig['score']}).")
                else:
                    sent_fail += 1
                    print(f"  [PUBLIC SIGNAL FAILED] {sig['pair']} {sig['type']} (Score: {sig['score']}).")
            else:
                print(f"  [PREMIUM LOGGED] {sig['pair']} {sig['type']} saved to DB (Score: {sig['score']}).")
        time.sleep(0.5)

    # 4. Session Report
    h, m = now.hour, now.minute
    if (h, m) in [(6, 55), (15, 55), (20, 55)]:
        date_str = now.strftime("%d %b").upper()
        send_telegram(fmt_session_report(session_signals, date_str))
        session_signals = []

    upsert_bot_status({
        "last_scan_at": datetime.now(timezone.utc).replace(tzinfo=None),
        "session": sess,
        "pairs_scanned": scanned,
        "signals_generated": generated,
        "signals_sent_ok": sent_ok,
        "signals_sent_fail": sent_fail,
    })

def poll_commands():
    global last_update_id
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        params = {"offset": last_update_id + 1, "timeout": 8, "allowed_updates": ["message", "callback_query"]}
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
                        log_scan_error("telegram_command", str(cmd_e))
    except Exception as e:
        print(f"[POLL ERROR] {e}")
        log_scan_error("poll_commands", str(e))

def main():
    issues = validate_runtime_config()
    if issues:
        for issue in issues:
            print(f"[CONFIG ERROR] {issue}")

    print("Veda Trader Bot v5 Online & Scanning...")
    send_telegram("🚀 <b>VEDA TRADER v5 ONLINE</b>\nLogic pipeline and delivery tracking active.")
    setup_bot_profile()  # Update bot commands on Telegram

    scan_markets()
    schedule.every(5).minutes.do(scan_markets)
    
    while True:
        schedule.run_pending()
        poll_commands()
        time.sleep(2)

if __name__ == "__main__":
    main()
