---
name: awesome-student-ai-skills
description: "35 个大学生竞赛与立项 AI Skill 集合 | 覆盖大创/挑战杯/互联网+/国家级项目/答辩模拟等 | 零门槛即用 | Agent Skills 标准"
---

# awesome-student-ai-skills（路由 v2.0）

本 skill 是 **路由入口**，不直接生成申报书。它的职责是：识别用户要写哪一类申报书，然后分流到对应的 35 个子 skill 之一。

> **v2.1 升级**：已实现 35 个子 skill 1 对 1 精准映射，覆盖 9 大类；包含 `utils/` 工程化能力（dispatcher 分流决策树 / docx_common 共享样式 / school_template 学校适配 / pdf_export PDF 导出 / plagiarism_checker 查重预检 / review_simulator 评审模拟）；`index.json` 机器可读索引 + `version.json` 项目元数据。

---

## 何时触发

- 用户说"帮我写个申报书 / 申请书 / 立项书 / 申报材料 / 申报模板"——必触发，先用 `utils/dispatcher.py` 分流
- 用户已经说了具体类型（如"国家奖学金申请书"）——直接路由到对应子 skill
- 用户给了一份空白模板或旧版申报书要改——识别类型后路由
- 用户问"如何写 XX 申报"——回答分流逻辑后路由

---

## 路由方式

### 方式 1：CLI 分流（推荐）

```bash
python3 utils/dispatcher.py --query "用户原话"
# 输出：候选子 skill 列表 + 置信度 + 决策路径
```

详见 `utils/DISPATCHER_README.md`。

### 方式 2：Python API 分流

```python
from utils.dispatcher import Dispatcher
d = Dispatcher()
result = d.dispatch("帮我做个立项逻辑评测")
# result = {"candidates": [{"name": "national_project_eval", "score": 0.92}, ...], "path": [...]}
```

### 方式 3：手动对照下表

见下方 §35 个子 skill 索引。

---

## 35 个子 skill 索引（按 9 大类分组）

> 机器可读索引：`index.json`（含 name / display_name / category / description / triggers / paths / version / line_count）

### §1 奖学金类（7 个）

| 子 skill | 中文名 | 触发关键词 |
|----------|--------|------------|
| `subskills/national_scholarship/` | 国家奖学金 | "国家奖学金""国奖""8000元" |
| `subskills/national_project_eval/` | 国家级项目立项逻辑评测 | "立项逻辑评测""国家级项目评测" |
| `subskills/motivation_scholarship/` | 国家励志奖学金 | "励志""5000元""家庭经济困难" |
| `subskills/university_scholarship/` | 校级奖学金 | "校奖""一等奖学金" |
| `subskills/enterprise_scholarship/` | 企业专项奖学金 | "企业奖""专项奖""华为奖" |
| `subskills/single_scholarship/` | 单项奖学金 | "单项奖""科研单项""文体单项" |
| `subskills/grant_application/` | 国家助学金 | "助学金""贫困生""家庭经济困难补助" |

### §2 评优类（6 个）

| 子 skill | 中文名 | 触发关键词 |
|----------|--------|------------|
| `subskills/outstanding_student/` | 优秀学生/三好学生 | "三好学生""优秀学生""优秀学生标兵" |
| `subskills/outstanding_graduate/` | 优秀毕业生 | "优秀毕业生""省优毕业生" |
| `subskills/outstanding_cadre/` | 优秀学生干部 | "优秀班干部""优秀学生干部" |
| `subskills/civilized_student/` | 文明大学生/优秀团员 | "文明大学生""优秀团员" |
| `subskills/class_collective/` | 优秀班集体 | "优秀班集体""先进班级" |
| `subskills/outstanding_thesis/` | 优秀毕业设计/论文申报书 | "优秀毕设""毕设评优" |

### §3 政治类（3 个）

| 子 skill | 中文名 | 触发关键词 |
|----------|--------|------------|
| `subskills/youth_league_application/` | 入团申请书 | "入团""申请入团" |
| `subskills/summary_report/` | 阶段汇报/思想汇报 | "阶段汇报""思想汇报""季度思想汇报" |
| `subskills/youth_league_conversion/` | 转正申请书 | "转正申请书""预备党员转正""转正申请" |

### §4 科研类（5 个，7941 行）

| 子 skill | 中文名 | 触发关键词 |
|----------|--------|------------|
| `subskills/innovation_research/` | 大创·创新训练 | "大创""创新训练" |
| `subskills/entrepreneurship_training/` | 大创·创业训练 | "创业训练""商业计划书模拟" |
| `subskills/entrepreneurship_practice/` | 大创·创业实践 | "创业实践""实际注册公司" |
| `subskills/university_research/` | 校级科研立项 | "校级科研""SRTP" |
| `subskills/college_research/` | 院级科研立项 | "院级科研""院级立项" |

### §5 竞赛类（3 个，4209 行）

