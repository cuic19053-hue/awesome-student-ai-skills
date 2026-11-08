-- Fail closed until the separate server-side submission capability is provisioned.
-- Existing tasks have no trustworthy submission provenance: never replay/apply them.
begin;

create table material_private.submit_capability (
 singleton boolean primary key default true check (singleton),
 secret_hash bytea not null check (octet_length(secret_hash) = 32)
);
alter table material_private.submit_capability enable row level security;
revoke all on material_private.submit_capability from public, anon, authenticated;

alter table public.material_jobs add column trusted_submission boolean not null default false;
-- Stop the old worker's existing claim query from taking untrusted queued jobs.
-- Retain payload/results for reconciliation. In-flight upstream requests can
-- still settle externally even though their previous lease is invalidated.
update public.material_jobs
 set status='needs_review', lease=null, lease_until=null,
     error='历史任务执行状态待核对，请核对结果与费用', updated_at=now()
 where status in ('pending','running');

revoke all on public.material_jobs from public, anon, authenticated;
-- Keep manual revision saves, but reserve the job association to trusted code.
-- The user-writable source column remains descriptive, not an audit proof.
revoke insert on public.material_revisions from authenticated;
grant insert(project_id,section_id,content,source,review_card) on public.material_revisions to authenticated;
drop function public.material_jobs_api(text,jsonb);
drop function public.material_apply(jsonb);

create function material_private.submission_authorized(p_secret text) returns boolean
language sql stable security definer set search_path='' as $$
 select length(p_secret)>=32 and exists (
  select 1 from material_private.submit_capability
  where secret_hash=sha256(convert_to(p_secret,'UTF8'))
 )
$$;
revoke all on function material_private.submission_authorized(text) from public, anon, authenticated;

create function material_private.public_job(j public.material_jobs) returns jsonb
language sql stable security invoker set search_path='' as $$
 select (to_jsonb(j)-array['payload','lease','calls','lease_until','idempotency','trusted_submission']) ||
  case when not j.trusted_submission and j.status='completed'
   then jsonb_build_object('status','needs_review','error','历史任务结果待核对')
   else '{}'::jsonb end
$$;
revoke all on function material_private.public_job(public.material_jobs) from public, anon, authenticated;

