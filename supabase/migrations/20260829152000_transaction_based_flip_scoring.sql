create table if not exists public.market_transaction_stats (
  city_key text not null,
  city text not null,
  voivodeship text not null,
  median_transaction_price_m2 numeric,
  sample_count integer not null default 0,
  period_from date,
  period_to date,
  source_name text not null default 'GUGiK RCN WFS',
  source_url text not null default 'https://mapy.geoportal.gov.pl/wss/service/rcn',
  fetched_at timestamptz not null default now(),
  primary key (city_key, voivodeship)
);

alter table public.market_transaction_stats enable row level security;

alter table public.source_candidates
  add column if not exists has_balcony boolean not null default false,
  add column if not exists has_terrace boolean not null default false,
  add column if not exists flip_score integer,
  add column if not exists score_note text,
  add column if not exists market_basis text,
  add column if not exists transaction_sample_count integer;

alter table public.offers
  add column if not exists has_balcony boolean not null default false,
  add column if not exists has_terrace boolean not null default false,
  add column if not exists flip_score integer,
  add column if not exists score_note text,
  add column if not exists market_basis text,
  add column if not exists transaction_sample_count integer;

create index if not exists market_transaction_stats_fetched_at_idx
  on public.market_transaction_stats (fetched_at desc);

update public.source_candidates set suggested_purchase_price = null
where suggested_purchase_price is not null;

update public.offers set suggested_purchase_price = null
where suggested_purchase_price is not null;

create or replace function public.recompute_flip_analysis()
returns void
language plpgsql
set search_path to 'public'
as $function$
begin
  update public.source_candidates c
  set has_balcony = lower(concat_ws(' ', c.title, c.description, c.floor_text)) ~ '(balkon|loggia)',
      has_terrace = lower(concat_ws(' ', c.title, c.description, c.floor_text)) ~ 'taras',
      suggested_purchase_price = null,
      market_price_m2 = null,
      market_discount_pct = null,
      renovation_cost_low = null,
      renovation_cost_high = null,
      suggested_sale_price = null,
      estimated_profit_low = null,
      estimated_profit_high = null,
      analysis_confidence = null,
      analysis_note = null,
      market_basis = null,
      transaction_sample_count = null,
      flip_score = null,
      score_note = null,
      flip_match = false
  where c.voivodeship in ('śląskie', 'opolskie');

  with benchmark as (
    select city_key,
           voivodeship,
           median_transaction_price_m2,
           sample_count,
           period_from,
           period_to,
           source_name
    from public.market_transaction_stats
    where median_transaction_price_m2 between 1000 and 100000
      and sample_count >= 5
      and fetched_at >= now() - interval '45 days'
  ), base as (
    select c.id,
           c.price,
           c.area,
           c.price_m2,
           c.voivodeship,
           c.has_balcony,
           c.has_terrace,
           b.median_transaction_price_m2,
           b.sample_count,
           b.period_from,
           b.period_to,
           b.source_name,
           round((((b.median_transaction_price_m2 - c.price_m2)
             / b.median_transaction_price_m2) * 100)::numeric, 2) as discount_pct,
           case
             when lower(coalesce(c.description, '')) ~ '(generaln.{0,10}remont|do remontu|remont kapital)' then round(c.area * 1600)::int
             when lower(coalesce(c.description, '')) ~ '(odświe|odswiez)' then round(c.area * 500)::int
             else round(c.area * 900)::int
           end as renovation_low,
           case
             when lower(coalesce(c.description, '')) ~ '(generaln.{0,10}remont|do remontu|remont kapital)' then round(c.area * 2500)::int
             when lower(coalesce(c.description, '')) ~ '(odświe|odswiez)' then round(c.area * 900)::int
             else round(c.area * 1500)::int
           end as renovation_high,
           round(c.area * b.median_transaction_price_m2 * 0.98)::int as sale_price
    from public.source_candidates c
    join benchmark b
      on b.city_key = lower(trim(c.city))
     and b.voivodeship = c.voivodeship
    where c.price is not null and c.price > 0
      and c.area is not null and c.area > 0
      and c.price_m2 is not null and c.price_m2 > 0
  ), profit as (
    select base.*,
           round(sale_price - price - renovation_high - sale_price * 0.05)::int as profit_low,
           round(sale_price - price - renovation_low - sale_price * 0.03)::int as profit_high
    from base
  ), components as (
    select profit.*,
           round(least(40::numeric, greatest(0::numeric, discount_pct)))::int as discount_points,
           round(least(30::numeric, greatest(0::numeric, (profit_low::numeric / price) * 100)))::int as profit_points,
           case when area between 25 and 60 then 10 else 0 end as liquidity_points,
           case when has_terrace then 10 when has_balcony then 6 else 0 end as amenity_points,
           case when sample_count >= 20 then 10 when sample_count >= 10 then 7 else 4 end as data_points
    from profit
  ), scored as (
    select components.*,
           least(100, discount_points + profit_points + liquidity_points + amenity_points + data_points)::int as total_score
    from components
  )
  update public.source_candidates c
  set market_price_m2 = round(s.median_transaction_price_m2::numeric, 2),
      market_discount_pct = s.discount_pct,
      renovation_cost_low = s.renovation_low,
      renovation_cost_high = s.renovation_high,
      suggested_sale_price = s.sale_price,
      estimated_profit_low = s.profit_low,
      estimated_profit_high = s.profit_high,
      analysis_confidence = case when s.sample_count >= 20 then 'wysoka' when s.sample_count >= 10 then 'średnia' else 'niska' end,
      analysis_note = concat(
        'Benchmark transakcyjny: mediana ', s.sample_count, ' transakcji lokali mieszkalnych z RCN w tej samej miejscowości',
        case when s.period_from is not null and s.period_to is not null then concat(' (', s.period_from, '–', s.period_to, ')') else '' end,
        '. Liczba pokoi pominięta. Cena sprzedaży: 98% mediany transakcyjnej. Rezerwa kosztowa: 3–5% ceny sprzedaży.'
      ),
      market_basis = 'ceny transakcyjne — GUGiK RCN',
      transaction_sample_count = s.sample_count,
      flip_score = s.total_score,
      score_note = concat(
        s.total_score, '/100: rabat ', s.discount_points, '/40, zysk ', s.profit_points,
        '/30, płynność metrażu ', s.liquidity_points, '/10, balkon/taras ', s.amenity_points,
        '/10, jakość danych ', s.data_points, '/10.'
      ),
      flip_match = (
        s.voivodeship in ('śląskie', 'opolskie')
        and s.price <= 350000
        and s.area between 25 and 60
        and s.discount_pct >= 30
        and s.profit_low > 0
      )
  from scored s
  where c.id = s.id;
