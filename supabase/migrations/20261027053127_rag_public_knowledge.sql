-- Public, reviewed reference knowledge. Service-role-only publication, read-only
-- RLS for users; students cannot promote sources or change vectors.
create extension if not exists vector with schema extensions;
grant usage on schema extensions to authenticated, service_role;

create table public.rag_public_sources (
  id text primary key,
  skill_id text not null,
  variant text not null default '',
  restrictions jsonb not null default '{}'::jsonb check (jsonb_typeof(restrictions) = 'object'),
  kind text not null check (kind in ('official', 'institution_report', 'example', 'skill_guidance')),
  title text not null,
  source_url text not null default '',
  school text not null default '',
  application_year integer check (application_year between 1900 and 2200),
  scope text not null default '',
  source_sha256 text not null check (source_sha256 ~ '^[0-9a-f]{64}$'),
  verified_at date,
  license text not null default '',
  rights_evidence_url text not null default '',
  rights_review_status text not null default '',
  rights_resolution_url text not null default '',
  approval_reference text not null default '',
  privacy_reviewed boolean not null default false,
  structure_reviewed boolean not null default false,
  example_structure text not null default '',
  example_match_type text not null default '',
  attribution text not null default '',
  published boolean not null default false,
  updated_at timestamptz not null default now(),
  check (kind <> 'institution_report' or example_structure <> ''),
  check (kind <> 'example' or (
    privacy_reviewed and structure_reviewed and source_url like 'https://%' and rights_evidence_url like 'https://%'
    and approval_reference <> '' and license <> '' and example_structure <> ''
    and example_match_type in ('direct', 'cross_track') and attribution <> ''
    and (rights_review_status = 'no_conflict' or
         (rights_review_status = 'resolved' and rights_resolution_url like 'https://%'))
  ))
);
create index rag_public_sources_scope_idx
  on public.rag_public_sources(skill_id, school, application_year) where published;

create table public.rag_public_chunks (
  id text primary key,
  source_id text not null references public.rag_public_sources(id) on delete cascade,
  source_ref text not null,
  content text not null,
  embedding_model text not null default '' check (embedding_model in ('', 'bge-m3')),
  embedding_revision text not null default '',
  embedding extensions.vector(1024),
  check ((embedding is null and embedding_model = '' and embedding_revision = '') or
         (embedding is not null and embedding_model = 'bge-m3' and embedding_revision <> ''))
);
create index rag_public_chunks_source_idx on public.rag_public_chunks(source_id);
create index rag_public_chunks_vector_idx
  on public.rag_public_chunks using hnsw (embedding extensions.vector_cosine_ops)
  where embedding is not null;

alter table public.rag_public_sources enable row level security;
alter table public.rag_public_chunks enable row level security;
revoke all on public.rag_public_sources, public.rag_public_chunks from public, anon, authenticated;
grant select on public.rag_public_sources, public.rag_public_chunks to authenticated;
grant select, insert, update, delete on public.rag_public_sources, public.rag_public_chunks to service_role;
create policy rag_public_sources_read on public.rag_public_sources for select to authenticated
  using (published);
create policy rag_public_chunks_read on public.rag_public_chunks for select to authenticated
  using (exists (select 1 from public.rag_public_sources s where s.id = source_id and s.published));

-- Import is one transaction per source: readers cannot observe a partial rebuild.
-- This is SECURITY INVOKER and is executable only by the service role.
create function public.rag_publish_public_source(p_source jsonb, p_chunks jsonb)
returns integer language plpgsql security invoker set search_path = '' as $$
declare n integer;
begin
  if jsonb_typeof(p_source) <> 'object' or jsonb_typeof(p_chunks) <> 'array'
     or jsonb_array_length(p_chunks) = 0 or jsonb_array_length(p_chunks) > 5000 then
    raise exception 'invalid public source payload';
  end if;
  insert into public.rag_public_sources (id, skill_id, variant, restrictions, kind, title, source_url, school,
      application_year, scope, source_sha256, verified_at, license, rights_evidence_url, rights_review_status, rights_resolution_url,
      approval_reference, privacy_reviewed, structure_reviewed, example_structure, example_match_type, attribution, published, updated_at)
  values (p_source->>'id', p_source->>'skill_id', coalesce(p_source->>'variant',''),
      coalesce(p_source->'restrictions', '{}'::jsonb), p_source->>'kind', p_source->>'title',
      coalesce(p_source->>'source_url',''), coalesce(p_source->>'school',''),
      nullif(p_source->>'application_year','')::integer, coalesce(p_source->>'scope',''),
      p_source->>'source_sha256', nullif(p_source->>'verified_at','')::date, coalesce(p_source->>'license',''),
      coalesce(p_source->>'rights_evidence_url',''), coalesce(p_source->>'rights_review_status',''),
      coalesce(p_source->>'rights_resolution_url',''), coalesce(p_source->>'approval_reference',''),
      coalesce((p_source->>'privacy_reviewed')::boolean,false), coalesce((p_source->>'structure_reviewed')::boolean,false),
      coalesce(p_source->>'example_structure',''), coalesce(p_source->>'example_match_type',''),
      coalesce(p_source->>'attribution',''), true, now())
  on conflict (id) do update set skill_id=excluded.skill_id, variant=excluded.variant,
      restrictions=excluded.restrictions, kind=excluded.kind,
      title=excluded.title, source_url=excluded.source_url, school=excluded.school,
      application_year=excluded.application_year, scope=excluded.scope,
      source_sha256=excluded.source_sha256, verified_at=excluded.verified_at, license=excluded.license,
      rights_evidence_url=excluded.rights_evidence_url, rights_review_status=excluded.rights_review_status,
      rights_resolution_url=excluded.rights_resolution_url, approval_reference=excluded.approval_reference,
      privacy_reviewed=excluded.privacy_reviewed, structure_reviewed=excluded.structure_reviewed,
      example_structure=excluded.example_structure, example_match_type=excluded.example_match_type,
      attribution=excluded.attribution,
      published=true, updated_at=now();
  delete from public.rag_public_chunks where source_id = p_source->>'id';
  insert into public.rag_public_chunks(id, source_id, source_ref, content, embedding_model, embedding_revision, embedding)
  select c.id, p_source->>'id', c.source_ref, c.content, coalesce(c.embedding_model,''), coalesce(c.embedding_revision,''),
      case when c.embedding is null then null else c.embedding::extensions.vector(1024) end
  from jsonb_to_recordset(p_chunks) as c(id text, source_ref text, content text,
      embedding_model text, embedding_revision text, embedding text);
  get diagnostics n = row_count;
  return n;
