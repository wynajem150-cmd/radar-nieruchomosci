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

STATE_FILE = Path("olx_deals_seen.json")
MAX_PRICE = 1000
MIN_PRICE = 80
THRESHOLD = 65

REGIONS = {
    "Śląskie": "slaskie",
    "Opolskie": "opolskie",
}

SEARCHES = [
    {
        "name": "Nintendo Switch OLED",
        "query": "nintendo switch oled",
        "required": ["nintendo", "switch", "oled"],
        "exclude": ["etui", "pokrowiec", "joy-con", "joycon", "gra ", "gry ", "stacja dokująca", "pudełko", "sam karton"],
    },
    {
        "name": "Xbox Series S",
        "query": "xbox series s",
        "required": ["xbox", "series"],
        "exclude": ["series x", "pad", "kontroler", "słuchawki", "gra ", "gry ", "konto", "pudełko"],
    },
    {
        "name": "PlayStation 4 Pro",
        "query": "ps4 pro",
        "required": ["ps4", "pro"],
        "exclude": ["pad", "kontroler", "gra ", "gry ", "konto", "pudełko", "obudowa"],
    },
    {
        "name": "GoPro Hero 10/11/12",
        "query": "gopro hero",
        "required": ["gopro", "hero"],
        "exclude": ["etui", "obudowa", "uchwyt", "bateria", "akumulator", "szkło", "ramka", "ładowarka", "gimbal"],
    },
    {
        "name": "Makita 18V LXT",
        "query": "makita 18v lxt",
        "required": ["makita"],
        "exclude": ["walizka", "ładowarka", "akumulator", "bateria", "uchwyt", "adapter", "części"],
    },
    {
        "name": "DeWalt XR 18V",
        "query": "dewalt xr 18v",
        "required": ["dewalt"],
        "exclude": ["walizka", "ładowarka", "akumulator", "bateria", "uchwyt", "adapter", "części"],
    },
]

PRICE_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[ .\u00a0]\d{3})*|\d{2,4})\s*(?:zł|PLN)", re.I)

HARD_EXCLUDE = [
    "uszkodz", "na części", "nie działa", "zbity", "pęknięty", "brak obrazu",
    "blokada", "zablokowany", "replika", "podróbka", "zamiennik",
]

POSITIVE = ["pilnie", "do negocjacji", "negocjacja", "gwarancja", "paragon", "faktura", "jak nowy", "mało używany"]


def normalize_url(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip("/"), "", ""))


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()[:24]


def load_state():
    if not STATE_FILE.exists():
        return {"initialized": False, "seen": []}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"initialized": False, "seen": []}
        data.setdefault("initialized", False)
        data.setdefault("seen", [])
        return data
    except Exception:
        return {"initialized": False, "seen": []}


def save_state(state):
    state["seen"] = state.get("seen", [])[-15000:]
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def telegram_send(message: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("OLX_TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Brak TELEGRAM_BOT_TOKEN lub OLX_TELEGRAM_CHAT_ID")
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=20,
    )
    r.raise_for_status()


def make_url(region_slug: str, query: str) -> str:
    q = query.replace(" ", "-")
    return (
        f"https://www.olx.pl/{region_slug}/q-{q}/"
        f"?search%5Bfilter_float_price%3Afrom%5D={MIN_PRICE}"
        f"&search%5Bfilter_float_price%3Ato%5D={MAX_PRICE}"
        f"&search%5Border%5D=created_at%3Adesc"
    )


def parse_price(text: str):
    for m in PRICE_RE.finditer(text):
        raw = m.group(1).replace("\u00a0", "").replace(" ", "").replace(".", "")
        try:
            value = int(raw)
        except ValueError:
            continue
        if MIN_PRICE <= value <= MAX_PRICE:
            return value
    return None


def valid_for_search(text: str, search: dict) -> bool:
    t = text.lower()
    if any(x in t for x in HARD_EXCLUDE):
        return False
    if any(x in t for x in search.get("exclude", [])):
        return False
    if not all(x in t for x in search.get("required", [])):
        return False
    return True


