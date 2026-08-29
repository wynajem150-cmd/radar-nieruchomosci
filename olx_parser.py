import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

PRICE_RE = re.compile(r"(?<!\d)(\d{2,3}(?:[ .\u00a0]\d{3})+|\d{4,7})(?:[,.]\d+)?\s*(?:zł|PLN)\b", re.I)
AREA_RE = re.compile(r"(?<!\d)(\d{2,3}(?:[,.]\d{1,2})?)\s*m(?:²|2)\b", re.I)
ROOMS_RE = re.compile(r"(?<!\d)([1-9])\s*(?:pok(?:oje|ój)?|pokoje|pok\.)\b", re.I)
FLOOR_RE = re.compile(r"pi[eę]tro\s*[:\-]?\s*([^|,;\n]{1,30})", re.I)
ID_RE = re.compile(r"-ID([A-Za-z0-9]+)\.html", re.I)


def _num(value):
    if value is None:
        return None
    text = str(value).replace("\u00a0", " ").replace(" ", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def normalize_url(href):
    url = urljoin("https://www.olx.pl", href)
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}{p.path}"


def offer_id(url):
    match = ID_RE.search(url)
    if match:
        return match.group(1)
    return re.sub(r"\W+", "_", urlparse(url).path).strip("_")[-180:]


def parse_core(text):
    clean = " ".join((text or "").split())
    p, a, r = PRICE_RE.search(clean), AREA_RE.search(clean), ROOMS_RE.search(clean)
    price = _num(p.group(1)) if p else None
    area = _num(a.group(1)) if a else None
    rooms = int(r.group(1)) if r else None
    ppm = price / area if price and area and area > 0 else None
    return price, area, rooms, ppm


def listing_links(html):
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if "/d/oferta/" not in href:
            continue
        url = normalize_url(href)
        if url in seen:
            continue
        seen.add(url)
        card = link
        for _ in range(5):
            if card.parent is None:
                break
            card = card.parent
            if card.get("data-cy") == "l-card":
                break
        text = " ".join(card.get_text(" ", strip=True).split())
        title = " ".join(link.get_text(" ", strip=True).split()) or text[:180]
        out.append((url, title, text))
    return out


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def parse_offer(html, url, fallback_title="", fallback_text=""):
    soup = BeautifulSoup(html, "html.parser")
    page_text = " ".join(soup.get_text(" ", strip=True).split())
    h1 = soup.find("h1")
    title = " ".join(h1.get_text(" ", strip=True).split()) if h1 else fallback_title
    price, area, rooms, ppm = parse_core(f"{fallback_text} {title} {page_text[:10000]}")
    description = ""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        description = str(meta.get("content"))

    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or tag.get_text())
        except Exception:
            continue
        roots = data if isinstance(data, list) else [data]
        for root in roots:
            for node in _walk(root):
                offers = node.get("offers")
                if price is None and isinstance(offers, dict) and offers.get("price") is not None:
                    try:
                        price = float(offers.get("price"))
                    except (TypeError, ValueError):
                        pass
                fs = node.get("floorSize")
                if area is None and isinstance(fs, dict) and fs.get("value") is not None:
                    try:
                        area = float(fs.get("value"))
                    except (TypeError, ValueError):
                        pass
                if rooms is None and node.get("numberOfRooms") is not None:
                    try:
                        rooms = int(float(node.get("numberOfRooms")))
                    except (TypeError, ValueError):
                        pass
                if not description and node.get("description"):
                    description = str(node.get("description"))

    if price is not None and area is not None and area > 0:
        ppm = price / area
    floor = FLOOR_RE.search(page_text)
    return {
        "source_offer_id": offer_id(url),
        "title": (title or "Oferta mieszkania")[:500],
        "url": normalize_url(url),
        "price": round(price) if price is not None else None,
        "area": round(area, 2) if area is not None else None,
        "rooms": rooms,
        "price_m2": round(ppm, 2) if ppm is not None else None,
        "floor_text": f"Piętro: {floor.group(1).strip()}" if floor else None,
        "description": description[:4000],
    }
