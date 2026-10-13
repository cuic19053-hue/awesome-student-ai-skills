-- An existing Wopally balance code can be redeemed into the dedicated
-- service account without minting a new provider code. The app's dedicated
-- capability and the caller's Supabase JWT are both required.
create or replace function public.workbench_backend_complete_card_redemption(
  p_intent_id uuid, p_face_value_micro_cny bigint, p_provider_user_id bigint,
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
  return public.workbench_complete_card_redemption(
    p_intent_id,p_face_value_micro_cny,p_provider_user_id
  );
end $$;
revoke all on function public.workbench_backend_complete_card_redemption(uuid,bigint,bigint,text)
  from public,anon,authenticated;
grant execute on function public.workbench_backend_complete_card_redemption(uuid,bigint,bigint,text)
  to authenticated;
