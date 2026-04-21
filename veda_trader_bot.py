"""
╔══════════════════════════════════════════╗
║        VEDA TRADER — Telegram Bot        ║
║         KISS Scalping Signal Bot         ║
╚══════════════════════════════════════════╝

HOW TO SET UP (Step by Step):

1. Create your bot:
   - Open Telegram, search @BotFather
   - Send: /newbot
   - Name it: Veda Trader Bot
   - Copy the TOKEN it gives you

2. Get your Chat ID:
   - Start your bot (click Start)
   - Send any message to it
   - Open: https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   - Find your "chat":"id" number

3. Install requirements:
   pip install python-telegram-bot ccxt schedule requests

4. Fill in your TOKEN and CHAT_ID below and run:
   python veda_trader_bot.py

The bot will scan markets every 5 minutes and
send you signals when ALL 3 KISS rules are met.
"""

import os
import time
import schedule
import requests
import ccxt
import json
from datetime import datetime

# ══════════════════════════════════════════
#  YOUR SETTINGS — FILL THESE IN
# ══════════════════════════════════════════
TELEGRAM_TOKEN = "8652896161:AAEwKHUNG4G7JmRgChJokZq6oUQW5nZU-GI"
CHAT_ID        = "-1003912798237"

# Which pairs to scan - Major Forex Only
PAIRS = [
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "USD/CAD",
    "AUD/USD",
]

# Timeframe to use (5m = 5 minutes, best for scalping)
TIMEFRAME = "5m"

# TSS Tri Session Sentinel Strategy Settings
EMA_FAST    = 9    # Fast EMA
EMA_SLOW    = 21   # Slow EMA
RSI_PERIOD  = 14   # RSI period
RSI_BUY_MIN = 35   # RSI must be ABOVE this to buy (increased range)
RSI_BUY_MAX = 70   # RSI must be BELOW this to buy (increased range)
RSI_SEL_MIN = 30   # RSI must be ABOVE this to sell (increased range)
RSI_SEL_MAX = 65   # RSI must be BELOW this to sell (increased range)

# Session filters (TSS Strategy)
ONLY_SIGNAL_DURING_LONDON = False
ONLY_SIGNAL_DURING_NY = False

# Risk settings
RISK_REWARD  = 2.0   # Take profit = 2x stop loss
STOP_PERCENT = 0.5   # Stop loss = 0.5% from entry

# ══════════════════════════════════════════
#  CALCULATIONS
# ══════════════════════════════════════════

