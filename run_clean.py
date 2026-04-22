#!/usr/bin/env python3
"""
Clean startup for Veda Trader Bot v5
Suppresses Windows warnings and provides clean output
"""

import os
import sys
import warnings

# Suppress all warnings
warnings.filterwarnings("ignore")
os.environ['PYTHONWARNINGS'] = 'ignore'

# Clean PYTHONPATH for Windows
if os.name == 'nt':
    # Suppress Windows symbol server errors
    os.environ['PATH'] = os.environ.get('PATH', '').replace('c:\\progra~1\\common~1\\system\\symsrv.dll.000', '')

# Import and run the bot
try:
    from veda_trader_bot import main
    main()
except ImportError:
    # Fallback if main() not defined
    import veda_trader_bot
    if hasattr(veda_trader_bot, 'main'):
        veda_trader_bot.main()
    else:
        # Run the main block directly
        exec(open('veda_trader_bot.py').read())