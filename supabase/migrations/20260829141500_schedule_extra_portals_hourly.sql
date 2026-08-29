select cron.schedule(
  'scan-extra-portals-hourly',
  '25 * * * *',
  $cron$
  select net.http_post(
    url := 'https://bjuxmxtfhglkafqsbbgq.supabase.co/functions/v1/scan-extra-portals',
    headers := jsonb_build_object(
      'content-type', 'application/json',
      'apikey', (
        select decrypted_secret
        from vault.decrypted_secrets
        where name = 'extra_portals_edge_anon_key'
        limit 1
      ),
      'authorization', 'Bearer ' || (
        select decrypted_secret
        from vault.decrypted_secrets
        where name = 'extra_portals_edge_anon_key'
        limit 1
      )
    ),
    body := jsonb_build_object('source', task.source, 'region', task.region)
  )
  from (values
    ('olx','śląskie'),('olx','opolskie'),
    ('otodom','śląskie'),('otodom','opolskie'),
    ('gratka','śląskie'),('gratka','opolskie'),
    ('morizon','śląskie'),('morizon','opolskie'),
    ('lento','śląskie'),('lento','opolskie'),
    ('e-licytacje','śląskie'),('e-licytacje','opolskie'),
    ('krz','śląskie'),('krz','opolskie')
  ) as task(source, region);
  $cron$
);
