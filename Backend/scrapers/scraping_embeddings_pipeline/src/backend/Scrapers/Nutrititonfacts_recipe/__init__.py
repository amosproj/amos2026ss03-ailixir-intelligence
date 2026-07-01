import json
import os

RAW_DIR_PATH = os.path.join('data', 'nutrition_recipe', 'raw')
INDEX_FILE_PATH = os.path.join('data', 'nutrition_recipe', 'index.json')

# Nutritionfacts scraper base dir
os.makedirs(RAW_DIR_PATH, exist_ok=True)

if not os.path.exists(INDEX_FILE_PATH):
    with open(INDEX_FILE_PATH, 'w') as f:
        f.write(json.dumps({'indexes': []}, indent=2))
