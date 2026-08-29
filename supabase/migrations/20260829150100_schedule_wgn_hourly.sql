select cron.schedule(
  'scan-wgn-hourly',
  '20 * * * *',
  $cron$
  select net.http_post(
    url := 'https://bjuxmxtfhglkafqsbbgq.supabase.co/functions/v1/scan-wgn-cron',
    headers := '{"content-type":"application/json"}'::jsonb,
    body := '{}'::jsonb
  );
  $cron$
);
