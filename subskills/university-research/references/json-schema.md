# 十一、JSON Schema 完整定义【v2.1 新增】

> 从 `subskills/university-research/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：构造 --data 输入文件、或 build.py 报字段校验错误时。

### 11.1 顶层字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| project_name | string | P0 | - | 课题名称 |
| leader_name | string | P0 | - | 负责人姓名 |
| leader_id | string | P0 | - | 学号 |
| leader_gender | string | P2 | "男" | 性别 |
| leader_major | string | P1 | - | 专业年级 |
| leader_phone | string | P1 | - | 联系电话 |
| leader_email | string | P2 | - | 邮箱 |
| advisor_name | string | P0 | - | 指导教师姓名 |
| advisor_title | string | P1 | - | 职称 |
| advisor_research | string | P1 | - | 研究方向 |
| advisor_phone | string | P1 | - | 指导教师电话 |
| college | string | P0 | - | 学院 |
| apply_date | string | P0 | - | 申报日期 |
| word_version | string | P1 | "enhanced" | 字数版本：standard/enhanced/peak |
| basic_info | object | P0 | - | 基础信息（research_type/discipline/duration/budget/project_source） |
| team_members | array | P1 | [] | 团队成员列表 |
| background | array | P0 | [] | 背景与意义（4 段） |
| policy_citations | array | P0 | [] | **国家政策引用（≥5 条）** |
| research_status | array | P0 | [] | 国内外研究现状（3 段） |
| literature_review | array | P0 | [] | **文献综述（≥15 条）** |
| scientific_challenges | array | P0 | [] | **科学挑战（2 个）** |
| research_goal | string | P0 | - | 研究目标 |
| research_content | array | P0 | [] | 研究内容 |
| key_problems | array | P0 | [] | 关键问题 |
| method_comparison | object | P1 | {} | **算法对比表** |
| tech_route | string | P0 | - | 总体技术路线文字 |
| tech_roadmap | array | P1 | [] | **技术路线图（2 张）** |
| formulas | array | P1 | [] | **数学公式（≥1 个）** |
| methods | array | P0 | [] | 研究方法 |
| data_source | string | P1 | - | 数据来源 |
| innovations | array | P1 | [] | 创新之处 |
| social_benefits | array | P1 | [] | **社会效益（5 项）** |
| team_foundation | string | P1 | - | 团队基础 |
| advisor_foundation | string | P1 | - | 指导教师基础 |
| lab_condition | string | P1 | - | 实验条件 |
| expected_outcomes | array | P0 | [] | 预期成果 |
| project_schedule | array | P1 | [] | **进度安排（4 阶段）** |
| schedule | array | P0 | [] | 进度安排（兼容旧版） |
| budget_items | array | P0 | [] | 经费预算 |
| budget_total | string | P0 | - | 申请经费 |
| references | array | P0 | [] | 参考文献（≥15 条） |

### 11.2 policy_citations 子字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| issuer | string | 是 | 发文机关（教育部/国务院/中办国办） |
| doc_no | string | 否 | 文号（教高〔2024〕3 号） |
| title | string | 是 | 文件标题 |
| publish_date | string | 是 | 发布时间（2024-03-15） |
| key_excerpt | string | 是 | 关键表述摘录（2~3 句） |
| relevance | string | 是 | 与课题关联说明（1~2 句） |

### 11.3 literature_review 子字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| idx | int | 是 | 文献编号 [1]~[20] |
| authors | string | 是 | 作者+年份（张华等（2022）） |
| view | string | 是 | 主要观点（30~50 字） |
| limit | string | 是 | 局限性（20~30 字） |
| lang | string | 是 | 语言：zh / en |

### 11.4 scientific_challenges 子字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| title | string | 是 | 标题（含关键技术词） |
| description | string | 是 | 问题描述段（3~5 句，含文献支撑 [N]） |
| sub_challenges | array | 是 | 子挑战列表（2 个） |
| sub_challenges[].name | string | 是 | 子挑战名称 |
| sub_challenges[].detail | string | 是 | 子挑战详述（5~8 句） |

### 11.5 method_comparison 子字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| title | string | 是 | 表标题 |
| dimensions | array | 是 | 维度列表（≥3 个） |
| methods | array | 是 | 方法列表（2~3 个） |
| methods[].name | string | 是 | 方法名（含文献引用 [N]） |
| methods[].values | array | 是 | 各维度取值 |
| conclusion | string | 是 | 选型结论 |

### 11.6 tech_roadmap 子字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| fig_no | string | 是 | 图号（图 1 / 图 2） |
| title | string | 是 | 图标题 |
| description | string | 是 | 图文字描述 |
| nodes | array | 是 | 图中节点列表 |

### 11.7 formulas 子字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| idx | int | 是 | 公式编号（1, 2, ...） |
| formula | string | 是 | 公式（纯文本或 LaTeX） |
| variables | string | 是 | 变量定义 |
| purpose | string | 是 | 用途说明 |

### 11.8 social_benefits 子字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| metric | string | 是 | 指标名 |
| baseline | string | 是 | 传统基准值 |
| expected | string | 是 | 系统预期值 |
| improvement | string | 是 | 提升幅度 |

### 11.9 project_schedule 子字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| phase | string | 是 | 阶段名 |
| time | string | 是 | 起止月份 |
| work | string | 是 | 主要任务（3~5 项） |
| output | string | 是 | 阶段成果 |

### 11.10 references 子字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| ref_type | string | 是 | journal/conference/book/thesis/web |
| authors | string | 是 | 作者 |
| title | string | 是 | 题名 |
| year | string | 是 | 年份 |
| journal | string | journal 必填 | 期刊名 |
| volume | string | journal 可选 | 卷 |
| issue | string | journal 可选 | 期 |
| pages | string | journal/conference 必填 | 页码 |
| conference | string | conference 必填 | 会议名 |
| city | string | conference/book/thesis 必填 | 出版地 |
| publisher | string | conference/book 必填 | 出版者 |
| school | string | thesis 必填 | 学位授予单位 |
| edition | string | book 可选 | 版本 |
| publish_date | string | web 必填 | 发布日期 |
| access_date | string | web 必填 | 访问日期 |
| url | string | web 必填 | URL |
| is_government | bool | web 可选 | 是否政府文件（决定 [Z/OL] 或 [EB/OL]） |

---

