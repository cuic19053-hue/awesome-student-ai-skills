# 查重预检 + 评审模拟器 使用说明

> 本目录提供"查重预检"与"评审模拟器"两个工程化模块，让学生在提交申报书前自检原创性与多维评分，降低被一票否决的风险。

---

## 一、文件清单

| 文件 | 行数 | 说明 |
|------|------|------|
| `review_criteria.json` | — | 30 个子 skill 的评审标准配置（维度/权重/细则/否决项/等级） |
| `plagiarism_checker.py` | ~740 | 查重预检核心模块 + CLI |
| `review_simulator.py` | ~1080 | 评审模拟器核心 + CLI + 多人对比 |
| `REVIEW_README.md` | 本文件 | 使用说明 |

---

## 二、查重预检（plagiarism_checker.py）

### 2.1 功能

- 检测申报书文本与**网络模板特征句库**（30 个子 skill × 4-7 条）的相似度
- 检测与**党政原文金句库**（10 条）的雷同，连续 ≥ 50 字直接判定 D 级
- 输出查重报告：整体相似度 / 最高单段相似度 / 命中段落定位 / 修改建议
- 输出等级：A（原创）/ B（轻度雷同）/ C（中度雷同）/ D（严重雷同，一票否决）

### 2.2 核心函数

```python
from plagiarism_checker import check_plagiarism, ngram_similarity, find_longest_common_substring, highlight_plagiarism

# 主查重函数
report = check_plagiarism(text="本人自入学以来...", skill_name="national_project_eval")
print(report.overall_similarity)   # 0.235
print(report.grade)                # 'C' / 'D' / ...
print(report.passed)               # True / False
print(report.suspected_segments)   # [{'segment': ..., 'similarity': ..., 'suggestion': ...}, ...]

# N-gram 相似度
sim = ngram_similarity("本人自入学以来", "本人自入学以来始终")  # 0-1

# 最长公共子串
lcs, length = find_longest_common_substring("本人自入学以来", "本人自入学以来始终")

# 高亮疑似抄袭段
highlighted = highlight_plagiarism(text, threshold=0.3)  # 返回带 <<...>> 标记的文本
```

### 2.3 CLI 用法

```bash
# 列出所有支持的子 skill
python plagiarism_checker.py --list-skills

# 检测单段文本
python plagiarism_checker.py \
    --text "我志愿加入中国共产党，拥护党的纲领..." \
    --skill youth_league_application

# 检测文件 + 输出 JSON 报告
python plagiarism_checker.py \
    --file input.txt \
    --skill national_project_eval \
    --json \
    --out report.json

# 输出高亮标注文本
python plagiarism_checker.py \
    --file input.txt \
    --skill youth_league_application \
    --highlight \
    --out highlighted.txt

# 跳过党政原文比对（仅与网络模板对比）
python plagiarism_checker.py --text "..." --skill motivation_scholarship --no-party
```

### 2.4 等级判定规则

| 等级 | 触发条件 | 是否通过 |
|------|---------|---------|
| A | overall < 15% 且 max < 40% | ✅ |
| B | overall < 30% 且 max < 60% | ✅ |
| C | overall < 50% 且 max < 80% | ❌ |
| D | overall ≥ 50% 或 max ≥ 80% 或党政原文连续 ≥ 50 字 | ❌（一票否决） |

### 2.5 模板特征句库覆盖

`TEMPLATE_LIBRARY` 覆盖以下 30 个子 skill：

national_project_eval, motivation_scholarship, university_scholarship, enterprise_scholarship,
single_scholarship, innovation_research, entrepreneurship_training, entrepreneurship_practice,
challenge_cup, internet_plus, graduate_recommendation, outstanding_graduate,
youth_league_application, summary_report, youth_league_application, college_research,
university_research, social_survey, outstanding_student, civilized_student,
outstanding_cadre, youth_league_application, grant_application, western_plan,
volunteer_teaching, tech_service, selected_graduate, policy_lecture,
class_collective, major_transfer

---

## 三、评审模拟器（review_simulator.py）

### 3.1 功能

