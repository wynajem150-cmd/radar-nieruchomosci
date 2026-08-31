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
  initial_price: number | null;
  price_change_count: number;
  price_change_pct: number | null;
  days_on_market: number | null;
  duplicate_count: number;
  duplicate_sources: string[];
  comparable_transactions: Array<{ date?: string; address?: string; area?: number; price?: number; price_m2?: number }>;
  comparable_count: number;
  sale_price_fast: number | null;
  sale_price_base: number | null;
  sale_price_optimistic: number | null;
  acquisition_costs: number | null;
  holding_costs: number | null;
  selling_costs: number | null;
  total_investment: number | null;
  net_profit_fast: number | null;
  net_profit_base: number | null;
  net_profit_optimistic: number | null;
  roi_fast: number | null;
  roi_base: number | null;
  roi_optimistic: number | null;
  liquidity_score: number | null;
  estimated_sale_days: number | null;
  liquidity_note: string | null;
  risk_score: number | null;
  risk_level: string | null;
  risk_flags: string[];
  risk_note: string | null;
  condition_score: number | null;
  renovation_scope: string | null;
  renovation_cost_base: number | null;
  photo_count: number;
  photo_analysis_note: string | null;
  monthly_rent_estimate: number | null;
  rental_yield_gross: number | null;
  rental_yield_net: number | null;
  rent_sample_count: number | null;
  rent_fallback_note: string | null;
  market_trend_3m_pct: number | null;
  market_trend_12m_pct: number | null;
  alert_tier: string | null;
  investment_summary: string | null;
  analysis_version: string | null;
  last_seen_at: string;
};

