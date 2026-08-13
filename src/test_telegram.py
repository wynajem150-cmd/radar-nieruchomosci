import os
import urllib.parse
import urllib.request

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

messages = [
    "🧪 TEST — 👀 WARTO SPRAWDZIĆ — 67/100\n📍 Bytom\n🌐 TEST\n💰 185 000 zł\n📐 42,0 m² | 4 405 zł/m²\n🚪 2 pokoje\n✅ dobry metraż 35–60 m²\n✅ 2 pokoje\n✅ do odświeżenia\n\nTo tylko wiadomość testowa.",
    "🧪 TEST — 🔥 MOCNA OKAZJA — 84/100\n📍 Opole\n🌐 TEST\n💰 229 000 zł\n📐 54,0 m² | 4 241 zł/m²\n🚪 3 pokoje\n✅ 21% poniżej mediany ceny/m²\n✅ dobry metraż 35–60 m²\n✅ balkon\n✅ do remontu\n\nTo tylko wiadomość testowa.",
]

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
for message in messages:
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": message}).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"Telegram HTTP {response.status}")
print("Wysłano 2 nowe testowe alerty.")
