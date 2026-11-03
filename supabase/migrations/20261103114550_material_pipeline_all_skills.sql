-- Extend the existing owner-scoped invoker RPC to the checked-in skill catalogue.
-- Keep the API-side rollout and Worker readiness gates independent.
create or replace function public.material_jobs_api(p_action text,p_args jsonb) returns jsonb
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
   and lower(replace(btrim(coalesce(state_json->>'skill_id','innovation-research')), '_', '-')) = any(array[
     'national-project-eval',
     'motivation-scholarship',
     'university-scholarship',
     'enterprise-scholarship',
     'single-scholarship',
     'grant-application',
     'outstanding-student',
     'outstanding-graduate',
     'outstanding-cadre',
     'civilized-student',
     'class-collective',
     'youth-league-application',
     'innovation-research',
     'entrepreneurship-training',
     'entrepreneurship-practice',
     'university-research',
     'college-research',
     'challenge-cup',
     'internet-plus',
     'social-survey',
     'volunteer-teaching',
     'policy-lecture',
     'tech-service',
     'western-plan',
     'graduate-recommendation',
     'selected-graduate',
     'major-transfer',
     'military-enlistment',
     'csc-scholarship',
     'exchange-program',
     'internet-plus-red-tour',
     'outstanding-thesis',
     'national-scholarship',
     'summary-report',
     'youth-league-conversion'
   ]::text[])) then raise exception 'unsupported type'; end if;
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
