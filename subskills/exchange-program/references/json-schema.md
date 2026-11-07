# §12 JSON Schema 完整字段（必加章节 7）

> 从 `subskills/exchange-program/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：构造 --data 输入文件、或 build.py 报字段校验错误时。

### 12.1 顶层字段总览

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ExchangeProgramApplication",
  "description": "交流项目申请书数据结构",
  "type": "object",
  "required": ["name", "current_college", "current_major", "grade", "target_university", "exchange_type", "exchange_duration", "current_gpa", "current_rank", "language_score", "target_courses", "target_teachers"],
  "properties": {
    "exchange_type": {
      "type": "string",
      "enum": ["school", "college", "csc"],
      "description": "交流项目类型：school（校际交换）/ college（院际交换）/ csc（CSC 公派）"
    },
    "target_university": {
      "type": "string",
      "description": "目标院校全称"
    },
    "exchange_duration": {
      "type": "string",
      "description": "交流时长（学期/学年 + 起止时间）"
    },
    "learning_plan": {
      "type": "object",
      "description": "学习计划（3 阶段）",
      "properties": {
        "prep_plan": {"type": "string"},
        "abroad_plan": {"type": "string"},
        "return_plan": {"type": "string"}
      }
    },
    "motivation": {
      "type": "string",
      "description": "交流动机整段（提供则直接使用，跳过模板拼装）"
    },
    "cultural_exchange": {
      "type": "string",
      "description": "文化交流意愿整段（提供则直接使用，跳过模板拼装）"
    },
    "safety_commitment": {
      "type": "string",
      "description": "安全保障整段（提供则直接使用，跳过模板拼装）"
    }
  }
}
```

### 12.2 完整字段清单（按 P0/P1/P2 分级）

#### P0 必填字段（15 项）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | ✅ | 真实姓名 |
| gender | string | ✅ | 男 / 女 |
| student_id | string | ✅ | 完整学号 |
| current_college | string | ✅ | 现学院全称 |
| current_major | string | ✅ | 现专业全称 |
| grade | string | ✅ | 入学年份 + 年级 |
| target_university | string | ✅ | 目标院校全称 |
| target_country | string | ✅ | 目标国家/地区 |
| target_qs_rank | string | ✅ | 目标院校 QS 排名（含年份） |
| exchange_type | string | ✅ | school / college / csc |
| exchange_duration | string | ✅ | 交流时长（学期/学年 + 起止时间） |
| current_gpa | string | ✅ | 现专业 GPA（含满分制） |
| current_rank | string | ✅ | 现专业排名（X/N 格式） |
| language_score | string | ✅ | 语言成绩（含取得时间 + 有效期） |
| target_courses | array | ✅ | 目标院校核心课程（≥5 门） |
| target_teachers | array | ✅ | 目标院校导师（≥2 位） |

#### P1 建议字段（动机与学习计划）

| 字段 | 类型 | 说明 |
|------|------|------|
| motivation_academic | string | 学术深化动机 |
| motivation_vision | string | 视野拓展动机 |
| motivation_language | string | 语言提升动机 |
| motivation_career | string | 职业规划动机 |
| target_labs | string | 目标院校实验室/学术资源 |
| prep_plan | string | 行前准备计划（4 要素） |
| abroad_plan | string | 在外学习计划（4 要素） |
| return_plan | string | 归国总结计划（3 要素） |
| weekly_schedule | string | 每周时间分配 |
| study_plan_table | array | 学习计划表（含 stage/time/content/target） |

#### P1 建议字段（文化交流与安全保障）

| 字段 | 类型 | 说明 |
|------|------|------|
| cultural_integration | string | 文化融入计划 |
| cultural_promotion | string | 中华文化传播计划 |
| academic_exchange | string | 学术交流计划 |
| safety_legal | string | 法律遵守承诺 |
| safety_insurance | string | 保险购买承诺 |
| safety_report | string | 定期汇报承诺 |
| safety_emergency | string | 紧急预案 |

#### P1 建议字段（学业背景）

