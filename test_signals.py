"""
VEDA TRADER - Signal Generation Test
Run: python test_signals.py

Tests if signals can be generated for current market pairs.
"""

import os
import sys
import time

# Load environment
from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print("  VEDA TRADER - SIGNAL GENERATION TEST")
print("=" * 60)

# Import after loading env
from config import (
    pairs_for_session, current_session, is_weekend,
    SESSIONS, FREE_FOREX_PAIRS, PREMIUM_FOREX_PAIRS
)
from engine import analyze_pair

# Check current state
now_utc = __import__('datetime').datetime.now(__import__('datetime').timezone.utc)
print(f"\n[STATUS] Current UTC: {now_utc.strftime('%Y-%m-%d %H:%M UTC')}")
print(f"[STATUS] Hour (UTC): {now_utc.hour}")

sess = current_session()
print(f"[STATUS] Current Session: {sess}")
print(f"[STATUS] Weekend Mode: {is_weekend()}")

# Test all FREE pairs
print("\n" + "=" * 60)
print("  TESTING FREE (PUBLIC) PAIRS")
print("=" * 60)

pairs = pairs_for_session(sess, "public")
print(f"\n[Pairs] {len(pairs)} pairs for {sess} session:")

results = []
for pair in pairs:
    print(f"\n  Analyzing {pair['name']}...")
    try:
        sig = analyze_pair(pair, tier="public")
        if sig:
            print(f"    ✅ SIGNAL: {sig['type']} | Score: {sig['score']} | Price: {sig['price']}")
            results.append(sig)
        else:
            print(f"    ⚠️  No signal (score too low or conditions not met)")
    except Exception as e:
        print(f"    ❌ Error: {e}")
    time.sleep(0.5)

# Test PREMIUM pairs
print("\n" + "=" * 60)
print("  TESTING PREMIUM PAIRS")
print("=" * 60)

premium_pairs = pairs_for_session(sess, "premium")
print(f"\n[Pairs] {len(premium_pairs)} premium pairs:")

premium_results = []
for pair in premium_pairs:
    print(f"\n  Analyzing {pair['name']}...")
    try:
        sig = analyze_pair(pair, tier="premium")
        if sig:
            print(f"    ✅ SIGNAL: {sig['type']} | Score: {sig['score']} | Price: {sig['price']}")
            premium_results.append(sig)
        else:
            print(f"    ⚠️  No signal (score too low)")
    except Exception as e:
        print(f"    ❌ Error: {e}")
    time.sleep(0.5)

# Summary
print("\n" + "=" * 60)
print("  SUMMARY")
print("=" * 60)
print(f"  Free signals generated: {len(results)}")
print(f"  Premium signals generated: {len(premium_results)}")

if len(results) == 0 and len(premium_results) == 0:
    print("\n⚠️  NO SIGNALS GENERATED!")
    print("""
Possible reasons:
1. Market conditions don't meet signal threshold (65+)
2. Weekend - only premium crypto runs
3. Session not active
4. Data fetching issues

Try running during active market hours:
- Asian: 00:00-08:00 UTC
- London: 08:00-16:00 UTC  
- New York: 13:00-22:00 UTC
""")
else:
    print("\n✅ Signals CAN be generated! Check if scan_markets() is running.")
