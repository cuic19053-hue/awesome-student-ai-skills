# §12 JSON Schema 完整字段（必加章节 7）

> 从 `subskills/outstanding-cadre/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：构造 --data 输入文件、或 build.py 报字段校验错误时。

### 12.1 顶层字段总览

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "OutstandingCadreApplication",
  "description": "优秀班干部 / 优秀学生干部申请书数据结构",
  "type": "object",
  "required": ["honor_title", "name", "college", "major", "grade", "cadre_position", "tenure_start", "tenure_end", "gpa", "rank", "duty_performances", "position_history"],
  "properties": {
    "honor_title": {
      "type": "string",
      "enum": ["优秀班干部", "优秀学生干部", "优秀班委", "校级优秀学生干部", "院级优秀学生干部"],
      "description": "评优标题全称，影响标题与正文措辞"
    },
    "cadre_position": {
      "type": "string",
      "description": "主要学生干部职务（如：班长、团支书、学委、宣委、体委、心理委员、楼长）"
    },
    "tenure_start": {
      "type": "string",
      "description": "任期开始（YYYY.MM 格式）"
    },
    "tenure_end": {
      "type": "string",
      "description": "任期结束（YYYY.MM 格式）"
    },
    "duty_performances": {
      "type": "object",
      "description": "履职量化清单（4 维度）",
      "required": ["activity_count", "service_hours", "awards", "peer_review"],
      "properties": {
        "activity_count": {"type": "string"},
        "service_hours": {"type": "string"},
        "awards": {"type": "string"},
        "peer_review": {"type": "string"}
      }
    }
  }
}
```

### 12.2 完整字段清单（按 P0/P1/P2 分级）

#### P0 必填字段（13 项）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| honor_title | string | ✅ | 优秀班干部 / 优秀学生干部 / 优秀班委 |
| name | string | ✅ | 真实姓名 |
| gender | string | ✅ | 男 / 女 |
| student_id | string | ✅ | 完整学号 |
| college | string | ✅ | 学院全称 |
| major | string | ✅ | 专业全称 |
| grade | string | ✅ | 入学年份 + 年级 |
| class_name | string | ✅ | 班级 |
| cadre_position | string | ✅ | 主要学生干部职务 |
| tenure_start | string | ✅ | 任期开始（YYYY.MM） |
| tenure_end | string | ✅ | 任期结束（YYYY.MM） |
| gpa | string | ✅ | 本学年 GPA（含满分制） |
| rank | string | ✅ | 专业排名（X/N 格式） |

#### P0 必填字段（履职相关 3 项）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| position_history | array | ✅ | 学生干部履职表（≥1 条） |
| duty_performances | object | ✅ | 履职量化清单（4 维度） |
| shortcomings | array | ✅ | 不足列表（1-2 条） |
| improvements | array | ✅ | 改进措施列表 |

#### P1 建议字段（学业与思想）

| 字段 | 类型 | 说明 |
|------|------|------|
| cadre_level | string | 职务级别（班级正职/班级副职/院级正职等） |
| position_level | string | 申报级别（校级/院级/班级） |
| political_status | string | 政治面貌 |
| phone | string | 联系电话 |
| apply_year | string | 申报学年 |
| apply_date | string | 申请日期 |
| weighted_avg | string | 本学年加权平均分 |
| rank_total | string | 排名基数 |
| course_count | number | 本学年修读课程数 |
| high_score_count | number | 85 分以上课程数 |
| core_courses | array | 主干课程表（4~6 门） |
| party_history | string | 入团/入团轨迹 |
| party_activities | array | 党日活动 / 团日活动列表 |

#### P1 建议字段（服务同学与工作成绩）

| 字段 | 类型 | 说明 |
|------|------|------|
| service_cases | array | 服务同学案例列表（2-3 个） |
| class_achievements | string | 班级整体成效 |
| honors | array | 个人荣誉列表 |
| cross_position | string | 跨职务统筹成效 |
| secondary_position | string | 兼任职务（如有） |
| volunteer_hours | number | 志愿服务时长 |
| volunteer_detail | string | 志愿服务详情 |

#### P2 可选字段（整段覆盖）

| 字段 | 类型 | 说明 |
|------|------|------|
| word_count_target | string | 字数档位（short/standard/long） |
| opening | string | 开头整段覆盖 |
| basic_info | string | 个人基本情况整段覆盖 |
| duty_performance | string | 履职情况整段覆盖 |
| work_achievements | string | 工作成绩整段覆盖 |
| shortcomings_section | string | 不足与改进整段覆盖 |
| ending | string | 结尾整段覆盖 |
| salutation | string | 称呼（默认"尊敬的学院领导、评审委员会："） |

### 12.3 数组字段子结构

**core_courses 子结构**：
```json
{
  "name": "数据结构",
  "credit": "4",
  "score": "85"
}
```

**position_history 子结构**（学生干部履职表）：
```json
{
  "role": "班长",
  "term": "2024.09-2025.05（1 学年）",
  "work": "组织班级主题班会 12 次、班委例会 15 次、班级活动 6 场，转发学院通知 50 余条",
  "effect": "班级加权平均分由 84.2 提升至 87.6，所在班级获评 2024 年度校级先进班集体"
}
```

**duty_performances 子结构**（履职量化清单）：
```json
{
  "activity_count": "主题班会 12 次、班级活动 6 场、班委例会 15 次，共 33 场",
  "service_hours": "累计 320 小时（日常履职 240h、活动组织 80h）",
  "awards": "校级先进班集体（2025.05）、院级优秀学生干部（2024.11）",
  "peer_review": "满意度 94%（47/50 人评议）"
}
```

