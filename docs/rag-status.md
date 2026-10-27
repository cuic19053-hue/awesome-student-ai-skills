# 全赛道 RAG 改造状态与运行说明

## 当前实现

- 从 `index.json` 和语义词表派生 35 个路由卡片；新增否定与多选歧义回归，不确定时继续追问。卡片的空资格条件表示尚未整理，不代表没有资格限制。
- 路由器不会因为进程中存在 `OPENAI_API_KEY` 或 `ROUTER_API_KEY` 就自动调用付费云模型；可选意图模型仅使用显式配置的本机回环服务。
- 35 个赛道的 MIT 项目写作指南已按 Markdown 标题和行号切分到公共语料；**指南不是官方评审规则，案例数据也不是用户事实**。
- 已提供真实范文的授权证据、脱敏、人工复核与公开再分发审核入口；未经批准的范文不会进入公共语料。已批准的历史范文默认不召回，仅在用户明确选择时作为跨学校、跨年份的结构参考，并标记同赛道或跨赛道。给写作模型仅传人工复核的结构摘要，不传范文具体事实。当前没有满足这些条件的已入库真实范文。
- 本机候选清单通过 `scripts/list_example_candidates.py` 查看：候选必须单独核实作品类型、作者署名与再分发权利，并完成人工脱敏审核。存在许可与原文保密声明冲突的候选直接暂缓，不嵌入、不发布。
- 本地语料监听已审核清单与摘录的文件变化；撤销批准后不必重启进程即可从本地召回中移除。云端以数据库发布状态为准，数据库故障时不会回退到可能已撤回的本地副本。
- 已收录覆盖全部 35 个赛道的高校官方通知批次文件摘要（共 42 篇正式官方通知、1 篇经核验的院级科创活动报道，涵盖东南大学、无锡学院、大连海洋大学、西安交通大学、大连理工大学、河南大学、温州大学等高校官网）；项目学校、用户确认年度以及来源标注的学历、学院或子类别限制均匹配时才返回，需回源核验。各赛道的覆盖情况以 `scripts/rag_coverage.py` 的实际统计为准；不能把一所学校、一年通知推广至其他学校或年度。
- 工作台、Agent 和本地 MCP 均可检索公共知识；结果标明资料类型、来源位置和适用范围；项目私有材料仍独立检索。章节生成仅检查引用名称和位置是否出现在本轮检索，**不声称已自动证明论断得到来源支持**。
- 发送给写作模型的内部指南会过滤明显的示例、代码、联系方式和数值性要求；这是降低误用风险的保护措施，不等于完成政策或事实核验。用户仍可在工作台核对标注“非官方”的原始公开指南。
- 非模板上传材料和 MCP 新增文本默认待核对；确认前不能索引或检索。旧版可能自动确认的材料保留原文，但因缺少明确确认来源，升级后须由用户重新确认。修改已确认内容时先隐藏并删除旧索引，重新确认或索引失败不会暴露旧片段。对明确的资格、金额、排名或截止问题，只返回范围匹配的官方证据或标记为用户提交、尚待核验的通知片段；未找到依据则提示补充，不用非官方指南猜测，也不扣模型额度。
- 本地可选 BGE-M3 向量召回与 Ollama 小模型重排；公共和私有向量均绑定模型版本，旧的无版本向量不参与语义检索。云端公共知识表和向量检索迁移、受限权限的逐来源原子导入及关键词降级已实现，但默认关闭、尚未部署。
- 云端非空私有索引替换通过用户身份下的单事务 RPC 完成：校验已确认原文的哈希，文本变更时返回冲突，插入失败时回滚旧快照；撤回确认仍先隐藏并移除索引。迁移须先于应用部署。
- 可选 Cloudflare Workers Free 模型适配器默认关闭；仅在服务端明确确认免费计划、账户订阅检查通过，且用户本次明确同意发送检索问题时调用；只发送问题和已发布公共片段，不发送私有项目材料。Workers Paid 计划超额会收费，必须独立核实账户计划和额度；尚未配置真实账户、调用或验证生产链路。

## 本机离线构建与检索

```bash
# 只处理仓库公共资料；本机 Ollama 需已安装 bge-m3，不上传任何资料。
.venv/bin/python scripts/build_public_knowledge.py \
  --out .agent-data/rag/public-knowledge-vectors.jsonl --embed-local --resume

# 校验全部来源、片段、模型版本、向量维度和内容；不连接数据库。
.venv/bin/python scripts/publish_public_knowledge.py .agent-data/rag/public-knowledge-vectors.jsonl

# 启动本地工作台前按需设置；该配置不能用于生产网关依赖本机。
export RAG_LOCAL_VECTOR_INDEX="$PWD/.agent-data/rag/public-knowledge-vectors.jsonl"
export RAG_LOCAL_RERANK_MODEL="qwen2.5:7b"  # 可选，失败回退融合排序
```

