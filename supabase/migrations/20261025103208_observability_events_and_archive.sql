-- Private metadata only. No source bodies, credentials, business payloads or material names.
create schema observability;
revoke all on schema observability from public, anon, authenticated;
create table observability.config (
  singleton boolean primary key default true check(singleton),
  enabled boolean not null default false,
  event_budget_bytes bigint not null default 150000000,
  soft_bytes bigint not null default 400000000,
  hard_bytes bigint not null default 450000000
);
insert into observability.config(singleton) values(true);
create table observability.capabilities (
  id text primary key, digest bytea not null unique,
  scope text not null check(scope in ('api','upload','ops')),
  enabled boolean not null default true
);
create table observability.archive_batches (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default clock_timestamp(),
  schema_version integer not null default 1,
  event_count integer not null default 0,
  plaintext_sha256 text, verified_at timestamptz,
  ciphertext_sha256 text, key_id text
);
create table observability.task_events (
  event_id uuid primary key,
  ingested_at timestamptz not null default clock_timestamp(),
  occurred_at timestamptz not null,
  trace_id text not null check(trace_id ~ '^[a-f0-9-]{16,64}$'),
  http_request_id text, job_id text, project_id text, owner_id uuid,
  usage_request_id text,
  event text not null check(event ~ '^[a-z_]+(\.[a-z_]+){1,3}$'),
  operation text not null,
  stage text not null default '', status text not null,
  level text not null check(level in ('info','warning','error')),
  component text not null, version text not null, environment text not null,
  duration_ms bigint, http_status integer, error_code text,
  metadata jsonb not null default '{}' check(octet_length(metadata::text)<=1024),
  archive_batch_id uuid references observability.archive_batches(id)
);
create index obs_trace_time on observability.task_events(trace_id,ingested_at,event_id);
create index obs_job_time on observability.task_events(job_id,ingested_at,event_id);
create index obs_request on observability.task_events(http_request_id) where http_request_id is not null;
create index obs_usage on observability.task_events(usage_request_id) where usage_request_id is not null;
create index obs_time on observability.task_events(ingested_at,event_id);
create index obs_unclaimed on observability.task_events(ingested_at,event_id) where archive_batch_id is null;
create index obs_archive on observability.task_events(archive_batch_id,event_id);
do $$ declare t text; begin
  foreach t in array array['config','capabilities','archive_batches','task_events'] loop
    execute format('alter table observability.%I enable row level security',t);
    execute format('revoke all on observability.%I from public,anon,authenticated',t);
  end loop;
end $$;

