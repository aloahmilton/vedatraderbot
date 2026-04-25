"""
+----------------------------------------------------------+
¦          VEDA TRADER — main.py (All-in-One)              ¦
¦   Signal Bot  +  Web Dashboard  in one single file       ¦
+----------------------------------------------------------+

Start everything with just:
    python main.py
"""

import os, time, hmac, hashlib, threading, schedule, requests, logging
from datetime import datetime, timezone
from functools import wraps
from dotenv import load_dotenv

from flask import (Flask, render_template, request, jsonify,
                   redirect, url_for, flash, session as flask_session)
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
# keep_alive removed for Render compatibility




from src.config import (
    pairs_for_session, public_pairs_for_session, premium_pairs_for_session, premium_crypto_pairs, current_session, session_label,
    TELEGRAM_TOKEN, SECRET_KEY, MONGO_URI,
    ALL_PAIRS, validate_runtime_config, SESSION_REPORT_TIMES_UTC
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

# -- Premium -----------------------------------------------
try:
    from src import premium
    PREMIUM_CHANNEL_ID = premium.PREMIUM_CHANNEL_ID
    PREMIUM_ENABLED    = premium.PREMIUM_ENABLED
except ImportError:
    PREMIUM_CHANNEL_ID = None
    PREMIUM_ENABLED    = False

# -- Database ----------------------------------------------
db = get_db()
if db is None:
    init_db(); db = get_db()
users_collection   = db["users"]   if db is not None else None
signals_collection = db["signals"] if db is not None else None

# -- Config ------------------------------------------------
AFFILIATE_LINK = os.getenv("AFFILIATE_LINK", "#")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "VedaGold2026!")

# -- Bot state ---------------------------------------------
session_signals:      list = []
last_session_alerted: str  = ""
last_update_id:       int  = 0

# ----------------------------------------------------------
#  FLASK APP
# ----------------------------------------------------------
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

# -- Public routes -----------------------------------------
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

# -- Admin routes ------------------------------------------
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

# ----------------------------------------------------------
#  BOT LOGIC
# ----------------------------------------------------------
def _deliver_signal(sig):
    if sig["tier"] == "public":
        return {"free": send_telegram(fmt_signal(sig, sig["no"]))}
    if PREMIUM_ENABLED and PREMIUM_CHANNEL_ID:
        sent = send_telegram(fmt_gold_signal(sig, sig["no"]), chat_id=PREMIUM_CHANNEL_ID)
        label = "GOLD" if sig.get("is_gold") else "PREMIUM"
        print(f"  [{label}] {'Sent' if sent else 'FAILED'} -> {sig['pair']}")
        return {"premium": sent}
    return {"premium": False}

def _store_signal(sig, delivered):
    delivery = delivered if isinstance(delivered, dict) else {"free": bool(delivered)}
    sig["delivery"] = delivery
    if sig["tier"] == "public":
        sig["telegram_ok"] = bool(delivery.get("free"))
    else:
        sig["telegram_ok"] = bool(delivery.get("premium"))
    save_signal_to_db(sig)
    record_signal_state(sig["pair"], sig["type"])

def _send_session_broadcasts(sess: str):
    free_pairs = public_pairs_for_session(sess)
    premium_pairs = premium_pairs_for_session(sess)

    send_telegram(fmt_session_announcement(sess), pin=True)
    if free_pairs:
        send_telegram(fmt_watchlist(sess, free_pairs))

    if PREMIUM_ENABLED and PREMIUM_CHANNEL_ID:
        send_telegram(fmt_session_announcement(sess), pin=True, chat_id=PREMIUM_CHANNEL_ID)
        if premium_pairs:
            send_telegram(fmt_watchlist(sess, premium_pairs), chat_id=PREMIUM_CHANNEL_ID)

def _weekend_scan_pairs(now, sess: str):
    day = now.weekday()
    if day == 5:
        return premium_crypto_pairs()
    if day == 6 and now.hour < 21:
        return premium_crypto_pairs()
    if day == 4 and now.hour >= 21:
        return premium_crypto_pairs()
    return pairs_for_session(sess)

