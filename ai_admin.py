"""
VEDA TRADER - ai_admin.py
AI-powered admin assistant using Claude API.
- Sends daily summaries to admin
- Suggests when to pause/resume signals
- Auto-replies to subscriber questions in channel
- Answers subscriber questions via DM
"""

import os
import requests
from datetime import datetime, timezone

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL      = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """You are the AI assistant for Veda Trader, a professional Telegram trading signal service.

Your roles:
1. ADMIN SUMMARIES: Give the admin clear, concise performance insights. Flag issues like low win rate, high SL hits, or unusual patterns.
2. SUBSCRIBER REPLIES: When subscribers ask questions, answer helpfully and professionally. You represent Veda Trader.
3. SIGNAL DECISIONS: Advise the admin when to pause signals (e.g., high volatility news events, poor performance streak) or resume them.

Tone: Professional, confident, friendly. Like a smart trading assistant.
Always be honest. Never promise guaranteed profits.
Keep replies SHORT (under 150 words unless asked for more)."""


def ask_claude(user_message: str, context: str = "") -> str:
    if not ANTHROPIC_API_KEY:
        return "AI not configured. Set ANTHROPIC_API_KEY in .env"
    
    messages = []
    if context:
        messages.append({"role": "user", "content": f"Context:\n{context}"})
        messages.append({"role": "assistant", "content": "Got it. I have the context."})
    messages.append({"role": "user", "content": user_message})

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": CLAUDE_MODEL,
                "max_tokens": 400,
                "system": SYSTEM_PROMPT,
                "messages": messages,
            },
            timeout=30,
        )
        data = r.json()
        return data["content"][0]["text"].strip()
    except Exception as e:
        return f"AI error: {e}"


# ── Admin Daily Summary ──────────────────────────────────────

def generate_admin_summary(stats: dict) -> str:
    context = f"""
Today's Veda Trader stats:
- Total signals: {stats.get('total', 0)}
- TP hits: {stats.get('tp_hits', 0)}
- SL hits: {stats.get('sl_hits', 0)}
- Win rate: {stats.get('winrate', 0)}%
- Free subscribers: {stats.get('free_subs', 0)}
- Premium subscribers: {stats.get('premium_subs', 0)}
- Current time: {datetime.now(timezone.utc).strftime('%H:%M UTC')}
"""
    prompt = (
        "Give me a short admin summary of today's performance. "
        "Note anything concerning. Suggest whether I should keep signals running or pause. "
        "End with one action I should take."
    )
    return ask_claude(prompt, context=context)


# ── Signal Pause Advisor ─────────────────────────────────────

def should_pause_signals(stats: dict, recent_results: list) -> tuple[bool, str]:
    """
    Returns (should_pause: bool, reason: str)
    """
    winrate = stats.get("winrate", 100)
    sl_hits = stats.get("sl_hits", 0)
    total   = stats.get("total", 0)

    # Auto-pause rules
    if total >= 5 and winrate < 30:
        reason = f"Win rate dropped to {winrate}%. Auto-pausing to protect subscribers."
        return True, reason

    if sl_hits >= 4:
        reason = f"{sl_hits} consecutive SL hits detected. Pausing signals."
        return True, reason

    # Ask Claude for nuanced advice
    context = f"Win rate: {winrate}%, SL hits: {sl_hits}, Total signals: {total}, Recent: {recent_results}"
    advice  = ask_claude(
        "Should I pause signals now? Reply with: PAUSE or CONTINUE, then one sentence reason.",
        context=context
    )
    should_pause = advice.strip().upper().startswith("PAUSE")
    return should_pause, advice


# ── Subscriber Question Handler ──────────────────────────────

def answer_subscriber_question(question: str, username: str, stats: dict) -> str:
    context = f"""
The subscriber @{username} is asking a question.
Current Veda Trader stats:
- Win rate today: {stats.get('winrate', 'N/A')}%
- Signals today: {stats.get('total', 0)}
- Free subs: {stats.get('free_subs', 0)}
- Premium subs: {stats.get('premium_subs', 0)}
"""
    return ask_claude(
        f"Subscriber @{username} asks: \"{question}\"\n\n"
        "Reply professionally on behalf of Veda Trader. Keep it under 100 words.",
        context=context
    )


# ── Channel Auto-Reply ───────────────────────────────────────

COMMON_QUESTIONS = {
    "how do i join premium": (
        "💎 To join Veda Trader Premium, contact our admin directly.\n"
        "You'll get: Indices, Crypto, Gold + Forex signals 24/7!"
    ),
    "what broker": (
        "🏦 Any broker that supports the pairs we signal works!\n"
        "We recommend brokers with low spreads. Check /start for our partner link."
    ),
    "is it free": (
        "✅ Yes! Our Forex signals are FREE in this channel.\n"
        "💎 Upgrade to Premium for Indices, Crypto & Gold signals."
    ),
    "what is the win rate": None,  # handled dynamically
    "how accurate": None,          # handled dynamically
}

def auto_reply(message_text: str, username: str, stats: dict) -> str | None:
    """
    Returns a reply string or None if we shouldn't reply.
    Tries keyword match first, then falls back to Claude.
    """
    lower = message_text.lower()

    for key, fixed_reply in COMMON_QUESTIONS.items():
        if key in lower:
            if fixed_reply:
                return fixed_reply
            # Dynamic reply needed
            return answer_subscriber_question(message_text, username, stats)

    # General trading question — let Claude handle it
    trading_keywords = [
        "signal", "trade", "buy", "sell", "profit", "loss", "pip", "spread",
        "when", "pair", "session", "crypto", "gold", "forex", "premium",
        "how much", "how do", "what is", "can i", "should i"
    ]
    if any(kw in lower for kw in trading_keywords):
        return answer_subscriber_question(message_text, username, stats)

    return None  # don't reply to irrelevant messages
