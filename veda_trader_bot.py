"""
╔══════════════════════════════════════════════════════════╗
║          VEDA TRADER — Signal Bot v4                     ║
║   Polished UI | Next Pair Queue | 18 Pairs | MT4/MT5     ║
╚══════════════════════════════════════════════════════════╝

SETUP:
  1. pip install yfinance pandas requests schedule
  2. Fill in TELEGRAM_TOKEN and CHAT_ID below
  3. python veda_trader_bot.py

WHAT'S NEW IN v4:
  - Polished Telegram UI with ▲ green / ▼ red arrows
  - "Next Up" queue shown after every signal
  - Approaching alerts now say "~X candles away"
  - MACD relaxed: direction-only (no longer requires growing histogram)
  - RSI widened to 35–70 buy / 30–65 sell
  - Cleaner signal card layout for channel display
"""

import os
import time
import math
import schedule
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

# ══════════════════════════════════════════
#  SETTINGS
# ══════════════════════════════════════════
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID        = os.getenv("TELEGRAM_CHANNEL_ID", "")
MONGO_URI      = os.getenv("MONGO_URI", "")

# ── Mongo (best-effort; bot still runs if DB is down) ──
_db = None
try:
    if MONGO_URI:
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        _db = _client["vedatrader"]
        _db.command("ping")
        print("[MongoDB] connected")
except Exception as _e:
    print(f"[MongoDB] connection failed: {_e}")
    _db = None

def _signals_col():
    return _db["signals"] if _db is not None else None

def _status_col():
    return _db["bot_status"] if _db is not None else None

def _errors_col():
    return _db["scan_errors"] if _db is not None else None

TIMEFRAME     = "5m"
LOOKBACK_DAYS = 2

EMA_FAST    = 9
EMA_SLOW    = 21
RSI_PERIOD  = 14
MACD_FAST   = 12
MACD_SLOW   = 26
MACD_SIG    = 9

RSI_BUY_MIN = 30
RSI_BUY_MAX = 75
RSI_SEL_MIN = 25
RSI_SEL_MAX = 70

VOL_MIN       = 0.40
RISK_REWARD   = 2.0
STOP_PERCENT  = 0.3
DEDUPE_MIN    = 10

# Expiration window for binary-style scalping signals
EXPIRY_MINUTES = 2

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
#  SESSION
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

def pairs_for_session(s: str) -> list[dict]:
    tag = "london" if s == "overlap" else s
    return [p for p in ALL_PAIRS if p["session"] in ("all", tag)]

# ══════════════════════════════════════════
#  STATE
# ══════════════════════════════════════════
last_signal_time:     dict = {}
last_session_alerted: str  = ""
pair_status:          dict = {}   # name -> {"candles_away": int, "direction": str}
session_signals:      list = []   # track all signals in current session
current_session_date: str  = ""  # track date for report header
session_signal_no:    int  = 0    # signal counter, resets each session
active_session_name:  str  = ""   # last session we counted under

# ══════════════════════════════════════════
#  TELEGRAM
# ══════════════════════════════════════════
def send_telegram(msg: str) -> bool:
    url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg,
               "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        r   = requests.post(url, json=payload, timeout=15)
        res = r.json()
        if not res.get("ok"):
            print(f"  [Telegram FAIL] {res.get('description')}")
            return False
        return True
    except Exception as e:
        print(f"  [Telegram Error] {e}")
        return False

# ══════════════════════════════════════════
#  DATA
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
        print(f"  [Fetch {ticker}] {e}")
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

# ══════════════════════════════════════════
#  CANDLES-AWAY ESTIMATE
#  Looks at EMA convergence rate over last 3
#  bars and extrapolates to crossover point.
# ══════════════════════════════════════════
def estimate_candles_to_cross(ef: pd.Series, es: pd.Series) -> int:
    """
    Returns estimated candles until EMA crossover.
    Returns 0 if already crossed, 99 if too far.
    """
    gaps = [(ef.iloc[-i] - es.iloc[-i]) for i in range(1, 4)]
    # gaps[0] = most recent gap
    if len(gaps) < 3:
        return 99
    # Rate of change per candle (negative = converging)
    rate = (gaps[0] - gaps[2]) / 2
    if rate == 0 or (gaps[0] > 0 and rate > 0) or (gaps[0] < 0 and rate < 0):
        return 99  # Diverging
    candles = abs(gaps[0] / rate)
    return max(1, math.ceil(candles))

