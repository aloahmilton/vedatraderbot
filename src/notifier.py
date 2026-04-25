import os
from datetime import datetime, timezone, timedelta

import requests

from .config import (
    ALL_PAIRS,
    CHAT_ID,
    EXPIRY_MINUTES,
    PUBLIC_CHANNEL_URL,
    TELEGRAM_TOKEN,
    current_session,
    session_label,
)


def send_telegram(msg: str, pin: bool = False, chat_id: str = None, **kwargs) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    target_chat = chat_id if chat_id is not None else CHAT_ID
    payload = {
        "chat_id": target_chat,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
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
                    timeout=10,
                )
        return True
    except Exception as e:
        print(f"  [Telegram Error] {e}")
        return False


def delete_telegram_message(message_id: int, chat_id: str = None) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteMessage"
    target_chat = chat_id if chat_id is not None else CHAT_ID
    try:
        r = requests.post(url, json={"chat_id": target_chat, "message_id": message_id}, timeout=5)
        return r.json().get("ok", False)
    except Exception:
        return False


def send_voice(voice_file_path: str, caption: str = None, chat_id: str = None) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendVoice"
    target_chat = chat_id if chat_id is not None else CHAT_ID
    try:
        with open(voice_file_path, "rb") as voice_file:
            files = {"voice": voice_file}
            data = {"chat_id": target_chat}
            if caption:
                data["caption"] = caption
                data["parse_mode"] = "HTML"
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
    empty = 5 - filled
    return "[" + ("#" * filled) + ("-" * empty) + f"] {score}/100"


def _quality_label(score: int) -> str:
    if score >= 85:
        return "A+ setup"
    if score >= 75:
        return "A setup"
    if score >= 65:
        return "B setup"
    return "Qualified"


def _expiry_slots():
    now = datetime.now(timezone.utc)
    base = now.replace(second=0, microsecond=0)
    return (
        now.strftime("%H:%M"),
        (base + timedelta(minutes=EXPIRY_MINUTES)).strftime("%H:%M"),
        (base + timedelta(minutes=EXPIRY_MINUTES * 2)).strftime("%H:%M"),
        (base + timedelta(minutes=EXPIRY_MINUTES * 3)).strftime("%H:%M"),
    )


def fmt_signal(sig: dict, sig_no: int = 0) -> str:
    is_buy = sig["type"] == "BUY"
    action = "BUY / CALL" if is_buy else "SELL / PUT"
    bias = "BUY" if is_buy else "SELL"
    sess_lbl = session_label(current_session()).split(" ", 1)[-1]
    now_str, t1, t2, t3 = _expiry_slots()
    score = sig.get("score", 0)
    header_no = f"#{sig_no:02d}" if sig_no else "##"

    return (
        f"<b>FOREX SCALP SIGNAL {header_no}</b>\n"
        f"<b>{sig['pair']}</b> | {sess_lbl}\n\n"
        f"<b>Bias:</b> {bias}\n"
        f"<b>Action:</b> {action}\n"
        f"<b>Entry:</b> <code>{sig['price']:.5f}</code>\n"
        f"<b>Time:</b> <code>{now_str} UTC</code>\n"
        f"<b>Expiry:</b> <code>{t1}</code> ({EXPIRY_MINUTES}m)\n"
        f"<b>Gale 1:</b> <code>{t2}</code>\n"
        f"<b>Gale 2:</b> <code>{t3}</code>\n\n"
        f"<b>Quality:</b> {_quality_label(score)} | <code>{score}/100</code>\n"
        f"<b>Trend:</b> {sig['trend']} | <b>ADX:</b> <code>{sig['adx']}</code>\n"
        f"<b>RSI:</b> <code>{sig['rsi']}</code> | <b>ATR:</b> <code>{sig['atr_bps']} bps</code>\n\n"
        f"<i>Free channel is forex only. Premium covers indices, stocks, commodities and crypto.</i>"
    )


