import pandas as pd
from datetime import datetime, timezone
from .config import (
    TF_SIGNAL, TF_TREND, TF_MAJOR, LOOKBACK, EMA_FAST, EMA_SLOW, EMA_MAJOR_PERIOD,
    RSI_BUY_MIN, RSI_BUY_MAX, RSI_SELL_MIN, RSI_SELL_MAX,
    ADX_MIN, ATR_MIN_BPS, BB_SQUEEZE_THRESHOLD, MIN_BODY_ATR_RATIO,
    VOL_EMA_PERIOD, GOLD_SCORE_THRESHOLD, SIGNAL_MIN_SCORE, EMA_SPREAD_MIN,
    VOLUME_CONFIRM_MULTIPLIER, RSI_MIDPOINT_BUY, RSI_MIDPOINT_SELL,
    SR_LOOKBACK, SR_PROXIMITY, RISK_REWARD, STOP_PERCENT, EXPIRY_MINUTES,
    PREMIUM_SIGNAL_MIN_SCORE, ADX_STRONG_MIN, TREND_SPREAD_STRONG_MIN,
    EMA_PULLBACK_MAX, WICK_RATIO_MAX
)
# BUG FIX: replaced direct yfinance calls with the multi-source fetcher
from .fetcher import fetch_ohlcv
from .indicators import (
    calc_ema, calc_rsi, calc_macd, calc_adx, calc_atr, 
    calc_bollinger, find_sr_levels, too_close_to_sr, calc_vol_ema
)
from .database import is_dupe, update_signal_result

# Premium system check
try:
    from . import premium
    PREMIUM_LOADED = True
except ImportError:
    PREMIUM_LOADED = False


def evaluate_pending_signals(session_signals):
    """Check signals past expiry and stamp WIN/LOSS."""
    from .notifier import send_telegram, fmt_result_msg
    now = datetime.now(timezone.utc)
    for s in session_signals:
        if s.get("result") is not None: continue
        age_min = (now - s["timestamp"]).total_seconds() / 60
        if age_min < EXPIRY_MINUTES: continue

        # BUG FIX: always use the stored ticker (e.g. "EURUSD=X"), never the
        # display name ("EUR/USD") which yfinance / Stooq don't understand.
        ticker = s.get("ticker") or s.get("pair", "")
        df = fetch_ohlcv(ticker)
        if df is None or len(df) < 2: continue

        exit_price = float(df["close"].iloc[-1])
        entry = float(s["price"])
        won = (exit_price > entry) if s["direction"] == "BUY" else (exit_price < entry)
        s["result"] = "WIN" if won else "LOSS"
        s["exit_price"] = exit_price

        send_telegram(fmt_result_msg(s))
        update_signal_result(s["pair"], s["timestamp"], s["result"], exit_price)
        print(f"  [OUTCOME] #{s['no']} {s['pair']} -> {s['result']}")

# fetch_ohlcv is imported from .fetcher (multi-source: yfinance + Stooq fallback)

def get_trend_direction(ticker: str) -> str:
    df = fetch_ohlcv(ticker, interval=TF_TREND, days=LOOKBACK)
    if df is None or len(df) < 30: return "NEUTRAL"
    ef = calc_ema(df["close"], EMA_FAST)
    es = calc_ema(df["close"], EMA_SLOW)
    f0, s0 = ef.iloc[-1], es.iloc[-1]
    if abs(f0 - s0) / s0 < 0.0003: return "NEUTRAL"
    return "UP" if f0 > s0 else "DOWN"

def get_major_trend(ticker: str) -> str:
    """Check 1H trend using 200 EMA."""
    df = fetch_ohlcv(ticker, interval=TF_MAJOR, days=7)  # More days for 200 EMA
    if df is None or len(df) < EMA_MAJOR_PERIOD: return "NEUTRAL"
    ema_major = calc_ema(df["close"], EMA_MAJOR_PERIOD)
    price = df["close"].iloc[-1]
    ema_val = ema_major.iloc[-1]
    if price > ema_val: return "UP"
    if price < ema_val: return "DOWN"
    return "NEUTRAL"

