do $$
begin
  perform cron.unschedule('scan-public-sales-hourly');
exception when others then
  null;
end $$;

select cron.schedule(
  'scan-public-sales-hourly',
  '32 * * * *',
  $cron$
  select net.http_post(
    url := 'https://bjuxmxtfhglkafqsbbgq.supabase.co/functions/v1/scan-public-sales',
    headers := jsonb_build_object(
      'content-type', 'application/json',
      'apikey', (select decrypted_secret from vault.decrypted_secrets where name = 'extra_portals_edge_anon_key' limit 1),
      'authorization', 'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name = 'extra_portals_edge_anon_key' limit 1)
    ),
    body := jsonb_build_object('source', task.source, 'region', task.region)
  )
  from (values
    ('sprzedajemy','śląskie'),
    ('sprzedajemy','opolskie'),
    ('pkp-nieruchomosci','śląskie'),
    ('pkp-nieruchomosci','opolskie'),
    ('amw','śląskie'),
    ('amw','opolskie'),
    ('zgm-gliwice','śląskie'),
    ('bip-katowice','śląskie'),
    ('bip-opole','opolskie'),
    ('bip-kedzierzyn-kozle','opolskie')
  ) as task(source, region);
  $cron$
);
