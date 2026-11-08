"""Personal sections with no starting information do not invent a profile."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from proposal.agent import OllamaAgent
from proposal.retrieval import ProjectRetriever
from proposal.section_grounding import missing_personal_starting_material
from proposal.skills import registry
from proposal.storage import Store
from proposal.tools import ProposalTools
from proposal.workflow import AgenticWorkflowEngine


@pytest.mark.parametrize("skill_id", ["national-scholarship", "grant-application", "outstanding-student", "major-transfer", "graduate-recommendation", "selected-graduate"])
def test_no_personal_information_produces_a_placeholder_without_a_model(tmp_path, monkeypatch, skill_id):
    store = Store(tmp_path)
    project = store.create_project()
    project_id = project["id"]
    store.update_project(project_id, state={"skill_id": skill_id, "outline_confirmed": True},
                         outline=[{"id": "profile", "title": "个人情况"}])
    store.add_message(project_id, "user", "我想申请，请帮我写申请书。")
    store.add_message(project_id, "assistant", "例如：姓名：张三，获得了一等奖。")
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))
    monkeypatch.setattr(agent, "_post", lambda *_a, **_kw: pytest.fail("empty profile must not call a model"))
    result = agent.generate_section(project_id, "profile")
    assert result["requires_student_input"] is True
    assert "待补充" in result["content"] and "张三" not in result["content"]
    assert store.get_project(project_id)["sections"]["profile"] == result["content"]


def test_no_new_information_does_not_replace_an_existing_section(tmp_path, monkeypatch):
    store = Store(tmp_path)
    project_id = store.create_project()["id"]
    store.update_project(project_id, state={"skill_id": "grant-application", "outline_confirmed": True},
                         outline=[{"id": "family", "title": "家庭情况"}],
                         sections={"family": "学生自己写的正文"})
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))
    monkeypatch.setattr(agent, "_post", lambda *_a, **_kw: pytest.fail("must not call model"))
    result = agent.generate_section(project_id, "family")
    assert result["requires_student_input"] and "保留现有正文" in result["notice"]
    assert store.get_project(project_id)["sections"]["family"] == "学生自己写的正文"


def test_personal_information_keeps_the_normal_generation_path(tmp_path, monkeypatch):
    store = Store(tmp_path)
    project_id = store.create_project()["id"]
    store.update_project(project_id, state={"skill_id": "grant-application", "outline_confirmed": True,
                         "confirmed_facts": {"family_income": "2万元"}},
                         outline=[{"id": "family", "title": "家庭情况"}])
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))
    calls = []

    class Result:
        content = "【家庭情况待补充】"
        def model_dump(self):
            return {"content": self.content, "status": "passed", "review_card": {"review_status": "completed"}}

    monkeypatch.setattr(AgenticWorkflowEngine, "run_workflow", lambda *_a, **_kw: calls.append(True) or Result())
    result = agent.generate_section(project_id, "family")
    assert calls == [True]
    assert result["content"] == "【家庭情况待补充】"


def test_name_alone_is_not_family_income_information():
    project = {"state": {"confirmed_facts": {"name": "李明"}}}
    skill = registry.get("grant-application")
    assert missing_personal_starting_material(project, skill, "家庭情况", [], [])
    project["state"]["confirmed_facts"]["family_income"] = "2万元"
    assert not missing_personal_starting_material(project, skill, "家庭情况", [], [])


def test_templates_examples_and_unconfirmed_sources_are_not_student_input():
    project = {"state": {"confirmed_facts": {}}}
    skill = registry.get("national-scholarship")
    messages = [{"role": "user", "content": "我是想申请奖学金。"},
                {"role": "assistant", "content": "姓名：张三"}]
    documents = [
        {"kind": "template", "confirmed": 1, "confirmation_origin": "user", "extracted_text": "姓名：张三"},
        {"kind": "source", "confirmed": 0, "confirmation_origin": "user", "extracted_text": "姓名：张三"},
        {"kind": "source", "confirmed": 1, "confirmation_origin": "user", "extracted_text": "示例 姓名：张三"},
    ]
    assert missing_personal_starting_material(project, skill, "个人情况", messages, documents)


@pytest.mark.parametrize("instruction", ["请不要使用我的资料。", "申请书里不要写家庭收入。"])
def test_privacy_opt_out_stops_personal_generation_with_stored_facts(tmp_path, monkeypatch, instruction):
    store = Store(tmp_path)
    project_id = store.create_project()["id"]
    store.update_project(project_id, state={"skill_id": "grant-application", "outline_confirmed": True,
                         "confirmed_facts": {"family_income": "2万元", "name": "李明"}},
                         outline=[{"id": "family", "title": "家庭情况"}],
                         sections={"family": "学生自己写的正文"})
    store.add_message(project_id, "user", instruction)
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))
    monkeypatch.setattr(AgenticWorkflowEngine, "run_workflow", lambda *_a, **_kw: pytest.fail("must respect opt-out"))
    result = agent.generate_section(project_id, "family")
    assert result["requires_student_input"]
    assert result["content"] == "学生自己写的正文"
    assert "不使用个人资料" in result["notice"] or "不写家庭收入" in result["notice"]


def test_explicit_permission_can_resume_personal_section_generation():
    from proposal.section_grounding import personal_section_privacy_notice
    skill = registry.get("grant-application")
    history = [{"role": "user", "content": "请不要使用我的资料，也不要写家庭收入。"},
               {"role": "user", "content": "可以重新使用我的资料，可以写家庭收入。"}]
    assert not personal_section_privacy_notice(skill, "家庭情况", history)


def test_major_transfer_personal_section_respects_opt_out():
    from proposal.section_grounding import personal_section_privacy_notice
    skill = registry.get("major-transfer")
    history = [{"role": "user", "content": "请不要使用我的资料。"}]
    assert "不使用个人资料" in personal_section_privacy_notice(skill, "个人基本情况", history)
