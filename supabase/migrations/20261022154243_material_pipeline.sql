-- Additive, pilot-only persistence. Never touches wallets, pricing or trials.
begin;
create schema if not exists material_private;
revoke all on schema material_private from public;
grant usage on schema material_private to anon, authenticated;
create table material_private.worker_capability (
  singleton boolean primary key default true check(singleton), secret_hash bytea not null
);
revoke all on material_private.worker_capability from public, anon, authenticated;
-- Provision the SHA-256 hash out of band; no secret is committed in migrations.
alter table public.projects add column if not exists material_revision bigint not null default 0;
create function material_private.bump_revision() returns trigger language plpgsql
set search_path='' as $$ begin new.material_revision=old.material_revision+1; return new; end $$;
create trigger material_revision_update before update on public.projects
for each row execute function material_private.bump_revision();
revoke all on function material_private.bump_revision() from public,anon,authenticated;

create table public.material_jobs (
 id text primary key check(id ~ '^[a-f0-9]{32}$'),
 project_id text not null references public.projects(id) on delete cascade,
 owner_id uuid not null references auth.users(id) on delete cascade,
 kind text not null check(kind in ('section','figure','export','outline','plan')),
 target text not null, idempotency text not null,
 payload jsonb not null,
 status text not null default 'pending' check(status in ('pending','running','completed','failed','cancelled','needs_review')),
 step text not null default 'queued', result jsonb not null default '{}', error text not null default '',
 lease text, lease_until timestamptz, calls jsonb not null default '[]',
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 unique(project_id,idempotency)
);
create index material_jobs_owner_project on public.material_jobs(owner_id,project_id,created_at desc);
create index material_jobs_queue on public.material_jobs(created_at) where status='pending';
create unique index material_jobs_one_active on public.material_jobs(project_id,kind,target) where status in ('pending','running');
alter table public.material_jobs enable row level security;
revoke all on public.material_jobs from public,anon;
grant select,insert,update on public.material_jobs to authenticated;
create policy material_jobs_owner on public.material_jobs for all to authenticated
using(owner_id=(select auth.uid())) with check(owner_id=(select auth.uid()) and exists(
 select 1 from public.projects p where p.id=project_id and p.owner_id=(select auth.uid())));

create table public.material_revisions (
 id bigint generated always as identity primary key, project_id text not null references public.projects(id) on delete cascade,
 section_id text not null, content text not null, source text not null, review_card jsonb,
 job_id text unique, created_at timestamptz not null default now()
);
create index material_revisions_project on public.material_revisions(project_id,section_id,id desc);
alter table public.material_revisions enable row level security;
revoke all on public.material_revisions from public,anon;
grant select,insert on public.material_revisions to authenticated;
grant usage,select on sequence public.material_revisions_id_seq to authenticated;
create policy material_revisions_read on public.material_revisions for select to authenticated using(exists(
 select 1 from public.projects p where p.id=project_id and p.owner_id=(select auth.uid())));
create policy material_revisions_insert on public.material_revisions for insert to authenticated with check(exists(
 select 1 from public.projects p where p.id=project_id and p.owner_id=(select auth.uid())));

-- RLS-scoped CAS for project JSON and metadata in one row-lock transaction.
create function public.material_patch(p_project_id text,p_revision bigint,p_fields jsonb) returns jsonb
language plpgsql security invoker set search_path='' as $$
declare v public.projects%rowtype;
begin
 if (select auth.uid()) is null then raise exception 'authentication required' using errcode='42501'; end if;
 select * into v from public.projects where id=p_project_id and owner_id=(select auth.uid()) for update;
 if not found then return null; end if;
 if v.material_revision<>p_revision then return jsonb_build_object('conflict',true); end if;
 update public.projects set
 title=case when p_fields?'title' then p_fields->>'title' else title end,
 school=case when p_fields?'school' then p_fields->>'school' else school end,
 level=case when p_fields?'level' then p_fields->>'level' else level end,
 discipline=case when p_fields?'discipline' then p_fields->>'discipline' else discipline end,
 state_json=coalesce(p_fields->'state',state_json), outline_json=coalesce(p_fields->'outline',outline_json),
 sections_json=coalesce(p_fields->'sections',sections_json), diagrams_json=coalesce(p_fields->'diagrams',diagrams_json),
 template_document_id=case when p_fields?'template_document_id' then p_fields->>'template_document_id' else template_document_id end,
 updated_at=now() where id=p_project_id returning * into v;
 return to_jsonb(v);
