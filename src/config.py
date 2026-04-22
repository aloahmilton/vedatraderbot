import os
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()

# ══════════════════════════════════════════
#  CREDENTIALS
# ══════════════════════════════════════════
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TOKEN_HERE")
CHAT_ID        = os.getenv("TELEGRAM_CHANNEL_ID", "YOUR_CHAT_ID_HERE")
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

# ══════════════════════════════════════════
#  PAIR UNIVERSE
# ══════════════════════════════════════════
ALL_PAIRS = [
    {"name": "EUR/USD", "ticker": "EURUSD=X", "session": "all"},
    {"name": "GBP/USD", "ticker": "GBPUSD=X", "session": "all"},
    {"name": "USD/JPY", "ticker": "USDJPY=X", "session": "all"},
    {"name": "USD/CAD", "ticker": "USDCAD=X", "session": "all"},
    {"name": "AUD/USD", "ticker": "AUDUSD=X", "session": "all"},
    {"name": "NZD/USD", "ticker": "NZDUSD=X", "session": "all"},
    {"name": "USD/CHF", "ticker": "USDCHF=X", "session": "all"},
    {"name": "EUR/GBP", "ticker": "EURGBP=X", "session": "london"},
    {"name": "EUR/JPY", "ticker": "EURJPY=X", "session": "london"},
    {"name": "GBP/JPY", "ticker": "GBPJPY=X", "session": "london"},
    {"name": "EUR/CHF", "ticker": "EURCHF=X", "session": "london"},
    {"name": "GBP/CHF", "ticker": "GBPCHF=X", "session": "london"},
    {"name": "EUR/CAD", "ticker": "EURCAD=X", "session": "newyork"},
    {"name": "GBP/CAD", "ticker": "GBPCAD=X", "session": "newyork"},
    {"name": "CAD/JPY", "ticker": "CADJPY=X", "session": "newyork"},
    {"name": "AUD/JPY", "ticker": "AUDJPY=X", "session": "asian"},
    {"name": "NZD/JPY", "ticker": "NZDJPY=X", "session": "asian"},
    {"name": "AUD/NZD", "ticker": "AUDNZD=X", "session": "asian"},
    
    # 💎 HIGH-VALUE INDICES & COMMODITIES
    {"name": "US30",    "ticker": "^DJI",     "session": "newyork"},
    {"name": "NAS100",  "ticker": "^IXIC",    "session": "newyork"},
    {"name": "GER40",   "ticker": "^GDAXI",   "session": "london"},
    {"name": "GOLD",    "ticker": "GC=F",     "session": "all"},
    {"name": "USOIL",   "ticker": "CL=F",     "session": "newyork"},
    
    # 🚀 PREMIUM STOCKS
    {"name": "NVDA",    "ticker": "NVDA",     "session": "newyork"},
    {"name": "TSLA",    "ticker": "TSLA",     "session": "newyork"},
    {"name": "AAPL",    "ticker": "AAPL",     "session": "newyork"},
    
    # ₿ CRYPTO
    {"name": "BTC/USD", "ticker": "BTC-USD",  "session": "all"},
    {"name": "ETH/USD", "ticker": "ETH-USD",  "session": "all"},
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

def is_dead_hour(pair_name: str) -> bool:
    h = datetime.now(timezone.utc).hour
    if h in DEAD_HOURS_UTC:
        if pair_name in ASIAN_PAIRS: return False
        return True
    return False
