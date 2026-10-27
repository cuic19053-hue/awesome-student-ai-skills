#!/usr/bin/env python3
"""Reproducible synthetic routing stress test; not a substitute for human labels."""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from utils.dispatcher import Dispatcher


def cases(router: Dispatcher) -> list[dict]:
    skills = router.skills
    output = []
    for index, skill in enumerate(skills):
        name, display = skill["name"], skill["display_name"]
        other = skills[(index + 1) % len(skills)]["display_name"]
        for category, query, expected in (
            ("canonical", f"我要申请{display}", name),
            ("canonical", f"帮我准备{display}材料", name),
            ("canonical", f"请给我写{display}", name),
            ("canonical", f"我准备{display}的申报材料", name),
            ("canonical", f"我想做{display}，麻烦帮我", name),
            ("explicit_negation", f"我不申请{other}，我要申请{display}", name),
            ("explicit_negation", f"不要{other}，我要做{display}", name),
            ("comparison", f"比较{display}和{other}有什么区别", None),
            ("multiple_options", f"想申请{display}或者{other}", None),
            ("insufficient", "我想写申请材料", None),
        ):
            output.append({"skill": name, "category": category, "query": query, "expected": expected})
    return output


def evaluate() -> dict:
    router = Dispatcher(intent_decider=False)
    samples = cases(router)
    failures = []
    categories: dict[str, list[bool]] = {}
    for sample in samples:
        got = router.route(sample["query"], top_n=5)["selected"]
        passed = got == sample["expected"]
        categories.setdefault(sample["category"], []).append(passed)
        if not passed:
            failures.append({**sample, "selected": got})
    return {"source": "synthetic templates; not human-labelled", "total": len(samples),
            "skills": len(router.skills), "accuracy": (len(samples)-len(failures))/len(samples),
            "categories": {k: {"passed": sum(v), "total": len(v)} for k,v in categories.items()},
            "failures": failures}


if __name__ == "__main__":
    report = evaluate()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(bool(report["failures"]))
