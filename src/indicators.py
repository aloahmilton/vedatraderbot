import pandas as pd
import numpy as np
from .config import MACD_FAST, MACD_SLOW, MACD_SIG, ADX_PERIOD, ATR_PERIOD, BB_PERIOD, BB_STDDEV

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

def find_sr_levels(df: pd.DataFrame, lookback: int = 50) -> list:
    recent = df.tail(lookback)
    highs  = recent["high"].nlargest(3).tolist()
    lows   = recent["low"].nsmallest(3).tolist()
    return highs + lows

def too_close_to_sr(price: float, levels: list, threshold: float = 0.002) -> bool:
    for lvl in levels:
        if abs(price - lvl) / price < threshold:
            return True
    return False

def calc_vol_ema(v: pd.Series, n: int) -> pd.Series:
    return v.ewm(span=n, adjust=False).mean()
