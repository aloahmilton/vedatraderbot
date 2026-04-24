"""
╔══════════════════════════════════════════════════════════╗
║           VEDA TRADER — online🟢 |v5                    ║
╚══════════════════════════════════════════════════════════╝

✅ TRADES ONLY DURING 4 MAIN SESSIONS
✅ SKIPS WEEKENDS COMPLETELY  
✅ 30MIN PRE-SESSION NOTIFICATIONS
✅ SESSION OPEN/CLOSE ALERTS
"""

import os, time, hmac, hashlib, threading, schedule, requests, logging
from datetime import datetime, timezone, timedelta
from functools import wraps
from dotenv import load_dotenv

from flask import (Flask, render_template, request, jsonify,
                   redirect, url_for, flash, session as flask_session)
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId

from src.config import (
    pairs_for_session, current_session, session_label,
    TELEGRAM_TOKEN, SECRET_KEY, MONGO_URI,
    ALL_PAIRS, validate_runtime_config
)
from src.engine import analyze_pair, evaluate_pending_signals
from src.notifier import (
    send_telegram, fmt_signal, fmt_gold_signal,
    fmt_session_announcement, fmt_session_close, fmt_watchlist,
    fmt_session_report, fmt_weekend_close, fmt_weekend_open,
    handle_telegram_command, setup_bot_profile
)
from src.database import (
    get_db, init_db, save_signal_to_db, record_signal_state,
    upsert_bot_status, log_scan_error
)

load_dotenv()

# ── Premium ───────────────────────────────────────────────
try:
    from src import premium
    PREMIUM_CHANNEL_ID = premium.PREMIUM_CHANNEL_ID
    PREMIUM_ENABLED    = premium.PREMIUM_ENABLED
except ImportError:
    PREMIUM_CHANNEL_ID = None
    PREMIUM_ENABLED    = False

# ── Database ──────────────────────────────────────────────
db = get_db()
if db is None:
    init_db(); db = get_db()
users_collection   = db["users"]   if db is not None else None
signals_collection = db["signals"] if db is not None else None

# ── Config ────────────────────────────────────────────────
AFFILIATE_LINK = os.getenv("AFFILIATE_LINK", "#")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "VedaGold2026!")

# ── Bot state ─────────────────────────────────────────────
session_signals:      list = []
last_update_id:       int  = 0
notified_sessions:    set  = set()  # Track which sessions we've notified

# ══════════════════════════════════════════════════════════
#  TRADING SESSIONS (UTC) — ONLY 4 SESSIONS
# ══════════════════════════════════════════════════════════
TRADING_SESSIONS = {
    "asian":    {"start": 0,  "end": 9,  "label": "🌏 Asian Session"},
    "london":   {"start": 8,  "end": 17, "label": "🇬🇧 London Session"},
    "newyork":  {"start": 13, "end": 20, "label": "🇺🇸 New York Session"},
}

def is_weekend():
    """Check if Saturday (5) or Sunday (6) — NO TRADING"""
    now = datetime.now(timezone.utc)
    return now.weekday() >= 5

def get_active_session():
    """Return current active session or None if outside trading hours"""
    if is_weekend():
        return None
    
    now = datetime.now(timezone.utc)
    hour = now.hour
    
    for sess_name, sess_info in TRADING_SESSIONS.items():
        if sess_info["start"] <= hour < sess_info["end"]:
            return sess_name
    return None

def is_trading_hours():
    """Return True if we're currently in trading hours"""
    return get_active_session() is not None

def time_to_session_open(session_name):
    """Return minutes until session opens, or None if already open"""
    now = datetime.now(timezone.utc)
    hour = now.hour
    minute = now.minute
    
    if session_name not in TRADING_SESSIONS:
        return None
    
    start_hour = TRADING_SESSIONS[session_name]["start"]
    end_hour = TRADING_SESSIONS[session_name]["end"]
    
    # If session is currently open
    if start_hour <= hour < end_hour:
        return None
    
    # Calculate minutes until opening
    if hour < start_hour:
        return (start_hour - hour) * 60 - minute
    else:
        # Next day session
        return ((24 - hour) + start_hour) * 60 - minute

