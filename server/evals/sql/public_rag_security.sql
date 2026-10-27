-- Run only inside a disposable PostgreSQL container, never on a real project.
set role service_role;
select public.rag_publish_public_source(
 '{"id":"institution-report","skill_id":"college-research","kind":"institution_report","title":"报道","school":"河南大学","application_year":2024,"source_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","example_structure":"研究问题与方法"}',
 '[{"id":"report-chunk","source_ref":"一","content":"答辩研究问题与方法"}]');
do $$ begin
 begin
  perform public.rag_publish_public_source(
   '{"id":"unapproved-example","skill_id":"innovation-research","kind":"example","title":"bad","source_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}',
   '[{"id":"unapproved-example-chunk","source_ref":"一","content":"content"}]');
  raise exception 'unapproved example accepted';
 exception when check_violation then null; end;
 begin
  perform public.rag_publish_public_source(
   '{"id":"missing-credit","skill_id":"class-collective","kind":"example","title":"示例","school":"示例大学","application_year":2026,"source_url":"https://example.edu.cn/source","source_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","license":"CC-BY","rights_evidence_url":"https://example.edu.cn/license","approval_reference":"review-1","privacy_reviewed":true,"structure_reviewed":true,"example_structure":"背景与方案","example_match_type":"direct"}',
   '[{"id":"missing-credit-chunk","source_ref":"一","content":"content"}]');
  raise exception 'example without attribution accepted';
 exception when check_violation then null; end;
 begin
  perform public.rag_publish_public_source(
   '{"id":"unresolved-rights","skill_id":"class-collective","kind":"example","title":"示例","school":"示例大学","application_year":2026,"source_url":"https://example.edu.cn/source","source_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","license":"CC-BY","rights_evidence_url":"https://example.edu.cn/license","rights_review_status":"resolved","approval_reference":"review-1","privacy_reviewed":true,"structure_reviewed":true,"example_structure":"背景与方案","example_match_type":"direct","attribution":"署名"}',
   '[{"id":"unresolved-rights-chunk","source_ref":"一","content":"content"}]');
  raise exception 'unresolved rights accepted';
 exception when check_violation then null; end;
end $$;
reset role;
set role service_role;
select public.rag_publish_public_source(
 '{"id":"reviewed-example","skill_id":"class-collective","kind":"example","title":"示例","school":"示例大学","application_year":2026,"source_url":"https://example.edu.cn/source","source_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","license":"CC-BY","rights_evidence_url":"https://example.edu.cn/license","rights_review_status":"no_conflict","approval_reference":"review-1","privacy_reviewed":true,"structure_reviewed":true,"example_structure":"背景与方案","example_match_type":"cross_track","attribution":"作者署名（测试）"}',
 '[{"id":"example-chunk","source_ref":"一","content":"案例具体事实与方案"}]');
reset role;
set role authenticated;
do $$ begin
 if (select count(*) from public.rag_search_public_knowledge('college-research','河南大学',2024,array['答辩'],null,'',30,'','{}',true)) <> 0 then
   raise exception 'institution report was treated as official policy';
 end if;
 if (select count(*) from public.rag_search_public_knowledge('class-collective','示例大学',2026,array['方案'])) <> 0 then
   raise exception 'historical example returned without explicit request';
 end if;
 if (select example_structure from public.rag_search_public_knowledge('class-collective','其他大学',2027,array['方案'],null,'',30,'','{}',false,true)) <> '背景与方案' then
   raise exception 'approved example metadata missing';
 end if;
 if (select count(*) from public.rag_search_public_knowledge('class-collective','示例大学',2026,array['方案'],null,'',30,'','{}',true,true)) <> 0 then
   raise exception 'example was treated as official policy';
 end if;
end $$;
reset role;
set role service_role;
select public.rag_publish_public_source(
 '{"id":"school-rule","skill_id":"innovation-research","kind":"official","title":"规则","school":"东南大学","application_year":2026,"scope":"历史批次","source_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","license":"summary"}',
 '[{"id":"r1","source_ref":"第 1 页","content":"研究经费预算"}]');
select public.rag_publish_public_source(
 '{"id":"guide","skill_id":"innovation-research","kind":"skill_guidance","title":"指南","source_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","license":"MIT"}',
 '[{"id":"g1","source_ref":"第 1 行","content":"项目研究预算"}]');
select public.rag_publish_public_source(
 '{"id":"vector","skill_id":"innovation-research","kind":"skill_guidance","title":"向量指南","source_sha256":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd","license":"MIT"}',
 jsonb_build_array(jsonb_build_object('id','v1','source_ref','line','content','无词匹配',
   'embedding_model','bge-m3','embedding_revision','revision1',
   'embedding',to_jsonb(array_fill(0.01::real,ARRAY[1024])))));
-- A failed rebuild rolls back both metadata and the earlier chunk deletion.
do $$ begin
 begin
  perform public.rag_publish_public_source(
   '{"id":"guide","skill_id":"innovation-research","kind":"skill_guidance","title":"BAD","source_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","license":"MIT"}',
   '[{"id":"duplicate","source_ref":"1","content":"x"},{"id":"duplicate","source_ref":"2","content":"y"}]');
  raise exception 'invalid rebuild unexpectedly succeeded';
 exception when unique_violation then null; end;
 if (select title from public.rag_public_sources where id='guide') <> '指南' or
    (select count(*) from public.rag_public_chunks where source_id='guide') <> 1 then
   raise exception 'failed rebuild did not roll back';
 end if;
