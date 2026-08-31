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
