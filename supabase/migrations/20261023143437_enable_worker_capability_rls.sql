-- Defense in depth: the table is only accessed by the SECURITY DEFINER worker RPC.
-- Keep direct anon/authenticated grants revoked; no user-facing policy is required.
alter table material_private.worker_capability enable row level security;
