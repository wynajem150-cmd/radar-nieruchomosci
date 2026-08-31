import json
import os

import requests

FUNCTION_URL = (
    "https://bjuxmxtfhglkafqsbbgq.supabase.co/"
    "functions/v1/dispatch-flip-alerts"
)
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
SUPABASE_ANON_KEY = os.environ.get(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJqdXhteHRmaGdsa2FmcXNiYmdxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODc5ODg4MDEsImV4cCI6MjEwMzU2NDgwMX0.5Sq9_I8tMZrF2qgOlg4g_LRqhjYmJwZKv2nBvAORvs0",
)
MODE = os.environ.get("RADAR_MODE", "alerts").strip().lower()
DRY_RUN = os.environ.get("RADAR_DRY_RUN", "0") == "1"


def main():
    if MODE not in {"alerts", "summary"}:
        raise SystemExit("RADAR_MODE musi mieć wartość alerts albo summary")
    if not BOT_TOKEN:
        raise RuntimeError("Brak TELEGRAM_BOT_TOKEN")

    response = requests.post(
        FUNCTION_URL,
        headers={
            "apikey": SUPABASE_ANON_KEY,
            "authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "x-telegram-bot-token": BOT_TOKEN,
            "content-type": "application/json",
        },
        json={"mode": MODE, "dry_run": DRY_RUN},
        timeout=180,
    )
    response.raise_for_status()
    result = response.json()
    if result.get("error") or result.get("ok") is False:
        raise RuntimeError(result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
