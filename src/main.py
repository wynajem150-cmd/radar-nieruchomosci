import argparse
import hashlib
import html
import json
import os
import re
import statistics
import sys
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

STATE_FILE = Path("seen.json")

PRICE_RE = re.compile(r"(?<!\d)(\d{2,3}(?:[ .\u00a0]\d{3})+|\d{4,7})\s*(?:zł|PLN)", re.I)
AREA_RE = re.compile(r"(\d{1,3}(?:[,.]\d{1,2})?)\s*m(?:²|2)\b", re.I)
ROOMS_RE = re.compile(r"(\d)\s*(?:pok(?:ój|oje|oi)|pokoje|rooms?)", re.I)

PORTAL_SELECTORS = {
    "otodom": 'a[href*="/pl/oferta/"]',
    "olx": 'a[href*="/d/oferta/"]',
    "gratka": 'a[href*="/nieruchomosci/"]',
    "morizon": 'a[href*="/oferta/"]',
}

POSITIVE_WORDS = [
    "do remontu", "do odświeżenia", "pilnie", "okazja", "negocjacji",
    "spadek", "bez pośredników", "bezpośrednio", "balkon", "winda"
]

def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    # Usuwamy tracking/query, bo ten sam lokal może mieć różne parametry URL.
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), "", ""))

def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()[:24]

def portal_from_url(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    if "otodom" in host:
        return "otodom"
    if "olx" in host:
        return "olx"
    if "gratka" in host:
        return "gratka"
    if "morizon" in host:
        return "morizon"
    return "generic"

def parse_number(s: str) -> float:
    return float(s.replace("\u00a0", "").replace(" ", "").replace(".", "").replace(",", "."))

def parse_listing_text(text: str):
    text_clean = " ".join(text.split())
    price = None
    area = None
    rooms = None

    m = PRICE_RE.search(text_clean)
    if m:
        try:
            price = parse_number(m.group(1))
        except ValueError:
            pass

    m = AREA_RE.search(text_clean)
    if m:
        try:
            area = float(m.group(1).replace(",", "."))
        except ValueError:
            pass

    m = ROOMS_RE.search(text_clean)
    if m:
        rooms = int(m.group(1))

    return price, area, rooms, text_clean

def load_state():
    if not STATE_FILE.exists():
        return {"seen": []}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("seen", []), list):
            return {"seen": []}
        return data
    except Exception:
        return {"seen": []}

def save_state(state):
    # Trzymamy tylko hashe URL-i; repo nie ujawnia konkretnych ofert.
    state["seen"] = state.get("seen", [])[-10000:]
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def load_config():
    raw = os.environ.get("SEARCH_CONFIG_JSON", "").strip()
    if not raw:
        raise RuntimeError(
            "Brak SEARCH_CONFIG_JSON. Dodaj go w GitHub: Settings > Secrets and variables > Actions > Secrets."
        )
    cfg = json.loads(raw)
    if not cfg.get("searches"):
        raise RuntimeError("SEARCH_CONFIG_JSON nie zawiera pola 'searches'.")
    cfg.setdefault("threshold", 60)
    return cfg

def telegram_send(message: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Brak TELEGRAM_BOT_TOKEN lub TELEGRAM_CHAT_ID.")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=20,
    )
    r.raise_for_status()

def get_cards(page, search_url):
    portal = portal_from_url(search_url)
    selector = PORTAL_SELECTORS.get(portal, "a[href]")
    page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_timeout(2500)
        page.wait_for_selector(selector, timeout=12000)
    except PlaywrightTimeoutError:
        pass

    cards = page.eval_on_selector_all(
        selector,
        """els => els.slice(0, 250).map(a => {
            let box = a.closest('article') || a.closest('li') || a.closest('[data-testid]') || a.parentElement;
            return {
                href: a.href || a.getAttribute('href') || '',
                text: (box?.innerText || a.innerText || '').trim()
            };
        })"""
    )

    results = []
    seen_urls = set()
    for card in cards:
        href = card.get("href", "")
        text = card.get("text", "")
        if not href or not text:
            continue
        full = urljoin(search_url, href)
        norm = normalize_url(full)
        if norm in seen_urls:
            continue
        seen_urls.add(norm)

        price, area, rooms, clean = parse_listing_text(text)
        if price is None or area is None or area <= 10:
            continue
        ppm2 = price / area
        results.append({
            "url": norm,
            "price": price,
            "area": area,
            "rooms": rooms,
            "ppm2": ppm2,
            "text": clean[:1200],
            "portal": portal,
        })
    return results

def listing_allowed(item, search):
    p = item["price"]
    a = item["area"]
    t = item["text"].lower()

    if search.get("max_price") is not None and p > float(search["max_price"]):
        return False
    if search.get("min_price") is not None and p < float(search["min_price"]):
        return False
    if search.get("min_area") is not None and a < float(search["min_area"]):
        return False
    if search.get("max_area") is not None and a > float(search["max_area"]):
        return False

    exclude = [x.lower() for x in search.get("exclude", [])]
    if any(word in t for word in exclude):
        return False

    room_filter = search.get("rooms")
    if room_filter and item["rooms"] is not None and item["rooms"] not in room_filter:
        return False

    return True

