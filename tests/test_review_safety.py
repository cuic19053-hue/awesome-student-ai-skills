"""评审安全回归：异常不是低分，更不能当作通过；不调用外部模型。"""

import json

import pytest

from server.proposal.workflow import AgenticWorkflowEngine


WEIGHTS = {
    "真实性与防伪事实": 0.35,
    "科学性与论证深度": 0.30,
    "结构与规范符合度": 0.20,
    "行文与学术成熟度": 0.15,
}


def response(score=85.0, **overrides):
    result = {
        "overall_score": score,
        "passed": True,
        "dimensions": [
            {"name": name, "score": score, "weight": weight, "comment": "测试评语"}
            for name, weight in WEIGHTS.items()
        ],
        "strengths": [],
        "weaknesses": [],
        "actionable_revisions": [],
        "user_action_required": [],
        "blocking_issues": [],
    }
    return {**result, **overrides}


def engine(**kwargs):
    return AgenticWorkflowEngine(draft_caller=lambda *_: "可编辑草稿", **kwargs)


@pytest.mark.parametrize("raw", [
    "not json",
    "{}",
    "null",
    "[]",
    '{"overall_score":99,"passed":true}',
    json.dumps(response(passed="false")),
    json.dumps(response(overall_score="99")),
    json.dumps(response(overall_score=float("nan"))),
    json.dumps(response(overall_score=float("inf"))),
    json.dumps(response(dimensions=[])),
    json.dumps(response(unexpected="field")),
])
def test_invalid_review_never_has_a_score_or_pass(raw):
    review = engine().parse_critic(raw)
    assert review.review_status == "failed"
    assert review.passed is False
    assert review.overall_score is None
    assert review.error_code == "invalid_review_output"


def test_server_recomputes_total_and_pass_instead_of_trusting_model():
    raw = response(20.0, overall_score=100.0, passed=True)
    review = engine().parse_critic(json.dumps(raw))
    assert review.overall_score == 20.0
    assert review.passed is False
    assert review.review_status == "completed"


def test_factuality_failure_cannot_be_hidden_by_other_high_scores():
    raw = response(100.0)
    raw["dimensions"][0]["score"] = 50.0
    review = engine().parse_critic(json.dumps(raw))
    assert review.overall_score == 82.5
    assert review.passed is False


@pytest.mark.parametrize("change", ["duplicate_dimension", "wrong_weight", "string_score", "duplicate_key"])
def test_invalid_rubric_or_json_cannot_be_silently_fixed(change):
    raw = response()
    if change == "duplicate_dimension":
        raw["dimensions"][1] = dict(raw["dimensions"][0])
    elif change == "wrong_weight":
        raw["dimensions"][0]["weight"] = 0.9
    elif change == "string_score":
        raw["dimensions"][0]["score"] = "85"
    text = json.dumps(raw)
    if change == "duplicate_key":
        text = text.replace('"passed": true', '"passed": false, "passed": true')
    assert engine().parse_critic(text).review_status == "failed"


@pytest.mark.parametrize("field", ["blocking_issues", "user_action_required"])
def test_blocking_findings_prevent_high_score_pass(field):
    review = engine().parse_critic(json.dumps(response(99.0, **{field: ["需核验事实"]})))
    assert review.passed is False
    assert review.overall_score == 99.0


def test_valid_json_and_exact_fence_are_accepted():
    text = json.dumps(response())
    for raw in [text, f"```json\n{text}\n```"]:
        review = engine().parse_critic(raw)
        assert review.review_status == "completed"
        assert review.passed is True
        assert review.overall_score == 85.0


def test_review_failure_preserves_draft_without_retrying_writing():
    calls = []

    def critic(messages, options):
        calls.append(options)
        return "invalid"

    result = engine(critic_caller=critic).run_workflow({}, "s", "章节", "", [])
    assert result.content == "可编辑草稿"
    assert result.status == "review_failed"
    assert result.passed is False
    assert result.final_score is None
    assert result.review_card.score is None
    assert result.review_card.grade == "评审未完成"
    assert result.iterations == 1
    assert len(calls) == 1
    assert calls[0]["response_schema"]["type"] == "object"
    assert result.user_hints


def test_transport_failure_is_not_disguised_as_invalid_json_or_success():
    def critic(*_):
        raise RuntimeError("secret upstream body must not leak")

    result = engine(critic_caller=critic).run_workflow({}, "s", "章节", "", [])
    assert result.status == "review_failed"
    assert result.history[0].critic.error_code == "review_unavailable"
    assert "secret upstream" not in result.model_dump_json()


def test_placeholder_prevents_ready_claim_even_if_reviewer_misses_it():
    workflow = AgenticWorkflowEngine(
        draft_caller=lambda *_: "研究方案【待补充：真实测试数据】",
        critic_caller=lambda *_: json.dumps(response(99)),
    )
    result = workflow.run_workflow({}, "s", "章节", "", [])
    assert result.status == "needs_user_attention"
    assert not result.passed
    assert not result.review_card.passed
    assert "金奖" not in result.review_card.grade