end $$;
revoke all on function public.material_patch(text,bigint,jsonb) from public,anon;
grant execute on function public.material_patch(text,bigint,jsonb) to authenticated;

create function public.material_jobs_api(p_action text,p_args jsonb) returns jsonb
language plpgsql security invoker set search_path='' as $$
declare j public.material_jobs%rowtype; uid uuid:=(select auth.uid());
begin
 if uid is null then raise exception 'authentication required' using errcode='42501'; end if;
 if not exists(select 1 from public.projects where id=p_args->>'project_id' and owner_id=uid) then
   raise exception 'project not owned' using errcode='42501'; end if;
 if p_action='submit' then
  if length(p_args->>'idempotency') not between 1 and 120 or length((p_args->'payload')::text)>8000000 then
   raise exception 'invalid job'; end if;
  if not exists(select 1 from public.projects where id=p_args->>'project_id'
   and coalesce(state_json->>'skill_id','innovation-research')='innovation-research') then raise exception 'unsupported type'; end if;
  perform 1 from public.projects where id=p_args->>'project_id' for update;
  select * into j from public.material_jobs where project_id=p_args->>'project_id' and
   (idempotency=p_args->>'idempotency' or (kind=p_args->>'kind' and target=p_args->>'target' and status in ('pending','running')))
   order by created_at limit 1;
  if not found then
   if (select material_revision from public.projects where id=p_args->>'project_id') <>
     (p_args->'payload'->>'base_revision')::bigint then return jsonb_build_object('conflict',true); end if;
   insert into public.material_jobs(id,project_id,owner_id,kind,target,idempotency,payload)
   values(p_args->>'id',p_args->>'project_id',uid,p_args->>'kind',p_args->>'target',p_args->>'idempotency',p_args->'payload') returning * into j;
  end if;
 elsif p_action='list' then
  return coalesce((select jsonb_agg(to_jsonb(x)-'payload'-'lease'-'calls'-'lease_until') from (
   select * from public.material_jobs where project_id=p_args->>'project_id' order by created_at desc limit 30) x),'[]');
 else
  select * into j from public.material_jobs where id=p_args->>'id' and project_id=p_args->>'project_id' for update;
  if not found then return null; end if;
  if p_action='raw' then return to_jsonb(j); end if;
  if p_action='cancel' and j.status in ('pending','running') then
   update public.material_jobs set status='cancelled',payload=payload-'config_ciphertext',updated_at=now(),
    error='已取消后续执行，已发生的调用费用仍按原规则核对' where id=j.id returning * into j;
  elsif p_action='applied' and j.status='completed' then
   update public.material_jobs set result=p_args->'result',updated_at=now() where id=j.id returning * into j;
  elsif p_action<>'get' then raise exception 'invalid action'; end if;
 end if;
 return to_jsonb(j)-'payload'-'lease'-'calls'-'lease_until';
end $$;
revoke all on function public.material_jobs_api(text,jsonb) from public,anon;
grant execute on function public.material_jobs_api(text,jsonb) to authenticated;

