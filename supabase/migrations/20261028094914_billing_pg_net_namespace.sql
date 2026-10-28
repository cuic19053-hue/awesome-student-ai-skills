-- Applied to production as migration 20261028094914.
-- pg_net is non-relocatable. Follow Supabase's documented drop/recreate
-- procedure only while our scheduler is paused and its HTTP queue is empty.
-- This preserves the user's data but discards pg_net's transient response log.
do $$
begin
  if exists (
    select 1 from pg_extension e join pg_namespace n on n.oid=e.extnamespace
    where e.extname='pg_net' and n.nspname='public'
  ) then
    if exists (select 1 from cron.job where jobname='stardust-billing-reconcile' and active) then
      raise exception 'pause the billing scheduler before moving pg_net';
    end if;
    if exists (select 1 from net.http_request_queue) then
      raise exception 'pending pg_net requests must finish before moving pg_net';
    end if;
    execute 'drop extension pg_net';
    execute 'create extension pg_net with schema extensions';
  end if;
end $$;
