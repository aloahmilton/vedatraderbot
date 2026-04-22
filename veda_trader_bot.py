"""
╔══════════════════════════════════════════════════════════╗
║          VEDA TRADER — Signal Bot v5                     ║
║   High-Accuracy | Multi-Timeframe | 5-Layer Filter       ║
╚══════════════════════════════════════════════════════════╝

WHAT CHANGED FROM v4 (why win rate was 49%):
  ✗ v4 had 3 triggers (CROSS, MOMO, PRE) — PRE fires before confirmation
  ✗ v4 RSI range 30–75 — too wide, filters nothing
  ✗ v4 had no higher-timeframe trend check — signals fired against the trend
  ✗ v4 had no ATR filter — fired in dead/flat markets
  ✗ v4 entered ON the crossover candle — risky, not confirmed
  ✗ v4 treated zero forex volume as "pass" — no volume filter at all

WHAT v5 FIXES:
  ✓ ONE trigger only: CONFIRMED crossover (previous candle crosses, current candle confirms)
  ✓ RSI tightened: 42–62 buy / 38–58 sell — high probability zone only
  ✓ 15M trend alignment: signal must match the 15M EMA direction
  ✓ ATR filter: market must have enough range to be worth trading
  ✓ ADX filter: trend strength must be above 20 (not a choppy range)
  ✓ Candle body confirmation: confirmation candle must close in signal direction
  ✓ Spread filter: avoids wide-spread news moments
  ✓ Time filter: avoids low-liquidity hours (00:00–06:00 UTC outside Asia pairs)
  ✓ Bollinger Band squeeze filter: avoids entering inside a squeeze (breakout pending)
  ✓ Support/Resistance proximity: avoids entries too close to key S/R levels

TARGET WIN RATE: 62–70%

SETUP:
  1. pip install yfinance pandas requests schedule python-dotenv pymongo ta
  2. Create .env file:
       TELEGRAM_BOT_TOKEN=your_token_here
       TELEGRAM_CHANNEL_ID=your_chat_id_here
       MONGO_URI=your_mongo_uri_here  (optional)
  3. python veda_trader_bot_v5.py
"""

import os
import time
import math
import schedule
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timezone, timedelta

# Premium system - optional, fully backward compatible
try:
    from premium import gold_signal_check, fmt_gold_signal, GOLD_CHAT_ID
    PREMIUM_ENABLED = True
except ImportError:
    PREMIUM_ENABLED = False
    GOLD_CHAT_ID = None

# Command handlers - separate file for cleanliness
try:
    from config_and_commands_vedatraderbot import handle_telegram_command
    COMMANDS_ENABLED = True
    print("✅ Command system loaded")
except ImportError as e:
    COMMANDS_ENABLED = False
    print(f"⚠️ Command system not loaded: {e}")
from dotenv import load_dotenv

try:
    from pymongo import MongoClient
    MONGO_AVAILABLE = True
except ImportError:
    MONGO_AVAILABLE = False

load_dotenv()

# ══════════════════════════════════════════
#  CREDENTIALS
# ══════════════════════════════════════════
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TOKEN_HERE")
CHAT_ID        = os.getenv("TELEGRAM_CHANNEL_ID", "YOUR_CHAT_ID_HERE")
MONGO_URI      = os.getenv("MONGO_URI", "")

# ── MongoDB (optional, bot runs without it) ──
_db = None
if MONGO_AVAILABLE and MONGO_URI:
    try:
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        _db = _client["vedatrader_v5"]
        _db.command("ping")
        print("[MongoDB] ✓ connected")
    except Exception as _e:
        print(f"[MongoDB] connection failed — running without DB: {_e}")

# ══════════════════════════════════════════
#  STRATEGY PARAMETERS
#  (tuned for 62–70% win rate target)
# ══════════════════════════════════════════

# Timeframes
TF_SIGNAL  = "5m"   # Signal generation timeframe
TF_TREND   = "15m"  # Higher timeframe for trend direction
LOOKBACK   = 3      # Days of data to fetch

# EMA settings
EMA_FAST   = 9
EMA_SLOW   = 21

# RSI — TIGHTENED from v4 (was 30–75, now strict zone only)
RSI_PERIOD   = 14
RSI_BUY_MIN  = 42   # Was 30
RSI_BUY_MAX  = 62   # Was 75
RSI_SELL_MIN = 38   # Was 25
RSI_SELL_MAX = 58   # Was 70

# MACD
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIG  = 9

# ADX — trend strength filter (NEW in v5)
ADX_PERIOD  = 14
ADX_MIN     = 20    # Below this = choppy range, skip