const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), {
  status,
  headers: { "content-type": "application/json; charset=utf-8" },
});
const money = (value: number | null) => value == null ? "brak danych" : `${Math.round(value).toLocaleString("pl-PL")} zł`;
const pct = (value: number | null) => value == null ? "brak danych" : `${Number(value).toLocaleString("pl-PL", { maximumFractionDigits: 1 })}%`;
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
  const history = offer.initial_price && offer.initial_price !== offer.price
    ? `📉 Historia ceny: ${money(offer.initial_price)} → ${money(offer.price)} (${pct(offer.price_change_pct)}, ${offer.price_change_count} zmian)`
    : `📅 W portfelu radaru: ${offer.days_on_market ?? 0} dni | zmian ceny: ${offer.price_change_count || 0}`;
  const duplicates = offer.duplicate_count > 1
    ? `🔁 Duplikaty: ${offer.duplicate_count} ogłoszenia | ${offer.duplicate_sources.join(", ")}`
    : "";
  const comps = (offer.comparable_transactions || []).slice(0, 3).map((item) => {
    const date = item.date ? new Intl.DateTimeFormat("pl-PL", { year: "numeric", month: "2-digit" }).format(new Date(item.date)) : "?";
    const address = item.address ? `, ${String(item.address).slice(0, 55)}` : "";
    return `• ${date}: ${item.area ?? "?"} m², ${money(item.price)}, ${item.price_m2 == null ? "?" : `${Math.round(item.price_m2).toLocaleString("pl-PL")} zł/m²`}${address}`;
  });
  const riskFlags = (offer.risk_flags || []).length ? `Czerwone flagi: ${offer.risk_flags.join(", ")}` : "Brak automatycznie wykrytych czerwonych flag.";
  const trend = offer.market_trend_3m_pct != null || offer.market_trend_12m_pct != null
    ? `📈 Trend transakcyjny: 3 mies. ${pct(offer.market_trend_3m_pct)} | 12 mies. ${pct(offer.market_trend_12m_pct)}`
    : "";
  return [
    `🔥 NOWA OFERTA — FLIP ${offer.alert_tier || "C"} | ${offer.flip_score ?? "?"}/100`,
    "",
    `🌐 ${offer.source}`,
    `📍 ${offer.city || "lokalizacja nieustalona"}${offer.voivodeship ? ` | woj. ${offer.voivodeship}` : ""}`,
    `🏠 ${offer.area ?? "?"} m²`,
    `💰 Cena ofertowa/wywoławcza: ${money(offer.price)}`,
    `📐 ${offer.price_m2 == null ? "brak ceny/m²" : `${Math.round(offer.price_m2).toLocaleString("pl-PL")} zł/m²`}`,
    offer.floor_text ? `🏢 ${offer.floor_text}` : "",
    amenity,
    history,
    duplicates,
    "",
    offer.title || "Oferta mieszkania",
    "",
    showAnalysis ? "📊 ANALIZA INWESTORSKA ALL-IN" : "",
    showAnalysis && offer.flip_score != null ? `Scoring: ${offer.flip_score}/100 | klasa ${offer.alert_tier || "C"}` : "",
    showAnalysis && offer.market_price_m2 != null ? `Mediana cen transakcyjnych RCN: ${Math.round(offer.market_price_m2).toLocaleString("pl-PL")} zł/m²` : "",
    showAnalysis && offer.transaction_sample_count != null ? `Próba RCN: ${offer.transaction_sample_count} | porównywalne: ${offer.comparable_count || 0}` : "",
    showAnalysis && offer.market_discount_pct != null ? `Rabat do rynku: ${Number(offer.market_discount_pct).toLocaleString("pl-PL", { maximumFractionDigits: 1 })}%` : "",
    "",
    showAnalysis ? `🛠 Stan: ${offer.renovation_scope || "nieustalony"} | ocena ${offer.condition_score ?? "?"}/100` : "",
    showAnalysis && offer.renovation_cost_low != null && offer.renovation_cost_high != null ? `Remont: ${money(offer.renovation_cost_low)} – ${money(offer.renovation_cost_high)} | baza ${money(offer.renovation_cost_base)}` : "",
    showAnalysis ? `Zdjęcia: ${offer.photo_count || 0}. ${offer.photo_analysis_note || ""}` : "",
    "",
    showAnalysis ? "🎯 SCENARIUSZE SPRZEDAŻY PO REMONCIE" : "",
    showAnalysis ? `Szybki: ${money(offer.sale_price_fast)} | bazowy: ${money(offer.sale_price_base)} | optymistyczny: ${money(offer.sale_price_optimistic)}` : "",
    showAnalysis ? `Zysk netto*: ${money(offer.net_profit_fast)} | ${money(offer.net_profit_base)} | ${money(offer.net_profit_optimistic)}` : "",
    showAnalysis ? `ROI: ${pct(offer.roi_fast)} | ${pct(offer.roi_base)} | ${pct(offer.roi_optimistic)}` : "",
    showAnalysis ? `Kapitał all-in: ${money(offer.total_investment)} (zakup + koszty nabycia ${money(offer.acquisition_costs)} + remont ${money(offer.renovation_cost_base)} + utrzymanie ${money(offer.holding_costs)})` : "",
    showAnalysis ? `Koszt sprzedaży w bazie: ${money(offer.selling_costs)}` : "",
    "",
    showAnalysis ? `⏱ Płynność: ${offer.liquidity_score ?? "?"}/100 | ok. ${offer.estimated_sale_days ?? "?"} dni` : "",
    showAnalysis ? offer.liquidity_note || "" : "",
    showAnalysis ? `⚠️ Ryzyko: ${offer.risk_score ?? "?"}/100 (${offer.risk_level || "nieustalone"})` : "",
    showAnalysis ? riskFlags : "",
    trend,
    "",
    showAnalysis && offer.monthly_rent_estimate != null ? `🏘 Plan B — najem: ${money(offer.monthly_rent_estimate)}/mies. | rentowność brutto ${pct(offer.rental_yield_gross)}, netto operacyjnie ${pct(offer.rental_yield_net)} | próba ${offer.rent_sample_count || 0}` : "",
    showAnalysis && comps.length ? "" : "",
    showAnalysis && comps.length ? "🔎 OSTATNIE TRANSAKCJE PORÓWNAWCZE" : "",
    showAnalysis ? comps : [],
    showAnalysis && offer.analysis_confidence ? `Pewność analizy: ${offer.analysis_confidence}` : "",
    showAnalysis && offer.score_note ? offer.score_note : "",
    "",
    `🔗 ${offer.url}`,
    "",
    "*Zysk netto kosztowo: po kosztach nabycia/remontu/utrzymania/sprzedaży, przed podatkiem dochodowym i finansowaniem. Analiza szacunkowa — nie jest wyceną ani gwarancją zysku.",
  ].flat().filter(Boolean).join("\n");
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
      const dailyCandidates = await rows(`source_candidates?select=source,source_offer_id,alert_tier,net_profit_base&last_seen_at=gte.${encodeURIComponent(since)}&limit=1000`, serviceKey);
      const candidateByKey = new Map(dailyCandidates.map((candidate: any) => [`${candidate.source}:${candidate.source_offer_id}`, candidate]));
      const sent: string[] = [];
      const skipped: string[] = [];
      for (const tester of testers) {
        const source = "summary:daily";
        if (await alreadyDelivered(serviceKey, tester.tester_code, source, localDate)) {
          skipped.push(tester.tester_code);
          continue;
        }
        const today = recent.filter((delivery: any) => delivery.tester_code === tester.tester_code
          && warsawDate(new Date(delivery.sent_at)) === localDate
          && !String(delivery.source).startsWith("test:") && delivery.source !== source);
        const count = today.length;
        const tiers = { A: 0, B: 0, C: 0 };
        const sources = new Set<string>();
        let totalBaseProfit = 0;
        for (const delivery of today) {
          sources.add(delivery.source);
          const candidate: any = candidateByKey.get(`${delivery.source}:${delivery.source_offer_id}`);
          const tier = candidate?.alert_tier === "A" || candidate?.alert_tier === "B" ? candidate.alert_tier : "C";
          tiers[tier as keyof typeof tiers]++;
          totalBaseProfit += Number(candidate?.net_profit_base || 0);
        }
        const text = count === 0
          ? "📊 PODSUMOWANIE DNIA — RADAR OKAZJI\n\nDzisiaj 0 ofert spełniających kryteria dobrego flipa.\n\nSystem sprawdza wszystkie podłączone źródła co godzinę i będzie szukał dalej."
          : `📊 PODSUMOWANIE DNIA — RADAR OKAZJI\n\nDzisiaj znaleziono i wysłano ${count} ${count === 1 ? "ofertę" : count < 5 ? "oferty" : "ofert"} spełniających kryteria dobrego flipa.\n\nKlasy: A — ${tiers.A}, B — ${tiers.B}, C — ${tiers.C}\nŹródła: ${[...sources].sort().join(", ")}\nŁączny potencjalny zysk bazowy*: ${money(totalBaseProfit)}\n\n*Przed podatkiem dochodowym i kosztem finansowania; nie sumuj ofert będących duplikatami jako osobnych inwestycji.`;
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

    const since = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
    const select = "source,source_offer_id,title,url,city,voivodeship,price,area,price_m2,floor_text,description,market_price_m2,market_discount_pct,renovation_cost_low,renovation_cost_high,suggested_sale_price,estimated_profit_low,estimated_profit_high,analysis_confidence,analysis_note,has_balcony,has_terrace,flip_score,score_note,market_basis,transaction_sample_count,initial_price,price_change_count,price_change_pct,days_on_market,duplicate_count,duplicate_sources,comparable_transactions,comparable_count,sale_price_fast,sale_price_base,sale_price_optimistic,acquisition_costs,holding_costs,selling_costs,total_investment,net_profit_fast,net_profit_base,net_profit_optimistic,roi_fast,roi_base,roi_optimistic,liquidity_score,estimated_sale_days,liquidity_note,risk_score,risk_level,risk_flags,risk_note,condition_score,renovation_scope,renovation_cost_base,photo_count,photo_analysis_note,monthly_rent_estimate,rental_yield_gross,rental_yield_net,rent_sample_count,rent_fallback_note,market_trend_3m_pct,market_trend_12m_pct,alert_tier,investment_summary,analysis_version,last_seen_at";
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
