import requests
import concurrent.futures
import time

TOKEN = "8652896161:AAEwKHUNG4G7JmRgChJokZq6oUQW5nZU-GI"
FREE_CH = "-1003912798237"

def delete_msg(mid):
    url = f"https://api.telegram.org/bot{TOKEN}/deleteMessage"
    while True:
        try:
            r = requests.post(url, json={"chat_id": FREE_CH, "message_id": mid}, timeout=5)
            if r.status_code == 429:
                retry_after = r.json().get("parameters", {}).get("retry_after", 2)
                time.sleep(retry_after)
                continue
            return r.status_code == 200
        except:
            return False

print(f"Aggressive cleanup for Free Channel {FREE_CH}...")
r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
    "chat_id": FREE_CH, "text": "🧹 Deep cleanup initialized..."
})
if r.status_code != 200:
    print(f"Failed to send start message. Proceeding anyway.")
    curr_id = 15000 # Guess high if we fail
else:
    curr_id = r.json()["result"]["message_id"]

deleted = 0
# 30 workers is safer for Telegram rate limits without triggering massive 429s
with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
    # Delete up to 25,000 messages
    futures = [executor.submit(delete_msg, curr_id - i) for i in range(25000)]
    
    for i, future in enumerate(concurrent.futures.as_completed(futures)):
        if future.result():
            deleted += 1
        if i > 0 and i % 1000 == 0:
            print(f"Processed {i} messages... (Deleted: {deleted})")

print(f"Cleanup finished! Total deleted: {deleted}")
