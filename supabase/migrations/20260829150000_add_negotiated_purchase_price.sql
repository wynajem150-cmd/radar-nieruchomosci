alter table public.source_candidates
  add column if not exists suggested_purchase_price integer;

alter table public.offers
  add column if not exists suggested_purchase_price integer;

CREATE OR REPLACE FUNCTION public.recompute_flip_analysis()
 RETURNS void
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
begin
  with stats as (
    select lower(city) as city_key,
           percentile_cont(0.5) within group (order by price_m2) as median_price_m2,
           count(*) as sample_count
    from public.source_candidates
    where city is not null
      and lower(city) <> 'nieustalona'
      and price_m2 between 1000 and 100000
      and area between 25 and 60
      and rooms between 1 and 3
    group by lower(city)
    having count(*) >= 5
  )
  update public.source_candidates c
  set market_price_m2 = round(s.median_price_m2::numeric, 2),
      market_discount_pct = round(
        greatest(
          -9999.99,
          least(9999.99, ((s.median_price_m2 - c.price_m2) / s.median_price_m2 * 100))
        )::numeric,
        2
      ),
      renovation_cost_low = case
        when lower(coalesce(c.description,'')) ~ '(generaln.{0,10}remont|do remontu|remont kapital)' then round(c.area * 1600)::int
        when lower(coalesce(c.description,'')) ~ '(odświe|odswiez)' then round(c.area * 500)::int
        else round(c.area * 900)::int
      end,
      renovation_cost_high = case
        when lower(coalesce(c.description,'')) ~ '(generaln.{0,10}remont|do remontu|remont kapital)' then round(c.area * 2500)::int
        when lower(coalesce(c.description,'')) ~ '(odświe|odswiez)' then round(c.area * 900)::int
        else round(c.area * 1500)::int
      end,
      suggested_purchase_price = round(c.price * 0.95)::int,
      suggested_sale_price = round(c.area * s.median_price_m2 * 0.98)::int,
      estimated_profit_low = round((c.area * s.median_price_m2 * 0.98) - c.price -
        (case
          when lower(coalesce(c.description,'')) ~ '(generaln.{0,10}remont|do remontu|remont kapital)' then c.area * 2500
          when lower(coalesce(c.description,'')) ~ '(odświe|odswiez)' then c.area * 900
          else c.area * 1500
        end) - (c.area * s.median_price_m2 * 0.98 * 0.05))::int,
      estimated_profit_high = round((c.area * s.median_price_m2 * 0.98) - c.price -
        (case
          when lower(coalesce(c.description,'')) ~ '(generaln.{0,10}remont|do remontu|remont kapital)' then c.area * 1600
          when lower(coalesce(c.description,'')) ~ '(odświe|odswiez)' then c.area * 500
          else c.area * 900
        end) - (c.area * s.median_price_m2 * 0.98 * 0.03))::int,
      analysis_confidence = case when s.sample_count >= 20 then 'wysoka' when s.sample_count >= 10 then 'średnia' else 'niska' end,
      analysis_note = 'Benchmark: mediana cen ofertowych podobnych mieszkań 25–60 m² / 1–3 pokoje w tej samej miejscowości. Sugerowana cena zakupu: 95% ceny ofertowej. Cena sprzedaży: 98% mediany. Rezerwa kosztowa: 3–5% ceny sprzedaży. Remont: heurystyka na podstawie opisu oferty.',
      flip_match = coalesce((
        c.voivodeship in ('śląskie','opolskie')
        and c.price is not null and c.price <= 350000
        and c.area between 25 and 60
        and c.rooms between 1 and 3
        and ((s.median_price_m2 - c.price_m2) / s.median_price_m2 * 100) >= 30
        and ((c.area * s.median_price_m2 * 0.98) - c.price -
          (case
            when lower(coalesce(c.description,'')) ~ '(generaln.{0,10}remont|do remontu|remont kapital)' then c.area * 2500
            when lower(coalesce(c.description,'')) ~ '(odświe|odswiez)' then c.area * 900
            else c.area * 1500
          end) - (c.area * s.median_price_m2 * 0.98 * 0.05)) > 0
      ), false)
  from stats s
  where lower(c.city) = s.city_key
    and c.price_m2 is not null and c.price_m2 > 0
    and c.price is not null
    and c.area is not null;
end;
$function$
;
