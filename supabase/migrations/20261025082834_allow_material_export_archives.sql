-- The material worker uploads a ZIP bundle, not only a stand-alone DOCX.
-- Preserve all existing MIME types, limits and the private/RLS access model.
do $$
begin
  if not exists (
    select 1 from storage.buckets
    where id = 'stardust-project-files' and public = false
  ) then
    raise exception 'Expected private project storage bucket is missing';
  end if;
  update storage.buckets
  set allowed_mime_types = array_append(allowed_mime_types, 'application/zip')
  where id = 'stardust-project-files'
    and allowed_mime_types is not null
    and not ('application/zip' = any(allowed_mime_types));
end
$$;
