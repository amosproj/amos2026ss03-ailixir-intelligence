"""
run.py  –  Place this file in your project root, NOT inside allixer_ocr/.

Expected folder layout:
    files/
    ├── run.py              ← this file
    └── allixer_ocr/
        ├── __init__.py
        ├── extractor.py
        ├── preprocessor.py
        ├── prompts.py
        ├── main.py
        └── schemas/
            ├── medical.py
            └── financial.py

Usage:
    python run.py --image test.jpg --domain medical
    python run.py --image invoice.png --domain financial
    python run.py --image test.jpg --domain medical --raw
"""

import sys
import os

# Ensure the project root is on sys.path so 'allixer_ocr' is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Now delegate to the package's main entry point
from allixer_ocr.main import main

if __name__ == "__main__":
    main()
