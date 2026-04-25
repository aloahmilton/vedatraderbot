"""
VEDA TRADER - engine.py
Real signal generation using RSI, EMA crossover, MACD, ATR.
Free channel: scalping (M1/M5)
Premium channel: swing (M15/H1)
"""

import time
import numpy as np
import yfinance as yf
from datetime import datetime, timezone

# ── Timeframes ───────────────────────────────────────────────
SCALP_INTERVAL  = "1m"   # Free forex scalping
SCALP_PERIOD    = "1d"
SWING_INTERVAL  = "15m"  # Premium normal trading
SWING_PERIOD    = "5d"


# ── Indicators ───────────────────────────────────────────────

def ema(series: np.ndarray, period: int) -> np.ndarray:
    result = np.zeros_like(series)
    k = 2.0 / (period + 1)
    result[0] = series[0]
    for i in range(1, len(series)):
        result[i] = series[i] * k + result[i - 1] * (1 - k)
    return result

def rsi(series: np.ndarray, period: int = 14) -> np.ndarray:
    deltas = np.diff(series)
    gains  = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.convolve(gains,  np.ones(period)/period, mode='valid')
    avg_loss = np.convolve(losses, np.ones(period)/period, mode='valid')
    rs = np.where(avg_loss == 0, 100.0, avg_gain / avg_loss)
    return 100.0 - (100.0 / (1.0 + rs))

def macd(series: np.ndarray, fast=12, slow=26, signal=9):
    fast_ema   = ema(series, fast)
    slow_ema   = ema(series, slow)
    macd_line  = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    histogram  = macd_line - signal_line
    return macd_line, signal_line, histogram

def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period=14) -> float:
    tr_list = []
    for i in range(1, len(high)):
        tr = max(high[i] - low[i],
                 abs(high[i] - close[i-1]),
                 abs(low[i]  - close[i-1]))
        tr_list.append(tr)
    if not tr_list:
        return 0.0
    recent = tr_list[-period:]
    return float(np.mean(recent))

def bollinger(series: np.ndarray, period=20, std_dev=2):
    if len(series) < period:
        return None, None, None
    rolling_mean = np.convolve(series, np.ones(period)/period, mode='valid')
    rolling_std  = np.array([np.std(series[i:i+period]) for i in range(len(series)-period+1)])
    upper = rolling_mean + std_dev * rolling_std
    lower = rolling_mean - std_dev * rolling_std
    return rolling_mean, upper, lower


# ── Data Fetching ────────────────────────────────────────────

def fetch_ohlcv(symbol: str, interval: str, period: str) -> dict | None:
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(interval=interval, period=period)
        if df is None or len(df) < 50:
            return None
        return {
            "open":   df["Open"].values,
            "high":   df["High"].values,
            "low":    df["Low"].values,
            "close":  df["Close"].values,
            "volume": df["Volume"].values,
        }
    except Exception as e:
        print(f"[FETCH ERROR] {symbol}: {e}")
        return None


# ── Signal Scoring ───────────────────────────────────────────

def score_signal(rsi_val: float, macd_hist: float, ema_cross: str,
                 bb_position: str, direction: str) -> int:
    """
    Score from 0-100. Signal is only sent if score >= 65.
    direction: 'BUY' or 'SELL'
    """
    score = 0

    # RSI (max 35 pts)
    if direction == "BUY":
        if rsi_val < 30:   score += 35  # oversold → strong buy
        elif rsi_val < 40: score += 25
        elif rsi_val < 50: score += 10
    else:  # SELL
        if rsi_val > 70:   score += 35  # overbought → strong sell
        elif rsi_val > 60: score += 25
        elif rsi_val > 50: score += 10

    # MACD histogram (max 30 pts)
    if direction == "BUY"  and macd_hist > 0: score += 30
    elif direction == "SELL" and macd_hist < 0: score += 30
    elif abs(macd_hist) < 0.00005: score += 10  # near-zero, neutral

    # EMA crossover (max 25 pts)
    if direction == "BUY"  and ema_cross == "bullish": score += 25
    elif direction == "SELL" and ema_cross == "bearish": score += 25

    # Bollinger band position (max 10 pts)
    if direction == "BUY"  and bb_position == "below_lower": score += 10
    elif direction == "SELL" and bb_position == "above_upper": score += 10

    return min(score, 100)


# ── Main Analyzer ────────────────────────────────────────────

