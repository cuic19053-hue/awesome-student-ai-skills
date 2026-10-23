-- Return only the minimum context needed by the Vercel inference relay.
-- The Worker capability and active lease are required; encrypted user config
-- stays inside Vercel and is never returned to the document Worker.
create function material_private.worker_context(
  p_secret text,
  p_job_id text,
  p_lease text
) returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  j public.material_jobs%rowtype;
begin
  if p_job_id !~ '^[a-f0-9]{32}$' or p_lease !~ '^[a-f0-9]{32}$' then
    raise exception 'invalid worker lease' using errcode='42501';
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
  if not coalesce((j.payload->>'paid')::boolean,false) then
    raise exception 'model inference not confirmed' using errcode='42501';
  end if;
  return jsonb_build_object(
    'id', j.id,
    'project_id', j.project_id,
    'owner_id', j.owner_id,
    'kind', j.kind,
    'target', j.target,
    'payload', jsonb_build_object(
      'paid', j.payload->'paid',
      'platform', j.payload->'platform',
      'config', j.payload->'config',
      'config_ciphertext', j.payload->'config_ciphertext',
      'spec', j.payload->'spec',
      'image_path', j.payload->'image_path',
      'image_upload_url', j.payload->'image_upload_url',
      'image_download_url', j.payload->'image_download_url'
    )
  );
end
$$;

revoke all on function material_private.worker_context(text,text,text) from public;
grant execute on function material_private.worker_context(text,text,text) to anon,authenticated;

create function public.material_worker_context(
  p_secret text,
  p_job_id text,
  p_lease text
) returns jsonb
language sql
security invoker
set search_path=''
as $$
  select material_private.worker_context(p_secret,p_job_id,p_lease)
$$;

revoke all on function public.material_worker_context(text,text,text) from public;
grant execute on function public.material_worker_context(text,text,text) to anon,authenticated;
