-- Project-only retrieval. Private chunks remain protected by caller RLS.
create extension if not exists vector with schema extensions;
grant usage on schema extensions to authenticated;

-- Legacy confirmed flags may have been set by automatic OCR. Preserve the
-- source text but require a fresh explicit user confirmation before retrieval.
alter table public.documents
  add column if not exists confirmation_origin text not null default '';

create table public.rag_chunk_embeddings (
  chunk_id text primary key references public.chunks(id) on delete cascade,
  model text not null check (model = 'bge-m3'),
  model_revision text not null check (model_revision <> ''),
  embedding extensions.vector(1024) not null
);
create index rag_chunk_embeddings_cosine_idx
  on public.rag_chunk_embeddings using hnsw (embedding extensions.vector_cosine_ops);
alter table public.rag_chunk_embeddings enable row level security;
revoke all on public.rag_chunk_embeddings from public, anon;
grant select, insert, update, delete on public.rag_chunk_embeddings to authenticated;
create policy rag_embeddings_owner on public.rag_chunk_embeddings
  for all to authenticated
  using (exists (
    select 1 from public.chunks c
    join public.documents d on d.id = c.document_id and d.project_id = c.project_id
    join public.projects p on p.id = c.project_id
    where c.id = rag_chunk_embeddings.chunk_id and p.owner_id = (select auth.uid())
      and d.confirmed and d.confirmation_origin = 'user' and d.kind <> 'template'
  ))
  with check (exists (
    select 1 from public.chunks c
    join public.documents d on d.id = c.document_id and d.project_id = c.project_id
    join public.projects p on p.id = c.project_id
    where c.id = rag_chunk_embeddings.chunk_id and p.owner_id = (select auth.uid())
      and d.confirmed and d.confirmation_origin = 'user' and d.kind <> 'template'
  ));

-- Replace a confirmed document's chunks and vectors in one transaction.
-- The caller's JWT/RLS is retained; no service-role or definer bypass.
create function public.rag_replace_project_chunks(
  p_document_id text, p_expected_sha256 text, p_chunks jsonb
) returns integer language plpgsql security invoker set search_path = '' as $$
declare
  doc record;
  item jsonb;
  vector_value jsonb;
  inserted integer := 0;
begin
  if coalesce(p_expected_sha256, '') !~ '^[0-9a-f]{64}$'
     or p_chunks is null or jsonb_typeof(p_chunks) <> 'array'
     or jsonb_array_length(p_chunks) < 1
     or jsonb_array_length(p_chunks) > 5000 then
    raise exception 'invalid chunk payload' using errcode = '22023';
  end if;
  select d.id, d.project_id, d.original_name, d.extracted_text into doc
  from public.documents d
  join public.projects p on p.id = d.project_id
  where d.id = p_document_id and p.owner_id = (select auth.uid())
    and d.confirmed and d.confirmation_origin = 'user' and d.kind <> 'template'
  for update of d;
  if not found then
    raise exception 'document unavailable or not confirmed' using errcode = '42501';
  end if;
  if encode(pg_catalog.sha256(pg_catalog.convert_to(doc.extracted_text, 'UTF8')), 'hex') <> p_expected_sha256 then
    -- Serialization failure is retried by PostgREST and can hang the request;
    -- this is a semantic conflict that requires the user to reconfirm.
    raise exception 'document changed during indexing' using errcode = 'PT409';
  end if;
  -- Validate everything before the delete; any later failure also rolls back.
  for item in select value from jsonb_array_elements(p_chunks) loop
    if jsonb_typeof(item) <> 'object'
       or coalesce(item->>'id', '') !~ '^[0-9a-f]{32}$'
       or length(coalesce(item->>'source_ref', '')) not between 1 and 500
       or length(coalesce(item->>'content', '')) not between 1 and 2000 then
      raise exception 'invalid chunk item' using errcode = '22023';
    end if;
    vector_value := item->'embedding';
    if vector_value is not null and vector_value <> 'null'::jsonb then
      if jsonb_typeof(vector_value) <> 'array' then
        raise exception 'invalid vector type' using errcode = '22023';
      end if;
      if jsonb_array_length(vector_value) <> 1024 or coalesce(item->>'embedding_model', '') <> 'bge-m3'
         or length(coalesce(item->>'embedding_revision', '')) not between 1 and 200 then
        raise exception 'invalid vector metadata' using errcode = '22023';
      end if;
    end if;
  end loop;
  delete from public.chunks where document_id = doc.id;
  for item in select value from jsonb_array_elements(p_chunks) loop
    insert into public.chunks(id, project_id, document_id, source_name, source_ref, content, embedding_json)
    values (item->>'id', doc.project_id, doc.id, doc.original_name,
            item->>'source_ref', item->>'content', '[]'::jsonb);
    vector_value := item->'embedding';
    if vector_value is not null and vector_value <> 'null'::jsonb then
      insert into public.rag_chunk_embeddings(chunk_id, model, model_revision, embedding)
      values (item->>'id', 'bge-m3', item->>'embedding_revision',
              (vector_value::text)::extensions.vector(1024));
    end if;
    inserted := inserted + 1;
  end loop;
  return inserted;
end $$;
revoke all on function public.rag_replace_project_chunks(text, text, jsonb) from public, anon;
grant execute on function public.rag_replace_project_chunks(text, text, jsonb) to authenticated;

-- Invoker privileges and underlying RLS are intentional: never use a service key here.
create function public.rag_project_search(
  p_project_id text, p_terms text[], p_embedding extensions.vector(1024) default null,
  p_model text default 'bge-m3', p_limit integer default 30, p_model_revision text default ''
) returns table (
  id text, document_id text, source_name text, source_ref text, content text,
  lexical_score real, vector_score real
) language sql stable security invoker set search_path = '' as $$
  with eligible as not materialized (
    select c.id, c.document_id, c.source_name, c.source_ref, c.content, e.embedding,
      (select count(*)::real from unnest(coalesce(p_terms[1:80], array[]::text[])) term
       where length(term) between 2 and 64 and position(lower(term) in lower(c.content)) > 0) as lex
    from public.chunks c
    join public.documents d on d.id = c.document_id and d.project_id = c.project_id
    join public.projects p on p.id = c.project_id and p.owner_id = (select auth.uid())
    left join public.rag_chunk_embeddings e on e.chunk_id = c.id and e.model = p_model
      and p_model_revision <> '' and e.model_revision = p_model_revision
    where c.project_id = p_project_id and d.confirmed and d.confirmation_origin = 'user'
      and d.kind <> 'template'
  ), lexical as (
    select eligible.id from eligible where lex > 0 order by lex desc, eligible.id
    limit greatest(1, least(coalesce(p_limit, 30), 30))
  ), semantic as (
    select eligible.id from eligible where p_embedding is not null and embedding is not null
    order by embedding operator(extensions.<=>) p_embedding, eligible.id
    limit greatest(1, least(coalesce(p_limit, 30), 30))
  )
  select e.id, e.document_id, e.source_name, e.source_ref, e.content, e.lex,
    case when e.embedding is not null and p_embedding is not null
      then (1 - (e.embedding operator(extensions.<=>) p_embedding))::real else 0::real end
  from eligible e where e.id in (select lexical.id from lexical union select semantic.id from semantic)
$$;
revoke all on function public.rag_project_search(text, text[], extensions.vector, text, integer, text) from public, anon;
grant execute on function public.rag_project_search(text, text[], extensions.vector, text, integer, text) to authenticated;