# ══════════════════════════════════════════
#  SIGNAL STRENGTH
# ══════════════════════════════════════════
def calc_strength(gap_pct: float, rsi_val: float, vol_r: float) -> int:
    sc = 0
    if gap_pct > 0.15:        sc += 2
    elif gap_pct > 0.05:      sc += 1
    if 48 <= rsi_val <= 58:   sc += 2
    elif 42 <= rsi_val <= 62: sc += 1
    if vol_r > 1.3:           sc += 1
    return min(sc, 5)

def strength_bar(sc: int) -> str:
    filled = "●" * sc
    empty  = "○" * (5 - sc)
    pct    = sc * 20
    return f"{filled}{empty}  {pct}%"

# ══════════════════════════════════════════
#  DEDUPE
# ══════════════════════════════════════════
def is_dupe(pair: str, direction: str) -> bool:
    last = last_signal_time.get(f"{pair}:{direction}")
    if not last: return False
    return (datetime.now(timezone.utc) - last).total_seconds() / 60 < DEDUPE_MIN

def record_sig(pair: str, direction: str, price: float) -> int:
    """Record signal in session log + bump per-session counter. Returns the signal number."""
    global current_session_date, session_signal_no, active_session_name
    now = datetime.now(timezone.utc)
    sess = current_session()

    # Reset counter on session change
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
        "result": None,        # "WIN" / "LOSS" set by evaluator after expiry
        "exit_price": None,
    })
    current_session_date = now.strftime("%d/%B").upper()
    return session_signal_no


def evaluate_pending_signals():
    """Re-check any signals past their 2-min expiry and stamp WIN/LOSS honestly."""
    now = datetime.now(timezone.utc)
    sigs_col = _signals_col()
    for s in session_signals:
        if s.get("result") is not None:
            continue
        age_min = (now - s["timestamp"]).total_seconds() / 60
        if age_min < EXPIRY_MINUTES:
            continue  # still in flight

        # Find the original pair info to fetch price
        info = next((p for p in ALL_PAIRS if p["name"] == s["pair"]), None)
        if not info: continue
        df = fetch_ohlcv(info["ticker"])
        if df is None or len(df) < 2: continue
        exit_price = float(df["close"].iloc[-1])
        entry = float(s["price"])

        if s["direction"] == "BUY":
            won = exit_price > entry
        else:
            won = exit_price < entry
        s["result"] = "WIN" if won else "LOSS"
        s["exit_price"] = exit_price

        # Persist outcome to DB if available
        if sigs_col is not None:
            try:
                sigs_col.update_one(
                    {"pair": s["pair"], "timestamp": s["timestamp"]},
                    {"$set": {"result": s["result"], "exit_price": exit_price}},
                )
            except Exception as e:
                print(f"  [DB outcome write] {e}")
        print(f"  [OUTCOME] #{s['no']} {s['pair']} {s['direction']} → {s['result']} "
              f"(entry {entry:.5f} → exit {exit_price:.5f})")


def calc_atr(df: pd.DataFrame, n: int = 14) -> float:
    """Average True Range — used to rank pair volatility for the watchlist."""
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(n).mean().iloc[-1]
    last = c.iloc[-1]
    return float(atr / last * 10000) if last else 0.0  # ATR in basis points

def rank_volatile_pairs(pairs: list[dict], top_n: int = 5) -> list[tuple]:
    """Return top N pairs by current ATR (high → low)."""
    scored = []
    for p in pairs:
        try:
            df = fetch_ohlcv(p["ticker"])
            if df is None or len(df) < 20: continue
            scored.append((p["name"], calc_atr(df)))
        except Exception:
            continue
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_n]


