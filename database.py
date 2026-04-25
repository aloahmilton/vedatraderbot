"""
VEDA TRADER - database.py
MongoDB connection and helpers.
"""

import os
from datetime import datetime, timezone
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

_client = None
_db     = None

def get_db():
    global _client, _db
    if _db is not None:
        return _db
    uri = os.getenv("MONGO_URI", "")
    if not uri:
        return None
    try:
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        _client.admin.command("ping")
        _db = _client["veda_trader"]
        print("[DB] MongoDB connected ✓")
        return _db
    except ConnectionFailure as e:
        print(f"[DB ERROR] {e}")
        return None

def init_db():
    db = get_db()
    if db is None:
        return
    # Create indexes
    db["signals"].create_index("timestamp")
    db["signals"].create_index("pair")
    db["users"].create_index("email", unique=True)
    db["users"].create_index("telegram_id", sparse=True)
    db["subscribers"].create_index("telegram_id", unique=True)
    print("[DB] Indexes created ✓")

def save_signal_to_db(sig: dict):
    db = get_db()
    if db is None:
        return
    doc = {**sig, "saved_at": datetime.now(timezone.utc)}
    db["signals"].insert_one(doc)

def record_signal_state(pair: str, direction: str):
    db = get_db()
    if db is None:
        return
    db["signal_state"].update_one(
        {"pair": pair},
        {"$set": {"direction": direction, "updated_at": datetime.now(timezone.utc)}},
        upsert=True
    )

def get_last_signal_direction(pair: str) -> str | None:
    db = get_db()
    if db is None:
        return None
    doc = db["signal_state"].find_one({"pair": pair})
    return doc.get("direction") if doc else None

def upsert_bot_status(data: dict):
    db = get_db()
    if db is None:
        return
    db["bot_status"].update_one(
        {"_id": "latest"},
        {"$set": data},
        upsert=True
    )

def log_scan_error(source: str, message: str):
    db = get_db()
    if db is None:
        return
    db["scan_errors"].insert_one({
        "source": source,
        "message": message,
        "timestamp": datetime.now(timezone.utc)
    })

# ── Subscriber Management ────────────────────────────────────

def add_subscriber(telegram_id: str, username: str, tier: str = "free"):
    db = get_db()
    if db is None:
        return False
    db["subscribers"].update_one(
        {"telegram_id": telegram_id},
        {"$set": {
            "telegram_id": telegram_id,
            "username": username,
            "tier": tier,
            "joined_at": datetime.now(timezone.utc),
            "active": True
        }},
        upsert=True
    )
    return True

def upgrade_subscriber(telegram_id: str):
    db = get_db()
    if db is None:
        return False
    result = db["subscribers"].update_one(
        {"telegram_id": telegram_id},
        {"$set": {"tier": "premium", "upgraded_at": datetime.now(timezone.utc)}}
    )
    return result.modified_count > 0

def downgrade_subscriber(telegram_id: str):
    db = get_db()
    if db is None:
        return False
    result = db["subscribers"].update_one(
        {"telegram_id": telegram_id},
        {"$set": {"tier": "free", "downgraded_at": datetime.now(timezone.utc)}}
    )
    return result.modified_count > 0

def remove_subscriber(telegram_id: str):
    db = get_db()
    if db is None:
        return False
    db["subscribers"].update_one(
        {"telegram_id": telegram_id},
        {"$set": {"active": False}}
    )
    return True

def get_all_subscribers(tier: str = None) -> list:
    db = get_db()
    if db is None:
        return []
    query = {"active": True}
    if tier:
        query["tier"] = tier
    return list(db["subscribers"].find(query))

def get_subscriber(telegram_id: str) -> dict | None:
    db = get_db()
    if db is None:
        return None
    return db["subscribers"].find_one({"telegram_id": telegram_id})

def get_daily_stats() -> dict:
    db = get_db()
    if db is None:
        return {}
    from datetime import timedelta
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    signals = list(db["signals"].find({"timestamp": {"$gte": since}}))
    tp_hits = sum(1 for s in signals if s.get("result") == "✅ TP HIT")
    sl_hits = sum(1 for s in signals if s.get("result") == "❌ SL HIT")
    total   = len(signals)
    winrate = round((tp_hits / total * 100), 1) if total else 0
    return {
        "total": total,
        "tp_hits": tp_hits,
        "sl_hits": sl_hits,
        "winrate": winrate,
        "free_subs": len(get_all_subscribers("free")),
        "premium_subs": len(get_all_subscribers("premium")),
    }
