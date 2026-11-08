# §10 JSON Schema 完整字段

> 从 `subskills/selected-graduate/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：构造 --data 输入文件、或 build.py 报字段校验错误时。

### 10.1 顶层结构

```json
{
  "version": "1.0.0",
  "selection_type": "central | directional | non_directional",
  "target_province": "string (报考目标省份或部委)",
  "word_version": "2000 | 2500 | 3000",
  "custom_word_count": "number (可选，自定义字数)",
  "basic_info": {...},
  "academics": {...},
  "party_info": {...},
  "student_work": [...],
  "awards": [...],
  "social_practice": [...],
  "motivation_4d": {...},
  "grassroots_willingness": {...},
  "development_plan": {...},
  "policy_references": [...],
  "signature": {...}
}
```

### 10.2 字段详解

#### 10.2.1 selection_type（选调类型，必填）

```json
"selection_type": "central"
```

枚举值：
- `central`：中央选调（中组部牵头，中央部委）
- `directional`：定向选调（省委组织部，双一流）
- `non_directional`：非定向选调（市委组织部/省委组织部，省内高校）

#### 10.2.2 target_province（目标省份或部委，必填）

```json
"target_province": "山东省"
```

或部委：

```json
"target_province": "国家发展和改革委员会"
```

#### 10.2.3 word_version（字数版本，必填）

```json
"word_version": 2500
```

枚举值：2000 / 2500 / 3000。

#### 10.2.4 basic_info（基本信息，必填）

```json
"basic_info": {
  "name": "张三",
  "gender": "男",
  "ethnicity": "汉族",
  "birth_year": 2001,
  "birth_month": 5,
  "native_place": "山东省济南市",
  "political_status": "中共党员",
  "party_join_date": "2022-05-15",
  "university": "山东大学",
  "college": "政治学与公共管理学院",
  "major": "政治学与行政学",
  "degree": "本科",
  "enrollment_year": 2020,
  "graduation_year": 2024
}
```

**字段约束**：
- `political_status` 必须为"中共党员"或"中共预备党员"（非定向部分岗位可放宽，但本 skill 默认要求党员）
- `party_join_date` 必须提供（YYYY-MM-DD 格式），党员必备
- `degree` 必须为"本科""硕士""博士"之一

#### 10.2.5 academics（学业情况，必填）

```json
"academics": {
  "gpa": 3.85,
  "gpa_total": 4.0,
  "rank": 3,
  "rank_total": 120,
  "english_level": "CET-6",
  "english_score": 580,
  "core_courses": ["政治学原理", "公共管理学", "中国政府与政治", "行政法学"],
  "minor_degree": "法学"
}
```

#### 10.2.6 party_info（党员信息，必填）

```json
"party_info": {
  "party_branch": "政治学与行政学专业本科生党支部",
  "party_position": "组织委员",
  "party_age_years": 2,
  "party_training": ["初级党校", "中级党校", "高级党校"],
  "study_notes_count": 12,
  "theory_exam_rank": "前5%"
}
```

#### 10.2.7 student_work（学生干部经历，必填）

```json
"student_work": [
  {
    "position": "校学生会主席",
    "organization": "校学生会",
    "level": "校级",
    "start_date": "2023-09",
    "end_date": "2024-06",
    "main_achievements": ["牵头组织XX大型活动，参与人次1500人", "推动学生会制度改革"]
  },
  {
    "position": "班长",
    "organization": "政治学与行政学专业2020级1班",
    "level": "班级",
    "start_date": "2020-09",
    "end_date": "2024-06",
    "main_achievements": ["所在班级获评校级先进班集体", "建立班级议事制度"]
  }
]
```

#### 10.2.8 awards（获奖经历，必填）

```json
"awards": [
  {
    "name": "国家奖学金",
    "level": "国家级",
    "year": 2023,
    "ranking": "专业第1"
  },
  {
    "name": "校级一等奖学金",
    "level": "校级",
    "year": 2022,
    "ranking": "连续3年"
  }
]
```

#### 10.2.9 social_practice（社会实践经历，选填）

```json
"social_practice": [
  {
    "name": "三下乡-XX省XX县XX村支教",
    "start_date": "2022-07",
    "end_date": "2022-08",
    "role": "队长",
    "achievements": "支教40天，服务学生120人，撰写调研报告获校级优秀成果奖"
  }
]
```

#### 10.2.10 motivation_4d（报考动机 4 维度，必填）

```json
"motivation_4d": {
  "political_standpoint": "作为一名中共党员...",
  "grassroots_service": "大学期间先后两次参加三下乡...",
  "career_pursuit": "我深知选调生是党和国家培养青年干部的重要渠道...",
  "hometown_attachment": "我是XX省XX市人..."
}
```

**字段约束**：4 维度缺一不可，每个维度必须有实质内容（不少于 100 字）。

#### 10.2.11 grassroots_willingness（基层工作意愿，必填）

```json
"grassroots_willingness": {
  "accept_rural": true,
  "accept_remote": true,
  "accept_cross_city": true,
  "service_years_commitment": 5,
  "psychological_readiness": "对艰苦环境有充分心理准备"
}
```

#### 10.2.12 development_plan（个人发展规划，必填）

```json
"development_plan": {
  "first_two_years": "前两年扎根基层，深入学习基层治理、群众工作、政策执行等基础业务...",
  "middle_two_years": "中间两年成长提升，在熟悉业务基础上独立承担重点工作...",
  "fifth_year": "第五年担当作为，力争成为本单位业务骨干..."
}
```

#### 10.2.13 policy_references（政策引用，选填）

```json
"policy_references": [
  {
    "name": "关于做好选调生工作的意见",
    "issuer": "中组部",
    "year": 2014,
    "quoted_in": "报考动机段"
  }
]
```

#### 10.2.14 signature（签字栏，必填）

```json
"signature": {
  "applicant_name": "张三",
  "applicant_date": "2024-09-15",
  "college_reviewer": "李四（学院党委副书记）",
  "college_review_date": "2024-09-16",
  "college_seal": "（学院党委盖章）"
}
```

### 10.3 完整 JSON 示例

```json
{
  "version": "1.0.0",
  "selection_type": "directional",
  "target_province": "山东省",
  "word_version": 2500,
  "basic_info": {
    "name": "张三",
    "gender": "男",
    "ethnicity": "汉族",
    "birth_year": 2001,
    "birth_month": 5,
    "native_place": "山东省济南市",
    "political_status": "中共党员",
    "party_join_date": "2022-05-15",
    "university": "山东大学",
    "college": "政治学与公共管理学院",
    "major": "政治学与行政学",
    "degree": "本科",
    "enrollment_year": 2020,
    "graduation_year": 2024
  },
  "academics": {
    "gpa": 3.85,
    "gpa_total": 4.0,
    "rank": 3,
    "rank_total": 120,
    "english_level": "CET-6",
    "english_score": 580
  },
  "party_info": {
    "party_branch": "政治学与行政学专业本科生党支部",
    "party_position": "组织委员",
    "party_age_years": 2
  },
  "student_work": [
    {
      "position": "校学生会主席",
      "organization": "校学生会",
      "level": "校级",
      "start_date": "2023-09",
      "end_date": "2024-06",
      "main_achievements": ["牵头组织XX大型活动，参与人次1500人"]
    }
  ],
  "awards": [
    {"name": "国家奖学金", "level": "国家级", "year": 2023}
  ],
  "motivation_4d": {
    "political_standpoint": "作为一名中共党员，我始终把政治建设摆在首位...",
    "grassroots_service": "大学期间我先后两次参加三下乡...",
    "career_pursuit": "我深知选调生是党和国家培养青年干部的重要渠道...",
    "hometown_attachment": "我是山东省济南市人..."
  },
  "grassroots_willingness": {
    "accept_rural": true,
    "accept_remote": true,
    "service_years_commitment": 5
  },
  "development_plan": {
    "first_two_years": "前两年扎根基层...",
    "middle_two_years": "中间两年成长提升...",
    "fifth_year": "第五年担当作为..."
  },
  "signature": {
    "applicant_name": "张三",
    "applicant_date": "2024-09-15"
  }
}
```

---

