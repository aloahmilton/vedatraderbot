# Veda Trader Bot
## TSS Tri Session Sentinel Trading Bot

Professional real-time trading signal bot for Telegram. Implements the TSS Tri Session Sentinel strategy exactly as per TradingView Pine Script.

## Features
✅ 100% matching TSS Pine Script logic
✅ Real-time 5 minute market scanning
✅ Instant Telegram channel alerts
✅ Consistent volume filters (no volatility spikes)
✅ Upcoming pair previews in every signal
✅ UTC timezone clearly marked
✅ 24/7 operation
✅ 7 top pairs scanned continuously

## Active Pairs
| Pair | Type |
|---|---|
| EUR/USD | Major Forex |
| GBP/USD | Major Forex |
| USD/JPY | Major Forex |
| USD/CAD | Commodity Forex |
| AUD/USD | Commodity Forex |

## Strategy Rules   
Signals trigger ONLY when ALL conditions are met:
1. EMA 9 crosses EMA 21
2. RSI 14 between 40-65
3. Volume above 20 period average
4. Normal volume range 0.8x - 3.0x (no extreme spikes)

## Installation
```bash
pip install -r requirements.txt
```

## Usage
```bash
# Run bot normally
python veda_trader_bot.py

# Run with auto-reload on script changes
python auto_reload_bot.py
```

## Configuration
Edit these values at top of `veda_trader_bot.py`:
```python
TELEGRAM_TOKEN = "your_bot_token_here"
CHAT_ID        = "your_channel_id_here"
```

## Telegram Channel
All signals are sent automatically to your configured Telegram channel in real time.

## Hosting
For 24/7 uptime host on:
- Replit
- Render
- Railway
- Any VPS

---
**⚠️ Trading involves risk. Only risk capital you can afford to lose.**