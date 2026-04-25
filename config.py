"""
VEDA TRADER - config.py
All pairs, sessions, and settings in one place.
"""

import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ────────────────────────────────────────────────
TELEGRAM_TOKEN          = os.getenv("TELEGRAM_BOT_TOKEN", "")
FREE_CHANNEL_ID         = os.getenv("FREE_TELEGRAM_CHANNEL_ID", "")
PREMIUM_CHANNEL_ID      = os.getenv("PREMIUM_TELEGRAM_CHANNEL_ID", "")
ADMIN_CHAT_ID           = os.getenv("ADMIN_CHAT_ID", "")          # your personal Telegram ID

# ── App ─────────────────────────────────────────────────────
SECRET_KEY      = os.getenv("SECRET_KEY", "veda-secret-2026")
MONGO_URI       = os.getenv("MONGO_URI", "")
AFFILIATE_LINK  = os.getenv("AFFILIATE_LINK", "#")
ADMIN_USERNAME  = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD  = os.getenv("ADMIN_PASSWORD", "VedaGold2026!")

# ── Sessions (UTC hours) ────────────────────────────────────
SESSIONS = {
    "asian":    {"start": 0,  "end": 8,  "label": "🌏 ASIAN SESSION",    "emoji": "🌏"},
    "london":   {"start": 8,  "end": 16, "label": "🇬🇧 LONDON SESSION",   "emoji": "🇬🇧"},
    "newyork":  {"start": 13, "end": 22, "label": "🗽 NEW YORK SESSION",  "emoji": "🗽"},
}

# Session report times (hour, minute) UTC - send summary near end of session
SESSION_REPORT_TIMES_UTC = {
    (7, 45),   # Asian close report
    (15, 45),  # London close report
    (21, 45),  # NY close report
}

# Session open announcement times UTC
SESSION_OPEN_TIMES_UTC = {
    (0,  0),   # Asian open
    (8,  0),   # London open
    (13, 0),   # NY open
}

def current_session() -> str:
    hour = datetime.now(timezone.utc).hour
    if 13 <= hour < 22:
        return "newyork"
    if 8 <= hour < 16:
        return "london"
    return "asian"

def session_label(sess: str) -> str:
    return SESSIONS.get(sess, {}).get("label", sess.upper())


# ── FREE CHANNEL PAIRS (Forex Scalping - all sessions) ──────
FREE_FOREX_PAIRS = [
    # Majors
    {"name": "EUR/USD", "symbol": "EURUSD=X", "pip": 0.0001, "tier": "public"},
    {"name": "GBP/USD", "symbol": "GBPUSD=X", "pip": 0.0001, "tier": "public"},
    {"name": "USD/JPY", "symbol": "USDJPY=X", "pip": 0.01,   "tier": "public"},
    {"name": "USD/CHF", "symbol": "USDCHF=X", "pip": 0.0001, "tier": "public"},
    {"name": "AUD/USD", "symbol": "AUDUSD=X", "pip": 0.0001, "tier": "public"},
    {"name": "USD/CAD", "symbol": "USDCAD=X", "pip": 0.0001, "tier": "public"},
    {"name": "NZD/USD", "symbol": "NZDUSD=X", "pip": 0.0001, "tier": "public"},
    # Crosses
    {"name": "EUR/GBP", "symbol": "EURGBP=X", "pip": 0.0001, "tier": "public"},
    {"name": "EUR/JPY", "symbol": "EURJPY=X", "pip": 0.01,   "tier": "public"},
    {"name": "GBP/JPY", "symbol": "GBPJPY=X", "pip": 0.01,   "tier": "public"},
]

# ── PREMIUM CHANNEL PAIRS (Forex + Indices + Crypto + Gold) ─
PREMIUM_FOREX_PAIRS = [
    {"name": "EUR/USD", "symbol": "EURUSD=X",  "pip": 0.0001, "tier": "premium"},
    {"name": "GBP/USD", "symbol": "GBPUSD=X",  "pip": 0.0001, "tier": "premium"},
    {"name": "USD/JPY", "symbol": "USDJPY=X",  "pip": 0.01,   "tier": "premium"},
    {"name": "GBP/JPY", "symbol": "GBPJPY=X",  "pip": 0.01,   "tier": "premium"},
    {"name": "EUR/JPY", "symbol": "EURJPY=X",  "pip": 0.01,   "tier": "premium"},
    {"name": "AUD/USD", "symbol": "AUDUSD=X",  "pip": 0.0001, "tier": "premium"},
]

