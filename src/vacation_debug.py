from datetime import datetime

import vacation_deals as v
import vacation_strict as s
from playwright.sync_api import sync_playwright


def short(text, n=700):
    text = v.norm(text)
    return text[:n] + ('...' if len(text) > n else '')


def run():
    today = datetime.now(v.WARSAW).date()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={'width': 1440, 'height': 1400},
            locale='pl-PL',
            user_agent='Mozilla/5.0 Chrome/131 Safari/537.36',
        )
        page = ctx.new_page()
        for source, airport, url, party_marker in v.SOURCES:
            print('\n===', source, airport, '===')
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=60000)
                page.wait_for_timeout(2500)
                visible, _ = v.page_text(page)
                print('party_marker:', party_marker.lower() in visible.lower())
                rows = v.cards(page, source, airport)
            except Exception as exc:
                print('BŁĄD:', exc)
                continue
            print('cards:', len(rows))
            for idx, row in enumerate(rows[:2], 1):
                text = v.norm(row.get('text'))
                start, end = s.flexible_dates(text, today)
                days = v.duration(text, start, end) if start and end else None
                meal = v.board(text)
                prices = s.current_price_matches(source, text)
                unique = s.unique_current_price(source, text)
                rating, scale = v.rating(text + ' ' + v.norm(row.get('meta')))
                print(f'CARD {idx}')
                print('title:', v.norm(row.get('title')))
                print('url:', v.clean_url(row.get('url') or ''))
                print('dates:', start, end, 'days:', days)
                print('board:', meal)
                print('prices:', prices, 'unique:', unique)
                print('rating:', rating, scale)
                print('airport_in_text:', airport.lower() in text.lower())
                print('TEXT:', short(text))
        ctx.close()
        browser.close()


if __name__ == '__main__':
    run()
