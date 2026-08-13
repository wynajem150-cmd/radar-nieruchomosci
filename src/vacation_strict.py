import hashlib
import os
import re
from datetime import date, datetime, timedelta

import vacation_deals as v
from playwright.sync_api import sync_playwright

# Push zmian w kodzie = bezpieczny test bez Telegrama i bez zapisu stanu.
# Harmonogram / workflow_dispatch = normalna praca produkcyjna.
SAFE_TEST_MODE = os.environ.get('VACATION_DRY_RUN', '').strip().lower() in {'1', 'true', 'yes'}

DATE_RE = re.compile(r'(\d{1,2})\.(\d{1,2})\.(\d{4})\s*[-–]\s*(\d{1,2})\.(\d{1,2})\.(\d{4})')
ITAKA_TOTAL_RE = re.compile(r'Łącznie:\s*([\d\s]+)\s*zł', re.I)
TUI_CFG_RE = re.compile(r'Lotnisko\s+([^\d]+?)\s+Godzina\s+\d{1,2}:\d{2}\s+Pobyt\s+(\d{1,2})\s+Data wylotu\s+(\d{1,2}\.\d{1,2}\.\d{4})\s+Uczestnicy\s+2\s+dorosłych', re.I)
TUI_TOTAL_RE = re.compile(r'([\d\s]{4,})\s*ZŁ\s+Twój wybór', re.I)


def flexible_dates(text, today):
    m = DATE_RE.search(text)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))), date(int(m.group(6)), int(m.group(5)), int(m.group(4)))
        except Exception:
            pass
    return None, None


def current_price_matches(source, text):
    pat = v.ITAKA_PRICE_RE if source == 'ITAKA' else v.TUI_PRICE_RE
    vals = []
    for m in pat.finditer(text):
        if source == 'ITAKA' and 'najniższa cena z 30 dni' in text[max(0, m.start()-100):m.start()].lower():
            continue
        vals.append(v.money(m.group(1)))
    return vals


def unique_current_price(source, text):
    vals = sorted(set(current_price_matches(source, text)))
    return vals[0] + v.fee(source, text) if len(vals) == 1 else None


def meal(text):
    low = text.lower()
    if 'all inclusive' in low:
        return 'All Inclusive'
    if any(x in low for x in ('dwa posiłki', 'dwa posilki', '2 posiłki', '2 posilki', 'half board', 'obiadokolac')):
        return 'HB'
    if any(x in low for x in ('trzy posiłki', '3 posiłki', 'full board')):
        return 'FB'
    return None


def exact_itaka(visible, c):
    pos = visible.find('Kiedy:')
    while pos >= 0:
        block = visible[pos:pos+1400]
        if c['airport'].lower() in block.lower() and meal(block) == c['board']:
            if str(c['start'].year) in block and str(c['start'].day) in block and str(c['end'].day) in block:
                m = ITAKA_TOTAL_RE.search(block)
                if m:
                    total = v.money(m.group(1))
                    if total > 0 and total % 2 == 0:
                        return total // 2, total
        pos = visible.find('Kiedy:', pos+1)
    return None, None


