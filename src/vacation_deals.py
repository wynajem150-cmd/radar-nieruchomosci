import hashlib
import html
import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import requests
from playwright.sync_api import sync_playwright

STATE_FILE = Path('vacation_state.json')
STATS_FILE = Path('vacation_daily_stats.json')
WARSAW = ZoneInfo('Europe/Warsaw')

MAX_PRICE_PP = 2500
SUPER_PRICE_PP = 2000
MIN_DISCOUNT = 25
SUPER_DISCOUNT = 40
MIN_DAYS = 5
MAX_DAYS = 10
MAX_DAYS_AHEAD = 30
ADULTS = 2
AIRPORTS = ('Katowice', 'Kraków', 'Wrocław')

SOURCES = [
    ('Wakacje.pl', 'Katowice', 'https://www.wakacje.pl/lastminute/'),
    ('Travelplanet', 'Katowice', 'https://www.travelplanet.pl/wakacje/tanie-last-minute/'),
    ('ITAKA', 'Katowice', 'https://www.itaka.pl/last-minute/'),
    ('TUI', 'Katowice', 'https://www.tui.pl/last-minute'),
    ('Rainbow', 'Katowice', 'https://r.pl/last-minute'),
]

PRICE_RE = re.compile(r'(\d{3,4})\s*zł(?:\s*/\s*os|\s*za osobę)?', re.I)
PCT_RE = re.compile(r'(?<!\d)(\d{2})\s*%')
DATE_RE = re.compile(r'(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})')
DAYS_RE = re.compile(r'(\d{1,2})\s*dni', re.I)
RATING10_RE = re.compile(r'(\d(?:[.,]\d)?)\s*/\s*10')
RATING5_RE = re.compile(r'(\d(?:[.,]\d)?)\s*/\s*5')
STARS_RE = re.compile(r'([1-5])\s*(?:★|\*|gwiazdk)', re.I)
BEACH_RE = re.compile(r'(\d{1,4})\s*m.{0,20}plaż', re.I)


def load(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def norm_url(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip('/'), p.query, ''))


def telegram(message):
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
    chat_id = os.environ.get('VACATION_TELEGRAM_CHAT_ID', '').strip()
    if not token or not chat_id:
        raise RuntimeError('Brak TELEGRAM_BOT_TOKEN lub VACATION_TELEGRAM_CHAT_ID')
    r = requests.post(
        f'https://api.telegram.org/bot{token}/sendMessage',
        json={'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML', 'disable_web_page_preview': False},
        timeout=20,
    )
    r.raise_for_status()


def extract_cards(page):
    return page.evaluate('''() => {
      const out=[];
      for (const a of document.querySelectorAll('a[href]')) {
        let n=a, chosen=null;
        for (let i=0;i<7 && n;i++,n=n.parentElement) {
          const t=(n.innerText||'').trim();
          if (t.length>80 && t.length<3500 && /\\d{3,4}\\s*zł/i.test(t)) { chosen=n; break; }
        }
        if (!chosen) continue;
        const h=chosen.querySelector('h1,h2,h3,h4,[class*=title],[data-testid*=title]');
        out.push({url:a.href, text:(chosen.innerText||'').trim(), title:h?(h.innerText||'').trim():''});
      }
      return out.slice(0,220);
    }''')


def price_from(text):
    vals=[]
    for m in PRICE_RE.finditer(text.replace('\u00a0',' ')):
        try:
            v=int(m.group(1))
            if 300 <= v <= 6000:
                vals.append(v)
        except Exception:
            pass
    return min(vals) if vals else None


def departure_from(text, today):
    dates=[]
    for d,m,y in DATE_RE.findall(text):
        try:
            dt=date(int(y),int(m),int(d))
            if today <= dt <= today+timedelta(days=MAX_DAYS_AHEAD):
                dates.append(dt)
        except Exception:
            pass
    return min(dates) if dates else None


