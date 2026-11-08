"""Direct project-writing requests are not replaced by an intake checklist."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from proposal.agent import OllamaAgent
from proposal.chat_drafts import plain_project_chapters
from proposal.project_writing import is_explicit_project_draft, project_sources_allowed, explicit_public_lookup
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools


@pytest.mark.parametrize("user_request", [
    "请直接写商业计划书中的项目简介，不要编造营业收入。",
    "请帮我写挑战杯研究方案，没有做过实验。",
    "我们做校园食物浪费研究，先写一段大创研究目标。",
    "请帮我写研究背景。",
    "请生成大创项目的立项依据。",
    "挑战杯项目可行性分析请帮我写一下。",
    "互联网+的用户需求请直接写出来。",
])
def test_clear_project_writing_request_is_recognized(user_request):
    assert is_explicit_project_draft(user_request, {"category": "competition"})


@pytest.mark.parametrize("user_request", [
    "商业计划书的项目简介怎么写？",
    "不要写商业计划书，先介绍一下。",
    "先别帮我写项目简介，请问需要哪些材料？",
    "给我讲讲市场分析的思路。",
    "可行性分析不要帮我写，请讲思路。",
])
def test_questions_and_refusals_are_not_forced_into_a_draft(user_request):
    assert not is_explicit_project_draft(user_request, {"category": "competition"})


def test_explicit_draft_prompt_prioritizes_user_request_and_labels_suggestions(tmp_path, monkeypatch):
    store = Store(tmp_path)
    project_id = store.create_project()["id"]
    store.update_project(project_id, state={"skill_id": "internet-plus", "skill_category": "competition"})
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_a: None)
    calls = []
    def reply(_path, payload):
        calls.append(payload)
        return {"message": {"content": "## 项目简介\n\n这是用户项目的可编辑初稿，未提供的具体信息需要继续补充。"}}
    monkeypatch.setattr(agent, "_post", reply)
    agent.chat(project_id, "请直接写商业计划书中的项目简介，没有营业收入，不要编造。")
    assert len(calls) == 1
    messages = calls[0]["messages"]
    assert "不能写成已经确定" in messages[0]["content"]
    assert "不要先列信息清单" in messages[-1]["content"]
    assert "WritingBlock" in messages[-1]["content"]
    assert "市场、定价、营收、融资及用户数量均需依据" in messages[0]["content"]
    assert calls[0]["tools"] == [], "直接起草且无上传材料时不应扇出无关搜索"


@pytest.mark.parametrize(("skill_id", "specific", "wrong"), [
    ("innovation-research", "不要假设项目一定涉及软件、算法或实验", "社会调查、学术论文与发明制作"),
    ("challenge-cup", "社会调查、学术论文与发明制作各有侧重", "不要默认已经注册公司"),
    ("internet-plus", "市场、定价、营收、融资及用户数量均需依据", "不要假设项目一定涉及软件"),
    ("social-survey", "数量、时间、地点及政策依据未提供时用占位", "不要假设项目一定涉及软件"),
])
def test_track_guidance_remains_specific_and_does_not_fabricate_facts(skill_id, specific, wrong):
    from proposal.project_writing import project_draft_guidance
    prompt = project_draft_guidance(skill_id)
    assert specific in prompt
    assert wrong not in prompt
    assert "只写本轮要求的部分" in prompt
    assert "已确认材料" in prompt
    assert "不能写成已决定或已完成" in prompt


def test_unmarked_business_introduction_is_available_for_student_review():
    project = {"state": {"skill_id": "internet-plus", "skill_category": "competition"}}
    raw = "## 项目简介\n\n本项目拟为校园闲置物品提供信息整理服务，先从学生提供的需求出发，具体运行情况尚需补充。"
    result = plain_project_chapters(raw, "请直接写商业计划书中的项目简介。", project)
    assert result and result[0][0] == "项目简介"


def test_material_opt_out_persists_until_explicitly_reenabled():
    history = [{"role": "user", "content": "请不要使用上传的附件。"}]
    assert not project_sources_allowed(history, "请直接写项目简介。")
    assert project_sources_allowed(history, "现在可以使用附件，请直接写项目简介。")
    assert not project_sources_allowed(history, "不使用附件，请直接写项目简介。")


@pytest.mark.parametrize("instruction", ["我不允许使用这些附件。", "这些材料不要再引用。", "我不想使用文件。", "不要使用我的个人资料。"])
def test_material_opt_out_supports_common_word_orders(instruction):
    assert not project_sources_allowed([], instruction)


def test_public_lookup_requires_an_affirmative_request():
    assert not explicit_public_lookup("不要查找资料，请直接写项目简介。")
    assert explicit_public_lookup("不要查找政策，请检索文献并写研究背景。")
    assert explicit_public_lookup("请查政策并写研究背景。")
    assert not explicit_public_lookup("不要查政策，直接写研究背景。")


def test_section_generation_does_not_read_disabled_attachments(tmp_path, monkeypatch):
    from proposal.workflow import AgenticWorkflowEngine
    store = Store(tmp_path)
    project_id = store.create_project()["id"]
    store.update_project(project_id, state={"skill_id": "internet-plus", "outline_confirmed": True},
                         outline=[{"id": "intro", "title": "项目简介"}])
    store.add_message(project_id, "user", "请不要使用上传的附件。")
    tools = ProposalTools(store, ProjectRetriever(store))
    monkeypatch.setattr(tools, "search_project_materials", lambda *_a, **_kw: pytest.fail("附件已禁用，不应检索"))
    agent = OllamaAgent(store, tools)
    seen = []
    class Result:
        content = "项目目标和用户需求待进一步明确。"
        def model_dump(self):
            return {"content": self.content, "status": "passed", "review_card": {"review_status": "completed"}}
    def workflow(*_a, **kwargs):
        seen.append(kwargs["evidence_results"])
        return Result()
    monkeypatch.setattr(AgenticWorkflowEngine, "run_workflow", workflow)
    agent.generate_section(project_id, "intro")
    assert seen == [[]]
