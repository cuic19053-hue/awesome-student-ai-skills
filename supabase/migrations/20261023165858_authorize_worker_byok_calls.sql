-- Bound BYOK calls too: the provider API key never leaves Vercel, and a
-- Worker capability cannot replay an active job without consuming its budget.
create function material_private.authorize_byok_call(
  p_secret text,
  p_job_id text,
  p_lease text,
  p_call_id text,
  p_operation text
) returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  j public.material_jobs%rowtype;
  max_calls integer;
  call_marker text;
begin
  if p_job_id !~ '^[a-f0-9]{32}$'
      or p_lease !~ '^[a-f0-9]{32}$'
      or p_call_id !~ '^[a-f0-9]{32}$' then
    raise exception 'invalid worker request' using errcode='42501';
  end if;
  if not exists (
    select 1
    from material_private.worker_capability
    where secret_hash=sha256(convert_to(p_secret,'UTF8'))
  ) then
    raise exception 'worker capability rejected' using errcode='42501';
  end if;
  select * into j
  from public.material_jobs
  where id=p_job_id
  for update;
  if not found or j.status<>'running' or j.lease is distinct from p_lease
      or j.lease_until<now() then
    raise exception 'lease expired or job cancelled' using errcode='42501';
  end if;
  if not coalesce((j.payload->>'paid')::boolean,false)
      or coalesce((j.payload->>'platform')::boolean,false) then
    raise exception 'not a BYOK paid job' using errcode='42501';
  end if;
  if p_operation='text' and j.kind not in ('section','outline','plan') then
    raise exception 'text operation not allowed' using errcode='42501';
  elsif p_operation='image' and not (
      j.kind='figure' and j.payload->'spec'->>'renderer'='gpt'
  ) then
    raise exception 'image operation not allowed' using errcode='42501';
  elsif p_operation not in ('text','image') then
    raise exception 'invalid operation' using errcode='42501';
  end if;
  max_calls:=case when j.kind='section' then 6 else 1 end;
  call_marker:='byok:'||p_call_id;
  if j.calls @> jsonb_build_array(call_marker)
      or jsonb_array_length(j.calls)>=max_calls then
    raise exception 'BYOK call budget exceeded' using errcode='42501';
  end if;
  update public.material_jobs
  set calls=calls||jsonb_build_array(call_marker),updated_at=now()
  where id=j.id;
  return jsonb_build_object('ok',true);
end
$$;

revoke all on function material_private.authorize_byok_call(text,text,text,text,text) from public;
grant execute on function material_private.authorize_byok_call(text,text,text,text,text) to anon,authenticated;

create function public.material_worker_authorize_byok(
  p_secret text,
  p_job_id text,
  p_lease text,
  p_call_id text,
  p_operation text
) returns jsonb
language sql
security invoker
set search_path=''
as $$
  select material_private.authorize_byok_call(p_secret,p_job_id,p_lease,p_call_id,p_operation)
$$;

revoke all on function public.material_worker_authorize_byok(text,text,text,text,text) from public;
grant execute on function public.material_worker_authorize_byok(text,text,text,text,text) to anon,authenticated;
