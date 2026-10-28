-- Applied to production as migration 20261028092403.
-- Supabase Cron provides a second, predictable trigger; GitHub remains the
-- independently scheduled alert channel. The bearer token lives in Vault, not
-- in cron.job or in the migration.
create extension if not exists pg_cron;
create extension if not exists pg_net;
revoke all on schema cron, net from public, anon, authenticated;
revoke all on all tables in schema net from public, anon, authenticated;
revoke all on all tables in schema cron from public, anon, authenticated;

create function billing_private.configure_scheduler(
  p_backend_secret text, p_worker_secret text
) returns jsonb language plpgsql security definer set search_path='' as $$
declare
  secret_id uuid;
  scheduled_job bigint;
begin
  perform public.workbench_check_backend(p_backend_secret);
  if p_worker_secret is null or octet_length(p_worker_secret) <> 64 or not exists (
    select 1 from billing_private.worker_capability
    where secret_hash=pg_catalog.sha256(pg_catalog.convert_to(p_worker_secret,'UTF8'))
  ) then
    raise exception 'worker capability required' using errcode='42501';
  end if;
  select id into secret_id from vault.secrets where name='stardust_billing_reconcile_token';
  if secret_id is null then
    perform vault.create_secret(p_worker_secret,'stardust_billing_reconcile_token',
      'Bearer credential for the fixed billing reconciliation endpoint');
  else
    perform vault.update_secret(secret_id,p_worker_secret,'stardust_billing_reconcile_token',
      'Bearer credential for the fixed billing reconciliation endpoint');
  end if;
  select cron.schedule(
    'stardust-billing-reconcile', '*/5 * * * *',
    $command$
      select net.http_post(
        url := 'https://agent.stardust.website/api/admin/reconcile-usage',
        headers := jsonb_build_object(
          'Content-Type','application/json',
          'User-Agent','StardustBillingReconciler/1.0',
          'x-billing-scheduler-mode','background',
          'x-billing-probe-token',(select decrypted_secret from vault.decrypted_secrets
            where name='stardust_billing_reconcile_token')
        ),
        body := '{}'::jsonb,
        timeout_milliseconds := 55000
      )
    $command$
  ) into scheduled_job;
  return jsonb_build_object('status','configured','job_id',scheduled_job);
end $$;
revoke all on function billing_private.configure_scheduler(text,text) from public, anon, authenticated;
grant execute on function billing_private.configure_scheduler(text,text) to anon, authenticated;
create function public.billing_reconciliation_scheduler(
  p_backend_secret text,p_worker_secret text
) returns jsonb language sql security invoker set search_path='' as $$
  select billing_private.configure_scheduler(p_backend_secret,p_worker_secret)
$$;
revoke all on function public.billing_reconciliation_scheduler(text,text) from public, anon, authenticated;
grant execute on function public.billing_reconciliation_scheduler(text,text) to anon, authenticated;
