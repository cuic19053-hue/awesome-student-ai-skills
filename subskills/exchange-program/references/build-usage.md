# §13 build.py 接口说明（必加章节 8）

> 从 `subskills/exchange-program/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要调用 build.py 或了解接口参数时。

### 13.1 build.py 接口概览

build.py 位于 `/home/z/my-project/skills/awesome-student-ai-skills/subskills/exchange_program/build.py`，提供 CLI 接口生成交流项目申请书 docx。

**核心类**：`ExchangeProgramDocBuilder`

**主构建方法**：`build(data: Dict[str, Any], output_path: str) -> str`

**编排顺序**：标题 → 称呼 → 开头 → 个人基本情况 → 交流动机 → 学习计划 → 文化交流意愿 → 安全保障 → 结尾 → 落款

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
- `--data`：数据 JSON 文件路径（与 `--demo` 二选一）
- `--out`：输出 docx 文件路径（必填）
- `--demo`：使用内置示例数据生成演示文档

### 13.3 文档格式规范

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

### 13.4 内部方法清单

| 方法 | 功能 | 字段消费 |
|------|------|---------|
| `_add_title` | 标题（固定"交流项目申请书"） | - |
| `_add_salutation` | 称呼 | salutation |
| `_add_opening` | 开头（身份 + 申请事项 + 汇报句） | opening / name / current_college / current_major / grade / target_university / exchange_duration |
| `_add_basic_info` | 个人基本情况 | basic_info / current_gpa / current_weighted_avg / current_rank / current_core_courses / language_score / language_breakdown |
| `_add_motivation` | 交流动机（4 维度） | motivation / motivation_academic / motivation_vision / motivation_language / motivation_career |
| `_add_learning_plan` | 学习计划（3 阶段 + 表格） | learning_plan / prep_plan / abroad_plan / return_plan / weekly_schedule / study_plan_table |
| `_add_target_courses_table` | 目标课程表 | target_courses |
| `_add_target_teachers_info` | 目标导师信息 | target_teachers |
| `_add_cultural_exchange` | 文化交流意愿（3 维度） | cultural_exchange / cultural_integration / cultural_promotion / academic_exchange |
| `_add_safety` | 安全保障（4 维度） | safety / safety_legal / safety_insurance / safety_report / safety_emergency |
| `_add_ending` | 结尾（朴素表态 + 此致敬礼） | ending |
| `_add_signature` | 落款 | name / apply_date |
| `_validate_data` | 数据校验（返回 warnings） | 全字段 |

### 13.5 字段消费规则

- **整段覆盖字段优先**：若 `opening` / `basic_info` / `motivation` / `learning_plan` / `cultural_exchange` / `safety` / `ending` 任一提供非空字符串，则直接使用，跳过模板拼装
- **4 维度动机切换**：`motivation` 整段优先；否则按 4 维度拼装，缺维度则跳过
- **3 阶段学习计划切换**：`learning_plan` 整段优先；否则按 3 阶段拼装，缺阶段则跳过
- **数组字段缺失处理**：`current_core_courses` / `target_courses` / `target_teachers` / `study_plan_table` 缺失则省略对应表格
- **必填字段警告**：P0 字段缺失触发 warning，但不阻断生成

### 13.6 同步更新清单

本 skill build.py 已实现以下功能，无需后续同步：
1. ✅ 3 类项目切换（school / college / csc）通过字段 `exchange_type` 标识
2. ✅ 4 维度交流动机（学术深化 / 视野拓展 / 语言提升 / 职业规划）
3. ✅ 3 阶段学习计划（行前准备 / 在外学习 / 归国总结）+ 学习计划表
4. ✅ 3 档字数版本（1500 / 2000 / 2500）通过字段完整度自然达到
5. ✅ 文化交流意愿 3 维度（融入 / 传播 / 学术交流）
6. ✅ 安全保障 4 维度（法律 / 保险 / 汇报 / 预案）
7. ✅ 现专业课程表（4~6 门）+ 目标院校课程表（≥5 门）
8. ✅ 数据校验（P0 字段 + 排名基数 + 课程数 + 师资数 + 4 维度动机 + 3 阶段学习计划 + 4 维度安全保障）

---

