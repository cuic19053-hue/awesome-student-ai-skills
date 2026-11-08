# 十七、JSON Schema 完整字段定义【v2.1 必加章节 9】

> 从 `subskills/college-research/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：构造 --data 输入文件、或 build.py 报字段校验错误时。

### 17.1 顶层字段总览

```jsonc
{
  // ===== 通用必采字段（P0） =====
  "project_name": "string, 课题名称 ≤30 字",
  "leader_name": "string, 负责人姓名",
  "leader_id": "string, 学号",
  "leader_gender": "string, 性别",
  "leader_major": "string, 专业年级",
  "leader_phone": "string, 联系电话",
  "leader_email": "string, 邮箱",
  "advisor_name": "string, 指导教师姓名+职称",
  "advisor_phone": "string, 指导教师电话",
  "college": "string, 学院全称",
  "apply_date": "string, 申报日期",

  // ===== 课题专属字段（P0） =====
  "basic_info": {
    "research_type": "string, 基础研究|应用研究|开发研究",
    "discipline": "string, 一级学科代码+名称",
    "duration": "string, 起止时间（3~6 个月）",
    "budget": "string, 申请经费（500~2000 元）"
  },
  "team_members": [
    {"name": "string", "id": "string", "major": "string", "role": "string", "phone": "string"}
  ],

  // ===== 16 栏目内容字段（P0/P1） =====
  "background": ["string×4, 时代背景/现实痛点/研究缺口/课题意义"],
  "research_status": ["string×3, 国内/国外/综合评述（简版）"],
  "research_goal": "string, 总目标+阶段目标",
  "research_content": ["string×2~4, 子任务"],
  "key_problems": ["string×1~2, 关键问题"],
  "tech_route": "string, 总体技术路线（简版）",
  "methods": ["string×3~4, 研究方法"],
  "data_source": "string, 数据来源与实验条件",
  "innovations": ["string×1~2, 创新点"],
  "team_foundation": "string, 团队基础",
  "advisor_foundation": "string, 指导教师基础",
  "lab_condition": "string, 实验条件",
  "expected_outcomes": ["string×1~3, 预期成果"],
  "schedule": [{"phase": "string", "time": "string", "work": "string", "output": "string"}],
  "budget_items": [{"item": "string", "amount": "string", "basis": "string"}],
  "budget_total": "string, 合计金额",
  "references": [{"ref_type": "string", "authors": "string", ...}],

  // ===== v2.1 新增 7 项强化字段（P0） =====
  "policy_citations": [{"agency": "string", "title": "string", "doc_no": "string", "date": "string", "excerpt": "string"}],
  "scientific_challenges": [{"title": "string", "description": "string", "sub_challenges": ["string"], "references": ["int"]}],
  "literature_review": {"significance": ["string"], "domestic": ["string"], "foreign": ["string"], "summary": "string"},
  "method_comparison": {"table_headers": ["string"], "methods": [{"name": "string", "features": {"技术特点": "string", "优势": "string", "劣势": "string"}, "reference": "int"}], "conclusion": "string"},
  "tech_roadmap": {"image_path": "string", "caption": "string", "description": "string"},
  "formulas": [{"formula": "string", "number": "int", "variables": [{"name": "string", "meaning": "string"}]}],
  "social_benefits": [{"indicator": "string", "baseline": "string", "expected": "string", "improvement": "string"}],
  "project_schedule": [{"phase": "string", "time": "string", "tasks": ["string"], "output": "string"}]
}
```

### 17.2 v2.1 新增字段详解

#### 17.2.1 policy_citations（国家政策引用，≥3 条）

```jsonc
"policy_citations": [
  {
    "agency": "中国心理学会",                // 发文机关
    "title": "大学生学习行为蓝皮书",          // 文件标题
    "doc_no": "",                            // 文号（如有）
    "date": "2024-09-20",                    // 发布日期 YYYY-MM-DD
    "excerpt": "全国高校学生学习拖延行为发生率达 67.8%...",  // 与课题相关的关键表述
    "url": "http://www.cps.org.cn/xxx",      // URL（如有）
    "access_date": "2025-02-15"              // 访问日期（如有 URL）
  }
  // ... 至少 3 条
]
```

#### 17.2.2 scientific_challenges（科学挑战，1~2 个）

```jsonc
"scientific_challenges": [
  {
    "title": "三维干预中各维度的协同机制设计",  // 一句话标题，含关键技术词
    "description": "本课题融合三维干预...",    // 3~5 句描述
    "sub_challenges": [                        // 子挑战列表（1~2 个）
      "子挑战 1：维度间剂量配比的优化..."
    ],
    "references": [3, 4]                       // 文献编号上标
  }
  // 1~2 个挑战
]
```

#### 17.2.3 literature_review（国内外研究现状综述，≥10 条）

```jsonc
"literature_review": {
  "significance": [                            // 研究意义段（3~5 段）
    "学习拖延是大学生最常见的自我调节失效行为之一...",
    "理论意义：本课题验证拖延行为三因素模型..."
  ],
  "domestic": [                                // 国内研究现状段（4~5 篇）
    "张丽等（2022）对 3 所高校 600 名大学生调查发现学习拖延发生率 65.4% [1]，但仅描述现象未提出干预方案。",
    // ...
  ],
  "foreign": [                                 // 国外研究现状段（3~5 篇，含 ≥3 篇英文）
    "Steel (2020) 综述了近 20 年拖延研究，提出\"动机-时间感知-冲动性\"三因素模型 [3]。",
    // ...
  ],
  "summary": "已有研究存在三个共性问题：① ...；② ...；③ ...。本课题的关键差异：（1）...；（2）...；（3）..."  // 总结与分析
}
```

#### 17.2.4 method_comparison（方法对比表，2 方法 × 3 维度）

```jsonc
"method_comparison": {
  "table_headers": ["维度", "单一正念干预", "三维融合干预（本课题）"],
  "methods": [
    {
      "name": "单一正念干预",
      "features": {
        "技术特点": "仅采用正念冥想训练（每周 2 次 × 30 分钟）",
        "优势": "实施简单、成本低、文献基础扎实 [4]",
        "劣势": "见效慢（≥6 周）、单一维度效果有限（降 12~15%）"
      },
      "reference": 4
    },
    {
      "name": "三维融合干预（本课题）",
      "features": {
        "技术特点": "正念+同伴监督+学业规划三维并行（每周 2+1+1 次）",
        "优势": "多维协同、覆盖拖延行为多因素 [3]、效果更全面",
        "劣势": "实施复杂、需多维度协调、对组织者要求高"
      },
      "reference": 3
    }
  ],
  "conclusion": "基于上表，单一正念干预实施简单但效果有限，三维融合干预虽实施复杂但覆盖拖延行为的多因素模型。结合本课题实际条件，本课题选用三维融合干预。"
}
```

#### 17.2.5 tech_roadmap（技术路线图，1 张）

```jsonc
"tech_roadmap": {
  "image_path": "/path/to/tech_roadmap.png",   // 图片路径（如无图则空字符串，使用文字描述版）
  "caption": "图 1 课题技术路线图",            // 图号+标题
  "description": "本课题技术路线分 4 阶段..."  // 图后说明文字 120~200 字
}
```

#### 17.2.6 formulas（数学公式，≥1，可选）

```jsonc
"formulas": [
  {
    "formula": "d = (μ₁ - μ₂) / s_p",          // 公式 LaTeX/Unicode
    "number": 1,                                // 公式编号
    "variables": [                              // 变量定义
      {"name": "d", "meaning": "Cohen's d 效应量"},
      {"name": "μ₁", "meaning": "干预组后测均值"},
      {"name": "μ₂", "meaning": "对照组后测均值"},
      {"name": "s_p", "meaning": "合并标准差，s_p = √((s₁² + s₂²) / 2)"}
    ]
  }
  // ≥1 个公式（如本课题无公式可省略此字段）
]
```

#### 17.2.7 social_benefits（社会效益量化，≥3 项）

```jsonc
"social_benefits": [
  {
    "indicator": "本院学生学习拖延发生率",
    "baseline": "71.3%（基线调研，本院 3 年级 120 人）",
    "expected": "≤51.3%",
    "improvement": "降低 ≥20 个百分点"
  },
  {
    "indicator": "期末挂科率（严重拖延学生）",
    "baseline": "32%（基线）",
    "expected": "≤20%",
    "improvement": "降低 ≥12 个百分点"
  },
  {
    "indicator": "学生自我效能感得分（SES 量表）",
    "baseline": "25.4 分（基线均值，满分 40）",
    "expected": "≥29.0 分",
    "improvement": "提升 ≥3.6 分（+14.2%）"
  }
  // ≥3 项
]
```

#### 17.2.8 project_schedule（进度安排，4 阶段 6 个月）

```jsonc
"project_schedule": [
  {
    "phase": "准备",
    "time": "2025.04",
    "tasks": ["文献综述 30 篇", "三维干预方案设计", "量表选型与预测试"],
    "output": "综述 1 份 + 方案 1 份"
  },
  {
    "phase": "试点",
    "time": "2025.05-07",
    "tasks": ["招募 200 人（干预 100+对照 100）", "4 周干预实施", "实施过程记录与质控"],
    "output": "实施记录 + 原始数据"
  },
  {
    "phase": "分析",
    "time": "2025.08-09",
    "tasks": ["SPSS 27 统计分析", "Amos 24 中介效应分析", "NVivo 14 访谈编码"],
    "output": "分析报告 1 份"
  },
  {
    "phase": "跟踪",
    "time": "2025.09",
    "tasks": ["2 个月跟踪测", "深度访谈 15 人", "撰写调研报告"],
    "output": "跟踪报告 + 调研报告 1 份"
  }
  // ≥4 阶段
]
```

### 17.3 references 子结构（5 类）

```jsonc
"references": [
  // 期刊
  {"ref_type": "journal", "authors": "张丽, 王伟", "title": "...", "journal": "...", "year": "2022", "volume": "45", "issue": "(3)", "pages": "612-619", "is_english": false},
  // 会议
  {"ref_type": "conference", "authors": "...", "title": "...", "conference": "...", "city": "...", "publisher": "...", "year": "...", "pages": "...", "is_english": true},
  // 专著
  {"ref_type": "book", "authors": "...", "title": "...", "edition": "2版", "city": "...", "publisher": "...", "year": "...", "pages": "...", "is_english": false},
  // 学位论文
  {"ref_type": "thesis", "authors": "...", "title": "...", "city": "...", "school": "...", "year": "..."},
  // 网络资源
  {"ref_type": "web", "authors": "...", "title": "...", "publish_date": "2024-09-20", "access_date": "2025-02-15", "url": "...", "is_government": true}
]
```

### 17.4 字段与 build.py 方法对应表

| 字段 | build.py 方法 | 章节位置 |
|------|---------------|----------|
| project_name/leader_name/...通用字段 | _add_cover / _add_leader_members / _add_basic_info | 封面 + §1~§4 |
| background | _add_background | §5 |
| **policy_citations** (v2.1) | _add_policy_citations | §5.5（v2.1 新增） |
| research_status | _add_research_status | §6 |
| **literature_review** (v2.1) | _add_literature_review | §6.5（v2.1 新增） |
| research_goal/research_content/key_problems | _add_research_content | §7 |
| **scientific_challenges** (v2.1) | _add_scientific_challenges | §7.5（v2.1 新增） |
| tech_route/methods/data_source | _add_research_scheme | §8 |
| **method_comparison** (v2.1) | _add_method_comparison | §8.5（v2.1 新增） |
| **formulas** (v2.1) | _add_formulas | §8.6（v2.1 新增） |
| **tech_roadmap** (v2.1) | _add_tech_roadmap | §8.7（v2.1 新增） |
| innovations | _add_innovation | §9 |
| team_foundation/advisor_foundation/lab_condition | _add_research_basis | §10 |
| expected_outcomes | _add_expected_results | §11 |
| **social_benefits** (v2.1) | _add_social_benefits | §11.5（v2.1 新增） |
| schedule / **project_schedule** (v2.1) | _add_schedule / _add_project_schedule | §12 |
| budget_items/budget_total | _add_budget | §13 |
| references | _add_references | §14 |

### 17.5 完整 JSON 示例（v2.1）

完整 v2.1 JSON 示例见 build.py 的 `DEFAULT_DATA` 常量，包含全部 16 栏目 + 9 项 v2.1 强化字段。用户填充时按此结构组织 JSON。

### 17.6 字段向后兼容

v2.1 新增字段（policy_citations / scientific_challenges / literature_review / method_comparison / tech_roadmap / formulas / social_benefits / project_schedule）均为可选字段。当用户 JSON 缺少这些字段时，build.py 会跳过对应章节的渲染并记录 warning，不阻断生成。这保证 v2.0 用户的旧 JSON 仍可在 v2.1 build.py 中运行。

---

