# 三、信息采集清单

> 从 `subskills/outstanding-student/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要逐条向用户提问采集信息时。

按字段优先级 P0/P1/P2 标注。P0 必采，缺失则警告；P1 建议采，缺失则降低文档质量；P2 可选，提供则增强文档。

### 3.1 通用必采（P0）

| 字段 | 说明 | 示例 |
|------|------|------|
| category | 评优类别 | outstanding_student / outstanding_youth_league |
| name | 真实姓名 | 张明 |
| gender | 性别 | 男 / 女 |
| student_id | 完整学号 | 2022123456 |
| college | 学院全称 | 计算机科学与技术学院 |
| major | 专业全称 | 计算机科学与技术 |
| grade | 入学年份+年级 | 2022 级 大三 |
| class_name | 班级 | 计科 2201 班 |
| political_status | 政治面貌（优秀团员必须共青团员） | 中共党员/中共预备党员/优秀团员/积极分子/共青团员/群众 |
| phone | 联系电话 | 138XXXXXXXX |
| apply_year | 申报学年 | 2024-2025 学年 |
| apply_date | 申请日期 | 2025 年 5 月 20 日 |
| salutation | 称呼（可默认） | 尊敬的学院领导、评审委员会： |

### 3.2 本学年学业信息（P0）

| 字段 | 说明 | 示例 |
|------|------|------|
| gpa | 本学年 GPA（满分制需标注） | 3.88/4.0 |
| weighted_avg | 本学年加权平均分 | 90.2 |
| rank | 专业排名（带基数） | 2/87 |
| rank_total | 排名基数（rank 已含基数可省） | 87 |
| course_count | 本学年修读课程数 | 12 |
| high_score_count | 85 分以上课程数 | 9 |
| core_courses | 主干课程表（5~8 门，含 name/credit/score） | [{"name":"数据结构","credit":"4","score":"93"}] |
| course_highlight | 课程亮点（高分课程汇总） | 数据结构 93、操作系统 92，专业核心课平均 91.5 |
| cet4 | 大学英语四级分数 | 568 |
| cet6 | 大学英语六级分数（无则空） | 532 |
| computer_level | 计算机等级 | 二级 C 语言（优秀）、三级数据库技术 |
| study_method | 学习方法（默认值可接受） | 注重课前预习与课后总结... |

### 3.3 思想政治信息（P0）

| 字段 | 说明 | 优秀学生 | 优秀团员 |
|------|------|---------|---------|
| party_history | 入团/入团轨迹 | 2023.09 递交申请材料... | 2019.05 入团，2024.09 转入大学团支部 |
| party_activities | 党日活动/团日活动列表 | 党日活动/阶段汇报 | 团日活动/智慧团建 |

### 3.4 优秀团员专属字段（P0，仅当 category=outstanding_youth_league）

| 字段 | 说明 | 示例 |
|------|------|------|
| league_role | 团内职务 | 团支部书记/组织委员/宣传委员 |
| league_activities | 本学年参与团日活动列表 | 2024.10 团日主题教育活动 |
| league_work_detail | 团务工作详情 | 组织主题团日活动 6 场，覆盖团员 240 人次 |
| league_work | 团务工作整段（提供则直接用） | 自定义文本 |

### 3.5 科研实践信息（P1）

| 字段 | 说明 | 示例 |
|------|------|------|
| research_projects | 大创/科研立项（含 name/level/role/duration/output） | 校级大创主持 |
| papers | 论文（含 title/journal/level/author_order/time） | 中文核心第一作者 |
| competitions | 学科竞赛（含 time/name/award/role） | 数学建模省级一等奖 |
| volunteer_hours | 志愿服务时长（小时） | 80 |
| volunteer_detail | 志愿服务详情 | 图书馆管理员/班级帮扶 |
| sanxiaxiang | 三下乡（含 time/place/role/output） | 2024.07 赴甘肃定西电商助农 |

### 3.6 学生工作信息（P0 优秀学生 / P1 优秀团员）

| 字段 | 说明 | 示例 |
|------|------|------|
| position | 学生干部职务（含任期） | 学院学生会主席（2024.09-2025.05） |
| position_work | 主要工作概述 | 组织大型活动 8 场，累计参与 2000+ 人次 |
| position_history | 学生干部履职表（含 role/term/work/effect） | 见示例 |
| student_work | 学生工作整段（提供则直接用） | 自定义文本 |

### 3.7 生活信息（P2）

| 字段 | 说明 | 示例 |
|------|------|------|
| dorm_role | 宿舍职务 | 宿舍长 |
| dorm_activity | 宿舍活动 | 组织宿舍 6 次集体活动 |
| dorm_honor | 宿舍荣誉 | 宿舍连续两学期获评文明宿舍 |
| interpersonal | 人际关系 | 与同学相处融洽，曾帮助室友完成实验调试 |
| lifestyle | 生活作风 | 生活中我注重勤俭节约，作息规律 |

### 3.8 荣誉信息（P1）

| 字段 | 说明 | 示例 |
|------|------|------|
| honors | 荣誉列表（含 time/name/level/issuer，按时间倒序） | 2024.11 校级一等奖学金（专业前 5%） |

### 3.9 整段覆盖字段（P2）

| 字段 | 说明 |
|------|------|
| opening / ideology / academics / research_practice / student_work / life / ending | 提供则直接使用，跳过模板拼装 |

**追问话术**：缺 GPA 时追问"本学年 GPA 是多少？满分是 4.0 还是 5.0？专业排名是多少？请按 X/N 格式提供"。缺学生干部履职时追问"担任什么职务？任期多长？具体做了哪些工作？取得了什么可量化成效？"。缺团务工作时追问"团内职务是？组织过哪些团日活动？覆盖多少团员？"。

**复述确认**：信息采集结束后，必须向用户复述"本学年 GPA X.XX/4.0，专业排名 X/N，担任 YYY 职务组织 Z 场活动服务 W 人次，志愿服务 V 小时"，确认无误后再进入撰写阶段。

---

