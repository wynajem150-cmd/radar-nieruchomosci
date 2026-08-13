import os
import urllib.parse
import urllib.request

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

messages = [
    "🧪 TEST — 🔥 OKAZJA WAKACYJNA — 82/100\n🏨 Hotel przykładowy 4★\n✈️ Katowice | 7 dni\n🍽 All Inclusive\n⭐ Ocena 8.2/10\n🏖 Plaża 150 m\n🧳 Bagaż rejestrowany\n💰 2299 zł/os. | 4598 zł za 2 osoby\n📉 Przecena 28%\n\nTo tylko wiadomość testowa.",
    "🧪 TEST — 🔥🔥 SUPER OKAZJA — 96/100\n🏨 Hotel przykładowy 4★\n✈️ Kraków | 7 dni\n🍽 All Inclusive\n⭐ Ocena 8.6/10\n🏖 Hotel przy plaży\n🧳 Bagaż rejestrowany\n💰 1899 zł/os. | 3798 zł za 2 osoby\n📉 Przecena 44%\n\nTo tylko wiadomość testowa.",
]

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
for message in messages:
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": message}).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"Telegram HTTP {response.status}")
print("Wysłano 2 testowe okazje wakacyjne.")