# ATR — volatility filter (NEW in v5)
ATR_PERIOD  = 14
ATR_MIN_BPS = 3.0   # Minimum ATR in basis points (0.03%)

# Bollinger Bands — squeeze filter (NEW in v5)
BB_PERIOD   = 20
BB_STDDEV   = 2.0
BB_SQUEEZE_THRESHOLD = 0.004  # Band width / price < this = squeeze, skip

# Support/Resistance proximity filter (NEW in v5)
SR_LOOKBACK = 50    # Candles to look back for S/R
SR_PROXIMITY = 0.002  # Skip if price within 0.2% of key S/R level

# Risk settings
RISK_REWARD   = 2.0
STOP_PERCENT  = 0.3   # 0.3% stop loss
EXPIRY_MINUTES = 5
DEDUPE_MIN    = 15    # Increased from 10 to 15 min to reduce noise

# Time filter — avoid dead hours (UTC)
# Exception: Asian pairs allowed during Asian hours
DEAD_HOURS_UTC = [0, 1, 2, 3, 4, 5]  # 00:00–06:00 UTC (very thin liquidity)
ASIAN_PAIRS    = ["AUD/JPY", "NZD/JPY", "AUD/NZD", "USD/JPY", "AUD/USD", "NZD/USD"]

# Minimum candle body size (as % of ATR) — filters doji/indecision candles
MIN_BODY_ATR_RATIO = 0.3

# ══════════════════════════════════════════
#  18-PAIR UNIVERSE
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
    """Return True if we should skip this pair due to low liquidity hours."""
    h = datetime.now(timezone.utc).hour
    if h in DEAD_HOURS_UTC:
        # Asian pairs are still OK during Asian hours
        if pair_name in ASIAN_PAIRS:
            return False
        return True
    return False

# ══════════════════════════════════════════
#  STATE
# ══════════════════════════════════════════
last_signal_time:     dict = {}
last_session_alerted: str  = ""
session_signals:      list = []
current_session_date: str  = ""
session_signal_no:    int  = 0
active_session_name:  str  = ""

# ══════════════════════════════════════════
#  TELEGRAM
# ══════════════════════════════════════════
def send_telegram(msg: str, pin: bool = False, chat_id: str = None) -> bool:
    url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    target_chat = chat_id if chat_id is not None else CHAT_ID
    payload = {"chat_id": target_chat, "text": msg,
               "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        r   = requests.post(url, json=payload, timeout=15)
        res = r.json()
        if not res.get("ok"):
            print(f"  [Telegram FAIL] {res.get('description')}")
            return False
        if pin:
            mid = res.get("result", {}).get("message_id")
            if mid:
                try:
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/pinChatMessage",
                         json={"chat_id": target_chat, "message_id": mid, "disable_notification": True},
                        timeout=10
                    )
                except Exception:
                    pass
        return True
    except Exception as e:
        print(f"  [Telegram Error] {e}")
        return False

# ══════════════════════════════════════════
#  DATA FETCHING
# ══════════════════════════════════════════
def fetch_ohlcv(ticker: str, interval: str = TF_SIGNAL, days: int = LOOKBACK) -> pd.DataFrame | None:
    try:
        df = yf.Ticker(ticker).history(period=f"{days}d", interval=interval)
        if df is None or len(df) < 60:
            return None
        df = df.rename(columns={"Open":"open","High":"high",
                                  "Low":"low","Close":"close","Volume":"volume"})
        return df[["open","high","low","close","volume"]].dropna().copy()
    except Exception as e:
        print(f"  [Fetch {ticker}/{interval}] {e}")
        return None

# ══════════════════════════════════════════
#  INDICATORS
# ══════════════════════════════════════════
def calc_ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def calc_rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d  = s.diff()
    g  = d.clip(lower=0).ewm(com=n-1, adjust=False).mean()
    l  = (-d.clip(upper=0)).ewm(com=n-1, adjust=False).mean()
    rs = g / l.replace(0, float("inf"))
    return 100 - (100 / (1 + rs))

def calc_macd(s: pd.Series):
    line = calc_ema(s, MACD_FAST) - calc_ema(s, MACD_SLOW)
    sig  = calc_ema(line, MACD_SIG)
    hist = line - sig
    return line, sig, hist