# ══════════════════════════════════════════════════════════
#  FLASK APP
# ══════════════════════════════════════════════════════════
app = Flask(__name__, template_folder="webapp")
app.secret_key = SECRET_KEY
logging.getLogger("werkzeug").setLevel(logging.WARNING)

def _oid(x):
    try:    return ObjectId(x)
    except: return None

def utc_now(): return datetime.now(timezone.utc)

def require_db():
    if db is None or users_collection is None or signals_collection is None:
        return "Database not configured. Set MONGO_URI and restart.", 503
    return None

def safe_seconds_ago(last_run):
    if not last_run: return None
    try:
        now = utc_now().replace(tzinfo=None)
        lr  = last_run.replace(tzinfo=None) if hasattr(last_run, "tzinfo") else last_run
        return int((now - lr).total_seconds())
    except: return None

def admin_required(fn):
    @wraps(fn)
    def wrap(*a, **kw):
        if not flask_session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return fn(*a, **kw)
    return wrap

def verify_telegram_auth(data):
    bot_token  = os.getenv("TELEGRAM_BOT_TOKEN")
    check_hash = data.get("hash")
    if not bot_token or not check_hash: return False
    tmp       = {k: v for k, v in data.items() if k != "hash" and v is not None}
    check_str = "\n".join(f"{k}={tmp[k]}" for k in sorted(tmp))
    secret    = hashlib.sha256(bot_token.encode()).digest()
    expected  = hmac.new(secret, check_str.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, check_hash)

# ── Public routes ─────────────────────────────────────────
@app.route("/")
def home(): return render_template("home.html")

@app.route("/register", methods=["GET","POST"])
def register():
    err = require_db()
    if err: return err
    if request.method == "POST":
        email, pw = request.form["email"], request.form["password"]
        if users_collection.find_one({"email": email}):
            flash("Email already registered")
            return redirect(url_for("register"))
        r = users_collection.insert_one({
            "email": email, "password": generate_password_hash(pw),
            "verified": False, "deposit_verified": False, "created_at": utc_now()
        })
        flask_session["user_id"] = str(r.inserted_id)
        return redirect(url_for("dashboard"))
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    err = require_db()
    if err: return err
    if request.method == "POST":
        email, pw = request.form["email"], request.form["password"]
        user = users_collection.find_one({"email": email})
        if user and check_password_hash(user["password"], pw):
            flask_session["user_id"] = str(user["_id"])
            return redirect(url_for("dashboard"))
        flash("Invalid credentials")
    return render_template("login.html")

@app.route("/logout")
def logout():
    flask_session.clear()
    return redirect(url_for("home"))

@app.route("/dashboard")
def dashboard():
    err = require_db()
    if err: return err
    if "user_id" not in flask_session: return redirect(url_for("login"))
    user = users_collection.find_one({"_id": _oid(flask_session["user_id"])})
    sigs = list(signals_collection.find().sort("timestamp", -1).limit(10))
    return render_template("dashboard.html", user=user, signals=sigs)

@app.route("/verify-deposit", methods=["POST"])
def verify_deposit():
    err = require_db()
    if err: return jsonify({"status":"error","message":"Database unavailable"}), 503
    if "user_id" not in flask_session:
        return jsonify({"status":"error","message":"Unauthorized"}), 401
    amount = float(request.form.get("amount", 0))
    if amount >= 10:
        users_collection.update_one(
            {"_id": _oid(flask_session["user_id"])},
            {"$set": {"deposit_verified": True, "verified": True,
                      "deposit_amount": amount, "verified_at": utc_now()}}
        )
        return jsonify({"status":"success","message":"Verified. Signal access granted."})
    return jsonify({"status":"error","message":"Minimum deposit is $10"})

@app.route("/bot-status")
def bot_status():
    err = require_db()
    if err: return err
    status_doc    = db["bot_status"].find_one({"_id": "latest"}) or {}
    recent_errors = list(db["scan_errors"].find().sort("timestamp", -1).limit(10))
    recent_sigs   = list(signals_collection.find().sort("timestamp", -1).limit(20))
    last_run      = status_doc.get("last_scan_at")
    return render_template("bot_status.html",
        status=status_doc, last_run=last_run,
        seconds_ago=safe_seconds_ago(last_run),
        recent_errors=recent_errors, recent_signals=recent_sigs,
        delivered=sum(1 for s in recent_sigs if s.get("telegram_ok")),
        failed=sum(1 for s in recent_sigs if s.get("telegram_ok") is False))

