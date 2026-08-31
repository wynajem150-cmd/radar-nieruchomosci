import { createClient } from "npm:@supabase/supabase-js@2";

const pages: Record<string, string[]> = {
  "śląskie": Array.from({ length: 6 }, (_, index) => `https://wgn.pl/sprzedaz/mieszkanie/slaskie/?page=${index + 1}`),
  "opolskie": Array.from({ length: 6 }, (_, index) => `https://wgn.pl/sprzedaz/mieszkanie/opolskie/?page=${index + 1}`),
};

const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), {
  status,
  headers: { "content-type": "application/json; charset=utf-8" },
});

function plain(html: string) {
  return html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ")
    .replace(/&nbsp;|&#160;/gi, " ").replace(/&sup2;|&#178;/gi, "²")
    .replace(/&amp;/gi, "&").replace(/&#39;|&apos;/gi, "'")
    .replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

function offerLinks(html: string, base: string) {
  const result: string[] = [];
  const regex = /href=["']([^"']+)["']/gi;
  let match;
  while ((match = regex.exec(html))) {
    try {
      const url = new URL(match[1], base);
      if (!url.hostname.endsWith("wgn.pl")) continue;
      if (!url.pathname.includes("/oferta/") || !/mieszkanie-na-sprzedaz/i.test(url.pathname)) continue;
      url.hash = "";
      if (!result.includes(url.toString())) result.push(url.toString());
    } catch {}
  }
  return result;
}

function numberValue(value?: string | null) {
  if (!value) return null;
  const parsed = Number(value.replace(/[\s\u00a0]/g, "").replace(",", "."));
  return Number.isFinite(parsed) ? parsed : null;
}

function phone(text: string) {
  const match = text.match(/(?:tel\.kom\.|tel\.|telefon)\s*[:\-]?\s*(?:\+48\s*)?(\d{3}[\s-]?\d{3}[\s-]?\d{3})/i)
    || text.match(/(?<!\d)(\d{3}[\s-]?\d{3}[\s-]?\d{3})(?!\d)/);
  return match ? match[1].replace(/\D/g, "") : null;
}

async function request(url: string) {
  const response = await fetch(url, {
    headers: {
      "user-agent": "RadarOkazji/0.4 public-listing-monitor",
      "accept-language": "pl-PL,pl;q=0.9",
      accept: "text/html,application/xhtml+xml",
    },
    redirect: "follow",
  });
  return { status: response.status, url: response.url, html: await response.text() };
}

Deno.serve(async (req) => {
  try {
    if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);
    const { region = "" } = await req.json().catch(() => ({}));
    if (!pages[region]) return json({ error: "bad_region" }, 400);

    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const secretKeys = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") || "{}");
    const serviceKey = secretKeys.default || Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
    if (!serviceKey) throw new Error("missing_service_role_key");
    const db = createClient(supabaseUrl, serviceKey, { auth: { persistSession: false } });
    const healthCity = `woj. ${region}`;
    const { data: health } = await db.from("source_health").select("last_scan_at")
      .eq("source", "wgn").eq("city", healthCity).maybeSingle();
    if (health?.last_scan_at && Date.now() - new Date(health.last_scan_at).getTime() < 45 * 60 * 1000) {
      return json({ ok: true, source: "wgn", region, throttled: true });
    }

    let httpStatus = 0;
    const urls: string[] = [];
    for (const page of pages[region]) {
      const listing = await request(page);
      httpStatus = listing.status;
      if (listing.status !== 200) continue;
      for (const url of offerLinks(listing.html, listing.url)) if (!urls.includes(url)) urls.push(url);
    }

    let parsed = 0;
    let contacts = 0;
    let sample: string | null = null;
    const errors: string[] = [];
    for (const url of urls.slice(0, 60)) {
      try {
        const detail = await request(url);
        if (detail.status !== 200) continue;
        const text = plain(detail.html);
        const cityMatch = text.match(/Miasto\s*:\s*([A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż .-]{2,60})/);
        const city = cityMatch?.[1]?.trim().replace(/\s+/g, " ") || "nieustalona";
        const priceMatch = text.match(/Cena(?:\s*\[[^\]]*\])?\s*([0-9 .\u00a0]{5,14})\s*zł/i);
        const areaMatch = text.match(/(?:Powierzchnia|Metraż)\s*([0-9]{1,3}(?:[,.][0-9]{1,2})?)\s*m²/i)
          || text.match(/([0-9]{1,3}(?:[,.][0-9]{1,2})?)\s*m²/i);
        const roomsMatch = text.match(/(?:Liczba|Ilość) pokoi\s*[:\-]?\s*([1-9])/i);
        const floorMatch = text.match(/Piętro\s*[:\-]?\s*([^,;|]{1,20})/i);
        const price = Math.round(numberValue(priceMatch?.[1]) || 0) || null;
        const area = numberValue(areaMatch?.[1]);
        if (price == null && area == null) continue;
        const contactPhone = phone(text);
        const contactEmail = text.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i)?.[0]?.toLowerCase() || null;
        const offerId = url.match(/\/oferta\/(\d+)/)?.[1] || crypto.randomUUID();
        const title = (text.match(/Mieszkanie na sprzedaż[^|]{0,180}/i)?.[0] || `Oferta WGN — ${city}`).slice(0, 500);
        const { error } = await db.from("source_candidates").upsert({
          source: "wgn",
          source_offer_id: offerId,
          url,
          city,
          voivodeship: region,
          title,
          price,
          area,
          rooms: roomsMatch ? Number(roomsMatch[1]) : null,
          price_m2: price && area ? Math.round((price / area) * 100) / 100 : null,
          floor_text: floorMatch ? `Piętro: ${floorMatch[1].trim()}` : null,
          description: text.slice(0, 5000),
          contact_phone: contactPhone,
          contact_email: contactEmail,
          seller_type: "agent",
          last_seen_at: new Date().toISOString(),
        }, { onConflict: "source,source_offer_id" });
        if (error) throw error;
        parsed++;
        if (contactPhone || contactEmail) contacts++;
        sample ||= url;
      } catch (error) {
        errors.push(String(error).slice(0, 300));
      }
    }

    const { error: analysisError } = await db.rpc("recompute_flip_analysis");
    if (analysisError) errors.push(`analysis: ${analysisError.message}`);
    const status = parsed > 0 ? "ok" : errors.length ? "error" : "no_offers";
    await db.from("source_health").upsert({
      source: "wgn",
      city: healthCity,
      status,
      http_status: httpStatus,
      offers_found: urls.length,
      contacts_found: contacts,
      last_scan_at: new Date().toISOString(),
      last_error: errors.length ? errors.join(" | ").slice(0, 1000) : null,
      sample_url: sample,
    }, { onConflict: "source,city" });
    return json({ ok: errors.length === 0, source: "wgn", region, found: urls.length, parsed, contacts, errors: errors.slice(0, 5) });
  } catch (error) {
    console.error(error);
    return json({ error: String(error) }, 500);
  }
});
