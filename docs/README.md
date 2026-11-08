# 文档与设计规范中心

本目录归档 awesome-student-ai-skills 的系统架构设计、Prompt 体系、模板及历史报告。

## 目录索引

### 📁 design/ (核心架构与设计规范)
- [AGENT_REFACTOR.md](./design/AGENT_REFACTOR.md)：学生申报 Agent 当前实现、已知缺口与后续重构路线
- [OPEN_AGENT_RUNTIME_RESEARCH.md](./design/OPEN_AGENT_RUNTIME_RESEARCH.md)：Kode、Codex 及其他开源 Agent 运行时的源码调研与接入约束
- [ARCHITECTURE.md](./design/ARCHITECTURE.md)：系统总体架构设计（分层架构、目录规范、数据流）
- [AGENT_DESIGN.md](./design/AGENT_DESIGN.md)：智能体工作流与交互状态机设计
- [AGENT_PROMPT.md](./design/AGENT_PROMPT.md)：主 Agent 与 35 个子赛道调度提示词系统
- [WRITING_STYLE.md](./design/WRITING_STYLE.md)：**写作风格规范（去 AI 味）**——六维硬约束、禁用词表、替换动作、强制质检流程

### 🛠️ scripts/ (工程化工具与门禁)
- `check_doc_consistency.py`：文档一致性门禁（赛道数 / README 声称量 / 索引数量）
- `inject_writing_style.py`：向 35 个子 skill 幂等注入去 AI 味写作规范块
- `progressive_disclosure.py`：**渐进式披露重构**——把大章节外移到 `references/`，精简 SKILL.md
- `check_skill_description.py`：按 Anthropic 官方规范校验 `description`（长度 / 触发词 / 唯一性）
- `sync_readme_kb.py`：同步 README 赛道表的 KB 数字

### 📁 reports/ (审计与分析报告)
- [CASE_ANALYSIS.md](./reports/CASE_ANALYSIS.md)：真实申报书案例精细化分析与撰写提炼报告
- [FIX_REPORT.md](./reports/FIX_REPORT.md)：综合审计缺陷修复与验收报告 (PR #9)

### 📁 templates/ (子智能体模板)
- [SUBAGENT_TEMPLATE.md](./templates/SUBAGENT_TEMPLATE.md)：新增子智能体标准模板与规范说明
