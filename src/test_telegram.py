import os
import urllib.parse
import urllib.request

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

messages = [
    "🔥🔥 SUPER PEREŁKA POLSKA\n🏨 Blue Marine Mielno\n📍 Mielno, zachodniopomorskie\n⭐ 4,5/5\n🍳 Śniadania i obiadokolacje w cenie\n💰 od 260 zł/noc za 2 osoby\n👤 od 130 zł/os./noc\n📉 ok. 60% taniej: 643 zł → 260 zł\n\n🔗 https://travelist.pl/odkryj/baltyk/polska/zachodniopomorskie/mielno\n\nℹ️ Cena „od” — po wejściu sprawdź konkretny termin przed rezerwacją.",

    "🔥🔥 SUPER PEREŁKA POLSKA\n🏨 Hotel Arka Medical Spa\n📍 Kołobrzeg, zachodniopomorskie\n⭐ 4,6/5\n🍳 Śniadania i obiadokolacje w cenie\n💰 od 249 zł/noc za 2 osoby\n👤 od 125 zł/os./noc\n📉 ok. 52% taniej: 519 zł → 249 zł\n\n🔗 https://travelist.pl/hotele/nad-morzem/sniadania-i-obiadokolacje-w-cenie/sniadania-obiady-i-kolacje-w-cenie\n\nℹ️ Cena „od” — po wejściu sprawdź konkretny termin przed rezerwacją.",

    "🇵🇱 PEREŁKA POLSKA\n🏨 Golden Tulip Gdańsk Residence\n📍 Gdańsk, pomorskie\n⭐ 4,5/5\n🍳 Śniadania i obiadokolacje w cenie\n💰 od 229 zł/noc za 2 osoby\n👤 od 115 zł/os./noc\n📉 ok. 31% taniej: 332 zł → 229 zł\n\n🔗 https://travelist.pl/hotele/nad-morzem/sniadania-i-obiadokolacje-w-cenie/sniadania-obiady-i-kolacje-w-cenie\n\nℹ️ Cena „od” — po wejściu sprawdź konkretny termin przed rezerwacją.",
]

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
for message in messages:
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": message}).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"Telegram HTTP {response.status}")
print("Wysłano 3 perełki Polska.")
