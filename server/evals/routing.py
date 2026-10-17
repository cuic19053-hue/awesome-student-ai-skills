#!/usr/bin/env python3
"""Deterministic routing regression and warm-path latency; no model/API calls."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from utils.dispatcher import Dispatcher


def evaluate() -> dict:
    dispatcher = Dispatcher(intent_decider=False)
    cases = [
        {"query": f"我要准备{skill['display_name']}申请材料", "expected": skill["name"]}
        for skill in dispatcher.skills
    ]
    cases += json.loads(Path(__file__).with_name("routing_cases.json").read_text(encoding="utf-8"))["cases"]
    samples = []
    for case in cases:
        started = time.perf_counter()
        result = dispatcher.route(case["query"], top_n=5)
        elapsed_ms = (time.perf_counter() - started) * 1000
        top = [item["name"] for item in result["candidates"]]
        samples.append({
            "query": case["query"],
            "expected": case["expected"],
            "selected": result["selected"],
            "top_1": top[0] if top else None,
            "top_3": top[:3],
            "passed": result["selected"] == case["expected"],
            "latency_ms": round(elapsed_ms, 3),
        })
    total = len(samples)
    latencies = sorted(item["latency_ms"] for item in samples)
    return {
        "total": total,
        "decision_accuracy": round(sum(item["passed"] for item in samples) / total, 4),
        "top_1_accuracy": round(sum(item["top_1"] == item["expected"] for item in samples) / total, 4),
        "top_3_recall": round(sum(
            item["expected"] in item["top_3"] for item in samples if item["expected"] is not None
        ) / sum(item["expected"] is not None for item in samples), 4),
        "latency_ms_p50": round(statistics.median(latencies), 3),
        "latency_ms_p95": latencies[min(total - 1, int(total * .95))],
        "failures": [item for item in samples if not item["passed"]],
    }


if __name__ == "__main__":
    report = evaluate()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not report["failures"] else 1)
