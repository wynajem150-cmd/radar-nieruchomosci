import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

LOG = Path("radar.log")
STATS = Path("daily_stats.json")
WARSAW = ZoneInfo("Europe/Warsaw")

text = LOG.read_text(encoding="utf-8", errors="ignore") if LOG.exists() else ""
now = datetime.now(WARSAW)
today = now.date().isoformat()

checked = sum(int(x) for x in re.findall(r"Odczytano (\d+)", text))
match = re.search(r"Nowych ofert: (\d+) \| alertów >= \d+: (\d+)", text)
new_offers = int(match.group(1)) if match else 0
alerts = int(match.group(2)) if match else 0
scores = [int(x) for x in re.findall(r"(?:OKAZJA|SPRAWDZIĆ)\s*[–-]\s*(\d+)/100", text)]
max_score = max(scores) if scores else 0

try:
    data = json.loads(STATS.read_text(encoding="utf-8"))
except Exception:
    data = {}

if data.get("date") != today:
    data = {
        "date": today,
        "runs": 0,
        "checked": 0,
        "new_offers": 0,
        "alerts": 0,
        "max_score": 0,
        "last_run": None,
        "reported": False,
    }

data["runs"] += 1
data["checked"] += checked
data["new_offers"] += new_offers
data["alerts"] += alerts
data["max_score"] = max(data.get("max_score", 0), max_score)
data["last_run"] = now.isoformat(timespec="minutes")

STATS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(data, ensure_ascii=False))
