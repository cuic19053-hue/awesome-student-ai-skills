# §13 build.py 接口 + 质检清单（必加章节 8/9/10）

> 从 `subskills/outstanding-cadre/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要调用 build.py 或了解接口参数时。

### 13.1 build.py 接口概览

build.py 位于 `/home/z/my-project/skills/awesome-student-ai-skills/subskills/outstanding_cadre/build.py`，提供 CLI 接口生成申请书 docx。

**核心类**：`ApplicationDocBuilder`

**主构建方法**：`build(data: Dict[str, Any], output_path: str) -> str`

**编排顺序**：标题 → 称呼 → 开头 → 一、个人基本情况 → 二、履职情况（含履职表 + 量化清单 + 服务案例）→ 三、工作成绩 → 四、不足与改进 → 结尾 → 落款

### 13.2 CLI 调用方式

**基础调用（用户提供 data.json）**：
```bash
python build.py --data data.json --out output.docx
```

**演示模式（使用内置示例数据）**：
```bash
python build.py --demo --out demo.docx
```

**参数说明**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `--data` | string | 否（与 --demo 二选一） | 数据 JSON 文件路径 |
| `--out` | string | ✅ | 输出 docx 文件路径 |
| `--demo` | flag | 否 | 使用内置示例数据生成演示文档 |

### 13.3 build.py 字段读取逻辑

build.py 通过 `_get()` 与 `_get_list()` 方法读取字段，关键读取逻辑如下：

| build.py 方法 | 读取字段 | 用途 |
|-------------|---------|------|
| `_add_title()` | honor_title | 决定标题（"优秀班干部申请书"或"优秀学生干部申请书"） |
| `_add_salutation()` | salutation | 称呼（默认"尊敬的学院领导、评审委员会："） |
| `_add_opening()` | name/college/major/grade/cadre_position/tenure_start/tenure_end/gpa/rank/honor_title | 开头身份句与核心数据 |
| `_add_basic_info()` | cadre_position/cadre_level/tenure_start/tenure_end/secondary_position/gpa/weighted_avg/rank/course_count/high_score_count/political_status/party_history | 个人基本情况段 |
| `_add_duty_performance()` | cadre_position/core_duties(可推断)/activity_count/service_hours + position_history + duty_performances + service_cases | 履职情况段（含两表 + 服务案例） |
| `_add_work_achievements()` | class_achievements/honors/cross_position | 工作成绩段 |
| `_add_shortcomings_section()` | shortcomings/improvements | 不足与改进段 |
| `_add_ending()` | ending | 结尾段（默认模板含"以上是我本学年的基本情况"） |
| `_add_position_table()` | position_history | 学生干部履职表 |
| `_add_duty_quantitative_table()` | duty_performances | 履职量化清单表 |

### 13.4 build.py 整段覆盖字段优先级

build.py 支持"整段覆盖"机制：若用户提供 `opening/basic_info/duty_performance/work_achievements/shortcomings_section/ending` 字段，则跳过模板拼装直接使用。**优先级**：整段覆盖字段 > 模板拼装。

**履职情况段处理**：若用户提供 `duty_performance` 整段覆盖字段，则直接使用该文本，不再插入学生干部履职表与履职量化清单表（用户须自行在文本中描述）。**建议不提供整段覆盖**，让 build.py 自动插入两表，保证表格规范。

### 13.5 build.py 数据校验（_validate_data）

build.py 内置 `_validate_data()` 方法，对缺失字段仅打印警告不阻断生成。校验项包括：

| 校验项 | 警告条件 | 警告信息 |
|-------|---------|---------|
| P0 必采字段 | name/college/major/grade/cadre_position/tenure_start/tenure_end/gpa/rank 任一缺失 | "缺少 {label}（{key}）" |
| 学生干部履职表 | position_history 缺失或不足 1 条 | "缺少 position_history 学生干部履职表（至少 1 条）" |
| 履职量化清单 | duty_performances 4 维度任一缺失 | "缺少 duty_performances.{key} 履职量化数据" |
| 不足与改进 | shortcomings 或 improvements 缺失 | "缺少 shortcomings 不足列表或 improvements 改进措施列表" |
| 排名校验 | rank 无基数且无 rank_total | "排名 '{rank}' 缺基数，应为 'X/N' 格式" |
| 学业门槛 | 排名前 X% 超过 50% | "排名前 X% 不满足优秀班干部前 50% 门槛" |
| 主干课程 | core_courses 缺失或不足 4 门 | "缺少 core_courses 主干课程表"或"主干课程仅 N 门，建议 4~6 门" |
| 任期时长 | tenure_start 与 tenure_end 间隔不足 8 个月 | "任期时长不足 1 学年（约 8 个月），请核对" |

### 13.6 质检清单（生成后必查，30 项）

生成 docx 后，按以下 30 项逐项检查。任一不达标返回撰写阶段修改：

#### 格式检查（10 项）

1. 标题按 honor_title 动态填充，黑体二号居中
2. 称呼顶格"尊敬的学院领导、评审委员会："，全角冒号
3. 正文宋体小四，1.5 倍行距，首行缩进 2 字符
4. 小节标题"一、个人基本情况"等，黑体小四加粗
5. 学生干部履职表 4 列（职务 / 任期 / 主要工作 / 成效），至少 1 条
6. 履职量化清单表 2 列（维度 / 量化数据），4 行（活动数/服务时长/获奖情况/同学评议）
7. "此致"另起一行空两格，"敬礼！"另起一行顶格
8. 落款右对齐，含"申请人：XXX"+ 日期两行
9. 页脚居中页码（宋体五号）
10. 全文无英文标点（除"CET-4""GPA"等专有名词）

#### 内容检查（12 项）

11. 开头含身份 + 职务 + GPA + 排名 + 申报 + 进入句
12. 个人基本情况含身份 + 职务与任期 + 学业 + 政治面貌
13. 履职情况含职务履职概况 + 履职表 + 量化清单 + 服务案例
14. 学生干部履职表 4 列齐全，每条含量化成效（数据/荣誉/影响至少 1 项）
15. 履职量化清单 4 维度齐全（活动数/服务时长/获奖情况/同学评议）
16. 服务同学段含 2-3 个具体案例（背景 + 行动 + 成效）
17. 工作成绩含班级整体成效 + 个人荣誉 + 跨职务统筹（多职务者）
18. 不足与改进含 1-2 条具体不足 + 对应改进措施 + 朴素表态
19. 结尾含"以上是我本学年的基本情况"+ 朴素表态 + 恳请评审
20. 全文无形容词代替事实（"积极组织""深受好评"）
21. 全文无抒情开头（"时光荏苒""岁月如梭"）
22. 全文无"恳请领导批准""完全符合评选条件"

#### 字数与学年口径检查（8 项）

23. 履职表数据与量化清单数据完全一致
24. 正文总字数 1500~2000 字（短版 1000 字；长版 2000 字）
25. 个人基本情况 300~400 字（短版 200~250；长版 400~450）
26. 履职情况 600~800 字（短版 400~450；长版 800~850）
27. 工作成绩 375~500 字（短版 200~250；长版 500~550）
28. 不足与改进 225~300 字（短版 100~150；长版 280~320）
29. 结尾 60~100 字（短版 50~70；长版 80~100）
30. 全文无 4 年综合数据（"大学 4 年加权 GPA""4 年累计"等）

### 13.7 字数自检脚本

```bash
python -c "
from docx import Document
d = Document('output.docx')
text = ''.join(p.text for p in d.paragraphs)
print(f'正文字数：{len(text)}')
assert 1500 <= len(text) <= 2000, f'字数 {len(text)} 不在 1500~2000 区间'
print('字数达标')
"
```

### 13.8 生成后人工补充

- 在落款"申请人：XXX"上方留 1 行手写签名空位（打印后手签）
- 附件材料（成绩单原件、学生干部任命书、班级评议表、荣誉证书复印件）单独装订
- 学校评审系统提交时一并上传 docx 与附件扫描件

### 13.9 输出文件命名建议

- 院级优秀班干部：`{name}_优秀班干部申请书_{apply_year}.docx`（如 `张明_优秀班干部申请书_2024-2025.docx`）
- 校级优秀学生干部：`{name}_优秀学生干部申请书_{apply_year}.docx`
- 校级优秀班委：`{name}_优秀班委申请书_{apply_year}.docx`

---

