type Tester = {
  tester_code: string;
  telegram_chat_id: number;
  locations: string[];
  voivodeships: string[];
  max_price: number;
  min_area: number;
  max_area: number;
  max_price_m2: number | null;
  min_market_discount_pct: number | null;
  flip_analysis_enabled: boolean;
  exclusions: string[];
};

type Candidate = {
  source: string;
  source_offer_id: string;
  title: string | null;
  url: string;
  city: string | null;
  voivodeship: string | null;
  price: number | null;
  area: number | null;
  price_m2: number | null;
  floor_text: string | null;
  description: string | null;
  market_price_m2: number | null;
  market_discount_pct: number | null;
  renovation_cost_low: number | null;
  renovation_cost_high: number | null;
  suggested_sale_price: number | null;
  estimated_profit_low: number | null;
  estimated_profit_high: number | null;
  analysis_confidence: string | null;
  analysis_note: string | null;
  has_balcony: boolean;
  has_terrace: boolean;
  flip_score: number | null;
  score_note: string | null;
  market_basis: string | null;
  transaction_sample_count: number | null;
  last_seen_at: string;
};

const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), {
  status,
  headers: { "content-type": "application/json; charset=utf-8" },
});
const money = (value: number | null) => value == null ? "brak danych" : `${Math.round(value).toLocaleString("pl-PL")} zł`;
const norm = (value: unknown) => String(value || "").toLowerCase().normalize("NFKC").replace(/\s+/g, " ").trim();
const warsawDate = (date: Date) => new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Warsaw", year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
const warsawHour = (date: Date) => Number(new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Warsaw", hour: "2-digit", hourCycle: "h23" }).format(date));

async function telegram(token: string, method: string, body: unknown) {
  const response = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok || !data.ok) throw new Error(`telegram_${method}_failed`);
  return data.result;
}

async function db(path: string, key: string, init: RequestInit = {}) {
  const base = Deno.env.get("SUPABASE_URL")!;
  return fetch(`${base}/rest/v1/${path}`, {
    ...init,
    headers: {
      apikey: key,
      authorization: `Bearer ${key}`,
      "content-type": "application/json",
      ...(init.headers || {}),
    },
  });
}

async function rows(path: string, key: string) {
  const response = await db(path, key);
  if (!response.ok) throw new Error(`db_read_${response.status}:${(await response.text()).slice(0, 300)}`);
  return response.json();
}

function matches(tester: Tester, offer: Candidate) {
  const locations = (tester.locations || []).map(norm);
  const regions = (tester.voivodeships || []).map(norm);
  if ((locations.length || regions.length) && !locations.includes(norm(offer.city)) && !regions.includes(norm(offer.voivodeship))) return false;
  if (offer.price == null || offer.price > tester.max_price) return false;
  if (offer.area == null || offer.area < Number(tester.min_area) || offer.area > Number(tester.max_area)) return false;
  if (tester.max_price_m2 != null && (offer.price_m2 == null || offer.price_m2 > tester.max_price_m2)) return false;
  if (tester.min_market_discount_pct != null && (offer.market_discount_pct == null || offer.market_discount_pct < Number(tester.min_market_discount_pct))) return false;
  const haystack = norm(`${offer.title || ""} ${offer.description || ""} ${offer.floor_text || ""}`);
  for (const exclusion of tester.exclusions || []) {
    const value = norm(exclusion);
    if (value && haystack.includes(value)) return false;
  }
  return true;
}

