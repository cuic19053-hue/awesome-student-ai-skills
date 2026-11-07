# §5 信息采集清单

> 从 `subskills/exchange-program/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要逐条向用户提问采集信息时。

按字段优先级 P0/P1/P2 标注。P0 必采，缺失则警告；P1 建议采，缺失则降低文档质量；P2 可选，提供则增强文档。

### 5.1 通用必采（P0）

| 字段 | 说明 | 示例 |
|------|------|------|
| name | 真实姓名 | 张明 |
| gender | 性别 | 男 / 女 |
| student_id | 完整学号 | 2023123456 |
| current_college | 现学院全称 | 计算机科学与技术学院 |
| current_major | 现专业全称 | 计算机科学与技术 |
| grade | 入学年份 + 年级 | 2023 级 大二 |
| class_name | 班级 | 计科 2301 班 |
| target_university | 目标院校全称 | 伦敦大学学院（UCL） |
| target_country | 目标国家/地区 | 英国 |
| target_qs_rank | 目标院校 QS 排名 | 2025 年 QS 全球第 9 |
| exchange_type | 交流项目类型 | school / college / csc |
| exchange_duration | 交流时长 | 1 学年（2025.09~2026.06） |
| phone | 联系电话 | 138XXXXXXXX |
| email | 邮箱 | zhangming@xxx.edu.cn |
| apply_date | 申请日期 | 2025 年 3 月 15 日 |
| salutation | 称呼（可默认） | 尊敬的评审委员会： |

### 5.2 学业信息（P0）

| 字段 | 说明 | 示例 |
|------|------|------|
| current_gpa | 现专业 GPA（含满分制） | 3.85/4.0 |
| current_weighted_avg | 现专业加权平均分 | 88.5 |
| current_rank | 现专业排名（X/N 格式） | 5/120 |
| current_rank_total | 排名基数 | 120 |
| current_course_count | 现专业已修课程数 | 18 |
| current_high_score_count | 85 分以上课程数 | 14 |
| current_core_courses | 现专业主干课程表（4~6 门） | [{"name":"数据结构","credit":"4","score":"94"}] |
| language_score | 语言成绩（含取得时间 + 有效期） | 雅思 6.5（2024.09 取得，有效期至 2026.09） |
| language_breakdown | 语言分项成绩 | 听力 7.0 / 阅读 7.0 / 写作 6.0 / 口语 5.5 |

### 5.3 交流动机信息（P0）

| 字段 | 说明 | 示例 |
|------|------|------|
| motivation_academic | 学术深化动机 | UCL CS 全球第 8 + Efros 教授 CVPR 论文 25 篇 |
| motivation_vision | 视野拓展动机 | International Week + Chinese Society |
| motivation_language | 语言提升动机 | 雅思 6.5 → 7.0 + 学术英语课程 + 语言交换伙伴 |
| motivation_career | 职业规划动机 | 跨国算法工程师 + 海外博士申请 + 归国科研 |
| target_courses | 目标院校核心课程（≥5 门，含 name/credit/teacher） | [{"name":"Machine Learning","credit":"4","teacher":"Alexei Efros"}] |
| target_teachers | 目标院校导师（≥2 位，含 name/title/research） | [{"name":"Alexei Efros","title":"教授","research":"计算机视觉"}] |
| target_labs | 目标院校实验室/学术资源 | Gatsby Computational Neuroscience Unit |

### 5.4 学习计划信息（P0）

| 字段 | 说明 | 示例 |
|------|------|------|
| prep_plan | 行前准备计划（4 要素） | 雅思冲刺 80 课时 + 阅读 3 本书 + 5 门预选 + 12 学分认定 |
| abroad_plan | 在外学习计划（4 要素） | 5 门课程 + 每周时间分配 + 学术讲座 + CVPR Workshop 论文 |
| return_plan | 归国总结计划（3 要素） | 12 学分转换 + 2 场分享会 + 加入李教授课题组 |
| weekly_schedule | 每周时间分配 | 授课 16h + 自习 20h + 课题组 8h + 讲座 4h + 跨文化 6h |
| study_plan_table | 学习计划表（含 stage/time/content/target） | 见示例 |

### 5.5 文化交流与安全保障信息（P0）

| 字段 | 说明 | 示例 |
|------|------|------|
| cultural_integration | 文化融入计划 | International Week + Chinese Society + 家庭寄宿 |
| cultural_promotion | 中华文化传播计划 | 组织中国春节展示 + 参加学联活动 |
| academic_exchange | 学术交流计划 | 参加 UCL CS 研讨会 + 与其他交换生交流 |
| safety_legal | 法律遵守承诺 | 遵守英国法律 + 不参与非法活动 + 按时完成学业 |
| safety_insurance | 保险购买承诺 | 含医疗 + 意外 + 紧急救援，保额 30 万元人民币 |
| safety_report | 定期汇报承诺 | 每月汇报学习 + 紧急情况 24 小时内汇报 |
| safety_emergency | 紧急预案 | 紧急联系人 + 使馆联系方式 + 当地报警电话 |

### 5.6 入学背景信息（P1）

| 字段 | 说明 | 示例 |
|------|------|------|
| gaokao_year | 高考年份 | 2023 年 |
| gaokao_score | 高考总分 + 省份 | 632 分（山东） |
| admission_mode | 录取方式 | 普通批次 / 提前批 / 大类招生 |
| research_experience | 已有科研经历 | 跟随 X 教授参与 ML 项目 6 个月 |
| competition_experience | 已有竞赛经历 | 全国大学生数学建模竞赛省级二等奖 |

### 5.7 整段覆盖字段（P2）

| 字段 | 说明 |
|------|------|
| opening / basic_info / motivation / learning_plan / cultural_exchange / safety / ending | 提供则直接使用，跳过模板拼装 |

**追问话术汇总**：
- 缺 GPA 时："现专业 GPA 是多少？满分是 4.0 还是 5.0？专业排名是多少？请按 X/N 格式提供"
- 缺语言成绩时："雅思/托福成绩是多少？何时取得？有效期到何时？"
- 缺目标院校信息时："请从目标院校官网与 QS 官网查证：目标院校 QS 排名（含年份）、2 门特色课程名与主讲教师、2 位导师姓名与研究方向、1~2 个特色项目"
- 缺学习计划时："交流期间打算修读哪些课程？请提供至少 5 门课程名与学分。每周时间如何分配？"
- 缺安全保障时："是否已购买海外保险？保额多少？紧急联系人是谁？当地报警电话是多少？"

**复述确认**：信息采集结束后，必须向用户复述"现专业 GPA X.XX/4.0，专业排名 X/N，雅思/托福成绩 X.X，申请赴 XX 大学（QS 第 X 名）参加 X 学期/学年 X 类交流项目，已查证 N 门目标课程与 M 位导师，已制定 3 阶段学习计划，已确认安全保障承诺"，确认无误后再进入撰写阶段。

---

