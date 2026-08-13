import hashlib
import re
from datetime import date, datetime, timedelta

import vacation_deals as v
from playwright.sync_api import sync_playwright

SAFE_TEST_MODE = True

DATE_PATTERNS = [
    re.compile(r'(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\s*[-–]\s*(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})'),
    re.compile(r'(\d{1,2})[.\-/](\d{1,2})\.?\s*[-–]\s*(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})'),
    re.compile(r'(\d{1,2})[.\-/](\d{1,2})\.?\s*[-–]\s*(\d{1,2})[.\-/](\d{1,2})(?![.\-/]\d)'),
]


def flexible_dates(text, today):
    for idx, pat in enumerate(DATE_PATTERNS):
        m = pat.search(text)
        if not m:
            continue
        try:
            if idx == 0:
                start = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                end = date(int(m.group(6)), int(m.group(5)), int(m.group(4)))
            elif idx == 1:
                end = date(int(m.group(5)), int(m.group(4)), int(m.group(3)))
                start = date(end.year, int(m.group(2)), int(m.group(1)))
                if start > end:
                    start = date(end.year - 1, start.month, start.day)
            else:
                year = today.year
                start = date(year, int(m.group(2)), int(m.group(1)))
                end = date(year, int(m.group(4)), int(m.group(3)))
                if end < start:
                    end = date(year + 1, end.month, end.day)
                if start < today - timedelta(days=2):
                    start = date(year + 1, start.month, start.day)
                    end = date(year + 1, end.month, end.day)
            return start, end
        except Exception:
            pass
    return None, None


def current_price_matches(source, text):
    pat = v.ITAKA_PRICE_RE if source == 'ITAKA' else v.TUI_PRICE_RE
    values = []
    for m in pat.finditer(text):
        before = text[max(0, m.start() - 90):m.start()].lower()
        if source == 'ITAKA' and 'najniższa cena z 30 dni' in before:
            continue
        try:
            values.append(v.money(m.group(1)))
        except Exception:
            pass
    return values


def unique_current_price(source, text):
    vals = current_price_matches(source, text)
    unique = sorted(set(vals))
    if len(unique) != 1:
        return None
    return unique[0] + v.fee(source, text)


def board_terms(meal):
    if meal == 'All Inclusive':
        return ('all inclusive',)
    if meal == 'HB':
        return ('half board', '2 posiłki', '2 posilki', 'obiadokolac')
    return ('full board', '3 posiłki', '3 posilki')


def detail_context(visible, source, start, end, airport, meal):
    low = visible.lower()
    starts = (f'{start.day:02d}.{start.month:02d}', f'{start.day}.{start.month}')
    ends = (f'{end.day:02d}.{end.month:02d}', f'{end.day}.{end.month}')
    for needle in starts:
        pos = 0
        while True:
            pos = low.find(needle.lower(), pos)
            if pos < 0:
                break
            ctx = visible[max(0, pos - 1200):pos + 2000]
            pos += len(needle)
            cl = ctx.lower()
            if airport.lower() not in cl:
                continue
            if not any(term in cl for term in board_terms(meal)):
                continue
            if not any(end_needle.lower() in cl for end_needle in ends):
                continue
            if unique_current_price(source, ctx) is None:
                continue
            return ctx
    return None