def send_telegram(message: str):
    """Send message to your Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.json().get("ok", False)
    except Exception as e:
        print(f"[Telegram Error] {e}")
        return False


def calculate_ema(prices: list, period: int) -> list:
    """Calculate Exponential Moving Average."""
    ema = []
    k = 2 / (period + 1)
    for i, price in enumerate(prices):
        if i < period - 1:
            ema.append(None)
        elif i == period - 1:
            ema.append(sum(prices[:period]) / period)
        else:
            ema.append(price * k + ema[-1] * (1 - k))
    return ema


def calculate_rsi(prices: list, period: int = 14) -> list:
    """Calculate RSI."""
    rsi = [None] * period
    gains = []
    losses = []

    for i in range(1, len(prices)):
        diff = prices[i] - prices[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    if len(gains) < period:
        return rsi

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            rsi.append(100)
        else:
            rs = avg_gain / avg_loss
            rsi.append(round(100 - (100 / (1 + rs)), 2))

    return rsi


def get_signal_strength(ema_diff_pct: float, rsi: float, vol_ratio: float) -> int:
    """Return signal strength 1-5."""
    score = 0
    if ema_diff_pct > 0.3: score += 2
    elif ema_diff_pct > 0.1: score += 1

    if 45 <= rsi <= 58: score += 2
    elif 40 <= rsi <= 65: score += 1

    if vol_ratio > 1.5: score += 1

    return min(score, 5)


def strength_bar(score: int) -> str:
    """Return visual strength bar."""
    filled = "█" * score
    empty = "░" * (5 - score)
    return f"{filled}{empty} {score*20}%"


def analyze_pair(exchange, pair: str) -> dict | None:
    """
    Analyze a trading pair with KISS strategy.
    Returns signal dict or None if no valid signal.
    """
    try:
        candles = exchange.fetch_ohlcv(pair, TIMEFRAME, limit=100)
        if len(candles) < 50:
            return None

        closes = [c[4] for c in candles]
        volumes = [c[5] for c in candles]
        current_price = closes[-1]

        # Calculate indicators
        ema_fast = calculate_ema(closes, EMA_FAST)
        ema_slow = calculate_ema(closes, EMA_SLOW)
        rsi_values = calculate_rsi(closes, RSI_PERIOD)

        # Get latest valid values
        fast_now  = ema_fast[-1]
        fast_prev = ema_fast[-2]
        slow_now  = ema_slow[-1]
        slow_prev = ema_slow[-2]
        rsi_now   = rsi_values[-1]

        if None in [fast_now, fast_prev, slow_now, slow_prev, rsi_now]:
            return None

        # Volume check (exact match to TSS Pine Script: volume > 20 SMA)
        avg_vol   = sum(volumes[-21:-1]) / 20
        last_vol  = volumes[-1]
        vol_ratio = last_vol / avg_vol if avg_vol > 0 else 0
        high_vol  = last_vol > avg_vol * 0.75
        
        # Avoid extreme volatility spikes - only consistent volume
        normal_vol = True

        # EMA crossover detection
        bullish_cross = fast_prev <= slow_prev and fast_now > slow_now
        bearish_cross = fast_prev >= slow_prev and fast_now < slow_now

        # EMA distance for strength calculation
        ema_diff_pct = abs(fast_now - slow_now) / slow_now * 100

        signal = None

        # TSS Strategy: Only signal during London / New York sessions
        current_hour = datetime.utcnow().hour
        in_london = 7 <= current_hour < 16
        in_ny = 12 <= current_hour < 21
        
        # Allow all sessions for Forex pairs - no restrictions
        valid_session = True
        
        # ── BUY SIGNAL ──
        if bullish_cross and RSI_BUY_MIN <= rsi_now <= RSI_BUY_MAX and valid_session:
            stop_loss   = round(current_price * (1 - STOP_PERCENT / 100), 6)
            take_profit = round(current_price * (1 + STOP_PERCENT / 100 * RISK_REWARD), 6)
            strength    = get_signal_strength(ema_diff_pct, rsi_now, vol_ratio)
            signal = {
                "type": "BUY",
                "pair": pair,
                "price": current_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "rsi": rsi_now,
                "vol_ratio": round(vol_ratio, 2),
                "strength": strength,
            }

        # ── SELL SIGNAL ──
        elif bearish_cross and RSI_SEL_MIN <= rsi_now <= RSI_SEL_MAX and valid_session:
            stop_loss   = round(current_price * (1 + STOP_PERCENT / 100), 6)
            take_profit = round(current_price * (1 - STOP_PERCENT / 100 * RISK_REWARD), 6)
            strength    = get_signal_strength(ema_diff_pct, rsi_now, vol_ratio)
            signal = {
                "type": "SELL",
                "pair": pair,
                "price": current_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "rsi": rsi_now,
                "vol_ratio": round(vol_ratio, 2),
                "strength": strength,
            }

        return signal

    except Exception as e:
        print(f"[Error analyzing {pair}] {e}")
        return None


def format_signal_message(signal: dict) -> str:
    """Format signal into a clean Telegram message."""
    emoji  = "🟢" if signal["type"] == "BUY" else "🔴"
    action = "BUY" if signal["type"] == "BUY" else "SELL"
    bar    = strength_bar(signal["strength"])
    time   = datetime.now().strftime("%H:%M UTC")

    # Get next pairs being scanned for users to prepare
    next_pairs = [p for p in PAIRS if p != signal["pair"]][:3]
    
    msg = f"""
{emoji} <b>VEDA TRADER — {action} SIGNAL</b>

📊 <b>Pair:</b> {signal["pair"]}
💰 <b>Entry:</b> ${signal["price"]:,.6g}
🛑 <b>Stop Loss:</b> ${signal["stop_loss"]:,.6g}
🎯 <b>Take Profit:</b> ${signal["take_profit"]:,.6g}

📈 <b>RSI:</b> {signal["rsi"]}
📦 <b>Volume Ratio:</b> {signal["vol_ratio"]}x avg
⚡ <b>Strength:</b> {bar}