function offerMessage(offer: Candidate, showAnalysis: boolean) {
  const amenity = offer.has_terrace ? "⭐ Atut: taras" : offer.has_balcony ? "⭐ Atut: balkon/loggia" : "";
  return [
    "🔥 NOWA OFERTA SPEŁNIAJĄCA KRYTERIA FLIPA",
    "",
    `🌐 ${offer.source}`,
    `📍 ${offer.city || "lokalizacja nieustalona"}${offer.voivodeship ? ` | woj. ${offer.voivodeship}` : ""}`,
    `🏠 ${offer.area ?? "?"} m²`,
    `💰 Cena ofertowa/wywoławcza: ${money(offer.price)}`,
    `📐 ${offer.price_m2 == null ? "brak ceny/m²" : `${Math.round(offer.price_m2).toLocaleString("pl-PL")} zł/m²`}`,
    offer.floor_text ? `🏢 ${offer.floor_text}` : "",
    amenity,
    "",
    offer.title || "Oferta mieszkania",
    "",
    showAnalysis ? "📊 ANALIZA OPŁACALNOŚCI FLIPA" : "",
    showAnalysis && offer.flip_score != null ? `Scoring opłacalności: ${offer.flip_score}/100` : "",
    showAnalysis && offer.market_price_m2 != null ? `Mediana cen transakcyjnych RCN: ${Math.round(offer.market_price_m2).toLocaleString("pl-PL")} zł/m²` : "",
    showAnalysis && offer.transaction_sample_count != null ? `Próba transakcyjna: ${offer.transaction_sample_count} lokali` : "",
    showAnalysis && offer.market_discount_pct != null ? `Rabat do rynku: ${Number(offer.market_discount_pct).toLocaleString("pl-PL", { maximumFractionDigits: 1 })}%` : "",
    showAnalysis && offer.renovation_cost_low != null && offer.renovation_cost_high != null ? `Szacowany remont/odświeżenie: ${money(offer.renovation_cost_low)} – ${money(offer.renovation_cost_high)}` : "",
    showAnalysis && offer.suggested_sale_price != null ? `Sugerowana cena sprzedaży po remoncie/odświeżeniu: ${money(offer.suggested_sale_price)}` : "",
    showAnalysis && offer.estimated_profit_low != null && offer.estimated_profit_high != null ? `Szacowany zysk: ${money(offer.estimated_profit_low)} – ${money(offer.estimated_profit_high)}` : "",
    showAnalysis && offer.analysis_confidence ? `Pewność analizy: ${offer.analysis_confidence}` : "",
    showAnalysis && offer.score_note ? offer.score_note : "",
    "",
    `🔗 ${offer.url}`,
    "",
    "Analiza jest szacunkowa i nie stanowi wyceny ani gwarancji zysku.",
  ].filter(Boolean).join("\n");
}

async function alreadyDelivered(key: string, tester: string, source: string, offerId: string) {
  const path = `deliveries?select=tester_code&tester_code=eq.${encodeURIComponent(tester)}&source=eq.${encodeURIComponent(source)}&source_offer_id=eq.${encodeURIComponent(offerId)}&limit=1`;
  return (await rows(path, key)).length > 0;
}

async function recordDelivery(key: string, tester: string, source: string, offerId: string, messageId: number) {
  const response = await db("deliveries", key, {
    method: "POST",
    headers: { Prefer: "return=minimal" },
    body: JSON.stringify({ tester_code: tester, source, source_offer_id: offerId, telegram_message_id: messageId }),
  });
  if (!response.ok) throw new Error(`delivery_insert_${response.status}`);
}