def get_offers(page, url: str, search: dict):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    selector = 'a[href*="/d/oferta/"]'
    try:
        page.wait_for_selector(selector, timeout=12000)
    except PlaywrightTimeoutError:
        pass

    cards = page.eval_on_selector_all(
        selector,
        """els => els.slice(0, 200).map(a => {
            const box = a.closest('div[data-cy="l-card"]') || a.closest('article') || a.closest('li') || a.parentElement;
            return {href: a.href || '', text: (box?.innerText || a.innerText || '').trim()};
        })""",
    )

    out = []
    local_seen = set()
    for c in cards:
        href = c.get("href", "")
        text = " ".join(c.get("text", "").split())
        if not href or not text:
            continue
        full = normalize_url(urljoin(url, href))
        if full in local_seen:
            continue
        local_seen.add(full)
        price = parse_price(text)
        if price is None:
            continue
        if not valid_for_search(text, search):
            continue
        out.append({"url": full, "text": text[:1000], "price": price})
    return out


def score_offer(item, median_price):
    ratio = item["price"] / median_price if median_price else 1.0
    if ratio <= 0.55:
        score = 95
    elif ratio <= 0.65:
        score = 88
    elif ratio <= 0.72:
        score = 80
    elif ratio <= 0.78:
        score = 74
    elif ratio <= 0.84:
        score = 68
    elif ratio <= 0.88:
        score = 62
    else:
        score = 45

    t = item["text"].lower()
    bonuses = [x for x in POSITIVE if x in t]
    score += min(8, len(bonuses) * 2)
    return min(score, 100), ratio, bonuses


def fmt_alert(item, search_name, region, score, median_price, ratio, bonuses):
    discount = max(0, round((1 - ratio) * 100))
    estimated_margin = max(0, round(median_price - item["price"]))
    label = "🔥 MOCNA OKAZJA" if score >= 78 else "👀 WARTO SPRAWDZIĆ"
    bonus_txt = "\n".join("✅ " + html.escape(x) for x in bonuses[:3])
    if bonus_txt:
        bonus_txt = "\n" + bonus_txt

    return (
        f"<b>🛒 {label} – {score}/100</b>\n"
        f"📦 {html.escape(search_name)}\n"
        f"📍 {html.escape(region)}\n"
        f"💰 Cena: <b>{item['price']} zł</b>\n"
        f"📊 Mediana podobnych ofert: <b>{round(median_price)} zł</b>\n"
        f"📉 Około <b>{discount}% poniżej mediany</b>\n"
        f"💵 Teoretyczna różnica do mediany: <b>~{estimated_margin} zł</b>"
        f"{bonus_txt}\n\n"
        f"⚠️ Sprawdź stan, kompletność i autentyczność przed zakupem.\n"
        f"🔗 <a href=\"{html.escape(item['url'], quote=True)}\">Otwórz ogłoszenie</a>"
    )


def run():
    state = load_state()
    seen = set(state.get("seen", []))
    initialized = bool(state.get("initialized", False))
    newly_seen = []
    alerts = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 1400},
            locale="pl-PL",
            user_agent=("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
        )

        for region, slug in REGIONS.items():
            for search in SEARCHES:
                url = make_url(slug, search["query"])
                print(f"\n--- {region} | {search['name']} ---")
                try:
                    offers = get_offers(page, url, search)
                except Exception as e:
                    print(f"Błąd: {e}", file=sys.stderr)
                    continue

                if len(offers) < 4:
                    print(f"Za mało poprawnych ofert do porównania: {len(offers)}")
                    for item in offers:
                        h = url_hash(item["url"])
                        if h not in seen:
                            seen.add(h)
                            newly_seen.append(h)
                    continue

                prices = [x["price"] for x in offers]
                median_price = statistics.median(prices)
                print(f"Odczytano {len(offers)} ofert, mediana {median_price:.0f} zł")

                for item in offers:
                    h = url_hash(item["url"])
                    if h in seen:
                        continue
                    seen.add(h)
                    newly_seen.append(h)

                    score, ratio, bonuses = score_offer(item, median_price)
                    if initialized and score >= THRESHOLD:
                        alerts.append((score, fmt_alert(item, search["name"], region, score, median_price, ratio, bonuses)))

        browser.close()

    alerts.sort(key=lambda x: x[0], reverse=True)
    for _, message in alerts[:15]:
        telegram_send(message)

    state["seen"] = list(seen)
    state["initialized"] = True
    save_state(state)
    print(f"\nNowych ofert: {len(newly_seen)} | alertów: {len(alerts)} | initialized wcześniej: {initialized}")


if __name__ == "__main__":
    run()