end $$;
revoke all on function public.rag_publish_public_source(jsonb, jsonb) from public, anon, authenticated;
grant execute on function public.rag_publish_public_source(jsonb, jsonb) to service_role;

create function public.rag_search_public_knowledge(
  p_skill_id text, p_school text, p_year integer, p_terms text[],
  p_embedding extensions.vector(1024) default null, p_embedding_revision text default '',
  p_limit integer default 30, p_variant text default '', p_filters jsonb default '{}'::jsonb,
  p_official_only boolean default false, p_include_examples boolean default false
) returns table (
  id text, source_id text, skill_id text, variant text, restrictions jsonb, kind text, title text, source_url text,
  school text, application_year integer, scope text, source_sha256 text, verified_at date, license text,
  rights_evidence_url text, rights_review_status text, rights_resolution_url text,
  example_structure text, example_match_type text, attribution text, source_ref text,
  content text, lexical_score real, vector_score real
) language sql stable security invoker set search_path = '' as $$
  with eligible as not materialized (
    select c.id, s.id as source_id, s.skill_id, s.variant, s.restrictions, s.kind, s.title, s.source_url,
      s.school, s.application_year, s.scope, s.source_sha256, s.verified_at, s.license,
      s.rights_evidence_url, s.rights_review_status, s.rights_resolution_url,
      s.example_structure, s.example_match_type, s.attribution, c.source_ref, c.content, c.embedding,
      c.embedding_revision,
      (select count(*)::real from unnest(coalesce(p_terms[1:80], array[]::text[])) term
       where length(term) between 2 and 64 and position(lower(term) in lower(
         c.content || case when s.kind = 'example' then ' ' || s.title || ' ' || s.scope else '' end
       )) > 0) lex
    from public.rag_public_chunks c
    join public.rag_public_sources s on s.id = c.source_id
    where s.published and s.skill_id = p_skill_id
      and (not coalesce(p_official_only, false) or s.kind = 'official')
      and (s.kind <> 'example' or coalesce(p_include_examples, false))
      and (s.variant = '' or (coalesce(p_variant,'') <> '' and s.variant = p_variant))
      and not exists (
        select 1 from jsonb_each(s.restrictions) requirement
        where jsonb_typeof(requirement.value) <> 'array'
          or not (requirement.value ? coalesce(p_filters->>requirement.key, ''))
      )
      and (s.kind = 'example' or s.school = '' or (coalesce(p_school,'') <> '' and s.school = p_school))
      and (s.kind = 'example' or s.application_year is null or s.application_year = p_year)
  ), lexical as (
    select eligible.id from eligible where lex > 0 order by lex desc, eligible.id
    limit greatest(1, least(coalesce(p_limit,30),30))
  ), semantic as (
    select eligible.id from eligible where p_embedding is not null and embedding is not null
      and p_embedding_revision <> '' and embedding_revision = p_embedding_revision
    order by embedding operator(extensions.<=>) p_embedding, eligible.id
    limit greatest(1, least(coalesce(p_limit,30),30))
  )
  select e.id, e.source_id, e.skill_id, e.variant, e.restrictions, e.kind, e.title, e.source_url,
    e.school, e.application_year, e.scope, e.source_sha256, e.verified_at, e.license,
    e.rights_evidence_url, e.rights_review_status, e.rights_resolution_url,
    e.example_structure, e.example_match_type, e.attribution, e.source_ref, e.content, e.lex,
    case when e.embedding is not null and p_embedding is not null
          and p_embedding_revision <> '' and e.embedding_revision = p_embedding_revision
      then (1 - (e.embedding operator(extensions.<=>) p_embedding))::real else 0::real end
  from eligible e where e.id in (select lexical.id from lexical union select semantic.id from semantic)
$$;
revoke all on function public.rag_search_public_knowledge(text, text, integer, text[], extensions.vector, text, integer, text, jsonb, boolean, boolean) from public, anon;
grant execute on function public.rag_search_public_knowledge(text, text, integer, text[], extensions.vector, text, integer, text, jsonb, boolean, boolean) to authenticated;
