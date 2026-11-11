# 大学生申报材料（申报书、申请书、商业计划书、实践报告、个人陈述）一站式工作台

<img align="right" src="./assets/logo.png" width="72" height="72" alt="Stardust Agent">

**Stardust Agent** 是面向大学生申报材料的开源 AI Agent 工作台。学生可以在项目中整理学校通知和实验记录，让 Agent 查找依据、协助起草，再逐章编辑并导出 Word。后端使用 Python 和 FastAPI，支持 Ollama 本地模型和 OpenAI 兼容接口。

[打开在线工作台](https://agent.stardust.website) · [查看大创 Word 样例](./examples/demos/demo_innovation_research.docx) · [Agent 设计说明](./docs/design/AGENT_REFACTOR.md) · [English](./README_EN.md)

## 跟着一次工具调用读代码

> 请查一下已确认材料，告诉我样本量和记录的观察指标。

测试项目里有一份已确认的观察记录。本机实测中，Qwen2.5 7B 选择了 `search_project_materials`。服务端在当前项目中检索，将命中的段落交还给模型。下面是这次回答的节选。

> 根据已确认的观察记录，团队观察了12株番茄苗，并记录了土壤含水量和病斑面积。

评测会同时核对工具名和答复内容。如果回答引入记录里没有的“准确率达到 92%”，这条用例就会失败。[用例与原始材料](./server/evals/cases.json) · [评测脚本](./server/evals/run.py)

| 工程问题 | 实现方式 | 源码 |
| --- | --- | --- |
| 模型怎样选工具，何时结束？ | 同步答复与 SSE 流式答复共用对话循环。一轮对话最多迭代 6 次，工具调用预算为 8 次。服务端执行前再次检查工具授权，并绑定当前项目。 | [运行时](./server/proposal/chat_runtime.py) · [工具路由](./server/proposal/chat_tools.py) |
| 回答里的材料从哪里来？ | 项目资料经用户确认后分段索引。RAG 检索结合关键词和可用的同版本向量，返回来源文件和段落位置。官方通知另按学校、年度和适用范围查找。 | [项目检索](./server/proposal/retrieval.py) · [知识来源与覆盖](./docs/rag-status.md) |
| 聊天怎样变成 Word？ | 学生从对话中预览并选取章节草稿，编辑后保存。导出使用项目里已保存的正文，提交前仍可核对学校模板和引用。 | [对话草稿](./server/proposal/chat_drafts.py) · [Word 导出](./server/proposal/exporter.py) |
| 长任务中途断开怎么办？ | 启用材料 worker 后，章节生成和导出等任务按项目入队。提交使用幂等键，写回前检查项目版本，付费任务租约中断时保留记录供核对。 | [任务队列](./server/proposal/material_jobs.py) · [执行进程](./server/material_worker.py) |

## 本地运行与复现

需要 Python 3.11 或更高版本，并启动本机 Ollama。在终端运行以下命令。

```bash
git clone https://github.com/cuic19053-hue/awesome-student-ai-skills.git
cd awesome-student-ai-skills
python3 -m venv .venv
.venv/bin/python -m pip install -r utils/requirements.txt -r server/requirements.txt
ollama pull qwen2.5:7b
ollama pull bge-m3
.venv/bin/python -m uvicorn app:app --app-dir server --host 127.0.0.1 --port 8765
```

打开本机工作台，在「模型配置」中选择 Ollama。点击「开始新对话」描述申报目标，上传并核对资料后即可提问。本机模式使用 SQLite，数据保存在 `.agent-data/`。云端使用 Supabase 按账号管理项目。平台模型使用工作台积分，自带 API Key 时按模型服务商规则计费。[本机工作台](http://127.0.0.1:8765) · [模型、存储和服务配置](./server/README.md)

在仓库根目录运行下面的命令，可以用本机模型复现上面的提问。脚本使用临时项目，输出实际调用的工具、答复片段和各用例的通过情况。

```bash
.venv/bin/python server/evals/run.py
```

## 场景、样例与扩展

35 个申报场景以 Skills 形式提供领域规范。Agent 识别任务后按需读取对应指南。可以用示例文档查看栏目和排版，各校正式要求以当年通知为准。[全部场景](./subskills/README.md) · [挑战杯样例](./examples/demos/demo_challenge_cup.docx) · [奖学金样例](./examples/demos/demo_national_scholarship.docx) · [全部 Word 样例](./examples/demos/)

开发者可以从 Codex、Cursor 或其他 MCP 客户端连接本机项目工具，也可以直接加载某一赛道的 `SKILL.md`。本机项目 MCP 与网页共享项目和材料，使用 stdio 启动的命令为 `.venv/bin/python server/mcp_server.py --transport stdio`。[项目 MCP 实现](./server/mcp_server.py) · [Skills 入口](./SKILL.md)

<details>
<summary><b>展开 35 个领域指南及文件大小</b></summary>

**🔬 科研与竞赛 · 9 个**

| # | 赛道 | 编码 | 内容量 |
|---|---|---|---|
| 1 | 大创 · 创新训练项目 | `innovation-research` | 59 KB |
| 2 | 大创 · 创业训练项目 | `entrepreneurship-training` | 46 KB |
| 3 | 大创 · 创业实践项目 | `entrepreneurship-practice` | 52 KB |
| 4 | 校级科研立项 | `university-research` | 61 KB |
| 5 | 院级科研立项 | `college-research` | 79 KB |
| 6 | 挑战杯 · 课外学术科技作品 | `challenge-cup` | 81 KB |
| 7 | 互联网+ · 商业计划书 | `internet-plus` | 75 KB |
| 8 | 互联网+ · 红旅赛道 | `internet-plus-red-tour` | 64 KB |
| 9 | 国家级项目立项逻辑评测 | `national-project-eval` | 43 KB |

**🏆 评优与资助· 12 个**

| # | 赛道 | 编码 | 内容量 |
|---|---|---|---|
| 10 | 国家奖学金（10000 元） | `national-scholarship` | 37 KB |
| 11 | 国家励志奖学金（6000 元） | `motivation-scholarship` | 46 KB |
| 12 | 校级奖学金 | `university-scholarship` | 43 KB |
| 13 | 企业专项奖学金 | `enterprise-scholarship` | 49 KB |
| 14 | 单项奖学金 | `single-scholarship` | 44 KB |
| 15 | 国家助学金 | `grant-application` | 68 KB |
| 16 | 优秀毕业生 | `outstanding-graduate` | 45 KB |
| 17 | 优秀学生 / 三好学生 / 优秀团员 | `outstanding-student` | 60 KB |
| 18 | 优秀学生干部 | `outstanding-cadre` | 71 KB |
| 19 | 文明大学生 | `civilized-student` | 61 KB |
| 20 | 优秀班集体 | `class-collective` | 55 KB |
| 21 | 优秀毕业设计 / 论文 | `outstanding-thesis` | 64 KB |

**🌾 活动类 · 5 个**

| # | 赛道 | 编码 | 内容量 |
|---|---|---|---|
| 22 | 三下乡 · 社会调查 | `social-survey` | 46 KB |
| 23 | 三下乡 · 支教 | `volunteer-teaching` | 52 KB |
| 24 | 三下乡 · 政策宣讲 | `policy-lecture` | 55 KB |
| 25 | 三下乡 · 科技服务 | `tech-service` | 66 KB |
| 26 | 西部计划 | `western-plan` | 63 KB |

**🚩 政治身份类 · 3 个**

| # | 赛道 | 编码 | 内容量 |
|---|---|---|---|
| 27 | 入团申请书 | `youth-league-application` | 61 KB |
| 28 | 阶段汇报 / 思想汇报 | `summary-report` | 29 KB |
| 29 | 转正申请书 | `youth-league-conversion` | 29 KB |

**🎓 升学类 · 2 个**

| # | 赛道 | 编码 | 内容量 |
|---|---|---|---|
| 30 | 保研推免申请 | `graduate-recommendation` | 45 KB |
| 31 | 选调生申请 | `selected-graduate` | 63 KB |

**✈️ 公派留学 / 交流类 · 2 个**

| # | 赛道 | 编码 | 内容量 |
|---|---|---|---|
| 32 | CSC 国家公派留学 | `csc-scholarship` | 59 KB |
| 33 | 交流项目申请 | `exchange-program` | 73 KB |

**📋 其他 · 2 个**

| # | 赛道 | 编码 | 内容量 |
|---|---|---|---|
| 34 | 转专业申请 | `major-transfer` | 66 KB |
| 35 | 应征入伍申请书 | `military-enlistment` | 60 KB |

</details>

## 项目与社区

项目源自团队参加挑战杯、反复修改申报书的实践。感谢完成了本项目绝大部分编写工作的 [@richyhu](https://github.com/richyhu)。欢迎通过 Issue 提供学校模板的差异、更新的申报要求和能够复现的问题。[项目演示视频](https://www.douyin.com/video/7692700167341985051) · [贡献指南](./CONTRIBUTING.md) · [作者联系方式](./assets/contact_qr.png)

<details>
<summary>社区路线图</summary>

> 已突破 140 ⭐，「讲莲杯 / 创青春 / 三创赛」已进入开发队列。**点 Star = 催更。**

| 里程碑 | 解锁赛道 |
|---|---|
| ⭐ 300 | 节能减排大赛、生命科学竞赛（学科专项类） |
| ⭐ 500 | 服务外包大赛、商业精英挑战赛（商科类） |
| ⭐ 1000 | 师范生教学技能、英语类竞赛 |

</details>

<details>
<summary>使用说明与免责声明</summary>

**本项目按「现状」提供，仅供学习和参考。**

1. **非官方出品**：与任何高校、教育主管部门、评审委员会无关。评审标准与格式规范基于公开信息和社区经验整理，不构成官方指导意见。
2. **真实性由使用者负责**：生成的申报材料，其真实性和准确性由使用者本人承担全部责任。虚假申报可能面临学籍处分乃至法律责任。
3. **不保证结果**：不承诺通过评审、获得立项或拿到奖学金。
4. **格式以学校模板为准**：各校模板在栏目顺序、字数、排版上可能不同，提交前请对照本校要求逐项检查。
5. **政治类文书的特殊性**：参考内容不构成政治立场建议，政治表述的准确性由申请人承担全部责任。
6. **责任豁免**：在法律允许的最大范围内，作者及贡献者不对因使用或无法使用本项目产生的任何直接、间接或后果性损害承担责任。
7. **合规使用**：请遵守所在国家/地区及学校的法律法规。如使用行为违反相关规定，请立即停止并删除本项目。

**使用本项目即表示你已阅读、理解并同意上述声明。**

</details>

本项目采用 MIT 许可，使用与分发时请保留原作者署名和许可声明。[LICENSE](./LICENSE)
