import json
import os
import statistics
from datetime import datetime

from playwright.sync_api import sync_playwright

import main as housing
import olx_deals as olx
import poland_deals as poland
import vacation_deals as v
import vacation_strict as vacation


def housing_test(pw):
    cfg = housing.load_config()
    best = None
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1400}, locale="pl-PL")
    for search in cfg["searches"]:
        try:
            items = housing.get_cards(page, search["url"])
        except Exception:
            continue
        allowed = [x for x in items if housing.listing_allowed(x, search)]
        ppms = [x["ppm2"] for x in allowed if 500 <= x["ppm2"] <= 50000]
        if len(ppms) < 3:
            continue
        median = statistics.median(ppms)
        for item in allowed:
            score, reasons, _ = housing.score_listing(item, median)
            cand = (score, housing.fmt_offer(item, score, reasons, search.get("name", "Wyszukiwanie"), median))
            if best is None or cand[0] > best[0]:
                best = cand
    browser.close()
    if best:
        housing.telegram_send("🧪 <b>TEST RADARU NIERUCHOMOŚCI</b>\n\n" + best[1])
    else:
        housing.telegram_send("🧪 <b>TEST RADARU NIERUCHOMOŚCI</b>\nBrak aktualnej oferty możliwej do wysłania w teście.")


def olx_test(pw):
    best = None
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1400}, locale="pl-PL")
    for region, slug in olx.REGIONS.items():
        for search in olx.SEARCHES:
            try:
                offers = olx.get_offers(page, olx.make_url(slug, search["query"]), search)
            except Exception:
                continue
            if len(offers) < 4:
                continue
            median = statistics.median([x["price"] for x in offers])
            for item in offers:
                score, ratio, bonuses = olx.score_offer(item, median)
                msg = olx.fmt_alert(item, search["name"], region, score, median, ratio, bonuses)
                cand = (score, msg)
                if best is None or cand[0] > best[0]:
                    best = cand
    browser.close()
    if best:
        olx.telegram_send("🧪 <b>TEST RADARU OLX</b>\n\n" + best[1])
    else:
        olx.telegram_send("🧪 <b>TEST RADARU OLX</b>\nBrak aktualnej oferty możliwej do wysłania w teście.")


def poland_test(pw):
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1600}, locale="pl-PL")
    page.goto(poland.URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3500)
    cards = poland.extract_cards(page)
    browser.close()
    offers = []
    for card in cards:
        o = poland.parse(card)
        if o:
            o["score"] = poland.score(o)
            offers.append(o)
    offers.sort(key=lambda x: (x["score"], x["discount"], -x["pp"]), reverse=True)
    if offers:
        poland.send_telegram("🧪 TEST RADARU POLSKA\n\n" + poland.message(offers[0]))
    else:
        poland.send_telegram("🧪 TEST RADARU POLSKA\nBrak aktualnej oferty spełniającej kryteria radaru.")


def vacation_test(pw):
    today = datetime.now(v.WARSAW).date()
    state = v.load(v.STATE_FILE, {"initialized": False, "prices": {}, "alerts": {}})
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 1400}, locale="pl-PL", user_agent="Mozilla/5.0 Chrome/131 Safari/537.36")
    search = ctx.new_page()
    detail = ctx.new_page()
    candidates = []
    for source, airport, url, party_marker in v.SOURCES:
        try:
            search.goto(url, wait_until="domcontentloaded", timeout=60000)
            search.wait_for_timeout(2400)
            visible, _ = v.page_text(search)
            if party_marker.lower() not in visible.lower():
                continue
            rows = v.cards(search, source, airport)
        except Exception:
            continue
        for row in rows:
            c = vacation.candidate(source, airport, row, today)
            if c:
                candidates.append(c)
    candidates.sort(key=lambda x: x["card_price"])
    best = None
    for c in candidates[:20]:
        d, err = vacation.verify(detail, c)
        if not d:
            continue
        import hashlib
        key = hashlib.sha256(f"{c['source']}|{c['title']}|{c['start']}|{c['airport']}".encode()).hexdigest()[:28]
        hist = v.history_discount(state, key, d["price"], today)
        discount = max(hist, d["official_discount"])
        sc = v.score(d["price"], discount, c["board"], d["beach_m"], d["transfer"])
        c.update(d)
        c.update({"key": key, "discount": discount, "score": sc})
        best = c
        break
    ctx.close()
    browser.close()
    if best:
        v.telegram("<b>🧪 TEST RADARU WAKACJE</b>\n\n" + v.fmt(best))
    else:
        v.telegram("<b>🧪 TEST RADARU WAKACJE</b>\nBrak aktualnej oferty, która przeszła pełną weryfikację radaru 2×.")


def main():
    with sync_playwright() as pw:
        housing_test(pw)
        olx_test(pw)
        poland_test(pw)
        vacation_test(pw)
    print("TEST_ONE_PER_RADAR_DONE")


if __name__ == "__main__":
    main()
