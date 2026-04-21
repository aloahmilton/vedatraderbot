"""
╔══════════════════════════════════════════════════════════╗
║          VEDA TRADER — Signal Bot v3                     ║
║     Multi-Session | MACD+EMA | 18 Pairs | MT4/MT5        ║
╚══════════════════════════════════════════════════════════╝

SETUP:
  1. pip install yfinance pandas requests schedule
  2. Fill in TELEGRAM_TOKEN and CHAT_ID below
  3. python veda_trader_bot.py

SIGNAL LOGIC (all 4 must align):
  1. EMA 9/21 crossover        — primary trigger
  2. MACD histogram direction  — confirms momentum, kills fakes
  3. RSI in safe zone          — avoids overbought/oversold traps
  4. Volume ≥ 80% of average   — filters dead/illiquid markets

SESSIONS (UTC):
  🌏 Asian   00:00–07:00  → AUD, NZD, JPY crosses
  🇬🇧 London  07:00–16:00  → EUR, GBP pairs
  🔥 Overlap 12:00–16:00  → All pairs (peak liquidity, best signals)
  🇺🇸 NY      16:00–21:00  → USD pairs

  A watchlist is sent at each session open so your users
  know exactly which pairs will be scanned that session.
"""

import time
import schedule
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timezone

# ══════════════════════════════════════════
#  SETTINGS — FILL THESE IN
# ══════════════════════════════════════════
TELEGRAM_TOKEN = "8652896161:AAEwKHUNG4G7JmRgChJokZq6oUQW5nZU-GI"
CHAT_ID        = "-1003912798237"

TIMEFRAME     = "5m"
LOOKBACK_DAYS = 2

# ── Indicator parameters ─────────────────
EMA_FAST    = 9
EMA_SLOW    = 21
RSI_PERIOD  = 14
MACD_FAST   = 12
MACD_SLOW   = 26
MACD_SIG    = 9

RSI_BUY_MIN = 38
RSI_BUY_MAX = 68
RSI_SEL_MIN = 32
RSI_SEL_MAX = 62

VOL_MIN     = 0.80   # last bar must be >= 80% of 20-bar average volume

# ── Risk management ──────────────────────
RISK_REWARD   = 2.0
STOP_PERCENT  = 0.3  # 0.3% SL from entry

# ── Deduplication (minutes) ──────────────
DEDUPE_MIN = 30

# ══════════════════════════════════════════
#  18-PAIR UNIVERSE — session-tagged
# ══════════════════════════════════════════
ALL_PAIRS = [
    # Majors — active all sessions
    {"name": "EUR/USD", "ticker": "EURUSD=X", "session": "all"},
    {"name": "GBP/USD", "ticker": "GBPUSD=X", "session": "all"},
    {"name": "USD/JPY", "ticker": "USDJPY=X", "session": "all"},
    {"name": "USD/CAD", "ticker": "USDCAD=X", "session": "all"},
    {"name": "AUD/USD", "ticker": "AUDUSD=X", "session": "all"},
    {"name": "NZD/USD", "ticker": "NZDUSD=X", "session": "all"},
    {"name": "USD/CHF", "ticker": "USDCHF=X", "session": "all"},
    # London/NY minors
    {"name": "EUR/GBP", "ticker": "EURGBP=X", "session": "london"},
    {"name": "EUR/JPY", "ticker": "EURJPY=X", "session": "london"},
    {"name": "GBP/JPY", "ticker": "GBPJPY=X", "session": "london"},
    {"name": "EUR/CHF", "ticker": "EURCHF=X", "session": "london"},
    {"name": "GBP/CHF", "ticker": "GBPCHF=X", "session": "london"},
    # NY minors
    {"name": "EUR/CAD", "ticker": "EURCAD=X", "session": "newyork"},
    {"name": "GBP/CAD", "ticker": "GBPCAD=X", "session": "newyork"},
    {"name": "CAD/JPY", "ticker": "CADJPY=X", "session": "newyork"},
    # Asian pairs
    {"name": "AUD/JPY", "ticker": "AUDJPY=X", "session": "asian"},
    {"name": "NZD/JPY", "ticker": "NZDJPY=X", "session": "asian"},
    {"name": "AUD/NZD", "ticker": "AUDNZD=X", "session": "asian"},
]

