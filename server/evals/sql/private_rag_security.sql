-- Run only in a disposable PostgreSQL container with test RLS, never on production.
insert into public.projects values
 ('a','00000000-0000-0000-0000-000000000001'), ('b','00000000-0000-0000-0000-000000000002');
insert into public.documents(id,project_id,confirmed,kind,confirmation_origin) values
 ('a1','a',true,'source','user'),('a2','a',false,'source',''),('a3','a',true,'template','user'),
 ('b1','b',true,'source','user'),('legacy','a',true,'source','');
insert into public.chunks(id,project_id,document_id,source_name,source_ref,content) values
 ('a1','a','a1','A','段落 1','项目研究内容'),('a2','a','a2','A2','段落 2','项目研究内容'),
 ('a3','a','a3','模板','段落 1','项目研究内容'),('b1','b','b1','B','段落 1','项目研究内容'),
 ('legacy','a','legacy','旧自动确认','段落 1','项目研究内容'),
 ('bad','a','b1','bad','段落 1','项目研究内容');
update public.documents set original_name='A', extracted_text='用户确认内容' where id='a1';
set role authenticated;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000001',false);
insert into public.rag_chunk_embeddings select 'a1','bge-m3','revision-1',array_fill(0.01::real,ARRAY[1024])::extensions.vector;
do $$ begin
 if (select count(*) from public.rag_project_search('a',array['项目'])) <> 1 then raise exception 'unconfirmed/template/cross-project leak'; end if;
 if (select count(*) from public.rag_project_search('b',array['项目'])) <> 0 then raise exception 'cross-user leak'; end if;
 if (select count(*) from public.rag_project_search('a',array['无匹配'],array_fill(0.01::real,ARRAY[1024])::extensions.vector,'bge-m3',30,'revision-1')) <> 1 then raise exception 'vector recall failed'; end if;
 if (select count(*) from public.rag_project_search('a',array['无匹配'],array_fill(0.01::real,ARRAY[1024])::extensions.vector,'bge-m3',30,'wrong-revision')) <> 0 then raise exception 'mixed vector revisions'; end if;
 begin
  insert into public.rag_chunk_embeddings select 'b1','bge-m3','revision-1',array_fill(0.01::real,ARRAY[1024])::extensions.vector;
  raise exception 'cross-user insert allowed';
 exception when insufficient_privilege then null; end;
end $$;
-- A changed document or invalid vector must not destroy the old snapshot.
do $$ declare expected text := encode(pg_catalog.sha256(convert_to('用户确认内容','UTF8')), 'hex');
begin
 begin
  perform public.rag_replace_project_chunks('a1',repeat('0',64),
    '[{"id":"11111111111111111111111111111111","source_ref":"第1段","content":"新内容"}]');
  raise exception 'stale hash accepted';
 exception when sqlstate 'PT409' then null; end;
 if not exists(select 1 from public.chunks where id='a1') then raise exception 'stale hash deleted old chunks'; end if;
 begin
  perform public.rag_replace_project_chunks('a1',expected,
    '[{"id":"11111111111111111111111111111111","source_ref":"第1段","content":"新内容","embedding":[0.1],"embedding_model":"bge-m3","embedding_revision":"revision-1"}]');
  raise exception 'invalid vector accepted';
 exception when invalid_parameter_value then null; end;
 if not exists(select 1 from public.chunks where id='a1') then raise exception 'invalid vector deleted old chunks'; end if;
 begin
  perform public.rag_replace_project_chunks('a1',expected,
    '[{"id":"11111111111111111111111111111111","source_ref":"第1段","content":"一"},{"id":"11111111111111111111111111111111","source_ref":"第2段","content":"二"}]');
  raise exception 'duplicate chunks accepted';
 exception when unique_violation then null; end;
 if not exists(select 1 from public.chunks where id='a1') then raise exception 'failed insert deleted old chunks'; end if;
 begin
  perform public.rag_replace_project_chunks('b1',expected,
    '[{"id":"11111111111111111111111111111111","source_ref":"第1段","content":"新内容"}]');
  raise exception 'cross-user replacement allowed';
 exception when insufficient_privilege then null; end;
 if (select public.rag_replace_project_chunks('a1',expected,
   jsonb_build_array(jsonb_build_object('id','11111111111111111111111111111111','source_ref','第1段',
     'content','用户确认内容','embedding_model','bge-m3','embedding_revision','revision-1',
     'embedding',to_jsonb(array_fill(0.01::real,ARRAY[1024])))))) <> 1 then
   raise exception 'atomic replacement count wrong';
 end if;
 if exists(select 1 from public.chunks where id='a1') then raise exception 'old chunk retained'; end if;
end $$;
update public.documents set confirmed=false where id='a1';
do $$ begin
 if (select count(*) from public.rag_project_search('a',array['项目'])) <> 0 then raise exception 'revoked material leaked'; end if;
end $$;
delete from public.chunks where id='11111111111111111111111111111111';
reset role;
do $$ begin
 if exists(select 1 from public.rag_chunk_embeddings where chunk_id='11111111111111111111111111111111') then raise exception 'vector not cascaded'; end if;
end $$;