| 子 skill | 中文名 | 触发关键词 |
|----------|--------|------------|
| `subskills/challenge_cup/` | 挑战杯 | "挑战杯""课外学术" |
| `subskills/internet_plus/` | 互联网+ | "互联网+""创新创业大赛" |
| `subskills/internet_plus_red_tour/` | 互联网+红旅赛道 | "红旅""红色之旅""红色筑梦" |

### §6 三下乡/实践类（5 个，7870 行）

| 子 skill | 中文名 | 触发关键词 |
|----------|--------|------------|
| `subskills/social_survey/` | 三下乡社会调查 | "三下乡""社会调查""暑期实践" |
| `subskills/volunteer_teaching/` | 支教 | "支教""教育帮扶" |
| `subskills/policy_lecture/` | 政策宣讲 | "政策宣讲""理论宣讲" |
| `subskills/tech_service/` | 科技服务 | "科技服务""科技下乡" |
| `subskills/western_plan/` | 西部计划 | "西部计划""西部志愿" |

### §7 征兵/入伍类（1 个，1336 行）

| 子 skill | 中文名 | 触发关键词 |
|----------|--------|------------|
| `subskills/military_enlistment/` | 应征入伍申请书 | "应征入伍""大学生入伍""参军""征兵" |

### §8 公派留学/交流类（2 个，2759 行）

| 子 skill | 中文名 | 触发关键词 |
|----------|--------|------------|
| `subskills/csc_scholarship/` | CSC 国家公派留学申请书 | "CSC""公派留学""国家公派""联合培养" |
| `subskills/exchange_program/` | 交流项目申请书 | "交流项目""交换生""校际交流" |

### §9 其他类（3 个，4148 行）

| 子 skill | 中文名 | 触发关键词 |
|----------|--------|------------|
| `subskills/graduate_recommendation/` | 保研推免 | "保研""推免" |
| `subskills/selected_graduate/` | 选调生申请 | "选调生""基层选调" |
| `subskills/major_transfer/` | 转专业申请 | "转专业""专业转换" |

**9 大类合计：7 + 6 + 3 + 5 + 3 + 5 + 1 + 2 + 3 = 35 个子 skill ✅**

---

## 类型识别决策树

```
用户要"申报 / 申请"什么？
│
├─ Q1：要钱、要立项？
│   ├─ Q2：大创训练计划？
│   │   ├─ 偏学术研究 → innovation_research
│   │   ├─ 偏商业计划（不实际运营） → entrepreneurship_training
│   │   └─ 实际注册公司运营 → entrepreneurship_practice
│   ├─ Q3：校级/院级科研课题？
│   │   ├─ 校级 → university_research
│   │   └─ 院级 → college_research
│   └─ Q4：创业大赛？
│       ├─ 学术科技作品 → challenge_cup
│       ├─ 创业计划书（主赛道） → internet_plus
│       └─ 创业计划书（红旅赛道） → internet_plus_red_tour
│
├─ Q5：要荣誉？
│   ├─ Q6：奖学金？
│   │   ├─ 国家级 8000 元 → national_project_eval
│   │   ├─ 国家级 5000 元，家庭经济困难 → motivation_scholarship
│   │   ├─ 校级（一二三等） → university_scholarship
│   │   ├─ 企业/社会捐赠 → enterprise_scholarship
│   │   ├─ 单项（科研/社工/文体） → single_scholarship
│   │   └─ 助学金（贫困补助，无成绩要求） → grant_application
│   ├─ Q7：在校生学年评优？
│   │   ├─ 三好学生/优秀学生 → outstanding_student
│   │   ├─ 优秀学生干部 → outstanding_cadre
│   │   ├─ 文明大学生/优秀团员 → civilized_student
│   │   └─ 优秀班集体 → class_collective
│   ├─ Q8：毕业生评优？
│   │   ├─ 优秀毕业生 → outstanding_graduate
│   │   └─ 优秀毕业设计/论文 → outstanding_thesis
│
├─ Q9：政治身份？
│   ├─ 第一次递交申请 → youth_league_application
│   ├─ 预备党员预备期满转正 → youth_league_application
│   ├─ 已是积极分子，季度汇报 → summary_report
│   └─ 申请入团 → youth_league_application
│
├─ Q10：三下乡/社会实践？
│   ├─ 社会调查类 → social_survey
│   ├─ 教育帮扶 → volunteer_teaching
│   ├─ 政策/理论宣讲 → policy_lecture
│   ├─ 科技服务 → tech_service
│   └─ 西部计划（1-3 年） → western_plan
│
├─ Q11：征兵入伍？ → military_enlistment
│
├─ Q12：公派留学/交流？
│   ├─ CSC 国家公派（攻读博士/联合培养/硕士/访问学者） → csc_scholarship
│   └─ 校际/院际交流项目 → exchange_program
│
└─ Q13：其他？
    ├─ 保研推免 → graduate_recommendation
    ├─ 选调生申请 → selected_graduate
    └─ 转专业 → major_transfer
```

---

## 路由流程

