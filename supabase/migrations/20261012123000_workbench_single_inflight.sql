-- A delayed provider usage log must not let a user pile up uncertain charges.
create index workbench_usage_unresolved_user_idx
  on public.workbench_usage_events(user_id)
  where status in ('reserved','needs_review');

create or replace function public.workbench_backend_reserve_usage(
  p_user_id uuid,p_request_id text,p_model text,p_reserved_micro_cny bigint,
  p_api_key_id bigint,p_server_secret text
) returns jsonb language plpgsql security definer
set search_path=pg_catalog,public as $$
begin
  perform public.workbench_check_backend(p_server_secret);
  if p_user_id is distinct from (select auth.uid()) then
    raise exception 'identity mismatch' using errcode='42501';
  end if;
  insert into public.workbench_credit_wallets(user_id)
  values(p_user_id) on conflict(user_id) do nothing;
  perform 1 from public.workbench_credit_wallets
  where user_id=p_user_id for update;
  if exists(
    select 1 from public.workbench_usage_events
    where user_id=p_user_id and status in ('reserved','needs_review')
      and request_id<>p_request_id
  ) then
    raise exception 'prior model charge pending review' using errcode='55000';
  end if;
  return public.workbench_reserve_usage(
    p_user_id,p_request_id,p_model,p_reserved_micro_cny,p_api_key_id
  );
end $$;
