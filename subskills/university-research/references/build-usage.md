# 十、docx 生成调用方式

> 从 `subskills/university-research/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要调用 build.py 生成文档、或排查生成参数时。

### 10.1 命令行用法

```bash
# 使用数据 JSON 生成
python build.py --data data.json --out output.docx

# 使用内置示例数据生成演示文档
python build.py --demo --out demo.docx

# 指定字数版本（standard / enhanced / peak）
python build.py --data data.json --out output.docx --version enhanced
```

### 10.2 JSON 字段说明（v2.1 完整版）

```json
{
  "project_name": "大学生课堂手机使用行为干预研究",
  "leader_name": "张明",
  "leader_id": "2022123456",
  "leader_gender": "男",
  "leader_major": "教育技术学 2022 级",
  "leader_phone": "138XXXXXXXX",
  "leader_email": "zhangming@xxx.edu.cn",
  "advisor_name": "李华教授",
  "advisor_title": "教授",
  "advisor_research": "教育技术学、学习行为分析",
  "advisor_phone": "139XXXXXXXX",
  "college": "教育学院",
  "apply_date": "2025 年 3 月 15 日",
  "word_version": "enhanced",

  "basic_info": {
    "research_type": "应用研究",
    "discipline": "0401 教育学",
    "duration": "2025 年 4 月 — 2026 年 3 月（共 12 个月）",
    "budget": "3500",
    "project_source": "自主选题"
  },

  "team_members": [
    {"name": "李四", "id": "2022123457", "major": "教育技术学 2022 级",
     "role": "问卷设计+数据采集", "phone": "139XXXXXXXX"},
    {"name": "王五", "id": "2022123458", "major": "心理学 2022 级",
     "role": "数据分析+论文撰写", "phone": "137XXXXXXXX"}
  ],

  "background": [
    "时代背景：2024 年教育部《关于进一步加强大学生课堂管理的指导意见》明确提出『严禁课堂手机使用』...",
    "现实痛点：调研本校 5 个学院 12 个班级发现...",
    "研究缺口：已有研究多停留在『现象描述』层面...",
    "课题意义：理论上探索行为干预理论..."
  ],

  "policy_citations": [
    {"issuer": "教育部", "doc_no": "教高〔2024〕3 号",
     "title": "关于进一步加强大学生课堂管理的指导意见",
     "publish_date": "2024-03-15",
     "key_excerpt": "严禁课堂手机使用，构建良好学习生态",
     "relevance": "直接对应本课题研究场景"},
    {"issuer": "国务院", "doc_no": "",
     "title": "关于全面深化新时代教师队伍建设改革的意见",
     "publish_date": "2023-12-20",
     "key_excerpt": "提升教师课堂管理能力",
     "relevance": "本课题为教师提供干预工具"}
  ],

  "research_status": [
    "国内研究现状：张华等（2022）对 5 所高校 1200 名大学生调查发现...",
    "国外研究现状：Smith et al. (2020) 对美国 3 所大学 800 名学生研究发现...",
    "综合评述：已有研究存在三个共性问题..."
  ],

  "literature_review": [
    {"idx": 1, "authors": "张华等", "year": "2022",
     "view": "课堂手机使用率达 75.8%",
     "limit": "仅描述现象未提出干预方案",
     "lang": "zh"},
    {"idx": 8, "authors": "Smith et al.", "year": "2020",
     "view": "『自律契约』干预 6 周后使用率从 82% 降至 61%",
     "limit": "仅美国样本，未跨文化验证",
     "lang": "en"}
  ],

  "scientific_challenges": [
    {"title": "三维干预协同机制设计中的混杂变量控制",
     "description": "在课堂手机使用行为干预研究中，『契约+提醒+辅导员协同』三维干预的协同效应识别是核心难题[3][5]...",
     "sub_challenges": [
       {"name": "三维干预的协同效应识别", "detail": "传统的单维干预研究将各维度视为独立变量..."},
       {"name": "混杂变量的倾向性得分匹配", "detail": "学生自控力、教师授课风格是影响干预效果的关键混杂变量..."}
     ]}
  ],

  "research_goal": "总目标：开发能将课堂手机使用率降低 ≥30 个百分点...",
  "research_content": [
    "干预方案设计：基于行为干预理论设计『契约+提醒+协同』三维方案...",
    "试点实施：在 3 所高校 6 个班级共 600 名学生中开展 12 周试点...",
    "效果评估：采用前后测+跟踪测设计...",
    "跟踪研究：干预结束后 6 个月进行跟踪测..."
  ],
  "key_problems": [
    "三维干预中各维度的协同机制设计...",
    "准实验设计中混杂变量的控制...",
    "干预长期效果的衰减规律与保持策略..."
  ],

  "method_comparison": {
    "title": "表 1 主流课堂手机干预方法对比表",
    "dimensions": ["技术特点", "优势", "劣势", "适用场景", "效率", "长期效果"],
    "methods": [
      {"name": "契约法[3]", "values": ["学生签订行为契约", "学生自主性强", "依赖学生自控力", "自控力较强的本科生", "短期降 15~22%", "6 月保持率 40~55%"]},
      {"name": "提醒法[5]", "values": ["课前自动提醒", "实时性强", "容易产生适应性", "中小型课堂", "短期降 18~25%", "6 月保持率 25~35%"]},
      {"name": "屏蔽法[4]", "values": ["硬件屏蔽信号", "立即生效", "法律伦理争议大", "涉密/特殊考场", "短期降 80%+", "撤销即失效"]}
    ],
    "conclusion": "基于上表，本课题选用『契约+提醒+辅导员协同』三维组合方案..."
  },

  "tech_route": "总体技术路线分 4 阶段（见图 2）：...",
  "tech_roadmap": [
    {"fig_no": "图 1", "title": "项目研究内容及其相互关系",
     "description": "总目标 → 研究内容 1.1（方案设计）→ 研究内容 1.2（试点实施）→ 研究内容 1.3（效果评估）→ 研究内容 1.4（长期跟踪）",
     "nodes": ["总目标：开发本土化干预方案", "研究内容 1.1 干预方案设计", "研究内容 1.2 试点实施", "研究内容 1.3 效果评估与跟踪", "研究内容 1.4 长期跟踪研究"]},
    {"fig_no": "图 2", "title": "项目技术路线图",
     "description": "阶段 1 准备（2025.04-05）→ 阶段 2 实施（2025.06-09）→ 阶段 3 分析（2025.10-11）→ 阶段 4 总结（2025.12-2026.03）",
     "nodes": ["阶段 1：准备阶段（产出综述+方案）", "阶段 2：试点实施（产出原始数据）", "阶段 3：数据分析（产出分析报告）", "阶段 4：跟踪研究（产出跟踪报告+论文）"]}
  ],

  "formulas": [
    {"idx": 1, "formula": "P(y=1|x) = σ(w·x+b) = 1 / (1 + exp(-(w·x+b)))",
     "variables": "y∈{0,1} 表示干预后是否达成行为改变；x 为特征向量；w 为权重向量；b 为偏置项；σ(·) 为 Sigmoid 函数",
     "purpose": "用于干预效果预测"}
  ],

  "methods": [
    "文献研究法：系统梳理国内外 50+ 篇相关文献...",
    "准实验法：采用『干预组-对照组』前后测设计...",
    "问卷调查法：开发课堂手机使用行为量表...",
    "深度访谈法：干预后对 30 名学生 + 6 名教师进行半结构化访谈。"
  ],
  "data_source": "数据来源：3 所合作高校 6 个班级共 600 名学生...",

  "innovations": [
    "方法创新。已有干预研究多采用单一手段...",
    "数据创新。已有研究样本量普遍 <200、周期 <1 月..."
  ],

  "social_benefits": [
    {"metric": "课堂手机使用率", "baseline": "78.3%", "expected": "≤48%", "improvement": "降低 ≥30 个百分点"},
    {"metric": "课堂抬头率", "baseline": "52%", "expected": "≥80%", "improvement": "提升 ≥28 个百分点"},
    {"metric": "学习成绩平均分", "baseline": "75.2 分", "expected": "≥82 分", "improvement": "提升 ≥7 分"},
    {"metric": "自我效能感得分", "baseline": "3.2/5", "expected": "≥4.0/5", "improvement": "提升 ≥0.8 分"},
    {"metric": "教师课堂管理满意度", "baseline": "60%", "expected": "≥85%", "improvement": "提升 ≥25 个百分点"}
  ],

  "team_foundation": "团队 3 名成员已修读《教育心理学》...",
  "advisor_foundation": "指导教师李华教授主持全国教育科学规划课题 1 项...",
  "lab_condition": "实验室配备眼动仪 Tobii Pro X3-120...",

  "expected_outcomes": [
    "中文核心期刊论文 1 篇（拟投《高等教育研究》）",
    "调研报告 1 份（约 1.5 万字）",
    "干预方案手册 1 套（含 12 项干预动作操作指南）"
  ],

  "project_schedule": [
    {"phase": "第一阶段 准备", "time": "2025.04-05（2 月）",
     "work": "文献综述 50 篇；方案设计；问卷开发与预试；任务分工",
     "output": "综述 1 份 + 方案 1 份 + 问卷 1 套"},
    {"phase": "第二阶段 实施", "time": "2025.06-09（4 月）",
     "work": "3 校 6 班 600 人 12 周干预；实施记录与数据采集；中期检查与调整",
     "output": "实施记录 + 原始数据"},
    {"phase": "第三阶段 分析", "time": "2025.10-11（2 月）",
     "work": "SPSS + Mplus 统计分析；干预效果评估；论文初稿撰写",
     "output": "分析报告 1 份 + 论文初稿"},
    {"phase": "第四阶段 总结", "time": "2025.12-2026.03（4 月）",
     "work": "6 个月后跟踪测；论文修改与投稿；结题材料整理",
     "output": "跟踪报告 1 份 + 论文 1 篇 + 结题报告"}
  ],

  "schedule": [
    {"phase": "准备", "time": "2025.04-05", "work": "文献综述 50 篇、方案设计", "output": "综述 1 份 + 方案 1 份"}
  ],

  "budget_items": [
    {"item": "资料费", "amount": "350", "basis": "图书 5 本 × 50 元 + 数据库订阅 100 元"},
    {"item": "调研费", "amount": "1200", "basis": "3 校实地调研 × 400 元"},
    {"item": "材料费", "amount": "600", "basis": "问卷印刷 600 份 × 1 元"},
    {"item": "会议费", "amount": "500", "basis": "参加教育学会议 1 次"},
    {"item": "印刷费", "amount": "450", "basis": "论文版面费 400 + 报告印刷 50"},
    {"item": "其他", "amount": "400", "basis": "礼品感谢 30 份 × 10 元 + 数据备份 U 盘 100 元"}
  ],
  "budget_total": "3500",

  "references": [
    {"ref_type": "journal", "authors": "张华, 李明, 王芳", "title": "大学生课堂手机使用行为研究",
     "journal": "高等教育研究", "year": "2022", "volume": "43", "issue": "(5)", "pages": "78-86"},
    {"ref_type": "conference", "authors": "Kumar S, Lee H", "title": "Comparative study of four classroom phone interventions",
     "conference": "Proceedings of the 2022 International Conference on Educational Technology",
     "city": "New York", "publisher": "ACM", "year": "2022", "pages": "215-222"},
    {"ref_type": "thesis", "authors": "Brown A", "title": "Behavioral economics approaches to classroom management",
     "city": "Stanford", "school": "Stanford University", "year": "2023"},
    {"ref_type": "web", "authors": "教育部", "title": "关于进一步加强大学生课堂管理的指导意见",
     "publish_date": "2024-03-15", "access_date": "2025-02-10",
     "url": "http://www.moe.gov.cn/xxx", "is_government": true},
    {"ref_type": "book", "authors": "Bandura A", "title": "Social learning theory",
     "city": "Englewood Cliffs", "publisher": "Prentice-Hall", "year": "1977"}
  ]
}
```

### 10.3 输出路径

输出路径默认为当前目录下的 `output.docx`，可通过 `--out` 参数指定：
```bash
python build.py --data data.json --out /path/to/output.docx
```

---

