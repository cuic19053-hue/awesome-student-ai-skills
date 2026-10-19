-- 只保存应用层 AES-GCM 密文，主密钥仅存在 Vercel 环境变量中。
create table public.user_model_configs (
  owner_id uuid primary key references auth.users(id) on delete cascade,
  ciphertext text not null check (octet_length(ciphertext) between 40 and 16384),
  updated_at timestamptz not null default now()
);
alter table public.user_model_configs enable row level security;
revoke all on public.user_model_configs from public, anon, authenticated;
grant select, insert, update, delete on public.user_model_configs to authenticated;
create policy own_model_config on public.user_model_configs
  for all to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));
