do $$
begin
  perform cron.unschedule('refresh-rent-benchmarks-hourly');
exception when others then
  null;
end $$;

select cron.schedule(
  'refresh-rent-benchmarks-hourly',
  '34 * * * *',
  $cron$
  select net.http_post(
    url := 'https://bjuxmxtfhglkafqsbbgq.supabase.co/functions/v1/refresh-rent-benchmarks',
    headers := jsonb_build_object(
      'content-type', 'application/json',
      'apikey', (select decrypted_secret from vault.decrypted_secrets where name = 'extra_portals_edge_anon_key' limit 1),
      'authorization', 'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name = 'extra_portals_edge_anon_key' limit 1)
    ),
    body := '{}'::jsonb
  );
  $cron$
);
