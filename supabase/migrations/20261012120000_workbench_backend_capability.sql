-- Narrow server capability for the Vercel application. The browser JWT
-- identifies the user; the separate, server-only secret authenticates the
-- application. This avoids putting Supabase's project-wide service_role key
-- in a serverless function.
create table public.workbench_backend_capability (
  singleton boolean primary key default true check (singleton),
  secret_hash bytea not null check (octet_length(secret_hash)=32)
);
alter table public.workbench_backend_capability enable row level security;
revoke all on public.workbench_backend_capability from public, anon, authenticated;
insert into public.workbench_backend_capability(singleton,secret_hash)
values (true,decode('f6445b8296945f898966bb4a438e010a8227dc9eb6606b309eef1420221bd618','hex'));

create or replace function public.workbench_check_backend(p_server_secret text)
returns void language plpgsql security definer
set search_path=pg_catalog,public as $$
begin
  if p_server_secret is null or octet_length(p_server_secret) <> 64 or
    not exists (
      select 1 from public.workbench_backend_capability
      where secret_hash = pg_catalog.sha256(convert_to(p_server_secret,'UTF8'))
    ) then
    raise exception 'server capability required' using errcode='42501';
  end if;
end $$;
revoke all on function public.workbench_check_backend(text) from public,anon,authenticated;

create or replace function public.workbench_backend_lookup_paired_voucher(
  p_code_hash bytea,p_server_secret text
) returns jsonb language plpgsql security definer
set search_path=pg_catalog,public as $$
begin
  perform public.workbench_check_backend(p_server_secret);
  if (select auth.uid()) is null then
    raise exception 'authentication required' using errcode='42501';
  end if;
  return public.workbench_lookup_paired_voucher(p_code_hash);
end $$;

create or replace function public.workbench_backend_begin_card_redemption(
  p_user_id uuid,p_code_hash bytea,p_code_ciphertext bytea,p_server_secret text
) returns jsonb language plpgsql security definer
set search_path=pg_catalog,public as $$
begin
  perform public.workbench_check_backend(p_server_secret);
  if p_user_id is distinct from (select auth.uid()) then
    raise exception 'identity mismatch' using errcode='42501';
  end if;
  return public.workbench_begin_card_redemption(p_user_id,p_code_hash,p_code_ciphertext);
end $$;

create or replace function public.workbench_backend_get_intent(
  p_intent_id uuid,p_user_id uuid,p_server_secret text
) returns jsonb language plpgsql security definer
set search_path=pg_catalog,public as $$
declare v public.workbench_card_redemptions%rowtype;
begin
  perform public.workbench_check_backend(p_server_secret);
  if p_user_id is distinct from (select auth.uid()) then
    raise exception 'identity mismatch' using errcode='42501';
  end if;
  select * into v from public.workbench_card_redemptions
  where id=p_intent_id and user_id=p_user_id;
  if not found then return '{}'::jsonb; end if;
  return jsonb_build_object(
    'id',v.id,'user_id',v.user_id,'status',v.status,
    'code_ciphertext',case when v.code_ciphertext is null then null
      else encode(v.code_ciphertext,'hex') end,
    'safe_message',v.safe_message,'face_value_micro_cny',v.face_value_micro_cny
  );
end $$;

create or replace function public.workbench_backend_complete_paired_voucher(
  p_intent_id uuid,p_face_value_micro_cny bigint,p_provider_user_id bigint,
  p_server_secret text
) returns jsonb language plpgsql security definer
set search_path=pg_catalog,public as $$
begin
  perform public.workbench_check_backend(p_server_secret);
  if not exists (
    select 1 from public.workbench_card_redemptions
    where id=p_intent_id and user_id=(select auth.uid())
  ) then
    raise exception 'identity mismatch' using errcode='42501';
  end if;
  return public.workbench_complete_paired_voucher(
    p_intent_id,p_face_value_micro_cny,p_provider_user_id
  );
end $$;

create or replace function public.workbench_backend_set_card_redemption_status(
  p_intent_id uuid,p_status text,p_safe_message text,p_server_secret text
) returns void language plpgsql security definer
set search_path=pg_catalog,public as $$
begin
  perform public.workbench_check_backend(p_server_secret);
  if not exists (
    select 1 from public.workbench_card_redemptions
    where id=p_intent_id and user_id=(select auth.uid())
  ) then
    raise exception 'identity mismatch' using errcode='42501';
  end if;
  perform public.workbench_set_card_redemption_status(p_intent_id,p_status,p_safe_message);
end $$;

create or replace function public.workbench_backend_reserve_usage(
  p_user_id uuid,p_request_id text,p_model text,p_reserved_micro_cny bigint,
  p_api_key_id bigint,p_server_secret text
) returns jsonb language plpgsql security definer
set search_path=pg_catalog,public as $$
begin
  perform public.workbench_check_backend(p_server_secret);
  if p_user_id is distinct from (select auth.uid()) then
    raise exception 'identity mismatch' using errcode='42501';
  end if;
  return public.workbench_reserve_usage(
    p_user_id,p_request_id,p_model,p_reserved_micro_cny,p_api_key_id
  );
end $$;

create or replace function public.workbench_backend_settle_usage(
  p_request_id text,p_actual_micro_cny bigint,p_provider_request_id text,
  p_server_secret text
) returns jsonb language plpgsql security definer
set search_path=pg_catalog,public as $$
begin
  perform public.workbench_check_backend(p_server_secret);
  if not exists (
    select 1 from public.workbench_usage_events
    where request_id=p_request_id and user_id=(select auth.uid())
  ) then
    raise exception 'identity mismatch' using errcode='42501';
  end if;
  return public.workbench_settle_usage(p_request_id,p_actual_micro_cny,p_provider_request_id);
end $$;

create or replace function public.workbench_backend_refund_usage(
  p_request_id text,p_reason text,p_server_secret text
) returns jsonb language plpgsql security definer
set search_path=pg_catalog,public as $$
begin
  perform public.workbench_check_backend(p_server_secret);
  if not exists (
    select 1 from public.workbench_usage_events
    where request_id=p_request_id and user_id=(select auth.uid())
  ) then
    raise exception 'identity mismatch' using errcode='42501';
  end if;
  return public.workbench_refund_usage(p_request_id,p_reason);
end $$;

revoke all on function public.workbench_backend_lookup_paired_voucher(bytea,text),
  public.workbench_backend_begin_card_redemption(uuid,bytea,bytea,text),
  public.workbench_backend_get_intent(uuid,uuid,text),
  public.workbench_backend_complete_paired_voucher(uuid,bigint,bigint,text),
  public.workbench_backend_set_card_redemption_status(uuid,text,text,text),
  public.workbench_backend_reserve_usage(uuid,text,text,bigint,bigint,text),
  public.workbench_backend_settle_usage(text,bigint,text,text),
  public.workbench_backend_refund_usage(text,text,text)
from public,anon,authenticated;
grant execute on function public.workbench_backend_lookup_paired_voucher(bytea,text),
  public.workbench_backend_begin_card_redemption(uuid,bytea,bytea,text),
  public.workbench_backend_get_intent(uuid,uuid,text),
  public.workbench_backend_complete_paired_voucher(uuid,bigint,bigint,text),
  public.workbench_backend_set_card_redemption_status(uuid,text,text,text),
  public.workbench_backend_reserve_usage(uuid,text,text,bigint,bigint,text),
  public.workbench_backend_settle_usage(text,bigint,text,text),
  public.workbench_backend_refund_usage(text,text,text)
to authenticated;
