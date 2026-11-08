"""Personal retrieval must not associate a clearly different applicant."""
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
import server.app as app
from proposal.personal_source_filter import filter_personal_evidence
from proposal.agent import OllamaAgent
from proposal.retrieval import ProjectRetriever, section_material_query
from proposal.storage import Store
from proposal.tools import ProposalTools
from proposal.skills import registry
from proposal.workflow import AgenticWorkflowEngine
from proposal.chat_tools import ChatToolRouter
from proposal.chat_context import conversation_messages


def test_confirmed_different_applicant_is_removed_but_unknown_and_notices_remain():
    project = {"id": "p", "state": {"confirmed_facts": {}}}
    history = [{"role": "user", "content": "我叫李明，想申请保研。"}]
    base = {"project_id": "p", "kind": "source", "confirmed": 1, "confirmation_origin": "user"}
    docs = [{**base, "id": "self", "extracted_text": "[行 1] 姓名：李明\n[行 2] 绩点：3.8"},
            {**base, "id": "other", "extracted_text": "[段落 1] 姓名：王五\n[段落 2] 绩点：4.5"},
            {**base, "id": "unlabelled", "extracted_text": "个人陈述写作材料"},
            {**base, "id": "notice", "kind": "official", "extracted_text": "申请人：王五"}]
    context = {"results": [{"document_id": key, "text": key} for key in ("self", "other", "unlabelled", "notice")],
               "retrieval_mode": "keyword_fallback"}
    result, removed = filter_personal_evidence(registry.get("graduate-recommendation"), project, history, docs, context)
    assert removed == ["other"]
    assert [item["document_id"] for item in result["results"]] == ["self", "unlabelled", "notice"]
    assert len(context["results"]) == 4


def test_unknown_or_conflicting_applicant_name_does_not_guess():
    project = {"id": "p", "state": {"confirmed_facts": {"name": "李明"}}}
    docs = [{"project_id": "p", "id": "d", "kind": "source", "confirmed": 1,
             "confirmation_origin": "user", "extracted_text": "姓名：王五"}]
    context = {"results": [{"document_id": "d"}]}
    for history in ([{"role": "user", "content": "我叫李华。"}],
                    [{"role": "user", "content": "我叫李华。"}, {"role": "user", "content": "我叫张三。"}]):
        filtered, removed = filter_personal_evidence(registry.get("graduate-recommendation"), project, history, docs, context)
        assert filtered == context and removed == []


def test_word_table_multiple_names_and_student_correction():
    project = {"id": "p", "state": {"confirmed_facts": {}}}
    history = [{"role": "user", "content": "我叫李明。"}, {"role": "user", "content": "更正，我叫李华。"}]
    base = {"project_id": "p", "kind": "source", "confirmed": 1, "confirmation_origin": "user"}
    docs = [{**base, "id": "self", "extracted_text": "[表格 1 第 1 行] 姓名 | 李华 | 专业 | 计算机"},
            {**base, "id": "mixed", "extracted_text": "[表格 1 第 1 行] 姓名 | 李华\n[表格 1 第 2 行] 姓名 | 王五"}]
    context = {"results": [{"document_id": "self"}, {"document_id": "mixed"}]}
    filtered, removed = filter_personal_evidence(registry.get("graduate-recommendation"), project, history, docs, context)
    assert removed == ["mixed"] and filtered["results"] == [{"document_id": "self"}]


def test_actual_upload_and_retrieval_excludes_other_name(tmp_path, monkeypatch):
    store = Store(tmp_path)
    retriever = ProjectRetriever(store)
    monkeypatch.setattr(retriever, "_embed_verified", lambda *_: (None, ""))
    tools = ProposalTools(store, retriever)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "retriever", retriever)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    with TestClient(app.app) as client:
        pid = client.post("/api/projects/conversation").json()["id"]
        assert client.post(f"/api/projects/{pid}/skill", json={"skill_id": "graduate-recommendation"}).status_code == 200
        store.add_message(pid, "user", "我叫李明，正在申请保研，请帮我写个人基本情况。")
        for name in ("李明", "王五"):
            text = f"姓名：{name}\n个人基本情况：{name}在计算机专业学习。".encode()
            response = client.post(f"/api/projects/{pid}/documents?kind=source", files={
                "files": (f"{name}资料.txt", text, "text/plain"),
            })
            assert response.status_code == 200
            doc_id = response.json()["documents"][0]["document"]["id"]
            assert client.patch(f"/api/documents/{doc_id}/confirm", json={"confirmed": True}).status_code == 200
        assert client.put(f"/api/projects/{pid}/outline", json={"outline": [{"id": "profile", "title": "个人基本情况"}]}).status_code == 200
        project = store.get_project(pid)
        context = tools.search_project_materials(pid, section_material_query(project, "profile"))
        assert len(context["results"]) == 2
        filtered, removed = filter_personal_evidence(registry.get("graduate-recommendation"), project,
                                                     store.messages(pid, limit=200), store.list_documents(pid), context)
        assert len(removed) == 1 and len(filtered["results"]) == 1
        assert "李明" in filtered["results"][0]["text"] and "王五" not in filtered["results"][0]["text"]


