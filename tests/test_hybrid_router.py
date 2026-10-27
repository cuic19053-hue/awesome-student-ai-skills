import json
from pathlib import Path

from utils.dispatcher import Dispatcher


def test_every_indexed_skill_has_a_decisive_canonical_route():
    router = Dispatcher(intent_decider=False)
    assert len(router.skills) == 35
    for skill in router.skills:
        result = router.route(f"我要准备{skill['display_name']}申请材料")
        assert result["selected"] == skill["name"], skill["name"]
        assert result["candidates"][0]["name"] == skill["name"]
        assert isinstance(router.dispatch(skill["display_name"])[0]["score"], int)


def test_confusions_and_abstentions():
    router = Dispatcher(intent_decider=False)
    path = Path(__file__).resolve().parents[1] / "server/evals/routing_cases.json"
    for case in json.loads(path.read_text(encoding="utf-8"))["cases"]:
        assert router.route(case["query"])["selected"] == case["expected"], case["query"]


def test_small_model_only_receives_ambiguous_top_candidates():
    class Decider:
        calls = []

        def decide(self, query, candidates):
            self.calls.append((query, [item["name"] for item in candidates]))
            return candidates[0]["name"]

    decider = Decider()
    router = Dispatcher(intent_decider=decider)
    assert router.route("我想报国奖")["method"] == "hard_rule"
    assert decider.calls == []
    result = router.route("我想写申请材料")
    assert result["selected"] is None
    assert decider.calls == []
    router.route("我想申请奖学金")
    assert len(decider.calls) == 1
    assert len(decider.calls[0][1]) <= 3
    assert router.route("国家奖学金或励志奖学金")["selected"] is None
    assert len(decider.calls) == 1


def test_explicit_choice_and_negated_generic_aliases():
    router = Dispatcher(intent_decider=False)
    assert router.route("我不申请大创·创业训练，我要申请大创·创新训练")["selected"] == "innovation-research"
    assert router.route("我不申请优秀学生/三好学生，我要申请国家助学金")["selected"] == "grant-application"
    assert router.route("别申请国家奖学金")["selected"] != "national-scholarship"
    assert router.route("想申请挑战杯或者互联网+")["selected"] is None
    assert router.route("想申请互联网+或者三下乡社会调查")["selected"] is None
    assert router.route("我要申报优秀团员")["selected"] == "outstanding-student"
    assert router.route("想申请优秀团员或者三好学生")["selected"] is None


def test_router_never_infers_cloud_consent_from_api_keys(monkeypatch):
    from utils.hybrid_router import configured_decider
    monkeypatch.setenv("OPENAI_API_KEY", "should-not-be-used")
    monkeypatch.setenv("ROUTER_API_KEY", "also-not-used")
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("ROUTER_INTENT_MODEL", raising=False)
    assert configured_decider() is None
    monkeypatch.setenv("ROUTER_INTENT_MODEL", "test-model")
    monkeypatch.setenv("OLLAMA_HOST", "https://remote.example")
    assert configured_decider() is None
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    decider = configured_decider()
    assert decider is not None and decider.local is not None and decider.cloud is None
