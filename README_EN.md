# Student Application Materials Workbench

<img align="right" src="./assets/logo.png" width="72" height="72" alt="Stardust Agent">

**Stardust Agent** is an open source AI agent workbench for student research proposals, applications, business plans, social practice reports and personal statements. Students organize calls for applications and research notes in a project, ask the agent to find evidence, edit sections and export a Word draft. The Python and FastAPI backend supports local Ollama models and APIs compatible with OpenAI Chat Completions.

[Open the workbench](https://agent.stardust.website) · [Download a sample Word proposal](./examples/demos/demo_innovation_research.docx) · [Agent design notes (Chinese)](./docs/design/AGENT_REFACTOR.md) · [简体中文](./README.md)

## Follow a tool call

> Check my confirmed materials. What was the sample size, and what did we measure?

The evaluation project contains one confirmed observation log. In a local run, Qwen2.5 7B selected `search_project_materials`. The server searched the current project and returned the matching passage to the model. A translated excerpt from the reply follows.

> According to the confirmed observation log, the team observed 12 tomato seedlings and recorded soil moisture and lesion area.

The evaluation checks the tool trace as well as the answer. It fails if the model introduces a claim of 92% accuracy, which does not appear in the log. [Fixture and expected behavior](./server/evals/cases.json) · [Evaluation runner](./server/evals/run.py)

| Engineering question | How the workbench handles it | Source |
| --- | --- | --- |
| How does a model choose tools and finish a turn? | Streaming and synchronous replies share a loop with up to six iterations and a budget of eight tool calls per turn. The server checks the grant again at invocation and binds tools to the current project. | [Runtime](./server/proposal/chat_runtime.py) · [Tool router](./server/proposal/chat_tools.py) |
| Where does evidence come from? | User confirmation makes project documents eligible for indexing. The RAG pipeline combines keyword matches with compatible vectors when available and returns the source file and passage location. Official notices use school, year and applicability filters. | [Project retrieval](./server/proposal/retrieval.py) · [Knowledge coverage](./docs/rag-status.md) |
| How does a conversation become a document? | Students preview candidate sections in the chat, select and edit the text, then save it. Word export reads the saved sections so students can check the draft against the current school template. | [Chat drafts](./server/proposal/chat_drafts.py) · [Word exporter](./server/proposal/exporter.py) |
| How do long jobs handle interruptions? | When enabled, the material worker queues jobs such as section generation and export. Submissions use idempotency keys and writes check the project revision. A paid job with an expired lease is held for review. | [Job queue](./server/proposal/material_jobs.py) · [Worker](./server/material_worker.py) |

## Run locally

Start Ollama and use Python 3.11 or later.

```bash
git clone https://github.com/cuic19053-hue/stardust-agent.git
cd stardust-agent
python3 -m venv .venv
.venv/bin/python -m pip install -r utils/requirements.txt -r server/requirements.txt
ollama pull qwen2.5:7b
ollama pull bge-m3
.venv/bin/python -m uvicorn app:app --app-dir server --host 127.0.0.1 --port 8765
```

Open the local workbench, choose Ollama in the model settings and start a conversation. Upload a source document and confirm its text before asking the agent to retrieve evidence from it. Local mode uses SQLite and stores data in `.agent-data/`. Cloud mode uses Supabase to scope projects to each account. Hosted model calls use workbench credits. When you bring your own API key, your provider's pricing applies. [Local workbench](http://127.0.0.1:8765) · [Model and storage configuration](./server/README.md)

Run the evaluation from the repository root to reproduce the example above. It creates temporary projects and reports tool calls, answer excerpts and results for each case.

```bash
.venv/bin/python server/evals/run.py
```

## Domain guides and integrations

The agent loads the relevant guidance for each of 35 application scenarios. For example, `subskills/innovation-research/SKILL.md` describes the structure of an undergraduate innovation proposal. The sample Word files illustrate document layouts. Applicants should check their school's current requirements before submission. [Domain catalog](./subskills/README.md) · [Challenge Cup sample](./examples/demos/demo_challenge_cup.docx) · [Scholarship sample](./examples/demos/demo_national_scholarship.docx) · [All Word examples](./examples/demos/)

Codex, Cursor and other MCP clients can use the local project tools over stdio. Run `.venv/bin/python server/mcp_server.py --transport stdio` to share the workbench's project store. Developers can also load individual Skills in a compatible IDE. [Project MCP server](./server/mcp_server.py) · [Skills entry point](./SKILL.md)

## Credits and license

The project grew out of the team's work preparing Challenge Cup proposals. Special thanks to [@richyhu](https://github.com/richyhu), who wrote most of the project. Contributions covering school templates, changes to application requirements and reproducible issues are welcome. [Demo video](https://www.douyin.com/video/7692700167341985051) · [Contributing](./CONTRIBUTING.md) · [MIT license](./LICENSE)
