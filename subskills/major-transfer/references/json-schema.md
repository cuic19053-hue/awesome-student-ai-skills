# §11 JSON Schema 完整字段（必加章节 7）

> 从 `subskills/major-transfer/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：构造 --data 输入文件、或 build.py 报字段校验错误时。

### 11.1 顶层字段总览

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "MajorTransferApplication",
  "description": "转专业申请书数据结构",
  "type": "object",
  "required": ["name", "current_college", "current_major", "grade", "target_college", "target_major", "current_gpa", "current_rank", "transfer_reason_type", "target_courses", "target_teachers"],
  "properties": {
    "transfer_reason_type": {
      "type": "string",
      "enum": ["interest", "academic", "career"],
      "description": "转专业原因类型：interest（兴趣驱动）/ academic（学业优势）/ career（职业规划）"
    },
    "current_major": {
      "type": "string",
      "description": "现专业全称"
    },
    "target_major": {
      "type": "string",
      "description": "目标专业全称"
    },
    "transfer_reason": {
      "type": "string",
      "description": "转专业原因整段（提供则直接使用，跳过模板拼装）"
    },
    "target_major_understanding": {
      "type": "string",
      "description": "目标专业认知整段（提供则直接使用，跳过模板拼装）"
    }
  }
}
```

### 11.2 完整字段清单（按 P0/P1/P2 分级）

#### P0 必填字段（15 项）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | ✅ | 真实姓名 |
| gender | string | ✅ | 男 / 女 |
| student_id | string | ✅ | 完整学号 |
| current_college | string | ✅ | 现学院全称 |
| current_major | string | ✅ | 现专业全称 |
| grade | string | ✅ | 入学年份 + 年级 |
| class_name | string | ✅ | 班级 |
| target_college | string | ✅ | 目标学院全称 |
| target_major | string | ✅ | 目标专业全称 |
| phone | string | ✅ | 联系电话 |
| apply_date | string | ✅ | 申请日期 |
| apply_window | string | ✅ | 申请窗口（大一第二学期/大二第一学期） |
| transfer_reason_type | string | ✅ | interest / academic / career |
| current_gpa | string | ✅ | 现专业 GPA（含满分制） |
| current_rank | string | ✅ | 现专业排名（X/N 格式） |
| target_courses | array | ✅ | 目标专业核心课程（≥5 门） |
| target_teachers | array | ✅ | 目标专业师资（≥2 位） |
| target_employment | object | ✅ | 就业前景（含 directions/rate/salary/source） |
| target_competitions | array | ✅ | 学科竞赛规划（≥2 个） |

#### P1 建议字段（学业与原因）

| 字段 | 类型 | 说明 |
|------|------|------|
| current_weighted_avg | string | 现专业加权平均分 |
| current_rank_total | string | 排名基数 |
| current_course_count | number | 现专业已修课程数 |
| current_high_score_count | number | 85 分以上课程数 |
| current_core_courses | array | 现专业主干课程表（4~6 门） |
| cross_courses | array | 与目标专业交叉课程 |
| interest_origin | string | 兴趣萌芽时间点（兴趣型必含） |
| interest_exploration | string | 兴趣探索成果（兴趣型必含） |
| interest_books | string | 阅读书目（兴趣型可选） |
| interest_club | string | 相关社团经历（兴趣型可选） |
| academic_cross | string | 学业优势核心论据（学业型必含） |
| academic_competitions | array | 目标专业相关竞赛（学业型必含） |
| academic_research | string | 目标专业相关科研（学业型可选） |
| career_target | string | 明确职业方向（职业型必含） |
| career_internship | string | 行业实习经历（职业型必含） |
| career_interview | string | 行业人物访谈（职业型可选） |
| career_research | string | 行业调研报告（职业型可选） |

#### P1 建议字段（转后规划）

