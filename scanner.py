import json
import os
import sys
import time
import uuid

import requests

from olx_parser import listing_links, parse_offer

FUNCTION_URL = "https://bjuxmxtfhglkafqsbbgq.supabase.co/functions/v1/process-offers"
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
MODE = os.environ.get("RADAR_MODE", "test").strip().lower()
RUN_ID = os.environ.get("RADAR_RUN_ID", uuid.uuid4().hex[:12])
DRY_RUN = os.environ.get("RADAR_DRY_RUN", "0") == "1"

CITIES = {
    "Gliwice": "gliwice",
    "Knurów": "knurow",
    "Miechów": "miechow",
    "Jędrzejów": "jedrzejow",
}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.7",
}


def scan_city(city, slug, max_details=30):
    search_url = f"https://www.olx.pl/nieruchomosci/mieszkania/sprzedaz/{slug}/"
    session = requests.Session()
    response = session.get(search_url, headers=HEADERS, timeout=25)
    response.raise_for_status()
    links = listing_links(response.text)
    if not links:
        raise RuntimeError("OLX nie zwrócił rozpoznawalnych ofert")

    offers = []
    for index, (url, title, card_text) in enumerate(links[:max_details]):
        try:
            detail = session.get(url, headers=HEADERS, timeout=25)
            detail.raise_for_status()
            offer = parse_offer(detail.text, url, title, card_text)
            offer["city"] = city
            if offer["price"] is None or offer["area"] is None or offer["rooms"] is None:
                continue
            offers.append(offer)
        except Exception as exc:
            print(f"WARN {city}: {url}: {exc}", file=sys.stderr)
        if index + 1 < min(len(links), max_details):
            time.sleep(0.3)
    return offers


def process(city, offers):
    payload = {
        "source": "olx",
        "city": city,
        "mode": MODE,
        "run_id": RUN_ID,
        "offers": offers,
    }
    if DRY_RUN:
        print(json.dumps({"dry_run": True, "city": city, "count": len(offers), "sample": offers[:2]}, ensure_ascii=False))
        return
    if not BOT_TOKEN:
        raise RuntimeError("Brak TELEGRAM_BOT_TOKEN")

    response = requests.post(
        FUNCTION_URL,
        headers={"x-telegram-bot-token": BOT_TOKEN, "content-type": "application/json"},
        json=payload,
        timeout=90,
    )
    if not response.ok:
        raise RuntimeError(f"process-offers HTTP {response.status_code}: {response.text[:800]}")
    result = response.json()
    if result.get("error"):
        raise RuntimeError(result["error"])
    print(json.dumps(result, ensure_ascii=False))


def main():
    if MODE not in {"test", "baseline", "live"}:
        raise SystemExit("RADAR_MODE musi być: test, baseline albo live")

    failures = []
    total = 0
    for city, slug in CITIES.items():
        try:
            offers = scan_city(city, slug)
            print(f"{city}: {len(offers)} kompletnych ofert")
            if not offers:
                raise RuntimeError("brak kompletnych ofert")
            process(city, offers)
            total += len(offers)
        except Exception as exc:
            failures.append(f"{city}: {exc}")
            print(f"ERROR {city}: {exc}", file=sys.stderr)

    print(json.dumps({"mode": MODE, "offers_total": total, "failures": failures}, ensure_ascii=False))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
