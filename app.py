from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timezone
from functools import wraps
import os
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))

MONGO_URI = os.getenv('MONGO_URI')
client = MongoClient(MONGO_URI)
db = client['vedatrader']
users_collection   = db['users']
signals_collection = db['signals']

AFFILIATE_LINK = os.getenv('AFFILIATE_LINK')

# ── Admin credentials (override via env) ───────────────────────────────────
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'VedaGold2026!')


def _oid(x):
    try: return ObjectId(x)
    except Exception: return None


def utc_now():
    return datetime.now(timezone.utc)


def admin_required(fn):
    @wraps(fn)
    def wrap(*a, **kw):
        if not session.get('is_admin'):
            return redirect(url_for('admin_login'))
        return fn(*a, **kw)
    return wrap


# ── Public + member routes ─────────────────────────────────────────────────
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email    = request.form['email']
        password = request.form['password']
        if users_collection.find_one({'email': email}):
            flash('Email already exists')
            return redirect(url_for('register'))
        result = users_collection.insert_one({
            'email': email,
            'password': generate_password_hash(password),
            'verified': False,
            'deposit_verified': False,
            'created_at': utc_now()
        })
        session['user_id'] = str(result.inserted_id)
        return redirect(url_for('dashboard'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form['email']
        password = request.form['password']
        user = users_collection.find_one({'email': email})
        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])
            return redirect(url_for('dashboard'))
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = users_collection.find_one({'_id': _oid(session['user_id'])})
    recent_signals = list(signals_collection.find().sort('timestamp', -1).limit(10))
    return render_template('dashboard.html', user=user, signals=recent_signals)

@app.route('/verify-deposit', methods=['POST'])
def verify_deposit():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    deposit_amount = float(request.form.get('amount', 0))
    if deposit_amount >= 10:
        users_collection.update_one(
            {'_id': _oid(session['user_id'])},
            {'$set': {
                'deposit_verified': True, 'verified': True,
                'deposit_amount': deposit_amount, 'verified_at': utc_now()
            }})
        return jsonify({'status': 'success', 'message': 'Verification complete. You now have access to signals.'})
    return jsonify({'status': 'error', 'message': 'Minimum deposit is $10'})

@app.route('/bot-status')
def bot_status():
    status_doc     = db['bot_status'].find_one({'_id': 'latest'}) or {}
    recent_errors  = list(db['scan_errors'].find().sort('timestamp', -1).limit(10))
    recent_signals = list(signals_collection.find().sort('timestamp', -1).limit(20))
    delivered = sum(1 for s in recent_signals if s.get('telegram_ok'))
    failed    = sum(1 for s in recent_signals if s.get('telegram_ok') is False)
    last_run = status_doc.get('last_scan_at')
    seconds_ago = int((utc_now().replace(tzinfo=None) - last_run).total_seconds()) if last_run else None
    return render_template('bot_status.html',
        status=status_doc, last_run=last_run, seconds_ago=seconds_ago,
        recent_errors=recent_errors, recent_signals=recent_signals,
        delivered=delivered, failed=failed)

@app.route('/broker-signup')
def broker_signup():
    return redirect(AFFILIATE_LINK)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


# ── Admin ──────────────────────────────────────────────────────────────────
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        u = request.form.get('username', '').strip()
        p = request.form.get('password', '')
        if u == ADMIN_USERNAME and p == ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect(url_for('admin_overview'))
        flash('Invalid admin credentials')
    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('admin_login'))

@app.route('/admin')
@admin_required
def admin_overview():
    sigs = list(signals_collection.find().sort('timestamp', -1).limit(500))
    wins   = sum(1 for s in sigs if s.get('result') == 'WIN')
    losses = sum(1 for s in sigs if s.get('result') == 'LOSS')
    pending = sum(1 for s in sigs if s.get('result') is None)
    decided = wins + losses
    win_rate = round((wins / decided) * 100, 1) if decided else 0.0
    delivered = sum(1 for s in sigs if s.get('telegram_ok'))
    failed    = sum(1 for s in sigs if s.get('telegram_ok') is False)

    status_doc = db['bot_status'].find_one({'_id': 'latest'}) or {}
    last_run = status_doc.get('last_scan_at')
    seconds_ago = int((utc_now().replace(tzinfo=None) - last_run).total_seconds()) if last_run else None

    return render_template('admin/overview.html',
        users_total=users_collection.count_documents({}),
        users_verified=users_collection.count_documents({'verified': True}),
        sigs_total=signals_collection.count_documents({}),
        wins=wins, losses=losses, pending=pending, win_rate=win_rate,
        delivered=delivered, failed=failed,
        status=status_doc, seconds_ago=seconds_ago,
        recent=sigs[:10])

@app.route('/admin/signals')
@admin_required
def admin_signals():
    sigs = list(signals_collection.find().sort('timestamp', -1).limit(200))
    return render_template('admin/signals.html', signals=sigs)

@app.route('/admin/users')
@admin_required
def admin_users():
    users = list(users_collection.find().sort('created_at', -1).limit(200))
    return render_template('admin/users.html', users=users)

@app.route('/admin/errors')
@admin_required
def admin_errors():
    errors = list(db['scan_errors'].find().sort('timestamp', -1).limit(200))
    return render_template('admin/errors.html', errors=errors)


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
