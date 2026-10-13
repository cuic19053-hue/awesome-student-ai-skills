-- AGT1 is a shop-only bearer code. Its paired Wopally balance code is
-- encrypted and never disclosed to a buyer or to the authenticated role.
alter table public.workbench_vouchers
  add column provider_code_ciphertext bytea;

create or replace function public.workbench_lookup_paired_voucher(p_code_hash bytea)
returns jsonb
language plpgsql security definer
set search_path = pg_catalog, public
as $$
declare v public.workbench_vouchers%rowtype;
begin
  if p_code_hash is null or octet_length(p_code_hash) <> 32 then
    raise exception 'invalid voucher digest' using errcode = '22023';
  end if;
  select * into v from public.workbench_vouchers where code_hash = p_code_hash;
  if not found then
    raise exception 'voucher not found' using errcode = 'P0002';
  end if;
  if v.status not in ('active','redeemed') or v.provider_code_ciphertext is null then
    raise exception 'voucher not ready' using errcode = '55000';
  end if;
  return jsonb_build_object(
    'id', v.id, 'status', v.status, 'face_value_micro_cny', v.face_value_micro_cny,
    'redeemed_by', v.redeemed_by,
    'provider_code_ciphertext', encode(v.provider_code_ciphertext, 'hex')
  );
end;
$$;

-- Wrapper keeps the provider-confirmed credit and voucher lifecycle in
-- one Postgres transaction. A mismatch rolls back everything.
create or replace function public.workbench_complete_paired_voucher(
  p_intent_id uuid, p_face_value_micro_cny bigint, p_provider_user_id bigint
) returns jsonb
language plpgsql security definer
set search_path = pg_catalog, public
as $$
declare
  v public.workbench_vouchers%rowtype;
  i public.workbench_card_redemptions%rowtype;
  result jsonb;
begin
  select * into i from public.workbench_card_redemptions
  where id = p_intent_id for update;
  if not found then raise exception 'intent not found' using errcode = 'P0002'; end if;
  select * into v from public.workbench_vouchers
  where code_hash = i.code_hash for update;
  if not found or v.provider_code_ciphertext is null
     or v.face_value_micro_cny <> p_face_value_micro_cny
     or v.status not in ('active','redeemed') then
    raise exception 'voucher mismatch' using errcode = '23514';
  end if;
  if v.status = 'redeemed' and v.redeemed_by <> i.user_id then
    raise exception 'voucher claimed by another user' using errcode = '23505';
  end if;
  if p_provider_user_id is null then
    raise exception 'provider account not verified' using errcode = '22023';
  end if;
  result := public.workbench_complete_card_redemption(
    p_intent_id, p_face_value_micro_cny, p_provider_user_id
  );
  update public.workbench_vouchers
  set status='redeemed', redeemed_by=i.user_id, redeemed_at=coalesce(redeemed_at,now()),
      transaction_id=(select transaction_id from public.workbench_card_redemptions where id=p_intent_id),
      updated_at=now()
  where id=v.id;
  return result;
end;
$$;

-- The older direct-credit RPC must no longer credit a shop code without
-- a confirmed provider redemption.
revoke all on function public.workbench_redeem_voucher(text)
  from public, anon, authenticated, service_role;
revoke all on function public.workbench_lookup_paired_voucher(bytea)
  from public, anon, authenticated;
revoke all on function public.workbench_complete_paired_voucher(uuid,bigint,bigint)
  from public, anon, authenticated;
grant execute on function public.workbench_lookup_paired_voucher(bytea) to service_role;
grant execute on function public.workbench_complete_paired_voucher(uuid,bigint,bigint) to service_role;
