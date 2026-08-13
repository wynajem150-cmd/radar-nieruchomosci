from datetime import datetime, timedelta

import vacation_deals as v
import vacation_strict as s
from playwright.sync_api import sync_playwright


def contexts(text, needles, radius=700):
    low = text.lower()
    for needle in needles:
        start = 0
        hits = 0
        while hits < 4:
            pos = low.find(needle.lower(), start)
            if pos < 0:
                break
            print(f'[{needle}]', text[max(0,pos-radius):pos+radius])
            start = pos + len(needle)
            hits += 1


def run():
    today = datetime.now(v.WARSAW).date()
    candidates = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width':1440,'height':1400}, locale='pl-PL', user_agent='Mozilla/5.0 Chrome/131 Safari/537.36')
        search = ctx.new_page(); detail = ctx.new_page()
        for source, airport, url, party_marker in v.SOURCES:
            search.goto(url, wait_until='domcontentloaded', timeout=60000); search.wait_for_timeout(2200)
            visible,_ = v.page_text(search)
            if party_marker.lower() not in visible.lower():
                continue
            for row in v.cards(search, source, airport):
                text=v.norm(row.get('text')); start,end=s.flexible_dates(text,today)
                days=v.duration(text,start,end) if start and end else None; meal=v.board(text); price=s.unique_current_price(source,text); rating,scale=v.rating(text+' '+v.norm(row.get('meta')))
                if start and end and today<=start<=today+timedelta(days=30) and days and 5<=days<=10 and meal and price and rating is not None:
                    candidates.append({'source':source,'airport':airport,'url':v.clean_url(row.get('url') or ''),'title':v.norm(row.get('title')) or text[:80],'text':text,'meta':v.norm(row.get('meta')),'start':start,'end':end,'days':days,'board':meal,'card_price':price})
        chosen=[]
        for source in ('ITAKA','TUI'):
            item=next((x for x in sorted(candidates,key=lambda y:y['card_price']) if x['source']==source),None)
            if item: chosen.append(item)
        for c in chosen:
            print('\n==========',c['source'],c['title'],'==========')
            detail.goto(c['url'],wait_until='domcontentloaded',timeout=60000); detail.wait_for_timeout(3500)
            visible,full=v.page_text(detail)
            html=detail.content()
            print('VISIBLE contexts:')
            contexts(visible,['plaża','plaży','bagaż rejestrowany','gwiazdk','kategoria','standard hotelu','klimatyzacja','Położenie','Ważne informacje'])
            print('HTML/metadata contexts:')
            contexts(html,['starRating','hotelCategory','category','stars','bagaż rejestrowany','plaża','distanceToBeach'],900)
        ctx.close(); browser.close()

if __name__=='__main__':
    run()