def quality_score(rsi, adx, atr_bps, bb_width, macd_hist, trend_aligned, body_ratio, direction) -> int:
    score = 0
    # RSI (25)
    rsi_center = RSI_MIDPOINT_BUY if direction == "BUY" else RSI_MIDPOINT_SELL
    score += max(0, 25 - int(abs(rsi - rsi_center) * 1.5))
    # ADX (20)
    score += min(20, int((adx - ADX_MIN) * 0.8)) if adx >= ADX_MIN else 0
    # ATR (15)
    score += min(15, int(atr_bps * 2.5)) if atr_bps >= ATR_MIN_BPS else 0
    # BB (15)
    score += min(15, int(bb_width * 5000)) if bb_width >= BB_SQUEEZE_THRESHOLD else 0
    # MACD (15)
    score += min(15, int(abs(macd_hist) * 10000))
    # Trend (10)
    if trend_aligned: score += 10
    return min(100, score)

def asset_signal_floor(category: str, tier: str) -> int:
    if tier == "premium" or category in {"indices", "stocks", "crypto", "commodities"}:
        return PREMIUM_SIGNAL_MIN_SCORE
    return SIGNAL_MIN_SCORE

def candle_quality(df: pd.DataFrame, direction: str, atr_now: float) -> tuple[float, float, float]:
    last = df.iloc[-1]
    body = abs(float(last["close"]) - float(last["open"]))
    upper_wick = float(last["high"]) - max(float(last["close"]), float(last["open"]))
    lower_wick = min(float(last["close"]), float(last["open"])) - float(last["low"])
    body_atr_ratio = body / atr_now if atr_now > 0 else 0.0
    against_wick = upper_wick if direction == "BUY" else lower_wick
    wick_ratio = against_wick / body if body > 0 else float("inf")
    return body_atr_ratio, wick_ratio, body