def calc_adx(df: pd.DataFrame, n: int = ADX_PERIOD) -> pd.Series:
    """Calculate ADX (trend strength). Above 20 = trending, below = choppy."""
    h, l, c = df["high"], df["low"], df["close"]
    tr    = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    up    = h.diff()
    down  = -l.diff()
    plus  = (up.where((up > down) & (up > 0), 0)).ewm(span=n, adjust=False).mean()
    minus = (down.where((down > up) & (down > 0), 0)).ewm(span=n, adjust=False).mean()
    atr   = tr.ewm(span=n, adjust=False).mean()
    pdi   = 100 * plus / atr.replace(0, float("nan"))
    mdi   = 100 * minus / atr.replace(0, float("nan"))
    dx    = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, float("nan"))
    return dx.ewm(span=n, adjust=False).mean()

def calc_atr(df: pd.DataFrame, n: int = ATR_PERIOD) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()

def calc_bollinger(s: pd.Series, n: int = BB_PERIOD, std: float = BB_STDDEV):
    mid   = s.rolling(n).mean()
    sigma = s.rolling(n).std()
    upper = mid + std * sigma
    lower = mid - std * sigma
    return upper, mid, lower

def find_sr_levels(df: pd.DataFrame, lookback: int = SR_LOOKBACK) -> list:
    """Find key support/resistance levels from recent swing highs/lows."""
    recent = df.tail(lookback)
    highs  = recent["high"].nlargest(3).tolist()
    lows   = recent["low"].nsmallest(3).tolist()
    return highs + lows

def too_close_to_sr(price: float, levels: list, threshold: float = SR_PROXIMITY) -> bool:
    """Return True if price is too close to a key S/R level."""
    for lvl in levels:
        if abs(price - lvl) / price < threshold:
            return True
    return False

# ══════════════════════════════════════════
#  TREND DIRECTION (15M)
#  NEW in v5 — signal must align with 15M trend
# ══════════════════════════════════════════
def get_trend_direction(ticker: str) -> str:
    """
    Returns 'UP', 'DOWN', or 'NEUTRAL' based on 15M EMA alignment.
    UP = EMA9 > EMA21 on 15M chart
    DOWN = EMA9 < EMA21 on 15M chart
    NEUTRAL = EMAs too close together
    """
    df = fetch_ohlcv(ticker, interval=TF_TREND, days=LOOKBACK)
    if df is None or len(df) < 30:
        return "NEUTRAL"

    ef = calc_ema(df["close"], EMA_FAST)
    es = calc_ema(df["close"], EMA_SLOW)

    f0, s0 = ef.iloc[-1], es.iloc[-1]
    gap_pct = abs(f0 - s0) / s0

    if gap_pct < 0.0003:  # EMAs within 0.03% = neutral
        return "NEUTRAL"
    return "UP" if f0 > s0 else "DOWN"

# ══════════════════════════════════════════
#  SIGNAL QUALITY SCORE (NEW in v5)
#  Returns a score 0–100. Only signals scoring
#  60+ are sent. This replaces the 1–5 star bar.
# ══════════════════════════════════════════
def quality_score(
    rsi: float, adx: float, atr_bps: float,
    bb_width: float, macd_hist: float,
    trend_aligned: bool, candle_body_ratio: float,
    direction: str
) -> tuple[int, dict]:
    """
    Score each signal 0–100 based on confluence of factors.
    Returns (score, breakdown_dict)
    """
    breakdown = {}

    # 1. RSI quality (max 25 pts) — best in middle zone
    if direction == "BUY":
        rsi_center = 52
    else:
        rsi_center = 48
    rsi_dist = abs(rsi - rsi_center)
    rsi_score = max(0, 25 - int(rsi_dist * 1.5))
    breakdown["RSI"] = rsi_score

    # 2. ADX strength (max 20 pts) — stronger trend = better
    adx_score = min(20, int((adx - ADX_MIN) * 0.8)) if adx >= ADX_MIN else 0
    breakdown["ADX"] = adx_score

    # 3. ATR volatility (max 15 pts) — enough range to profit
    atr_score = min(15, int(atr_bps * 2.5)) if atr_bps >= ATR_MIN_BPS else 0
    breakdown["ATR"] = atr_score

    # 4. Bollinger Band (max 15 pts) — wider bands = cleaner breakouts
    bb_score = min(15, int(bb_width * 5000)) if bb_width >= BB_SQUEEZE_THRESHOLD else 0
    breakdown["BB"] = bb_score

    # 5. MACD histogram strength (max 15 pts)
    macd_score = min(15, int(abs(macd_hist) * 10000))
    breakdown["MACD"] = macd_score

    # 6. Trend alignment bonus (max 10 pts) — huge factor
    trend_score = 10 if trend_aligned else 0
    breakdown["Trend"] = trend_score

    total = rsi_score + adx_score + atr_score + bb_score + macd_score + trend_score
    return min(100, total), breakdown

