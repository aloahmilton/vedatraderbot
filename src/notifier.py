import requests
import os
from datetime import datetime, timezone, timedelta
from .config import TELEGRAM_TOKEN, CHAT_ID, PUBLIC_CHANNEL_URL, EXPIRY_MINUTES, current_session, session_label, ALL_PAIRS

def send_telegram(msg: str, pin: bool = False, chat_id: str = None, **kwargs) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    target_chat = chat_id if chat_id is not None else CHAT_ID
    payload = {
        "chat_id": target_chat,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if "reply_markup" in kwargs:
        payload["reply_markup"] = kwargs["reply_markup"]
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code != 200:
            print(f"  [Telegram FAIL] HTTP {r.status_code}: {r.text[:200]}")
            return False
        res = r.json()
        if not res.get("ok"):
            print(f"  [Telegram FAIL] {res.get('description')}")
            return False
        if pin:
            mid = res.get("result", {}).get("message_id")
            if mid:
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/pinChatMessage",
                    json={"chat_id": target_chat, "message_id": mid, "disable_notification": True},
                    timeout=10
                )
        return True
    except Exception as e:
        print(f"  [Telegram Error] {e}")
        return False

def send_voice(voice_file_path: str, caption: str = None, chat_id: str = None) -> bool:
    """Send voice message to Telegram. voice_file_path should be path to .ogg or .mp3 file."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendVoice"
    target_chat = chat_id if chat_id is not None else CHAT_ID
    try:
        with open(voice_file_path, 'rb') as voice_file:
            files = {'voice': voice_file}
            data = {'chat_id': target_chat}
            if caption:
                data['caption'] = caption
                data['parse_mode'] = 'HTML'
            r = requests.post(url, data=data, files=files, timeout=30)
            res = r.json()
            if not res.get("ok"):
                print(f"  [Voice FAIL] {res.get('description')}")
                return False
            return True
    except Exception as e:
        print(f"  [Voice Error] {e}")
        return False

def score_bar(score: int) -> str:
    filled = score // 20
    empty  = 5 - filled
    return "█" * filled + "░" * empty + f"  {score}/100"

def fmt_signal(sig: dict, sig_no: int = 0) -> str:
    is_buy = sig["type"] == "BUY"
    arrow  = "🟢 <b>BUY  /  CALL</b>" if is_buy else "🔴 <b>SELL  /  PUT</b>"
    icon   = "🚀" if is_buy else "📉"
    bar    = ("🟩" * 4) if is_buy else ("🟥" * 4)
    sess_lbl = session_label(current_session()).split(" ", 1)[-1]

    now     = datetime.now(timezone.utc)
    now_str = now.strftime("%H:%M")
    base    = now.replace(second=0, microsecond=0)
    t1      = (base + timedelta(minutes=EXPIRY_MINUTES)).strftime("%H:%M")
    t2      = (base + timedelta(minutes=EXPIRY_MINUTES * 2)).strftime("%H:%M")
    t3      = (base + timedelta(minutes=EXPIRY_MINUTES * 3)).strftime("%H:%M")

    score   = sig.get("score", 0)
    q_bar   = score_bar(score)
    
    tier = "✅ VALID"
    if score >= 80: tier = "💎 PREMIUM"
    elif score >= 65: tier = "🔥 HIGH QUALITY"

    header_no = f"#{sig_no:02d}" if sig_no else "##"

    return (
        f"📡 <b>VEDA TRADER v5</b>   ·   {sess_lbl}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{icon}  <b>{sig['pair']}</b>\n"
        f"🕹  Action: {arrow}\n"
        f"\n"
        f"💵  Entry Price:    <code>{sig['price']:.5f}</code>\n"
        f"⏱  Entry Time:     <code>{now_str} UTC</code>\n"
        f"⏳  Expiry:         <code>{EXPIRY_MINUTES} min  →  {t1}</code>\n"
        f"\n"
        f"🛡  <b>Gale Recovery:</b>\n"
        f"   ┣ 1st Gale  →  <code>{t2}</code>\n"
        f"   ┗ 2nd Gale  →  <code>{t3}</code>\n"
        f"\n"
        f"📊  <b>Signal Quality:</b>  {tier}\n"
        f"   <code>{q_bar}</code>\n"
        f"\n"
        f"🧭  15M Trend: <b>{sig['trend']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"ⓘ <b>Trade Stocks, Indices & Crypto?</b>\n"
        f"👉 <b>Click /start to upgrade to GOLD</b>"
    )

def fmt_premium_signal(sig: dict, sig_no: int = 0):
    """Branded formatting for premium signals."""
    is_buy = sig["type"] == "BUY"
    icon = "💎"
    arrow = "🚀 <b>BUY / CALL</b>" if is_buy else "📉 <b>SELL / PUT</b>"
    
    now = datetime.now(timezone.utc)
    now_str = now.strftime("%H:%M")
    base = now.replace(second=0, microsecond=0)
    t1 = (base + timedelta(minutes=EXPIRY_MINUTES)).strftime("%H:%M")
    t2 = (base + timedelta(minutes=EXPIRY_MINUTES * 2)).strftime("%H:%M")
    
    return (
        f"💎 <b>VEDA TRADER — PREMIUM</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>{sig['pair']}</b> — {arrow}\n"
        f"\n"
        f"💵  Price: <code>{sig['price']:.5f}</code>\n"
        f"⏱  Time:  <code>{now_str} UTC</code>\n"
        f"⏳  Exp:   <code>{EXPIRY_MINUTES}m → {t1}</code>\n"
        f"🛡  Gale:  <code>{t2}</code>\n"
        f"\n"
        f"📊  Score: <b>{sig['score']}/100</b>\n"
        f"🧭  Trend: <b>{sig['trend']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 <i>Elite algorithmic execution</i>"
    )

def fmt_gold_signal(sig: dict, sig_no: int = 0):
    """Ultra-premium branding for gold signals."""
    is_buy = sig["type"] == "BUY"
    arrow = "🚀 <b>BUY / CALL</b>" if is_buy else "📉 <b>SELL / PUT</b>"
    
    now = datetime.now(timezone.utc)
    now_str = now.strftime("%H:%M")
    base = now.replace(second=0, microsecond=0)
    t1 = (base + timedelta(minutes=EXPIRY_MINUTES)).strftime("%H:%M")
    
    return (
        f"👑 <b>VEDA TRADER — GOLD</b> 👑\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⭐ <b>HIGH ACCURACY SETUP</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>{sig['pair']}</b> — {arrow}\n"
        f"\n"
        f"💵  Entry: <code>{sig['price']:.5f}</code>\n"
        f"⏱  Time:  <code>{now_str} UTC</code>\n"
        f"⏳  Exp:   <code>{EXPIRY_MINUTES}m → {t1}</code>\n"
        f"\n"
        f"📊  Accuracy: <b>{sig['score']}/100</b>\n"
        f"🧭  1H Trend: <b>CONFIRMED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✨ <i>This is an elite tier signal.</i>"
    )

def fmt_session_announcement(sess: str) -> str:
    SESSION_META = {
        "asian":   ("ASIAN SESSION",       "🌏"),
        "london":  ("LONDON SESSION",      "🇬🇧"),
        "overlap": ("LONDON × NY OVERLAP", "🔥"),
        "newyork": ("NEW YORK SESSION",    "🇺🇸"),
    }
    label, emoji = SESSION_META.get(sess, ("SESSION", "🔔"))
    
    return (
        f"{emoji} <b>{label} — NOW OPEN</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"🎯 <b>v5 filters active:</b> ATR + ADX + 15M trend\n"
        f"📉 Expect fewer signals, but much higher quality.\n"
        f"💎 <b>Stay sharp.</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━"
    )

def fmt_watchlist(sess: str, pairs: list) -> str:
    tips = {
        "asian":   "JPY, AUD and NZD crosses most active. Expect steady moves.",
        "london":  "EUR and GBP wake up. First 2 hours = strongest breakouts.",
        "overlap": "Peak liquidity. All pairs can run hard. Best signals.",
        "newyork": "USD pairs dominate. Watch for high-impact news events.",
    }
    
    # Chunk pairs into rows of 2 for a cleaner grid look
    rows = []
    for i in range(0, len(pairs), 2):
        pair_row = pairs[i:i+2]
        row_str = "  ·  ".join([f"<b>{p['name']}</b>" for p in pair_row])
        rows.append(f"  🔹 {row_str}")
        
    pair_grid = "\n".join(rows)
    sess_name = session_label(sess).upper()
    tip = tips.get(sess, "Trade the plan. Stay disciplined.")

    return (
        f"📋 <b>VEDA TRADER v5 — WATCHLIST</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌍 <b>{sess_name}</b>\n"
        f"\n"
        f"📡 <b>SCANNING {len(pairs)} PAIRS:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{pair_grid}\n"
        f"\n"
        f"💡 <i>{tip}</i>\n"
        f"⚠️ <b>v5 filters active:</b> ATR + ADX + 15M Trend\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━"
    )

def fmt_session_report(signals: list, date_str: str) -> str:
    if not signals:
        return "📊 <b>SESSION REPORT</b>\n━━━━━━━━━━━━━━━━━━━━\nNo signals recorded this session."
        
    wins = sum(1 for s in signals if s.get('result') == 'WIN')
    losses = sum(1 for s in signals if s.get('result') == 'LOSS')
    pending = sum(1 for s in signals if s.get('result') is None)
    
    lines = []
    for s in signals:
        res = s.get('result')
        tag = "✅ WIN" if res == "WIN" else "❌ LOSS" if res == "LOSS" else "⏳ PENDING"
        lines.append(f"<code>#{s.get('no','?'):02d}</code>  {s['pair']}  →  <b>{tag}</b>")
        
    total = wins + losses
    wr = f"{(wins/total*100):.1f}%" if total > 0 else "0.0%"
    target_hit = "🎯 <b>TARGET REACHED</b>" if total > 0 and wins/total >= 0.62 else "📉 <b>SESSION IN PROGRESS</b>"

    return (
        f"📊 <b>SESSION RESULTS — {date_str}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        + "\n".join(lines) +
        f"\n\n━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>{wins} WINS</b>   ❌ <b>{losses} LOSSES</b>" + (f"   ⏳ <b>{pending} PENDING</b>" if pending else "") +
        f"\n\n🏆 Win Rate: <b>{wr}</b>\n{target_hit}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━"
    )

def fmt_result_msg(s: dict):
    won = s["result"] == "WIN"
    sign = "+" if (s["exit_price"] - s["price"]) >= 0 else ""
    pct = abs(s["exit_price"] - s["price"]) / s["price"] * 100
    label = "GAIN ✅" if won else "LOSS ❌"
    
    return (
        f"⚡ <b>✨ TRADE RESULT #{s['no']} ✨</b> ⚡\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"<b>{label}</b>  ·  {s['pair']}\n"
        f"<code>{s['price']:.5f} → {s['exit_price']:.5f}  ({sign}{pct:.2f}%)</code>"
    )

def answer_callback_query(callback_query_id: str, text: str = None):
    """Answer a callback query to dismiss loading state"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass

