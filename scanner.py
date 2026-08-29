import json
import os
import uuid

import requests

FUNCTION_URL = "https://bjuxmxtfhglkafqsbbgq.supabase.co/functions/v1/process-offers"
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
MODE = os.environ.get("RADAR_MODE", "test").strip().lower()
RUN_ID = os.environ.get("RADAR_RUN_ID", uuid.uuid4().hex[:12])
DRY_RUN = os.environ.get("RADAR_DRY_RUN", "0") == "1"

# Aktualne publiczne oferty zweryfikowane 29.08.2026.
# Służą wyłącznie do testu przepływu: filtr -> właściwy tester -> Telegram.
TEST_BATCHES = {
    "Knurów": [{
        "source_offer_id": "test-knurow-k2j0y9",
        "title": "Knurów, ul. Władysława Jagiełły - mieszkanie 2-pokojowe",
        "url": "https://adresowo.pl/o/mieszkanie-knurow-ul-wladyslawa-jagielly-2-pokojowe-k2j0y9",
        "price": 270000,
        "area": 48.0,
        "rooms": 2,
        "price_m2": 5625.0,
        "floor_text": "Piętro: 3",
        "description": "Mieszkanie 2-pokojowe, 48 m², Knurów, trzecie piętro.",
    }],
    "Jędrzejów": [{
        "source_offer_id": "test-jedrzejow-h4r5q6",
        "title": "Jędrzejów, ul. Feliksa Przypkowskiego - mieszkanie 3-pokojowe",
        "url": "https://adresowo.pl/o/mieszkanie-jedrzejow-ul-feliksa-przypkowskiego-3-pokojowe-h4r5q6",
        "price": 455000,
        "area": 64.0,
        "rooms": 3,
        "price_m2": 7109.38,
        "floor_text": "Parter",
        "description": "Mieszkanie 3-pokojowe, 64 m², Jędrzejów, parter.",
    }],
}


def process(city, offers):
    payload = {
        "source": "verified-public-test",
        "city": city,
        "mode": "test",
        "run_id": RUN_ID,
        "offers": offers,
    }
    if DRY_RUN:
        print(json.dumps({"dry_run": True, "city": city, "offers": offers}, ensure_ascii=False))
        return {"dry_run": True}
    if not BOT_TOKEN:
        raise RuntimeError("Brak TELEGRAM_BOT_TOKEN")
    response = requests.post(
        FUNCTION_URL,
        headers={"x-telegram-bot-token": BOT_TOKEN, "content-type": "application/json"},
        json=payload,
        timeout=90,
    )
    response.raise_for_status()
    result = response.json()
    if result.get("error"):
        raise RuntimeError(result["error"])
    print(json.dumps(result, ensure_ascii=False))
    return result


def main():
    if MODE != "test":
        raise SystemExit(
            "Tryby baseline/live są celowo wyłączone do czasu podłączenia dozwolonego API/feedu źródła ofert."
        )
    sent = 0
    for city, offers in TEST_BATCHES.items():
        result = process(city, offers)
        sent += int(result.get("sent_count", 0)) if not DRY_RUN else 0
    print(json.dumps({"ok": True, "mode": "test", "sent_count": sent}, ensure_ascii=False))


if __name__ == "__main__":
    main()