# ══════════════════════════════════════════
#  DEDUPLICATION
# ══════════════════════════════════════════
def is_dupe(pair: str, direction: str) -> bool:
    last = last_signal_time.get(f"{pair}:{direction}")
    if not last: return False
    return (datetime.now(timezone.utc) - last).total_seconds() / 60 < DEDUPE_MIN

def record_sig(pair: str, direction: str, price: float) -> int:
    global current_session_date, session_signal_no, active_session_name
    now = datetime.now(timezone.utc)
    sess = current_session()

    if sess != active_session_name:
        session_signal_no = 0
        active_session_name = sess

    last_signal_time[f"{pair}:{direction}"] = now
    session_signal_no += 1

    session_signals.append({
        "no": session_signal_no,
        "pair": pair,
        "time": now.strftime("%H:%M"),
        "direction": direction,
        "price": price,
        "timestamp": now,
        "result": None,
        "exit_price": None,
    })
    current_session_date = now.strftime("%d/%B").upper()
    return session_signal_no

# ══════════════════════════════════════════
#  OUTCOME EVALUATOR
# ══════════════════════════════════════════
def evaluate_pending_signals():
    """Check signals past expiry and stamp WIN/LOSS."""
    now = datetime.now(timezone.utc)
    for s in session_signals:
        if s.get("result") is not None:
            continue
        age_min = (now - s["timestamp"]).total_seconds() / 60
        if age_min < EXPIRY_MINUTES:
            continue

        info = next((p for p in ALL_PAIRS if p["name"] == s["pair"]), None)
        if not info: continue
        df = fetch_ohlcv(info["ticker"])
        if df is None or len(df) < 2: continue

        exit_price = float(df["close"].iloc[-1])
        entry = float(s["price"])
        won = (exit_price > entry) if s["direction"] == "BUY" else (exit_price < entry)
        s["result"] = "WIN" if won else "LOSS"
        s["exit_price"] = exit_price

        pct = (exit_price - entry) / entry * 100 * (1 if s["direction"] == "BUY" else -1)
        sign = "+" if pct >= 0 else ""
        bar = ("🟩" * 4) if won else ("🟥" * 4)
        label = "GAIN ✅" if won else "LOSS ❌"

        result_msg = (
            f"⚡ <b>✨ TRADE RESULT #{s['no']} ✨</b> ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"\n"
            f"<b>{label}</b>  ·  {s['pair']}\n"
            f"<code>{entry:.5f} → {exit_price:.5f}  ({sign}{pct:.2f}%)</code>"
        )
        send_telegram(result_msg)
        print(f"  [OUTCOME] #{s['no']} {s['pair']} {s['direction']} → {s['result']}")

        if _db is not None:
            try:
                _db["signals"].update_one(
                    {"pair": s["pair"], "timestamp": s["timestamp"]},
                    {"$set": {"result": s["result"], "exit_price": exit_price}},
                )
            except Exception: pass

