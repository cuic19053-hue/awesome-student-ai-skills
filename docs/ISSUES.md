# awesome-student-ai-skills 技术问题清单（本地草稿，未发布）

> 状态：**仅本地盘点，未发布到 GitHub**。生成日期：2026-10-30。
> 范围：subskills(35) + Web 平台(server/) + MCP + 配置 + 运维 + 工作台。
> 方法：只读代码审计 + 项目自身事故报告交叉验证，未改动任何代码。

---

## 0. 根因收敛（回答"充钱了吗 / 为什么没有老客户 / 哪里卡住"）

1. **变现链路没闭环**：`/api/pay/create` 直接支付已 410 关闭，只剩卡密/券兑换这一条窄路；
   上游成本对账 `billing_status=provider_cost_reconciliation_pending`，充值后价值无法兑现。
2. **材料管线只对单 skill 且默认关**：`MATERIAL_PIPELINE_ENABLED`/`MATERIAL_WORKER_READY` 双开关默认 off，
   且 `materials.py:44` 仅 `innovation-research` 启用，其余 34 赛道走旧链。
3. **RAG 向量检索未上生产**：云端 Embedder 强制本机回环 → Vercel 无 Ollama → 退化中文 bigram 关键词匹配。
4. **付费工作台被 15+ 个环境开关 gate**，且权威 `.env.vercel.prod` 缺 7 个关键键，按文档部署即静默关停。
5. **subskills 层事实错误**：#5 奖助学金金额/政策、#1 表格路线图被错误关闭且未修完。

---

## 1. 已发布 GitHub（7 条，全部 open）

| # | 主题 |
|---|------|
| #46 | 写作请求被 `is_policy_question` 误判为政策问题降级 |
| #47 | 新用户首条无引导 |
| #48 | 长文本提交无反馈 |
| #49 | material job 失败 / needs_review 无恢复 |
| #50 | 计费 5 边界 |
| #51 | 项目重复创建（无防抖/幂等） |
| #52 | 核心功能三周零产出 |

## 2. 旧外部 issue（#1–#5）

| # | 状态 | 主题 |
|---|------|------|
| #5 | **关闭但未修完（事实错误仍在线，最优先）** | 奖助学金金额/政策：6 个奖学金 skill 仍写国奖 8000/励志 5000；`grant-application/build.py` 硬编码 4400/3300/2200 三档，`SKILL.md` 引已过时财教〔2007〕92号 |
| #1 | **关闭但未修完** | 技术路线图=表格非图片：`figgen`/`render_flowchart` 仅 3/35 build.py 接入 |
| #3 | 已修 | GRM/GMM 内容残留已清 |
| #4 | 已修 | Windows GBK 编码（35/35 build.py 加 reconfigure） |

## 3. 未发布 Web 平台（代码/数据级）

### 严重（6）
- 变现/审计硬编码"未接通"：`/api/pay/create` 410、`/api/pay/orders` 503、`/api/admin/profit-summary` 503、`billing_status=provider_cost_reconciliation_pending`
- 材料管线仅 innovation-research 单 skill 且双开关默认关（`materials.py:41-47`、`app.py:2916-2918`）
- 付费用户充值后价值未兑现（充 20 花 0.03、充 10 花 0.50）
- 私有材料检索云端退化中文 bigram（`retrieval.py:20-22,157`，Embedder 强制本机回环）
- 注册无验证码/邮箱校验/限流（`app.py:158-160`）
- 导出前置门槛 `require_export_content` 卡住正文（`chat_drafts.py:85-88`）

### 高（6）
- chat 6 轮 × 45s 易超时（`agent.py:838`）
- chat 历史截断 9 条 × 3500 字符（`agent.py:826`）
- material_worker 无结构化错误码统一"执行未完成"（`material_worker.py:489`）
- 注册数据污染（165 用户混入 batch_user_*/test_signup_speed_*/一次性邮箱）
- 冷启动套话"先从你刚才的需求开始"贯穿全期
- 导出 saving_artifacts 无恢复

### 中（13）
- RAG 未上生产（`RAG_PUBLIC_DB_ENABLED`/`RAG_DB_SEARCH_ENABLED` false + `documents.confirmation_origin` 迁移未上）
- CF Free 适配器未配真实账户
- 真实范文 0 入库（`server/knowledge/approved_examples/` 仅 README）
- RAG 评测未人工标注
- 大文件配额/清理/限流未实现
- STORAGE_UPLOAD_PROXY 默认关
- 跨标签页幂等未实现
- 上游收据人工兜底未闭环
- 45s 预算边界
- 流式需 [DONE]/finish_reason
- 对账告警依赖容量/调度/通知
- 心跳告警未接外部账号
- SECURITY DEFINER 未评估

