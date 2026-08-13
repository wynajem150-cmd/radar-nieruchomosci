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
SAFE_TEST_MODE = True  # po teście zostanie wyłączone
AIRPORTS = ('Katowice', 'Kraków', 'Wrocław')

# Tryb konserwatywny: używamy tylko źródeł, gdzie oferta jest parsowana
# jako jeden konkretny wariant. Nie bierzemy najniższej kwoty z całej strony.
SOURCES = [
    ('ITAKA', 'Katowice', 'https://www.itaka.pl/last-minute/z-katowic/?page=1&participants%5B0%5D%5Badults%5D=2', '2 + 0'),
    ('ITAKA', 'Kraków', 'https://www.itaka.pl/last-minute/z-krakowa/?page=1&participants%5B0%5D%5Badults%5D=2', '2 + 0'),
    ('ITAKA', 'Wrocław', 'https://www.itaka.pl/last-minute/z-wroclawia/?page=1&participants%5B0%5D%5Badults%5D=2', '2 + 0'),
    ('TUI', 'Katowice', 'https://www.tui.pl/last-minute-z-katowic', '2 dorosłych'),
    ('TUI', 'Kraków', 'https://www.tui.pl/last-minute-z-krakowa', '2 dorosłych'),
    ('TUI', 'Wrocław', 'https://www.tui.pl/last-minute-z-wroclawia', '2 dorosłych'),
]

RANGE_RE = re.compile(r'(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{4}))?\s*[-–]\s*(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})')
DAYS_RE = re.compile(r'(\d{1,2})\s*dni\b', re.I)
NIGHTS_RE = re.compile(r'(\d{1,2})\s*nocleg', re.I)
ITAKA_PRICE_RE = re.compile(r'(\d{1,2}(?:[ .\u00a0]\d{3})|\d{3,4})\s*zł\s*/\s*os\.?', re.I)
TUI_PRICE_RE = re.compile(r'(\d{1,2}(?:[ .\u00a0]\d{3})|\d{3,4})\s*zł\s*osoba\b', re.I)
ITAKA_FEE_RE = re.compile(r'\+\s*(\d{1,3})\s*zł\s*\(\s*TFG\s+i\s+TFP\s*\)', re.I)
ITAKA_30D_RE = re.compile(r'Najniższa\s+cena\s+z\s+30\s+dni\s*:\s*(\d{1,2}(?:[ .\u00a0]\d{3})|\d{3,4})\s*zł\s*/\s*os', re.I)
RATING_RE = re.compile(r'(?<!\d)(\d(?:[.,]\d)?)\s*/\s*(10|6|5)\b')
STAR_RE = re.compile(r'\b([3-5])\s*(?:★|\*|gwiazdk)', re.I)
BEACH_RE_1 = re.compile(r'(\d{1,4})\s*m[^.\n]{0,70}plaż', re.I)
BEACH_RE_2 = re.compile(r'plaż[^.\n]{0,70}?(\d{1,4})\s*m', re.I)
DIRECT_BEACH = ('bezpośrednio przy plaży','bezposrednio przy plazy','tuż przy plaży','tuz przy plazy','plaża przy hotelu','plaza przy hotelu')
WARM = ('turcja','egipt','tunezja','grecja','cypr','hiszpania','albania','bułgaria','bulgaria','maroko','malta','zanzibar','kenia','dominikana')


def norm(s):
    return ' '.join((s or '').replace('\u00a0',' ').split())


