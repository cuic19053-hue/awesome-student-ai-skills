# Dispatcher 使用说明 (DISPATCHER_README)

> 模块：`utils/dispatcher.py`
> 项目：`awesome-student-ai-skills`
> 版本：v2.0（T40 引入）
> 最后更新：2025-05-20
> 覆盖子 skill 数：35 个，分为 9 大类

本目录下 `dispatcher.py` 是「大学生申报书制作 skill」的**分流决策树**入口，配套
`../index.json`（机器可读索引）与 `../version.json`（版本元数据）使用。本文档说明
何时用、怎么用、CLI 用法、Python API 用法、决策树结构、自检与扩展。

---

## 1. 何时用

当用户说出以下任意一种意图时，**强烈建议**先调用本 dispatcher 做分流，再交给具体子 skill：

- "我要申报 X" / "我想申请 X" / "帮我写 X 申请书"
- "三下乡立项" / "大创申报" / "保研推免" / "入团" / "评优" / "国奖" 等模糊词
- "我是大学生，要交一份 X"

当前项目下挂 35 个子 skill，覆盖 9 大类，单凭肉眼选择难度大；dispatcher 通过
**关键词匹配**或**5 级交互式决策树**，可在 1 次输入或 3~5 次问答内定位 top 3 候选。

---

## 2. 文件位置约定

```
awesome-student-ai-skills/
├── index.json              ← 机器可读索引（30 个子 skill 元数据）
├── version.json            ← 项目版本元数据（v2.0 / 总行数 45024）
├── SKILL.md                ← 父 skill 说明
├── subskills/
│   ├── national_project_eval/
│   │   ├── SKILL.md
│   │   └── build.py
│   ├── ... (共 30 个)
├── utils/
│   ├── dispatcher.py       ← 本模块
│   └── DISPATCHER_README.md ← 本文档
├── scripts/
│   └── build_docx.py
├── references/
└── examples/
```

---

## 3. CLI 用法

### 3.1 关键词匹配（最快路径）

```bash
# 返回 top 3 候选
python3 utils/dispatcher.py "国家级项目立项逻辑评测"

# 返回 top 5
python3 utils/dispatcher.py "入团申请书" -n 5

# 以 JSON 输出（便于上层 agent 解析）
python3 utils/dispatcher.py "暑期三下乡调研" --json
```

### 3.2 交互式决策树

```bash
python3 utils/dispatcher.py -i
```

进入 CLI 问答，逐题选择，最终给出叶子节点推荐的子 skill。支持 `q` 退出、`b` 回上一题。

### 3.3 列出全部子 skill

```bash
python3 utils/dispatcher.py --list            # 友好分组打印
python3 utils/dispatcher.py --list --json     # JSON 输出
```

### 3.4 查看某子 skill 详情

```bash
python3 utils/dispatcher.py --info national_project_eval
```

### 3.5 自检（验证 index.json 与磁盘目录一致）

```bash
python3 utils/dispatcher.py --selfcheck
```

输出 `missing_in_index`（磁盘有但索引漏）与 `missing_on_disk`（索引有但磁盘无），
返回码 0 表示一致，1 表示有差异。

---

## 4. Python API 用法

```python
from utils.dispatcher import Dispatcher

d = Dispatcher()                              # 自动加载 ../index.json

# 关键词匹配
top3 = d.dispatch("国家级项目立项逻辑评测")              # 默认 top 3
for r in top3:
    print(r["name"], r["display_name"], r["score"], r["matched"])

# 自定义 top N
top5 = d.dispatch("保研推免申请书", top_n=5)

# 关键词匹配原始结果（含全部候选+分数）
all_candidates = d.keyword_match("三下乡")

# 交互式
d.interactive_dispatch()

# 列出全部 / 查看详情 / 自检
d.list_all()
d.info("youth_league_application")
d.selfcheck()
```

---

## 5. 决策树结构

决策树共 11 个节点（Q1 入口 + 9 个二级节点 + Q10 公派留学），最大深度 2 层，叶子节点直接给出候选子 skill name。

```
Q1 (类型?)
├── scholarship   → Q2 (国奖/励志/校奖/企业/单项/助学金?)
├── honor         → Q3 (优秀学生/毕业生/班干部/文明/班集体/毕设评优?)
├── political     → Q4 (入团/评优/汇报/入团?)
├── research      → Q5 (大创创新/创业训练/创业实践/校级/院级?)
├── competition   → Q6 (挑战杯/互联网+主赛道/互联网+红旅?)
├── practice      → Q7 (社会调查/支教/政策宣讲/科技服务/西部计划?)
├── military      → Q9 (应征入伍?)
├── study_abroad  → Q10 (CSC公派/交流项目?)
└── other         → Q8 (保研/选调生/转专业?)
```

每个节点的 `options` 含 `label`（人类可读）/ `value`（程序值）/ `next`（下一节点 id）
或 `skills`（叶子节点时直接列出候选子 skill name）。

