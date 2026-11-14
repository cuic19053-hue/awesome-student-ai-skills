-- Persist the user-visible input and response associated with each metered
-- model request. Content stays project-scoped and is never written to billing
-- or observability events.
create table public.workbench_model_interactions (
  request_id text primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id text not null references public.projects(id) on delete cascade,
  model text not null check (length(model) between 1 and 120),
  input_text text not null default '',
  output_text text not null default '',
  status text not null default 'started'
    check (status in ('started','completed','failed','unknown')),
  error_code text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (length(input_text) <= 200000),
  check (length(output_text) <= 200000),
  check (error_code is null or error_code ~ '^[A-Z_]{1,80}$')
);

create index workbench_model_interactions_project_created_idx
  on public.workbench_model_interactions(project_id, created_at desc);
create index workbench_model_interactions_user_created_idx
  on public.workbench_model_interactions(user_id, created_at desc);

alter table public.workbench_model_interactions enable row level security;
revoke all on public.workbench_model_interactions from public, anon, authenticated;
grant select on public.workbench_model_interactions to authenticated;
create policy workbench_model_interactions_owner_read
  on public.workbench_model_interactions for select to authenticated
  using (user_id = (select auth.uid()));

create function public.workbench_backend_record_model_interaction(
  p_user_id uuid,
  p_project_id text,
  p_request_id text,
  p_model text,
  p_input_text text,
  p_output_text text,
  p_status text,
  p_error_code text,
  p_server_secret text
) returns void language plpgsql security definer
set search_path = pg_catalog, public as $$
begin
  perform public.workbench_check_backend(p_server_secret);
  if p_user_id is distinct from (select auth.uid()) then
    raise exception 'identity mismatch' using errcode='42501';
  end if;
  if p_project_id is null or p_request_id is null
     or p_request_id !~ '^(o2x1_|o90v1_|m12_)[a-f0-9]{32}$'
     or p_model is null or length(p_model) not between 1 and 120
     or coalesce(length(p_input_text),0) > 200000
     or coalesce(length(p_output_text),0) > 200000
     or p_status not in ('started','completed','failed','unknown')
     or (p_error_code is not null and p_error_code !~ '^[A-Z_]{1,80}$') then
    raise exception 'invalid model interaction' using errcode='22023';
  end if;
  if not exists (
    select 1 from public.projects where id=p_project_id and owner_id=p_user_id
  ) then
    raise exception 'project ownership mismatch' using errcode='42501';
  end if;

  insert into public.workbench_model_interactions(
    request_id,user_id,project_id,model,input_text,output_text,status,error_code
  ) values (
    p_request_id,p_user_id,p_project_id,p_model,coalesce(p_input_text,''),
    coalesce(p_output_text,''),p_status,p_error_code
  )
  on conflict (request_id) do update set
    input_text=case when excluded.input_text<>'' then excluded.input_text
                    else workbench_model_interactions.input_text end,
    output_text=case when excluded.output_text<>'' then excluded.output_text
                     else workbench_model_interactions.output_text end,
    status=excluded.status,
    error_code=excluded.error_code,
    updated_at=now()
  where workbench_model_interactions.user_id=excluded.user_id
    and workbench_model_interactions.project_id=excluded.project_id
    and workbench_model_interactions.model=excluded.model;
  if not found then
    raise exception 'model interaction identity mismatch' using errcode='42501';
  end if;
end $$;
revoke all on function public.workbench_backend_record_model_interaction(
  uuid,text,text,text,text,text,text,text,text
) from public, anon;
grant execute on function public.workbench_backend_record_model_interaction(
  uuid,text,text,text,text,text,text,text,text
) to authenticated;

create function material_private.record_model_interaction(
  p_secret text,
  p_job_id text,
  p_lease text,
  p_request_id text,
  p_model text,
  p_input_text text,
  p_output_text text,
  p_status text,
  p_error_code text
) returns boolean language plpgsql security definer set search_path='' as $$
declare j public.material_jobs%rowtype;
begin
  if not exists(select 1 from material_private.worker_capability
    where secret_hash=sha256(convert_to(p_secret,'UTF8'))) then
    raise exception 'worker capability rejected' using errcode='42501';
  end if;
  select * into j from public.material_jobs
  where id=p_job_id and status='running' and lease=p_lease and lease_until>=now()
  for update;
  if not found or not j.calls ? p_request_id then
    raise exception 'worker lease or request invalid' using errcode='42501';
  end if;
  if p_model not in ('deepseek-v4-flash','gpt-image-2')
     or (j.kind in ('section','outline','plan') and p_model<>'deepseek-v4-flash')
     or (j.kind='figure' and p_model<>'gpt-image-2')
     or p_request_id !~ '^(o2x1_|o90v1_|m12_)[a-f0-9]{32}$'
     or p_status not in ('started','completed','failed','unknown')
     or coalesce(length(p_input_text),0)>200000
     or coalesce(length(p_output_text),0)>200000
     or (p_error_code is not null and p_error_code !~ '^[A-Z_]{1,80}$') then
    raise exception 'invalid model interaction' using errcode='22023';
  end if;
  insert into public.workbench_model_interactions(
    request_id,user_id,project_id,model,input_text,output_text,status,error_code
  ) values (
    p_request_id,j.owner_id,j.project_id,p_model,coalesce(p_input_text,''),
    coalesce(p_output_text,''),p_status,p_error_code
  ) on conflict(request_id) do update set
    input_text=case when excluded.input_text<>'' then excluded.input_text
                    else workbench_model_interactions.input_text end,
    output_text=case when excluded.output_text<>'' then excluded.output_text
                     else workbench_model_interactions.output_text end,
    status=excluded.status,error_code=excluded.error_code,updated_at=now()
  where workbench_model_interactions.user_id=excluded.user_id
    and workbench_model_interactions.project_id=excluded.project_id
    and workbench_model_interactions.model=excluded.model;
  if not found then
    raise exception 'model interaction identity mismatch' using errcode='42501';
  end if;
  return true;
end $$;
revoke all on function material_private.record_model_interaction(
  text,text,text,text,text,text,text,text,text
) from public, anon, authenticated;

create function public.material_worker_record_model_interaction(
  p_secret text,p_job_id text,p_lease text,p_request_id text,p_model text,
  p_input_text text default '',p_output_text text default '',
  p_status text default 'started',p_error_code text default null
) returns boolean language sql security invoker set search_path='' as $$
  select material_private.record_model_interaction(
    p_secret,p_job_id,p_lease,p_request_id,p_model,p_input_text,p_output_text,p_status,p_error_code
  )
$$;
revoke all on function public.material_worker_record_model_interaction(
  text,text,text,text,text,text,text,text,text
) from public;
grant execute on function public.material_worker_record_model_interaction(
  text,text,text,text,text,text,text,text,text
) to anon, authenticated;
