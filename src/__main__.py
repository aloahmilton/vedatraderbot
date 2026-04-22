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
    import sys
    # Add root to path so we can import main
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
        
    from main import main
    main()