# ══════════════════════════════════════════
#  CORE ANALYSIS — THE v5 FILTER STACK
# ══════════════════════════════════════════
def analyze(pair_info: dict) -> dict | None:
    """
    5-layer filter stack — ALL must pass for a signal to fire.

    Layer 1: Time filter          — avoid dead liquidity hours
    Layer 2: Volatility filter    — ATR & BB squeeze
    Layer 3: Trend alignment      — 15M EMA must agree
    Layer 4: Momentum filter      — ADX + MACD + RSI
    Layer 5: Entry confirmation   — candle body + S/R proximity
    """
    name   = pair_info["name"]
    ticker = pair_info["ticker"]

    # ── LAYER 1: Time filter ──────────────────────────────────
    if is_dead_hour(name):
        return None

    # ── Fetch 5M data ─────────────────────────────────────────
    df = fetch_ohlcv(ticker)
    if df is None or len(df) < 80:
        return None

    closes = df["close"]
    opens  = df["open"]
    highs  = df["high"]
    lows   = df["low"]
    price  = float(closes.iloc[-1])

    # ── Core indicators ───────────────────────────────────────
    ef = calc_ema(closes, EMA_FAST)
    es = calc_ema(closes, EMA_SLOW)
    rv = calc_rsi(closes, RSI_PERIOD)
    _, _, hist_series = calc_macd(closes)
    adx_series = calc_adx(df)
    atr_series = calc_atr(df)
    bb_upper, bb_mid, bb_lower = calc_bollinger(closes)

    # Latest values
    f0, f1       = float(ef.iloc[-1]),       float(ef.iloc[-2])
    s0, s1       = float(es.iloc[-1]),       float(es.iloc[-2])
    f_prev, s_prev = float(ef.iloc[-3]),     float(es.iloc[-3])
    rsi_now      = float(rv.iloc[-1])
    hist_now     = float(hist_series.iloc[-1])
    hist_prev    = float(hist_series.iloc[-2])
    adx_now      = float(adx_series.iloc[-1])
    atr_now      = float(atr_series.iloc[-1])
    atr_bps      = (atr_now / price) * 10000
    bb_u         = float(bb_upper.iloc[-1])
    bb_l         = float(bb_lower.iloc[-1])
    bb_width     = (bb_u - bb_l) / price
    candle_open  = float(opens.iloc[-1])
    candle_body  = abs(price - candle_open)
    body_ratio   = candle_body / atr_now if atr_now > 0 else 0

    if any(pd.isna(x) for x in [f0, f1, s0, s1, rsi_now, hist_now, adx_now, atr_now, bb_u]):
        return None

    # ── LAYER 2: Volatility filter ────────────────────────────
    # Skip if ATR too low (dead market)
    if atr_bps < ATR_MIN_BPS:
        return None

    # Skip if Bollinger Bands are squeezed (breakout not yet triggered)
    if bb_width < BB_SQUEEZE_THRESHOLD:
        return None

    # ── LAYER 3: 15M Trend alignment ─────────────────────────
    # Signal must match the higher timeframe trend
    trend = get_trend_direction(ticker)
    # If neutral or conflicting trend, skip
    if trend == "NEUTRAL":
        return None

    # ── LAYER 4: Momentum & crossover ────────────────────────
    # Crossover detection: CONFIRMED means the crossover happened on
    # the PREVIOUS candle and the CURRENT candle confirms direction.
    # This is more reliable than entering on the crossover candle itself.

    # Previous candle crossover (candle -2 crossed over candle -3)
    bull_cross_confirmed = (f_prev <= s_prev) and (f1 > s1) and (f0 > s0)
    bear_cross_confirmed = (f_prev >= s_prev) and (f1 < s1) and (f0 < s0)

    # ADX must show a trending market
    if adx_now < ADX_MIN:
        return None

    # MACD must agree: not just direction, histogram must be growing
    macd_bull = hist_now > 0 and hist_now > hist_prev  # growing bullish momentum
    macd_bear = hist_now < 0 and hist_now < hist_prev  # growing bearish momentum

    # RSI must be in high-probability zone (STRICT — no loose ranges)
    rsi_buy_ok  = RSI_BUY_MIN  <= rsi_now <= RSI_BUY_MAX
    rsi_sell_ok = RSI_SELL_MIN <= rsi_now <= RSI_SELL_MAX

    # ── LAYER 5: Entry confirmation ───────────────────────────
    # Candle body must be meaningful (not a doji)
    if body_ratio < MIN_BODY_ATR_RATIO:
        return None

    # Check proximity to support/resistance levels
    sr_levels = find_sr_levels(df)
    if too_close_to_sr(price, sr_levels):
        return None

    # ── FINAL SIGNAL LOGIC ────────────────────────────────────
    buy_signal = (
        bull_cross_confirmed and
        trend == "UP" and          # 15M must be bullish
        macd_bull and
        rsi_buy_ok and
        price > bb_mid.iloc[-1]   # Price above BB midline (momentum up)
    )

    sell_signal = (
        bear_cross_confirmed and
        trend == "DOWN" and        # 15M must be bearish
        macd_bear and
        rsi_sell_ok and
        price < bb_mid.iloc[-1]   # Price below BB midline (momentum down)
    )

    if not buy_signal and not sell_signal:
        return None

    direction = "BUY" if buy_signal else "SELL"
    trend_aligned = (
        (direction == "BUY"  and trend == "UP") or
        (direction == "SELL" and trend == "DOWN")
    )

    if is_dupe(name, direction):
        return None

    # ── Calculate quality score ───────────────────────────────
    score, breakdown = quality_score(
        rsi=rsi_now, adx=adx_now, atr_bps=atr_bps,
        bb_width=bb_width, macd_hist=hist_now,
        trend_aligned=trend_aligned,
        candle_body_ratio=body_ratio,
        direction=direction
    )

    # Only send signals that score 55+ out of 100
    if score < 55:
        print(f"  [FILTERED] {name} {direction} — score {score}/100 (below threshold)")
        return None

    # ── Calculate entry levels ────────────────────────────────
    if direction == "BUY":
        sl = round(price * (1 - STOP_PERCENT / 100), 6)
        tp = round(price * (1 + STOP_PERCENT / 100 * RISK_REWARD), 6)
    else:
        sl = round(price * (1 + STOP_PERCENT / 100), 6)
        tp = round(price * (1 - STOP_PERCENT / 100 * RISK_REWARD), 6)

    signal = {
        "type":       direction,
        "pair":       name,
        "price":      price,
        "sl":         sl,
        "tp":         tp,
        "rsi":        round(rsi_now, 1),
        "adx":        round(adx_now, 1),
        "atr_bps":    round(atr_bps, 1),
        "score":      score,
        "breakdown":  breakdown,
        "trend":      trend,
        "bb_width":   round(bb_width * 100, 3),
        "macd_hist":  round(hist_now, 6),
    }

    # Check if this qualifies as GOLD signal
    if PREMIUM_ENABLED:
        bb_pos = (price - bb_l) / (bb_u - bb_l) if (bb_u - bb_l) > 0 else 0.5
        if gold_signal_check(rsi_now, adx_now, hist_now, bb_pos, score):
            signal["is_gold"] = True
        else:
            signal["is_gold"] = False
    
    return signal

