import os, urllib.parse, urllib.request
TOKEN=os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID=os.environ['TELEGRAM_CHAT_ID']
msgs=[
'''🇪🇬 EGIPT — HAPPY LIFE VILLAGE
🏨 Happy Life Village, Dahab
⭐ 7,9/10
✈️ Katowice
📅 30.08–06.09.2026 | 8 dni / 7 nocy
🍽 All Inclusive
🏖 bezpośrednio przy plaży
💰 ok. 2454 zł/os. | 4908 zł/2 os.
🔗 https://www.wakacje.pl/hotele/egipt/happy-life-village-14411.html
⚠️ Przed rezerwacją potwierdź finalną cenę i bagaż.''',
'''🇪🇬 EGIPT — EMPIRE BEACH RESORT
🏨 Empire Beach Resort, Hurghada
⭐ 7,0/10
✈️ Katowice
📅 28.08–04.09.2026 | 8 dni / 7 nocy
🍽 All Inclusive
🏖 bezpośrednio przy prywatnej plaży
💰 ok. 2444 zł/os. | 4888 zł/2 os.
🔗 https://www.wakacje.pl/hotele/egipt/empire-beach-resort-ex-triton-empire-beach-resort-hurghada-8327.html
⚠️ Przed rezerwacją potwierdź finalną cenę i bagaż.''',
'''🇹🇷 TURCJA — MERSOY EXCLUSIVE AQUA RESORT
🏨 Mersoy Exclusive Aqua Resort 4★, Icmeler
⭐ 7,4/10
✈️ Katowice → Bodrum
📅 26.08–02.09.2026 | 8 dni / 7 nocy
🍽 All Inclusive
🏖 ok. 150 m od plaży
💰 ok. 2072 zł/os. | 4143 zł/2 os.
✅ Przechodzi limit ceny i plaży.
🔗 https://www.wakacje.pl/oferty/turcja/wybrzeze-egejskie/icmeler/mersoy-exclusive-aqua-resort-1145596.html''',
'''🇹🇷 TURCJA — SIDE KERVAN
🏨 Side Kervan 3★, Side
⭐ 7,6/10
📅 01.09–08.09.2026 | 8 dni / 7 nocy
🍽 All Inclusive
💰 od ok. 2050 zł/os.
⚠️ Plaża ok. 750 m — poza limitem 500 m.
🔗 https://www.wakacje.pl/oferty/turcja/riwiera-turecka/side/side-kervan-759415.html''',
'''🇹🇷 TURCJA — ERGUN
🏨 Ergun, Alanya
⭐ 7,2/10
📅 01.09–08.09.2026 | 8 dni / 7 nocy
🍽 All Inclusive
💰 od ok. 2014 zł/os.
⚠️ Plaża ok. 800 m — poza limitem 500 m.
🔗 https://www.wakacje.pl/oferty/turcja/riwiera-turecka/alanya/ergun-763049.html'''
]
url=f'https://api.telegram.org/bot{TOKEN}/sendMessage'
for m in msgs:
    data=urllib.parse.urlencode({'chat_id':CHAT_ID,'text':m}).encode()
    with urllib.request.urlopen(urllib.request.Request(url,data=data),timeout=20) as r:
        assert r.status==200
print('sent',len(msgs))
