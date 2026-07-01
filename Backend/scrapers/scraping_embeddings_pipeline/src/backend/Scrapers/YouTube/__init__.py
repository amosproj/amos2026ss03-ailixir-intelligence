import json
import os

RAW_DIR_PATH = os.path.join('data', 'youtube', 'raw')
INDEX_FILE_PATH = os.path.join('data', 'youtube', 'index.json')

# YouTube scraper base dir
os.makedirs(RAW_DIR_PATH, exist_ok=True)

if not os.path.exists(INDEX_FILE_PATH):
    with open(INDEX_FILE_PATH, 'w') as f:
        f.write(json.dumps({'indexes': [], 'channel_map': {}}, indent=2))
