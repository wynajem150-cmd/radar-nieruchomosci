import json
import os
import urllib.parse
import urllib.request

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

messages = [
    "🧪 TEST — 👀 WARTO SPRAWDZIĆ — 63/100\n📍 Gliwice\n🌐 TEST\n💰 239 000 zł\n📐 52,0 m² | 4 596 zł/m²\n🚪 2 pokoje\n✅ dobry metraż 35–60 m²\n✅ 2 pokoje\n✅ cena poniżej lokalnej mediany\n\nTo tylko wiadomość testowa.",
    "🧪 TEST — 🔥 MOCNA OKAZJA — 78/100\n📍 Zabrze\n🌐 TEST\n💰 199 000 zł\n📐 47,5 m² | 4 189 zł/m²\n🚪 2 pokoje\n✅ 18% poniżej mediany ceny/m²\n✅ dobry metraż 35–60 m²\n✅ balkon\n\nTo tylko wiadomość testowa.",
    "🧪 TEST — 🔥 MOCNA OKAZJA — 91/100\n📍 Kędzierzyn-Koźle\n🌐 TEST\n💰 215 000 zł\n📐 50,0 m² | 4 300 zł/m²\n🚪 3 pokoje\n✅ 26% poniżej mediany ceny/m²\n✅ dobry metraż 35–60 m²\n✅ do remontu\n✅ bezpośrednio\n\nTo tylko wiadomość testowa.",
]

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
for message in messages:
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": message}).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"Telegram HTTP {response.status}")
print("Wysłano 3 testowe alerty.")