@app.route("/broker-signup")
def broker_signup(): return redirect(AFFILIATE_LINK)

@app.route("/telegram-auth", methods=["POST"])
def telegram_auth():
    err = require_db()
    if err: return jsonify({"status":"error","message":"Database unavailable"}), 503
    data = request.get_json()
    if not data: return jsonify({"status":"error","message":"No data"}), 400
    if not verify_telegram_auth(data):
        return jsonify({"status":"error","message":"Invalid auth"}), 401
    tg_id = str(data.get("id",""))
    if not tg_id: return jsonify({"status":"error","message":"Missing ID"}), 400
    try:
        user = users_collection.find_one({"telegram_id": tg_id})
        if not user:
            r = users_collection.insert_one({
                "telegram_id": tg_id, "first_name": data.get("first_name",""),
                "last_name": data.get("last_name",""), "username": data.get("username",""),
                "verified": True, "deposit_verified": False, "created_at": utc_now()
            })
            flask_session["user_id"] = str(r.inserted_id)
        else:
            users_collection.update_one({"telegram_id": tg_id}, {"$set": {
                "first_name": data.get("first_name",""),
                "last_name": data.get("last_name",""),
                "username": data.get("username","")
            }})
            flask_session["user_id"] = str(user["_id"])
        return jsonify({"status":"success"})
    except Exception as e:
        print(f"[TG AUTH ERROR] {e}")
        return jsonify({"status":"error","message":"Auth failed"}), 500

# ── Admin routes ──────────────────────────────────────────
@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        if (request.form.get("username","").strip() == ADMIN_USERNAME and
                request.form.get("password","") == ADMIN_PASSWORD):
            flask_session["is_admin"] = True
            return redirect(url_for("admin_overview"))
        flash("Invalid admin credentials")
    return render_template("admin/login.html")

@app.route("/admin/logout")
def admin_logout():
    flask_session.pop("is_admin", None)
    return redirect(url_for("admin_login"))

@app.route("/admin")
@admin_required
def admin_overview():
    err = require_db()
    if err: return err
    sigs     = list(signals_collection.find().sort("timestamp", -1).limit(500))
    wins     = sum(1 for s in sigs if s.get("result") == "WIN")
    losses   = sum(1 for s in sigs if s.get("result") == "LOSS")
    decided  = wins + losses
    status_doc = db["bot_status"].find_one({"_id": "latest"}) or {}
    last_run   = status_doc.get("last_scan_at")
    return render_template("admin/overview.html",
        users_total=users_collection.count_documents({}),
        users_verified=users_collection.count_documents({"verified": True}),
        sigs_total=signals_collection.count_documents({}),
        wins=wins, losses=losses,
        pending=sum(1 for s in sigs if s.get("result") is None),
        win_rate=round(wins/decided*100,1) if decided else 0.0,
        delivered=sum(1 for s in sigs if s.get("telegram_ok")),
        failed=sum(1 for s in sigs if s.get("telegram_ok") is False),
        status=status_doc, seconds_ago=safe_seconds_ago(last_run),
        recent=sigs[:10])

@app.route("/admin/signals")
@admin_required
def admin_signals():
    err = require_db()
    if err: return err
    return render_template("admin/signals.html",
        signals=list(signals_collection.find().sort("timestamp",-1).limit(200)))

@app.route("/admin/users")
@admin_required
def admin_users():
    err = require_db()
    if err: return err
    return render_template("admin/users.html",
        users=list(users_collection.find().sort("created_at",-1).limit(200)))

@app.route("/admin/errors")
@admin_required
def admin_errors():
    err = require_db()
    if err: return err
    return render_template("admin/errors.html",
        errors=list(db["scan_errors"].find().sort("timestamp",-1).limit(200)))

# ══════════════════════════════════════════════════════════
#  BOT LOGIC — SESSION CONTROLLED
# ══════════════════════════════════════════════════════════

