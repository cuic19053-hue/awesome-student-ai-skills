# §8 信息采集清单

> 从 `subskills/outstanding-thesis/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要逐条向用户提问采集信息时。

按"通用必采 → 毕设信息 → 课题信息 → 研究方法 → 创新点 → 成果应用"顺序采集。每轮不超过 5 个字段，关键缺失字段必须追问，**禁止编造毕设题目/答辩成绩/创新点/论文/专利/采纳证明**。

### 8.1 通用必采（10 字段）

| 字段 | 说明 | 示例 | 缺失追问策略 |
|------|------|------|--------------|
| name | 申请人姓名 | 张明 | "申请人全名？" |
| student_id | 学号 | 2021123456 | "学号？" |
| gender | 性别 | 男 | "性别？" |
| college | 学院全称 | 计算机科学与技术学院 | "学院全称？" |
| major | 专业全称 | 计算机科学与技术 | "专业全称？" |
| grade | 年级 | 2021 级 大四 | "入学年份？" |
| class_name | 班级 | 计科 2101 班 | "班级？" |
| phone | 联系电话 | 138XXXXXXXX | "手机号？" |
| apply_level | 申报规格 | school / college | "校级还是院级？" |
| apply_year | 毕业年份 | 2025 届 | "毕业年份？" |
| apply_date | 申报日期 | 2025 年 6 月 10 日 | "申报日期？" |

### 8.2 毕设信息（10 字段，硬指标）

| 字段 | 说明 | 示例 |
|------|------|------|
| thesis_title | 毕业设计/论文题目全称 | 基于对比学习的小样本医学影像分割方法研究 |
| thesis_type | 毕业设计类型 | experimental 实验研究 / engineering 工程设计 / theoretical 理论研究 / software 软件开发 / art_design 艺术设计 |
| advisor | 指导教师全名 + 职称 | 张伟 教授 |
| advisor_title | 导师职称独立字段 | 教授 |
| defense_score | 答辩成绩 | 92（优秀） |
| defense_rank | 答辩成绩专业排名 | 1/87 |
| plagiarism_rate | 查重率 | 8.5% |
| defense_date | 答辩日期 | 2025 年 5 月 28 日 |
| research_duration | 研究周期 | 2024.09-2025.05（9 个月） |
| graduate_type | 申请人类型 | undergraduate / master / doctor / junior_college |

### 8.3 课题信息（4 字段）

| 字段 | 说明 | 示例 |
|------|------|------|
| project_source | 课题来源 | 导师国家自然科学基金子课题（项目编号 62XXXXXXXX） / 自选题 / 校企合作 / 竞赛延伸 |
| research_problem | 核心 scientific/engineering 问题 | 现有监督学习方法在小样本场景下精度不足 |
| research_significance | 学术/应用意义 | 学术：改进对比学习迁移性能；应用：服务基层医院 AI 辅助诊断 |
| research_goals | 研究目标列表 | ["构建小样本医学影像数据集", "设计对比学习分割网络", "在公开数据集上验证"] |

### 8.4 研究方法信息（6 字段）

| 字段 | 说明 | 示例 |
|------|------|------|
| research_method | 研究方法主线（按 thesis_type 分流） | 文献调研 → 实验设计 → 数据采集 → 模型训练 → 性能评估 |
| technical_route | 技术路线文字描述 | 基于对比学习预训练 + Transformer 分割网络 + 迁移学习策略 |
| key_technologies | 关键技术列表 | [{name, application_step, problem_solved}] |
| data_material | 数据/材料/装置描述 | ISIC 2018 数据集（2 595 张） + 自建数据集（300 张，已脱敏） |
| research_stages | 研究阶段列表 | [{stage, time, content, output}]（4-6 项） |
| experiments | 实验设计与结果 | [{name, dataset, metric, baseline, ours, improvement}] |

### 8.5 创新点信息（核心，1 字段列表）

| 字段 | 说明 | 示例 |
|------|------|------|
| innovation_points | 创新点列表 | [{type: "theoretical", name, description, comparison, support_material}] |

每个创新点对象含 5 字段：
- type：theoretical 理论 / method 方法 / application 应用
- name：创新点名称
- description：创新点描述（80-120 字）
- comparison：与现有方法/理论/应用对比 + 量化优势
- support_material：支撑材料（论文/专利/软著/采纳证明）

### 8.6 成果与应用价值信息（4 字段）

| 字段 | 说明 | 示例 |
|------|------|------|
| achievements | 成果清单 6 类 | [{category: "论文", name, level, author_order, time}, ...] |
| application_scenarios | 应用场景列表 | [{scene, value, evidence}]（3-5 项） |
| adoption_proofs | 采纳证明列表 | [{unit, content, date, proof_no}] |
| future_research | 后续研究方向 | [{problem, breakthrough, prospect}]（2-3 项） |

### 8.7 摘要信息（1 字段）

| 字段 | 说明 | 示例 |
|------|------|------|
| abstract | 摘要文本（300~500 字，4 句结构） | 自动生成或用户自定义 |

### 8.8 字段优先级与追问话术

**P0 必采**（缺则无法撰写）：name、major、grade、thesis_title、thesis_type、advisor、defense_score、innovation_points
**P1 重要**（缺则影响质量）：project_source、research_problem、research_method、key_technologies、research_stages、achievements、application_scenarios
**P2 可选**（缺则用占位）：student_id、phone、plagiarism_rate、adoption_proofs、future_research

追问话术示例：
- 用户说"我毕设做得不错" → "毕设题目全称？指导教师姓名 + 职称？答辩成绩？查重率？"
- 用户说"我有几个创新点" → "每个创新点是什么？属于理论创新、方法创新还是应用创新？有什么支撑材料？与现有方法对比有什么优势？"
- 用户说"我发了论文" → "题目？期刊？级别（SCI/EI/核心）？你是第几作者？"
- 用户说"我有专利" → "专利名称？专利类型（发明/实用新型/外观）？状态（已授权/实质审查中）？你是第几发明人？"
- 用户说"我的研究有应用价值" → "应用在什么场景？合作单位？采纳证明？效果数据？"

**复述确认**：所有信息采完后，按"毕设信息 / 课题信息 / 研究方法 / 创新点 / 成果应用"顺序复述给用户确认，再进入撰写阶段。

---