知识来源变更后应重新运行构建；向量与当前来源内容和本机模型摘要不一致时不会混用。模型重排只处理融合召回的前 8 个候选，失败不影响检索。

本机 2026-10-27 对每个赛道各一条来源关联的 Agent 整理问题进行了实测：BGE-M3 加 `qwen2.5:7b` 对 35 条均返回有效排序，召回各用例指定来源；该次本机 P50 约 5.59 秒、P95 约 10.07 秒。样本未经过独立人工评分，问题也不是随机用户问题，只用于验证本机调用链，不代表线上延迟、用户场景准确率或引用支持率。院级科研用例命中的是明确标为非规则的校内活动报道。

## 可选云端免费模型预备配置

[Cloudflare Workers AI 官方价格说明](https://developers.cloudflare.com/workers-ai/platform/pricing/)区分 Free 与 Paid 计划：Free 每日额度用完后请求失败，Paid 超额可能收费。启用前，运营方须独立确认账户确为 Workers Free 且没有开启付费网关；代码中的标志并不能替代账单核验。

1. 在隔离环境配置 `RAG_CF_ACCOUNT_ID`、具备 Workers AI、Account Settings Read 和 Billing Read 权限的 `RAG_CF_API_TOKEN`、人工确认的 `RAG_CF_FREE_PLAN_CONFIRMED=true`，并固定经核验的 `RAG_CF_MODEL_REVISION=cloudflare:bge-m3:<版本标识>`。
2. 用 `scripts/build_public_knowledge.py --embed-cloudflare-free --out <索引路径>` 编码**公共语料**；该路径与本地 Ollama 模型不同，不得混用向量版本。额度用尽或账单信息不完整时停止并可续跑。
3. 在隔离数据库导入同版本公共索引，验证 RLS、实时检索及费用后，再决定是否在云端启用 `RAG_PUBLIC_DB_ENABLED` 和 `RAG_CF_ENABLED`。工作台每次检索必须单独勾选同意发送问题；未勾选、账单检查失败、额度耗尽或模型失败均降级。

适配器每次推理前确认账户标识与标准账户类型、读取账户订阅并保守拒绝任何已有订阅；这并不能消除账户状态并发变化或供应商未来计费规则变化的风险，必须监控账单并保持运营侧免费计划约束。当前未配置账号或经过真实调用验证。

## 当前状态与上线边界

- 全部 35 个赛道的官方通知覆盖均已达到 `school_year_scoped`；历史范文严格遵循版权授权与脱敏准则，未获明确许可与人工审查前保持 `hold_do_not_index`（0 入库、0 隐式召回），确保合规与安全。
- 数据库迁移未应用于生产，`RAG_PUBLIC_DB_ENABLED` 和 `RAG_DB_SEARCH_ENABLED` 应保持 `false`。新版应用依赖新增的 `documents.confirmation_origin` 字段，因此部署必须先运行并验证迁移；旧材料不会被删除，但需重新确认。导入脚本仅显式 `--execute` 才会调用 Supabase 服务角色；必须先在隔离项目完成迁移、JWT/RLS、向量版本、回滚及费用验证。切勿把本机 Docker 测试当成生产验证。
- 云端查询 Embedding/Rerank 适配器及逐次授权已实现，但真实免费账户、账单权限、实际调用及生产费用约束尚未验证。不能仅凭环境变量宣称账户免费；不得将本地 Ollama 作为生产线上依赖。
- 350 条路由与 175 条标题检索用例由目录和标题**自动合成**；另有 175 条与现有来源关联的问题及适用范围探针，由 Agent 整理并生成。它们均未经过独立人工标注或审核，不能当作真实用户场景的金标准；来源支持率、误引率和生产延迟尚未完成评测。
- `.agent-data/rag/review/knowledge-review-candidates.csv` 是不覆盖已有文件的待审候选，不是人工评测结果。独立审核人应逐项核查原文、问题与适用范围，使用非敏感审核编号标记；`scripts/evaluate_reviewed_knowledge.py` 会拒绝未审核或来源哈希变化的用例。该脚本仅核对召回与来源范围，仍不能自动证明正文论断得到引用支持。

```bash
.venv/bin/python scripts/rag_coverage.py
.venv/bin/python server/evals/routing_full.py
.venv/bin/python server/evals/knowledge_full.py
.venv/bin/python server/evals/knowledge_scoped.py
.venv/bin/python server/evals/local_model_coverage.py --index <本机索引路径> --output <新的本机测量记录>
.venv/bin/python scripts/prepare_knowledge_review.py --output <新的待审CSV路径>
.venv/bin/python scripts/evaluate_reviewed_knowledge.py <已审核CSV路径>
.venv/bin/python scripts/test_public_rag_postgres.py  # 隔离 Docker，绝不连接真实库
.venv/bin/python scripts/test_private_rag_postgres.py # 隔离 Docker，验证项目隔离和撤销
.venv/bin/python scripts/test_rag_postgrest.py       # 隔离 Docker，验证 PostgREST JWT/RPC
```