def analyze_pair(pair_info: dict) -> dict | None:
    name, ticker = pair_info["name"], pair_info["ticker"]
    tier = pair_info.get("tier", "public")
    category = pair_info.get("category", "forex")
    df = fetch_ohlcv(ticker)
    if df is None or len(df) < 80: return None

    closes, opens = df["close"], df["open"]
    price = float(closes.iloc[-1])
    
    ef, es = calc_ema(closes, EMA_FAST), calc_ema(closes, EMA_SLOW)
    rv = calc_rsi(closes)
    _, _, hist_series = calc_macd(closes)
    adx_series, atr_series = calc_adx(df), calc_atr(df)
    bb_u, bb_m, bb_l = calc_bollinger(closes)

    f0, f1, f_prev = ef.iloc[-1], ef.iloc[-2], ef.iloc[-3]
    s0, s1, s_prev = es.iloc[-1], es.iloc[-2], es.iloc[-3]
    rsi_now, adx_now = rv.iloc[-1], adx_series.iloc[-1]
    hist_now, hist_prev = hist_series.iloc[-1], hist_series.iloc[-2]
    atr_now = atr_series.iloc[-1]
    atr_bps = (atr_now / price) * 10000
    bb_width = (bb_u.iloc[-1] - bb_l.iloc[-1]) / price
    body_ratio = abs(price - opens.iloc[-1]) / atr_now if atr_now > 0 else 0

    if atr_bps < ATR_MIN_BPS or bb_width < BB_SQUEEZE_THRESHOLD: return None
    
    trend = get_trend_direction(ticker)
    if trend == "NEUTRAL": return None

    ema_spread = abs(f0 - s0) / price if price else 0
    ema_rising = f0 > f1 > f_prev
    ema_falling = f0 < f1 < f_prev

    # Allow continuation trends with healthy separation, not only fresh crosses.
    bull_cross = ((f_prev <= s_prev) and (f1 > s1) and (f0 > s0)) or (f0 > s0 and ema_rising and ema_spread >= EMA_SPREAD_MIN)
    bear_cross = ((f_prev >= s_prev) and (f1 < s1) and (f0 < s0)) or (f0 < s0 and ema_falling and ema_spread >= EMA_SPREAD_MIN)

    if adx_now < ADX_MIN: return None
    
    macd_bull = hist_now > 0 and hist_now > hist_prev
    macd_bear = hist_now < 0 and hist_now < hist_prev
    
    rsi_buy_ok = RSI_BUY_MIN <= rsi_now <= RSI_BUY_MAX
    rsi_sell_ok = RSI_SELL_MIN <= rsi_now <= RSI_SELL_MAX

    if body_ratio < MIN_BODY_ATR_RATIO: return None
    if too_close_to_sr(price, find_sr_levels(df, SR_LOOKBACK), SR_PROXIMITY): return None

    buy_sig = bull_cross and trend == "UP" and macd_bull and rsi_buy_ok and price > bb_m.iloc[-1]
    sell_sig = bear_cross and trend == "DOWN" and macd_bear and rsi_sell_ok and price < bb_m.iloc[-1]

    if not buy_sig and not sell_sig: return None
    
    direction = "BUY" if buy_sig else "SELL"
    candle_body_ratio, against_wick_ratio, candle_body = candle_quality(df, direction, atr_now)

    if candle_body_ratio < MIN_BODY_ATR_RATIO:
        return None
    if against_wick_ratio > WICK_RATIO_MAX:
        return None

    price_to_fast_ema = abs(price - f0) / price if price else 0
    if price_to_fast_ema > EMA_PULLBACK_MAX:
        return None

    trend_spread = abs(f0 - s0) / price if price else 0
    if adx_now < ADX_STRONG_MIN and trend_spread < TREND_SPREAD_STRONG_MIN:
        return None
    
    # ── VOLUME CONFIRMATION (New) ──
    v_ema = calc_vol_ema(df["volume"], VOL_EMA_PERIOD).iloc[-1]
    v_now = df["volume"].iloc[-1]
    if v_now < v_ema * VOLUME_CONFIRM_MULTIPLIER:
        return None

    # ── MAJOR TREND CONFIRMATION (New) ──
    major_trend = get_major_trend(ticker)
    if major_trend != "NEUTRAL" and major_trend != ( "UP" if direction == "BUY" else "DOWN"):
        return None

    if is_dupe(name, direction): return None

    score = quality_score(rsi_now, adx_now, atr_bps, bb_width, hist_now, True, body_ratio, direction)
    if score < asset_signal_floor(category, tier):
        return None

    sl = round(price * (1 - STOP_PERCENT/100 if direction == "BUY" else 1 + STOP_PERCENT/100), 6)
    tp = round(price * (1 + STOP_PERCENT/100*RISK_REWARD if direction == "BUY" else 1 - STOP_PERCENT/100*RISK_REWARD), 6)

    # ── GOLD SIGNAL CHECK ──
    is_gold = False
    if PREMIUM_LOADED and premium.PREMIUM_ENABLED:
        bb_pos = (price - bb_l.iloc[-1]) / (bb_u.iloc[-1] - bb_l.iloc[-1]) if (bb_u.iloc[-1] - bb_l.iloc[-1]) > 0 else 0.5
        is_gold = premium.gold_signal_check(rsi_now, adx_now, hist_now, bb_pos, score)

    signal = {
        "type": direction, "pair": name, "price": price, "sl": sl, "tp": tp,
        "rsi": round(rsi_now, 1), "adx": round(adx_now, 1), "atr_bps": round(atr_bps, 1),
        "score": score, "trend": trend, "is_gold": is_gold,
        "ticker": ticker, "tier": tier, "category": category,
        "ema_gap_bps": round(trend_spread * 10000, 1),
        "wick_ratio": round(against_wick_ratio, 2),
        "entry_gap_bps": round(price_to_fast_ema * 10000, 1),
        "body_atr_ratio": round(candle_body_ratio, 2)
    }
    return signal
