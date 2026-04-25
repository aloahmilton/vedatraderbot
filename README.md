# ⚡ VEDA TRADER — Setup Guide

## Project Structure
```
veda_trader/
├── main.py              ← Run this
├── requirements.txt
├── .env.example         ← Copy to .env and fill in your values
└── src/
    ├── config.py        ← Pairs, sessions, settings
    ├── engine.py        ← Real signal logic (RSI, EMA, MACD)
    ├── notifier.py      ← Telegram messages
    ├── database.py      ← MongoDB helpers
    └── ai_admin.py      ← AI assistant (Claude-powered)
```

---

## Step 1 — Install Python packages
```bash
pip install -r requirements.txt
```

---

## Step 2 — Set up your Telegram Bot

1. Open Telegram → search **@BotFather**
2. Send `/newbot` → follow the steps → copy your **BOT TOKEN**
3. Create two channels:
   - One for **Free** (Forex signals)
   - One for **Premium** (Forex + Indices + Crypto + Gold)
4. Add your bot as **admin** to both channels
5. Get your channel IDs:
   - Forward a message from your channel to **@userinfobot**
   - It will show the channel ID (starts with -100...)
6. Get your personal Telegram ID:
   - Message **@userinfobot** directly → it shows your ID

---

## Step 3 — Set up MongoDB

1. Go to [mongodb.com](https://mongodb.com) → create a free cluster
2. Go to **Database Access** → Add a user with read/write permissions
3. Go to **Network Access** → Allow access from anywhere (0.0.0.0/0)
4. Click **Connect** → copy the connection string
5. Replace `<password>` in the URI with your actual password

---

## Step 4 — Get your Anthropic API Key (for AI admin)

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Create an API key
3. Add it to your .env as `ANTHROPIC_API_KEY`

---

## Step 5 — Configure your .env

```bash
cp .env.example .env
```

Edit `.env` with all your values.

---

## Step 6 — Run the bot

```bash
python main.py
```

---

## Admin Panel
Open in your browser: `http://localhost:5000/admin`
- Username: what you set in .env (default: `admin`)
- Password: what you set in .env

---

## Admin Telegram Commands

| Command | Description |
|---------|-------------|
| `/grant <telegram_id>` | Give user premium access |
| `/revoke <telegram_id>` | Remove premium access |
| `/kick <telegram_id>` | Remove subscriber |
| `/subscribers` | View all subscriber counts |
| `/summary` | Get today's performance summary |
| `/broadcast <message>` | Send message to all channels |
| `/pause` | Pause all signals |
| `/resume` | Resume signals |

---

## How Signals Work

### Free Channel (Forex Scalping)
- Scans: EUR/USD, GBP/USD, USD/JPY, GBP/JPY and more
- Timeframe: 1-minute candles
- Duration: 3-5 minutes per trade
- Strategy: RSI + EMA crossover + MACD + Bollinger Bands
- Min score threshold: 65/100

### Premium Channel (Normal Trading)
- Scans: Forex + Indices (US30, NAS100, GER40) + Crypto + Gold
- Timeframe: 15-minute candles
- Duration: 30-60 minutes per trade
- Strategy: Same indicators, higher threshold (70/100)
- R:R ratio: 1:2 minimum

### Sessions
- 🌏 Asian: 00:00–08:00 UTC
- 🇬🇧 London: 08:00–16:00 UTC
- 🗽 New York: 13:00–22:00 UTC
- Signals STOP at end of each session, resume at next open

### AI Admin Features
- Auto-replies to subscriber questions in DMs
- Sends you hourly summaries
- Auto-pauses signals if win rate drops below 30%
- Alerts you to unusual market patterns

---

## Deploy to Render (Free Hosting)

1. Push code to GitHub
2. Go to [render.com](https://render.com) → New Web Service
3. Connect your repo
4. Set environment variables (copy from your .env)
5. Start command: `python main.py`
6. Done — bot runs 24/7 for free!