end $$;
reset role;
set role service_role;
select public.rag_publish_public_source(
 '{"id":"restricted","skill_id":"enterprise-scholarship","restrictions":{"education_level":["硕士","博士"],"college":["生物工程学院"]},"kind":"official","title":"专项","school":"大连理工大学","application_year":2025,"source_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}',
 '[{"id":"restricted-rule","source_ref":"一","content":"奖学金条件"}]');
reset role;
set role authenticated;
do $$ begin
 if (select count(*) from public.rag_search_public_knowledge('enterprise-scholarship','大连理工大学',2025,array['奖学金'])) <> 0 then
   raise exception 'unspecified restrictions leaked';
 end if;
 if (select count(*) from public.rag_search_public_knowledge('enterprise-scholarship','大连理工大学',2025,array['奖学金'],null,'',30,'','{"education_level":"本科","college":"生物工程学院"}')) <> 0 then
   raise exception 'wrong education level leaked';
 end if;
 if (select count(*) from public.rag_search_public_knowledge('enterprise-scholarship','大连理工大学',2025,array['奖学金'],null,'',30,'','{"education_level":"硕士","college":"生物工程学院"}')) <> 1 then
   raise exception 'matching restrictions failed';
 end if;
end $$;
reset role;
insert into public.rag_public_sources(id,skill_id,kind,title,source_sha256)
 values('draft','innovation-research','official','未审核',repeat('c',64));
insert into public.rag_public_chunks(id,source_id,source_ref,content) values('hidden','draft','1','预算');
set role authenticated;
do $$ begin
 if (select count(*) from public.rag_public_sources where skill_id='innovation-research') <> 3 then raise exception 'draft visible'; end if;
 if (select count(*) from public.rag_search_public_knowledge('innovation-research','东南大学',2026,array['预算'])) <> 2 then raise exception 'matching school failed'; end if;
 if (select count(*) from public.rag_search_public_knowledge('innovation-research','其他大学',2026,array['预算'])) <> 1 then raise exception 'wrong school leak'; end if;
 if (select count(*) from public.rag_search_public_knowledge('innovation-research','东南大学',null,array['预算'])) <> 1 then raise exception 'missing year leak'; end if;
 if (select count(*) from public.rag_search_public_knowledge('innovation-research','东南大学',2026,array['预算'],null,'',30,'','{}',true)) <> 1 then raise exception 'official-only filter failed'; end if;
 if (select count(*) from public.rag_search_public_knowledge('innovation-research','东南大学',null,array['预算'],null,'',30,'','{}',true)) <> 0 then raise exception 'unverified guidance shown as policy'; end if;
 if (select count(*) from public.rag_search_public_knowledge('other','东南大学',2026,array['预算'])) <> 0 then raise exception 'wrong skill leak'; end if;
 if (select count(*) from public.rag_search_public_knowledge('innovation-research','',null,array['zzzzz'],array_fill(0.01::real,ARRAY[1024])::extensions.vector,'revision1')) <> 1 then raise exception 'vector failed'; end if;
 if (select count(*) from public.rag_search_public_knowledge('innovation-research','',null,array['zzzzz'],array_fill(0.01::real,ARRAY[1024])::extensions.vector,'different')) <> 0 then raise exception 'mixed vector revisions'; end if;
 begin
  perform public.rag_publish_public_source('{}','[]');
  raise exception 'student can publish';
 exception when insufficient_privilege then null; end;
end $$;
reset role;
update public.rag_public_sources set published=false where id='school-rule';
set role authenticated;
do $$ begin
 if (select count(*) from public.rag_search_public_knowledge('innovation-research','东南大学',2026,array['预算'])) <> 1 then raise exception 'revoked source visible'; end if;
end $$;
reset role;
set role service_role;
select public.rag_publish_public_source(
 '{"id":"honor-student","skill_id":"outstanding-student","variant":"outstanding_student","kind":"official","title":"学生","school":"无锡学院","application_year":2024,"source_sha256":"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"}',
 '[{"id":"student-rule","source_ref":"一","content":"评优条件"}]');
select public.rag_publish_public_source(
 '{"id":"honor-league","skill_id":"outstanding-student","variant":"outstanding_youth_league","kind":"official","title":"团员","school":"无锡学院","application_year":2024,"source_sha256":"ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"}',
 '[{"id":"league-rule","source_ref":"一","content":"评优条件"}]');
reset role;
set role authenticated;
do $$ begin
 if (select count(*) from public.rag_search_public_knowledge('outstanding-student','无锡学院',2024,array['评优'])) <> 0 then
   raise exception 'unspecified variant leaked';
 end if;
 if (select count(*) from public.rag_search_public_knowledge('outstanding-student','无锡学院',2024,array['评优'],null,'',30,'outstanding_youth_league')) <> 1 then
   raise exception 'variant scope failed';
 end if;
end $$;