-- Worker capability is independent of user tokens and limited to leased jobs.
create function material_private.worker_rpc(p_secret text,p_action text,p_args jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare j public.material_jobs%rowtype; request_id text; model text; r jsonb;
begin
 if not exists(select 1 from material_private.worker_capability
   where secret_hash=sha256(convert_to(p_secret,'UTF8'))) then
  raise exception 'worker capability rejected' using errcode='42501'; end if;
 if p_action='claim' then
  update public.material_jobs set status=case when coalesce((payload->>'paid')::boolean,false) then 'needs_review' else 'pending' end,
    error=case when coalesce((payload->>'paid')::boolean,false) then '租约中断，禁止盲目重复调用，请核对结果与费用' else '' end,
    payload=case when coalesce((payload->>'paid')::boolean,false) then payload-'config_ciphertext' else payload end,
    updated_at=now() where status='running' and lease_until<now();
  select * into j from public.material_jobs where status='pending' order by created_at for update skip locked limit 1;
  if not found then return null; end if;
  update public.material_jobs set status='running',lease=replace(gen_random_uuid()::text,'-',''),
    lease_until=now()+interval '120 seconds',updated_at=now() where id=j.id returning * into j;
  return to_jsonb(j);
 end if;
 select * into j from public.material_jobs where id=p_args->>'id' for update;
 if not found or j.status<>'running' or j.lease is distinct from p_args->>'lease' or j.lease_until<now() then
  raise exception 'lease expired or job cancelled' using errcode='42501'; end if;
 if p_action='heartbeat' or p_action='checkpoint' then
  update public.material_jobs set lease_until=now()+interval '120 seconds',
    step=case when p_action='checkpoint' then left(p_args->>'step',100) else step end,
    result=result||coalesce(p_args->'partial','{}'::jsonb),updated_at=now() where id=j.id;
  return jsonb_build_object('ok',true);
 elsif p_action='finish' then
  if p_args->>'status' not in ('completed','failed','needs_review') then raise exception 'invalid status'; end if;
  update public.material_jobs set status=p_args->>'status',result=result||coalesce(p_args->'result','{}'),
   error=left(coalesce(p_args->>'error',''),400),payload=payload-'config_ciphertext',updated_at=now() where id=j.id;
  return jsonb_build_object('ok',true);
 elsif p_action in ('reserve','settle','refund') then
  -- Restore identity only within this guarded transaction, never mint a JWT.
  perform set_config('request.jwt.claim.sub',j.owner_id::text,true);
  perform set_config('request.jwt.claims',jsonb_build_object('sub',j.owner_id::text,'role','authenticated')::text,true);
  request_id:=p_args->>'request_id';
  if p_action='reserve' then
   model:=p_args->>'model';
   if j.kind not in ('section','figure','outline','plan') or not coalesce((j.payload->>'platform')::boolean,false)
     or model not in ('deepseek-v4-flash','gpt-image-2')
     or (j.kind in ('section','outline','plan') and model<>'deepseek-v4-flash')
     or (j.kind='figure' and model<>'gpt-image-2')
     or jsonb_array_length(j.calls)>=(case when j.kind='section' then 6 else 1 end) then raise exception 'call budget exceeded'; end if;
   r:=public.workbench_reserve_usage(j.owner_id,request_id,model,
     case when model='gpt-image-2' then 2000000 else 200000 end,(p_args->>'api_key_id')::bigint);
   update public.material_jobs set calls=calls||jsonb_build_array(request_id) where id=j.id;
   return r;
  end if;
  if not j.calls ? request_id then raise exception 'request not owned by job' using errcode='42501'; end if;
  if p_action='settle' then return public.workbench_settle_usage(request_id,(p_args->>'amount')::bigint,p_args->>'provider_id'); end if;
  return public.workbench_refund_usage(request_id,left(p_args->>'reason',120));
 end if;
 raise exception 'invalid worker action';
end $$;
revoke all on function material_private.worker_rpc(text,text,jsonb) from public;
grant execute on function material_private.worker_rpc(text,text,jsonb) to anon,authenticated;
-- Public wrapper is invoker; privileged implementation is not in exposed schema.
create function public.material_worker_rpc(p_secret text,p_action text,p_args jsonb) returns jsonb
language sql security invoker set search_path='' as $$
 select material_private.worker_rpc(p_secret,p_action,p_args)
$$;
revoke all on function public.material_worker_rpc(text,text,jsonb) from public;
grant execute on function public.material_worker_rpc(text,text,jsonb) to anon,authenticated;

create function public.material_apply(p_args jsonb) returns jsonb language plpgsql
security invoker set search_path='' as $$
declare p public.projects%rowtype; j public.material_jobs%rowtype; conflict boolean; fields jsonb; r jsonb;
begin
 if (select auth.uid()) is null then raise exception 'authentication required' using errcode='42501'; end if;
 select * into p from public.projects where id=p_args->>'project_id' and owner_id=(select auth.uid()) for update;
 if not found then raise exception 'project not owned' using errcode='42501'; end if;
 select * into j from public.material_jobs where id=p_args->>'id' and project_id=p.id for update;
 if not found or j.status<>'completed' then raise exception 'job not completed'; end if;
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
revoke all on function public.material_apply(jsonb) from public,anon;
grant execute on function public.material_apply(jsonb) to authenticated;
commit;
