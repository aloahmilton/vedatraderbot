#!/usr/bin/env python3
"""
Setup Veda Trader Bot profile on Telegram

This script configures:
- Bot display name
- Bot description
- About text
- Command menu
"""

import requests

TELEGRAM_TOKEN = "8652896161:AAEwKHUNG4G7JmRgChJokZq6oUQW5nZU-GI"

def telegram_api(method: str, **kwargs) -> dict:
    """Call Telegram Bot API"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"
    try:
        r = requests.post(url, json=kwargs, timeout=15)
        return r.json()
    except Exception as e:
        return {"ok": False, "description": str(e)}

def setup_bot_profile():
    print("Setting up Veda Trader Bot profile...\n")

    # 1. Bot Name
    print("✓ Setting bot name...")
    res = telegram_api("setMyName", name="Veda Trader")
    print(f"  {res.get('ok', False)}: {res.get('description', '')}")

    # 2. Bot Description (What can this bot do?)
    print("\n✓ Setting description...")
    res = telegram_api("setMyDescription", description="""✅ Real-time forex signals with 5-minute expiry
✅ Pre-signal alerts 1 minute before entry
✅ Session reports with win rate stats
✅ Automatic win/loss tracking

Monitors 18 currency pairs across London, NY and Asian sessions.""")
    print(f"  {res.get('ok', False)}: {res.get('description', '')}")

    # 3. About Text (profile page)
    print("\n✓ Setting about text...")
    res = telegram_api("setMyAboutText", text="""⚡ Veda Trader
High accuracy forex signal bot with automatic Gale management, session reports and live result tracking.

