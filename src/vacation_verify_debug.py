from datetime import datetime, timedelta

import vacation_deals as v
import vacation_strict as s
from playwright.sync_api import sync_playwright


def run():
    today = datetime.now(v.WARSAW).date()
    candidates = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1440, 'height': 1400}, locale='pl-PL', user_agent='Mozilla/5.0 Chrome/131 Safari/537.36')
        search = ctx.new_page()
        detail = ctx.new_page()

        for source, airport, url, party_marker in v.SOURCES:
            search.goto(url, wait_until='domcontentloaded', timeout=60000)
            search.wait_for_timeout(2200)
            visible, _ = v.page_text(search)
            if party_marker.lower() not in visible.lower():
                continue
            for row in v.cards(search, source, airport):
                text = v.norm(row.get('text'))
                start, end = s.flexible_dates(text, today)
                days = v.duration(text, start, end) if start and end else None
                meal = v.board(text)
                price = s.unique_current_price(source, text)
                rating, scale = v.rating(text + ' ' + v.norm(row.get('meta')))
                if not start or not end or not (today <= start <= today + timedelta(days=30)):
                    continue
                if not days or not (5 <= days <= 10) or not meal or price is None or rating is None:
                    continue
                candidates.append({'source': source, 'airport': airport, 'url': v.clean_url(row.get('url') or ''), 'title': v.norm(row.get('title')) or text[:80], 'text': text, 'meta': v.norm(row.get('meta')), 'start': start, 'end': end, 'days': days, 'board': meal, 'card_price': price})

        # Jeden przykład ITAKA i jeden TUI wystarczą do poznania układu strony szczegółów.
        chosen = []
        for source in ('ITAKA', 'TUI'):
            item = next((x for x in sorted(candidates, key=lambda y: y['card_price']) if x['source'] == source), None)
            if item:
                chosen.append(item)

        for c in chosen:
            print('\n================ DETAIL', c['source'], '================')
            print('HOTEL:', c['title'])
            print('KARTA:', c['airport'], c['start'], c['end'], c['board'], c['card_price'], 'zł/os.')
            print('URL:', c['url'])
            detail.goto(c['url'], wait_until='domcontentloaded', timeout=60000)
            detail.wait_for_timeout(3500)
            visible, full = v.page_text(detail)
            print('VISIBLE_START:', visible[:5000])
            for needle in [c['airport'], f"{c['start'].day:02d}.{c['start'].month:02d}", str(c['card_price']), 'bagaż rejestrowany', 'Bagaż rejestrowany', 'All Inclusive']:
                pos = visible.lower().find(needle.lower())
                print('NEEDLE', repr(needle), 'POS', pos)
                if pos >= 0:
                    print('CTX:', visible[max(0, pos-500):pos+1000])
            print('FULL_HAS_BAGGAGE:', 'bagaż rejestrowany' in full.lower())

        ctx.close()
        browser.close()


if __name__ == '__main__':
    run()