def exact_tui(visible, c):
    m = TUI_CFG_RE.search(visible)
    if not m:
        return None, None
    try:
        start = datetime.strptime(m.group(3), '%d.%m.%Y').date()
    except Exception:
        return None, None
    end = start + timedelta(days=int(m.group(2)))
    if start != c['start'] or end != c['end'] or v.norm(m.group(1)).lower() != c['airport'].lower():
        return None, None
    tm = TUI_TOTAL_RE.search(visible)
    if not tm:
        return None, None
    block = visible[max(0, tm.start()-1000):tm.end()]
    if meal(block) != c['board']:
        return None, None
    total = v.money(tm.group(1))
    return (total // 2, total) if total > 0 and total % 2 == 0 else (None, None)


def exact_variant(visible, c):
    return exact_itaka(visible, c) if c['source'] == 'ITAKA' else exact_tui(visible, c)


def standard(full):
    # Najpierw dane strukturalne / oficjalna kategoria, dopiero potem fallback tekstowy.
    patterns = (
        r'"stars"\s*:\s*([3-5])\b',
        r'Kategoria\s+lokalna\s*([3-5])\s*gwiazd',
        r'\b([3-5])\s*gwiazdk(?:owy|owego|i)',
    )
    for pat in patterns:
        m = re.search(pat, full, re.I)
        if m:
            return int(m.group(1))
    return None


def official_beach(source, visible, full):
    low = visible.lower()
    if source == 'TUI':
        pos = low.find('położenie:')
        if pos < 0:
            pos = low.find('położenie')
        if pos >= 0:
            block = visible[pos:pos+1200]
            ok, dist = v.beach(block)
            if ok or dist is not None:
                return ok, dist
    else:
        # ITAKA zwykle podaje dystans w oficjalnej sekcji „Plaża”.
        for marker in ('plaża', 'plaza'):
            pos = low.find(marker)
            if pos >= 0:
                block = visible[pos:pos+1200]
                ok, dist = v.beach(block)
                if ok or dist is not None:
                    return ok, dist
    return v.beach(full)


def verify(page, c):
    try:
        page.goto(c['url'], wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(3200)
        visible, full = v.page_text(page)
    except Exception as exc:
        return None, f'otwarcie: {exc}'

    p, total = exact_variant(visible, c)
    if p is None:
        return None, 'brak dokładnego wariantu 2 os. + termin + lotnisko + wyżywienie + cena'
    if p != c['card_price']:
        return None, f"cena karty {c['card_price']} != szczegóły {p} zł/os."
    if p > v.MAX_PRICE_PP:
        return None, 'cena >2500 zł/os.'

    r, scale = v.rating(c['text'] + ' ' + c['meta'] + ' ' + visible[:5000])
    if r is None:
        return None, 'ocena poniżej progu lub niepotwierdzona'
    beach_ok, beach_m = official_beach(c['source'], visible, full)
    if not beach_ok:
        return None, 'plaża >500 m lub niepotwierdzona'
    if not v.baggage(full):
        return None, 'bagaż rejestrowany w cenie niepotwierdzony'
    if not v.climate(full):
        return None, 'klimatyzacja niepotwierdzona'
    st = standard(full)
    if st is None or st < 3:
        return None, 'standard min. 3★ niepotwierdzony'

    # Drugi niezależny odczyt tej samej strony chroni przed chwilową / błędną ceną.
    page.reload(wait_until='domcontentloaded', timeout=60000)
    page.wait_for_timeout(2200)
    visible2, full2 = v.page_text(page)
    p2, total2 = exact_variant(visible2, c)
    if p2 != p or total2 != total:
        return None, 'cena/konfiguracja zmieniła się przy drugim odczycie'
    beach_ok2, _ = official_beach(c['source'], visible2, full2)
    if not v.baggage(full2) or not beach_ok2:
        return None, 'warunki nie potwierdziły się 2×'

    official, ref = v.official_discount(c['source'], c['text'], c['base_price'])
    return {'price': p, 'total': total, 'rating': r, 'scale': scale, 'stars': st, 'beach_m': beach_m, 'transfer': 'transfer' in full.lower(), 'official_discount': official, 'official_ref': ref}, None


def candidate(source, airport, row, today):
    text = v.norm(row.get('text')); url = v.clean_url(row.get('url') or '')
    if not text or not url:
        return None
    start, end = flexible_dates(text, today)
    if not start or not end or not (today <= start <= today + timedelta(days=30)):
        return None
    days = v.duration(text, start, end)
    board = meal(text)
    vals = sorted(set(current_price_matches(source, text)))
    if not days or not (5 <= days <= 10) or not board or airport.lower() not in text.lower() or len(vals) != 1:
        return None
    base = vals[0]; price = base + v.fee(source, text)
    if price > 2500:
        return None
    r, scale = v.rating(text + ' ' + v.norm(row.get('meta')))
    if r is None:
        return None
    return {'source': source, 'airport': airport, 'url': url, 'title': v.norm(row.get('title')) or text[:80], 'text': text, 'meta': v.norm(row.get('meta')), 'start': start, 'end': end, 'days': days, 'board': board, 'base_price': base, 'card_price': price}


def run():
    today = datetime.now(v.WARSAW).date()
    state = v.load(v.STATE_FILE, {'initialized': False, 'prices': {}, 'alerts': {}})
    state.setdefault('prices', {}); state.setdefault('alerts', {})
    checked = pref = verified = sent = max_score = max_discount = 0; best = None; items = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1440, 'height': 1400}, locale='pl-PL', user_agent='Mozilla/5.0 Chrome/131 Safari/537.36')
        search = ctx.new_page(); detail = ctx.new_page()
        for source, airport, url, party_marker in v.SOURCES:
            try:
                search.goto(url, wait_until='domcontentloaded', timeout=60000)
                search.wait_for_timeout(2400)
                visible, _ = v.page_text(search)
                if party_marker.lower() not in visible.lower():
                    print(source, airport, 'POMINIĘTO: brak potwierdzenia 2 dorosłych')
                    continue
                rows = v.cards(search, source, airport)
            except Exception as exc:
                print(source, airport, 'BŁĄD:', exc)
                continue
            print(source, airport, 'kart:', len(rows))
            for row in rows:
                checked += 1
                c = candidate(source, airport, row, today)
                if c:
                    items.append(c); pref += 1

        items.sort(key=lambda x: x['card_price'])
        for c in items[:20]:
            print('Weryfikuję', c['source'], c['title'][:45], c['card_price'])
            d, err = verify(detail, c)
            if not d:
                print(' ODRZUT:', err); continue
            key = hashlib.sha256(f"{c['source']}|{c['title']}|{c['start']}|{c['airport']}".encode()).hexdigest()[:28]
            hist = v.history_discount(state, key, d['price'], today); discount = max(hist, d['official_discount'])
            verified += 1; best = d['price'] if best is None else min(best, d['price']); max_discount = max(max_discount, discount)
            print(' POTWIERDZONE 2X:', d['price'], 'zł/os., razem', d['total'], 'zł, spadek', discount, '%')
            if discount < 25:
                continue
            sc = v.score(d['price'], discount, c['board'], d['beach_m'], d['transfer']); max_score = max(max_score, sc)
            c.update(d); c.update({'key': key, 'discount': discount, 'score': sc})
            if SAFE_TEST_MODE:
                print(' SAFE TEST — bez Telegrama i bez zapisu stanu'); continue
            old = state['alerts'].get(key, {})
            if old and not (d['price'] <= int(old.get('price', d['price']))-100 or discount >= int(old.get('discount', discount))+5):
                continue
            if not state.get('initialized') and d['official_discount'] < 25:
                continue
            v.telegram(v.fmt(c)); state['alerts'][key] = {'date': today.isoformat(), 'price': d['price'], 'discount': discount, 'score': sc}; sent += 1
        ctx.close(); browser.close()

    if SAFE_TEST_MODE:
        print('SAFE TEST: checked=', checked, 'prefilter=', pref, 'verified2x=', verified, 'alerts=0'); return
    state['initialized'] = True
    v.save(v.STATE_FILE, state)
    v.stats(checked, pref, verified, sent, max_score, best, max_discount)
    print('PRODUKCJA: checked=', checked, 'prefilter=', pref, 'verified2x=', verified, 'alerts=', sent)


if __name__ == '__main__':
    run()
