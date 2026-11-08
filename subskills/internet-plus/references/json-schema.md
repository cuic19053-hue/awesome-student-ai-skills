# 十六、JSON Schema

> 从 `subskills/internet-plus/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：构造 --data 输入文件、或 build.py 报字段校验错误时。

### 16.1 顶层字段（45 字段）

```json
{
  // 通用必采（12 字段）
  "project_name": "string",
  "track": "main|red_journey|vocational",
  "group": "string",
  "team_name": "string",
  "leader_name": "string",
  "leader_id": "string",
  "leader_major": "string",
  "leader_grade": "string",
  "leader_phone": "string",
  "college": "string",
  "school": "string",
  "apply_date": "string",
  "advisor_name": "string",
  "advisor_title": "string",
  "advisor_research": "string",

  // 赛级与字数档
  "competition_level": "school|province|national",

  // 项目核心（10 字段）
  "one_liner": "string",
  "industry": "string",
  "target_user": "string",
  "pain_point": "string",
  "stage": "string",
  "registered": "string",
  "revenue": "string",
  "users": "string",
  "ip_status": "string",
  "partnerships": "string",

  // 11 大栏目
  "executive_summary": "string",
  "market_analysis": "object",
  "product_service": "object",
  "business_model": "object",
  "operations": "object",
  "financial_forecast": "object",
  "financing_plan": "object",
  "team_intro": "object",
  "risk_analysis": "array",
  "personal_growth": "object",
  "team_collaboration": "object",

  // 11 项案例化必加章节（新增）
  "policy_citations": "array",
  "scientific_challenges": "array",
  "literature_review": "object",
  "algorithm_comparison": "object",
  "tech_roadmap": "array",
  "formulas": "array",
  "economic_benefits": "array",
  "project_innovation": "object",
  "industry_value": "object",
  "marketing_4p": "object",
  "pricing_3c": "object",
  "financial_statements": "object",
  "practice_process": "object",
  "tech_barriers": "object"
}
```

### 16.2 policy_citations（国家政策引用，10+）

```json
"policy_citations": [
  {
    "order": 1,
    "date": "2026.03",
    "issuer": "国务院办公厅",
    "doc_number": "国办发〔2026〕XX 号",
    "title": "关于加强基层消防工作的意见",
    "key_excerpt": "推动智能化装备研发与实战化应用",
    "relevance": "本项目研发的 XX 系统正是响应该号召，通过 XX 技术实现 XX"
  }
]
```

### 16.3 scientific_challenges（科学挑战，3 段）

```json
"scientific_challenges": [
  {
    "id": 1,
    "title": "多模态数据时空融合与三维火场实时重构计算",
    "description": "火场环境具有高温、浓烟、强遮挡、动态变化等极端特性...",
    "sub_challenges": [
      {
        "title": "多模态数据时空配准",
        "detail": "不同传感器采样频率、坐标系、视场角差异大...",
        "literature_refs": [1, 2, 3]
      },
      {
        "title": "实时三维重构算法",
        "detail": "传统 SLAM 算法在动态火场中漂移严重...",
        "literature_refs": [4, 5, 6]
      }
    ]
  }
]
```

### 16.4 literature_review（文献综述，30+）

```json
"literature_review": {
  "research_significance": [
    {
      "direction": "多模态感知技术对火场信息获取的意义",
      "content": "多模态感知技术通过融合...",
      "literature_refs": [1, 2, 3]
    }
  ],
  "research_status": [
    {
      "direction": "多模态感知研究现状",
      "content": "国内外学者在多模态感知领域开展了大量研究...",
      "literature_refs": [1, 2, 3, 4, 5]
    }
  ],
  "gap_analysis": "现有研究存在以下不足：1. ... 2. ... 3. ...",
  "references": [
    {
      "id": 1,
      "authors": "Wang Y, Zhang X, Li H",
      "title": "Multi-modal sensor fusion for fire detection using deep learning",
      "journal": "IEEE Transactions on Geoscience and Remote Sensing",
      "year": 2024,
      "volume": "62",
      "issue": "3",
      "pages": "1-15",
      "type": "journal",
      "language": "en"
    }
  ]
}
```

### 16.5 algorithm_comparison（算法对比表）

```json
"algorithm_comparison": {
  "title": "主流自适应路径规划算法对比表",
  "headers": ["维度", "DQN 算法", "DDPG 算法", "SAC 算法"],
  "rows": [
    {"dimension": "技术特点", "values": ["基于值函数", "基于 Actor-Critic", "基于最大熵"]},
    {"dimension": "优势", "values": ["离散动作空间稳定", "连续动作空间", "探索与利用平衡"]},
    {"dimension": "劣势", "values": ["连续动作失效", "探索能力弱", "计算复杂度高"]},
    {"dimension": "适用场景", "values": ["离散决策", "路径跟踪", "复杂动态环境"]},
    {"dimension": "计算效率", "values": ["中", "高", "低"]},
    {"dimension": "文献来源", "values": ["[15]", "[16]", "[17]"]}
  ],
  "conclusion": "基于上表对比分析，本项目选用 SAC 算法，理由如下：1. ... 2. ... 3. ... 4. ..."
}
```

### 16.6 tech_roadmap（技术路线图，3 张）

```json
"tech_roadmap": [
  {
    "figure_number": "图 1",
    "title": "项目开展的主要研究内容及其相互关系",
    "description": "本项目研究内容分为 4 大模块：模块 1（多模态感知）→ 模块 2（三维重构）→ 模块 3（目标检测）→ 模块 4（路径规划）",
    "nodes": [
      {"id": 1, "name": "多模态感知", "content": "数据采集与融合", "section": "§3.1", "input": "多源传感数据", "output": "融合特征"},
      {"id": 2, "name": "三维重构", "content": "火场三维建模", "section": "§3.2", "input": "融合特征", "output": "三维点云"}
    ]
  }
]
```

### 16.7 formulas（数学公式）

```json
"formulas": [
  {
    "algorithm_name": "ASCN",
    "algorithm_full_name": "Adaptive Spatial Clustering Network",
    "description": "ASCN 算法用于多模态点云数据融合",
    "formulas": [
      {
        "number": "式(1)",
        "name": "密度计算公式",
        "expression": "ρ(p) = |N(p, r)| / V(r)",
        "variables": [
          {"symbol": "N(p, r)", "meaning": "以点 p 为中心、半径为 r 的邻域内的点集"},
          {"symbol": "V(r)", "meaning": "邻域球体积"},
          {"symbol": "ρ(p)", "meaning": "点 p 处的局部密度"}
        ]
      }
    ],
    "flow_steps": ["Step 1：输入多模态点云 P", "Step 2：计算密度 ρ(p_i)", "Step 3：归一化密度"],
    "innovations": ["引入动态扩张率", "多模态信息融合", "时间复杂度 O(n log n)"]
  }
]
```

### 16.8 economic_benefits（社会经济效益量化，12 项）

```json
"economic_benefits": [
  {
    "indicator": "单次城市火灾平均经济损失",
    "traditional_baseline": "100%（基准）",
    "system_expected": "60%-80%",
    "improvement": "降低 20%-40%",
    "improvement_multiplier": "1.25-1.67 倍"
  }
]
```

### 16.9 personal_growth（个人成长 3 段）

```json
"personal_growth": {
  "learning_growth": "作为 [项目角色]，我在本项目中承担 [具体动作]...",
  "practice_experience": "项目过程中，我参与了 [实践活动]...",
  "reflection_breakthrough": "项目过程中最深刻的反思来自 [失败案例]...",
  "role": "（旧字段保留，与新字段互补）",
  "transformation": "从 X 变为 Y 的具体变化",
  "hard_skills": "硬技能：市场测算/财务建模/产品原型",
  "soft_skills": "软技能：沟通/协调/抗压",
  "failure": "至少 1 个具体失败案例 + 复盘收获"
}
```

### 16.10 project_innovation（项目创新 3 套）

```json
"project_innovation": {
  "tech_innovation": {
    "name": "Fire-Transformer 算法",
    "description": "本项目提出 Fire-Transformer 算法，相较现有 Transformer...",
    "quantitative_improvement": "在准确率上提升 15%，延迟降低 40%",
    "patent_refs": ["专利号 1"]
  },
  "model_innovation": {
    "name": "校园认证 + 信用积分双轨模式",
    "description": "本项目创新性提出...",
    "quantitative_improvement": "CAC 降低 30%，转化率提升 25%"
  },
  "business_innovation": {
    "name": "无人机 + 应急救援新业态",
    "description": "本项目开创...",
    "quantitative_improvement": "3 年内为行业节约 10 亿元"
  }
}
```

### 16.11 industry_value（产业价值 4 维度）

```json
"industry_value": {
  "market_scale": {
    "tam": "250 亿元/年",
    "sam": "6.4 亿元/年",
    "som": "1272 万元/年",
    "data_source": "艾瑞咨询《2024 中国二手电商报告》",
    "share_in_3_years": "SOM × 30% = 380 万元/年"
  },
  "employment_driving": {
    "direct_employment": "团队 5 人 + 公司员工 10 人 = 15 人",
    "indirect_employment": "上游供应商 5 人 + 下游客户 8 人 + 配套服务 7 人 = 20 人",
    "total_in_3_years": "3 年内带动就业 35 人"
  },
  "tax_contribution": {
    "year1": "0 万元（亏损）",
    "year3": "9 万元（所得税）",
    "year5": "55.5 万元（所得税）",
    "cumulative_5_years": "约 92.7 万元"
  },
  "social_benefit": {
    "description": "本项目通过 XX 技术实现 XX 功能，在 12 项核心指标上实现显著提升...",
    "indicator_count": 12,
    "key_metrics": ["响应时间缩短 50%-70%", "识别召回率提升 ≥22 个百分点"]
  }
}
```

### 16.12 team_collaboration（团队协作 4 维度）

```json
"team_collaboration": {
  "division": "CEO 张三负责战略+融资；CTO 王五负责技术+架构...",
  "complementarity": "团队 5 人覆盖工商管理+计算机+软件工程+市场营销+视觉传达 5 专业",
  "consensus": "团队愿景：成为校园闲置流转第一品牌。价值观：用户第一、数据驱动、快速迭代",
  "crisis_handling": "曾就'先扩张 10 校 vs 深耕 5 校'产生分歧，通过用户调研数据 + 投票机制解决",
  "tools": "（旧字段保留）飞书+Notion+Figma+周会+日站会"
}
```

### 16.13 marketing_4p（4P 营销）

```json
"marketing_4p": {
  "product": "产品定位：校园闲置流转第一品牌。产品组合：核心小程序 + 拓展 PC 端 + 衍生同城服务",
  "price": "定价方法：竞品对标 + 用户价值。价格体系：基础免费 + 增值会员 9.9/月 + 企业版 99/月",
  "place": "渠道：微信小程序 + 校园社团 + 社群裂变。覆盖：本市 5 所高校 → 本省 50 所 → 全国",
  "promotion": "推广：地推 + KOL + 内容营销。预算 30 万，预期 ROI 1:5"
}
```

### 16.14 pricing_3c（3C 定价）

```json
"pricing_3c": {
  "cost": "变动成本 30 元/件 + 固定成本分摊 10 元/件 = 40 元/件，加成率 50% → 单价 60 元",
  "competitor": "竞品 A 100 元（高端），竞品 B 60 元（中端），竞品 C 30 元（低端），本项目 50 元（中端偏下）",
  "customer": "50 份调研：35% 接受 5 元/月，68% 接受 9.9 元/月，22% 接受 19.9 元/月，定价 9.9 元/月"
}
```

### 16.15 financial_statements（5 年三表）

```json
"financial_statements": {
  "income_statement": {
    "title": "5 年利润表（单位：万元）",
    "headers": ["项目", "Year1", "Year2", "Year3", "Year4", "Year5"],
    "rows": [
      {"item": "营业收入", "y1": "12", "y2": "60", "y3": "200", "y4": "500", "y5": "1000"},
      {"item": "净利润", "y1": "-3", "y2": "6.8", "y3": "51", "y4": "153", "y5": "314.5"}
    ]
  },
  "cash_flow_statement": {
    "title": "5 年现金流量表（单位：万元）",
    "headers": ["项目", "Year1", "Year2", "Year3", "Year4", "Year5"],
    "rows": [
      {"item": "经营活动现金流", "y1": "-2", "y2": "8", "y3": "60", "y4": "180", "y5": "370"}
    ]
  },
  "balance_sheet": {
    "title": "5 年资产负债表（单位：万元）",
    "headers": ["项目", "Year1", "Year2", "Year3", "Year4", "Year5"],
    "rows": [
      {"item": "资产总计", "y1": "50", "y2": "57", "y3": "118", "y4": "395", "y5": "765"},
      {"item": "负债合计", "y1": "5", "y2": "8", "y3": "25", "y4": "130", "y5": "230"},
      {"item": "所有者权益", "y1": "45", "y2": "49", "y3": "93", "y4": "265", "y5": "535"}
    ]
  },
  "solvency_ratios": {
    "title": "偿债能力指标",
    "headers": ["指标", "Year1", "Year2", "Year3", "Year4", "Year5"],
    "rows": [
      {"item": "流动比率", "y1": "8.0", "y2": "5.6", "y3": "4.0", "y4": "4.6", "y5": "4.8"},
      {"item": "资产负债率", "y1": "10%", "y2": "14%", "y3": "21%", "y4": "33%", "y5": "30%"}
    ]
  },
  "npv": {
    "discount_rate": "10%",
    "calculation": "NPV = -50 + 38/1.1 + 41/1.21 + ... = 772.4 万元",
    "conclusion": "NPV > 0，项目可行"
  }
}
```

### 16.16 practice_process（实践过程）

```json
"practice_process": {
  "activities": [
    {
      "figure_number": "图 31",
      "title": "项目成员组织专业性学习",
      "description": "2024 年 9 月，项目团队在指导教师闫教授带领下，组织为期 2 周的专业性学习...",
      "activity_type": "team_learning"
    }
  ],
  "cooperation_agreements": [
    {
      "partner": "河南工业大学安保科",
      "type": "学校内部",
      "content": "校园火灾防卫安全巡逻协议"
    }
  ]
}
```

### 16.17 tech_barriers（技术壁垒）

```json
"tech_barriers": {
  "patents": [
    {
      "name": "一种消防无人机用转动压紧夹持式可旋转水枪装置",
      "application_number": "CN2024XXXXXXXXXX.X",
      "application_date": "2024 年 X 月 X 日",
      "abstract": "...",
      "relation_to_project": "本专利解决 [技术问题]，是本项目 [核心模块] 的关键技术"
    }
  ],
  "inspection_reports": [
    {
      "institution": "[检测机构名称]",
      "date": "2024 年 X 月 X 日",
      "report_number": "[编号]",
      "key_metrics": ["指标 1", "指标 2", "指标 3"]
    }
  ],
  "system_verifications": [
    {
      "scenario": "[验证场景]",
      "date": "2024 年 X 月 X 日",
      "results": ["结果 1", "结果 2"],
      "screenshot_description": "[图号 + 说明]"
    }
  ]
}
```

### 16.18 完整 JSON 示例

完整 JSON 示例见 build.py 中 DEFAULT_DATA。

---