def test_personal_section_workflow_receives_only_applicable_materials(tmp_path, monkeypatch):
    store = Store(tmp_path)
    retriever = ProjectRetriever(store)
    monkeypatch.setattr(retriever, "_embed_verified", lambda *_: (None, ""))
    tools = ProposalTools(store, retriever)
    agent = OllamaAgent(store, tools)
    monkeypatch.setattr(tools, "search_public_knowledge", lambda *_args, **_kwargs: {"results": []})
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "retriever", retriever)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "agent", agent)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    captured = []

    class SimulatedResult:
        content = "我叫李明，学习计算机专业。"
        def model_dump(self):
            return {"content": self.content, "status": "passed", "review_card": {"review_status": "completed"}}

    def simulated_workflow(_self, **kwargs):
        captured.extend(kwargs["evidence_results"])
        return SimulatedResult()

    monkeypatch.setattr(AgenticWorkflowEngine, "run_workflow", simulated_workflow)
    with TestClient(app.app) as client:
        pid = client.post("/api/projects/conversation").json()["id"]
        client.post(f"/api/projects/{pid}/skill", json={"skill_id": "graduate-recommendation"})
        store.add_message(pid, "user", "我叫李明，正在申请保研。")
        for filename, kind, text in [
            ("李明.txt", "source", "姓名：李明\n个人基本情况：学习计算机专业。"),
            ("王五.txt", "source", "姓名：王五\n个人基本情况：曾担任研究助理。"),
            ("通知.txt", "official", "学校通知：个人基本情况应填写所在专业。"),
        ]:
            response = client.post(f"/api/projects/{pid}/documents?kind={kind}", files={
                "files": (filename, text.encode(), "text/plain"),
            })
            assert response.status_code == 200
            doc_id = response.json()["documents"][0]["document"]["id"]
            assert client.patch(f"/api/documents/{doc_id}/confirm", json={"confirmed": True}).status_code == 200
        assert client.put(f"/api/projects/{pid}/outline", json={"outline": [{"id": "profile", "title": "个人基本情况"}]}).status_code == 200
        result = agent.generate_section(pid, "profile")
        names = {item["source_name"] for item in captured}
        assert names == {"李明.txt", "通知.txt"}
        assert "姓名与当前学生不同" in result["notice"]
        assert "王五" not in result["content"]


def test_chat_tool_filters_only_explicit_personal_writing_not_comparison():
    project = {"id": "p", "state": {"skill_id": "graduate-recommendation", "confirmed_facts": {}}}
    base = {"project_id": "p", "kind": "source", "confirmed": 1, "confirmation_origin": "user"}
    docs = [{**base, "id": "self", "extracted_text": "姓名：李明"},
            {**base, "id": "same", "extracted_text": "姓名：李明"},
            {**base, "id": "other", "extracted_text": "姓名：王五"},
            {**base, "id": "unknown", "extracted_text": "保研材料的一般说明"},
            {**base, "id": "notice", "kind": "official", "extracted_text": "申请人：王五"}]
    context = {"results": [{"document_id": key} for key in ("self", "same", "other", "unknown", "notice")]}

    class FakeStore:
        messages_data = [{"role": "user", "content": "我叫李明。"}]
        def messages(self, *_args, **_kwargs):
            return self.messages_data
        def list_documents(self, *_args):
            return docs

    class FakeTools:
        store = FakeStore()
        def schemas(self):
            return [{"function": {"name": "search_project_materials", "parameters": {"properties": {"project_id": {}}}}}]
        def invoke(self, _name, _arguments):
            return context

    tools = FakeTools()
    call = {"function": {"name": "search_project_materials", "arguments": {"query": "个人情况"}}}
    for text in ("请帮我起草保研个人陈述。", "根据资料写个人陈述。", "请分别从学习和科研写我的个人陈述。"):
        router = ChatToolRouter(tools, "p", project, user_text=text)
        name, result = router.invoke(call)
        assert name == "search_project_materials"
        assert [item["document_id"] for item in result["results"]] == ["self", "same", "unknown", "notice"]
        assert "请核对材料" in result["message"] and len(context["results"]) == 5
    for text in ("请对比李明和王五的个人资料。", "帮我比较两位学生的申请材料。", "保研需要准备哪些材料？", "不要帮我写申请书。"):
        router = ChatToolRouter(tools, "p", project, user_text=text)
        assert router.invoke(call)[1] == context
    tools.store.messages_data = [{"role": "user", "content": "我想申请保研。"}]
    router = ChatToolRouter(tools, "p", project, user_text="请帮我起草保研个人陈述。")
    assert router.invoke(call)[1] == context