PREMIUM_INDICES = [
    {"name": "US30",    "symbol": "^DJI",   "pip": 1.0,  "tier": "premium"},
    {"name": "SPX500",  "symbol": "^GSPC",  "pip": 0.25, "tier": "premium"},
    {"name": "NAS100",  "symbol": "^IXIC",  "pip": 0.25, "tier": "premium"},
    {"name": "UK100",   "symbol": "^FTSE",  "pip": 0.5,  "tier": "premium"},
    {"name": "GER40",   "symbol": "^GDAXI", "pip": 0.5,  "tier": "premium"},
]

PREMIUM_CRYPTO = [
    {"name": "BTC/USD", "symbol": "BTC-USD", "pip": 1.0,   "tier": "premium"},
    {"name": "ETH/USD", "symbol": "ETH-USD", "pip": 0.1,   "tier": "premium"},
    {"name": "XRP/USD", "symbol": "XRP-USD", "pip": 0.0001,"tier": "premium"},
    {"name": "SOL/USD", "symbol": "SOL-USD", "pip": 0.01,  "tier": "premium"},
]

PREMIUM_COMMODITIES = [
    {"name": "GOLD",    "symbol": "GC=F",   "pip": 0.1,  "tier": "premium"},
    {"name": "SILVER",  "symbol": "SI=F",   "pip": 0.01, "tier": "premium"},
    {"name": "OIL",     "symbol": "CL=F",   "pip": 0.01, "tier": "premium"},
]

ALL_FREE_PAIRS     = FREE_FOREX_PAIRS
ALL_PREMIUM_PAIRS  = (
    PREMIUM_FOREX_PAIRS +
    PREMIUM_INDICES +
    PREMIUM_CRYPTO +
    PREMIUM_COMMODITIES
)

# Set of all forex pair names for easy identification
FOREX_PAIRS = {p["name"] for p in (FREE_FOREX_PAIRS + PREMIUM_FOREX_PAIRS)}

# Session-specific pair filtering
SESSION_PAIRS = {
    "asian":   ["USD/JPY", "AUD/USD", "NZD/USD", "EUR/JPY", "GBP/JPY",
                "BTC/USD", "ETH/USD", "XRP/USD", "SOL/USD"],
    "london":  ["EUR/USD", "GBP/USD", "EUR/GBP", "EUR/JPY", "GBP/JPY",
                "GOLD", "GER40", "UK100"],
    "newyork": ["EUR/USD", "GBP/USD", "USD/CAD", "USD/CHF", "AUD/USD",
                "US30", "SPX500", "NAS100", "OIL", "GOLD"],
}

def pairs_for_session(sess: str, tier: str = "public") -> list:
    """Return pairs active for a session and tier."""
    allowed_names = SESSION_PAIRS.get(sess, [])
    source = ALL_FREE_PAIRS if tier == "public" else ALL_PREMIUM_PAIRS
    # If session list defined, filter; else return all
    if allowed_names:
        filtered = [p for p in source if p["name"] in allowed_names]
        return filtered if filtered else source
    return source

def is_weekend() -> bool:
    now = datetime.now(timezone.utc)
    day = now.weekday()
    # Friday 21:00 UTC to Sunday 21:00 UTC
    if day == 4 and now.hour >= 21: return True
    if day == 5: return True
    if day == 6 and now.hour < 21: return True
    return False

def validate_runtime_config() -> list:
    issues = []
    if not TELEGRAM_TOKEN:    issues.append("⚠ TELEGRAM_BOT_TOKEN not set")
    if not FREE_CHANNEL_ID:   issues.append("⚠ FREE_TELEGRAM_CHANNEL_ID not set")
    if not PREMIUM_CHANNEL_ID:issues.append("⚠ PREMIUM_TELEGRAM_CHANNEL_ID not set")
    if not MONGO_URI:         issues.append("⚠ MONGO_URI not set")
    if not ADMIN_CHAT_ID:     issues.append("⚠ ADMIN_CHAT_ID not set (AI summaries disabled)")
    return issues
