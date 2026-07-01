import json
import os

CONFIG_FILE_PATH = os.path.join('data', 'config.json')

os.makedirs(os.path.dirname(CONFIG_FILE_PATH), exist_ok=True)

if not os.path.exists(CONFIG_FILE_PATH):
    with open(CONFIG_FILE_PATH, 'w') as f:
        f.write(json.dumps({}, indent=2))
