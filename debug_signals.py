import os
import sys
from datetime import datetime, timezone

# Add current directory to path
sys.path.insert(0, os.getcwd())

from src.engine import analyze_pair, fetch_ohlcv, get_trend_direction, calc_ema, calc_adx, calc_atr, calc_rsi, calc_macd
from src.config import pairs_for_session, current_session, ALL_PAIRS

def debug_pair(pair_info):
    name, ticker = pair_info["name"], pair_info["ticker"]
    print(f"\n--- DEBUGGING {name} ({ticker}) ---")
    df = fetch_ohlcv(ticker)
    if df is None:
        print("Failed to fetch OHLCV")
        return
    
    closes = df["close"]
    price = float(closes.iloc[-1])
    
    ef, es = calc_ema(closes, 9), calc_ema(closes, 21)
    f0, f1 = ef.iloc[-1], ef.iloc[-2]
    s0, s1 = es.iloc[-1], es.iloc[-2]
    
    adx_series = calc_adx(df)
    adx_now = adx_series.iloc[-1]
    
    atr_series = calc_atr(df)
    atr_now = atr_series.iloc[-1]
    atr_bps = (atr_now / price) * 10000
    
    rsi_series = calc_rsi(closes)
    rsi_now = rsi_series.iloc[-1]
    
    trend = get_trend_direction(ticker)
    
    print(f"Price: {price}")
    print(f"EMA9: {f0:.5f}, EMA21: {s0:.5f} (Diff: {f0-s0:.5f})")
    print(f"ADX: {adx_now:.1f}")
    print(f"ATR bps: {atr_bps:.1f}")
    print(f"RSI: {rsi_now:.1f}")
    print(f"Trend: {trend}")
    
    # Check volume
    from src.config import VOL_EMA_PERIOD, VOLUME_CONFIRM_MULTIPLIER
    from src.indicators import calc_vol_ema
    v_ema = calc_vol_ema(df["volume"], VOL_EMA_PERIOD).iloc[-1]
    v_now = df["volume"].iloc[-1]
    print(f"Volume: {v_now} (EMA: {v_ema:.1f}, Ratio: {v_now/v_ema:.2f})")

if __name__ == "__main__":
    p = {"name": "EUR/USD", "ticker": "EURUSD=X"}
    debug_pair(p)
