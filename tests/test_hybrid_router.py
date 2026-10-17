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