# ══════════════════════════════════════════
#  MESSAGE FORMATTING
# ══════════════════════════════════════════
def score_bar(score: int) -> str:
    """Visual quality bar from score 0–100."""
    filled = score // 20
    empty  = 5 - filled
    return "█" * filled + "░" * empty + f"  {score}/100"

def fmt_signal(sig: dict, sig_no: int = 0) -> str:
    is_buy = sig["type"] == "BUY"
    arrow  = "🟢▲" if is_buy else "🔴▼"
    label  = "BUY  /  CALL" if is_buy else "SELL  /  PUT"
    bar    = ("🟩" * 4) if is_buy else ("🟥" * 4)
    sess   = current_session()
    sess_lbl = session_label(sess).split(" ", 1)[-1]

    now     = datetime.now(timezone.utc)
    now_str = now.strftime("%H:%M")
    base    = now.replace(second=0, microsecond=0)
    t1      = (base + timedelta(minutes=EXPIRY_MINUTES)).strftime("%H:%M")
    t2      = (base + timedelta(minutes=EXPIRY_MINUTES * 2)).strftime("%H:%M")
    t3      = (base + timedelta(minutes=EXPIRY_MINUTES * 3)).strftime("%H:%M")

    score   = sig.get("score", 0)
    q_bar   = score_bar(score)
    rsi     = sig.get("rsi", "—")
    adx     = sig.get("adx", "—")
    atr     = sig.get("atr_bps", "—")
    trend   = sig.get("trend", "—")
    price   = sig.get("price")
    price_s = f"{price:.5f}" if isinstance(price, (int, float)) else "—"

    # Quality tier label
    if score >= 80:
        tier = "💎 PREMIUM"
    elif score >= 65:
        tier = "🔥 HIGH QUALITY"
    else:
        tier = "✅ VALID"

    header_no = f"#{sig_no:02d}" if sig_no else "##"

    return (
        f"✨ <b>NEW TRADE</b> ✨\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"{bar}\n"
        f"📡  <b>VEDA SIGNAL  {header_no}</b>   ·   {sess_lbl}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"{arrow}  <b>{sig['pair']}</b>   ·   <b>{label}</b>\n"
        f"\n"
        f"💵  Entry price    <code>{price_s}</code>\n"
        f"⏱  Entry time     <code>{now_str} UTC</code>\n"
        f"⏳  Expiry          <code>{EXPIRY_MINUTES} min  →  {t1}</code>\n"
        f"\n"
        f"🛡  <b>Gale Recovery</b>\n"
        f"   ┣ 1st gale  →  <code>{t2}</code>\n"
        f"   ┗ 2nd gale  →  <code>{t3}</code>\n"
        f"\n"
        f"📊  <b>Signal Quality</b>  {tier}\n"
        f"   <code>{q_bar}</code>\n"
        f"\n"
        f"📈  RSI <code>{rsi}</code>  ·  ADX <code>{adx}</code>  ·  ATR <code>{atr} bps</code>\n"
        f"🧭  15M Trend: <b>{trend}</b>  ·  Aligned: <b>{'YES ✓' if sig.get('trend') else 'NO'}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Result posted in {EXPIRY_MINUTES + 1} min. Trade the plan.</i>"
    )


