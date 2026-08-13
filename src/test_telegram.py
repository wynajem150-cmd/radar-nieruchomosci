import os
import urllib.parse
import urllib.request

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

messages = [
    "🏖 REALNA OFERTA — DO WERYFIKACJI RABATU/BAGAŻU\n🇧🇬 Bułgaria — Primorsko\n🏨 Belitsa 3★\n⭐ Ocena 4,2/5\n✈️ Katowice → Burgas\n📅 21.08–28.08.2026 | 8 dni / 7 nocy\n🍽 All Inclusive\n🏖 Plaża: 250 m / 350 m\n💰 2169 zł/os. | 4338 zł za 2 osoby\n\n✅ spełnia budżet, termin, długość, lotnisko, wyżywienie, standard, ocenę i plażę\n⚠️ Travelplanet na liście nie potwierdza przeceny ≥25% ani bagażu rejestrowanego — sprawdź przed rezerwacją.\n🔗 https://www.travelplanet.pl/hotele/bulgaria/primorsko/belitsa/",

    "🏖 REALNA OFERTA — DO WERYFIKACJI RABATU/BAGAŻU\n🇧🇬 Bułgaria — Słoneczny Brzeg\n🏨 Palace 3★\n⭐ Ocena 4,2/5\n✈️ Katowice → Burgas\n📅 20.08–26.08.2026 | 7 dni / 5 nocy\n🍽 Dwa posiłki (HB)\n🏖 Hotel tuż przy plaży\n💰 2449 zł/os. | 4898 zł za 2 osoby\n\n✅ spełnia budżet, termin, długość, lotnisko, wyżywienie, standard, ocenę i plażę\n⚠️ Travelplanet na liście nie potwierdza przeceny ≥25% ani bagażu rejestrowanego — sprawdź przed rezerwacją.\n🔗 https://www.travelplanet.pl/hotele/bulgaria/sloneczny-brzeg/palace/",

    "🏖 REALNA OFERTA — DO WERYFIKACJI RABATU/BAGAŻU\n🇧🇬 Bułgaria — Primorsko\n🏨 Perla Plaza 3★\n⭐ Ocena 4,1/5\n✈️ Katowice → Burgas\n📅 18.08–25.08.2026 | 8 dni / 7 nocy\n🍽 All Inclusive\n🏖 Hotel tuż przy piaszczystej plaży\n💰 2459 zł/os. | 4918 zł za 2 osoby\n\n✅ spełnia budżet, termin, długość, lotnisko, wyżywienie, standard, ocenę i plażę\n⚠️ Travelplanet na liście nie potwierdza przeceny ≥25% ani bagażu rejestrowanego — sprawdź przed rezerwacją.\n🔗 https://www.travelplanet.pl/hotele/bulgaria/primorsko/perla-plaza/",
]

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
for message in messages:
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": message}).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"Telegram HTTP {response.status}")
print("Wysłano 3 realne oferty wakacyjne.")
