create or replace function public.finalize_flip_outlier_risk()
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  affected integer := 0;
begin
  update public.source_candidates c set
    risk_score = least(100, coalesce(c.risk_score, 0) + 20),
    risk_level = case when coalesce(c.risk_score, 0) + 20 >= 60 then 'wysokie' when coalesce(c.risk_score, 0) + 20 >= 30 then 'średnie' else 'podwyższone — anomalia ceny' end,
    risk_flags = array_append(coalesce(c.risk_flags, '{}'::text[]), 'cena ponad 70% poniżej rynku — zweryfikuj typ i kompletność oferty'),
    risk_note = concat_ws(' ', c.risk_note, 'Cena jest skrajnym odstępstwem od transakcji RCN; sprawdź, czy chodzi o pełną własność lokalu, cenę całkowitą i aktualną ofertę.'),
    flip_score = greatest(0, coalesce(c.flip_score, 0) - 3),
    alert_tier = case when greatest(0, coalesce(c.flip_score, 0) - 3) >= 80 then 'A' when greatest(0, coalesce(c.flip_score, 0) - 3) >= 65 then 'B' else 'C' end
  where c.market_discount_pct >= 70
    and not ('cena ponad 70% poniżej rynku — zweryfikuj typ i kompletność oferty' = any(coalesce(c.risk_flags, '{}'::text[])));
  get diagnostics affected = row_count;
  return affected;
end;
$$;

revoke all on function public.finalize_flip_outlier_risk() from public, anon, authenticated;
grant execute on function public.finalize_flip_outlier_risk() to service_role;

do $$
begin
  perform cron.unschedule('recompute-flip-analysis-hourly');
exception when others then
  null;
end $$;

select cron.schedule(
  'recompute-flip-analysis-hourly',
  '38 * * * *',
  $cron$select public.recompute_flip_analysis(); select public.finalize_flip_outlier_risk();$cron$
);