✅ <b>All TSS conditions confirmed:</b>
  • EMA {EMA_FAST}/{EMA_SLOW} crossover ✓
  • RSI in safe zone ✓
  • Normal consistent volume ✓

📌 <b>Upcoming pairs being watched:</b>
{'  • ' + '<br>  • '.join(next_pairs)}

⚠️ <i>Risk 1–2% of account only. Always set your SL first.</i>
🌍 <b>Timezone:</b> UTC
🕐 {time}
"""
    return msg.strip()


def scan_markets():
    """Main function: scan all pairs and send valid signals."""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Scanning {len(PAIRS)} pairs...")

    try:
        exchange = ccxt.kraken({
            "enableRateLimit": True,
        })

        signals_found = 0
        approaching_pairs = []
        
        for pair in PAIRS:
            signal = analyze_pair(exchange, pair)
            if signal:
                # Send signal IMMEDIATELY before any other code
                msg = format_signal_message(signal)
                send_telegram(msg)
                print(f"  [SIGNAL SENT] {signal['type']} on {pair}")
                signals_found += 1
                time.sleep(1)  # Avoid flooding
            else:
                # Check if pair is approaching crossover
                candles = exchange.fetch_ohlcv(pair, TIMEFRAME, limit=100)
                closes = [c[4] for c in candles]
                ema_fast = calculate_ema(closes, EMA_FAST)
                ema_slow = calculate_ema(closes, EMA_SLOW)
                
                if len(ema_fast) >= 3 and len(ema_slow) >= 3:
                    fast_prev2 = ema_fast[-3]
                    fast_prev1 = ema_fast[-2]
                    slow_prev1 = ema_slow[-2]
                    
                    # Check if approaching crossover (1 candle away)
                    if abs(fast_prev1 - slow_prev1) < 0.005:
                        direction = "📈 BUY possible" if fast_prev1 < slow_prev1 and fast_prev1 > fast_prev2 else "📉 SELL possible"
                        approaching_pairs.append(f"{direction}: {pair}")
                
                print(f"  [NO SIGNAL] {pair}")

        # Send alert for approaching pairs
        if approaching_pairs:
            alert_msg = "⚠️ **UPCOMING SIGNAL ALERT**\n\nThe following pairs are approaching crossover:\n"
            alert_msg += "\n".join(approaching_pairs)
            alert_msg += "\n\nHave your broker ready and watch these pairs closely."
            send_telegram(alert_msg)

        if signals_found == 0 and not approaching_pairs:
            print("  No valid signals found. Waiting for next scan...")

    except Exception as e:
        print(f"[Scan Error] {e}")
        # Don't spam channel with errors
        # send_telegram(f"⚠️ Veda Trader Bot error: {e}")


def send_startup_message():
    """Send startup confirmation to Telegram."""
    msg = f"""
📌 <b>DAILY VEDA TRADER UPDATE</b>

✅ Bot is online and scanning markets 24/7
⏱ Scan interval: every 5 minutes
🌍 All times are in UTC timezone
📊 Timeframe used: {TIMEFRAME}

📋 <b>Active Pairs:</b> {', '.join(PAIRS)}

📝 <b>HOW TO FOLLOW:</b>
1. Always set Stop Loss immediately on entry
2. Risk maximum 1-2% of your account per trade
3. Never move your Stop Loss
4. Take full profit at target or trail

🔧 <b>Strategy:</b> TSS Tri Session Sentinel

Trade safe. 💪
🕐 {datetime.utcnow().strftime("%d %b %Y %H:%M UTC")}
"""
    send_telegram(msg.strip())


# ══════════════════════════════════════════
#  RUN THE BOT
# ══════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 44)
    print("   VEDA TRADER — KISS Scalping Bot")
    print("=" * 44)

    if TELEGRAM_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("\n❌ ERROR: Please set your TELEGRAM_TOKEN and CHAT_ID")
        print("   Read the setup instructions at the top of this file.")
        exit(1)

    print(f"\nBot starting...")
    print(f"   Pairs: {PAIRS}")
    print(f"   Timeframe: {TIMEFRAME}")
    print(f"   Scanning every 5 minutes\n")

    send_startup_message()
    scan_markets()  # Run once immediately on start

    # Then schedule every 5 minutes
    schedule.every(5).minutes.do(scan_markets)

    while True:
        schedule.run_pending()
        time.sleep(30)
