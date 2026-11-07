# §12 build.py 接口说明（必加章节 8）

> 从 `subskills/major-transfer/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要调用 build.py 或了解接口参数时。

### 12.1 build.py 接口概览

build.py 位于 `/home/z/my-project/skills/awesome-student-ai-skills/subskills/major_transfer/build.py`，提供 CLI 接口生成转专业申请书 docx。

**核心类**：`MajorTransferDocBuilder`

**主构建方法**：`build(data: Dict[str, Any], output_path: str) -> str`

**编排顺序**：标题 → 称呼 → 开头 → 个人基本情况 → 现专业学习 → 转专业原因 → 目标专业认知 → 转后规划 → 结尾 → 落款

### 12.2 CLI 调用方式

**基础调用（用户提供 data.json）**：
```bash
python build.py --data data.json --out output.docx
```

**演示模式（使用内置示例数据）**：
```bash
python build.py --demo --out demo.docx
```

**参数说明**：
- `--data`：数据 JSON 文件路径（与 `--demo` 二选一）
- `--out`：输出 docx 文件路径（必填）
- `--demo`：使用内置示例数据生成演示文档

### 12.3 文档格式规范

| 项 | 规范 |
|----|------|
| 纸张 | A4（21.0 × 29.7 cm） |
| 页边距 | 上下 2.54cm，左右 2.5cm |
| 标题 | 黑体二号（22pt），居中，段前后 12pt |
| 称呼 | 顶格，宋体小四（12pt），全角冒号 |
| 正文 | 宋体小四（12pt），1.5 倍行距，首行缩进 2 字符 |
| 小节标题 | 黑体小四加粗（12pt），首行缩进 2 字符 |
| 表格 | 宋体五号（10.5pt），居中，表头加粗 |
| "此致" | 另起一行，首行缩进 2 字符 |
| "敬礼！" | 另起一行，顶格，后接感叹号 |
| 落款 | 右对齐，含申请人 + 日期 |
| 页脚 | 居中页码，宋体五号 |

### 12.4 内部方法清单

| 方法 | 功能 | 字段消费 |
|------|------|---------|
| `_add_title` | 标题（按 transfer_reason_type 动态填充"转专业申请书"） | - |
| `_add_salutation` | 称呼 | salutation |
| `_add_opening` | 开头（身份 + 申请事项 + 汇报句） | opening / name / current_college / current_major / grade / target_college / target_major |
| `_add_basic_info` | 个人基本情况 | basic_info / gaokao_year / gaokao_score / admission_mode / original_choice / current_reason |
| `_add_current_study` | 现专业学习（含课程表） | current_study / current_gpa / current_weighted_avg / current_rank / current_core_courses / cross_courses |
| `_add_transfer_reason` | 转专业原因（按 3 类切换） | transfer_reason / transfer_reason_type / interest_* / academic_* / career_* |
| `_add_target_understanding` | 目标专业认知（4 维度） | target_understanding / target_courses / target_teachers / target_employment / target_competitions |
| `_add_future_plan` | 转后规划（含学习计划表） | future_plan / short_term_plan / mid_term_plan / long_term_plan / study_plan_table |
| `_add_ending` | 结尾（朴素表态 + 此致敬礼） | ending |
| `_add_signature` | 落款 | name / apply_date |
| `_validate_data` | 数据校验（返回 warnings） | 全字段 |

### 12.5 字段消费规则

- **整段覆盖字段优先**：若 `opening` / `basic_info` / `current_study` / `transfer_reason` / `target_understanding` / `future_plan` / `ending` 任一提供非空字符串，则直接使用，跳过模板拼装
- **3 类原因切换**：`transfer_reason_type` 为 `interest` / `academic` / `career` 时，分别调用 `_build_interest_reason` / `_build_academic_reason` / `_build_career_reason` 子方法
- **数组字段缺失处理**：`current_core_courses` / `target_courses` / `target_teachers` / `target_competitions` / `study_plan_table` 缺失则省略对应表格
- **必填字段警告**：P0 字段缺失触发 warning，但不阻断生成

### 12.6 同步更新清单

本 skill build.py 已实现以下功能，无需后续同步：
1. ✅ 3 类原因切换（interest / academic / career）
2. ✅ 4 维度目标专业认知（专业课程/师资力量/就业前景/学科竞赛）
3. ✅ 3 档字数版本（800/1000/1500）通过字段完整度自然达到
4. ✅ 学习计划表（短/中/长期 3 行）
5. ✅ 现专业课程表（4~6 门）
6. ✅ 交叉课程高亮（学业优势型）
7. ✅ 数据校验（P0 字段 + 排名基数 + 课程数 + 师资数 + 4 维度齐全）

---

