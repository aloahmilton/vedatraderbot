"""
VEDA TRADER - main.py
Signal Bot + Web Dashboard + AI Admin
Run: python main.py
"""

import os, time, threading, schedule, logging
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

from flask import (Flask, render_template_string, request, jsonify,
                   redirect, url_for, flash, session as flask_session)
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

from config import (
    FREE_CHANNEL_ID, PREMIUM_CHANNEL_ID, ADMIN_CHAT_ID,
    SECRET_KEY, ADMIN_USERNAME, ADMIN_PASSWORD,
    ALL_FREE_PAIRS, ALL_PREMIUM_PAIRS, FOREX_PAIRS,
    pairs_for_session, current_session, session_label,
    SESSION_REPORT_TIMES_UTC, SESSION_OPEN_TIMES_UTC,
    is_weekend, validate_runtime_config, SESSIONS,
    TELEGRAM_TOKEN
)
from engine import analyze_pair, evaluate_pending_signals
from notifier import (
    send_telegram, send_admin,
    fmt_signal, fmt_activity_result, fmt_session_announcement,
    fmt_session_close, fmt_watchlist, fmt_session_report,
    fmt_daily_report, fmt_weekend_close, fmt_weekend_open,
    fmt_broker_reminder, fmt_admin_summary,
    handle_telegram_command, setup_bot_profile
)
from database import (
    get_db, init_db, save_signal_to_db, record_signal_state,
    upsert_bot_status, log_scan_error, get_daily_stats,
    get_daily_stats_for_date, get_all_subscribers
)
from ai_admin import (
    generate_admin_summary, should_pause_signals, auto_reply
)

import requests as req

# -- State ---------------------------------------------------
session_signals:      list = []
last_session_alerted: str  = ""
last_update_id:       int  = 0
signals_paused:       bool = False
last_summary_hour:    int  = -1
last_broker_reminder: str  = ""
last_daily_report_date: str = ""

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# -- Flask App -----------------------------------------------
app = Flask(__name__)
app.secret_key = SECRET_KEY
logging.getLogger("werkzeug").setLevel(logging.WARNING)

def admin_required(fn):
    @wraps(fn)
    def wrap(*a, **kw):
        if not flask_session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return fn(*a, **kw)
    return wrap

# -- Web Routes ----------------------------------------------

