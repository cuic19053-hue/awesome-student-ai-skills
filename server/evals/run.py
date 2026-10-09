#!/usr/bin/env python3
"""Run a small local-model regression set; no API key or cloud model is used."""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

SERVER_DIR = Path(__file__).resolve().parents[1]
ROOT = SERVER_DIR.parent
for path in (str(SERVER_DIR), str(ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from proposal.agent import ModelUnavailable, OllamaAgent
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools


def run_case(case: dict[str, Any], root: Path, model: str) -> dict[str, Any]:
    store = Store(root / case["id"])
    retriever = ProjectRetriever(store)
    tools = ProposalTools(store, retriever)
    agent = OllamaAgent(store, tools, model=model)
    project = store.create_project(**case["project"])
    for index, source in enumerate(case.get("documents", [])):
        file_path = store.files_dir / project["id"] / f"seed-{index}.txt"
        file_path.write_text(source["text"], encoding="utf-8")
        document = store.add_document(
            project["id"],
            source["name"],
            str(file_path),
            "source",
            "text/plain",
        )
        store.update_document_extraction(
            document["id"],
            source["text"],
            "ready",
            confirmed=True,
        )
        retriever.index_document(document["id"], source["text"])

    if case.get("previous_assistant"):
        store.add_message(project["id"], "assistant", case["previous_assistant"])
    try:
        result = agent.chat(project["id"], case["user_message"])
    except ModelUnavailable as exc:
        return {"id": case["id"], "passed": False, "error": str(exc)}

    project_after = store.get_project(project["id"])
    response = result["message"]
    failures = []
    for tool_name in case.get("required_tools", []):
        if tool_name not in result.get("tool_calls", []):
            failures.append(f"缺少预期工具调用：{tool_name}")
    for expected in case.get("required_text", []):
        if expected not in response:
            failures.append(f"回答缺少预期证据文本：{expected}")
    for forbidden in case.get("forbidden_text", []):
        if forbidden in response:
            failures.append(f"回答含不应出现的陈述：{forbidden}")
    question_count = len(re.findall(r"[?？]", response))
    max_questions = case.get("max_questions")
    if max_questions is not None and question_count > max_questions:
        failures.append(
            f"本轮追问过多：检测到 {question_count} 个问号，上限为 {max_questions}"
        )
    if case.get("assert_no_confirmed_facts") and project_after["state"].get("confirmed_facts"):
        failures.append("用户未确认时，项目事实被写入了 confirmed_facts")
    return {
        "id": case["id"],
        "title": case["title"],
        "passed": not failures,
        "failures": failures,
        "tool_calls": result.get("tool_calls", []),
        "question_count": question_count,
        "answer_preview": response[:500],
    }


def main() -> int:
    cases_file = Path(__file__).with_name("cases.json")
    dataset = json.loads(cases_file.read_text(encoding="utf-8"))
    model = "qwen2.5:7b"
    import os

    model = os.environ.get("OLLAMA_MODEL", model)
    report = {
        "dataset": dataset["name"],
        "dataset_version": dataset["version"],
        "model": model,
        "cases": [],
    }
    with tempfile.TemporaryDirectory(prefix="proposal-agent-eval-") as temp_dir:
        root = Path(temp_dir)
        try:
            for case in dataset["cases"]:
                report["cases"].append(run_case(case, root, model))
        except ModelUnavailable as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
            return 2
    passed = sum(1 for item in report["cases"] if item["passed"])
    total = len(report["cases"])
    report["summary"] = {
        "passed": passed,
        "total": total,
        "pass_rate": round(passed / total, 3) if total else 0,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
