-- Keep card redemption intents inaccessible to browser roles and index the
-- nullable transaction reference for FK checks and reconciliation lookups.
create policy "deny client access to card redemption intents"
  on public.workbench_card_redemptions
  for all
  to anon, authenticated
  using (false)
  with check (false);

create index workbench_card_redemptions_transaction_id_idx
  on public.workbench_card_redemptions (transaction_id);
