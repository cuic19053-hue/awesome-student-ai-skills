-- Adjust trial free policy: 3 free conversation turns per user.
ALTER TABLE public.workbench_credit_wallets
  ADD COLUMN IF NOT EXISTS free_chat_count integer NOT NULL DEFAULT 3 CHECK (free_chat_count >= 0);

CREATE OR REPLACE FUNCTION public.workbench_consume_free_chat(p_user_id uuid)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_remaining integer;
BEGIN
  IF p_user_id IS NULL THEN
    RAISE EXCEPTION 'user_id required' USING ERRCODE = '22023';
  END IF;

  INSERT INTO public.workbench_credit_wallets(user_id, balance_micro_cny, total_credited_micro_cny, total_spent_micro_cny, free_chat_count)
  VALUES (p_user_id, 0, 0, 0, 3)
  ON CONFLICT (user_id) DO NOTHING;

  UPDATE public.workbench_credit_wallets
  SET free_chat_count = free_chat_count - 1,
      updated_at = now()
  WHERE user_id = p_user_id AND free_chat_count > 0
  RETURNING free_chat_count INTO v_remaining;

  RETURN COALESCE(v_remaining, -1);
END;
$$;

CREATE OR REPLACE FUNCTION public.workbench_refund_free_chat(p_user_id uuid)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_remaining integer;
BEGIN
  IF p_user_id IS NULL THEN
    RAISE EXCEPTION 'user_id required' USING ERRCODE = '22023';
  END IF;

  UPDATE public.workbench_credit_wallets
  SET free_chat_count = LEAST(3, free_chat_count + 1),
      updated_at = now()
  WHERE user_id = p_user_id
  RETURNING free_chat_count INTO v_remaining;

  RETURN COALESCE(v_remaining, 3);
END;
$$;

GRANT EXECUTE ON FUNCTION public.workbench_consume_free_chat(uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.workbench_refund_free_chat(uuid) TO authenticated, service_role;

CREATE OR REPLACE FUNCTION public.workbench_backend_consume_free_chat(
  p_user_id uuid, p_server_secret text
) RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
BEGIN
  PERFORM public.workbench_check_backend(p_server_secret);
  IF p_user_id IS DISTINCT FROM (SELECT auth.uid()) THEN
    RAISE EXCEPTION 'identity mismatch' USING ERRCODE='42501';
  END IF;
  RETURN public.workbench_consume_free_chat(p_user_id);
END $$;

CREATE OR REPLACE FUNCTION public.workbench_backend_refund_free_chat(
  p_user_id uuid, p_server_secret text
) RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
BEGIN
  PERFORM public.workbench_check_backend(p_server_secret);
  IF p_user_id IS DISTINCT FROM (SELECT auth.uid()) THEN
    RAISE EXCEPTION 'identity mismatch' USING ERRCODE='42501';
  END IF;
  RETURN public.workbench_refund_free_chat(p_user_id);
END $$;

GRANT EXECUTE ON FUNCTION public.workbench_backend_consume_free_chat(uuid, text) TO authenticated;
GRANT EXECUTE ON FUNCTION public.workbench_backend_refund_free_chat(uuid, text) TO authenticated;

CREATE OR REPLACE FUNCTION public.handle_new_user_welcome_credits()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_domain text;
  v_today_grants integer;
BEGIN
  v_domain := lower(split_part(new.email, '@', 2));

  IF v_domain NOT IN ('qq.com', 'foxmail.com', '163.com', '126.com', 'sina.com', 'gmail.com', 'outlook.com', 'hotmail.com')
     AND v_domain NOT LIKE '%.edu.cn' AND v_domain <> 'edu.cn' THEN
    INSERT INTO public.workbench_credit_wallets (user_id, balance_micro_cny, total_credited_micro_cny, free_chat_count)
    VALUES (new.id, 0, 0, 0)
    ON CONFLICT (user_id) DO NOTHING;
    RETURN new;
  END IF;

  SELECT count(*) INTO v_today_grants
  FROM public.workbench_credit_wallets
  WHERE created_at >= date_trunc('day', now()) AND free_chat_count > 0;

  IF v_today_grants >= 100 THEN
    INSERT INTO public.workbench_credit_wallets (user_id, balance_micro_cny, total_credited_micro_cny, free_chat_count)
    VALUES (new.id, 0, 0, 0)
    ON CONFLICT (user_id) DO NOTHING;
    RETURN new;
  END IF;

  INSERT INTO public.workbench_credit_wallets (user_id, balance_micro_cny, total_credited_micro_cny, free_chat_count)
  VALUES (new.id, 0, 0, 3)
  ON CONFLICT (user_id) DO UPDATE SET free_chat_count = EXCLUDED.free_chat_count;
  RETURN new;
END;
$$;
