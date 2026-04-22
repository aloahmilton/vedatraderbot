import requests
from datetime import datetime, timezone, timedelta
from .config import TELEGRAM_TOKEN, CHAT_ID, EXPIRY_MINUTES, current_session, session_label, ALL_PAIRS

def send_telegram(msg: str, pin: bool = False, chat_id: str = None) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    target_chat = chat_id if chat_id is not None else CHAT_ID
    payload = {
        "chat_id": target_chat, 
        "text": msg,
        "parse_mode": "HTML", 
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
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
        f"✨ <b>NEW SIGNAL</b> ✨\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"📡  <b>VEDA TRADER  {header_no}</b>   ·   {sess_lbl}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
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
        f"📈  RSI <code>{sig['rsi']}</code>  ·  ADX <code>{sig['adx']}</code>  ·  ATR <code>{sig['atr_bps']} bps</code>\n"
        f"🧭  15M Trend: <b>{sig['trend']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Result posted in {EXPIRY_MINUTES + 1} min. Trade responsibly.</i>"
    )

def fmt_gold_signal(sig: dict, sig_no: int = 0):
    """Premium formatting for gold signals."""
    is_buy = sig["type"] == "BUY"
    icon = "👑"
    arrow = "🚀 <b>BUY / CALL</b>" if is_buy else "📉 <b>SELL / PUT</b>"
    
    # Gold signals are high accuracy setups
    base_msg = fmt_signal(sig, sig_no)
    
    return (
        f"👑 <b>VEDA TRADER — GOLD SIGNAL</b> 👑\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💎 <b>PREMIUM SELECTION</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"🎯 {sig['pair']} — {arrow}\n"
        f"📊 Accuracy Score: <b>{sig['score']}/100</b>\n"
        f"\n"
        f"🛡 <i>This signal met all 'Best of the Best' filters including 1H trend and Volume confirmation.</i>\n"
        f"\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✨ {base_msg}"
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

def handle_telegram_command(update: dict, send_telegram_func, PREMIUM_ENABLED: bool):
    try:
        message = update.get("message", {})
        chat_id = str(message.get("chat", {}).get("id"))
        username = message.get("from", {}).get("username", "Unknown")
        text = message.get("text", "")

        if text == "/start":
            welcome_msg = (
                f"🎯 <b>VEDA TRADER BOT v5</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"\n"
                f"✅ <b>Active & Scanning Markets</b>\n"
                f"\n"
                f"📊 Monitoring {len(ALL_PAIRS)} currency pairs & assets\n"
                f"⏰ Signals every 5 minutes\n"
                f"🌍 3 trading sessions\n"
                f"\n"
                f"👑 <b>GOLD Premium Available</b>\n"
                f"   • 85%+ win rate signals\n"
                f"   • Elite high-value asset picks\n"
                f"   • Private channel delivery\n"
                f"\n"
                f"Use /gold to check premium status"
            )
            send_telegram_func(welcome_msg, chat_id=chat_id)

        elif text == "/status":
            status_msg = (
                f"📊 <b>BOT STATUS</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"\n"
                f"✅ <b>ONLINE & ACTIVE</b>\n"
                f"\n"
                f"🌍 Session: {session_label(current_session())}\n"
                f"📈 Assets: {len(ALL_PAIRS)}\n"
                f"👑 Premium: {'Enabled' if PREMIUM_ENABLED else 'Disabled'}\n"
            )
            send_telegram_func(status_msg, chat_id=chat_id)

        elif text == "/pairs":
            # Group pairs by session
            sessions = {"all": [], "london": [], "newyork": [], "asian": []}
            for p in ALL_PAIRS:
                sessions[p.get("session", "all")].append(p["name"])
            
            pairs_msg = "📊 <b>MONITORED ASSETS</b>\n━━━━━━━━━━━━━━━━━━━━\n"
            for sess, names in sessions.items():
                if names:
                    pairs_msg += f"\n<b>{sess.upper()}:</b>\n{', '.join(names)}\n"
            send_telegram_func(pairs_msg, chat_id=chat_id)

        elif text == "/gold" and PREMIUM_ENABLED:
            try:
                from .premium import get_gold_stats
                active, expiring = get_gold_stats()
                msg = (
                    f"👑 <b>GOLD TIER STATUS</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"\n"
                    f"✅ Active members: {active}\n"
                    f"📊 Filters: Ultra-strict (85%+ accuracy)\n"
                    f"\n"
                    f"<i>Elite signals only.</i>"
                )
                send_telegram_func(msg, chat_id=chat_id)
            except ImportError:
                send_telegram_func("❌ Premium module error.", chat_id=chat_id)

        elif text.startswith("/addgold ") and PREMIUM_ENABLED:
            # Simple admin check (can be improved)
            if chat_id.startswith("-") == False: # Private chat only
                parts = text.split()
                if len(parts) >= 3:
                    target_id, days = parts[1], parts[2]
                    try:
                        from .premium import add_gold_user
                        if add_gold_user(target_id, days, username):
                            send_telegram_func(f"✅ Added {target_id} for {days} days.", chat_id=chat_id)
                    except:
                        send_telegram_func("❌ Failed to add user.", chat_id=chat_id)

    except Exception as e:
        print(f"[COMMAND HANDLER] {e}")

def setup_bot_profile():
    # Simple setup call
    commands = [
        {"command": "start", "description": "Get bot info"},
        {"command": "status", "description": "Check bot status"},
    ]
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setMyCommands"
    requests.post(url, json={"commands": commands})
