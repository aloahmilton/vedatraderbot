import os
from .config import GOLD_SCORE_THRESHOLD

# Gold Chat ID can be set via env or hardcoded here if needed
PREMIUM_CHANNEL_ID = os.getenv("PREMIUM_TELEGRAM_CHANNEL_ID", os.getenv("PREMIUM_CHANNEL_ID", None))
PREMIUM_ENABLED = PREMIUM_CHANNEL_ID is not None and PREMIUM_CHANNEL_ID not in ("your_PREMIUM_TELEGRAM_CHANNEL_ID_here", "your_PREMIUM_CHANNEL_ID_here", None)

def gold_signal_check(rsi, adx, hist, bb_pos, score):
    """
    Ultra-strict logic for 'Best of the Best' signals.
    - Score must be above threshold (85+)
    - Strong trend (ADX > 30)
    - RSI in the sweet spot (45-55)
    - Momentum (hist) must be significant
    """
    if score < GOLD_SCORE_THRESHOLD:
        return False
    
    # Extra filters for 'Gold' status
    if adx < 30: return False
    if not (42 <= rsi <= 58): return False
    if abs(hist) < 0.0001: return False
    
    return True

def get_gold_stats():
    """Real membership stats from DB."""
    from .database import get_db
    db = get_db()
    if db is not None:
        active = db["users"].count_documents({"active": True})
        return active, 0
    return 0, 0

def add_gold_user(user_id, days, admin_username):
    """Save premium user to DB."""
    from .database import add_premium_user
    return add_premium_user(user_id, days, admin_username)

def is_gold_user(user_id):
    """Check if a specific user has active premium access in DB."""
    from .database import get_premium_user
    user = get_premium_user(user_id)
    if not user: return False
    
    # Check expiry
    from datetime import datetime, timezone
    if user.get("expiry") and user["expiry"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return False
    
    return user.get("active", False)
