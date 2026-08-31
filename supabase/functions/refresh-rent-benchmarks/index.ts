import { createClient } from "npm:@supabase/supabase-js@2";

type RentOffer = { city: string; voivodeship: string; price: number; area: number; rent_m2: number; url: string };

const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), {
  status,
  headers: { "content-type": "application/json; charset=utf-8" },
});

const decode = (value: string) => value.replace(/&amp;/gi, "&").replace(/&quot;/gi, '"').replace(/&#39;/gi, "'");
const plain = (html: string) => html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
  .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();

function median(values: number[]) {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

async function request(url: string) {
  const response = await fetch(url, {
    headers: {
      "user-agent": "RadarOkazji/0.6 rent-benchmark",
      "accept-language": "pl-PL,pl;q=0.9",
      accept: "text/html,application/xhtml+xml",
    },
    redirect: "follow",
  });
  return { status: response.status, url: response.url, html: await response.text() };
}

function detailLinks(html: string, base: string) {
  const result: string[] = [];
  const regex = /<a\b[^>]*href=["']([^"'#]+)["'][^>]*>/gi;
  let match;
  while ((match = regex.exec(html))) {
    try {
      const url = new URL(decode(match[1]), base);
      url.hash = "";
      if (url.hostname.endsWith("sprzedajemy.pl") && /-nr\d+$/i.test(url.pathname) && !result.includes(url.toString())) result.push(url.toString());
    } catch {}
  }
  return result;
}

async function scanRegion(region: string): Promise<{ status: number; links: number; offers: RentOffer[] }> {
  const slug = region === "śląskie" ? "slaskie" : "opolskie";
  const links: string[] = [];
  let status = 0;
  for (const suffix of ["", "?offset=30"]) {
    const page = await request(`https://sprzedajemy.pl/${slug}/nieruchomosci/mieszkania/wynajem${suffix}`);
    status = page.status;
    if (page.status !== 200) continue;
    for (const link of detailLinks(page.html, page.url)) if (!links.includes(link)) links.push(link);
  }
  const offers: RentOffer[] = [];
  for (let index = 0; index < Math.min(links.length, 50); index += 5) {
    const batch = await Promise.all(links.slice(index, index + 5).map(async (url) => {
      try {
        const detail = await request(url);
        if (detail.status !== 200) return null;
        const match = detail.html.match(/SPR\.OfferJSON\s*=\s*(\{[^\n]+\})\s*;?/);
        if (!match) return null;
        const data = JSON.parse(match[1]);
        const raw = data.goOfferProperties || data.offer || {};
        const attrs = raw.customAttrIdValPairs || {};
        const keywords = Array.isArray(data.keywords) ? data.keywords : [];
        const city = String(keywords[4] || keywords.at(-1) || "").trim();
        const price = Number(raw.priceAsNumber ?? raw.price);
        const area = Number(attrs["143"]);
        const rentM2 = price / area;
        if (!city || !Number.isFinite(price) || price < 500 || price > 15000 || !Number.isFinite(area) || area < 15 || area > 150 || rentM2 < 10 || rentM2 > 250) return null;
        return { city, voivodeship: region, price: Math.round(price), area, rent_m2: Math.round(rentM2 * 100) / 100, url: detail.url } satisfies RentOffer;
      } catch {
        return null;
      }
    }));
    offers.push(...batch.filter((offer): offer is RentOffer => offer !== null));
  }
  return { status, links: links.length, offers };
}

Deno.serve(async (req) => {
  try {
    if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const secretKeys = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") || "{}");
    const serviceKey = secretKeys.default || Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
    if (!serviceKey) throw new Error("missing_service_role_key");
    const db = createClient(supabaseUrl, serviceKey, { auth: { persistSession: false } });

    const regions = await Promise.all(["śląskie", "opolskie"].map(scanRegion));
    const offers = regions.flatMap((region) => region.offers);
    const grouped = new Map<string, RentOffer[]>();
    for (const offer of offers) {
      const key = `${offer.voivodeship}:${offer.city.toLowerCase()}`;
      grouped.set(key, [...(grouped.get(key) || []), offer]);
    }
    const saved: Array<{ city: string; voivodeship: string; sample_count: number }> = [];
    for (const cityOffers of grouped.values()) {
      if (cityOffers.length < 3) continue;
      const first = cityOffers[0];
      const row = {
        city_key: first.city.toLowerCase(),
        city: first.city,
        voivodeship: first.voivodeship,
        median_rent_m2: Math.round(median(cityOffers.map((offer) => offer.rent_m2)) * 100) / 100,
        median_monthly_rent: Math.round(median(cityOffers.map((offer) => offer.price))),
        sample_count: cityOffers.length,
        sample_offers: cityOffers.slice(0, 5).map(({ city: _city, voivodeship: _voivodeship, ...offer }) => offer),
        source_name: "Sprzedajemy.pl — oferty najmu",
        source_url: "https://sprzedajemy.pl/nieruchomosci/mieszkania/wynajem",
        fetched_at: new Date().toISOString(),
      };
      const { error } = await db.from("rent_market_stats").upsert(row, { onConflict: "city_key,voivodeship" });
      if (error) throw error;
      saved.push({ city: first.city, voivodeship: first.voivodeship, sample_count: cityOffers.length });
    }
    return json({
      ok: true,
      found: offers.length,
      saved_cities: saved.length,
      saved,
      regions: regions.map((region, index) => ({ voivodeship: index === 0 ? "śląskie" : "opolskie", http_status: region.status, links: region.links, parsed: region.offers.length })),
    });
  } catch (error) {
    console.error(error);
    const message = error instanceof Error ? error.message : JSON.stringify(error);
    return json({ error: message.slice(0, 500) }, 500);
  }
});