### 低（7）
- free 租约过期自动重放（`material_jobs.py:111`）
- 分片 6MiB 强校验（`worker.mjs:215`）
- 下载事件不落日志（`worker.mjs:223-229`）
- 错误截断 400 字符（`material_jobs.py:176`）
- 时间戳 HMAC 窗口 90s（`billing_reconcile.py:54`）
- `json.load() is not True` 严格比较（`material_worker.py:61`）
- BYOK 429 重试 3 次（`agent.py:316,337`）

## 4. subskills 层新增（第 2 轮起）

| 严重度 | 位置 | 问题 |
|--------|------|------|
| 中 | `military-enlistment/build.py:654-657,1007,1024`；`western-plan/build.py:604-606,951,1005` | 政治面貌逻辑矛盾：模板"党员必写：入团时间"，示例数据 political_detail 写"2023年6月入党"、abilities 写"中共党员，2023年6月入团"，自相矛盾且复制到两 skill |
| 中 | `challenge-cup/build.py:1495-1530,1321` | DEFAULT_DATA 编造政策文号（`国办发〔2026〕12号`、`国发〔2021〕109号`）与无来源统计（2024火灾74.5万起/死亡2338人），会逐字写入申报书 |
| 低 | `index.json:46-47,659-662` | 路由触发词仍含旧金额（国奖 8000、励志 5000） |
| 低 | `national-scholarship/SKILL.md` frontmatter | 同一文件 description/正文已写 10000，triggers/适用段仍写 8000 |
| 高 | `utils/review_criteria.json`（28/35）| 缺 7 赛道评审标准（csc-scholarship、exchange-program、internet-plus-red-tour、military-enlistment、national-scholarship、outstanding-thesis、youth-league-conversion），`simulate_student_review` 对这 7 赛道直接报错；`review_simulator.py:6` 写"30 个"与实际 28 不符 |
| 低 | `military-enlistment/SKILL.md:250,1061` vs `:54,504,1170` | 年龄示例"18-24 周岁"与校验"女兵 18-22"不一致 |

## 5. 环境配置漂移（第 4 轮）

| 严重度 | 位置 | 问题 |
|--------|------|------|
| 中高 | `.env.vercel.prod` / `.current` / `.latest` | 三个快照漂移；权威 `.env.vercel.prod`（Oct 13）缺 7 键：APP_VERSION、MATERIAL_PIPELINE_ENABLED、MATERIAL_WORKER_READY、STORAGE_UPLOAD_PROXY_ENABLED、OBSERVABILITY_ENABLED、OBSERVABILITY_WRITE_KEY、USER_CONFIG_ENCRYPTION_KEY |
| 低 | `.env.vercel.prod.current` | MATERIAL_PIPELINE_ENABLED/MATERIAL_WORKER_READY/STORAGE_UPLOAD_PROXY_ENABLED 值为字面 `"[SENSITIVE]"`（脱敏占位，非布尔），快照不可信 |
| 低 | 根目录 `evals/` | 空死目录，真实评测在 `server/evals/` |

## 6. 工作台专项（第 5–6 轮）

| 严重度 | 位置 | 问题 |
|--------|------|------|
| 低 | `wopally_client.py:130` | `int(provider_user_id)` 未捕获异常，上游返回非数字 user_id 时 500 |
| 低 | `prepare_workbench_pairing.py:76-78` | `code_hash` 两处格式不一致：generate 脚本纯 64 hex，prepare 脚本 `\x`+hex（66 字符） |
| 低 | `payment.py` | `EPayClient`/`build_pay_url`/`verify_notify`/`build_sign`/`hmac_equal` 零引用死代码（直接支付已 410 关闭） |
| 低 | `app.py:965-969,992-999` | `_maybe_deduct_credits` 空实现 + `except BaseException` 退款分支死代码（实际 reserve/settle 在 agent.py transport） |

## 7. 已撤销/更正

- ~~导出页质检缺 LibreOffice/PyMuPDF~~：核查 `infra/material-worker/Dockerfile` 与 `requirements.txt` 后确认 worker 环境完整，撤销。
- `materials.py:44` None-state 隐患：复核 `storage.py:_project_row` state 恒为 dict，撤销。

---

## 8. 建议修复顺序（供后续决策，尚未执行）

- **P0**：放开材料管线（env 开关 + 35 赛道）；打通充值价值兑现；RAG 向量检索上生产。
- **P1**：重开 GitHub issue #5/#1（金额政策、表格路线图）；补 review_criteria 7 赛道。
- **P2**：统一 env 单一事实源；清理死代码；注册验证码/限流。

> 本文件仅盘点，未修复、未发布。修复需用户明确改口"不用修"后另行执行。