def score_listing(item, median_ppm2):
    ratio = item["ppm2"] / median_ppm2 if median_ppm2 else 1.0
    score = 0
    reasons = []

    if ratio <= 0.75:
        score += 55
        reasons.append(f"{round((1-ratio)*100)}% poniżej mediany ceny/m²")
    elif ratio <= 0.82:
        score += 47
        reasons.append(f"{round((1-ratio)*100)}% poniżej mediany ceny/m²")
    elif ratio <= 0.90:
        score += 37
        reasons.append(f"{round((1-ratio)*100)}% poniżej mediany ceny/m²")
    elif ratio <= 0.95:
        score += 27
        reasons.append(f"{round((1-ratio)*100)}% poniżej mediany ceny/m²")
    elif ratio <= 1.00:
        score += 15
        reasons.append("poniżej mediany ceny/m²")

    text_lower = item["text"].lower()
    found = [w for w in POSITIVE_WORDS if w in text_lower]
    if found:
        bonus = min(15, 5 + 2 * len(found))
        score += bonus
        reasons.append("sygnały: " + ", ".join(found[:3]))

    if item["rooms"] in (2, 3):
        score += 8
        reasons.append(f"{item['rooms']} pokoje")

    if 35 <= item["area"] <= 65:
        score += 7
        reasons.append("płynny metraż 35–65 m²")

    return min(score, 100), reasons, ratio

def money(v):
    return f"{v:,.0f}".replace(",", " ") + " zł"

def fmt_offer(item, score, reasons, search_name, median_ppm2):
    safe_name = html.escape(search_name)
    safe_portal = html.escape(item["portal"].upper())
    reasons_txt = "\n".join("✅ " + html.escape(r) for r in reasons[:4])

    if score >= 75:
        label = "🔥 MOCNA OKAZJA"
    else:
        label = "👀 WARTO SPRAWDZIĆ"

    return (
        f"<b>{label} – {score}/100</b>\n"
        f"📍 {safe_name}\n"
        f"🌐 {safe_portal}\n"
        f"💰 <b>{money(item['price'])}</b>\n"
        f"📐 {item['area']:.1f} m² | {money(item['ppm2'])}/m²\n"
        + (f"🚪 {item['rooms']} pokoje\n" if item["rooms"] else "")
        + f"📊 Mediana w bieżących wynikach: {money(median_ppm2)}/m²\n\n"
        + reasons_txt
        + f"\n\n🔗 <a href=\"{html.escape(item['url'], quote=True)}\">Otwórz ogłoszenie</a>"
    )

def run(dry_run=False):
    cfg = load_config()
    threshold = int(cfg.get("threshold", 60))
    state = load_state()
    seen = set(state.get("seen", []))
    newly_seen = []
    alerts = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 1400},
            locale="pl-PL",
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        )

        for search in cfg["searches"]:
            name = search.get("name", "Wyszukiwanie")
            url = search["url"]
            print(f"\n--- {name} ---")
            try:
                items = get_cards(page, url)
            except Exception as e:
                print(f"Błąd pobierania {name}: {e}", file=sys.stderr)
                continue

            allowed = [x for x in items if listing_allowed(x, search)]
            ppms = [x["ppm2"] for x in allowed if 500 <= x["ppm2"] <= 50000]
            if len(ppms) < 3:
                print(f"Za mało poprawnie odczytanych ofert ({len(ppms)}), pomijam scoring.")
                continue
            median_ppm2 = statistics.median(ppms)
            print(f"Odczytano {len(items)}, po filtrach {len(allowed)}, mediana {median_ppm2:.0f} zł/m².")

            for item in allowed:
                h = url_hash(item["url"])
                if h in seen:
                    continue

                # Zapisujemy jako widziane niezależnie od score, żeby nie wracało później.
                seen.add(h)
                newly_seen.append(h)

                score, reasons, _ = score_listing(item, median_ppm2)
                if score >= threshold:
                    alerts.append((score, fmt_offer(item, score, reasons, name, median_ppm2)))

        browser.close()

    # Najlepsze najpierw.
    alerts.sort(key=lambda x: x[0], reverse=True)
    for score, message in alerts[:20]:
        print("\nALERT:", re.sub("<[^>]+>", "", message))
        if not dry_run:
            telegram_send(message)

    if newly_seen:
        state["seen"] = list(seen)
        save_state(state)

    print(f"\nNowych ofert: {len(newly_seen)} | alertów >= {threshold}: {len(alerts)}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test-telegram", action="store_true")
    args = parser.parse_args()

    if args.test_telegram:
        telegram_send("✅ <b>Radar nieruchomości działa.</b>\nTo jest wiadomość testowa.")
        print("Wiadomość testowa wysłana.")
        return

    run(dry_run=args.dry_run)

if __name__ == "__main__":
    main()