- 多维度评分（按 skill 类型动态加载 `review_criteria.json` 中的评审标准）
- 维度示例：思想品德 / 学业表现 / 创新能力 / 实践经历 / 材料规范 / 团队 / 学术价值 / 家庭经济 等
- 自动检查硬门槛（GPA 排名 / 必修课不及格 / 违纪记录 / 党员身份 / 公司注册 等）
- 自动检查一票否决项（字数下限 / 必引理论 / 查重率 > 30% 等）
- 集成查重预检（自动调用 `plagiarism_checker`）
- 输出评审报告 docx（含评分表 / 评语 / 优势 / 不足 / 改进建议）
- 多人对比排序

### 3.2 核心类

```python
from review_simulator import ReviewSimulator, compare_applicants

sim = ReviewSimulator(
    skill_name="national_project_eval",
    application_text="本人自入学以来...",
    applicant_data={
        "name": "张三",
        "gpa_rank_percent": 5,
        "comprehensive_rank_percent": 8,
        "english_level": "CET-6",
        "is_party_member": True,
        "papers": [{"level": "SCI", "author_order": 1}],
        "competitions": [{"level": "国家级", "award": "一等奖"}],
        "volunteer_hours": 80,
        "cadre_positions": [{"position": "班长", "tenure_months": 24, "level": "院级"}],
    },
)

result = sim.simulate_review()
print(result.total_score)  # 87.05
print(result.grade)        # 'B'
print(result.passed)       # True
print(result.dimensions)   # [DimensionScore(...), ...]
print(result.veto_triggered)  # []（无否决）
print(result.improvements)    # 改进建议

# 生成 docx 报告
sim.generate_review_report("/tmp/report.docx")
```

### 3.3 申请人数据字段约定

`applicant_data` 推荐字段（按 skill 不同需提供不同子集）：

| 字段 | 类型 | 适用 skill | 说明 |
|------|------|-----------|------|
| `name` | str | 全部 | 申请人姓名 |
| `gpa_rank_percent` | float | 学业类 | GPA 排名百分比（如 5 = 前 5%） |
| `comprehensive_rank_percent` | float | 国奖/励志 | 综合排名百分比 |
| `english_level` | str | 全部 | CET-4 / CET-6 / IELTS-7 / TOEFL-100 |
| `english_qualified` | bool | 保研推免 | 英语是否达标 |
| `is_party_member` | bool | 政治类/选调 | 是否党员 |
| `is_probationary_member` | bool | 政治类 | 是否预备党员 |
| `is_activist` | bool | 政治类 | 是否优秀团员/积极分子 |
| `is_league_member` | bool | 政治类 | 是否团员 |
| `is_graduate` | bool | 西部计划 | 是否应届毕业生 |
| `is_student_cadre` | bool | 选调/优秀干部 | 是否学生干部 |
| `has_failed_required` | bool | 学业类 | 必修课是否有不及格 |
| `has_discipline_record` | bool | 全部 | 是否有违纪记录 |
| `poverty_registered` | bool | 励志/助学金 | 是否通过家庭经济困难认定 |
| `poverty_level` | str | 励志/助学金 | 一般/困难/特困 |
| `company_registered` | bool | 创业实践 | 公司是否已注册 |
| `operation_months` | int | 创业实践 | 公司运营月数 |
| `papers` | list[dict] | 科研类 | `[{"level": "SCI/EI/CSSCI/核心", "author_order": 1}]` |
| `competitions` | list[dict] | 全部 | `[{"level": "国际/国家级/省级", "award": "一等奖"}]` |
| `patents` | list[dict] | 科研类 | `[{"type": "发明", "inventor_order": 1}]` |
| `innovation_projects` | list[dict] | 大创/科研 | `[{"level": "国家级/省级/校级"}]` |
| `volunteer_hours` | int | 全部 | 志愿服务时长 |
| `cadre_positions` | list[dict] | 干部类 | `[{"position": "班长", "tenure_months": 24, "level": "校级/院级"}]` |
| `social_practice` | list[dict] | 全部 | `[{"award": "省级优秀"}]` |
| `advisor` | str | 大创/科研 | 指导教师姓名 |
| `team_members` | list[dict] | 大创/科研 | `[{"discipline": "计算机"}]` |
| `industry_match` | bool | 企业奖学金 | 职业规划是否与目标行业匹配 |
| `internship_relevant` | bool | 企业奖学金 | 是否有相关实习经历 |
| `_required_fields_missing` | list[str] | 全部 | 缺失的必填字段名 |