ADMIN_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<title>Veda Trader Admin</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0a0a0f; color: #e2e8f0; font-family: 'Courier New', monospace; }
  .header { background: linear-gradient(135deg, #f59e0b, #d97706); padding: 20px 30px; }
  .header h1 { font-size: 1.6rem; color: #000; letter-spacing: 2px; }
  .header p { color: #000; opacity: 0.7; font-size: 0.85rem; }
  .container { max-width: 1100px; margin: 0 auto; padding: 30px 20px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 30px; }
  .card { background: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 20px; }
  .card h3 { font-size: 0.75rem; color: #6b7280; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
  .card .val { font-size: 2rem; font-weight: bold; color: #f59e0b; }
  .card .sub { font-size: 0.8rem; color: #6b7280; margin-top: 4px; }
  .section { background: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 24px; margin-bottom: 24px; }
  .section h2 { font-size: 1rem; color: #f59e0b; margin-bottom: 16px; text-transform: uppercase; letter-spacing: 1px; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th { text-align: left; padding: 8px 12px; color: #6b7280; border-bottom: 1px solid #1f2937; font-size: 0.75rem; }
  td { padding: 10px 12px; border-bottom: 1px solid #1f2937; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; }
  .badge-buy { background: #064e3b; color: #34d399; }
  .badge-sell { background: #450a0a; color: #f87171; }
  .badge-tp { background: #064e3b; color: #34d399; }
  .badge-sl { background: #450a0a; color: #f87171; }
  .badge-open { background: #1e3a5f; color: #60a5fa; }
  .badge-premium { background: #451a03; color: #f59e0b; }
  .badge-free { background: #1f2937; color: #9ca3af; }
  .btn { display: inline-block; padding: 8px 16px; border-radius: 6px; border: none; cursor: pointer; font-size: 0.85rem; font-family: inherit; }
  .btn-primary { background: #f59e0b; color: #000; font-weight: bold; }
  .btn-danger { background: #7f1d1d; color: #fca5a5; }
  .btn-sm { padding: 4px 10px; font-size: 0.75rem; }
  .status-dot { width: 8px; height: 8px; border-radius: 50%; background: #22c55e; display: inline-block; margin-right: 6px; animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
  .input { background: #1f2937; border: 1px solid #374151; color: #e2e8f0; padding: 8px 12px; border-radius: 6px; width: 100%; font-family: inherit; font-size: 0.85rem; }
  .form-row { display: flex; gap: 8px; margin-bottom: 12px; }
  .paused-banner { background: #7f1d1d; border: 1px solid #991b1b; padding: 12px 20px; border-radius: 8px; margin-bottom: 20px; color: #fca5a5; font-weight: bold; }
  .ai-box { background: #0f172a; border: 1px solid #1e3a5f; border-radius: 8px; padding: 16px; font-size: 0.85rem; line-height: 1.6; color: #94a3b8; white-space: pre-wrap; }
  .nav { display: flex; gap: 16px; padding: 12px 30px; background: #111827; border-bottom: 1px solid #1f2937; }
  .nav a { color: #6b7280; text-decoration: none; font-size: 0.85rem; }
  .nav a:hover { color: #f59e0b; }
  .flash { background: #064e3b; color: #34d399; padding: 10px 16px; border-radius: 6px; margin-bottom: 16px; }
</style>
</head>
<body>
<div class="header">
  <h1>VEDA TRADER ADMIN</h1>
  <p>Signal Bot Control Panel</p>
</div>
<div class="nav">
  <a href="/admin">Dashboard</a>
  <a href="/admin/signals">Signals</a>
  <a href="/admin/subscribers">Subscribers</a>
  <a href="/admin/broadcast">Broadcast</a>
  <a href="/admin/logout">Logout</a>
</div>
<div class="container">
  {% if paused %}
  <div class="paused-banner">SIGNALS ARE PAUSED - <a href="/admin/resume" style="color:#fca5a5">Click to Resume</a></div>
  {% endif %}
  {% with msgs = get_flashed_messages() %}{% if msgs %}
  {% for m in msgs %}<div class="flash">{{ m }}</div>{% endfor %}
  {% endif %}{% endwith %}

  {{ content }}
</div>
</body>
</html>"""

def render_admin(content, **kwargs):
    from flask import render_template_string, get_flashed_messages
    return render_template_string(
        ADMIN_TEMPLATE,
        content=content,
        paused=signals_paused,
        get_flashed_messages=get_flashed_messages,
        **kwargs
    )

@app.route("/")
def home():
    return """<html><body style="background:#0a0a0f;color:#e2e8f0;font-family:monospace;display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column;gap:16px">
    <h1 style="color:#f59e0b;font-size:2rem">VEDA TRADER</h1>
    <p style="color:#6b7280">Professional Trading Signals</p>
    <a href="/admin" style="background:#f59e0b;color:#000;padding:10px 24px;border-radius:6px;text-decoration:none;font-weight:bold">Admin Panel -></a>
    </body></html>"""

@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        if (request.form.get("username") == ADMIN_USERNAME and
                request.form.get("password") == ADMIN_PASSWORD):
            flask_session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))
        return """<p style="color:red">Wrong credentials</p>""" + _login_form()
    return _login_form()

def _login_form():
    return """<html><body style="background:#0a0a0f;color:#e2e8f0;font-family:monospace;display:flex;align-items:center;justify-content:center;height:100vh">
    <form method="POST" style="background:#111827;padding:32px;border-radius:8px;min-width:300px;display:flex;flex-direction:column;gap:12px">
    <h2 style="color:#f59e0b;margin-bottom:8px">Admin Login</h2>
    <input name="username" placeholder="Username" style="background:#1f2937;border:1px solid #374151;color:#e2e8f0;padding:10px;border-radius:6px;font-family:monospace">
    <input name="password" type="password" placeholder="Password" style="background:#1f2937;border:1px solid #374151;color:#e2e8f0;padding:10px;border-radius:6px;font-family:monospace">
    <button type="submit" style="background:#f59e0b;color:#000;padding:10px;border:none;border-radius:6px;font-weight:bold;cursor:pointer">Login</button>
    </form></body></html>"""

@app.route("/admin/logout")
def admin_logout():
    flask_session.clear()
    return redirect(url_for("admin_login"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    stats  = get_daily_stats()
    status = {}
    db = get_db()
    if db:
        status = db["bot_status"].find_one({"_id": "latest"}) or {}

    ai_note = generate_admin_summary(stats)

    content = f"""
    <div class="grid">
      <div class="card"><h3>Signals Today</h3><div class="val">{stats.get('total',0)}</div>
      <div class="card"><h3>Win Rate</h3><div class="val" style="color:{'#22c55e' if stats.get('winrate',0)>=60 else '#ef4444'}">{stats.get('winrate',0)}%</div>
      <div class="card"><h3>TP Hits</h3><div class="val" style="color:#22c55e">{stats.get('tp_hits',0)}</div>
      <div class="card"><h3>SL Hits</h3><div class="val" style="color:#ef4444">{stats.get('sl_hits',0)}</div>
      <div class="card"><h3>Free Subs</h3><div class="val">{stats.get('free_subs',0)}</div>
      <div class="card"><h3>Premium Subs</h3><div class="val" style="color:#f59e0b">{stats.get('premium_subs',0)}</div>
    </div>

    <div class="section">
      <h2>AI Admin Assistant</h2>
      <div class="ai-box">{ai_note}</div>

    <div class="section">
      <h2>Quick Controls</h2>
      <div style="display:flex;gap:12px;flex-wrap:wrap">
        <a href="/admin/pause" class="btn btn-danger">Pause Signals</a>
        <a href="/admin/resume" class="btn btn-primary">Resume Signals</a>
        <a href="/admin/signals" class="btn btn-primary">View Signals</a>
        <a href="/admin/subscribers" class="btn btn-primary">Subscribers</a>
        <a href="/admin/broadcast" class="btn btn-primary">Broadcast</a>
      </div>

    <div class="section">
      <h2><span class="status-dot"></span>Bot Status</h2>
      <table>
        <tr><th>Field</th><th>Value</th></tr>
        <tr><td>Session</td><td>{status.get('session','-').title()}</td></tr>
        <tr><td>Last Scan</td><td>{status.get('last_scan_at','-')}</td></tr>
        <tr><td>Pairs Scanned</td><td>{status.get('pairs_scanned',0)}</td></tr>
        <tr><td>Signals Generated</td><td>{status.get('signals_generated',0)}</td></tr>
      </table>
    </div>
    """
    return render_admin(content)

@app.route("/admin/signals")
@admin_required
def admin_signals():
    db = get_db()
    signals = list(db["signals"].find().sort("timestamp",-1).limit(50)) if db else []
    rows = ""
    for s in signals:
        direction_badge = f'<span class="badge badge-buy">BUY</span>' if s.get("type")=="BUY" else f'<span class="badge badge-sell">SELL</span>'
        result = s.get("result","Open")
        if "TP" in result:   rb = f'<span class="badge badge-tp">{result}</span>'
        elif "SL" in result: rb = f'<span class="badge badge-sl">{result}</span>'
        else:                rb = f'<span class="badge badge-open">{result}</span>'
        tier_b = f'<span class="badge badge-premium">PREMIUM</span>' if s.get("tier")=="premium" else f'<span class="badge badge-free">FREE</span>'
        ts = s.get("timestamp","")
        rows += f"<tr><td>{ts}</td><td>{s.get('pair','')}</td><td>{direction_badge}</td><td>{s.get('score',0)}</td><td>{s.get('price','')}</td><td>{s.get('tp','')}</td><td>{s.get('sl','')}</td><td>{rb}</td><td>{tier_b}</td></tr>"

    content = f"""
    <div class="section">
      <h2>Recent Signals (Last 50)</h2>
      <table>
        <tr><th>Time</th><th>Pair</th><th>Dir</th><th>Score</th><th>Entry</th><th>TP</th><th>SL</th><th>Result</th><th>Tier</th></tr>
        {rows if rows else '<tr><td colspan="9" style="color:#6b7280;text-align:center;padding:20px">No signals yet</td></tr>'}
      </table>
    </div>"""
    return render_admin(content)

@app.route("/admin/subscribers")
@admin_required
def admin_subscribers():
    free    = get_all_subscribers("free")
    premium = get_all_subscribers("premium")
    def rows(subs, tier):
        out = ""
        for s in subs:
            badge = f'<span class="badge badge-premium">PREMIUM</span>' if tier=="premium" else f'<span class="badge badge-free">FREE</span>'
            out += f"<tr><td>{s.get('telegram_id','')}</td><td>@{s.get('username','')}</td><td>{badge}</td><td>{s.get('joined_at','')}</td><td><a href='/admin/grant/{s.get('telegram_id','')}' class='btn btn-sm btn-primary'>Grant</a> <a href='/admin/revoke/{s.get('telegram_id','')}' class='btn btn-sm btn-danger'>Revoke</a></td></tr>"
        return out

    content = f"""
    <div class="grid">
      <div class="card"><h3>Free Subscribers</h3><div class="val">{len(free)}</div>
      <div class="card"><h3>Premium Subscribers</h3><div class="val" style="color:#f59e0b">{len(premium)}</div>
      <div class="card"><h3>Total</h3><div class="val">{len(free)+len(premium)}</div>
    </div>
    <div class="section">
      <h2>Premium Subscribers</h2>
      <table><tr><th>ID</th><th>Username</th><th>Tier</th><th>Joined</th><th>Actions</th></tr>
      {rows(premium,'premium') or '<tr><td colspan="5" style="color:#6b7280;text-align:center;padding:20px">None yet</td></tr>'}
      </table>
    </div>
    <div class="section">
      <h2>Free Subscribers</h2>
      <table><tr><th>ID</th><th>Username</th><th>Tier</th><th>Joined</th><th>Actions</th></tr>
      {rows(free,'free') or '<tr><td colspan="5" style="color:#6b7280;text-align:center;padding:20px">None yet</td></tr>'}
      </table>
    </div>
    <div class="section">
      <h2>Add / Manage Subscriber</h2>
      <form method="POST" action="/admin/grant-form" style="display:flex;flex-direction:column;gap:10px;max-width:400px">
        <input class="input" name="telegram_id" placeholder="Telegram ID">
        <div style="display:flex;gap:8px">
          <button type="submit" name="action" value="grant" class="btn btn-primary">Grant Premium</button>
          <button type="submit" name="action" value="revoke" class="btn btn-danger">Revoke Premium</button>
        </div>
      </form>
    </div>"""
    return render_admin(content)

@app.route("/admin/grant/<tid>")
@admin_required
def admin_grant(tid):
    from database import upgrade_subscriber
    upgrade_subscriber(tid)
    flash(f"Granted premium to {tid}")
    return redirect(url_for("admin_subscribers"))

@app.route("/admin/revoke/<tid>")
@admin_required
def admin_revoke(tid):
    from database import downgrade_subscriber
    downgrade_subscriber(tid)
    flash(f"Revoked premium from {tid}")
    return redirect(url_for("admin_subscribers"))

@app.route("/admin/grant-form", methods=["POST"])
@admin_required
def admin_grant_form():
    from database import upgrade_subscriber, downgrade_subscriber
    tid    = request.form.get("telegram_id","").strip()
    action = request.form.get("action","grant")
    if tid:
        if action == "grant":
            upgrade_subscriber(tid)
            flash(f"Granted premium to {tid}")
        else:
            downgrade_subscriber(tid)
            flash(f"Revoked premium from {tid}")
    return redirect(url_for("admin_subscribers"))

@app.route("/admin/broadcast", methods=["GET","POST"])
@admin_required
def admin_broadcast():
    if request.method == "POST":
        msg     = request.form.get("message","").strip()
        channel = request.form.get("channel","both")
        if msg:
            if channel in ("free","both"):
                send_telegram(f"Veda Trader Update\n\n{msg}", chat_id=FREE_CHANNEL_ID)
            if channel in ("premium","both") and PREMIUM_CHANNEL_ID:
                send_telegram(f"Veda Trader Update\n\n{msg}", chat_id=PREMIUM_CHANNEL_ID)
            flash("Broadcast sent!")
    content = """
    <div class="section">
      <h2>Send Broadcast</h2>
      <form method="POST" style="display:flex;flex-direction:column;gap:12px;max-width:600px">
        <textarea class="input" name="message" rows="5" placeholder="Type your message..."></textarea>
        <select class="input" name="channel">
          <option value="both">Both Channels</option>
          <option value="free">Free Channel Only</option>
          <option value="premium">Premium Channel Only</option>
        </select>
        <button type="submit" class="btn btn-primary">Send Broadcast</button>
      </form>
    </div>"""
    return render_admin(content)

@app.route("/admin/pause")
@admin_required
def admin_pause():
    global signals_paused
    signals_paused = True
    flash("Signals paused.")
    send_telegram("Signals paused by admin. We'll be back shortly.", chat_id=FREE_CHANNEL_ID)
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/resume")
@admin_required
def admin_resume():
    global signals_paused
    signals_paused = False
    flash("Signals resumed.")
    send_telegram("Signals are back! Watch for new entries.", chat_id=FREE_CHANNEL_ID)
    return redirect(url_for("admin_dashboard"))

# -- Signal Delivery -----------------------------------------

def _deliver_signal(sig: dict) -> dict:
    results = {}
    msg = fmt_signal(sig)
    pair_name = sig["pair"]
    is_forex = pair_name in FOREX_PAIRS
    tier = sig["tier"]

    if tier == "public":
        results["free"] = send_telegram(msg, chat_id=FREE_CHANNEL_ID)
        if PREMIUM_CHANNEL_ID and not is_forex:
            results["premium"] = send_telegram(msg, chat_id=PREMIUM_CHANNEL_ID)
    else:
        if PREMIUM_CHANNEL_ID and not is_forex:
            results["premium"] = send_telegram(msg, chat_id=PREMIUM_CHANNEL_ID)

    return results

def _store_signal(sig: dict, delivery: dict):
    sig["telegram_ok"] = any(delivery.values())
    save_signal_to_db(sig)
    record_signal_state(sig["pair"], sig["type"])


def _send_trade_result(sig: dict):
    msg = fmt_activity_result(sig)
    send_telegram(msg, chat_id=FREE_CHANNEL_ID)
    if PREMIUM_CHANNEL_ID and sig.get("tier") == "premium":
        send_telegram(msg, chat_id=PREMIUM_CHANNEL_ID)
    send_admin(msg)


def _send_daily_report(report_date):
    stats = get_daily_stats_for_date(report_date)
    date_str = report_date.strftime("%d %b %Y")
    msg = fmt_daily_report(stats, date_str)
    send_admin(msg)
    send_telegram(msg, chat_id=FREE_CHANNEL_ID)
    if PREMIUM_CHANNEL_ID:
        send_telegram(msg, chat_id=PREMIUM_CHANNEL_ID)


# -- Session Management --------------------------------------

def _handle_session_change(sess: str):
    global last_session_alerted, session_signals

    if last_session_alerted and last_session_alerted != "weekend":
        send_telegram(fmt_session_close(last_session_alerted))
        if PREMIUM_CHANNEL_ID:
            send_telegram(fmt_session_close(last_session_alerted), chat_id=PREMIUM_CHANNEL_ID)
        if session_signals:
            send_telegram(fmt_session_report(session_signals,
                datetime.now(timezone.utc).strftime("%d %b").upper()))
            if PREMIUM_CHANNEL_ID:
                premium_sigs = [s for s in session_signals if s.get("tier")=="premium"]
                if premium_sigs:
                    send_telegram(fmt_session_report(premium_sigs,
                        datetime.now(timezone.utc).strftime("%d %b").upper()),
                        chat_id=PREMIUM_CHANNEL_ID)
        session_signals = []

    free_pairs    = pairs_for_session(sess, "public")
    premium_pairs = pairs_for_session(sess, "premium")

    send_telegram(fmt_broker_reminder())

    send_telegram(fmt_session_announcement(sess), pin=True)
    send_telegram(fmt_watchlist(sess, free_pairs))

    if PREMIUM_CHANNEL_ID:
        send_telegram(fmt_session_announcement(sess), pin=True, chat_id=PREMIUM_CHANNEL_ID)
        premium_non_forex = [p for p in premium_pairs if p["name"] not in FOREX_PAIRS]
        send_telegram(fmt_watchlist(sess, premium_non_forex), chat_id=PREMIUM_CHANNEL_ID)

    last_session_alerted = sess
    print(f"[SESSION] {session_label(sess)} announced")


# -- Main Scanner --------------------------------------------

def scan_markets():
    global session_signals, last_session_alerted, last_summary_hour, signals_paused, last_daily_report_date

    if signals_paused:
        print("[BOT] Paused - skipping scan.")
        return

    now  = datetime.now(timezone.utc)
    sess = current_session()
    day  = now.weekday()

    weekend = is_weekend()

    try:
        closed_signals = evaluate_pending_signals(session_signals)
        for sig in closed_signals:
            if not sig.get("result_notified"):
                _send_trade_result(sig)
                sig["result_notified"] = True
    except Exception as e:
        log_scan_error("evaluate_pending_signals", str(e))

    if not weekend and sess != last_session_alerted:
        _handle_session_change(sess)

    if weekend and last_session_alerted != "weekend":
        send_telegram(fmt_weekend_close(), pin=True)
        if PREMIUM_CHANNEL_ID:
            send_telegram(fmt_weekend_close(), pin=True, chat_id=PREMIUM_CHANNEL_ID)
        last_session_alerted = "weekend"

    if weekend:
        if not PREMIUM_CHANNEL_ID:
            return
        from config import PREMIUM_CRYPTO
        pairs_to_scan = PREMIUM_CRYPTO
    else:
        pairs_to_scan = (
            pairs_for_session(sess, "public") +
            (pairs_for_session(sess, "premium") if PREMIUM_CHANNEL_ID else [])
        )

    if day == 6 and now.hour >= 21 and last_session_alerted == "weekend":
        send_telegram(fmt_weekend_open(), pin=True)

    if now.hour != last_summary_hour and now.minute < 5:
        last_summary_hour = now.hour
        stats = get_daily_stats()
        pause, reason = should_pause_signals(stats, [s.get("result") for s in session_signals[-10:]])
        if pause:
            signals_paused = True
            send_admin(f"AI auto-paused signals:\n{reason}")
            send_telegram("Signals temporarily paused. Our team is reviewing market conditions.", chat_id=FREE_CHANNEL_ID)
        else:
            if now.hour % 4 == 0 and now.minute < 5:
                summary = generate_admin_summary(stats)
                send_admin(f"Hourly Summary\n\n{summary}")

    if now.date().isoformat() != last_daily_report_date:
        if now.hour == 23 and now.minute >= 55:
            _send_daily_report(now.date())
            last_daily_report_date = now.date().isoformat()
        elif now.hour == 0 and now.minute < 5:
            _send_daily_report(now.date() - timedelta(days=1))
            last_daily_report_date = now.date().isoformat()

    scanned = generated = sent_ok = sent_fail = premium_ok = premium_fail = 0

    seen_pairs = set()
    for pair in pairs_to_scan:
        if pair["name"] in seen_pairs:
            continue
        seen_pairs.add(pair["name"])
        scanned += 1

        from database import get_last_signal_direction
        last_dir = get_last_signal_direction(pair["name"])

        try:
            sig = analyze_pair(pair, tier=pair.get("tier", "public"))
        except Exception as e:
            log_scan_error("analyze_pair", f"{pair.get('name','?')}: {e}")
            time.sleep(0.5)
            continue

        if sig:
            if sig["type"] == last_dir:
                print(f"  [SKIP] {sig['pair']} {sig['type']} - same as last signal")
                continue

            generated += 1
            sig["no"]        = len(session_signals) + 1
            sig["timestamp"] = datetime.now(timezone.utc)

            delivered = _deliver_signal(sig)
            _store_signal(sig, delivered)
            session_signals.append(sig)

            if sig["tier"] == "public":
                if delivered.get("free"):  sent_ok   += 1
                else:                       sent_fail += 1
            else:
                if delivered.get("premium"): premium_ok   += 1
                else:                         premium_fail += 1

            print(f"  [SIGNAL] {sig['pair']} {sig['type']} score={sig['score']} tier={sig['tier']}")

        time.sleep(0.6)

    upsert_bot_status({
        "last_scan_at":      now,
        "session":           sess,
        "pairs_scanned":     scanned,
        "signals_generated": generated,
        "signals_sent_ok":   sent_ok,
        "signals_sent_fail": sent_fail,
        "premium_sent_ok":   premium_ok,
        "premium_sent_fail": premium_fail,
        "paused":            signals_paused,
    })

    print(f"[SCAN] {now.strftime('%H:%M')} | {sess} | scanned={scanned} generated={generated} ok={sent_ok} fail={sent_fail}")


# -- Command Polling -----------------------------------------

def set_signals_paused(paused: bool):
    global signals_paused
    signals_paused = paused
    print(f"[BOT] signals_paused set to {signals_paused}")
    upsert_bot_status({"paused": signals_paused})
    return signals_paused


def poll_commands():
    global last_update_id
    if not TELEGRAM_TOKEN:
        return
    try:
        r = req.get(
            f"{BASE_URL}/getUpdates",
            params={"offset": last_update_id+1, "timeout": 8,
                    "allowed_updates": ["message","callback_query"]},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("ok") and data.get("result"):
                for upd in data["result"]:
                    last_update_id = max(last_update_id, upd["update_id"])
                    try:
                        msg  = upd.get("message", {})
                        text = (msg.get("text") or "").strip()
                        chat_id  = str(msg.get("chat",{}).get("id",""))
                        username = msg.get("from",{}).get("username","user")

                        if text and not text.startswith("/"):
                            stats = get_daily_stats()
                            reply = auto_reply(text, username, stats)
                            if reply and chat_id:
                                send_telegram(reply, chat_id=chat_id)
                        else:
                            handle_telegram_command(
                                upd,
                                send_telegram,
                                bool(PREMIUM_CHANNEL_ID),
                                pause_callback=set_signals_paused,
                                resume_callback=set_signals_paused
                            )
                    except Exception as e:
                        log_scan_error("telegram_command", str(e))
    except Exception as e:
        print(f"[POLL ERROR] {e}")


# -- Entry Point ---------------------------------------------

def main():
    issues = validate_runtime_config()
    for issue in issues:
        print(f"[CONFIG] {issue}")

    db = get_db()
    if db is None:
        init_db()
        db = get_db()

    print("=" * 52)
    print("  VEDA TRADER - Starting Up")
    print("=" * 52)

    port = int(os.getenv("PORT", 5000))
    web  = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False),
        daemon=True, name="WebDashboard"
    )
    web.start()
    print(f"[WEB] Admin dashboard -> http://0.0.0.0:{port}/admin")

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