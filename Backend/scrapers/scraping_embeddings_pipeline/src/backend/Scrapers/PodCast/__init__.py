import json
import os

RAW_DIR_PATH = os.path.join('data', 'podcast', 'raw')
INDEX_FILE_PATH = os.path.join('data', 'podcast', 'index.json')
VOSK_DIR_PATH = os.path.join('data', 'podcast', 'vosk_model')

# PodCast scraper base dir
os.makedirs(RAW_DIR_PATH, exist_ok=True)

# Vosk model dir
os.makedirs(VOSK_DIR_PATH, exist_ok=True)

if not os.path.exists(INDEX_FILE_PATH):
    with open(INDEX_FILE_PATH, 'w') as f:
        f.write(json.dumps({'indexes': []}, indent=2))
