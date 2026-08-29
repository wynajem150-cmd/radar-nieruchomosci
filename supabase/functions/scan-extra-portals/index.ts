type SourceConfig = {
  pages: Record<string, string>;
  linkPattern: RegExp;
  baseHost: string;
};

const configs: Record<string, SourceConfig> = {
  olx: {
    pages: {
      "śląskie": "https://www.olx.pl/nieruchomosci/mieszkania/sprzedaz/slaskie/",
      "opolskie": "https://www.olx.pl/nieruchomosci/mieszkania/sprzedaz/opolskie/",
    },
    linkPattern: /\/d\/oferta\//i,
    baseHost: "olx.pl",
  },
  otodom: {
    pages: {
      "śląskie": "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie/slaskie",
      "opolskie": "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie/opolskie",
    },
    linkPattern: /\/pl\/oferta\//i,
    baseHost: "otodom.pl",
  },
  gratka: {
    pages: {
      "śląskie": "https://gratka.pl/nieruchomosci/mieszkania/slaskie",
      "opolskie": "https://gratka.pl/nieruchomosci/mieszkania/opolskie",
    },
    linkPattern: /\/nieruchomosci\/mieszkanie[^"'?#\s]*\/(?:ob\/)?[a-z0-9-]{5,}/i,
    baseHost: "gratka.pl",
  },
  morizon: {
    pages: {
      "śląskie": "https://www.morizon.pl/mieszkania/slaskie/",
      "opolskie": "https://www.morizon.pl/mieszkania/opolskie/",
    },
    linkPattern: /\/oferta\/sprzedaz-mieszkanie-/i,
    baseHost: "morizon.pl",
  },
  lento: {
    pages: {
      "śląskie": "https://slaskie.lento.pl/nieruchomosci/mieszkania/sprzedaz.html",
      "opolskie": "https://opolskie.lento.pl/nieruchomosci/mieszkania/sprzedaz.html",
    },
    linkPattern: /\/[a-z0-9ąćęłńóśźż_-]+,[0-9]+\.html/i,
    baseHost: "lento.pl",
  },
  "e-licytacje": {
    pages: {
      "śląskie": "https://licytacje.komornik.pl/wyszukiwarka-licytacji?mainCategory=REAL_ESTATE&province=%C5%9Bl%C4%85skie",
      "opolskie": "https://licytacje.komornik.pl/wyszukiwarka-licytacji?mainCategory=REAL_ESTATE&province=opolskie",
    },
    linkPattern: /\/licytacje\/[0-9]+\//i,
    baseHost: "licytacje.komornik.pl",
  },
  krz: {
    pages: {
      "śląskie": "https://krz.ms.gov.pl/#!/application/KRZPortalPUB/1.4/KrzSearchPortalPublic",
      "opolskie": "https://krz.ms.gov.pl/#!/application/KRZPortalPUB/1.4/KrzSearchPortalPublic",
    },
    linkPattern: /\/KrzSearchPortalPublic/i,
    baseHost: "krz.ms.gov.pl",
  },
};

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json; charset=utf-8" } });

const plain = (html: string) => html
  .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
  .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ")
  .replace(/&nbsp;|&#160;/gi, " ")
  .replace(/&sup2;|&#178;/gi, "²")
  .replace(/&quot;|&#34;/gi, '"')
  .replace(/&amp;/gi, "&")
  .replace(/&#39;|&apos;/gi, "'")
  .replace(/<[^>]+>/g, " ")
  .replace(/\s+/g, " ")
  .trim();

const numberValue = (value?: string | null) => {
  if (!value) return null;
  const normalized = value.replace(/[\s\u00a0]/g, "").replace(",", ".");
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
};

const decodeUnicode = (value: string) =>
  value.replace(/\\u([0-9a-f]{4})/gi, (_match, hex) => String.fromCharCode(Number.parseInt(hex, 16)));

const meta = (html: string, property: string) => {
  const escaped = property.replace(/[.*+?^$()|[\]\\]/g, "\\$&");
  return html.match(new RegExp(`<meta[^>]+(?:property|name)=["']${escaped}["'][^>]+content=["']([^"']+)["']`, "i"))?.[1]
    || html.match(new RegExp(`<meta[^>]+content=["']([^"']+)["'][^>]+(?:property|name)=["']${escaped}["']`, "i"))?.[1]
    || null;
};

function offerLinks(html: string, base: string, config: SourceConfig) {
  const result: string[] = [];
  const regex = /href=["']([^"'#]+)["']/gi;
  let match;
  while ((match = regex.exec(html))) {
    try {
      const url = new URL(match[1], base);
      if (!url.hostname.endsWith(config.baseHost)) continue;
      if (!config.linkPattern.test(url.pathname + url.search)) continue;
      url.hash = "";
      const normalized = url.toString();
      if (!result.includes(normalized)) result.push(normalized);
    } catch {}
  }
  return result;
}

function auctionTargets(html: string, base: string) {
  const result: Array<{ url: string; html: string }> = [];
  const regex = /<a\b[^>]*href=["']([^"']*\/licytacje\/[0-9]+\/[^"']*)["'][^>]*>([\s\S]*?)<\/a>/gi;
  let match;
  while ((match = regex.exec(html))) {
    try {
      const url = new URL(match[1], base);
      const cardText = plain(match[2]);
      if (!/(mieszkania|lokal mieszkal|spółdzielcze.{0,40}lokal)/i.test(cardText)) continue;
      if (!result.some((item) => item.url === url.toString())) {
        result.push({ url: url.toString(), html: match[2] });
      }
    } catch {}
  }
  return result;
}

function idFromUrl(url: string) {
  let hash = 2166136261;
  for (const char of url) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash >>> 0).toString(36);
}

function parseDetail(html: string, url: string, source: string, region: string) {
  const text = plain(html);
  const title = (meta(html, "og:title")
    || html.match(/<h1[^>]*>([\s\S]{1,500}?)<\/h1>/i)?.[1]
    || text.match(/(?:Mieszkanie|Lokal mieszkalny|nieruchomość)[^|]{0,240}/i)?.[0]
    || `Oferta ${source}`).replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 500);

  const plausiblePrice = (raw?: string | null) => {
    const value = numberValue(raw);
    const minimum = source === "e-licytacje" ? 1000 : 20000;
    return value != null && value >= minimum && value <= 10000000 ? Math.round(value) : null;
  };
  const jsonPrice = html.match(/"price"\s*:\s*"?([0-9]{2,12}(?:[.,][0-9]{1,2})?)/i)?.[1];
  const auctionPrice = text.match(/Cena wywołania\s*[:\-]?\s*([0-9 .\u00a0]{2,15}(?:,[0-9]{2})?)\s*zł/i)?.[1];
  const textPrices = Array.from(text.matchAll(/([0-9][0-9 .\u00a0]{3,12})\s*zł/gi))
    .map((match) => plausiblePrice(match[1]));
  const price = plausiblePrice(jsonPrice)
    ?? plausiblePrice(auctionPrice)
    ?? textPrices.find((value) => value != null)
    ?? null;

  const jsonArea = html.match(/"(?:usableArea|floorSize|area)"\s*:\s*(?:\{[^}]{0,200}"value"\s*:\s*)?"?([0-9]{1,3}(?:[.,][0-9]{1,2})?)/i)?.[1];
  const areaText = text.match(/(?:powierzchni(?:a)?|metraż|pow\.)\s*(?:całkowitej|użytkowej)?\s*[:\-]?\s*([0-9]{1,3}(?:[.,][0-9]{1,2})?)\s*(?:m²|m2)/i)?.[1]
    || text.match(/([0-9]{1,3}(?:[.,][0-9]{1,2})?)\s*(?:m²|m2)/i)?.[1];
  const area = numberValue(jsonArea || areaText);

  const jsonRooms = html.match(/"(?:numberOfRooms|roomsNumber|rooms)"\s*:\s*"?([1-9])/i)?.[1];
  const roomsText = text.match(/([1-9])\s*(?:pok(?:ój|oje|oi)?|pokoje)/i)?.[1]
    || text.match(/(?:liczba|ilość) pokoi\s*[:\-]?\s*([1-9])/i)?.[1];
  const rooms = Number(jsonRooms || roomsText || 0) || null;

  const cityJson = html.match(/"addressLocality"\s*:\s*"([^"]{2,100})"/i)?.[1]
    || html.match(/"city"\s*:\s*\{[^}]{0,300}"name"\s*:\s*"([^"]{2,100})"/i)?.[1];
  const postalCity = text.match(/\b\d{2}-\d{3}\s+([A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż -]{2,60})/)?.[1];
  const rawCity = cityJson || postalCity || "nieustalona";
  const city = decodeUnicode(rawCity).replace(/\s+/g, " ").trim().slice(0, 100);

  const phone = text.match(/(?:(?:\+|00)48[\s-]?)?(\d{3}[\s-]?\d{3}[\s-]?\d{3})/)?.[1]?.replace(/\D/g, "") || null;
  const email = text.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i)?.[0]?.toLowerCase() || null;
  const floor = text.match(/Piętro\s*[:\-]?\s*([^,;|]{1,20})/i)?.[1]?.trim() || null;
  const sellerType = /bez pośrednik|prywatn|ogłoszenie prywatne/i.test(text) ? "private" : "agent";
  const priceM2 = price && area ? Math.round((price / area) * 100) / 100 : null;

  return {
    source,
    source_offer_id: idFromUrl(url),
    url,
    city,
    voivodeship: region,
    title,
    price,
    area,
    rooms,
    price_m2: priceM2,
    floor_text: floor ? `Piętro: ${floor}` : null,
    description: text.slice(0, 5000),
    contact_phone: phone,
    contact_email: email,
    seller_type: source === "e-licytacje" ? "komornik" : sellerType,
    last_seen_at: new Date().toISOString(),
  };
}

async function request(url: string) {
  const response = await fetch(url, {
    headers: {
      "user-agent": "RadarOkazji/0.3 public-listing-monitor",
      "accept-language": "pl-PL,pl;q=0.9",
      accept: "text/html,application/xhtml+xml",
    },
    redirect: "follow",
  });
  return { status: response.status, url: response.url, html: await response.text() };
}

async function dbFetch(path: string, serviceKey: string, init: RequestInit = {}) {
  const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
  return fetch(`${supabaseUrl}/rest/v1/${path}`, {
    ...init,
    headers: {
      apikey: serviceKey,
      authorization: `Bearer ${serviceKey}`,
      "content-type": "application/json",
      ...(init.headers || {}),
    },
  });
}

Deno.serve(async (req) => {
  try {
    if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);
    const body = await req.json();
    const source = String(body?.source || "");
    const region = String(body?.region || "");
    const config = configs[source];
    if (!config || !config.pages[region]) return json({ error: "bad_source_or_region" }, 400);

    const secretKeys = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") || "{}");
    const serviceKey = secretKeys.default || Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
    if (!serviceKey) throw new Error("missing_service_role_key");

    const healthPath = "source_health?select=last_scan_at&source=eq." + encodeURIComponent(source)
      + "&city=eq." + encodeURIComponent("woj. " + region)
      + "&order=last_scan_at.desc&limit=1";
    const healthResponse = await dbFetch(healthPath, serviceKey);
    if (healthResponse.ok) {
      const healthRows = await healthResponse.json();
      if (healthRows?.[0]?.last_scan_at
        && Date.now() - new Date(healthRows[0].last_scan_at).getTime() < 45 * 60 * 1000) {
        return json({ ok: true, source, region, throttled: true });
      }
    }

    let httpStatus: number | null = null;
    let found = 0;
    let parsed = 0;
    let contacts = 0;
    let sample: string | null = null;
    let lastError: string | null = null;

    try {
      const listing = await request(config.pages[region]);
      httpStatus = listing.status;
      if (listing.status !== 200) throw new Error(`HTTP ${listing.status} ${config.pages[region]}`);

      if (source === "krz") {
        lastError = "KRZ wymaga oficjalnego dostępu do danych lub eksportu; publiczna aplikacja nie udostępnia listy w HTML.";
      } else {
        const targets = source === "e-licytacje"
          ? auctionTargets(listing.html, listing.url).slice(0, 15)
          : offerLinks(listing.html, listing.url, config).slice(0, 15).map((url) => ({ url, html: "" }));
        found = targets.length;
        for (const target of targets) {
          const url = target.url;
          try {
            let detailHtml = target.html;
            let detailUrl = url;
            if (!detailHtml) {
              const detail = await request(url);
              if (detail.status !== 200) continue;
              detailHtml = detail.html;
              detailUrl = detail.url;
            }
            const offer = parseDetail(detailHtml, detailUrl, source, region);
            if (offer.price == null && offer.area == null) continue;
            const upsert = await dbFetch(
              "source_candidates?on_conflict=source,source_offer_id",
              serviceKey,
              {
                method: "POST",
                headers: { Prefer: "resolution=merge-duplicates,return=minimal" },
                body: JSON.stringify(offer),
              },
            );
            if (!upsert.ok) throw new Error(`upsert ${upsert.status}: ${(await upsert.text()).slice(0, 300)}`);
            parsed++;
            if (offer.contact_phone || offer.contact_email) contacts++;
            sample ||= url;
          } catch (error) {
            console.error(source, region, url, error);
          }
        }

        const rpc = await dbFetch("rpc/recompute_flip_analysis", serviceKey, { method: "POST", body: "{}" });
        if (!rpc.ok) throw new Error(`analysis ${rpc.status}: ${(await rpc.text()).slice(0, 300)}`);
      }
    } catch (error) {
      lastError = String(error).slice(0, 1000);
    }

    const status = source === "krz"
      ? "requires_official_access"
      : lastError
      ? "error"
      : parsed > 0
      ? "ok"
      : "no_offers";

    await dbFetch(
      "source_health?on_conflict=source,city",
      serviceKey,
      {
        method: "POST",
        headers: { Prefer: "resolution=merge-duplicates,return=minimal" },
        body: JSON.stringify({
          source,
          city: `woj. ${region}`,
          status,
          http_status: httpStatus,
          offers_found: found,
          contacts_found: contacts,
          last_scan_at: new Date().toISOString(),
          last_error: lastError,
          sample_url: sample,
        }),
      },
    );

    return json({ ok: !lastError, source, region, status, found, parsed, contacts, httpStatus, lastError });
  } catch (error) {
    console.error(error);
    return json({ error: "internal_error" }, 500);
  }
});
