# 开源 Agent 运行时调研：Kode 与当前工作台

调研日期：2026-11-08。目标是为学生申报工作台选择可复用的真实 Agent 运行时，并保留现有 Skills、项目隔离和计费能力。

## GitHub 仓库与用途

| 项目 | 源码定位 | 与本项目的关系 |
| --- | --- | --- |
| [Kode Agent SDK](https://github.com/shareAI-lab/kode-agent-sdk) | MIT，TypeScript Agent 运行时；本次检查的提交为 `ad1e7035eaa88a7ba58e7ffd6148b5a73c09a60a` | 优先验证对象，具备事件、Skills、工具、检查点和存储；需要 Node worker 与 Python 业务服务之间的接口 |
| [Kode CLI](https://github.com/shareAI-lab/Kode-CLI) | ShareAI Lab 的 Agent 产品与交互层 | 可研究会话、任务进度和用户交互；不是 Python 库 |
| [Learn Claude Code](https://github.com/shareAI-lab/learn-claude-code) | ShareAI Lab 的 Agent harness 教学项目 | 理解工具循环、上下文与分工；教学代码与生产运行时应分开评估 |
| [OpenAI Agents SDK Python](https://github.com/openai/openai-agents-python) | MIT，Python Agent SDK | 语言与现有 FastAPI 一致，适合做对照实验；会话历史不等于持久后台执行 |
| [LangGraph](https://github.com/langchain-ai/langgraph) | MIT，Python 图执行与检查点运行时 | 适合有明确状态图的材料生成；Postgres 检查点需要独立组件与数据设计 |
| [OpenAI Codex](https://github.com/openai/codex) | Apache-2.0，Rust Agent harness | 可研究真实的会话、上下文压缩、Skills 及 app-server，但不能称为 ChatGPT 私有源码 |
| [OpenCode](https://github.com/anomalyco/opencode) | MIT，TypeScript/Bun Agent 产品 | 可研究会话、权限、提供商、工具及交互；接入现有 Python 服务需额外进程边界 |

## Kode 源码中直接相关的部分

- [Agent 主循环](https://github.com/shareAI-lab/kode-agent-sdk/blob/ad1e7035eaa88a7ba58e7ffd6148b5a73c09a60a/src/core/agent.ts)、[工具执行器](https://github.com/shareAI-lab/kode-agent-sdk/blob/ad1e7035eaa88a7ba58e7ffd6148b5a73c09a60a/src/core/agent/tool-runner.ts)：负责一次任务的模型调用、工具执行和上下文续接。
- [SkillsManager](https://github.com/shareAI-lab/kode-agent-sdk/blob/ad1e7035eaa88a7ba58e7ffd6148b5a73c09a60a/src/core/skills/manager.ts)：扫描 `SKILL.md`，分别获取元数据、正文和资源目录。
- [恢复与分叉指南](https://github.com/shareAI-lab/kode-agent-sdk/blob/ad1e7035eaa88a7ba58e7ffd6148b5a73c09a60a/docs/en/guides/resume-fork.md)：介绍执行阶段、恢复点与崩溃恢复；应用仍需重新绑定监听器，并确保同一 Agent 不被多个实例并行执行。
- [事件说明](https://github.com/shareAI-lab/kode-agent-sdk/blob/ad1e7035eaa88a7ba58e7ffd6148b5a73c09a60a/docs/en/guides/events.md)：区分进度、控制和监控，适合对话流、业务确认和运维观察分别处理。
- [数据库实现](https://github.com/shareAI-lab/kode-agent-sdk/tree/ad1e7035eaa88a7ba58e7ffd6148b5a73c09a60a/src/infra/db)：提供 SQLite、PostgreSQL 存储。接入本项目之前必须单独验证租户隔离、密钥边界和计费。

上游 [README](https://github.com/shareAI-lab/kode-agent-sdk/blob/ad1e7035eaa88a7ba58e7ffd6148b5a73c09a60a/README.md) 明确提示 npm `2.7.5` 不包含当前主分支的部分生命周期修复；应先以固定提交实验，不能默认已发布包和源码相同。其推荐生产形态是无状态 API、独立长驻 worker、队列及共享存储；不是将长任务塞入 Vercel 单个请求。

固定提交在 2026-11-08 的 `npm audit --omit=dev` 报告 15 项依赖告警（2 项 critical、8 项 high、5 项 moderate）。这是依赖审计结果，不代表已证实对本产品可利用；接入生产前需要逐项评估和处理。

## 已确认的接入缺口

1. **Skills 兼容**：本项目的 35 个 `SKILL.md` 都有 Kode 可识别的 frontmatter，但对照真实 YAML 解析，34 个描述与 Kode 当前正则读取结果不同。要复用 `index.json` 或增加 YAML 解析兼容层；同时保留示例事实过滤，不能直接把完整示例当成学生事实。
2. **语言与部署**：工作台是 Python/FastAPI，Kode 是 Node/TypeScript。需要定义独立 worker 和授权的工具桥接；现有 Vercel 请求有时间限制，不能把普通流式请求称为持久运行。
3. **计费**：现有 Wopally 逐次预留、结算及结果不明的待核对处理必须继续生效。网络中断或上游已扣费但回复未知时，不得盲目重放模型请求。
4. **隔离**：Kode 的本地 sandbox 不应被当作操作系统级隔离。学生申报场景应默认只暴露项目授权工具，不直接开放任意 shell、跨项目文件访问或未经核验的副作用工具。
5. **恢复**：需要为会话/任务建立所有权、幂等键、状态、事件与租约，并验证断线恢复、并发和账单待核对；不要把工具结果未知误判成执行失败。

## 验证状态与下一步

本次以隔离临时目录和 Node 22 编译了 Kode 固定提交，跑通官方离线示例；另用假模型执行“调用只读工具 → 读取本项目国家奖学金 Skill → 接收工具结果 → 生成答复”的两轮循环，确认调用一次工具。测试时跳过依赖安装脚本，因此不代表 SQLite 原生依赖已验证。OpenAI Python SDK 也做过无网络、假模型的工具调用循环验证。二者均未替换当前工作台运行时，也都没有完成 Wopally 实际计费、真实断线恢复或生产数据隔离验收。

建议先建立独立实验 worker：固定 Kode 源码版本，用假模型与临时存储验证一次技能加载、工具回传、流式事件、停止和恢复；随后桥接现有工具和计费，并使用隔离测试数据验证故障场景。通过这些检查后，再决定如何接入现有入口。
