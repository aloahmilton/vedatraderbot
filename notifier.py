"""
VEDA TRADER - notifier.py
Telegram message formatting and delivery.
"""

import os
import requests
from datetime import datetime, timezone
from src.config import (
    TELEGRAM_TOKEN, FREE_CHANNEL_ID, PREMIUM_CHANNEL_ID,
    ADMIN_CHAT_ID, SESSIONS, session_label
)

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

LOGO = "⚡ <b>VEDA TRADER</b>"


# ── Core Sender ──────────────────────────────────────────────

def send_telegram(text: str, chat_id: str = None, pin: bool = False,
                  parse_mode: str = "HTML") -> bool:
    target = chat_id or FREE_CHANNEL_ID
    if not target or not TELEGRAM_TOKEN:
        return False
    try:
        r = requests.post(
            f"{BASE_URL}/sendMessage",
            json={"chat_id": target, "text": text,
                  "parse_mode": parse_mode, "disable_web_page_preview": True},
            timeout=10
        )
        data = r.json()
        if not data.get("ok"):
            print(f"[TG ERROR] {data.get('description')}")
            return False
        if pin:
            msg_id = data["result"]["message_id"]
            requests.post(f"{BASE_URL}/pinChatMessage",
                          json={"chat_id": target, "message_id": msg_id}, timeout=5)
        return True
    except Exception as e:
        print(f"[TG SEND ERROR] {e}")
        return False

def send_admin(text: str) -> bool:
    """Send message directly to admin's personal Telegram."""
    if not ADMIN_CHAT_ID:
        return False
    return send_telegram(text, chat_id=ADMIN_CHAT_ID)


# ── Signal Formatters ────────────────────────────────────────

def fmt_signal(sig: dict) -> str:
    arrow   = "📈" if sig["type"] == "BUY" else "📉"
    tier_lbl = "🔓 FREE SIGNAL" if sig["tier"] == "public" else "💎 PREMIUM SIGNAL"
    now_str = datetime.now(timezone.utc).strftime("%H:%M UTC")

    return (
        f"{LOGO}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"{tier_lbl}  |  {sig.get('quality','')}\n\n"
        f"{arrow}  <b>{sig['pair']}</b>  —  <b>{sig['type']}</b>\n\n"
        f"🕐 Time: <code>{now_str}</code>\n"
        f"💰 Entry: <code>{sig['price']}</code>\n"
        f"🎯 Take Profit: <code>{sig['tp']}</code>  (+{sig['tp_pips']} pips)\n"
        f"🛑 Stop Loss: <code>{sig['sl']}</code>  (-{sig['sl_pips']} pips)\n"
        f"⏱ Duration: {sig['duration']}\n\n"
        f"📊 RSI: {sig['rsi']}  |  EMA: {sig['ema_cross'].title()}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <i>Trade at your own risk. Not financial advice.</i>"
    )

def fmt_gold_signal(sig: dict) -> str:
    arrow = "📈" if sig["type"] == "BUY" else "📉"
    now_str = datetime.now(timezone.utc).strftime("%H:%M UTC")
    return (
        f"{LOGO}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🥇 GOLD SIGNAL  |  {sig.get('quality','')}\n\n"
        f"{arrow}  <b>XAUUSD</b>  —  <b>{sig['type']}</b>\n\n"
        f"🕐 Time: <code>{now_str}</code>\n"
        f"💰 Entry: <code>{sig['price']}</code>\n"
        f"🎯 TP: <code>{sig['tp']}</code>\n"
        f"🛑 SL: <code>{sig['sl']}</code>\n"
        f"⏱ Duration: {sig['duration']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <i>Not financial advice.</i>"
    )


# ── Session Messages ─────────────────────────────────────────

