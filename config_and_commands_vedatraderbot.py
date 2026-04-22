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
    res = telegram_api("setMyCommands", commands=[
        {"command": "start", "description": "Start the bot"},
        {"command": "status", "description": "Check bot status"},
        {"command": "pairs", "description": "List monitored pairs"},
        {"command": "sessions", "description": "Show session schedule"},
        {"command": "stats", "description": "Show today's stats"}
    ])
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
        if text == "/gold" and PREMIUM_ENABLED:
            from premium import fmt_gold_status
            send_telegram_func(fmt_gold_status(user_id), chat_id=chat_id)

        elif text.startswith("/stats") and PREMIUM_ENABLED:
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
