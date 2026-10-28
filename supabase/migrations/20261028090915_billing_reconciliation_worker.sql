-- Applied to production as migration 20261028090915.
-- Reconciliation runs separately from user requests. No refund or guessed charge.
create schema if not exists billing_private;
revoke all on schema billing_private from public, anon, authenticated;
grant usage on schema billing_private to anon, authenticated;

create table billing_private.worker_capability (
  singleton boolean primary key default true check (singleton),
  secret_hash bytea not null check (octet_length(secret_hash) = 32)
);
create table billing_private.reconciliation_queue (
  request_id text primary key references public.workbench_usage_events(request_id) on delete cascade,
  attempts integer not null default 0 check (attempts >= 0),
  next_attempt_at timestamptz not null default now(),
  lease_id uuid,
  lease_expires_at timestamptz,
  last_result text not null default '',
  last_alert_at timestamptz
);
alter table billing_private.worker_capability enable row level security;
alter table billing_private.reconciliation_queue enable row level security;
revoke all on all tables in schema billing_private from public, anon, authenticated;
create index billing_reconciliation_due_idx on billing_private.reconciliation_queue(next_attempt_at);
create index billing_usage_pending_age_idx on public.workbench_usage_events(created_at)
  where status in ('reserved', 'needs_review');

create function billing_private.reconcile_rpc(
  p_backend_secret text, p_worker_secret text, p_action text, p_args jsonb
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  q billing_private.reconciliation_queue%rowtype;
  e public.workbench_usage_events%rowtype;
  result jsonb;
  alert_count integer;
  reason text;
begin
  perform public.workbench_check_backend(p_backend_secret);
  if p_worker_secret is null or octet_length(p_worker_secret) <> 64 or not exists (
    select 1 from billing_private.worker_capability
    where secret_hash = pg_catalog.sha256(pg_catalog.convert_to(p_worker_secret, 'UTF8'))
  ) then
    raise exception 'worker capability required' using errcode = '42501';
  end if;

  if p_action in ('claim', 'alerts') then
    insert into billing_private.reconciliation_queue(request_id)
    select u.request_id from public.workbench_usage_events u
    where u.status in ('reserved', 'needs_review') and u.created_at < now() - interval '2 minutes'
      and not exists (select 1 from billing_private.reconciliation_queue x where x.request_id=u.request_id)
    order by u.created_at limit 100
    on conflict (request_id) do nothing;
  end if;

  if p_action = 'claim' then
    select x.* into q from billing_private.reconciliation_queue x
    join public.workbench_usage_events u on u.request_id=x.request_id
    where u.status='reserved' and x.next_attempt_at <= now()
      and (x.lease_expires_at is null or x.lease_expires_at <= now())
    order by x.next_attempt_at, u.created_at
    for update of x skip locked limit 1;
    if not found then return jsonb_build_object('status','idle'); end if;
    update billing_private.reconciliation_queue set
      attempts=attempts+1, lease_id=gen_random_uuid(), lease_expires_at=now()+interval '2 minutes'
    where request_id=q.request_id returning * into q;
    select * into e from public.workbench_usage_events where request_id=q.request_id;
    return jsonb_build_object('status','claimed','request_id',e.request_id,
      'model',e.model,'api_key_id',e.api_key_id,'lease_id',q.lease_id);
  elsif p_action = 'alerts' then
    with due as (
      select x.request_id from billing_private.reconciliation_queue x
      join public.workbench_usage_events u on u.request_id=x.request_id
      where u.status in ('reserved','needs_review') and u.created_at < now()-interval '1 hour'
        and (x.last_alert_at is null or x.last_alert_at < now()-interval '6 hours')
      order by u.created_at for update of x skip locked limit 100
    ), updated as (
      update billing_private.reconciliation_queue x set last_alert_at=now()
      from due where x.request_id=due.request_id returning x.request_id
    ) select count(*) into alert_count from updated;
    return jsonb_build_object('status','checked','alert_count',alert_count);
  elsif p_action in ('complete','defer') then
    select * into q from billing_private.reconciliation_queue
    where request_id=p_args->>'request_id' for update;
    if not found or q.lease_id::text is distinct from p_args->>'lease_id'
      or q.lease_expires_at is null or q.lease_expires_at <= now() then
      return jsonb_build_object('status','lease_expired');
    end if;
    select * into e from public.workbench_usage_events where request_id=q.request_id for update;
    if not found or e.status <> 'reserved' then
      update billing_private.reconciliation_queue set lease_id=null,lease_expires_at=null,
        next_attempt_at='infinity',last_result='already_resolved' where request_id=q.request_id;
      return jsonb_build_object('status','already_resolved');
    end if;
    if p_action='complete' then
      if coalesce(p_args->>'actual_micro_cny','') !~ '^[0-9]{1,12}$'
        or coalesce(p_args->>'provider_request_id','') !~ '^[a-zA-Z0-9_-]{1,128}$' then
        raise exception 'invalid confirmed receipt' using errcode='22023';
      end if;
      result := public.workbench_settle_usage(q.request_id,
        (p_args->>'actual_micro_cny')::bigint, p_args->>'provider_request_id');
      update billing_private.reconciliation_queue set lease_id=null,lease_expires_at=null,
        next_attempt_at='infinity',last_result=result->>'status' where request_id=q.request_id;
      return result;
    end if;
    reason := p_args->>'reason';
    if reason not in ('receipt_not_found','ambiguous_receipts','ownership_mismatch',
      'unsupported_model','invalid_receipt_pricing','invalid_provider_id',
      'provider_unavailable','model_mismatch','invalid_key','incomplete_scan') or reason is null then
      raise exception 'invalid retry reason' using errcode='22023';
    end if;
    update billing_private.reconciliation_queue set lease_id=null,lease_expires_at=null,
      next_attempt_at=now()+make_interval(mins => least(5 * power(2,least(attempts-1,6))::integer, 360)),
      last_result=reason where request_id=q.request_id;
    return jsonb_build_object('status','deferred');
  end if;
  raise exception 'invalid worker action' using errcode='22023';
end $$;
revoke all on function billing_private.reconcile_rpc(text,text,text,jsonb) from public, anon, authenticated;
grant execute on function billing_private.reconcile_rpc(text,text,text,jsonb) to anon, authenticated;

create function public.billing_reconciliation_worker(
  p_backend_secret text,p_worker_secret text,p_action text,p_args jsonb
) returns jsonb language sql security invoker set search_path='' as $$
  select billing_private.reconcile_rpc(p_backend_secret,p_worker_secret,p_action,p_args)
$$;
revoke all on function public.billing_reconciliation_worker(text,text,text,jsonb) from public, anon, authenticated;
grant execute on function public.billing_reconciliation_worker(text,text,text,jsonb) to anon, authenticated;
