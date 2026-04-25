"""
src/fetcher.py  —  Multi-source OHLCV fetcher
==============================================

Priority order (tries each in sequence, returns first success):
  1. yfinance  — works on most VPS / Render / Railway
  2. Stooq     — free, no API key, good forex coverage
  3. Returns None if both fail (bot logs error, skips pair)

Why this matters
----------------
yfinance is blocked on some hosting environments (403 from Yahoo CDN).
Stooq serves the same data over a plain CSV endpoint that bypasses
those blocks. Having both means the bot keeps running even if one
source goes down.
"""

import io
import time
import pandas as pd
import requests
from datetime import datetime, timezone, timedelta

# ── Stooq symbol map  (Yahoo ticker → Stooq symbol) ──────────────────────
_STOOQ_MAP = {
    "EURUSD=X": "eurusd",   "GBPUSD=X": "gbpusd",   "USDJPY=X": "usdjpy",
    "USDCAD=X": "usdcad",   "AUDUSD=X": "audusd",   "NZDUSD=X": "nzdusd",
    "USDCHF=X": "usdchf",   "EURGBP=X": "eurgbp",   "EURJPY=X": "eurjpy",
    "GBPJPY=X": "gbpjpy",   "EURCHF=X": "eurchf",   "GBPCHF=X": "gbpchf",
    "EURCAD=X": "eurcad",   "GBPCAD=X": "gbpcad",   "CADJPY=X": "cadjpy",
    "AUDJPY=X": "audjpy",   "NZDJPY=X": "nzdjpy",   "AUDNZD=X": "audnzd",
    # Premium
    "GC=F":   "gc.f",       "SI=F":   "si.f",        "CL=F":   "cl.f",
    "^DJI":   "dji",        "^GSPC":  "spx",         "^NDX":   "ndx",         "^GDAXI": "dax",
    "NVDA":   "nvda.us",    "TSLA":   "tsla.us",     "AAPL":   "aapl.us",
    "MSFT":   "msft.us",    "META":   "meta.us",     "AMD":    "amd.us",
    "BTC-USD": "btcusd",    "ETH-USD": "ethusd",     "SOL-USD": "solusd",
}

# ── Stooq interval map  (yfinance interval → Stooq interval char) ─────────
_STOOQ_INTERVAL = {
    "5m": "5", "15m": "15", "1h": "60", "1d": "d",
}

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})


def _rename(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise column names to lowercase open/high/low/close/volume."""
    df = df.rename(columns={c: c.lower() for c in df.columns})
    needed = ["open", "high", "low", "close", "volume"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns after rename: {missing}")
    return df[needed].dropna().copy()


# ─────────────────────────────────────────────────────────────────────────
#  Source 1 — yfinance
# ─────────────────────────────────────────────────────────────────────────
def _fetch_yfinance(ticker: str, interval: str, days: int) -> pd.DataFrame | None:
    try:
        import yfinance as yf
        df = yf.Ticker(ticker).history(period=f"{days}d", interval=interval)
        if df is None or len(df) < 10:
            return None
        return _rename(df)
    except Exception as e:
        print(f"  [yfinance/{ticker}] {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────
#  Source 2 — Stooq  (free CSV, no API key)
# ─────────────────────────────────────────────────────────────────────────
def _fetch_stooq(ticker: str, interval: str, days: int) -> pd.DataFrame | None:
    symbol = _STOOQ_MAP.get(ticker)
    if not symbol:
        return None
    stooq_i = _STOOQ_INTERVAL.get(interval, "5")
    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=days + 2)  # extra buffer
    url   = (
        f"https://stooq.com/q/d/l/"
        f"?s={symbol}&d1={start.strftime('%Y%m%d')}"
        f"&d2={end.strftime('%Y%m%d')}&i={stooq_i}"
    )
    try:
        r = _SESSION.get(url, timeout=15)
        if r.status_code != 200 or len(r.content) < 50:
            return None
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = [c.lower() for c in df.columns]
        # Stooq columns: date, open, high, low, close, volume
        if "date" in df.columns:
            df = df.set_index("date")
        if "vol" in df.columns and "volume" not in df.columns:
            df = df.rename(columns={"vol": "volume"})
        if "volume" not in df.columns:
            df["volume"] = 0.0
        df = df.sort_index()
        return _rename(df)
    except Exception as e:
        print(f"  [stooq/{ticker}] {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────
#  Public entry point
# ─────────────────────────────────────────────────────────────────────────
def fetch_ohlcv(ticker: str, interval: str = "5m", days: int = 3) -> pd.DataFrame | None:
    """
    Fetch OHLCV data for `ticker`.
    Tries yfinance first, falls back to Stooq.
    Returns a DataFrame with columns [open, high, low, close, volume]
    or None if both sources fail.
    """
    for attempt, fn in enumerate([_fetch_yfinance, _fetch_stooq], 1):
        df = fn(ticker, interval, days)
        if df is not None and len(df) >= 30:
            return df
        if attempt == 1:
            time.sleep(0.3)   # small pause before fallback

    print(f"  [fetcher] All sources failed for {ticker}/{interval}")
    return None