📊 18 pairs | 🕒 5min expiry | 🌍 3 sessions""")
    print(f"  {res.get('ok', False)}: {res.get('description', '')}")

    # 4. Commands menu
    print("\n✓ Setting commands...")
    commands = [
        {"command": "start", "description": "Get bot info and status"},
        {"command": "status", "description": "Check bot status"},
        {"command": "pairs", "description": "List monitored pairs"},
        {"command": "sessions", "description": "Show session schedule"},
        {"command": "gold", "description": "Check GOLD membership status"}
    ]
    res = telegram_api("setMyCommands", commands=commands)
    print(f"  {res.get('ok', False)}: {res.get('description', '')}")

    print("\n✅ Bot profile configured successfully!")

def handle_telegram_command(update: dict, send_telegram_func, PREMIUM_ENABLED: bool):
    """Handle incoming Telegram commands - separate file to keep main bot clean"""
    try:
        message = update.get("message", {})
        chat_id = str(message.get("chat", {}).get("id"))
        user_id = str(message.get("from", {}).get("id"))
        username = message.get("from", {}).get("username", "Unknown")
        text = message.get("text", "")

        # User commands
        if text == "/start":
            welcome_msg = (
                f"🎯 <b>VEDA TRADER BOT v5</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"\n"
                f"✅ <b>Active & Scanning Markets</b>\n"
                f"\n"
                f"📊 Monitoring 18 currency pairs\n"
                f"⏰ Signals every 5 minutes\n"
                f"🌍 3 trading sessions\n"
                f"\n"
                f"👑 <b>GOLD Premium Available</b>\n"
                f"   • 85%+ win rate signals\n"
                f"   • 2-3 elite signals/day\n"
                f"   • Private channel delivery\n"
                f"\n"
                f"Use /gold to check premium status"
            )
            send_telegram_func(welcome_msg, chat_id=chat_id)

        elif text == "/status":
            current_sess = "unknown"
            try:
                from datetime import datetime, timezone
                h = datetime.now(timezone.utc).hour
                if 12 <= h < 16: current_sess = "London/NY Overlap"
                elif 7 <= h < 16: current_sess = "London Session"
                elif 16 <= h < 21: current_sess = "New York Session"
                else: current_sess = "Asian Session"
            except:
                pass

            status_msg = (
                f"📊 <b>BOT STATUS</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"\n"
                f"✅ <b>ONLINE & ACTIVE</b>\n"
                f"\n"
                f"🌍 Current Session: {current_sess}\n"
                f"📈 Scanning: 18 pairs\n"
                f"⏰ Next scan: ~{30} seconds\n"
                f"👑 Premium: {'Enabled' if PREMIUM_ENABLED else 'Disabled'}\n"
            )
            send_telegram_func(status_msg, chat_id=chat_id)

        elif text == "/pairs":
            pairs_msg = (
                f"📊 <b>MONITORED PAIRS</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"\n"
                f"<b>🇪🇺 Major Forex (All Sessions):</b>\n"
                f"EUR/USD, GBP/USD, USD/JPY, USD/CAD\n"
                f"AUD/USD, NZD/USD, USD/CHF\n"
                f"\n"
                f"<b>🇬🇧 London Session:</b>\n"
                f"EUR/GBP, EUR/JPY, GBP/JPY\n"
                f"EUR/CHF, GBP/CHF\n"
                f"\n"
                f"<b>🇺🇸 New York Session:</b>\n"
                f"EUR/CAD, GBP/CAD, CAD/JPY\n"
                f"\n"
                f"<b>🌏 Asian Session:</b>\n"
                f"AUD/JPY, NZD/JPY, AUD/NZD\n"
            )
            send_telegram_func(pairs_msg, chat_id=chat_id)

        elif text == "/sessions":
            sessions_msg = (
                f"⏰ <b>TRADING SESSIONS (UTC)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"\n"
                f"🌏 <b>Asian Session</b>\n"
                f"   Start: 00:00 UTC\n"
                f"   Duration: 7 hours\n"
                f"   Pairs: AUD/JPY, NZD/JPY, AUD/NZD\n"
                f"\n"
                f"🇬🇧 <b>London Session</b>\n"
                f"   Start: 07:00 UTC\n"
                f"   Duration: 4 hours\n"
                f"   Pairs: EUR/GBP, EUR/JPY, GBP/JPY, etc.\n"
                f"\n"
                f"🔥 <b>London/NY Overlap</b>\n"
                f"   Start: 12:00 UTC\n"
                f"   Duration: 4 hours\n"
                f"   Pairs: All pairs (best signals)\n"
                f"\n"
                f"🇺🇸 <b>New York Session</b>\n"
                f"   Start: 16:00 UTC\n"
                f"   Duration: 5 hours\n"
                f"   Pairs: USD pairs, EUR/CAD, GBP/CAD\n"
            )
            send_telegram_func(sessions_msg, chat_id=chat_id)

        elif text == "/gold" and PREMIUM_ENABLED:
            from premium import get_gold_stats
            active, expiring = get_gold_stats()
            stats_msg = (
                f"👑 <b>GOLD TIER STATS</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"\n"
                f"✅ Active users: {active}\n"
                f"⏰ Expiring soon: {expiring}\n"
                f"\n"
                f"📊 Ultra-strict gold filters active"
            )
            send_telegram_func(stats_msg, chat_id=chat_id)

        # Admin commands (only respond in private chat)
        elif chat_id.startswith("-") == False:  # Private chat
            if text.startswith("/addgold ") and PREMIUM_ENABLED:
                # /addgold user_id days
                parts = text.split()
                if len(parts) >= 3:
                    target_user_id = parts[1]
                    try:
                        days = int(parts[2])
                        from premium import add_gold_user
                        success = add_gold_user(target_user_id, days, username)
                        if success:
                            send_telegram_func(f"✅ Added {target_user_id} to GOLD for {days} days", chat_id=chat_id)
                        else:
                            send_telegram_func("❌ Failed to add user", chat_id=chat_id)
                    except ValueError:
                        send_telegram_func("❌ Invalid format: /addgold user_id days", chat_id=chat_id)

    except Exception as e:
        print(f"[COMMAND HANDLER] {e}")
        pass


if __name__ == "__main__":
    setup_bot_profile()
