"""Main entry point for running userbot with: python -m userbot"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from userbot import run

if __name__ == "__main__":
    run()