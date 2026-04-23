import os
import sys
from datetime import datetime, timezone

# Add current directory to path
sys.path.insert(0, os.getcwd())

from src.engine import analyze_pair
from src.config import pairs_for_session, current_session, ALL_PAIRS

def test_signals():
    sess = current_session()
    pairs = pairs_for_session(sess)
    print(f"Testing {len(pairs)} pairs for session '{sess}'...")
    
    found = 0
    for p in pairs:
        # print(f"  Scanning {p['name']}...")
        try:
            sig = analyze_pair(p)
            if sig:
                print(f"[!] SIGNAL FOUND: {sig['pair']} ({sig['type']}) - Score: {sig['score']} - Gold: {sig['is_gold']}")
                found += 1
        except Exception as e:
            print(f"[ERROR] {p['name']}: {e}")
            
    print(f"\nDone. Total signals found: {found}")

if __name__ == "__main__":
    test_signals()
