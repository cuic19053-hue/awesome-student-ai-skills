-- Card-code redemption and user-owned workbench credits.
-- One credit unit is one micro-CNY; display points are units / 10,000
-- (100 points per CNY). All writes go through server-only RPC functions.

create table public.workbench_credit_wallets (
  user_id uuid primary key references auth.users(id) on delete cascade,
  balance_micro_cny bigint not null default 0 check (balance_micro_cny >= 0),
  total_credited_micro_cny bigint not null default 0 check (total_credited_micro_cny >= 0),
  total_spent_micro_cny bigint not null default 0 check (total_spent_micro_cny >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.workbench_credit_transactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  delta_micro_cny bigint not null check (delta_micro_cny <> 0),
  balance_after_micro_cny bigint not null check (balance_after_micro_cny >= 0),
  kind text not null check (kind in ('card_redeem', 'payment_credit', 'usage_reserve', 'usage_settle', 'usage_refund', 'admin_adjustment')),
  reference_id text not null,
  model text,
  request_id text,
  created_at timestamptz not null default now(),
  constraint workbench_credit_transactions_user_ref_unique unique (user_id, kind, reference_id)
);

create index workbench_credit_transactions_user_created_idx
  on public.workbench_credit_transactions (user_id, created_at desc);
create unique index workbench_payment_event_unique_idx
  on public.workbench_credit_transactions (reference_id)
  where kind = 'payment_credit';
create index workbench_credit_transactions_request_idx
  on public.workbench_credit_transactions (request_id)
  where request_id is not null;

-- Payment provider webhooks are authenticated by the application server.
-- The payment event id makes retries idempotent; only the paid order's
-- workbench user receives the credits.
create or replace function public.workbench_grant_payment_credits(
  p_user_id uuid,
  p_event_id text,
  p_amount_micro_cny bigint
) returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  v_balance bigint;
  v_existing public.workbench_credit_transactions%rowtype;
begin
  if p_user_id is null or p_event_id is null or length(trim(p_event_id)) < 8
     or length(p_event_id) > 160 or p_amount_micro_cny is null
     or p_amount_micro_cny <= 0 then
    raise exception 'invalid payment credit event' using errcode = '22023';
  end if;

  perform pg_advisory_xact_lock(hashtextextended(p_event_id, 0));

  insert into public.workbench_credit_wallets(user_id)
  values (p_user_id)
  on conflict (user_id) do nothing;

  select balance_micro_cny into v_balance
  from public.workbench_credit_wallets
  where user_id = p_user_id
  for update;

  select * into v_existing
  from public.workbench_credit_transactions
  where kind = 'payment_credit'
    and reference_id = p_event_id;

  if found then
    if v_existing.user_id <> p_user_id then
      raise exception 'payment event already assigned to another user' using errcode = '23505';
    end if;
    return jsonb_build_object(
      'duplicate', true,
      'balance_micro_cny', v_balance,
      'credited_micro_cny', v_existing.delta_micro_cny
    );
  end if;

  update public.workbench_credit_wallets
  set balance_micro_cny = balance_micro_cny + p_amount_micro_cny,
      total_credited_micro_cny = total_credited_micro_cny + p_amount_micro_cny,
      updated_at = now()
  where user_id = p_user_id
  returning balance_micro_cny into v_balance;

  insert into public.workbench_credit_transactions(
    user_id, delta_micro_cny, balance_after_micro_cny, kind, reference_id
  ) values (
    p_user_id, p_amount_micro_cny, v_balance, 'payment_credit', p_event_id
  );

  return jsonb_build_object(
    'duplicate', false,
    'balance_micro_cny', v_balance,
    'credited_micro_cny', p_amount_micro_cny
  );
end;
$$;

-- Raw card codes are encrypted by the application and only readable by the
-- service role for reconciliation after an uncertain upstream response.
create table public.workbench_card_redemptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  code_hash bytea not null unique,
  code_ciphertext bytea,
  status text not null default 'pending'
    check (status in ('pending', 'credited', 'rejected', 'needs_review')),
  face_value_micro_cny bigint check (face_value_micro_cny is null or face_value_micro_cny > 0),
  provider_user_id bigint,
  provider_redeemed_at timestamptz,
  transaction_id uuid references public.workbench_credit_transactions(id),
  safe_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index workbench_card_redemptions_user_created_idx
  on public.workbench_card_redemptions (user_id, created_at desc);

create table public.workbench_usage_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  request_id text not null unique,
  api_key_id bigint,
  model text not null,
  reserved_micro_cny bigint not null check (reserved_micro_cny > 0),
  actual_micro_cny bigint check (actual_micro_cny is null or actual_micro_cny >= 0),
  provider_request_id text,
  status text not null default 'reserved'
    check (status in ('reserved', 'settled', 'refunded', 'needs_review')),
  created_at timestamptz not null default now(),
  settled_at timestamptz
);

