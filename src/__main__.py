#!/usr/bin/env python3
"""
Veda Trader Bot v5 - Main Entry Point
"""

import warnings
import os

# Suppress warnings
warnings.filterwarnings("ignore")
os.environ['PYTHONWARNINGS'] = 'ignore'

# Clean Windows path
if os.name == 'nt':
    os.environ['PATH'] = os.environ.get('PATH', '').replace('c:\\progra~1\\common~1\\system\\symsrv.dll.000', '')

# Run the bot
if __name__ == "__main__":
    from bot.main import main
    main()