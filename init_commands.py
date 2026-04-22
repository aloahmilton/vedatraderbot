#!/usr/bin/env python3
"""
Quick script to initialize bot commands on Telegram
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_TOKEN:
    print("TELEGRAM_BOT_TOKEN not found in .env")
    exit(1)

commands = [
    {"command": "start", "description": "Get bot info and welcome message"},
    {"command": "status", "description": "Check bot health and current session"},
    {"command": "pairs", "description": "List all monitored currency pairs"},
    {"command": "sessions", "description": "View the trading session schedule"},
    {"command": "premium", "description": "Access premium features and signals"},
]

url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setMyCommands"
response = requests.post(url, json={"commands": commands})

if response.status_code == 200:
    data = response.json()
    if data.get("ok"):
        print("Bot commands initialized successfully!")
        print("Commands:")
        for cmd in commands:
            print(f"  /{cmd['command']} - {cmd['description']}")
    else:
        print(f"Failed: {data.get('description')}")
else:
    print(f"HTTP Error: {response.status_code}")