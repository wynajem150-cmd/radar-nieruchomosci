import { createClient } from "npm:@supabase/supabase-js@2";

type Offer = {
  source: string;
  source_offer_id: string;
  url: string;
  city: string;
  voivodeship: string;
  title: string;
  price: number | null;
  area: number | null;
  rooms: number | null;
  price_m2: number | null;
  floor_text: string | null;
  description: string;
  contact_phone: string | null;
  contact_email: string | null;
  seller_type: string;
  last_seen_at: string;
};

const allowed = new Set([
  "sprzedajemy",
  "pkp-nieruchomosci",
  "amw",
  "zgm-gliwice",
  "bip-opole",
  "bip-katowice",
  "bip-kedzierzyn-kozle",
]);

const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), {
  status,
  headers: { "content-type": "application/json; charset=utf-8" },
});

const decode = (value: string) => value
  .replace(/&nbsp;|&#160;/gi, " ")
  .replace(/&sup2;|&#178;/gi, "²")
  .replace(/&quot;|&#34;/gi, '"')
  .replace(/&#39;|&apos;/gi, "'")
  .replace(/&amp;/gi, "&");

const plain = (html: string) => decode(html)
  .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
  .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ")
  .replace(/<[^>]+>/g, " ")
  .replace(/\s+/g, " ")
  .trim();

const numberValue = (value?: string | null) => {
  if (!value) return null;
  const compact = value.replace(/[\s\u00a0]/g, "");
  const normalized = compact.includes(",")
    ? compact.replace(/\./g, "").replace(",", ".")
    : (compact.match(/\./g)?.length === 1 && /\.\d{1,2}$/.test(compact)
      ? compact
      : compact.replace(/\./g, ""));
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
};

const decimalValue = (value?: string | null) => {
  if (!value) return null;
  const parsed = Number(value.replace(/[\s\u00a0]/g, "").replace(",", "."));
  return Number.isFinite(parsed) ? parsed : null;
};

const meta = (html: string, property: string) => {
  const escaped = property.replace(/[.*+?^$()|[\]\\]/g, "\\$&");
  return decode(html.match(new RegExp(`<meta[^>]+(?:property|name)=["']${escaped}["'][^>]+content=["']([^"']+)["']`, "i"))?.[1]
    || html.match(new RegExp(`<meta[^>]+content=["']([^"']+)["'][^>]+(?:property|name)=["']${escaped}["']`, "i"))?.[1]
    || "");
};

function idFromUrl(url: string) {
  let hash = 2166136261;
  for (const char of url) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash >>> 0).toString(36);
}

async function request(url: string) {
  const response = await fetch(url, {
    headers: {
      "user-agent": "RadarOkazji/0.5 public-listing-monitor",
      "accept-language": "pl-PL,pl;q=0.9",
      accept: "text/html,application/xhtml+xml",
    },
    redirect: "follow",
  });
  return { status: response.status, url: response.url, html: await response.text() };
}

function links(html: string, base: string, accept: (url: URL, text: string) => boolean) {
  const result: Array<{ url: string; text: string }> = [];
  const regex = /<a\b[^>]*href=["']([^"'#]+)["'][^>]*>([\s\S]*?)<\/a>/gi;
  let match;
  while ((match = regex.exec(html))) {
    try {
      const url = new URL(decode(match[1]), base);
      url.hash = "";
      const text = plain(match[2]);
      if (!accept(url, text)) continue;
      if (!result.some((item) => item.url === url.toString())) result.push({ url: url.toString(), text });
    } catch {}
  }
  return result;
}

function phone(text: string) {
  return text.match(/(?:(?:\+|00)48[\s-]?)?(\d{3}[\s-]?\d{3}[\s-]?\d{3})/)?.[1]?.replace(/\D/g, "") || null;
}

function standardOffer(source: string, url: string, html: string, region: string, fixedCity?: string, titleHint?: string): Offer | null {
  const text = plain(html);
  const title = (titleHint || meta(html, "og:title") || html.match(/<h1[^>]*>([\s\S]{1,500}?)<\/h1>/i)?.[1] || `Oferta ${source}`)
    .replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 500);
  const priceText = text.match(/(?:cena(?:\s+wywoławcza)?|wartość)\s*[:\-]?\s*([0-9][0-9 .\u00a0]{3,14}(?:,[0-9]{2})?)\s*zł/i)?.[1]
    || text.match(/([0-9][0-9 .\u00a0]{4,14})\s*zł/i)?.[1];
  const areaText = text.match(/(?:powierzchni(?:a)?(?:\s+użytkowa)?|pow\.)\s*[:\-]?\s*([0-9]{1,3}(?:[,.][0-9]{1,2})?)\s*(?:m²|m2)/i)?.[1]
    || text.match(/Pow\.\s*budynku\s*\/\s*działki\s*\[m2\]\s*([0-9]{1,4}(?:[,.][0-9]{1,2})?)/i)?.[1]
    || text.match(/([0-9]{1,3}(?:[,.][0-9]{1,2})?)\s*(?:m²|m2)/i)?.[1];
  const roomsText = text.match(/(?:liczba|ilość)\s+(?:pokoi|izb)\s*[:\-]?\s*([1-9])/i)?.[1]
    || text.match(/([1-9])\s*(?:pok(?:ój|oje|oi)?)/i)?.[1];
  const city = fixedCity || text.match(/(?:Miejscowość|Gmina|Miasto)\s*[:\-]\s*([A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż -]{2,60})/i)?.[1]?.trim() || "nieustalona";
  const price = Math.round(numberValue(priceText) || 0) || null;
  const area = decimalValue(areaText);
  const floor = text.match(/Piętro\s*[:\-]?\s*([^,;|]{1,20})/i)?.[1]?.trim() || null;
  if (price == null && area == null) return null;
  return {
    source,
    source_offer_id: idFromUrl(url),
    url,
    city: city.slice(0, 100),
    voivodeship: region,
    title,
    price,
    area,
    rooms: roomsText ? Number(roomsText) : null,
    price_m2: price && area ? Math.round((price / area) * 100) / 100 : null,
    floor_text: floor ? `Piętro: ${floor}` : null,
    description: text.slice(0, 5000),
    contact_phone: phone(text),
    contact_email: text.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i)?.[0]?.toLowerCase() || null,
    seller_type: source.startsWith("bip-") || source === "zgm-gliwice" || source === "pkp-nieruchomosci" || source === "amw" ? "przetarg publiczny" : "unknown",
    last_seen_at: new Date().toISOString(),
  };
}

async function mapLimit<T, R>(items: T[], limit: number, fn: (item: T) => Promise<R>) {
  const result: R[] = [];
  for (let index = 0; index < items.length; index += limit) {
    result.push(...await Promise.all(items.slice(index, index + limit).map(fn)));
  }
  return result;
}

async function scanSprzedajemy(region: string) {
  const slug = region === "śląskie" ? "slaskie" : "opolskie";
  const pages = [
    `https://sprzedajemy.pl/${slug}/nieruchomosci/mieszkania/sprzedaz`,
    `https://sprzedajemy.pl/${slug}/nieruchomosci/mieszkania/sprzedaz?offset=30`,
  ];
  const targets: Array<{ url: string; text: string }> = [];
  let httpStatus = 0;
  for (const page of pages) {
    const listing = await request(page);
    httpStatus = listing.status;
    if (!listing.status.toString().startsWith("2")) continue;
    for (const item of links(listing.html, listing.url, (url) => url.hostname.endsWith("sprzedajemy.pl") && /-nr\d+$/i.test(url.pathname))) {
      if (!targets.some((target) => target.url === item.url)) targets.push(item);
    }
  }
  const parsed = await mapLimit(targets.slice(0, 40), 5, async (target) => {
    try {
      const detail = await request(target.url);
      if (detail.status !== 200) return null;
      const match = detail.html.match(/SPR\.OfferJSON\s*=\s*(\{[^\n]+\})\s*;?/);
      if (!match) return standardOffer("sprzedajemy", detail.url, detail.html, region, undefined, target.text);
      const data = JSON.parse(match[1]);
      const raw = data.goOfferProperties || data.offer || {};
      const attributes = raw.customAttrIdValPairs || {};
      const keywords = Array.isArray(data.keywords) ? data.keywords : [];
      const city = String(keywords[4] || keywords.at(-1) || "nieustalona");
      const price = Number(raw.priceAsNumber ?? raw.price) || null;
      const area = Number(attributes["143"]) || null;
      const description = meta(detail.html, "description") || plain(detail.html).slice(0, 5000);
      return {
        source: "sprzedajemy",
        source_offer_id: detail.url.match(/-nr(\d+)/)?.[1] || idFromUrl(detail.url),
        url: detail.url,
        city,
        voivodeship: region,
        title: String(raw.title || target.text || "Oferta Sprzedajemy.pl").slice(0, 500),
        price: price ? Math.round(price) : null,
        area,
        rooms: Number(attributes["145"]) || null,
        price_m2: price && area ? Math.round((price / area) * 100) / 100 : null,
        floor_text: null,
        description: description.slice(0, 5000),
        contact_phone: null,
        contact_email: null,
        seller_type: data.accountType === "personal" ? "private" : "agent",
        last_seen_at: new Date().toISOString(),
      } satisfies Offer;
    } catch {
      return null;
    }
  });
  return { httpStatus, found: targets.length, offers: parsed.filter((offer): offer is Offer => offer !== null) };
}

async function scanPkp(region: string) {
  const woj = region === "śląskie" ? "12" : "8";
  const page = `https://www.pkp.pl/pl/nieruchomosci-przetargi/?option=com_aukcje2&menu=2&pkp=&result=show&status=&servitude=0&catg=&woj=${woj}&city=&page_size=50`;
  const listing = await request(page);
  if (listing.status !== 200) return { httpStatus: listing.status, found: 0, offers: [] as Offer[] };
  const cards = [...listing.html.matchAll(/<div class="result">([\s\S]*?)<\/div>/gi)].map((match) => match[1]);
  const candidates = cards.map((card) => {
    const href = card.match(/href=["']([^"']*show=\d+)["']/i)?.[1];
    const text = plain(card);
    if (!href || !/Kategoria:\s*Sprzedaż/i.test(text) || !/(lokal mieszkalny|mieszkanie)/i.test(text) || /(działk|grunt|garaż|miejsce postojowe)/i.test(text)) return null;
    return { url: new URL(decode(href), listing.url).toString(), text };
  }).filter((item): item is { url: string; text: string } => item !== null);
  const offers = await mapLimit(candidates.slice(0, 25), 5, async (candidate) => {
    const detail = await request(candidate.url);
    if (detail.status !== 200) return null;
    const combined = `${candidate.text} ${detail.html}`;
    const text = plain(combined);
    const actualRegion = text.match(/Województwo:\s*([A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż-]+)\s+Miejscowość:/i)?.[1]?.trim().toLowerCase();
    if (actualRegion !== region) return null;
    const fixedCity = text.match(/Miejscowość:\s*([A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż -]+?)\s+Status:/i)?.[1]?.trim();
    const title = text.match(/Nazwa:\s*(.+?)\s+Data ogłoszenia/i)?.[1]?.trim();
    return standardOffer("pkp-nieruchomosci", detail.url, combined, region, fixedCity, title);
  });
  return { httpStatus: listing.status, found: candidates.length, offers: offers.filter((offer): offer is Offer => offer !== null) };
}

async function scanAmw(region: string) {
  const page = "https://amw.com.pl/pl/nieruchomosci/przetargi-nieruchomosci/wyniki-wyszukiwania/page,0,limit,30,surface_unit,ha,sort,date_asc";
  const listing = await request(page);
  if (listing.status !== 200) return { httpStatus: listing.status, found: 0, offers: [] as Offer[] };
  const targets = links(listing.html, listing.url, (url) => url.hostname.endsWith("amw.com.pl")
    && /\/pl\/nieruchomosci\/przetargi-nieruchomosci\/[a-z0-9-]+$/i.test(url.pathname));
  const parsed = await mapLimit(targets.slice(0, 30), 5, async (target) => {
    const detail = await request(target.url);
    if (detail.status !== 200) return null;
    const text = plain(detail.html);
    if (!new RegExp(`Woj\\.:\\s*${region}`, "i").test(text)) return null;
    if (!/(lokal mieszkalny|mieszkanie)/i.test(text) || /(miejsce postojowe|m\. postojowe|garaż)/i.test(text)) return null;
    const city = text.match(/(?:Gmina|Powiat)\s*:\s*([A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż -]+)/i)?.[1]?.trim();
    return standardOffer("amw", detail.url, detail.html, region, city, target.text);
  });
  return { httpStatus: listing.status, found: targets.length, offers: parsed.filter((offer): offer is Offer => offer !== null) };
}

async function scanZgmGliwice() {
  const page = "https://zgm-gliwice.pl/przetargi-lokale-mieszkalne/";
  const listing = await request(page);
  const offers: Offer[] = [];
  const regex = /<h4[^>]*>\s*<a href=["']([^"']+)["']>([\s\S]*?)<\/a><\/h4>\s*<p[^>]*>([\s\S]*?)<\/p>/gi;
  let match;
  while ((match = regex.exec(listing.html))) {
    const url = new URL(decode(match[1]), listing.url).toString();
    const title = plain(match[2]);
    const summary = plain(match[3]);
    const area = decimalValue(summary.match(/([0-9]{1,3}(?:[,.][0-9]{1,2})?)\s*m2/i)?.[1]);
    const price = Math.round(numberValue(summary.match(/([0-9][0-9 .]{3,14}(?:,[0-9]{2})?)\s*zł/i)?.[1]) || 0) || null;
    offers.push({
      source: "zgm-gliwice", source_offer_id: idFromUrl(url), url, city: "Gliwice", voivodeship: "śląskie",
      title, price, area, rooms: null, price_m2: price && area ? Math.round((price / area) * 100) / 100 : null,
      floor_text: null, description: `${title}. ${summary}. Przetarg na lokal mieszkalny ZGM Gliwice.`,
      contact_phone: null, contact_email: null, seller_type: "przetarg publiczny", last_seen_at: new Date().toISOString(),
    });
  }
  return { httpStatus: listing.status, found: offers.length, offers };
}

async function scanBip(source: string, region: string) {
  const now = new Date();
  const month = now.getUTCMonth() + 1;
  const configs: Record<string, { page: string; city: string; accept: (url: URL, text: string) => boolean }> = {
    "bip-opole": {
      page: `https://www.bip.um.opole.pl/przetargi,9_${now.getUTCFullYear()}-${month}`,
      city: "Opole",
      accept: (url) => new RegExp(`/przetargi,9_${now.getUTCFullYear()}-${month}_\\d+$`).test(url.pathname),
    },
    "bip-katowice": {
      page: "https://bip.katowice.eu/ogloszenia/tablicaogloszen/default.aspx?menu=679",
      city: "Katowice",
      accept: (url, text) => /dokument\.aspx/i.test(url.pathname) && /(sprzedaż|zbycie|przetarg)/i.test(text) && /(lokal mieszkalny|mieszkania)/i.test(text),
    },
    "bip-kedzierzyn-kozle": {
      page: "https://bip.kedzierzynkozle.pl/artykuly/995/ogloszenia",
      city: "Kędzierzyn-Koźle",
      accept: (url, text) => /\/artykul\//i.test(url.pathname) && /(sprzedaż|zbycie|przetarg)/i.test(text) && /(lokal mieszkalny|mieszkania)/i.test(text),
    },
  };
  const config = configs[source];
  const listing = await request(config.page);
  if (listing.status !== 200) return { httpStatus: listing.status, found: 0, offers: [] as Offer[] };
  const targets = links(listing.html, listing.url, config.accept);
  const parsed = await mapLimit(targets.slice(0, 25), 5, async (target) => {
    const detail = await request(target.url);
    if (detail.status !== 200) return null;
    const text = plain(detail.html);
    if (!/(sprzedaż|zbycie|przetarg)/i.test(text) || !/(lokal mieszkalny|mieszkania)/i.test(text)) return null;
    return standardOffer(source, detail.url, detail.html, region, config.city, target.text);
  });
  return { httpStatus: listing.status, found: targets.length, offers: parsed.filter((offer): offer is Offer => offer !== null) };
}

Deno.serve(async (req) => {
  try {
    if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);
    const body = await req.json().catch(() => ({}));
    const source = String(body?.source || "").trim().toLowerCase();
    const region = String(body?.region || "").trim().toLowerCase();
    if (!allowed.has(source) || !["śląskie", "opolskie"].includes(region)) return json({ error: "bad_source_or_region" }, 400);

    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const secretKeys = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") || "{}");
    const serviceKey = secretKeys.default || Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
    if (!serviceKey) throw new Error("missing_service_role_key");
    const db = createClient(supabaseUrl, serviceKey, { auth: { persistSession: false } });
    const healthCity = source === "zgm-gliwice" ? "Gliwice"
      : source === "bip-opole" ? "Opole"
      : source === "bip-katowice" ? "Katowice"
      : source === "bip-kedzierzyn-kozle" ? "Kędzierzyn-Koźle"
      : `woj. ${region}`;
    const { data: health } = await db.from("source_health").select("last_scan_at")
      .eq("source", source).eq("city", healthCity).maybeSingle();
    if (health?.last_scan_at && Date.now() - new Date(health.last_scan_at).getTime() < 45 * 60 * 1000) {
      return json({ ok: true, source, region, throttled: true });
    }

    let scan;
    if (source === "sprzedajemy") scan = await scanSprzedajemy(region);
    else if (source === "pkp-nieruchomosci") scan = await scanPkp(region);
    else if (source === "amw") scan = await scanAmw(region);
    else if (source === "zgm-gliwice") scan = await scanZgmGliwice();
    else scan = await scanBip(source, region);

    let saved = 0;
    const errors: string[] = [];
    for (const offer of scan.offers) {
      if (!offer.price && !offer.area) continue;
      const { error } = await db.from("source_candidates").upsert(offer, { onConflict: "source,source_offer_id" });
      if (error) errors.push(error.message.slice(0, 250)); else saved++;
    }
    const status = errors.length ? "error" : saved > 0 ? "ok" : "no_offers";
    await db.from("source_health").upsert({
      source, city: healthCity, status, http_status: scan.httpStatus, offers_found: scan.found,
      contacts_found: scan.offers.filter((offer) => offer.contact_phone || offer.contact_email).length,
      last_scan_at: new Date().toISOString(), last_error: errors.length ? errors.join(" | ").slice(0, 1000) : null,
      sample_url: scan.offers[0]?.url || null,
    }, { onConflict: "source,city" });
    return json({ ok: errors.length === 0, source, region, status, found: scan.found, parsed: scan.offers.length, saved, errors: errors.slice(0, 5) });
  } catch (error) {
    console.error(error);
    return json({ error: String(error).slice(0, 500) }, 500);
  }
});