end;
$function$;

do $$
begin
  perform cron.unschedule('refresh-rcn-benchmarks-hourly');
exception when others then
  null;
end $$;

select cron.schedule(
  'refresh-rcn-benchmarks-hourly',
  '30 * * * *',
  $cron$
  select net.http_post(
    url := 'https://bjuxmxtfhglkafqsbbgq.supabase.co/functions/v1/refresh-rcn-benchmarks',
    headers := jsonb_build_object(
      'content-type', 'application/json',
      'apikey', (select decrypted_secret from vault.decrypted_secrets where name = 'extra_portals_edge_anon_key' limit 1),
      'authorization', 'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name = 'extra_portals_edge_anon_key' limit 1)
    ),
    body := '{"limit":6}'::jsonb
  );
  $cron$
);

do $$
begin
  perform cron.unschedule('scan-wgn-hourly');
exception when others then
  null;
end $$;

select cron.schedule(
  'scan-wgn-hourly',
  '20 * * * *',
  $cron$
  select net.http_post(
    url := 'https://bjuxmxtfhglkafqsbbgq.supabase.co/functions/v1/scan-wgn-cron',
    headers := jsonb_build_object(
      'content-type', 'application/json',
      'apikey', (select decrypted_secret from vault.decrypted_secrets where name = 'extra_portals_edge_anon_key' limit 1),
      'authorization', 'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name = 'extra_portals_edge_anon_key' limit 1)
    ),
    body := '{}'::jsonb
  );
  $cron$
);