**service_cases 子结构**：
```json
{
  "background": "2024.11 班级 X 同学因家中变故情绪低落、期中考试 2 门不及格",
  "action": "组织班委集体帮扶 + 一对一谈心 3 次",
  "effect": "X 同学期末加权平均分提升 5 分、2 门课程补考通过"
}
```

**honors 子结构**：
```json
{
  "time": "2024.11",
  "name": "院级优秀学生干部",
  "level": "院级",
  "issuer": "XX 大学计算机学院"
}
```

**shortcomings 子结构**（字符串数组）：
```json
"班级少数同学（3-5 人）学业帮扶成效不显著，期末仍有 2 人挂科"
```

**improvements 子结构**（字符串数组）：
```json
"下学年建立'一对一'长期帮扶机制，覆盖全部学业困难同学（加权平均分 <75），每月跟踪 1 次、每学期评估 1 次"
```

### 12.4 完整 data.json 示例（优秀班干部，1500 字版）

```json
{
  "honor_title": "优秀班干部",
  "name": "张明", "student_id": "2022123456", "gender": "男",
  "college": "计算机科学与技术学院", "major": "计算机科学与技术",
  "grade": "2022 级 大三", "class_name": "计科 2201 班",
  "political_status": "中共预备党员", "phone": "138XXXXXXXX",
  "apply_year": "2024-2025 学年", "apply_date": "2025 年 5 月 20 日",
  "salutation": "尊敬的学院领导、评审委员会：",
  "cadre_position": "班长", "cadre_level": "班级正职",
  "position_level": "院级", "tenure_start": "2024.09", "tenure_end": "2025.05",
  "secondary_position": "团支部副书记",
  "gpa": "3.65/4.0", "weighted_avg": "82.5", "rank": "30/87", "rank_total": "87",
  "course_count": "12", "high_score_count": "5",
  "core_courses": [
    {"name": "数据结构", "credit": "4", "score": "85"},
    {"name": "操作系统", "credit": "4", "score": "82"},
    {"name": "计算机网络", "credit": "3", "score": "80"},
    {"name": "数据库原理", "credit": "3", "score": "84"},
    {"name": "计算机组成原理", "credit": "4", "score": "79"}
  ],
  "party_history": "2023.09 提交申请材料，2024.03 列为优秀团员/积极分子，2025.06 转为中共预备党员。",
  "party_activities": [
    "2024.10 主题党日活动'红色教育基地走访'",
    "2024.12 党史学习交流"
  ],
  "position_history": [
    {"role": "班长", "term": "2024.09-2025.05（1 学年）",
     "work": "组织班级主题班会 12 次、班委例会 15 次、班级活动 6 场，转发学院通知 50 余条",
     "effect": "班级加权平均分由 84.2 提升至 87.6，所在班级获评 2024 年度校级先进班集体"}
  ],
  "duty_performances": {
    "activity_count": "主题班会 12 次、班级活动 6 场、班委例会 15 次，共 33 场",
    "service_hours": "累计 320 小时（日常履职 240h、活动组织 80h）",
    "awards": "校级先进班集体（2025.05）、院级优秀学生干部（2024.11）",
    "peer_review": "满意度 94%（47/50 人评议）"
  },
  "service_cases": [
    {"background": "2024.11 班级 X 同学因家中变故情绪低落、期中考试 2 门不及格",
     "action": "组织班委集体帮扶 + 一对一谈心 3 次",
     "effect": "X 同学期末加权平均分提升 5 分、2 门课程补考通过"},
    {"background": "2025.03 班级 Y 同学出现轻度焦虑倾向",
     "action": "及时向辅导员与心理中心报告，组织宿舍长密切关注，陪同 Y 同学接受心理中心咨询 2 次",
     "effect": "Y 同学情绪逐步稳定"},
    {"background": "2024.12 宿舍 Z 与 W 因作息时间冲突产生矛盾",
     "action": "组织双方调解 2 次，制定宿舍作息公约",
     "effect": "矛盾化解"}
  ],
  "class_achievements": "班级加权平均分由 84.2 提升至 87.6（提升 3.4 分），班级挂科率由 8% 降至 2%（下降 6 个百分点），班级体测合格率 95%，班级获评 2024 年度校级先进班集体（2025.05）、校级文明班级（2025.04）。",
  "honors": [
    {"time": "2024.11", "name": "院级优秀学生干部", "level": "院级", "issuer": "XX 大学计算机学院"},
    {"time": "2025.05", "name": "校级优秀团员", "level": "校级", "issuer": "XX 大学团委"}
  ],
  "cross_position": "本学年同时担任班长与团支部副书记，统筹班级建设与团支部建设：在 2024.11 主题班会'民族团结一家亲'中联动团支部组织团员与非团员结对学习；在 2025.04 班级学习互助活动中联动团支部组织团员的'团员帮扶先锋'行动，所在班级与团支部均获评校级先进。",
  "shortcomings": [
    "班级少数同学（3-5 人）学业帮扶成效不显著，期末仍有 2 人挂科",
    "心理排查工作偏重于已知案例，对潜在危机的预防性排查不足"
  ],
  "improvements": [
    "下学年建立'一对一'长期帮扶机制，覆盖全部学业困难同学（加权平均分 <75），每月跟踪 1 次、每学期评估 1 次",
    "下学年开展全班心理排查 4 次（每学期 2 次），重点关注学业困难、经济困难、家庭变故 3 类同学，建立'心理重点关注名单'动态管理"
  ]
}
```

### 12.5 校级优秀学生干部 data.json 关键差异字段

```json
{
  "honor_title": "校级优秀学生干部",
  "cadre_position": "学院学生会主席",
  "cadre_level": "院级正职",
  "position_level": "校级",
  "tenure_start": "2024.09",
  "tenure_end": "2025.05"
}
```

---