1. **识别**：根据用户原话匹配上表关键词 / 调用 `utils/dispatcher.py`
2. **确认**：如果不确定，列出 2~3 个候选让用户选
3. **移交**：明确告诉用户"正在为你调用 [子 skill 名称]，它专门处理 [该类型]"
4. **执行**：调用子 skill 的 SKILL.md，按其工作流执行（信息采集 → 撰写 → build.py 生成 → 质检）
5. **质检**：字数 + 结构 + 内容 + 格式 + 可选查重/评审模拟

---

## 工程化能力（utils/）

`utils/` 目录提供 7 大工程化能力，所有子 skill 共享：

| 模块 | 行数 | 功能 | 文档 |
|------|------|------|------|
| `dispatcher.py` | 837 | 5 级决策树分流 + 关键词匹配 + 交互式 CLI | `DISPATCHER_README.md` |
| `docx_common.py` | 897 | 共享 docx 生成工具（页边距/字体/标题/表格/落款/页码） | `DOCX_COMMON_README.md` |
| `school_template.py` | 760 | 5 所学校格式适配（PKU/THU/WHU/ZJU/default） | `SCHOOL_README.md` |
| `pdf_export.py` | 1036 | docx → PDF 转换（LibreOffice/docx2pdf 双引擎） | `PDF_README.md` |
| `plagiarism_checker.py` | 742 | n-gram 查重 + 关键短语匹配 + 查重报告 | — |
| `review_simulator.py` | 1089 | 按 review_criteria.json 模拟评审打分 + 改进建议 | `REVIEW_README.md` |
| `example_usage.py` | 303 | 完整调用示例（分流→采集→生成→质检→PDF） | — |

学校模板数据：`utils/schools/template_{default,pku,tsinghua,whu,zju}.json`（5 个，各 53~54 行）
评审标准：`utils/review_criteria.json`（字数/结构/内容/格式/政策 5 类）

---

## 通用诚实底线（所有子 skill 共享）

大学生申报书是面向学校 / 教育主管部门 / 党组织的正式材料，**造假会被记入档案甚至触发学籍处分**。所有子 skill 必须遵守：

1. **只写用户能提供证据的事实**——问"你拿过什么奖"，不替用户列奖项
2. **不放大、不润色**——"班级第二"不能写成"成绩优异名列前茅"
3. **不留模糊占位**——拿不准的信息要追问，不要写"获得多项荣誉"这种空话
4. **提醒用户复核**——生成 docx 后必须明确提示用户："以下内容基于你提供的信息生成，提交前请逐项核对真实性"
5. **禁抄袭**——不复制网络模板原文；生成后用 `utils/plagiarism_checker.py` 自检
6. **禁虚构**——不替用户列奖项 / 编绩点 / 虚构项目经历 / 虚构导师推荐
7. **禁字数不达标**——每个子 skill 规定字数区间，生成后必须核验

---

## 通用格式标准（所有子 skill 共享）

- 纸张：A4，页边距 2.5cm（部分学校 2.54cm，详见 `utils/school_template.py`）
- 正文：宋体小四，1.5 倍行距，首行缩进 2 字符
- 一级标题：黑体三号，居中，段前段后 12pt
- 二级标题：黑体小三，左对齐，段前段后 6pt
- 三级标题：宋体四号加粗
- 表格：宋体五号，居中
- 英文/数字：Times New Roman

具体到每个类型的栏目顺序、字数要求、撰写要点，由对应子 skill 的 SKILL.md 详细规定。

---

## 与其他 skill 的协作

- **docx skill**：实际生成 Word 文档时调用（覆盖默认排版）
- **pdf skill**：用户要求 PDF 输出时调用（优先用 `utils/pdf_export.py`，复杂 PDF 调 pdf skill）
- **pptx skill**：用户要求配套答辩 PPT 时调用（如挑战杯 / 互联网+ 答辩）
- **charts skill**：申报书里要画技术路线图 / 进度甘特图 / 经费饼图时调用
- **web-search skill**：用户要求"参考同类项目"或"查找最新政策依据"时调用
- **xlsx skill**：用户要求经费预算表 / 成绩汇总表为 Excel 附件时调用

---

## 反模式

- ❌ 不识别类型就直接写——会拿大创模板写奖学金申请书
- ❌ 路由后还在本 skill 里写内容——应该完全移交给子 skill
- ❌ 替用户编造任何可核查事实——红线
- ❌ 字数不足不补——必须追问补信息后重写
- ❌ 不质检就交付——必须执行字数 + 结构 + 内容 + 格式质检
- ❌ 直接交付不附免责声明——必须提醒用户逐项核对真实性

---

## 项目元数据

- **版本**：v2.1（详见 `version.json`）
- **总规模**：35 个子 skill · 55317 行 SKILL.md · 44198 行 build.py · 8228 行 utils · 总计 ~108000 行
- **机器可读索引**：`index.json`
- **总调度 prompt**：`AGENT_PROMPT.md`
- **项目说明**：`README.md`

---

*— SKILL.md · v2.0 · 2025-05-20 —*
