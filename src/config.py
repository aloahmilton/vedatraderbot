import os
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()

# ══════════════════════════════════════════
#  CREDENTIALS
# ══════════════════════════════════════════
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TOKEN_HERE")
CHAT_ID        = os.getenv("FREE_TELEGRAM_CHANNEL_ID", "YOUR_CHAT_ID_HERE")
PUBLIC_CHANNEL_URL = os.getenv("PUBLIC_CHANNEL_URL", "https://t.me/VedaTrader")
MONGO_URI      = os.getenv("MONGO_URI", "")
SECRET_KEY     = os.getenv("SECRET_KEY", "dev_secret_key")

# ══════════════════════════════════════════
#  STRATEGY PARAMETERS
# ══════════════════════════════════════════
TF_SIGNAL  = "5m"
TF_TREND   = "15m"
TF_MAJOR   = "1h"
LOOKBACK   = 3

EMA_FAST   = 9
EMA_SLOW   = 21

RSI_PERIOD   = 14
RSI_BUY_MIN  = 42
RSI_BUY_MAX  = 62
RSI_SELL_MIN = 38
RSI_SELL_MAX = 58

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIG  = 9

ADX_PERIOD  = 14
ADX_MIN     = 20

ATR_PERIOD  = 14
ATR_MIN_BPS = 3.0

BB_PERIOD   = 20
BB_STDDEV   = 2.0
BB_SQUEEZE_THRESHOLD = 0.004

SR_LOOKBACK = 50
SR_PROXIMITY = 0.002

RISK_REWARD   = 2.0
STOP_PERCENT  = 0.3
EXPIRY_MINUTES = 5
DEDUPE_MIN    = 15

DEAD_HOURS_UTC = [0, 1, 2, 3, 4, 5]
ASIAN_PAIRS    = ["AUD/JPY", "NZD/JPY", "AUD/NZD", "USD/JPY", "AUD/USD", "NZD/USD"]
MIN_BODY_ATR_RATIO = 0.3
EMA_MAJOR_PERIOD = 200 # For HTF trend check
VOL_EMA_PERIOD = 20    # For volume confirmation
GOLD_SCORE_THRESHOLD = 85
SIGNAL_MIN_SCORE = 60
EMA_SPREAD_MIN = 0.00015
VOLUME_CONFIRM_MULTIPLIER = 1.05
RSI_MIDPOINT_BUY = 52
RSI_MIDPOINT_SELL = 48
PREMIUM_SIGNAL_MIN_SCORE = 70
ADX_STRONG_MIN = 24
TREND_SPREAD_STRONG_MIN = 0.00035
EMA_PULLBACK_MAX = 0.0016
WICK_RATIO_MAX = 1.35
SESSION_REPORT_TIMES_UTC = [(6, 55), (15, 55), (20, 55)]

