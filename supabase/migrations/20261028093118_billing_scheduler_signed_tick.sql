-- Applied to production as migration 20261028093118.
-- pg_net request queues can be readable to PUBLIC on hosted Supabase. Never
-- place a long-lived credential in that queue: send a short-lived signed tick
-- and consume each tick at most once.
create table billing_private.scheduler_ticks (
  tick bigint primary key,
  created_at timestamptz not null default now()
);
alter table billing_private.scheduler_ticks enable row level security;
revoke all on billing_private.scheduler_ticks from public, anon, authenticated;

create function billing_private.consume_scheduler_tick(
  p_backend_secret text, p_worker_secret text, p_timestamp bigint
) returns jsonb language plpgsql security definer set search_path='' as $$
declare inserted integer;
begin
  perform public.workbench_check_backend(p_backend_secret);
  if p_worker_secret is null or octet_length(p_worker_secret) <> 64 or not exists (
    select 1 from billing_private.worker_capability
    where secret_hash=pg_catalog.sha256(pg_catalog.convert_to(p_worker_secret,'UTF8'))
  ) then raise exception 'worker capability required' using errcode='42501'; end if;
  if p_timestamp is null or abs(extract(epoch from clock_timestamp())::bigint - p_timestamp)>90
    or p_timestamp % 60 <> 0 then
    return jsonb_build_object('status','expired');
  end if;
  delete from billing_private.scheduler_ticks where created_at < now()-interval '1 day';
  insert into billing_private.scheduler_ticks(tick) values(p_timestamp) on conflict do nothing;
  get diagnostics inserted = row_count;
  return jsonb_build_object('status',case when inserted=1 then 'accepted' else 'duplicate' end);
end $$;
revoke all on function billing_private.consume_scheduler_tick(text,text,bigint) from public, anon, authenticated;
grant execute on function billing_private.consume_scheduler_tick(text,text,bigint) to anon, authenticated;
create function public.billing_reconciliation_scheduler_tick(
  p_backend_secret text,p_worker_secret text,p_timestamp bigint
) returns jsonb language sql security invoker set search_path='' as $$
  select billing_private.consume_scheduler_tick(p_backend_secret,p_worker_secret,p_timestamp)
$$;
revoke all on function public.billing_reconciliation_scheduler_tick(text,text,bigint) from public, anon, authenticated;
grant execute on function public.billing_reconciliation_scheduler_tick(text,text,bigint) to anon, authenticated;

create or replace function billing_private.configure_scheduler(
  p_backend_secret text, p_worker_secret text
) returns jsonb language plpgsql security definer set search_path='' as $$
declare secret_id uuid; scheduled_job bigint;
begin
  perform public.workbench_check_backend(p_backend_secret);
  if p_worker_secret is null or octet_length(p_worker_secret) <> 64 or not exists (
    select 1 from billing_private.worker_capability
    where secret_hash=pg_catalog.sha256(pg_catalog.convert_to(p_worker_secret,'UTF8'))
  ) then raise exception 'worker capability required' using errcode='42501'; end if;
  select id into secret_id from vault.secrets where name='stardust_billing_reconcile_token';
  if secret_id is null then
    perform vault.create_secret(p_worker_secret,'stardust_billing_reconcile_token',
      'Credential used to sign short-lived billing scheduler ticks');
  else
    perform vault.update_secret(secret_id,p_worker_secret,'stardust_billing_reconcile_token',
      'Credential used to sign short-lived billing scheduler ticks');
  end if;
  select cron.schedule('stardust-billing-reconcile','*/5 * * * *',$command$
    select net.http_post(
      url := 'https://agent.stardust.website/api/admin/reconcile-usage',
      headers := jsonb_build_object(
        'Content-Type','application/json',
        'User-Agent','StardustBillingReconciler/1.0',
        'x-billing-scheduler-timestamp',t.tick,
        'x-billing-scheduler-signature',encode(extensions.hmac(
          'stardust-billing-tick:' || t.tick, t.secret, 'sha256'),'hex')
      ),
      body := '{}'::jsonb,
      timeout_milliseconds := 55000
    ) from (
      select extract(epoch from date_trunc('minute',clock_timestamp()))::bigint::text as tick,
        (select decrypted_secret from vault.decrypted_secrets
         where name='stardust_billing_reconcile_token') as secret
    ) t
  $command$) into scheduled_job;
  return jsonb_build_object('status','configured','job_id',scheduled_job);
end $$;
