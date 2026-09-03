# awesome-student-ai-skills

[![Awesome](https://awesome.re/badge.svg)](https://awesome.re)
[![Agent Skills](https://img.shields.io/badge/Agent_Skills-Compatible-6e3bf0)](https://agentskills.io/specification)
[![Platform](https://img.shields.io/badge/Platform-WorkBuddy_|_Trae_|_Claude_Code_|_Codex_|_Cursor_|_Windsurf-blue)]()
[![License](https://img.shields.io/badge/License-MIT-green)](./LICENSE)
[![Subskills](https://img.shields.io/badge/Subskills-32-blue)](#能写哪些申报书)
[![Content](https://img.shields.io/badge/Content-2.4MB_|_42000+_lines-orange)]()
[![Mermaid](https://img.shields.io/badge/Charts-Mermaid-ff3670)]()

> 📊 **项目数据看板**
>
> | 指标 | 数值 | 说明 |
> |---|---|---|
> | 覆盖赛道 | **32 个** | 9 大类，从大创到公派留学全覆盖 |
> | 总内容量 | **2,400 KB** | 42,000+ 行结构化领域知识 |
> | 平均深度 | **68 KB / 赛道** | 最深 116 KB（大创创新训练） |
> | 最近更新 | 2026-07 | v2.1 版本 |
> | Star 目标 | 🎯 **1,000** | 当前向目标推进中 |
>
> ⭐ **如果这个项目帮到了你，点个 Star 让更多同学看到。Star 数越多，越能吸引赛道专家贡献内容，最终受益的是所有使用者。**

一套覆盖中国大学生常见申报场景的 Agent Skills。**32 个子 skill**，从大创立项到申请材料，从奖学金到保研推免，从应征入伍到公派留学。

> 🔔 **下载任意支持 Agent Skills 的工具（如 WorkBuddy），装上这 32 个 skills，对话就能生成图文并茂的申报书。**
> 不需要克隆、不需要装环境、不需要会编程。技术路线图、甘特图、流程图全部自动生成，输出可直接提交的 Word 文档。

---

## 为什么做这个

中国大学生每年要写多少份申报书？大创、奖学金、三下乡、入团、保研——每一份都要求格式规范、语气恰当、事实准确。但大多数人要么对着空白模板发愁，要么去网上搜一些不知所云的范文。

ChatGPT 可以帮你写，但通用模型不知道"大创"是什么、不知道国家奖学金评审看什么、不知道申请材料有查重。

这个项目把**高校申报书的领域知识**打包成了 Agent Skills——不是给聊天框里贴一段 prompt，而是让支持 Agent Skills 的 AI 工具（WorkBuddy、Claude Code、Codex、Cursor 等）在需要时自动加载对应的专业知识。

## 能写哪些申报书

**8 大类 · 32 个子 skill · 2,400 KB 结构化领域知识**

> 状态说明：✅ 已完备（可直接使用）｜ 🔄 持续打磨中｜ 📅 Star 解锁（达到对应 Star 数后启动）

### 🔬 项目类（要钱、要立项）— 8 个

| # | 赛道 | 编码 | 内容量 | 状态 |
|---|---|---|---|---|
| 1 | 大创 · 创新训练项目 | `innovation_research` | 116 KB | ✅ |
| 2 | 大创 · 创业训练项目 | `entrepreneurship_training` | 112 KB | ✅ |
| 3 | 大创 · 创业实践项目 | `entrepreneurship_practice` | 52 KB | ✅ |
| 4 | 校级科研立项 | `university_research` | 101 KB | ✅ |
| 5 | 院级科研立项 | `college_research` | 98 KB | ✅ |
| 6 | 挑战杯 · 课外学术科技作品 | `challenge_cup` | 102 KB | ✅ |
| 7 | 互联网+ · 商业计划书 | `internet_plus` | 93 KB | ✅ |
| 8 | 互联网+ · 红旅赛道 | `internet_plus_red_tour` | 79 KB | ✅ |

### 🏆 评优类（要荣誉）— 12 个

| # | 赛道 | 编码 | 内容量 | 状态 |
|---|---|---|---|---|
| 9 | 国家奖学金（8000 元） | `national_project_eval` | 39 KB | ✅ |
| 10 | 国家励志奖学金（5000 元） | `motivation_scholarship` | 43 KB | ✅ |
| 11 | 校级奖学金 | `university_scholarship` | 40 KB | ✅ |
| 12 | 企业专项奖学金 | `enterprise_scholarship` | 47 KB | ✅ |
| 13 | 单项奖学金 | `single_scholarship` | 44 KB | ✅ |
| 14 | 国家助学金 | `grant_application` | 75 KB | ✅ |
| 15 | 优秀毕业生 | `outstanding_graduate` | 46 KB | ✅ |
| 16 | 优秀学生 / 三好学生 | `outstanding_student` | 58 KB | ✅ |
| 17 | 优秀学生干部 | `outstanding_cadre` | 87 KB | ✅ |
| 18 | 文明大学生 / 优秀团员 | `civilized_student` | 60 KB | ✅ |
| 19 | 优秀班集体 | `class_collective` | 66 KB | ✅ |
| 20 | 优秀毕业设计 / 论文 | `outstanding_thesis` | 73 KB | ✅ |

### 🌾 活动类 — 5 个

| # | 赛道 | 编码 | 内容量 | 状态 |
|---|---|---|---|---|
| 21 | 三下乡 · 社会调查 | `social_survey` | 46 KB | ✅ |
| 22 | 三下乡 · 支教 | `volunteer_teaching` | 48 KB | ✅ |
| 23 | 三下乡 · 政策宣讲 | `policy_lecture` | 54 KB | ✅ |
| 24 | 三下乡 · 科技服务 | `tech_service` | 63 KB | ✅ |
| 25 | 西部计划 | `western_plan` | 74 KB | ✅ |

### 🚩 政治身份类 — 4 个

| # | 赛道 | 编码 | 内容量 | 状态 |
|---|---|---|---|---|
| 26 | 申请材料 | `youth_league_application` | 58 KB | ✅ |
| 27 | 阶段汇报 | `summary_report` | 51 KB | ✅ |
| 28 | 转正申请书 | `youth_league_application` | 90 KB | ✅ |
| 29 | 入团申请书 | `youth_league_application` | 72 KB | ✅ |

### 🎓 升学类 — 2 个

| # | 赛道 | 编码 | 内容量 | 状态 |
|---|---|---|---|---|
| 30 | 保研推免申请 | `graduate_recommendation` | 43 KB | ✅ |
| 31 | 选调生申请 | `selected_graduate` | 68 KB | ✅ |

### ✈️ 公派留学 / 交流类 — 2 个

| # | 赛道 | 编码 | 内容量 | 状态 |
|---|---|---|---|---|
| 32 | CSC 国家公派留学 | `csc_scholarship` | 65 KB | ✅ |
| 33 | 交流项目申请 | `exchange_program` | 89 KB | ✅ |

### 📋 其他 — 2 个

| # | 赛道 | 编码 | 内容量 | 状态 |
|---|---|---|---|---|
| 34 | 转专业申请 | `major_transfer` | 78 KB | ✅ |
| 35 | 应征入伍申请书 | `military_enlistment` | 73 KB | ✅ |

---

### 📅 Star 解锁路线图

> 以下赛道已规划，达到对应 Star 数后启动开发。**点 Star = 催更。**

| Star 里程碑 | 解锁赛道 | 说明 |
|---|---|---|
| ⭐ 100 | 讲莲杯、创青春、三创赛 | 竞赛类扩展 |
| ⭐ 300 | 节能减排大赛、生命科学竞赛 | 学科专项类 |
| ⭐ 500 | 服务外包大赛、商业精英挑战赛 | 商科类扩展 |
| ⭐ 1000 | 师范生教学技能、英语类竞赛 | 教师资格 + 外语类 |

## 项目结构

```
awesome-student-ai-skills/
├── subskills/               # 32 个赛道 skill（核心资产）
│   ├── innovation_research/SKILL.md    # 大创 · 创新训练（116 KB）
│   ├── national_project_eval/SKILL.md   # 国家奖学金
│   └── ...（共 35 个，详见上方表格）
├── references/              # 共享知识库
│   ├── writing_guide.md     # 撰写规范
│   ├── review_criteria.md   # 评审打分维度
│   └── pitfalls.md          # 常见错误与避坑指南
├── examples/demos/          # 10 个成品 .docx 模板（直接下载）
├── SKILL.md                 # 路由入口：识别类型 → 分流到子 skill
├── index.json               # 机器可读子 skill 索引
└── README.md                # 你正在看的
```

### 路由设计

根目录的 `SKILL.md` 是**路由器**，不直接生成内容。它的职责：

1. 识别用户要写哪类申报书（关键词匹配 + 决策树）
2. 不确定时列出候选让用户确认
3. 移交到对应子 skill

每个子 skill 是独立的，有完整的 YAML frontmatter（name、description、触发条件），Agent 可以根据描述自动匹配。

## 核心设计原则

### 1. 诚实底线

这不是"AI 帮你编一份看起来光鲜的申报书"的工具。所有子 skill 都内置了诚实约束：

- **只写用户能提供证据的事实** —— 问"你拿过什么奖"，不替你列奖项
- **不放大、不润色** —— "班级第二"就是"班级第二"，不是"成绩优异名列前茅"
- **不留模糊占位** —— 拿不准的信息追问，不写"获得多项荣誉"这种空话
- **提醒复核** —— 生成后明确提示用户逐项核对真实性

大学生申报书是面向学校/教育主管部门的正式材料。造假会被记入档案甚至触发学籍处分——这是红线，Skill 里写了，README 里再说一遍。

### 2. 渐进式加载

遵循 Agent Skills 规范的三层加载机制：

- **元数据层**（~100 tokens）：启动时只加载 name 和 description
- **指令层**：Agent 匹配到对应 skill 后，才加载 SKILL.md 正文
- **资源层**：执行过程中按需加载 references/ 中的深度文档

不把 35 个 skill 全塞进上下文。

### 3. 学校差异兼容

每个学校的模板有微调（栏目顺序、字号、页边距）。Skill 的策略是：

- 优先用用户提供的学校模板
- Skill 提供**内容质量参考**（怎么写好、怎么避坑）
- 格式标准以 `references/writing_guide.md` 为准

---

## 怎么用（3 步，5 分钟）

### 1. 挑一个支持 Agent Skills 的工具（免费）

| 工具 | 特点 | 下载 |
|---|---|---|
| **WorkBuddy** | 对话生成 .docx，图文并茂 | [官网](https://workbuddy.tencent.com) |
| **Trae** | 字节跳动出品，内置 Skills 支持 | [官网](https://www.trae.cn) |
| **Claude Code** | 终端 AI，开发者首选 | [官网](https://claude.ai/code) |
| **Codex** | OpenAI 出品，终端 AI | [官网](https://github.com/openai/codex) |
| **Cursor** | AI 编辑器，内置 Skills 支持 | [官网](https://cursor.sh) |
| **Windsurf** | Codeium 出品，AI IDE | [官网](https://codeium.com/windsurf) |
| **Qwen Coder** | 通义千问编程助手 | [官网](https://tongyi.aliyun.com) |

> 任选一个即可，推荐 WorkBuddy 或 Trae（零基础最友好，直接输出 Word）。

### 2. 安装这 32 个 skills
在工具中搜索或安装 `cuic19053-hue/awesome-student-ai-skills`，一键装全部 32 个赛道

### 3. 开始对话
直接跟 AI 说：

> "帮我写一份大创创新训练申报书，我的课题是无人机路径规划"

AI 会自动：
- 📋 追问你缺少的信息（排名？指导老师？预算？）
- ✍️ 生成申报书正文
- 📊 生成 Mermaid 图表（技术路线图 + 甘特图 + 流程图）
- 📄 输出图文并茂的 Word 文档，可直接提交

---

### 备选：网页 AI 直接用（不用装任何软件）

如果你不想装任何工具，也可以直接用网页 AI：

1. 打开 [豆包](https://doubao.com)、[DeepSeek](https://chat.deepseek.com)、[Claude](https://claude.ai) 等
2. 在 [subskills/](./subskills/README.md) 找到你需要的赛道，复制 `SKILL.md` 全部内容
3. 粘贴到 AI 对话框，说"我要申请 xxx，请按这个 skill 帮我写"

> ⚠️ 网页 AI 输出纯文本，不包含图片和 Word 排版。图文并茂的文档需要用支持 Agent Skills 的工具。

### 备选：直接下载成品模板

[examples/demos/](https://github.com/cuic19053-hue/awesome-student-ai-skills/tree/main/examples/demos) 目录存放了 10 个排版好的 .docx 文档：

| 下载 | 类型 |
|---|---|
| [📄 国家奖学金.docx](https://github.com/cuic19053-hue/awesome-student-ai-skills/raw/main/examples/demos/demo_national_project_eval.docx) | 奖学金 |
| [📄 申请材料.docx](https://github.com/cuic19053-hue/awesome-student-ai-skills/raw/main/examples/demos/demo_youth_league_application.docx) | 政治身份 |
| [📄 挑战杯.docx](https://github.com/cuic19053-hue/awesome-student-ai-skills/raw/main/examples/demos/demo_challenge_cup.docx) | 竞赛 |
| [📄 互联网+商业计划书.docx](https://github.com/cuic19053-hue/awesome-student-ai-skills/raw/main/examples/demos/demo_internet_plus.docx) | 竞赛 |
| [📄 大创创新训练.docx](https://github.com/cuic19053-hue/awesome-student-ai-skills/raw/main/examples/demos/demo_innovation_research.docx) | 科研 |
| [📄 优秀毕业生.docx](https://github.com/cuic19053-hue/awesome-student-ai-skills/raw/main/examples/demos/demo_outstanding_graduate.docx) | 评优 |
| [📄 院级科研立项.docx](https://github.com/cuic19053-hue/awesome-student-ai-skills/raw/main/examples/demos/demo_college_research.docx) | 科研 |
| [📄 应征入伍.docx](https://github.com/cuic19053-hue/awesome-student-ai-skills/raw/main/examples/demos/demo_military_enlistment.docx) | 征兵 |
| [📄 CSC 公派留学.docx](https://github.com/cuic19053-hue/awesome-student-ai-skills/raw/main/examples/demos/demo_csc_scholarship.docx) | 公派留学 |
| [📄 大创创业训练.docx](https://github.com/cuic19053-hue/awesome-student-ai-skills/raw/main/examples/demos/demo_entrepreneurship_training.docx) | 科研 |

点击链接 → 浏览器下载 → Word 打开 → 替换成自己的信息。

---

## 不是什么东西

- 不是"一键生成完美申报书"的魔法按钮 —— 你需要提供真实经历和数据
- 不是政策咨询工具 —— 不解读学校的评审规则变化
- 不保证中标 —— 申报结果取决于你的实际条件和评审偏好
- 不是学术不端工具 —— 不会帮你编造论文、奖项、经历
  

---

### 💡 觉得手调 Prompt 太繁琐？或者立项书反复被导师打回？

如果你手头的项目面临申报截止、缺乏创新点，或需要针对**具体比赛方向**做深度打磨，作者提供 1 对 1 定制化支持：

* **🎁 新人专属福利**：添加微信，**免费帮看立项书前 500 字**，指出 3 个最常被导师打回的逻辑硬伤。
* **🛠️ 承接深度服务**：
  * **大创 / 挑战杯 / 互联网+** 立项逻辑链深度重构与降噪
  * 核心研发流程 / 技术路线图绘制（提供高清矢量格式）
  * 商业计划书（BP）逻辑漏洞诊断与排版规范化
  * 模拟答辩：评委视角 10 问与防身话术设计
* **🔒 严格保密承诺**：所有材料仅用于当次梳理诊断，交付后 24 小时内本地彻底销毁，绝不外传或留档。

<br>

<div align="center">
  <img src="assets/contact_qr.png" width="220" alt="作者微信二维码">
  <p>👉 <b>扫码添加作者微信</b>（备注：<b>GitHub立项</b>，优先通过）</p>
</div>

---

## 免责声明

**本项目按"现状"提供，仅供学习和参考使用。**

1. **非官方出品**：本项目与任何高校、教育主管部门、奖学金评审委员会无关。Skill 中的评审标准、格式规范基于公开信息和社区经验整理，不构成官方指导意见。
2. **内容真实性由使用者负责**：Skill 生成的申报书内容取决于你提供的信息。使用本项目产生的任何申报材料，其真实性和准确性由使用者本人承担全部责任。用虚假信息申报奖学金、科研立项等，可能面临学籍处分乃至法律责任。
3. **不保证结果**：本项目不承诺、不保证使用后一定能通过评审、获得立项、拿到奖学金。评审结果受多种因素影响，包括但不限于：你的实际条件、竞争激烈程度、评审专家的主观判断、学校政策变化。
4. **格式以学校模板为准**：不同学校下发的模板在栏目顺序、字数要求、排版规范上可能存在差异。Skill 提供的内容参考不能替代学校官方模板，提交前请对照本校要求逐项检查。
5. **政治类文书的特殊性**：申请材料、阶段汇报等政治身份类文书有严格的政治表述规范。Skill 中的参考内容不构成政治立场建议。申请人对文书中政治表述的准确性承担全部责任。
6. **责任豁免**：在法律允许的最大范围内，本项目作者及贡献者不对因使用或无法使用本项目而产生的任何直接、间接、附带、特殊或后果性损害承担责任，包括但不限于申报失败、奖学金落选、项目被拒、学籍处分或其他损失，即使已被告知可能发生此类损害。
7. **合规使用**：使用者必须遵守所在国家/地区以及所在学校的相关法律法规和规章制度。如使用行为违反相关规定，请立即停止使用并删除本项目。

**使用本项目即表示你已阅读、理解并同意上述声明。** 如果你不同意，请勿使用。

---

## 致谢

感谢 [@richyhu](https://github.com/richyhu) 完成了本项目绝大部分的编写工作。从大创申报书到申请材料的每一个栏目、每一条避坑指南、每一处格式规范，都来自他对高校申报体系的深入理解和大量实践积累。

这些 skill 凝结了巨大的工作量——不只是写 prompt，而是把一套庞杂的、隐性的、散落在各高校通知文件里的领域知识，系统性地编码为 Agent 可理解、可执行的结构化指令。这在国内 Agent Skills 生态中是非常稀缺的工作。

---

## 贡献

欢迎提 Issue 和 PR。

如果你发现：

- 某个学校的模板格式有特殊要求，Skill 没有覆盖
- 某个申报类型的评审标准有更新（比如互联网+ 2026 新规）
- Skill 输出的内容有事实性错误

请告诉我们。

贡献前请阅读 `references/writing_guide.md` 了解撰写规范，确保你的修改符合项目的诚实底线。

---

## 许可

MIT License —— 随便用、随便改，但请保留原作者署名和免责声明。

详见 [LICENSE](./LICENSE)。

---

*如果你用这个项目写出了一份好的申报书，或者踩了什么坑，欢迎提 Issue 分享。让后面的人少走弯路。*
