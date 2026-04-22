import os
from datetime import datetime, timezone
from pymongo import MongoClient
from .config import MONGO_URI, DEDUPE_MIN

_db = None
_client = None

def init_db():
    global _db, _client
    if MONGO_URI:
        try:
            _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            _db = _client["vedatrader_v5"]
            _db.command("ping")
            return _db
        except Exception as e:
            print(f"[MongoDB] Connection failed: {e}")
    return None

def get_db():
    global _db
    if _db is None:
        init_db()
    return _db

# In-memory state for deduplication
last_signal_time = {}

def is_dupe(pair: str, direction: str) -> bool:
    last = last_signal_time.get(f"{pair}:{direction}")
    if not last: return False
    return (datetime.now(timezone.utc) - last).total_seconds() / 60 < DEDUPE_MIN

def record_signal_state(pair: str, direction: str):
    last_signal_time[f"{pair}:{direction}"] = datetime.now(timezone.utc)

def save_signal_to_db(sig_data):
    db = get_db()
    if db is not None:
        try:
            db["signals"].insert_one(sig_data)
        except Exception as e:
            print(f"[DB Error] Save failed: {e}")

def update_signal_result(pair, timestamp, result, exit_price):
    db = get_db()
    if db is not None:
        try:
            db["signals"].update_one(
                {"pair": pair, "timestamp": timestamp},
                {"$set": {"result": result, "exit_price": exit_price}},
            )
        except Exception as e:
            print(f"[DB Error] Update failed: {e}")
