-- Applied to production as migration 20261028081757.
-- A delayed provider receipt must not block all subsequent user requests.
-- Keep historical holds intact: elapsed time is not proof of provider failure.
-- The underlying reservation RPC already locks the wallet, checks available
-- funds, and deduplicates request IDs atomically.
create or replace function public.workbench_backend_reserve_usage(
  p_user_id uuid, p_request_id text, p_model text, p_reserved_micro_cny bigint,
  p_api_key_id bigint, p_server_secret text
) returns jsonb language plpgsql security definer
set search_path = pg_catalog, public as $$
begin
  perform public.workbench_check_backend(p_server_secret);
  if p_user_id is distinct from (select auth.uid()) then
    raise exception 'identity mismatch' using errcode = '42501';
  end if;
  return public.workbench_reserve_usage(
    p_user_id, p_request_id, p_model, p_reserved_micro_cny, p_api_key_id
  );
end $$;

-- Preserve the narrow server capability + verified user identity boundary.
revoke all on function public.workbench_backend_reserve_usage(
  uuid, text, text, bigint, bigint, text
) from public, anon;
grant execute on function public.workbench_backend_reserve_usage(
  uuid, text, text, bigint, bigint, text
) to authenticated;