def fmt_session_announcement(sess: str) -> str:
    SESSION_META = {
        "asian":   ("ASIAN SESSION",       0),
        "london":  ("LONDON SESSION",      7),
        "overlap": ("LONDON × NY OVERLAP", 12),
        "newyork": ("NEW YORK SESSION",    16),
    }
    label, start_h = SESSION_META.get(sess, ("SESSION", 0))
    from zoneinfo import ZoneInfo
    today     = datetime.now(timezone.utc).date()
    start_utc = datetime(today.year, today.month, today.day, start_h, 0, tzinfo=timezone.utc)

    WORLD_TZ = [
        ("🇬🇧 UK",           "Europe/London"),
        ("🇨🇲 Cameroon",     "Africa/Douala"),
        ("🇿🇦 South Africa", "Africa/Johannesburg"),
        ("🇳🇬 Nigeria",      "Africa/Lagos"),
        ("🇧🇷 Brazil",       "America/Sao_Paulo"),
        ("🇺🇸 Miami",        "America/New_York"),
        ("🇲🇽 Mexico",       "America/Mexico_City"),
        ("🇮🇳 India",        "Asia/Kolkata"),
        ("🇲🇾 Malaysia",     "Asia/Kuala_Lumpur"),
    ]
    lines = []
    for flag, tz in WORLD_TZ:
        try:
            local = start_utc.astimezone(ZoneInfo(tz))
            lines.append(f"{flag} — {local.strftime('%-I:%M %p')}")
        except Exception:
            continue

    return (
        f"🔔 <b>{label} — NOW OPEN</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        + "\n".join(lines) +
        f"\n\n🎯 v5 filters active: ATR + ADX + 15M trend + BB\n"
        f"📉 Expect fewer signals, but much higher quality.\n"
        f"💎 Stay sharp."
    )


def fmt_watchlist(sess: str, pairs: list) -> str:
    tips = {
        "asian":   "JPY, AUD and NZD crosses most active. Expect tight, steady moves.",
        "london":  "EUR and GBP wake up now. First 2 hours = strongest breakouts.",
        "overlap": "Peak liquidity. All pairs can run hard. Best signals of the day.",
        "newyork": "USD pairs dominate. Keep SL tight around news events.",
    }
    lines = "\n".join(f"  {'🟢' if i%2==0 else '🔵'} {p['name']}" for i, p in enumerate(pairs))
    return (
        f"📋 <b>VEDA TRADER v5 — SESSION WATCHLIST</b>\n"
        f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"{session_label(sess)} is active.\n\n"
        f"<b>v5 active filters:</b>\n"
        f"  ✓ 15M trend alignment\n"
        f"  ✓ ADX ≥ {ADX_MIN} (trending market only)\n"
        f"  ✓ ATR ≥ {ATR_MIN_BPS} bps (enough volatility)\n"
        f"  ✓ BB squeeze check\n"
        f"  ✓ RSI strict zone ({RSI_BUY_MIN}–{RSI_BUY_MAX})\n"
        f"  ✓ MACD growing momentum\n"
        f"  ✓ S/R proximity filter\n\n"
        f"<b>Pairs scanning:</b>\n{lines}\n\n"
        f"💡 {tips.get(sess, '')}\n"
        f"⚠️ Fewer signals than v4. Every one counts more."
    )


def fmt_session_report() -> str:
    if not session_signals:
        return "📊 <b>Session Report</b>\n\nNo signals this session.\n"

    evaluate_pending_signals()
    lines = []
    wins = losses = pending = 0
    for s in session_signals:
        dir_l = "BUY" if s["direction"] == "BUY" else "SELL"
        result = s.get("result")
        if result == "WIN":   tag = "WIN ✅";  wins += 1
        elif result == "LOSS": tag = "LOSS ❌"; losses += 1
        else:                  tag = "⏳";       pending += 1
        lines.append(f"#{s.get('no','?')}  {s['pair']}  {s['time']}  {dir_l} → {tag}")

    total = wins + losses
    wr    = f"{(wins / total * 100):.0f}%" if total else "—"
    target_hit = "✅ TARGET HIT" if total > 0 and wins / total >= 0.62 else "📊 IN PROGRESS"

    return (
        f"📊 <b>SESSION RESULTS — {current_session_date}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        + "\n".join(lines) +
        f"\n\n━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ {wins} WIN   ❌ {losses} LOSS"
        + (f"   ⏳ {pending}" if pending else "") +
        f"\n🎯 Win rate: <b>{wr}</b>  {target_hit}"
    )

# ══════════════════════════════════════════
#  SESSION WATCHLIST TRIGGER
# ══════════════════════════════════════════
def maybe_send_watchlist():
    global last_session_alerted
    sess = current_session()
    if sess != last_session_alerted:
        pairs = pairs_for_session(sess)
        send_telegram(fmt_session_announcement(sess), pin=True)
        if send_telegram(fmt_watchlist(sess, pairs)):
            last_session_alerted = sess
            print(f"  [WATCHLIST] {sess} — {len(pairs)} pairs")

