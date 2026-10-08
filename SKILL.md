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
# 输出：候选子 skill 列表、关键词匹配分数和加载路径
```

详见 `utils/DISPATCHER_README.md`。

### 方式 2：Python API 分流

```python
from utils.dispatcher import Dispatcher
d = Dispatcher()
candidates = d.dispatch("国家级项目立项逻辑评测")
if candidates:
    top = candidates[0]
    print(top["name"], top["score"])
    print(top["skill_md_path"])
```

`dispatch()` 返回候选字典列表；未命中时返回空列表。每项包含 `name`、`score`、`matched`、`skill_md_path` 和 `build_py_path` 等字段。`score` 是整数关键词匹配分数，不是概率；加载路径相对于仓库根目录。

### 方式 3：手动对照下表

见下方 §35 个子 skill 索引。

---

## 35 个子 skill 索引（按 9 大类分组）

> 机器可读索引：`index.json`（含 name / display_name / category / description / triggers / paths / version / line_count）

### §1 奖学金类（6 个）

| 子 skill | 中文名 | 触发关键词 |
|----------|--------|------------|
| `subskills/national-scholarship/` | 国家奖学金 | "国家奖学金""国奖""10000元" |
| `subskills/motivation-scholarship/` | 国家励志奖学金 | "励志""6000元""家庭经济困难" |
| `subskills/university-scholarship/` | 校级奖学金 | "校奖""一等奖学金" |
| `subskills/enterprise-scholarship/` | 企业专项奖学金 | "企业奖""专项奖""华为奖" |
| `subskills/single-scholarship/` | 单项奖学金 | "单项奖""科研单项""文体单项" |
| `subskills/grant-application/` | 国家助学金 | "助学金""贫困生""家庭经济困难补助" |

### §2 评优类（6 个）

| 子 skill | 中文名 | 触发关键词 |
|----------|--------|------------|
| `subskills/outstanding-student/` | 优秀学生/三好学生 | "三好学生""优秀学生""优秀学生标兵" |
| `subskills/outstanding-graduate/` | 优秀毕业生 | "优秀毕业生""省优毕业生" |
| `subskills/outstanding-cadre/` | 优秀学生干部 | "优秀班干部""优秀学生干部" |
| `subskills/civilized-student/` | 文明大学生/优秀团员 | "文明大学生""优秀团员" |
| `subskills/class-collective/` | 优秀班集体 | "优秀班集体""先进班级" |
| `subskills/outstanding-thesis/` | 优秀毕业设计/论文申报书 | "优秀毕设""毕设评优" |

### §3 政治类（3 个）

| 子 skill | 中文名 | 触发关键词 |
|----------|--------|------------|
| `subskills/youth-league-application/` | 入团申请书 | "入团""申请入团" |
| `subskills/summary-report/` | 阶段汇报/思想汇报 | "阶段汇报""思想汇报""季度思想汇报" |
| `subskills/youth-league-conversion/` | 转正申请书 | "转正申请书""预备党员转正""转正申请" |

### §4 科研类（6 个）

| 子 skill | 中文名 | 触发关键词 |
|----------|--------|------------|
| `subskills/national-project-eval/` | 国家级项目立项逻辑评测 | "国家级项目立项逻辑评测""国家级项目评测" |
| `subskills/innovation-research/` | 大创·创新训练 | "大创""创新训练" |
| `subskills/entrepreneurship-training/` | 大创·创业训练 | "创业训练""商业计划书模拟" |
| `subskills/entrepreneurship-practice/` | 大创·创业实践 | "创业实践""实际注册公司" |
| `subskills/university-research/` | 校级科研立项 | "校级科研""SRTP" |
| `subskills/college-research/` | 院级科研立项 | "院级科研""院级立项" |

### §5 竞赛类（3 个，4209 行）

| 子 skill | 中文名 | 触发关键词 |
|----------|--------|------------|
| `subskills/challenge-cup/` | 挑战杯 | "挑战杯""课外学术" |
| `subskills/internet-plus/` | 互联网+ | "互联网+""创新创业大赛" |
| `subskills/internet-plus-red-tour/` | 互联网+红旅赛道 | "红旅""红色之旅""红色筑梦" |

### §6 三下乡/实践类（5 个，7870 行）

| 子 skill | 中文名 | 触发关键词 |
|----------|--------|------------|
| `subskills/social-survey/` | 三下乡社会调查 | "三下乡""社会调查""暑期实践" |
| `subskills/volunteer-teaching/` | 支教 | "支教""教育帮扶" |
| `subskills/policy-lecture/` | 政策宣讲 | "政策宣讲""理论宣讲" |
| `subskills/tech-service/` | 科技服务 | "科技服务""科技下乡" |
| `subskills/western-plan/` | 西部计划 | "西部计划""西部志愿" |

### §7 征兵/入伍类（1 个，1336 行）

| 子 skill | 中文名 | 触发关键词 |
|----------|--------|------------|
| `subskills/military-enlistment/` | 应征入伍申请书 | "应征入伍""大学生入伍""参军""征兵" |

### §8 公派留学/交流类（2 个，2759 行）

| 子 skill | 中文名 | 触发关键词 |
|----------|--------|------------|
| `subskills/csc-scholarship/` | CSC 国家公派留学申请书 | "CSC""公派留学""国家公派""联合培养" |
| `subskills/exchange-program/` | 交流项目申请书 | "交流项目""交换生""校际交流" |

### §9 其他类（3 个，4148 行）

| 子 skill | 中文名 | 触发关键词 |
|----------|--------|------------|
| `subskills/graduate-recommendation/` | 保研推免 | "保研""推免" |
| `subskills/selected-graduate/` | 选调生申请 | "选调生""基层选调" |
| `subskills/major-transfer/` | 转专业申请 | "转专业""专业转换" |

**9 大类合计：6 + 6 + 3 + 6 + 3 + 5 + 1 + 2 + 3 = 35 个子 skill ✅**

---

## 类型识别决策树

```
用户要"申报 / 申请"什么？
│
├─ Q1：科研立项或立项逻辑评测？
│   ├─ Q2：大创训练计划？
│   │   ├─ 偏学术研究 → innovation-research
│   │   ├─ 偏商业计划（不实际运营） → entrepreneurship-training
│   │   └─ 实际注册公司运营 → entrepreneurship-practice
│   ├─ Q3：校级/院级科研课题？
│   │   ├─ 校级 → university-research
│   │   └─ 院级 → college-research
│   └─ 国家级项目立项逻辑评测 → national-project-eval
│
├─ Q4：学科竞赛？
│   ├─ 学术科技作品 → challenge-cup
│   ├─ 创业计划书（主赛道） → internet-plus
│   └─ 创业计划书（红旅赛道） → internet-plus-red-tour
│
├─ Q5：要荣誉？
│   ├─ Q6：奖学金？
│   │   ├─ 国家奖学金 10000 元 → national-scholarship
│   │   ├─ 国家励志奖学金 6000 元，家庭经济困难 → motivation-scholarship
│   │   ├─ 校级（一二三等） → university-scholarship
│   │   ├─ 企业/社会捐赠 → enterprise-scholarship
│   │   ├─ 单项（科研/社工/文体） → single-scholarship
│   │   └─ 助学金（贫困补助，无成绩要求） → grant-application
│   ├─ Q7：在校生学年评优？
│   │   ├─ 三好学生/优秀学生 → outstanding-student
│   │   ├─ 优秀学生干部 → outstanding-cadre
│   │   ├─ 文明大学生/优秀团员 → civilized-student
│   │   └─ 优秀班集体 → class-collective
│   ├─ Q8：毕业生评优？
│   │   ├─ 优秀毕业生 → outstanding-graduate
│   │   └─ 优秀毕业设计/论文 → outstanding-thesis
│
├─ Q9：政治身份？
│   ├─ 申请入团 → youth-league-application
│   ├─ 转正申请 → youth-league-conversion
│   └─ 阶段汇报/思想汇报 → summary-report
│
├─ Q10：三下乡/社会实践？
│   ├─ 社会调查类 → social-survey
│   ├─ 教育帮扶 → volunteer-teaching
│   ├─ 政策/理论宣讲 → policy-lecture
│   ├─ 科技服务 → tech-service
│   └─ 西部计划（1-3 年） → western-plan
│
├─ Q11：征兵入伍？ → military-enlistment
│
├─ Q12：公派留学/交流？
│   ├─ CSC 国家公派（攻读博士/联合培养/硕士/访问学者） → csc-scholarship
│   └─ 校际/院际交流项目 → exchange-program
│
└─ Q13：其他？
    ├─ 保研推免 → graduate-recommendation
    ├─ 选调生申请 → selected-graduate
    └─ 转专业 → major-transfer
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
