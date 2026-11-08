# §5 信息采集清单

> 从 `subskills/major-transfer/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要逐条向用户提问采集信息时。

按字段优先级 P0/P1/P2 标注。P0 必采，缺失则警告；P1 建议采，缺失则降低文档质量；P2 可选，提供则增强文档。

### 5.1 通用必采（P0）

| 字段 | 说明 | 示例 |
|------|------|------|
| name | 真实姓名 | 张明 |
| gender | 性别 | 男 / 女 |
| student_id | 完整学号 | 2024123456 |
| current_college | 现学院全称 | 化学工程学院 |
| current_major | 现专业全称 | 化学工程与工艺 |
| grade | 入学年份 + 年级 | 2024 级 大一 |
| class_name | 班级 | 化工 2401 班 |
| target_college | 目标学院全称 | 计算机科学与技术学院 |
| target_major | 目标专业全称 | 计算机科学与技术 |
| phone | 联系电话 | 138XXXXXXXX |
| apply_date | 申请日期 | 2025 年 5 月 20 日 |
| apply_window | 申请窗口 | 大一第二学期 / 大二第一学期 |
| salutation | 称呼（可默认） | 尊敬的学院领导、教务处老师： |
| transfer_reason_type | 转专业原因类型 | interest / academic / career |

### 5.2 现专业学业信息（P0）

| 字段 | 说明 | 示例 |
|------|------|------|
| current_gpa | 现专业 GPA（含满分制） | 3.92/4.0 |
| current_weighted_avg | 现专业加权平均分 | 89.5 |
| current_rank | 现专业排名（X/N 格式） | 3/95 |
| current_rank_total | 排名基数（rank 已含基数可省） | 95 |
| current_course_count | 现专业已修课程数 | 12 |
| current_high_score_count | 85 分以上课程数 | 9 |
| current_core_courses | 现专业主干课程表（4~6 门，含 name/credit/score） | [{"name":"高等数学（上）","credit":"5","score":"95"}] |
| cross_courses | 与目标专业交叉课程（学业优势型必含） | [{"name":"线性代数","credit":"3","score":"94"}] |

### 5.3 转专业原因信息（P0）

| 字段 | 说明 | 示例 |
|------|------|------|
| transfer_reason_type | 原因类型 | interest / academic / career |
| interest_origin | 兴趣萌芽时间点（兴趣型必含） | 2024.09 通识课《人工智能导论》 |
| interest_exploration | 兴趣探索成果（兴趣型必含） | 自学吴恩达 ML 课程 120 小时 + 3 个 Kaggle 项目 |
| interest_books | 阅读书目（兴趣型可选） | 《深度学习》前 6 章 |
| interest_club | 相关社团经历（兴趣型可选） | 校 ACM 协会每周 2 次训练 |
| academic_cross | 学业优势核心论据（学业型必含） | 数学类课程均 94+ + 数模省二等奖 |
| academic_competitions | 目标专业相关竞赛（学业型必含） | 2025.04 全国大学生数学建模竞赛省级二等奖 |
| academic_research | 目标专业相关科研（学业型可选） | 跟随 X 教授参与 ML 项目 3 个月 |
| career_target | 明确职业方向（职业型必含） | 医疗 AI 算法工程师 |
| career_internship | 行业实习经历（职业型必含） | 2025.01~2025.04 XX 医院信息科实习 3 个月 |
| career_interview | 行业人物访谈（职业型可选） | 访谈 3 位医疗 AI 从业者 |
| career_research | 行业调研报告（职业型可选） | 医疗 AI 行业人才缺口 30 万 |

### 5.4 目标专业认知信息（P0）

| 字段 | 说明 | 示例 |
|------|------|------|
| target_courses | 目标专业核心课程（≥5 门，含 name/credit/goal） | [{"name":"数据结构","credit":"4","goal":"算法设计"}] |
| target_teachers | 目标专业师资（≥2 位，含 name/title/research） | [{"name":"李XX","title":"教授","research":"计算机视觉"}] |
| target_employment | 就业前景（含 directions/employment_rate/salary/source） | {"directions":["算法工程师","后端开发"],"rate":"96.8%","salary":"8500/月","source":"麦可思 2024"} |
| target_competitions | 学科竞赛规划（≥2 个，含 name/level/time/role） | [{"name":"ACM-ICPC","level":"国家级","time":"2026.03","role":"队长"}] |

### 5.5 转后规划信息（P0）

| 字段 | 说明 | 示例 |
|------|------|------|
| short_term_plan | 短期规划（转入后 1 学期补修课程） | 补修《C++》《数据结构》共 8 学分 |
| mid_term_plan | 中期规划（转入后 1~2 学年科研/竞赛） | 加入李XX 教授课题组 + ACM-ICPC 区域赛铜牌 |
| long_term_plan | 长期规划（毕业去向） | 保研至清华计算机系医疗 AI 方向 |
| study_plan_table | 转后学习计划表（含 stage/courses/projects/target） | 见示例 |

### 5.6 入学背景信息（P1）

| 字段 | 说明 | 示例 |
|------|------|------|
| gaokao_year | 高考年份 | 2024 年 |
| gaokao_score | 高考总分 + 省份 | 632 分（山东） |
| admission_mode | 录取方式 | 普通批次 / 提前批 / 调剂 / 大类招生 |
| original_choice | 高考第一志愿专业 | 计算机科学与技术 |
| current_reason | 为何就读现专业 | 调剂至化学工程 |

### 5.7 整段覆盖字段（P2）

| 字段 | 说明 |
|------|------|
| opening / basic_info / current_study / transfer_reason / target_understanding / future_plan / ending | 提供则直接使用，跳过模板拼装 |

**追问话术汇总**：
- 缺 GPA 时："现专业 GPA 是多少？满分是 4.0 还是 5.0？专业排名是多少？请按 X/N 格式提供"
- 缺交叉课程时："现专业是否有与目标专业交叉的课程？课程名、学分、成绩分别是多少？"
- 缺目标专业课程时："请从目标学院官网培养方案中查证至少 5 门目标专业核心课程名与学分"
- 缺目标专业师资时："请从目标学院官网师资队伍栏目查证至少 2 位教师姓名、职称、研究方向"
- 缺转后规划时："转入后短期（1 学期）补修什么课程？中期（1~2 学年）参与什么科研/竞赛？长期（毕业去向）是保研/考研/就业？"

**复述确认**：信息采集结束后，必须向用户复述"现专业 GPA X.XX/4.0，专业排名 X/N，申请转入 YY 学院 ZZ 专业，转专业原因类型为（兴趣/学业/职业），目标专业核心课程已查证 N 门，已查证 M 位师资，转后补修 N 学分"，确认无误后再进入撰写阶段。

---

