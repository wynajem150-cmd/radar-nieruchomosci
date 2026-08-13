import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TARGET_FILE = Path("olx_chat_id.txt")


def api(method, data=None):
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    if data is None:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    encoded = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=encoded)
    with urllib.request.urlopen