| 字段 | 类型 | 说明 |
|------|------|------|
| current_weighted_avg | string | 现专业加权平均分 |
| current_rank_total | string | 排名基数 |
| current_course_count | number | 现专业已修课程数 |
| current_high_score_count | number | 85 分以上课程数 |
| current_core_courses | array | 现专业主干课程表（4~6 门） |
| language_breakdown | string | 语言分项成绩 |
| research_experience | string | 已有科研经历 |
| competition_experience | string | 已有竞赛经历 |

#### P1 建议字段（入学背景）

| 字段 | 类型 | 说明 |
|------|------|------|
| gaokao_year | string | 高考年份 |
| gaokao_score | string | 高考总分 + 省份 |
| admission_mode | string | 录取方式 |

#### P2 可选字段（整段覆盖）

| 字段 | 类型 | 说明 |
|------|------|------|
| word_count_target | string | 字数档位（short/standard/long） |
| opening | string | 开头整段覆盖 |
| basic_info | string | 个人基本情况整段覆盖 |
| motivation | string | 交流动机整段覆盖 |
| learning_plan | string | 学习计划整段覆盖 |
| cultural_exchange | string | 文化交流意愿整段覆盖 |
| safety | string | 安全保障整段覆盖 |
| ending | string | 结尾整段覆盖 |
| salutation | string | 称呼（默认"尊敬的评审委员会："） |

### 12.3 数组字段子结构

**current_core_courses 子结构**：
```json
{
  "name": "数据结构",
  "credit": "4",
  "score": "94"
}
```

**target_courses 子结构**：
```json
{
  "name": "Machine Learning",
  "credit": "4",
  "teacher": "Alexei Efros",
  "semester": "2025 Fall"
}
```

**target_teachers 子结构**：
```json
{
  "name": "Alexei Efros",
  "title": "教授",
  "research": "计算机视觉",
  "achievement": "ACM Fellow，近 3 年 CVPR/ICCV 论文 25 篇"
}
```

**study_plan_table 子结构**：
```json
{
  "stage": "行前准备",
  "time": "2025.07~09",
  "content": "雅思冲刺 + 文化预习 + 课程预选 + 学分认定",
  "target": "雅思 7.0 + 5 门预选 + 12 学分认定"
}
```

### 12.4 完整 data.json 示例（校际交换，2000 字版）