create function material_private.jobs_api(p_action text,p_args jsonb,p_secret text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare j public.material_jobs%rowtype; uid uuid:=(select auth.uid());
 page_offset integer; page_limit integer; path_prefix text;
begin
 if uid is null then raise exception 'authentication required' using errcode='42501'; end if;
 if not exists(select 1 from public.projects where id=p_args->>'project_id' and owner_id=uid) then
  raise exception 'project not owned' using errcode='42501'; end if;
 if p_action in ('submit','raw','applied','cleanup_paths') and
    not coalesce(material_private.submission_authorized(p_secret),false) then
  raise exception 'submission capability rejected' using errcode='42501';
 end if;
 if p_action='has_jobs' then
  return to_jsonb(exists(select 1 from public.material_jobs where project_id=p_args->>'project_id' and owner_id=uid));
 elsif p_action='cleanup_paths' then
  page_offset:=coalesce((p_args->>'offset')::integer,0);
  page_limit:=coalesce((p_args->>'limit')::integer,500);
  if page_offset<0 or page_offset>1000000 or page_limit<1 or page_limit>500 then
   raise exception 'invalid page';
  end if;
  path_prefix:=uid::text||'/'||(p_args->>'project_id')||'/_material/';
  return coalesce((select jsonb_agg(jsonb_build_object(
   'output_path',case when left(x.payload->>'output_path',length(path_prefix))=path_prefix
    and substring(x.payload->>'output_path' from length(path_prefix)+1) ~ '^[a-f0-9]{32}[.]zip$'
    then x.payload->>'output_path' else null end,
   'image_path',case when left(x.payload->>'image_path',length(path_prefix))=path_prefix
    and substring(x.payload->>'image_path' from length(path_prefix)+1) ~ '^[a-f0-9]{32}-image[.]png$'
    then x.payload->>'image_path' else null end) order by x.created_at,x.id)
   from (select * from public.material_jobs where project_id=p_args->>'project_id' and owner_id=uid
     order by created_at,id offset page_offset limit page_limit) x),'[]'::jsonb);
 elsif p_action='submit' then
  if length(p_args->>'idempotency') not between 1 and 120 or length((p_args->'payload')::text)>8000000 then
   raise exception 'invalid job'; end if;
  if not exists(select 1 from public.projects where id=p_args->>'project_id'
   and lower(replace(btrim(coalesce(state_json->>'skill_id','innovation-research')), '_', '-')) = any(array[
    'national-project-eval','motivation-scholarship','university-scholarship','enterprise-scholarship',
    'single-scholarship','grant-application','outstanding-student','outstanding-graduate',
    'outstanding-cadre','civilized-student','class-collective','youth-league-application',
    'innovation-research','entrepreneurship-training','entrepreneurship-practice','university-research',
    'college-research','challenge-cup','internet-plus','social-survey','volunteer-teaching',
    'policy-lecture','tech-service','western-plan','graduate-recommendation','selected-graduate',
    'major-transfer','military-enlistment','csc-scholarship','exchange-program','internet-plus-red-tour',
    'outstanding-thesis','national-scholarship','summary-report','youth-league-conversion'
   ]::text[])) then raise exception 'unsupported type'; end if;
  perform 1 from public.projects where id=p_args->>'project_id' and owner_id=uid for update;
  select * into j from public.material_jobs where project_id=p_args->>'project_id' and owner_id=uid and
   (idempotency=p_args->>'idempotency' or (kind=p_args->>'kind' and target=p_args->>'target' and status in ('pending','running')))
   order by created_at limit 1;
  if not found then
   if (select material_revision from public.projects where id=p_args->>'project_id') <>
     (p_args->'payload'->>'base_revision')::bigint then return jsonb_build_object('conflict',true); end if;
   insert into public.material_jobs(id,project_id,owner_id,kind,target,idempotency,payload,trusted_submission)
   values(p_args->>'id',p_args->>'project_id',uid,p_args->>'kind',p_args->>'target',p_args->>'idempotency',p_args->'payload',true) returning * into j;
  end if;
 elsif p_action='list' then
  return coalesce((select jsonb_agg(x.item order by x.created_at desc,x.id desc) from (
   select material_private.public_job(jobrow) as item,jobrow.created_at,jobrow.id from public.material_jobs jobrow
    where jobrow.project_id=p_args->>'project_id' and jobrow.owner_id=uid order by jobrow.created_at desc,jobrow.id desc limit 30) x),'[]'::jsonb);
 elsif p_action='find' then
  select * into j from public.material_jobs where project_id=p_args->>'project_id' and owner_id=uid
   and idempotency=p_args->>'idempotency' limit 1;
  if not found then return null; end if;
 else
  select * into j from public.material_jobs where id=p_args->>'id' and project_id=p_args->>'project_id' and owner_id=uid for update;
  if not found then return null; end if;
  if p_action in ('raw','applied') and not j.trusted_submission then
   raise exception 'historical job requires review' using errcode='42501'; end if;
  if p_action='raw' then return to_jsonb(j)-'trusted_submission'; end if;
  if p_action='cancel' and j.status in ('pending','running') then
   update public.material_jobs set status='cancelled',payload=payload-'config_ciphertext',updated_at=now(),
    error='已取消后续执行，已发生的调用费用仍按原规则核对' where id=j.id returning * into j;
  elsif p_action='applied' and j.status='completed' then
   update public.material_jobs set result=p_args->'result',updated_at=now() where id=j.id returning * into j;
  elsif p_action<>'get' then raise exception 'invalid action'; end if;
 end if;
 return material_private.public_job(j);
end $$;
revoke all on function material_private.jobs_api(text,jsonb,text) from public, anon;
grant execute on function material_private.jobs_api(text,jsonb,text) to authenticated;

create function public.material_jobs_api(p_action text,p_args jsonb,p_secret text default null) returns jsonb
language sql security invoker set search_path='' as $$
 select material_private.jobs_api(p_action,p_args,p_secret)
$$;
revoke all on function public.material_jobs_api(text,jsonb,text) from public, anon;
grant execute on function public.material_jobs_api(text,jsonb,text) to authenticated;

create function material_private.apply_job(p_args jsonb,p_secret text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare p public.projects%rowtype; j public.material_jobs%rowtype; conflict boolean; fields jsonb; r jsonb;
begin
 if (select auth.uid()) is null then raise exception 'authentication required' using errcode='42501'; end if;
 if not coalesce(material_private.submission_authorized(p_secret),false) then
  raise exception 'submission capability rejected' using errcode='42501'; end if;
 select * into p from public.projects where id=p_args->>'project_id' and owner_id=(select auth.uid()) for update;
 if not found then raise exception 'project not owned' using errcode='42501'; end if;
 select * into j from public.material_jobs where id=p_args->>'id' and project_id=p.id and owner_id=(select auth.uid()) for update;
 if not found or j.status<>'completed' or not j.trusted_submission then raise exception 'job not applicable'; end if;
 if coalesce((j.result->>'applied')::boolean,false) then return j.result; end if;
 conflict:=p.material_revision<>(j.payload->>'base_revision')::bigint;
 r:=j.result; fields:=p_args->'fields';
 if j.kind='section' then
  insert into public.material_revisions(project_id,section_id,content,source,review_card,job_id)
  values(p.id,j.target,r->>'content',case when conflict then 'ai_generated_alternative' else 'ai_generated' end,r->'review_card',j.id)
  on conflict(job_id) do nothing;
 end if;
 if conflict then
  r:=r||jsonb_build_object('conflict_status','user_edit_preserved','notice','输入已变化，结果保留为备选，未覆盖当前项目');
 elsif fields<>'{}'::jsonb then
  update public.projects set state_json=coalesce(fields->'state',state_json),
   outline_json=coalesce(fields->'outline',outline_json),
   sections_json=coalesce(fields->'sections',sections_json),diagrams_json=coalesce(fields->'diagrams',diagrams_json),
   updated_at=now() where id=p.id;
 end if;
 r:=r||jsonb_build_object('applied',true);
 update public.material_jobs set result=r,updated_at=now() where id=j.id;
 return r;
end $$;
revoke all on function material_private.apply_job(jsonb,text) from public, anon;
grant execute on function material_private.apply_job(jsonb,text) to authenticated;
create function public.material_apply(p_args jsonb,p_secret text default null) returns jsonb
language sql security invoker set search_path='' as $$
 select material_private.apply_job(p_args,p_secret)
$$;
revoke all on function public.material_apply(jsonb,text) from public, anon;
grant execute on function public.material_apply(jsonb,text) to authenticated;
commit;
