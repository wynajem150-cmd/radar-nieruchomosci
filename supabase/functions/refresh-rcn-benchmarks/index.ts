import { createClient } from "npm:@supabase/supabase-js@2";

const RCN_URL = "https://mapy.geoportal.gov.pl/wss/service/rcn";
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), {
  status,
  headers: { "content-type": "application/json; charset=utf-8" },
});
const decode = (value: string) => value.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/&#39;/g, "'");
const escapeXml = (value: string) => value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;" }[char]!));
const escapeLike = (value: string) => escapeXml(value.replace(/[*!?]/g, (char) => `!${char}`));

function tag(block: string, name: string) {
  return decode(block.match(new RegExp(`<ms:${name}>([\\s\\S]*?)<\\/ms:${name}>`, "i"))?.[1]?.trim() || "");
}

function numberValue(value: string) {
  const parsed = Number(value.replace(/[\s\u00a0]/g, "").replace(",", "."));
  return Number.isFinite(parsed) ? parsed : null;
}

function median(values: number[]) {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

async function benchmark(city: string, voivodeship: string) {
  const teryt = voivodeship === "śląskie" ? "24" : "16";
  const filter = `<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0" xmlns:ms="http://mapserver.gis.umn.edu/mapserver"><fes:And><fes:PropertyIsLike wildCard="*" singleChar="?" escapeChar="!" matchCase="false"><fes:ValueReference>ms:lok_adres</fes:ValueReference><fes:Literal>*${escapeLike(city)}*</fes:Literal></fes:PropertyIsLike><fes:PropertyIsLike wildCard="*" singleChar="?" escapeChar="!"><fes:ValueReference>ms:teryt</fes:ValueReference><fes:Literal>${teryt}*</fes:Literal></fes:PropertyIsLike><fes:PropertyIsEqualTo><fes:ValueReference>ms:tran_rodzaj_rynku</fes:ValueReference><fes:Literal>wtorny</fes:Literal></fes:PropertyIsEqualTo><fes:PropertyIsEqualTo><fes:ValueReference>ms:lok_funkcja</fes:ValueReference><fes:Literal>mieszkalna</fes:Literal></fes:PropertyIsEqualTo></fes:And></fes:Filter>`;
  const params = new URLSearchParams({
    SERVICE: "WFS",
    VERSION: "2.0.0",
    REQUEST: "GetFeature",
    TYPENAMES: "ms:lokale",
    COUNT: "300",
    SORTBY: "ms:dok_data D",
    FILTER: filter,
  });
  const response = await fetch(`${RCN_URL}?${params}`, {
    headers: { "user-agent": "RadarOkazji/0.4 RCN-transaction-benchmark", accept: "application/gml+xml,text/xml" },
  });
  if (!response.ok) throw new Error(`RCN HTTP ${response.status}`);
  const xml = await response.text();
  const blocks = [...xml.matchAll(/<wfs:member>([\s\S]*?)<\/wfs:member>/gi)].map((match) => match[1]);
  const cutoff = new Date();
  cutoff.setUTCFullYear(cutoff.getUTCFullYear() - 2);
  const rows = blocks.map((block) => {
    const area = numberValue(tag(block, "lok_pow_uzyt"));
    const price = numberValue(tag(block, "lok_cena_brutto"));
    const dateText = tag(block, "dok_data");
    const normalizedDate = dateText
      ? dateText.replace(" ", "T").replace(/([+-]\d{2})$/, "$1:00")
      : "";
    const date = normalizedDate ? new Date(normalizedDate) : null;
    const transactionType = tag(block, "tran_rodzaj_trans");
    return { area, price, date, transactionType };
  }).filter((row) => row.area != null && row.area >= 25 && row.area <= 60
    && row.price != null && row.price >= 20000 && row.price <= 3000000
    && row.date != null && !Number.isNaN(row.date.getTime()) && row.date >= cutoff
    && (!row.transactionType || row.transactionType === "wolnyRynek"));
  const values = rows.map((row) => row.price! / row.area!).filter((value) => value >= 1000 && value <= 100000);
  const dates = rows.map((row) => row.date!).sort((a, b) => a.getTime() - b.getTime());
  return {
    median_transaction_price_m2: values.length ? Math.round(median(values) * 100) / 100 : null,
    sample_count: values.length,
    period_from: dates[0]?.toISOString().slice(0, 10) || null,
    period_to: dates.at(-1)?.toISOString().slice(0, 10) || null,
  };
}

Deno.serve(async (req) => {
  try {
    if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);
    const body = await req.json().catch(() => ({}));
    const limit = Math.max(1, Math.min(10, Number(body?.limit) || 6));
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const secretKeys = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") || "{}");
    const serviceKey = secretKeys.default || Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
    if (!serviceKey) throw new Error("missing_service_role_key");
    const db = createClient(supabaseUrl, serviceKey, { auth: { persistSession: false } });

    const { data: candidates, error: candidatesError } = await db.from("source_candidates")
      .select("city,voivodeship,last_seen_at")
      .in("voivodeship", ["śląskie", "opolskie"])
      .not("city", "is", null)
      .neq("city", "nieustalona")
      .order("last_seen_at", { ascending: false })
      .limit(500);
    if (candidatesError) throw candidatesError;
    const { data: existing, error: existingError } = await db.from("market_transaction_stats")
      .select("city_key,voivodeship,fetched_at");
    if (existingError) throw existingError;
    const fresh = new Map((existing || []).map((row: any) => [`${row.voivodeship}:${row.city_key}`, new Date(row.fetched_at).getTime()]));
    const locations: Array<{ city: string; voivodeship: string }> = [];
    const seen = new Set<string>();
    for (const row of candidates || []) {
      const city = String(row.city || "").trim();
      const voivodeship = String(row.voivodeship || "");
      const key = `${voivodeship}:${city.toLowerCase()}`;
      if (!city || seen.has(key)) continue;
      seen.add(key);
      const fetchedAt = fresh.get(key) || 0;
      if (Date.now() - fetchedAt < 24 * 60 * 60 * 1000) continue;
      locations.push({ city, voivodeship });
      if (locations.length >= limit) break;
    }

    const results = await Promise.all(locations.map(async (location) => {
      try {
        const stats = await benchmark(location.city, location.voivodeship);
        const { error } = await db.from("market_transaction_stats").upsert({
          city_key: location.city.toLowerCase(),
          city: location.city,
          voivodeship: location.voivodeship,
          ...stats,
          source_name: "GUGiK RCN WFS",
          source_url: RCN_URL,
          fetched_at: new Date().toISOString(),
        }, { onConflict: "city_key,voivodeship" });
        if (error) throw error;
        return { ...location, ...stats };
      } catch (error) {
        return { ...location, error: String(error).slice(0, 500) };
      }
    }));
    const { error: analysisError } = await db.rpc("recompute_flip_analysis");
    if (analysisError) throw analysisError;
    return json({ ok: results.every((result) => !("error" in result)), refreshed: results.length, results });
  } catch (error) {
    console.error(error);
    return json({ error: String(error) }, 500);
  }
});