def _deliver_signal(sig):
    """Route signals to correct channels"""
    if sig["tier"] == "public":
        return send_telegram(fmt_signal(sig, sig["no"]))
    if sig["tier"] == "premium":
        if PREMIUM_ENABLED and PREMIUM_CHANNEL_ID:
            sent = send_telegram(fmt_gold_signal(sig, sig["no"]), chat_id=PREMIUM_CHANNEL_ID)
            label = "GOLD" if sig.get("is_gold") else "PREMIUM"
            print(f"  [{label}] {'Sent' if sent else 'FAILED'} → {sig['pair']}")
            return sent
    return False

def _store_signal(sig, delivered):
    sig["telegram_ok"] = bool(delivered) if sig["tier"] == "public" else None
    save_signal_to_db(sig)
    record_signal_state(sig["pair"], sig["type"])

def handle_session_notifications():
    """Send 30min pre-session and session open/close notifications"""
    global notified_sessions
    
    now = datetime.now(timezone.utc)
    current_session = get_active_session()
    
    for sess_name, sess_info in TRADING_SESSIONS.items():
        mins_to_open = time_to_session_open(sess_name)
        
        # ⏰ 30 MINUTES BEFORE SESSION
        if mins_to_open is not None and 29 <= mins_to_open <= 31:
            if f"{sess_name}_30min" not in notified_sessions:
                msg = f"⏰ <b>{sess_info['label']}</b> opens in 30 minutes!\n\nGet your watchlist ready. High-probability setups incoming! 📈"
                send_telegram(msg, pin=True)
                notified_sessions.add(f"{sess_name}_30min")
                print(f"[NOTIFY] ⏰ 30min pre-session: {sess_name}")
        
        # 🟢 SESSION JUST OPENED
        if sess_name == current_session and f"{sess_name}_open" not in notified_sessions:
            pairs = [p for p in ALL_PAIRS if p["session"] in ("all", sess_name)]
            send_telegram(fmt_session_announcement(sess_name), pin=True)
            send_telegram(fmt_watchlist(sess_name, pairs))
            notified_sessions.add(f"{sess_name}_open")
            print(f"[NOTIFY] 🟢 Session open: {sess_name}")
        
        # 🔴 SESSION JUST CLOSED
        elif sess_name != current_session and f"{sess_name}_close" not in notified_sessions:
            prev_hour = (now - timedelta(minutes=5)).hour
            if sess_info["start"] <= prev_hour < sess_info["end"] and not (sess_info["start"] <= now.hour < sess_info["end"]):
                send_telegram(fmt_session_close(sess_name))
                notified_sessions.add(f"{sess_name}_close")
                print(f"[NOTIFY] 🔴 Session closed: {sess_name}")
    
    # Reset notifications at midnight UTC
    if now.hour == 0 and now.minute == 0:
        notified_sessions.clear()