```json
{
  "name": "张明", "student_id": "2023123456", "gender": "男",
  "current_college": "计算机科学与技术学院", "current_major": "计算机科学与技术",
  "grade": "2023 级 大二", "class_name": "计科 2301 班",
  "target_university": "伦敦大学学院（UCL）", "target_country": "英国",
  "target_qs_rank": "2025 年 QS 全球第 9，计算机科学学科全球第 8",
  "exchange_type": "school", "exchange_duration": "1 学年（2025.09~2026.06）",
  "phone": "138XXXXXXXX", "email": "zhangming@xxx.edu.cn",
  "apply_date": "2025 年 3 月 15 日",
  "salutation": "尊敬的评审委员会：",
  "current_gpa": "3.85/4.0", "current_weighted_avg": "88.5",
  "current_rank": "5/120", "current_rank_total": "120",
  "current_course_count": "18", "current_high_score_count": "14",
  "current_core_courses": [
    {"name": "数据结构", "credit": "4", "score": "94"},
    {"name": "算法分析与设计", "credit": "4", "score": "92"},
    {"name": "操作系统", "credit": "4", "score": "90"},
    {"name": "计算机网络", "credit": "3", "score": "88"},
    {"name": "机器学习", "credit": "3", "score": "95"}
  ],
  "language_score": "雅思 6.5（2024.09 取得，有效期至 2026.09）",
  "language_breakdown": "听力 7.0 / 阅读 7.0 / 写作 6.0 / 口语 5.5",
  "motivation_academic": "UCL 计算机科学专业在 2025 年 QS 学科排名全球第 8，其开设的《Machine Learning》（4 学分）由 Alexei Efros 教授（ACM Fellow，研究方向为计算机视觉）主讲，团队近 3 年在 CVPR、ICCV 发表论文 25 篇。同时拥有 Gatsby Computational Neuroscience Unit 等顶级实验室，定期举办 ICML、NeurIPS 等顶级会议讲座。",
  "motivation_vision": "UCL 每年 3 月举办 International Week 跨文化交流活动，吸引来自 150 多个国家的学生参与。我计划参与该活动，与来自不同文化背景的学生组成 5 人小组共同完成跨文化主题项目。此外，我计划加入 UCL Chinese Society，在传播中华文化的同时，深入了解英国本土文化。",
  "motivation_language": "当前雅思总分 6.5（2024.09 取得，有效期至 2026.09）。通过交流，我目标将雅思总分提升至 7.0 以上，其中口语提升至 6.5。具体方式包括：参与 UCL Language Centre 学术英语课程（2 小时/周），加入 UCL English Speaking Union 每周练习口语（3 小时/周），与当地学生组成语言交换伙伴（每周 2 次）。",
  "motivation_career": "我的长期职业目标是成为跨国科技公司（如 Google、Microsoft）的算法工程师。UCL 计算机视觉方向全球领先，导师 Alexei Efros 教授的团队近 3 年在 CVPR、ICCV 发表论文 25 篇。通过交流学习与参与团队研究，我将积累前沿学术经历，为未来申请海外博士项目（目标：斯坦福、CMU）奠定基础。归国后，我计划将交流经历转化为科研论文（目标 1 篇 CVPR/ICCV），并申请清华或北大直博项目。",
  "target_courses": [
    {"name": "Machine Learning", "credit": "4", "teacher": "Alexei Efros", "semester": "2025 Fall"},
    {"name": "Computer Vision", "credit": "4", "teacher": "John S.", "semester": "2025 Fall"},
    {"name": "Academic English", "credit": "2", "teacher": "Sarah M.", "semester": "2025 Fall"},
    {"name": "Deep Learning", "credit": "4", "teacher": "Yann L.", "semester": "2026 Spring"},
    {"name": "British Culture", "credit": "2", "teacher": "David W.", "semester": "2026 Spring"}
  ],
  "target_teachers": [
    {"name": "Alexei Efros", "title": "教授", "research": "计算机视觉", "achievement": "ACM Fellow，近 3 年 CVPR/ICCV 论文 25 篇"},
    {"name": "John S.", "title": "副教授", "research": "机器学习与推荐系统", "achievement": "近 3 年 NeurIPS/ICML 论文 12 篇"}
  ],
  "target_labs": "Gatsby Computational Neuroscience Unit",
  "prep_plan": "行前准备阶段（2025.07~2025.09，3 个月）：①语言强化：参加新东方雅思冲刺班（80 课时，2025.07~08），目标雅思 7.0；②文化预习：阅读《英国文化简史》《UCL 校史》《British Academic Culture》3 本书；③课程预选：已与 UCL International Office 沟通，预选 5 门课程共 16 学分；④学分认定：已与本校教务处沟通，5 门课程可转换为 12 学分。",
  "abroad_plan": "在外学习阶段（2025.09~2026.06，2 学期）：第 1 学期修读《Machine Learning》《Computer Vision》《Academic English》共 10 学分；第 2 学期修读《Deep Learning》《British Culture》+ 参与 Alexei Efros 教授课题组研究项目（4 学分研究实习），共 10 学分。每周时间分配：授课 16h、自习 20h、课题组 8h、讲座 4h、跨文化 6h。学术活动：参加 UCL CS 每周研讨会（约 30 场/学期）+ Gatsby Unit 每月开放日。阶段性产出：第 1 学期 1 篇课程论文，第 2 学期目标以第二作者发表 1 篇 CVPR Workshop 论文。",
  "return_plan": "归国总结阶段（2026.07~2026.09，2 个月）：①学分转换：5 门 UCL 课程共 16 学分已确认为本校 12 学分（含 8 学分专业核心课 + 4 学分专业选修课），不影响毕业；②经验分享：拟在本校举办 2 场交流分享会，并在国际处网站发布 1 篇交流心得；③后续学业衔接：基于交流期间积累的计算机视觉研究经历，归国后申请加入本校人工智能研究院李教授课题组，目标 2026.12 前完成 CVPR 论文投稿，并申请清华或北大直博项目。",
  "weekly_schedule": "授课 16h + 自习 20h + 课题组 8h + 讲座 4h + 跨文化 6h",
  "study_plan_table": [
    {"stage": "行前准备", "time": "2025.07~09", "content": "雅思冲刺 + 文化预习 + 课程预选 + 学分认定", "target": "雅思 7.0 + 5 门预选课程 + 12 学分认定"},
    {"stage": "在外学习", "time": "2025.09~2026.06", "content": "5 门课程 + 课题组研究 + 学术讲座", "target": "16 学分 + CVPR Workshop 论文 1 篇"},
    {"stage": "归国总结", "time": "2026.07~09", "content": "学分转换 + 经验分享 + 加入本校课题组", "target": "12 学分转换 + 2 场分享会 + 加入李教授课题组"}
  ],
  "cultural_integration": "参与 UCL International Week 与 150 多个国家学生组成 5 人小组完成跨文化项目；申请家庭寄宿（Homestay）3 个月，深入体验英国家庭生活。",
  "cultural_promotion": "加入 UCL Chinese Society，参与组织 2026 年春节文化展示活动（含书法、茶艺、汉服展示）；在学联组织的中秋节、端午节活动中担任志愿者。",
  "academic_exchange": "参加 UCL CS 每周研讨会（约 30 场/学期）；与其他交换生组成学习小组每周交流 1 次；学期末举办 1 场面向本校师生的线上分享会。",
  "safety_legal": "严格遵守英国法律与 UCL 校规，不参与任何非法活动，按时完成学业任务，尊重英国当地风俗习惯与文化传统，维护中国留学生良好形象。",
  "safety_insurance": "已购买中国平安'留学无忧'海外保险，含医疗费用（保额 50 万元人民币）、意外伤害（保额 30 万元人民币）、紧急救援（保额 100 万元人民币），保险期限覆盖 2025.09~2026.06 整个交流期。",
  "safety_report": "每月 5 日前向本校国际处提交上月学习进度报告；紧急情况 24 小时内电话汇报；每学期末提交交流总结报告；与本校导师保持每两周 1 次的视频沟通。",
  "safety_emergency": "国内紧急联系人：父亲 XX，电话 138XXXXXXXX；国外紧急联系人：UCL International Office，电话 +44-20-7679-2000；中国驻英使馆：+44-20-7299-4049；英国报警急救：999；应对流程：先报警 → 再联系使馆 → 再通知家人 → 最后通知本校。",
  "gaokao_year": "2023 年", "gaokao_score": "632 分（山东）",
  "admission_mode": "普通批次",
  "research_experience": "2024.09~2025.03 跟随本校李教授参与医疗影像 AI 项目 6 个月，独立完成数据预处理模块，处理 1200 例 CT 数据。",
  "competition_experience": "2024.11 全国大学生数学建模竞赛省级二等奖（队长，负责建模与编程）；2025.04 中国大学生计算机设计大赛省级一等奖。"
}
```

### 12.5 CSC 公派型 data.json 关键差异字段

```json
{
  "exchange_type": "csc",
  "exchange_duration": "1 学年（CSC 公派联合培养，2025.09~2026.06）",
  "safety_report": "每月 5 日前向本校国际处与 CSC 留学服务中心提交学习进度报告；紧急情况 24 小时内电话汇报；每学期末提交交流总结报告；归国前 1 个月向 CSC 提交回国服务承诺书；履行 CSC 协议回国服务 2 年义务。"
}
```

### 12.6 院际交换型 data.json 关键差异字段

```json
{
  "exchange_type": "college",
  "exchange_duration": "1 学期（院际交换，2025.09~2026.01）",
  "target_university": "京都大学（工学部信息学科）",
  "target_country": "日本",
  "target_qs_rank": "2025 年 QS 全球第 50"
}
```

---

