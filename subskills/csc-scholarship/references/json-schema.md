# §9 JSON Schema 完整字段

> 从 `subskills/csc-scholarship/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：构造 --data 输入文件、或 build.py 报字段校验错误时。

本节给出 build.py 接受的 JSON 数据完整字段定义，与 §7 信息采集清单一一对应。

### §9.1 顶层字段

```json
{
  "name": "王某某",
  "gender": "男",
  "birth_date": "1995-06-15",
  "nationality": "中国",
  "ethnicity": "汉族",
  "political_status": "中共党员",
  "marital_status": "已婚",
  "current_unit": "XX 大学材料科学与工程学院 2022 级博士研究生",
  "phone": "138XXXXXXXX",
  "email": "wang@example.edu.cn",
  "student_id": "2022B11050",

  "csc_type": "joint_phd",
  "csc_type_label": "联合培养博士研究生",

  "target_country": "美国",
  "target_university_en": "Massachusetts Institute of Technology",
  "target_university_cn": "麻省理工学院",
  "target_university_qs_rank": 1,
  "target_department_en": "Department of Materials Science and Engineering",
  "target_department_cn": "材料科学与工程系",

  "target_advisor_name": "Yet-Ming Chiang",
  "target_advisor_title": "Kyocera 讲席教授",
  "target_advisor_honor": "美国国家工程院院士",
  "target_advisor_email": "chiang@mit.edu",
  "target_advisor_h_index": 95,
  "target_advisor_recent_papers": 28,
  "target_advisor_nature_science_papers": 4,
  "target_advisor_research": "电化学储能与材料科学",

  "study_start": "2024-09-01",
  "study_end": "2026-08-31",
  "study_period_months": 24,

  "research_direction": "硫碳复合正极的原位表征与界面调控",
  "research_field_category": "新能源/储能",

  "language_test_type": "IELTS",
  "language_score": "7.0",
  "language_test_date": "2023-03-15",
  "language_min_requirement": "6.5",

  "recommend_unit": "XX 大学",
  "domestic_advisor_name": "李某某",
  "domestic_advisor_title": "教授",
  "domestic_advisor_research": "锂硫电池正极材料",

  "return_target_unit": "XX 大学材料学院",
  "return_position": "副教授",
  "return_research": "先进电池材料产业化研究",
  "return_service_years": 2,

  "word_count_version": "3000",
  "material_type": "B",
  "salutation": "尊敬的国家留学基金管理委员会评审专家：",
  "apply_date": "2024-03-10"
}
```

### §9.2 教育背景子结构 education_background

```json
"education_background": {
  "bachelor": {
    "school": "XX 大学",
    "school_en": "XX University",
    "major": "材料科学与工程",
    "start": "2013-09",
    "end": "2017-06",
    "degree": "工学学士",
    "gpa": "3.7/4.0",
    "rank": "5/120"
  },
  "master": {
    "school": "XX 大学",
    "school_en": "XX University",
    "major": "材料学",
    "start": "2017-09",
    "end": "2020-06",
    "degree": "工学硕士",
    "advisor": "李某某 教授",
    "gpa": "3.85/4.0",
    "rank": "2/45",
    "thesis_title": "硫碳复合正极的制备与电化学性能研究"
  },
  "phd": {
    "school": "XX 大学",
    "school_en": "XX University",
    "major": "材料科学与工程",
    "start": "2020-09",
    "expected_end": "2024-06",
    "advisor": "李某某 教授",
    "research_direction": "锂硫电池正极材料",
    "gpa": "3.9/4.0",
    "rank": "1/30"
  }
}
```

### §9.3 学术成果子结构 academic_achievements

```json
"academic_achievements": {
  "publications": [
    {
      "authors": "Wang X, Li Y, et al.",
      "title": "Sulfur-carbon composite cathode for lithium-sulfur batteries",
      "journal": "Advanced Energy Materials",
      "year": 2023,
      "if": 24.4,
      "role": "第一作者"
    }
  ],
  "patents": [
    {
      "title": "一种硫碳复合正极制备方法",
      "patent_no": "ZL202210012345.6",
      "year": 2023,
      "role": "第一发明人"
    }
  ],
  "awards": [
    {
      "name": "国家奖学金",
      "year": 2022,
      "level": "国家级"
    }
  ],
  "projects": [
    {
      "name": "国家自然科学基金面上项目",
      "role": "主要参与人",
      "pi": "李某某 教授",
      "year": "2021-2024"
    }
  ]
}
```

### §9.4 留学动机子结构 motivation（4 维度）

```json
"motivation": {
  "academic_pursuit": "本人在国内已系统开展锂硫电池正极材料研究...",
  "national_strategy": "本人研究方向与《"十四五"新型储能发展实施方案》...",
  "discipline_gap": "国内外在本研究方向的设备差距体现在...",
  "personal_development": "本人在国内博士第 3 年已完成硫碳复合正极基础研究..."
}
```

### §9.5 学习计划子结构 research_plan（5 要素）

```json
"research_plan": {
  "research_direction": "硫碳复合正极的原位表征与界面调控",
  "research_background": "...",
  "research_objectives": ["目标1", "目标2", "目标3", "目标4"],
  "research_contents": ["内容1", "内容2", "内容3", "内容4"],
  "research_methods": "原位同步辐射实验为主，辅以 DFT 计算",

  "courses": [
    {"code": "3.091", "name": "Introduction to Solid State Chemistry", "credits": 5.0, "reason": "基础巩固材料化学基础"},
    {"code": "3.43", "name": "Electrochemical Energy Storage", "credits": 4.5, "reason": "与本人研究方向直接相关"}
  ],

  "advisor_collab": "外方导师与本人国内导师已有 6 年合作基础...",

  "collab_research": {
    "my_role": "硫碳复合正极样品制备、原位 XRD 实验设计、数据分析",
    "advisor_role": "同步辐射光源申请与机时安排、原位电化学池设计、DFT 计算支持",
    "sustainability": "留学结束后，本课题将继续以中-美合作形式延续"
  },

  "expected_outcomes": {
    "papers": 3,
    "first_author_papers": 2,
    "target_journals": ["Advanced Energy Materials", "Joule", "ACS Energy Letters"],
    "patents_pct": 1,
    "patents_domestic": 2,
    "conferences": 2,
    "oral_presentations": 1
  },

  "timeline": [
    {"period": "2024.09~2024.12", "task": "硫碳复合正极制备工艺优化"},
    {"period": "2025.01~2025.06", "task": "原位 XRD 表征"},
    {"period": "2025.07~2025.12", "task": "原型器件组装与测试"},
    {"period": "2026.01~2026.06", "task": "数据分析与论文撰写"},
    {"period": "2026.07~2026.08", "task": "归国总结与成果汇报"}
  ]
}
```

### §9.6 合作基础子结构 collaboration_basis

```json
"collaboration_basis": {
  "joint_papers": [
    {"title": "xxx", "journal": "Nature Communications", "year": 2022}
  ],
  "mutual_visits": 3,
  "email_exchanges": 200,
  "joint_projects": [
    {"name": "中美锂硫电池合作项目", "period": "2020-2025", "funder": "NSFC-NSF"}
  ]
}
```

### §9.7 归国计划子结构 return_plan

```json
"return_plan": {
  "return_date": "2026-09",
  "target_unit": "XX 大学材料学院",
  "position": "副教授",
  "research_plan": "组建先进电池材料课题组，继续推进锂硫电池产业化研究",
  "industry_partner": "宁德时代新能源科技股份有限公司",
  "service_years": 2,
  "long_term_plan": "3 年内申报国家自然科学基金青年项目，5 年内组建 5 人课题组",
  "return_letter_signed": true
}
```

### §9.8 经济保障子结构 financial_arrangement

```json
"financial_arrangement": {
  "csc_allowance_monthly_usd": 1900,
  "csc_allowance_total_usd": 45600,
  "tuition_waived": true,
  "tuition_waiver_source": "MIT 材料系免学费（见邀请函附件 5）",
  "advisor_research_stipend_monthly_usd": 500,
  "spouse_income_monthly_cny": 12000,
  "emergency_fund_cny": 60000,
  "insurance_arrangement": "CSC 统一购买国际医疗保险 + 个人购买商业补充保险"
}
```

### §9.9 输出控制字段

```json
{
  "word_count_version": "3000",
  "material_type": "B",
  "salutation": "尊敬的国家留学基金管理委员会评审专家：",
  "opening": "",
  "motivation_text": "",
  "university_choice_text": "",
  "study_plan_text": "",
  "return_plan_text": "",
  "financial_text": "",
  "apply_date": "2024-03-10"
}
```

### §9.10 字段默认值与覆盖规则

| 字段 | 默认值 | 覆盖规则 |
|---|---|---|
| csc_type | joint_phd | 用户提供时覆盖 |
| csc_type_label | 联合培养博士研究生 | 按 csc_type 自动映射 |
| word_count_version | 按 csc_type 自动（2500/3000/4000） | 用户提供时覆盖 |
| material_type | B | 用户提供时覆盖 |
| salutation | "尊敬的国家留学基金管理委员会评审专家：" | 用户提供时覆盖 |
| study_period_months | 按 study_start/end 自动计算 | 用户提供时覆盖 |
| return_service_years | 2 | 用户提供时覆盖 |

---

