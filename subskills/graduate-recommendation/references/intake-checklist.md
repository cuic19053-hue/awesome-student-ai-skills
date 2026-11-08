# 三、信息采集清单

> 从 `subskills/graduate-recommendation/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要逐条向用户提问采集信息时。

### 3.1 学业硬指标（必采）

| 字段 | 说明 | 示例 |
|------|------|------|
| gpa_6sem | 前 6 学期 GPA（含分母） | 3.92/4.0 |
| weighted_avg | 加权平均分 | 91.5/100 |
| rank | 专业排名（X/N） | 1/87 |
| rank_percent | 排名百分比 | 前 1.1% |
| main_courses | 主修课程（含学期/学分/成绩） | 数组 |
| scholarships | 奖学金（时间/名称/级别） | 数组 |
| cet4 | CET-4 成绩 | 580 |
| cet6 | CET-6 成绩 | 580 |
| toefl | TOEFL 成绩（如有） | 105 |
| ielts | IELTS 成绩（如有） | 7.5 |
| recommend_qualified | 是否已取得本校推免资格 | 是/否 |

**追问话术**：
- "你前 6 学期 GPA 是多少？分母是 4.0 还是 5.0？"
- "专业排名 X/N，N 是专业总人数还是同年级人数？"
- "CET-6 考了几次？最高分多少？"
- "奖学金请按时间倒序列出，注明级别（国家/省/校/院）"

### 3.2 科研软实力（必采）

**论文**（每篇）：
- title 题目
- journal 期刊或会议全称
- level 级别（SCI 一区/二区/EI/CCF-A/B/C/中文核心/普通）
- author_order 作者排序（1/2/3...）
- status 状态（已发表/已录用/在审/已投）
- publish_date 发表或录用时间

**专利**（每项）：
- name 专利名称
- type 类型（发明/实用新型/外观）
- apply_no 申请号
- status 状态（已授权/实质审查/已公开/已受理）
- inventor_order 发明人排序

**大创/科研立项**（每个）：
- project_name 项目名称
- level 级别（国家级/省级/校级）
- role 角色（负责人/参与）
- duration 起止时间
- output 项目产出

**学科竞赛**（每个）：
- contest_name 竞赛全称
- award 奖项（特/一/二/三）
- level 级别（国家/省/校）
- time 获奖时间

**追问话术**：
- "论文作者排序是第几作者？通信作者吗？"
- "大创项目你是负责人还是参与？参与几个？"
- "竞赛获奖级别是国家级还是省级？证书上有写吗？"

### 3.3 申请信息（必采）

| 字段 | 说明 |
|------|------|
| applicant_name | 姓名 |
| applicant_gender | 性别 |
| applicant_birth | 出生年月 |
| applicant_political | 政治面貌 |
| applicant_college | 学院 |
| applicant_major | 专业 |
| applicant_class | 班级 |
| applicant_phone | 联系电话 |
| applicant_email | 邮箱（学校邮箱优先） |
| target_school | 申请学校 |
| target_college | 申请学院 |
| target_direction | 申请研究方向 |
| target_advisor | 申请导师（如已联系） |
| apply_channel | 渠道（夏令营/预推免/九推） |
| apply_date | 申请日期 |

### 3.4 推荐信（必采）

**推荐人 1**（一般为本校导师）：
- name 姓名
- title 职称
- relation 与申请人关系（任课教师/科研导师/班主任）
- research_area 研究方向
- contact 联系方式

**推荐人 2**（一般为另一位任课教师或科研导师）：
同上字段。

### 3.5 个人陈述要点（必采）

- direction_motivation 选择该方向的真实契机（具体事件/项目/论文）
- school_match 选择该校的具体理由（导师/平台/资源）
- graduate_plan 研究生阶段计划（课程/科研/产出）
- career_goal 长期职业规划（一句话即可）

**字段缺失处理**：
- P0 字段（姓名/GPA/排名/CET-6/申请学校/申请方向）缺失：必须追问
- 论文/专利/大创可缺失（少数申请人无）
- 推荐人联系方式缺失：留空让用户后续手填

