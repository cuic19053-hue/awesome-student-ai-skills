# §6 信息采集清单

> 从 `subskills/outstanding-cadre/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要逐条向用户提问采集信息时。

按字段优先级 P0/P1/P2 标注。P0 必采，缺失则警告；P1 建议采，缺失则降低文档质量；P2 可选，提供则增强文档。

### 6.1 通用必采（P0）

| 字段 | 说明 | 示例 |
|------|------|------|
| name | 申请人姓名 | 张明 |
| gender | 性别 | 男 |
| student_id | 学号 | 2022123456 |
| college | 学院全称 | 计算机科学与技术学院 |
| major | 专业全称 | 计算机科学与技术 |
| grade | 年级 | 2022 级 大三 |
| class_name | 班级 | 计科 2201 班 |
| political_status | 政治面貌 | 中共预备党员 |
| phone | 联系电话 | 138XXXXXXXX |
| apply_year | 申报学年 | 2024-2025 学年 |
| apply_date | 申请日期 | 2025 年 5 月 20 日 |
| honor_title | 评优标题全称 | 优秀班干部 |

### 6.2 学生干部职务（P0，优秀班干部专属必采）

| 字段 | 说明 | 示例 |
|------|------|------|
| cadre_position | 主要学生干部职务 | 班长 |
| cadre_level | 职务级别 | 班级正职 |
| tenure_start | 任期开始 | 2024.09 |
| tenure_end | 任期结束 | 2025.05 |
| position_level | 申报级别（校级/院级/班级） | 院级 |
| position_history | 学生干部履职表（≥1 条） | 见 §12.3 |

### 6.3 学业成绩（P0）

| 字段 | 说明 | 示例 |
|------|------|------|
| gpa | 本学年 GPA（含满分制） | 3.65/4.0 |
| weighted_avg | 本学年加权平均分 | 82.5 |
| rank | 专业排名（X/N 格式） | 30/87 |
| rank_total | 排名基数 | 87 |
| course_count | 本学年修读课程数 | 12 |
| high_score_count | 85 分以上课程数 | 5 |
| core_courses | 主干课程表（4~6 门） | 见 §12.3 |

### 6.4 履职量化清单（P0，必采）

| 字段 | 说明 | 示例 |
|------|------|------|
| duty_performances | 履职量化清单（4 维度） | 见 §12.3 |
| duty_performances.activity_count | 活动数 | "主题班会 12 次、班级活动 6 场，共 18 场" |
| duty_performances.service_hours | 服务时长 | "累计 280 小时（日常履职 200h、活动组织 80h）" |
| duty_performances.awards | 获奖情况 | "校级优秀学生干部（2024.11）" |
| duty_performances.peer_review | 同学评议 | "满意度 92%（46/50 人评议）" |

### 6.5 服务同学案例与工作成绩（P1，建议采）

| 字段 | 说明 | 示例 |
|------|------|------|
| service_cases | 服务同学案例列表（2-3 个，含 background/action/effect） | 见 §12.3 |
| class_achievements | 班级整体成效 | "班级加权平均分由 84.2 提升至 87.6" |
| honors | 个人荣誉列表（含 time/name/level/issuer） | 见 §12.3 |
| cross_position | 跨职务统筹成效 | "在班长与团支书双重职务中..." |

### 6.6 思想政治与综合表现（P1）

| 字段 | 说明 | 示例 |
|------|------|------|
| party_history | 入团/入团轨迹 | 2023.09 提交申请材料，2025.06 转为中共预备党员 |
| party_activities | 党日活动/团日活动 | ["2024.10 主题党日活动"] |
| volunteer_hours | 志愿服务时长 | 80 |
| volunteer_detail | 志愿服务详情 | "担任图书馆管理员..." |

### 6.7 不足与改进（P0，必采）

| 字段 | 说明 | 示例 |
|------|------|------|
| shortcomings | 不足列表（1-2 条） | ["班级少数同学学业帮扶成效不显著"] |
| improvements | 改进措施列表 | ["下学年建立'一对一'长期帮扶机制"] |

### 6.8 整段覆盖字段（P2，可选）

| 字段 | 说明 |
|------|------|
| opening | 开头整段覆盖 |
| basic_info | 个人基本情况整段覆盖 |
| duty_performance | 履职情况整段覆盖 |
| work_achievements | 工作成绩整段覆盖 |
| shortcomings_section | 不足与改进整段覆盖 |
| ending | 结尾整段覆盖 |
| salutation | 称呼（默认"尊敬的学院领导、评审委员会："） |

### 6.9 信息采集复述确认

**复述确认**：信息采集结束后，必须向用户复述"本学年 GPA X.XX/4.0，专业排名 X/N，担任 YYY 职务（Z 级，2024.09-2025.05），组织活动 W 场、服务时长 V 小时、同学评议满意度 U%，获评 S 项荣誉"，确认无误后再进入撰写阶段。

---

