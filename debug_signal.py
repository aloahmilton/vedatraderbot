from veda_trader_bot import analyze_pair, send_telegram, format_signal_message
import ccxt

print("Testing USD/CAD signal...")
ex = ccxt.kraken()
signal = analyze_pair(ex, 'USD/CAD')

print(f"Signal found: {signal}")

if signal:
    msg = format_signal_message(signal)
    print(f"Formatted message:\n{msg}")
    result = send_telegram(msg)
    print(f"Telegram send result: {result}")