# ══════════════════════════════════════════
#  SESSION HELPERS
# ══════════════════════════════════════════
def current_session() -> str:
    h = datetime.now(timezone.utc).hour
    if 12 <= h < 16: return "overlap"
    if 7  <= h < 16: return "london"
    if 16 <= h < 21: return "newyork"
    return "asian"

def session_label(s: str) -> str:
    return {
        "overlap":  "🔥 London/NY Overlap (Peak Liquidity)",
        "london":   "🇬🇧 London Session",
        "newyork":  "🇺🇸 New York Session",
        "asian":    "🌏 Asian Session",
    }.get(s, s)

def pairs_for_session(s: str) -> list[dict]:
    tag = "london" if s == "overlap" else s
    return [p for p in ALL_PAIRS if p["session"] in ("all", tag)]

# ══════════════════════════════════════════
#  STATE
# ══════════════════════════════════════════
last_signal_time:    dict = {}
last_session_alerted: str = ""

# ══════════════════════════════════════════
#  TELEGRAM
# ══════════════════════════════════════════
def send_telegram(msg: str) -> bool:
    url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg,
               "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=payload, timeout=15)
        res = r.json()
        if not res.get("ok"):
            print(f"  [Telegram FAIL] {res.get('description')}")
            return False
        return True
    except Exception as e:
        print(f"  [Telegram Exception] {e}")
        return False

# ══════════════════════════════════════════
#  DATA FETCH
# ══════════════════════════════════════════
def fetch_ohlcv(ticker: str) -> pd.DataFrame | None:
    try:
        df = yf.Ticker(ticker).history(period=f"{LOOKBACK_DAYS}d", interval=TIMEFRAME)
        if df is None or len(df) < 60:
            return None
        df = df.rename(columns={"Open":"open","High":"high",
                                  "Low":"low","Close":"close","Volume":"volume"})
        return df[["open","high","low","close","volume"]].dropna().copy()
    except Exception as e:
        print(f"  [Fetch Error {ticker}] {e}")
        return None

# ══════════════════════════════════════════
#  INDICATORS
# ══════════════════════════════════════════
def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d    = s.diff()
    g    = d.clip(lower=0).ewm(com=n-1, adjust=False).mean()
    l    = (-d.clip(upper=0)).ewm(com=n-1, adjust=False).mean()
    rs   = g / l.replace(0, float("inf"))
    return 100 - (100 / (1 + rs))