def days_from(text):
    m=DAYS_RE.search(text)
    return int(m.group(1)) if m else None


def airport_from(text):
    low=text.lower()
    for a in AIRPORTS:
        if a.lower() in low:
            return a
    return None


def board_from(text):
    low=text.lower()
    if 'all inclusive' in low:
        return 'All Inclusive'
    if any(x in low for x in ('half board','2 posiłki','2 posilki','obiadokolac',' hb ')):
        return 'HB'
    if any(x in low for x in ('full board','3 posiłki','3 posilki')):
        return 'FB'
    return None


def rating_from(text):
    m=RATING10_RE.search(text)
    if m:
        return float(m.group(1).replace(',','.')),10
    m=RATING5_RE.search(text)
    if m:
        return float(m.group(1).replace(',','.')),5
    return None,None


def rating_ok(v,scale):
    return (scale==10 and v>=7.0) or (scale==5 and v>=4.0)


def stars_from(text):
    m=STARS_RE.search(text)
    return int(m.group(1)) if m else None


def beach_ok(text):
    low=text.lower()
    m=BEACH_RE.search(low)
    if m:
        return int(m.group(1)) <= 500
    return any(x in low for x in ('przy plaży','przy plazy','bezpośrednio przy plaży','bezposrednio przy plazy','blisko plaży','blisko plazy'))


def baggage_ok(text):
    low=text.lower()
    if 'bez bagażu rejestrowan' in low or 'bez bagazu rejestrowan' in low:
        return False
    return ('bagaż rejestrowany' in low or 'bagaz rejestrowany' in low or bool(re.search(r'bagaż.{0,30}(15|20|23|25|30)\s*kg',low)))


def climate_ok(text):
    low=text.lower()
    warm=any(x in low for x in ('turcja','egipt','tunezja','grecja','cypr','hiszpania','albania','maroko','malta','zanzibar','kenia','dominikana'))
    return (not warm) or ('klimatyzac' in low)


def published_discount(text):
    vals=[int(x) for x in PCT_RE.findall(text)]
    return max(vals) if vals else 0


def history_discount(state,key,price,today):
    hist=state.setdefault('prices',{}).setdefault(key,[])
    cutoff=today-timedelta(days=30)
    clean=[]
    for row in hist:
        try:
            if date.fromisoformat(row['date'])>=cutoff:
                clean.append(row)
        except Exception:
            pass
    old=max([int(x['price']) for x in clean],default=price)
    drop=round((old-price)/old*100) if old>price else 0
    clean.append({'date':today.isoformat(),'price':price})
    state['prices'][key]=clean[-40:]
    return drop


def score(price,discount,board,beach,baggage,transfer):
    s=55+min(25,max(0,discount-20))
    s += 12 if price<=2000 else 8 if price<=2250 else 4
    s += 5 if board=='All Inclusive' else 0
    s += 4 if beach else 0
    s += 4 if baggage else 0
    s += 2 if transfer else 0
    return min(100,s)


def fmt(o):
    label='🔥🔥 SUPER OKAZJA' if o['price']<=SUPER_PRICE_PP and o['discount']>=SUPER_DISCOUNT else '🔥 OKAZJA WAKACYJNA'
    return (
        f"<b>{label} — {o['score']}/100</b>\n"
        f"🏨 <b>{html.escape(o['title'])}</b>\n"
        f"🌐 {html.escape(o['source'])}\n"
        f"✈️ {o['airport']} | {o['departure']:%d.%m.%Y} | {o['days']} dni\n"
        f"🍽 {o['board']} | ⭐ {o['stars']}★ | ocena {o['rating']:.1f}/{o['scale']}\n"
        f"🏖 plaża ≤500 m | 🧳 bagaż rejestrowany\n"
        f"💰 <b>{o['price']} zł/os.</b> | {o['price']*2} zł za 2 osoby\n"
        f"📉 <b>przecena ok. {o['discount']}%</b>\n"
        f"🔗 <a href=\"{html.escape(o['url'],quote=True)}\">Otwórz ofertę</a>"
    )


