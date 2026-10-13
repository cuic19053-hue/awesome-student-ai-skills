-- Workbench-issued shop vouchers. Codes are kept only in a private seller CSV;
-- the database stores SHA-256 digests of high-entropy AGT1 codes. Newly
-- imported vouchers are drafts and cannot be redeemed until explicitly
-- activated after shop import and funding reconciliation.
create table public.workbench_vouchers (
  id uuid primary key default gen_random_uuid(),
  batch_id uuid not null,
  code_hash bytea not null unique check (octet_length(code_hash) = 32),
  face_value_micro_cny bigint not null check (face_value_micro_cny > 0),
  status text not null default 'draft'
    check (status in ('draft', 'active', 'redeemed', 'revoked')),
  redeemed_by uuid references auth.users(id) on delete set null,
  redeemed_at timestamptz,
  transaction_id uuid references public.workbench_credit_transactions(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index workbench_vouchers_batch_status_idx
  on public.workbench_vouchers (batch_id, status);
create index workbench_vouchers_redeemed_by_idx
  on public.workbench_vouchers (redeemed_by)
  where redeemed_by is not null;
create index workbench_vouchers_transaction_id_idx
  on public.workbench_vouchers (transaction_id)
  where transaction_id is not null;

alter table public.workbench_vouchers enable row level security;
revoke all on public.workbench_vouchers from anon, authenticated;
grant select, insert, update on public.workbench_vouchers to service_role;
create policy "deny direct voucher access"
  on public.workbench_vouchers for all to anon, authenticated
  using (false) with check (false);

-- The code itself is a 128-bit bearer secret. Only a verified Supabase user
-- may redeem it, and the caller cannot specify the credited user or amount.
create or replace function public.workbench_redeem_voucher(p_code text)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  v_user_id uuid := (select auth.uid());
  v_code text;
  v_voucher public.workbench_vouchers%rowtype;
  v_balance bigint;
  v_transaction_id uuid;
begin
  if v_user_id is null then
    raise exception 'authentication required' using errcode = '42501';
  end if;
  if p_code is null or length(p_code) > 128 then
    raise exception 'invalid voucher code' using errcode = '22023';
  end if;
  v_code := upper(regexp_replace(p_code, '[[:space:]]', '', 'g'));
  if v_code !~ '^AGT1-([0-9A-F]{8}-){3}[0-9A-F]{8}$' then
    raise exception 'invalid voucher code' using errcode = '22023';
  end if;

  select * into v_voucher
  from public.workbench_vouchers
  where code_hash = pg_catalog.sha256(
    convert_to('workbench-voucher-v1:' || v_code, 'UTF8')
  )
  for update;
  if not found then
    raise exception 'voucher not found' using errcode = 'P0002';
  end if;
  if v_voucher.status = 'redeemed' then
    if v_voucher.redeemed_by <> v_user_id then
      raise exception 'voucher already redeemed' using errcode = '23505';
    end if;
    select balance_micro_cny into v_balance
    from public.workbench_credit_wallets where user_id = v_user_id;
    return jsonb_build_object(
      'duplicate', true,
      'credited_micro_cny', v_voucher.face_value_micro_cny,
      'balance_micro_cny', coalesce(v_balance, 0)
    );
  end if;
  if v_voucher.status <> 'active' then
    raise exception 'voucher not active' using errcode = '55000';
  end if;

  insert into public.workbench_credit_wallets(user_id)
  values (v_user_id)
  on conflict (user_id) do nothing;
  select balance_micro_cny into v_balance
  from public.workbench_credit_wallets
  where user_id = v_user_id for update;
  update public.workbench_credit_wallets
  set balance_micro_cny = balance_micro_cny + v_voucher.face_value_micro_cny,
      total_credited_micro_cny = total_credited_micro_cny + v_voucher.face_value_micro_cny,
      updated_at = now()
  where user_id = v_user_id
  returning balance_micro_cny into v_balance;

  insert into public.workbench_credit_transactions(
    user_id, delta_micro_cny, balance_after_micro_cny, kind, reference_id
  ) values (
    v_user_id, v_voucher.face_value_micro_cny, v_balance,
    'card_redeem', v_voucher.id::text
  ) returning id into v_transaction_id;
  update public.workbench_vouchers
  set status = 'redeemed', redeemed_by = v_user_id, redeemed_at = now(),
      transaction_id = v_transaction_id, updated_at = now()
  where id = v_voucher.id;

  return jsonb_build_object(
    'duplicate', false,
    'credited_micro_cny', v_voucher.face_value_micro_cny,
    'balance_micro_cny', v_balance
  );
end;
$$;

revoke all on function public.workbench_redeem_voucher(text)
  from public, anon, authenticated;
grant execute on function public.workbench_redeem_voucher(text)
  to authenticated, service_role;
