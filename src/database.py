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

# In-memory state for fast local caching
last_signal_time = {}

def is_dupe(pair: str, direction: str) -> bool:
    # 1. Check local cache first for speed
    local_last = last_signal_time.get(f"{pair}:{direction}")
    if local_last:
        if (datetime.now(timezone.utc) - local_last).total_seconds() / 60 < DEDUPE_MIN:
            return True

    # 2. Check Database (Source of Truth for persistence)
    db = get_db()
    if db is not None:
        try:
            last_sig = db["signals"].find_one(
                {"pair": pair, "type": direction},
                sort=[("timestamp", -1)]
            )
            if last_sig:
                last_time = last_sig["timestamp"]
                if last_time.tzinfo is None:
                    last_time = last_time.replace(tzinfo=timezone.utc)
                
                diff = (datetime.now(timezone.utc) - last_time).total_seconds() / 60
                if diff < DEDUPE_MIN:
                    # Sync local cache
                    last_signal_time[f"{pair}:{direction}"] = last_time
                    return True
        except Exception as e:
            print(f"[DB Error] Dupe check failed: {e}")
    
    return False

def record_signal_state(pair: str, direction: str):
    last_signal_time[f"{pair}:{direction}"] = datetime.now(timezone.utc)

def save_signal_to_db(sig_data):
    db = get_db()
    if db is not None:
        try:
            db["signals"].insert_one(sig_data)
        except Exception as e:
            print(f"[DB Error] Save failed: {e}")

def upsert_bot_status(status: dict):
    db = get_db()
    if db is not None:
        try:
            db["bot_status"].update_one(
                {"_id": "latest"},
                {"$set": status},
                upsert=True,
            )
        except Exception as e:
            print(f"[DB Error] Status upsert failed: {e}")

def log_scan_error(source: str, message: str):
    db = get_db()
    if db is not None:
        try:
            db["scan_errors"].insert_one({
                "source": source,
                "message": str(message),
                "timestamp": datetime.now(timezone.utc),
            })
        except Exception as e:
            print(f"[DB Error] Scan error logging failed: {e}")

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

# 👑 PREMIUM USER MANAGEMENT
def get_premium_user(user_id: str):
    db = get_db()
    if db is not None:
        try:
            return db["users"].find_one({"user_id": str(user_id)})
        except: return None
    return None

def add_premium_user(user_id: str, days: int, username: str = "Unknown"):
    db = get_db()
    if db is not None:
        try:
            from datetime import timedelta
            expiry = datetime.now(timezone.utc) + timedelta(days=int(days))
            db["users"].update_one(
                {"user_id": str(user_id)},
                {"$set": {"user_id": str(user_id), "username": username, "expiry": expiry, "active": True}},
                upsert=True
            )
            return True
        except Exception as e:
            print(f"[DB Error] Add user failed: {e}")
            return False
    return False

def get_recent_premium_signals(category: str = None, limit: int = 5):
    db = get_db()
    if db is not None:
        try:
            query = {"tier": "premium"}
            if category and category != "gold":
                query["category"] = category
            elif category == "gold":
                query["is_gold"] = True
                
            return list(db["signals"].find(query).sort("timestamp", -1).limit(limit))
        except: return []
    return []
