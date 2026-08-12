# Radar nieruchomości 0 zł

Automat działa w GitHub Actions, więc Twój komputer może być wyłączony.
Co 15 minut otwiera podane strony wyników wyszukiwania, wykrywa nowe mieszkania,
liczy prosty score 0–100 i wysyła najlepsze oferty na Telegram.

## Koszt

- Python: 0 zł
- Playwright: 0 zł
- SQLite nie jest potrzebne w wersji chmurowej
- Telegram Bot API: 0 zł do zwykłych powiadomień
- GitHub Actions: 0 zł przy użyciu standardowego runnera w PUBLICZNYM repozytorium

Uwaga: repozytorium publiczne oznacza, że kod jest publiczny. Token Telegrama
i konfigurację wyszukiwań trzymamy w GitHub Secrets, nie w kodzie.

## Krok 1 — Telegram

1. Zainstaluj/otwórz Telegram.
2. Wyszukaj oficjalnego bota `@BotFather`.
3. Wyślij `/newbot`.
4. Nadaj nazwę, np. `Radar Mieszkan`.
5. Nadaj username kończący się na `bot`.
6. BotFather poda TOKEN. Nie wklejaj go do repozytorium.

Następnie:
1. Otwórz swojego nowego bota i kliknij Start / wyślij `/start`.
2. W przeglądarce otwórz:
   `https://api.telegram.org/bot<TWOJ_TOKEN>/getUpdates`
3. W JSON znajdź `"chat":{"id":123456789...}`. Ta liczba to TELEGRAM_CHAT_ID.

## Krok 2 — GitHub

1. Załóż darmowe konto na GitHub.
2. Utwórz PUBLICZNE repozytorium, np. `radar-nieruchomosci`.
3. Wgraj całą zawartość tego folderu do repozytorium.

Struktura ma wyglądać:

```
radar-nieruchomosci/
├── .github/
│   └── workflows/
│       └── radar.yml
├── src/
│   └── main.py
├── requirements.txt
├── seen.json
└── README.md
```

## Krok 3 — zbuduj wyszukiwania na portalach

Na każdym portalu ustaw ręcznie dokładne filtry:
- sprzedaż mieszkania,
- lokalizacja,
- cena maksymalna,
- metraż,
- liczba pokoi,
- inne parametry.

Potem skopiuj PEŁNY adres strony z wynikami wyszukiwania.

Najlepiej tworzyć osobne wyszukiwanie dla każdej lokalizacji,
np. Gliwice, Zabrze, Bytom, Katowice itd.

## Krok 4 — SEARCH_CONFIG_JSON

W GitHub wejdź:
Settings > Secrets and variables > Actions > New repository secret

Nazwa:
`SEARCH_CONFIG_JSON`

Wartość, przykład:

```json
{
  "threshold": 60,
  "searches": [
    {
      "name": "Gliwice 2-3 pokoje",
      "url": "TU_WKLEJ_LINK_Z_PORTALU",
      "max_price": 350000,
      "min_area": 35,
      "max_area": 65,
      "rooms": [2, 3],
      "exclude": ["kamienica", "udział", "licytacja", "TBS"]
    }
  ]
}
```

Możesz dodać wiele obiektów do `searches`.

## Krok 5 — sekrety Telegrama

Dodaj dwa kolejne Repository secrets:

`TELEGRAM_BOT_TOKEN`
- token otrzymany od BotFather

`TELEGRAM_CHAT_ID`
- numer chat_id otrzymany z getUpdates

## Krok 6 — pierwsze uruchomienie

GitHub:
Actions > Radar nieruchomości > Run workflow

Jeżeli wszystko działa, automat będzie później uruchamiał się sam co 15 minut.

## Jak działa scoring

Punkty są liczone m.in. za:
- cenę za m² poniżej mediany aktualnych wyników wyszukiwania,
- 2–3 pokoje,
- metraż 35–65 m²,
- słowa takie jak „do remontu”, „pilnie”, „negocjacji”, „bezpośrednio”,
- balkon/windę.

Próg ustawia pole:
`"threshold": 60`

Wyższy próg = mniej alertów, ale bardziej selektywnych.

## Ważne ograniczenia

Strony portali zmieniają HTML i czasem blokują automatyczne przeglądanie.
Jeśli portal zmieni układ strony lub pokaże CAPTCHA, selektor dla tego portalu
może wymagać poprawki.

Nie zwiększaj częstotliwości bez potrzeby. 15 minut jest rozsądnym startem.
Korzystaj wyłącznie z publicznie dostępnych wyników wyszukiwania i zgodnie
z regulaminem danego serwisu.


## Heartbeat

Publiczne repozytoria GitHub mogą mieć automatycznie wyłączone zaplanowane workflow
po 60 dniach bez aktywności. Dlatego pakiet zawiera `heartbeat.yml`, który raz w miesiącu
robi pusty commit. Ma to utrzymywać regularną aktywność repozytorium bez udziału komputera.
