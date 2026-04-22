import yfinance as yf
import pandas as pd
from datetime import datetime, timezone
from .config import (
    TF_SIGNAL, TF_TREND, TF_MAJOR, LOOKBACK, EMA_FAST, EMA_SLOW, EMA_MAJOR_PERIOD,
    RSI_BUY_MIN, RSI_BUY_MAX, RSI_SELL_MIN, RSI_SELL_MAX,
    ADX_MIN, ATR_MIN_BPS, BB_SQUEEZE_THRESHOLD, MIN_BODY_ATR_RATIO,
    VOL_EMA_PERIOD, GOLD_SCORE_THRESHOLD,
    SR_LOOKBACK, SR_PROXIMITY, RISK_REWARD, STOP_PERCENT, EXPIRY_MINUTES
)
from .indicators import (
    calc_ema, calc_rsi, calc_macd, calc_adx, calc_atr, 
    calc_bollinger, find_sr_levels, too_close_to_sr, calc_vol_ema
)
from .database import is_dupe, update_signal_result

def evaluate_pending_signals(session_signals):
    """Check signals past expiry and stamp WIN/LOSS."""
    from .notifier import send_telegram, fmt_result_msg
    now = datetime.now(timezone.utc)
    for s in session_signals:
        if s.get("result") is not None: continue
        age_min = (now - s["timestamp"]).total_seconds() / 60
        if age_min < EXPIRY_MINUTES: continue

        df = fetch_ohlcv(s["ticker"] if "ticker" in s else s["pair"]) # Ensure ticker is used
        if df is None or len(df) < 2: continue

        exit_price = float(df["close"].iloc[-1])
        entry = float(s["price"])
        won = (exit_price > entry) if s["direction"] == "BUY" else (exit_price < entry)
        s["result"] = "WIN" if won else "LOSS"
        s["exit_price"] = exit_price

        send_telegram(fmt_result_msg(s))
        update_signal_result(s["pair"], s["timestamp"], s["result"], exit_price)
        print(f"  [OUTCOME] #{s['no']} {s['pair']} → {s['result']}")

def fetch_ohlcv(ticker: str, interval: str = TF_SIGNAL, days: int = LOOKBACK) -> pd.DataFrame | None:
    try:
        df = yf.Ticker(ticker).history(period=f"{days}d", interval=interval)
        if df is None or len(df) < 60: return None
        df = df.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})
        return df[["open","high","low","close","volume"]].dropna().copy()
    except Exception as e:
        print(f"  [Fetch {ticker}/{interval}] {e}")
        return None

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
    df = fetch_ohlcv(ticker, interval=TF_MAJOR, days=5) # More days for 200 EMA
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
    rsi_center = 52 if direction == "BUY" else 48
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

def analyze_pair(pair_info: dict) -> dict | None:
    name, ticker = pair_info["name"], pair_info["ticker"]
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

    bull_cross = (f_prev <= s_prev) and (f1 > s1) and (f0 > s0)
    bear_cross = (f_prev >= s_prev) and (f1 < s1) and (f0 < s0)

    if adx_now < ADX_MIN: return None
    
    macd_bull = hist_now > 0 and hist_now > hist_prev
    macd_bear = hist_now < 0 and hist_now < hist_prev
    
    rsi_buy_ok = RSI_BUY_MIN <= rsi_now <= RSI_BUY_MAX
    rsi_sell_ok = RSI_SELL_MIN <= rsi_now <= RSI_SELL_MAX

    if body_ratio < MIN_BODY_ATR_RATIO: return None
    if too_close_to_sr(price, find_sr_levels(df)): return None

    buy_sig = bull_cross and trend == "UP" and macd_bull and rsi_buy_ok and price > bb_m.iloc[-1]
    sell_sig = bear_cross and trend == "DOWN" and macd_bear and rsi_sell_ok and price < bb_m.iloc[-1]

    if not buy_sig and not sell_sig: return None
    
    direction = "BUY" if buy_sig else "SELL"
    
    # ── VOLUME CONFIRMATION (New) ──
    v_ema = calc_vol_ema(df["volume"], VOL_EMA_PERIOD).iloc[-1]
    v_now = df["volume"].iloc[-1]
    if v_now < v_ema * 1.1: # 10% higher than average volume
        return None

    # ── MAJOR TREND CONFIRMATION (New) ──
    major_trend = get_major_trend(ticker)
    if major_trend != "NEUTRAL" and major_trend != ( "UP" if direction == "BUY" else "DOWN"):
        return None

    if is_dupe(name, direction): return None

    score = quality_score(rsi_now, adx_now, atr_bps, bb_width, hist_now, True, body_ratio, direction)
    if score < 55: return None

    sl = round(price * (1 - STOP_PERCENT/100 if direction == "BUY" else 1 + STOP_PERCENT/100), 6)
    tp = round(price * (1 + STOP_PERCENT/100*RISK_REWARD if direction == "BUY" else 1 - STOP_PERCENT/100*RISK_REWARD), 6)

    signal = {
        "type": direction, "pair": name, "price": price, "sl": sl, "tp": tp,
        "rsi": round(rsi_now, 1), "adx": round(adx_now, 1), "atr_bps": round(atr_bps, 1),
        "score": score, "trend": trend, "is_gold": score >= GOLD_SCORE_THRESHOLD
    }
    return signal
