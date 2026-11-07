# §6 信息采集清单与 JSON Schema（必加章节 6）

> 从 `subskills/class-collective/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：构造 --data 输入文件、或 build.py 报字段校验错误时。

### 6.1 信息采集清单（21 项必填 + 8 项选填）

#### 6.1.1 班级基本信息（5 项必填）

| 字段 | 说明 | 示例 |
|------|------|------|
| class_name | 班级全称 | "计算机科学与技术 2023 级 1 班" |
| college | 学院全称 | "计算机学院" |
| major | 专业全称 | "计算机科学与技术" |
| class_size | 班级总人数 | 38 |
| collective_type | 申报类别 | advanced_class / good_study_class / may_fourth_flag / civilized_class |

#### 6.1.2 人员构成（4 项必填）

| 字段 | 说明 | 示例 |
|------|------|------|
| male_count | 男生人数 | 26 |
| female_count | 女生人数 | 12 |
| member_count | 团员人数 | 36 |
| party_member_count | 党员（含预备）人数 | 4 |

#### 6.1.3 班委建制（2 项必填）

| 字段 | 说明 | 示例 |
|------|------|------|
| class_committee | 班委列表（职务 + 姓名 + 任期） | [{"post":"班长","name":"张三","term":"2024.09-2025.06"},...] |
| head_teacher | 班主任 / 辅导员信息 | {"name":"李老师","title":"副教授","unit":"计算机学院软件工程系"} |

#### 6.1.4 5 维度量化数据（5 项必填）

| 字段 | 说明 | 示例 |
|------|------|------|
| ideology_score | 思想建设得分（含 5 子项） | {"party_ratio":5,"member_ratio":3,"youth_study":4,"theme_meeting":4,"ideology_grade":4,"total":18,"max":20} |
| study_score | 学习建设得分（含 5 子项） | {"gpa":6,"top10":5,"pass_rate":4,"competition":4,"cet":3,"total":22,"max":25} |
| activity_score | 活动建设得分（含 5 子项） | {"collective_activity":4,"school_participation":3,"volunteer":3,"culture_award":4,"social_practice":3,"total":17,"max":20} |
| discipline_score | 纪律建设得分（含 5 子项） | {"attendance":5,"late":3,"violation":5,"cheating":4,"network":2,"total":18,"max":20} |
| hygiene_score | 卫生建设得分（含 4 子项） | {"excellent_rate":5,"civilized_dormitory":3,"pass_rate":3,"safety":2,"total":13,"max":15} |

#### 6.1.5 班级核心数据（5 项必填）

| 字段 | 说明 | 示例 |
|------|------|------|
| avg_gpa | 班级平均学分绩点 | 3.42 |
| pass_rate | 课程及格率（百分比） | 98.5 |
| competition_awards | 学科竞赛获奖（按级别） | {"national":3,"provincial":5,"school":12} |
| cet4_pass_rate | 英语四级通过率 | 88.5 |
| cet6_pass_rate | 英语六级通过率 | 65.8 |

#### 6.1.6 6 段正文（6 项必填）

| 字段 | 说明 | 示例 |
|------|------|------|
| overview_text | §1 班级概况正文 | （300~500 字） |
| ideology_text | §2 思想建设正文 | （500~900 字） |
| study_text | §3 学风建设正文 | （600~1000 字） |
| activity_text | §4 班级活动正文 | （500~900 字） |
| honor_text | §5 班级荣誉正文 | （300~500 字） |
| outlook_text | §6 工作展望正文 | （300~500 字） |

#### 6.1.7 班级荣誉（选填 3 项）

| 字段 | 说明 | 示例 |
|------|------|------|
| collective_honors | 集体荣誉清单 | [{"year":"2024","name":"校级先进班集体","level":"校级"}] |
| personal_honors_summary | 个人荣誉汇总 | {"national":3,"provincial":5,"school":18,"total_count":26} |
| signature_dates | 签字日期 | {"class_monitor":"2025-05-20","head_teacher":"2025-05-21","college":"2025-05-22"} |

#### 6.1.8 字数版本与格式（选填 5 项）

| 字段 | 说明 | 示例 |
|------|------|------|
| word_count_version | 字数版本 | 3000 / 4000 / 5000（默认 4000） |
| class_slogan | 班级口号 / 班训 | "团结奋进，求实创新" |
| target_honor | 申报目标荣誉全称 | "2024-2025 学年校级先进班集体" |
| submit_date | 申报日期 | "2025-05-20" |
| defense_needed | 是否需答辩 | true / false |

### 6.2 JSON Schema 完整定义

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ClassCollectiveApplication",
  "description": "班集体申报书数据模型（先进班集体 / 优良学风班 / 五四红旗团支部 / 文明班级）",
  "type": "object",
  "required": [
    "class_name", "college", "major", "class_size", "collective_type",
    "male_count", "female_count", "member_count", "party_member_count",
    "class_committee", "head_teacher",
    "ideology_score", "study_score", "activity_score", "discipline_score", "hygiene_score",
    "avg_gpa", "pass_rate", "competition_awards", "cet4_pass_rate", "cet6_pass_rate",
    "overview_text", "ideology_text", "study_text", "activity_text", "honor_text", "outlook_text"
  ],
  "properties": {
    "class_name": {"type": "string", "minLength": 4, "maxLength": 50, "description": "班级全称"},
    "college": {"type": "string", "minLength": 2, "maxLength": 30, "description": "学院全称"},
    "major": {"type": "string", "minLength": 2, "maxLength": 30, "description": "专业全称"},
    "class_size": {"type": "integer", "minimum": 10, "maximum": 100, "description": "班级总人数"},
    "collective_type": {
      "type": "string",
      "enum": ["advanced_class", "good_study_class", "may_fourth_flag", "civilized_class"],
      "description": "申报类别"
    },
    "male_count": {"type": "integer", "minimum": 0, "maximum": 100},
    "female_count": {"type": "integer", "minimum": 0, "maximum": 100},
    "member_count": {"type": "integer", "minimum": 0, "maximum": 100, "description": "团员人数"},
    "party_member_count": {"type": "integer", "minimum": 0, "maximum": 100, "description": "党员（含预备）人数"},
    "class_committee": {
      "type": "array",
      "minItems": 5,
      "maxItems": 15,
      "items": {
        "type": "object",
        "required": ["post", "name", "term"],
        "properties": {
          "post": {"type": "string", "description": "职务"},
          "name": {"type": "string", "description": "姓名"},
          "term": {"type": "string", "description": "任期"}
        }
      }
    },
    "head_teacher": {
      "type": "object",
      "required": ["name", "title", "unit"],
      "properties": {
        "name": {"type": "string"},
        "title": {"type": "string", "description": "职称"},
        "unit": {"type": "string", "description": "所在单位"}
      }
    },
    "ideology_score": {
      "type": "object",
      "required": ["party_ratio", "member_ratio", "youth_study", "theme_meeting", "ideology_grade", "total", "max"],
      "properties": {
        "party_ratio": {"type": "number", "minimum": 0, "maximum": 5},
        "member_ratio": {"type": "number", "minimum": 0, "maximum": 3},
        "youth_study": {"type": "number", "minimum": 0, "maximum": 4},
        "theme_meeting": {"type": "number", "minimum": 0, "maximum": 4},
        "ideology_grade": {"type": "number", "minimum": 0, "maximum": 4},
        "total": {"type": "number", "minimum": 0, "maximum": 20},
        "max": {"type": "number", "const": 20}
      }
    },
    "study_score": {
      "type": "object",
      "required": ["gpa", "top10", "pass_rate", "competition", "cet", "total", "max"],
      "properties": {
        "gpa": {"type": "number", "minimum": 0, "maximum": 8},
        "top10": {"type": "number", "minimum": 0, "maximum": 5},
        "pass_rate": {"type": "number", "minimum": 0, "maximum": 5},
        "competition": {"type": "number", "minimum": 0, "maximum": 4},
        "cet": {"type": "number", "minimum": 0, "maximum": 3},
        "total": {"type": "number", "minimum": 0, "maximum": 25},
        "max": {"type": "number", "const": 25}
      }
    },
    "activity_score": {
      "type": "object",
      "required": ["collective_activity", "school_participation", "volunteer", "culture_award", "social_practice", "total", "max"],
      "properties": {
        "collective_activity": {"type": "number", "minimum": 0, "maximum": 5},
        "school_participation": {"type": "number", "minimum": 0, "maximum": 4},
        "volunteer": {"type": "number", "minimum": 0, "maximum": 4},
        "culture_award": {"type": "number", "minimum": 0, "maximum": 4},
        "social_practice": {"type": "number", "minimum": 0, "maximum": 3},
        "total": {"type": "number", "minimum": 0, "maximum": 20},
        "max": {"type": "number", "const": 20}
      }
    },
    "discipline_score": {
      "type": "object",
      "required": ["attendance", "late", "violation", "cheating", "network", "total", "max"],
      "properties": {
        "attendance": {"type": "number", "minimum": 0, "maximum": 5},
        "late": {"type": "number", "minimum": 0, "maximum": 4},
        "violation": {"type": "number", "minimum": 0, "maximum": 5},
        "cheating": {"type": "number", "minimum": 0, "maximum": 4},
        "network": {"type": "number", "minimum": 0, "maximum": 2},
        "total": {"type": "number", "minimum": 0, "maximum": 20},
        "max": {"type": "number", "const": 20}
      }
    },
    "hygiene_score": {
      "type": "object",
      "required": ["excellent_rate", "civilized_dormitory", "pass_rate", "safety", "total", "max"],
      "properties": {
        "excellent_rate": {"type": "number", "minimum": 0, "maximum": 5},
        "civilized_dormitory": {"type": "number", "minimum": 0, "maximum": 4},
        "pass_rate": {"type": "number", "minimum": 0, "maximum": 3},
        "safety": {"type": "number", "minimum": 0, "maximum": 3},
        "total": {"type": "number", "minimum": 0, "maximum": 15},
        "max": {"type": "number", "const": 15}
      }
    },
    "avg_gpa": {"type": "number", "minimum": 0, "maximum": 4, "description": "班级平均学分绩点"},
    "pass_rate": {"type": "number", "minimum": 0, "maximum": 100, "description": "课程及格率（百分比）"},
    "competition_awards": {
      "type": "object",
      "required": ["national", "provincial", "school"],
      "properties": {
        "national": {"type": "integer", "minimum": 0},
        "provincial": {"type": "integer", "minimum": 0},
        "school": {"type": "integer", "minimum": 0}
      }
    },
    "cet4_pass_rate": {"type": "number", "minimum": 0, "maximum": 100},
    "cet6_pass_rate": {"type": "number", "minimum": 0, "maximum": 100},
    "overview_text": {"type": "string", "minLength": 200, "maxLength": 600},
    "ideology_text": {"type": "string", "minLength": 400, "maxLength": 1000},
    "study_text": {"type": "string", "minLength": 500, "maxLength": 1100},
    "activity_text": {"type": "string", "minLength": 400, "maxLength": 1000},
    "honor_text": {"type": "string", "minLength": 200, "maxLength": 600},
    "outlook_text": {"type": "string", "minLength": 200, "maxLength": 600},
    "collective_honors": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["year", "name", "level"],
        "properties": {
          "year": {"type": "string"},
          "name": {"type": "string"},
          "level": {"type": "string", "enum": ["国家级", "省级", "校级", "院级"]}
        }
      }
    },
    "personal_honors_summary": {
      "type": "object",
      "properties": {
        "national": {"type": "integer"},
        "provincial": {"type": "integer"},
        "school": {"type": "integer"},
        "total_count": {"type": "integer"}
      }
    },
    "word_count_version": {"type": "integer", "enum": [3000, 4000, 5000], "default": 4000},
    "class_slogan": {"type": "string", "maxLength": 50},
    "target_honor": {"type": "string"},
    "submit_date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
    "defense_needed": {"type": "boolean", "default": false}
  }
}
```

