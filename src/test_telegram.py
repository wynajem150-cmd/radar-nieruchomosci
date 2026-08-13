import os
import urllib.parse
import urllib.request

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

messages = [
    "🧪 TEST — 👀 WARTO SPRAWDZIĆ — 69/100\n🛒 OLX OKAZJA\n📍 Gliwice, śląskie\n🎮 Nintendo Switch OLED\n💰 Cena: 620 zł\n📊 Mediana podobnych ofert: 900 zł\n📉 Około 31% poniżej mediany\n💵 Potencjalna różnica: ok. 280 zł\n✅ cena mocno poniżej rynku\n✅ popularny model, łatwy do odsprzedaży\n⚠️ sprawdź stan, blokady i komplet zestawu\n\nTo tylko wiadomość testowa.",
    "🧪 TEST — 🔥 MOCNA OKAZJA — 86/100\n🛒 OLX OKAZJA\n📍 Opole, opolskie\n🔧 Makita 18V LXT\n💰 Cena: 180 zł\n📊 Mediana podobnych ofert: 330 zł\n📉 Około 45% poniżej mediany\n💵 Potencjalna różnica: ok. 150 zł\n✅ bardzo niska cena względem podobnych ofert\n✅ markowy sprzęt, dobry popyt\n⚠️ sprawdź czy to pełne narzędzie, nie sama bateria/ładowarka\n\nTo tylko wiadomość testowa.",
]

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
for message in messages:
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": message}).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"Telegram HTTP {response.status}")
print("Wysłano 2 testowe okazje OLX.")