def strict_verify(page, candidate):
    try:
        page.goto(candidate['url'], wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(2600)
        visible, full = v.page_text(page)
    except Exception as exc:
        return None, f'otwarcie strony: {exc}'

    title_words = [w.lower() for w in re.findall(r'[\wąćęłńóśźż-]{4,}', candidate['title'], re.I)[:4]]
    if title_words and sum(word in full.lower() for word in title_words) < min(2, len(title_words)):
        return None, 'hotel nie zgadza się ze stroną szczegółów'

    ctx = detail_context(visible, candidate['source'], candidate['start'], candidate['end'], candidate['airport'], candidate['board'])
    if not ctx:
        return None, 'brak jednoznacznego bloku termin + lotnisko + wyżywienie + cena'

    price = unique_current_price(candidate['source'], ctx)
    if price is None or price > v.MAX_PRICE_PP:
        return None, 'cena niejednoznaczna lub przekracza limit'

    rating, scale = v.rating(candidate['text'] + ' ' + candidate['meta'] + ' ' + full)
    if rating is None:
        return None, 'nie potwierdzono wymaganej oceny hotelu'

    st = v.stars(full)
    if st is None or st < 3:
        return None, 'nie potwierdzono minimum 3 gwiazdek'

    beach_ok, beach_m = v.beach(full)
    if not beach_ok:
        return None, 'nie potwierdzono plaży do 500 m'

    if not v.baggage(full):
        return None, 'nie potwierdzono bagażu rejestrowanego w cenie'

    if not v.climate(full):
        return None, 'nie potwierdzono klimatyzacji w ciepłym kraju'

    base = unique_current_price(candidate['source'], ctx) - v.fee(candidate['source'], ctx)
    official_discount, official_ref = v.official_discount(candidate['source'], ctx, base)
    first = {
        'price': price,
        'fee': v.fee(candidate['source'], ctx),
        'rating': rating,
        'scale': scale,
        'stars': st,
        'beach_m': beach_m,
        'transfer': 'transfer' in full.lower(),
        'official_discount': official_discount,
        'official_ref': official_ref,
    }

    try:
        page.reload(wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(1800)
        visible2, full2 = v.page_text(page)
    except Exception as exc:
        return None, f'drugi odczyt: {exc}'

    ctx2 = detail_context(visible2, candidate['source'], candidate['start'], candidate['end'], candidate['airport'], candidate['board'])
    price2 = unique_current_price(candidate['source'], ctx2) if ctx2 else None
    if price2 != price:
        return None, f'cena nie potwierdziła się 2× ({price} -> {price2})'
    if not v.baggage(full2) or not v.beach(full2)[0]:
        return None, 'warunki nie potwierdziły się przy drugim odczycie'

    return first, None


def run():
    today = datetime.now(v.WARSAW).date()
    state = v.load(v.STATE_FILE, {'initialized': False, 'prices': {}, 'alerts': {}})
    state.setdefault('prices', {})
    state.setdefault('alerts', {})
    checked = pref = verified = sent = max_score = max_discount = 0
    best = None
    candidates = []
    seen = set()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1440, 'height': 1400}, locale='pl-PL', user_agent='Mozilla/5.0 Chrome/131 Safari/537.36')
        search = ctx.new_page()
        detail = ctx.new_page()

        for source, airport, url, party_marker in v.SOURCES:
            try:
                search.goto(url, wait_until='domcontentloaded', timeout=60000)
                search.wait_for_timeout(2500)
                visible, _ = v.page_text(search)
            except Exception as exc:
                print(source, airport, 'BŁĄD:', exc)
                continue

            if party_marker.lower() not in visible.lower():
                print(source, airport, 'POMINIĘTO: brak potwierdzenia 2 dorosłych')
                continue

            rows = v.cards(search, source, airport)
            print(source, airport, 'kart:', len(rows))
            for row in rows:
                text = v.norm(row.get('text'))
                url2 = v.clean_url(row.get('url') or '')
                title = v.norm(row.get('title')) or text[:80]
                meta = v.norm(row.get('meta'))
                ident = hashlib.sha256((source + url2 + text[:200]).encode()).hexdigest()[:20]
                if not text or not url2 or ident in seen:
                    continue
                seen.add(ident)
                checked += 1

                start, end = flexible_dates(text, today)
                days = v.duration(text, start, end) if start and end else None
                meal = v.board(text)
                p = unique_current_price(source, text)
                if not start or not end or not (today <= start <= today + timedelta(days=v.MAX_DAYS_AHEAD)):
                    continue
                if days is None or not (v.MIN_DAYS <= days <= v.MAX_DAYS):
                    continue
                if airport.lower() not in text.lower() or not meal or p is None or p > v.MAX_PRICE_PP:
                    continue
                candidates.append({'source': source, 'airport': airport, 'url': url2, 'title': title, 'text': text, 'meta': meta, 'start': start, 'end': end, 'days': days, 'board': meal, 'card_price': p})
                pref += 1

        candidates.sort(key=lambda x: x['card_price'])
        for c in candidates[:24]:
            print('Weryfikuję:', c['source'], c['airport'], c['title'][:50], c['card_price'], 'zł/os.')
            d, err = strict_verify(detail, c)
            if not d:
                print('  ODRZUT:', err)
                continue

            key = hashlib.sha256(f"{c['source']}|{c['title'].lower()}|{c['start']}|{c['end']}|{c['airport']}|{c['board']}".encode()).hexdigest()[:28]
            historical = v.history_discount(state, key, d['price'], today)
            discount = max(historical, d['official_discount'])
            verified += 1
            best = d['price'] if best is None else min(best, d['price'])
            max_discount = max(max_discount, discount)
            print('  POTWIERDZONE 2×:', d['price'], 'zł/os.; przecena', discount, '%')

            if discount < v.MIN_DISCOUNT:
                continue

            sc = v.score(d['price'], discount, c['board'], d['beach_m'], d['transfer'])
            max_score = max(max_score, sc)
            c.update(d)
            c.update({'key': key, 'discount': discount, 'score': sc})

            if SAFE_TEST_MODE:
                print('  SAFE TEST — alert nie został wysłany')
                continue

            old = state['alerts'].get(key, {})
            old_price = old.get('price')
            old_discount = int(old.get('discount', 0) or 0)
            if old and not ((old_price is not None and d['price'] <= int(old_price) - 100) or discount >= old_discount + 5):
                continue
            if not state.get('initialized') and d['official_discount'] < v.MIN_DISCOUNT:
                continue
            v.telegram(v.fmt(c))
            state['alerts'][key] = {'date': today.isoformat(), 'price': d['price'], 'discount': discount, 'score': sc}
            sent += 1

        ctx.close()
        browser.close()

    if SAFE_TEST_MODE:
        print('SAFE TEST: checked=', checked, 'prefilter=', pref, 'verified2x=', verified, 'alerts=0')
        return

    state['initialized'] = True
    v.save(v.STATE_FILE, state)
    v.stats(checked, pref, verified, sent, max_score, best, max_discount)
    print('PRODUKCJA: checked=', checked, 'prefilter=', pref, 'verified2x=', verified, 'alerts=', sent)


if __name__ == '__main__':
    run()