### 6.3 最小可用 JSON 示例

```json
{
  "class_name": "计算机科学与技术 2023 级 1 班",
  "college": "计算机学院",
  "major": "计算机科学与技术",
  "class_size": 38,
  "collective_type": "advanced_class",
  "male_count": 26,
  "female_count": 12,
  "member_count": 36,
  "party_member_count": 4,
  "class_committee": [
    {"post": "班长", "name": "张三", "term": "2024.09-2025.06"},
    {"post": "团支书", "name": "李四", "term": "2024.09-2025.06"}
  ],
  "head_teacher": {"name": "王老师", "title": "副教授", "unit": "计算机学院软件工程系"},
  "ideology_score": {"party_ratio": 5, "member_ratio": 3, "youth_study": 4, "theme_meeting": 4, "ideology_grade": 4, "total": 18, "max": 20},
  "study_score": {"gpa": 6, "top10": 5, "pass_rate": 4, "competition": 4, "cet": 3, "total": 22, "max": 25},
  "activity_score": {"collective_activity": 4, "school_participation": 3, "volunteer": 3, "culture_award": 4, "social_practice": 3, "total": 17, "max": 20},
  "discipline_score": {"attendance": 5, "late": 3, "violation": 5, "cheating": 4, "network": 2, "total": 18, "max": 20},
  "hygiene_score": {"excellent_rate": 5, "civilized_dormitory": 3, "pass_rate": 3, "safety": 2, "total": 13, "max": 15},
  "avg_gpa": 3.42,
  "pass_rate": 98.5,
  "competition_awards": {"national": 3, "provincial": 5, "school": 12},
  "cet4_pass_rate": 88.5,
  "cet6_pass_rate": 65.8,
  "overview_text": "（300~500 字班级概况正文）",
  "ideology_text": "（500~900 字思想建设正文）",
  "study_text": "（600~1000 字学风建设正文）",
  "activity_text": "（500~900 字班级活动正文）",
  "honor_text": "（300~500 字班级荣誉正文）",
  "outlook_text": "（300~500 字工作展望正文）",
  "word_count_version": 4000,
  "class_slogan": "团结奋进，求实创新",
  "target_honor": "2024-2025 学年校级先进班集体",
  "submit_date": "2025-05-20",
  "defense_needed": true
}
```

---

