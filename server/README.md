# 大学生申报材料 Agent（本机测试版）

这是 Skills 仓库上的本地优先网页 Agent。工作台目录包含仓库中的 35 个 Skill，支持自然语言自动路由和手动选赛道；对话、资料确认、逐章编辑、校验与 Word 草稿导出复用同一套工作流。模型默认使用 Ollama，也可在“模型配置”中选择用户自备的 OpenAI Chat Completions 兼容 API。

## 对话草稿保存与导出

- 聊天中起草不等于已保存章节。点击「从对话整理草稿」预览最近 200 条消息中的完整章节，核对、编辑并勾选后保存；不会自动把建议预算等写成已确认事实，不调用模型或扣积分。
- 已有不同正文的章节不会被聊天候选覆盖；并发修改会提示重新核对。原聊天保持不变。
- 导出前保存编辑器中的最新修改；没有正式正文时先提示保存，确需空白草稿必须明确确认。
- 云端下载携带当前账号登录凭证，令牌不进入下载链接。新版材料产物为 ZIP，私有桶必须允许 `application/zip`；应用相应增量迁移，不要开放桶或取消大小限制。

## 工作台付费链路（生产状态）

目标流程：用户仅登录工作台 → 从 [Wopally 的 CatFK 店铺](https://catfk.com/shop/KGFPJI42) 购买工作台卡密或中转站余额卡密 → 工作台核验并绑定当前 Supabase 用户 → 后端将余额兑入低权限 `github-skills` 中转站账户 → 用户获得 ¥1＝10 积分（¥0.5＝5 积分）→ DeepSeek Flash 写作/GPT Image 生图按官方 API 单价的 2 倍计费。用户无需登录中转站、选择模型或接触服务端 Key。BYOK/Ollama 独立且不扣积分。

**2026-10-13 已验证真实余额码充值及 DeepSeek Flash 用量结算。** 首笔 ¥0.5 充值到账 5 积分；生产账本此后还记录了其他余额码兑换和多笔已结算的文本模型调用。店铺购买入口已恢复；Supabase 中同批 AGT1 卡密仍为激活状态，私密配对余额码尚未使用。`github-skills` 专用 Key 属分组 127。**GPT Image 的真实生成与费用结算、失败退费等场景尚未全面验收**，不能把“充值已到账”等同于“所有付费功能均已验收”。

两个系统无法共享数据库事务：工作台先创建唯一兑换意向，中转站确认余额码实际面值与服务账户后，Supabase 在一笔事务内给该用户加积分；超时或本地入账失败保留待核对，重试只查该账户的兑换历史，不盲目重复向中转站提交。每个文字调用预留 ¥0.2（2 积分），图片调用预留 ¥2（20 积分），查中转站 `usage` 中唯一 User-Agent 标识对应的确认用量。`o2x1_` 新请求按官方价的 2 倍结算；历史 `o90v1_` 按 9 折、`m12_` 按 12 倍、无前缀请求按 3 倍结算。多预留退回；实际费用高于预留或暂时无法确认时保留预留并阻止该用户继续调用，等待人工核对。图片一次仅生成一张 PNG，服务端 Key 不下发浏览器。

### 官方价快照 o90v1（2026-10-14）

- [DeepSeek 官方人民币价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)：Flash 每百万 token 空闲输入未命中 ¥1、命中 ¥0.02、输出 ¥4；高峰分别 ¥2、¥0.04、¥8。只接受中转站各分项和总额均匹配这两档官方价的记录，然后打 9 折；分组费率不参与本版零售定价。无法匹配则保留预留待核对，不猜测收费。
- [GPT Image 2 官方 Standard 单价](https://developers.openai.com/api/docs/pricing)：纯文字生图输入 $5/百万 text token、图片输出 $30/百万 image token。按中转站报告的确认 token 用量计算（不是固定每张估价）；缺少图片输出用量则不自动结算。仅支持当前 text-only 单张生成，不套用 Batch/Responses 缓存价。
- 图片美元转人民币固定使用 `6.705025`，来源为 [ExchangeRate-API](https://open.er-api.com/v6/latest/USD) 的 2026-10-14 00:02:32 UTC 参考报价，之后乘 `0.9`。这是公示的固定计费汇率，不是实时汇率或银行卡结算汇率。
- 调整官方单价或汇率必须新增价格版本并保留旧版，不能修改 `o90v1` 的历史算法。本版并不自动同步未来官方价格。

部署配置见 `.env.example`：`WORKBENCH_BACKEND_SECRET` 是 Supabase 专用的窄权限能力密钥，不是 project-wide `service_role`；`WORKBENCH_REDEEM_ENCRYPTION_KEY` 解密已配对的私密站内码。`WOPALLY_SERVICE_EMAIL/PASSWORD` 仅为 `github-skills` 低权限登录；`WOPALLY_WORKBENCH_API_KEY` 仅在服务端调用分组 127。`WOPALLY_ORIGIN_IP` 仅用于源站固定 IP 连接，TLS 仍校验 `api.wopally.cn` 证书。不应在代码仓库、浏览器或日志中输出任何明文卡密和密钥。

**剩余场景仍需验收：** 测试 GPT Image 请求，核对上游用量和工作台扣点；再验证失败退费、重复兑换与零余额拦截。任何一项不符，立刻将 `WORKBENCH_MODEL_BUNDLE_PAUSED=true` 与 `WORKBENCH_VOUCHERS_PAUSED=true` 写入 Vercel 生产环境并重新部署，必要时先停用专用 Key 692。利润报表不作为自动转账依据。

安全提醒：绝不可把用户输入传给 Sub2API 管理端 `create-and-redeem`；该端点对不存在的码可能先创建再充值。AGT1 店铺码与配对的私密站内码分离；若店铺实际发放现有中转站余额码，则走“仅兑换已存在余额码”路径，并在中转站确认面值后入账，禁止订阅码/并发码。

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
本地模式默认连接本机 `http://127.0.0.1:11434`。若显式设置 `OLLAMA_HOST` 指向远程服务，网页会显示远程警告；项目对话内容将发送到该模型主机。自定义 API 模式需填写 HTTPS API Base URL、模型名及自己的 API Key，并支持工具调用；本地模式的 API Key 暂存在当前标签页 `sessionStorage`。云端模式点击保存后，完整模型配置由 Vercel 使用独立 AES-256-GCM 密钥加密，保存至 Supabase `user_model_configs` 专用表（RLS 按账号隔离），不写入项目数据或 Auth metadata；同账号新设备登录后读取并仅保留于页面内存，每次推理经 Agent 转发至模型服务商。退出登录清除本机副本；清理浏览历史不删除云端配置，需在模型设置主动删除。请勿在公共/共用电脑配置；公网多人使用前，必须完成身份验证和项目数据隔离。

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