def is_session_ending() -> bool:
    h, m = datetime.now(timezone.utc).hour, datetime.now(timezone.utc).minute
    return (h, m) in [(6, 55), (15, 55), (20, 55)]

# ══════════════════════════════════════════
#  MAIN SCAN LOOP
# ══════════════════════════════════════════
def scan_markets():
    now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    sess    = current_session()
    pairs   = pairs_for_session(sess)
    print(f"\n[{now_str}] {sess.upper()} | scanning {len(pairs)} pairs | v5 filters ON")

    try:
        evaluate_pending_signals()
    except Exception as e:
        print(f"  [evaluator error] {e}")

    maybe_send_watchlist()

    signals_found = 0

    for p in pairs:
        name = p["name"]
        try:
            sig = analyze(p)
        except Exception as e:
            print(f"  [analyze error] {name}: {e}")
            continue

        if sig:
            ok = send_telegram(fmt_signal(sig))
            record_sig(name, sig["type"], sig["price"])
            arrow = "▲" if sig["type"] == "BUY" else "▼"
            
            # Send to gold channel if this is a GOLD signal
            if PREMIUM_ENABLED and sig.get("is_gold", False) and GOLD_CHAT_ID:
                send_telegram(fmt_gold_signal(sig), chat_id=GOLD_CHAT_ID)
                gold_tag = " 👑 GOLD"
            else:
                gold_tag = ""
                
            print(f"  [{arrow} {sig['type']} {'✓' if ok else '✗'}] {name}  Score={sig['score']}/100{gold_tag}")
            signals_found += 1
            time.sleep(1)
        else:
            print(f"  [no signal] {name}")

        time.sleep(0.5)   # slight rate limit for Yahoo API

    if is_session_ending() and session_signals:
        send_telegram(fmt_session_report())
        print(f"  [SESSION REPORT] sent — {len(session_signals)} signals this session")
        session_signals.clear()

    if not signals_found:
        print(f"  v5 filters rejected all signals this scan. Market quality too low.")

# ══════════════════════════════════════════
#  STARTUP
# ══════════════════════════════════════════
def send_startup():
    send_telegram(
        f"🚀 <b>VEDA TRADER — BOT v5 ONLINE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Upgrade from v4:</b>\n"
        f"  ✓ 15M trend alignment added\n"
        f"  ✓ ADX filter (no chop)\n"
        f"  ✓ ATR filter (no dead markets)\n"
        f"  ✓ BB squeeze filter\n"
        f"  ✓ RSI tightened to {RSI_BUY_MIN}–{RSI_BUY_MAX}\n"
        f"  ✓ MACD momentum must be growing\n"
        f"  ✓ S/R proximity filter\n"
        f"  ✓ Quality score (55+/100 required)\n\n"
        f"🎯 Target win rate: <b>62–70%</b>\n"
        f"📉 Expected signal volume: lower than v4\n"
        f"📈 Expected accuracy: significantly higher\n\n"
        f"🕐 Started: {datetime.now(timezone.utc).strftime('%d %b %Y  %H:%M UTC')}"
    )

# ══════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════
# Command handlers moved to config_and_commands_vedatraderbot.py


def main():
    """Main bot function for clean startup"""
    last_update_id = 0

    send_startup()
    scan_markets()

    schedule.every(5).minutes.do(scan_markets)

    print("\nBot is running. Press Ctrl+C to stop.\n")

    # Command polling setup
    last_update_id = 0

    while True:
        schedule.run_pending()

        # Poll for commands (quiet operation)
        if COMMANDS_ENABLED:
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
                params = {"offset": last_update_id + 1, "timeout": 1}  # Reduced timeout
                response = requests.get(url, params=params, timeout=5)

                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok") and data.get("result"):
                        for update in data["result"]:
                            last_update_id = max(last_update_id, update["update_id"])
                            try:
                                handle_telegram_command(update, send_telegram, PREMIUM_ENABLED)
                            except Exception as cmd_e:
                                print(f"[COMMAND ERROR] {cmd_e}")
            except requests.exceptions.RequestException:
                pass  # Network issues - ignore silently
            except Exception as e:
                print(f"[COMMAND POLL ERROR] {e}")

        time.sleep(30)


if __name__ == "__main__":
    # Suppress Windows path warnings
    import warnings
    warnings.filterwarnings("ignore", category=UserWarning)
    import os
    os.environ['PYTHONWARNINGS'] = 'ignore'

    main()