def scan_markets():
    global session_signals, last_session_alerted
    now  = datetime.now(timezone.utc)
    sess = current_session()
    day = now.weekday() # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    weekend_crypto_only = (
        (day == 4 and now.hour >= 21) or
        day == 5 or
        (day == 6 and now.hour < 21)
    )
    sent_ok = sent_fail = premium_ok = premium_fail = scanned = generated = 0

    try:
        evaluate_pending_signals(session_signals)
    except Exception as e:
        print(f"[EVAL ERROR] {e}"); log_scan_error("evaluate_pending_signals", str(e))

    if sess != last_session_alerted and not weekend_crypto_only:
        if last_session_alerted:
            send_telegram(fmt_session_close(last_session_alerted))
            if PREMIUM_ENABLED and PREMIUM_CHANNEL_ID:
                send_telegram(fmt_session_close(last_session_alerted), chat_id=PREMIUM_CHANNEL_ID)
        _send_session_broadcasts(sess)
        last_session_alerted = sess

    # -- Weekend Logic --
    # Friday Close (21:00 UTC) - free forex pauses, premium crypto can still run
    if day == 4 and now.hour >= 21:
        if last_session_alerted != "weekend":
            send_telegram(fmt_weekend_close(), pin=True)
            last_session_alerted = "weekend"
        if not (PREMIUM_ENABLED and premium_crypto_pairs()):
            print("[MARKET] Weekend close reached. Scanning paused.")
            return

    # Saturday - forex/indices/stocks closed, premium crypto remains active
    if day == 5:
        if not (PREMIUM_ENABLED and premium_crypto_pairs()):
            print("[MARKET] Saturday. Markets closed.")
            return

    # Sunday Open (21:00 UTC)
    if day == 6:
        if now.hour < 21:
            if not (PREMIUM_ENABLED and premium_crypto_pairs()):
                print("[MARKET] Sunday. Markets opening soon...")
                return
        elif last_session_alerted == "weekend":
            send_telegram(fmt_weekend_open(), pin=True)
            # This will trigger session announcement on next scan because sess != "weekend"

    pairs = _weekend_scan_pairs(now, sess)
    print(f"[{now.strftime('%H:%M:%S')}] Scanning {len(pairs)} pairs ({sess})")

    for p in pairs:
        scanned += 1
        try:
            sig = analyze_pair(p)
        except Exception as e:
            print(f"  [SCAN ERROR] {p.get('name','?')}: {e}")
            log_scan_error("analyze_pair", f"{p.get('name','?')}: {e}")
            time.sleep(0.5); continue

        if sig:
            generated += 1
            sig["no"]        = len(session_signals) + 1
            sig["timestamp"] = datetime.now(timezone.utc)
            sig["direction"] = sig["type"]
            delivered = _deliver_signal(sig)
            _store_signal(sig, delivered)
            session_signals.append(sig)
            if sig["tier"] == "public":
                if delivered.get("free"):
                    sent_ok += 1
                    print(f"  [OK SIGNAL] {sig['pair']} {sig['type']}  score={sig['score']}")
                else:
                    sent_fail += 1
                    print(f"  [FAILED SIGNAL] {sig['pair']} DELIVERY FAILED")
            else:
                if delivered.get("premium"):
                    premium_ok += 1
                else:
                    premium_fail += 1
                print(f"  [PREMIUM] {sig['pair']} {sig['type']}  score={sig['score']}")
        time.sleep(0.5)

    if (now.hour, now.minute) in SESSION_REPORT_TIMES_UTC:
        send_telegram(fmt_session_report(session_signals, now.strftime("%d %b").upper()))
        if PREMIUM_ENABLED and PREMIUM_CHANNEL_ID:
            premium_signals = [s for s in session_signals if s.get("tier") == "premium"]
            if premium_signals:
                send_telegram(
                    fmt_session_report(premium_signals, now.strftime("%d %b").upper()),
                    chat_id=PREMIUM_CHANNEL_ID
                )
        session_signals = []

    upsert_bot_status({
        "last_scan_at":      datetime.now(timezone.utc).replace(tzinfo=None),
        "session":           sess,
        "pairs_scanned":     scanned,
        "signals_generated": generated,
        "signals_sent_ok":   sent_ok,
        "signals_sent_fail": sent_fail,
        "premium_sent_ok":   premium_ok,
        "premium_sent_fail": premium_fail,
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
                    try:    handle_telegram_command(upd, send_telegram, PREMIUM_ENABLED)
                    except Exception as e:
                        print(f"[CMD ERROR] {e}"); log_scan_error("telegram_command", str(e))
    except Exception as e:
        print(f"[POLL ERROR] {e}")

# ----------------------------------------------------------
#  ENTRY POINT
# ----------------------------------------------------------
def main():
    for issue in validate_runtime_config():
        print(f"[CONFIG] {issue}")

    print("=" * 52)
    print("  VEDA TRADER - Bot + Dashboard starting")
    print("=" * 52)

    # Web dashboard in background thread
    port = int(os.getenv("PORT", 5000))
    web  = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False),
        daemon=True, name="WebDashboard"
    )
    web.start()
    print(f"[WEB] Dashboard -> http://0.0.0.0:{port}")

    setup_bot_profile()

    scan_markets()
    schedule.every(5).minutes.do(scan_markets)

    print("[BOT] Running. Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        poll_commands()
        time.sleep(2)


    
    

if __name__ == "__main__":
    main()