def macd(s: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    line = ema(s, MACD_FAST) - ema(s, MACD_SLOW)
    sig  = ema(line, MACD_SIG)
    hist = line - sig
    return line, sig, hist

# ══════════════════════════════════════════
#  SIGNAL STRENGTH
# ══════════════════════════════════════════
def calc_strength(gap_pct: float, rsi_val: float,
                  vol_r: float, hist: float) -> int:
    sc = 0
    if gap_pct > 0.15:    sc += 2
    elif gap_pct > 0.05:  sc += 1
    if 48 <= rsi_val <= 58:  sc += 2
    elif 42 <= rsi_val <= 62: sc += 1
    if vol_r > 1.3:       sc += 1
    if abs(hist) > 0.00005: sc += 1
    return min(sc, 5)

def strength_bar(sc: int) -> str:
    return "█" * sc + "░" * (5 - sc) + f"  {sc*20}%"

# ══════════════════════════════════════════
#  DEDUPLICATION
# ══════════════════════════════════════════
def is_dupe(pair: str, direction: str) -> bool:
    key  = f"{pair}:{direction}"
    last = last_signal_time.get(key)
    if not last: return False
    return (datetime.now(timezone.utc) - last).total_seconds() / 60 < DEDUPE_MIN

def record(pair: str, direction: str):
    last_signal_time[f"{pair}:{direction}"] = datetime.now(timezone.utc)

# ══════════════════════════════════════════
#  ANALYSIS
# ══════════════════════════════════════════
def analyze(pair_info: dict) -> dict | None:
    df = fetch_ohlcv(pair_info["ticker"])
    if df is None: return None

    closes  = df["close"]
    volumes = df["volume"]
    price   = closes.iloc[-1]

    ef = ema(closes, EMA_FAST)
    es = ema(closes, EMA_SLOW)
    rv = rsi(closes, RSI_PERIOD)
    _, _, hist_s = macd(closes)

    f0, f1     = ef.iloc[-1],    ef.iloc[-2]
    s0, s1     = es.iloc[-1],    es.iloc[-2]
    rsi_now    = rv.iloc[-1]
    hist_now   = hist_s.iloc[-1]
    hist_prev  = hist_s.iloc[-2]

    if any(pd.isna(x) for x in [f0, f1, s0, s1, rsi_now, hist_now]):
        return None

    avg_vol   = volumes.iloc[-21:-1].mean()
    vol_ratio = (volumes.iloc[-1] / avg_vol) if avg_vol > 0 else 0
    good_vol  = vol_ratio >= VOL_MIN

    bull_x = (f1 <= s1) and (f0 > s0)
    bear_x = (f1 >= s1) and (f0 < s0)

    macd_bull = (hist_now > 0) and (hist_now > hist_prev)
    macd_bear = (hist_now < 0) and (hist_now < hist_prev)

    gap_pct = abs(f0 - s0) / s0 * 100
    name    = pair_info["name"]

    if bull_x and RSI_BUY_MIN <= rsi_now <= RSI_BUY_MAX and good_vol and macd_bull:
        if is_dupe(name, "BUY"): return None
        sl = round(price * (1 - STOP_PERCENT / 100), 6)
        tp = round(price * (1 + STOP_PERCENT / 100 * RISK_REWARD), 6)
        return {"type":"BUY", "pair":name, "price":price, "sl":sl, "tp":tp,
                "rsi":round(rsi_now,1), "vol":round(vol_ratio,2),
                "strength":calc_strength(gap_pct,rsi_now,vol_ratio,hist_now)}

    if bear_x and RSI_SEL_MIN <= rsi_now <= RSI_SEL_MAX and good_vol and macd_bear:
        if is_dupe(name, "SELL"): return None
        sl = round(price * (1 + STOP_PERCENT / 100), 6)
        tp = round(price * (1 - STOP_PERCENT / 100 * RISK_REWARD), 6)
        return {"type":"SELL","pair":name, "price":price, "sl":sl, "tp":tp,
                "rsi":round(rsi_now,1), "vol":round(vol_ratio,2),
                "strength":calc_strength(gap_pct,rsi_now,vol_ratio,hist_now)}

    return None

# ══════════════════════════════════════════
#  MESSAGE TEMPLATES
# ══════════════════════════════════════════
def fmt_signal(sig: dict) -> str:
    emoji = "🟢" if sig["type"] == "BUY" else "🔴"
    bar   = strength_bar(sig["strength"])
    now   = datetime.now(timezone.utc).strftime("%H:%M UTC")
    sess  = session_label(current_session())
    return f"""{emoji} <b>VEDA TRADER — {sig['type']} SIGNAL</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 <b>Pair:</b>        {sig['pair']}
💰 <b>Entry:</b>       {sig['price']:,.5g}
🛑 <b>Stop Loss:</b>   {sig['sl']:,.5g}
🎯 <b>Take Profit:</b> {sig['tp']:,.5g}
📐 <b>R:R Ratio:</b>   1:{RISK_REWARD}

📈 <b>RSI:</b>         {sig['rsi']}
📦 <b>Volume:</b>      {sig['vol']}x avg
⚡ <b>Strength:</b>    {bar}

✅ <b>All 4 conditions confirmed:</b>
  • EMA {EMA_FAST}/{EMA_SLOW} crossover ✓
  • MACD histogram momentum ✓
  • RSI in safe zone ✓
  • Volume confirmed ✓

🌍 <b>Session:</b> {sess}
🕐 <b>Time:</b>    {now}

⚠️ <i>Execute manually on MT4/MT5. Risk 1–2% max per trade.</i>"""


def fmt_watchlist(sess: str, pairs: list[dict]) -> str:
    lines = "\n".join(f"  • {p['name']}" for p in pairs)
    now   = datetime.now(timezone.utc).strftime("%H:%M UTC")
    tips  = {
        "asian":   "JPY, AUD and NZD crosses are most active. Expect smaller, steadier moves.",
        "london":  "EUR and GBP pairs are waking up. Strong breakouts common in the first 2 hours.",
        "overlap": "Peak liquidity — all pairs can move hard. These are the highest-quality signals of the day.",
        "newyork": "USD pairs dominate. Keep stops tight around news events.",
    }
    return f"""📋 <b>VEDA TRADER — SESSION WATCHLIST</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

{session_label(sess)} has opened.

👀 <b>Pairs being scanned this session:</b>
{lines}

💡 {tips.get(sess, '')}

🔔 Signals fire automatically when all 4 conditions align.
🕐 {now}"""


def fmt_approaching(alerts: list[str]) -> str:
    lines = "\n".join(f"  • {a}" for a in alerts)
    now   = datetime.now(timezone.utc).strftime("%H:%M UTC")
    return f"""⚠️ <b>VEDA TRADER — APPROACHING SIGNALS</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

EMA crossover may fire on the next candle:
{lines}

👀 Open your MT4/MT5 now and watch these pairs.
🕐 {now}"""

# ══════════════════════════════════════════
#  SESSION WATCHLIST (once per session)
# ══════════════════════════════════════════
def maybe_send_watchlist():
    global last_session_alerted
    sess = current_session()
    if sess != last_session_alerted:
        pairs = pairs_for_session(sess)
        if send_telegram(fmt_watchlist(sess, pairs)):
            last_session_alerted = sess
            print(f"  [WATCHLIST] {sess} — {len(pairs)} pairs")

# ══════════════════════════════════════════
#  MAIN SCAN LOOP
# ══════════════════════════════════════════
def scan_markets():
    now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    sess    = current_session()
    pairs   = pairs_for_session(sess)
    print(f"\n[{now_str}] {sess.upper()} | Scanning {len(pairs)} pairs...")

    maybe_send_watchlist()

    signals_found = 0
    approaching   = []

    for p in pairs:
        sig = analyze(p)
        if sig:
            ok = send_telegram(fmt_signal(sig))
            record(sig["pair"], sig["type"])
            print(f"  [{sig['type']} {'✓' if ok else '✗'}] {sig['pair']}  RSI={sig['rsi']}  Vol={sig['vol']}x")
            signals_found += 1
            time.sleep(1)
        else:
            # Approaching crossover check
            df = fetch_ohlcv(p["ticker"])
            if df is not None:
                ef  = ema(df["close"], EMA_FAST)
                es  = ema(df["close"], EMA_SLOW)
                f0, f1 = ef.iloc[-1], ef.iloc[-2]
                s0, s1 = es.iloc[-1], es.iloc[-2]
                gap_pct = abs(f0 - s0) / s0 * 100
                converging = abs(f0 - s0) < abs(f1 - s1)
                if gap_pct < 0.04 and converging:
                    d = "📈 BUY setup" if f0 > s0 else "📉 SELL setup"
                    approaching.append(f"{d} — {p['name']}")
            print(f"  [no signal] {p['name']}")
        time.sleep(0.4)

    if approaching:
        send_telegram(fmt_approaching(approaching))
        print(f"  [APPROACHING] {len(approaching)} pair(s)")

    if not signals_found and not approaching:
        print("  No signals detected.")

# ══════════════════════════════════════════
#  STARTUP MESSAGE
# ══════════════════════════════════════════
def send_startup():
    pair_lines = "\n".join(
        f"  • {p['name']:10}  [{p['session']}]" for p in ALL_PAIRS
    )
    msg = f"""📌 <b>VEDA TRADER — BOT ONLINE v3</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ Scanning every 5 minutes across all sessions
📊 Strategy: EMA {EMA_FAST}/{EMA_SLOW} + MACD + RSI + Volume (4 conditions)
🌍 Data source: Yahoo Finance (real-time Forex)
💼 Execution: Manual on your MT4/MT5

📋 <b>All 18 pairs monitored:</b>
{pair_lines}

⏰ <b>Session schedule (UTC):</b>
  🌏 00:00–07:00  Asian   → JPY / AUD / NZD crosses
  🇬🇧 07:00–16:00  London  → EUR / GBP pairs
  🔥 12:00–16:00  Overlap → All pairs (strongest signals)
  🇺🇸 16:00–21:00  NY      → USD pairs

🔔 Watchlist sent at each session open.
🕐 Started: {datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")}"""
    send_telegram(msg)

# ══════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 54)
    print("     VEDA TRADER — TSS Signal Bot v3")
    print("     18 Pairs | 3 Sessions | EMA+MACD+RSI+Vol")
    print("=" * 54)

    send_startup()
    scan_markets()

    schedule.every(5).minutes.do(scan_markets)

    print("\nBot running. Press Ctrl+C to stop.\n")
    while True:
        schedule.run_pending()
        time.sleep(30)