def fmt_gold_signal(sig: dict, sig_no: int = 0):
    is_buy = sig["type"] == "BUY"
    action = "BUY" if is_buy else "SELL"
    now_str, t1, _, _ = _expiry_slots()
    header = "ELITE GOLD" if sig.get("is_gold") else "PREMIUM"
    category = sig.get("category", "asset").upper()

    return (
        f"<b>{header} SCALP SIGNAL</b>\n"
        f"<b>{sig['pair']}</b> | {category}\n\n"
        f"<b>Action:</b> {action}\n"
        f"<b>Entry:</b> <code>{sig['price']:.5f}</code>\n"
        f"<b>Time:</b> <code>{now_str} UTC</code>\n"
        f"<b>Expiry:</b> <code>{t1}</code> ({EXPIRY_MINUTES}m)\n\n"
        f"<b>Score:</b> <code>{sig['score']}/100</code>\n"
        f"<b>Trend:</b> {sig['trend']} | <b>ADX:</b> <code>{sig['adx']}</code>\n"
        f"<b>RSI:</b> <code>{sig['rsi']}</code> | <b>EMA Gap:</b> <code>{sig.get('ema_gap_bps', 0)} bps</code>\n"
        f"<b>Entry Stretch:</b> <code>{sig.get('entry_gap_bps', 0)} bps</code>\n"
        f"<b>Wick Risk:</b> <code>{sig.get('wick_ratio', 0)}</code>"
    )


def fmt_session_announcement(sess: str) -> str:
    session_meta = {
        "asian": ("ASIAN SESSION", "Asia"),
        "london": ("LONDON SESSION", "London"),
        "overlap": ("LONDON x NY OVERLAP", "Overlap"),
        "newyork": ("NEW YORK SESSION", "New York"),
    }
    label, short_name = session_meta.get(sess, ("SESSION", "Session"))
    return (
        f"<b>{label} OPEN</b>\n\n"
        f"{short_name} scalp filters are active: trend alignment, momentum confirmation, candle quality and structure checks.\n"
        f"Expect fewer signals, cleaner entries."
    )


def fmt_session_close(sess: str) -> str:
    session_meta = {
        "asian": "ASIAN SESSION",
        "london": "LONDON SESSION",
        "overlap": "LONDON x NY OVERLAP",
        "newyork": "NEW YORK SESSION",
    }
    label = session_meta.get(sess, "SESSION")
    return f"<b>{label} CLOSED</b>\n\nSession wrapped. We reset and wait for the next clean setup."


def fmt_weekend_close() -> str:
    return (
        "<b>WEEKEND MODE</b>\n\n"
        "Forex markets are closed for the week.\n"
        "Scanning pauses until Sunday 21:00 UTC."
    )


def fmt_weekend_open() -> str:
    return (
        "<b>MARKETS REOPENING</b>\n\n"
        "The Asian session is warming up and scanning resumes now."
    )


def fmt_watchlist(sess: str, pairs: list) -> str:
    tips = {
        "asian": "JPY, AUD and NZD pairs usually lead this session.",
        "london": "EUR and GBP are the main focus early in London.",
        "overlap": "Peak liquidity. Strongest scalp conditions usually show here.",
        "newyork": "USD pairs and US premium assets are the focus.",
    }
    pair_names = ", ".join(f"<b>{p['name']}</b>" for p in pairs) if pairs else "<i>No assets configured</i>"
    sess_name = session_label(sess).upper()
    tip = tips.get(sess, "Trade the plan. Stay disciplined.")
    return (
        f"<b>{sess_name} WATCHLIST</b>\n\n"
        f"{pair_names}\n\n"
        f"<i>{tip}</i>"
    )


def fmt_session_report(signals: list, date_str: str) -> str:
    if not signals:
        return f"<b>SESSION REPORT - {date_str}</b>\n\nNo signals recorded this session."

    wins = sum(1 for s in signals if s.get("result") == "WIN")
    losses = sum(1 for s in signals if s.get("result") == "LOSS")
    pending = sum(1 for s in signals if s.get("result") is None)
    total = wins + losses
    wr = f"{(wins / total * 100):.1f}%" if total else "0.0%"
    lines = []
    for s in signals:
        res = s.get("result")
        tag = "WIN" if res == "WIN" else "LOSS" if res == "LOSS" else "PENDING"
        lines.append(f"<code>#{s.get('no', '?'):02d}</code> {s['pair']} -> <b>{tag}</b>")
    summary = f"<b>Wins:</b> {wins} | <b>Losses:</b> {losses}"
    if pending:
        summary += f" | <b>Pending:</b> {pending}"
    return (
        f"<b>SESSION REPORT - {date_str}</b>\n\n"
        + "\n".join(lines)
        + f"\n\n{summary}\n<b>Win Rate:</b> {wr}"
    )


