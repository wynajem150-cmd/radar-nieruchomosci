import json
import os

import requests

FUNCTION_URL = (
    "https://bjuxmxtfhglkafqsbbgq.supabase.co/"
    "functions/v1/dispatch-flip-alerts"
)
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
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