| 字段 | 类型 | 说明 |
|------|------|------|
| short_term_plan | string | 短期规划（转入后 1 学期） |
| mid_term_plan | string | 中期规划（转入后 1~2 学年） |
| long_term_plan | string | 长期规划（毕业去向） |
| study_plan_table | array | 转后学习计划表（含 stage/time/content/target） |

#### P1 建议字段（入学背景）

| 字段 | 类型 | 说明 |
|------|------|------|
| gaokao_year | string | 高考年份 |
| gaokao_score | string | 高考总分 + 省份 |
| admission_mode | string | 录取方式 |
| original_choice | string | 高考第一志愿专业 |
| current_reason | string | 为何就读现专业 |

#### P2 可选字段（整段覆盖）

| 字段 | 类型 | 说明 |
|------|------|------|
| word_count_target | string | 字数档位（short/standard/long） |
| opening | string | 开头整段覆盖 |
| basic_info | string | 个人基本情况整段覆盖 |
| current_study | string | 现专业学习整段覆盖 |
| transfer_reason | string | 转专业原因整段覆盖 |
| target_understanding | string | 目标专业认知整段覆盖 |
| future_plan | string | 转后规划整段覆盖 |
| ending | string | 结尾整段覆盖 |
| salutation | string | 称呼（默认"尊敬的学院领导、教务处老师："） |

### 11.3 数组字段子结构

**current_core_courses / cross_courses 子结构**：
```json
{
  "name": "高等数学（上）",
  "credit": "5",
  "score": "95"
}
```

**target_courses 子结构**：
```json
{
  "name": "数据结构",
  "credit": "4",
  "goal": "培养算法设计能力"
}
```

**target_teachers 子结构**：
```json
{
  "name": "李XX",
  "title": "教授",
  "research": "计算机视觉与医学影像分析"
}
```

**target_employment 子结构**：
```json
{
  "directions": ["互联网算法工程师", "金融机构 IT 岗位", "政府信息化岗位"],
  "rate": "96.8%",
  "salary": "8500 元/月起薪",
  "source": "麦可思《2024 中国大学生就业报告》"
}
```

**target_competitions 子结构**：
```json
{
  "name": "全国大学生数学建模竞赛",
  "level": "国家级",
  "time": "2025.09",
  "role": "算法负责人，目标省级一等奖"
}
```

**study_plan_table 子结构**：
```json
{
  "stage": "短期",
  "time": "2025.09~2026.01",
  "content": "补修《C++ 程序设计》《数据结构》共 8 学分",
  "target": "GPA≥3.8，学分补修完毕"
}
```

### 11.4 完整 data.json 示例（兴趣驱动型，1000 字版）