create index workbench_usage_events_user_created_idx
  on public.workbench_usage_events (user_id, created_at desc);
create index workbench_usage_events_key_created_idx
  on public.workbench_usage_events (api_key_id, created_at desc)
  where api_key_id is not null;

alter table public.workbench_credit_wallets enable row level security;
alter table public.workbench_credit_transactions enable row level security;
alter table public.workbench_card_redemptions enable row level security;
alter table public.workbench_usage_events enable row level security;

revoke all on public.workbench_credit_wallets,
  public.workbench_credit_transactions,
  public.workbench_card_redemptions from anon, authenticated;
grant select on public.workbench_credit_wallets,
  public.workbench_credit_transactions,
  public.workbench_usage_events to authenticated;
grant select, insert, update on public.workbench_credit_wallets,
  public.workbench_credit_transactions,
  public.workbench_card_redemptions,
  public.workbench_usage_events to service_role;

create policy "users read own credit wallet"
  on public.workbench_credit_wallets for select to authenticated
  using ((select auth.uid()) = user_id);

create policy "users read own credit transactions"
  on public.workbench_credit_transactions for select to authenticated
  using ((select auth.uid()) = user_id);

create policy "users read own usage events"
  on public.workbench_usage_events for select to authenticated
  using ((select auth.uid()) = user_id);

-- No client policy for card-redemption intents: they contain encrypted bearer
-- codes and are only accessed by the trusted application server.

create or replace function public.workbench_begin_card_redemption(
  p_user_id uuid,
  p_code_hash bytea,
  p_code_ciphertext bytea
) returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  v_intent public.workbench_card_redemptions%rowtype;
  v_recent_count integer;
begin
  if p_user_id is null or p_code_hash is null or octet_length(p_code_hash) <> 32
     or p_code_ciphertext is null then
    raise exception 'invalid redemption request' using errcode = '22023';
  end if;

  -- Serialize per-user card submissions so concurrent requests cannot bypass
  -- the hourly guard. Duplicate submissions are returned without re-counting.
  perform pg_advisory_xact_lock(hashtextextended(p_user_id::text, 0));

  select * into v_intent
  from public.workbench_card_redemptions
  where code_hash = p_code_hash;
  if found then
    if v_intent.user_id <> p_user_id then
      raise exception 'card already claimed' using errcode = '23505';
    end if;
    return jsonb_build_object(
      'intent_id', v_intent.id,
      'status', v_intent.status,
      'face_value_micro_cny', v_intent.face_value_micro_cny,
      'duplicate', true
    );
  end if;

  select count(*) into v_recent_count
  from public.workbench_card_redemptions
  where user_id = p_user_id and created_at >= now() - interval '1 hour';
  if v_recent_count >= 10 then
    raise exception 'card redemption rate limit exceeded' using errcode = '54000';
  end if;

  insert into public.workbench_card_redemptions(user_id, code_hash, code_ciphertext)
  values (p_user_id, p_code_hash, p_code_ciphertext)
  returning * into v_intent;

  return jsonb_build_object(
    'intent_id', v_intent.id,
    'status', v_intent.status,
    'face_value_micro_cny', v_intent.face_value_micro_cny,
    'duplicate', false
  );
end;
$$;

create or replace function public.workbench_complete_card_redemption(
  p_intent_id uuid,
  p_face_value_micro_cny bigint,
  p_provider_user_id bigint
) returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  v_intent public.workbench_card_redemptions%rowtype;
  v_balance bigint;
  v_tx public.workbench_credit_transactions%rowtype;
begin
  if p_face_value_micro_cny is null or p_face_value_micro_cny <= 0 then
    raise exception 'invalid card value' using errcode = '22023';
  end if;

  select * into v_intent
  from public.workbench_card_redemptions
  where id = p_intent_id
  for update;

  if not found then
    raise exception 'redemption intent not found' using errcode = 'P0002';
  end if;

  if v_intent.status = 'credited' then
    select * into v_tx from public.workbench_credit_transactions
    where id = v_intent.transaction_id;
    return jsonb_build_object(
      'status', 'credited',
      'duplicate', true,
      'balance_micro_cny', v_tx.balance_after_micro_cny
    );
  end if;

  if v_intent.status not in ('pending', 'needs_review') then
    raise exception 'redemption intent is not completable' using errcode = '55000';
  end if;

  insert into public.workbench_credit_wallets(user_id)
  values (v_intent.user_id)
  on conflict (user_id) do nothing;

  select balance_micro_cny into v_balance
  from public.workbench_credit_wallets
  where user_id = v_intent.user_id
  for update;

  update public.workbench_credit_wallets
  set balance_micro_cny = balance_micro_cny + p_face_value_micro_cny,
      total_credited_micro_cny = total_credited_micro_cny + p_face_value_micro_cny,
      updated_at = now()
  where user_id = v_intent.user_id
  returning balance_micro_cny into v_balance;

  insert into public.workbench_credit_transactions(
    user_id, delta_micro_cny, balance_after_micro_cny, kind, reference_id
  ) values (
    v_intent.user_id, p_face_value_micro_cny, v_balance, 'card_redeem', v_intent.id::text
  ) returning * into v_tx;

  update public.workbench_card_redemptions
  set status = 'credited',
      face_value_micro_cny = p_face_value_micro_cny,
      provider_user_id = p_provider_user_id,
      provider_redeemed_at = now(),
      transaction_id = v_tx.id,
      code_ciphertext = null,
      safe_message = null,
      updated_at = now()
  where id = p_intent_id;

  return jsonb_build_object(
    'status', 'credited',
    'duplicate', false,
    'balance_micro_cny', v_balance,
    'transaction_id', v_tx.id
  );
