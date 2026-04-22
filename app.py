from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from pymongo import MongoClient
from datetime import datetime
import os
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))

# Cloud MongoDB Atlas connection
MONGO_URI = os.getenv('MONGO_URI')
client = MongoClient(MONGO_URI)
db = client['vedatrader']
users_collection = db['users']
signals_collection = db['signals']

# Affiliate broker link - load from env
AFFILIATE_LINK = os.getenv('AFFILIATE_LINK')

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        if users_collection.find_one({'email': email}):
            flash('Email already exists')
            return redirect(url_for('register'))

        user = {
            'email': email,
            'password': generate_password_hash(password),
            'verified': False,
            'deposit_verified': False,
            'created_at': datetime.utcnow()
        }
        users_collection.insert_one(user)
        session['user_id'] = str(user['_id'])

        return redirect(url_for('dashboard'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
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

    user = users_collection.find_one({'_id': session['user_id']})
    recent_signals = list(signals_collection.find().sort('timestamp', -1).limit(10))

    return render_template('dashboard.html', user=user, signals=recent_signals)

@app.route('/verify-deposit', methods=['POST'])
def verify_deposit():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    # In production integrate with broker API here
    deposit_amount = float(request.form.get('amount', 0))

    if deposit_amount >= 10:
        users_collection.update_one(
            {'_id': session['user_id']},
            {'$set': {
                'deposit_verified': True,
                'verified': True,
                'deposit_amount': deposit_amount,
                'verified_at': datetime.utcnow()
            }}
        )
        return jsonify({'status': 'success', 'message': 'Verification complete. You now have access to signals.'})

    return jsonify({'status': 'error', 'message': 'Minimum deposit is $10'})

@app.route('/bot-status')
def bot_status():
    status_doc = db['bot_status'].find_one({'_id': 'latest'}) or {}
    recent_errors = list(db['scan_errors'].find().sort('timestamp', -1).limit(10))
    recent_signals = list(signals_collection.find().sort('timestamp', -1).limit(20))

    delivered = sum(1 for s in recent_signals if s.get('telegram_ok'))
    failed = sum(1 for s in recent_signals if s.get('telegram_ok') is False)

    last_run = status_doc.get('last_scan_at')
    seconds_ago = None
    if last_run:
        seconds_ago = int((datetime.utcnow() - last_run).total_seconds())

    return render_template(
        'bot_status.html',
        status=status_doc,
        last_run=last_run,
        seconds_ago=seconds_ago,
        recent_errors=recent_errors,
        recent_signals=recent_signals,
        delivered=delivered,
        failed=failed,
    )

@app.route('/broker-signup')
def broker_signup():
    return redirect(AFFILIATE_LINK)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)