节点定义见 `dispatcher.py` 顶部 `DECISION_TREE` 常量，可在不修改类逻辑的前提下直接
增删选项。

---

## 6. 关键词匹配打分规则

`keyword_match(text)` 对每个子 skill 加权打分：

| 命中项           | 加分 | 说明 |
|------------------|------|------|
| `name` 命中       | +3   | 子 skill 英文名出现在用户文本 |
| `display_name` 命中 | +4 | 中文显示名完整出现 |
| `trigger` 命中    | +2   | 每个 trigger 关键词命中各 +2 |
| `category` 命中   | +1~2 | 大类关键词命中（每类最多 +2） |

分数 ≥ 1 的候选项进入排序，按分数降序、name 字母序兜底，取 top N 返回。

---

## 7. selfcheck：保持 index.json 与磁盘一致

每次新增/删除子 skill 后，运行：

```bash
python3 utils/dispatcher.py --selfcheck
```

selfcheck 会区分「真实子 skill」（含 SKILL.md 的目录）与「空 placeholder 目录」（无 SKILL.md），
前者计入 `disk_count`，后者归类到 `empty_placeholders` 不计入 missing 列表。

若有差异，会列出 `missing_in_index`（磁盘有 SKILL.md 但索引漏）与 `missing_on_disk`（索引有但磁盘无），
需手动同步 `index.json` 与 `version.json`。

T40 首次 selfcheck 即发现 5 个未纳入索引的子 skill（military_enlistment/csc_scholarship/
exchange_program/internet_plus_red_tour/outstanding_thesis），全部补入。

---

## 8. 扩展指南

### 8.1 新增子 skill

1. 在 `subskills/<new_name>/` 下创建 `SKILL.md` 与 `build.py`
2. 在 `index.json` 的 `skills` 数组追加一项（含全部必填字段）
3. 在 `version.json` 的 `skills` 数组追加简版记录，并更新 `total_skills` / `total_lines`
   / `categories_breakdown`
4. 在 `dispatcher.py` 的 `DECISION_TREE` 相关节点追加 option，或在
   `_FALLBACK_SKILLS` 追加 fallback 记录
5. 运行 `python3 utils/dispatcher.py --selfcheck` 确认一致

### 8.2 新增大类

1. 在 `dispatcher.py` 的 `CATEGORY_DISPLAY` 与 `CATEGORY_KEYWORDS` 追加新类
2. 在 `DECISION_TREE.Q1.options` 追加选项，指向新二级节点
3. 在 `index.json.categories` 与 `version.json.categories_breakdown` 追加新类

### 8.3 调整打分权重

修改 `keyword_match` 中的加分常量（name +3 / display_name +4 / trigger +2 / category +1~2），
权重越高代表该项越能精确识别子 skill。

---

## 9. 依赖与兼容性

- Python 3.8+（使用 `from __future__ import annotations` 与 `typing.Optional[Path]`）
- 仅依赖标准库：`json / os / sys / re / argparse / datetime / pathlib / typing`
- 无第三方依赖，可在任意 sandbox 直接运行

---

## 10. 常见问题

**Q1: 用户输入"我要写申报书"，没具体类型，怎么办？**
A: `keyword_match` 会因命中"申报书"这个泛词而匹配多个子 skill（display_name 含"申请"），
建议此时改用 `interactive_dispatch()` 走决策树。

**Q2: top 3 里没有用户想要的子 skill，怎么办？**
A: 检查 `index.json` 中该子 skill 的 `triggers` 是否覆盖用户常用说法；或在
`_FALLBACK_SKILLS` 同步补充 triggers。

**Q3: index.json 不存在时还能用吗？**
A: 可以。`Dispatcher.__init__` 会 fallback 到 `_FALLBACK_SKILLS`（30 个子 skill 的精简元数据），
保证基本可用，但路径字段为空，需另行处理。

**Q4: 能否被上层 LLM agent 调用？**
A: 可以。推荐 `--json` 模式输出，结构化字段含 `name/display_name/category/description/
score/matched/skill_md_path/build_py_path`，agent 可直接读取 `skill_md_path` 指向的
SKILL.md 并按其指引生成 docx。

---

## 11. 与父 skill SKILL.md 的关系

父 skill `SKILL.md` 描述整个项目（30 个子 skill 的总入口）。本 dispatcher 是父 skill
的**分流引擎**：父 skill 收到用户输入后，先调 `Dispatcher.dispatch()` 得到 top 3 候选，
再用候选的 `skill_md_path` 加载具体子 skill 的 SKILL.md，按其指引完成 docx 生成。

---

## 12. 版本历史

- **v2.0 (2025-05-20, T40)**：初版，含 5 级决策树（Q1~Q10，11 节点）+ 关键词匹配 + 交互式 CLI + selfcheck（区分真实子 skill 与空 placeholder）+ index.json（35 子 skill）+ version.json（总行数 51690）+ 本 README。dispatcher.py 837 行，覆盖 35 个子 skill。
