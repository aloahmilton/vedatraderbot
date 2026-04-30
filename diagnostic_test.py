"""
VEDA TRADER - Diagnostic Script
Run: python diagnostic_test.py

Tests all external connections and helps diagnose why the bot might be dormant.
"""

import os
import sys
import json
import time

# Load environment
from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print("  VEDA TRADER - DIAGNOSTIC TEST")
print("=" * 60)

# ── Test 1: Environment Variables ─────────────────────────────────
print("\n[1] CHECKING ENVIRONMENT VARIABLES...")
required_vars = [
    "TELEGRAM_BOT_TOKEN",
    "FREE_TELEGRAM_CHANNEL_ID", 
    "ADMIN_CHAT_ID",
    "MONGO_URI",
]
missing = []
for var in required_vars:
    value = os.getenv(var, "")
    if not value:
        missing.append(var)
        print(f"   ❌ {var}: NOT SET")
    else:
        # Mask sensitive values
        if "KEY" in var or "TOKEN" in var or "URI" in var:
            print(f"   ✅ {var}: SET")
        else:
            print(f"   ✅ {var}: {value}")

if missing:
    print(f"\n   ⚠️  MISSING: {', '.join(missing)}")
    print("   → Add these to your .env file")
else:
    print("   ✅ All required variables set!")

# ── Test 2: MongoDB Connection ─────────────────────────────────
print("\n[2] TESTING MONGODB CONNECTION...")
try:
    from pymongo import MongoClient
    uri = os.getenv("MONGO_URI", "")
    if uri:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client["veda_trader"]
        
        # Check collections
        collections = db.list_collection_names()
        print(f"   ✅ MongoDB Connected!")
        print(f"   📊 Collections: {collections}")
        
        # Check bot status
        status = db["bot_status"].find_one({"_id": "latest"})
        if status:
            print(f"   📌 Last status: {status.get('last_scan_at', 'Unknown')}")
            print(f"   📌 Session: {status.get('session', 'Unknown')}")
        else:
            print("   ⚠️  No bot status found (bot may not have run yet)")
    else:
        print("   ❌ MONGO_URI not set")
except Exception as e:
    print(f"   ❌ MongoDB Error: {e}")

# ── Test 3: Telegram API ────────────────────────────────────────
print("\n[3] TESTING TELEGRAM API...")
import requests

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

if TELEGRAM_TOKEN:
    try:
        # Get bot info
        r = requests.get(f"{BASE_URL}/getMe", timeout=10)
        if r.status_code == 200:
            me = r.json()
            if me.get("ok"):
                bot_info = me.get("result", {})
                print(f"   ✅ Bot Connected: @{bot_info.get('username')}")
                print(f"   📌 Name: {bot_info.get('first_name')}")
            else:
                print(f"   ❌ Bot error: {me}")
        else:
            print(f"   ❌ HTTP {r.status_code}")
    except Exception as e:
        print(f"   ❌ Telegram Error: {e}")
    
    # Try sending test message
    ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
    if ADMIN_CHAT_ID:
        try:
            test_msg = "⚡ VEDA TRADER DIAGNOSTIC TEST\n\nThis is a test message to verify the bot is working."
            r = requests.post(
                f"{BASE_URL}/sendMessage",
                json={"chat_id": ADMIN_CHAT_ID, "text": test_msg},
                timeout=10
            )
            if r.status_code == 200:
                result = r.json()
                if result.get("ok"):
                    print(f"   ✅ Test message sent to admin!")
                else:
                    print(f"   ❌ Send error: {result}")
            else:
                print(f"   ❌ HTTP {r.status_code}")
        except Exception as e:
            print(f"   ❌ Send Error: {e}")
else:
    print("   ❌ TELEGRAM_BOT_TOKEN not set")

# ── Test 4: Yahoo Finance Data ────────────────────────────────
print("\n[4] TESTING YAHOO FINANCE DATA...")
import yfinance as yf

test_pairs = [
    {"name": "EUR/USD", "symbol": "EURUSD=X"},
    {"name": "GBP/USD", "symbol": "GBPUSD=X"},
    {"name": "BTC/USD", "symbol": "BTC-USD"},
]

for pair in test_pairs:
    try:
        ticker = yf.Ticker(pair["symbol"])
        df = ticker.history(interval="1m", period="1d")
        if df is not None and len(df) > 0:
            price = df["Close"].iloc[-1]
            print(f"   ✅ {pair['name']}: {price:.5f}")
        else:
            print(f"   ❌ {pair['name']}: No data")
        time.sleep(0.5)  # Rate limit
    except Exception as e:
        print(f"   ❌ {pair['name']}: {e}")

# ── Test 5: Signal Generation Test ────────────────────────────────
print("\n[5] TESTING SIGNAL GENERATION...")
try:
    from engine import analyze_pair
    
    test_pairs = [
        {"name": "EUR/USD", "symbol": "EURUSD=X", "pip": 0.0001, "tier": "public"},
    ]
    
    for pair in test_pairs:
        print(f"   Testing {pair['name']}...")
        sig = analyze_pair(pair, tier="public")
        if sig:
            print(f"   ✅ SIGNAL GENERATED!")
            print(f"   📌 Type: {sig['type']}")
            print(f"   📌 Score: {sig['score']}")
            print(f"   📌 Price: {sig['price']}")
        else:
            print(f"   ⚠️  No signal (market conditions don't meet threshold)")
        time.sleep(1)
except Exception as e:
    print(f"   ❌ Signal Error: {e}")

# ── Summary ──────────────────────────────────────────────
print("\n" + "=" * 60)
print("  DIAGNOSTIC COMPLETE")
print("=" * 60)

print("""
Common reasons why the bot is dormant:

1. ❌ Bot process not running on deployment
   → Check your Render/digitalocean logs

2. ❌ MongoDB connection failed
   → Check MONGO_URI in .env

3. ❌ No signals passing threshold
   → Markets may be ranging/low volatility

4. ❌ Network/firewall blocking
   → Ensure outbound HTTPS allowed

5. ❌ Bot crashed silently
   → Check deployment logs
""")