def handle_telegram_command(update: dict, send_telegram_func, PREMIUM_ENABLED: bool):
    try:
        admin_ids = {x.strip() for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip()}

        # Handle Callback Queries (Button Clicks)
        if "callback_query" in update:
            cb = update["callback_query"]
            callback_id = cb["id"]
            msg_ctx = cb.get("message", {})
            chat_id = str(msg_ctx.get("chat", {}).get("id") or cb.get("from", {}).get("id", ""))
            user_id = str(cb.get("from", {}).get("id", ""))
            data = cb["data"]
            
            if data == "view_premium":
                markup = {
                    "inline_keyboard": [
                        [{"text": "📊 Stocks", "callback_data": "cat_stocks"}, {"text": "₿ Crypto", "callback_data": "cat_crypto"}],
                        [{"text": "🏛 Indices", "callback_data": "cat_indices"}, {"text": "🥇 Gold Assets", "callback_data": "cat_commodities"}],
                        [{"text": "🏆 Elite Gold Signals", "callback_data": "cat_gold"}],
                        [{"text": "⬅️ Back", "callback_data": "back_to_start"}]
                    ]
                }
                msg = "💎 <b>PREMIUM HUB</b>\n\nSelect a category to view the latest high-accuracy signals:"
                send_telegram_func(msg, chat_id=chat_id, reply_markup=markup)
                answer_callback_query(callback_id)
            
            elif data.startswith("cat_"):
                category = data.replace("cat_", "")
                from .premium import is_gold_user
                if is_gold_user(user_id):
                    from .database import get_recent_premium_signals
                    sigs = get_recent_premium_signals(category=category, limit=3)
                    cat_name = category.upper()
                    if not sigs:
                        send_telegram_func(f"💎 <b>{cat_name} HUB</b>\n\nNo active signals in this category at the moment. Scanning markets...", chat_id=chat_id)
                    else:
                        msg = f"💎 <b>LATEST {cat_name} SIGNALS</b>\n━━━━━━━━━━━━━━━━━━━━\n"
                        for s in sigs:
                            msg += f"\n✨ <b>{s['pair']}</b> ({s['type']})\nScore: <b>{s['score']}/100</b>\nPrice: <code>{s['price']:.5f}</code>\n"
                        send_telegram_func(msg, chat_id=chat_id)
                else:
                    from .database import get_recent_premium_signals
                    sigs = get_recent_premium_signals(category=category, limit=2)
                    cat_name = category.upper()
                    if sigs:
                        msg = f"🔒 <b>{cat_name} GOLD PREVIEW</b>\n━━━━━━━━━━━━━━━━━━━━\n"
                        for s in sigs:
                            msg += f"\n• <b>{s['pair']}</b> ({s['type']}) — Score <b>{s['score']}/100</b>"
                        msg += "\n\n👑 Full access requires GOLD membership.\nUse /start and tap <b>Membership Info</b>."
                    else:
                        msg = f"🔒 <b>{cat_name} ACCESS</b>\n\nNo preview signals right now.\nThis category is reserved for <b>GOLD Members</b>."
                    send_telegram_func(msg, chat_id=chat_id)
                answer_callback_query(callback_id)
            
            elif data == "gold_info":
                msg = (
                    "👑 <b>GOLD MEMBERSHIP INFO</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "🎯 <b>Premium Features:</b>\n"
                    "• Access to Stocks, Indices & Crypto signals\n"
                    "• Higher accuracy signals (80-95% score)\n"
                    "• Real-time market scanning\n"
                    "• Exclusive gold-tier signals\n\n"
                    "💰 <b>Pricing:</b> Contact admin for details\n\n"
                    "📞 Use /start to begin upgrade process"
                )
                send_telegram_func(msg, chat_id=chat_id)
                answer_callback_query(callback_id)

            elif data == "back_to_start":
                # Trigger /start logic
                return handle_telegram_command({"message": {"chat": {"id": chat_id}, "from": {"id": user_id}, "text": "/start"}}, send_telegram_func, PREMIUM_ENABLED)

            return

        message = update.get("message", {})
        chat_id = str(message.get("chat", {}).get("id"))
        user_id = str(message.get("from", {}).get("id"))
        username = message.get("from", {}).get("username", "Unknown")
        text = message.get("text", "")
        if not chat_id:
            return

        if text == "/start":
            markup = {
                "inline_keyboard": [
                    [{"text": "📊 Free Signals Channel", "url": PUBLIC_CHANNEL_URL}],
                    [{"text": "💎 View Premium Assets", "callback_data": "view_premium"}],
                    [{"text": "👑 Membership Info", "callback_data": "gold_info"}]
                ]
            }
            welcome_msg = (
                f"🎯 <b>VEDA TRADER BOT v5</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"\n"
                f"✅ <b>Active & Scanning Markets</b>\n"
                f"\n"
                f"Use the buttons below to access our automated trading hub."
            )
            send_telegram_func(welcome_msg, chat_id=chat_id, reply_markup=markup)

        elif text == "/status":
            markup = {"inline_keyboard": [[{"text": "🔄 Refresh", "callback_data": "view_premium"}]]}
            from .premium import is_gold_user
            has_gold = is_gold_user(user_id)
            status_msg = (
                f"📊 <b>BOT STATUS</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"\n"
                f"✅ <b>ONLINE & ACTIVE</b>\n"
                f"\n"
                f"🌍 Session: {session_label(current_session())}\n"
                f"👑 Your Status: {'💎 GOLD MEMBER' if has_gold else '🆓 FREE TIER'}\n"
            )
            send_telegram_func(status_msg, chat_id=chat_id, reply_markup=markup)

        elif text == "/pairs":
            from .config import ALL_PAIRS
            pairs_list = [f"• <b>{p['name']}</b> ({p['category'].title()})" for p in ALL_PAIRS]
            pairs_msg = (
                f"📋 <b>MONITORED PAIRS</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"\n" + "\n".join(pairs_list) +
                f"\n\n<b>Total: {len(ALL_PAIRS)} pairs</b>"
            )
            send_telegram_func(pairs_msg, chat_id=chat_id)

        elif text == "/sessions":
            sessions_msg = (
                f"🕐 <b>TRADING SESSIONS</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"\n"
                f"🌏 <b>Asian Session:</b> 00:00 - 09:00 UTC\n"
                f"🇬🇧 <b>London Session:</b> 07:00 - 16:00 UTC\n"
                f"🔥 <b>London/NY Overlap:</b> 12:00 - 16:00 UTC\n"
                f"🇺🇸 <b>New York Session:</b> 16:00 - 21:00 UTC\n"
                f"\n"
                f"💡 <b>Current:</b> {session_label(current_session())}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            send_telegram_func(sessions_msg, chat_id=chat_id)

        elif text == "/premium":
            markup = {
                "inline_keyboard": [
                    [{"text": "📊 Stocks", "callback_data": "cat_stocks"}, {"text": "₿ Crypto", "callback_data": "cat_crypto"}],
                    [{"text": "🏛 Indices", "callback_data": "cat_indices"}, {"text": "🥇 Gold Assets", "callback_data": "cat_commodities"}],
                    [{"text": "🏆 Elite Gold Signals", "callback_data": "cat_gold"}],
                    [{"text": "⬅️ Back", "callback_data": "back_to_start"}]
                ]
            }
            msg = "💎 <b>PREMIUM HUB</b>\n\nSelect a category to view the latest high-accuracy signals:"
            send_telegram_func(msg, chat_id=chat_id, reply_markup=markup)
        elif text == "/help":
            send_telegram_func(
                "🧭 <b>AVAILABLE COMMANDS</b>\n\n"
                "/start - Open main menu\n"
                "/status - Bot status\n"
                "/pairs - Tracked assets\n"
                "/sessions - Trading sessions\n"
                "/premium - Premium hub\n"
                "/test - Send channel test\n"
                "/myid - Show your Telegram ID",
                chat_id=chat_id
            )
        elif text == "/myid":
            send_telegram_func(f"🆔 Your user ID: <code>{user_id}</code>", chat_id=chat_id)

        elif text == "/test":
            # Send test message to channel
            test_msg = "🧪 <b>TEST MESSAGE</b>\n\nBot is working! Sent at " + datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
            success = send_telegram_func(test_msg)
            if success:
                send_telegram_func("✅ Test message sent to channel!", chat_id=chat_id)
            else:
                send_telegram_func("❌ Failed to send test message. Check CHAT_ID and bot permissions.", chat_id=chat_id)

        elif text.startswith("/addgold "):
            if admin_ids and user_id not in admin_ids:
                send_telegram_func("🚫 You are not allowed to use /addgold.", chat_id=chat_id)
                return
            parts = text.split()
            if len(parts) >= 3:
                target_id, days = parts[1], parts[2]
                from .premium import add_gold_user
                if add_gold_user(target_id, days, username):
                    send_telegram_func(f"✅ User {target_id} updated to GOLD for {days} days.", chat_id=chat_id)
                else:
                    send_telegram_func("❌ Could not update GOLD membership.", chat_id=chat_id)
            else:
                send_telegram_func("Usage: /addgold <user_id> <days>", chat_id=chat_id)

    except Exception as e:
        print(f"[COMMAND HANDLER] {e}")

def fmt_premium_watchlist(sess: str, pairs: list) -> str:
    """Watchlist formatted specifically for premium members."""
    # Filter only premium pairs for this list
    premium_pairs = [p for p in pairs if p.get("tier") == "premium"]
    if not premium_pairs:
        return ""
    
    rows = []
    for i in range(0, len(premium_pairs), 2):
        pair_row = premium_pairs[i:i+2]
        row_str = "  ·  ".join([f"<b>{p['name']}</b>" for p in pair_row])
        rows.append(f"  💎 {row_str}")
        
    pair_grid = "\n".join(rows)
    sess_name = session_label(sess).upper()

    return (
        f"👑 <b>VEDA TRADER — PREMIUM WATCHLIST</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🌍 <b>{sess_name}</b>\n"
        f"\n"
        f"📡 <b>MONITORING {len(premium_pairs)} ELITE ASSETS:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{pair_grid}\n"
        f"\n"
        f"🚀 <i>Scanning for high-accuracy institutional setups.</i>\n"
        f"⚠️ <b>v5 filters:</b> ATR + ADX + 1H Trend Confirmation\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

def setup_bot_profile():
    # Update bot commands and description
    commands = [
        {"command": "start", "description": "Get bot info and welcome message"},
        {"command": "status", "description": "Check bot health and current session"},
        {"command": "pairs", "description": "List all monitored currency pairs"},
        {"command": "sessions", "description": "View the trading session schedule"},
        {"command": "premium", "description": "Access premium features and signals"},
        {"command": "test", "description": "Send test message to channel"},
        {"command": "help", "description": "Show available commands"},
        {"command": "myid", "description": "Show your Telegram user ID"},
    ]
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setMyCommands"
    requests.post(url, json={"commands": commands})
    print("[BOT] Commands updated on Telegram")
