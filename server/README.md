# 大学生申报材料 Agent（本机测试版）

这是 Skills 仓库上的本地优先网页 Agent。工作台目录包含仓库中的 35 个 Skill，支持自然语言自动路由和手动选赛道；对话、资料确认、逐章编辑、校验与 Word 草稿导出复用同一套工作流。模型默认使用 Ollama，也可在“模型配置”中选择用户自备的 OpenAI Chat Completions 兼容 API。

## 启动网页

要求 Python 3.11+；在仓库根目录执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r utils/requirements.txt
.venv/bin/python -m pip install -r server/requirements.txt
```

首次 OCR 使用时，RapidOCR 会下载其开源识别模型。材料处理和 OCR 均在本机完成；官方通知搜索与 Crossref 文献查询需要联网，但只发送搜索关键词，不上传学生的项目文件。搜索服务可能受网络环境影响；如果自动搜索不可用，可粘贴学校官网 HTTPS 链接，Agent 只读取 `edu.cn` / `gov.cn` 官方页面。也可通过 `SEARXNG_URL` 配置自建/信任的 SearXNG JSON API。

确认 Ollama 已启动并准备模型：

```bash
ollama pull qwen2.5:7b
ollama pull bge-m3
```

启动 Ollama 桌面应用，或在单独终端运行 `ollama serve`，然后：

```bash
.venv/bin/python -m uvicorn app:app --app-dir server --host 127.0.0.1 --port 8765
```

浏览器打开 <http://127.0.0.1:8765>。`--host 127.0.0.1` 只监听本机；未经身份验证的版本不要改为公网监听。
本地模式默认连接本机 `http://127.0.0.1:11434`。若显式设置 `OLLAMA_HOST` 指向远程服务，网页会显示远程警告；项目对话内容将发送到该模型主机。自定义 API 模式需填写 HTTPS API Base URL、模型名及自己的 API Key，并支持工具调用；API Key 暂存在当前浏览器标签页的 `sessionStorage`，每次推理请求都会发送到此 Agent 服务后转发至模型提供商，不保存到项目数据库。请勿在公共/共用电脑配置；公网多人使用前，必须完成身份验证和项目数据隔离。

默认项目数据库、上传材料、OCR 结果和 Word 文件保存在仓库根目录 `.agent-data/`，该目录已加入 `.gitignore`。可用环境变量 `PROPOSAL_AGENT_DATA_DIR` 改到其他本地路径。

## 当前网页流程

1. 点击“开始新建材料”，输入需要准备的材料。系统用 `utils/dispatcher.py` 进行匹配；低置信度时列出候选赛道供选择，也可从 35 个 Skill 下拉列表手动指定。
2. 创建项目后，Agent 按所选 Skill 的规范指导信息采集、拟定目录和逐章草稿。用户可以上传材料、确认 OCR 文字、修改章节，并运行导出前基础检查。
3. Word 导出沿用共享工作台的模板填充与通用排版流程。不同赛道的核心章节要求由所选 Skill 驱动；尚未逐个接通各赛道 `build.py` 专属排版器，因此导出后仍需核对赛道表格、学校模板和正式要求。

上传、确认材料、引用和事实核验等机制沿用原大创 Agent 的安全边界：未确认材料不进入检索，缺少依据处标为“待补充/待验证”，正式提交前需要人工核对。

未确认材料不进入 RAG。缺少依据的内容应保留“待补充/待验证”；论文元数据或摘要不等于已阅读全文。导出文件始终是草稿，正式提交前需要人工核对学校通知、数据和引用。

## Agent 与工具

网页 Agent 可选择 Ollama 本地模型或用户自备的 OpenAI Chat Completions 兼容 API，通过 tool calling 调用一组受限 Python 工具。模型设置包含连通性测试；生成文件、确认目录、确认事实、确认文献和确认图表由网页端显式执行，不允许模型任意访问磁盘或运行命令。

MCP 服务复用同一 `ProposalTools` 实现，当前提供：

- `list_projects`
- `create_project`
- `get_project_state`
- `add_text_material`（待确认）
- `confirm_project_material`
- `get_writing_guidance`
- `search_project_materials`
- `search_papers`
- `search_official_notices`
- `fetch_official_notice`
- `save_project_fact`
- `save_section`
- `save_diagram`
- `validate_project`
- `export_docx`
- `simulate_review`（仅用户主动要求时）

启动 stdio MCP（与网页共享本机项目库）：

```bash
PROPOSAL_AGENT_DATA_DIR="$PWD/.agent-data" \
  .venv/bin/python server/mcp_server.py --transport stdio
```

启动本机 Streamable HTTP MCP：

```bash
PROPOSAL_AGENT_DATA_DIR="$PWD/.agent-data" \
  .venv/bin/python server/mcp_server.py --transport streamable-http --host 127.0.0.1 --port 8765
```

网页本身默认在 `8765` 端口；HTTP MCP 建议改用其他端口（例如 `8766`），避免冲突。外部 MCP 客户端应使用 stdio 子进程方式，或单独指定未占用端口。

## 测试

```bash
.venv/bin/python -m pytest tests -q
PYTHONPATH=server:. .venv/bin/python server/evals/run.py
```

自动化单元/接口测试使用测试数据库和假模型，不产生模型费用。`server/evals/run.py` 会调用本机 Ollama 跑 `server/evals/cases.json` 中的小型行为回归集，并输出每个案例的工具调用、答案片段、追问数量和通过率。回归集覆盖材料证据、未确认事实保护、歧义确认拦截，以及“没有学校模板后继续自然对话”；当前对话案例要求每轮只问一个关键问题。本地模型未启动时会明确报错。