def analyze_pair(pair: dict, tier: str = "public") -> dict | None:
    """
    Analyze a pair and return a signal dict or None.
    tier: 'public' = scalping (1m), 'premium' = swing (15m)
    """
    interval = SCALP_INTERVAL  if tier == "public" else SWING_INTERVAL
    period   = SCALP_PERIOD    if tier == "public" else SWING_PERIOD

    data = fetch_ohlcv(pair["symbol"], interval, period)
    if data is None:
        return None

    closes = data["close"]
    highs  = data["high"]
    lows   = data["low"]

    if len(closes) < 50:
        return None

    # ── Indicators ──
    rsi_vals = rsi(closes, 14)
    if len(rsi_vals) < 2:
        return None
    rsi_now  = float(rsi_vals[-1])

    ema9  = ema(closes, 9)
    ema21 = ema(closes, 21)
    ema50 = ema(closes, 50)

    ema_cross = "bullish" if ema9[-1] > ema21[-1] > ema50[-1] else \
                "bearish" if ema9[-1] < ema21[-1] < ema50[-1] else "neutral"

    macd_line, signal_line, histogram = macd(closes)
    macd_hist_now = float(histogram[-1])

    _, bb_upper, bb_lower = bollinger(closes, 20)
    price = float(closes[-1])
    if bb_upper is not None and bb_lower is not None:
        if price > bb_upper[-1]:   bb_pos = "above_upper"
        elif price < bb_lower[-1]: bb_pos = "below_lower"
        else:                       bb_pos = "inside"
    else:
        bb_pos = "inside"

    atr_val = atr(highs, lows, closes, 14)

    # ── Direction detection ──
    # Determine candidate direction
    buy_signals  = 0
    sell_signals = 0

    if rsi_now < 40:          buy_signals  += 1
    if rsi_now > 60:          sell_signals += 1
    if macd_hist_now > 0:     buy_signals  += 1
    if macd_hist_now < 0:     sell_signals += 1
    if ema_cross == "bullish": buy_signals  += 1
    if ema_cross == "bearish": sell_signals += 1
    if bb_pos == "below_lower": buy_signals += 1
    if bb_pos == "above_upper": sell_signals += 1

    if buy_signals > sell_signals:
        direction = "BUY"
    elif sell_signals > buy_signals:
        direction = "SELL"
    else:
        return None  # No clear direction

    score = score_signal(rsi_now, macd_hist_now, ema_cross, bb_pos, direction)

    # Minimum score threshold
    min_score = 65 if tier == "public" else 70
    if score < min_score:
        return None

    # ── TP / SL calculation ──
    pip = pair.get("pip", 0.0001)

    if tier == "public":  # scalping
        sl_pips = round(atr_val / pip * 0.8, 1)
        tp_pips = round(sl_pips * 1.2, 1)   # 1:1.2 RR for scalping
        duration = "3-5 mins"
    else:  # premium swing
        sl_pips = round(atr_val / pip * 1.2, 1)
        tp_pips = round(sl_pips * 2.0, 1)   # 1:2 RR for swing
        duration = "30-60 mins"

    if direction == "BUY":
        sl_price = round(price - (sl_pips * pip), 5)
        tp_price = round(price + (tp_pips * pip), 5)
    else:
        sl_price = round(price + (sl_pips * pip), 5)
        tp_price = round(price - (tp_pips * pip), 5)

    # ── Quality label ──
    if score >= 85:   quality = "🔥 STRONG"
    elif score >= 75: quality = "✅ GOOD"
    else:             quality = "⚡ MODERATE"

    return {
        "pair":      pair["name"],
        "symbol":    pair["symbol"],
        "type":      direction,
        "tier":      tier,
        "price":     price,
        "sl":        sl_price,
        "tp":        tp_price,
        "sl_pips":   sl_pips,
        "tp_pips":   tp_pips,
        "score":     score,
        "quality":   quality,
        "duration":  duration,
        "rsi":       round(rsi_now, 2),
        "ema_cross": ema_cross,
        "bb_pos":    bb_pos,
        "atr":       round(atr_val, 6),
        "interval":  interval,
    }


# ── Pending Signal Evaluator ─────────────────────────────────

def evaluate_pending_signals(session_signals: list) -> None:
    """
    Check open signals - mark TP/SL hit if price crossed target.
    Updates signal dict in-place with 'result'.
    """
    for sig in session_signals:
        if sig.get("result"):  # already closed
            continue
        try:
            data = fetch_ohlcv(sig["symbol"], "1m", "1h")
            if not data:
                continue
            current_price = float(data["close"][-1])
            if sig["type"] == "BUY":
                if current_price >= sig["tp"]:
                    sig["result"] = "✅ TP HIT"
                elif current_price <= sig["sl"]:
                    sig["result"] = "❌ SL HIT"
            else:
                if current_price <= sig["tp"]:
                    sig["result"] = "✅ TP HIT"
                elif current_price >= sig["sl"]:
                    sig["result"] = "❌ SL HIT"
            time.sleep(0.3)
        except Exception as e:
            print(f"[EVAL] {sig.get('pair','?')}: {e}")