def scan_markets():
    """Scan markets ONLY during active trading sessions (Mon-Fri, 4 sessions only)"""
    global session_signals
    
    now = datetime.now(timezone.utc)
    
    # ❌ STOP: NO TRADING ON WEEKENDS
    if is_weekend():
        day_name = "Saturday" if now.weekday() == 5 else "Sunday"
        print(f"[{now.strftime('%H:%M:%S')}] 🛑 {day_name} - NO TRADING. Scanning paused.")
        return
    
    # ❌ STOP: NO TRADING OUTSIDE SESSIONS
    active_session = get_active_session()
    if active_session is None:
        next_sess = None
        hour = now.hour
        for sess_name, sess_info in TRADING_SESSIONS.items():
            mins = time_to_session_open(sess_name)
            if mins is not None and (next_sess is None or mins < time_to_session_open(next_sess)):
                next_sess = sess_name
        next_label = TRADING_SESSIONS[next_sess]["label"] if next_sess else "Unknown"
        print(f"[{now.strftime('%H:%M:%S')}] ⏸ Outside trading hours. Next: {next_label}")
        handle_session_notifications()  # Still send pre-session alerts
        return
    
    # ✅ WE'RE IN A TRADING SESSION
    print(f"[{now.strftime('%H:%M:%S')}] ✅ TRADING ACTIVE: {TRADING_SESSIONS[active_session]['label']}")
    
    # Handle notifications
    handle_session_notifications()
    
    # Evaluate pending signals
    try:
        evaluate_pending_signals(session_signals)
    except Exception as e:
        print(f"[EVAL ERROR] {e}")
        log_scan_error("evaluate_pending_signals", str(e))
    
    # Scan pairs for current session
    pairs = pairs_for_session(active_session)
    sent_ok = sent_fail = scanned = generated = 0
    
    print(f"Scanning {len(pairs)} pairs ({TRADING_SESSIONS[active_session]['label']})")

    for p in pairs:
        scanned += 1
        try:
            sig = analyze_pair(p)
        except Exception as e:
            print(f"  [SCAN ERROR] {p.get('name','?')}: {e}")
            log_scan_error("analyze_pair", f"{p.get('name','?')}: {e}")
            time.sleep(0.5)
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
                    print(f"  [✓ SIGNAL] {sig['pair']} {sig['type']}  score={sig['score']}")
                else:
                    sent_fail += 1
                    print(f"  [✗ SIGNAL] {sig['pair']} DELIVERY FAILED")
            else:
                print(f"  [PREMIUM] {sig['pair']} {sig['type']}  score={sig['score']}")
        
        time.sleep(0.5)

    # Session report at session close times
    if (now.hour, now.minute) in [(9,0), (17,0), (20,0)]:
        send_telegram(fmt_session_report(session_signals, now.strftime("%d %b").upper()))
        session_signals = []

    upsert_bot_status({
        "last_scan_at": datetime.now(timezone.utc).replace(tzinfo=None),
        "session": active_session,
        "pairs_scanned": scanned,
        "signals_generated": generated,
        "signals_sent_ok": sent_ok,
        "signals_sent_fail": sent_fail,
    })

def poll_commands():
    global last_update_id
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
            params={"offset": last_update_id+1, "timeout": 8,
                    "allowed_updates": ["message","callback_query"]},
            timeout=5
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("ok") and data.get("result"):
                for upd in data["result"]:
                    last_update_id = max(last_update_id, upd["update_id"])
                    try:
                        handle_telegram_command(upd, send_telegram, PREMIUM_ENABLED)
                    except Exception as e:
                        print(f"[CMD ERROR] {e}")
                        log_scan_error("telegram_command", str(e))
    except Exception as e:
        print(f"[POLL ERROR] {e}")

# ══════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════
def main():
    for issue in validate_runtime_config():
        print(f"[CONFIG] {issue}")

    print("=" * 70)
    print("  🚀 VEDA TRADER v5 — SESSION CONTROLLED BOT")
    print("=" * 70)
    print("  📅 TRADING SESSIONS (UTC, Mon-Fri ONLY):")
    print("     🌏 Asian:     00:00 - 09:00 UTC")
    print("     🇬🇧 London:   08:00 - 17:00 UTC")
    print("     🇺🇸 New York: 13:00 - 20:00 UTC")
    print("  ⏰ 30min pre-session notifications")
    print("  🔔 Session open/close alerts")
    print("  🛑 NO TRADING: Weekends, Outside Sessions")
    print("=" * 70)

    # Web dashboard
    port = int(os.getenv("PORT", 5000))
    web = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False),
        daemon=True, name="WebDashboard"
    )
    web.start()
    print(f"[WEB] Dashboard → http://0.0.0.0:{port}\n")

    send_telegram(
        "🚀 <b>VEDA TRADER v5 ONLINE</b>\n"
        "Trading bot + web dashboard running.\n\n"
        "📅 <b>TRADING SCHEDULE (UTC):</b>\n"
        "🌏 Asian: 00:00 - 09:00\n"
        "🇬🇧 London: 08:00 - 17:00\n"
        "🇺🇸 New York: 13:00 - 20:00\n\n"
        "⏰ 30min pre-session alerts\n"
        "📡 Forex → FREE channel\n"
        "💎 Premium → PREMIUM channel\n"
        "🛑 Weekends: NO TRADING"
    )
    setup_bot_profile()

    scan_markets()
    schedule.every(5).minutes.do(scan_markets)

    print("[BOT] ✅ Running. Only trading during 4 main sessions.")
    print("[BOT] Ctrl+C to stop.\n")
    
    while True:
        schedule.run_pending()
        poll_commands()
        time.sleep(2)

if __name__ == "__main__":
    main()
