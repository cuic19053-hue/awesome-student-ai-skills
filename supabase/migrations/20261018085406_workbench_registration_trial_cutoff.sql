-- User-approved boundary: 2026-10-18 16:51:47 Asia/Shanghai.
-- Registration time comes from auth.users, never user-editable metadata.
-- This migration changes trial counts only; it never changes monetary balances.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE public.workbench_credit_wallets
  ALTER COLUMN free_chat_count SET DEFAULT 0;

CREATE OR REPLACE FUNCTION public.workbench_enforce_trial_billing()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog AS $$
BEGIN
  IF NEW.total_credited_micro_cny > 0 OR NEW.balance_micro_cny > 0
     OR NEW.total_spent_micro_cny > 0 OR EXISTS (
       SELECT 1 FROM auth.users u
       WHERE u.id = NEW.user_id
         AND (u.created_at IS NULL OR u.created_at <= timestamptz '2026-10-18 08:51:47+00')
     ) THEN
    NEW.free_chat_count := 0;
  END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.workbench_enforce_trial_billing()
  FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE TRIGGER workbench_enforce_trial_billing
BEFORE INSERT OR UPDATE ON public.workbench_credit_wallets
FOR EACH ROW EXECUTE FUNCTION public.workbench_enforce_trial_billing();

UPDATE public.workbench_credit_wallets w
SET free_chat_count = 0, updated_at = now()
WHERE w.free_chat_count <> 0 AND (
  w.total_credited_micro_cny > 0 OR w.balance_micro_cny > 0
  OR w.total_spent_micro_cny > 0 OR EXISTS (
    SELECT 1 FROM auth.users u
    WHERE u.id = w.user_id
      AND (u.created_at IS NULL OR u.created_at <= timestamptz '2026-10-18 08:51:47+00')
  )
);

CREATE OR REPLACE FUNCTION public.workbench_consume_free_chat(p_user_id uuid)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog AS $$
DECLARE v_remaining integer;
BEGIN
  IF p_user_id IS NULL THEN
    RAISE EXCEPTION 'user_id required' USING ERRCODE = '22023';
  END IF;
  IF (SELECT auth.uid()) IS NOT NULL AND p_user_id IS DISTINCT FROM (SELECT auth.uid()) THEN
    RAISE EXCEPTION 'identity mismatch' USING ERRCODE = '42501';
  END IF;
  -- A missing wallet must not manufacture a new registration/trial.
  UPDATE public.workbench_credit_wallets w
  SET free_chat_count = w.free_chat_count - 1, updated_at = now()
  WHERE w.user_id = p_user_id AND w.free_chat_count > 0
    AND w.total_credited_micro_cny = 0 AND w.balance_micro_cny = 0
    AND w.total_spent_micro_cny = 0
    AND EXISTS (
      SELECT 1 FROM auth.users u WHERE u.id = p_user_id
        AND u.created_at > timestamptz '2026-10-18 08:51:47+00'
    )
  RETURNING w.free_chat_count INTO v_remaining;
  RETURN COALESCE(v_remaining, -1);
END $$;

CREATE OR REPLACE FUNCTION public.workbench_refund_free_chat(p_user_id uuid)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog AS $$
DECLARE v_remaining integer;
BEGIN
  IF p_user_id IS NULL THEN
    RAISE EXCEPTION 'user_id required' USING ERRCODE = '22023';
  END IF;
  IF (SELECT auth.uid()) IS NOT NULL AND p_user_id IS DISTINCT FROM (SELECT auth.uid()) THEN
    RAISE EXCEPTION 'identity mismatch' USING ERRCODE = '42501';
  END IF;
  -- A delayed failure from before recharge must not reactivate a trial.
  UPDATE public.workbench_credit_wallets w
  SET free_chat_count = LEAST(3, w.free_chat_count + 1), updated_at = now()
  WHERE w.user_id = p_user_id AND w.total_credited_micro_cny = 0
    AND w.balance_micro_cny = 0 AND w.total_spent_micro_cny = 0
    AND EXISTS (
      SELECT 1 FROM auth.users u WHERE u.id = p_user_id
        AND u.created_at > timestamptz '2026-10-18 08:51:47+00'
    )
  RETURNING w.free_chat_count INTO v_remaining;
  RETURN COALESCE(v_remaining, 0);
END $$;

-- These raw mutations are server-only. Authenticated users must go through
-- the existing backend wrappers, which check BOTH the JWT owner and server secret.
REVOKE ALL ON FUNCTION public.workbench_consume_free_chat(uuid),
  public.workbench_refund_free_chat(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.workbench_consume_free_chat(uuid),
  public.workbench_refund_free_chat(uuid) TO service_role;
REVOKE ALL ON FUNCTION public.workbench_backend_consume_free_chat(uuid, text),
  public.workbench_backend_refund_free_chat(uuid, text) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.workbench_backend_consume_free_chat(uuid, text),
  public.workbench_backend_refund_free_chat(uuid, text) TO authenticated;

CREATE OR REPLACE FUNCTION public.handle_new_user_welcome_credits()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog AS $$
DECLARE
  v_domain text;
  v_today_grants integer;
  v_count integer := 0;
BEGIN
  v_domain := lower(split_part(COALESCE(NEW.email, ''), '@', 2));
  -- Preserve existing signup-domain and daily-grant safeguards.
  IF NEW.created_at > timestamptz '2026-10-18 08:51:47+00'
     AND (v_domain IN ('qq.com', 'foxmail.com', '163.com', '126.com', 'sina.com',
                      'gmail.com', 'outlook.com', 'hotmail.com')
          OR v_domain LIKE '%.edu.cn' OR v_domain = 'edu.cn') THEN
    SELECT count(*) INTO v_today_grants
    FROM public.workbench_credit_wallets
    WHERE created_at >= date_trunc('day', now()) AND free_chat_count > 0;
    IF v_today_grants < 100 THEN v_count := 3; END IF;
  END IF;
  INSERT INTO public.workbench_credit_wallets
    (user_id, balance_micro_cny, total_credited_micro_cny, free_chat_count)
  VALUES (NEW.id, 0, 0, v_count)
  ON CONFLICT (user_id) DO NOTHING;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.handle_new_user_welcome_credits()
  FROM PUBLIC, anon, authenticated;

-- Older installations may already have a signup trigger referencing this
-- function. Reuse it instead of introducing duplicate grants.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_trigger t
    WHERE t.tgrelid = 'auth.users'::regclass
      AND t.tgfoid = 'public.handle_new_user_welcome_credits()'::regprocedure
      AND NOT t.tgisinternal AND t.tgenabled <> 'D'
  ) THEN
    CREATE TRIGGER workbench_registration_trial
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user_welcome_credits();
  END IF;
END $$;
COMMIT;
