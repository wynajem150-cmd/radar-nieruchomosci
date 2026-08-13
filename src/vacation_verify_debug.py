from datetime import datetime, timedelta

import vacation_deals as v
import vacation_strict as s
from playwright.sync_api import sync_playwright


def run():
    # Tylko test techniczny: wyższy limit pozwala zweryfikować istniejące oferty.
    # Nie wysyła Telegrama i nie zapisuje stanu.
    v.MAX_PRICE_PP = 6000
    today = datetime.now(v.WARSAW).date()
    candidates = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={'width': 1440, 'height': 1400},
            locale='pl-PL',
            user_agent='Mozilla/5.0 Chrome/131 Safari/537.36',
        )
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
                if not start or not end or not (today <= start <= today + timedelta(days=30)):
                    continue
                days = v.duration(text, start, end)
                meal = v.board(text)
                price = s.unique_current_price(source, text)
                rating, scale = v.rating(text + ' ' + v.norm(row.get('meta')))
                if not days or not (5 <= days <= 10) or not meal or price is None or rating is None:
                    continue
                candidates.append({
                    'source': source,
                    'airport': airport,
                    'url': v.clean_url(row.get('url') or ''),
                    'title': v.norm(row.get('title')) or text[:80],
                    'text': text,
                    'meta': v.norm(row.get('meta')),
                    'start': start,
                    'end': end,
                    'days': days,
                    'board': meal,
                    'card_price': price,
                })

        candidates.sort(key=lambda x: x['card_price'])
        print('KANDYDATÓW TESTOWYCH:', len(candidates))
        for c in candidates[:6]:
            print('\nTEST:', c['source'], c['airport'], c['title'][:60])
            print('KARTA:', c['card_price'], 'zł/os.', c['start'], c['end'], c['board'])
            data, error = s.strict_verify(detail, c)
            if data:
                print('POTWIERDZONE 2X:', data['price'], 'zł/os.; stars=', data['stars'], 'beach=', data['beach_m'], 'baggage=OK')
            else:
                print('ODRZUT:', error)

        ctx.close()
        browser.close()


if __name__ == '__main__':
    run()