# ══════════════════════════════════════════
#  PAIR UNIVERSE
# ══════════════════════════════════════════
ALL_PAIRS = [
    {"name": "EUR/USD", "ticker": "EURUSD=X", "session": "all", "tier": "public",  "category": "forex"},
    {"name": "GBP/USD", "ticker": "GBPUSD=X", "session": "all", "tier": "public",  "category": "forex"},
    {"name": "USD/JPY", "ticker": "USDJPY=X", "session": "all", "tier": "public",  "category": "forex"},
    {"name": "USD/CAD", "ticker": "USDCAD=X", "session": "all", "tier": "public",  "category": "forex"},
    {"name": "AUD/USD", "ticker": "AUDUSD=X", "session": "all", "tier": "public",  "category": "forex"},
    {"name": "NZD/USD", "ticker": "NZDUSD=X", "session": "all", "tier": "public",  "category": "forex"},
    {"name": "USD/CHF", "ticker": "USDCHF=X", "session": "all", "tier": "public",  "category": "forex"},
    {"name": "EUR/GBP", "ticker": "EURGBP=X", "session": "london", "tier": "public", "category": "forex"},
    {"name": "EUR/JPY", "ticker": "EURJPY=X", "session": "london", "tier": "public", "category": "forex"},
    {"name": "GBP/JPY", "ticker": "GBPJPY=X", "session": "london", "tier": "public", "category": "forex"},
    {"name": "EUR/CHF", "ticker": "EURCHF=X", "session": "london", "tier": "public", "category": "forex"},
    {"name": "GBP/CHF", "ticker": "GBPCHF=X", "session": "london", "tier": "public", "category": "forex"},
    {"name": "EUR/CAD", "ticker": "EURCAD=X", "session": "newyork", "tier": "public", "category": "forex"},
    {"name": "GBP/CAD", "ticker": "GBPCAD=X", "session": "newyork", "tier": "public", "category": "forex"},
    {"name": "CAD/JPY", "ticker": "CADJPY=X", "session": "newyork", "tier": "public", "category": "forex"},
    {"name": "AUD/JPY", "ticker": "AUDJPY=X", "session": "asian", "tier": "public", "category": "forex"},
    {"name": "NZD/JPY", "ticker": "NZDJPY=X", "session": "asian", "tier": "public", "category": "forex"},
    {"name": "AUD/NZD", "ticker": "AUDNZD=X", "session": "asian", "tier": "public", "category": "forex"},
    
    # 💎 PREMIUM ASSETS
    {"name": "US30",    "ticker": "^DJI",     "session": "newyork", "tier": "premium", "category": "indices"},
    {"name": "US500",   "ticker": "^GSPC",    "session": "newyork", "tier": "premium", "category": "indices"},
    {"name": "NAS100",  "ticker": "^NDX",     "session": "newyork", "tier": "premium", "category": "indices"},
    {"name": "GER40",   "ticker": "^GDAXI",   "session": "london",  "tier": "premium", "category": "indices"},
    {"name": "GOLD",    "ticker": "GC=F",     "session": "all",     "tier": "premium", "category": "commodities"},
    {"name": "SILVER",  "ticker": "SI=F",     "session": "all",     "tier": "premium", "category": "commodities"},
    {"name": "USOIL",   "ticker": "CL=F",     "session": "newyork", "tier": "premium", "category": "commodities"},
    {"name": "BRENT",   "ticker": "BZ=F",     "session": "london",  "tier": "premium", "category": "commodities"},
    {"name": "NVDA",    "ticker": "NVDA",     "session": "newyork", "tier": "premium", "category": "stocks"},
    {"name": "TSLA",    "ticker": "TSLA",     "session": "newyork", "tier": "premium", "category": "stocks"},
    {"name": "AAPL",    "ticker": "AAPL",     "session": "newyork", "tier": "premium", "category": "stocks"},
    {"name": "MSFT",    "ticker": "MSFT",     "session": "newyork", "tier": "premium", "category": "stocks"},
    {"name": "META",    "ticker": "META",     "session": "newyork", "tier": "premium", "category": "stocks"},
    {"name": "AMD",     "ticker": "AMD",      "session": "newyork", "tier": "premium", "category": "stocks"},
    {"name": "BTC/USD", "ticker": "BTC-USD",  "session": "all",     "tier": "premium", "category": "crypto"},
    {"name": "ETH/USD", "ticker": "ETH-USD",  "session": "all",     "tier": "premium", "category": "crypto"},
    {"name": "SOL/USD", "ticker": "SOL-USD",  "session": "all",     "tier": "premium", "category": "crypto"},
]

# ══════════════════════════════════════════
#  SESSION LOGIC
# ══════════════════════════════════════════
def current_session() -> str:
    h = datetime.now(timezone.utc).hour
    if 12 <= h < 16: return "overlap"
    if 7  <= h < 16: return "london"
    if 16 <= h < 21: return "newyork"
    return "asian"

def session_label(s: str) -> str:
    return {
        "overlap":  "🔥 London/NY Overlap",
        "london":   "🇬🇧 London Session",
        "newyork":  "🇺🇸 New York Session",
        "asian":    "🌏 Asian Session",
    }.get(s, s)

def pairs_for_session(s: str) -> list:
    tag = "london" if s == "overlap" else s
    return [p for p in ALL_PAIRS if p["session"] in ("all", tag)]

def public_pairs_for_session(s: str) -> list:
    return [p for p in pairs_for_session(s) if p.get("tier") == "public" and p.get("category") == "forex"]

def premium_pairs_for_session(s: str) -> list:
    return [p for p in pairs_for_session(s) if p.get("tier") == "premium"]

def premium_crypto_pairs() -> list:
    return [p for p in ALL_PAIRS if p.get("tier") == "premium" and p.get("category") == "crypto"]

def is_dead_hour(pair_name: str) -> bool:
    h = datetime.now(timezone.utc).hour
    if h in DEAD_HOURS_UTC:
        if pair_name in ASIAN_PAIRS: return False
        return True
    return False

def validate_runtime_config() -> list[str]:
    """Return configuration issues that would break delivery/runtime."""
    issues = []
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN in ("YOUR_TOKEN_HERE", "YOUR_TELEGRAM_TOKEN"):
        issues.append("TELEGRAM_BOT_TOKEN is missing or still placeholder.")
    if not CHAT_ID or CHAT_ID in ("YOUR_CHAT_ID_HERE", "YOUR_CHANNEL_ID"):
        issues.append("FREE_TELEGRAM_CHANNEL_ID is missing or still placeholder.")
    if not MONGO_URI:
        issues.append("MONGO_URI is not set (signals will not persist).")
    return issues