create function observability.write_event(e jsonb, source text) returns boolean
language plpgsql set search_path='' set timezone='UTC' as $$
declare c observability.config%rowtype; db_bytes bigint; k text; v jsonb;
begin
 select * into c from observability.config where singleton;
 if not c.enabled then return false; end if;
 select pg_database_size(current_database()) into db_bytes;
 if db_bytes>=300000000 then raise log 'observability_warning=DATABASE_300MB'; end if;
 if db_bytes>=c.hard_bytes or
   ((db_bytes>=c.soft_bytes or pg_total_relation_size('observability.task_events')>=c.event_budget_bytes)
    and coalesce(e->>'level','info')='info') then
   raise log 'observability_gap=CAPACITY_LIMIT';
   return false;
 end if;
 if octet_length(e::text)>4096 or jsonb_typeof(coalesce(e->'metadata','{}'))<>'object'
   or octet_length(coalesce(e->'metadata','{}')::text)>1024 then raise exception 'invalid event'; end if;
 for k,v in select * from jsonb_each(coalesce(e->'metadata','{}')) loop
   if k=any(array['file_bytes','chapter_count','outline_count','record_count',
      'prompt_tokens','completion_tokens','attempt','response_bytes']) then
     if v::text !~ '^[0-9]{1,13}$' then raise exception 'invalid metadata'; end if;
   elsif k='billable' then
     if jsonb_typeof(v)<>'boolean' then raise exception 'invalid metadata'; end if;
   elsif k='mime_type' then
     if jsonb_typeof(v)<>'string' or coalesce(v#>>'{}','')<>all(array['application/zip','application/pdf','text/plain','text/markdown',
       'image/png','image/jpeg','image/webp',
       'application/vnd.openxmlformats-officedocument.wordprocessingml.document'])
       then raise exception 'invalid metadata'; end if;
   elsif k='transaction_kind' then
     if jsonb_typeof(v)<>'string' or coalesce(v#>>'{}','')<>all(array['card_redeem','usage_reserve','usage_settle','usage_refund','admin_adjustment','payment_credit'])
       then raise exception 'invalid metadata'; end if;
   else raise exception 'metadata not allowlisted'; end if;
 end loop;
 if (e->>'stage') !~ '^[a-z_]{0,64}$'
   or coalesce(e->>'version','unknown') !~ '^([a-f0-9]{7,40}|unknown)$'
   or coalesce(e->>'environment','local')<>all(array['production','preview','local','test'])
   or coalesce(e->>'status','')<>all(array['started','queued','running','completed','failed','accepted','pending','cancelled','needs_review','reserved','settled','refunded','credited','rejected'])
   or coalesce(e->>'error_code','') !~ '^[A-Z_]{0,80}$'
   or coalesce(e->>'usage_request_id','') !~ '^[a-zA-Z0-9_:-]{0,100}$'
   or coalesce(e->>'job_id','') !~ '^[a-f0-9]{0,32}$'
   or coalesce(e->>'project_id','') !~ '^[a-f0-9]{0,32}$'
   or coalesce(e->>'http_request_id','') !~ '^[a-f0-9]{0,32}$'
   or (e->>'http_status' is not null and (e->>'http_status')::integer not between 100 and 599)
   or (e->>'duration_ms' is not null and (e->>'duration_ms')::bigint not between 0 and 1000000000000)
   then raise exception 'invalid event fields'; end if;
 if source='upload_proxy' and e->>'event' not like 'upload.%' then raise exception 'invalid source event'; end if;
 insert into observability.task_events(event_id,occurred_at,trace_id,http_request_id,
  job_id,project_id,owner_id,usage_request_id,event,operation,stage,status,level,component,
  version,environment,duration_ms,http_status,error_code,metadata)
 values ((e->>'event_id')::uuid,(e->>'occurred_at')::timestamptz,e->>'trace_id',e->>'http_request_id',
  e->>'job_id',e->>'project_id',(e->>'owner_id')::uuid,e->>'usage_request_id',e->>'event',
  split_part(e->>'event','.',1),coalesce(e->>'stage',''),e->>'status',coalesce(e->>'level','info'),source,
  coalesce(e->>'version','unknown'),coalesce(e->>'environment','production'),
  (e->>'duration_ms')::bigint,(e->>'http_status')::integer,e->>'error_code',coalesce(e->'metadata','{}'))
 on conflict(event_id) do nothing;
 return true;
end $$;
revoke all on function observability.write_event(jsonb,text) from public,anon,authenticated;

create function observability.event_line(e observability.task_events) returns text
language sql immutable set search_path='' set timezone='UTC' as $$
 select jsonb_build_object(
  'event_id',e.event_id,'ingested_at',e.ingested_at,'occurred_at',e.occurred_at,
  'trace_id',e.trace_id,'http_request_id',e.http_request_id,'job_id',e.job_id,
  'project_id',e.project_id,'owner_id',e.owner_id,'usage_request_id',e.usage_request_id,
  'event',e.event,'operation',e.operation,'stage',e.stage,'status',e.status,'level',e.level,
  'component',e.component,'version',e.version,'environment',e.environment,
  'duration_ms',e.duration_ms,'http_status',e.http_status,'error_code',e.error_code,'metadata',e.metadata)::text
$$;
revoke all on function observability.event_line(observability.task_events) from public,anon,authenticated;

-- Purpose-specific random capabilities, hashes only in DB.
-- Privileged implementation stays in an unexposed schema; public wrapper is invoker.
-- Schema USAGE does not grant any table access or helper-function execution.
create function observability.api(p_key text,p_action text,p_args jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' set timezone='UTC' as $$
declare cap observability.capabilities%rowtype; e jsonb; n integer:=0; b observability.archive_batches%rowtype;
 result jsonb; last_time timestamptz; last_id uuid; db_bytes bigint;
begin
 if length(coalesce(p_key,''))<32 or octet_length(p_args::text)>200000 then
   raise exception 'observability access denied' using errcode='42501'; end if;
 select * into cap from observability.capabilities
 where digest=sha256(convert_to(p_key,'UTF8')) and enabled;
 if not found then raise exception 'observability access denied' using errcode='42501'; end if;
 if p_action='append' then
   if cap.scope not in ('api','upload') or jsonb_typeof(p_args->'events')<>'array'
     or jsonb_array_length(p_args->'events')>48 then raise exception 'invalid ingestion' using errcode='42501'; end if;
   for e in select * from jsonb_array_elements(p_args->'events') loop
     if observability.write_event(e,case cap.scope when 'upload' then 'upload_proxy' else 'api' end) then n:=n+1; end if;
   end loop;
   return jsonb_build_object('written',n);
 end if;
 if cap.scope<>'ops' then raise exception 'observability access denied' using errcode='42501'; end if;
 if p_action='list' or p_action='trace' then
   last_time:=coalesce((p_args->>'after_time')::timestamptz,'-infinity'::timestamptz);
   last_id:=coalesce((p_args->>'after_id')::uuid,'00000000-0000-0000-0000-000000000000'::uuid);
   select coalesce(jsonb_agg(observability.event_line(q.row_value)::jsonb),'[]') into result from (
    select t as row_value from observability.task_events t
    where (t.ingested_at,t.event_id)>(last_time,last_id)
      and (p_args->>'since' is null or t.ingested_at>=(p_args->>'since')::timestamptz)
      and (p_args->>'until' is null or t.ingested_at<(p_args->>'until')::timestamptz)
      and (p_args->>'operation' is null or t.operation=p_args->>'operation')
      and (p_args->>'job_id' is null or t.job_id=p_args->>'job_id')
      and (p_args->>'usage_request_id' is null or t.usage_request_id=p_args->>'usage_request_id')
      and (p_args->>'owner_id' is null or t.owner_id=(p_args->>'owner_id')::uuid)
      and (p_args->>'error_code' is null or t.error_code=p_args->>'error_code')
      and (p_args->>'level' is null or t.level=p_args->>'level')
      and (p_args->>'environment' is null or t.environment=p_args->>'environment')
      and (p_action<>'trace' or t.trace_id=p_args->>'trace_id' or t.http_request_id=p_args->>'trace_id'
        or t.usage_request_id in (select x.usage_request_id from observability.task_events x
          where x.trace_id=p_args->>'trace_id' or x.http_request_id=p_args->>'trace_id'))
    order by t.ingested_at,t.event_id limit least(200,greatest(1,coalesce((p_args->>'limit')::int,200)))
   ) q;
   return jsonb_build_object('events',result);
 elsif p_action in ('stats','status') then
   select pg_database_size(current_database()) into db_bytes;
   return jsonb_build_object(
    'database_bytes',db_bytes,'capacity_warning',db_bytes>=300000000,
    'events_bytes',pg_total_relation_size('observability.task_events'),
    'events',(select count(*) from observability.task_events),
    'unarchived',(select count(*) from observability.task_events where archive_batch_id is null),
    'pending_batches',(select count(*) from observability.archive_batches where verified_at is null),
    'unverified_events',(select count(*) from observability.task_events t left join observability.archive_batches a
       on a.id=t.archive_batch_id where a.verified_at is null),
    'oldest_unverified_at',(select min(t.ingested_at) from observability.task_events t left join observability.archive_batches a
       on a.id=t.archive_batch_id where a.verified_at is null),
    'old_unverified',(select count(*) from observability.task_events t left join observability.archive_batches a
       on a.id=t.archive_batch_id where t.ingested_at<now()-interval '30 days' and a.verified_at is null),
    'last_verified',(select max(verified_at) from observability.archive_batches),
    'groups',(select coalesce(jsonb_agg(g),'[]') from
      (select operation,level,error_code,count(*) from observability.task_events
       where (p_args->>'since' is null or ingested_at>=(p_args->>'since')::timestamptz)
       group by operation,level,error_code) g));
 elsif p_action='inventory' then
   select coalesce(jsonb_agg(to_jsonb(q)),'[]') into result from (
     select id,event_count,plaintext_sha256,ciphertext_sha256,key_id,verified_at
     from observability.archive_batches
     where verified_at>=now()-interval '180 days' and
       (verified_at,id)>(coalesce((p_args->>'after_time')::timestamptz,'-infinity'::timestamptz),
         coalesce((p_args->>'after_id')::uuid,'00000000-0000-0000-0000-000000000000'::uuid))
     order by verified_at,id limit 200) q;
   return jsonb_build_object('batches',result);
 elsif p_action='claim' then
   perform pg_advisory_xact_lock(hashtextextended('stardust_observability_archive',0));
   select * into b from observability.archive_batches where verified_at is null order by created_at limit 1;
   if not found then
     insert into observability.archive_batches default values returning * into b;
     update observability.task_events set archive_batch_id=b.id where event_id in (
       select event_id from observability.task_events where archive_batch_id is null
       and ingested_at<clock_timestamp()-interval '2 minutes'
       order by ingested_at,event_id for update skip locked limit 5000);
     get diagnostics n=row_count;
     if n=0 then delete from observability.archive_batches where id=b.id; return null; end if;
     update observability.archive_batches set event_count=n,
       plaintext_sha256=(select encode(sha256(convert_to(
        string_agg(observability.event_line(t),chr(10) order by t.event_id)||chr(10),'UTF8')),'hex')
        from observability.task_events t where t.archive_batch_id=b.id)
     where id=b.id returning * into b;
   end if;
   return to_jsonb(b);
 elsif p_action='page' then
   select * into b from observability.archive_batches where id=(p_args->>'batch_id')::uuid;
   if not found then raise exception 'batch not found'; end if;
   if b.verified_at is not null then raise exception 'batch already acknowledged'; end if;
   select coalesce(jsonb_agg(q.line),'[]') into result from (
     select observability.event_line(t) as line from observability.task_events t
     where archive_batch_id=b.id order by event_id limit 200 offset greatest(0,(p_args->>'offset')::int)) q;
   return jsonb_build_object('lines',result,'batch',to_jsonb(b));
 elsif p_action='ack' then
   select * into b from observability.archive_batches where id=(p_args->>'batch_id')::uuid for update;
   if not found or not coalesce((p_args->>'event_count')::int=b.event_count,false)
      or not coalesce(p_args->>'plaintext_sha256'=b.plaintext_sha256,false)
      or coalesce(p_args->>'ciphertext_sha256','') !~ '^[a-f0-9]{64}$'
      or coalesce(p_args->>'key_id','') !~ '^[a-f0-9]{32}$' then raise exception 'archive verification mismatch'; end if;
   if b.verified_at is not null and (b.ciphertext_sha256<>p_args->>'ciphertext_sha256' or b.key_id<>p_args->>'key_id')
     then raise exception 'archive receipt conflict'; end if;
   update observability.archive_batches set verified_at=coalesce(verified_at,clock_timestamp()),
     ciphertext_sha256=p_args->>'ciphertext_sha256',key_id=p_args->>'key_id' where id=b.id;
   return jsonb_build_object('verified',true);
 elsif p_action='purge' then
   delete from observability.task_events where event_id in (
     select t.event_id from observability.task_events t join observability.archive_batches a on a.id=t.archive_batch_id
     where a.verified_at is not null and t.ingested_at<now()-interval '30 days' limit 1000);
   get diagnostics n=row_count;
   return jsonb_build_object('deleted',n);
 end if;
 raise exception 'unsupported observability action' using errcode='42501';
end $$;
revoke all on function observability.api(text,text,jsonb) from public;
grant usage on schema observability to anon,authenticated;
grant execute on function observability.api(text,text,jsonb) to anon,authenticated;
create function public.observability_api(p_key text,p_action text,p_args jsonb default '{}') returns jsonb
language sql security invoker set search_path='' as $$
 select observability.api(p_key,p_action,p_args)
$$;
revoke all on function public.observability_api(text,text,jsonb) from public;
grant execute on function public.observability_api(text,text,jsonb) to anon,authenticated;

create function observability.job_event() returns trigger language plpgsql security definer set search_path='' as $$
declare e jsonb;
begin
 if tg_op='UPDATE' and new.status=old.status and new.step=old.step then return new; end if;
 e:=jsonb_build_object('event_id',gen_random_uuid(),'trace_id',
   substr(encode(sha256(convert_to('job:'||new.owner_id||':'||new.id,'UTF8')),'hex'),1,32),
   'owner_id',new.owner_id,'project_id',new.project_id,'job_id',new.id,
   'occurred_at',clock_timestamp(),'event','task.'||case when new.status='failed' then 'failed' else 'transition' end,
   'stage',new.step,'status',new.status,'level',case when new.status in ('failed','needs_review') then 'error' else 'info' end,
   'error_code',case when new.status in ('failed','needs_review') then
     coalesce(new.result->>'error_code','TASK_EXECUTION_FAILED') else null end,
   'version',coalesce(new.result->>'worker_version','unknown'),'environment',
     case when new.payload->>'environment'='preview' then 'preview' else 'production' end,
   'metadata',jsonb_build_object('billable',coalesce((new.payload->>'paid')::boolean,false)));
 -- This is a database-state fact, not proof that a browser-reported state actually executed.
 begin perform observability.write_event(e,'database'); exception when others then raise log 'observability_gap=JOB_EVENT_UNAVAILABLE'; end;
 return new;
exception when others then
 raise log 'observability_gap=JOB_EVENT_UNAVAILABLE'; return new;
end $$;
revoke all on function observability.job_event() from public,anon,authenticated;
create trigger observability_job_event after insert or update on public.material_jobs
for each row execute function observability.job_event();

create function observability.ledger_event() returns trigger language plpgsql security definer set search_path='' as $$
begin
 begin perform observability.write_event(jsonb_build_object(
  'event_id',gen_random_uuid(),'trace_id',substr(encode(sha256(convert_to(
    'billing:'||new.user_id||':'||coalesce(new.request_id,new.id::text),'UTF8')),'hex'),1,32),
  'owner_id',new.user_id,'usage_request_id',new.request_id,'occurred_at',clock_timestamp(),
  'event','billing.recorded','stage','ledger_committed','status','completed','level','info',
  'version','unknown','environment','production','metadata',jsonb_build_object('transaction_kind',new.kind)
 ),'database'); exception when others then raise log 'observability_gap=LEDGER_EVENT_UNAVAILABLE'; end;
 return new;
end $$;
revoke all on function observability.ledger_event() from public,anon,authenticated;
create trigger observability_ledger_event after insert on public.workbench_credit_transactions
for each row execute function observability.ledger_event();

create function observability.worker_event(p_secret text,p_job_id text,p_lease text,p_event jsonb)
returns boolean language plpgsql security definer set search_path='' as $$
declare ctx jsonb; e jsonb;
begin
 if not exists(select 1 from material_private.worker_capability
    where secret_hash=sha256(convert_to(p_secret,'UTF8'))) then
   raise exception 'worker capability rejected' using errcode='42501'; end if;
 select jsonb_build_object('owner_id',j.owner_id,'project_id',j.project_id) into ctx
 from public.material_jobs j where j.id=p_job_id and j.status='running'
   and j.lease=p_lease and j.lease_until>=now() for update;
 if ctx is null then raise exception 'worker lease invalid' using errcode='42501'; end if;
 if p_event->>'event' is null or p_event->>'event' not in ('task.checkpoint','task.execution_failed','task.execution_finished')
   then raise exception 'invalid worker event' using errcode='42501'; end if;
 e:=p_event||jsonb_build_object('event_id',gen_random_uuid(),'owner_id',ctx->>'owner_id',
   'project_id',ctx->>'project_id','job_id',p_job_id,'occurred_at',clock_timestamp(),
   'trace_id',substr(encode(sha256(convert_to('job:'||(ctx->>'owner_id')||':'||p_job_id,'UTF8')),'hex'),1,32));
 return observability.write_event(e,'worker');
end $$;
revoke all on function observability.worker_event(text,text,text,jsonb) from public;
grant execute on function observability.worker_event(text,text,text,jsonb) to anon,authenticated;
create function public.observability_worker_event(p_secret text,p_job_id text,p_lease text,p_event jsonb)
returns boolean language sql security invoker set search_path='' as $$
 select observability.worker_event(p_secret,p_job_id,p_lease,p_event)
$$;
revoke all on function public.observability_worker_event(text,text,text,jsonb) from public;
grant execute on function public.observability_worker_event(text,text,text,jsonb) to anon,authenticated;