def fmt_session_announcement(sess: str) -> str:
    info = SESSIONS.get(sess, {})
    label = info.get("label", sess.upper())
    now_str = datetime.now(timezone.utc).strftime("%d %b %Y  %H:%M UTC")

    tips = {
        "asian":   "Best pairs: USD/JPY, AUD/USD, GBP/JPY\nVolatility is moderate — wait for clear setups.",
        "london":  "Best pairs: EUR/USD, GBP/USD, Gold\nHighest volatility of the day — prime scalping time!",
        "newyork": "Best pairs: EUR/USD, GBP/USD, US30, NAS100\nOverlap with London until 16:00 UTC = high volume.",
    }
    tip = tips.get(sess, "Stay disciplined. Follow the signals.")

    return (
        f"{LOGO}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔔 <b>{label} OPEN</b>\n"
        f"📅 {now_str}\n\n"
        f"📌 {tip}\n\n"
        f"🚨 Signals starting now. Stay ready!\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )

def fmt_session_close(sess: str) -> str:
    label = session_label(sess)
    return (
        f"{LOGO}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔕 <b>{label} CLOSED</b>\n\n"
        f"✅ Session ended. Stop trading and wait for the next session.\n"
        f"📊 Session report coming up shortly...\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )

def fmt_session_report(signals: list, date_str: str) -> str:
    if not signals:
        return f"{LOGO}\n📊 <b>SESSION REPORT — {date_str}</b>\n\nNo signals this session."

    tp_hits = sum(1 for s in signals if s.get("result") == "✅ TP HIT")
    sl_hits = sum(1 for s in signals if s.get("result") == "❌ SL HIT")
    pending = sum(1 for s in signals if not s.get("result"))
    total   = len(signals)
    winrate = round(tp_hits / total * 100) if total else 0

    lines = [
        f"{LOGO}",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"📊 <b>SESSION REPORT — {date_str}</b>\n",
        f"📤 Signals sent:  {total}",
        f"✅ TP Hit:        {tp_hits}",
        f"❌ SL Hit:        {sl_hits}",
        f"⏳ Still open:   {pending}",
        f"🎯 Win Rate:      {winrate}%\n",
    ]

    for s in signals[-5:]:  # last 5 signals summary
        result = s.get("result", "⏳ Open")
        lines.append(f"• {s['pair']} {s['type']} → {result}")

    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("⚠️ <i>Past results do not guarantee future performance.</i>")
    return "\n".join(lines)

def fmt_watchlist(sess: str, pairs: list) -> str:
    label = session_label(sess)
    names = "\n".join(f"• {p['name']}" for p in pairs)
    return (
        f"{LOGO}\n"
        f"👀 <b>WATCHLIST — {label}</b>\n\n"
        f"{names}\n\n"
        f"⚡ Scanning these pairs for signals..."
    )

def fmt_weekend_close() -> str:
    return (
        f"{LOGO}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏁 <b>MARKETS CLOSING</b>\n\n"
        f"Forex & indices markets are closing for the weekend.\n"
        f"📅 Markets reopen: <b>Sunday 21:00 UTC</b>\n\n"
        f"💎 Premium members: Crypto signals continue 24/7.\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )

def fmt_weekend_open() -> str:
    return (
        f"{LOGO}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 <b>MARKETS REOPENING</b>\n\n"
        f"Forex & indices are back! Asian session starting now.\n"
        f"📌 Make sure your broker account is ready.\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )

def fmt_broker_reminder() -> str:
    affiliate = os.getenv("AFFILIATE_LINK", "#")
    return (
        f"{LOGO}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏦 <b>DON'T MISS THE SIGNALS!</b>\n\n"
        f"New session starting soon. Make sure you have a broker ready.\n\n"
        f"👉 <a href='{affiliate}'>Open a free broker account here</a>\n\n"
        f"✅ Fast registration  ✅ Low minimum deposit\n"
        f"✅ Works with our signals\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )


# ── Admin Summary Formatter ──────────────────────────────────

def fmt_admin_summary(stats: dict, ai_note: str = "") -> str:
    lines = [
        f"🤖 <b>VEDA ADMIN SUMMARY</b>",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"📊 Signals (24h): {stats.get('total', 0)}",
        f"✅ TP Hits: {stats.get('tp_hits', 0)}",
        f"❌ SL Hits: {stats.get('sl_hits', 0)}",
        f"🎯 Win Rate: {stats.get('winrate', 0)}%",
        f"",
        f"👥 Free subs: {stats.get('free_subs', 0)}",
        f"💎 Premium subs: {stats.get('premium_subs', 0)}",
    ]
    if ai_note:
        lines += ["", f"🧠 <b>AI Note:</b>", ai_note]
    return "\n".join(lines)


# ── Bot Commands Handler ─────────────────────────────────────

def handle_telegram_command(update: dict, send_fn, premium_enabled: bool):
    from src.database import (
        add_subscriber, upgrade_subscriber, downgrade_subscriber,
        remove_subscriber, get_all_subscribers, get_subscriber, get_daily_stats
    )

    msg = update.get("message", {})
    text = (msg.get("text") or "").strip()
    chat_id = str(msg.get("chat", {}).get("id", ""))
    username = msg.get("from", {}).get("username", "unknown")
    is_admin = (chat_id == str(ADMIN_CHAT_ID))

    if not text.startswith("/"):
        return

    cmd = text.split()[0].lower()
    args = text.split()[1:]

    # ── Public commands ──
    if cmd == "/start":
        add_subscriber(chat_id, username, "free")
        send_fn(
            f"{LOGO}\n\n"
            f"👋 Welcome <b>{username}</b>!\n\n"
            f"You're now registered for FREE forex signals.\n\n"
            f"💎 Want premium signals (indices, crypto, gold)?\n"
            f"Contact admin: @VedaTraderAdmin\n\n"
            f"Commands:\n"
            f"/signals — view recent signals\n"
            f"/status — bot status\n"
            f"/premium — learn about premium",
            chat_id=chat_id
        )
        return

    if cmd == "/premium":
        send_fn(
            f"{LOGO}\n\n"
            f"💎 <b>PREMIUM MEMBERSHIP</b>\n\n"
            f"✅ Forex + Indices + Crypto + Gold signals\n"
            f"✅ Higher accuracy swing trades\n"
            f"✅ 24/7 crypto signals on weekends\n"
            f"✅ Priority support\n\n"
            f"📩 Contact admin to upgrade: @VedaTraderAdmin",
            chat_id=chat_id
        )
        return

    if cmd == "/status":
        from src.database import get_db
        db = get_db()
        status = db["bot_status"].find_one({"_id": "latest"}) if db else {}
        send_fn(
            f"🤖 <b>Bot Status</b>\n\n"
            f"✅ Online\n"
            f"📊 Last scan: {status.get('session','—').title()} session\n"
            f"📤 Signals today: {status.get('signals_generated', 0)}",
            chat_id=chat_id
        )
        return

    if cmd == "/signals":
        from src.database import get_db
        db = get_db()
        if db:
            recent = list(db["signals"].find({"tier": "public"}).sort("timestamp", -1).limit(5))
            if recent:
                lines = [f"{LOGO}\n📋 <b>Recent Signals</b>\n"]
                for s in recent:
                    result = s.get("result", "⏳")
                    lines.append(f"• {s['pair']} {s['type']} → {result}")
                send_fn("\n".join(lines), chat_id=chat_id)
            else:
                send_fn("No signals yet today.", chat_id=chat_id)
        return

    # ── Admin-only commands ──
    if not is_admin:
        if cmd in ["/grant", "/revoke", "/kick", "/subscribers", "/summary", "/broadcast"]:
            send_fn("⛔ Admin only.", chat_id=chat_id)
        return

    if cmd == "/grant" and args:
        target_id = args[0].replace("@", "")
        ok = upgrade_subscriber(target_id)
        send_fn(f"{'✅ Upgraded' if ok else '❌ User not found'}: {target_id}", chat_id=chat_id)
        return

    if cmd == "/revoke" and args:
        target_id = args[0].replace("@", "")
        ok = downgrade_subscriber(target_id)
        send_fn(f"{'✅ Downgraded to free' if ok else '❌ User not found'}: {target_id}", chat_id=chat_id)
        return

    if cmd == "/kick" and args:
        target_id = args[0].replace("@", "")
        ok = remove_subscriber(target_id)
        send_fn(f"{'✅ Removed' if ok else '❌ Not found'}: {target_id}", chat_id=chat_id)
        return

    if cmd == "/subscribers":
        free    = get_all_subscribers("free")
        premium = get_all_subscribers("premium")
        send_fn(
            f"👥 <b>Subscribers</b>\n\n"
            f"🔓 Free: {len(free)}\n"
            f"💎 Premium: {len(premium)}\n"
            f"📊 Total: {len(free) + len(premium)}",
            chat_id=chat_id
        )
        return

    if cmd == "/summary":
        stats = get_daily_stats()
        send_fn(fmt_admin_summary(stats), chat_id=chat_id)
        return

    if cmd == "/broadcast" and args:
        message = " ".join(args)
        send_fn(f"📢 <b>Admin Broadcast</b>\n\n{message}", chat_id=FREE_CHANNEL_ID)
        if premium_enabled and PREMIUM_CHANNEL_ID:
            send_fn(f"📢 <b>Admin Broadcast</b>\n\n{message}", chat_id=PREMIUM_CHANNEL_ID)
        send_fn("✅ Broadcast sent.", chat_id=chat_id)
        return

    if cmd == "/pause":
        send_fn("⏸ Signaling paused. Use /resume to restart.", chat_id=chat_id)
        return

    if cmd == "/resume":
        send_fn("▶️ Signaling resumed.", chat_id=chat_id)
        return


# ── Bot Profile Setup ────────────────────────────────────────

def setup_bot_profile():
    try:
        requests.post(f"{BASE_URL}/setMyCommands", json={"commands": [
            {"command": "start",       "description": "Register & get started"},
            {"command": "signals",     "description": "View recent signals"},
            {"command": "status",      "description": "Bot status"},
            {"command": "premium",     "description": "Learn about premium"},
        ]}, timeout=5)
        print("[BOT] Commands set ✓")
    except Exception as e:
        print(f"[BOT SETUP ERROR] {e}")
