import os
import sys
import time
import subprocess

def run_bot():
    print(f"[{time.ctime()}] Starting Veda Trader Bot with auto-reload")
    process = subprocess.Popen([sys.executable, "veda_trader_bot.py"])
    
    last_mtime = os.path.getmtime("veda_trader_bot.py")
    
    try:
        while True:
            current_mtime = os.path.getmtime("veda_trader_bot.py")
            
            if current_mtime != last_mtime:
                print(f"\n[{time.ctime()}] Script modified! Restarting bot...")
                process.terminate()
                process.wait()
                last_mtime = current_mtime
                process = subprocess.Popen([sys.executable, "veda_trader_bot.py"])
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
        print("\nBot stopped")

if __name__ == "__main__":
    run_bot()