import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

STATS = Path("daily_stats.json")
WARSAW = ZoneInfo("Europe/Warsaw")

now = datetime.now(WARSAW)
if now.hour != 20:
    print(f"Pominięto raport: w Polsce jest {now:%H:%M}.")
    raise SystemExit(0)

try:
    data = json.loads(STATS.read_text(encoding="utf-8"))
except Exception:
    data = {}

today = now.date().isoformat()
if data.get("date") != today:
    print("Brak dzisiejszych statystyk.")
    raise SystemExit(0)

if data.get("reported"):
    print("Raport za dziś został już wysłany.")
    raise SystemExit(0)

token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
if not token or not chat_id:
    raise RuntimeError("Brak TELEGRAM_BOT_TOKEN lub TELEGRAM_CHAT_ID.")

message = (
    "✅ <b>Radar nieruchomości działa</b>\n\n"
    f"📅 {now:%d.%m.%Y}\n"
    f"🔄 Uruchomień dziś: <b>{data.get('runs', 0)}</b>\n"
    f"🔎 Sprawdzonych ofert: <b>{data.get('checked', 0)}</b>\n"
    f"🆕 Nowych ofert: <b>{data.get('new_offers', 0)}</b>\n"
    f"📲 Alertów wysłanych: <b>{data.get('alerts', 0)}</b>\n"
    f"🏆 Najwyższy score: <b>{data.get('max_score', 0)}/100</b>\n\n"
    "To jest dzienny raport kontrolny."
)

url = f"https://api.telegram.org/bot{token}/sendMessage"
r = requests.post(
    url,
    json={
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    },
    timeout=20,
)
r.raise_for_status()

data["reported"] = True
STATS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print("Dzienny raport wysłany na Telegram.")
