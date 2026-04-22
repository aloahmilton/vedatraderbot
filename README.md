# Veda Trader Bot v5
## TSS Tri Session Sentinel Trading Bot

Professional real-time trading signal bot for Telegram with a clean, modular architecture.

## ✨ Features

- ✅ **Modular Architecture**: Clean code separated into `config`, `engine`, `indicators`, `notifier`, and `database`.
- ✅ **Premium UI**: Professional Telegram message formatting with grid-style watchlists and polished reports.
- ✅ **5-Layer Filter Stack**: Time + Volatility + Trend + Momentum + Entry filters for high-accuracy signals.
- ✅ **Session Intelligence**: Automated Watchlists and Reports for London, New York, and Asian sessions.
- ✅ **Automatic Outcome Tracking**: Real-time WIN/LOSS evaluation and gain/loss percentage reporting.

## 🚀 Installation & Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
# Edit .env or src/config.py with your TELEGRAM_TOKEN and MONGO_URI
```

## 🎯 Usage

```bash
# Start the Signal Bot
python main.py

# Start the Web Dashboard
python app.py
```

### Telegram Commands
- `/start` - Bot info and welcome message
- `/status` - Check bot health and current session
- `/pairs` - List all monitored currency pairs
- `/sessions` - View the trading session schedule

## 📂 File Structure

```text
veda/
├── main.py             # Main Signal Bot entry point
├── app.py              # Web Dashboard (Flask)
├── Procfile            # Deployment config
├── src/
│   ├── config.py       # Strategy params, pairs, and sessions
│   ├── engine.py       # Signal filtering and analysis brain
│   ├── indicators.py   # Pure math for EMA, RSI, ADX, etc.
│   ├── notifier.py     # Telegram formatting and command handling
│   └── database.py     # MongoDB integration and state management
├── webapp/             # Dashboard HTML templates
└── old_versions/       # Archived legacy files (backup)
```

## 🛠 Strategy Logic
The bot uses a **5-Layer Filter Stack** to ensure only high-probability trades are sent:
1. **Time Filter**: Avoids dead liquidity hours.
2. **Volatility Filter**: Checks ATR and Bollinger Band squeeze status.
3. **Trend Filter**: Aligns 5M signals with the 15M higher timeframe trend.
4. **Momentum Filter**: Confirms direction with ADX, MACD, and RSI crossovers.
5. **Entry Filter**: Verifies candle body size and proximity to Support/Resistance.

---

**⚠️ Trading involves risk. Only risk capital you can afford to lose. This bot is for educational purposes.**