#!/usr/bin/env python3
"""
Vocab - Terminal Vocabulary Memorization App
Run directly with: python main.py
"""
import sys
from vocab.app import main

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nGoodbye!")
        sys.exit(0)
