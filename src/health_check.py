import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from playwright.sync_api import sync_playwright

import main as housing
import olx_deals
import poland_deals
import vacation_deals as vacation

STATE_FILE = Path("health_state.json")
WARSAW = ZoneInfo("Europe/Warsaw")
FAIL_AFTER = 3
DRY_RUN = os.environ.get("HEALTH_DRY_RUN", "").lower() in {"1", "true", "yes"}


def load_state():
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    data.setdefault("sources", {})
    return data


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def telegram(chat_env, text):
    if DRY_RUN:
        print("DRY RUN TELEGRAM:", text.replace("\n", " | "))
        return True
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get(chat_env, "").strip()
    if not token or not chat:
        print(f"Brak sekretu Telegram: {chat_env}", file=sys.stderr)
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text, "disable_web_page_preview": True},
            timeout=20,
        )
        r.raise_for_status()
        return True
    except Exception as exc:
        print(f"Błąd Telegram: {exc}", file=sys.stderr)
        return False


def update_health(state, key, label, count, chat_env):
    now = datetime.now(WARSAW).isoformat(timespec="seconds")
    row = state["sources"].get(key, {})
    was_alerted = bool(row.get("alerted", False))

    if count > 0:
        print(f"HEALTH OK | {label} | {count}")
        if was_alerted:
            if telegram(chat_env, f"✅ RADAR WRÓCIŁ DO DZIAŁANIA\n{label}\nPonownie odczytano {count} ofert/kart."):
                row["alerted"] = False
                row["recovered_at"] = now
        row.update({"zero_streak": 0, "last_count": count, "last_check": now, "last_ok": now})
    else:
        streak = int(row.get("zero_streak", 0)) + 1
        print(f"HEALTH ZERO | {label} | seria {streak}")
        row.update({"zero_streak": streak, "last_count": 0, "last_check": now})
        if streak >= FAIL_AFTER and not was_alerted:
            msg = (
                "⚠️ RADAR — PROBLEM TECHNICZNY\n"
                f"{label}\n"
                f"0 ofert/kart przez {streak} kolejne kontrole.\n"
                "Możliwa zmiana strony, blokada albo błąd parsera."
            )
            if telegram(chat_env, msg):
                row["alerted"] = True
                row["alerted_at"] = now

    state["sources"][key] = row


def check_housing(page, state):
    raw = os.environ.get("SEARCH_CONFIG_JSON", "").strip()
    if not raw:
        raise RuntimeError("Brak SEARCH_CONFIG_JSON dla monitora")
    cfg = json.loads(raw)
    totals = {}
    attempted = set()
    for search in cfg.get("searches", []):
        url = search.get("url", "")
        portal = housing.portal_from_url(url)
        if portal not in {"otodom", "olx", "gratka", "morizon"}:
            continue
        attempted.add(portal)
        totals.setdefault(portal, 0)
        try:
            totals[portal] += len(housing.get_cards(page, url))
        except Exception as exc:
            print(f"HEALTH błąd {portal}: {exc}", file=sys.stderr)
    labels = {
        "otodom": "Nieruchomości / Otodom",
        "olx": "Nieruchomości / OLX",
        "gratka": "Nieruchomości / Gratka",
        "morizon": "Nieruchomości / Morizon",
    }
    for portal in sorted(attempted):
        update_health(state, f"housing:{portal}", labels[portal], totals.get(portal, 0), "TELEGRAM_CHAT_ID")


def check_olx(page, state):
    total = 0
    for _, slug in olx_deals.REGIONS.items():
        for search in olx_deals.SEARCHES[:2]:
            try:
                page.goto(olx_deals.make_url(slug, search["query"]), wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(1500)
                total += page.locator('a[href*="/d/oferta/"]').count()
            except Exception as exc:
                print(f"HEALTH błąd OLX okazje: {exc}", file=sys.stderr)
    update_health(state, "deals:olx", "Radar okazji / OLX", total, "OLX_TELEGRAM_CHAT_ID")


def check_poland(page, state):
    count = 0
    try:
        page.goto(poland_deals.URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        count = len(poland_deals.extract_cards(page))
    except Exception as exc:
        print(f"HEALTH błąd Travelist: {exc}", file=sys.stderr)
    update_health(state, "poland:travelist", "Polska / Travelist", count, "VACATION_TELEGRAM_CHAT_ID")


def check_vacation(page, state):
    for source, airport, url, party_marker in vacation.SOURCES:
        count = 0
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1800)
            visible, _ = vacation.page_text(page)
            if party_marker.lower() in visible.lower():
                count = len(vacation.cards(page, source, airport))
        except Exception as exc:
            print(f"HEALTH błąd {source} {airport}: {exc}", file=sys.stderr)
        update_health(
            state,
            f"vacation:{source}:{airport}",
            f"Wakacje / {source} / {airport}",
            count,
            "VACATION_TELEGRAM_CHAT_ID",
        )


def run():
    state = load_state()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 1400},
            locale="pl-PL",
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
        )
        page = ctx.new_page()
        check_housing(page, state)
        check_olx(page, state)
        check_poland(page, state)
        check_vacation(page, state)
        ctx.close()
        browser.close()
    if not DRY_RUN:
        save_state(state)
    print("Monitor techniczny zakończony.")


if __name__ == "__main__":
    run()