### 3.4 CLI 用法

```bash
# 列出所有支持的子 skill
python review_simulator.py --list-skills

# 单人评审（控制台输出）
python review_simulator.py \
    --skill national_project_eval \
    --data applicant.json \
    --text-file text.txt

# 单人评审 + 输出 docx 报告
python review_simulator.py \
    --skill national_project_eval \
    --data applicant.json \
    --text-file text.txt \
    --out report.docx

# 单人评审 + 输出 JSON
python review_simulator.py \
    --skill national_project_eval \
    --data applicant.json \
    --text-file text.txt \
    --json --out report.json

# 多人对比排序
python review_simulator.py \
    --compare applicants.json \
    --out ranking.json
```

`applicants.json` 格式：

```json
[
  {
    "skill_name": "national_project_eval",
    "application_text": "本人在过去一学年中...",
    "applicant_data": {"name": "甲同学", "gpa_rank_percent": 5, "comprehensive_rank_percent": 7, ...}
  },
  {
    "skill_name": "national_project_eval",
    "application_text": "...",
    "applicant_data": {"name": "乙同学", ...}
  }
]
```

### 3.5 评分等级

| 等级 | 分数区间 | 含义 | 通过 |
|------|---------|------|------|
| A | ≥ 90 | 优（强烈推荐通过） | ✅ |
| B | 80-89 | 良（建议通过） | ✅ |
| C | 70-79 | 中（待定/有保留通过） | ❌ |
| D | < 70 | 差（不建议通过） | ❌ |

**特别规则**：触发任一一票否决项时，等级直接降为 D，总分封顶 59.99。

---

## 四、review_criteria.json 结构说明

```json
{
  "_meta": {
    "version": "1.0.0",
    "grade_scale": {"A": "优 (90-100)", "B": "良 (80-89)", ...},
    "global_veto": ["查重率 > 30%", ...]
  },
  "national_project_eval": {
    "name": "国家奖学金",
    "max_score": 100,
    "threshold_pass": 85,
    "hard_gates": {
      "gpa_rank_top": "10%",
      "comprehensive_rank_top": "10%",
      ...
    },
    "dimensions": [
      {"name": "思想品德", "weight": 15, "max": 15, "criteria": "..."},
      {"name": "学业表现", "weight": 40, "max": 40, "criteria": "..."},
      ...
    ],
    "veto_items": ["学习成绩排名或综合排名 > 10%...", ...],
    "breakthrough_channels": ["排名前 10%-30% 但有..."]
  },
  ...
}
```

每个 skill 必含字段：
- `name`：中文名
- `max_score`：满分（一般为 100）
- `threshold_pass`：通过线
- `hard_gates`：硬门槛（客观准入条件）
- `dimensions`：评审维度列表，每个含 `name` / `weight` / `max` / `criteria`
- `veto_items`：一票否决项列表

部分 skill 还含：
- `breakthrough_channels`：破格通道（如国奖前 10%-30% 破格 7 类）

---

## 五、与各子 skill 集成建议

各子 skill 的 `build.py` 可在生成 docx 后调用本模块做自检：

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'utils'))
from review_simulator import ReviewSimulator

# 生成完 docx 后，从 data + 生成的文本提取做模拟评审
sim = ReviewSimulator(skill_name="national_project_eval",
                     application_text=full_text,
                     applicant_data=data)
result = sim.simulate_review()
if not result.passed:
    print("⚠️ 模拟评审未通过，建议根据改进建议修改：")
    for imp in result.improvements:
        print(f"  - {imp}")
```

---

## 六、依赖

- Python ≥ 3.8
- 标准库：`argparse` / `json` / `re` / `os` / `sys` / `dataclasses`
- 可选（生成 docx 报告）：`python-docx`（未安装时自动降级为 txt）

---

## 七、版本

- v1.0.0（2025-06-15）— 首版发布，覆盖 30 个子 skill，集成查重 + 评审 + 多人对比。