def is_session_ending() -> bool:
    """Detect if we're at the final candle of current session"""
    h = datetime.now(timezone.utc).hour
    m = datetime.now(timezone.utc).minute
    # Session end times (last 5min candle):
    # Asian ends at 06:55 (ends 07:00)
    # London ends at 15:55 (ends 16:00)
    # NY ends at 20:55 (ends 21:00)
    session_ends = {
        "asian": (6, 55),
        "london": (15, 55),
        "overlap": (15, 55),
        "newyork": (20, 55)
    }
    sess = current_session()
    end_h, end_m = session_ends.get(sess, (0, 0))
    return h == end_h and m == end_m

# ══════════════════════════════════════════
#  ANALYSIS
# ══════════════════════════════════════════
def analyze(pair_info: dict) -> dict | None:
    df = fetch_ohlcv(pair_info["ticker"])
    if df is None: return None

    closes  = df["close"]
    volumes = df["volume"]
    price   = closes.iloc[-1]

    ef           = calc_ema(closes, EMA_FAST)
    es           = calc_ema(closes, EMA_SLOW)
    rv           = calc_rsi(closes, RSI_PERIOD)
    _, _, hist_s = calc_macd(closes)

    f0, f1   = ef.iloc[-1],    ef.iloc[-2]
    s0, s1   = es.iloc[-1],    es.iloc[-2]
    rsi_now  = rv.iloc[-1]
    hist_now = hist_s.iloc[-1]

    if any(pd.isna(x) for x in [f0, f1, s0, s1, rsi_now, hist_now]):
        return None

    avg_vol   = volumes.iloc[-21:-1].mean()
    vol_ratio = (volumes.iloc[-1] / avg_vol) if avg_vol > 0 else 0
    # Yahoo Finance reports 0 volume for forex (decentralised market).
    # Treat missing volume as "pass" instead of permanently blocking signals.
    good_vol  = (avg_vol == 0) or (vol_ratio >= VOL_MIN)

    bull_x     = (f1 <= s1) and (f0 > s0)
    bear_x     = (f1 >= s1) and (f0 < s0)
    macd_bull  = hist_now > 0   # Relaxed: direction only
    macd_bear  = hist_now < 0

    gap_pct = abs(f0 - s0) / s0 * 100
    gap_prev = abs(f1 - s1)
    converging = abs(f0 - s0) < gap_prev  # gap is getting smaller
    name    = pair_info["name"]

    # Update convergence status for "next up" display
    candles_away = estimate_candles_to_cross(ef, es)
    direction_of_cross = "BUY" if f0 < s0 else "SELL"  # what would fire IF it crosses
    pair_status[name] = {
        "candles_away": candles_away,
        "direction": direction_of_cross,
        "rsi": round(rsi_now, 1),
        "vol": round(vol_ratio, 2),
    }

    # ── PRIMARY TRIGGER: confirmed EMA crossover on the most recent candle ──
    confirmed_buy  = bull_x and macd_bull and good_vol and RSI_BUY_MIN <= rsi_now <= RSI_BUY_MAX
    confirmed_sell = bear_x and macd_bear and good_vol and RSI_SEL_MIN <= rsi_now <= RSI_SEL_MAX

    # ── SECONDARY TRIGGER: 1–2 candles pre-cross (early entry) ──
    pre_signal = candles_away <= 2 and converging and good_vol

    # ── TERTIARY TRIGGER: momentum continuation ──
    # EMAs already stacked the right way + MACD agreeing + price pushing fresh.
    # Catches trends so we don't only trade reversals.
    last3_high = df["high"].iloc[-4:-1].max()
    last3_low  = df["low"].iloc[-4:-1].min()
    fresh_high = closes.iloc[-1] > last3_high
    fresh_low  = closes.iloc[-1] < last3_low

    momentum_buy  = (f0 > s0) and macd_bull and good_vol and fresh_high and \
                    RSI_BUY_MIN <= rsi_now <= RSI_BUY_MAX and (f0 - s0) > (f1 - s1)
    momentum_sell = (f0 < s0) and macd_bear and good_vol and fresh_low and \
                    RSI_SEL_MIN <= rsi_now <= RSI_SEL_MAX and (s0 - f0) > (s1 - f1)

    if confirmed_buy or momentum_buy or (pre_signal and f0 < s0 and RSI_BUY_MIN <= rsi_now <= RSI_BUY_MAX and macd_bull):
        if is_dupe(name, "BUY"): return None
        sl = round(price * (1 - STOP_PERCENT / 100), 6)
        tp = round(price * (1 + STOP_PERCENT / 100 * RISK_REWARD), 6)
        return {
            "type": "BUY",  "pair": name, "price": price,
            "sl": sl, "tp": tp, "rsi": round(rsi_now, 1),
            "vol": round(vol_ratio, 2),
            "strength": calc_strength(gap_pct, rsi_now, vol_ratio),
            "trigger": "CROSS" if confirmed_buy else ("MOMO" if momentum_buy else "PRE"),
        }

    if confirmed_sell or momentum_sell or (pre_signal and f0 > s0 and RSI_SEL_MIN <= rsi_now <= RSI_SEL_MAX and macd_bear):
        if is_dupe(name, "SELL"): return None
        sl = round(price * (1 + STOP_PERCENT / 100), 6)
        tp = round(price * (1 - STOP_PERCENT / 100 * RISK_REWARD), 6)
        return {
            "type": "SELL", "pair": name, "price": price,
            "sl": sl, "tp": tp, "rsi": round(rsi_now, 1),
            "vol": round(vol_ratio, 2),
            "strength": calc_strength(gap_pct, rsi_now, vol_ratio),
            "trigger": "CROSS" if confirmed_sell else ("MOMO" if momentum_sell else "PRE"),
        }

    return None

