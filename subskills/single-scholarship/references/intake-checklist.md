# 三、信息采集清单

> 从 `subskills/single-scholarship/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要逐条向用户提问采集信息时。

### 3.1 通用必采（10 字段）

| 字段 | 说明 | 示例 | 缺失追问 |
|------|------|------|----------|
| name | 申请人姓名 | 张三 | "全名？" |
| student_id | 学号 | 2022123456 | "学号？" |
| gender | 性别 | 男/女 | "性别？" |
| college | 学院全称 | 计算机学院 | "学院全称？" |
| major | 专业全称 | 计算机科学与技术 | "专业？" |
| grade | 入学年份+年级 | 2022 级 大三 | "年级？" |
| class_name | 班级 | 计科 2201 | "班级？" |
| political_status | 政治面貌 | 共青团员 | "政治面貌？" |
| phone | 联系电话 | 138XXXXXXXX | "电话？" |
| apply_year | 申报学年 | 2024-2025 学年 | "申报学年？" |

### 3.2 子方向判定字段

| 字段 | 类型 | 取值 | 说明 |
|------|------|------|------|
| category | string | research/social_work/art_sport/progress | 子方向代码 |
| apply_date | string | 2025 年 6 月 15 日 | 申请日期 |

子方向自动判定逻辑：有 papers/patents/innovations → research；有 position + organized_activities/volunteer_hours → social_work；有 art_sport_awards → art_sport；有 gpa_improvement 或 rank_improvement → progress。用户未指定 category 但提供多项 → 优先按用户主述方向。

### 3.3 科研单项专属字段（category=research）

| 字段 | 说明 | 示例 |
|------|------|------|
| papers | 论文列表 | [{title, journal, level, author_order, time}] |
| patents | 专利列表 | [{name, type, application_no, status, inventor_order}] |
| innovations | 大创/科研立项 | [{name, level, role, duration, output}] |
| research_summary | 科研经历小结（80~150 字） | "研究方向为 NLP，已发表 SCI 论文 1 篇..." |
| advisor | 指导教师 | {name, title, research_field} |
| gpa | 本学年 GPA | 3.65/4.0 |
| rank | 专业排名 | 10/87 |

论文要素：题目/期刊/级别（SCI/EI/中文核心/省级）+作者排序（第一/第二/通讯）+录用或见刊时间。
专利要素：名称/类型（发明/实用新型）+申请号或授权号+状态（已授权/实质审查/受理）+发明人排序。
大创要素：项目名/级别（国家级/省级/校级）+角色（主持/参与）+起止时间+产出。

### 3.4 社工单项专属字段（category=social_work）

| 字段 | 说明 | 示例 |
|------|------|------|
| position | 学生干部职务（含任期） | 学院学生会主席（2024.09-2025.06） |
| position_work | 履职数据 | "组织迎新晚会等大型活动 8 场，累计参与 2000+ 人次" |
| organized_activities | 组织活动列表 | [{name, time, scale, role}] |
| volunteer_hours | 志愿服务总时长（小时） | 120 |
| volunteer_detail | 志愿服务详情 | "三下乡 2 次、社区支教 4 次、马拉松志愿者 1 次" |
| service_beneficiaries | 服务受益人数 | 2000+ |
| social_honors | 社会工作荣誉 | "2024 年度校级优秀学生干部" |
| gpa | 本学年 GPA | 3.65/4.0 |
| rank | 专业排名 | 10/87 |

履职数据必含：活动名称+时间+规模+本人角色；志愿服务必含：项目名+时长+服务对象。

### 3.5 文体单项专属字段（category=art_sport）

| 字段 | 说明 | 示例 |
|------|------|------|
| art_sport_awards | 获奖/作品列表 | [{name, level, time, role, work_name}] |
| art_sport_type | 类型 | 文艺/体育/才艺 |
| art_sport_duration | 训练年限 | "钢琴学习 12 年、大学 3 年" |
| art_sport_works | 作品/参赛经历 | [{work, occasion, time, result}] |
| team_role | 在队伍中的角色 | "校合唱团声部长" |
| art_sport_summary | 经历小结（80~150 字） | "自幼学习钢琴，大学加入校合唱团..." |
| gpa | 本学年 GPA | 3.65/4.0 |
| rank | 专业排名 | 10/87 |

获奖要素：竞赛/展演全称+级别（国际/国家/省/校/院）+时间+角色（独奏/合奏/队长/主力）+作品名。

### 3.6 学习进步单项专属字段（category=progress）

| 字段 | 说明 | 示例 |
|------|------|------|
| gpa_before | 上一学年 GPA | 2.8/4.0 |
| gpa_after | 本学年 GPA | 3.6/4.0 |
| gpa_improvement | GPA 提升幅度 | 0.8 |
| rank_before | 上一学年排名 | 60/87 |
| rank_after | 本学年排名 | 15/87 |
| rank_improvement | 排名提升位数 | 45 |
| weighted_before | 上一学年加权 | 78.5 |
| weighted_after | 本学年加权 | 87.2 |
| improvement_method | 进步方法（80~150 字） | "调整学习方法，建立错题本..." |
| progress_courses | 进步课程对比 | [{name, before, after}] |

GPA 提升幅度计算：gpa_after - gpa_before；排名提升计算：rank_before - rank_after；进步方法必含具体策略，不空谈。

### 3.7 其他方面字段（通用，简略）

| 字段 | 说明 | 示例 |
|------|------|------|
| party_history | 入团/入团情况 | "2023.09 提交申请材料" |
| party_activities | 党团活动 | ["参加分党校第 8 期培训结业"] |
| lifestyle | 生活简略 | "生活中勤俭节约，作息规律" |
| interpersonal | 人际关系 | "与同学相处融洽" |
| honors | 其他荣誉（非该方向） | [] |
| cet4 | CET-4 成绩 | 510 |
| cet6 | CET-6 成绩 | 480 |
| dorm_role | 宿舍职务 | 宿舍长 |
| dorm_honor | 宿舍荣誉 | "文明宿舍" |

### 3.8 字段优先级

- P0（必采）：name/college/major/grade/category/apply_year/apply_date
- P1（核心）：3.3~3.6 各方向专属字段
- P2（简略）：3.7 其他方面字段

### 3.9 追问话术与复述确认

- 论文级别追问："是 SCI 还是 EI？第几作者？"
- 学生干部追问："具体担任什么职务？任期？组织过哪些活动？规模？"
- 文体获奖追问："是省级还是校级？独奏还是合奏？"
- GPA 进步追问："上学年 GPA 多少？本学年呢？排名变化？"
- 信息采完按书信体结构复述确认后再进入撰写

### 3.10 信息采集示例对话

用户："我想申请科研单项奖学金。"
追问 1："以第几作者发表了哪些论文？期刊级别？录用还是见刊？"
追问 2："有没有申请专利？发明专利还是实用新型？发明人排序？"
追问 3："有没有主持或参与大创项目？国家级/省级/校级？"
追问 4："指导教师是谁？研究方向是什么？"
追问 5："本学年 GPA 与专业排名？是否挂科？"

复述："根据您提供的信息，您将以第一作者 SCI 论文 1 篇 + 发明专利 1 项 + 国家级大创主持申请科研单项奖学金，确认无误后开始撰写。"

---