end;
$$;

create or replace function public.workbench_set_card_redemption_status(
  p_intent_id uuid,
  p_status text,
  p_safe_message text
) returns void
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
begin
  if p_status not in ('pending', 'rejected', 'needs_review') then
    raise exception 'invalid redemption status' using errcode = '22023';
  end if;
  update public.workbench_card_redemptions
  set status = p_status,
      safe_message = left(coalesce(p_safe_message, ''), 240),
      code_ciphertext = case when p_status = 'rejected' then null else code_ciphertext end,
      updated_at = now()
  where id = p_intent_id and status <> 'credited';
  if not found then
    raise exception 'redemption intent not found or already credited' using errcode = 'P0002';
  end if;
end;
$$;

create or replace function public.workbench_reserve_usage(
  p_user_id uuid,
  p_request_id text,
  p_model text,
  p_reserved_micro_cny bigint,
  p_api_key_id bigint default null
) returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  v_event public.workbench_usage_events%rowtype;
  v_balance bigint;
  v_inserted integer;
begin
  if p_user_id is null or length(p_request_id) < 8 or length(p_request_id) > 128
     or p_model is null or length(p_model) > 160
     or p_reserved_micro_cny <= 0 then
    raise exception 'invalid usage reservation' using errcode = '22023';
  end if;

  insert into public.workbench_credit_wallets(user_id)
  values (p_user_id)
  on conflict (user_id) do nothing;

  select balance_micro_cny into v_balance
  from public.workbench_credit_wallets where user_id = p_user_id for update;

  insert into public.workbench_usage_events(
    user_id, request_id, model, reserved_micro_cny, api_key_id
  ) values (
    p_user_id, p_request_id, p_model, p_reserved_micro_cny, p_api_key_id
  ) on conflict (request_id) do nothing;
  get diagnostics v_inserted = row_count;

  select * into v_event from public.workbench_usage_events
  where request_id = p_request_id for update;

  if v_event.user_id <> p_user_id then
    raise exception 'request belongs to another user' using errcode = '23505';
  end if;
  if v_inserted = 0 then
    return jsonb_build_object('status', v_event.status, 'duplicate', true, 'balance_micro_cny', v_balance);
  end if;
  if v_balance < p_reserved_micro_cny then
    delete from public.workbench_usage_events where id = v_event.id;
    raise exception 'insufficient workbench credits' using errcode = '23514';
  end if;

  update public.workbench_credit_wallets
  set balance_micro_cny = balance_micro_cny - p_reserved_micro_cny,
      updated_at = now()
  where user_id = p_user_id
  returning balance_micro_cny into v_balance;

  insert into public.workbench_credit_transactions(
    user_id, delta_micro_cny, balance_after_micro_cny, kind, reference_id, model, request_id
  ) values (
    p_user_id, -p_reserved_micro_cny, v_balance, 'usage_reserve', p_request_id, p_model, p_request_id
  );

  return jsonb_build_object(
    'status', 'reserved', 'duplicate', false, 'balance_micro_cny', v_balance,
    'reservation_id', v_event.id
  );
end;
$$;

create or replace function public.workbench_settle_usage(
  p_request_id text,
  p_actual_micro_cny bigint,
  p_provider_request_id text default null
) returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  v_event public.workbench_usage_events%rowtype;
  v_balance bigint;
  v_refund bigint;