# ══════════════════════════════════════════
#  "NEXT UP" QUEUE BUILDER
#  Returns top 3 closest-to-signal pairs
#  (excluding the pair that just signalled)
# ══════════════════════════════════════════
def build_next_queue(exclude_pair: str) -> str:
    candidates = [
        (name, info) for name, info in pair_status.items()
        if name != exclude_pair and info["candles_away"] <= 10
    ]
    candidates.sort(key=lambda x: x[1]["candles_away"])

    if not candidates:
        return "  📭 No pairs approaching right now."

    lines = []
    for name, info in candidates[:3]:
        arrow   = "▲" if info["direction"] == "BUY" else "▼"
        color   = "🟢" if info["direction"] == "BUY"  else "🔴"
        candles = info["candles_away"]
        label   = f"~{candles} candle{'s' if candles != 1 else ''} away"
        lines.append(f"  {color} {arrow} {name}  —  {label}  (RSI {info['rsi']})")

    return "\n".join(lines)

# ══════════════════════════════════════════
#  MESSAGE TEMPLATES
# ══════════════════════════════════════════
def fmt_signal(sig: dict, sig_no: int = 0) -> str:
    is_buy  = sig["type"] == "BUY"
    color   = "🟩" if is_buy else "🟥"
    label   = "BUY / CALL" if is_buy else "SELL / PUT"
    sess    = current_session()
    sess_lbl = session_label(sess).split(" ", 1)[-1]  # drop the leading emoji

    now = datetime.now(timezone.utc)
    now_str = now.strftime("%H:%M")
    base = now.replace(second=0, microsecond=0)
    t1 = (base + timedelta(minutes=EXPIRY_MINUTES)).strftime("%H:%M")
    t2 = (base + timedelta(minutes=EXPIRY_MINUTES * 2)).strftime("%H:%M")
    t3 = (base + timedelta(minutes=EXPIRY_MINUTES * 3)).strftime("%H:%M")

    header = f"📡 SIGNAL #{sig_no} · {sess_lbl}" if sig_no else "📡 SIGNAL"

    return (
        f"{header}\n"
        f"💰 {EXPIRY_MINUTES}-minute expiration\n"
        f"{sig['pair']}; {now_str}; {label} {color}\n"
        f"\n"
        f"🕐 TIME TO {t1}\n"
        f"1st GALE —> TIME TO {t2}\n"
        f"2nd GALE — TIME TO {t3}"
    )


