import hashlib
import json
import os
import re
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

URL = "https://travelist.pl/hotele/polska"
STATE = Path("poland_deals_seen.json")
MAX_PP_NIGHT = 150
MIN_DISCOUNT = 25
SUPER_DISCOUNT = 40
MIN_RATING = 4.0
MAX_ALERTS = 6

PRICE_OBJECT_RE = re.compile(r"Cena\s+w\s+obiekcie:\s*([\d\s]+)\s*zł", re.I)
PRICE_TRAVELIST_RE = re.compile(r"Cena\s+Travelist:\s*od\s*([\d\s]+)\s*zł", re.I)
RATING_RE = re.compile(r"(\d(?:[.,]\d)?)\s*/\s*5")


def norm(text):
    return " ".join((text or "").replace("\u00a0", " ").split())


def money(text):
    return int(re.sub(r"\D", "", text))


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"seen": {}, "initialized": False}


def save_state(data):
    STATE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def send_telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("VACATION_TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Brak TELEGRAM_BOT_TOKEN lub VACATION_TELEGRAM_CHAT_ID")
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=20,
    )
    r.raise_for_status()


def extract_cards(page):
    return page.evaluate("""() => {
      const out=[];
      for (const a of document.querySelectorAll('a[href]')) {
        if (!/zobacz\s+ofertę/i.test((a.innerText||'').trim())) continue;
        let n=a, box=null;
        for (let i=0;i<10 && n;i++,n=n.parentElement) {
          const t=(n.innerText||'').trim();
          if (t.length>80 && t.length<3000 && /Cena\s+Travelist:/i.test(t) && /Cena\s+w\s+obiekcie:/i.test(t)) { box=n; break; }
        }
        if (!box) continue;
        const h=box.querySelector('h1,h2,h3,h4,[class*=title]');
        out.push({url:a.href,text:(box.innerText||'').trim(),title:h?(h.innerText||'').trim():''});
      }
      return out.slice(0,120);
    }""")


def parse(card):
    text = norm(card.get("text"))
    m_old = PRICE_OBJECT_RE.search(text)
    m_new = PRICE_TRAVELIST_RE.search(text)
    if not m_old or not m_new:
        return None
    old_total = money(m_old.group(1))
    new_total = money(m_new.group(1))
    if old_total <= 0 or new_total <= 0 or new_total >= old_total:
        return None

    rating = None
    m_rating = RATING_RE.search(text)
    if m_rating:
        rating = float(m_rating.group(1).replace(",", "."))
    if rating is None or rating < MIN_RATING:
        return None

    pp_night = new_total / 2
    if pp_night > MAX_PP_NIGHT:
        return None

    discount = round((old_total - new_total) / old_total * 100)
    if discount < MIN_DISCOUNT:
        return None

    low = text.lower()
    breakfast = "śniad" in low or "sniad" in low
    half_board = "obiadokol" in low
    title = norm(card.get("title")) or text[:100]
    url = (card.get("url") or "").split("#")[0]
    key = hashlib.sha256(url.encode()).hexdigest()[:24]
    return {
        "key": key,
        "title": title,
        "url": url,
        "old": old_total,
        "new": new_total,
        "pp": pp_night,
        "discount": discount,
        "rating": rating,
        "breakfast": breakfast,
        "half_board": half_board,
    }


def score(o):
    s = 55 + min(25, max(0, o["discount"] - 20))
    if o["pp"] <= 100:
        s += 12
    elif o["pp"] <= 125:
        s += 8
    else:
        s += 4
    if o["breakfast"]:
        s += 8
    if o["half_board"]:
        s += 3
    return min(100, s)


def message(o):
    label = "🔥🔥 SUPER PEREŁKA POLSKA" if o["discount"] >= SUPER_DISCOUNT else "🇵🇱 PEREŁKA POLSKA"
    meals = "śniadania + obiadokolacje" if o["half_board"] else "śniadania w ofercie" if o["breakfast"] else "wyżywienie do sprawdzenia"
    return (
        f"{label} — {o['score']}/100\n"
        f"🏨 {o['title']}\n"
        f"⭐ {o['rating']:.1f}/5\n"
        f"🍳 {meals}\n"
        f"💰 od {o['new']} zł / noc za 2 osoby\n"
        f"👤 od {o['pp']:.0f} zł / os. / noc\n"
        f"📉 przecena {o['discount']}% (z {o['old']} zł)\n"
        f"🔗 {o['url']}\n\n"
        "ℹ️ Cena Travelist jest ceną „od” — przed rezerwacją wybierz konkretny termin w kalendarzu."
    )


def run():
    state = load_state()
    state.setdefault("seen", {})
    offers = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1600}, locale="pl-PL")
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3500)
        cards = extract_cards(page)
        browser.close()

    for card in cards:
        o = parse(card)
        if o:
            o["score"] = score(o)
            offers.append(o)

    offers.sort(key=lambda x: (x["score"], x["discount"], -x["pp"]), reverse=True)
    print(f"Travelist: kart={len(cards)}, dopasowanych={len(offers)}")

    if not state.get("initialized"):
        for o in offers:
            state["seen"][o["key"]] = {"price": o["new"], "discount": o["discount"]}
        state["initialized"] = True
        save_state(state)
        print("Pierwszy skan: zapisano bazę, bez alertów.")
        return

    sent = 0
    for o in offers:
        old = state["seen"].get(o["key"])
        should_send = old is None
        if old:
            should_send = o["new"] <= int(old.get("price", o["new"])) - 20 or o["discount"] >= int(old.get("discount", o["discount"])) + 5
        if should_send and sent < MAX_ALERTS:
            send_telegram(message(o))
            sent += 1
        state["seen"][o["key"]] = {"price": o["new"], "discount": o["discount"]}

    save_state(state)
    print(f"Alertów Polska: {sent}")


if __name__ == "__main__":
    run()
