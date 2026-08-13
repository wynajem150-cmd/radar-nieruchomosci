import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

STATS=Path('vacation_daily_stats.json')
WARSAW=ZoneInfo('Europe/Warsaw')
now=datetime.now(WARSAW)
if now.hour!=20:
    print(f'Pominięto raport: {now:%H:%M}')
    raise SystemExit(0)

try:
    data=json.loads(STATS.read_text(encoding='utf-8'))
except Exception:
    data={}

today=now.date().isoformat()
if data.get('date')!=today or data.get('reported'):
    print('Brak raportu do wysłania.')
    raise SystemExit(0)

token=os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
chat_id=os.environ.get('VACATION_TELEGRAM_CHAT_ID','').strip()
if not token or not chat_id:
    raise RuntimeError('Brak TELEGRAM_BOT_TOKEN lub VACATION_TELEGRAM_CHAT_ID')

best=data.get('best_price')
best_txt=f'{best} zł/os.' if best is not None else 'brak'
message=(
    '✅ <b>Radar wakacji działa</b>\n\n'
    f'📅 {now:%d.%m.%Y}\n'
    f'🔄 Uruchomień dziś: <b>{data.get("runs",0)}</b>\n'
    f'🔎 Sprawdzonych kart ofert: <b>{data.get("checked",0)}</b>\n'
    f'🎯 Spełniających kryteria: <b>{data.get("matched",0)}</b>\n'
    f'📲 Alertów wysłanych: <b>{data.get("alerts",0)}</b>\n'
    f'🏆 Najwyższy score: <b>{data.get("max_score",0)}/100</b>\n'
    f'💰 Najniższa cena: <b>{best_txt}</b>\n'
    f'📉 Największa wykryta przecena: <b>{data.get("max_discount",0)}%</b>\n\n'
    'To jest dzienny raport kontrolny.'
)
r=requests.post(f'https://api.telegram.org/bot{token}/sendMessage',json={'chat_id':chat_id,'text':message,'parse_mode':'HTML','disable_web_page_preview':True},timeout=20)
r.raise_for_status()
data['reported']=True
STATS.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print('Raport wakacyjny wysłany.')
