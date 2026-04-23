from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timezone
from functools import wraps
import os
import secrets
import hmac
import hashlib
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

from src.database import get_db, init_db
from src.config import SECRET_KEY, MONGO_URI

load_dotenv()

app = Flask(__name__, template_folder='webapp')
app.secret_key = SECRET_KEY

db = get_db()
if db is None:
    print("CRITICAL: Could not connect to MongoDB")
    init_db()
    db = get_db()
    
users_collection   = db['users'] if db is not None else None
signals_collection = db['signals'] if db is not None else None

AFFILIATE_LINK = os.getenv('AFFILIATE_LINK')

# ── Admin credentials (override via env) ───────────────────────────────────
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'VedaGold2026!')


def _oid(x):
    try: return ObjectId(x)
    except Exception: return None


def utc_now():
    return datetime.now(timezone.utc)


def verify_telegram_auth(data):
    """Verify Telegram login widget data using bot token."""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        return False

    # Remove hash from data for verification
    check_hash = data.get('hash')
    if not check_hash:
        return False

    data_check = data.copy()
    del data_check['hash']

    # Sort keys alphabetically
    data_check_arr = []
    for key in sorted(data_check.keys()):
        if data_check[key] is not None:
            data_check_arr.append(f"{key}={data_check[key]}")

    data_check_string = "\n".join(data_check_arr)

    # Calculate expected hash
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    return hmac.compare_digest(expected_hash, check_hash)


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

def require_db():
    if db is None or users_collection is None or signals_collection is None:
        return "Database is not configured. Set MONGO_URI and restart.", 503
    return None

@app.route('/register', methods=['GET', 'POST'])
def register():
    db_err = require_db()
    if db_err:
        return db_err
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
    db_err = require_db()
    if db_err:
        return db_err
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
    db_err = require_db()
    if db_err:
        return db_err
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = users_collection.find_one({'_id': _oid(session['user_id'])})
    recent_signals = list(signals_collection.find().sort('timestamp', -1).limit(10))
    return render_template('dashboard.html', user=user, signals=recent_signals)

@app.route('/verify-deposit', methods=['POST'])
def verify_deposit():
    db_err = require_db()
    if db_err:
        return jsonify({'status': 'error', 'message': 'Database unavailable'}), 503
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
    db_err = require_db()
    if db_err:
        return db_err
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

@app.route('/telegram-auth', methods=['POST'])
def telegram_auth():
    try:
        # Check database availability first
        db_err = require_db()
        if db_err:
            return jsonify({'status': 'error', 'message': 'Database unavailable'}), 503

        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'No data received'}), 400

        # Verify Telegram auth data
        if not verify_telegram_auth(data):
            return jsonify({'status': 'error', 'message': 'Invalid Telegram authentication'}), 401

        telegram_id = str(data.get('id'))
        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')
        username = data.get('username', '')

        if not telegram_id:
            return jsonify({'status': 'error', 'message': 'Invalid Telegram data'}), 400

        # Check if user exists by telegram_id
        user = users_collection.find_one({'telegram_id': telegram_id})

        if not user:
            # Create new user account
            user_doc = {
                'telegram_id': telegram_id,
                'first_name': first_name,
                'last_name': last_name,
                'username': username,
                'verified': True,
                'deposit_verified': False,
                'created_at': utc_now()
            }
            result = users_collection.insert_one(user_doc)
            session['user_id'] = str(result.inserted_id)
        else:
            # Update existing user info
            users_collection.update_one(
                {'telegram_id': telegram_id},
                {'$set': {
                    'first_name': first_name,
                    'last_name': last_name,
                    'username': username
                }}
            )
            session['user_id'] = str(user['_id'])

        return jsonify({'status': 'success', 'message': 'Authenticated successfully'})

    except Exception as e:
        print(f"Telegram auth error: {e}")
        return jsonify({'status': 'error', 'message': 'Authentication failed'}), 500

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
    db_err = require_db()
    if db_err:
        return db_err
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
    db_err = require_db()
    if db_err:
        return db_err
    sigs = list(signals_collection.find().sort('timestamp', -1).limit(200))
    return render_template('admin/signals.html', signals=sigs)

@app.route('/admin/users')
@admin_required
def admin_users():
    db_err = require_db()
    if db_err:
        return db_err
    users = list(users_collection.find().sort('created_at', -1).limit(200))
    return render_template('admin/users.html', users=users)

@app.route('/admin/errors')
@admin_required
def admin_errors():
    db_err = require_db()
    if db_err:
        return db_err
    errors = list(db['scan_errors'].find().sort('timestamp', -1).limit(200))
    return render_template('admin/errors.html', errors=errors)


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
