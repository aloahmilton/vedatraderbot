# VEDA TRADER — Setup & Bug Fix Guide

## What Was Fixed (5 Bugs)

### Bug 1 — yfinance Blocked (CRITICAL — Why Bot Sent No Signals)
**Symptom:** Bot runs but never generates any signals. Console shows `HTTP Error 403`.  
**Cause:** Yahoo Finance blocks requests from cloud hosting (Render, Railway, Heroku).  
**Fix:** Created `src/fetcher.py` — a multi-source data fetcher that tries yfinance first,
then automatically falls back to Stooq (free, no API key needed). Every pair in
`engine.py` now uses this fetcher instead of calling yfinance directly.

### Bug 2 — MongoDB Connection Timeout (Bot Runs Without DB)
**Symptom:** `No replica set members found yet, Timeout: 5.0s`  
**Cause:** MongoDB Atlas blocks connections from IPs not on the whitelist.  
**Fix (you must do this manually):**
1. Go to [MongoDB Atlas](https://cloud.mongodb.com)
2. Your cluster → **Security** → **Network Access**
3. Click **Add IP Address** → **Allow Access from Anywhere** → Confirm
4. This adds `0.0.0.0/0` — allows connections from any server
5. Wait ~30 seconds, then restart the bot

> Note: The bot still works without MongoDB — signals are sent to Telegram but not persisted.

### Bug 3 — requirements.txt Corrupted (UTF-16 encoding)
**Symptom:** `pip install -r requirements.txt` fails with encoding errors on deployment.  
**Cause:** File was saved as UTF-16 (Windows Notepad default) instead of UTF-8.  
**Fix:** Rewrote the file in clean ASCII/UTF-8.

### Bug 4 — Outcome Evaluator Ticker Lookup Crash
**Symptom:** `evaluate_pending_signals` never correctly evaluates WIN/LOSS results.  
**Cause:** Code did `fetch_ohlcv(s["pair"])` which passed `"EUR/USD"` as the ticker.
Neither yfinance nor Stooq recognise `"EUR/USD"` — they need `"EURUSD=X"`.  
**Fix:** Changed to `fetch_ohlcv(s.get("ticker") or s.get("pair"))` — the signal dict
already stores the real ticker (`"EURUSD=X"`), so it now uses that correctly.

### Bug 5 — Datetime Comparison Crash in Web Dashboard
**Symptom:** `/bot-status` and `/admin` pages crash with `TypeError: can't subtract offset-naive and offset-aware datetimes`.  
**Cause:** `upsert_bot_status()` saves `last_run` without timezone info, but `utc_now()` returns a timezone-aware datetime.  
**Fix:** Both `seconds_ago` calculations now strip timezone from both sides before subtracting.

---

## Running the Bot

### Local / VPS
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy and fill in your .env
cp .env.example .env
# Edit .env with your Telegram token, channel IDs, MongoDB URI

# 3. Run the signal bot
python main.py

# 4. Run the web dashboard (separate terminal)
python app.py
```

### On Render / Railway
```
Build command:  pip install -r requirements.txt
Start command:  python main.py     (for the bot worker)
                gunicorn app:app   (for the web dashboard)
```

> Set all environment variables from `.env.example` in your platform's dashboard.
> Do NOT commit your real `.env` file to GitHub.

---

## File Structure

```
vedatraderbot/
├── main.py              # Bot entry point — scan loop + command polling
├── app.py               # Flask web dashboard
├── requirements.txt     # Dependencies (fixed: UTF-8)
├── Procfile             # Render/Heroku process definition
├── .env.example         # Template for your environment variables
├── src/
│   ├── config.py        # All settings, pair universe, session logic
│   ├── fetcher.py       # NEW: Multi-source OHLCV fetcher (yfinance + Stooq)
│   ├── engine.py        # Signal analysis, 7-layer filter stack
│   ├── indicators.py    # EMA, RSI, MACD, ADX, ATR, Bollinger, S/R
│   ├── notifier.py      # Telegram message formatting + command handler
│   ├── database.py      # MongoDB operations (deduplication, signal storage)
│   └── premium.py       # Gold tier logic
└── webapp/              # HTML templates for the web dashboard
```

---

## Signal Flow (How It Works)

```
Every 5 minutes:
  1. evaluate_pending_signals()    — stamp WIN/LOSS on signals past expiry
  2. Session check                 — announce new session if changed
  3. For each pair in session:
       fetch_ohlcv() [yfinance → Stooq fallback]
         ↓
       Layer 1: Time filter        (skip dead hours 00-06 UTC)
       Layer 2: ATR + BB filter    (skip flat/squeeze markets)
       Layer 3: 15M trend align    (must match higher timeframe)
       Layer 4: ADX filter         (trending market only, ADX ≥ 20)
       Layer 5: MACD momentum      (histogram growing)
       Layer 6: RSI strict zone    (42-62 buy / 38-58 sell)
       Layer 7: Candle + S/R       (body confirmation + avoid S/R)
         ↓
       Quality score 0-100         (must be 60+ to fire)
         ↓
       Send to FREE or PREMIUM channel
       Save to MongoDB
```

---

## Telegram Commands

| Command      | What it does                      |
|-------------|-----------------------------------|
| `/start`    | Welcome menu with buttons         |
| `/status`   | Bot health + current session      |
| `/pairs`    | All 30 monitored pairs            |
| `/sessions` | Trading session schedule          |
| `/premium`  | Premium hub                       |
| `/test`     | Send test message to channel      |
| `/myid`     | Show your Telegram user ID        |
| `/addgold <user_id> <days>` | Admin: grant premium |

---

## Admin Panel

Visit `/admin` in your web dashboard browser.  
Login with `ADMIN_USERNAME` and `ADMIN_PASSWORD` from your `.env`.

Shows: signal history, win/loss rate, delivery stats, error log, user list.