def fmt_watchlist(sess: str, pairs: list[dict], volatile: list[tuple] | None = None) -> str:
    now_str = datetime.now(timezone.utc).strftime("%H:%M UTC")
    tips = {
        "asian":   "JPY, AUD and NZD crosses most active. Expect tight, steady moves.",
        "london":  "EUR and GBP wake up now. First 2 hours = strongest breakouts.",
        "overlap": "Peak liquidity. All pairs can run hard. Best signals of the day.",
        "newyork": "USD pairs dominate. Keep SL tight around news events.",
    }
    lines = "\n".join(
        f"  {'🟢' if i % 2 == 0 else '🔵'} {p['name']}"
        for i, p in enumerate(pairs)
    )

    vol_block = ""
    if volatile:
        v_lines = "\n".join(
            f"  🔥 <b>{name}</b> — ATR {atr:.1f} bps"
            for name, atr in volatile
        )
        vol_block = (
            f"\n<b>🎯 Top movers this session (focus list):</b>\n{v_lines}\n"
        )

    return (
        f"📋 <b>VEDA TRADER — SESSION WATCHLIST</b>\n"
        f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"\n"
        f"{session_label(sess)} has opened.\n"
        f"{vol_block}\n"
        f"<b>All pairs scanned this session:</b>\n"
        f"{lines}\n"
        f"\n"
        f"💡 {tips.get(sess, '')}\n"
        f"\n"
        f"🔔 Signals fire when EMA + MACD + RSI align.\n"
        f"🕐 {now_str}"
    )


def fmt_approaching(alerts: list[tuple]) -> str:
    """
    alerts = list of (pair_name, direction, candles_away)
    """
    now_str = datetime.now(timezone.utc).strftime("%H:%M UTC")
    lines = []
    for name, direction, candles in alerts:
        arrow = "▲" if direction == "BUY"  else "▼"
        color = "🟢" if direction == "BUY"  else "🔴"
        label = "BUY / CALL" if direction == "BUY" else "SELL / PUT"
        lines.append(
            f"  {color} {arrow} <b>{name}</b>  —  {label}  (~{candles} candle{'s' if candles != 1 else ''})"
        )
    body = "\n".join(lines)
    return (
        f"⚠️ <b>VEDA TRADER — SIGNALS APPROACHING</b>\n"
        f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"\n"
        f"EMA crossover expected soon:\n"
        f"\n"
        f"{body}\n"
        f"\n"
        f"👀 Open MT4/MT5 and get ready.\n"
        f"🕐 {now_str}"
    )


def fmt_session_report() -> str:
    """End-of-session report with REAL win/loss outcomes (evaluator-driven)."""
    if not session_signals:
        return f"📊 Operations Report ({current_session_date})\n\n\nNo signals recorded this session.\n"

    # Make sure every signal has been evaluated before we report
    evaluate_pending_signals()

    lines = []
    wins = losses = pending = 0
    for sig in session_signals:
        dir_label = "BUY/CALL" if sig["direction"] == "BUY" else "SELL/PUT"
        no = sig.get("no", "?")
        result = sig.get("result")
        if result == "WIN":
            tag = "GAIN ✅"; wins += 1
        elif result == "LOSS":
            tag = "LOSS ❌"; losses += 1
        else:
            tag = "PENDING ⏳"; pending += 1
        lines.append(f"#{no}  {sig['pair']}; {sig['time']}; {dir_label} → {tag}")

    total = wins + losses
    wr = f"{(wins / total * 100):.0f}%" if total else "—"

    report = (
        f"📊 <b>VEDA TRADER — Operations Report</b>\n"
        f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"<b>{current_session_date}</b>\n\n"
        f"{chr(10).join(lines)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ {wins} WIN     ❌ {losses} LOSS"
        + (f"     ⏳ {pending} PENDING" if pending else "") +
        f"\n🎯 Win rate: <b>{wr}</b>\n"
    )
    return report