Deno.serve(async (req) => {
  try {
    if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);
    const botToken = req.headers.get("x-telegram-bot-token") || "";
    if (!botToken) return json({ error: "missing_bot_token" }, 401);
    const me = await telegram(botToken, "getMe", {});
    if (String(me?.username || "").toLowerCase() !== "radarokazjibot") return json({ error: "wrong_bot" }, 403);
    const body = await req.json().catch(() => ({}));
    const mode = body?.mode === "summary" ? "summary" : "alerts";
    const dryRun = body?.dry_run === true;
    const keys = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") || "{}");
    const serviceKey = keys.default || Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
    if (!serviceKey) throw new Error("missing_service_key");
    const testers: Tester[] = await rows("testers?select=tester_code,telegram_chat_id,locations,voivodeships,max_price,min_area,max_area,max_price_m2,min_market_discount_pct,flip_analysis_enabled,exclusions&active=eq.true&telegram_chat_id=not.is.null", serviceKey);

    if (mode === "summary") {
      const now = new Date();
      const localDate = warsawDate(now);
      const localHour = warsawHour(now);
      if (localHour !== 20 && !dryRun) return json({ ok: true, mode, skipped: "outside_20_warsaw", local_hour: localHour });
      const since = new Date(now.getTime() - 26 * 60 * 60 * 1000).toISOString();
      const recent = await rows(`deliveries?select=tester_code,source,source_offer_id,sent_at&sent_at=gte.${encodeURIComponent(since)}`, serviceKey);
      const sent: string[] = [];
      const skipped: string[] = [];
      for (const tester of testers) {
        const source = "summary:daily";
        if (await alreadyDelivered(serviceKey, tester.tester_code, source, localDate)) {
          skipped.push(tester.tester_code);
          continue;
        }
        const count = recent.filter((delivery: any) => delivery.tester_code === tester.tester_code
          && warsawDate(new Date(delivery.sent_at)) === localDate
          && !String(delivery.source).startsWith("test:") && delivery.source !== source).length;
        const text = count === 0
          ? "📊 PODSUMOWANIE DNIA — RADAR OKAZJI\n\nDzisiaj 0 ofert spełniających kryteria dobrego flipa.\n\nSystem sprawdza wszystkie podłączone źródła co godzinę i będzie szukał dalej."
          : `📊 PODSUMOWANIE DNIA — RADAR OKAZJI\n\nDzisiaj znaleziono i wysłano ${count} ${count === 1 ? "ofertę" : count < 5 ? "oferty" : "ofert"} spełniających kryteria dobrego flipa.`;
        if (dryRun) {
          sent.push(`${tester.tester_code}:${count}`);
          continue;
        }
        const message = await telegram(botToken, "sendMessage", { chat_id: tester.telegram_chat_id, text });
        await recordDelivery(serviceKey, tester.tester_code, source, localDate, message.message_id);
        sent.push(`${tester.tester_code}:${count}`);
      }
      return json({ ok: true, mode, local_date: localDate, sent_count: sent.length, sent, skipped, dry_run: dryRun });
    }

    const analysis = await db("rpc/recompute_flip_analysis", serviceKey, { method: "POST", body: "{}" });
    if (!analysis.ok) throw new Error(`analysis_${analysis.status}:${(await analysis.text()).slice(0, 300)}`);
    const since = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
    const select = "source,source_offer_id,title,url,city,voivodeship,price,area,price_m2,floor_text,description,market_price_m2,market_discount_pct,renovation_cost_low,renovation_cost_high,suggested_sale_price,estimated_profit_low,estimated_profit_high,analysis_confidence,analysis_note,has_balcony,has_terrace,flip_score,score_note,market_basis,transaction_sample_count,last_seen_at";
    const candidates: Candidate[] = await rows(`source_candidates?select=${select}&flip_match=eq.true&last_seen_at=gte.${encodeURIComponent(since)}&order=last_seen_at.desc&limit=200`, serviceKey);
    const sent: string[] = [];
    const errors: string[] = [];
    let matched = 0;
    for (const candidate of candidates) {
      for (const tester of testers) {
        if (!matches(tester, candidate)) continue;
        matched++;
        if (await alreadyDelivered(serviceKey, tester.tester_code, candidate.source, candidate.source_offer_id)) continue;
        if (dryRun) {
          sent.push(`${tester.tester_code}:${candidate.source}:${candidate.source_offer_id}`);
          continue;
        }
        try {
          const message = await telegram(botToken, "sendMessage", {
            chat_id: tester.telegram_chat_id,
            text: offerMessage(candidate, Boolean(tester.flip_analysis_enabled)),
            disable_web_page_preview: false,
          });
          await recordDelivery(serviceKey, tester.tester_code, candidate.source, candidate.source_offer_id, message.message_id);
          sent.push(`${tester.tester_code}:${candidate.source}:${candidate.source_offer_id}`);
        } catch (error) {
          errors.push(`${tester.tester_code}:${candidate.source_offer_id}:${String(error)}`.slice(0, 500));
        }
      }
    }
    return json({ ok: errors.length === 0, mode, candidates: candidates.length, matched, sent_count: sent.length, sent, errors, dry_run: dryRun });
  } catch (error) {
    console.error(error);
    return json({ error: String(error) }, 500);
  }
});
