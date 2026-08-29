import os
import re
import requests

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
SUPABASE_URL = "https://bjuxmxtfhglkafqsbbgq.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJqdXhteHRmaGdsa2FmcXNiYmdxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODc5ODg4MDEsImV4cCI6MjEwMzU2NDgwMX0.5Sq9_I8tMZrF2qgOlg4g_LRqhjYmJwZKv2nBvAORvs0"

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")


def tg(method, payload=None, timeout=30):
    r = requests.post(f"{TG_API}/{method}", json=payload or {}, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(data)
    return data.get("result")


def supabase_rpc(update_id, token, chat_id, username):
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "p_update_id": update_id,
        "p_token": token,
        "p_chat_id": chat_id,
        "p_username": username or None,
    }
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/rpc/process_telegram_start",
        headers=headers,
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def fmt_money(v):
    return f"{int(v):,}".replace(",", " ") + " zł"


def fmt_profile(row):
    exclusions = row.get("exclusions") or []
    exclusions_text = ", ".join(exclusions) if exclusions else "brak"
    return (
        "✅ Radar Okazji został aktywowany.\n\n"
        f"Kod: {row['tester_code']}\n"
        f"📍 Lokalizacja: {', '.join(row['locations'])}\n"
        f"💰 Cena maks.: {fmt_money(row['max_price'])}\n"
        f"📐 Metraż: {row['min_area']}-{row['max_area']} m²\n"
        f"🚪 Pokoje: {row['min_rooms']}-{row['max_rooms']}\n"
        f"📊 Maks. cena/m²: {fmt_money(row['max_price_m2']) if row.get('max_price_m2') else 'bez znaczenia'}\n"
        f"⛔ Wykluczenia: {exclusions_text}\n\n"
        "Od teraz ten Telegram jest przypisany do Twojego profilu testowego."
    )


def handle_start(update):
    msg = update.get("message") or {}
    text = (msg.get("text") or "").strip()
    if not text.startswith("/start"):
        return
    parts = text.split(maxsplit=1)
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    username = (msg.get("from") or {}).get("username")
    if not chat_id:
        return
    if len(parts) != 2 or not UUID_RE.match(parts[1]):
        tg("sendMessage", {"chat_id": chat_id, "text": "Ten link aktywacyjny jest nieprawidłowy. Skontaktuj się z administratorem Radaru Okazji."})
        return
    rows = supabase_rpc(update["update_id"], parts[1], chat_id, username)
    if rows:
        tg("sendMessage", {"chat_id": chat_id, "text": fmt_profile(rows[0])})
    else:
        tg("sendMessage", {"chat_id": chat_id, "text": "Ten link został już użyty albo nie jest aktywny. Jeśli to Twój link, skontaktuj się z administratorem."})


def main():
    updates = tg("getUpdates", {"timeout": 20, "allowed_updates": ["message"]}, timeout=30) or []
    for update in updates:
        try:
            handle_start(update)
        except Exception as exc:
            print(f"ERROR update {update.get('update_id')}: {exc}")


if __name__ == "__main__":
    main()