def fmt_session_alert(session_name: str, utc_hour: int) -> str:
    """Format pre-session alert 60 minutes before start"""
    session_names = {
        "london": "London Session",
        "newyork": "New York Session",
        "asian": "Asian Session",
        "overlap": "London/NY Overlap"
    }
    
    utc_time = f"{utc_hour:02d}:00"
    
    return (
        f"‼️ SET YOUR ALARMS ‼️\n"
        f"\n"
        f"THE \"{session_names.get(session_name, session_name).upper()}\" WILL START IN 60 MINUTES\n"
        f"\n"
        f"STARTS AT {utc_time} (UTC)\n"
        f"\n"
        f"🇬🇧 UK – Starts at {utc_hour + 1:02d}:00\n"
        f"🇿🇦 South Africa – Starts at {utc_hour + 2:02d}:00\n"
        f"🇪🇸 Spain – Starts at {utc_hour + 1:02d}:00\n"
        f"🇧🇷 Brazil – Starts at {utc_hour - 3:02d}:00\n"
        f"🇺🇸 Miami – Starts at {utc_hour - 4:02d}:00\n"
        f"🇲🇽 Mexico – Starts at {utc_hour - 6:02d}:00\n"
        f"🇨🇴 Colombia – Starts at {utc_hour - 5:02d}:00\n"
        f"🇳🇬 Nigeria – Starts at {utc_hour + 1:02d}:00\n"
        f"🇮🇳 India – Starts at {utc_hour + 5:02d}:30\n"
        f"🇲🇾 Malaysia – Starts at {utc_hour + 8:02d}:00\n"
        f"🇵🇭 Philippines – Starts at {utc_hour + 8:02d}:00\n"
        f"\n"
        f"Duration: {4 if session_name == 'london' else 5 if session_name == 'newyork' else 7} hours"
    )


# ══════════════════════════════════════════
#  SESSION WATCHLIST (once per session)
# ══════════════════════════════════════════
def maybe_send_watchlist():
    global last_session_alerted
    sess = current_session()
    if sess != last_session_alerted:
        pairs = pairs_for_session(sess)
        # Rank top movers by ATR for the focus list
        try:
            volatile = rank_volatile_pairs(pairs, top_n=5)
        except Exception as e:
            print(f"  [WATCHLIST volatility rank failed] {e}")
            volatile = []
        if send_telegram(fmt_watchlist(sess, pairs, volatile)):
            last_session_alerted = sess
            top = ", ".join(n for n, _ in volatile) or "—"
            print(f"  [WATCHLIST] {sess} — {len(pairs)} pairs · top movers: {top}")


last_pre_session_alerted: str = ""

def maybe_send_pre_session_alert():
    global last_pre_session_alerted
    now = datetime.now(timezone.utc)
    h = now.hour
    m = now.minute
    
    # Only trigger on the first 5 minutes of each alert hour
    if m > 5:
        return
    
    session_starts = {
        ("asian", 0): 23,    # Asian starts 00:00 → alert 23:00
        ("london", 7): 6,    # London starts 07:00 → alert 06:00
        ("overlap", 12): 11, # Overlap starts 12:00 → alert 11:00
        ("newyork", 16): 15  # NY starts 16:00 → alert 15:00
    }
    
    for (sess_name, start_h), alert_h in session_starts.items():
        if h == alert_h and last_pre_session_alerted != sess_name:
            send_telegram(fmt_session_alert(sess_name, start_h))
            last_pre_session_alerted = sess_name
            print(f"  [PRE-ALERT] {sess_name} — 60 minute warning sent")
            return

# ══════════════════════════════════════════
#  MAIN SCAN
# ══════════════════════════════════════════
def _record_signal_db(sig: dict, telegram_ok: bool):
    col = _signals_col()
    if col is None: return
    try:
        col.insert_one({
            "type": sig["type"],
            "pair": sig["pair"],
            "price": float(sig["price"]),
            "sl": sig["sl"], "tp": sig["tp"],
            "rsi": sig["rsi"], "vol": sig["vol"],
            "strength": sig["strength"],
            "trigger": sig.get("trigger", "CROSS"),
            "expiry_minutes": EXPIRY_MINUTES,
            "telegram_ok": bool(telegram_ok),
            "timestamp": datetime.now(timezone.utc),
        })
    except Exception as e:
        print(f"  [DB signal write] {e}")

def _record_status(sess: str, pairs_scanned: int, signals_found: int, errors: list):
    col = _status_col()
    if col is None: return
    try:
        col.update_one(
            {"_id": "latest"},
            {"$set": {
                "last_scan_at": datetime.now(timezone.utc),
                "session": sess,
                "pairs_scanned": pairs_scanned,
                "signals_found": signals_found,
                "errors_in_scan": len(errors),
            },
             "$inc": {"total_scans": 1, "total_signals": signals_found}},
            upsert=True,
        )
    except Exception as e:
        print(f"  [DB status write] {e}")