begin
  if p_actual_micro_cny is null or p_actual_micro_cny < 0 then
    raise exception 'invalid actual usage amount' using errcode = '22023';
  end if;
  select * into v_event from public.workbench_usage_events
  where request_id = p_request_id for update;
  if not found then
    raise exception 'usage reservation not found' using errcode = 'P0002';
  end if;
  if v_event.status = 'settled' then
    select balance_micro_cny into v_balance from public.workbench_credit_wallets where user_id = v_event.user_id;
    return jsonb_build_object('status', 'settled', 'duplicate', true, 'balance_micro_cny', v_balance);
  end if;
  if v_event.status <> 'reserved' then
    raise exception 'usage event is not settleable' using errcode = '55000';
  end if;
  if p_actual_micro_cny > v_event.reserved_micro_cny then
    update public.workbench_usage_events
    set status = 'needs_review', actual_micro_cny = p_actual_micro_cny,
        provider_request_id = p_provider_request_id
    where id = v_event.id;
    return jsonb_build_object(
      'status', 'needs_review',
      'duplicate', false,
      'reserved_micro_cny', v_event.reserved_micro_cny,
      'actual_micro_cny', p_actual_micro_cny
    );
  end if;

  v_refund := v_event.reserved_micro_cny - p_actual_micro_cny;
  update public.workbench_credit_wallets
  set balance_micro_cny = balance_micro_cny + v_refund,
      total_spent_micro_cny = total_spent_micro_cny + p_actual_micro_cny,
      updated_at = now()
  where user_id = v_event.user_id
  returning balance_micro_cny into v_balance;

  if v_refund > 0 then
    insert into public.workbench_credit_transactions(
      user_id, delta_micro_cny, balance_after_micro_cny, kind, reference_id, model, request_id
    ) values (
      v_event.user_id, v_refund, v_balance, 'usage_settle', p_request_id, v_event.model, p_request_id
    ) on conflict (user_id, kind, reference_id) do nothing;
  end if;

  update public.workbench_usage_events
  set status = 'settled', actual_micro_cny = p_actual_micro_cny,
      provider_request_id = p_provider_request_id, settled_at = now()
  where id = v_event.id;
  return jsonb_build_object('status', 'settled', 'duplicate', false, 'balance_micro_cny', v_balance);
end;
$$;

create or replace function public.workbench_refund_usage(
  p_request_id text,
  p_reason text default 'provider_error'
) returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  v_event public.workbench_usage_events%rowtype;
  v_balance bigint;
begin
  select * into v_event from public.workbench_usage_events
  where request_id = p_request_id for update;
  if not found then
    raise exception 'usage reservation not found' using errcode = 'P0002';
  end if;
  if v_event.status = 'refunded' then
    select balance_micro_cny into v_balance from public.workbench_credit_wallets where user_id = v_event.user_id;
    return jsonb_build_object('status', 'refunded', 'duplicate', true, 'balance_micro_cny', v_balance);
  end if;
  if v_event.status <> 'reserved' then
    raise exception 'usage event is not refundable' using errcode = '55000';
  end if;
  update public.workbench_credit_wallets
  set balance_micro_cny = balance_micro_cny + v_event.reserved_micro_cny, updated_at = now()
  where user_id = v_event.user_id
  returning balance_micro_cny into v_balance;
  insert into public.workbench_credit_transactions(
    user_id, delta_micro_cny, balance_after_micro_cny, kind, reference_id, model, request_id
  ) values (
    v_event.user_id, v_event.reserved_micro_cny, v_balance, 'usage_refund', p_request_id, v_event.model, p_request_id
  ) on conflict (user_id, kind, reference_id) do nothing;
  update public.workbench_usage_events
  set status = 'refunded', settled_at = now()
  where id = v_event.id;
  return jsonb_build_object('status', 'refunded', 'duplicate', false, 'balance_micro_cny', v_balance);
end;
$$;

revoke all on function public.workbench_begin_card_redemption(uuid, bytea, bytea) from public, anon, authenticated;
revoke all on function public.workbench_grant_payment_credits(uuid, text, bigint) from public, anon, authenticated;
revoke all on function public.workbench_complete_card_redemption(uuid, bigint, bigint) from public, anon, authenticated;
revoke all on function public.workbench_set_card_redemption_status(uuid, text, text) from public, anon, authenticated;
revoke all on function public.workbench_reserve_usage(uuid, text, text, bigint, bigint) from public, anon, authenticated;
revoke all on function public.workbench_settle_usage(text, bigint, text) from public, anon, authenticated;
revoke all on function public.workbench_refund_usage(text, text) from public, anon, authenticated;
grant execute on function public.workbench_begin_card_redemption(uuid, bytea, bytea) to service_role;
grant execute on function public.workbench_grant_payment_credits(uuid, text, bigint) to service_role;
grant execute on function public.workbench_complete_card_redemption(uuid, bigint, bigint) to service_role;
grant execute on function public.workbench_set_card_redemption_status(uuid, text, text) to service_role;
grant execute on function public.workbench_reserve_usage(uuid, text, text, bigint, bigint) to service_role;
grant execute on function public.workbench_settle_usage(text, bigint, text) to service_role;
grant execute on function public.workbench_refund_usage(text, text) to service_role;