def load(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def clean_url(url):
    p=urlsplit(url)
    return urlunsplit((p.scheme,p.netloc.lower(),p.path.rstrip('/'),p.query,''))


def money(s):
    return int(re.sub(r'\D','',s))


def price_base(source,text):
    m=(ITAKA_PRICE_RE if source=='ITAKA' else TUI_PRICE_RE).search(text)
    return money(m.group(1)) if m else None


def fee(source,text):
    if source!='ITAKA': return 0
    m=ITAKA_FEE_RE.search(text)
    return int(m.group(1)) if m else 0


def price_total(source,text):
    p=price_base(source,text)
    return None if p is None else p+fee(source,text)


def dates(text):
    m=RANGE_RE.search(text)
    if not m: return None,None
    try:
        end=date(int(m.group(6)),int(m.group(5)),int(m.group(4)))
        sy=int(m.group(3)) if m.group(3) else end.year
        start=date(sy,int(m.group(2)),int(m.group(1)))
        if start>end: start=date(end.year-1,start.month,start.day)
        return start,end
    except Exception:
        return None,None


def duration(text,start,end):
    m=DAYS_RE.search(text)
    if m: return int(m.group(1))
    m=NIGHTS_RE.search(text)
    if m: return int(m.group(1))+1
    return (end-start).days+1 if start and end else None


def board(text):
    low=' '+text.lower()+' '
    if 'all inclusive' in low: return 'All Inclusive'
    if any(x in low for x in ('half board','2 posiłki','2 posilki','obiadokolac',' hb ')): return 'HB'
    if any(x in low for x in ('full board','3 posiłki','3 posilki')): return 'FB'
    return None


def rating(text):
    vals=[]
    for v,s in RATING_RE.findall(text):
        value=float(v.replace(',','.')); scale=int(s)
        threshold={10:7.0,6:4.2,5:4.0}[scale]
        if value<=scale: vals.append((value,scale,value>=threshold))
    for value,scale,ok in vals:
        if ok: return value,scale
    return None,None


def stars(text):
    m=STAR_RE.search(text)
    return int(m.group(1)) if m else None


def beach(text):
    low=text.lower(); ds=[]
    for pat in (BEACH_RE_1,BEACH_RE_2):
        for m in pat.finditer(text):
            try: ds.append(int(m.group(1)))
            except Exception: pass
    if ds:
        d=min(ds); return d<=500,d
    if any(x in low for x in DIRECT_BEACH): return True,0
    return False,None


def baggage(text):
    low=text.lower()
    if re.search(r'bez\s+bagażu\s+rejestrowan|bez\s+bagazu\s+rejestrowan',low): return False
    for m in re.finditer(r'bagaż\s+rejestrowany|bagaz\s+rejestrowany',low):
        ctx=low[max(0,m.start()-100):m.end()+140]
        if any(x in ctx for x in ('dopłat','dopl','płatn','platn','dokup','nie obejmuje')): continue
        if 'w cenie' in ctx or re.search(r'\b(?:15|20|23|25|30)\s*kg\b',ctx): return True
    return False


def climate(text):
    low=text.lower()
    return not any(x in low for x in WARM) or 'klimatyzac' in low


def official_discount(source,text,current_base):
    if source!='ITAKA': return 0,None
    m=ITAKA_30D_RE.search(text)
    if not m: return 0,None
    old=money(m.group(1))
    if old<=current_base: return 0,old
    return round((old-current_base)/old*100),old


def history_discount(state,key,current,today):
    hist=state.setdefault('prices',{}).setdefault(key,[])
    cutoff=today-timedelta(days=30); clean=[]
    for row in hist:
        try:
            if date.fromisoformat(row['date'])>=cutoff: clean.append({'date':row['date'],'price':int(row['price'])})
        except Exception: pass
    old=max([r['price'] for r in clean],default=current)
    drop=round((old-current)/old*100) if old>current else 0
    if not clean or clean[-1]!={'date':today.isoformat(),'price':current}: clean.append({'date':today.isoformat(),'price':current})
    state['prices'][key]=clean[-40:]
    return drop


def page_text(page):
    d=page.evaluate("""() => { const b=document.body; const attrs=Array.from(document.querySelectorAll('[aria-label],[title],img[alt]')).slice(0,1000).map(x=>[x.getAttribute('aria-label'),x.getAttribute('title'),x.getAttribute('alt')].filter(Boolean).join(' ')).join(' '); return {visible:b?(b.innerText||''):'',full:(b?(b.textContent||''):'')+' '+attrs}; }""")
    return norm(d['visible']),norm(d['full'])


def cards(page,source,airport):
    return page.evaluate("""({source,airport}) => {
      const out=[]; const cta=source==='ITAKA'?/sprawdź\s+ofertę/i:/zobacz\s+ofertę/i;
      const price=source==='ITAKA'?/\d[\d .\u00a0]{2,8}\s*zł\s*\/\s*os/i:/\d[\d .\u00a0]{2,8}\s*zł\s*osoba/i;
      for(const a of document.querySelectorAll('a[href]')){
        if(!cta.test((a.innerText||'').trim())) continue; let n=a,box=null;
        for(let i=0;i<10&&n;i++,n=n.parentElement){ const t=(n.innerText||'').trim(); if(t.length>70&&t.length<3200&&price.test(t)&&t.toLowerCase().includes(airport.toLowerCase())){box=n;break;} }
        if(!box) continue; const h=box.querySelector('h1,h2,h3,h4,h5,[class*=title],[data-testid*=title]');
        const meta=Array.from(box.querySelectorAll('[aria-label],[title],img[alt]')).map(x=>[x.getAttribute('aria-label'),x.getAttribute('title'),x.getAttribute('alt')].filter(Boolean).join(' ')).join(' ');
        out.push({url:a.href,text:(box.innerText||'').trim(),title:h?(h.innerText||'').trim():'',meta});
      } return out.slice(0,100);
    }""",{'source':source,'airport':airport})


def context_for(visible,source,start,end,airport,meal):
    low=visible.lower(); needles=[f'{start.day:02d}.{start.month:02d}',f'{start.day}.{start.month}']
    board_terms=['all inclusive'] if meal=='All Inclusive' else (['half board','2 posiłki','2 posilki','obiadokolac'] if meal=='HB' else ['full board','3 posiłki','3 posilki'])
    for needle in needles:
        pos=0
        while True:
            pos=low.find(needle.lower(),pos)
            if pos<0: break
            ctx=visible[max(0,pos-1400):pos+2200]; cl=ctx.lower(); pos+=len(needle)
            if airport.lower() not in cl or not any(x in cl for x in board_terms): continue
            if not any(x.lower() in cl for x in (f'{end.day:02d}.{end.month:02d}',f'{end.day}.{end.month}')): continue
            if price_base(source,ctx) is None: continue
            return ctx
    return None


def verify(page,c):
    try:
        page.goto(c['url'],wait_until='domcontentloaded',timeout=60000); page.wait_for_timeout(2500)
        visible,full=page_text(page)
    except Exception as e: return None,f'otwarcie: {e}'
    words=[w.lower() for w in re.findall(r'[\wąćęłńóśźż-]{4,}',c['title'],re.I)[:4]]
    if words and sum(w in full.lower() for w in words)<min(2,len(words)): return None,'nie potwierdzono hotelu'
    ctx=context_for(visible,c['source'],c['start'],c['end'],c['airport'],c['board'])
    if not ctx: return None,'brak jednego wariantu termin+lotnisko+wyżywienie+cena'
    p=price_total(c['source'],ctx)
    if p is None or p>MAX_PRICE_PP: return None,'cena poza limitem lub niejednoznaczna'
    st=stars(full)
    if st is None or st<3: return None,'nie potwierdzono min 3★'
    bok,bm=beach(full)
    if not bok: return None,'nie potwierdzono plaży <=500m'
    if not baggage(full): return None,'nie potwierdzono bagażu rejestrowanego w cenie'
    if not climate(full): return None,'nie potwierdzono klimatyzacji'
    r,rs=rating(c['text']+' '+c['meta'])
    if r is None: return None,'nie potwierdzono oceny'
    od,ref=official_discount(c['source'],ctx,price_base(c['source'],ctx))
    first={'price':p,'fee':fee(c['source'],ctx),'stars':st,'beach_m':bm,'rating':r,'scale':rs,'official_discount':od,'official_ref':ref,'transfer':'transfer' in full.lower()}
    try:
        page.reload(wait_until='domcontentloaded',timeout=60000); page.wait_for_timeout(1800); vis2,full2=page_text(page)
    except Exception as e: return None,f'drugi odczyt: {e}'
    ctx2=context_for(vis2,c['source'],c['start'],c['end'],c['airport'],c['board'])
    if not ctx2 or price_total(c['source'],ctx2)!=p: return None,'cena nie potwierdziła się 2×'
    if not baggage(full2) or not beach(full2)[0]: return None,'warunki nie potwierdziły się 2×'
    return first,None


def score(price,discount,meal,bm,transfer):
    s=55+min(25,max(0,discount-20))+(12 if price<=2000 else 8 if price<=2250 else 4)
    s+=5 if meal=='All Inclusive' else 0; s+=5 if bm==0 else 4 if bm is not None and bm<=200 else 2; s+=2 if transfer else 0
    return min(100,s)


def telegram(msg):
    token=os.environ.get('TELEGRAM_BOT_TOKEN','').strip(); chat=os.environ.get('VACATION_TELEGRAM_CHAT_ID','').strip()
    if not token or not chat: raise RuntimeError('Brak sekretów Telegram')
    r=requests.post(f'https://api.telegram.org/bot{token}/sendMessage',json={'chat_id':chat,'text':msg,'parse_mode':'HTML','disable_web_page_preview':False},timeout=20); r.raise_for_status()


def fmt(o):
    label='🔥🔥 SUPER OKAZJA' if o['price']<=SUPER_PRICE_PP and o['discount']>=SUPER_DISCOUNT else '🔥 OKAZJA WAKACYJNA'
    beach_txt='przy hotelu' if o['beach_m']==0 else f"ok. {o['beach_m']} m"
    return (f"<b>{label} — {o['score']}/100</b>\n✅ <b>CENA ZWERYFIKOWANA 2×</b>\n🏨 <b>{html.escape(o['title'])}</b>\n🌐 {o['source']}\n✈️ {o['airport']} | {o['start']:%d.%m.%Y}–{o['end']:%d.%m.%Y} | {o['days']} dni\n🍽 {o['board']}\n⭐ {o['stars']}★ | ocena {o['rating']:.1f}/{o['scale']}\n🏖 Plaża: {beach_txt}\n🧳 Bagaż rejestrowany: <b>potwierdzony w cenie</b>\n💰 <b>{o['price']} zł/os.</b> | ok. {o['price']*2} zł za 2 osoby\n📉 <b>spadek ceny {o['discount']}%</b>\n🔗 <a href=\"{html.escape(o['url'],quote=True)}\">Otwórz ofertę</a>\n\n⚠️ Cena potwierdzona w chwili skanu; portal może ją później zmienić.")


def stats(checked,pref,verified,alerts,max_score,best,max_discount):
    ds=datetime.now(WARSAW).date().isoformat(); d=load(STATS_FILE,{})
    if d.get('date')!=ds: d={'date':ds,'runs':0,'checked':0,'prefiltered':0,'verified':0,'matched':0,'alerts':0,'max_score':0,'best_price':None,'max_discount':0,'reported':False}
    d['runs']+=1; d['checked']+=checked; d['prefiltered']+=pref; d['verified']+=verified; d['matched']=d['verified']; d['alerts']+=alerts; d['max_score']=max(d['max_score'],max_score); d['max_discount']=max(d['max_discount'],max_discount)
    if best is not None: d['best_price']=best if d['best_price'] is None else min(d['best_price'],best)
    save(STATS_FILE,d)


def run():
    today=datetime.now(WARSAW).date(); state=load(STATE_FILE,{'initialized':False,'prices':{},'alerts':{}}); checked=pref=verified=sent=max_score=max_discount=0; best=None; candidates=[]; seen=set()
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True); ctx=browser.new_context(viewport={'width':1440,'height':1400},locale='pl-PL',user_agent='Mozilla/5.0 Chrome/131 Safari/537.36'); search=ctx.new_page(); detail=ctx.new_page()
        for source,airport,url,party_marker in SOURCES:
            try: search.goto(url,wait_until='domcontentloaded',timeout=60000); search.wait_for_timeout(2500); vis,_=page_text(search)
            except Exception as e: print(source,airport,'BŁĄD',e); continue
            if party_marker.lower() not in vis.lower(): print(source,airport,'POMINIĘTO: brak potwierdzenia 2 dorosłych'); continue
            try: rows=cards(search,source,airport)
            except Exception as e: print('Błąd kart',e); continue
            print(source,airport,'kart:',len(rows))
            for row in rows:
                text=norm(row.get('text')); url2=clean_url(row.get('url') or ''); title=norm(row.get('title')) or text[:80]; meta=norm(row.get('meta'))
                ident=hashlib.sha256((source+url2+text[:200]).encode()).hexdigest()[:20]
                if not text or not url2 or ident in seen: continue
                seen.add(ident); checked+=1; start,end=dates(text); days=duration(text,start,end) if start and end else None; meal=board(text); p=price_total(source,text); r,rs=rating(text+' '+meta)
                if not start or not end or not (today<=start<=today+timedelta(days=MAX_DAYS_AHEAD)) or days is None or not(MIN_DAYS<=days<=MAX_DAYS): continue
                if airport.lower() not in text.lower() or not meal or p is None or p>MAX_PRICE_PP or r is None: continue
                candidates.append({'source':source,'airport':airport,'url':url2,'title':title,'text':text,'meta':meta,'start':start,'end':end,'days':days,'board':meal,'card_price':p}); pref+=1
        candidates.sort(key=lambda x:x['card_price'])
        for c in candidates[:24]:
            print('Weryfikuję',c['source'],c['airport'],c['title'][:45],c['card_price']); d,err=verify(detail,c)
            if not d: print(' ODRZUT:',err); continue
            key=hashlib.sha256(f"{c['source']}|{c['title'].lower()}|{c['start']}|{c['end']}|{c['airport']}|{c['board']}".encode()).hexdigest()[:28]
            hd=history_discount(state,key,d['price'],today); disc=max(hd,d['official_discount']); verified+=1; best=d['price'] if best is None else min(best,d['price']); max_discount=max(max_discount,disc)
            if disc<MIN_DISCOUNT: print(' OK, ale przecena',disc,'%'); continue
            sc=score(d['price'],disc,c['board'],d['beach_m'],d['transfer']); max_score=max(max_score,sc); c.update(d); c.update({'key':key,'discount':disc,'score':sc});
            if SAFE_TEST_MODE: print(' TEST OKAZJI:',d['price'],'zł/os.',disc,'% — bez wysyłki'); continue
            old=state.setdefault('alerts',{}).get(key,{}); oldp=old.get('price'); oldd=int(old.get('discount',0) or 0)
            if old and not ((oldp is not None and d['price']<=int(oldp)-100) or disc>=oldd+5): continue
            if not state.get('initialized') and d['official_discount']<MIN_DISCOUNT: continue
            telegram(fmt(c)); state['alerts'][key]={'date':today.isoformat(),'price':d['price'],'discount':disc,'score':sc}; sent+=1
        ctx.close(); browser.close()
    if SAFE_TEST_MODE: print('SAFE TEST: żadnych alertów ani zmian stanu. checked=',checked,'pref=',pref,'verified=',verified); return
    state['initialized']=True; save(STATE_FILE,state); stats(checked,pref,verified,sent,max_score,best,max_discount); print('sprawdzono',checked,'prefiltr',pref,'zweryfikowano',verified,'alertów',sent)

if __name__=='__main__': run()