```json
{
  "name": "张明", "student_id": "2024123456", "gender": "男",
  "current_college": "化学工程学院", "current_major": "化学工程与工艺",
  "grade": "2024 级 大一", "class_name": "化工 2401 班",
  "target_college": "计算机科学与技术学院", "target_major": "计算机科学与技术",
  "phone": "138XXXXXXXX", "apply_date": "2025 年 5 月 20 日",
  "apply_window": "大一第二学期", "transfer_reason_type": "interest",
  "salutation": "尊敬的学院领导、教务处老师：",
  "current_gpa": "3.92/4.0", "current_weighted_avg": "89.5",
  "current_rank": "3/95", "current_rank_total": "95",
  "current_course_count": "12", "current_high_score_count": "9",
  "current_core_courses": [
    {"name": "高等数学（上）", "credit": "5", "score": "95"},
    {"name": "线性代数", "credit": "3", "score": "94"},
    {"name": "无机化学", "credit": "4", "score": "88"},
    {"name": "C 程序设计", "credit": "3", "score": "96"}
  ],
  "cross_courses": [
    {"name": "高等数学（上）", "credit": "5", "score": "95"},
    {"name": "C 程序设计", "credit": "3", "score": "96"}
  ],
  "interest_origin": "2024.09 通识课《人工智能导论》",
  "interest_exploration": "自学吴恩达《Machine Learning》课程（累计 120 小时），完成 3 个 Kaggle 入门项目",
  "interest_books": "阅读《深度学习》（花书）前 6 章",
  "interest_club": "加入校 ACM 协会，每周参与 2 次算法训练，累计解决 LeetCode 题 150 道",
  "gaokao_year": "2024 年", "gaokao_score": "632 分（山东）",
  "admission_mode": "普通批次", "original_choice": "计算机科学与技术",
  "current_reason": "因分数未达计算机科学与技术专业录取线，调剂至化学工程与工艺专业",
  "target_courses": [
    {"name": "数据结构", "credit": "4", "goal": "算法设计"},
    {"name": "操作系统", "credit": "4", "goal": "系统级编程"},
    {"name": "计算机网络", "credit": "3", "goal": "网络协议分析"},
    {"name": "数据库系统原理", "credit": "3", "goal": "数据管理"},
    {"name": "编译原理", "credit": "4", "goal": "语言处理"}
  ],
  "target_teachers": [
    {"name": "李XX", "title": "教授", "research": "计算机视觉与医学影像分析"},
    {"name": "王XX", "title": "副教授", "research": "机器学习与推荐系统"}
  ],
  "target_employment": {"directions": ["互联网算法工程师", "金融机构 IT 岗位", "政府信息化岗位"], "rate": "96.8%", "salary": "8500 元/月起薪", "source": "麦可思《2024 中国大学生就业报告》"},
  "target_competitions": [
    {"name": "全国大学生数学建模竞赛", "level": "国家级", "time": "2025.09", "role": "算法负责人，目标省级一等奖"},
    {"name": "ACM-ICPC 区域赛", "level": "国家级", "time": "2026.03", "role": "队长，目标铜牌"}
  ],
  "short_term_plan": "补修《C++ 程序设计》（4 学分）、《数据结构》（4 学分）共 8 学分；现专业已修通识课 18 学分可认定",
  "mid_term_plan": "加入李XX 教授课题组参与医学影像分析项目，目标以第二作者发表 1 篇 SCI 论文；2026.03 参加 ACM-ICPC 区域赛",
  "long_term_plan": "保研至清华大学计算机系医疗 AI 方向",
  "study_plan_table": [
    {"stage": "短期", "time": "2025.09~2026.01", "content": "补修《C++》《数据结构》共 8 学分", "target": "GPA≥3.8"},
    {"stage": "中期", "time": "2026.02~2027.06", "content": "加入李XX 课题组 + ACM-ICPC 区域赛", "target": "SCI 论文 1 篇 + 铜牌"},
    {"stage": "长期", "time": "2027.07~2028.06", "content": "保研清华计算机系医疗 AI 方向", "target": "获保研资格 + 入读清华"}
  ]
}
```

### 11.5 学业优势型 data.json 关键差异字段

```json
{
  "transfer_reason_type": "academic",
  "academic_cross": "高等数学（上）95 分、线性代数 94 分、C 程序设计 96 分（专业第一），为转入计算机科学后的算法学习奠定扎实数学基础",
  "academic_competitions": [
    {"name": "全国大学生数学建模竞赛", "award": "省级二等奖", "time": "2025.04", "role": "队长，负责建模与编程"}
  ],
  "academic_research": "2024.11 起跟随数学学院 X 教授参与机器学习项目 3 个月，独立完成数据预处理模块"
}
```

### 11.6 职业规划型 data.json 关键差异字段

```json
{
  "transfer_reason_type": "career",
  "career_target": "医疗 AI 算法工程师",
  "career_internship": "2025.01~2025.04 在 XX 医院信息科实习 3 个月，参与肺结节 CT 影像辅助诊断项目，独立完成数据预处理模块（处理 1200 例 CT 数据）",
  "career_interview": "访谈 3 位医疗 AI 行业从业者",
  "career_research": "医疗 AI 行业人才缺口约 30 万人"
}
```

---

