-- Stardust Agent cloud foundation:
-- authenticated users own projects; child rows and private files are scoped to
-- the owning project. API keys are intentionally not represented in this schema.

create table public.projects (
  id text primary key default replace(gen_random_uuid()::text, '-', ''),
  owner_id uuid not null references auth.users(id) on delete cascade,
  title text not null default '我的大创项目',
  level text not null default '',
  discipline text not null default '',
  school text not null default '',
  state_json jsonb not null default '{}'::jsonb,
  outline_json jsonb not null default '[]'::jsonb,
  sections_json jsonb not null default '{}'::jsonb,
  diagrams_json jsonb not null default '[]'::jsonb,
  template_document_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.documents (
  id text primary key default replace(gen_random_uuid()::text, '-', ''),
  project_id text not null references public.projects(id) on delete cascade,
  original_name text not null,
  storage_path text not null unique,
  kind text not null default 'source'
    check (kind in ('source', 'template', 'photo', 'official')),
  content_type text not null default '',
  extracted_text text not null default '',
  extraction_status text not null default 'pending',
  extraction_warning text not null default '',
  low_confidence_count integer not null default 0 check (low_confidence_count >= 0),
  confirmed boolean not null default false,
  created_at timestamptz not null default now()
);

alter table public.projects
  add constraint projects_template_document_id_fkey
  foreign key (template_document_id)
  references public.documents(id)
  on delete set null;

create table public.chunks (
  id text primary key default replace(gen_random_uuid()::text, '-', ''),
  project_id text not null references public.projects(id) on delete cascade,
  document_id text not null references public.documents(id) on delete cascade,
  source_name text not null,
  source_ref text not null default '',
  content text not null,
  embedding_json jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create table public.messages (
  id text primary key default replace(gen_random_uuid()::text, '-', ''),
  project_id text not null references public.projects(id) on delete cascade,
  role text not null check (role in ('user', 'assistant', 'system')),
  content text not null,
  created_at timestamptz not null default now()
);

create table public.token_usages (
  id text primary key default replace(gen_random_uuid()::text, '-', ''),
  project_id text not null references public.projects(id) on delete cascade,
  task_type text not null default 'chat',
  model text not null,
  prompt_tokens integer not null default 0 check (prompt_tokens >= 0),
  completion_tokens integer not null default 0 check (completion_tokens >= 0),
  total_tokens integer not null default 0 check (total_tokens >= 0),
  latency_ms integer not null default 0 check (latency_ms >= 0),
  key_fingerprint text not null default 'user-provided',
  created_at timestamptz not null default now()
);

create index projects_owner_updated_idx on public.projects(owner_id, updated_at desc);
create index documents_project_created_idx on public.documents(project_id, created_at);
create index chunks_project_idx on public.chunks(project_id);
create index chunks_document_idx on public.chunks(document_id);
create index messages_project_created_idx on public.messages(project_id, created_at);
create index token_usages_project_created_idx on public.token_usages(project_id, created_at);

alter table public.projects enable row level security;
alter table public.documents enable row level security;
alter table public.chunks enable row level security;
alter table public.messages enable row level security;
alter table public.token_usages enable row level security;

revoke all on public.projects, public.documents, public.chunks, public.messages, public.token_usages from anon;
grant select, insert, update, delete on public.projects, public.documents, public.chunks, public.messages, public.token_usages to authenticated;

create policy "owners manage their projects"
on public.projects for all to authenticated
using ((select auth.uid()) = owner_id)
with check ((select auth.uid()) = owner_id);

create policy "owners manage documents in their projects"
on public.documents for all to authenticated
using (
  exists (
    select 1 from public.projects p
    where p.id = documents.project_id
      and p.owner_id = (select auth.uid())
  )
)
with check (
  exists (
    select 1 from public.projects p
    where p.id = documents.project_id
      and p.owner_id = (select auth.uid())
  )
);

create policy "owners manage chunks in their projects"
on public.chunks for all to authenticated
using (
  exists (
    select 1 from public.projects p
    where p.id = chunks.project_id
      and p.owner_id = (select auth.uid())
  )
)
with check (
  exists (
    select 1 from public.projects p
    where p.id = chunks.project_id
      and p.owner_id = (select auth.uid())
  )
);

create policy "owners manage messages in their projects"
on public.messages for all to authenticated
using (
  exists (
    select 1 from public.projects p
    where p.id = messages.project_id
      and p.owner_id = (select auth.uid())
  )
)
with check (
  exists (
    select 1 from public.projects p
    where p.id = messages.project_id
      and p.owner_id = (select auth.uid())
  )
);

create policy "owners read usage for their projects"
on public.token_usages for all to authenticated
using (
  exists (
    select 1 from public.projects p
    where p.id = token_usages.project_id
      and p.owner_id = (select auth.uid())
  )
)
with check (
  exists (
    select 1 from public.projects p
    where p.id = token_usages.project_id
      and p.owner_id = (select auth.uid())
  )
);

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'stardust-project-files',
  'stardust-project-files',
  false,
  20971520,
  array[
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/pdf',
    'text/plain',
    'text/markdown',
    'image/png',
    'image/jpeg',
    'image/webp'
  ]
);

create policy "owners read project files"
on storage.objects for select to authenticated
using (
  bucket_id = 'stardust-project-files'
  and (storage.foldername(name))[1] = (select auth.uid()::text)
  and exists (
    select 1 from public.projects p
    where p.id = (storage.foldername(name))[2]
      and p.owner_id = (select auth.uid())
  )
);

create policy "owners upload project files"
on storage.objects for insert to authenticated
with check (
  bucket_id = 'stardust-project-files'
  and (storage.foldername(name))[1] = (select auth.uid()::text)
  and exists (
    select 1 from public.projects p
    where p.id = (storage.foldername(name))[2]
      and p.owner_id = (select auth.uid())
  )
);

create policy "owners update project files"
on storage.objects for update to authenticated
using (
  bucket_id = 'stardust-project-files'
  and (storage.foldername(name))[1] = (select auth.uid()::text)
  and exists (
    select 1 from public.projects p
    where p.id = (storage.foldername(name))[2]
      and p.owner_id = (select auth.uid())
  )
)
with check (
  bucket_id = 'stardust-project-files'
  and (storage.foldername(name))[1] = (select auth.uid()::text)
  and exists (
    select 1 from public.projects p
    where p.id = (storage.foldername(name))[2]
      and p.owner_id = (select auth.uid())
  )
);

create policy "owners delete project files"
on storage.objects for delete to authenticated
using (
  bucket_id = 'stardust-project-files'
  and (storage.foldername(name))[1] = (select auth.uid()::text)
  and exists (
    select 1 from public.projects p
    where p.id = (storage.foldername(name))[2]
      and p.owner_id = (select auth.uid())
  )
);