def update_stats(checked,matched,alerts,max_score,best_price,max_discount):
    now=datetime.now(WARSAW); ds=now.date().isoformat()
    d=load(STATS_FILE,{})
    if d.get('date')!=ds:
        d={'date':ds,'runs':0,'checked':0,'matched':0,'alerts':0,'max_score':0,'best_price':None,'max_discount':0,'reported':False}
    d['runs']+=1; d['checked']+=checked; d['matched']+=matched; d['alerts']+=alerts
    d['max_score']=max(d['max_score'],max_score); d['max_discount']=max(d['max_discount'],max_discount)
    if best_price is not None:
        d['best_price']=best_price if d['best_price'] is None else min(d['best_price'],best_price)
    save(STATS_FILE,d)


def run():
    today=datetime.now(WARSAW).date()
    state=load(STATE_FILE,{'initialized':False,'prices':{},'alerts':{}})
    checked=matched=max_score=max_discount=0; best_price=None; candidates=[]; card_seen=set()

    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1400},locale='pl-PL',user_agent='Mozilla/5.0 Chrome/131 Safari/537.36')
        for source,_airport,url in SOURCES:
            try:
                page.goto(url,wait_until='domcontentloaded',timeout=60000); page.wait_for_timeout(3000)
                cards=extract_cards(page)
            except Exception as e:
                print(source,e); continue
            print(source,'kart:',len(cards))
            for c in cards:
                text=' '.join((c.get('text') or '').split()); url2=norm_url(c.get('url') or '')
                if not text or not url2: continue
                cid=hashlib.sha256((source+url2+text[:180]).encode()).hexdigest()[:20]
                if cid in card_seen: continue
                card_seen.add(cid); checked+=1
                price=price_from(text); dep=departure_from(text,today); days=days_from(text); airport=airport_from(text); board=board_from(text)
                rating,scale=rating_from(text); stars=stars_from(text)
                if not price or price>MAX_PRICE_PP or not dep or not days or not (MIN_DAYS<=days<=MAX_DAYS): continue
                if airport not in AIRPORTS or not board or not rating_ok(rating,scale) or stars is None or stars<3: continue
                if not beach_ok(text) or not baggage_ok(text) or not climate_ok(text): continue
                matched+=1; best_price=price if best_price is None else min(best_price,price)
                title=(c.get('title') or '').strip() or text[:70]
                key=hashlib.sha256(f'{source}|{title.lower()}|{dep}|{airport}'.encode()).hexdigest()[:24]
                discount=max(published_discount(text),history_discount(state,key,price,today)); max_discount=max(max_discount,discount)
                if discount<MIN_DISCOUNT: continue
                transfer='transfer' in text.lower(); sc=score(price,discount,board,True,True,transfer); max_score=max(max_score,sc)
                old=state.setdefault('alerts',{}).get(key)
                if old and price>int(old.get('price',price))-100 and discount<int(old.get('discount',discount))+5: continue
                candidates.append({'key':key,'source':source,'title':title,'url':url2,'price':price,'departure':dep,'days':days,'airport':airport,'board':board,'rating':rating,'scale':scale,'stars':stars,'discount':discount,'score':sc})
        browser.close()

    candidates.sort(key=lambda x:(x['score'],x['discount'],-x['price']),reverse=True)
    sent=0
    if state.get('initialized'):
        for o in candidates[:12]:
            telegram(fmt(o)); state['alerts'][o['key']]={'date':today.isoformat(),'price':o['price'],'discount':o['discount']}; sent+=1
    else:
        print('Pierwszy przebieg: buduję bazę cen bez alertów.')
    state['initialized']=True; save(STATE_FILE,state)
    update_stats(checked,matched,sent,max_score,best_price,max_discount)
    print('sprawdzono',checked,'dopasowano',matched,'alertów',sent)

if __name__=='__main__':
    run()