def test_chat_tool_honors_material_opt_out_for_writing_and_ordinary_questions():
    project = {"id": "p", "state": {"skill_id": "graduate-recommendation"}}
    class FakeStore:
        messages_data = [{"role": "user", "content": "请不要使用我的附件。"}]
        def messages(self, *_args, **_kwargs):
            return self.messages_data
        def list_documents(self, *_args):
            return []
    class FakeTools:
        store = FakeStore()
        calls = 0
        def schemas(self):
            return [{"function": {"name": "search_project_materials", "parameters": {"properties": {"project_id": {}}}}}]
        def invoke(self, _name, _arguments):
            self.calls += 1
            return {"results": [{"document_id": "p-doc", "text": "学生资料"}]}
    tools = FakeTools()
    call = {"function": {"name": "search_project_materials", "arguments": {"query": "资料"}}}
    for message in ("请帮我写个人陈述。", "保研材料一般有哪些？"):
        router = ChatToolRouter(tools, "p", project, user_text=message)
        _, result = router.invoke(call)
        assert result["results"] == [] and result["retrieval_mode"] == "disabled_by_user"
        assert tools.calls == 0
    router = ChatToolRouter(tools, "p", project, user_text="现在可以重新使用我的附件。")
    assert router.invoke(call)[1]["results"][0]["text"] == "学生资料"
    assert tools.calls == 1


def test_chat_tool_fails_closed_when_material_preference_cannot_be_read():
    class BrokenStore:
        def messages(self, *_args, **_kwargs):
            raise RuntimeError("unavailable")
    class FakeTools:
        store = BrokenStore()
        def schemas(self):
            return [{"function": {"name": "search_project_materials", "parameters": {"properties": {}}}}]
        def invoke(self, *_args):
            raise AssertionError("must not retrieve files without checking the student's choice")
    router = ChatToolRouter(FakeTools(), "p", {"id": "p", "state": {}}, user_text="请帮我查资料")
    _, result = router.invoke({"function": {"name": "search_project_materials", "arguments": {}}})
    assert result["results"] == [] and result["retrieval_mode"] == "preference_unavailable"


def test_project_state_hides_filenames_when_student_forbids_using_materials():
    project = {"id": "p", "state": {"skill_id": "graduate-recommendation"}}
    class FakeStore:
        def messages(self, *_args, **_kwargs):
            return [{"role": "user", "content": "请不要读取我的附件。"}]
    class FakeTools:
        store = FakeStore()
        def schemas(self):
            return [{"function": {"name": "get_project_state", "parameters": {"properties": {"project_id": {}}}}}]
        def invoke(self, _name, _arguments):
            return {"project": {"id": "p", "title": "我的项目"}, "documents": [{"name": "敏感文件名.txt"}]}
    tools = FakeTools()
    call = {"function": {"name": "get_project_state", "arguments": {}}}
    router = ChatToolRouter(tools, "p", project, user_text="请介绍我的项目")
    result = router.invoke(call)[1]
    assert result["project"]["title"] == "我的项目" and result["documents"] == []
    router = ChatToolRouter(tools, "p", project, user_text="可以重新读取我的附件")
    assert router.invoke(call)[1]["documents"][0]["name"] == "敏感文件名.txt"


def test_model_context_hides_different_applicant_metadata_only_for_writing():
    project = {"id": "p", "state": {"skill_id": "graduate-recommendation", "confirmed_facts": {}}}
    base = {"project_id": "p", "kind": "source", "confirmed": 1, "confirmation_origin": "user",
            "extraction_status": "ready"}
    docs = [{**base, "id": "self", "original_name": "李明成绩.txt", "extracted_text": "姓名：李明"},
            {**base, "id": "other", "original_name": "王五成绩.txt", "extracted_text": "姓名：王五"},
            {**base, "id": "notice", "kind": "official", "original_name": "学校通知.txt", "extracted_text": "通知"}]
    class FakeStore:
        def list_documents(self, _pid):
            return docs
    class FakeAgent:
        store = FakeStore()
        def _compact_project(self, _project):
            return {"confirmed_state": {}}
    agent = FakeAgent()
    history = [{"role": "user", "content": "我叫李明。"}]
    writing = conversation_messages(agent, project, "p", history, "请根据材料写个人陈述。")
    assert "李明成绩.txt" in writing[0]["content"] and "学校通知.txt" in writing[0]["content"]
    assert "王五成绩.txt" not in writing[0]["content"]
    comparison = conversation_messages(agent, project, "p", history, "请对比李明和王五的个人资料。")
    assert "王五成绩.txt" in comparison[0]["content"]
    denied = conversation_messages(agent, project, "p", [*history, {"role": "user", "content": "请不要读取附件。"}], "请写个人陈述。")
    assert all(doc["original_name"] not in denied[0]["content"] for doc in docs)
    mixed = conversation_messages(agent, project, "p", [], "请写个人陈述。",
                                  original_user_text="我叫李明，敏感政策问题无须发送。请写个人陈述。")
    assert "李明成绩.txt" in mixed[0]["content"] and "王五成绩.txt" not in mixed[0]["content"]
    assert all("敏感政策问题无须发送" not in message["content"] for message in mixed)
    mixed_denied = conversation_messages(agent, project, "p", [], "请写个人陈述。",
                                         original_user_text="我叫李明，不要使用附件。请写个人陈述。")
    assert all(doc["original_name"] not in mixed_denied[0]["content"] for doc in docs)