def _record_error(pair: str, err: str):
    col = _errors_col()
    if col is None: return
    try:
        col.insert_one({
            "pair": pair, "error": str(err)[:500],
            "timestamp": datetime.now(timezone.utc),
        })
    except Exception:
        pass


def scan_markets():
    now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    sess    = current_session()
    pairs   = pairs_for_session(sess)
    print(f"\n[{now_str}] {sess.upper()} | {len(pairs)} pairs")

    # Evaluate any signals whose 2-min expiry has passed → real WIN/LOSS
    try:
        evaluate_pending_signals()
    except Exception as e:
        print(f"  [evaluator error] {e}")

    maybe_send_watchlist()
    maybe_send_pre_session_alert()

    signals_found = 0
    scan_errors: list = []

    for p in pairs:
        name = p["name"]
        try:
            sig = analyze(p)   # also populates pair_status[name]
        except Exception as e:
            print(f"  [analyze error] {name}: {e}")
            _record_error(name, e)
            scan_errors.append(name)
            continue

        if sig:
            sig_no = record_sig(name, sig["type"], sig["price"])
            ok = send_telegram(fmt_signal(sig, sig_no))
            _record_signal_db(sig, ok)
            arrow = "▲" if sig["type"] == "BUY" else "▼"
            print(f"  [#{sig_no} {arrow} {sig['type']} {'✓' if ok else '✗'}] {name}  "
                  f"RSI={sig['rsi']}  trig={sig.get('trigger','?')}")
            signals_found += 1
            time.sleep(1)
        else:
            status = pair_status.get(name, {})
            ca     = status.get("candles_away", 99)
            print(f"  [no signal] {name}  {f'⚡ ~{ca}c' if ca <= 5 else ''}")

        time.sleep(0.4)

    # Persist scan status (last cron run, counts, error count)
    _record_status(sess, len(pairs), signals_found, scan_errors)

    # Send end-of-session report if this is the final candle
    if is_session_ending() and session_signals:
        send_telegram(fmt_session_report())
        print(f"  [SESSION REPORT] Sent with {len(session_signals)} signals")
        session_signals.clear()

    if not signals_found:
        print("  Quiet market — no signals.")

# ══════════════════════════════════════════
#  STARTUP
# ══════════════════════════════════════════
def send_startup():
    all_names = ", ".join(p["name"] for p in ALL_PAIRS)
    msg = (
        f"📌 <b>VEDA TRADER — BOT ONLINE  v4</b>\n"
        f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"\n"
        f"✅  Scanning every <b>5 minutes</b>, 24/5\n"
        f"📊  Strategy: EMA {EMA_FAST}/{EMA_SLOW} + MACD + RSI + Volume\n"
        f"💼  Execution: Manual on your MT4/MT5\n"
        f"🌍  Data: Yahoo Finance (live Forex)\n"
        f"\n"
        f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"<b>18 pairs monitored:</b>\n"
        f"  {all_names}\n"
        f"\n"
        f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"<b>Session schedule (UTC):</b>\n"
        f"  🌏  00:00–07:00   Asian   → AUD / JPY / NZD\n"
        f"  🇬🇧  07:00–16:00   London  → EUR / GBP\n"
        f"  🔥  12:00–16:00   Overlap → All pairs (best)\n"
        f"  🇺🇸  16:00–21:00   NY      → USD pairs\n"
        f"\n"
        f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"<b>Signal key:</b>\n"
        f"  🟢 ▲  BUY / CALL   —   Go Long\n"
        f"  🔴 ▼  SELL / PUT   —   Go Short\n"
        f"\n"
        f"🔔  Watchlist sent at each session open.\n"
        f"🕐  Started: {datetime.now(timezone.utc).strftime('%d %b %Y  %H:%M UTC')}"
    )
    send_telegram(msg)

# ══════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 54)
    print("     VEDA TRADER — Signal Bot v4")
    print("     18 Pairs | 3 Sessions | EMA+MACD+RSI+Vol")
    print("=" * 54)

    send_startup()
    scan_markets()

    schedule.every(5).minutes.do(scan_markets)

    print("\nBot is running. Press Ctrl+C to stop.\n")
    while True:
        schedule.run_pending()
        time.sleep(30)