def fmt_result_msg(s: dict):
    won = s["result"] == "WIN"
    sign = "+" if (s["exit_price"] - s["price"]) >= 0 else ""
    pct = abs(s["exit_price"] - s["price"]) / s["price"] * 100
    label = "GAIN" if won else "LOSS"
    return (
        f"<b>TRADE RESULT #{s['no']}</b>\n"
        f"<b>{label}</b> | {s['pair']}\n"
        f"<code>{s['price']:.5f} -> {s['exit_price']:.5f} ({sign}{pct:.2f}%)</code>"
    )


def answer_callback_query(callback_query_id: str, text: str = None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass


def handle_telegram_command(update: dict, send_telegram_func, premium_enabled: bool):
    try:
        admin_ids = {x.strip() for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip()}

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
                        [{"text": "Stocks", "callback_data": "cat_stocks"}, {"text": "Crypto", "callback_data": "cat_crypto"}],
                        [{"text": "Indices", "callback_data": "cat_indices"}, {"text": "Commodities", "callback_data": "cat_commodities"}],
                        [{"text": "Elite Gold", "callback_data": "cat_gold"}],
                        [{"text": "Back", "callback_data": "back_to_start"}],
                    ]
                }
                send_telegram_func(
                    "<b>PREMIUM HUB</b>\n\nChoose an asset class to view recent premium setups.",
                    chat_id=chat_id,
                    reply_markup=markup,
                )
                answer_callback_query(callback_id)
                return

            if data.startswith("cat_"):
                category = data.replace("cat_", "")
                from .database import get_recent_premium_signals
                from .premium import is_gold_user

                cat_name = category.upper()
                limit = 3 if is_gold_user(user_id) else 2
                sigs = get_recent_premium_signals(category=category, limit=limit)

                if is_gold_user(user_id):
                    if not sigs:
                        msg = f"<b>{cat_name} HUB</b>\n\nNo live setups right now. The scanner is still running."
                    else:
                        rows = [
                            f"<b>{s['pair']}</b> | {s['type']} | <code>{s['score']}/100</code> | <code>{s['price']:.5f}</code>"
                            for s in sigs
                        ]
                        msg = f"<b>LATEST {cat_name} SETUPS</b>\n\n" + "\n".join(rows)
                else:
                    if sigs:
                        rows = [f"<b>{s['pair']}</b> | {s['type']} | <code>{s['score']}/100</code>" for s in sigs]
                        msg = (
                            f"<b>{cat_name} PREVIEW</b>\n\n"
                            + "\n".join(rows)
                            + "\n\nFull access is available to premium members."
                        )
                    else:
                        msg = f"<b>{cat_name} ACCESS</b>\n\nNo preview setups right now."
                send_telegram_func(msg, chat_id=chat_id)
                answer_callback_query(callback_id)
                return

            if data == "gold_info":
                send_telegram_func(
                    "<b>PREMIUM MEMBERSHIP</b>\n\n"
                    "Premium members receive indices, stocks, commodities and crypto scalp setups.\n"
                    "The free channel remains forex only.",
                    chat_id=chat_id,
                )
                answer_callback_query(callback_id)
                return

            if data == "back_to_start":
                handle_telegram_command(
                    {"message": {"chat": {"id": chat_id}, "from": {"id": user_id}, "text": "/start"}},
                    send_telegram_func,
                    premium_enabled,
                )
                answer_callback_query(callback_id)
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
                    [{"text": "Free Forex Channel", "url": PUBLIC_CHANNEL_URL}],
                    [{"text": "View Premium Assets", "callback_data": "view_premium"}],
                    [{"text": "Membership Info", "callback_data": "gold_info"}],
                ]
            }
            send_telegram_func(
                "<b>VEDA TRADER BOT</b>\n\n"
                "Free channel: forex scalp signals.\n"
                "Premium: indices, stocks, commodities and crypto.",
                chat_id=chat_id,
                reply_markup=markup,
            )

        elif text == "/status":
            from .premium import is_gold_user

            tier = "PREMIUM" if is_gold_user(user_id) else "FREE"
            send_telegram_func(
                "<b>BOT STATUS</b>\n\n"
                "Scanner: ONLINE\n"
                f"Session: {session_label(current_session())}\n"
                f"Your tier: {tier}",
                chat_id=chat_id,
            )

        elif text == "/pairs":
            pairs_list = [f"- <b>{p['name']}</b> ({p['category']})" for p in ALL_PAIRS]
            send_telegram_func(
                "<b>MONITORED ASSETS</b>\n\n" + "\n".join(pairs_list) + f"\n\nTotal: <b>{len(ALL_PAIRS)}</b>",
                chat_id=chat_id,
            )

        elif text == "/sessions":
            send_telegram_func(
                "<b>TRADING SESSIONS</b>\n\n"
                "Asian: 00:00-09:00 UTC\n"
                "London: 07:00-16:00 UTC\n"
                "London/NY overlap: 12:00-16:00 UTC\n"
                "New York: 16:00-21:00 UTC\n\n"
                f"Current: {session_label(current_session())}",
                chat_id=chat_id,
            )

        elif text == "/premium":
            markup = {
                "inline_keyboard": [
                    [{"text": "Stocks", "callback_data": "cat_stocks"}, {"text": "Crypto", "callback_data": "cat_crypto"}],
                    [{"text": "Indices", "callback_data": "cat_indices"}, {"text": "Commodities", "callback_data": "cat_commodities"}],
                    [{"text": "Elite Gold", "callback_data": "cat_gold"}],
                    [{"text": "Back", "callback_data": "back_to_start"}],
                ]
            }
            send_telegram_func(
                "<b>PREMIUM HUB</b>\n\nChoose an asset class to view recent premium setups.",
                chat_id=chat_id,
                reply_markup=markup,
            )

        elif text == "/help":
            send_telegram_func(
                "<b>AVAILABLE COMMANDS</b>\n\n"
                "/start\n/status\n/pairs\n/sessions\n/premium\n/test\n/myid",
                chat_id=chat_id,
            )

        elif text == "/myid":
            send_telegram_func(f"Your user ID: <code>{user_id}</code>", chat_id=chat_id)

        elif text == "/test":
            test_msg = "<b>TEST MESSAGE</b>\n\nBot is running at " + datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
            success = send_telegram_func(test_msg)
            if success:
                send_telegram_func("Test message sent to the free channel.", chat_id=chat_id)
            else:
                send_telegram_func("Failed to send the test message. Check channel ID and bot permissions.", chat_id=chat_id)

        elif text.startswith("/addgold "):
            if admin_ids and user_id not in admin_ids:
                send_telegram_func("You are not allowed to use /addgold.", chat_id=chat_id)
                return
            parts = text.split()
            if len(parts) >= 3:
                target_id, days = parts[1], parts[2]
                from .premium import add_gold_user

                if add_gold_user(target_id, days, username):
                    send_telegram_func(f"User {target_id} upgraded to premium for {days} days.", chat_id=chat_id)
                else:
                    send_telegram_func("Could not update premium membership.", chat_id=chat_id)
            else:
                send_telegram_func("Usage: /addgold <user_id> <days>", chat_id=chat_id)

        elif text.startswith("/clearchannel"):
            if admin_ids and user_id not in admin_ids:
                send_telegram_func("Admin only.", chat_id=chat_id)
                return

            parts = text.split()
            count = 100
            if len(parts) > 1:
                try:
                    count = int(parts[1])
                except Exception:
                    pass

            send_telegram_func(f"Cleaning the last {count} messages from the current chat.", chat_id=chat_id)
            curr_id = message.get("message_id")
            if not curr_id:
                send_telegram_func("Could not determine the current message ID.", chat_id=chat_id)
                return

            deleted = 0
            for i in range(count):
                if delete_telegram_message(curr_id - i):
                    deleted += 1
            send_telegram_func(f"Cleanup finished. Deleted about {deleted} messages.", chat_id=chat_id)

    except Exception as e:
        print(f"[COMMAND HANDLER] {e}")


def setup_bot_profile():
    commands = [
        {"command": "start", "description": "Open the main menu"},
        {"command": "status", "description": "Check bot and session status"},
        {"command": "pairs", "description": "List monitored assets"},
        {"command": "sessions", "description": "View session schedule"},
        {"command": "premium", "description": "Open premium assets hub"},
        {"command": "test", "description": "Send a test message"},
        {"command": "help", "description": "Show available commands"},
        {"command": "myid", "description": "Show your Telegram user ID"},
    ]
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setMyCommands"
    try:
        requests.post(url, json={"commands": commands}, timeout=10)
        print("[BOT] Commands updated on Telegram")
    except Exception as e:
        print(f"[BOT] Command setup failed: {e}")
